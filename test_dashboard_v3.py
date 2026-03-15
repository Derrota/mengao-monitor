"""
Testes para Dashboard v3 🦞

Cobertura:
- DashboardConfig
- DashboardV3 renderização
- API list rendering
- Alert list rendering
- Notification list rendering
- Uptime calculation
- Time ago formatting
- Stats tracking
"""

import unittest
from datetime import datetime, timedelta
from dashboard_v3 import DashboardV3, DashboardConfig, create_dashboard


class TestDashboardConfig(unittest.TestCase):
    """Testes para DashboardConfig"""

    def test_default_config(self):
        """Config padrão"""
        config = DashboardConfig()
        self.assertEqual(config.title, "Mengão Monitor")
        self.assertEqual(config.theme, "dark")
        self.assertEqual(config.refresh_interval, 5)
        self.assertEqual(config.websocket_url, "ws://localhost:8082")
        self.assertEqual(config.max_alerts_display, 50)
        self.assertEqual(config.chart_history_points, 60)
        self.assertTrue(config.auto_refresh)
        self.assertTrue(config.show_flamengo_badge)

    def test_custom_config(self):
        """Config customizada"""
        config = DashboardConfig(
            title="Custom Monitor",
            theme="light",
            refresh_interval=10,
            websocket_url="ws://custom:9090",
            show_flamengo_badge=False
        )
        self.assertEqual(config.title, "Custom Monitor")
        self.assertEqual(config.theme, "light")
        self.assertEqual(config.refresh_interval, 10)
        self.assertEqual(config.websocket_url, "ws://custom:9090")
        self.assertFalse(config.show_flamengo_badge)


class TestDashboardV3(unittest.TestCase):
    """Testes para DashboardV3"""

    def setUp(self):
        self.dashboard = DashboardV3()

    def test_initialization(self):
        """Inicialização básica"""
        self.assertIsNotNone(self.dashboard.config)
        self.assertEqual(self.dashboard.config.title, "Mengão Monitor")

    def test_initialization_custom_config(self):
        """Inicialização com config customizada"""
        config = DashboardConfig(title="Test Monitor")
        dashboard = DashboardV3(config)
        self.assertEqual(dashboard.config.title, "Test Monitor")

    def test_stats_initial(self):
        """Stats iniciais"""
        stats = self.dashboard.get_stats()
        self.assertEqual(stats["renders"], 0)
        self.assertIsNone(stats["last_render"])
        self.assertEqual(stats["errors"], 0)

    def test_stats_after_render(self):
        """Stats após render"""
        self.dashboard.render_html()
        stats = self.dashboard.get_stats()
        self.assertEqual(stats["renders"], 1)
        self.assertIsNotNone(stats["last_render"])

    def test_render_basic(self):
        """Renderização básica"""
        html = self.dashboard.render_html()
        self.assertIn("Mengão Monitor", html)
        self.assertIn("Dashboard v3", html)
        self.assertIn("chart.js", html.lower())
        self.assertIn("WebSocket", html)

    def test_render_with_apis(self):
        """Renderização com APIs"""
        apis = [
            {"name": "API 1", "status": "online", "uptime_percent": 99.9, "response_time_ms": 100},
            {"name": "API 2", "status": "offline", "uptime_percent": 95.0, "response_time_ms": 0},
        ]
        html = self.dashboard.render_html(apis=apis)
        self.assertIn("API 1", html)
        self.assertIn("API 2", html)
        self.assertIn("online", html)
        self.assertIn("offline", html)
        self.assertIn("1/2 online", html)

    def test_render_with_alerts(self):
        """Renderização com alertas"""
        alerts = [
            {"level": "L1", "endpoint": "api.test.com", "reason": "timeout", "status": "active"},
            {"level": "L2", "endpoint": "api.prod.com", "reason": "down", "status": "escalated"},
            {"level": "L3", "endpoint": "api.critical.com", "reason": "critical", "status": "active"},
        ]
        html = self.dashboard.render_html(alerts=alerts)
        self.assertIn("L1", html)
        self.assertIn("L2", html)
        self.assertIn("L3", html)
        self.assertIn("api.test.com", html)
        self.assertIn("api.prod.com", html)

    def test_render_with_notifications(self):
        """Renderização com notificações"""
        notifications = [
            {"title": "Alert", "message": "API down", "timestamp": datetime.now().isoformat()},
            {"title": "Recovery", "message": "API back online", "timestamp": datetime.now().isoformat()},
        ]
        html = self.dashboard.render_html(notifications=notifications)
        self.assertIn("Alert", html)
        self.assertIn("Recovery", html)
        self.assertIn("API down", html)

    def test_render_with_system_metrics(self):
        """Renderização com métricas de sistema"""
        system_metrics = {"cpu": 45.2, "memory": 62.1, "disk": 51.0}
        html = self.dashboard.render_html(system_metrics=system_metrics)
        self.assertIn("systemChart", html)

    def test_render_with_websocket_status(self):
        """Renderização com status WebSocket"""
        websocket_status = {"connections_active": 3, "messages_sent": 100}
        html = self.dashboard.render_html(websocket_status=websocket_status)
        self.assertIn("3 clientes conectados", html)

    def test_render_flamengo_badge(self):
        """Badge do Flamengo"""
        config = DashboardConfig(show_flamengo_badge=True)
        dashboard = DashboardV3(config)
        html = dashboard.render_html()
        self.assertIn("AO VIVO", html)
        self.assertIn("🔴⚫", html)

    def test_render_no_flamengo_badge(self):
        """Sem badge do Flamengo"""
        config = DashboardConfig(show_flamengo_badge=False)
        dashboard = DashboardV3(config)
        html = dashboard.render_html()
        self.assertNotIn("AO VIVO", html)

    def test_render_footer(self):
        """Footer rubro-negro"""
        html = self.dashboard.render_html()
        self.assertIn("Uma vez Flamengo, sempre Flamengo", html)
        self.assertIn("TJF", html)

    def test_render_dark_theme(self):
        """Tema dark (padrão)"""
        html = self.dashboard.render_html()
        self.assertIn("--fla-dark", html)
        self.assertIn("--fla-red", html)


