"""
Tests for the Plugin System (v2.5) - using unittest
"""

import os
import json
import tempfile
import shutil
import unittest
from datetime import datetime
from pathlib import Path

from plugins import (
    PluginBase,
    PluginManager,
    HealthCheckPlugin,
    AlertHandlerPlugin,
    ExporterPlugin,
    HookPlugin,
    PluginInfo,
)


# ─── Mock Plugins for Testing ────────────────────────────────────────

class MockHealthCheck(HealthCheckPlugin):
    name = "mock_health"
    version = "1.0.0"
    
    def __init__(self, return_status="ok"):
        super().__init__()
        self.return_status = return_status
        self.check_count = 0
        self.success_count = 0
        self.failure_count = 0
    
    def check(self, api_name: str, url: str, config: dict = None) -> dict:
        self.check_count += 1
        return {
            "status": self.return_status,
            "latency_ms": 42.0,
            "message": f"Mock check for {api_name}",
        }
    
    def on_success(self, api_name: str, result: dict) -> None:
        self.success_count += 1
    
    def on_failure(self, api_name: str, result: dict) -> None:
        self.failure_count += 1


class MockAlertHandler(AlertHandlerPlugin):
    name = "mock_alert"
    version = "1.0.0"
    
    def __init__(self, should_succeed=True):
        super().__init__()
        self.should_succeed = should_succeed
        self.sent_alerts = []
    
    def send_alert(self, alert: dict) -> bool:
        self.sent_alerts.append(alert)
        return self.should_succeed


class MockExporter(ExporterPlugin):
    name = "mock_exporter"
    version = "1.0.0"
    
    def __init__(self, should_succeed=True):
        super().__init__()
        self.should_succeed = should_succeed
        self.exported_metrics = []
    
    def export(self, metrics: dict) -> bool:
        self.exported_metrics.append(metrics)
        return self.should_succeed


class MockHook(HookPlugin):
    name = "mock_hook"
    version = "1.0.0"
    
    def __init__(self):
        super().__init__()
        self.events_received = []
        self.register_hook("test_event", self._on_test)
        self.register_hook("startup", self._on_startup)
    
    def _on_test(self, **kwargs) -> str:
        self.events_received.append(("test_event", kwargs))
        return "test_ok"
    
    def _on_startup(self, **kwargs) -> str:
        self.events_received.append(("startup", kwargs))
        return "startup_ok"


class FailingHealthCheck(HealthCheckPlugin):
    name = "failing_health"
    version = "1.0.0"
    
    def check(self, api_name: str, url: str, config: dict = None) -> dict:
        raise ValueError("Intentional failure")


class DisabledPlugin(HealthCheckPlugin):
    name = "disabled_plugin"
    version = "1.0.0"
    enabled = False
    
    def check(self, api_name: str, url: str, config: dict = None) -> dict:
        return {"status": "ok"}


# ─── Plugin Base Tests ───────────────────────────────────────────────

class TestPluginBase(unittest.TestCase):
    def test_plugin_info(self):
        plugin = MockHealthCheck()
        info = plugin.get_info()
        
        self.assertEqual(info["name"], "mock_health")
        self.assertEqual(info["version"], "1.0.0")
        self.assertTrue(info["enabled"])
        self.assertFalse(info["initialized"])
        self.assertIsNone(info["load_time"])
        self.assertEqual(info["type"], "MockHealthCheck")
    
    def test_plugin_initialize(self):
        plugin = MockHealthCheck()
        self.assertFalse(plugin._initialized)
        
        plugin.initialize({"some": "config"})
        
        self.assertTrue(plugin._initialized)
        self.assertIsNotNone(plugin._load_time)
    
    def test_plugin_shutdown(self):
        plugin = MockHealthCheck()
        plugin.initialize({})
        self.assertTrue(plugin._initialized)
        
        plugin.shutdown()
        
        self.assertFalse(plugin._initialized)
    
    def test_plugin_enabled_default(self):
        plugin = MockHealthCheck()
        self.assertTrue(plugin.enabled)
    
    def test_plugin_disabled(self):
        plugin = DisabledPlugin()
        self.assertFalse(plugin.enabled)


# ─── Health Check Plugin Tests ───────────────────────────────────────

