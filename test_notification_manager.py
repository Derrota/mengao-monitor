"""
Testes para NotificationManager v3.1 🦞
"""

import unittest
import time
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from notification_manager import (
    NotificationManager, NotificationRule, Notification, 
    NotificationPriority, NotificationChannel,
    get_notification_manager, notify, notify_low, notify_medium, 
    notify_high, notify_critical
)

# Mock broadcast_alert para testes
import notification_manager
notification_manager.broadcast_alert = MagicMock()


class TestNotificationPriority(unittest.TestCase):
    """Testes para enum NotificationPriority."""
    
    def test_values(self):
        self.assertEqual(NotificationPriority.LOW.value, "low")
        self.assertEqual(NotificationPriority.MEDIUM.value, "medium")
        self.assertEqual(NotificationPriority.HIGH.value, "high")
        self.assertEqual(NotificationPriority.CRITICAL.value, "critical")


class TestNotificationChannel(unittest.TestCase):
    """Testes para enum NotificationChannel."""
    
    def test_values(self):
        self.assertEqual(NotificationChannel.WEBSOCKET.value, "websocket")
        self.assertEqual(NotificationChannel.DISCORD.value, "discord")
        self.assertEqual(NotificationChannel.SLACK.value, "slack")
        self.assertEqual(NotificationChannel.TELEGRAM.value, "telegram")
        self.assertEqual(NotificationChannel.EMAIL.value, "email")


class TestNotificationRule(unittest.TestCase):
    """Testes para NotificationRule."""
    
    def test_default_values(self):
        rule = NotificationRule(name="test")
        self.assertEqual(rule.name, "test")
        self.assertTrue(rule.enabled)
        self.assertEqual(rule.channels, [])
        self.assertEqual(rule.priority_filter, [])
        self.assertEqual(rule.endpoint_filter, [])
        self.assertEqual(rule.cooldown_seconds, 300)
        self.assertEqual(rule.rate_limit_per_hour, 10)
    
    def test_custom_values(self):
        rule = NotificationRule(
            name="critical_alerts",
            enabled=True,
            channels=[NotificationChannel.DISCORD, NotificationChannel.TELEGRAM],
            priority_filter=[NotificationPriority.HIGH, NotificationPriority.CRITICAL],
            endpoint_filter=["/api/health"],
            cooldown_seconds=60,
            rate_limit_per_hour=5
        )
        self.assertEqual(rule.name, "critical_alerts")
        self.assertTrue(rule.enabled)
        self.assertEqual(len(rule.channels), 2)
        self.assertEqual(len(rule.priority_filter), 2)
        self.assertEqual(rule.endpoint_filter, ["/api/health"])
        self.assertEqual(rule.cooldown_seconds, 60)
        self.assertEqual(rule.rate_limit_per_hour, 5)


class TestNotification(unittest.TestCase):
    """Testes para Notification."""
    
    def test_creation(self):
        notif = Notification(
            id="test_1",
            title="Test Alert",
            message="This is a test",
            priority=NotificationPriority.HIGH
        )
        self.assertEqual(notif.id, "test_1")
        self.assertEqual(notif.title, "Test Alert")
        self.assertEqual(notif.message, "This is a test")
        self.assertEqual(notif.priority, NotificationPriority.HIGH)
        self.assertIsNone(notif.endpoint)
        self.assertEqual(notif.data, {})
        self.assertEqual(notif.channels, [])
        self.assertFalse(notif.sent)
        self.assertEqual(notif.attempts, 0)
        self.assertIsNone(notif.last_attempt)
    
    def test_with_endpoint_and_data(self):
        notif = Notification(
            id="test_2",
            title="API Down",
            message="Health check failed",
            priority=NotificationPriority.CRITICAL,
            endpoint="/api/health",
            data={"status_code": 500, "response_time": 5000}
        )
        self.assertEqual(notif.endpoint, "/api/health")
        self.assertEqual(notif.data["status_code"], 500)
        self.assertEqual(notif.data["response_time"], 5000)


