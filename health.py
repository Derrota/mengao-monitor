"""
Health Check + Dashboard v2 para Mengão Monitor 🦞
System metrics, API status, webhook stats, and dashboard with Chart.js.
v2.1: Token-based authentication
"""

from flask import Flask, jsonify, Response, request
import os
from datetime import datetime

from dashboard_v2 import render_dashboard_v2
from system_metrics import SystemMetricsCollector
from auth import auth_manager, require_auth, optional_auth, AuthToken

app = Flask(__name__)
system_collector = SystemMetricsCollector()

# Estado global do monitor (será injetado)
monitor_state = {
    'started_at': None,
    'last_check': None,
    'checks_count': 0,
    'apis_monitored': 0,
    'errors_count': 0,
    'apis': [],
    'webhook_sender': None,  # Referência ao WebhookSender para stats
    'auth_enabled': False  # Autenticação opcional
}


def is_auth_enabled():
    """Verifica se autenticação está habilitada."""
    return monitor_state.get('auth_enabled', False)


@app.route('/')
@optional_auth
def dashboard():
    """Dashboard HTML v2 com gráficos Chart.js."""
    webhook_stats = {}
    if monitor_state.get('webhook_sender'):
        webhook_stats = monitor_state['webhook_sender'].get_stats()
    
    html = render_dashboard_v2(monitor_state, webhook_stats)
    return Response(html, mimetype='text/html')


@app.route('/health')
def health():
    """Endpoint de health check básico (público)."""
    return jsonify({
        'status': 'healthy',
        'service': 'mengao-monitor',
        'version': '2.1.0',
        'timestamp': datetime.now().isoformat(),
        'auth_enabled': is_auth_enabled()
    })


@app.route('/status')
@optional_auth
def status():
    """Status detalhado do monitor."""
    # Collect system metrics
    system_metrics = system_collector.collect()
    system_dict = system_collector.to_dict(system_metrics)
    
    started = monitor_state.get('started_at')
    
    # Webhook stats
    webhook_stats = {}
    if monitor_state.get('webhook_sender'):
        webhook_stats = monitor_state['webhook_sender'].get_stats()
    
    result = {
        'service': 'mengao-monitor',
        'version': '2.1.0',
        'status': 'running',
        'uptime_seconds': (datetime.now() - started).total_seconds() if started else 0,
        'last_check': monitor_state.get('last_check'),
        'checks_count': monitor_state.get('checks_count', 0),
        'apis_monitored': monitor_state.get('apis_monitored', 0),
        'errors_count': monitor_state.get('errors_count', 0),
        'apis': monitor_state.get('apis', []),
        'system': system_dict,
        'webhooks': webhook_stats,
        'pid': os.getpid(),
        'authenticated': getattr(request, 'authenticated', False)
    }
    
    # Adiciona stats de auth se autenticado com scope admin
    if getattr(request, 'authenticated', False):
        token = getattr(request, 'auth_token', None)
        if token and token.has_scope('admin'):
            result['auth_stats'] = auth_manager.get_stats()
    
    return jsonify(result)


@app.route('/metrics')
def metrics():
    """Endpoint de métricas no formato Prometheus (público para coleta)."""
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
    
    # Webhook metrics
    webhook_lines = []
    if monitor_state.get('webhook_sender'):
        ws = monitor_state['webhook_sender']
        stats = ws.get_stats()
        webhook_lines = [
            '',
            '# HELP mengao_monitor_webhooks_sent_total Total de webhooks enviados',
            '# TYPE mengao_monitor_webhooks_sent_total counter',
            f'mengao_monitor_webhooks_sent_total {stats.get("sent", 0)}',
            '',
            '# HELP mengao_monitor_webhooks_failed_total Total de webhooks falharam',
            '# TYPE mengao_monitor_webhooks_failed_total counter',
            f'mengao_monitor_webhooks_failed_total {stats.get("failed", 0)}',
            '',
            '# HELP mengao_monitor_webhooks_retries_total Total de retries de webhooks',
            '# TYPE mengao_monitor_webhooks_retries_total counter',
            f'mengao_monitor_webhooks_retries_total {stats.get("retries", 0)}',
            '',
            '# HELP mengao_monitor_webhooks_rate_limited_total Total de webhooks bloqueados por rate limit',
            '# TYPE mengao_monitor_webhooks_rate_limited_total counter',
            f'mengao_monitor_webhooks_rate_limited_total {stats.get("rate_limited", 0)}',
        ]
    
    # Auth metrics
    auth_lines = []
    if is_auth_enabled():
        auth_stats = auth_manager.get_stats()
        auth_lines = [
            '',
            '# HELP mengao_monitor_auth_active_tokens Tokens de auth ativos',
            '# TYPE mengao_monitor_auth_active_tokens gauge',
            f'mengao_monitor_auth_active_tokens {auth_stats.get("active_tokens", 0)}',
            '',
            '# HELP mengao_monitor_auth_locked_ips IPs bloqueados por tentativas falhas',
            '# TYPE mengao_monitor_auth_locked_ips gauge',
            f'mengao_monitor_auth_locked_ips {auth_stats.get("locked_ips", 0)}',
        ]
    
    # Combine all metrics
    all_lines = api_lines + webhook_lines + auth_lines + [''] + system_lines
    
    return '\n'.join(all_lines), 200, {'Content-Type': 'text/plain'}


