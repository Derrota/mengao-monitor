"""
Health Check + Dashboard para Mengão Monitor v1.5 🦞
System metrics, API status, and dashboard.
"""

from flask import Flask, jsonify, Response
import os
from datetime import datetime

from dashboard import render_dashboard
from system_metrics import SystemMetricsCollector

app = Flask(__name__)
system_collector = SystemMetricsCollector()

# Estado global do monitor (será injetado)
monitor_state = {
    'started_at': None,
    'last_check': None,
    'checks_count': 0,
    'apis_monitored': 0,
    'errors_count': 0,
    'apis': []
}


@app.route('/')
def dashboard():
    """Dashboard HTML."""
    html = render_dashboard(monitor_state)
    return Response(html, mimetype='text/html')


@app.route('/health')
def health():
    """Endpoint de health check básico."""
    return jsonify({
        'status': 'healthy',
        'service': 'mengao-monitor',
        'version': '1.5.0',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/status')
def status():
    """Status detalhado do monitor."""
    # Collect system metrics
    system_metrics = system_collector.collect()
    system_dict = system_collector.to_dict(system_metrics)
    
    started = monitor_state.get('started_at')
    
    return jsonify({
        'service': 'mengao-monitor',
        'version': '1.5.0',
        'status': 'running',
        'uptime_seconds': (datetime.now() - started).total_seconds() if started else 0,
        'last_check': monitor_state.get('last_check'),
        'checks_count': monitor_state.get('checks_count', 0),
        'apis_monitored': monitor_state.get('apis_monitored', 0),
        'errors_count': monitor_state.get('errors_count', 0),
        'apis': monitor_state.get('apis', []),
        'system': system_dict,
        'pid': os.getpid()
    })


@app.route('/metrics')
def metrics():
    """Endpoint de métricas no formato Prometheus."""
    # Collect system metrics
    system_metrics = system_collector.collect()
    system_lines = system_collector.to_prometheus(system_metrics).split('\n')
    
    # API metrics
    api_lines = [
        '# HELP mengao_monitor_checks_total Total de verificacoes realizadas',
        '# TYPE mengao_monitor_checks_total counter',
        f'mengao_monitor_checks_total {monitor_state.get("checks_count", 0)}',
        '',
        '# HELP mengao_monitor_errors_total Total de erros encontrados',
        '# TYPE mengao_monitor_errors_total counter',
        f'mengao_monitor_errors_total {monitor_state.get("errors_count", 0)}',
        '',
        '# HELP mengao_monitor_apis_total Numero de APIs monitoradas',
        '# TYPE mengao_monitor_apis_total gauge',
        f'mengao_monitor_apis_total {monitor_state.get("apis_monitored", 0)}',
    ]
    
    # Add per-API metrics
    for api in monitor_state.get('apis', []):
        name = api.get('name', 'unknown').replace(' ', '_').lower()
        status_val = 1 if api.get('status') == 'online' else 0
        api_lines.extend([
            '',
            f'# HELP mengao_monitor_api_status Status da API (1=online, 0=offline)',
            f'# TYPE mengao_monitor_api_status gauge',
            f'mengao_monitor_api_status{{api="{name}"}} {status_val}',
        ])
        
        if api.get('response_time'):
            api_lines.extend([
                f'# HELP mengao_monitor_api_response_time Tempo de resposta em segundos',
                f'# TYPE mengao_monitor_api_response_time gauge',
                f'mengao_monitor_api_response_time{{api="{name}"}} {api["response_time"]}',
            ])
    
    # Combine all metrics
    all_lines = api_lines + [''] + system_lines
    
    return '\n'.join(all_lines), 200, {'Content-Type': 'text/plain'}


@app.route('/apis')
def apis():
    """Lista de APIs com status."""
    return jsonify({
        'apis': monitor_state.get('apis', []),
        'last_check': monitor_state.get('last_check'),
        'checks_count': monitor_state.get('checks_count', 0)
    })


def update_state(**kwargs):
    """Atualiza estado global do monitor."""
    monitor_state.update(kwargs)


def start_health_server(port=8080):
    """Inicia servidor de health check em thread separada."""
    import threading
    
    def run():
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread
