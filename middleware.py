"""
Middleware para Mengão Monitor 🦞
CORS, rate limiting e logging de requests.
"""

import time
import logging
from functools import wraps
from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from flask import request, jsonify, Response, g
from werkzeug.wrappers import Response as WerkzeugResponse


@dataclass
class RateLimitRule:
    """Regra de rate limiting."""
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_limit: int = 10  # requests em 10 segundos
    burst_window: int = 10  # segundos


class RateLimiter:
    """Rate limiter por IP e endpoint."""
    
    def __init__(self, rule: Optional[RateLimitRule] = None):
        self.rule = rule or RateLimitRule()
        self._requests: Dict[str, List[float]] = {}  # ip -> [timestamps]
        self._burst: Dict[str, List[float]] = {}     # ip -> [timestamps]
        self._blocked: Dict[str, datetime] = {}      # ip -> blocked_until
    
    def _cleanup_old(self, timestamps: List[float], window_seconds: int) -> List[float]:
        """Remove timestamps antigos."""
        cutoff = time.time() - window_seconds
        return [ts for ts in timestamps if ts > cutoff]
    
    def _get_client_ip(self) -> str:
        """Obtém IP do cliente considerando proxies."""
        if request.headers.get('X-Forwarded-For'):
            return request.headers['X-Forwarded-For'].split(',')[0].strip()
        return request.remote_addr or 'unknown'
    
    def is_allowed(self, endpoint: str = None) -> tuple[bool, Optional[Dict]]:
        """
        Verifica se request é permitido.
        
        Returns:
            (allowed, headers_dict)
        """
        client_ip = self._get_client_ip()
        key = f"{client_ip}:{endpoint or 'global'}"
        
        # Verifica se IP está bloqueado
        if client_ip in self._blocked:
            if datetime.now() < self._blocked[client_ip]:
                return False, {
                    'X-RateLimit-Blocked': 'true',
                    'X-RateLimit-Blocked-Until': self._blocked[client_ip].isoformat()
                }
            else:
                del self._blocked[client_ip]
        
        now = time.time()
        
        # Inicializa listas se necessário
        if key not in self._requests:
            self._requests[key] = []
        if key not in self._burst:
            self._burst[key] = []
        
        # Limpa timestamps antigos
        self._requests[key] = self._cleanup_old(self._requests[key], 3600)  # 1 hora
        self._burst[key] = self._cleanup_old(self._burst[key], self.rule.burst_window)
        
        # Verifica limites
        minute_count = len([ts for ts in self._requests[key] if ts > now - 60])
        hour_count = len(self._requests[key])
        burst_count = len(self._burst[key])
        
        # Headers informativos
        headers = {
            'X-RateLimit-Limit-Minute': str(self.rule.requests_per_minute),
            'X-RateLimit-Remaining-Minute': str(max(0, self.rule.requests_per_minute - minute_count)),
            'X-RateLimit-Limit-Hour': str(self.rule.requests_per_hour),
            'X-RateLimit-Remaining-Hour': str(max(0, self.rule.requests_per_hour - hour_count)),
        }
        
        # Verifica se excedeu limites
        if minute_count >= self.rule.requests_per_minute:
            headers['X-RateLimit-Reset-Minute'] = str(int(now + 60))
            return False, headers
        
        if hour_count >= self.rule.requests_per_hour:
            headers['X-RateLimit-Reset-Hour'] = str(int(now + 3600))
            return False, headers
        
        if burst_count >= self.rule.burst_limit:
            # Bloqueia IP por 1 minuto se exceder burst
            self._blocked[client_ip] = datetime.now() + timedelta(minutes=1)
            return False, headers
        
        # Registra request
        self._requests[key].append(now)
        self._burst[key].append(now)
        
        return True, headers


