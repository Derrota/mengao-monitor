"""
Testes para API Manager e Config Watcher 🦞
v2.1: API REST + Hot-reload
"""

import pytest
import json
import time
import tempfile
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

# Test API Manager
from api_manager import EndpointManager, EndpointRuntime, endpoint_manager


class TestEndpointRuntime:
    """Testes para EndpointRuntime."""
    
    def test_create_endpoint(self):
        ep = EndpointRuntime(name="test", url="https://example.com")
        assert ep.name == "test"
        assert ep.url == "https://example.com"
        assert ep.method == "GET"
        assert ep.enabled is True
        assert ep.paused is False
        assert ep.checks_count == 0
    
    def test_to_dict(self):
        ep = EndpointRuntime(
            name="test",
            url="https://example.com",
            tags=["prod", "api"]
        )
        d = ep.to_dict()
        assert d['name'] == "test"
        assert d['url'] == "https://example.com"
        assert d['tags'] == ["prod", "api"]
    
    def test_from_dict(self):
        data = {
            'name': 'test',
            'url': 'https://example.com',
            'method': 'POST',
            'timeout': 30,
            'tags': ['api']
        }
        ep = EndpointRuntime.from_dict(data)
        assert ep.name == "test"
        assert ep.method == "POST"
        assert ep.timeout == 30
    
    def test_from_dict_ignores_extra_fields(self):
        data = {
            'name': 'test',
            'url': 'https://example.com',
            'extra_field': 'should be ignored',
            'checks_count': 999  # Should be ignored
        }
        ep = EndpointRuntime.from_dict(data)
        assert ep.name == "test"
        assert ep.checks_count == 0  # Default, not from data


class TestEndpointManager:
    """Testes para EndpointManager."""
    
    def setup_method(self):
        """Setup para cada teste."""
        self.manager = EndpointManager()
    
    def test_add_endpoint(self):
        success, msg = self.manager.add_endpoint({
            'name': 'test',
            'url': 'https://example.com'
        })
        assert success is True
        assert 'test' in self.manager.endpoints
    
    def test_add_endpoint_missing_name(self):
        success, msg = self.manager.add_endpoint({
            'url': 'https://example.com'
        })
        assert success is False
        assert 'name' in msg
    
    def test_add_endpoint_missing_url(self):
        success, msg = self.manager.add_endpoint({
            'name': 'test'
        })
        assert success is False
        assert 'url' in msg
    
    def test_add_duplicate_endpoint(self):
        self.manager.add_endpoint({'name': 'test', 'url': 'https://example.com'})
        success, msg = self.manager.add_endpoint({'name': 'test', 'url': 'https://other.com'})
        assert success is False
        assert 'already exists' in msg
    
    def test_remove_endpoint(self):
        self.manager.add_endpoint({'name': 'test', 'url': 'https://example.com'})
        success, msg = self.manager.remove_endpoint('test')
        assert success is True
        assert 'test' not in self.manager.endpoints
    
    def test_remove_nonexistent(self):
        success, msg = self.manager.remove_endpoint('nonexistent')
        assert success is False
        assert 'not found' in msg
    
    def test_update_endpoint(self):
        self.manager.add_endpoint({'name': 'test', 'url': 'https://example.com'})
        success, msg = self.manager.update_endpoint('test', {'timeout': 30})
        assert success is True
        assert self.manager.endpoints['test'].timeout == 30
    
    def test_pause_resume(self):
        self.manager.add_endpoint({'name': 'test', 'url': 'https://example.com'})
        
        # Pause
        success, _ = self.manager.pause_endpoint('test')
        assert success is True
        assert self.manager.endpoints['test'].paused is True
        
        # Resume
        success, _ = self.manager.resume_endpoint('test')
        assert success is True
        assert self.manager.endpoints['test'].paused is False
    
    def test_get_active_endpoints(self):
        self.manager.add_endpoint({'name': 'ep1', 'url': 'https://example.com'})
        self.manager.add_endpoint({'name': 'ep2', 'url': 'https://example.com'})
        self.manager.pause_endpoint('ep1')
        
        active = self.manager.get_active_endpoints()
        assert len(active) == 1
        assert active[0].name == 'ep2'
    
    def test_update_check_result(self):
        self.manager.add_endpoint({'name': 'test', 'url': 'https://example.com'})
        self.manager.update_check_result('test', 'online')
        
        ep = self.manager.get_endpoint('test')
        assert ep.checks_count == 1
        assert ep.errors_count == 0
        assert ep.last_status == 'online'
        
        self.manager.update_check_result('test', 'offline', 'Connection refused')
        assert ep.checks_count == 2
        assert ep.errors_count == 1
    
    def test_get_stats(self):
        self.manager.add_endpoint({'name': 'ep1', 'url': 'https://example.com'})
        self.manager.add_endpoint({'name': 'ep2', 'url': 'https://example.com'})
        self.manager.pause_endpoint('ep1')
        self.manager.update_check_result('ep2', 'online')
        
        stats = self.manager.get_stats()
        assert stats['total'] == 2
        assert stats['active'] == 1
        assert stats['paused'] == 1
        assert stats['total_checks'] == 1
    
    def test_change_callback(self):
        callback = MagicMock()
        self.manager.on_change(callback)
        
        self.manager.add_endpoint({'name': 'test', 'url': 'https://example.com'})
        callback.assert_called_with('added', 'test')
        
        self.manager.pause_endpoint('test')
        callback.assert_called_with('paused', 'test')
    
    def test_load_from_config(self):
        config = [
            {'name': 'api1', 'url': 'https://api1.com'},
            {'name': 'api2', 'url': 'https://api2.com', 'method': 'POST'}
        ]
        self.manager.load_from_config(config)
        
        assert len(self.manager.endpoints) == 2
        assert self.manager.endpoints['api1'].url == 'https://api1.com'
        assert self.manager.endpoints['api2'].method == 'POST'


