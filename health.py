"""
Health Check + Dashboard v2 para Mengão Monitor 🦞
System metrics, API status, webhook stats, and dashboard with Chart.js.
v2.1: Token-based authentication
v2.3: Middleware (CORS, rate limiting, request logging)
v2.4: Circuit Breaker pattern para endpoints
v2.7: Meta-Monitoring (self-diagnostics, watchdog)
v2.8: Config Watcher endpoints (hot-reload management) 🆕
v3.0: WebSocket para updates em tempo real 🆕
"""

from flask import Flask, jsonify, Response, request
import os
from datetime import datetime
from typing import Optional

from dashboard_v2 import render_dashboard_v2
from system_metrics import SystemMetricsCollector
from auth import auth_manager, require_auth, optional_auth, AuthToken
from middleware import setup_middleware
from circuit_breaker import get_circuit_manager, CircuitBreakerConfig
from plugins import PluginManager
from health_checks import HealthCheckManager
from meta_monitor import get_meta_monitor
from config_watcher import ConfigWatcher, ConfigDiff
from websocket_server import (
    get_websocket_server, start_websocket_server, stop_websocket_server,
    broadcast_status_update, broadcast_metrics_update, broadcast_alert,
    broadcast_health_check, broadcast_sla_update
)

app = Flask(__name__)

# Configura middleware (CORS, rate limiting, logging)
MIDDLEWARE_CONFIG = {
    'rate_limit': {
        'requests_per_minute': 60,
        'requests_per_hour': 1000,
        'burst_limit': 10,
        'burst_window': 10
    },
    'cors': {
        'allowed_origins': ['*'],
        'allowed_methods': ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
        'allowed_headers': ['Content-Type', 'Authorization', 'X-Requested-With'],
        'max_age': 86400,
        'allow_credentials': False
    }
}

app = setup_middleware(app, MIDDLEWARE_CONFIG)
system_collector = SystemMetricsCollector()
plugin_manager = PluginManager()  # Plugin System v2.5

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
        'version': '2.8.0',
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
    
    # Circuit Breaker metrics
    cb_lines = []
    cb_manager = get_circuit_manager()
    cb_summary = cb_manager.get_stats_summary()
    cb_lines = [
        '',
        '# HELP mengao_monitor_circuit_breakers_total Total de circuit breakers',
        '# TYPE mengao_monitor_circuit_breakers_total gauge',
        f'mengao_monitor_circuit_breakers_total {cb_summary["total_breakers"]}',
        '',
        '# HELP mengao_monitor_circuit_breakers_open Circuit breakers abertos',
        '# TYPE mengao_monitor_circuit_breakers_open gauge',
        f'mengao_monitor_circuit_breakers_open {cb_summary["states"]["open"]}',
        '',
        '# HELP mengao_monitor_circuit_breakers_half_open Circuit breakers em half-open',
        '# TYPE mengao_monitor_circuit_breakers_half_open gauge',
        f'mengao_monitor_circuit_breakers_half_open {cb_summary["states"]["half_open"]}',
        '',
        '# HELP mengao_monitor_circuit_breakers_closed Circuit breakers fechados',
        '# TYPE mengao_monitor_circuit_breakers_closed gauge',
        f'mengao_monitor_circuit_breakers_closed {cb_summary["states"]["closed"]}',
        '',
        '# HELP mengao_monitor_circuit_breaker_rejected_total Requests rejeitados por circuito aberto',
        '# TYPE mengao_monitor_circuit_breaker_rejected_total counter',
        f'mengao_monitor_circuit_breaker_rejected_total {cb_summary["total_rejected_calls"]}',
    ]
    
    # Per-circuit-breaker metrics
    for cb_name, cb_status in cb_manager.get_all_status().items():
        cb_safe = cb_name.replace(' ', '_').lower()
        state_val = {'closed': 0, 'half_open': 1, 'open': 2}.get(cb_status['state'], 0)
        cb_lines.extend([
            '',
            f'# HELP mengao_circuit_breaker_state Estado do circuit breaker (0=closed, 1=half_open, 2=open)',
            f'# TYPE mengao_circuit_breaker_state gauge',
            f'mengao_circuit_breaker_state{{name="{cb_safe}"}} {state_val}',
            f'mengao_circuit_breaker_failure_rate{{name="{cb_safe}"}} {cb_status["stats"]["failure_rate"]}',
            f'mengao_circuit_breaker_consecutive_failures{{name="{cb_safe}"}} {cb_status["consecutive_failures"]}',
        ])
    
    # Combine all metrics
    all_lines = api_lines + webhook_lines + auth_lines + cb_lines + [''] + system_lines
    
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


