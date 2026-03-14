"""
Testes para SLA Reporter v2.9
"""

import unittest
import json
from datetime import datetime, timedelta
from sla_reporter import SLAReporter, SLAMetrics, Incident


class TestSLAMetrics(unittest.TestCase):
    """Testes para SLAMetrics dataclass."""
    
    def test_default_values(self):
        """Valores padrão corretos."""
        metrics = SLAMetrics(
            endpoint_name="test",
            period_start="2026-03-14T00:00:00Z",
            period_end="2026-03-14T23:59:59Z"
        )
        self.assertEqual(metrics.endpoint_name, "test")
        self.assertEqual(metrics.uptime_percent, 100.0)
        self.assertEqual(metrics.total_checks, 0)
        self.assertTrue(metrics.sla_compliant)
        self.assertEqual(metrics.sla_target_percent, 99.9)


class TestIncident(unittest.TestCase):
    """Testes para Incident dataclass."""
    
    def test_incident_creation(self):
        """Criação de incidente."""
        incident = Incident(
            endpoint_name="api",
            start_time="2026-03-14T10:00:00Z",
            reason="timeout"
        )
        self.assertEqual(incident.endpoint_name, "api")
        self.assertFalse(incident.resolved)
        self.assertIsNone(incident.end_time)
    
    def test_incident_resolved(self):
        """Incidente resolvido."""
        incident = Incident(
            endpoint_name="api",
            start_time="2026-03-14T10:00:00Z",
            end_time="2026-03-14T10:05:00Z",
            duration_seconds=300,
            resolved=True
        )
        self.assertTrue(incident.resolved)
        self.assertEqual(incident.duration_seconds, 300)


