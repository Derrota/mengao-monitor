"""
Rate Limiter para Mengão Monitor v1.6 🦞
Previne spam de alertas e protege webhooks.
"""

import time
from datetime import datetime, timedelta
from typing import Dict, Optional
from dataclasses import dataclass, field
from collections import defaultdict
from threading import Lock


@dataclass
class RateLimitConfig:
    """Configuração de rate limiting."""
    max_alerts_per_minute: int = 5
    max_alerts_per_hour: int = 30
    max_alerts_per_day: int = 100
    cooldown_seconds: int = 300  # 5 min entre alertas do mesmo endpoint
    burst_limit: int = 3  # máx de alertas em rajada
    burst_window_seconds: int = 60  # janela de rajada


@dataclass
class AlertCounter:
    """Contador de alertas para um endpoint."""
    minute_count: int = 0
    hour_count: int = 0
    day_count: int = 0
    burst_count: int = 0
    last_alert: Optional[datetime] = None
    last_minute_reset: datetime = field(default_factory=datetime.now)
    last_hour_reset: datetime = field(default_factory=datetime.now)
    last_day_reset: datetime = field(default_factory=datetime.now)
    last_burst_reset: datetime = field(default_factory=datetime.now)


class RateLimiter:
    """
    Rate limiter por endpoint com múltiplas janelas de tempo.
    
    Features:
    - Limite por minuto/hora/dia
    - Burst protection (rajada de alertas)
    - Cooldown entre alertas do mesmo endpoint
    - Thread-safe
    """
    
    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        self.counters: Dict[str, AlertCounter] = defaultdict(AlertCounter)
        self._lock = Lock()
        
        # Stats
        self.stats = {
            'allowed': 0,
            'blocked_minute': 0,
            'blocked_hour': 0,
            'blocked_day': 0,
            'blocked_burst': 0,
            'blocked_cooldown': 0
        }
    
    def _reset_counters_if_needed(self, counter: AlertCounter, now: datetime):
        """Reseta contadores baseado no tempo."""
        # Reset minuto
        if (now - counter.last_minute_reset).total_seconds() >= 60:
            counter.minute_count = 0
            counter.last_minute_reset = now
        
        # Reset hora
        if (now - counter.last_hour_reset).total_seconds() >= 3600:
            counter.hour_count = 0
            counter.last_hour_reset = now
        
        # Reset dia
        if (now - counter.last_day_reset).total_seconds() >= 86400:
            counter.day_count = 0
            counter.last_day_reset = now
        
        # Reset burst window
        if (now - counter.last_burst_reset).total_seconds() >= self.config.burst_window_seconds:
            counter.burst_count = 0
            counter.last_burst_reset = now
    
    def _in_cooldown(self, counter: AlertCounter, now: datetime) -> bool:
        """Verifica se endpoint está em cooldown."""
        if not counter.last_alert:
            return False
        
        elapsed = (now - counter.last_alert).total_seconds()
        return elapsed < self.config.cooldown_seconds
    
    def allow_alert(self, endpoint_name: str) -> bool:
        """
        Verifica se alerta é permitido para o endpoint.
        
        Returns:
            True se alerta pode ser enviado, False se bloqueado
        """
        with self._lock:
            now = datetime.now()
            counter = self.counters[endpoint_name]
            
            # Reset contadores se necessário
            self._reset_counters_if_needed(counter, now)
            
            # Verifica cooldown
            if self._in_cooldown(counter, now):
                self.stats['blocked_cooldown'] += 1
                return False
            
            # Verifica limite por minuto
            if counter.minute_count >= self.config.max_alerts_per_minute:
                self.stats['blocked_minute'] += 1
                return False
            
            # Verifica limite por hora
            if counter.hour_count >= self.config.max_alerts_per_hour:
                self.stats['blocked_hour'] += 1
                return False
            
            # Verifica limite por dia
            if counter.day_count >= self.config.max_alerts_per_day:
                self.stats['blocked_day'] += 1
                return False
            
            # Verifica burst
            if counter.burst_count >= self.config.burst_limit:
                self.stats['blocked_burst'] += 1
                return False
            
            # Permite e incrementa contadores
            counter.minute_count += 1
            counter.hour_count += 1
            counter.day_count += 1
            counter.burst_count += 1
            counter.last_alert = now
            
            self.stats['allowed'] += 1
            return True
    
    def get_remaining(self, endpoint_name: str) -> Dict[str, int]:
        """Retorna quantos alertas restam para o endpoint."""
        with self._lock:
            counter = self.counters.get(endpoint_name)
            if not counter:
                return {
                    'minute': self.config.max_alerts_per_minute,
                    'hour': self.config.max_alerts_per_hour,
                    'day': self.config.max_alerts_per_day,
                    'burst': self.config.burst_limit
                }
            
            now = datetime.now()
            self._reset_counters_if_needed(counter, now)
            
            return {
                'minute': max(0, self.config.max_alerts_per_minute - counter.minute_count),
                'hour': max(0, self.config.max_alerts_per_hour - counter.hour_count),
                'day': max(0, self.config.max_alerts_per_day - counter.day_count),
                'burst': max(0, self.config.burst_limit - counter.burst_count)
            }
    
    def get_stats(self) -> Dict:
        """Retorna estatísticas do rate limiter."""
        return self.stats.copy()
    
    def reset_stats(self):
        """Reseta estatísticas."""
        self.stats = {
            'allowed': 0,
            'blocked_minute': 0,
            'blocked_hour': 0,
            'blocked_day': 0,
            'blocked_burst': 0,
            'blocked_cooldown': 0
        }
    
    def reset_endpoint(self, endpoint_name: str):
        """Reseta contadores de um endpoint específico."""
        with self._lock:
            if endpoint_name in self.counters:
                del self.counters[endpoint_name]
    
    def get_all_endpoints_status(self) -> Dict[str, Dict]:
        """Retorna status de todos os endpoints monitorados."""
        with self._lock:
            now = datetime.now()
            status = {}
            
            for name, counter in self.counters.items():
                self._reset_counters_if_needed(counter, now)
                
                status[name] = {
                    'last_alert': counter.last_alert.isoformat() if counter.last_alert else None,
                    'in_cooldown': self._in_cooldown(counter, now),
                    'remaining': self.get_remaining(name)
                }
            
            return status
