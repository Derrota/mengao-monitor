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
- **Circuit Breaker** - Proteção contra endpoints instáveis (v2.4) 🆕
- **Plugin System** - Arquitetura extensível para customizacoes (v2.5) 🆕
- **Health Checks Avançados** - DNS, SSL, TCP, HTTP headers, SLO, JSON validation (v2.6) 🆕
- **Meta-Monitoring** - Self-diagnostics, watchdog, process health (v2.7) 🆕
- **Config Watcher** - Hot-reload management via API (v2.8) 🆕
- **SLA Reporting** - Relatórios automáticos com uptime, MTTR, incidents (v2.9) 🆕
- **WebSocket** - Updates em tempo real para dashboard (v3.0) 🆕
- **Notification Manager** - Sistema unificado de notificações (v3.1) 🆕
- **Alert Escalation** - Escalação automática L1→L2→L3 com políticas (v3.2) 🆕
- **Dashboard v3** - Interface em tempo real com WebSocket (v3.3) 🆕

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
| `:8080/dashboard/v3` | Dashboard v3 com WebSocket em tempo real 🆕 |
| `:8080/apis` | Status JSON das APIs |
| `:8080/health` | Health check do monitor |
| `:8080/status` | Status detalhado com métricas de sistema |
| `:8080/webhooks/stats` | Estatísticas detalhadas de webhooks |
| `:8080/meta/watchdog/start` | Iniciar watchdog do meta-monitor (admin) |
| `:8080/config/watcher` | Status do config watcher |
| `:8080/config/watcher/reload` | Força reload da config (write) |
| `:8080/config/watcher/history` | Histórico de diffs |
| `:8080/config/watcher/start` | Iniciar config watcher (admin) |
| `:8080/config/watcher/stop` | Parar config watcher (admin) |
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

## ⚡ Circuit Breaker (v2.4) 🆕

Previne flood de requests para endpoints instáveis com o padrão Circuit Breaker:

**Estados:**
- 🟢 **CLOSED**: Normal, requests passam
- 🔴 **OPEN**: Falhas acima do threshold, requests bloqueados
- 🟡 **HALF_OPEN**: Após timeout, permite request de teste

**Configuração padrão:**
```python
failure_threshold: 5      # Falhas consecutivas para abrir
recovery_timeout: 60      # Segundos antes de half-open
success_threshold: 3      # Sucessos para fechar
half_open_max_calls: 1    # Requests simultâneos em half-open
```

**Endpoints de Gerenciamento:**
```bash
# Status de todos os circuit breakers
curl http://localhost:8080/circuit-breakers

# Status detalhado de um específico
curl http://localhost:8080/circuit-breakers/API%20Produção

# Reset manual (requer auth write)
curl -X POST http://localhost:8080/circuit-breakers/API%20Produção/reset \
  -H "Authorization: Bearer mm_token"

# Reset todos (requer auth admin)
curl -X POST http://localhost:8080/circuit-breakers/reset-all
```

**Métricas Prometheus:**
```
mengao_monitor_circuit_breakers_total 5
mengao_monitor_circuit_breakers_open 1
mengao_monitor_circuit_breakers_closed 4
mengao_circuit_breaker_state{name="api_prod"} 0
mengao_circuit_breaker_failure_rate{name="api_prod"} 12.5
mengao_circuit_breaker_rejected_total 42
```

**Fluxo de Estados:**
```
CLOSED ──(5 falhas)──> OPEN
   ↑                      │
   │                      │ (60s timeout)
   │                      ↓
   └──(3 sucessos)── HALF_OPEN
```

## 🔌 Plugin System (v2.5) 🆕

Arquitetura extensível para adicionar funcionalidades customizadas ao monitor:

**Tipos de Plugins:**
- **HealthCheckPlugin** - Lógica customizada de health check
- **AlertHandlerPlugin** - Entrega de alertas customizada (SMS, PagerDuty, etc.)
- **ExporterPlugin** - Exportar métricas para sistemas externos
- **HookPlugin** - Executar código em eventos (startup, shutdown, alert, etc.)