class TestHealthCheckPlugin(unittest.TestCase):
    def test_check_returns_result(self):
        plugin = MockHealthCheck(return_status="ok")
        result = plugin.check("test_api", "http://example.com")
        
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["latency_ms"], 42.0)
        self.assertIn("test_api", result["message"])
    
    def test_on_success_called(self):
        plugin = MockHealthCheck(return_status="ok")
        result = plugin.check("test_api", "http://example.com")
        plugin.on_success("test_api", result)
        
        self.assertEqual(plugin.success_count, 1)
        self.assertEqual(plugin.failure_count, 0)
    
    def test_on_failure_called(self):
        plugin = MockHealthCheck(return_status="error")
        result = plugin.check("test_api", "http://example.com")
        plugin.on_failure("test_api", result)
        
        self.assertEqual(plugin.success_count, 0)
        self.assertEqual(plugin.failure_count, 1)


# ─── Alert Handler Plugin Tests ──────────────────────────────────────

class TestAlertHandlerPlugin(unittest.TestCase):
    def test_send_alert(self):
        handler = MockAlertHandler(should_succeed=True)
        alert = {"api_name": "test", "status": "error", "message": "Test alert"}
        
        result = handler.send_alert(alert)
        
        self.assertTrue(result)
        self.assertEqual(len(handler.sent_alerts), 1)
        self.assertEqual(handler.sent_alerts[0], alert)
    
    def test_send_alert_failure(self):
        handler = MockAlertHandler(should_succeed=False)
        alert = {"api_name": "test", "status": "error"}
        
        result = handler.send_alert(alert)
        
        self.assertFalse(result)
    
    def test_format_alert(self):
        handler = MockAlertHandler()
        alert = {"api_name": "myapi", "status": "error", "message": "Connection failed"}
        
        formatted = handler.format_alert(alert)
        
        self.assertIn("myapi", formatted)
        self.assertIn("error", formatted)
        self.assertIn("Connection failed", formatted)


# ─── Exporter Plugin Tests ───────────────────────────────────────────

class TestExporterPlugin(unittest.TestCase):
    def test_export_metrics(self):
        exporter = MockExporter(should_succeed=True)
        metrics = {"uptime": 99.9, "response_time": 150}
        
        result = exporter.export(metrics)
        
        self.assertTrue(result)
        self.assertEqual(len(exporter.exported_metrics), 1)
    
    def test_export_failure(self):
        exporter = MockExporter(should_succeed=False)
        metrics = {"uptime": 99.9}
        
        result = exporter.export(metrics)
        
        self.assertFalse(result)


# ─── Hook Plugin Tests ───────────────────────────────────────────────

class TestHookPlugin(unittest.TestCase):
    def test_trigger_hook(self):
        hook = MockHook()
        results = hook.trigger("test_event", data="hello")
        
        self.assertEqual(results, ["test_ok"])
        self.assertEqual(len(hook.events_received), 1)
        self.assertEqual(hook.events_received[0][0], "test_event")
        self.assertEqual(hook.events_received[0][1], {"data": "hello"})
    
    def test_trigger_multiple_hooks(self):
        hook = MockHook()
        hook.trigger("test_event")
        hook.trigger("startup")
        
        self.assertEqual(len(hook.events_received), 2)
    
    def test_trigger_nonexistent_hook(self):
        hook = MockHook()
        results = hook.trigger("nonexistent_event")
        
        self.assertEqual(results, [])


# ─── Plugin Manager Tests ────────────────────────────────────────────

