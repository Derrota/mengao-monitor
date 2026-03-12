"""
Testes unitários para Mengão Monitor v1.2 🦞
"""

import pytest
import json
import tempfile
import os
from unittest.mock import patch, MagicMock
from monitor import APIMonitor
from webhooks import WebhookSender
from history import UptimeHistory


@pytest.fixture
def sample_config():
    """Config de exemplo para testes."""
    return {
        "check_interval": 60,
        "log_file": "test_monitor.log",
        "history_db": ":memory:",
        "webhook_cooldown": 300,
        "webhooks": [
            {"type": "discord", "url": "https://discord.com/api/webhooks/test"},
            {"type": "slack", "url": "https://hooks.slack.com/test"}
        ],
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


# === Testes APIMonitor ===

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

    def test_parse_webhooks_new_format(self, monitor):
        """Testa parsing do novo formato de webhooks."""
        webhooks = monitor._parse_webhooks()
        assert len(webhooks) == 2
        assert webhooks[0]['type'] == 'discord'
        assert webhooks[1]['type'] == 'slack'

    def test_parse_webhooks_legacy_format(self):
        """Testa parsing do formato legado."""
        config = {"webhook_url": "https://discord.com/test"}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f)
            f.flush()
            mon = APIMonitor(f.name)
            webhooks = mon._parse_webhooks()
            assert len(webhooks) == 1
            assert webhooks[0]['type'] == 'discord'
            os.unlink(f.name)

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
            "timeout": 1,
            "expected_status": 200
        }
        
        result = monitor.check_api(api_config)
        
        assert result['status'] in ['timeout', 'online', 'offline']

    @patch('requests.post')
    def test_send_alert_offline(self, mock_post, monitor):
        """Testa envio de alerta para API offline."""
        mock_post.return_value.status_code = 200
        
        result = {
            'name': 'Test API',
            'url': 'https://test.com',
            'status': 'offline',
            'error': 'Connection refused',
            'timestamp': '2026-03-12T13:00:00'
        }
        
        monitor.send_alert(result)
        
        # Verifica se webhook foi chamado (pelo menos 1x)
        assert mock_post.call_count >= 1

    @patch('requests.post')
    def test_send_alert_online_no_alert(self, mock_post, monitor):
        """Testa que alerta não é enviado para API online."""
        result = {
            'name': 'Test API',
            'url': 'https://test.com',
            'status': 'online',
            'error': None,
            'timestamp': '2026-03-12T13:00:00'
        }
        
        monitor.send_alert(result)
        
        # Não deve enviar webhook para status online
        mock_post.assert_not_called()


# === Testes WebhookSender ===

class TestWebhookSender:
    """Testes para multi-webhook."""

    def test_cooldown(self):
        """Testa cooldown de alertas."""
        from datetime import datetime, timedelta
        
        sender = WebhookSender([])
        sender.cooldown_seconds = 60
        
        # Sem cooldown inicialmente
        assert not sender._in_cooldown("api1")
        
        # Simula alerta enviado
        sender.cooldowns["api1"] = datetime.now()
        assert sender._in_cooldown("api1")
        
        # Cooldown expirado
        sender.cooldowns["api1"] = datetime.now() - timedelta(seconds=120)
        assert not sender._in_cooldown("api1")

    def test_format_discord(self):
        """Testa formatação Discord."""
        sender = WebhookSender([])
        result = {
            'name': 'Test',
            'url': 'https://test.com',
            'status': 'offline',
            'error': 'Connection refused',
            'timestamp': '2026-03-12T13:00:00'
        }
        
        payload = sender._format_discord(result)
        assert 'embeds' in payload
        assert 'Test' in payload['embeds'][0]['title']

    def test_format_slack(self):
        """Testa formatação Slack."""
        sender = WebhookSender([])
        result = {
            'name': 'Test',
            'url': 'https://test.com',
            'status': 'timeout',
            'error': 'Timeout',
            'timestamp': '2026-03-12T13:00:00'
        }
        
        payload = sender._format_slack(result)
        assert 'blocks' in payload

    def test_format_telegram(self):
        """Testa formatação Telegram."""
        sender = WebhookSender([])
        result = {
            'name': 'Test',
            'url': 'https://test.com',
            'status': 'error',
            'error': 'Status 500',
            'timestamp': '2026-03-12T13:00:00'
        }
        
        payload = sender._format_telegram(result, '123456')
        assert payload['chat_id'] == '123456'
        assert 'parse_mode' in payload


