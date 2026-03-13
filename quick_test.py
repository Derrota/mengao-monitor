"""
Teste rápido - apenas classes de dados (sem Flask)
"""

import sys
import os
import tempfile
import json
import time

# Test EndpointRuntime diretamente (sem importar api_manager que tem Flask)
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

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
    paused: bool = False
    added_at: str = ""
    last_check: Optional[str] = None
    last_status: str = "unknown"
    checks_count: int = 0
    errors_count: int = 0
    
    def to_dict(self):
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'EndpointRuntime':
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


def test_endpoint_runtime():
    ep = EndpointRuntime(name="test", url="https://example.com", tags=["prod"])
    assert ep.name == "test"
    assert ep.method == "GET"
    assert ep.paused is False
    
    d = ep.to_dict()
    assert d['name'] == "test"
    assert d['tags'] == ["prod"]
    
    ep2 = EndpointRuntime.from_dict({'name': 'test2', 'url': 'https://example.com', 'method': 'POST'})
    assert ep2.method == "POST"
    
    print("✅ EndpointRuntime: OK")


def test_config_diff():
    sys.path.insert(0, os.path.dirname(__file__))
    from config_watcher import ConfigDiff
    
    old = {'a': 1, 'b': 2}
    new = {'a': 1, 'c': 3}
    diff = ConfigDiff.diff(old, new)
    assert len(diff['added']) == 1
    assert diff['added'][0]['key'] == 'c'
    assert len(diff['removed']) == 1
    assert diff['removed'][0]['key'] == 'b'
    
    # Endpoints diff
    old_eps = [{'name': 'api1', 'url': 'https://api1.com'}]
    new_eps = [{'name': 'api1', 'url': 'https://api1.com'}, {'name': 'api2', 'url': 'https://api2.com'}]
    diff = ConfigDiff.endpoints_diff(old_eps, new_eps)
    assert len(diff['added']) == 1
    assert diff['added'][0]['name'] == 'api2'
    assert diff['unchanged'] == 1
    
    print("✅ ConfigDiff: OK")


def test_config_watcher():
    sys.path.insert(0, os.path.dirname(__file__))
    from config_watcher import ConfigWatcher
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({'version': 1}, f)
        path = f.name
    
    try:
        callback_called = [False]
        def callback(config):
            callback_called[0] = True
        
        watcher = ConfigWatcher(path, callback, check_interval=0.5)
        stats = watcher.get_stats()
        assert stats['file_exists'] is True
        assert stats['running'] is False
        assert stats['reload_count'] == 0
        
        # Force reload
        result = watcher.force_reload()
        assert result is True
        assert callback_called[0] is True
        assert watcher._reload_count == 1
        
        print("✅ ConfigWatcher: OK")
    finally:
        os.unlink(path)


if __name__ == "__main__":
    print("🦞 Mengão Monitor v2.1 - Testes Rápidos\n")
    test_endpoint_runtime()
    test_config_diff()
    test_config_watcher()
    print("\n🦞 Todos os testes passaram! 🔴⚫")