class TestPluginManager(unittest.TestCase):
    def test_init(self):
        manager = PluginManager()
        
        self.assertEqual(len(manager._plugins), 0)
        self.assertEqual(len(manager._health_checks), 0)
        self.assertEqual(len(manager._alert_handlers), 0)
        self.assertEqual(len(manager._exporters), 0)
        self.assertEqual(len(manager._hooks), 0)
    
    def test_register_health_check(self):
        manager = PluginManager()
        plugin = MockHealthCheck()
        
        result = manager.register(plugin)
        
        self.assertTrue(result)
        self.assertIn("mock_health", manager._plugins)
        self.assertIn("mock_health", manager._health_checks)
        self.assertTrue(plugin._initialized)
    
    def test_register_alert_handler(self):
        manager = PluginManager()
        plugin = MockAlertHandler()
        
        result = manager.register(plugin)
        
        self.assertTrue(result)
        self.assertIn("mock_alert", manager._alert_handlers)
    
    def test_register_exporter(self):
        manager = PluginManager()
        plugin = MockExporter()
        
        result = manager.register(plugin)
        
        self.assertTrue(result)
        self.assertIn("mock_exporter", manager._exporters)
    
    def test_register_hook(self):
        manager = PluginManager()
        plugin = MockHook()
        
        result = manager.register(plugin)
        
        self.assertTrue(result)
        self.assertIn("mock_hook", manager._hooks)
    
    def test_register_duplicate(self):
        manager = PluginManager()
        plugin1 = MockHealthCheck()
        plugin2 = MockHealthCheck()
        
        manager.register(plugin1)
        result = manager.register(plugin2)  # Should replace
        
        self.assertTrue(result)
        self.assertEqual(len(manager._health_checks), 1)
    
    def test_unregister(self):
        manager = PluginManager()
        plugin = MockHealthCheck()
        manager.register(plugin)
        
        result = manager.unregister("mock_health")
        
        self.assertTrue(result)
        self.assertNotIn("mock_health", manager._plugins)
        self.assertNotIn("mock_health", manager._health_checks)
    
    def test_unregister_nonexistent(self):
        manager = PluginManager()
        
        result = manager.unregister("nonexistent")
        
        self.assertFalse(result)
    
    def test_get_plugin(self):
        manager = PluginManager()
        plugin = MockHealthCheck()
        manager.register(plugin)
        
        retrieved = manager.get_plugin("mock_health")
        
        self.assertIs(retrieved, plugin)
    
    def test_get_plugin_not_found(self):
        manager = PluginManager()
        
        retrieved = manager.get_plugin("nonexistent")
        
        self.assertIsNone(retrieved)
    
    def test_enable_disable_plugin(self):
        manager = PluginManager()
        plugin = MockHealthCheck()
        manager.register(plugin)
        
        self.assertTrue(plugin.enabled)
        
        result = manager.disable_plugin("mock_health")
        self.assertTrue(result)
        self.assertFalse(plugin.enabled)
        
        result = manager.enable_plugin("mock_health")
        self.assertTrue(result)
        self.assertTrue(plugin.enabled)
    
    def test_run_health_checks(self):
        manager = PluginManager()
        plugin = MockHealthCheck(return_status="ok")
        manager.register(plugin)
        
        results = manager.run_health_checks("test_api", "http://example.com")
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "ok")
        self.assertEqual(results[0]["plugin"], "mock_health")
        self.assertEqual(plugin.check_count, 1)
        self.assertEqual(plugin.success_count, 1)
    
    def test_run_health_checks_with_failure(self):
        manager = PluginManager()
        plugin = MockHealthCheck(return_status="error")
        manager.register(plugin)
        
        results = manager.run_health_checks("test_api", "http://example.com")
        
        self.assertEqual(results[0]["status"], "error")
        self.assertEqual(plugin.failure_count, 1)
    
    def test_run_health_checks_disabled_skipped(self):
        manager = PluginManager()
        plugin = DisabledPlugin()
        manager.register(plugin)
        
        results = manager.run_health_checks("test_api", "http://example.com")
        
        self.assertEqual(len(results), 0)
    
    def test_run_health_checks_with_exception(self):
        manager = PluginManager()
        plugin = FailingHealthCheck()
        manager.register(plugin)
        
        results = manager.run_health_checks("test_api", "http://example.com")
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "error")
        self.assertIn("Intentional failure", results[0]["message"])
    
    def test_send_alert(self):
        manager = PluginManager()
        handler = MockAlertHandler(should_succeed=True)
        manager.register(handler)
        
        alert = {"api_name": "test", "status": "error"}
        results = manager.send_alert(alert)
        
        self.assertTrue(results["mock_alert"])
        self.assertEqual(len(handler.sent_alerts), 1)
    
    def test_export_metrics(self):
        manager = PluginManager()
        exporter = MockExporter(should_succeed=True)
        manager.register(exporter)
        
        metrics = {"uptime": 99.9}
        results = manager.export_metrics(metrics)
        
        self.assertTrue(results["mock_exporter"])
        self.assertEqual(len(exporter.exported_metrics), 1)
    
    def test_trigger_hooks(self):
        manager = PluginManager()
        hook = MockHook()
        manager.register(hook)
        
        results = manager.trigger_hooks("test_event", data="hello")
        
        self.assertIn("mock_hook", results)
        self.assertEqual(results["mock_hook"], ["test_ok"])
    
    def test_get_all_plugins(self):
        manager = PluginManager()
        manager.register(MockHealthCheck())
        manager.register(MockAlertHandler())
        
        plugins = manager.get_all_plugins()
        
        self.assertEqual(len(plugins), 2)
        names = [p["name"] for p in plugins]
        self.assertIn("mock_health", names)
        self.assertIn("mock_alert", names)
    
    def test_get_stats(self):
        manager = PluginManager()
        manager.register(MockHealthCheck())
        manager.register(MockAlertHandler())
        manager.register(MockExporter())
        manager.register(MockHook())
        
        stats = manager.get_stats()
        
        self.assertEqual(stats["total_plugins"], 4)
        self.assertEqual(stats["health_checks"], 1)
        self.assertEqual(stats["alert_handlers"], 1)
        self.assertEqual(stats["exporters"], 1)
        self.assertEqual(stats["hooks"], 1)
    
    def test_shutdown_all(self):
        manager = PluginManager()
        plugin1 = MockHealthCheck()
        plugin2 = MockAlertHandler()
        manager.register(plugin1)
        manager.register(plugin2)
        
        manager.shutdown_all()
        
        self.assertEqual(len(manager._plugins), 0)
        self.assertFalse(plugin1._initialized)
        self.assertFalse(plugin2._initialized)
    
    def test_load_plugins_from_dir(self):
        with tempfile.TemporaryDirectory() as tmp_path:
            # Create a plugin file
            plugin_file = Path(tmp_path) / "test_plugin.py"
            plugin_file.write_text('''
from plugins import HealthCheckPlugin

class TestDirPlugin(HealthCheckPlugin):
    name = "test_dir_plugin"
    version = "1.0.0"
    
    def check(self, api_name, url, config=None):
        return {"status": "ok"}
''')
            
            manager = PluginManager()
            loaded = manager.load_plugins_from_dir(tmp_path)
            
            self.assertEqual(loaded, 1)
            self.assertIn("test_dir_plugin", manager._plugins)
    
    def test_load_plugins_skips_underscored_files(self):
        with tempfile.TemporaryDirectory() as tmp_path:
            # Create files starting with _
            (Path(tmp_path) / "__init__.py").write_text("")
            (Path(tmp_path) / "_private.py").write_text("")
            (Path(tmp_path) / "public_plugin.py").write_text('''
from plugins import HealthCheckPlugin

class PublicPlugin(HealthCheckPlugin):
    name = "public_plugin"
    version = "1.0.0"
    
    def check(self, api_name, url, config=None):
        return {"status": "ok"}
''')
            
            manager = PluginManager()
            loaded = manager.load_plugins_from_dir(tmp_path)
            
            self.assertEqual(loaded, 1)
            self.assertIn("public_plugin", manager._plugins)
    
    def test_load_plugins_nonexistent_dir(self):
        manager = PluginManager()
        loaded = manager.load_plugins_from_dir("/nonexistent/path")
        
        self.assertEqual(loaded, 0)
    
    def test_config_passed_to_plugin(self):
        config = {
            "mock_health": {
                "custom_setting": "value",
            }
        }
        manager = PluginManager(config=config)
        
        # MockHealthCheck doesn't use config, but we can verify it's passed
        plugin = MockHealthCheck()
        manager.register(plugin)
        
        self.assertTrue(plugin._initialized)


