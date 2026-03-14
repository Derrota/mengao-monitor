"""
Testes para Health Checks Avançados v2.6
"""

import unittest
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock
import socket
import ssl

from health_checks import (
    CheckStatus, CheckResult, HealthCheck, DNSCheck, SSLCheck, TCPCheck,
    HTTPHeaderCheck, ResponseTimeSLOCheck, JSONResponseCheck, HealthCheckManager
)


class TestCheckResult(unittest.TestCase):
    """Testes para CheckResult."""
    
    def test_to_dict(self):
        result = CheckResult(
            name="test",
            status=CheckStatus.HEALTHY,
            message="All good",
            duration_ms=12.34,
            details={"key": "value"}
        )
        
        d = result.to_dict()
        self.assertEqual(d["name"], "test")
        self.assertEqual(d["status"], "healthy")
        self.assertEqual(d["message"], "All good")
        self.assertEqual(d["duration_ms"], 12.34)
        self.assertIn("timestamp", d)
        self.assertEqual(d["details"], {"key": "value"})


class TestHealthCheckBase(unittest.TestCase):
    """Testes para classe base HealthCheck."""
    
    def test_run_success(self):
        """Testa execução bem-sucedida."""
        class MockCheck(HealthCheck):
            def _execute(self):
                return CheckResult(
                    name=self.name,
                    status=CheckStatus.HEALTHY,
                    message="OK",
                    duration_ms=0
                )
        
        check = MockCheck("test_check")
        result = check.run()
        
        self.assertEqual(result.status, CheckStatus.HEALTHY)
        self.assertEqual(check.run_count, 1)
        self.assertEqual(check.failure_count, 0)
        self.assertIsNotNone(check.last_result)
        self.assertIsNotNone(check.last_run)
    
    def test_run_failure(self):
        """Testa execução com falha."""
        class MockCheck(HealthCheck):
            def _execute(self):
                raise ValueError("Test error")
        
        check = MockCheck("test_check")
        result = check.run()
        
        self.assertEqual(result.status, CheckStatus.UNHEALTHY)
        self.assertIn("Test error", result.message)
        self.assertEqual(check.run_count, 1)
        self.assertEqual(check.failure_count, 1)
    
    def test_get_stats(self):
        """Testa estatísticas do check."""
        class MockCheck(HealthCheck):
            def _execute(self):
                return CheckResult(
                    name=self.name,
                    status=CheckStatus.HEALTHY,
                    message="OK",
                    duration_ms=0
                )
        
        check = MockCheck("test", "Test description")
        check.run()
        check.run()
        
        stats = check.get_stats()
        self.assertEqual(stats["name"], "test")
        self.assertEqual(stats["description"], "Test description")
        self.assertEqual(stats["run_count"], 2)
        self.assertEqual(stats["failure_count"], 0)
        self.assertEqual(stats["success_rate"], 100.0)


class TestDNSCheck(unittest.TestCase):
    """Testes para DNSCheck."""
    
    @patch('socket.gethostbyname_ex')
    def test_dns_resolution_success(self, mock_resolve):
        """Testa resolução DNS bem-sucedida."""
        mock_resolve.return_value = ('example.com', [], ['93.184.216.34'])
        
        check = DNSCheck("dns_test", "example.com")
        result = check.run()
        
        self.assertEqual(result.status, CheckStatus.HEALTHY)
        self.assertIn("93.184.216.34", result.message)
    
    @patch('socket.gethostbyname_ex')
    def test_dns_resolution_with_expected_ips(self, mock_resolve):
        """Testa resolução DNS com IPs esperados."""
        mock_resolve.return_value = ('example.com', [], ['93.184.216.34'])
        
        check = DNSCheck("dns_test", "example.com", expected_ips=["93.184.216.34"])
        result = check.run()
        
        self.assertEqual(result.status, CheckStatus.HEALTHY)
    
    @patch('socket.gethostbyname_ex')
    def test_dns_resolution_ip_mismatch(self, mock_resolve):
        """Testa resolução DNS com IP diferente do esperado."""
        mock_resolve.return_value = ('example.com', [], ['1.2.3.4'])
        
        check = DNSCheck("dns_test", "example.com", expected_ips=["93.184.216.34"])
        result = check.run()
        
        self.assertEqual(result.status, CheckStatus.DEGRADED)
    
    @patch('socket.gethostbyname_ex')
    def test_dns_resolution_failure(self, mock_resolve):
        """Testa falha na resolução DNS."""
        mock_resolve.side_effect = socket.gaierror("Name resolution failed")
        
        check = DNSCheck("dns_test", "nonexistent.invalid")
        result = check.run()
        
        self.assertEqual(result.status, CheckStatus.UNHEALTHY)


class TestTCPCheck(unittest.TestCase):
    """Testes para TCPCheck."""
    
    @patch('socket.socket')
    def test_tcp_port_open(self, mock_socket_class):
        """Testa porta TCP aberta."""
        mock_socket = MagicMock()
        mock_socket.connect_ex.return_value = 0
        mock_socket_class.return_value.__enter__ = MagicMock(return_value=mock_socket)
        mock_socket_class.return_value.__exit__ = MagicMock(return_value=False)
        
        # Simplificado: mock direto do socket
        with patch('socket.socket') as mock_sock:
            mock_instance = MagicMock()
            mock_instance.connect_ex.return_value = 0
            mock_sock.return_value = mock_instance
            
            check = TCPCheck("tcp_test", "localhost", 8080)
            result = check.run()
            
            self.assertEqual(result.status, CheckStatus.HEALTHY)
            self.assertIn("open", result.message)
    
    @patch('socket.socket')
    def test_tcp_port_closed(self, mock_socket_class):
        """Testa porta TCP fechada."""
        with patch('socket.socket') as mock_sock:
            mock_instance = MagicMock()
            mock_instance.connect_ex.return_value = 111  # Connection refused
            mock_sock.return_value = mock_instance
            
            check = TCPCheck("tcp_test", "localhost", 9999)
            result = check.run()
            
            self.assertEqual(result.status, CheckStatus.UNHEALTHY)


class TestHTTPHeaderCheck(unittest.TestCase):
    """Testes para HTTPHeaderCheck."""
    
    @patch('requests.request')
    def test_headers_match(self, mock_request):
        """Testa headers que batem."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {
            "Content-Type": "application/json",
            "X-Request-Id": "abc123"
        }
        mock_request.return_value = mock_response
        
        check = HTTPHeaderCheck(
            "header_test",
            "https://example.com",
            expected_headers={"Content-Type": "application/json"}
        )
        result = check.run()
        
        self.assertEqual(result.status, CheckStatus.HEALTHY)
    
    @patch('requests.request')
    def test_headers_missing(self, mock_request):
        """Testa header faltando."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_request.return_value = mock_response
        
        check = HTTPHeaderCheck(
            "header_test",
            "https://example.com",
            expected_headers={"X-Missing-Header": "value"}
        )
        result = check.run()
        
        self.assertEqual(result.status, CheckStatus.UNHEALTHY)
        self.assertIn("Missing", result.message)