class TestRenderApiList(unittest.TestCase):
    """Testes para renderização de lista de APIs"""

    def setUp(self):
        self.dashboard = DashboardV3()

    def test_empty_list(self):
        """Lista vazia"""
        result = self.dashboard._render_api_list([])
        self.assertIn("Nenhuma API", result)

    def test_single_api(self):
        """Uma API"""
        apis = [{"name": "Test API", "status": "online", "uptime_percent": 99.9, "response_time_ms": 50}]
        result = self.dashboard._render_api_list(apis)
        self.assertIn("Test API", result)
        self.assertIn("online", result)
        self.assertIn("99.9", result)

    def test_multiple_apis(self):
        """Múltiplas APIs"""
        apis = [
            {"name": "API 1", "status": "online", "uptime_percent": 99.9, "response_time_ms": 50},
            {"name": "API 2", "status": "offline", "uptime_percent": 95.0, "response_time_ms": 0},
            {"name": "API 3", "status": "degraded", "uptime_percent": 97.5, "response_time_ms": 500},
        ]
        result = self.dashboard._render_api_list(apis)
        self.assertIn("API 1", result)
        self.assertIn("API 2", result)
        self.assertIn("API 3", result)
        self.assertIn("degraded", result)

    def test_limit_20(self):
        """Limite de 20 APIs"""
        apis = [{"name": f"API {i}", "status": "online", "uptime_percent": 99.0, "response_time_ms": 100} 
                for i in range(30)]
        result = self.dashboard._render_api_list(apis)
        # Deve ter no máximo 20
        self.assertEqual(result.count("api-item"), 20)


class TestRenderAlertList(unittest.TestCase):
    """Testes para renderização de lista de alertas"""

    def setUp(self):
        self.dashboard = DashboardV3()

    def test_empty_list(self):
        """Lista vazia"""
        result = self.dashboard._render_alert_list([])
        self.assertIn("Nenhum alerta", result)

    def test_single_alert(self):
        """Um alerta"""
        alerts = [{"level": "L1", "endpoint": "test.com", "reason": "timeout", "status": "active"}]
        result = self.dashboard._render_alert_list(alerts)
        self.assertIn("L1", result)
        self.assertIn("test.com", result)
        self.assertIn("timeout", result)

    def test_multiple_levels(self):
        """Múltiplos níveis"""
        alerts = [
            {"level": "L1", "endpoint": "a.com", "reason": "slow", "status": "active"},
            {"level": "L2", "endpoint": "b.com", "reason": "down", "status": "escalated"},
            {"level": "L3", "endpoint": "c.com", "reason": "critical", "status": "active"},
        ]
        result = self.dashboard._render_alert_list(alerts)
        self.assertIn("L1", result)
        self.assertIn("L2", result)
        self.assertIn("L3", result)

    def test_limit_10(self):
        """Limite de 10 alertas"""
        alerts = [{"level": "L1", "endpoint": f"api{i}.com", "reason": "test", "status": "active"}
                  for i in range(20)]
        result = self.dashboard._render_alert_list(alerts)
        self.assertEqual(result.count("alert-item"), 10)


class TestRenderNotificationList(unittest.TestCase):
    """Testes para renderização de lista de notificações"""

    def setUp(self):
        self.dashboard = DashboardV3()

    def test_empty_list(self):
        """Lista vazia"""
        result = self.dashboard._render_notification_list([])
        self.assertIn("Nenhuma notificação", result)

    def test_single_notification(self):
        """Uma notificação"""
        notifs = [{"title": "Test", "message": "Hello", "timestamp": datetime.now().isoformat()}]
        result = self.dashboard._render_notification_list(notifs)
        self.assertIn("Test", result)
        self.assertIn("Hello", result)

    def test_limit_20(self):
        """Limite de 20 notificações"""
        notifs = [{"title": f"Notif {i}", "message": "msg", "timestamp": datetime.now().isoformat()}
                  for i in range(30)]
        result = self.dashboard._render_notification_list(notifs)
        self.assertEqual(result.count("notif-item"), 20)


