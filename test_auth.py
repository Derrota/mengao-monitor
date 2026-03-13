"""
Testes para módulo de autenticação (auth.py) 🦞
"""

import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from auth import AuthToken, AuthManager, auth_manager, require_auth, optional_auth


class TestAuthToken:
    """Testes para AuthToken dataclass."""

    def test_token_creation(self):
        """Testa criação básica de token."""
        token = AuthToken(
            token="mm_test123",
            name="test",
            created_at=datetime.now(),
            scopes=["read", "write"]
        )
        
        assert token.token == "mm_test123"
        assert token.name == "test"
        assert token.scopes == ["read", "write"]
        assert token.enabled is True
        assert token.expires_at is None

    def test_token_not_expired_no_expiry(self):
        """Token sem expiração nunca expira."""
        token = AuthToken(
            token="mm_test",
            name="test",
            created_at=datetime.now()
        )
        
        assert token.is_expired() is False

    def test_token_not_expired_future(self):
        """Token com expiração futura não está expirado."""
        token = AuthToken(
            token="mm_test",
            name="test",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1)
        )
        
        assert token.is_expired() is False

    def test_token_expired(self):
        """Token expirado é detectado."""
        token = AuthToken(
            token="mm_test",
            name="test",
            created_at=datetime.now(),
            expires_at=datetime.now() - timedelta(hours=1)
        )
        
        assert token.is_expired() is True

    def test_has_scope_read(self):
        """Testa verificação de scope read."""
        token = AuthToken(
            token="mm_test",
            name="test",
            created_at=datetime.now(),
            scopes=["read"]
        )
        
        assert token.has_scope("read") is True
        assert token.has_scope("write") is False
        assert token.has_scope("admin") is False

    def test_has_scope_admin_overrides(self):
        """Admin tem acesso a todos os scopes."""
        token = AuthToken(
            token="mm_test",
            name="test",
            created_at=datetime.now(),
            scopes=["admin"]
        )
        
        assert token.has_scope("read") is True
        assert token.has_scope("write") is True
        assert token.has_scope("admin") is True
        assert token.has_scope("delete") is True

    def test_to_dict_masks_token(self):
        """to_dict() mascara o token."""
        token = AuthToken(
            token="mm_abcdefghijklmnop",
            name="test",
            created_at=datetime(2026, 3, 13, 10, 0),
            scopes=["read"]
        )
        
        d = token.to_dict()
        assert d["token"] == "mm_abcd...mnop"
        assert d["name"] == "test"
        assert d["scopes"] == ["read"]
        assert d["enabled"] is True