# ===== CIRCUIT BREAKER ENDPOINTS =====

@app.route('/circuit-breakers')
@optional_auth
def circuit_breakers_status():
    """Status de todos os circuit breakers."""
    manager = get_circuit_manager()
    return jsonify({
        'circuit_breakers': manager.get_all_status(),
        'summary': manager.get_stats_summary(),
        'timestamp': datetime.now().isoformat()
    })


@app.route('/circuit-breakers/<name>')
@optional_auth
def circuit_breaker_detail(name):
    """Status detalhado de um circuit breaker específico."""
    manager = get_circuit_manager()
    cb = manager.get(name)
    
    if not cb:
        return jsonify({'error': f'Circuit breaker not found: {name}'}), 404
    
    return jsonify(cb.get_status())


@app.route('/circuit-breakers/<name>/reset', methods=['POST'])
@require_auth(scope='write')
def circuit_breaker_reset(name):
    """Reset manual de um circuit breaker específico."""
    manager = get_circuit_manager()
    cb = manager.get(name)
    
    if not cb:
        return jsonify({'error': f'Circuit breaker not found: {name}'}), 404
    
    cb.reset()
    return jsonify({
        'message': f'Circuit breaker reset: {name}',
        'new_state': cb.state.value
    })


@app.route('/circuit-breakers/reset-all', methods=['POST'])
@require_auth(scope='admin')
def circuit_breakers_reset_all():
    """Reset de todos os circuit breakers (requer admin)."""
    manager = get_circuit_manager()
    manager.reset_all()
    return jsonify({
        'message': 'All circuit breakers reset',
        'count': len(manager._breakers)
    })


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


# ===== PLUGIN ENDPOINTS (v2.5) =====

@app.route('/plugins')
@optional_auth
def plugins_list():
    """Lista todos os plugins registrados."""
    return jsonify({
        'plugins': plugin_manager.get_all_plugins(),
        'stats': plugin_manager.get_stats(),
        'timestamp': datetime.now().isoformat()
    })


@app.route('/plugins/<name>')
@optional_auth
def plugin_detail(name):
    """Detalhes de um plugin específico."""
    plugin = plugin_manager.get_plugin(name)
    
    if not plugin:
        return jsonify({'error': f'Plugin not found: {name}'}), 404
    
    return jsonify(plugin.get_info())


@app.route('/plugins/<name>/enable', methods=['POST'])
@require_auth(scope='write')
def plugin_enable(name):
    """Habilita um plugin."""
    if plugin_manager.enable_plugin(name):
        return jsonify({'message': f'Plugin enabled: {name}'})
    return jsonify({'error': f'Plugin not found: {name}'}), 404


@app.route('/plugins/<name>/disable', methods=['POST'])
@require_auth(scope='write')
def plugin_disable(name):
    """Desabilita um plugin."""
    if plugin_manager.disable_plugin(name):
        return jsonify({'message': f'Plugin disabled: {name}'})
    return jsonify({'error': f'Plugin not found: {name}'}), 404


@app.route('/plugins/load', methods=['POST'])
@require_auth(scope='admin')
def plugins_load():
    """Carrega plugins de um diretório (requer admin)."""
    data = request.get_json()
    if not data or 'directory' not in data:
        return jsonify({'error': 'Missing directory path'}), 400
    
    loaded = plugin_manager.load_plugins_from_dir(data['directory'])
    return jsonify({
        'message': f'Loaded {loaded} plugins',
        'loaded': loaded,
        'directory': data['directory']
    })


def get_plugin_manager():
    """Retorna o plugin manager para uso externo."""
    return plugin_manager


# ===== HEALTH CHECKS ENDPOINTS (v2.6) =====

# Health Check Manager global
health_check_manager = HealthCheckManager()


@app.route('/health-checks')
@optional_auth
def health_checks_list():
    """Lista todos os health checks registrados."""
    return jsonify({
        'health_checks': health_check_manager.get_all_stats(),
        'timestamp': datetime.now().isoformat()
    })


@app.route('/health-checks/status')
@optional_auth
def health_checks_status():
    """Status geral de todos os health checks."""
    return jsonify(health_check_manager.get_status())


