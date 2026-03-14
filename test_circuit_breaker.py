"""
Testes para Circuit Breaker Pattern.
"""

import pytest
import time
from unittest.mock import patch, MagicMock

from circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerManager,
    CircuitState,
    get_circuit_manager,
    reset_circuit_manager,
)


class TestCircuitBreakerConfig:
    """Testes para configuração do circuit breaker."""
    
    def test_default_config(self):
        config = CircuitBreakerConfig()
        assert config.failure_threshold == 5
        assert config.recovery_timeout == 60
        assert config.success_threshold == 3
        assert config.monitor_window == 300
        assert config.half_open_max_calls == 1
    
    def test_custom_config(self):
        config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=30,
            success_threshold=2,
        )
        assert config.failure_threshold == 3
        assert config.recovery_timeout == 30
        assert config.success_threshold == 2


class TestCircuitBreaker:
    """Testes para CircuitBreaker."""
    
    def test_initial_state_is_closed(self):
        cb = CircuitBreaker("test")
        assert cb.state == CircuitState.CLOSED
    
    def test_can_execute_when_closed(self):
        cb = CircuitBreaker("test")
        assert cb.can_execute() is True
    
    def test_record_success_increments_stats(self):
        cb = CircuitBreaker("test")
        cb.can_execute()
        cb.record_success()
        assert cb.stats.successful_calls == 1
        assert cb.stats.total_calls == 1
    
    def test_record_failure_increments_stats(self):
        cb = CircuitBreaker("test")
        cb.can_execute()
        cb.record_failure()
        assert cb.stats.failed_calls == 1
    
    def test_opens_after_threshold_failures(self):
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker("test", config)
        
        # 3 falhas consecutivas
        for i in range(3):
            assert cb.can_execute() is True
            cb.record_failure()
        
        assert cb.state == CircuitState.OPEN
    
    def test_rejects_when_open(self):
        config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=60)
        cb = CircuitBreaker("test", config)
        
        # Abre o circuito
        for _ in range(2):
            cb.can_execute()
            cb.record_failure()
        
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False
        assert cb.stats.rejected_calls == 1
    
    def test_transitions_to_half_open_after_timeout(self):
        config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=1)
        cb = CircuitBreaker("test", config)
        
        # Abre o circuito
        for _ in range(2):
            cb.can_execute()
            cb.record_failure()
        
        assert cb.state == CircuitState.OPEN
        
        # Espera timeout
        time.sleep(1.1)
        
        # Deve permitir transição para half-open
        assert cb.can_execute() is True
        assert cb.state == CircuitState.HALF_OPEN
    
    def test_half_open_success_closes_circuit(self):
        config = CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout=0,
            success_threshold=2,
        )
        cb = CircuitBreaker("test", config)
        
        # Abre o circuito
        for _ in range(2):
            cb.can_execute()
            cb.record_failure()
        
        # Vai para half-open
        cb.can_execute()
        assert cb.state == CircuitState.HALF_OPEN
        
        # 2 sucessos consecutivos fecha o circuito
        cb.record_success()
        assert cb.state == CircuitState.HALF_OPEN
        
        cb.can_execute()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
    
    def test_half_open_failure_reopens_circuit(self):
        config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0)
        cb = CircuitBreaker("test", config)
        
        # Abre o circuito
        for _ in range(2):
            cb.can_execute()
            cb.record_failure()
        
        # Vai para half-open
        cb.can_execute()
        assert cb.state == CircuitState.HALF_OPEN
        
        # Falha em half-open volta para open
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
    
    def test_callbacks_on_state_change(self):
        config = CircuitBreakerConfig(failure_threshold=2)
        cb = CircuitBreaker("test", config)
        
        callback = MagicMock()
        cb.set_state_change_callback(callback)
        
        # Abre o circuito
        for _ in range(2):
            cb.can_execute()
            cb.record_failure()
        
        callback.assert_called_once_with("test", CircuitState.CLOSED, CircuitState.OPEN)
    
    def test_callback_on_failure_threshold(self):
        config = CircuitBreakerConfig(failure_threshold=2)
        cb = CircuitBreaker("test", config)
        
        callback = MagicMock()
        cb.set_failure_threshold_callback(callback)
        
        # Abre o circuito
        for _ in range(2):
            cb.can_execute()
            cb.record_failure()
        
        callback.assert_called_once_with("test", 2)
    
    def test_reset_manually(self):
        config = CircuitBreakerConfig(failure_threshold=2)
        cb = CircuitBreaker("test", config)
        
        # Abre o circuito
        for _ in range(2):
            cb.can_execute()
            cb.record_failure()
        
        assert cb.state == CircuitState.OPEN
        
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb._consecutive_failures == 0
    
    def test_get_status(self):
        cb = CircuitBreaker("test")
        cb.can_execute()
        cb.record_success()
        
        status = cb.get_status()
        assert status["name"] == "test"
        assert status["state"] == "closed"
        assert status["stats"]["successful_calls"] == 1
        assert status["stats"]["total_calls"] == 1
    
    def test_failure_rate_calculation(self):
        cb = CircuitBreaker("test")
        
        # 3 sucessos, 2 falhas
        for _ in range(3):
            cb.can_execute()
            cb.record_success()
        for _ in range(2):
            cb.can_execute()
            cb.record_failure()
        
        assert cb.stats.failure_rate == 40.0  # 2/5 * 100
        assert cb.stats.success_rate == 60.0  # 3/5 * 100
    
    def test_consecutive_reset_on_success(self):
        config = CircuitBreakerConfig(failure_threshold=5)
        cb = CircuitBreaker("test", config)
        
        # 2 falhas
        for _ in range(2):
            cb.can_execute()
            cb.record_failure()
        
        assert cb._consecutive_failures == 2
        
        # 1 sucesso reseta contador de falhas
        cb.can_execute()
        cb.record_success()
        assert cb._consecutive_failures == 0


