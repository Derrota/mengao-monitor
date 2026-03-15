"""
Testes para Data Layer - Persistência unificada 🦞
"""

import unittest
import os
import json
import tempfile
import time
from datetime import datetime, timedelta
from data_layer import DataLayer, QueryFilter, DataType, DataLayerStats


class TestDataLayerInit(unittest.TestCase):
    """Testes de inicialização."""
    
    def test_memory_db(self):
        """Testa banco em memória."""
        dl = DataLayer(db_path=":memory:")
        stats = dl.get_stats()
        self.assertIsInstance(stats, DataLayerStats)
        dl.close()
    
    def test_file_db(self):
        """Testa banco em arquivo."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            dl = DataLayer(db_path=db_path)
            self.assertTrue(os.path.exists(db_path))
            dl.close()
        finally:
            os.unlink(db_path)
    
    def test_schema_created(self):
        """Testa se schema foi criado."""
        dl = DataLayer(db_path=":memory:")
        conn = dl._get_conn()
        
        # Verifica tabelas
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row['name'] for row in cursor.fetchall()}
        
        expected = {'schema_version', 'health_checks', 'alerts', 'metrics', 
                   'incidents', 'system_state'}
        self.assertTrue(expected.issubset(tables))
        dl.close()


class TestHealthChecks(unittest.TestCase):
    """Testes de health checks."""
    
    def setUp(self):
        self.dl = DataLayer(db_path=":memory:")
    
    def tearDown(self):
        self.dl.close()
    
    def test_record_check(self):
        """Testa registro de check."""
        check_id = self.dl.record_check(
            api_name="test_api",
            url="https://example.com",
            status="up",
            response_time_ms=150.5,
            status_code=200
        )
        self.assertIsInstance(check_id, int)
        self.assertGreater(check_id, 0)
    
    def test_record_check_with_metadata(self):
        """Testa check com metadata."""
        check_id = self.dl.record_check(
            api_name="test_api",
            url="https://example.com",
            status="up",
            metadata={"region": "us-east", "version": "1.0"}
        )
        
        checks = self.dl.get_checks()
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]['metadata']['region'], "us-east")
    
    def test_get_checks_filter_api(self):
        """Testa filtro por API."""
        self.dl.record_check("api1", "https://api1.com", "up")
        self.dl.record_check("api2", "https://api2.com", "up")
        self.dl.record_check("api1", "https://api1.com", "down")
        
        checks = self.dl.get_checks(QueryFilter(api_name="api1"))
        self.assertEqual(len(checks), 2)
    
    def test_get_checks_filter_status(self):
        """Testa filtro por status."""
        self.dl.record_check("api1", "https://api1.com", "up")
        self.dl.record_check("api1", "https://api1.com", "down")
        self.dl.record_check("api1", "https://api1.com", "up")
        
        checks = self.dl.get_checks(QueryFilter(status="up"))
        self.assertEqual(len(checks), 2)
    
    def test_get_checks_limit_offset(self):
        """Testa paginação."""
        for i in range(10):
            self.dl.record_check("api", f"https://api{i}.com", "up")
        
        page1 = self.dl.get_checks(QueryFilter(limit=5, offset=0))
        page2 = self.dl.get_checks(QueryFilter(limit=5, offset=5))
        
        self.assertEqual(len(page1), 5)
        self.assertEqual(len(page2), 5)
        self.assertNotEqual(page1[0]['id'], page2[0]['id'])
    
    def test_get_uptime_100(self):
        """Testa uptime 100%."""
        for _ in range(10):
            self.dl.record_check("api", "https://api.com", "up")
        
        uptime = self.dl.get_uptime("api", hours=24)
        self.assertEqual(uptime, 100.0)
    
    def test_get_uptime_50(self):
        """Testa uptime 50%."""
        for i in range(10):
            status = "up" if i % 2 == 0 else "down"
            self.dl.record_check("api", "https://api.com", status)
        
        uptime = self.dl.get_uptime("api", hours=24)
        self.assertEqual(uptime, 50.0)
    
    def test_get_uptime_no_data(self):
        """Testa uptime sem dados."""
        uptime = self.dl.get_uptime("nonexistent", hours=24)
        self.assertEqual(uptime, 100.0)  # Assume OK sem dados
    
    def test_get_avg_response_time(self):
        """Testa tempo médio de resposta."""
        self.dl.record_check("api", "https://api.com", "up", response_time_ms=100)
        self.dl.record_check("api", "https://api.com", "up", response_time_ms=200)
        self.dl.record_check("api", "https://api.com", "up", response_time_ms=300)
        
        avg = self.dl.get_avg_response_time("api", hours=24)
        self.assertEqual(avg, 200.0)
    
    def test_get_percentile_response_time(self):
        """Testa percentil de tempo de resposta."""
        for i in range(100):
            self.dl.record_check("api", "https://api.com", "up", 
                                response_time_ms=float(i * 10))
        
        p95 = self.dl.get_percentile_response_time("api", percentile=95, hours=24)
        p50 = self.dl.get_percentile_response_time("api", percentile=50, hours=24)
        
        self.assertIsNotNone(p95)
        self.assertIsNotNone(p50)
        self.assertGreater(p95, p50)


class TestAlerts(unittest.TestCase):
    """Testes de alertas."""
    
    def setUp(self):
        self.dl = DataLayer(db_path=":memory:")
    
    def tearDown(self):
        self.dl.close()
    
    def test_record_alert(self):
        """Testa registro de alerta."""
        alert_id = self.dl.record_alert(
            alert_id="alert_001",
            api_name="test_api",
            level="L1",
            message="API is down"
        )
        self.assertIsInstance(alert_id, int)
    
    def test_update_alert_status(self):
        """Testa atualização de status."""
        self.dl.record_alert("alert_001", "api", "L1", "Down")
        
        result = self.dl.update_alert_status("alert_001", "acknowledged")
        self.assertTrue(result)
        
        alerts = self.dl.get_alerts(status="acknowledged")
        self.assertEqual(len(alerts), 1)
        self.assertIsNotNone(alerts[0]['acknowledged_at'])
    
    def test_escalate_alert(self):
        """Testa escalação de alerta."""
        self.dl.record_alert("alert_001", "api", "L1", "Down")
        
        result = self.dl.escalate_alert("alert_001", "L2")
        self.assertTrue(result)
        
        alerts = self.dl.get_alerts()
        self.assertEqual(alerts[0]['level'], "L2")
        self.assertEqual(alerts[0]['escalation_count'], 1)
    
    def test_get_alerts_by_api(self):
        """Testa busca por API."""
        self.dl.record_alert("a1", "api1", "L1", "Down")
        self.dl.record_alert("a2", "api2", "L1", "Down")
        self.dl.record_alert("a3", "api1", "L2", "Still down")
        
        alerts = self.dl.get_alerts(api_name="api1")
        self.assertEqual(len(alerts), 2)
    
    def test_alert_with_details(self):
        """Testa alerta com detalhes."""
        self.dl.record_alert(
            "alert_001", "api", "L1", "Down",
            details={"error": "Connection refused", "attempts": 3}
        )
        
        alerts = self.dl.get_alerts()
        self.assertEqual(alerts[0]['details']['error'], "Connection refused")


class TestMetrics(unittest.TestCase):
    """Testes de métricas."""
    
    def setUp(self):
        self.dl = DataLayer(db_path=":memory:")
    
    def tearDown(self):
        self.dl.close()
    
    def test_record_metric(self):
        """Testa registro de métrica."""
        metric_id = self.dl.record_metric(
            metric_name="response_time",
            metric_value=150.5,
            labels={"endpoint": "/api/users"}
        )
        self.assertIsInstance(metric_id, int)
    
    def test_get_metrics(self):
        """Testa busca de métricas."""
        for i in range(10):
            self.dl.record_metric("cpu_usage", float(i * 10))
        
        metrics = self.dl.get_metrics("cpu_usage")
        self.assertEqual(len(metrics), 10)
    
    def test_get_metric_aggregate_avg(self):
        """Testa agregação AVG."""
        self.dl.record_metric("response_time", 100.0)
        self.dl.record_metric("response_time", 200.0)
        self.dl.record_metric("response_time", 300.0)
        
        avg = self.dl.get_metric_aggregate("response_time", "avg")
        self.assertEqual(avg, 200.0)
    
    def test_get_metric_aggregate_sum(self):
        """Testa agregação SUM."""
        self.dl.record_metric("requests", 10.0)
        self.dl.record_metric("requests", 20.0)
        
        total = self.dl.get_metric_aggregate("requests", "sum")
        self.assertEqual(total, 30.0)
    
    def test_get_metric_aggregate_min_max(self):
        """Testa agregação MIN/MAX."""
        self.dl.record_metric("value", 10.0)
        self.dl.record_metric("value", 50.0)
        self.dl.record_metric("value", 30.0)
        
        self.assertEqual(self.dl.get_metric_aggregate("value", "min"), 10.0)
        self.assertEqual(self.dl.get_metric_aggregate("value", "max"), 50.0)


class TestIncidents(unittest.TestCase):
    """Testes de incidentes."""
    
    def setUp(self):
        self.dl = DataLayer(db_path=":memory:")
    
    def tearDown(self):
        self.dl.close()
    
    def test_record_incident(self):
        """Testa registro de incidente."""
        inc_id = self.dl.record_incident(
            incident_id="inc_001",
            api_name="test_api",
            severity="high",
            title="API Outage"
        )
        self.assertIsInstance(inc_id, int)
    
    def test_resolve_incident(self):
        """Testa resolução de incidente."""
        self.dl.record_incident("inc_001", "api", "high", "Outage")
        time.sleep(0.1)  # Pequeno delay para MTTR
        
        result = self.dl.resolve_incident(
            "inc_001",
            resolution="Fixed by restarting",
            root_cause="Memory leak"
        )
        self.assertTrue(result)
        
        incidents = self.dl.get_incidents(status="resolved")
        self.assertEqual(len(incidents), 1)
        self.assertIsNotNone(incidents[0]['mttr_seconds'])
        self.assertEqual(incidents[0]['root_cause'], "Memory leak")
    
    def test_get_mttr(self):
        """Testa cálculo de MTTR."""
        # Cria e resolve alguns incidentes
        for i in range(3):
            self.dl.record_incident(f"inc_{i}", "api", "medium", f"Incident {i}")
            time.sleep(0.05)
            self.dl.resolve_incident(f"inc_{i}", "Fixed")
        
        mttr = self.dl.get_mttr()
        self.assertIsNotNone(mttr)
        self.assertGreater(mttr, 0)
    
    def test_get_incidents_by_api(self):
        """Testa busca por API."""
        self.dl.record_incident("i1", "api1", "high", "Outage")
        self.dl.record_incident("i2", "api2", "low", "Slow")
        self.dl.record_incident("i3", "api1", "medium", "Errors")
        
        incidents = self.dl.get_incidents(api_name="api1")
        self.assertEqual(len(incidents), 2)


class TestSystemState(unittest.TestCase):
    """Testes de system state."""
    
    def setUp(self):
        self.dl = DataLayer(db_path=":memory:")
    
    def tearDown(self):
        self.dl.close()
    
    def test_set_get_string(self):
        """Testa string."""
        self.dl.set_state("app_name", "Mengão Monitor")
        value = self.dl.get_state("app_name")
        self.assertEqual(value, "Mengão Monitor")
    
    def test_set_get_int(self):
        """Testa int."""
        self.dl.set_state("port", 8080)
        value = self.dl.get_state("port")
        self.assertEqual(value, 8080)
        self.assertIsInstance(value, int)
    
    def test_set_get_float(self):
        """Testa float."""
        self.dl.set_state("threshold", 0.95)
        value = self.dl.get_state("threshold")
        self.assertEqual(value, 0.95)
        self.assertIsInstance(value, float)
    
    def test_set_get_bool(self):
        """Testa bool."""
        self.dl.set_state("enabled", True)
        value = self.dl.get_state("enabled")
        self.assertEqual(value, True)
        self.assertIsInstance(value, bool)
    
    def test_set_get_json(self):
        """Testa JSON."""
        config = {"apis": ["api1", "api2"], "interval": 60}
        self.dl.set_state("config", config)
        value = self.dl.get_state("config")
        self.assertEqual(value, config)
    
    def test_get_default(self):
        """Testa valor default."""
        value = self.dl.get_state("nonexistent", "default")
        self.assertEqual(value, "default")
    
    def test_delete_state(self):
        """Testa deleção."""
        self.dl.set_state("key", "value")
        result = self.dl.delete_state("key")
        self.assertTrue(result)
        
        value = self.dl.get_state("key")
        self.assertIsNone(value)


class TestMaintenance(unittest.TestCase):
    """Testes de manutenção."""
    
    def setUp(self):
        self.dl = DataLayer(db_path=":memory:")
    
    def tearDown(self):
        self.dl.close()
    
    def test_cleanup_old_data(self):
        """Testa limpeza de dados antigos."""
        # Dados "antigos" (timestamp manual)
        old_time = (datetime.now() - timedelta(days=31)).isoformat()
        self.dl.record_check("api", "https://api.com", "up", timestamp=old_time)
        
        # Dados recentes
        self.dl.record_check("api", "https://api.com", "up")
        
        self.dl.cleanup_old_data(days=30)
        
        checks = self.dl.get_checks()
        self.assertEqual(len(checks), 1)  # Só o recente
    
    def test_get_stats(self):
        """Testa estatísticas."""
        self.dl.record_check("api", "https://api.com", "up")
        self.dl.record_alert("a1", "api", "L1", "Down")
        self.dl.record_metric("cpu", 50.0)
        self.dl.record_incident("i1", "api", "low", "Issue")
        
        stats = self.dl.get_stats()
        self.assertEqual(stats.total_checks, 1)
        self.assertEqual(stats.total_alerts, 1)
        self.assertEqual(stats.total_metrics, 1)
        self.assertEqual(stats.total_incidents, 1)
    
    def test_backup(self):
        """Testa backup."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            backup_path = f.name
        
        try:
            dl = DataLayer(db_path=db_path)
            dl.record_check("api", "https://api.com", "up")
            
            result = dl.backup(backup_path)
            self.assertTrue(result)
            self.assertTrue(os.path.exists(backup_path))
            
            dl.close()
        finally:
            os.unlink(db_path)
            if os.path.exists(backup_path):
                os.unlink(backup_path)


class TestThreadSafety(unittest.TestCase):
    """Testes de thread safety."""
    
    def test_concurrent_writes(self):
        """Testa escritas concorrentes."""
        import threading
        import tempfile
        import os
        
        # Usa banco em arquivo para compartilhar entre threads
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            dl = DataLayer(db_path=db_path)
            errors = []
            
            def write_checks(thread_id):
                try:
                    # Cria própria instância para esta thread
                    thread_dl = DataLayer(db_path=db_path)
                    for i in range(100):
                        thread_dl.record_check(f"api_{thread_id}", f"https://api{thread_id}.com", "up")
                    thread_dl.close()
                except Exception as e:
                    errors.append(e)
            
            threads = []
            for i in range(5):
                t = threading.Thread(target=write_checks, args=(i,))
                threads.append(t)
                t.start()
            
            for t in threads:
                t.join()
            
            self.assertEqual(len(errors), 0)
            
            stats = dl.get_stats()
            self.assertEqual(stats.total_checks, 500)
            
            dl.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


if __name__ == '__main__':
    unittest.main()