**Exemplo: SSL Certificate Check Plugin:**
```python
from plugins import HealthCheckPlugin

class SSLCheckPlugin(HealthCheckPlugin):
    name = "ssl_check"
    version = "1.0.0"
    description = "Validates SSL certificate expiration"
    
    def check(self, api_name: str, url: str, config: dict = None) -> dict:
        # Custom SSL validation logic
        return {
            "status": "ok",
            "days_left": 45,
            "expires": "2026-05-01"
        }
```

**Endpoints de Gerenciamento:**
```bash
# Listar todos os plugins
curl http://localhost:8080/plugins

# Detalhes de um plugin específico
curl http://localhost:8080/plugins/ssl_check

# Habilitar/desabilitar plugin
curl -X POST http://localhost:8080/plugins/ssl_check/enable
curl -X POST http://localhost:8080/plugins/ssl_check/disable

# Carregar plugins de um diretório
curl -X POST http://localhost:8080/plugins/load \
  -H "Content-Type: application/json" \
  -d '{"directory": "./custom_plugins/"}'
```

**Estrutura de Plugins:**
```
mengao-monitor/
├── plugins.py              # Plugin system core
├── test_plugins.py         # Testes (43 test cases)
├── plugins_examples/       # Exemplos de plugins
├── health_checks.py     # Health Checks Avançados v2.6 (DNS, SSL, TCP, SLO, JSON) 🆕
├── test_health_checks.py # Testes v2.6 (25 test cases) 🆕
│   └── example_plugins.py  # SSL, SLO, Console, File, JSON, Lifecycle
└── custom_plugins/         # Seus plugins customizados
    └── my_plugin.py
```

**Métricas Prometheus de Plugins:**
```
mengao_monitor_plugins_total 6
mengao_monitor_plugins_enabled 5
mengao_monitor_plugins_health_checks 2
mengao_monitor_plugins_alert_handlers 2
```
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
├── circuit_breaker.py   # Circuit Breaker v2.4 (resiliência) 🆕
├── test_circuit_breaker.py # Testes v2.4 (circuit breaker) 🆕
├── plugins.py           # Plugin System v2.5 (extensibilidade) 🆕
├── test_plugins.py      # Testes v2.5 (43 test cases) 🆕
├── plugins_examples/    # Exemplos de plugins 🆕
├── health_checks.py     # Health Checks Avançados v2.6 (DNS, SSL, TCP, SLO, JSON) 🆕
├── test_health_checks.py # Testes v2.6 (25 test cases) 🆕
├── meta_monitor.py      # Meta-Monitoring v2.7 (self-diagnostics) 🆕
├── test_meta_monitor.py # Testes v2.7 (20 test cases) 🆕
├── test_config_watcher.py # Testes v2.8 (18 test cases) 🆕
├── sla_reporter.py        # SLA Reporting v2.9 (relatórios automáticos) 🆕
├── test_sla_reporter.py   # Testes v2.9 (25 test cases) 🆕
├── websocket_server.py    # WebSocket Server v3.0 (updates tempo real) 🆕
├── test_websocket.py      # Testes v3.0 (19 test cases) 🆕
├── notification_manager.py  # Notification Manager v3.1 (sistema unificado) 🆕
├── test_notification_manager.py # Testes v3.1 (25 test cases) 🆕
├── alert_escalation.py      # Alert Escalation v3.2 (escalação automática) 🆕
├── test_alert_escalation.py # Testes v3.2 (27 test cases) 🆕
│   └── example_plugins.py # SSL, SLO, Console, File, JSON, Lifecycle
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
- [x] **v2.4**: Circuit Breaker pattern para endpoints ✅
- [x] **v2.5**: Plugin System (extensibilidade) ✅
- [x] **v2.6**: Health Checks Avançados (DNS, SSL, TCP, SLO, JSON) ✅
- [x] **v2.7**: Meta-Monitoring (self-diagnostics, watchdog) ✅
- [x] **v2.8**: Config Watcher API (hot-reload management) ✅
- [x] **v2.9**: SLA Reporting automático (JSON/CSV/HTML, incidents, MTTR) ✅ 🆕
- [x] **v3.0**: WebSocket para updates em tempo real ✅ 🆕
- [x] **v3.1**: Notification Manager (sistema unificado) ✅ 🆕
- [x] **v3.2**: Alert Escalation (escalação automática L1→L2→L3) ✅ 🆕
- [x] **v3.3**: Dashboard v3 com WebSocket em tempo real ✅ 🆕

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