# ─── Integration Tests ───────────────────────────────────────────────

class TestPluginIntegration(unittest.TestCase):
    def test_full_workflow(self):
        """Test a complete workflow with multiple plugin types."""
        manager = PluginManager()
        
        # Register all types
        health = MockHealthCheck(return_status="ok")
        alert = MockAlertHandler(should_succeed=True)
        exporter = MockExporter(should_succeed=True)
        hook = MockHook()
        
        manager.register(health)
        manager.register(alert)
        manager.register(exporter)
        manager.register(hook)
        
        # Trigger startup hooks
        manager.trigger_hooks("startup")
        
        # Run health checks
        check_results = manager.run_health_checks("api1", "http://example.com")
        self.assertEqual(check_results[0]["status"], "ok")
        
        # Send alert
        alert_results = manager.send_alert({"api_name": "api1", "status": "ok"})
        self.assertTrue(alert_results["mock_alert"])
        
        # Export metrics
        export_results = manager.export_metrics({"uptime": 99.9})
        self.assertTrue(export_results["mock_exporter"])
        
        # Check stats
        stats = manager.get_stats()
        self.assertEqual(stats["total_plugins"], 4)
        
        # Shutdown
        manager.shutdown_all()
        self.assertEqual(len(manager._plugins), 0)
    
    def test_plugin_replacement(self):
        """Test replacing a plugin with same name."""
        manager = PluginManager()
        
        plugin1 = MockHealthCheck(return_status="ok")
        plugin1.version = "1.0.0"
        manager.register(plugin1)
        
        plugin2 = MockHealthCheck(return_status="degraded")
        plugin2.version = "2.0.0"
        manager.register(plugin2)
        
        # Should have replaced
        current = manager.get_plugin("mock_health")
        self.assertEqual(current.version, "2.0.0")
        self.assertEqual(current.return_status, "degraded")


if __name__ == "__main__":
    unittest.main()
