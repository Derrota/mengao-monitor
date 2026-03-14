"""
Testes para Alert Escalation Manager v3.2 🦞
"""

import unittest
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from alert_escalation import (
    AlertEscalationManager,
    EscalationPolicy,
    EscalationLevel,
    EscalationStatus,
    ActiveAlert
)


class TestEscalationPolicy(unittest.TestCase):
    """Testes para EscalationPolicy."""
    
    def test_default_policy(self):
        """Testa política com valores padrão."""
        policy = EscalationPolicy(
            name="Test Policy",
            endpoint="api.example.com"
        )
        
        self.assertEqual(policy.name, "Test Policy")
        self.assertEqual(policy.endpoint, "api.example.com")
        self.assertTrue(policy.enabled)
        self.assertEqual(policy.l1_timeout, 300)
        self.assertEqual(policy.l2_timeout, 900)
        self.assertEqual(policy.l3_timeout, 1800)
        self.assertEqual(policy.l1_channels, ["websocket"])
        self.assertEqual(policy.l2_channels, ["websocket", "discord"])
        self.assertEqual(policy.l3_channels, ["websocket", "discord", "telegram"])
    
    def test_custom_policy(self):
        """Testa política com valores customizados."""
        policy = EscalationPolicy(
            name="Critical API",
            endpoint="critical.api.com",
            l1_timeout=60,
            l2_timeout=300,
            l3_timeout=600,
            l1_channels=["websocket", "email"],
            l2_channels=["websocket", "discord", "email"],
            l3_channels=["websocket", "discord", "telegram", "email"],
            max_escalations_per_hour=10
        )
        
        self.assertEqual(policy.l1_timeout, 60)
        self.assertEqual(policy.max_escalations_per_hour, 10)
        self.assertIn("email", policy.l1_channels)


class TestActiveAlert(unittest.TestCase):
    """Testes para ActiveAlert."""
    
    def test_alert_creation(self):
        """Testa criação de alerta."""
        alert = ActiveAlert(
            id="test123",
            endpoint="api.test.com",
            message="API is down",
            priority="high",
            created_at=datetime.now()
        )
        
        self.assertEqual(alert.id, "test123")
        self.assertEqual(alert.current_level, EscalationLevel.L1)
        self.assertEqual(alert.status, EscalationStatus.ACTIVE)
        self.assertEqual(alert.escalation_count, 0)
    
    def test_time_active(self):
        """Testa cálculo de tempo ativo."""
        created = datetime.now() - timedelta(minutes=10)
        alert = ActiveAlert(
            id="test123",
            endpoint="api.test.com",
            message="Test",
            priority="high",
            created_at=created
        )
        
        self.assertGreater(alert.time_active, 600)  # > 10 min
        self.assertLess(alert.time_active, 610)     # < ~10 min + margem
    
    def test_time_in_current_level(self):
        """Testa tempo no nível atual."""
        created = datetime.now() - timedelta(minutes=10)
        escalated = datetime.now() - timedelta(minutes=3)
        
        alert = ActiveAlert(
            id="test123",
            endpoint="api.test.com",
            message="Test",
            priority="high",
            created_at=created,
            last_escalation=escalated
        )
        
        # Tempo no nível atual deve ser ~3 min (180s)
        self.assertGreater(alert.time_in_current_level, 175)
        self.assertLess(alert.time_in_current_level, 185)


