"""
Testes para ConfigWatcher (v2.8)
"""

import unittest
import json
import time
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from config_watcher import ConfigWatcher, ConfigDiff


class TestConfigWatcher(unittest.TestCase):
    """Testes para ConfigWatcher."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, 'config.json')
        self.callback = MagicMock()
        
        # Config inicial
        self.initial_config = {
            'endpoints': [{'name': 'API 1', 'url': 'http://test.com'}],
            'webhooks': []
        }
        self._write_config(self.initial_config)
    
    def tearDown(self):
        if hasattr(self, 'watcher'):
            self.watcher.stop()
    
    def _write_config(self, config):
        with open(self.config_path, 'w') as f:
            json.dump(config, f)
    
    def test_initialization(self):
        watcher = ConfigWatcher(self.config_path, self.callback, check_interval=1)
        
        self.assertEqual(str(watcher.config_path), self.config_path)
        self.assertEqual(watcher.check_interval, 1)
        self.assertEqual(watcher._reload_count, 0)
        self.assertFalse(watcher._running)
    
    def test_start_stop(self):
        watcher = ConfigWatcher(self.config_path, self.callback, check_interval=1)
        watcher.start()
        
        self.assertTrue(watcher._running)
        self.assertIsNotNone(watcher._thread)
        
        watcher.stop()
        self.assertFalse(watcher._running)
    
    def test_detects_change(self):
        watcher = ConfigWatcher(self.config_path, self.callback, check_interval=0.5)
        watcher.start()
        
        # Aguardar watcher inicializar
        time.sleep(0.3)
        
        # Modificar config
        new_config = {
            'endpoints': [{'name': 'API 2', 'url': 'http://new.com'}],
            'webhooks': []
        }
        self._write_config(new_config)
        
        # Aguardar detecção
        time.sleep(1.0)
        
        # Callback deve ter sido chamado
        self.callback.assert_called_once()
        called_config = self.callback.call_args[0][0]
        self.assertEqual(called_config['endpoints'][0]['name'], 'API 2')
    
    def test_no_change_no_callback(self):
        watcher = ConfigWatcher(self.config_path, self.callback, check_interval=0.3)
        watcher.start()
        
        time.sleep(1.0)
        
        # Callback não deve ser chamado se não houve mudança
        self.callback.assert_not_called()
    
    def test_get_stats(self):
        watcher = ConfigWatcher(self.config_path, self.callback, check_interval=1)
        watcher.start()
        
        stats = watcher.get_stats()
        
        self.assertEqual(stats['config_path'], self.config_path)
        self.assertTrue(stats['running'])
        self.assertEqual(stats['check_interval'], 1)
        self.assertEqual(stats['reload_count'], 0)
        self.assertTrue(stats['file_exists'])
        self.assertGreater(stats['file_size'], 0)
    
    def test_force_reload(self):
        watcher = ConfigWatcher(self.config_path, self.callback, check_interval=1)
        watcher.start()
        
        result = watcher.force_reload()
        
        self.assertTrue(result)
        self.assertEqual(watcher._reload_count, 1)
        self.callback.assert_called_once()
    
    def test_reload_count_increments(self):
        watcher = ConfigWatcher(self.config_path, self.callback, check_interval=0.3)
        watcher.start()
        
        # Force reload 3 vezes
        watcher.force_reload()
        watcher.force_reload()
        watcher.force_reload()
        
        self.assertEqual(watcher._reload_count, 3)
    
    def test_lifecycle_callbacks(self):
        on_start = MagicMock()
        on_success = MagicMock()
        on_error = MagicMock()
        
        watcher = ConfigWatcher(self.config_path, self.callback, check_interval=0.3)
        watcher.on_reload_start(on_start)
        watcher.on_reload_success(on_success)
        watcher.on_reload_error(on_error)
        
        watcher.start()
        time.sleep(0.2)
        
        # Modificar config para trigger _handle_change
        new_config = {'endpoints': [{'name': 'New API'}], 'webhooks': []}
        self._write_config(new_config)
        time.sleep(0.5)
        
        on_start.assert_called()
        on_success.assert_called()
        on_error.assert_not_called()
        
        watcher.stop()
    
    def test_error_handling(self):
        # Callback que falha
        error_callback = MagicMock(side_effect=Exception("Test error"))
        
        watcher = ConfigWatcher(self.config_path, error_callback, check_interval=1)
        
        result = watcher.force_reload()
        
        self.assertFalse(result)
        self.assertEqual(watcher._error_count, 1)
        self.assertEqual(watcher._last_error, "Test error")
    
    def test_missing_file(self):
        missing_path = os.path.join(self.temp_dir, 'missing.json')
        watcher = ConfigWatcher(missing_path, self.callback, check_interval=1)
        
        stats = watcher.get_stats()
        
        self.assertFalse(stats['file_exists'])
        self.assertEqual(stats['file_size'], 0)
    
    def test_invalid_json(self):
        # Escrever JSON inválido
        with open(self.config_path, 'w') as f:
            f.write('{ invalid json }')
        
        watcher = ConfigWatcher(self.config_path, self.callback, check_interval=1)
        
        # force_reload deve falhar com JSON inválido
        result = watcher.force_reload()
        
        self.assertFalse(result)
        # _last_error deve estar setado
        self.assertIsNotNone(watcher._last_error)


class TestConfigDiff(unittest.TestCase):
    """Testes para ConfigDiff."""
    
    def test_added_keys(self):
        old = {'a': 1}
        new = {'a': 1, 'b': 2}
        
        diff = ConfigDiff.diff(old, new)
        
        self.assertEqual(len(diff['added']), 1)
        self.assertEqual(diff['added'][0]['key'], 'b')
        self.assertEqual(diff['removed'], [])
        self.assertEqual(diff['modified'], [])
    
    def test_removed_keys(self):
        old = {'a': 1, 'b': 2}
        new = {'a': 1}
        
        diff = ConfigDiff.diff(old, new)
        
        self.assertEqual(diff['added'], [])
        self.assertEqual(len(diff['removed']), 1)
        self.assertEqual(diff['removed'][0]['key'], 'b')
        self.assertEqual(diff['modified'], [])
    
    def test_modified_keys(self):
        old = {'a': 1}
        new = {'a': 2}
        
        diff = ConfigDiff.diff(old, new)
        
        self.assertEqual(diff['added'], [])
        self.assertEqual(diff['removed'], [])
        self.assertEqual(len(diff['modified']), 1)
        self.assertEqual(diff['modified'][0]['key'], 'a')
        self.assertEqual(diff['modified'][0]['old'], 1)
        self.assertEqual(diff['modified'][0]['new'], 2)
    
    def test_no_changes(self):
        old = {'a': 1, 'b': 2}
        new = {'a': 1, 'b': 2}
        
        diff = ConfigDiff.diff(old, new)
        
        self.assertEqual(diff['added'], [])
        self.assertEqual(diff['removed'], [])
        self.assertEqual(diff['modified'], [])
    
    def test_endpoints_diff_added(self):
        old = [{'name': 'API 1'}]
        new = [{'name': 'API 1'}, {'name': 'API 2'}]
        
        diff = ConfigDiff.endpoints_diff(old, new)
        
        self.assertEqual(len(diff['added']), 1)
        self.assertEqual(diff['added'][0]['name'], 'API 2')
        self.assertEqual(diff['removed'], [])
        self.assertEqual(diff['modified'], [])
        self.assertEqual(diff['unchanged'], 1)
    
    def test_endpoints_diff_removed(self):
        old = [{'name': 'API 1'}, {'name': 'API 2'}]
        new = [{'name': 'API 1'}]
        
        diff = ConfigDiff.endpoints_diff(old, new)
        
        self.assertEqual(diff['added'], [])
        self.assertEqual(len(diff['removed']), 1)
        self.assertEqual(diff['removed'][0]['name'], 'API 2')
    
    def test_endpoints_diff_modified(self):
        old = [{'name': 'API 1', 'url': 'http://old.com'}]
        new = [{'name': 'API 1', 'url': 'http://new.com'}]
        
        diff = ConfigDiff.endpoints_diff(old, new)
        
        self.assertEqual(diff['added'], [])
        self.assertEqual(diff['removed'], [])
        self.assertEqual(len(diff['modified']), 1)
        self.assertEqual(diff['modified'][0]['name'], 'API 1')


if __name__ == '__main__':
    unittest.main()
