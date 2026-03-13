# 🦞 Mengão Monitor

**Monitor de APIs simples, eficiente e rubro-negro.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![CI](https://github.com/Derrota/mengao-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/Derrota/mengao-monitor/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Flamengo](https://img.shields.io/badge/torcida-rubro--negra-red.svg)](https://www.flamengo.com.br)

Mengão Monitor é uma ferramenta de monitoramento de APIs leve e eficiente. Construída com Python puro, sem dependências pesadas, focada em simplicidade e confiabilidade.

## ✨ Features

- **Monitoramento multi-endpoint** - Monitore várias APIs simultaneamente
- **API REST de Gerenciamento** - Adicione, remova, pause endpoints em runtime (v2.1) 🆕
- **Hot-reload de Config** - Detecta mudanças no config.json automaticamente (v2.1) 🆕
- **Webhooks multi-plataforma** - Alertas via Discord, Slack, Telegram
- **Alertas por email** - Notificações SMTP com HTML templates
- **Dashboard web v2** - Interface visual com gráficos Chart.js em tempo real
- **Métricas Prometheus** - Exportação padrão para integração
- **Métricas de Sistema** - CPU, memória, disco, rede em tempo real
- **Histórico SQLite** - Tracking de uptime com estatísticas
- **Logging estruturado** - JSON para produção, texto para desenvolvimento
- **Configuração flexível** - JSON ou YAML com validação
- **Docker ready** - Dockerfile e docker-compose incluídos
- **CI/CD** - GitHub Actions com testes multi-Python
- **Rate Limiting** - Proteção contra spam de alertas (v1.6)
- **Retry automático** - Webhooks com backoff exponencial (v1.6)
- **Webhook Stats** - Estatísticas detalhadas de envio (v2.0)

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
| `:9090/metrics` | Métricas Prometheus (APIs + Sistema + Webhooks) |
| `:8080/` | Dashboard web v2 com gráficos Chart.js |
| `:8080/apis` | Status JSON das APIs |
| `:8080/health` | Health check do monitor |
| `:8080/status` | Status detalhado com métricas de sistema |
| `:8080/webhooks/stats` | Estatísticas detalhadas de webhooks |
| `:8081/api/v1/endpoints` | API REST de gerenciamento (v2.1) 🆕 |

## 🔧 API REST de Gerenciamento (v2.1) 🆕

Gerencie endpoints em runtime sem restart:

```bash
# Listar todos os endpoints
curl http://localhost:8081/api/v1/endpoints

# Adicionar novo endpoint
curl -X POST http://localhost:8081/api/v1/endpoints \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Nova API",
    "url": "https://api.nova.com/health",
    "interval": 30,
    "tags": ["produção"]
  }'

# Obter endpoint específico
curl http://localhost:8081/api/v1/endpoints/Nova%20API

# Atualizar endpoint
curl -X PUT http://localhost:8081/api/v1/endpoints/Nova%20API \
  -H "Content-Type: application/json" \
  -d '{"timeout": 30, "interval": 120}'

# Pausar endpoint
curl -X POST http://localhost:8081/api/v1/endpoints/Nova%20API/pause

# Retomar endpoint
curl -X POST http://localhost:8081/api/v1/endpoints/Nova%20API/resume

# Remover endpoint
curl -X DELETE http://localhost:8081/api/v1/endpoints/Nova%20API

# Estatísticas do gerenciador
curl http://localhost:8081/api/v1/stats
```

**Resposta do `/api/v1/endpoints`:**
```json
{
  "endpoints": [
    {
      "name": "API Produção",
      "url": "https://api.prod.com/health",
      "method": "GET",
      "timeout": 15,
      "interval": 60,
      "enabled": true,
      "paused": false,
      "last_status": "online",
      "checks_count": 142,
      "errors_count": 3,
      "added_at": "2026-03-13T06:00:00"
    }
  ],
  "stats": {
    "total": 5,
    "active": 4,
    "paused": 1,
    "statuses": {"online": 4, "offline": 1},
    "total_checks": 1247,
    "total_errors": 12
  }
}
```

## 👁️ Hot-reload de Configuração (v2.1) 🆕

O Mengão Monitor detecta automaticamente mudanças no arquivo de configuração:

```json
{
  "config_watcher": {
    "enabled": true,
    "check_interval": 10,
    "reload_count": 3,
    "last_reload": "2026-03-13T06:15:00"
  }
}
```

**Como funciona:**
1. Monitor calcula hash SHA256 do config.json a cada 10s
2. Quando detecta mudança, recarrega automaticamente
3. Loga diff do que mudou (endpoints adicionados/removidos/modificados)
4. Não reinicia o monitor — apenas atualiza config interna

**Exemplo de log:**
```
🔄 Config change detected: config.json
🔄 Hot-reload: Processing config changes...
  Added: 1 endpoints
  Removed: 0 endpoints
  Modified: 2 endpoints
✅ Config reloaded successfully
```

## 🛡️ Autenticação (v2.2) 🆕

Proteção token-based para endpoints sensíveis:

```bash
# Token bootstrap é gerado automaticamente na primeira execução
# Verifique os logs para o token inicial

# Usar token em requisições
curl -H "Authorization: Bearer mm_seu_token_aqui" http://localhost:8080/

# Criar novo token (requer admin)
curl -X POST http://localhost:8081/api/v1/tokens \
  -H "Authorization: Bearer mm_admin_token" \
  -H "Content-Type: application/json" \
  -d '{"name": "monitoring", "scopes": ["read"], "expires_hours": 720}'

# Listar tokens
curl -H "Authorization: Bearer mm_admin_token" http://localhost:8081/api/v1/tokens

# Revogar token
curl -X DELETE http://localhost:8081/api/v1/tokens/TOKEN_ID \
  -H "Authorization: Bearer mm_admin_token"
```

**Scopes disponíveis:**
- `read` - Acesso a dashboard, métricas, status
- `write` - Gerenciar endpoints (adicionar, pausar, remover)
- `admin` - Acesso total (gerenciar tokens, config)

**Proteção contra brute force:**
- 10 tentativas falhas → IP bloqueado por 5 minutos
- Lockout automático com expiração
- Stats de tentativas falhas disponíveis

**Endpoints protegidos:**
| Endpoint | Scope necessário |
|----------|-----------------|
| `/` (dashboard) | read |
| `/metrics` | read |
| `/webhooks/stats` | read |
| `/api/v1/endpoints` (GET) | read |
| `/api/v1/endpoints` (POST/PUT/DELETE) | write |
| `/api/v1/tokens` | admin |

**Endpoints públicos (sem auth):**
- `/health` - Health check
- `/status` - Status básico
- `/apis` - Lista de APIs monitoradas

## 📈 Métricas de Sistema

O Mengão Monitor coleta métricas de sistema automaticamente:

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

## 📊 Webhook Stats (v2.0)

O dashboard v2 exibe estatísticas detalhadas de webhooks:

```json
{
  "sent": 42,
  "failed": 3,
  "retries": 8,
  "rate_limited": 12,
  "cooldown_skipped": 25,
  "rate_limiter": {
    "allowed": 156,
    "blocked": 12
  }
}
```

**Métricas Prometheus de Webhooks:**
```
mengao_monitor_webhooks_sent_total 42
mengao_monitor_webhooks_failed_total 3
mengao_monitor_webhooks_retries_total 8
mengao_monitor_webhooks_rate_limited_total 12
```

## 🛡️ Rate Limiting (v1.6)

Proteção contra spam de alertas com múltiplas camadas:

```python
# Configuração padrão
max_alerts_per_minute: 5
max_alerts_per_hour: 30
max_alerts_per_day: 100
burst_limit: 3           # máx em rajada
burst_window_seconds: 60 # janela de rajada
cooldown_seconds: 300    # entre alertas do mesmo endpoint
```

**Camadas de proteção:**
- ⏱️ **Por minuto** - Máximo 5 alertas/minuto por endpoint
- 📊 **Por hora** - Máximo 30 alertas/hora por endpoint  
- 📅 **Por dia** - Máximo 100 alertas/dia por endpoint
- 💥 **Burst** - Máximo 3 alertas em 60 segundos (rajada)
- ❄️ **Cooldown** - 5 minutos entre alertas do mesmo endpoint

## 🔄 Retry Automático (v1.6)

Webhooks com retry automático e backoff exponencial:

```
Tentativa 1 → Falha → Espera 1s
Tentativa 2 → Falha → Espera 3s  
Tentativa 3 → Falha → Erro final
```

- **3 tentativas** por webhook
- **Backoff exponencial**: 1s, 3s, 5s
- **Timeout**: 10s por request
- **4xx**: Não retry (erro do cliente)
- **5xx**: Retry automático (erro do servidor)

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
  "rate_limiting": {
    "max_alerts_per_minute": 5,
    "max_alerts_per_hour": 30,
    "max_alerts_per_day": 100,
    "burst_limit": 3,
    "burst_window_seconds": 60,
    "cooldown_seconds": 300
  },
  "log_level": "INFO",
  "log_format": "json",
  "metrics_enabled": true,
  "metrics_port": 9090,
  "user_agent": "MengaoMonitor/2.0"
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

# Rate limiting metrics (v1.6)
mengao_webhook_sent_total 42
mengao_webhook_failed_total 3
mengao_webhook_retries_total 8
mengao_rate_limit_allowed_total 156
mengao_rate_limit_blocked_total 12

# Webhook metrics (v2.0)
mengao_monitor_webhooks_sent_total 42
mengao_monitor_webhooks_failed_total 3
mengao_monitor_webhooks_retries_total 8
mengao_monitor_webhooks_rate_limited_total 12
```

## 🧪 Testes

```bash
# Executar todos os testes
pytest

# Com cobertura
pytest --cov=. --cov-report=html

# Testes específicos
pytest test_v15.py -v

# Testes de rate limiting
pytest test_v15.py::TestRateLimiter -v

# Testes de autenticação
pytest test_auth.py -v
```

## 📁 Estrutura do Projeto

```
mengao-monitor/
├── main.py              # Entry point principal (v2.1)
├── monitor.py           # Monitor legado (v1.2)
├── config.py            # Configuração com validação
├── config_watcher.py    # Hot-reload de configuração (v2.1) 🆕
├── logger.py            # Logging estruturado
├── metrics.py           # Métricas Prometheus (APIs)
├── system_metrics.py    # Métricas de sistema (CPU, memória, disco)
├── webhooks.py          # Notificações multi-plataforma + retry
├── rate_limiter.py      # Rate limiting por endpoint (v1.6)
├── api_manager.py       # API REST de gerenciamento (v2.1) 🆕
├── history.py           # Histórico SQLite
├── dashboard.py         # Dashboard web (v1.x)
├── dashboard_v2.py      # Dashboard web v2 com Chart.js (v2.0)
├── health.py            # Health check + métricas de sistema
├── email_alerts.py      # Alertas por email
├── test_monitor.py      # Testes legados
├── test_v13.py          # Testes v1.3
├── test_v15.py          # Testes v1.5+ (config, metrics, rate limiter)
├── test_v21.py          # Testes v2.1 (API manager, config watcher) 🆕
├── test_auth.py         # Testes v2.2 (autenticação, brute force) 🆕
├── middleware.py        # Middleware v2.3 (CORS, rate limiting, logging) 🆕
├── test_middleware.py   # Testes v2.3 (middleware) 🆕
├── requirements.txt     # Dependências
├── Dockerfile           # Container
├── docker-compose.yml
└── README.md
```

## 🗺️ Roadmap

- [x] **v1.5**: Métricas de sistema (CPU, memória, disco, rede) ✅
- [x] **v1.6**: Rate limiting + retry automático ✅
- [x] **v2.0**: Dashboard com gráficos Chart.js + webhook stats ✅
- [x] **v2.1**: API REST de gerenciamento + Hot-reload de config ✅
- [x] **v2.2**: Autenticação no dashboard + API ✅
- [x] **v2.3**: Middleware (CORS, rate limiting, request logging) ✅
- [ ] **v2.4**: Multi-region checks
- [ ] **v2.4**: SLA reporting automático
- [ ] **v2.5**: Interface React + WebSocket

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