## 🏥 Health Checks Avançados (v2.6) 🆕

Sistema de health checks customizáveis para monitorar além de HTTP status:

**Tipos de Checks:**
- **DNSCheck** - Verifica resolução DNS de hostname
- **SSLCheck** - Valida certificado SSL (expiração, issuer, SANs)
- **TCPCheck** - Verifica se porta TCP está aberta
- **HTTPHeaderCheck** - Valida headers HTTP específicos na resposta
- **ResponseTimeSLOCheck** - Verifica se tempo de resposta está dentro do SLO
- **JSONResponseCheck** - Valida estrutura e valores de resposta JSON

**Exemplo de Configuração:**
```json
{
  "health_checks": [
    {
      "type": "dns",
      "name": "dns_example",
      "hostname": "api.exemplo.com",
      "expected_ips": ["1.2.3.4"]
    },
    {
      "type": "ssl",
      "name": "ssl_example",
      "hostname": "api.exemplo.com",
      "warn_days": 30,
      "critical_days": 7
    },
    {
      "type": "response_time_slo",
      "name": "slo_example",
      "url": "https://api.exemplo.com/health",
      "slo_ms": 500,
      "warn_threshold": 0.8
    },
    {
      "type": "json_response",
      "name": "json_example",
      "url": "https://api.exemplo.com/status",
      "required_fields": ["status", "data.count"],
      "json_path_checks": {"data.count": {"gt": 0}}
    }
  ]
}
```

**Endpoints de Gerenciamento:**
```bash
# Status geral de todos os health checks
curl http://localhost:8080/health-checks/status

# Lista de todos os health checks
curl http://localhost:8080/health-checks

# Detalhes de um check específico
curl http://localhost:8080/health-checks/dns_example

# Executar check específico (requer auth write)
curl -X POST http://localhost:8080/health-checks/dns_example/run

# Executar todos os checks
curl -X POST http://localhost:8080/health-checks/run-all

# Histórico de execuções
curl http://localhost:8080/health-checks/history?name=dns_example&limit=50
```

**Status Response:**
```json
{
  "overall_status": "degraded",
  "summary": {
    "total": 4,
    "healthy": 3,
    "degraded": 1,
    "unhealthy": 0
  },
  "checks": {
    "dns_example": {
      "name": "dns_example",
      "status": "healthy",
      "message": "DNS resolved: 1.2.3.4",
      "duration_ms": 12.34,
      "timestamp": "2026-03-14T00:30:00"
    }
  }
}
```

**Check Stats:**
```json
{
  "name": "ssl_example",
  "description": "SSL certificate check for api.exemplo.com:443",
  "run_count": 142,
  "failure_count": 3,
  "success_rate": 97.89,
  "last_run": "2026-03-14T00:30:00",
  "last_status": "healthy"
}
```

**Testes:** 25 test cases cobrindo todos os tipos de check.

## 🦞 Meta-Monitoring (v2.7) 🆕

Monitora a saúde do próprio Mengão Monitor — garantindo que o monitor está saudável:

**Health Checks:**
- **Process Health** - CPU, memória, threads, arquivos abertos
- **Thread Health** - Status de todas as threads ativas
- **Memory Health** - Detalhes de uso de memória (RSS, VMS, USS, PSS)
- **Uptime Health** - Tempo de atividade e estabilidade

**Thresholds Configuráveis:**
```python
thresholds = {
    'cpu_percent': 80.0,      # Alerta se CPU > 80%
    'memory_percent': 90.0,   # Alerta se memória > 90%
    'memory_mb': 500.0,       # Alerta se > 500MB
    'threads': 50,            # Alerta se > 50 threads
    'open_files': 100,        # Alerta se > 100 arquivos abertos
    'response_time_ms': 1000, # Alerta se response time > 1s
}
```

