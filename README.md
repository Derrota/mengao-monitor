# Mengão Monitor 🦞

Monitor de APIs simples e eficiente. Verifica se suas APIs estão online e manda alertas quando caem.

## Features

- ✅ Monitoramento de múltiplas APIs
- ✅ Alertas por webhook (Discord, Slack, etc.)
- ✅ Logs detalhados
- ✅ Configuração via JSON
- ✅ Leve e rápido

## Instalação

```bash
pip install -r requirements.txt
```

## Configuração

Edite o arquivo `config.json` com suas APIs:

```json
{
  "apis": [
    {
      "name": "Minha API",
      "url": "https://api.exemplo.com/health",
      "method": "GET",
      "timeout": 5,
      "expected_status": 200
    }
  ],
  "check_interval": 300,
  "webhook_url": "https://discord.com/api/webhooks/..."
}
```

## Uso

```bash
python monitor.py
```

## Sobre

Feito com Python e amor rubro-negro. Uma vez Flamengo, sempre Flamengo. 🔴⚫️
