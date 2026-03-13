"""
Testes para Mengão Monitor v1.3 🦞
Cobre: config validation, main monitor, metrics, webhooks, history
"""

import json
import tempfile
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime

# Módulos v1.3
from config import (
    APIEndpoint, WebhookConfig, DashboardConfig, HistoryConfig,
    MonitorConfig, load_config, parse_config, create_sample_config
)
from webhooks import WebhookSender
from history import UptimeHistory


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def sample_endpoint():
    """Endpoint de exemplo."""
    return APIEndpoint(
        name="Test API",
        url="https://httpbin.org/status/200",
        method="GET",
        timeout=10,
        expected_status=200,
        interval=60,
        tags=["test"]
    )


@pytest.fixture
def sample_config_dict():
    """Config dict válido para testes."""
    return {
        "endpoints": [
            {
                "name": "Test API",
                "url": "https://httpbin.org/status/200",
                "method": "GET",
                "timeout": 10,
                "expected_status": 200,
                "interval": 60
            }
        ],
        "webhooks": [
            {
                "platform": "discord",
                "url": "https://discord.com/api/webhooks/test",
                "enabled": True,
                "events": ["down", "up"]
            }
        ],
        "dashboard": {
            "enabled": True,
            "port": 8080,
            "theme": "dark"
        },
        "history": {
            "enabled": True,
            "db_path": ":memory:"
        },
        "log_level": "INFO",
        "log_format": "json",
        "metrics_enabled": True,
        "metrics_port": 9090
    }


@pytest.fixture
def config_file(sample_config_dict):
    """Arquivo de config temporário."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(sample_config_dict, f)
        return f.name


@pytest.fixture
def history():
    """Instância UptimeHistory com banco em memória."""
    return UptimeHistory(":memory:")


# ============================================================
# TESTES: APIEndpoint
# ============================================================

class TestAPIEndpoint:
    """Testes para validação de endpoints."""

    def test_valid_endpoint(self, sample_endpoint):
        """Endpoint válido não deve ter erros."""
        errors = sample_endpoint.validate()
        assert errors == []

    def test_missing_name(self):
        """Nome vazio deve gerar erro."""
        ep = APIEndpoint(name="", url="https://test.com")
        errors = ep.validate()
        assert any("name" in e.lower() for e in errors)

    def test_missing_url(self):
        """URL vazia deve gerar erro."""
        ep = APIEndpoint(name="Test", url="")
        errors = ep.validate()
        assert any("url" in e.lower() for e in errors)

    def test_invalid_url_scheme(self):
        """URL sem http/https deve gerar erro."""
        ep = APIEndpoint(name="Test", url="ftp://test.com")
        errors = ep.validate()
        assert any("scheme" in e.lower() for e in errors)

    def test_invalid_method(self):
        """Método HTTP inválido deve gerar erro."""
        ep = APIEndpoint(name="Test", url="https://test.com", method="INVALID")
        errors = ep.validate()
        assert any("method" in e.lower() for e in errors)

    def test_timeout_too_low(self):
        """Timeout < 1 deve gerar erro."""
        ep = APIEndpoint(name="Test", url="https://test.com", timeout=0)
        errors = ep.validate()
        assert any("timeout" in e.lower() for e in errors)

    def test_interval_too_low(self):
        """Interval < 5 deve gerar erro."""
        ep = APIEndpoint(name="Test", url="https://test.com", interval=3)
        errors = ep.validate()
        assert any("interval" in e.lower() for e in errors)

    def test_default_values(self):
        """Verifica valores padrão."""
        ep = APIEndpoint(name="Test", url="https://test.com")
        assert ep.method == "GET"
        assert ep.timeout == 10
        assert ep.expected_status == 200
        assert ep.interval == 60
        assert ep.enabled is True
        assert ep.tags == []


# ============================================================
# TESTES: WebhookConfig
# ============================================================

class TestWebhookConfig:
    """Testes para configuração de webhooks."""

    def test_valid_webhook(self):
        """Webhook válido não deve ter erros."""
        wh = WebhookConfig(platform="discord", url="https://discord.com/test")
        errors = wh.validate()
        assert errors == []

    def test_invalid_platform(self):
        """Plataforma inválida deve gerar erro."""
        wh = WebhookConfig(platform="invalid", url="https://test.com")
        errors = wh.validate()
        assert any("platform" in e.lower() for e in errors)

    def test_missing_url(self):
        """URL vazia deve gerar erro."""
        wh = WebhookConfig(platform="discord", url="")
        errors = wh.validate()
        assert any("url" in e.lower() for e in errors)

    def test_supported_platforms(self):
        """Todas as plataformas suportadas devem ser válidas."""
        for platform in ["discord", "slack", "telegram", "generic"]:
            wh = WebhookConfig(platform=platform, url="https://test.com")
            errors = wh.validate()
            assert errors == [], f"Platform {platform} should be valid"


# ============================================================
# TESTES: MonitorConfig
# ============================================================

class TestMonitorConfig:
    """Testes para configuração principal."""

    def test_valid_config(self, sample_config_dict):
        """Config válido deve parsear sem erros."""
        config = parse_config(sample_config_dict)
        assert len(config.endpoints) == 1
        assert len(config.webhooks) == 1
        assert config.endpoints[0].name == "Test API"

    def test_empty_endpoints(self):
        """Config sem endpoints deve falhar."""
        config = MonitorConfig(endpoints=[])
        errors = config.validate()
        assert any("endpoint" in e.lower() for e in errors)

    def test_invalid_log_level(self, sample_config_dict):
        """Log level inválido deve gerar erro."""
        sample_config_dict["log_level"] = "INVALID"
        with pytest.raises(ValueError, match="log level"):
            parse_config(sample_config_dict)

    def test_invalid_metrics_port(self, sample_config_dict):
        """Porta de métricas inválida deve gerar erro."""
        sample_config_dict["metrics_port"] = 99999
        with pytest.raises(ValueError, match="metrics port"):
            parse_config(sample_config_dict)


# ============================================================
# TESTES: load_config
# ============================================================

class TestLoadConfig:
    """Testes para carregamento de config."""

    def test_load_json(self, config_file):
        """Carregamento de JSON deve funcionar."""
        config = load_config(config_file)
        assert len(config.endpoints) == 1
        os.unlink(config_file)

    def test_file_not_found(self):
        """Arquivo inexistente deve lançar FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_config("nao_existe.json")

    def test_invalid_json(self):
        """JSON inválido deve lançar exceção."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{invalid json}")
            f.flush()
            with pytest.raises(Exception):
                load_config(f.name)
            os.unlink(f.name)

    def test_load_yaml(self):
        """Carregamento de YAML (se disponível)."""
        try:
            import yaml
        except ImportError:
            pytest.skip("PyYAML not installed")
        
        yaml_content = """
endpoints:
  - name: Test
    url: https://test.com
    interval: 60
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            config = load_config(f.name)
            assert config.endpoints[0].name == "Test"
            os.unlink(f.name)


# ============================================================
# TESTES: WebhookSender
# ============================================================

class TestWebhookSender:
    """Testes para envio de webhooks."""

    def test_cooldown(self):
        """Testa cooldown entre alertas."""
        from datetime import timedelta
        
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
        """Testa formatação de payload Discord."""
        sender = WebhookSender([])
        result = {
            'name': 'Test API',
            'url': 'https://test.com',
            'status': 'offline',
            'error': 'Connection refused',
            'response_time_ms': 150,
            'timestamp': datetime.now().isoformat()
        }
        
        payload = sender._format_discord(result)
        assert 'embeds' in payload
        assert 'Test API' in payload['embeds'][0]['title']

    def test_format_slack(self):
        """Testa formatação de payload Slack."""
        sender = WebhookSender([])
        result = {
            'name': 'Test API',
            'url': 'https://test.com',
            'status': 'timeout',
            'error': 'Timeout after 10s',
            'response_time_ms': None,
            'timestamp': datetime.now().isoformat()
        }
        
        payload = sender._format_slack(result)
        assert 'blocks' in payload

    def test_format_telegram(self):
        """Testa formatação de payload Telegram."""
        sender = WebhookSender([])
        result = {
            'name': 'Test API',
            'url': 'https://test.com',
            'status': 'error',
            'error': 'Status 500',
            'response_time_ms': 200,
            'timestamp': datetime.now().isoformat()
        }
        
        payload = sender._format_telegram(result, '123456')
        assert payload['chat_id'] == '123456'
        assert 'parse_mode' in payload

    @patch('webhooks.requests.post')
    def test_send_without_cooldown(self, mock_post):
        """Testa envio sem cooldown."""
        mock_post.return_value.status_code = 200
        
        webhooks = [{"type": "discord", "url": "https://discord.com/test"}]
        sender = WebhookSender(webhooks)
        sender.cooldown_seconds = 0  # Sem cooldown
        
        result = {
            'name': 'API',
            'url': 'https://test.com',
            'status': 'offline',
            'error': 'Down',
            'timestamp': datetime.now().isoformat()
        }
        
        # Primeiro envio
        sender.send(result, MagicMock())
        assert mock_post.call_count == 1
        
        # Segundo envio (sem cooldown, deve enviar)
        sender.send(result, MagicMock())
        assert mock_post.call_count == 2


