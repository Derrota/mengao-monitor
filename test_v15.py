"""
Testes unitários para Mengão Monitor v1.5 🦞
Atualizados para a nova arquitetura com config.py, main.py, system_metrics.py
"""

import pytest
import json
import tempfile
import os
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta


# === Testes Config Module ===

class TestConfig:
    """Testes para config.py - validação e carregamento."""

    def test_load_json_config(self, tmp_path):
        """Testa carregamento de config JSON."""
        config_file = tmp_path / "config.json"
        config_data = {
            "endpoints": [
                {
                    "name": "Test API",
                    "url": "https://api.test.com/health",
                    "method": "GET",
                    "timeout": 10,
                    "expected_status": 200,
                    "interval": 60
                }
            ],
            "webhooks": [],
            "log_level": "INFO"
        }
        config_file.write_text(json.dumps(config_data))
        
        from config import load_config
        config = load_config(str(config_file))
        
        assert len(config.endpoints) == 1
        assert config.endpoints[0].name == "Test API"
        assert config.endpoints[0].timeout == 10

    def test_load_yaml_config(self, tmp_path):
        """Testa carregamento de config YAML."""
        pytest.importorskip("yaml")
        
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
endpoints:
  - name: Test API
    url: https://api.test.com/health
    method: GET
    timeout: 10
    expected_status: 200
    interval: 60