class TestNotificationManager(unittest.TestCase):
    """Testes para NotificationManager."""
    
    def setUp(self):
        self.manager = NotificationManager()
    
    def test_initial_state(self):
        self.assertEqual(len(self.manager.rules), 1)  # default_websocket
        self.assertEqual(len(self.manager.notification_history), 0)
        self.assertEqual(self.manager.stats['notifications_total'], 0)
    
    def test_add_rule(self):
        rule = NotificationRule(
            name="discord_critical",
            channels=[NotificationChannel.DISCORD],
            priority_filter=[NotificationPriority.CRITICAL]
        )
        self.manager.add_rule(rule)
        self.assertIn("discord_critical", self.manager.rules)
        self.assertEqual(len(self.manager.rules), 2)
    
    def test_remove_rule(self):
        self.manager.remove_rule("default_websocket")
        self.assertEqual(len(self.manager.rules), 0)
    
    def test_register_webhook_sender(self):
        sender = MagicMock()
        self.manager.register_webhook_sender(NotificationChannel.DISCORD, sender)
        self.assertIn(NotificationChannel.DISCORD, self.manager.webhook_senders)
    
    @patch('notification_manager.broadcast_alert')
    def test_notify_websocket(self, mock_broadcast):
        notif_id = self.manager.notify(
            title="Test Alert",
            message="This is a test",
            priority=NotificationPriority.MEDIUM
        )
        
        self.assertIsNotNone(notif_id)
        self.assertEqual(self.manager.stats['notifications_total'], 1)
        self.assertEqual(self.manager.stats['notifications_sent'], 1)
        self.assertEqual(len(self.manager.notification_history), 1)
        
        # Verifica se broadcast foi chamado
        mock_broadcast.assert_called_once()
    
    def test_notify_with_force_channels(self):
        # Registra sender mock para Discord
        discord_sender = MagicMock()
        self.manager.register_webhook_sender(NotificationChannel.DISCORD, discord_sender)
        
        notif_id = self.manager.notify(
            title="Test Alert",
            message="This is a test",
            priority=NotificationPriority.HIGH,
            force_channels=[NotificationChannel.DISCORD]
        )
        
        self.assertIsNotNone(notif_id)
        discord_sender.assert_called_once()
    
    def test_rate_limiting(self):
        # Remove regra padrão para evitar interferência
        self.manager.remove_rule("default_websocket")
        
        # Registra sender mock
        sender = MagicMock()
        self.manager.register_webhook_sender(NotificationChannel.DISCORD, sender)
        
        # Adiciona regra com rate limit baixo
        rule = NotificationRule(
            name="limited",
            channels=[NotificationChannel.DISCORD],
            rate_limit_per_hour=2,
            cooldown_seconds=0  # Sem cooldown para este teste
        )
        self.manager.add_rule(rule)
        
        # Envia 3 notificações (deve suprimir a 3ª)
        for i in range(3):
            self.manager.notify(
                title=f"Alert {i}",
                message=f"Message {i}",
                priority=NotificationPriority.HIGH,
                force_channels=[NotificationChannel.DISCORD]
            )
        
        # Apenas 2 devem ter sido enviadas
        self.assertEqual(sender.call_count, 2)
        self.assertEqual(self.manager.stats['notifications_suppressed'], 1)
    
    def test_cooldown(self):
        # Remove regra padrão para evitar interferência
        self.manager.remove_rule("default_websocket")
        
        # Registra sender mock
        sender = MagicMock()
        self.manager.register_webhook_sender(NotificationChannel.DISCORD, sender)
        
        # Adiciona regra com cooldown
        rule = NotificationRule(
            name="cooldown_test",
            channels=[NotificationChannel.DISCORD],
            cooldown_seconds=60
        )
        self.manager.add_rule(rule)
        
        # Envia primeira notificação
        self.manager.notify(
            title="Alert 1",
            message="First alert",
            priority=NotificationPriority.HIGH,
            endpoint="/api/test",
            force_channels=[NotificationChannel.DISCORD]
        )
        
        # Envia segunda notificação imediatamente (deve ser suprimida)
        self.manager.notify(
            title="Alert 2",
            message="Second alert",
            priority=NotificationPriority.HIGH,
            endpoint="/api/test",
            force_channels=[NotificationChannel.DISCORD]
        )
        
        # Apenas 1 deve ter sido enviada
        self.assertEqual(sender.call_count, 1)
        self.assertEqual(self.manager.stats['notifications_suppressed'], 1)
    
    def test_priority_filter(self):
        # Remove regra padrão para evitar interferência
        self.manager.remove_rule("default_websocket")
        
        # Registra sender mock
        sender = MagicMock()
        self.manager.register_webhook_sender(NotificationChannel.DISCORD, sender)
        
        # Adiciona regra que só aceita HIGH e CRITICAL
        rule = NotificationRule(
            name="high_only",
            channels=[NotificationChannel.DISCORD],
            priority_filter=[NotificationPriority.HIGH, NotificationPriority.CRITICAL]
        )
        self.manager.add_rule(rule)
        
        # Envia notificação LOW (deve ser filtrada)
        self.manager.notify(
            title="Low Alert",
            message="This is low priority",
            priority=NotificationPriority.LOW,
            force_channels=[NotificationChannel.DISCORD]
        )
        
        # Envia notificação HIGH (deve passar)
        self.manager.notify(
            title="High Alert",
            message="This is high priority",
            priority=NotificationPriority.HIGH,
            force_channels=[NotificationChannel.DISCORD]
        )
        
        # Apenas 1 deve ter sido enviada (HIGH)
        self.assertEqual(sender.call_count, 1)
    
    def test_endpoint_filter(self):
        # Remove regra padrão para evitar interferência
        self.manager.remove_rule("default_websocket")
        
        # Registra sender mock
        sender = MagicMock()
        self.manager.register_webhook_sender(NotificationChannel.DISCORD, sender)
        
        # Adiciona regra que só aceita endpoint específico
        rule = NotificationRule(
            name="health_only",
            channels=[NotificationChannel.DISCORD],
            endpoint_filter=["/api/health"]
        )
        self.manager.add_rule(rule)
        
        # Envia notificação para endpoint diferente (deve ser filtrada)
        self.manager.notify(
            title="Other Alert",
            message="This is for another endpoint",
            priority=NotificationPriority.HIGH,
            endpoint="/api/status"
        )
        
        # Envia notificação para endpoint correto (deve passar)
        self.manager.notify(
            title="Health Alert",
            message="This is for health",
            priority=NotificationPriority.HIGH,
            endpoint="/api/health"
        )
        
        # Apenas 1 deve ter sido enviada
        self.assertEqual(sender.call_count, 1)
    
    def test_get_stats(self):
        # Envia algumas notificações
        self.manager.notify("Test 1", "Message 1", NotificationPriority.LOW)
        self.manager.notify("Test 2", "Message 2", NotificationPriority.HIGH)
        
        stats = self.manager.get_stats()
        
        self.assertEqual(stats['notifications_total'], 2)
        self.assertEqual(stats['notifications_sent'], 2)
        self.assertIn('rules', stats)
        self.assertIn('recent_notifications', stats)
        self.assertEqual(len(stats['recent_notifications']), 2)
    
    def test_get_history(self):
        # Envia notificações com diferentes prioridades
        self.manager.notify("Low", "msg", NotificationPriority.LOW)
        self.manager.notify("High", "msg", NotificationPriority.HIGH)
        self.manager.notify("Critical", "msg", NotificationPriority.CRITICAL)
        
        # Histórico completo
        history = self.manager.get_history()
        self.assertEqual(len(history), 3)
        
        # Filtrar por prioridade
        high_history = self.manager.get_history(priority=NotificationPriority.HIGH)
        self.assertEqual(len(high_history), 1)
        self.assertEqual(high_history[0]['priority'], 'high')
    
    def test_get_history_with_endpoint_filter(self):
        self.manager.notify("Alert 1", "msg", NotificationPriority.HIGH, endpoint="/api/a")
        self.manager.notify("Alert 2", "msg", NotificationPriority.HIGH, endpoint="/api/b")
        
        history = self.manager.get_history(endpoint="/api/a")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['endpoint'], '/api/a')


