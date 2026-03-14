"""
Plugin System for Mengão Monitor v2.5

Allows extending the monitor with custom plugins:
- HealthCheck plugins: custom health check logic
- AlertHandler plugins: custom alert delivery (SMS, PagerDuty, etc.)
- Exporter plugins: export metrics to external systems
- Hook plugins: run code on events (startup, shutdown, alert, etc.)

Usage:
    from plugins import PluginManager, HealthCheckPlugin

    class MyCheck(HealthCheckPlugin):
        name = "my_check"
        
        def check(self, api_name: str, url: str) -> dict:
            # custom logic
            return {"status": "ok", "latency_ms": 42}

    manager = PluginManager()
    manager.register(MyCheck())
    manager.load_plugins_from_dir("./plugins/")

    # In monitor loop:
    results = manager.run_health_checks("api_name", "http://...")
"""

import os
import sys
import json
import importlib
import importlib.util
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("mengao_monitor.plugins")


# ─── Base Plugin Classes ─────────────────────────────────────────────

class PluginBase(ABC):
    """Base class for all plugins."""
    name: str = "unnamed"
    version: str = "1.0.0"
    description: str = ""
    enabled: bool = True
    
    def __init__(self):
        self._initialized = False
        self._load_time: Optional[datetime] = None
    
    def initialize(self, config: dict) -> None:
        """Called when plugin is loaded. Override for setup logic."""
        self._initialized = True
        self._load_time = datetime.now()
    
    def shutdown(self) -> None:
        """Called when plugin is unloaded. Override for cleanup."""
        self._initialized = False
    
    def get_info(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "enabled": self.enabled,
            "initialized": self._initialized,
            "load_time": self._load_time.isoformat() if self._load_time else None,
            "type": self.__class__.__name__,
        }


class HealthCheckPlugin(PluginBase):
    """Plugin for custom health check logic."""
    
    @abstractmethod
    def check(self, api_name: str, url: str, config: dict = None) -> dict:
        """
        Perform a health check.
        
        Returns:
            dict with at least:
            - status: "ok" | "degraded" | "error"
            - latency_ms: float (optional)
            - details: str (optional)
        """
        pass
    
    def on_success(self, api_name: str, result: dict) -> None:
        """Called when check succeeds."""
        pass
    
    def on_failure(self, api_name: str, result: dict) -> None:
        """Called when check fails."""
        pass


class AlertHandlerPlugin(PluginBase):
    """Plugin for custom alert delivery."""
    
    @abstractmethod
    def send_alert(self, alert: dict) -> bool:
        """
        Send an alert.
        
        Args:
            alert: dict with api_name, status, message, timestamp, etc.
        
        Returns:
            True if alert was sent successfully.
        """
        pass
    
    def format_alert(self, alert: dict) -> str:
        """Format alert for display. Override for custom formatting."""
        return (
            f"[{alert.get('api_name', 'unknown')}] "
            f"{alert.get('status', 'unknown')}: "
            f"{alert.get('message', '')}"
        )


class ExporterPlugin(PluginBase):
    """Plugin for exporting metrics to external systems."""
    
    @abstractmethod
    def export(self, metrics: dict) -> bool:
        """
        Export metrics data.
        
        Args:
            metrics: dict with api stats, uptime, response times, etc.
        
        Returns:
            True if export was successful.
        """
        pass


class HookPlugin(PluginBase):
    """Plugin for running code on specific events."""
    
    def __init__(self):
        super().__init__()
        # Events: startup, shutdown, before_check, after_check, alert_sent, config_changed
        self.hooks: Dict[str, List[Callable]] = {}
    
    def register_hook(self, event: str, callback: Callable) -> None:
        """Register a callback for an event."""
        if event not in self.hooks:
            self.hooks[event] = []
        self.hooks[event].append(callback)
    
    def trigger(self, event: str, **kwargs) -> List[Any]:
        """Trigger all callbacks for an event."""
        results = []
        for callback in self.hooks.get(event, []):
            try:
                result = callback(**kwargs)
                results.append(result)
            except Exception as e:
                logger.error(f"Hook {event} callback failed: {e}")
        return results


# ─── Plugin Manager ──────────────────────────────────────────────────