class TestSLAReporter(unittest.TestCase):
    """Testes para SLAReporter."""
    
    def setUp(self):
        self.reporter = SLAReporter()
    
    def test_initialization(self):
        """Inicialização correta."""
        stats = self.reporter.get_stats()
        self.assertEqual(stats["endpoints_tracked"], 0)
        self.assertEqual(stats["total_incidents"], 0)
        self.assertEqual(stats["default_sla_target"], 99.9)
    
    def test_set_sla_target(self):
        """Definir target de SLA."""
        self.reporter.set_sla_target("api_prod", 99.99)
        self.assertEqual(self.reporter.get_sla_target("api_prod"), 99.99)
        self.assertEqual(self.reporter.get_sla_target("unknown"), 99.9)
    
    def test_record_incident(self):
        """Registrar incidente."""
        incident = self.reporter.record_incident("api", "connection refused")
        self.assertEqual(incident.endpoint_name, "api")
        self.assertEqual(incident.reason, "connection refused")
        self.assertFalse(incident.resolved)
        
        stats = self.reporter.get_stats()
        self.assertEqual(stats["total_incidents"], 1)
        self.assertEqual(stats["open_incidents"], 1)
    
    def test_resolve_incident(self):
        """Resolver incidente."""
        self.reporter.record_incident("api", "timeout")
        resolved = self.reporter.resolve_incident("api")
        
        self.assertIsNotNone(resolved)
        self.assertTrue(resolved.resolved)
        self.assertIsNotNone(resolved.end_time)
        self.assertGreater(resolved.duration_seconds, 0)
        
        stats = self.reporter.get_stats()
        self.assertEqual(stats["open_incidents"], 0)
        self.assertEqual(stats["resolved_incidents"], 1)
    
    def test_resolve_no_incident(self):
        """Resolver quando não há incidentes abertos."""
        result = self.reporter.resolve_incident("api")
        self.assertIsNone(result)
    
    def test_get_open_incidents(self):
        """Obter incidentes abertos."""
        self.reporter.record_incident("api1", "error1")
        self.reporter.record_incident("api2", "error2")
        self.reporter.record_incident("api1", "error3")
        
        # Todos abertos
        open_all = self.reporter.get_open_incidents()
        self.assertEqual(len(open_all), 3)
        
        # Filtrar por endpoint
        open_api1 = self.reporter.get_open_incidents("api1")
        self.assertEqual(len(open_api1), 2)
        
        # Resolver um
        self.reporter.resolve_incident("api1")
        open_api1_after = self.reporter.get_open_incidents("api1")
        self.assertEqual(len(open_api1_after), 1)
    
    def test_generate_report_no_data(self):
        """Gerar relatório sem dados."""
        report = self.reporter.generate_report("api", period_hours=24)
        
        self.assertEqual(report.endpoint_name, "api")
        self.assertEqual(report.total_checks, 0)
        self.assertEqual(report.uptime_percent, 100.0)
        self.assertTrue(report.sla_compliant)
    
    def test_generate_report_with_data(self):
        """Gerar relatório com dados."""
        checks_data = [
            {"status": "success", "response_time_ms": 100, "timestamp": "2026-03-14T10:00:00Z"},
            {"status": "success", "response_time_ms": 150, "timestamp": "2026-03-14T10:01:00Z"},
            {"status": "failure", "response_time_ms": 5000, "timestamp": "2026-03-14T10:02:00Z"},
            {"status": "success", "response_time_ms": 120, "timestamp": "2026-03-14T10:03:00Z"},
            {"status": "success", "response_time_ms": 110, "timestamp": "2026-03-14T10:04:00Z"},
        ]
        
        report = self.reporter.generate_report("api", period_hours=24, checks_data=checks_data)
        
        self.assertEqual(report.total_checks, 5)
        self.assertEqual(report.successful_checks, 4)
        self.assertEqual(report.failed_checks, 1)
        self.assertEqual(report.uptime_percent, 80.0)
        self.assertFalse(report.sla_compliant)  # 80% < 99.9%
        
        # Response times
        self.assertAlmostEqual(report.avg_response_time_ms, 1096.0, places=0)
        self.assertEqual(report.max_response_time_ms, 5000)
        self.assertEqual(report.min_response_time_ms, 100)
    
    def test_generate_report_with_up_field(self):
        """Gerar relatório usando campo 'up' em vez de 'status'."""
        checks_data = [
            {"up": True, "response_time": 100},
            {"up": True, "response_time": 150},
            {"up": False, "response_time": 0},
        ]
        
        report = self.reporter.generate_report("api", period_hours=24, checks_data=checks_data)
        
        self.assertEqual(report.total_checks, 3)
        self.assertEqual(report.successful_checks, 2)
        self.assertEqual(report.failed_checks, 1)
    
    def test_generate_report_with_incidents(self):
        """Gerar relatório com incidentes registrados."""
        # Registrar incidentes
        inc1 = self.reporter.record_incident("api", "timeout")
        inc1.resolved = True
        inc1.duration_seconds = 300
        
        inc2 = self.reporter.record_incident("api", "500 error")
        inc2.resolved = True
        inc2.duration_seconds = 600
        
        checks_data = [
            {"status": "success", "response_time_ms": 100},
            {"status": "failure", "response_time_ms": 5000},
            {"status": "success", "response_time_ms": 120},
        ]
        
        report = self.reporter.generate_report("api", period_hours=24, checks_data=checks_data)
        
        self.assertEqual(report.incidents, 2)
        self.assertEqual(report.total_downtime_seconds, 900)
        self.assertEqual(report.mttr_seconds, 450)  # (300 + 600) / 2
    
    def test_generate_multi_endpoint_report(self):
        """Gerar relatório para múltiplos endpoints."""
        checks_api1 = [
            {"status": "success", "response_time_ms": 100},
            {"status": "success", "response_time_ms": 150},
        ]
        checks_api2 = [
            {"status": "success", "response_time_ms": 200},
            {"status": "failure", "response_time_ms": 0},
        ]
        
        # Simular dados (em produção viria do history_db)
        reports = {}
        reports["api1"] = self.reporter.generate_report("api1", checks_data=checks_api1)
        reports["api2"] = self.reporter.generate_report("api2", checks_data=checks_api2)
        
        self.assertEqual(reports["api1"].uptime_percent, 100.0)
        self.assertEqual(reports["api2"].uptime_percent, 50.0)
    
    def test_export_json(self):
        """Exportar relatório como JSON."""
        checks_data = [
            {"status": "success", "response_time_ms": 100},
            {"status": "success", "response_time_ms": 150},
        ]
        
        report = self.reporter.generate_report("api", checks_data=checks_data)
        json_str = self.reporter.export_json(report)
        
        data = json.loads(json_str)
        self.assertEqual(data["endpoint_name"], "api")
        self.assertEqual(data["total_checks"], 2)
        self.assertIn("uptime_percent", data)
        self.assertIn("avg_response_time_ms", data)
    
    def test_export_csv(self):
        """Exportar relatório como CSV."""
        checks_data = [
            {"status": "success", "response_time_ms": 100},
        ]
        
        report = self.reporter.generate_report("api", checks_data=checks_data)
        csv_str = self.reporter.export_csv(report)
        
        self.assertIn("Metric,Value", csv_str)
        self.assertIn("endpoint_name,api", csv_str)
        self.assertIn("total_checks,1", csv_str)
    
    def test_export_html(self):
        """Exportar relatório como HTML."""
        checks_data = [
            {"status": "success", "response_time_ms": 100},
            {"status": "failure", "response_time_ms": 5000},
        ]
        
        report = self.reporter.generate_report("api", checks_data=checks_data)
        html = self.reporter.export_html(report)
        
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("SLA Report: api", html)
        self.assertIn("BREACH", html)  # 50% < 99.9%
        self.assertIn("50.00%", html)
    
    def test_export_html_compliant(self):
        """Exportar HTML quando SLA está compliant."""
        checks_data = [
            {"status": "success", "response_time_ms": 100},
            {"status": "success", "response_time_ms": 150},
        ]
        
        report = self.reporter.generate_report("api", checks_data=checks_data)
        html = self.reporter.export_html(report)
        
        self.assertIn("COMPLIANT", html)
        self.assertIn("100.00%", html)
    
    def test_sla_breach_count(self):
        """Contagem de breaches de SLA."""
        # Checks em horas diferentes
        checks_data = [
            {"status": "success", "response_time_ms": 100, "timestamp": "2026-03-14T10:00:00Z"},
            {"status": "success", "response_time_ms": 100, "timestamp": "2026-03-14T10:30:00Z"},
            {"status": "failure", "response_time_ms": 0, "timestamp": "2026-03-14T11:00:00Z"},
            {"status": "failure", "response_time_ms": 0, "timestamp": "2026-03-14T11:30:00Z"},
            {"status": "success", "response_time_ms": 100, "timestamp": "2026-03-14T12:00:00Z"},
        ]
        
        report = self.reporter.generate_report("api", checks_data=checks_data)
        
        # Hora 10: 100% (compliant)
        # Hora 11: 0% (breach)
        # Hora 12: 100% (compliant)
        self.assertEqual(report.sla_breach_count, 1)
    
    def test_thread_safety(self):
        """Teste básico de thread safety."""
        import threading
        
        errors = []
        
        def record_and_resolve():
            try:
                for i in range(100):
                    self.reporter.record_incident(f"api_{i % 5}", f"error_{i}")
                    self.reporter.resolve_incident(f"api_{i % 5}")
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=record_and_resolve) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        self.assertEqual(len(errors), 0)
        stats = self.reporter.get_stats()
        self.assertEqual(stats["total_incidents"], 500)


