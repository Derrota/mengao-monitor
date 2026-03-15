"""
Dashboard v3 - Real-time Dashboard com WebSocket 🦞

Interface visual moderna com updates em tempo real via WebSocket.
Integra com Notification Manager e Alert Escalation.

Features:
- Gráficos Chart.js em tempo real
- WebSocket para updates instantâneos
- Alert escalation timeline
- Notification feed
- Dark theme rubro-negro
"""

import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from threading import Lock


@dataclass
class DashboardConfig:
    """Configuração do Dashboard v3"""
    title: str = "Mengão Monitor"
    theme: str = "dark"  # dark, light
    refresh_interval: int = 5  # seconds (fallback if no WebSocket)
    websocket_url: str = "ws://localhost:8082"
    max_alerts_display: int = 50
    max_notifications_display: int = 100
    chart_history_points: int = 60  # points on charts
    auto_refresh: bool = True
    show_flamengo_badge: bool = True


class DashboardV3:
    """Dashboard v3 com WebSocket e tempo real"""

    def __init__(self, config: Optional[DashboardConfig] = None):
        self.config = config or DashboardConfig()
        self._lock = Lock()
        self._stats = {
            "renders": 0,
            "last_render": None,
            "errors": 0
        }

    def get_stats(self) -> Dict:
        """Estatísticas do dashboard"""
        with self._lock:
            return dict(self._stats)

    def render_html(self, 
                    apis: List[Dict] = None,
                    alerts: List[Dict] = None,
                    notifications: List[Dict] = None,
                    escalation_stats: Dict = None,
                    system_metrics: Dict = None,
                    websocket_status: Dict = None) -> str:
        """
        Renderiza dashboard HTML completo com WebSocket.
        
        Args:
            apis: Lista de APIs monitoradas
            alerts: Alertas ativos
            notifications: Notificações recentes
            escalation_stats: Stats do alert escalation
            system_metrics: Métricas de sistema
            websocket_status: Status do WebSocket server
        """
        apis = apis or []
        alerts = alerts or []
        notifications = notifications or []
        escalation_stats = escalation_stats or {}
        system_metrics = system_metrics or {}
        websocket_status = websocket_status or {}

        with self._lock:
            self._stats["renders"] += 1
            self._stats["last_render"] = datetime.now().isoformat()

        # Calcular resumo
        total_apis = len(apis)
        online_apis = sum(1 for a in apis if a.get("status") == "online")
        offline_apis = total_apis - online_apis
        uptime_avg = self._calc_uptime_avg(apis)

        # Alertas por nível
        active_alerts = [a for a in alerts if a.get("status") in ("active", "escalated")]
        l1_alerts = sum(1 for a in active_alerts if a.get("level") == "L1")
        l2_alerts = sum(1 for a in active_alerts if a.get("level") == "L2")
        l3_alerts = sum(1 for a in active_alerts if a.get("level") == "L3")

        html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.config.title} - Dashboard v3</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        :root {{
            --fla-red: #dc143c;
            --fla-black: #1a1a1a;
            --fla-dark: #0d0d0d;
            --fla-gray: #2a2a2a;
            --fla-light: #3a3a3a;
            --text-primary: #ffffff;
            --text-secondary: #a0a0a0;
            --status-online: #00ff88;
            --status-offline: #ff4444;
            --status-degraded: #ffaa00;
            --level-l1: #ffaa00;
            --level-l2: #ff6600;
            --level-l3: #ff0000;
        }}

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: var(--fla-dark);
            color: var(--text-primary);
            min-height: 100vh;
        }}

        .header {{
            background: linear-gradient(135deg, var(--fla-red) 0%, var(--fla-black) 100%);
            padding: 1.5rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 3px solid var(--fla-red);
        }}

        .header h1 {{
            font-size: 1.8rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .header .badge {{
            background: var(--fla-black);
            padding: 0.3rem 0.8rem;
            border-radius: 20px;
            font-size: 0.8rem;
            animation: pulse 2s infinite;
        }}

        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.7; }}
        }}

        .ws-status {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.9rem;
        }}

        .ws-dot {{
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: var(--status-offline);
        }}

        .ws-dot.connected {{
            background: var(--status-online);
            box-shadow: 0 0 10px var(--status-online);
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 1.5rem;
        }}

        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 1.5rem;
        }}

        .summary-card {{
            background: var(--fla-gray);
            border-radius: 12px;
            padding: 1.2rem;
            border-left: 4px solid var(--fla-red);
            transition: transform 0.2s;
        }}

        .summary-card:hover {{
            transform: translateY(-2px);
        }}

        .summary-card h3 {{
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin-bottom: 0.5rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .summary-card .value {{
            font-size: 2rem;
            font-weight: bold;
        }}

        .summary-card .value.online {{ color: var(--status-online); }}
        .summary-card .value.offline {{ color: var(--status-offline); }}
        .summary-card .value.warning {{ color: var(--status-degraded); }}
        .summary-card .value.critical {{ color: var(--level-l3); }}

        .grid {{
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 1.5rem;
            margin-bottom: 1.5rem;
        }}

        @media (max-width: 1024px) {{
            .grid {{ grid-template-columns: 1fr; }}
        }}

        .panel {{
            background: var(--fla-gray);
            border-radius: 12px;
            overflow: hidden;
        }}

        .panel-header {{
            background: var(--fla-light);
            padding: 1rem 1.2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--fla-black);
        }}

        .panel-header h2 {{
            font-size: 1rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .panel-body {{
            padding: 1.2rem;
            max-height: 400px;
            overflow-y: auto;
        }}

        .chart-container {{
            height: 250px;
            position: relative;
        }}

        /* API List */
        .api-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.8rem;
            background: var(--fla-dark);
            border-radius: 8px;
            margin-bottom: 0.5rem;
            transition: background 0.2s;
        }}

        .api-item:hover {{
            background: var(--fla-black);
        }}

        .api-name {{
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .api-status {{
            padding: 0.2rem 0.6rem;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: bold;
            text-transform: uppercase;
        }}

        .api-status.online {{
            background: rgba(0, 255, 136, 0.2);
            color: var(--status-online);
        }}

        .api-status.offline {{
            background: rgba(255, 68, 68, 0.2);
            color: var(--status-offline);
        }}

        .api-status.degraded {{
            background: rgba(255, 170, 0, 0.2);
            color: var(--status-degraded);
        }}

        .api-meta {{
            font-size: 0.8rem;
            color: var(--text-secondary);
        }}

        /* Alerts */
        .alert-item {{
            padding: 0.8rem;
            background: var(--fla-dark);
            border-radius: 8px;
            margin-bottom: 0.5rem;
            border-left: 3px solid var(--level-l1);
        }}

        .alert-item.L2 {{ border-left-color: var(--level-l2); }}
        .alert-item.L3 {{ border-left-color: var(--level-l3); }}

        .alert-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.3rem;
        }}

        .alert-level {{
            padding: 0.15rem 0.5rem;
            border-radius: 8px;
            font-size: 0.7rem;
            font-weight: bold;
        }}

        .alert-level.L1 {{ background: var(--level-l1); color: black; }}
        .alert-level.L2 {{ background: var(--level-l2); color: white; }}
        .alert-level.L3 {{ background: var(--level-l3); color: white; }}

        .alert-time {{
            font-size: 0.75rem;
            color: var(--text-secondary);
        }}

        .alert-endpoint {{
            font-weight: 600;
            margin-bottom: 0.2rem;
        }}

        .alert-reason {{
            font-size: 0.85rem;
            color: var(--text-secondary);
        }}

        /* Notifications */
        .notif-item {{
            padding: 0.6rem 0.8rem;
            border-bottom: 1px solid var(--fla-light);
            font-size: 0.85rem;
        }}

        .notif-item:last-child {{ border-bottom: none; }}

        .notif-time {{
            font-size: 0.7rem;
            color: var(--text-secondary);
        }}

        .notif-title {{
            font-weight: 600;
            margin-bottom: 0.2rem;
        }}

        /* Status indicators */
        .status-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            display: inline-block;
        }}

        .status-dot.online {{ background: var(--status-online); }}
        .status-dot.offline {{ background: var(--status-offline); }}

        /* Footer */
        .footer {{
            text-align: center;
            padding: 1.5rem;
            color: var(--text-secondary);
            font-size: 0.85rem;
            border-top: 2px solid var(--fla-red);
            margin-top: 2rem;
        }}

        .footer .flamengo {{
            font-size: 1.2rem;
            margin-bottom: 0.5rem;
        }}

        /* Scrollbar */
        ::-webkit-scrollbar {{ width: 8px; }}
        ::-webkit-scrollbar-track {{ background: var(--fla-dark); }}
        ::-webkit-scrollbar-thumb {{ background: var(--fla-light); border-radius: 4px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: var(--fla-red); }}

        /* Live indicator */
        .live-badge {{
            display: inline-flex;
            align-items: center;
            gap: 0.3rem;
            background: rgba(220, 20, 60, 0.3);
            padding: 0.2rem 0.6rem;
            border-radius: 12px;
            font-size: 0.75rem;
        }}

        .live-badge::before {{
            content: '';
            width: 6px;
            height: 6px;
            background: var(--fla-red);
            border-radius: 50%;
            animation: blink 1s infinite;
        }}

        @keyframes blink {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.3; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>
            🦞 {self.config.title}
            <span class="badge">Dashboard v3</span>
            {"<span class='live-badge'>🔴⚫ AO VIVO</span>" if self.config.show_flamengo_badge else ""}
        </h1>
        <div class="ws-status">
            <span class="ws-dot" id="wsDot"></span>
            <span id="wsStatus">Conectando...</span>
        </div>
    </div>

    <div class="container">
        <!-- Summary Cards -->
        <div class="summary">
            <div class="summary-card">
                <h3>📊 APIs Monitoradas</h3>
                <div class="value">{total_apis}</div>
            </div>
            <div class="summary-card">
                <h3>✅ Online</h3>
                <div class="value online">{online_apis}</div>
            </div>
            <div class="summary-card">
                <h3>❌ Offline</h3>
                <div class="value {'offline' if offline_apis > 0 else ''}">{offline_apis}</div>
            </div>
            <div class="summary-card">
                <h3>📈 Uptime Médio</h3>
                <div class="value {'online' if uptime_avg > 99 else 'warning' if uptime_avg > 95 else 'critical'}">{uptime_avg:.1f}%</div>
            </div>
            <div class="summary-card">
                <h3>🚨 Alertas Ativos</h3>
                <div class="value {'critical' if l3_alerts > 0 else 'warning' if l2_alerts > 0 else ''}">{len(active_alerts)}</div>
            </div>
        </div>

        <!-- Main Grid -->
        <div class="grid">
            <!-- Left Column -->
            <div>
                <!-- Response Time Chart -->
                <div class="panel" style="margin-bottom: 1.5rem;">
                    <div class="panel-header">
                        <h2>⏱️ Tempo de Resposta</h2>
                        <span class="live-badge">Tempo Real</span>
                    </div>
                    <div class="panel-body">
                        <div class="chart-container">
                            <canvas id="responseTimeChart"></canvas>
                        </div>
                    </div>
                </div>

                <!-- API Status -->
                <div class="panel">
                    <div class="panel-header">
                        <h2>🔗 Status das APIs</h2>
                        <span id="apiCount">{online_apis}/{total_apis} online</span>
                    </div>
                    <div class="panel-body" id="apiList">
                        {self._render_api_list(apis)}
                    </div>
                </div>
            </div>

            <!-- Right Column -->
            <div>
                <!-- Alert Escalation -->
                <div class="panel" style="margin-bottom: 1.5rem;">
                    <div class="panel-header">
                        <h2>🚨 Alertas em Escalação</h2>
                        <span>L1: {l1_alerts} | L2: {l2_alerts} | L3: {l3_alerts}</span>
                    </div>
                    <div class="panel-body" id="alertList">
                        {self._render_alert_list(alerts[:10])}
                    </div>
                </div>

                <!-- Notifications Feed -->
                <div class="panel">
                    <div class="panel-header">
                        <h2>🔔 Notificações</h2>
                        <span id="notifCount">{len(notifications)} recentes</span>
                    </div>
                    <div class="panel-body" id="notifList">
                        {self._render_notification_list(notifications[:20])}
                    </div>
                </div>
            </div>
        </div>

        <!-- System Metrics -->
        <div class="panel">
            <div class="panel-header">
                <h2>💻 Métricas de Sistema</h2>
                <span class="live-badge">Atualização Contínua</span>
            </div>
            <div class="panel-body">
                <div class="chart-container">
                    <canvas id="systemChart"></canvas>
                </div>
            </div>
        </div>
    </div>

    <div class="footer">
        <div class="flamengo">🔴⚫ Uma vez Flamengo, sempre Flamengo! 🔴⚫</div>
        <div>Mengão Monitor v3.3 - Dashboard com WebSocket | TJF - Tropa Jovem Fla</div>
        <div style="margin-top: 0.5rem; font-size: 0.75rem;">
            Renderizado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 
            WebSocket: {websocket_status.get('connections_active', 0)} clientes conectados
        </div>
    </div>

    <script>
        // WebSocket Connection
        let ws = null;
        let reconnectAttempts = 0;
        const maxReconnectAttempts = 10;
        const wsUrl = '{self.config.websocket_url}';

        // Chart instances
        let responseTimeChart = null;
        let systemChart = null;

        // Data buffers
        const responseTimeData = {{
            labels: [],
            datasets: {{}}
        }};

        const systemData = {{
            labels: [],
            cpu: [],
            memory: [],
            disk: []
        }};

        function connectWebSocket() {{
            const wsDot = document.getElementById('wsDot');
            const wsStatus = document.getElementById('wsStatus');

            wsStatus.textContent = 'Conectando...';
            wsDot.classList.remove('connected');

            try {{
                ws = new WebSocket(wsUrl);

                ws.onopen = () => {{
                    console.log('WebSocket connected');
                    wsDot.classList.add('connected');
                    wsStatus.textContent = 'Conectado';
                    reconnectAttempts = 0;

                    // Subscribe to channels
                    ws.send(JSON.stringify({{
                        type: 'subscribe',
                        channels: ['status', 'metrics', 'alerts', 'notifications']
                    }}));
                }};

                ws.onmessage = (event) => {{
                    const msg = JSON.parse(event.data);
                    handleMessage(msg);
                }};

                ws.onclose = () => {{
                    wsDot.classList.remove('connected');
                    wsStatus.textContent = 'Desconectado';
                    scheduleReconnect();
                }};

                ws.onerror = (error) => {{
                    console.error('WebSocket error:', error);
                    wsStatus.textContent = 'Erro';
                }};
            }} catch (e) {{
                console.error('Failed to connect:', e);
                scheduleReconnect();
            }}
        }}

        function scheduleReconnect() {{
            if (reconnectAttempts < maxReconnectAttempts) {{
                reconnectAttempts++;
                const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
                console.log(`Reconnecting in ${{delay}}ms (attempt ${{reconnectAttempts}})`);
                setTimeout(connectWebSocket, delay);
            }}
        }}

        function handleMessage(msg) {{
            switch (msg.type) {{
                case 'status_update':
                    updateApiStatus(msg.data);
                    break;
                case 'metrics_update':
                    updateSystemMetrics(msg.data);
                    break;
                case 'alert':
                    updateAlerts(msg.data);
                    break;
                case 'notification':
                    updateNotifications(msg.data);
                    break;
                case 'subscribed':
                    console.log('Subscribed to:', msg.data.channels);
                    break;
                case 'pong':
                    // Keep-alive response
                    break;
            }}
        }}

        function updateApiStatus(data) {{
            // Update API list item
            const apiList = document.getElementById('apiList');
            const item = apiList.querySelector(`[data-api="${{data.api}}"]`);
            if (item) {{
                const statusBadge = item.querySelector('.api-status');
                statusBadge.className = `api-status ${{data.status}}`;
                statusBadge.textContent = data.status;
            }}

            // Update chart
            const now = new Date().toLocaleTimeString();
            if (responseTimeData.labels.length >= 60) {{
                responseTimeData.labels.shift();
                Object.values(responseTimeData.datasets).forEach(ds => ds.data.shift());
            }}
            responseTimeData.labels.push(now);

            if (!responseTimeData.datasets[data.api]) {{
                responseTimeData.datasets[data.api] = {{
                    label: data.api,
                    data: [],
                    borderColor: getRandomColor(),
                    tension: 0.4,
                    fill: false
                }};
            }}
            responseTimeData.datasets[data.api].data.push(data.response_time || 0);

            if (responseTimeChart) {{
                responseTimeChart.data.labels = responseTimeData.labels;
                responseTimeChart.data.datasets = Object.values(responseTimeData.datasets);
                responseTimeChart.update('none');
            }}
        }}

        function updateSystemMetrics(data) {{
            const now = new Date().toLocaleTimeString();
            if (systemData.labels.length >= 60) {{
                systemData.labels.shift();
                systemData.cpu.shift();
                systemData.memory.shift();
                systemData.disk.shift();
            }}
            systemData.labels.push(now);
            systemData.cpu.push(data.cpu || 0);
            systemData.memory.push(data.memory || 0);
            systemData.disk.push(data.disk || 0);

            if (systemChart) {{
                systemChart.data.labels = systemData.labels;
                systemChart.data.datasets[0].data = systemData.cpu;
                systemChart.data.datasets[1].data = systemData.memory;
                systemChart.data.datasets[2].data = systemData.disk;
                systemChart.update('none');
            }}
        }}

        function updateAlerts(data) {{
            const alertList = document.getElementById('alertList');
            const alertHtml = `
                <div class="alert-item ${{data.level || 'L1'}}">
                    <div class="alert-header">
                        <span class="alert-level ${{data.level || 'L1'}}">${{data.level || 'L1'}}</span>
                        <span class="alert-time">agora</span>
                    </div>
                    <div class="alert-endpoint">${{data.endpoint || 'Unknown'}}</div>
                    <div class="alert-reason">${{data.reason || data.event || 'Alert'}}</div>
                </div>
            `;
            alertList.insertAdjacentHTML('afterbegin', alertHtml);

            // Limit items
            while (alertList.children.length > 10) {{
                alertList.removeChild(alertList.lastChild);
            }}
        }}

        function updateNotifications(data) {{
            const notifList = document.getElementById('notifList');
            const notifHtml = `
                <div class="notif-item">
                    <div class="notif-time">agora</div>
                    <div class="notif-title">${{data.title || 'Notification'}}</div>
                    <div>${{data.message || ''}}</div>
                </div>
            `;
            notifList.insertAdjacentHTML('afterbegin', notifHtml);

            // Limit items
            while (notifList.children.length > 20) {{
                notifList.removeChild(notifList.lastChild);
            }}
        }}

        function getRandomColor() {{
            const colors = ['#dc143c', '#00ff88', '#ffaa00', '#00aaff', '#ff6600', '#aa00ff'];
            return colors[Math.floor(Math.random() * colors.length)];
        }}

        // Initialize Charts
        function initCharts() {{
            // Response Time Chart
            const rtCtx = document.getElementById('responseTimeChart').getContext('2d');
            responseTimeChart = new Chart(rtCtx, {{
                type: 'line',
                data: {{
                    labels: [],
                    datasets: []
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{
                            labels: {{ color: '#a0a0a0' }}
                        }}
                    }},
                    scales: {{
                        x: {{
                            ticks: {{ color: '#a0a0a0' }},
                            grid: {{ color: 'rgba(255,255,255,0.05)' }}
                        }},
                        y: {{
                            ticks: {{ color: '#a0a0a0' }},
                            grid: {{ color: 'rgba(255,255,255,0.05)' }},
                            title: {{
                                display: true,
                                text: 'ms',
                                color: '#a0a0a0'
                            }}
                        }}
                    }}
                }}
            }});

            // System Metrics Chart
            const sysCtx = document.getElementById('systemChart').getContext('2d');
            systemChart = new Chart(sysCtx, {{
                type: 'line',
                data: {{
                    labels: [],
                    datasets: [
                        {{
                            label: 'CPU %',
                            data: [],
                            borderColor: '#dc143c',
                            tension: 0.4,
                            fill: false
                        }},
                        {{
                            label: 'Memória %',
                            data: [],
                            borderColor: '#00ff88',
                            tension: 0.4,
                            fill: false
                        }},
                        {{
                            label: 'Disco %',
                            data: [],
                            borderColor: '#ffaa00',
                            tension: 0.4,
                            fill: false
                        }}
                    ]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{
                            labels: {{ color: '#a0a0a0' }}
                        }}
                    }},
                    scales: {{
                        x: {{
                            ticks: {{ color: '#a0a0a0' }},
                            grid: {{ color: 'rgba(255,255,255,0.05)' }}
                        }},
                        y: {{
                            ticks: {{ color: '#a0a0a0' }},
                            grid: {{ color: 'rgba(255,255,255,0.05)' }},
                            min: 0,
                            max: 100
                        }}
                    }}
                }}
            }});
        }}

        // Ping keepalive
        setInterval(() => {{
            if (ws && ws.readyState === WebSocket.OPEN) {{
                ws.send(JSON.stringify({{ type: 'ping' }}));
            }}
        }}, 30000);

        // Initialize
        document.addEventListener('DOMContentLoaded', () => {{
            initCharts();
            connectWebSocket();
        }});
    </script>