# Test Config Watcher
from config_watcher import ConfigWatcher, ConfigDiff


class TestConfigWatcher:
    """Testes para ConfigWatcher."""
    
    def test_init(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'test': True}, f)
            path = f.name
        
        try:
            callback = MagicMock()
            watcher = ConfigWatcher(path, callback, check_interval=1)
            assert watcher.config_path == Path(path)
            assert watcher.check_interval == 1
            assert watcher._reload_count == 0
        finally:
            os.unlink(path)
    
    def test_start_stop(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'test': True}, f)
            path = f.name
        
        try:
            callback = MagicMock()
            watcher = ConfigWatcher(path, callback, check_interval=1)
            watcher.start()
            assert watcher._running is True
            time.sleep(0.1)
            watcher.stop()
            assert watcher._running is False
        finally:
            os.unlink(path)
    
    def test_detect_change(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'version': 1}, f)
            path = f.name
        
        try:
            callback = MagicMock()
            watcher = ConfigWatcher(path, callback, check_interval=0.5)
            watcher.start()
            
            # Wait for initial load
            time.sleep(0.3)
            
            # Modify file
            with open(path, 'w') as f:
                json.dump({'version': 2}, f)
            
            # Wait for detection
            time.sleep(1)
            
            watcher.stop()
            
            # Callback should have been called
            callback.assert_called()
            assert watcher._reload_count >= 1
        finally:
            os.unlink(path)
    
    def test_get_stats(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'test': True}, f)
            path = f.name
        
        try:
            watcher = ConfigWatcher(path, MagicMock(), check_interval=1)
            stats = watcher.get_stats()
            
            assert stats['config_path'] == path
            assert stats['running'] is False
            assert stats['reload_count'] == 0
            assert stats['file_exists'] is True
        finally:
            os.unlink(path)
    
    def test_force_reload(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'version': 1}, f)
            path = f.name
        
        try:
            callback = MagicMock()
            watcher = ConfigWatcher(path, callback, check_interval=1)
            
            result = watcher.force_reload()
            assert result is True
            callback.assert_called_with({'version': 1})
            assert watcher._reload_count == 1
        finally:
            os.unlink(path)


class TestConfigDiff:
    """Testes para ConfigDiff."""
    
    def test_diff_added_removed(self):
        old = {'a': 1, 'b': 2}
        new = {'a': 1, 'c': 3}
        
        diff = ConfigDiff.diff(old, new)
        assert len(diff['added']) == 1
        assert diff['added'][0]['key'] == 'c'
        assert len(diff['removed']) == 1
        assert diff['removed'][0]['key'] == 'b'
    
    def test_diff_modified(self):
        old = {'a': 1}
        new = {'a': 2}
        
        diff = ConfigDiff.diff(old, new)
        assert len(diff['modified']) == 1
        assert diff['modified'][0]['key'] == 'a'
        assert diff['modified'][0]['old'] == 1
        assert diff['modified'][0]['new'] == 2
    
    def test_endpoints_diff(self):
        old = [
            {'name': 'api1', 'url': 'https://api1.com'},
            {'name': 'api2', 'url': 'https://api2.com'}
        ]
        new = [
            {'name': 'api1', 'url': 'https://api1.com'},  # unchanged
            {'name': 'api2', 'url': 'https://api2-new.com'},  # modified
            {'name': 'api3', 'url': 'https://api3.com'}  # added
        ]
        
        diff = ConfigDiff.endpoints_diff(old, new)
        assert len(diff['added']) == 1
        assert diff['added'][0]['name'] == 'api3'
        assert len(diff['modified']) == 1
        assert diff['modified'][0]['name'] == 'api2'
        assert diff['unchanged'] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