@app.route('/webhooks/stats')
@optional_auth
def webhook_stats():
    """Estatísticas detalhadas de webhooks."""
    if not monitor_state.get('webhook_sender'):
        return jsonify({'error': 'Webhook sender not configured'}), 404
    
    ws = monitor_state['webhook_sender']
    return jsonify(ws.get_stats())


@app.route('/apis')
@optional_auth
def apis():
    """Lista de APIs com status."""
    return jsonify({
        'apis': monitor_state.get('apis', []),
        'last_check': monitor_state.get('last_check'),
        'checks_count': monitor_state.get('checks_count', 0)
    })


# ===== AUTH ENDPOINTS =====

@app.route('/auth/tokens', methods=['GET'])
@require_auth(scope='admin')
def list_tokens():
    """Lista todos os tokens (requer admin)."""
    return jsonify({
        'tokens': auth_manager.list_tokens(),
        'stats': auth_manager.get_stats()
    })


@app.route('/auth/tokens', methods=['POST'])
@require_auth(scope='admin')
def create_token():
    """Cria novo token (requer admin)."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Missing JSON body'}), 400
    
    name = data.get('name')
    if not name:
        return jsonify({'error': 'Missing token name'}), 400
    
    scopes = data.get('scopes', ['read'])
    expires_hours = data.get('expires_hours')
    
    token = auth_manager.create_token(
        name=name,
        scopes=scopes,
        expires_hours=expires_hours
    )
    
    return jsonify({
        'message': f'Token created: {name}',
        'token': token.token,  # Única vez que o token completo é retornado
        'warning': 'Save this token securely. It will not be shown again.'
    }), 201


@app.route('/auth/tokens/<token_prefix>', methods=['DELETE'])
@require_auth(scope='admin')
def revoke_token(token_prefix):
    """Revoga um token (requer admin)."""
    # Busca token pelo prefixo
    for token_str in auth_manager.tokens.keys():
        if token_str.startswith(token_prefix) or token_str.endswith(token_prefix):
            auth_manager.revoke_token(token_str)
            return jsonify({'message': f'Token revoked'})
    
    return jsonify({'error': 'Token not found'}), 404


@app.route('/auth/stats', methods=['GET'])
@require_auth(scope='admin')
def auth_stats():
    """Estatísticas de autenticação (requer admin)."""
    return jsonify(auth_manager.get_stats())


def update_state(**kwargs):
    """Atualiza estado global do monitor."""
    monitor_state.update(kwargs)


def set_webhook_sender(sender):
    """Define o webhook sender para coleta de stats."""
    monitor_state['webhook_sender'] = sender


def enable_auth(enabled=True):
    """Habilita/desabilita autenticação."""
    monitor_state['auth_enabled'] = enabled


def create_bootstrap_token():
    """Cria token inicial para setup (usado apenas no primeiro start)."""
    if len(auth_manager.tokens) == 0:
        token = auth_manager.create_token(
            name='bootstrap-admin',
            scopes=['admin'],
            expires_hours=24
        )
        return token
    return None


def start_health_server(port=8080):
    """Inicia servidor de health check em thread separada."""
    import threading
    
    def run():
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread
