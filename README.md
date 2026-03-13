# 🦞 Mengão Monitor

**Monitor de APIs simples, eficiente e rubro-negro.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![CI](https://github.com/Derrota/mengao-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/Derrota/mengao-monitor/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Flamengo](https://img.shields.io/badge/torcida-rubro--negra-red.svg)](https://www.flamengo.com.br)

Mengão Monitor é uma ferramenta de monitoramento de APIs leve e eficiente. Construída com Python puro, sem dependências pesadas, focada em simplicidade e confiabilidade.

## ✨ Features

- **Monitoramento multi-endpoint** - Monitore várias APIs simultaneamente
- **Webhooks multi-plataforma** - Alertas via Discord, Slack, Telegram
- **Alertas por email** - Notificações SMTP com HTML templates
- **Dashboard web** - Interface visual com tema rubro-negro
- **Métricas Prometheus** - Exportação padrão para integração
- **Métricas de Sistema** - CPU, memória, disco, rede em tempo real
- **Histórico SQLite** - Tracking de uptime com estatísticas
- **Logging estruturado** - JSON para produção, texto para desenvolvimento
- **Configuração flexível** - JSON ou YAML com validação
- **Docker ready** - Dockerfile e docker-compose incluídos
- **CI/CD** - GitHub Actions com testes multi-Python

## 🚀 Quick Start

### Instalação

```bash
# Clone o repositório
git clone https://github.com/Derrota/mengao-monitor.git
cd mengao-monitor

# Instale as dependências
pip install -r requirements.txt

# Crie a configuração padrão
python main.py --init
```

### Configuração

Edite o `config.json` gerado:

```json
{
  "endpoints": [
    {
      "name": "Minha API",
      "url": "https://api.exemplo.com/health",
      "method": "GET",
      "timeout": 10,
      "expected_status": 200,
      "interval": 60
    }
  ],
  "webhooks": [
    {
      "platform": "discord",
      "url": "https://discord.com/api/webhooks/...",
      "events": ["down", "up"]
    }
  ]
}
```

### Execução

```bash
# Modo normal (loop contínuo)
python main.py

# Check único
python main.py --check

# Ver estatísticas
python main.py --stats

# Com configuração customizada
python main.py -c config.yaml

# Debug
python main.py --log-level DEBUG --log-format text
```

## 📊 Endpoints

| Endpoint | Descrição |
|----------|-----------|
| `:9090/metrics` | Métricas Prometheus (APIs + Sistema) |
| `:8080/` | Dashboard web |
| `:8080/apis` | Status JSON das APIs |
| `:8080/health` | Health check do monitor |
| `:8080/status` | Status detalhado com métricas de sistema |

## 📈 Métricas de Sistema

O Mengão Monitor agora coleta métricas de sistema automaticamente:

```
# CPU
mengao_system_cpu_percent 15.2

# Memória
mengao_system_memory_percent 45.8
mengao_system_memory_used_mb 1024.5
mengao_system_memory_total_mb 2048.0

# Disco
mengao_system_disk_percent 62.1
mengao_system_disk_used_gb 120.5
mengao_system_disk_total_gb 256.0

# Rede
mengao_system_network_bytes_sent 1024000
mengao_system_network_bytes_recv 2048000

# Sistema
mengao_system_process_count 156
mengao_system_uptime_seconds 86400.5
```

## ⚙️ Configuração Completa

```json
{
  "endpoints": [
    {
      "name": "API Produção",
      "url": "https://api.prod.com/health",
      "method": "GET",
      "timeout": 10,
      "expected_status": 200,
      "headers": {"Authorization": "Bearer token"},
      "interval": 60,
      "enabled": true,
      "tags": ["produção", "api"]
    }
  ],
  "webhooks": [
    {
      "platform": "discord",
      "url": "https://discord.com/api/webhooks/...",
      "enabled": true,
      "events": ["down", "up", "slow"],
      "cooldown": 300,
      "min_severity": "warning"
    },
    {
      "platform": "slack",
      "url": "https://hooks.slack.com/services/...",
      "enabled": true,
      "events": ["down", "up"]
    }
  ],
  "email": {
    "enabled": true,
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "use_tls": true,
    "username": "alertas@exemplo.com",
    "password": "sua-senha-app",
    "from_addr": "alertas@exemplo.com",
    "to_addrs": ["admin@exemplo.com", "dev@exemplo.com"],
    "events": ["down", "up"],
    "cooldown": 300
  },
  "dashboard": {
    "enabled": true,
    "host": "0.0.0.0",
    "port": 8080,
    "refresh_interval": 30,
    "theme": "dark",
    "title": "Mengão Monitor"
  },
  "history": {
    "enabled": true,
    "db_path": "uptime_history.db",
    "retention_days": 90,
    "export_format": "csv"
  },
  "log_level": "INFO",
  "log_format": "json",
  "metrics_enabled": true,
  "metrics_port": 9090,
  "user_agent": "MengaoMonitor/1.5"
}
```

## 🐳 Docker

```bash
# Build
docker build -t mengao-monitor .

# Run
docker run -d \
  -v $(pwd)/config.json:/app/config.json \
  -v $(pwd)/data:/app/data \
  -p 8080:8080 \
  -p 9090:9090 \
  mengao-monitor

# Docker Compose
docker-compose up -d
```

## 📈 Métricas Prometheus

O Mengão Monitor exporta métricas no formato Prometheus:

```
# HELP mengao_monitor_endpoint_up Whether endpoint is up (1) or down (0)
# TYPE mengao_monitor_endpoint_up gauge
mengao_monitor_endpoint_up{name="API Prod",url="https://..."} 1

# HELP mengao_monitor_response_time_ms Response time in milliseconds
# TYPE mengao_monitor_response_time_ms gauge
mengao_monitor_response_time_ms{name="API Prod",type="last"} 142.50

# HELP mengao_monitor_uptime_percentage Uptime percentage
# TYPE mengao_monitor_uptime_percentage gauge
mengao_monitor_uptime_percentage{name="API Prod"} 99.95
```

## 🧪 Testes

```bash
# Executar todos os testes
pytest

# Com cobertura
pytest --cov=. --cov-report=html

# Testes específicos
pytest test_monitor.py -v
```

## 📁 Estrutura do Projeto

```
mengao-monitor/
├── main.py              # Entry point principal
├── monitor.py           # Monitor legado (v1.2)
├── config.py            # Configuração com validação
├── logger.py            # Logging estruturado
├── metrics.py           # Métricas Prometheus (APIs)
├── system_metrics.py    # Métricas de sistema (CPU, memória, disco)
├── webhooks.py          # Notificações multi-plataforma
├── history.py           # Histórico SQLite
├── dashboard.py         # Dashboard web
├── health.py            # Health check + métricas de sistema
├── email_alerts.py      # Alertas por email
├── test_monitor.py      # Testes
├── requirements.txt     # Dependências
├── Dockerfile           # Container
├── docker-compose.yml
└── README.md
```

## 🗺️ Roadmap

- [x] **v1.5**: Métricas de sistema (CPU, memória, disco, rede) ✅
- [ ] **v1.6**: Autenticação no dashboard
- [ ] **v1.7**: Multi-region checks
- [ ] **v1.8**: SLA reporting automático
- [ ] **v2.0**: Interface React + API REST

## 🤝 Contribuindo

1. Fork o projeto
2. Crie sua feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

## 📜 Licença

MIT License - veja [LICENSE](LICENSE) para detalhes.

## 🦞 Sobre

Criado com ❤️ e paixão rubro-negra por [Lek](https://github.com/Derrota).

**Uma vez Flamengo, sempre Flamengo!** 🔴⚫
