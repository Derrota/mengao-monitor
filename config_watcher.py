"""
Hot-reload de configuração 🦞
Detecta mudanças no arquivo de config e recarrega automaticamente.
"""

import os
import time
import json
import hashlib
import threading
from pathlib import Path
from typing import Callable, Optional, Dict, Any
from datetime import datetime


class ConfigWatcher:
    """Monitora arquivo de config e recarrega quando detecta mudanças."""
    
    def __init__(self, config_path: str, callback: Callable, check_interval: int = 5):
        """
        Args:
            config_path: Caminho para o arquivo de config
            callback: Função chamada quando config muda (recebe dict da nova config)
            check_interval: Intervalo em segundos para verificar mudanças
        """
        self.config_path = Path(config_path)
        self.callback = callback
        self.check_interval = check_interval
        
        self._last_hash = None
        self._last_mtime = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._reload_count = 0
        self._last_reload: Optional[datetime] = None
        self._error_count = 0
        self._last_error: Optional[str] = None
        
        # Callbacks de ciclo de vida
        self._on_reload_start: Optional[Callable] = None
        self._on_reload_success: Optional[Callable] = None
        self._on_reload_error: Optional[Callable] = None
    
    def on_reload_start(self, callback: Callable):
        """Registra callback para início de reload."""
        self._on_reload_start = callback
    
    def on_reload_success(self, callback: Callable):
        """Registra callback para reload bem-sucedido."""
        self._on_reload_success = callback
    
    def on_reload_error(self, callback: Callable):
        """Registra callback para erro de reload."""
        self._on_reload_error = callback
    
    def _compute_hash(self) -> Optional[str]:
        """Computa hash do arquivo de config."""
        try:
            with open(self.config_path, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()
        except Exception:
            return None
    
    def _get_mtime(self) -> Optional[float]:
        """Obtém timestamp de modificação do arquivo."""
        try:
            return self.config_path.stat().st_mtime
        except Exception:
            return None
    
    def _load_config(self) -> Optional[Dict[str, Any]]:
        """Carrega config do arquivo."""
        try:
            with open(self.config_path, 'r') as f:
                if self.config_path.suffix in ('.yaml', '.yml'):
                    try:
                        import yaml
                        return yaml.safe_load(f)
                    except ImportError:
                        self._last_error = "PyYAML not installed for YAML support"
                        return None
                else:
                    return json.load(f)
        except Exception as e:
            self._last_error = str(e)
            return None
    
    def _check_for_changes(self):
        """Verifica se o arquivo mudou."""
        current_hash = self._compute_hash()
        current_mtime = self._get_mtime()
        
        if current_hash is None:
            return
        
        # Primeira execução - apenas armazena estado
        if self._last_hash is None:
            self._last_hash = current_hash
            self._last_mtime = current_mtime
            return
        
        # Verifica mudança por hash (mais confiável)
        if current_hash != self._last_hash:
            self._handle_change()
            self._last_hash = current_hash
            self._last_mtime = current_mtime
    
    def _handle_change(self):
        """Manipula mudança detectada."""
        if self._on_reload_start:
            try:
                self._on_reload_start(self.config_path)
            except Exception:
                pass
        
        # Carrega nova config
        new_config = self._load_config()
        
        if new_config is None:
            self._error_count += 1
            if self._on_reload_error:
                try:
                    self._on_reload_error(self._last_error)
                except Exception:
                    pass
            return
        
        # Chama callback principal
        try:
            self.callback(new_config)
            self._reload_count += 1
            self._last_reload = datetime.now()
            self._last_error = None
            
            if self._on_reload_success:
                try:
                    self._on_reload_success(new_config)
                except Exception:
                    pass
                    
        except Exception as e:
            self._error_count += 1
            self._last_error = str(e)
            if self._on_reload_error:
                try:
                    self._on_reload_error(str(e))
                except Exception:
                    pass
    
    def _watch_loop(self):
        """Loop principal de monitoramento."""
        while self._running:
            try:
                self._check_for_changes()
            except Exception:
                pass
            time.sleep(self.check_interval)
    
    def start(self):
        """Inicia monitoramento."""
        if self._running:
            return
        
        self._running = True
        
        # Carrega estado inicial
        self._last_hash = self._compute_hash()
        self._last_mtime = self._get_mtime()
        
        # Inicia thread
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Para monitoramento."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=self.check_interval + 1)
            self._thread = None
    
    def get_stats(self) -> dict:
        """Estatísticas do watcher."""
        return {
            'config_path': str(self.config_path),
            'running': self._running,
            'check_interval': self.check_interval,
            'reload_count': self._reload_count,
            'last_reload': self._last_reload.isoformat() if self._last_reload else None,
            'error_count': self._error_count,
            'last_error': self._last_error,
            'file_exists': self.config_path.exists(),
            'file_size': self.config_path.stat().st_size if self.config_path.exists() else 0,
        }
    
    def force_reload(self) -> bool:
        """Força reload imediato."""
        config = self._load_config()
        if config:
            try:
                self.callback(config)
                self._reload_count += 1
                self._last_reload = datetime.now()
                return True
            except Exception as e:
                self._error_count += 1
                self._last_error = str(e)
                return False
        return False


class ConfigDiff:
    """Calcula diferenças entre configs."""
    
    @staticmethod
    def diff(old_config: dict, new_config: dict) -> dict:
        """Calcula diff entre duas configs."""
        changes = {
            'added': [],
            'removed': [],
            'modified': [],
        }
        
        old_keys = set(old_config.keys())
        new_keys = set(new_config.keys())
        
        # Chaves adicionadas
        for key in new_keys - old_keys:
            changes['added'].append({'key': key, 'value': new_config[key]})
        
        # Chaves removidas
        for key in old_keys - new_keys:
            changes['removed'].append({'key': key, 'value': old_config[key]})
        
        # Chaves modificadas
        for key in old_keys & new_keys:
            if old_config[key] != new_config[key]:
                changes['modified'].append({
                    'key': key,
                    'old': old_config[key],
                    'new': new_config[key]
                })
        
        return changes
    
    @staticmethod
    def endpoints_diff(old_endpoints: list, new_endpoints: list) -> dict:
        """Calcula diff específico para lista de endpoints."""
        old_names = {ep.get('name') for ep in old_endpoints}
        new_names = {ep.get('name') for ep in new_endpoints}
        
        old_map = {ep.get('name'): ep for ep in old_endpoints}
        new_map = {ep.get('name'): ep for ep in new_endpoints}
        
        added = [new_map[name] for name in new_names - old_names]
        removed = [old_map[name] for name in old_names - new_names]
        
        modified = []
        for name in old_names & new_names:
            if old_map[name] != new_map[name]:
                modified.append({
                    'name': name,
                    'old': old_map[name],
                    'new': new_map[name]
                })
        
        return {
            'added': added,
            'removed': removed,
            'modified': modified,
            'unchanged': len(old_names & new_names) - len(modified)
        }