class TestAlertEscalationManager(unittest.TestCase):
    """Testes para AlertEscalationManager."""
    
    def setUp(self):
        """Setup para cada teste."""
        self.manager = AlertEscalationManager()
        self.policy = EscalationPolicy(
            name="Test Policy",
            endpoint="api.test.com",
            l1_timeout=1,  # 1 segundo para testes rápidos
            l2_timeout=2,
            l3_timeout=5,
            max_escalations_per_hour=100
        )
        self.manager.add_policy(self.policy)
    
    def tearDown(self):
        """Cleanup após cada teste."""
        self.manager.stop()
    
    def test_add_policy(self):
        """Testa adição de política."""
        self.assertIn("api.test.com", self.manager.policies)
        self.assertEqual(self.manager.policies["api.test.com"].name, "Test Policy")
    
    def test_remove_policy(self):
        """Testa remoção de política."""
        self.manager.remove_policy("api.test.com")
        self.assertNotIn("api.test.com", self.manager.policies)
    
    def test_create_alert(self):
        """Testa criação de alerta."""
        callback = Mock()
        self.manager.on_escalate = callback
        
        alert = self.manager.create_alert(
            endpoint="api.test.com",
            message="API down",
            priority="critical"
        )
        
        self.assertIsNotNone(alert)
        self.assertEqual(alert.endpoint, "api.test.com")
        self.assertEqual(alert.current_level, EscalationLevel.L1)
        self.assertEqual(alert.status, EscalationStatus.ACTIVE)
        self.assertEqual(len(alert.events), 1)
        callback.assert_called_once()
    
    def test_create_alert_no_policy(self):
        """Testa criação de alerta sem política."""
        alert = self.manager.create_alert(
            endpoint="unknown.api.com",
            message="Test"
        )
        self.assertIsNone(alert)
    
    def test_create_alert_disabled_policy(self):
        """Testa criação de alerta com política desabilitada."""
        self.policy.enabled = False
        alert = self.manager.create_alert(
            endpoint="api.test.com",
            message="Test"
        )
        self.assertIsNone(alert)
    
    def test_acknowledge_alert(self):
        """Testa reconhecimento de alerta."""
        callback = Mock()
        self.manager.on_acknowledge = callback
        
        alert = self.manager.create_alert("api.test.com", "Test")
        result = self.manager.acknowledge_alert(alert.id, "admin")
        
        self.assertTrue(result)
        self.assertEqual(alert.status, EscalationStatus.ACKNOWLEDGED)
        self.assertEqual(alert.acknowledged_by, "admin")
        callback.assert_called_once()
    
    def test_acknowledge_nonexistent(self):
        """Testa reconhecimento de alerta inexistente."""
        result = self.manager.acknowledge_alert("nonexistent", "admin")
        self.assertFalse(result)
    
    def test_resolve_alert(self):
        """Testa resolução de alerta."""
        callback = Mock()
        self.manager.on_resolve = callback
        
        alert = self.manager.create_alert("api.test.com", "Test")
        result = self.manager.resolve_alert(alert.id, "Fixed")
        
        self.assertTrue(result)
        self.assertEqual(alert.status, EscalationStatus.RESOLVED)
        self.assertIsNotNone(alert.resolved_at)
        self.assertNotIn(alert.id, self.manager.active_alerts)
        self.assertEqual(len(self.manager.alert_history), 1)
        callback.assert_called_once()
    
    def test_resolve_nonexistent(self):
        """Testa resolução de alerta inexistente."""
        result = self.manager.resolve_alert("nonexistent")
        self.assertFalse(result)
    
    def test_get_active_alerts(self):
        """Testa obtenção de alertas ativos."""
        self.manager.create_alert("api.test.com", "Test 1")
        self.manager.create_alert("api.test.com", "Test 2")
        
        alerts = self.manager.get_active_alerts()
        self.assertEqual(len(alerts), 2)
    
    def test_get_active_alerts_filtered(self):
        """Testa obtenção de alertas filtrados por endpoint."""
        policy2 = EscalationPolicy(name="Other", endpoint="other.api.com")
        self.manager.add_policy(policy2)
        
        self.manager.create_alert("api.test.com", "Test 1")
        self.manager.create_alert("other.api.com", "Test 2")
        
        alerts = self.manager.get_active_alerts("api.test.com")
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].endpoint, "api.test.com")
    
    def test_get_stats(self):
        """Testa estatísticas do gerenciador."""
        self.manager.create_alert("api.test.com", "Test 1")
        self.manager.create_alert("api.test.com", "Test 2")
        
        stats = self.manager.get_stats()
        
        self.assertEqual(stats["active_alerts"], 2)
        self.assertEqual(stats["total_policies"], 1)
        self.assertIn("l1", stats["alerts_by_level"])
        self.assertEqual(stats["alerts_by_level"]["l1"], 2)
    
    def test_rate_limit(self):
        """Testa rate limiting de escalações."""
        self.policy.max_escalations_per_hour = 2
        
        # Criar 2 alertas (dentro do limite)
        alert1 = self.manager.create_alert("api.test.com", "Test 1")
        alert2 = self.manager.create_alert("api.test.com", "Test 2")
        
        self.assertIsNotNone(alert1)
        self.assertIsNotNone(alert2)
        
        # Terceiro alerta deve falhar (rate limited)
        alert3 = self.manager.create_alert("api.test.com", "Test 3")
        self.assertIsNone(alert3)
    
    def test_quiet_hours(self):
        """Testa horário silencioso."""
        current_hour = datetime.now().hour
        
        # Configurar quiet hours que incluem hora atual
        self.policy.quiet_hours_start = current_hour
        self.policy.quiet_hours_end = (current_hour + 1) % 24
        self.policy.quiet_hours_escalate_anyway = False
        
        alert = self.manager.create_alert("api.test.com", "Test")
        self.assertIsNone(alert)
    
    def test_quiet_hours_escalate_anyway(self):
        """Testa L3 sempre escala mesmo em quiet hours."""
        current_hour = datetime.now().hour
        
        self.policy.quiet_hours_start = current_hour
        self.policy.quiet_hours_end = (current_hour + 1) % 24
        self.policy.quiet_hours_escalate_anyway = True
        
        alert = self.manager.create_alert("api.test.com", "Test")
        self.assertIsNotNone(alert)


class TestEscalationWorker(unittest.TestCase):
    """Testes para o worker de escalação."""
    
    def setUp(self):
        """Setup para cada teste."""
        self.manager = AlertEscalationManager()
        self.policy = EscalationPolicy(
            name="Fast Policy",
            endpoint="api.fast.com",
            l1_timeout=1.0,  # 1s
            l2_timeout=2.0,  # 2s
            l3_timeout=3.0,  # 3s
            max_escalations_per_hour=100
        )
        self.manager.add_policy(self.policy)
    
    def tearDown(self):
        """Cleanup após cada teste."""
        self.manager.stop()
    
    def test_escalation_l1_to_l2(self):
        """Testa escalação de L1 para L2."""
        callback = Mock()
        self.manager.on_escalate = callback
        
        alert = self.manager.create_alert("api.fast.com", "Test")
        self.assertEqual(alert.current_level, EscalationLevel.L1)
        
        # Iniciar worker
        self.manager.start()
        
        # Esperar escalação (> 1s + margem)
        time.sleep(1.5)
        
        # Verificar se escalou
        alert = self.manager.get_alert(alert.id)
        self.assertEqual(alert.current_level, EscalationLevel.L2)
        self.assertEqual(alert.escalation_count, 1)
        self.assertEqual(len(alert.events), 2)  # Criação + escalação
    
    def test_escalation_l2_to_l3(self):
        """Testa escalação de L2 para L3."""
        alert = self.manager.create_alert("api.fast.com", "Test")
        
        self.manager.start()
        time.sleep(3.5)  # Esperar L1→L2→L3 (1s + 2s + margem)
        
        alert = self.manager.get_alert(alert.id)
        self.assertEqual(alert.current_level, EscalationLevel.L3)
        self.assertEqual(alert.escalation_count, 2)
    
    def test_alert_expiration(self):
        """Testa expiração de alerta após L3 timeout."""
        alert = self.manager.create_alert("api.fast.com", "Test")
        
        self.manager.start()
        time.sleep(7.0)  # Esperar expiração (1s + 2s + 3s + margem)
        
        # Alerta deve ter expirado e ido para histórico
        alert = self.manager.get_alert(alert.id)
        self.assertIsNone(alert)
        self.assertEqual(len(self.manager.alert_history), 1)
        self.assertEqual(self.manager.alert_history[0].status, EscalationStatus.EXPIRED)
    
    def test_acknowledge_prevents_escalation(self):
        """Testa que acknowledge previne escalação."""
        alert = self.manager.create_alert("api.fast.com", "Test")
        
        self.manager.start()
        time.sleep(0.5)  # Um pouco de tempo
        
        # Acknowledge antes do timeout (1s)
        self.manager.acknowledge_alert(alert.id, "admin")
        
        time.sleep(1.5)  # Esperar mais que timeout L1
        
        # Deve permanecer acknowledged, sem escalar
        alert = self.manager.get_alert(alert.id)
        self.assertEqual(alert.status, EscalationStatus.ACKNOWLEDGED)
        self.assertEqual(alert.current_level, EscalationLevel.L1)


class TestEdgeCases(unittest.TestCase):
    """Testes de edge cases."""
    
    def setUp(self):
        self.manager = AlertEscalationManager()
    
    def test_multiple_endpoints(self):
        """Testa múltiplos endpoints com políticas diferentes."""
        policy1 = EscalationPolicy(name="API 1", endpoint="api1.com", l1_timeout=100)
        policy2 = EscalationPolicy(name="API 2", endpoint="api2.com", l1_timeout=200)
        
        self.manager.add_policy(policy1)
        self.manager.add_policy(policy2)
        
        alert1 = self.manager.create_alert("api1.com", "Test 1")
        alert2 = self.manager.create_alert("api2.com", "Test 2")
        
        self.assertEqual(alert1.endpoint, "api1.com")
        self.assertEqual(alert2.endpoint, "api2.com")
        self.assertEqual(len(self.manager.active_alerts), 2)
    
    def test_resolve_during_escalation(self):
        """Testa resolução durante processo de escalação."""
        policy = EscalationPolicy(
            name="Fast",
            endpoint="fast.com",
            l1_timeout=0.5,
            max_escalations_per_hour=100
        )
        self.manager.add_policy(policy)
        
        alert = self.manager.create_alert("fast.com", "Test")
        self.manager.start()
        
        time.sleep(0.3)
        self.manager.resolve_alert(alert.id, "Manual fix")
        
        time.sleep(1.0)
        
        # Deve permanecer resolvido
        self.assertIsNone(self.manager.get_alert(alert.id))
        self.assertEqual(len(self.manager.alert_history), 1)
        self.assertEqual(self.manager.alert_history[0].status, EscalationStatus.RESOLVED)
    
    def test_history_limit(self):
        """Testa limite de histórico."""
        self.manager.max_history = 5
        
        policy = EscalationPolicy(
            name="Test",
            endpoint="test.com",
            l1_timeout=0.1,
            l2_timeout=0.1,
            l3_timeout=0.1,
            max_escalations_per_hour=100
        )
        self.manager.add_policy(policy)
        
        # Criar e resolver 10 alertas
        for i in range(10):
            alert = self.manager.create_alert("test.com", f"Test {i}")
            self.manager.resolve_alert(alert.id)
        
        # Histórico deve ter no máximo 5
        self.assertEqual(len(self.manager.alert_history), 5)


if __name__ == "__main__":
    unittest.main()