class TestAuthManager:
    """Testes para AuthManager."""

    def setup_method(self):
        """Setup para cada teste."""
        self.manager = AuthManager(secret_key="test_secret")

    def test_create_token(self):
        """Testa criação de token."""
        token = self.manager.create_token("test_user", scopes=["read", "write"])
        
        assert token.name == "test_user"
        assert token.scopes == ["read", "write"]
        assert token.token.startswith("mm_")
        assert token.enabled is True
        assert token.expires_at is None

    def test_create_token_with_expiry(self):
        """Testa criação de token com expiração."""
        token = self.manager.create_token(
            "temp_user",
            scopes=["read"],
            expires_hours=24
        )
        
        assert token.expires_at is not None
        assert token.expires_at > datetime.now()
        assert token.expires_at < datetime.now() + timedelta(hours=25)

    def test_validate_token_valid(self):
        """Testa validação de token válido."""
        token = self.manager.create_token("test")
        
        validated = self.manager.validate_token(token.token)
        assert validated is not None
        assert validated.name == "test"

    def test_validate_token_invalid(self):
        """Testa validação de token inexistente."""
        validated = self.manager.validate_token("mm_invalid")
        assert validated is None

    def test_validate_token_revoked(self):
        """Testa validação de token revogado."""
        token = self.manager.create_token("test")
        self.manager.revoke_token(token.token)
        
        validated = self.manager.validate_token(token.token)
        assert validated is None

    def test_validate_token_expired(self):
        """Testa validação de token expirado."""
        token = self.manager.create_token("test", expires_hours=-1)
        
        validated = self.manager.validate_token(token.token)
        assert validated is None

    def test_revoke_token(self):
        """Testa revogação de token."""
        token = self.manager.create_token("test")
        assert self.manager.revoke_token(token.token) is True
        assert token.enabled is False

    def test_revoke_nonexistent(self):
        """Testa revogação de token inexistente."""
        assert self.manager.revoke_token("mm_nope") is False

    def test_delete_token(self):
        """Testa remoção de token."""
        token = self.manager.create_token("test")
        assert self.manager.delete_token(token.token) is True
        assert token.token not in self.manager.tokens

    def test_delete_nonexistent(self):
        """Testa remoção de token inexistente."""
        assert self.manager.delete_token("mm_nope") is False

    def test_is_ip_locked_no_attempts(self):
        """IP sem tentativas não está bloqueado."""
        assert self.manager.is_ip_locked("192.168.1.1") is False

    def test_is_ip_locked_few_attempts(self):
        """IP com poucas tentativas não está bloqueado."""
        for _ in range(5):
            self.manager.record_failed_attempt("192.168.1.1")
        
        assert self.manager.is_ip_locked("192.168.1.1") is False

    def test_is_ip_locked_max_attempts(self):
        """IP com muitas tentativas é bloqueado."""
        for _ in range(10):
            self.manager.record_failed_attempt("192.168.1.1")
        
        assert self.manager.is_ip_locked("192.168.1.1") is True

    def test_is_ip_locked_different_ips(self):
        """Bloqueio é por IP."""
        for _ in range(10):
            self.manager.record_failed_attempt("192.168.1.1")
        
        assert self.manager.is_ip_locked("192.168.1.1") is True
        assert self.manager.is_ip_locked("192.168.1.2") is False

    def test_get_stats(self):
        """Testa estatísticas do manager."""
        # Cria tokens
        self.manager.create_token("active1")
        self.manager.create_token("active2")
        expired = self.manager.create_token("expired", expires_hours=-1)
        revoked = self.manager.create_token("revoked")
        self.manager.revoke_token(revoked.token)
        
        stats = self.manager.get_stats()
        
        assert stats["total_tokens"] == 4
        assert stats["active_tokens"] == 2
        assert stats["expired_tokens"] == 1
        assert stats["revoked_tokens"] == 1

    def test_list_tokens(self):
        """Testa listagem de tokens."""
        self.manager.create_token("user1")
        self.manager.create_token("user2")
        
        tokens = self.manager.list_tokens()
        assert len(tokens) == 2
        assert all("token" in t for t in tokens)
        assert all("name" in t for t in tokens)