**Endpoints de Gerenciamento:**
```bash
# Status geral do meta-monitor
curl http://localhost:8080/meta

# Executar todos os health checks
curl http://localhost:8080/meta/checks

# Histórico de health checks
curl http://localhost:8080/meta/history?limit=100&status=healthy

# Estatísticas
curl http://localhost:8080/meta/stats

# Thresholds (GET/PUT)
curl http://localhost:8080/meta/thresholds
curl -X PUT http://localhost:8080/meta/thresholds \
  -H "Content-Type: application/json" \
  -d '{"cpu_percent": 70.0, "memory_mb": 400.0}'

# Watchdog (start/stop)
curl -X POST http://localhost:8080/meta/watchdog/start
curl -X POST http://localhost:8080/meta/watchdog/stop
```

**Status Response:**
```json
{
  "overall_status": "healthy",
  "checks": {
    "process": {
      "name": "process_health",
      "status": "healthy",
      "message": "Processo saudável",
      "details": {
        "pid": 1234,
        "cpu_percent": 15.5,
        "memory_mb": 120.3,
        "memory_percent": 5.2,
        "threads": 12,
        "open_files": 25,
        "connections": 8,
        "uptime_seconds": 86400.5
      },
      "duration_ms": 12.34
    },
    "threads": { ... },
    "memory": { ... },
    "uptime": { ... }
  },
  "timestamp": "2026-03-14T01:40:00",
  "history_size": 142
}
```

**Watchdog:** Thread daemon que executa health checks periodicamente (padrão: 30s).

**Testes:** 20+ test cases cobrindo todos os health checks e funcionalidades.

## 📊 SLA Reporting (v2.9) 🆕

Relatórios automáticos de SLA com uptime, response time, incidents e MTTR:

**Endpoints:**
```bash
# Relatório de SLA para um endpoint (JSON)
curl http://localhost:8080/sla/report/api_prod?period=24

# Relatório em HTML (dashboard)
curl http://localhost:8080/sla/report/api_prod?format=html

# Relatório em CSV
curl http://localhost:8080/sla/report/api_prod?format=csv

# Relatório para todos os endpoints
curl http://localhost:8080/sla/reports?period=168

# Listar incidentes abertos
curl http://localhost:8080/sla/incidents?open=true

# Registrar incidente
curl -X POST http://localhost:8080/sla/incidents \
  -H "Content-Type: application/json" \
  -d '{"endpoint_name": "api_prod", "reason": "timeout"}'

# Resolver incidente
curl -X POST http://localhost:8080/sla/incidents/api_prod/resolve

# Configurar target de SLA
curl -X PUT http://localhost:8080/sla/targets \
  -H "Content-Type: application/json" \
  -d '{"endpoint_name": "api_prod", "target": 99.99}'
```

**Métricas de SLA:**
- **Uptime %** - Percentual de disponibilidade
- **Response Time** - Avg, P95, P99, Min, Max
- **Incidents** - Contagem e duração total
- **MTTR** - Mean Time To Recovery
- **SLA Breaches** - Janelas de 1h abaixo do target

**Export Formats:**
- **JSON** - Para integração com APIs
- **HTML** - Dashboard visual com status badges
- **CSV** - Para planilhas e análises

**Testes:** 25 test cases cobrindo métricas, incidentes, exports e thread safety.

## 🔌 WebSocket para Updates em Tempo Real (v3.0) 🆕

Servidor WebSocket para receber updates do monitor em tempo real no dashboard:

**Canais disponíveis:**
- **status** - Updates de status das APIs (online, offline, timeout)
- **metrics** - Métricas de sistema (CPU, memória, disco)
- **alerts** - Alertas enviados (webhooks, email)
- **health_checks** - Resultados de health checks
- **sla** - Updates de SLA (uptime, incidents)

**Endpoints de Gerenciamento:**
```bash
# Status do servidor WebSocket
curl http://localhost:8080/websocket/status

# Iniciar servidor (requer auth admin)
curl -X POST http://localhost:8080/websocket/start \
  -H "Authorization: Bearer mm_token" \
  -H "Content-Type: application/json" \
  -d '{"host": "localhost", "port": 8082}'

# Parar servidor (requer auth admin)
curl -X POST http://localhost:8080/websocket/stop

# Listar clientes conectados
curl http://localhost:8080/websocket/clients

# Enviar broadcast manual (requer auth write)
curl -X POST http://localhost:8080/websocket/broadcast \
  -H "Authorization: Bearer mm_token" \
  -H "Content-Type: application/json" \
  -d '{"channel": "alerts", "type": "test", "data": {"message": "Test alert"}}'
```

