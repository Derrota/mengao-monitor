# 🦞 Mengão Monitor

> Monitor de APIs simples, eficiente e rubro-negro.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-pytest-green.svg)](https://docs.pytest.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

Monitoramento de APIs com alertas via webhook (Discord, Slack, Telegram), histórico de uptime em SQLite e dashboard HTML. Feito com Python puro, sem firulas.

## ⚡ Instalação

```bash
git clone https://github.com/Derrota/mengao-monitor.git
cd mengao-monitor
pip install -r requirements.txt
cp config.example.json config.json
# Edite config.json com suas APIs e webhooks
```

### Docker

```bash
# Build e run
docker compose up -d

# Ou manual
docker build -t mengao-monitor .
docker run -d -v ./data:/data -p 8080:8080 mengao-monitor
```

## 🚀 Uso

```bash
# Monitor básico
python monitor.py

# Com health check + dashboard
python monitor.py --health --health-port 8080

# Config customizado
python monitor.py -c meu_config.json

# Ver estatísticas
python monitor.py --stats

# Exportar histórico
python monitor.py --export-csv historico.csv
```

## 📋 Configuração

`config.json`:
```json
{
  "check_interval": 300,
  "log_file": "monitor.log",
  "log_level": "INFO",
  "history_db": "uptime.db",
  "webhook_cooldown": 300,
  
  "webhooks": [
    {"type": "discord", "url": "https://discord.com/api/webhooks/..."},
    {"type": "slack", "url": "https://hooks.slack.com/services/..."},
    {"type": "telegram", "url": "https://api.telegram.org/botTOKEN", "chat_id": "123"}
  ],
  
  "apis": [
    {
      "name": "Minha API",
      "url": "https://api.exemplo.com/health",
      "method": "GET",
      "timeout": 5,
      "expected_status": 200
    }
  ]
}
```

### Campos da API

| Campo | Obrigatório | Default | Descrição |
|-------|-------------|---------|-----------|
| `name` | ✅ | - | Nome da API |
| `url` | ✅ | - | URL para verificar |
| `method` | ❌ | GET | Método HTTP |
| `timeout` | ❌ | 5 | Timeout em segundos |
| `expected_status` | ❌ | 200 | Status code esperado |

### Webhooks

Suporta múltiplos webhooks simultâneos:

| Tipo | Campos obrigatórios |
|------|-------------------|
| `discord` | `url` |
| `slack` | `url` |
| `telegram` | `url`, `chat_id` |

**Cooldown**: Alertas do mesmo endpoint só são reenviados após `webhook_cooldown` segundos (default: 5 min).

## 🏥 Health Check + Dashboard

Quando habilitado com `--health`, expõe endpoints:

| Endpoint | Descrição |
|----------|-----------|
| `GET /` | Dashboard HTML com auto-refresh |
| `GET /health` | Health check básico (JSON) |
| `GET /status` | Status detalhado com uptime, memória, CPU |
| `GET /metrics` | Métricas Prometheus |
| `GET /apis` | Lista de APIs com status |

```bash
curl http://localhost:8080/health
# {"status":"healthy","service":"mengao-monitor","version":"1.2.0",...}

curl http://localhost:8080/apis
# {"apis": [...], "last_check": "...", "checks_count": 42}
```

## 📊 Histórico de Uptime

Histórico é salvo automaticamente em SQLite (`uptime.db`):

```bash
# Ver estatísticas
python monitor.py --stats

# Exportar CSV
python monitor.py --export-csv uptime_24h.csv
```

**Limpeza automática**: Registros com mais de 30 dias são removidos a cada 100 checks.

## 🧪 Testes

```bash
pytest test_monitor.py -v
pytest test_monitor.py --cov=monitor --cov=webhooks --cov=history
```

## 🏗️ Arquitetura

```
mengao-monitor/
├── monitor.py          # Monitor principal (loop + CLI)
├── health.py           # Health check server (Flask)
├── dashboard.py        # Dashboard HTML
├── webhooks.py         # Multi-webhook (Discord/Slack/Telegram)
├── history.py          # Uptime history (SQLite)
├── test_monitor.py     # Testes unitários
├── config.example.json # Config de exemplo
├── Dockerfile          # Container
├── docker-compose.yml  # Docker Compose
├── requirements.txt    # Dependências
└── README.md           # Este arquivo
```

### Fluxo

1. Carrega `config.json`
2. Para cada API na lista:
   - Faz request HTTP
   - Compara status com `expected_status`
   - Registra no histórico SQLite
   - Se diferente de `online`, envia webhooks (com cooldown)
3. Atualiza dashboard/health endpoints
4. Aguarda `check_interval` segundos
5. Repete

## 📤 Webhooks

Envia alertas quando API está:
- ❌ **Offline** - Erro de conexão
- ⏰ **Timeout** - Timeout excedido  
- ⚠️ **Error** - Status inesperado

**Não envia alerta** quando API está online (só quando dá ruim).

### Formatos

**Discord**: Embed com cor por status
**Slack**: Blocks com header e fields
**Telegram**: Mensagem formatada com Markdown

## 📝 Logs

Logs são salvos em `monitor.log` (configurável) e exibidos no console:

```
2026-03-12 13:00:00 - INFO - 🦞 Mengão Monitor v1.2 iniciado!
2026-03-12 13:00:00 - INFO - 📊 Monitorando 3 APIs
2026-03-12 13:00:00 - INFO - 📤 Webhooks: 2 configurados
2026-03-12 13:00:01 - INFO - ✅ Minha API - Online (0.234s)
2026-03-12 13:00:02 - ERROR - ❌ API Caída - Offline
2026-03-12 13:00:02 - INFO - 📤 Webhook discord enviado para API Caída
```

## 🔄 Changelog

### v1.2 (2026-03-12)
- ✅ Multi-webhook: Discord, Slack, Telegram
- ✅ Cooldown anti-spam (5 min default)
- ✅ Uptime history em SQLite
- ✅ Dashboard HTML com auto-refresh
- ✅ Dockerfile + docker-compose
- ✅ CLI: `--stats`, `--export-csv`
- ✅ Endpoint `/apis` para status em JSON
- ✅ Métricas Prometheus por API

### v1.1 (2026-03-12)
- Health check endpoints
- Testes unitários
- CLI arguments

### v1.0 (2026-03-12)
- Monitor básico
- Webhook Discord
- Logging

## 🦞 Por que "Mengão"?

Porque assim como o Flamengo, este monitor:
- Nunca desiste (loop infinito de verificações)
- É eficiente (pouco overhead)
- Avisa quando algo está errado (webhooks)
- Tem histórico vitorioso (uptime tracking)

---

**Feito com 🔴⚫ por [Derrota](https://github.com/Derrota)**