class TestNotificationManagerSingleton(unittest.TestCase):
    """Testes para singleton global."""
    
    def test_get_notification_manager(self):
        manager1 = get_notification_manager()
        manager2 = get_notification_manager()
        self.assertIs(manager1, manager2)
    
    @patch('notification_manager.broadcast_alert')
    def test_notify_convenience(self, mock_broadcast):
        notif_id = notify(
            title="Convenience Test",
            message="Using convenience function",
            priority=NotificationPriority.MEDIUM
        )
        
        self.assertIsNotNone(notif_id)
        mock_broadcast.assert_called_once()
    
    @patch('notification_manager.broadcast_alert')
    def test_priority_convenience_functions(self, mock_broadcast):
        notify_low("Low", "msg")
        notify_medium("Medium", "msg")
        notify_high("High", "msg")
        notify_critical("Critical", "msg")
        
        self.assertEqual(mock_broadcast.call_count, 4)


class TestNotificationManagerEdgeCases(unittest.TestCase):
    """Testes para edge cases."""
    
    def setUp(self):
        self.manager = NotificationManager()
    
    def test_notify_with_empty_channels(self):
        # Remove regra padrão
        self.manager.remove_rule("default_websocket")
        
        # Adiciona regra sem canais
        rule = NotificationRule(name="empty", channels=[])
        self.manager.add_rule(rule)
        
        notif_id = self.manager.notify("Test", "msg", NotificationPriority.HIGH)
        
        # Notificação criada mas não enviada (sem canais)
        self.assertIsNotNone(notif_id)
        self.assertEqual(self.manager.stats['notifications_total'], 1)
        self.assertEqual(self.manager.stats['notifications_sent'], 0)
    
    def test_history_limit(self):
        # Envia mais notificações que o limite
        for i in range(1050):
            self.manager.notify(f"Test {i}", f"msg {i}", NotificationPriority.LOW)
        
        # Histórico deve ser limitado
        self.assertEqual(len(self.manager.notification_history), 1000)
    
    def test_disabled_rule(self):
        sender = MagicMock()
        self.manager.register_webhook_sender(NotificationChannel.DISCORD, sender)
        
        # Adiciona regra desabilitada
        rule = NotificationRule(
            name="disabled",
            enabled=False,
            channels=[NotificationChannel.DISCORD]
        )
        self.manager.add_rule(rule)
        
        self.manager.notify("Test", "msg", NotificationPriority.HIGH)
        
        # Discord não deve ser chamado (regra desabilitada)
        sender.assert_not_called()


if __name__ == '__main__':
    unittest.main()