@dataclass
class PluginInfo:
    """Metadata about a registered plugin."""
    plugin: PluginBase
    source: str  # "manual" or file path
    registered_at: datetime = field(default_factory=datetime.now)


class PluginManager:
    """Manages all plugins for Mengão Monitor."""
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self._plugins: Dict[str, PluginInfo] = {}
        self._health_checks: Dict[str, HealthCheckPlugin] = {}
        self._alert_handlers: Dict[str, AlertHandlerPlugin] = {}
        self._exporters: Dict[str, ExporterPlugin] = {}
        self._hooks: Dict[str, HookPlugin] = {}
        
        # Plugin directories to watch
        self._plugin_dirs: List[str] = []
        
        logger.info("PluginManager initialized")
    
    def register(self, plugin: PluginBase, source: str = "manual") -> bool:
        """Register a plugin instance."""
        if plugin.name in self._plugins:
            logger.warning(f"Plugin '{plugin.name}' already registered, replacing")
        
        try:
            # Initialize with config
            plugin_config = self.config.get(plugin.name, {})
            plugin.initialize(plugin_config)
            
            # Store by type
            info = PluginInfo(plugin=plugin, source=source)
            self._plugins[plugin.name] = info
            
            if isinstance(plugin, HealthCheckPlugin):
                self._health_checks[plugin.name] = plugin
            elif isinstance(plugin, AlertHandlerPlugin):
                self._alert_handlers[plugin.name] = plugin
            elif isinstance(plugin, ExporterPlugin):
                self._exporters[plugin.name] = plugin
            elif isinstance(plugin, HookPlugin):
                self._hooks[plugin.name] = plugin
            
            logger.info(f"Plugin '{plugin.name}' v{plugin.version} registered ({source})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register plugin '{plugin.name}': {e}")
            return False
    
    def unregister(self, plugin_name: str) -> bool:
        """Unregister a plugin."""
        if plugin_name not in self._plugins:
            logger.warning(f"Plugin '{plugin_name}' not found")
            return False
        
        try:
            info = self._plugins[plugin_name]
            info.plugin.shutdown()
            
            # Remove from all dicts
            self._plugins.pop(plugin_name, None)
            self._health_checks.pop(plugin_name, None)
            self._alert_handlers.pop(plugin_name, None)
            self._exporters.pop(plugin_name, None)
            self._hooks.pop(plugin_name, None)
            
            logger.info(f"Plugin '{plugin_name}' unregistered")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unregister plugin '{plugin_name}': {e}")
            return False
    
    def load_plugins_from_dir(self, dir_path: str) -> int:
        """
        Load all plugins from a directory.
        
        Looks for Python files with plugin classes (subclasses of PluginBase).
        Each file should define at least one plugin class.
        
        Returns:
            Number of plugins loaded.
        """
        path = Path(dir_path)
        if not path.exists():
            logger.warning(f"Plugin directory not found: {dir_path}")
            return 0
        
        if str(path) not in self._plugin_dirs:
            self._plugin_dirs.append(str(path))
        
        loaded = 0
        for file_path in path.glob("*.py"):
            if file_path.name.startswith("_"):
                continue
            
            try:
                count = self._load_plugin_file(str(file_path))
                loaded += count
            except Exception as e:
                logger.error(f"Failed to load plugins from {file_path}: {e}")
        
        logger.info(f"Loaded {loaded} plugins from {dir_path}")
        return loaded
    
    def _load_plugin_file(self, file_path: str) -> int:
        """Load plugins from a single Python file."""
        module_name = Path(file_path).stem
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if not spec or not spec.loader:
            return 0
        
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        
        loaded = 0
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and 
                issubclass(attr, PluginBase) and 
                attr not in (PluginBase, HealthCheckPlugin, AlertHandlerPlugin, 
                            ExporterPlugin, HookPlugin)):
                try:
                    instance = attr()
                    if self.register(instance, source=file_path):
                        loaded += 1
                except Exception as e:
                    logger.error(f"Failed to instantiate {attr_name}: {e}")
        
        return loaded
    
    def load_plugins_from_config(self, config_path: str) -> int:
        """Load plugins specified in a config file."""
        try:
            with open(config_path) as f:
                if config_path.endswith('.json'):
                    config = json.load(f)
                else:
                    import yaml
                    config = yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config {config_path}: {e}")
            return 0
        
        plugins_config = config.get("plugins", {})
        loaded = 0
        
        # Load from directories
        for dir_path in plugins_config.get("directories", []):
            loaded += self.load_plugins_from_dir(dir_path)
        
        # Load specific modules
        for module_path in plugins_config.get("modules", []):
            try:
                loaded += self._load_plugin_file(module_path)
            except Exception as e:
                logger.error(f"Failed to load module {module_path}: {e}")
        
        return loaded
    
    # ─── Health Checks ───────────────────────────────────────────────
    
    def run_health_checks(self, api_name: str, url: str, config: dict = None) -> List[dict]:
        """Run all registered health check plugins."""
        results = []
        for name, plugin in self._health_checks.items():
            if not plugin.enabled:
                continue
            try:
                result = plugin.check(api_name, url, config)
                result["plugin"] = name
                results.append(result)
                
                if result.get("status") == "ok":
                    plugin.on_success(api_name, result)
                else:
                    plugin.on_failure(api_name, result)
                    
            except Exception as e:
                logger.error(f"Health check plugin '{name}' failed: {e}")
                results.append({
                    "plugin": name,
                    "status": "error",
                    "message": str(e),
                })
        
        return results
    
    # ─── Alerts ──────────────────────────────────────────────────────
    
    def send_alert(self, alert: dict) -> Dict[str, bool]:
        """Send alert through all registered alert handlers."""
        results = {}
        for name, plugin in self._alert_handlers.items():
            if not plugin.enabled:
                continue
            try:
                success = plugin.send_alert(alert)
                results[name] = success
            except Exception as e:
                logger.error(f"Alert handler '{name}' failed: {e}")
                results[name] = False
        
        return results
    
    # ─── Exporters ───────────────────────────────────────────────────
    
    def export_metrics(self, metrics: dict) -> Dict[str, bool]:
        """Export metrics through all registered exporters."""
        results = {}
        for name, plugin in self._exporters.items():
            if not plugin.enabled:
                continue
            try:
                success = plugin.export(metrics)
                results[name] = success
            except Exception as e:
                logger.error(f"Exporter '{name}' failed: {e}")
                results[name] = False
        
        return results
    
    # ─── Hooks ───────────────────────────────────────────────────────
    
    def trigger_hooks(self, event: str, **kwargs) -> Dict[str, List[Any]]:
        """Trigger hooks for an event across all hook plugins."""
        results = {}
        for name, plugin in self._hooks.items():
            if not plugin.enabled:
                continue
            try:
                results[name] = plugin.trigger(event, **kwargs)
            except Exception as e:
                logger.error(f"Hook plugin '{name}' failed on {event}: {e}")
        
        return results
    
    # ─── Management ──────────────────────────────────────────────────
    
    def get_all_plugins(self) -> List[dict]:
        """Get info about all registered plugins."""
        return [info.plugin.get_info() for info in self._plugins.values()]
    
    def get_plugin(self, name: str) -> Optional[PluginBase]:
        """Get a specific plugin by name."""
        info = self._plugins.get(name)
        return info.plugin if info else None
    
    def enable_plugin(self, name: str) -> bool:
        """Enable a plugin."""
        plugin = self.get_plugin(name)
        if plugin:
            plugin.enabled = True
            return True
        return False
    
    def disable_plugin(self, name: str) -> bool:
        """Disable a plugin."""
        plugin = self.get_plugin(name)
        if plugin:
            plugin.enabled = False
            return True
        return False
    
    def shutdown_all(self) -> None:
        """Shutdown all plugins."""
        for name, info in list(self._plugins.items()):
            try:
                info.plugin.shutdown()
                logger.info(f"Plugin '{name}' shut down")
            except Exception as e:
                logger.error(f"Error shutting down plugin '{name}': {e}")
        
        self._plugins.clear()
        self._health_checks.clear()
        self._alert_handlers.clear()
        self._exporters.clear()
        self._hooks.clear()
    
    def get_stats(self) -> dict:
        """Get plugin system statistics."""
        return {
            "total_plugins": len(self._plugins),
            "health_checks": len(self._health_checks),
            "alert_handlers": len(self._alert_handlers),
            "exporters": len(self._exporters),
            "hooks": len(self._hooks),
            "plugin_dirs": self._plugin_dirs,
            "plugins": self.get_all_plugins(),
        }
