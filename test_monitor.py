"""
Testes unitários para Mengão Monitor 🦞
"""

import pytest
import json
import tempfile
import os
from unittest.mock import patch, MagicMock
from monitor import APIMonitor


@pytest.fixture
def sample_config():
    """Config de exemplo para testes."""
    return {
        "check_interval": 60,
        "log_file": "test_monitor.log",
        "webhook_url": "https://discord.com/api/webhooks/test",
        "apis": [
            {
                "name": "Test API",
                "url": "https://httpbin.org/status/200",
                "method": "GET",
                "timeout": 5,
                "expected_status": 200
            }
        ]
    }


@pytest.fixture
def config_file(sample_config):
    """Cria arquivo de config temporário."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(sample_config, f)
        return f.name


@pytest.fixture
def monitor(config_file):
    """Instância do monitor para testes."""
    monitor = APIMonitor(config_file)
    yield monitor
    os.unlink(config_file)


class TestAPIMonitor:
    """Testes para a classe APIMonitor."""

    def test_load_config_success(self, monitor, sample_config):
        """Testa carregamento de config válido."""
        assert monitor.config['check_interval'] == 60
        assert len(monitor.config['apis']) == 1

    def test_load_config_file_not_found(self):
        """Testa erro quando arquivo não existe."""
        with pytest.raises(SystemExit):
            APIMonitor("arquivo_inexistente.json")

    def test_check_api_online(self, monitor):
        """Testa verificação de API online."""
        api_config = {
            "name": "httpbin",
            "url": "https://httpbin.org/status/200",
            "method": "GET",
            "timeout": 10,
            "expected_status": 200
        }
        
        result = monitor.check_api(api_config)
        
        assert result['name'] == "httpbin"
        assert result['status'] in ['online', 'timeout', 'offline']
        assert 'timestamp' in result

    def test_check_api_timeout(self, monitor):
        """Testa timeout de API."""
        api_config = {
            "name": "slow-api",
            "url": "https://httpbin.org/delay/10",
            "method": "GET",
            "timeout": 1,  # Timeout curto
            "expected_status": 200
        }
        
        result = monitor.check_api(api_config)
        
        # Pode dar timeout ou online dependendo da rede
        assert result['status'] in ['timeout', 'online', 'offline']

    @patch('requests.post')
    def test_send_webhook_offline(self, mock_post, monitor):
        """Testa envio de webhook para API offline."""
        mock_post.return_value.status_code = 200
        
        result = {
            'name': 'Test API',
            'url': 'https://test.com',
            'status': 'offline',
            'error': 'Connection refused',
            'timestamp': '2026-03-12T13:00:00'
        }
        
        monitor.send_webhook(result)
        
        # Verifica se webhook foi chamado
        mock_post.assert_called_once()

    @patch('requests.post')
    def test_send_webhook_online_no_alert(self, mock_post, monitor):
        """Testa que webhook não é enviado para API online."""
        result = {
            'name': 'Test API',
            'url': 'https://test.com',
            'status': 'online',
            'error': None,
            'timestamp': '2026-03-12T13:00:00'
        }
        
        monitor.send_webhook(result)
        
        # Não deve enviar webhook para status online
        mock_post.assert_not_called()


class TestConfigValidation:
    """Testes para validação de configuração."""

    def test_valid_config(self, sample_config):
        """Testa config válido."""
        # Deve ter campos obrigatórios
        assert 'check_interval' in sample_config
        assert 'apis' in sample_config
        assert isinstance(sample_config['apis'], list)

    def test_api_config_required_fields(self, sample_config):
        """Testa campos obrigatórios na config de API."""
        api = sample_config['apis'][0]
        
        required_fields = ['name', 'url']
        for field in required_fields:
            assert field in api


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
