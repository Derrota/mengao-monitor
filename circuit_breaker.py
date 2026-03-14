"""
Circuit Breaker Pattern para Mengão Monitor.

Previne flood de requests para endpoints instáveis.
Implementa os 3 estados: CLOSED, OPEN, HALF_OPEN.

Estados:
- CLOSED: Normal, requests passam
- OPEN: Falhas acima do threshold, requests bloqueados
- HALF_OPEN: Após timeout, permite 1 request de teste
"""

import time
import threading
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Optional, Callable
import logging

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing, blocking requests
    HALF_OPEN = "half_open" # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuração do circuit breaker."""
    failure_threshold: int = 5          # Falhas consecutivas para abrir
    recovery_timeout: int = 60          # Segundos antes de tentar half-open
    success_threshold: int = 3          # Sucessos em half-open para fechar
    monitor_window: int = 300           # Janela de monitoramento (segundos)
    half_open_max_calls: int = 1        # Máx requests simultâneos em half-open


@dataclass
class CircuitStats:
    """Estatísticas do circuit breaker."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0     # Rejeitados por circuito aberto
    timeouts: int = 0
    state_changes: int = 0
    last_failure_time: float = 0
    last_success_time: float = 0
    last_state_change: float = field(default_factory=time.time)
    
    @property
    def failure_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return (self.failed_calls / self.total_calls) * 100
    
    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return (self.successful_calls / self.total_calls) * 100


class CircuitBreaker:
    """
    Circuit Breaker para um endpoint específico.
    
    Uso:
        cb = CircuitBreaker("API Produção", config)
        
        if cb.can_execute():
            try:
                result = make_request()
                cb.record_success()
            except Exception as e:
                cb.record_failure()
        else:
            # Request rejeitado - circuito aberto
            pass
    """
    
    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.stats = CircuitStats()
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._half_open_calls = 0
        self._lock = threading.Lock()
        
        # Callbacks para eventos
        self._on_state_change: Optional[Callable] = None
        self._on_failure_threshold: Optional[Callable] = None
        
        logger.info(f"Circuit breaker initialized: {name} (state: {self.state.value})")
    
    def set_state_change_callback(self, callback: Callable):
        """Define callback para mudanças de estado."""
        self._on_state_change = callback
    
    def set_failure_threshold_callback(self, callback: Callable):
        """Define callback quando threshold de falhas é atingido."""
        self._on_failure_threshold = callback
    
    def can_execute(self) -> bool:
        """
        Verifica se um request pode ser executado.
        
        Returns:
            True se o circuito permite o request
        """
        with self._lock:
            self.stats.total_calls += 1
            
            if self.state == CircuitState.CLOSED:
                return True
            
            elif self.state == CircuitState.OPEN:
                # Verifica se já passou o timeout de recovery
                if self._should_attempt_reset():
                    self._transition_to(CircuitState.HALF_OPEN)
                    return self._can_execute_half_open()
                
                self.stats.rejected_calls += 1
                logger.debug(f"Circuit {self.name}: OPEN - request rejected")
                return False
            
            elif self.state == CircuitState.HALF_OPEN:
                return self._can_execute_half_open()
    
    def _can_execute_half_open(self) -> bool:
        """Verifica se pode executar em estado HALF_OPEN."""
        if self._half_open_calls < self.config.half_open_max_calls:
            self._half_open_calls += 1
            logger.debug(f"Circuit {self.name}: HALF_OPEN - allowing test request")
            return True
        
        self.stats.rejected_calls += 1
        logger.debug(f"Circuit {self.name}: HALF_OPEN - max calls reached")
        return False
    
    def record_success(self):
        """Registra um request bem-sucedido."""
        with self._lock:
            self.stats.successful_calls += 1
            self.stats.last_success_time = time.time()
            self._consecutive_failures = 0
            self._consecutive_successes += 1
            
            if self.state == CircuitState.HALF_OPEN:
                if self._consecutive_successes >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
                    logger.info(f"Circuit {self.name}: HALF_OPEN → CLOSED (recovered)")
            
            logger.debug(f"Circuit {self.name}: success recorded (consecutive: {self._consecutive_successes})")
    
    def record_failure(self, error: Optional[Exception] = None):
        """Registra uma falha."""
        with self._lock:
            self.stats.failed_calls += 1
            self.stats.last_failure_time = time.time()
            self._consecutive_successes = 0
            self._consecutive_failures += 1
            
            logger.debug(f"Circuit {self.name}: failure recorded (consecutive: {self._consecutive_failures})")
            
            if self.state == CircuitState.CLOSED:
                if self._consecutive_failures >= self.config.failure_threshold:
                    if self._on_failure_threshold:
                        self._on_failure_threshold(self.name, self._consecutive_failures)
                    
                    self._transition_to(CircuitState.OPEN)
                    logger.warning(
                        f"Circuit {self.name}: CLOSED → OPEN "
                        f"({self._consecutive_failures} consecutive failures)"
                    )
            
            elif self.state == CircuitState.HALF_OPEN:
                # Falha em half-open volta para open imediatamente
                self._transition_to(CircuitState.OPEN)
                self._half_open_calls = 0
                logger.warning(f"Circuit {self.name}: HALF_OPEN → OPEN (test request failed)")
    
    def _should_attempt_reset(self) -> bool:
        """Verifica se deve tentar resetar (ir para half-open)."""
        time_since_open = time.time() - self.stats.last_state_change
        return time_since_open >= self.config.recovery_timeout
    
    def _transition_to(self, new_state: CircuitState):
        """Transiciona para um novo estado."""
        old_state = self.state
        self.state = new_state
        self.stats.state_changes += 1
        self.stats.last_state_change = time.time()
        
        if new_state == CircuitState.CLOSED:
            self._consecutive_failures = 0
            self._consecutive_successes = 0
            self._half_open_calls = 0
        
        if self._on_state_change:
            self._on_state_change(self.name, old_state, new_state)
    
    def get_status(self) -> Dict:
        """Retorna status atual do circuit breaker."""
        return {
            "name": self.name,
            "state": self.state.value,
            "consecutive_failures": self._consecutive_failures,
            "consecutive_successes": self._consecutive_successes,
            "stats": {
                "total_calls": self.stats.total_calls,
                "successful_calls": self.stats.successful_calls,
                "failed_calls": self.stats.failed_calls,
                "rejected_calls": self.stats.rejected_calls,
                "failure_rate": round(self.stats.failure_rate, 2),
                "success_rate": round(self.stats.success_rate, 2),
                "state_changes": self.stats.state_changes,
            },
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "recovery_timeout": self.config.recovery_timeout,
                "success_threshold": self.config.success_threshold,
            }
        }
    
    def reset(self):
        """Reset manual do circuit breaker para estado CLOSED."""
        with self._lock:
            old_state = self.state
            self.state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._consecutive_successes = 0
            self._half_open_calls = 0
            logger.info(f"Circuit {self.name}: manually reset (was {old_state.value})")


class CircuitBreakerManager:
    """
    Gerenciador de múltiplos circuit breakers.
    
    Uso:
        manager = CircuitBreakerManager()
        manager.create("API Produção", config)
        manager.create("API Staging", config)
        
        # No loop de monitoramento
        for endpoint in endpoints:
            cb = manager.get(endpoint.name)
            if cb and not cb.can_execute():
                continue  # Pula endpoint com circuito aberto
    """
    
    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()
        
        # Callbacks globais
        self._global_state_change: Optional[Callable] = None
        self._global_failure_threshold: Optional[Callable] = None
    
    def create(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        """Cria um novo circuit breaker."""
        with self._lock:
            if name in self._breakers:
                logger.warning(f"Circuit breaker {name} already exists, returning existing")
                return self._breakers[name]
            
            cb = CircuitBreaker(name, config)
            
            # Registra callbacks globais
            if self._global_state_change:
                cb.set_state_change_callback(self._global_state_change)
            if self._global_failure_threshold:
                cb.set_failure_threshold_callback(self._global_failure_threshold)
            
            self._breakers[name] = cb
            logger.info(f"Circuit breaker created: {name}")
            return cb
    
    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Obtém circuit breaker por nome."""
        return self._breakers.get(name)
    
    def get_or_create(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        """Obtém ou cria circuit breaker."""
        cb = self.get(name)
        if cb is None:
            cb = self.create(name, config)
        return cb
    
    def remove(self, name: str) -> bool:
        """Remove circuit breaker."""
        with self._lock:
            if name in self._breakers:
                del self._breakers[name]
                logger.info(f"Circuit breaker removed: {name}")
                return True
            return False
    
    def get_all_status(self) -> Dict:
        """Retorna status de todos os circuit breakers."""
        return {
            name: cb.get_status()
            for name, cb in self._breakers.items()
        }
    
    def get_open_circuits(self) -> list:
        """Retorna lista de circuitos abertos."""
        return [
            name for name, cb in self._breakers.items()
            if cb.state == CircuitState.OPEN
        ]
    
    def get_stats_summary(self) -> Dict:
        """Retorna resumo de estatísticas."""
        total = len(self._breakers)
        open_count = sum(1 for cb in self._breakers.values() if cb.state == CircuitState.OPEN)
        half_open_count = sum(1 for cb in self._breakers.values() if cb.state == CircuitState.HALF_OPEN)
        closed_count = total - open_count - half_open_count
        
        total_rejected = sum(cb.stats.rejected_calls for cb in self._breakers.values())
        total_failures = sum(cb.stats.failed_calls for cb in self._breakers.values())
        
        return {
            "total_breakers": total,
            "states": {
                "closed": closed_count,
                "open": open_count,
                "half_open": half_open_count,
            },
            "total_rejected_calls": total_rejected,
            "total_failed_calls": total_failures,
            "open_circuits": self.get_open_circuits(),
        }
    
    def reset_all(self):
        """Reset manual de todos os circuit breakers."""
        with self._lock:
            for cb in self._breakers.values():
                cb.reset()
            logger.info("All circuit breakers reset")
    
    def set_global_state_change_callback(self, callback: Callable):
        """Define callback global para mudanças de estado."""
        self._global_state_change = callback
        for cb in self._breakers.values():
            cb.set_state_change_callback(callback)
    
    def set_global_failure_threshold_callback(self, callback: Callable):
        """Define callback global para threshold de falhas."""
        self._global_failure_threshold = callback
        for cb in self._breakers.values():
            cb.set_failure_threshold_callback(callback)


# Instância global do manager
_global_manager: Optional[CircuitBreakerManager] = None


def get_circuit_manager() -> CircuitBreakerManager:
    """Obtém instância global do circuit breaker manager."""
    global _global_manager
    if _global_manager is None:
        _global_manager = CircuitBreakerManager()
    return _global_manager


def reset_circuit_manager():
    """Reset da instância global (útil para testes)."""
    global _global_manager
    _global_manager = None