</body>
</html>"""

        return html

    def _render_api_list(self, apis: List[Dict]) -> str:
        """Renderiza lista de APIs"""
        if not apis:
            return '<div style="text-align:center;color:var(--text-secondary);padding:2rem;">Nenhuma API monitorada</div>'

        items = []
        for api in apis[:20]:
            name = api.get("name", "Unknown")
            status = api.get("status", "unknown")
            response_time = api.get("response_time_ms", 0)
            uptime = api.get("uptime_percent", 0)

            items.append(f"""
                <div class="api-item" data-api="{name}">
                    <div>
                        <div class="api-name">
                            <span class="status-dot {status}"></span>
                            {name}
                        </div>
                        <div class="api-meta">Uptime: {uptime:.1f}% | RT: {response_time:.0f}ms</div>
                    </div>
                    <span class="api-status {status}">{status}</span>
                </div>
            """)

        return "\n".join(items)

    def _render_alert_list(self, alerts: List[Dict]) -> str:
        """Renderiza lista de alertas"""
        if not alerts:
            return '<div style="text-align:center;color:var(--text-secondary);padding:2rem;">Nenhum alerta ativo ✅</div>'

        items = []
        for alert in alerts[:10]:
            level = alert.get("level", "L1")
            endpoint = alert.get("endpoint", alert.get("endpoint_name", "Unknown"))
            reason = alert.get("reason", alert.get("event", "Alert"))
            created = alert.get("created_at", "")
            elapsed = self._time_ago(created) if created else "agora"

            items.append(f"""
                <div class="alert-item {level}">
                    <div class="alert-header">
                        <span class="alert-level {level}">{level}</span>
                        <span class="alert-time">{elapsed}</span>
                    </div>
                    <div class="alert-endpoint">{endpoint}</div>
                    <div class="alert-reason">{reason}</div>
                </div>
            """)

        return "\n".join(items)

    def _render_notification_list(self, notifications: List[Dict]) -> str:
        """Renderiza lista de notificações"""
        if not notifications:
            return '<div style="text-align:center;color:var(--text-secondary);padding:2rem;">Nenhuma notificação recente</div>'

        items = []
        for notif in notifications[:20]:
            title = notif.get("title", "Notification")
            message = notif.get("message", "")
            timestamp = notif.get("timestamp", "")
            elapsed = self._time_ago(timestamp) if timestamp else "agora"

            items.append(f"""
                <div class="notif-item">
                    <div class="notif-time">{elapsed}</div>
                    <div class="notif-title">{title}</div>
                    <div>{message}</div>
                </div>
            """)

        return "\n".join(items)

    def _calc_uptime_avg(self, apis: List[Dict]) -> float:
        """Calcula uptime médio"""
        if not apis:
            return 0.0
        uptimes = [a.get("uptime_percent", 0) for a in apis]
        return sum(uptimes) / len(uptimes) if uptimes else 0.0

    def _time_ago(self, timestamp_str: str) -> str:
        """Converte timestamp para 'há X tempo'"""
        try:
            if isinstance(timestamp_str, str):
                ts = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            else:
                ts = timestamp_str

            now = datetime.now(ts.tzinfo) if ts.tzinfo else datetime.now()
            diff = now - ts

            seconds = int(diff.total_seconds())
            if seconds < 60:
                return f"há {seconds}s"
            elif seconds < 3600:
                return f"há {seconds // 60}min"
            elif seconds < 86400:
                return f"há {seconds // 3600}h"
            else:
                return f"há {seconds // 86400}d"
        except Exception:
            return "agora"


def create_dashboard(config: Optional[DashboardConfig] = None) -> DashboardV3:
    """Factory function para criar dashboard"""
    return DashboardV3(config)