**Configuração:**
```json
{
  "websocket": {
    "enabled": true,
    "host": "localhost",
    "port": 8082,
    "ping_interval": 30,
    "ping_timeout": 10,
    "max_history": 100
  }
}
```

**Protocolo de Mensagens:**

*Conexão:*
```javascript
const ws = new WebSocket('ws://localhost:8082');

// Recebe welcome message
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  console.log(msg.type, msg.data);
};
```

*Subscribe a canais:*
```javascript
// Inscrever em canais
ws.send(JSON.stringify({
  type: 'subscribe',
  channels: ['status', 'metrics', 'alerts']
}));

// Recebe confirmação
// { type: 'subscribed', data: { channels: ['status', 'metrics', 'alerts'] } }
```

*Receber updates:*
```javascript
// Update de status
// { type: 'status_update', data: { api: 'API Prod', status: 'online', ... }, timestamp: '...' }

// Update de métricas
// { type: 'metrics_update', data: { cpu: 45.2, memory: 62.1, ... }, timestamp: '...' }

// Alerta
// { type: 'alert', data: { endpoint: 'API Prod', event: 'down', ... }, timestamp: '...' }
```

*Ping/Pong:*
```javascript
// Enviar ping
ws.send(JSON.stringify({ type: 'ping' }));

// Recebe pong
// { type: 'pong', data: { timestamp: '...' } }
```

*Histórico:*
```javascript
// Solicitar histórico de mensagens
ws.send(JSON.stringify({
  type: 'get_history',
  channel: 'status',  // opcional
  limit: 10
}));

// Recebe histórico
// { type: 'history', data: { messages: [...] } }
```

**Status Response:**
```json
{
  "websocket": {
    "connections_total": 15,
    "connections_active": 3,
    "messages_sent": 1247,
    "messages_received": 89,
    "errors": 0,
    "started_at": "2026-03-14T05:00:00",
    "clients": {
      "client_1234": {
        "connected_at": "2026-03-14T05:01:00",
        "subscriptions": ["status", "metrics"],
        "last_ping": "2026-03-14T05:05:00"
      }
    },
    "subscriptions": {
      "status": ["client_1234"],
      "metrics": ["client_1234"]
    }
  },
  "timestamp": "2026-03-14T05:06:00"
}
```

**Testes:** 19 test cases cobrindo mensagens, clientes, subscriptions e broadcast.

## 🔔 Notification Manager (v3.1) 🆕

Sistema unificado de notificações com regras, rate limiting e múltiplos canais:

**Canais suportados:**
- **websocket** - Broadcast para clientes WebSocket conectados
- **discord** - Webhooks Discord (via `webhooks.py`)
- **slack** - Webhooks Slack (via `webhooks.py`)
- **telegram** - Bot Telegram (via `webhooks.py`)
- **email** - SMTP (via `email_alerts.py`)

**Prioridades:**
- **low** - Informativo (ex: config reload)
- **medium** - Aviso (ex: response time alto)
- **high** - Alerta (ex: endpoint down)
- **critical** - Crítico (ex: múltiplos endpoints down)

**Endpoints:**
```bash
# Estatísticas do gerenciador
curl http://localhost:8080/notifications

# Histórico de notificações
curl http://localhost:8080/notifications/history?limit=50&priority=high

# Enviar notificação manual (requer auth write)
curl -X POST http://localhost:8080/notifications/send \
  -H "Authorization: Bearer mm_token" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Alert",
    "message": "This is a test notification",
    "priority": "high",
    "endpoint": "/api/test",
    "channels": ["websocket", "discord"]
  }'

# Listar regras
curl http://localhost:8080/notifications/rules

# Adicionar regra (requer auth admin)
curl -X POST http://localhost:8080/notifications/rules \
  -H "Authorization: Bearer mm_token" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "critical_alerts",
    "channels": ["websocket", "discord", "telegram"],
    "priority_filter": ["high", "critical"],
    "cooldown_seconds": 60,
    "rate_limit_per_hour": 5
  }'
```

**Configuração:**
```json
{
  "notifications": {
    "enabled": true,
    "max_history": 1000,
    "rules": [
      {
        "name": "critical_alerts",
        "enabled": true,
        "channels": ["websocket", "discord"],
        "priority_filter": ["high", "critical"],
        "cooldown_seconds": 60,
        "rate_limit_per_hour": 5
      },
      {
        "name": "all_websocket",
        "enabled": true,
        "channels": ["websocket"],
        "cooldown_seconds": 0,
        "rate_limit_per_hour": 1000
      }
    ]
  }
}
```

**Regras de Notificação:**
- **name** - Identificador único da regra
- **enabled** - Ativar/desativar regra
- **channels** - Canais de entrega
- **priority_filter** - Prioridades aceitas (vazio = todas)
- **endpoint_filter** - Endpoints específicos (vazio = todos)
- **cooldown_seconds** - Tempo entre notificações similares
- **rate_limit_per_hour** - Máximo de notificações por hora

**Stats Response:**
```json
{
  "notifications_total": 142,
  "notifications_sent": 135,
  "notifications_failed": 2,
  "notifications_suppressed": 5,
  "by_priority": {"low": 45, "medium": 62, "high": 28, "critical": 7},
  "by_channel": {"websocket": 142, "discord": 35, "telegram": 7},
  "rules": {
    "critical_alerts": {
      "enabled": true,
      "channels": ["websocket", "discord"],
      "cooldown_seconds": 60,
      "rate_limit_per_hour": 5
    }
  },
  "recent_notifications": [...]
}
```

**Testes:** 25 test cases cobrindo regras, rate limiting, cooldown, filtros e edge cases.

## ⚙️ Config Watcher (v2.8) 🆕

Gerencie o hot-reload de configuração via API:

**Endpoints:**
```bash
# Status do config watcher
curl http://localhost:8080/config/watcher

# Força reload imediato (requer auth write)
curl -X POST http://localhost:8080/config/watcher/reload 
  -H "Authorization: Bearer mm_token"

# Histórico de diffs
curl http://localhost:8080/config/watcher/history?limit=10

# Iniciar watcher (requer auth admin)
curl -X POST http://localhost:8080/config/watcher/start

# Parar watcher (requer auth admin)
curl -X POST http://localhost:8080/config/watcher/stop
```

**Status Response:**
```json
{
  "watcher": {
    "config_path": "config.json",
    "running": true,
    "check_interval": 5,
    "reload_count": 3,
    "last_reload": "2026-03-14T03:00:00",
    "error_count": 0,
    "last_error": null,
    "file_exists": true,
    "file_size": 1024
  },
  "diff_history_size": 3,
  "timestamp": "2026-03-14T03:00:00"
}
```

**Histórico de Diffs:**
```json
{
  "history": [
    {
      "timestamp": "2026-03-14T03:00:00",
      "added": [{"key": "email", "value": {...}}],
      "removed": [],
      "modified": [{"key": "endpoints", "old": [...], "new": [...]}]
    }
  ],
  "total": 3
}
```

**Testes:** 18 test cases (ConfigWatcher + ConfigDiff).

## 🚨 Alert Escalation (v3.2) 🆕

Sistema de escalação automática de alertas por níveis (L1 → L2 → L3) com políticas configuráveis:

**Níveis de Escalação:**
- **L1** (Primeiro contato) - Webhook padrão, WebSocket
- **L2** (Escalação) - Múltiplos canais (Discord, Slack)
- **L3** (Crítico) - Todos os canais + on-call (Telegram, Email)

