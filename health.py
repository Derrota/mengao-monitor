"""
Health Check Endpoint para Mengão Monitor 🦞
Permite monitorar o próprio monitor via HTTP.
"""

from flask import Flask, jsonify
import psutil
import os
from datetime import datetime

app = Flask(__name__)

# Estado global do monitor (será injetado)
monitor_state = {
    'started_at': None,
    'last_check': None,
    'checks_count': 0,
    'apis_monitored': 0,
    'errors_count': 0
}


@app.route('/health')
def health():
    """Endpoint de health check básico."""
    return jsonify({
        'status': 'healthy',
        'service': 'mengao-monitor',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/status')
def status():
    """Status detalhado do monitor."""
    process = psutil.Process(os.getpid())
    
    return jsonify({
        'service': 'mengao-monitor',
        'version': '1.1.0',
        'status': 'running',
        'uptime_seconds': (datetime.now() - monitor_state['started_at']).total_seconds() if monitor_state['started_at'] else 0,
        'last_check': monitor_state['last_check'],
        'checks_count': monitor_state['checks_count'],
        'apis_monitored': monitor_state['apis_monitored'],
        'errors_count': monitor_state['errors_count'],
        'memory_mb': round(process.memory_info().rss / 1024 / 1024, 2),
        'cpu_percent': process.cpu_percent(),
        'pid': os.getpid()
    })


@app.route('/metrics')
def metrics():
    """Endpoint de métricas no formato Prometheus."""
    lines = [
        '# HELP mengao_monitor_checks_total Total de verificações realizadas',
        '# TYPE mengao_monitor_checks_total counter',
        f'mengao_monitor_checks_total {monitor_state["checks_count"]}',
        '',
        '# HELP mengao_monitor_errors_total Total de erros encontrados',
        '# TYPE mengao_monitor_errors_total counter',
        f'mengao_monitor_errors_total {monitor_state["errors_count"]}',
        '',
        '# HELP mengao_monitor_apis_total Número de APIs monitoradas',
        '# TYPE mengao_monitor_apis_total gauge',
        f'mengao_monitor_apis_total {monitor_state["apis_monitored"]}',
    ]
    
    return '\n'.join(lines), 200, {'Content-Type': 'text/plain'}


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
