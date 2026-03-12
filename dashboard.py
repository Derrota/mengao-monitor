"""
Dashboard HTML simples para Mengão Monitor 🦞
"""

from flask import render_template_string
from datetime import datetime
from typing import Dict

DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🦞 Mengão Monitor</title>
    <meta http-equiv="refresh" content="30">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0a0a;
            color: #e0e0e0;
            min-height: 100vh;
        }
        .header {
            background: linear-gradient(135deg, #c8102e 0%, #1a1a1a 100%);
            padding: 20px;
            text-align: center;
            border-bottom: 3px solid #c8102e;
        }
        .header h1 { font-size: 2em; }
        .header .subtitle { color: #aaa; margin-top: 5px; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: #1a1a1a;
            border-radius: 8px;
            padding: 20px;
            border-left: 4px solid #c8102e;
        }
        .stat-card .label { color: #888; font-size: 0.9em; }
        .stat-card .value { font-size: 1.8em; font-weight: bold; margin-top: 5px; }
        .stat-card .value.green { color: #2ecc71; }
        .stat-card .value.red { color: #e74c3c; }
        .stat-card .value.yellow { color: #f39c12; }
        .api-list { display: flex; flex-direction: column; gap: 15px; }
        .api-card {
            background: #1a1a1a;
            border-radius: 8px;
            padding: 20px;
            display: grid;
            grid-template-columns: 1fr auto;
            align-items: center;
            gap: 20px;
        }
        .api-card .api-name { font-size: 1.2em; font-weight: bold; }
        .api-card .api-url { color: #888; font-size: 0.85em; margin-top: 4px; }
        .api-card .api-meta { color: #666; font-size: 0.8em; margin-top: 8px; }
        .status-badge {
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 0.9em;
        }
        .status-badge.online { background: #2ecc71; color: #000; }
        .status-badge.offline { background: #e74c3c; color: #fff; }
        .status-badge.timeout { background: #f39c12; color: #000; }
        .status-badge.error { background: #e67e22; color: #fff; }
        .footer {
            text-align: center;
            padding: 20px;
            color: #666;
            margin-top: 40px;
        }
        .footer a { color: #c8102e; text-decoration: none; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🦞 Mengão Monitor</h1>
        <div class="subtitle">Monitor de APIs rubro-negro</div>
    </div>
    
    <div class="container">
        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">Status Geral</div>
                <div class="value {{ 'green' if overall_status == 'healthy' else 'red' }}">
                    {{ overall_status | upper }}
                </div>
            </div>
            <div class="stat-card">
                <div class="label">APIs Monitoradas</div>
                <div class="value">{{ apis | length }}</div>
            </div>
            <div class="stat-card">
                <div class="label">Uptime Médio (24h)</div>
                <div class="value {{ 'green' if avg_uptime > 99 else 'yellow' if avg_uptime > 95 else 'red' }}">
                    {{ avg_uptime }}%
                </div>
            </div>
            <div class="stat-card">
                <div class="label">Última Verificação</div>
                <div class="value" style="font-size: 1.2em;">{{ last_check }}</div>
            </div>
        </div>
        
        <h2 style="margin-bottom: 15px;">📊 APIs</h2>
        <div class="api-list">
            {% for api in apis %}
            <div class="api-card">
                <div>
                    <div class="api-name">{{ api.name }}</div>
                    <div class="api-url">{{ api.url }}</div>
                    <div class="api-meta">
                        ⏱️ {{ api.response_time or 'N/A' }}s | 
                        📈 {{ api.uptime }}% uptime (24h) |
                        🔄 {{ api.checks }} checks
                    </div>
                </div>
                <div class="status-badge {{ api.status }}">{{ api.status | upper }}</div>
            </div>
            {% endfor %}
        </div>
    </div>
    
    <div class="footer">
        <p>🦞 Feito com 🔴⚫ por <a href="https://github.com/Derrota">Derrota</a></p>
        <p>Auto-refresh a cada 30s</p>
    </div>
</body>
</html>
"""


def render_dashboard(state: Dict, history=None) -> str:
    """Renderiza dashboard HTML."""
    apis = state.get('apis', [])
    
    # Calcula stats
    online_count = sum(1 for a in apis if a.get('status') == 'online')
    overall = 'healthy' if online_count == len(apis) else 'degraded' if online_count > 0 else 'down'
    
    # Uptime médio
    uptimes = [a.get('uptime', 0) for a in apis]
    avg_uptime = round(sum(uptimes) / len(uptimes), 1) if uptimes else 0
    
    last_check = state.get('last_check', 'Nunca')
    if last_check != 'Nunca':
        try:
            dt = datetime.fromisoformat(last_check)
            last_check = dt.strftime('%H:%M:%S')
        except:
            pass
    
    return render_template_string(
        DASHBOARD_TEMPLATE,
        overall_status=overall,
        apis=apis,
        avg_uptime=avg_uptime,
        last_check=last_check
    )
