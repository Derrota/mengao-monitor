"""
Alert Escalation para Mengão Monitor v3.2 🦞
Sistema de escalação automática de alertas por níveis (L1 → L2 → L3).
"""

import time
import threading
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict


class EscalationLevel(Enum):
    """Níveis de escalação."""
    L1 = "l1"  # Primeiro contato - webhook padrão
    L2 = "l2"  # Escalação - múltiplos canais
    L3 = "l3"  # Crítico - todos os canais + on-call


class EscalationStatus(Enum):
    """Status do alerta em escalação."""
    ACTIVE = "active"
    ESCALATED = "escalated"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    EXPIRED = "expired"


@dataclass
class EscalationPolicy:
    """Política de escalação para um endpoint."""
    name: str
    endpoint: str
    enabled: bool = True
    
    # Timing por nível (segundos)
    l1_timeout: int = 300      # 5 min → L2
    l2_timeout: int = 900      # 15 min → L3
    l3_timeout: int = 1800     # 30 min → expira
    
    # Canais por nível
    l1_channels: List[str] = field(default_factory=lambda: ["websocket"])
    l2_channels: List[str] = field(default_factory=lambda: ["websocket", "discord"])
    l3_channels: List[str] = field(default_factory=lambda: ["websocket", "discord", "telegram"])
    
    # Contato de on-call (para L3)
    on_call_webhook: Optional[str] = None
    on_call_phone: Optional[str] = None
    
    # Regras
    max_escalations_per_hour: int = 5
    quiet_hours_start: Optional[int] = None  # 0-23
    quiet_hours_end: Optional[int] = None    # 0-23
    quiet_hours_escalate_anyway: bool = False  # L3 sempre escala


@dataclass
class EscalationEvent:
    """Evento de escalação."""
    id: str
    alert_id: str
    endpoint: str
    from_level: EscalationLevel
    to_level: EscalationLevel
    timestamp: datetime
    reason: str
    notified_channels: List[str] = field(default_factory=list)


@dataclass
class ActiveAlert:
    """Alerta ativo em processo de escalação."""
    id: str
    endpoint: str
    message: str
    priority: str
    created_at: datetime
    current_level: EscalationLevel = EscalationLevel.L1
    status: EscalationStatus = EscalationStatus.ACTIVE
    
    # Tracking
    last_escalation: Optional[datetime] = None
    escalation_count: int = 0
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    
    # Histórico
    events: List[EscalationEvent] = field(default_factory=list)
    
    @property
    def time_active(self) -> float:
        """Tempo ativo em segundos."""
        end = self.resolved_at or datetime.now()
        return (end - self.created_at).total_seconds()
    
    @property
    def time_in_current_level(self) -> float:
        """Tempo no nível atual em segundos."""
        if self.last_escalation:
            return (datetime.now() - self.last_escalation).total_seconds()
        return self.time_active