class TestUptimeCalculation(unittest.TestCase):
    """Testes para cálculo de uptime"""

    def setUp(self):
        self.dashboard = DashboardV3()

    def test_empty_apis(self):
        """Sem APIs"""
        result = self.dashboard._calc_uptime_avg([])
        self.assertEqual(result, 0.0)

    def test_single_api(self):
        """Uma API"""
        apis = [{"uptime_percent": 99.5}]
        result = self.dashboard._calc_uptime_avg(apis)
        self.assertEqual(result, 99.5)

    def test_multiple_apis(self):
        """Múltiplas APIs"""
        apis = [
            {"uptime_percent": 100.0},
            {"uptime_percent": 99.0},
            {"uptime_percent": 98.0},
        ]
        result = self.dashboard._calc_uptime_avg(apis)
        self.assertAlmostEqual(result, 99.0, places=1)

    def test_missing_uptime(self):
        """Uptime ausente (default 0)"""
        apis = [{"name": "test"}]
        result = self.dashboard._calc_uptime_avg(apis)
        self.assertEqual(result, 0.0)


class TestTimeAgo(unittest.TestCase):
    """Testes para formatação de tempo"""

    def setUp(self):
        self.dashboard = DashboardV3()

    def test_seconds(self):
        """Segundos atrás"""
        ts = (datetime.now() - timedelta(seconds=30)).isoformat()
        result = self.dashboard._time_ago(ts)
        self.assertIn("30", result)

    def test_minutes(self):
        """Minutos atrás"""
        ts = (datetime.now() - timedelta(minutes=5)).isoformat()
        result = self.dashboard._time_ago(ts)
        self.assertIn("5min", result)

    def test_hours(self):
        """Horas atrás"""
        ts = (datetime.now() - timedelta(hours=3)).isoformat()
        result = self.dashboard._time_ago(ts)
        self.assertIn("3h", result)

    def test_days(self):
        """Dias atrás"""
        ts = (datetime.now() - timedelta(days=2)).isoformat()
        result = self.dashboard._time_ago(ts)
        self.assertIn("2d", result)

    def test_invalid_timestamp(self):
        """Timestamp inválido"""
        result = self.dashboard._time_ago("invalid")
        self.assertEqual(result, "agora")


class TestCreateDashboard(unittest.TestCase):
    """Testes para factory function"""

    def test_create_default(self):
        """Criação com padrão"""
        dashboard = create_dashboard()
        self.assertIsInstance(dashboard, DashboardV3)
        self.assertEqual(dashboard.config.title, "Mengão Monitor")

    def test_create_custom(self):
        """Criação com config customizada"""
        config = DashboardConfig(title="Custom")
        dashboard = create_dashboard(config)
        self.assertEqual(dashboard.config.title, "Custom")


class TestIntegration(unittest.TestCase):
    """Testes de integração"""

    def test_full_render(self):
        """Render completo com todos os dados"""
        dashboard = DashboardV3()
        
        apis = [
            {"name": "Prod API", "status": "online", "uptime_percent": 99.99, "response_time_ms": 45},
            {"name": "Staging API", "status": "online", "uptime_percent": 99.5, "response_time_ms": 120},
            {"name": "Legacy API", "status": "offline", "uptime_percent": 85.0, "response_time_ms": 0},
        ]
        
        alerts = [
            {"level": "L1", "endpoint": "Legacy API", "reason": "connection refused", "status": "active", "created_at": datetime.now().isoformat()},
        ]
        
        notifications = [
            {"title": "Alert", "message": "Legacy API is down", "timestamp": datetime.now().isoformat()},
        ]
        
        system_metrics = {"cpu": 25.5, "memory": 45.2, "disk": 51.0}
        websocket_status = {"connections_active": 2}
        
        html = dashboard.render_html(
            apis=apis,
            alerts=alerts,
            notifications=notifications,
            system_metrics=system_metrics,
            websocket_status=websocket_status
        )
        
        # Verificações
        self.assertIn("Mengão Monitor", html)
        self.assertIn("Prod API", html)
        self.assertIn("Legacy API", html)
        self.assertIn("2/3 online", html)
        self.assertIn("L1", html)
        self.assertIn("connection refused", html)
        self.assertIn("2 clientes conectados", html)
        self.assertIn("chart.js", html.lower())
        
        # Stats
        stats = dashboard.get_stats()
        self.assertEqual(stats["renders"], 1)

    def test_multiple_renders(self):
        """Múltiplos renders"""
        dashboard = DashboardV3()
        
        for i in range(5):
            dashboard.render_html()
        
        stats = dashboard.get_stats()
        self.assertEqual(stats["renders"], 5)


if __name__ == "__main__":
    unittest.main()