class TestCircuitBreakerManager:
    """Testes para CircuitBreakerManager."""
    
    def test_create_breaker(self):
        manager = CircuitBreakerManager()
        cb = manager.create("API Test")
        assert cb.name == "API Test"
        assert manager.get("API Test") is cb
    
    def test_create_duplicate_returns_existing(self):
        manager = CircuitBreakerManager()
        cb1 = manager.create("API Test")
        cb2 = manager.create("API Test")
        assert cb1 is cb2
    
    def test_get_nonexistent_returns_none(self):
        manager = CircuitBreakerManager()
        assert manager.get("nonexistent") is None
    
    def test_get_or_create(self):
        manager = CircuitBreakerManager()
        
        # Cria
        cb1 = manager.get_or_create("API Test")
        assert cb1 is not None
        
        # Obtém existente
        cb2 = manager.get_or_create("API Test")
        assert cb1 is cb2
    
    def test_remove_breaker(self):
        manager = CircuitBreakerManager()
        manager.create("API Test")
        
        assert manager.remove("API Test") is True
        assert manager.get("API Test") is None
    
    def test_remove_nonexistent(self):
        manager = CircuitBreakerManager()
        assert manager.remove("nonexistent") is False
    
    def test_get_all_status(self):
        manager = CircuitBreakerManager()
        manager.create("API 1")
        manager.create("API 2")
        
        status = manager.get_all_status()
        assert "API 1" in status
        assert "API 2" in status
    
    def test_get_open_circuits(self):
        config = CircuitBreakerConfig(failure_threshold=2)
        manager = CircuitBreakerManager()
        
        cb1 = manager.create("API 1", config)
        cb2 = manager.create("API 2", config)
        
        # Abre apenas API 1
        for _ in range(2):
            cb1.can_execute()
            cb1.record_failure()
        
        open_circuits = manager.get_open_circuits()
        assert "API 1" in open_circuits
        assert "API 2" not in open_circuits
    
    def test_get_stats_summary(self):
        config = CircuitBreakerConfig(failure_threshold=2)
        manager = CircuitBreakerManager()
        
        cb1 = manager.create("API 1", config)
        cb2 = manager.create("API 2", config)
        
        # Abre API 1
        for _ in range(2):
            cb1.can_execute()
            cb1.record_failure()
        
        summary = manager.get_stats_summary()
        assert summary["total_breakers"] == 2
        assert summary["states"]["open"] == 1
        assert summary["states"]["closed"] == 1
        assert "API 1" in summary["open_circuits"]
    
    def test_reset_all(self):
        config = CircuitBreakerConfig(failure_threshold=2)
        manager = CircuitBreakerManager()
        
        cb1 = manager.create("API 1", config)
        cb2 = manager.create("API 2", config)
        
        # Abre ambos
        for cb in [cb1, cb2]:
            for _ in range(2):
                cb.can_execute()
                cb.record_failure()
        
        manager.reset_all()
        
        assert cb1.state == CircuitState.CLOSED
        assert cb2.state == CircuitState.CLOSED
    
    def test_global_callbacks(self):
        manager = CircuitBreakerManager()
        callback = MagicMock()
        
        manager.set_global_state_change_callback(callback)
        
        config = CircuitBreakerConfig(failure_threshold=2)
        cb = manager.create("API Test", config)
        
        # Abre o circuito
        for _ in range(2):
            cb.can_execute()
            cb.record_failure()
        
        callback.assert_called_once()


class TestGlobalManager:
    """Testes para instância global."""
    
    def test_get_circuit_manager_creates_singleton(self):
        reset_circuit_manager()
        manager1 = get_circuit_manager()
        manager2 = get_circuit_manager()
        assert manager1 is manager2
    
    def test_reset_circuit_manager(self):
        reset_circuit_manager()
        manager1 = get_circuit_manager()
        reset_circuit_manager()
        manager2 = get_circuit_manager()
        assert manager1 is not manager2


class TestIntegration:
    """Testes de integração."""
    
    def test_full_workflow(self):
        """Testa workflow completo: closed → open → half-open → closed."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=0,
            success_threshold=2,
        )
        cb = CircuitBreaker("API Test", config)
        
        # CLOSED: requests passam
        assert cb.can_execute() is True
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        
        # 3 falhas → OPEN
        for _ in range(3):
            cb.can_execute()
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        
        # OPEN: requests rejeitados
        assert cb.can_execute() is False
        
        # Após timeout → HALF_OPEN
        cb.can_execute()
        assert cb.state == CircuitState.HALF_OPEN
        
        # 2 sucessos → CLOSED
        cb.record_success()
        cb.can_execute()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
    
    def test_manager_with_multiple_endpoints(self):
        """Testa manager com múltiplos endpoints."""
        config = CircuitBreakerConfig(failure_threshold=2)
        manager = CircuitBreakerManager()
        
        # Cria 3 circuitos
        apis = ["Produção", "Staging", "Dev"]
        for api in apis:
            manager.create(api, config)
        
        # Abre Produção e Staging
        for api in ["Produção", "Staging"]:
            cb = manager.get(api)
            for _ in range(2):
                cb.can_execute()
                cb.record_failure()
        
        # Verifica status
        open_circuits = manager.get_open_circuits()
        assert len(open_circuits) == 2
        assert "Produção" in open_circuits
        assert "Staging" in open_circuits
        assert "Dev" not in open_circuits
        
        # Stats
        summary = manager.get_stats_summary()
        assert summary["states"]["open"] == 2
        assert summary["states"]["closed"] == 1