class TestAuthDecorators:
    """Testes para decorators de autenticação."""

    def setup_method(self):
        """Setup para cada teste."""
        # Limpa tokens do manager global
        auth_manager.tokens.clear()
        auth_manager._failed_attempts.clear()

    def test_require_auth_no_header(self):
        """Endpoint protegido sem header retorna 401."""
        from flask import Flask
        app = Flask(__name__)
        
        @app.route("/protected")
        @require_auth("read")
        def protected():
            return "OK"
        
        with app.test_client() as client:
            response = client.get("/protected")
            assert response.status_code == 401
            assert b"Missing or invalid" in response.data

    def test_require_auth_invalid_token(self):
        """Endpoint protegido com token inválido retorna 401."""
        from flask import Flask
        app = Flask(__name__)
        
        @app.route("/protected")
        @require_auth("read")
        def protected():
            return "OK"
        
        with app.test_client() as client:
            response = client.get(
                "/protected",
                headers={"Authorization": "Bearer mm_invalid"}
            )
            assert response.status_code == 401
            assert b"Invalid or expired" in response.data

    def test_require_auth_valid_token(self):
        """Endpoint protegido com token válido retorna 200."""
        from flask import Flask
        app = Flask(__name__)
        
        token = auth_manager.create_token("test", scopes=["read"])
        
        @app.route("/protected")
        @require_auth("read")
        def protected():
            return "OK"
        
        with app.test_client() as client:
            response = client.get(
                "/protected",
                headers={"Authorization": f"Bearer {token.token}"}
            )
            assert response.status_code == 200

    def test_require_auth_insufficient_scope(self):
        """Token sem scope necessário retorna 403."""
        from flask import Flask
        app = Flask(__name__)
        
        token = auth_manager.create_token("test", scopes=["read"])
        
        @app.route("/admin")
        @require_auth("admin")
        def admin():
            return "OK"
        
        with app.test_client() as client:
            response = client.get(
                "/admin",
                headers={"Authorization": f"Bearer {token.token}"}
            )
            assert response.status_code == 403
            assert b"Insufficient permissions" in response.data

    def test_require_auth_locked_ip(self):
        """IP bloqueado retorna 429."""
        from flask import Flask
        app = Flask(__name__)
        
        # Bloqueia IP
        for _ in range(10):
            auth_manager.record_failed_attempt("127.0.0.1")
        
        @app.route("/protected")
        @require_auth("read")
        def protected():
            return "OK"
        
        with app.test_client() as client:
            response = client.get("/protected")
            assert response.status_code == 429
            assert b"Too many failed attempts" in response.data

    def test_optional_auth_no_header(self):
        """Auth opcional sem header funciona."""
        from flask import Flask
        app = Flask(__name__)
        
        @app.route("/optional")
        @optional_auth
        def optional():
            return f"authenticated={getattr(request, 'authenticated', False)}"
        
        with app.test_client() as client:
            response = client.get("/optional")
            assert response.status_code == 200
            assert b"authenticated=False" in response.data

    def test_optional_auth_with_valid_token(self):
        """Auth opcional com token válido adiciona info."""
        from flask import Flask
        from flask import request
        app = Flask(__name__)
        
        token = auth_manager.create_token("test")
        
        @app.route("/optional")
        @optional_auth
        def optional():
            return f"authenticated={request.authenticated}"
        
        with app.test_client() as client:
            response = client.get(
                "/optional",
                headers={"Authorization": f"Bearer {token.token}"}
            )
            assert response.status_code == 200
            assert b"authenticated=True" in response.data


class TestBruteForceProtection:
    """Testes para proteção contra brute force."""

    def setup_method(self):
        """Setup para cada teste."""
        auth_manager._failed_attempts.clear()

    def test_failed_attempts_recorded(self):
        """Tentativas falhas são registradas."""
        auth_manager.record_failed_attempt("10.0.0.1")
        auth_manager.record_failed_attempt("10.0.0.1")
        
        assert len(auth_manager._failed_attempts["10.0.0.1"]) == 2

    def test_lockout_after_max_attempts(self):
        """Lockout após max tentativas."""
        for i in range(10):
            auth_manager.record_failed_attempt("10.0.0.1")
        
        assert auth_manager.is_ip_locked("10.0.0.1") is True

    def test_lockout_expires(self):
        """Lockout expira após tempo."""
        # Simula tentativas antigas
        old_time = time.time() - 400  # 400 segundos atrás (mais que lockout de 300s)
        auth_manager._failed_attempts["10.0.0.1"] = [old_time] * 10
        
        # Lockout deveria ter expirado
        assert auth_manager.is_ip_locked("10.0.0.1") is False

    def test_lockout_stats(self):
        """Estatísticas incluem IPs bloqueados."""
        for _ in range(10):
            auth_manager.record_failed_attempt("10.0.0.1")
        
        stats = auth_manager.get_stats()
        assert stats["locked_ips"] >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