class AlertEscalationManager:
    """Gerenciador de escalação de alertas."""
    
    def __init__(self):
        self.policies: Dict[str, EscalationPolicy] = {}
        self.active_alerts: Dict[str, ActiveAlert] = {}
        self.alert_history: List[ActiveAlert] = []
        self.max_history = 500
        
        # Rate limiting por endpoint
        self.escalation_counts: Dict[str, List[datetime]] = defaultdict(list)
        
        # Callbacks
        self.on_escalate: Optional[Callable] = None
        self.on_acknowledge: Optional[Callable] = None
        self.on_resolve: Optional[Callable] = None
        
        # Thread safety
        self._lock = threading.Lock()
        
        # Worker thread
        self._running = False
        self._worker: Optional[threading.Thread] = None
    
    def start(self):
        """Inicia o worker de escalação."""
        if self._running:
            return
        
        self._running = True
        self._worker = threading.Thread(target=self._escalation_worker, daemon=True)
        self._worker.start()
    
    def stop(self):
        """Para o worker de escalação."""
        self._running = False
        if self._worker:
            self._worker.join(timeout=5)
    
    def add_policy(self, policy: EscalationPolicy):
        """Adiciona uma política de escalação."""
        with self._lock:
            self.policies[policy.endpoint] = policy
    
    def remove_policy(self, endpoint: str):
        """Remove uma política de escalação."""
        with self._lock:
            self.policies.pop(endpoint, None)
    
    def get_policy(self, endpoint: str) -> Optional[EscalationPolicy]:
        """Obtém política para um endpoint."""
        return self.policies.get(endpoint)
    
    def create_alert(self, endpoint: str, message: str, priority: str = "high") -> Optional[ActiveAlert]:
        """
        Cria um novo alerta com escalação automática.
        
        Returns:
            ActiveAlert se criado, None se política não existe ou rate limited
        """
        with self._lock:
            policy = self.policies.get(endpoint)
            if not policy or not policy.enabled:
                return None
            
            # Check rate limit
            if not self._check_rate_limit(endpoint, policy):
                return None
            
            # Check quiet hours
            if self._is_quiet_hours(policy):
                if not policy.quiet_hours_escalate_anyway:
                    return None
            
            alert_id = str(uuid.uuid4())[:8]
            alert = ActiveAlert(
                id=alert_id,
                endpoint=endpoint,
                message=message,
                priority=priority,
                created_at=datetime.now()
            )
            
            # Evento inicial
            event = EscalationEvent(
                id=str(uuid.uuid4())[:8],
                alert_id=alert_id,
                endpoint=endpoint,
                from_level=EscalationLevel.L1,
                to_level=EscalationLevel.L1,
                timestamp=datetime.now(),
                reason="Alert created",
                notified_channels=policy.l1_channels
            )
            alert.events.append(event)
            
            self.active_alerts[alert_id] = alert
            
            # Notificar L1
            if self.on_escalate:
                self.on_escalate(alert, EscalationLevel.L1, policy.l1_channels)
            
            return alert
    
    def acknowledge_alert(self, alert_id: str, acknowledged_by: str = "system") -> bool:
        """
        Reconhece um alerta (para escalação).
        
        Returns:
            True se reconhecido com sucesso
        """
        with self._lock:
            alert = self.active_alerts.get(alert_id)
            if not alert or alert.status not in (EscalationStatus.ACTIVE, EscalationStatus.ESCALATED):
                return False
            
            alert.status = EscalationStatus.ACKNOWLEDGED
            alert.acknowledged_at = datetime.now()
            alert.acknowledged_by = acknowledged_by
            
            if self.on_acknowledge:
                self.on_acknowledge(alert)
            
            return True
    
    def resolve_alert(self, alert_id: str, reason: str = "Resolved") -> bool:
        """
        Resolve um alerta.
        
        Returns:
            True se resolvido com sucesso
        """
        with self._lock:
            alert = self.active_alerts.get(alert_id)
            if not alert:
                return False
            
            alert.status = EscalationStatus.RESOLVED
            alert.resolved_at = datetime.now()
            
            # Mover para histórico
            self.alert_history.append(alert)
            if len(self.alert_history) > self.max_history:
                self.alert_history = self.alert_history[-self.max_history:]
            
            del self.active_alerts[alert_id]
            
            if self.on_resolve:
                self.on_resolve(alert, reason)
            
            return True
    
    def get_active_alerts(self, endpoint: Optional[str] = None) -> List[ActiveAlert]:
        """Obtém alertas ativos, opcionalmente filtrados por endpoint."""
        with self._lock:
            alerts = list(self.active_alerts.values())
            if endpoint:
                alerts = [a for a in alerts if a.endpoint == endpoint]
            return sorted(alerts, key=lambda a: a.created_at, reverse=True)
    
    def get_alert(self, alert_id: str) -> Optional[ActiveAlert]:
        """Obtém um alerta específico."""
        return self.active_alerts.get(alert_id)
    
    def get_stats(self) -> Dict[str, Any]:
        """Estatísticas do gerenciador de escalação."""
        with self._lock:
            active_by_level = defaultdict(int)
            active_by_endpoint = defaultdict(int)
            
            for alert in self.active_alerts.values():
                active_by_level[alert.current_level.value] += 1
                active_by_endpoint[alert.endpoint] += 1
            
            return {
                "active_alerts": len(self.active_alerts),
                "total_policies": len(self.policies),
                "alerts_by_level": dict(active_by_level),
                "alerts_by_endpoint": dict(active_by_endpoint),
                "history_size": len(self.alert_history),
                "worker_running": self._running
            }
    
    def _check_rate_limit(self, endpoint: str, policy: EscalationPolicy) -> bool:
        """Verifica rate limit de escalações."""
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        
        # Limpar timestamps antigos
        self.escalation_counts[endpoint] = [
            ts for ts in self.escalation_counts[endpoint] if ts > hour_ago
        ]
        
        if len(self.escalation_counts[endpoint]) >= policy.max_escalations_per_hour:
            return False
        
        self.escalation_counts[endpoint].append(now)
        return True
    
    def _is_quiet_hours(self, policy: EscalationPolicy) -> bool:
        """Verifica se está em horário silencioso."""
        if policy.quiet_hours_start is None or policy.quiet_hours_end is None:
            return False
        
        current_hour = datetime.now().hour
        start = policy.quiet_hours_start
        end = policy.quiet_hours_end
        
        if start <= end:
            return start <= current_hour < end
        else:  # Overnight (ex: 22-6)
            return current_hour >= start or current_hour < end
    
    def _escalation_worker(self):
        """Worker thread que verifica e executa escalações."""
        while self._running:
            try:
                self._check_escalations()
            except Exception as e:
                pass  # Log seria feito pelo sistema principal
            
            time.sleep(0.5)  # Verifica a cada 500ms (rápido para testes)
    
    def _check_escalations(self):
        """Verifica alertas que precisam escalar."""
        now = datetime.now()
        to_escalate = []
        to_expire = []
        
        with self._lock:
            for alert_id, alert in list(self.active_alerts.items()):
                if alert.status not in (EscalationStatus.ACTIVE, EscalationStatus.ESCALATED):
                    continue
                
                policy = self.policies.get(alert.endpoint)
                if not policy:
                    continue
                
                time_in_level = alert.time_in_current_level
                
                # Verificar escalação
                if alert.current_level == EscalationLevel.L1:
                    if time_in_level >= policy.l1_timeout:
                        to_escalate.append((alert, EscalationLevel.L2, policy))
                
                elif alert.current_level == EscalationLevel.L2:
                    if time_in_level >= policy.l2_timeout:
                        to_escalate.append((alert, EscalationLevel.L3, policy))
                
                elif alert.current_level == EscalationLevel.L3:
                    if time_in_level >= policy.l3_timeout:
                        to_expire.append(alert)
        
        # Executar escalações (fora do lock)
        for alert, new_level, policy in to_escalate:
            self._escalate_alert(alert, new_level, policy)
        
        for alert in to_expire:
            self._expire_alert(alert)
    
    def _escalate_alert(self, alert: ActiveAlert, new_level: EscalationLevel, policy: EscalationPolicy):
        """Escala um alerta para o próximo nível."""
        old_level = alert.current_level
        
        # Determinar canais
        if new_level == EscalationLevel.L2:
            channels = policy.l2_channels
        elif new_level == EscalationLevel.L3:
            channels = policy.l3_channels
        else:
            channels = []
        
        # Criar evento
        event = EscalationEvent(
            id=str(uuid.uuid4())[:8],
            alert_id=alert.id,
            endpoint=alert.endpoint,
            from_level=old_level,
            to_level=new_level,
            timestamp=datetime.now(),
            reason=f"Timeout: {alert.time_in_current_level:.0f}s in {old_level.value}",
            notified_channels=channels
        )
        
        with self._lock:
            alert.current_level = new_level
            alert.status = EscalationStatus.ESCALATED
            alert.last_escalation = datetime.now()
            alert.escalation_count += 1
            alert.events.append(event)
        
        # Callback
        if self.on_escalate:
            self.on_escalate(alert, new_level, channels)
    
    def _expire_alert(self, alert: ActiveAlert):
        """Expira um alerta após timeout máximo."""
        with self._lock:
            alert.status = EscalationStatus.EXPIRED
            alert.resolved_at = datetime.now()
            
            # Mover para histórico
            self.alert_history.append(alert)
            if len(self.alert_history) > self.max_history:
                self.alert_history = self.alert_history[-self.max_history:]
            
            del self.active_alerts[alert.id]


# Singleton global
_escalation_manager: Optional[AlertEscalationManager] = None


def get_escalation_manager() -> AlertEscalationManager:
    """Obtém instância global do gerenciador de escalação."""
    global _escalation_manager
    if _escalation_manager is None:
        _escalation_manager = AlertEscalationManager()
    return _escalation_manager