# ============================================================
# TESTES: UptimeHistory
# ============================================================

class TestUptimeHistory:
    """Testes para histórico SQLite."""

    def test_record_check(self, history):
        """Testa registro de verificação."""
        result = {
            'name': 'Test API',
            'url': 'https://test.com',
            'status': 'online',
            'response_time': 0.150,
            'error': None,
            'timestamp': datetime.now().isoformat()
        }
        
        history.record_check(result)
        recent = history.get_recent_checks('Test API', limit=1)
        
        assert len(recent) == 1
        assert recent[0]['status'] == 'online'

    def test_uptime_calculation(self, history):
        """Testa cálculo de uptime percentual."""
        # 9 online + 1 offline = 90% uptime
        for _ in range(9):
            history.record_check({
                'name': 'API',
                'url': 'https://test.com',
                'status': 'online',
                'response_time': 0.100
            })
        
        history.record_check({
            'name': 'API',
            'url': 'https://test.com',
            'status': 'offline',
            'response_time': None
        })
        
        uptime = history.get_uptime('API', hours=24)
        assert uptime == 90.0

    def test_avg_response_time(self, history):
        """Testa cálculo de tempo de resposta médio."""
        for ms in [0.100, 0.200, 0.300]:
            history.record_check({
                'name': 'API',
                'url': 'https://test.com',
                'status': 'online',
                'response_time': ms
            })
        
        avg = history.get_avg_response_time('API', hours=24)
        assert avg == 0.2

    def test_all_apis_stats(self, history):
        """Testa estatísticas de todas as APIs."""
        history.record_check({
            'name': 'API1',
            'url': 'https://test1.com',
            'status': 'online',
            'response_time': 0.100
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
        history.record_check({
            'name': 'API',
            'url': 'https://test.com',
            'status': 'online',
            'response_time': 0.100
        })
        
        deleted = history.cleanup_old_records(days=0)
        assert deleted >= 1

    def test_export_csv(self, history, tmp_path):
        """Testa exportação para CSV."""
        history.record_check({
            'name': 'API',
            'url': 'https://test.com',
            'status': 'online',
            'response_time': 0.100
        })
        
        csv_file = tmp_path / "export.csv"
        count = history.export_csv(str(csv_file), hours=24)
        
        assert count == 1
        assert csv_file.exists()

    def test_multiple_apis(self, history):
        """Testa tracking de múltiplas APIs simultaneamente."""
        apis = ["API1", "API2", "API3"]
        
        for api in apis:
            history.record_check({
                'name': api,
                'url': f'https://{api.lower()}.com',
                'status': 'online',
                'response_time': 0.100
            })
        
        stats = history.get_all_apis_stats(hours=24)
        assert len(stats) == 3
        for api in apis:
            assert api in stats


# ============================================================
# TESTES: create_sample_config
# ============================================================

class TestCreateSampleConfig:
    """Testes para criação de config de exemplo."""

    def test_create_sample(self, tmp_path):
        """Criação de sample config deve gerar arquivo válido."""
        sample_file = tmp_path / "config.sample.json"
        create_sample_config(str(sample_file))
        
        assert sample_file.exists()
        
        # Deve ser JSON válido
        with open(sample_file) as f:
            data = json.load(f)
        
        assert "endpoints" in data
        assert "webhooks" in data
        assert len(data["endpoints"]) > 0


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