@app.route('/health-checks/<name>')
@optional_auth
def health_check_detail(name):
    """Detalhes de um health check específico."""
    stats = health_check_manager.get_check_stats(name)
    
    if not stats:
        return jsonify({'error': f'Health check not found: {name}'}), 404
    
    return jsonify(stats)


@app.route('/health-checks/<name>/run', methods=['POST'])
@require_auth(scope='write')
def health_check_run(name):
    """Executa um health check específico."""
    result = health_check_manager.run_check(name)
    
    if not result:
        return jsonify({'error': f'Health check not found: {name}'}), 404
    
    return jsonify(result.to_dict())


@app.route('/health-checks/run-all', methods=['POST'])
@require_auth(scope='write')
def health_checks_run_all():
    """Executa todos os health checks."""
    results = health_check_manager.run_all()
    return jsonify({
        'results': {name: r.to_dict() for name, r in results.items()},
        'timestamp': datetime.now().isoformat()
    })


@app.route('/health-checks/history')
@optional_auth
def health_checks_history():
    """Histórico de execuções de health checks."""
    name = request.args.get('name')
    limit = request.args.get('limit', 100, type=int)
    
    return jsonify({
        'history': health_check_manager.get_history(name=name, limit=limit),
        'count': len(health_check_manager.history)
    })


def get_health_check_manager():
    """Retorna o health check manager para uso externo."""
    return health_check_manager


# ===== META-MONITORING ENDPOINTS (v2.7) =====

meta_monitor = get_meta_monitor()


@app.route('/meta')
@optional_auth
def meta_status():
    """Status geral do meta-monitor (saúde do próprio processo)."""
    return jsonify(meta_monitor.get_overall_status())


@app.route('/meta/checks')
@optional_auth
def meta_checks():
    """Executa todos os health checks do meta-monitor."""
    checks = meta_monitor.run_all_checks()
    return jsonify({
        'checks': {name: check.to_dict() for name, check in checks.items()},
        'timestamp': datetime.now().isoformat()
    })


@app.route('/meta/history')
@optional_auth
def meta_history():
    """Histórico de health checks do meta-monitor."""
    limit = request.args.get('limit', 100, type=int)
    status_filter = request.args.get('status')
    
    return jsonify({
        'history': meta_monitor.get_history(limit=limit, status_filter=status_filter),
        'count': len(meta_monitor.checks_history)
    })


@app.route('/meta/stats')
@optional_auth
def meta_stats():
    """Estatísticas do meta-monitor."""
    return jsonify(meta_monitor.get_stats())


