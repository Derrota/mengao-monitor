"""
Dashboard v2 com gráficos Chart.js para Mengão Monitor 🦞
Uptime history, response time charts, webhook stats.
"""

from flask import render_template_string
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json


DASHBOARD_V2_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🦞 Mengão Monitor v2</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
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
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
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
        .stat-card .value.blue { color: #3498db; }
        
        .charts-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .chart-card {
            background: #1a1a1a;
            border-radius: 8px;
            padding: 20px;
        }
        .chart-card h3 {
            margin-bottom: 15px;
            color: #c8102e;
            font-size: 1.1em;
        }
        .chart-container {
            position: relative;
            height: 250px;
        }
        
        .webhook-stats {
            background: #1a1a1a;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 30px;
        }
        .webhook-stats h3 {
            color: #c8102e;
            margin-bottom: 15px;
        }
        .webhook-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
        }
        .webhook-stat {
            text-align: center;
            padding: 15px;
            background: #252525;
            border-radius: 6px;
        }
        .webhook-stat .count { font-size: 1.5em; font-weight: bold; }
        .webhook-stat .label { color: #888; font-size: 0.85em; margin-top: 5px; }
        
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
        
        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        .tab {
            padding: 10px 20px;
            background: #252525;
            border: none;
            border-radius: 6px;
            color: #e0e0e0;
            cursor: pointer;
            transition: all 0.2s;
        }
        .tab:hover, .tab.active {
            background: #c8102e;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🦞 Mengão Monitor</h1>
        <div class="subtitle">Monitor de APIs rubro-negro v2.0</div>
    </div>
    
    <div class="container">
        <!-- Stats Overview -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">Status Geral</div>
                <div class="value {{ 'green' if overall_status == 'healthy' else 'red' }}">
                    {{ overall_status | upper }}
                </div>
            </div>
            <div class="stat-card">
                <div class="label">APIs Monitoradas</div>
                <div class="value blue">{{ apis | length }}</div>
            </div>
            <div class="stat-card">
                <div class="label">Uptime Médio (24h)</div>
                <div class="value {{ 'green' if avg_uptime > 99 else 'yellow' if avg_uptime > 95 else 'red' }}">
                    {{ avg_uptime }}%
                </div>
            </div>
            <div class="stat-card">
                <div class="label">Alertas Enviados</div>
                <div class="value yellow">{{ webhook_stats.sent }}</div>
            </div>
        </div>
        
        <!-- Webhook Stats -->
        <div class="webhook-stats">
            <h3>📊 Webhook Statistics</h3>
            <div class="webhook-grid">
                <div class="webhook-stat">
                    <div class="count green">{{ webhook_stats.sent }}</div>
                    <div class="label">Sent</div>
                </div>
                <div class="webhook-stat">
                    <div class="count red">{{ webhook_stats.failed }}</div>
                    <div class="label">Failed</div>
                </div>
                <div class="webhook-stat">
                    <div class="count yellow">{{ webhook_stats.retries }}</div>
                    <div class="label">Retries</div>
                </div>
                <div class="webhook-stat">
                    <div class="count blue">{{ webhook_stats.rate_limited }}</div>
                    <div class="label">Rate Limited</div>
                </div>
                <div class="webhook-stat">
                    <div class="count">{{ webhook_stats.cooldown_skipped }}</div>
                    <div class="label">Cooldown Skipped</div>
                </div>
            </div>
        </div>
        
        <!-- Charts -->
        <div class="charts-grid">
            <div class="chart-card">
                <h3>📈 Uptime por API (24h)</h3>
                <div class="chart-container">
                    <canvas id="uptimeChart"></canvas>
                </div>
            </div>
            <div class="chart-card">
                <h3>⏱️ Response Time (ms)</h3>
                <div class="chart-container">
                    <canvas id="responseTimeChart"></canvas>
                </div>
            </div>
        </div>
        
        <!-- API List -->
        <h2 style="margin-bottom: 15px;">🔍 APIs Monitoradas</h2>
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
        <p>Auto-refresh a cada 30s | v2.0</p>
    </div>
    
    <script>
        // Uptime Chart
        const uptimeCtx = document.getElementById('uptimeChart').getContext('2d');
        new Chart(uptimeCtx, {
            type: 'bar',
            data: {
                labels: {{ api_names | tojson }},
                datasets: [{
                    label: 'Uptime %',
                    data: {{ api_uptimes | tojson }},
                    backgroundColor: {{ api_colors | tojson }},
                    borderColor: {{ api_colors | tojson }},
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100,
                        ticks: { color: '#888' },
                        grid: { color: '#333' }
                    },
                    x: {
                        ticks: { color: '#888' },
                        grid: { color: '#333' }
                    }
                },
                plugins: {
                    legend: { display: false }
                }
            }
        });
        
        // Response Time Chart
        const rtCtx = document.getElementById('responseTimeChart').getContext('2d');
        new Chart(rtCtx, {
            type: 'line',
            data: {
                labels: {{ api_names | tojson }},
                datasets: [{
                    label: 'Response Time (ms)',
                    data: {{ api_response_times | tojson }},
                    borderColor: '#c8102e',
                    backgroundColor: 'rgba(200, 16, 46, 0.1)',
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: { color: '#888' },
                        grid: { color: '#333' }
                    },
                    x: {
                        ticks: { color: '#888' },
                        grid: { color: '#333' }
                    }
                },
                plugins: {
                    legend: { display: false }
                }
            }
        });
    </script>
</body>
</html>
"""


def render_dashboard_v2(
    state: Dict,
    webhook_stats: Optional[Dict] = None,
    history_stats: Optional[Dict] = None
) -> str:
    """Renderiza dashboard v2 com gráficos Chart.js."""
    apis = state.get('apis', [])
    
    # Calcula stats
    online_count = sum(1 for a in apis if a.get('status') == 'online')
    overall = 'healthy' if online_count == len(apis) else 'degraded' if online_count > 0 else 'down'
    
    # Uptime médio
    uptimes = [a.get('uptime', 0) for a in apis]
    avg_uptime = round(sum(uptimes) / len(uptimes), 1) if uptimes else 0
    
    # Dados para gráficos
    api_names = [a.get('name', 'unknown') for a in apis]
    api_uptimes = [a.get('uptime', 0) for a in apis]
    api_response_times = [
        round(a.get('response_time', 0) * 1000) if a.get('response_time') else 0
        for a in apis
    ]
    
    # Cores baseadas no uptime
    api_colors = []
    for uptime in api_uptimes:
        if uptime >= 99:
            api_colors.append('#2ecc71')  # green
        elif uptime >= 95:
            api_colors.append('#f39c12')  # yellow
        else:
            api_colors.append('#e74c3c')  # red
    
    # Default webhook stats
    if webhook_stats is None:
        webhook_stats = {
            'sent': 0,
            'failed': 0,
            'retries': 0,
            'rate_limited': 0,
            'cooldown_skipped': 0
        }
    
    return render_template_string(
        DASHBOARD_V2_TEMPLATE,
        overall_status=overall,
        apis=apis,
        avg_uptime=avg_uptime,
        webhook_stats=webhook_stats,
        api_names=api_names,
        api_uptimes=api_uptimes,
        api_response_times=api_response_times,
        api_colors=api_colors
    )