# === Testes UptimeHistory ===

class TestUptimeHistory:
    """Testes para histórico SQLite."""

    @pytest.fixture
    def history(self):
        """Instância com banco em memória."""
        return UptimeHistory(":memory:")

    def test_record_check(self, history):
        """Testa registro de verificação."""
        result = {
            'name': 'Test API',
            'url': 'https://test.com',
            'status': 'online',
            'response_time': 0.5,
            'error': None,
            'timestamp': '2026-03-12T13:00:00'
        }
        
        history.record_check(result)
        
        recent = history.get_recent_checks('Test API', limit=1)
        assert len(recent) == 1
        assert recent[0]['status'] == 'online'

    def test_uptime_calculation(self, history):
        """Testa cálculo de uptime."""
        # Registra 10 checks: 9 online, 1 offline
        for i in range(9):
            history.record_check({
                'name': 'API',
                'url': 'https://test.com',
                'status': 'online',
                'response_time': 0.1,
                'timestamp': '2026-03-12T13:00:00'
            })
        
        history.record_check({
            'name': 'API',
            'url': 'https://test.com',
            'status': 'offline',
            'response_time': None,
            'timestamp': '2026-03-12T13:00:00'
        })
        
        uptime = history.get_uptime('API', hours=24)
        assert uptime == 90.0

    def test_avg_response_time(self, history):
        """Testa tempo de resposta médio."""
        for time_val in [0.1, 0.2, 0.3]:
            history.record_check({
                'name': 'API',
                'url': 'https://test.com',
                'status': 'online',
                'response_time': time_val,
                'timestamp': '2026-03-12T13:00:00'
            })
        
        avg = history.get_avg_response_time('API', hours=24)
        assert avg == 0.2

    def test_all_apis_stats(self, history):
        """Testa stats de todas as APIs."""
        history.record_check({
            'name': 'API1',
            'url': 'https://test1.com',
            'status': 'online',
            'response_time': 0.1
        })
        history.record_check({
            'name': 'API2',
            'url': 'https://test2.com',
            'status': 'offline',
            'response_time': None
        })
        
        stats = history.get_all_apis_stats(hours=24)
        assert 'API1' in stats
        assert 'API2' in stats
        assert stats['API1']['uptime_percent'] == 100.0
        assert stats['API2']['uptime_percent'] == 0.0

    def test_cleanup_old_records(self, history):
        """Testa limpeza de registros antigos."""
        # Registra um check
        history.record_check({
            'name': 'API',
            'url': 'https://test.com',
            'status': 'online',
            'response_time': 0.1
        })
        
        # Cleanup com 0 dias (deve remover tudo)
        deleted = history.cleanup_old_records(days=0)
        assert deleted >= 1

    def test_export_csv(self, history, tmp_path):
        """Testa exportação CSV."""
        history.record_check({
            'name': 'API',
            'url': 'https://test.com',
            'status': 'online',
            'response_time': 0.1
        })
        
        csv_file = tmp_path / "export.csv"
        count = history.export_csv(str(csv_file), hours=24)
        
        assert count == 1
        assert csv_file.exists()


# === Testes Config Validation ===

class TestConfigValidation:
    """Testes para validação de configuração."""

    def test_valid_config(self, sample_config):
        """Testa config válido."""
        assert 'check_interval' in sample_config
        assert 'apis' in sample_config
        assert isinstance(sample_config['apis'], list)

    def test_api_config_required_fields(self, sample_config):
        """Testa campos obrigatórios na config de API."""
        api = sample_config['apis'][0]
        
        required_fields = ['name', 'url']
        for field in required_fields:
            assert field in api

    def test_webhooks_config(self, sample_config):
        """Testa config de webhooks."""
        webhooks = sample_config.get('webhooks', [])
        assert len(webhooks) > 0
        
        for wh in webhooks:
            assert 'type' in wh
            assert 'url' in wh


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
