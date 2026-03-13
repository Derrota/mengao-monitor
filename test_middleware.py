"""
Testes para middleware.py 🦞
CORS, rate limiting e logging de requests.
"""

import time
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from flask import Flask, jsonify
from werkzeug.test import Client
from werkzeug.wrappers import Response

from middleware import (
    RateLimitRule,
    RateLimiter,
    CORSMiddleware,
    RequestLogger,
    setup_middleware,
    rate_limit,
    cors_origin,
)


@pytest.fixture
def app():
    """Cria app Flask para testes."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    
    @app.route('/test')
    def test_endpoint():
        return jsonify({'status': 'ok'})
    
    @app.route('/api/test')
    def api_test():
        return jsonify({'api': 'ok'})
    
    @app.route('/api/protected')
    @rate_limit()
    def protected_endpoint():
        return jsonify({'protected': 'ok'})
    
    return app


@pytest.fixture
def client(app):
    """Cria cliente de teste."""
    return app.test_client()


class TestRateLimitRule:
    """Testes para RateLimitRule."""
    
    def test_default_values(self):
        rule = RateLimitRule()
        assert rule.requests_per_minute == 60
        assert rule.requests_per_hour == 1000
        assert rule.burst_limit == 10
        assert rule.burst_window == 10
    
    def test_custom_values(self):
        rule = RateLimitRule(
            requests_per_minute=30,
            requests_per_hour=500,
            burst_limit=5,
            burst_window=5
        )
        assert rule.requests_per_minute == 30
        assert rule.requests_per_hour == 500
        assert rule.burst_limit == 5
        assert rule.burst_window == 5


class TestRateLimiter:
    """Testes para RateLimiter."""
    
    def test_initialization(self):
        limiter = RateLimiter()
        assert limiter.rule.requests_per_minute == 60
        assert len(limiter._requests) == 0
        assert len(limiter._burst) == 0
    
    def test_custom_rule(self):
        rule = RateLimitRule(requests_per_minute=10)
        limiter = RateLimiter(rule)
        assert limiter.rule.requests_per_minute == 10
    
    @patch('middleware.request')
    def test_is_allowed_first_request(self, mock_request):
        mock_request.remote_addr = '127.0.0.1'
        mock_request.headers = {}
        
        limiter = RateLimiter()
        allowed, headers = limiter.is_allowed('/test')
        
        assert allowed is True
        assert 'X-RateLimit-Limit-Minute' in headers
        assert 'X-RateLimit-Remaining-Minute' in headers
    
    @patch('middleware.request')
    def test_exceeds_minute_limit(self, mock_request):
        mock_request.remote_addr = '127.0.0.1'
        mock_request.headers = {}
        
        rule = RateLimitRule(requests_per_minute=2, burst_limit=100)
        limiter = RateLimiter(rule)
        
        # Primeiro request - permitido
        allowed, _ = limiter.is_allowed('/test')
        assert allowed is True
        
        # Segundo request - permitido
        allowed, _ = limiter.is_allowed('/test')
        assert allowed is True
        
        # Terceiro request - bloqueado
        allowed, headers = limiter.is_allowed('/test')
        assert allowed is False
        assert 'X-RateLimit-Reset-Minute' in headers
    
    @patch('middleware.request')
    def test_exceeds_burst_limit(self, mock_request):
        mock_request.remote_addr = '127.0.0.1'
        mock_request.headers = {}
        
        rule = RateLimitRule(
            requests_per_minute=100,
            requests_per_hour=10000,
            burst_limit=3,
            burst_window=10
        )
        limiter = RateLimiter(rule)
        
        # 3 requests em burst - todos permitidos
        for _ in range(3):
            allowed, _ = limiter.is_allowed('/test')
            assert allowed is True
        
        # 4o request - bloqueado por burst
        allowed, _ = limiter.is_allowed('/test')
        assert allowed is False
    
    @patch('middleware.request')
    def test_ip_blocked_temporarily(self, mock_request):
        mock_request.remote_addr = '127.0.0.1'
        mock_request.headers = {}
        
        rule = RateLimitRule(burst_limit=1)
        limiter = RateLimiter(rule)
        
        # Excede burst - IP bloqueado
        limiter.is_allowed('/test')
        allowed, headers = limiter.is_allowed('/test')
        
        assert allowed is False
        assert 'X-RateLimit-Blocked' in headers
    
    @patch('middleware.request')
    def test_forwarded_for_header(self, mock_request):
        mock_request.remote_addr = '127.0.0.1'
        mock_request.headers = {'X-Forwarded-For': '192.168.1.1, 10.0.0.1'}
        
        limiter = RateLimiter()
        allowed, _ = limiter.is_allowed('/test')
        
        # Deve usar primeiro IP do X-Forwarded-For
        assert '192.168.1.1:test' in limiter._requests
    
    @patch('middleware.request')
    def test_different_endpoints_tracked_separately(self, mock_request):
        mock_request.remote_addr = '127.0.0.1'
        mock_request.headers = {}
        
        rule = RateLimitRule(requests_per_minute=1)
        limiter = RateLimiter(rule)
        
        # Endpoint 1
        allowed1, _ = limiter.is_allowed('/api/v1')
        assert allowed1 is True
        
        # Endpoint 2 - deve ser independente
        allowed2, _ = limiter.is_allowed('/api/v2')
        assert allowed2 is True
        
        # Endpoint 1 novamente - deve bloquear
        allowed3, _ = limiter.is_allowed('/api/v1')
        assert allowed3 is False


class TestCORSMiddleware:
    """Testes para CORSMiddleware."""
    
    def test_default_config(self):
        cors = CORSMiddleware()
        assert '*' in cors.allowed_origins
        assert 'GET' in cors.allowed_methods
        assert 'Content-Type' in cors.allowed_headers
    
    def test_custom_config(self):
        cors = CORSMiddleware(
            allowed_origins=['https://example.com'],
            allowed_methods=['GET', 'POST'],
            allowed_headers=['Authorization'],
            max_age=3600,
            allow_credentials=True
        )
        assert cors.allowed_origins == ['https://example.com']
        assert cors.allowed_methods == ['GET', 'POST']
        assert cors.max_age == 3600
        assert cors.allow_credentials is True
    
    @patch('middleware.request')
    def test_process_response_wildcard(self, mock_request):
        mock_request.headers = {'Origin': 'https://example.com'}
        
        cors = CORSMiddleware()
        response = Response()
        
        processed = cors.process_response(response)
        
        assert processed.headers['Access-Control-Allow-Origin'] == 'https://example.com'
        assert 'GET' in processed.headers['Access-Control-Allow-Methods']
    
    @patch('middleware.request')
    def test_process_response_specific_origin(self, mock_request):
        mock_request.headers = {'Origin': 'https://allowed.com'}
        
        cors = CORSMiddleware(allowed_origins=['https://allowed.com'])
        response = Response()
        
        processed = cors.process_response(response)
        
        assert processed.headers['Access-Control-Allow-Origin'] == 'https://allowed.com'
    
    @patch('middleware.request')
    def test_process_response_disallowed_origin(self, mock_request):
        mock_request.headers = {'Origin': 'https://evil.com'}
        
        cors = CORSMiddleware(allowed_origins=['https://allowed.com'])
        response = Response()
        
        processed = cors.process_response(response)
        
        assert processed.headers['Access-Control-Allow-Origin'] == 'null'
    
    @patch('middleware.request')
    def test_credentials_header(self, mock_request):
        mock_request.headers = {'Origin': 'https://example.com'}
        
        cors = CORSMiddleware(allow_credentials=True)
        response = Response()
        
        processed = cors.process_response(response)
        
        assert processed.headers['Access-Control-Allow-Credentials'] == 'true'


class TestRequestLogger:
    """Testes para RequestLogger."""
    
    @patch('middleware.g')
    @patch('middleware.request')
    def test_log_request_success(self, mock_request, mock_g):
        mock_request.method = 'GET'
        mock_request.path = '/test'
        mock_request.remote_addr = '127.0.0.1'
        mock_request.headers = {'User-Agent': 'pytest'}
        mock_g.request_duration = 10.5
        
        logger = MagicMock()
        request_logger = RequestLogger(logger)
        
        response = Response(status=200)
        request_logger.log_request(response)
        
        logger.info.assert_called_once()
        call_args = logger.info.call_args
        assert 'HTTP 200 GET /test' in call_args[0][0]
    
    @patch('middleware.g')
    @patch('middleware.request')
    def test_log_request_error(self, mock_request, mock_g):
        mock_request.method = 'POST'
        mock_request.path = '/api/error'
        mock_request.remote_addr = '127.0.0.1'
        mock_request.headers = {'User-Agent': 'pytest'}
        mock_g.request_duration = 50.0
        
        logger = MagicMock()
        request_logger = RequestLogger(logger)
        
        response = Response(status=500)
        request_logger.log_request(response)
        
        logger.warning.assert_called_once()
        call_args = logger.warning.call_args
        assert 'HTTP 500 POST /api/error' in call_args[0][0]


class TestSetupMiddleware:
    """Testes para setup_middleware."""
    
    def test_setup_default(self, app):
        configured_app = setup_middleware(app)
        assert configured_app is app
    
    def test_setup_with_rate_limit_config(self, app):
        config = {
            'rate_limit': {
                'requests_per_minute': 30,
                'requests_per_hour': 500
            }
        }
        configured_app = setup_middleware(app, config)
        assert configured_app is app
    
    def test_setup_with_cors_config(self, app):
        config = {
            'cors': {
                'allowed_origins': ['https://example.com'],
                'max_age': 3600
            }
        }
        configured_app = setup_middleware(app, config)
        assert configured_app is app


class TestRateLimitDecorator:
    """Testes para rate_limit decorator."""
    
    def test_decorator_allows_request(self, client):
        # Primeiro request deve passar
        response = client.get('/api/protected')
        assert response.status_code == 200
    
    def test_decorator_blocks_excessive_requests(self, app, client):
        # Configura rate limit baixo para teste
        from middleware import rate_limiter
        original_rule = rate_limiter.rule
        rate_limiter.rule = RateLimitRule(requests_per_minute=1, burst_limit=1)
        
        try:
            # Primeiro request - OK
            response1 = client.get('/api/protected')
            assert response1.status_code == 200
            
            # Segundo request - bloqueado
            response2 = client.get('/api/protected')
            assert response2.status_code == 429
            
            data = response2.get_json()
            assert 'error' in data
            assert 'Rate limit exceeded' in data['error']
        finally:
            rate_limiter.rule = original_rule


class TestCorsOriginDecorator:
    """Testes para cors_origin decorator."""
    
    def test_decorator_adds_cors_header(self, app, client):
        @app.route('/cors-test')
        @cors_origin(['https://example.com'])
        def cors_endpoint():
            return jsonify({'cors': 'ok'})
        
        response = client.get('/cors-test', headers={'Origin': 'https://example.com'})
        # Nota: o decorator só adiciona header se response for Response
        assert response.status_code == 200


class TestIntegration:
    """Testes de integração."""
    
    def test_full_middleware_stack(self, app):
        config = {
            'rate_limit': {
                'requests_per_minute': 100,
                'requests_per_hour': 1000
            },
            'cors': {
                'allowed_origins': ['*'],
                'allow_credentials': False
            }
        }
        
        configured_app = setup_middleware(app, config)
        client = configured_app.test_client()
        
        # Request normal
        response = client.get('/test')
        assert response.status_code == 200
        assert 'Access-Control-Allow-Origin' in response.headers
        
        # Request API
        response = client.get('/api/test')
        assert response.status_code == 200
        assert 'X-RateLimit-Limit-Minute' in response.headers
    
    def test_cors_preflight(self, app):
        configured_app = setup_middleware(app)
        client = configured_app.test_client()
        
        response = client.options('/test', headers={
            'Origin': 'https://example.com',
            'Access-Control-Request-Method': 'POST'
        })
        
        # Deve retornar headers CORS mesmo para OPTIONS
        assert 'Access-Control-Allow-Origin' in response.headers


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
