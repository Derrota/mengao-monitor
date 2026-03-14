"""
Notification Manager para Mengão Monitor v3.1 🦞
Unifica alertas via WebSocket + Webhooks (Discord/Slack/Telegram).
"""

import json
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from websocket_server import (
    broadcast_alert, broadcast_status_update, broadcast_sla_update,
    get_websocket_server
)


class NotificationPriority(Enum):
    """Prioridade da notificação."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class NotificationChannel(Enum):
    """Canal de entrega."""
    WEBSOCKET = "websocket"
    DISCORD = "discord"
    SLACK = "slack"
    TELEGRAM = "telegram"
    EMAIL = "email"


@dataclass
class NotificationRule:
    """Regra de notificação."""
    name: str
    enabled: bool = True
    channels: List[NotificationChannel] = field(default_factory=list)
    priority_filter: List[NotificationPriority] = field(default_factory=list)
    endpoint_filter: List[str] = field(default_factory=list)  # vazio = todos
    cooldown_seconds: int = 300  # 5 minutos entre notificações similares
    rate_limit_per_hour: int = 10


@dataclass
class Notification:
    """Notificação a ser enviada."""
    id: str
    title: str
    message: str
    priority: NotificationPriority
    timestamp: datetime = field(default_factory=datetime.now)
    endpoint: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    channels: List[NotificationChannel] = field(default_factory=list)
    sent: bool = False
    attempts: int = 0
    last_attempt: Optional[datetime] = None


class NotificationManager:
    """Gerenciador unificado de notificações."""
    
    def __init__(self):
        self.rules: Dict[str, NotificationRule] = {}
        self.notification_history: List[Notification] = []
        self.max_history = 1000
        
        # Rate limiting
        self.sent_count: Dict[str, int] = defaultdict(int)  # channel -> count
        self.last_reset = datetime.now()
        
        # Cooldown tracking
        self.last_sent: Dict[str, datetime] = {}  # key -> timestamp
        
        # Webhook senders (injetados)
        self.webhook_senders: Dict[NotificationChannel, Callable] = {}
        
        # Stats
        self.stats = {
            'notifications_total': 0,
            'notifications_sent': 0,
            'notifications_failed': 0,
            'notifications_suppressed': 0,
            'by_priority': defaultdict(int),
            'by_channel': defaultdict(int)
        }
        
        # Lock para thread safety
        self._lock = threading.Lock()
        
        # Regra padrão: WebSocket para todos os alertas
        self.add_rule(NotificationRule(
            name='default_websocket',
            channels=[NotificationChannel.WEBSOCKET],
            cooldown_seconds=0,  # WebSocket não precisa de cooldown
            rate_limit_per_hour=1000  # WebSocket é local, sem limite real
        ))
    
    def add_rule(self, rule: NotificationRule):
        """Adiciona regra de notificação."""
        with self._lock:
            self.rules[rule.name] = rule
    
    def remove_rule(self, name: str):
        """Remove regra de notificação."""
        with self._lock:
            self.rules.pop(name, None)
    
    def register_webhook_sender(self, channel: NotificationChannel, sender: Callable):
        """Registra função de envio para um canal de webhook."""
        self.webhook_senders[channel] = sender
    
    def notify(self, title: str, message: str, priority: NotificationPriority,
               endpoint: Optional[str] = None, data: Optional[Dict[str, Any]] = None,
               force_channels: Optional[List[NotificationChannel]] = None) -> str:
        """
        Envia notificação.
        
        Args:
            title: Título da notificação
            message: Corpo da mensagem
            priority: Prioridade
            endpoint: Endpoint relacionado (opcional)
            data: Dados adicionais
            force_channels: Canais específicos (sobrescreve regras)
            
        Returns:
            ID da notificação
        """
        with self._lock:
            notif_id = f"notif_{int(time.time() * 1000)}"
            notification = Notification(
                id=notif_id,
                title=title,
                message=message,
                priority=priority,
                endpoint=endpoint,
                data=data or {}
            )
            
            self.stats['notifications_total'] += 1
            self.stats['by_priority'][priority.value] += 1
            
            # Determina canais de entrega
            if force_channels:
                notification.channels = force_channels
            else:
                notification.channels = self._get_channels_for_notification(notification)
            
            # Verifica rate limiting e cooldown
            if not self._should_send(notification):
                self.stats['notifications_suppressed'] += 1
                notification.sent = False
                self.notification_history.append(notification)
                self._trim_history()
                return notif_id
            
            # Envia para cada canal
            for channel in notification.channels:
                self._send_to_channel(notification, channel)
            
            notification.sent = True
            self.notification_history.append(notification)
            self._trim_history()
            
            return notif_id
    
    def _get_channels_for_notification(self, notification: Notification) -> List[NotificationChannel]:
        """Determina canais baseado nas regras."""
        channels = set()
        
        for rule in self.rules.values():
            if not rule.enabled:
                continue
            
            # Filtro de prioridade
            if rule.priority_filter and notification.priority not in rule.priority_filter:
                continue
            
            # Filtro de endpoint
            if rule.endpoint_filter and notification.endpoint not in rule.endpoint_filter:
                continue
            
            # Adiciona canais da regra
            for channel in rule.channels:
                channels.add(channel)
        
        return list(channels)
    
    def _should_send(self, notification: Notification) -> bool:
        """Verifica se deve enviar (rate limiting + cooldown)."""
        # Reset contador a cada hora
        now = datetime.now()
        if (now - self.last_reset).total_seconds() > 3600:
            self.sent_count.clear()
            self.last_reset = now
        
        for channel in notification.channels:
            # Verifica rate limit por canal
            rule = self._get_rule_for_channel(channel)
            if rule and self.sent_count[channel.value] >= rule.rate_limit_per_hour:
                return False
            
            # Verifica cooldown
            cooldown_key = f"{channel.value}:{notification.endpoint or 'global'}"
            if cooldown_key in self.last_sent:
                last = self.last_sent[cooldown_key]
                if rule and (now - last).total_seconds() < rule.cooldown_seconds:
                    return False
        
        return True
    
    def _get_rule_for_channel(self, channel: NotificationChannel) -> Optional[NotificationRule]:
        """Busca regra que inclui um canal específico."""
        for rule in self.rules.values():
            if channel in rule.channels:
                return rule
        return None
    
    def _send_to_channel(self, notification: Notification, channel: NotificationChannel):
        """Envia notificação para um canal específico."""
        notification.attempts += 1
        notification.last_attempt = datetime.now()
        
        try:
            if channel == NotificationChannel.WEBSOCKET:
                self._send_websocket(notification)
            elif channel in self.webhook_senders:
                self.webhook_senders[channel](notification)
            else:
                print(f"⚠️ No sender registered for channel: {channel.value}")
                return
            
            # Atualiza stats
            self.sent_count[channel.value] += 1
            self.stats['notifications_sent'] += 1
            self.stats['by_channel'][channel.value] += 1
            
            # Atualiza cooldown
            cooldown_key = f"{channel.value}:{notification.endpoint or 'global'}"
            self.last_sent[cooldown_key] = datetime.now()
            
        except Exception as e:
            print(f"❌ Failed to send notification via {channel.value}: {e}")
            self.stats['notifications_failed'] += 1
    
    def _send_websocket(self, notification: Notification):
        """Envia via WebSocket."""
        broadcast_alert({
            'id': notification.id,
            'title': notification.title,
            'message': notification.message,
            'priority': notification.priority.value,
            'endpoint': notification.endpoint,
            'data': notification.data,
            'timestamp': notification.timestamp.isoformat()
        })
    
    def _trim_history(self):
        """Limita tamanho do histórico."""
        if len(self.notification_history) > self.max_history:
            self.notification_history = self.notification_history[-self.max_history:]
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas."""
        with self._lock:
            stats = self.stats.copy()
            stats['rules'] = {
                name: {
                    'enabled': rule.enabled,
                    'channels': [c.value for c in rule.channels],
                    'cooldown_seconds': rule.cooldown_seconds,
                    'rate_limit_per_hour': rule.rate_limit_per_hour
                }
                for name, rule in self.rules.items()
            }
            stats['recent_notifications'] = [
                {
                    'id': n.id,
                    'title': n.title,
                    'priority': n.priority.value,
                    'channels': [c.value for c in n.channels],
                    'sent': n.sent,
                    'timestamp': n.timestamp.isoformat()
                }
                for n in self.notification_history[-10:]
            ]
            return stats
    
    def get_history(self, limit: int = 50, 
                    priority: Optional[NotificationPriority] = None,
                    endpoint: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retorna histórico de notificações com filtros."""
        with self._lock:
            history = self.notification_history
            
            if priority:
                history = [n for n in history if n.priority == priority]
            
            if endpoint:
                history = [n for n in history if n.endpoint == endpoint]
            
            return [
                {
                    'id': n.id,
                    'title': n.title,
                    'message': n.message,
                    'priority': n.priority.value,
                    'endpoint': n.endpoint,
                    'channels': [c.value for c in n.channels],
                    'sent': n.sent,
                    'attempts': n.attempts,
                    'timestamp': n.timestamp.isoformat(),
                    'last_attempt': n.last_attempt.isoformat() if n.last_attempt else None
                }
                for n in history[-limit:]
            ]


# Instância global (singleton)
_notification_manager: Optional[NotificationManager] = None


def get_notification_manager() -> NotificationManager:
    """Retorna instância global do gerenciador de notificações."""
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = NotificationManager()
    return _notification_manager


def notify(title: str, message: str, priority: NotificationPriority,
           endpoint: Optional[str] = None, data: Optional[Dict[str, Any]] = None,
           force_channels: Optional[List[NotificationChannel]] = None) -> str:
    """Função de conveniência para enviar notificação."""
    manager = get_notification_manager()
    return manager.notify(title, message, priority, endpoint, data, force_channels)


# Funções de conveniência por prioridade
def notify_low(title: str, message: str, **kwargs) -> str:
    return notify(title, message, NotificationPriority.LOW, **kwargs)


def notify_medium(title: str, message: str, **kwargs) -> str:
    return notify(title, message, NotificationPriority.MEDIUM, **kwargs)


def notify_high(title: str, message: str, **kwargs) -> str:
    return notify(title, message, NotificationPriority.HIGH, **kwargs)


def notify_critical(title: str, message: str, **kwargs) -> str:
    return notify(title, message, NotificationPriority.CRITICAL, **kwargs)