@app.route('/meta/thresholds', methods=['GET'])
@optional_auth
def meta_thresholds_get():
    """Retorna thresholds configurados."""
    return jsonify({
        'thresholds': meta_monitor.thresholds,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/meta/thresholds', methods=['PUT'])
@require_auth(scope='admin')
def meta_thresholds_update():
    """Atualiza thresholds do meta-monitor (requer admin)."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Missing JSON body'}), 400
    
    updated = []
    for key, value in data.items():
        if key in meta_monitor.thresholds:
            meta_monitor.thresholds[key] = value
            updated.append(key)
    
    return jsonify({
        'message': f'Updated {len(updated)} thresholds',
        'updated': updated,
        'thresholds': meta_monitor.thresholds
    })


@app.route('/meta/watchdog/start', methods=['POST'])
@require_auth(scope='admin')
def meta_watchdog_start():
    """Inicia watchdog do meta-monitor (requer admin)."""
    meta_monitor.start_watchdog()
    return jsonify({
        'message': 'Watchdog started',
        'interval': meta_monitor.check_interval
    })


@app.route('/meta/watchdog/stop', methods=['POST'])
@require_auth(scope='admin')
def meta_watchdog_stop():
    """Para watchdog do meta-monitor (requer admin)."""
    meta_monitor.stop_watchdog()
    return jsonify({'message': 'Watchdog stopped'})


def get_meta_monitor_instance():
    """Retorna instância do meta-monitor para uso externo."""
    return meta_monitor


# ===== CONFIG WATCHER ENDPOINTS (v2.8) 🆕

config_watcher_instance: Optional[ConfigWatcher] = None
config_diff_history: list = []
max_diff_history = 100


def get_config_watcher() -> Optional[ConfigWatcher]:
    """Retorna instância do config watcher."""
    return config_watcher_instance


def set_config_watcher(watcher: ConfigWatcher):
    """Define instância global do config watcher."""
    global config_watcher_instance
    config_watcher_instance = watcher


@app.route('/config/watcher')
@optional_auth
def config_watcher_status():
    """Status do config watcher."""
    if not config_watcher_instance:
        return jsonify({'error': 'Config watcher not configured'}), 404
    
    return jsonify({
        'watcher': config_watcher_instance.get_stats(),
        'diff_history_size': len(config_diff_history),
        'timestamp': datetime.now().isoformat()
    })


@app.route('/config/watcher/reload', methods=['POST'])
@require_auth(scope='write')
def config_watcher_force_reload():
    """Força reload imediato da configuração."""
    if not config_watcher_instance:
        return jsonify({'error': 'Config watcher not configured'}), 404
    
    success = config_watcher_instance.force_reload()
    
    if success:
        return jsonify({
            'message': 'Config reloaded successfully',
            'reload_count': config_watcher_instance._reload_count,
            'last_reload': config_watcher_instance._last_reload.isoformat() if config_watcher_instance._last_reload else None
        })
    else:
        return jsonify({
            'error': 'Failed to reload config',
            'last_error': config_watcher_instance._last_error
        }), 500


@app.route('/config/watcher/history')
@optional_auth
def config_watcher_history():
    """Histórico de diffs de configuração."""
    limit = request.args.get('limit', 20, type=int)
    
    return jsonify({
        'history': config_diff_history[-limit:],
        'total': len(config_diff_history)
    })


@app.route('/config/watcher/start', methods=['POST'])
@require_auth(scope='admin')
def config_watcher_start():
    """Inicia o config watcher."""
    if not config_watcher_instance:
        return jsonify({'error': 'Config watcher not configured'}), 404
    
    if config_watcher_instance._running:
        return jsonify({'message': 'Config watcher already running'})
    
    config_watcher_instance.start()
    return jsonify({
        'message': 'Config watcher started',
        'check_interval': config_watcher_instance.check_interval
    })


@app.route('/config/watcher/stop', methods=['POST'])
@require_auth(scope='admin')
def config_watcher_stop():
    """Para o config watcher."""
    if not config_watcher_instance:
        return jsonify({'error': 'Config watcher not configured'}), 404
    
    config_watcher_instance.stop()
    return jsonify({'message': 'Config watcher stopped'})


def record_config_diff(old_config: dict, new_config: dict):
    """Registra diff de configuração no histórico."""
    diff = ConfigDiff.diff(old_config, new_config)
    
    entry = {
        'timestamp': datetime.now().isoformat(),
        'added': diff['added'],
        'removed': diff['removed'],
        'modified': diff['modified']
    }
    
    global config_diff_history
    config_diff_history.append(entry)
    
    # Manter apenas últimos N diffs
    if len(config_diff_history) > max_diff_history:
        config_diff_history = config_diff_history[-max_diff_history:]


# ===== SLA REPORTER ENDPOINTS (v2.9) 🆕

from sla_reporter import SLAReporter

sla_reporter = SLAReporter()


@app.route('/sla/report/<endpoint_name>')
@optional_auth
def sla_report_endpoint(endpoint_name):
    """Gera relatório de SLA para um endpoint específico."""
    period_hours = request.args.get('period', 24, type=int)
    format_type = request.args.get('format', 'json')
    
    report = sla_reporter.generate_report(endpoint_name, period_hours=period_hours)
    
    if format_type == 'html':
        html = sla_reporter.export_html(report)
        return Response(html, mimetype='text/html')
    elif format_type == 'csv':
        csv_data = sla_reporter.export_csv(report)
        return Response(csv_data, mimetype='text/csv')
    else:
        return jsonify(asdict(report))


@app.route('/sla/reports')
@optional_auth
def sla_reports_all():
    """Gera relatório de SLA para todos os endpoints monitorados."""
    period_hours = request.args.get('period', 24, type=int)
    
    # Obter lista de endpoints do monitor
    endpoints = [api.get('name') for api in monitor_state.get('apis', []) if api.get('name')]
    
    if not endpoints:
        return jsonify({'error': 'No endpoints monitored'}), 404
    
    reports = {}
    for name in endpoints:
        reports[name] = asdict(sla_reporter.generate_report(name, period_hours=period_hours))
    
    return jsonify({
        'reports': reports,
        'period_hours': period_hours,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/sla/incidents')
@optional_auth
def sla_incidents():
    """Lista incidentes de SLA."""
    endpoint_name = request.args.get('endpoint')
    open_only = request.args.get('open', 'false').lower() == 'true'
    
    if open_only:
        incidents = sla_reporter.get_open_incidents(endpoint_name)
    else:
        incidents = []
        endpoints = [endpoint_name] if endpoint_name else sla_reporter._incidents.keys()
        for name in endpoints:
            incidents.extend(sla_reporter._incidents.get(name, []))
    
    return jsonify({
        'incidents': [asdict(i) for i in incidents],
        'count': len(incidents)
    })


@app.route('/sla/incidents', methods=['POST'])
@require_auth(scope='write')
def sla_record_incident():
    """Registra um novo incidente de SLA."""
    data = request.get_json()
    if not data or 'endpoint_name' not in data:
        return jsonify({'error': 'Missing endpoint_name'}), 400
    
    incident = sla_reporter.record_incident(
        endpoint_name=data['endpoint_name'],
        reason=data.get('reason', '')
    )
    
    return jsonify({
        'message': 'Incident recorded',
        'incident': asdict(incident)
    }), 201


@app.route('/sla/incidents/<endpoint_name>/resolve', methods=['POST'])
@require_auth(scope='write')
def sla_resolve_incident(endpoint_name):
    """Resolve o último incidente aberto de um endpoint."""
    incident = sla_reporter.resolve_incident(endpoint_name)
    
    if not incident:
        return jsonify({'error': 'No open incidents found'}), 404
    
    return jsonify({
        'message': 'Incident resolved',
        'incident': asdict(incident)
    })


@app.route('/sla/targets', methods=['GET'])
@optional_auth
def sla_targets_get():
    """Retorna targets de SLA configurados."""
    return jsonify({
        'targets': sla_reporter._sla_targets,
        'default': sla_reporter._default_sla_target
    })


@app.route('/sla/targets', methods=['PUT'])
@require_auth(scope='admin')
def sla_targets_update():
    """Atualiza target de SLA para um endpoint."""
    data = request.get_json()
    if not data or 'endpoint_name' not in data or 'target' not in data:
        return jsonify({'error': 'Missing endpoint_name or target'}), 400
    
    sla_reporter.set_sla_target(data['endpoint_name'], data['target'])
    
    return jsonify({
        'message': f'SLA target updated for {data["endpoint_name"]}',
        'target': data['target']
    })


@app.route('/sla/stats')
@optional_auth
def sla_stats():
    """Estatísticas do SLA reporter."""
    return jsonify(sla_reporter.get_stats())


def get_sla_reporter():
    """Retorna instância do SLA reporter para uso externo."""
    return sla_reporter


# ===== WEBSOCKET ENDPOINTS (v3.0) 🆕

@app.route('/websocket/status')
@optional_auth
def websocket_status():
    """Status do servidor WebSocket."""
    server = get_websocket_server()
    return jsonify({
        'websocket': server.get_stats(),
        'timestamp': datetime.now().isoformat()
    })


@app.route('/websocket/start', methods=['POST'])
@require_auth(scope='admin')
def websocket_start():
    """Inicia servidor WebSocket (requer admin)."""
    try:
        data = request.get_json() or {}
        host = data.get('host', 'localhost')
        port = data.get('port', 8082)
        
        server = start_websocket_server(host=host, port=port)
        
        return jsonify({
            'message': f'WebSocket server started on ws://{host}:{port}',
            'host': host,
            'port': port,
            'stats': server.get_stats()
        })
    except ImportError as e:
        return jsonify({
            'error': 'websockets library not installed',
            'install': 'pip install websockets'
        }), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/websocket/stop', methods=['POST'])
@require_auth(scope='admin')
def websocket_stop():
    """Para servidor WebSocket (requer admin)."""
    stop_websocket_server()
    return jsonify({'message': 'WebSocket server stopped'})


@app.route('/websocket/broadcast', methods=['POST'])
@require_auth(scope='write')
def websocket_broadcast():
    """Envia mensagem broadcast para clientes WebSocket."""
    data = request.get_json()
    if not data or 'channel' not in data or 'type' not in data:
        return jsonify({'error': 'Missing channel or type'}), 400
    
    server = get_websocket_server()
    server.broadcast_sync(
        channel=data['channel'],
        message_type=data['type'],
        data=data.get('data', {})
    )
    
    return jsonify({
        'message': f'Broadcast sent to channel: {data["channel"]}',
        'clients_notified': server.get_client_count()
    })


@app.route('/websocket/clients')
@optional_auth
def websocket_clients():
    """Lista clientes WebSocket conectados."""
    server = get_websocket_server()
    stats = server.get_stats()
    
    return jsonify({
        'clients': stats.get('clients', {}),
        'count': server.get_client_count(),
        'subscriptions': stats.get('subscriptions', {})
    })


# ==========================================
# Notification Manager Endpoints (v3.1) 🆕
# ==========================================

@app.route('/notifications')
@optional_auth
def notification_stats():
    """Estatísticas do gerenciador de notificações."""
    from notification_manager import get_notification_manager
    manager = get_notification_manager()
    return jsonify(manager.get_stats())


@app.route('/notifications/history')
@optional_auth
def notification_history():
    """Histórico de notificações com filtros opcionais."""
    from notification_manager import get_notification_manager, NotificationPriority
    manager = get_notification_manager()
    
    limit = request.args.get('limit', 50, type=int)
    priority = request.args.get('priority')
    endpoint = request.args.get('endpoint')
    
    priority_enum = None
    if priority:
        try:
            priority_enum = NotificationPriority(priority)
        except ValueError:
            return jsonify({'error': f'Invalid priority: {priority}'}), 400
    
    history = manager.get_history(limit=limit, priority=priority_enum, endpoint=endpoint)
    return jsonify({'history': history, 'count': len(history)})


@app.route('/notifications/send', methods=['POST'])
@require_auth(scope='write')
def notification_send():
    """Envia notificação manual."""
    from notification_manager import get_notification_manager, NotificationPriority, NotificationChannel
    manager = get_notification_manager()
    
    data = request.get_json()
    if not data or 'title' not in data or 'message' not in data:
        return jsonify({'error': 'Missing title or message'}), 400
    
    priority_str = data.get('priority', 'medium')
    try:
        priority = NotificationPriority(priority_str)
    except ValueError:
        return jsonify({'error': f'Invalid priority: {priority_str}'}), 400
    
    force_channels = None
    if 'channels' in data:
        force_channels = []
        for ch in data['channels']:
            try:
                force_channels.append(NotificationChannel(ch))
            except ValueError:
                return jsonify({'error': f'Invalid channel: {ch}'}), 400
    
    notif_id = manager.notify(
        title=data['title'],
        message=data['message'],
        priority=priority,
        endpoint=data.get('endpoint'),
        data=data.get('data'),
        force_channels=force_channels
    )
    
    return jsonify({
        'notification_id': notif_id,
        'message': 'Notification sent'
    })


@app.route('/notifications/rules', methods=['GET'])
@optional_auth
def notification_rules_list():
    """Lista regras de notificação."""
    from notification_manager import get_notification_manager
    manager = get_notification_manager()
    return jsonify({
        'rules': {
            name: {
                'enabled': rule.enabled,
                'channels': [c.value for c in rule.channels],
                'priority_filter': [p.value for p in rule.priority_filter],
                'endpoint_filter': rule.endpoint_filter,
                'cooldown_seconds': rule.cooldown_seconds,
                'rate_limit_per_hour': rule.rate_limit_per_hour
            }
            for name, rule in manager.rules.items()
        }
    })


@app.route('/notifications/rules', methods=['POST'])
@require_auth(scope='admin')
def notification_rules_add():
    """Adiciona regra de notificação."""
    from notification_manager import get_notification_manager, NotificationRule, NotificationChannel, NotificationPriority
    manager = get_notification_manager()
    
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({'error': 'Missing rule name'}), 400
    
    channels = []
    for ch in data.get('channels', ['websocket']):
        try:
            channels.append(NotificationChannel(ch))
        except ValueError:
            return jsonify({'error': f'Invalid channel: {ch}'}), 400
    
    priority_filter = []
    for p in data.get('priority_filter', []):
        try:
            priority_filter.append(NotificationPriority(p))
        except ValueError:
            return jsonify({'error': f'Invalid priority: {p}'}), 400
    
    rule = NotificationRule(
        name=data['name'],
        enabled=data.get('enabled', True),
        channels=channels,
        priority_filter=priority_filter,
        endpoint_filter=data.get('endpoint_filter', []),
        cooldown_seconds=data.get('cooldown_seconds', 300),
        rate_limit_per_hour=data.get('rate_limit_per_hour', 10)
    )
    
    manager.add_rule(rule)
    return jsonify({'message': f'Rule added: {data["name"]}'})