webhooks: []
log_level: INFO
""")
        
        from config import load_config
        config = load_config(str(config_file))
        
        assert len(config.endpoints) == 1
        assert config.endpoints[0].name == "Test API"

    def test_config_defaults(self, tmp_path):
        """Testa valores padrão da config."""
        config_file = tmp_path / "config.json"
        config_data = {
            "endpoints": [
                {
                    "name": "Test",
                    "url": "https://test.com"
                }
            ]
        }
        config_file.write_text(json.dumps(config_data))
        
        from config import load_config
        config = load_config(str(config_file))
        
        # Defaults
        assert config.endpoints[0].method == "GET"
        assert config.endpoints[0].timeout == 10
        assert config.endpoints[0].expected_status == 200
        assert config.endpoints[0].interval == 60
        assert config.endpoints[0].enabled is True

    def test_config_validation_missing_url(self, tmp_path):
        """Testa validação - URL obrigatória."""
        config_file = tmp_path / "config.json"
        config_data = {
            "endpoints": [
                {
                    "name": "Test"
                    # missing url
                }
            ]
        }
        config_file.write_text(json.dumps(config_data))
        
        from config import load_config
        with pytest.raises(Exception):
            load_config(str(config_file))

    def test_email_config(self, tmp_path):
        """Testa configuração de email."""
        config_file = tmp_path / "config.json"
        config_data = {
            "endpoints": [{"name": "Test", "url": "https://test.com"}],
            "email": {
                "enabled": True,
                "smtp_host": "smtp.gmail.com",
                "smtp_port": 587,
                "username": "test@test.com",
                "password": "secret",
                "from_addr": "test@test.com",
                "to_addrs": ["admin@test.com"]
            }
        }
        config_file.write_text(json.dumps(config_data))
        
        from config import load_config
        config = load_config(str(config_file))
        
        assert config.email.enabled is True
        assert config.email.smtp_host == "smtp.gmail.com"
        assert len(config.email.to_emails) == 1


# === Testes System Metrics ===

class TestSystemMetrics:
    """Testes para system_metrics.py."""

    def test_collect_metrics(self):
        """Testa coleta de métricas do sistema."""
        from system_metrics import SystemMetricsCollector
        
        collector = SystemMetricsCollector()
        metrics = collector.collect()
        
        assert metrics.cpu_percent >= 0
        assert metrics.memory_percent >= 0
        assert metrics.memory_total_mb > 0
        assert metrics.disk_percent >= 0
        assert metrics.process_count > 0
        assert metrics.uptime_seconds >= 0

    def test_to_dict(self):
        """Testa conversão para dict."""
        from system_metrics import SystemMetricsCollector
        
        collector = SystemMetricsCollector()
        metrics = collector.collect()
        data = collector.to_dict(metrics)
        
        assert isinstance(data, dict)
        assert "cpu_percent" in data
        assert "memory_percent" in data
        assert "disk_percent" in data

    def test_to_prometheus(self):
        """Testa formato Prometheus."""
        from system_metrics import SystemMetricsCollector
        
        collector = SystemMetricsCollector()
        metrics = collector.collect()
        prom = collector.to_prometheus(metrics)
        
        assert "mengao_system_cpu_percent" in prom
        assert "mengao_system_memory_percent" in prom
        assert "mengao_system_disk_percent" in prom
        assert "# HELP" in prom
        assert "# TYPE" in prom


# === Testes Webhooks ===

class TestWebhookSender:
    """Testes para webhooks.py."""

    def test_cooldown_basic(self):
        """Testa cooldown básico."""
        from webhooks import WebhookSender
        
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
        from webhooks import WebhookSender
        
        sender = WebhookSender([])
        result = {
            'name': 'Test API',
            'url': 'https://test.com',
            'status': 'offline',
            'error': 'Connection refused',
            'timestamp': datetime.now().isoformat()
        }
        
        payload = sender._format_discord(result)
        assert 'embeds' in payload
        assert 'Test API' in payload['embeds'][0]['title']
        assert payload['embeds'][0]['color'] == 0xFF0000  # Red for offline

    def test_format_slack(self):
        """Testa formatação Slack."""
        from webhooks import WebhookSender
        
        sender = WebhookSender([])
        result = {
            'name': 'Test API',
            'url': 'https://test.com',
            'status': 'timeout',
            'error': 'Timeout after 10s',
            'timestamp': datetime.now().isoformat()
        }
        
        payload = sender._format_slack(result)
        assert 'blocks' in payload
        assert len(payload['blocks']) >= 2

    def test_format_telegram(self):
        """Testa formatação Telegram."""
        from webhooks import WebhookSender
        
        sender = WebhookSender([])
        result = {
            'name': 'Test API',
            'url': 'https://test.com',
            'status': 'error',
            'error': 'Status 500',
            'timestamp': datetime.now().isoformat()
        }
        
        payload = sender._format_telegram(result, '123456')
        assert payload['chat_id'] == '123456'
        assert 'parse_mode' in payload
        assert 'Test API' in payload['text']

    def test_no_alert_when_online(self):
        """Testa que alerta não é enviado quando API está online."""
        from webhooks import WebhookSender
        
        sender = WebhookSender([{"type": "discord", "url": "https://test.com"}])
        
        result = {
            'name': 'Test',
            'url': 'https://test.com',
            'status': 'online',
            'error': None,
            'timestamp': datetime.now().isoformat()
        }
        
        with patch('requests.post') as mock_post:
            sender.send(result)
            mock_post.assert_not_called()

    @patch('requests.post')
    def test_send_alert_offline(self, mock_post):
        """Testa envio de alerta para API offline."""
        mock_post.return_value.status_code = 200
        
        from webhooks import WebhookSender
        
        sender = WebhookSender([
            {"type": "discord", "url": "https://discord.com/webhook/test"}
        ])
        
        result = {
            'name': 'Test API',
            'url': 'https://test.com',
            'status': 'offline',
            'error': 'Connection refused',
            'timestamp': datetime.now().isoformat()
        }
        
        sender.send(result)
        
        assert mock_post.call_count == 1
        # Cooldown deve ser atualizado
        assert 'Test API' in sender.cooldowns


# === Testes Email Alerts ===

class TestEmailAlerts:
    """Testes para email_alerts.py."""

    def test_email_config_validation(self):
        """Testa validação de config de email."""
        from email_alerts import EmailAlerter
        from config import EmailConfig
        
        # Config desabilitado
        config = EmailConfig(enabled=False)
        alerter = EmailAlerter(config)
        assert alerter.enabled is False

    def test_html_template_rendering(self):
        """Testa renderização de template HTML."""
        from email_alerts import EmailAlerter
        from config import EmailConfig
        
        config = EmailConfig(
            enabled=True,
            smtp_host="smtp.test.com",
            username="test@test.com",
            password="secret",
            from_addr="test@test.com",
            to_emails=["admin@test.com"]
        )
        
        alerter = EmailAlerter(config)
        
        # Testa template de alerta
        html = alerter._render_alert_html(
            api_name="Test API",
            url="https://test.com",
            error="Connection refused",
            status_code=0
        )
        
        assert "Test API" in html
        assert "Connection refused" in html
        assert "🔴" in html or "offline" in html.lower()

    def test_recovery_template(self):
        """Testa template de recuperação."""
        from email_alerts import EmailAlerter
        from config import EmailConfig
        
        config = EmailConfig(
            enabled=True,
            smtp_host="smtp.test.com",
            username="test@test.com",
            password="secret",
            from_addr="test@test.com",
            to_emails=["admin@test.com"]
        )
        
        alerter = EmailAlerter(config)
        
        html = alerter._render_recovery_html(
            api_name="Test API",
            url="https://test.com",
            response_time_ms=150.5
        )
        
        assert "Test API" in html
        assert "150.5" in html or "online" in html.lower()


# === Testes History ===

class TestUptimeHistory:
    """Testes para history.py."""

    @pytest.fixture
    def history(self):
        """Instância com banco em memória."""
        from history import UptimeHistory
        return UptimeHistory(":memory:")

    def test_record_check(self, history):
        """Testa registro de verificação."""
        result = {
            'name': 'Test API',
            'url': 'https://test.com',
            'status': 'online',
            'response_time_ms': 150.5,
            'error': None,
            'timestamp': datetime.now().isoformat()
        }
        
        history.record_check(result)
        
        recent = history.get_recent_checks('Test API', limit=1)
        assert len(recent) == 1
        assert recent[0]['status'] == 'online'

    def test_uptime_calculation(self, history):
        """Testa cálculo de uptime."""
        # 9 online, 1 offline = 90% uptime
        for i in range(9):
            history.record_check({
                'name': 'API',
                'url': 'https://test.com',
                'status': 'online',
                'response_time_ms': 100.0,
                'timestamp': datetime.now().isoformat()
            })
        
        history.record_check({
            'name': 'API',
            'url': 'https://test.com',
            'status': 'offline',
            'response_time_ms': 0,
            'timestamp': datetime.now().isoformat()
        })
        
        uptime = history.get_uptime('API', hours=24)
        assert uptime == 90.0

    def test_avg_response_time(self, history):
        """Testa tempo de resposta médio."""
        for time_val in [100.0, 200.0, 300.0]:
            history.record_check({
                'name': 'API',
                'url': 'https://test.com',
                'status': 'online',
                'response_time_ms': time_val,
                'timestamp': datetime.now().isoformat()
            })
        
        avg = history.get_avg_response_time('API', hours=24)
        assert avg == 200.0

    def test_export_csv(self, history, tmp_path):
        """Testa exportação CSV."""
        history.record_check({
            'name': 'API',
            'url': 'https://test.com',
            'status': 'online',
            'response_time_ms': 150.0,
            'timestamp': datetime.now().isoformat()
        })
        
        csv_file = tmp_path / "export.csv"
        count = history.export_csv(str(csv_file), hours=24)
        
        assert count == 1
        assert csv_file.exists()


# === Testes Health/Dashboard ===

class TestHealthEndpoints:
    """Testes para health.py endpoints."""

    def test_health_endpoint(self):
        """Testa endpoint /health."""
        from health import app
        
        with app.test_client() as client:
            response = client.get('/health')
            data = response.get_json()
            
            assert response.status_code == 200
            assert data['status'] == 'healthy'
            assert data['service'] == 'mengao-monitor'

    def test_apis_endpoint(self):
        """Testa endpoint /apis."""
        from health import app, update_state
        
        update_state(apis=[
            {'name': 'Test', 'status': 'online', 'response_time_ms': 100}
        ])
        
        with app.test_client() as client:
            response = client.get('/apis')
            data = response.get_json()
            
            assert response.status_code == 200
            assert len(data['apis']) == 1

    def test_status_endpoint(self):
        """Testa endpoint /status."""
        from health import app
        
        with app.test_client() as client:
            response = client.get('/status')
            data = response.get_json()
            
            assert response.status_code == 200
            assert 'system' in data
            assert 'version' in data


# === Integration Test ===

class TestMonitorIntegration:
    """Testes de integração básicos."""

    def test_full_config_load_and_validate(self, tmp_path):
        """Testa carregamento completo de config."""
        config_file = tmp_path / "config.json"
        config_data = {
            "endpoints": [
                {
                    "name": "Flamengo",
                    "url": "https://www.flamengo.com.br",
                    "method": "GET",
                    "timeout": 15,
                    "expected_status": 200,
                    "interval": 120,
                    "enabled": True,
                    "tags": ["flamengo"]
                }
            ],
            "webhooks": [
                {
                    "platform": "discord",
                    "url": "https://discord.com/api/webhooks/test",
                    "enabled": True,
                    "events": ["down", "up"],
                    "cooldown": 300
                }
            ],
            "email": {
                "enabled": False,
                "smtp_host": "smtp.gmail.com",
                "smtp_port": 587,
                "use_tls": True,
                "username": "",
                "password": "",
                "from_addr": "",
                "to_addrs": []
            },
            "dashboard": {
                "enabled": True,
                "host": "0.0.0.0",
                "port": 8080,
                "theme": "dark"
            },
            "history": {
                "enabled": True,
                "db_path": ":memory:",
                "retention_days": 90
            },
            "log_level": "INFO",
            "log_format": "json",
            "metrics_enabled": True,
            "metrics_port": 9090
        }
        config_file.write_text(json.dumps(config_data))
        
        from config import load_config
        config = load_config(str(config_file))
        
        # Validações
        assert len(config.endpoints) == 1
        assert config.endpoints[0].name == "Flamengo"
        assert config.endpoints[0].tags == ["flamengo"]
        assert len(config.webhooks) == 1
        assert config.webhooks[0].platform == "discord"
        assert config.email.enabled is False
        assert config.dashboard.enabled is True
        assert config.history.enabled is True
        assert config.metrics_enabled is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
