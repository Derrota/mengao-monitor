"""
API REST para gerenciamento dinâmico de endpoints 🦞
Permite adicionar, remover, pausar e retomar endpoints em runtime.
"""

from flask import Flask, jsonify, request
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict
import threading
import time


@dataclass
class EndpointRuntime:
    """Endpoint com estado de runtime."""
    name: str
    url: str
    method: str = "GET"
    timeout: int = 15
    expected_status: int = 200
    interval: int = 60
    enabled: bool = True
    tags: List[str] = field(default_factory=list)
    headers: Dict[str, str] = field(default_factory=dict)
    body: Optional[str] = None
    
    # Runtime state
    paused: bool = False
    added_at: str = ""
    last_check: Optional[str] = None
    last_status: str = "unknown"
    checks_count: int = 0
    errors_count: int = 0
    
    def __post_init__(self):
        if not self.added_at:
            self.added_at = datetime.now().isoformat()
    
    def to_dict(self):
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'EndpointRuntime':
        # Filtra campos que não são do dataclass
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


class EndpointManager:
    """Gerenciador de endpoints em runtime."""
    
    def __init__(self):
        self.endpoints: Dict[str, EndpointRuntime] = {}
        self.lock = threading.Lock()
        self._change_callbacks = []
    
    def on_change(self, callback):
        """Registra callback para mudanças nos endpoints."""
        self._change_callbacks.append(callback)
    
    def _notify_change(self, action: str, name: str):
        """Notifica callbacks sobre mudanças."""
        for cb in self._change_callbacks:
            try:
                cb(action, name)
            except Exception:
                pass
    
    def add_endpoint(self, data: dict) -> tuple[bool, str]:
        """Adiciona novo endpoint."""
        with self.lock:
            name = data.get('name')
            if not name:
                return False, "Missing 'name' field"
            if not data.get('url'):
                return False, "Missing 'url' field"
            
            if name in self.endpoints:
                return False, f"Endpoint '{name}' already exists"
            
            endpoint = EndpointRuntime.from_dict(data)
            self.endpoints[name] = endpoint
            self._notify_change('added', name)
            return True, f"Endpoint '{name}' added successfully"
    
    def remove_endpoint(self, name: str) -> tuple[bool, str]:
        """Remove endpoint."""
        with self.lock:
            if name not in self.endpoints:
                return False, f"Endpoint '{name}' not found"
            
            del self.endpoints[name]
            self._notify_change('removed', name)
            return True, f"Endpoint '{name}' removed successfully"
    
    def update_endpoint(self, name: str, data: dict) -> tuple[bool, str]:
        """Atualiza endpoint existente."""
        with self.lock:
            if name not in self.endpoints:
                return False, f"Endpoint '{name}' not found"
            
            endpoint = self.endpoints[name]
            for key, value in data.items():
                if hasattr(endpoint, key) and key not in ('added_at', 'checks_count', 'errors_count'):
                    setattr(endpoint, key, value)
            
            self._notify_change('updated', name)
            return True, f"Endpoint '{name}' updated successfully"
    
    def pause_endpoint(self, name: str) -> tuple[bool, str]:
        """Pausa monitoramento de um endpoint."""
        with self.lock:
            if name not in self.endpoints:
                return False, f"Endpoint '{name}' not found"
            
            self.endpoints[name].paused = True
            self._notify_change('paused', name)
            return True, f"Endpoint '{name}' paused"
    
    def resume_endpoint(self, name: str) -> tuple[bool, str]:
        """Retoma monitoramento de um endpoint."""
        with self.lock:
            if name not in self.endpoints:
                return False, f"Endpoint '{name}' not found"
            
            self.endpoints[name].paused = False
            self._notify_change('resumed', name)
            return True, f"Endpoint '{name}' resumed"
    
    def get_endpoint(self, name: str) -> Optional[EndpointRuntime]:
        """Obtém endpoint por nome."""
        with self.lock:
            return self.endpoints.get(name)
    
    def get_all_endpoints(self) -> List[dict]:
        """Obtém todos os endpoints."""
        with self.lock:
            return [ep.to_dict() for ep in self.endpoints.values()]
    
    def get_active_endpoints(self) -> List[EndpointRuntime]:
        """Obtém endpoints ativos (não pausados)."""
        with self.lock:
            return [ep for ep in self.endpoints.values() if ep.enabled and not ep.paused]
    
    def update_check_result(self, name: str, status: str, error: Optional[str] = None):
        """Atualiza resultado de check de um endpoint."""
        with self.lock:
            if name in self.endpoints:
                ep = self.endpoints[name]
                ep.last_check = datetime.now().isoformat()
                ep.last_status = status
                ep.checks_count += 1
                if status != 'online':
                    ep.errors_count += 1
    
    def get_stats(self) -> dict:
        """Estatísticas do gerenciador."""
        with self.lock:
            total = len(self.endpoints)
            paused = sum(1 for ep in self.endpoints.values() if ep.paused)
            active = total - paused
            
            statuses = {}
            for ep in self.endpoints.values():
                s = ep.last_status
                statuses[s] = statuses.get(s, 0) + 1
            
            return {
                'total': total,
                'active': active,
                'paused': paused,
                'statuses': statuses,
                'total_checks': sum(ep.checks_count for ep in self.endpoints.values()),
                'total_errors': sum(ep.errors_count for ep in self.endpoints.values()),
            }
    
    def load_from_config(self, endpoints_config: list):
        """Carrega endpoints de configuração inicial."""
        for ep_data in endpoints_config:
            self.add_endpoint(ep_data)