**Endpoints:**
```bash
# Listar políticas de escalação
curl http://localhost:8080/escalation/policies

# Adicionar política (requer auth admin)
curl -X POST http://localhost:8080/escalation/policies \
  -H "Authorization: Bearer mm_token" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Critical API",
    "endpoint": "api.prod.com",
    "l1_timeout": 300,
    "l2_timeout": 900,
    "l3_timeout": 1800,
    "l1_channels": ["websocket"],
    "l2_channels": ["websocket", "discord"],
    "l3_channels": ["websocket", "discord", "telegram"],
    "max_escalations_per_hour": 5
  }'

# Remover política
curl -X DELETE http://localhost:8080/escalation/policies/api.prod.com

# Listar alertas ativos
curl http://localhost:8080/escalation/alerts

# Detalhe de um alerta
curl http://localhost:8080/escalation/alerts/abc123

# Reconhecer alerta (para escalação)
curl -X POST http://localhost:8080/escalation/alerts/abc123/acknowledge \
  -H "Authorization: Bearer mm_token" \
  -d '{"acknowledged_by": "admin"}'

# Resolver alerta
curl -X POST http://localhost:8080/escalation/alerts/abc123/resolve \
  -H "Authorization: Bearer mm_token" \
  -d '{"reason": "Fixed"}'

# Estatísticas
curl http://localhost:8080/escalation/stats
```

**Política de Escalação:**
```json
{
  "name": "Production API",
  "endpoint": "api.prod.com",
  "enabled": true,
  "l1_timeout": 300,      // 5 min → L2
  "l2_timeout": 900,      // 15 min → L3
  "l3_timeout": 1800,     // 30 min → expira
  "l1_channels": ["websocket"],
  "l2_channels": ["websocket", "discord"],
  "l3_channels": ["websocket", "discord", "telegram"],
  "max_escalations_per_hour": 5,
  "quiet_hours_start": 22,
  "quiet_hours_end": 6,
  "quiet_hours_escalate_anyway": false
}
```

**Fluxo de Escalação:**
```
Alerta criado (L1)
  ↓ (5 min sem acknowledge)
Escalação (L2) → Discord
  ↓ (15 min sem acknowledge)
Escalação (L3) → Telegram + on-call
  ↓ (30 min sem resolução)
Expira → Histórico
```

**Estados do Alerta:**
- **active** - L1, aguardando ação
- **escalated** - L2 ou L3, notificações enviadas
- **acknowledged** - Alguém reconheceu (para escalação)
- **resolved** - Problema resolvido
- **expired** - Timeout máximo atingido

**Reconhecimento (Acknowledge):**
Quando um alerta é reconhecido, ele para de escalar. Isso permite que a equipe responda sem pressão de escalação automática.

**Rate Limiting:**
- Máximo de N escalações por hora por endpoint
- Previne flood de notificações em falhas intermitentes

**Horário Silencioso:**
- Configure quiet hours (ex: 22h-6h)
- L3 sempre escala mesmo em quiet hours (opcional)

**Testes:** 27 test cases cobrindo políticas, escalação, acknowledge, resolve, rate limiting e edge cases.

## 🖥️ Dashboard v3 (v3.3) 🆕

Dashboard moderno com updates em tempo real via WebSocket:

**Features:**
- **WebSocket nativo** - Updates instantâneos sem polling
- **Gráficos Chart.js** - Response time e métricas de sistema em tempo real
- **Alert timeline** - Visualização de alertas em escalação (L1/L2/L3)
- **Notification feed** - Stream de notificações ao vivo
- **Dark theme rubro-negro** - Cores do Mengão 🦞
- **Auto-reconnect** - Reconexão automática com backoff exponencial
- **Responsive** - Funciona em desktop e mobile

**Endpoint:**
```
http://localhost:8080/dashboard/v3
```

**Canais WebSocket:**
- `status` - Updates de status das APIs
- `metrics` - Métricas de sistema (CPU, memória, disco)
- `alerts` - Alertas em escalação
- `notifications` - Feed de notificações

**Arquitetura:**
```
Browser ←→ WebSocket (ws://localhost:8082)
                ↓
         Dashboard v3 (HTML/JS)
                ↓
    ┌───────────┼───────────┐
    ↓           ↓           ↓
Status API  Metrics    Alerts
    ↓           ↓           ↓
Chart.js    Chart.js   Alert List
```

**Configuração:**
```python
from dashboard_v3 import DashboardV3, DashboardConfig

config = DashboardConfig(
    title="Mengão Monitor",
    websocket_url="ws://localhost:8082",
    show_flamengo_badge=True,
    chart_history_points=60
)

dashboard = DashboardV3(config)
html = dashboard.render_html(apis=apis, alerts=alerts)
```

**Testes:** 40 test cases cobrindo renderização, listas, cálculos e integração.
