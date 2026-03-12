# 🦞 Mengão Monitor

> Monitor de APIs simples, eficiente e rubro-negro.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-pytest-green.svg)](https://docs.pytest.org/)

Monitoramento de APIs com alertas via webhook. Feito com Python puro, sem firulas.

## ⚡ Instalação

```bash
git clone https://github.com/Derrota/mengao-monitor.git
cd mengao-monitor
pip install -r requirements.txt
cp config.example.json config.json
# Edite config.json com suas APIs
```

## 🚀 Uso

```bash
# Monitor básico
python monitor.py

# Com health check endpoint
python monitor.py --health --health-port 8080

# Config customizado
python monitor.py -c meu_config.json
```

## 📋 Configuração

`config.json`:
```json
{
  "check_interval": 60,
  "log_file": "monitor.log",
  "webhook_url": "https://discord.com/api/webhooks/SEU_WEBHOOK",
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

## 🏥 Health Check

Quando habilitado com `--health`, expõe endpoints:

- `GET /health` - Health check básico
- `GET /status` - Status detalhado (uptime, memória, CPU)
- `GET /metrics` - Métricas no formato Prometheus

```bash
curl http://localhost:8080/health
# {"status":"healthy","service":"mengao-monitor","timestamp":"..."}

curl http://localhost:8080/status
# {"service":"mengao-monitor","version":"1.1.0","uptime_seconds":120,...}
```

## 🧪 Testes

```bash
pytest test_monitor.py -v
pytest test_monitor.py --cov=monitor
```

## 🏗️ Arquitetura

```
mengao-monitor/
├── monitor.py          # Monitor principal
├── health.py           # Health check server (Flask)
├── test_monitor.py     # Testes unitários
├── config.example.json # Config de exemplo
├── requirements.txt    # Dependências
└── README.md          # Este arquivo
```

### Fluxo

1. Carrega `config.json`
2. Para cada API na lista:
   - Faz request HTTP
   - Compara status com `expected_status`
   - Se diferente de `online`, envia webhook
3. Aguarda `check_interval` segundos
4. Repete

## 📤 Webhooks

Envia alertas Discord embed quando API está:
- ❌ **Offline** - Erro de conexão
- ⏰ **Timeout** - Timeout excedido
- ⚠️ **Error** - Status inesperado

Não envia alerta quando API está online (só quando dá ruim).

## 📝 Logs

Logs são salvos em `monitor.log` (configurável) e exibidos no console:

```
2026-03-12 13:00:00 - INFO - 🦞 Mengão Monitor iniciado!
2026-03-12 13:00:00 - INFO - 📊 Monitorando 3 APIs
2026-03-12 13:00:01 - INFO - ✅ Minha API - Online (0.234s)
2026-03-12 13:00:02 - ERROR - ❌ API Caída - Offline
```

## 🦞 Por que "Mengão"?

Porque assim como o Flamengo, este monitor:
- Nunca desiste (loop infinito de verificações)
- É eficiente (pouco overhead)
- Avisa quando algo está errado (webhooks)

---

**Feito com 🔴⚫ por [Derrota](https://github.com/Derrota)**