class CORSMiddleware:
    """Middleware para CORS."""
    
    def __init__(
        self,
        allowed_origins: List[str] = None,
        allowed_methods: List[str] = None,
        allowed_headers: List[str] = None,
        max_age: int = 86400,
        allow_credentials: bool = False
    ):
        self.allowed_origins = allowed_origins or ['*']
        self.allowed_methods = allowed_methods or ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
        self.allowed_headers = allowed_headers or ['Content-Type', 'Authorization', 'X-Requested-With']
        self.max_age = max_age
        self.allow_credentials = allow_credentials
    
    def process_response(self, response: WerkzeugResponse) -> WerkzeugResponse:
        """Adiciona headers CORS à response."""
        origin = request.headers.get('Origin', '*')
        
        # Verifica se origem é permitida
        if '*' in self.allowed_origins or origin in self.allowed_origins:
            response.headers['Access-Control-Allow-Origin'] = origin
        else:
            response.headers['Access-Control-Allow-Origin'] = 'null'
        
        response.headers['Access-Control-Allow-Methods'] = ', '.join(self.allowed_methods)
        response.headers['Access-Control-Allow-Headers'] = ', '.join(self.allowed_headers)
        response.headers['Access-Control-Max-Age'] = str(self.max_age)
        
        if self.allow_credentials:
            response.headers['Access-Control-Allow-Credentials'] = 'true'
        
        return response


class RequestLogger:
    """Logger de requests HTTP."""
    
    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger('middleware')
    
    def log_request(self, response: WerkzeugResponse) -> WerkzeugResponse:
        """Loga informações do request."""
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        
        log_data = {
            'method': request.method,
            'path': request.path,
            'status': response.status_code,
            'ip': client_ip,
            'user_agent': request.headers.get('User-Agent', 'unknown'),
            'duration_ms': getattr(g, 'request_duration', 0),
        }
        
        if response.status_code >= 400:
            self.logger.warning(f"HTTP {response.status_code} {request.method} {request.path}", extra=log_data)
        else:
            self.logger.info(f"HTTP {response.status_code} {request.method} {request.path}", extra=log_data)
        
        return response


# Instâncias globais
rate_limiter = RateLimiter()
cors_middleware = CORSMiddleware()
request_logger = RequestLogger()


def setup_middleware(app, config: dict = None):
    """Configura middleware na aplicação Flask."""
    config = config or {}
    
    # Configura rate limiter
    if 'rate_limit' in config:
        rule = RateLimitRule(**config['rate_limit'])
        global rate_limiter
        rate_limiter = RateLimiter(rule)
    
    # Configura CORS
    if 'cors' in config:
        global cors_middleware
        cors_middleware = CORSMiddleware(**config['cors'])
    
    # Registra handlers
    @app.before_request
    def before_request():
        """Executa antes de cada request."""
        g.request_start = time.time()
        
        # Rate limiting para endpoints da API
        if request.path.startswith('/api/'):
            allowed, headers = rate_limiter.is_allowed(request.path)
            if not allowed:
                response = jsonify({
                    'error': 'Rate limit exceeded',
                    'message': 'Too many requests. Please try again later.'
                })
                response.status_code = 429
                for key, value in headers.items():
                    response.headers[key] = value
                return response
    
    @app.after_request
    def after_request(response):
        """Executa após cada request."""
        # Calcula duração
        if hasattr(g, 'request_start'):
            g.request_duration = (time.time() - g.request_start) * 1000
        
        # CORS
        response = cors_middleware.process_response(response)
        
        # Logging
        response = request_logger.log_request(response)
        
        # Rate limit headers (mesmo para requests permitidos)
        if request.path.startswith('/api/'):
            allowed, headers = rate_limiter.is_allowed(request.path)
            for key, value in headers.items():
                response.headers[key] = value
        
        return response
    
    return app


def rate_limit(endpoint: str = None, rule: RateLimitRule = None):
    """Decorator para rate limiting específico de endpoint."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            limiter = RateLimiter(rule) if rule else rate_limiter
            allowed, headers = limiter.is_allowed(endpoint or request.path)
            
            if not allowed:
                response = jsonify({
                    'error': 'Rate limit exceeded',
                    'message': 'Too many requests. Please try again later.'
                })
                response.status_code = 429
                for key, value in headers.items():
                    response.headers[key] = value
                return response
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def cors_origin(origins: List[str]):
    """Decorator para CORS específico de endpoint."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            response = f(*args, **kwargs)
            
            origin = request.headers.get('Origin')
            if origin and (origin in origins or '*' in origins):
                if isinstance(response, Response):
                    response.headers['Access-Control-Allow-Origin'] = origin
            
            return response
        return decorated_function
    return decorator