class TestSLAReporterEdgeCases(unittest.TestCase):
    """Testes de edge cases."""
    
    def setUp(self):
        self.reporter = SLAReporter()
    
    def test_empty_checks_data(self):
        """Dados vazios."""
        report = self.reporter.generate_report("api", checks_data=[])
        self.assertEqual(report.total_checks, 0)
        self.assertEqual(report.uptime_percent, 100.0)
    
    def test_all_failures(self):
        """Todos os checks falharam."""
        checks_data = [
            {"status": "failure", "response_time_ms": 0},
            {"status": "failure", "response_time_ms": 0},
            {"status": "failure", "response_time_ms": 0},
        ]
        
        report = self.reporter.generate_report("api", checks_data=checks_data)
        self.assertEqual(report.uptime_percent, 0.0)
        self.assertFalse(report.sla_compliant)
    
    def test_all_success(self):
        """Todos os checks sucesso."""
        checks_data = [
            {"status": "success", "response_time_ms": 100},
            {"status": "success", "response_time_ms": 150},
            {"status": "success", "response_time_ms": 200},
        ]
        
        report = self.reporter.generate_report("api", checks_data=checks_data)
        self.assertEqual(report.uptime_percent, 100.0)
        self.assertTrue(report.sla_compliant)
    
    def test_no_response_times(self):
        """Checks sem response time."""
        checks_data = [
            {"status": "success"},
            {"status": "success"},
        ]
        
        report = self.reporter.generate_report("api", checks_data=checks_data)
        self.assertEqual(report.avg_response_time_ms, 0)
        self.assertEqual(report.max_response_time_ms, 0)
        self.assertEqual(report.min_response_time_ms, 0)
    
    def test_custom_sla_target(self):
        """Target de SLA customizado."""
        self.reporter.set_sla_target("api", 95.0)
        
        checks_data = [
            {"status": "success", "response_time_ms": 100},
            {"status": "success", "response_time_ms": 100},
            {"status": "failure", "response_time_ms": 0},
        ]
        
        report = self.reporter.generate_report("api", checks_data=checks_data)
        # 66.67% < 95% = breach
        self.assertFalse(report.sla_compliant)
        self.assertEqual(report.sla_target_percent, 95.0)


if __name__ == "__main__":
    unittest.main()