# Flask API
api_app = Flask(__name__)
endpoint_manager = EndpointManager()


@api_app.route('/api/v1/endpoints', methods=['GET'])
def list_endpoints():
    """Lista todos os endpoints."""
    return jsonify({
        'endpoints': endpoint_manager.get_all_endpoints(),
        'stats': endpoint_manager.get_stats()
    })


@api_app.route('/api/v1/endpoints', methods=['POST'])
def add_endpoint():
    """Adiciona novo endpoint."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Missing JSON body'}), 400
    
    success, message = endpoint_manager.add_endpoint(data)
    if success:
        return jsonify({'message': message}), 201
    else:
        return jsonify({'error': message}), 400


@api_app.route('/api/v1/endpoints/<name>', methods=['GET'])
def get_endpoint(name):
    """Obtém endpoint específico."""
    endpoint = endpoint_manager.get_endpoint(name)
    if endpoint:
        return jsonify(endpoint.to_dict())
    else:
        return jsonify({'error': f'Endpoint {name} not found'}), 404


@api_app.route('/api/v1/endpoints/<name>', methods=['PUT'])
def update_endpoint(name):
    """Atualiza endpoint."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Missing JSON body'}), 400
    
    success, message = endpoint_manager.update_endpoint(name, data)
    if success:
        return jsonify({'message': message})
    else:
        return jsonify({'error': message}), 404


@api_app.route('/api/v1/endpoints/<name>', methods=['DELETE'])
def delete_endpoint(name):
    """Remove endpoint."""
    success, message = endpoint_manager.remove_endpoint(name)
    if success:
        return jsonify({'message': message})
    else:
        return jsonify({'error': message}), 404


@api_app.route('/api/v1/endpoints/<name>/pause', methods=['POST'])
def pause_endpoint(name):
    """Pausa endpoint."""
    success, message = endpoint_manager.pause_endpoint(name)
    if success:
        return jsonify({'message': message})
    else:
        return jsonify({'error': message}), 404


@api_app.route('/api/v1/endpoints/<name>/resume', methods=['POST'])
def resume_endpoint(name):
    """Retoma endpoint."""
    success, message = endpoint_manager.resume_endpoint(name)
    if success:
        return jsonify({'message': message})
    else:
        return jsonify({'error': message}), 404


@api_app.route('/api/v1/stats', methods=['GET'])
def get_stats():
    """Estatísticas do gerenciador."""
    return jsonify(endpoint_manager.get_stats())


def start_api_server(port=8081):
    """Inicia servidor API em thread separada."""
    def run():
        api_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread
