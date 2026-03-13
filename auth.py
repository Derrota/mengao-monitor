"""
Autenticação para Mengão Monitor 🦞
Token-based authentication para proteger endpoints sensíveis.
"""

import hashlib
import hmac
import secrets
import time
from functools import wraps
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from flask import request, jsonify, Response


@dataclass
class AuthToken:
    """Token de autenticação."""
    token: str
    name: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    scopes: List[str] = field(default_factory=list)  # ["read", "write", "admin"]
    enabled: bool = True
    
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at
    
    def has_scope(self, scope: str) -> bool:
        if "admin" in self.scopes:
            return True
        return scope in self.scopes
    
    def to_dict(self) -> dict:
        return {
            "token": self.token[:8] + "..." + self.token[-4:],  # Mascarado
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "scopes": self.scopes,
            "enabled": self.enabled
        }


class AuthManager:
    """Gerenciador de autenticação."""
    
    def __init__(self, secret_key: Optional[str] = None):
        self.secret_key = secret_key or secrets.token_hex(32)
        self.tokens: Dict[str, AuthToken] = {}
        self._failed_attempts: Dict[str, List[float]] = {}  # IP -> timestamps
        self._max_attempts = 10
        self._lockout_seconds = 300  # 5 minutos
    
    def create_token(
        self, 
        name: str, 
        scopes: List[str] = None,
        expires_hours: Optional[int] = None
    ) -> AuthToken:
        """Cria novo token de autenticação."""
        token_str = f"mm_{secrets.token_urlsafe(32)}"
        
        expires_at = None
        if expires_hours:
            expires_at = datetime.now() + timedelta(hours=expires_hours)
        
        token = AuthToken(
            token=token_str,
            name=name,
            created_at=datetime.now(),
            expires_at=expires_at,
            scopes=scopes or ["read"],
            enabled=True
        )
        
        self.tokens[token_str] = token
        return token
    
    def revoke_token(self, token_str: str) -> bool:
        """Revoga um token."""
        if token_str in self.tokens:
            self.tokens[token_str].enabled = False
            return True
        return False
    
    def delete_token(self, token_str: str) -> bool:
        """Remove um token permanentemente."""
        if token_str in self.tokens:
            del self.tokens[token_str]
            return True
        return False
    
    def validate_token(self, token_str: str) -> Optional[AuthToken]:
        """Valida um token."""
        token = self.tokens.get(token_str)
        if token is None:
            return None
        if not token.enabled:
            return None
        if token.is_expired():
            return None
        return token
    
    def is_ip_locked(self, ip: str) -> bool:
        """Verifica se IP está bloqueado por tentativas falhas."""
        if ip not in self._failed_attempts:
            return False
        
        # Limpa tentativas antigas
        cutoff = time.time() - self._lockout_seconds
        self._failed_attempts[ip] = [
            ts for ts in self._failed_attempts[ip] if ts > cutoff
        ]
        
        return len(self._failed_attempts[ip]) >= self._max_attempts
    
    def record_failed_attempt(self, ip: str):
        """Registra tentativa falha de autenticação."""
        if ip not in self._failed_attempts:
            self._failed_attempts[ip] = []
        self._failed_attempts[ip].append(time.time())
    
    def get_stats(self) -> dict:
        """Estatísticas do gerenciador de auth."""
        active_tokens = sum(1 for t in self.tokens.values() if t.enabled and not t.is_expired())
        expired_tokens = sum(1 for t in self.tokens.values() if t.is_expired())
        revoked_tokens = sum(1 for t in self.tokens.values() if not t.enabled)
        
        return {
            "total_tokens": len(self.tokens),
            "active_tokens": active_tokens,
            "expired_tokens": expired_tokens,
            "revoked_tokens": revoked_tokens,
            "locked_ips": len([
                ip for ip in self._failed_attempts 
                if self.is_ip_locked(ip)
            ])
        }
    
    def list_tokens(self) -> List[dict]:
        """Lista todos os tokens (mascarados)."""
        return [t.to_dict() for t in self.tokens.values()]


# Instância global
auth_manager = AuthManager()


def require_auth(scope: str = "read"):
    """Decorator para proteger endpoints com autenticação."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Verifica bloqueio de IP
            client_ip = request.remote_addr or "unknown"
            if auth_manager.is_ip_locked(client_ip):
                return jsonify({
                    "error": "Too many failed attempts. Try again later.",
                    "retry_after": auth_manager._lockout_seconds
                }), 429
            
            # Extrai token do header Authorization
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return jsonify({
                    "error": "Missing or invalid Authorization header",
                    "expected": "Bearer <token>"
                }), 401
            
            token_str = auth_header[7:]  # Remove "Bearer "
            token = auth_manager.validate_token(token_str)
            
            if token is None:
                auth_manager.record_failed_attempt(client_ip)
                return jsonify({"error": "Invalid or expired token"}), 401
            
            if not token.has_scope(scope):
                return jsonify({
                    "error": f"Insufficient permissions. Required scope: {scope}",
                    "token_scopes": token.scopes
                }), 403
            
            # Token válido, executa função
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator


def optional_auth(f):
    """Decorator para autenticação opcional (adiciona info se autenticado)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token_str = auth_header[7:]
            token = auth_manager.validate_token(token_str)
            if token:
                # Adiciona info do token ao request context
                request.auth_token = token
                request.authenticated = True
            else:
                request.auth_token = None
                request.authenticated = False
        else:
            request.auth_token = None
            request.authenticated = False
        
        return f(*args, **kwargs)
    return decorated_function