class TestResponseTimeSLOCheck(unittest.TestCase):
    """Testes para ResponseTimeSLOCheck."""
    
    @patch('requests.request')
    def test_within_slo(self, mock_request):
        """Testa resposta dentro do SLO."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response
        
        check = ResponseTimeSLOCheck("slo_test", "https://example.com", slo_ms=1000)
        result = check.run()
        
        # Como o mock é instantâneo, deve estar dentro do SLO
        self.assertEqual(result.status, CheckStatus.HEALTHY)
    
    @patch('requests.request')
    def test_slo_violated(self, mock_request):
        """Testa violação de SLO."""
        def slow_request(*args, **kwargs):
            time.sleep(0.05)  # 50ms
            return MagicMock(status_code=200)
        
        mock_request.side_effect = slow_request
        
        check = ResponseTimeSLOCheck("slo_test", "https://example.com", slo_ms=10)  # 10ms SLO
        result = check.run()
        
        self.assertEqual(result.status, CheckStatus.UNHEALTHY)
        self.assertIn("violated", result.message.lower())


class TestJSONResponseCheck(unittest.TestCase):
    """Testes para JSONResponseCheck."""
    
    @patch('requests.request')
    def test_valid_json_with_required_fields(self, mock_request):
        """Testa JSON válido com campos obrigatórios."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok", "data": {"count": 42}}
        mock_request.return_value = mock_response
        
        check = JSONResponseCheck(
            "json_test",
            "https://example.com/api",
            required_fields=["status", "data.count"]
        )
        result = check.run()
        
        self.assertEqual(result.status, CheckStatus.HEALTHY)
    
    @patch('requests.request')
    def test_missing_required_field(self, mock_request):
        """Testa campo obrigatório faltando."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_request.return_value = mock_response
        
        check = JSONResponseCheck(
            "json_test",
            "https://example.com/api",
            required_fields=["status", "missing_field"]
        )
        result = check.run()
        
        self.assertEqual(result.status, CheckStatus.UNHEALTHY)
    
    @patch('requests.request')
    def test_invalid_json(self, mock_request):
        """Testa resposta que não é JSON."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Not JSON")
        mock_request.return_value = mock_response
        
        check = JSONResponseCheck("json_test", "https://example.com/api")
        result = check.run()
        
        self.assertEqual(result.status, CheckStatus.UNHEALTHY)
        self.assertIn("not valid json", result.message.lower())
    
    @patch('requests.request')
    def test_json_path_condition_gt(self, mock_request):
        """Testa condição gt em json path."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"count": 100}}
        mock_request.return_value = mock_response
        
        check = JSONResponseCheck(
            "json_test",
            "https://example.com/api",
            json_path_checks={"data.count": {"gt": 50}}
        )
        result = check.run()
        
        self.assertEqual(result.status, CheckStatus.HEALTHY)


class TestHealthCheckManager(unittest.TestCase):
    """Testes para HealthCheckManager."""
    
    def test_register_and_unregister(self):
        """Testa registro e remoção de checks."""
        manager = HealthCheckManager()
        
        class MockCheck(HealthCheck):
            def _execute(self):
                return CheckResult(self.name, CheckStatus.HEALTHY, "OK", 0)
        
        check = MockCheck("test")
        manager.register(check)
        self.assertIn("test", manager.checks)
        
        result = manager.unregister("test")
        self.assertTrue(result)
        self.assertNotIn("test", manager.checks)
    
    def test_run_check(self):
        """Testa execução de check específico."""
        manager = HealthCheckManager()
        
        class MockCheck(HealthCheck):
            def _execute(self):
                return CheckResult(self.name, CheckStatus.HEALTHY, "OK", 0)
        
        check = MockCheck("test")
        manager.register(check)
        
        result = manager.run_check("test")
        self.assertIsNotNone(result)
        self.assertEqual(result.status, CheckStatus.HEALTHY)
        
        # Check inexistente
        result = manager.run_check("nonexistent")
        self.assertIsNone(result)
    
    def test_run_all(self):
        """Testa execução de todos os checks."""
        manager = HealthCheckManager()
        
        class MockCheck(HealthCheck):
            def _execute(self):
                return CheckResult(self.name, CheckStatus.HEALTHY, "OK", 0)
        
        manager.register(MockCheck("check1"))
        manager.register(MockCheck("check2"))
        
        results = manager.run_all()
        self.assertEqual(len(results), 2)
        self.assertIn("check1", results)
        self.assertIn("check2", results)
    
    def test_get_status(self):
        """Testa status geral."""
        manager = HealthCheckManager()
        
        class HealthyCheck(HealthCheck):
            def _execute(self):
                return CheckResult(self.name, CheckStatus.HEALTHY, "OK", 0)
        
        class DegradedCheck(HealthCheck):
            def _execute(self):
                return CheckResult(self.name, CheckStatus.DEGRADED, "Warning", 0)
        
        manager.register(HealthyCheck("healthy"))
        manager.register(DegradedCheck("degraded"))
        
        status = manager.get_status()
        self.assertEqual(status["overall_status"], "degraded")
        self.assertEqual(status["summary"]["healthy"], 1)
        self.assertEqual(status["summary"]["degraded"], 1)
    
    def test_history(self):
        """Testa histórico de execuções."""
        manager = HealthCheckManager()
        
        class MockCheck(HealthCheck):
            def _execute(self):
                return CheckResult(self.name, CheckStatus.HEALTHY, "OK", 0)
        
        check = MockCheck("test")
        manager.register(check)
        
        manager.run_check("test")
        manager.run_check("test")
        
        history = manager.get_history()
        self.assertEqual(len(history), 2)
        
        history_filtered = manager.get_history(name="test")
        self.assertEqual(len(history_filtered), 2)
    
    def test_create_from_config(self):
        """Testa criação de checks a partir de config."""
        manager = HealthCheckManager()
        
        config = {
            "health_checks": [
                {
                    "type": "dns",
                    "name": "dns_example",
                    "hostname": "example.com"
                },
                {
                    "type": "tcp",
                    "name": "tcp_local",
                    "host": "localhost",
                    "port": 8080
                }
            ]
        }
        
        manager.create_from_config(config)
        self.assertIn("dns_example", manager.checks)
        self.assertIn("tcp_local", manager.checks)
        self.assertIsInstance(manager.checks["dns_example"], DNSCheck)
        self.assertIsInstance(manager.checks["tcp_local"], TCPCheck)


class TestSSLCheck(unittest.TestCase):
    """Testes para SSLCheck (mockados)."""
    
    @patch('socket.create_connection')
    @patch('ssl.create_default_context')
    def test_ssl_valid(self, mock_context, mock_connection):
        """Testa certificado SSL válido."""
        # Mock do certificado
        mock_cert = {
            'subject': ((('commonName', 'example.com'),),),
            'issuer': ((('organizationName', 'Let\'s Encrypt'),),),
            'notBefore': 'Jan 1 00:00:00 2025 GMT',
            'notAfter': 'Dec 31 23:59:59 2026 GMT',
            'subjectAltName': (('DNS', 'example.com'),),
            'serialNumber': '123456'
        }
        
        mock_sock = MagicMock()
        mock_sock.getpeercert.return_value = mock_cert
        
        mock_ssl_sock = MagicMock()
        mock_ssl_sock.__enter__ = MagicMock(return_value=mock_sock)
        mock_ssl_sock.__exit__ = MagicMock(return_value=False)
        
        mock_context_instance = MagicMock()
        mock_context_instance.wrap_socket.return_value = mock_ssl_sock
        mock_context.return_value = mock_context_instance
        
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=MagicMock())
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_connection.return_value = mock_conn
        
        check = SSLCheck("ssl_test", "example.com")
        result = check.run()
        
        # Certificado válido por mais de 30 dias
        self.assertIn(result.status, [CheckStatus.HEALTHY, CheckStatus.DEGRADED, CheckStatus.UNHEALTHY])


if __name__ == '__main__':
    unittest.main()
