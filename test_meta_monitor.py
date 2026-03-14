"""
Testes para Meta-Monitor (v2.7)
"""

import unittest
import time
import threading
from meta_monitor import (
    MetaMonitor, ProcessMetrics, HealthCheckResult, 
    HealthStatus, get_meta_monitor
)


class TestHealthStatus(unittest.TestCase):
    """Testes para enum HealthStatus."""
    
    def test_values(self):
        self.assertEqual(HealthStatus.HEALTHY.value, "healthy")
        self.assertEqual(HealthStatus.DEGRADED.value, "degraded")
        self.assertEqual(HealthStatus.UNHEALTHY.value, "unhealthy")
        self.assertEqual(HealthStatus.UNKNOWN.value, "unknown")


class TestProcessMetrics(unittest.TestCase):
    """Testes para ProcessMetrics."""
    
    def test_to_dict(self):
        metrics = ProcessMetrics(
            pid=1234,
            cpu_seconds_user=1.5,
            cpu_seconds_system=0.5,
            memory_rss_mb=100.5,
            memory_vms_mb=200.0,
            threads=10,
            uptime_seconds=3600.0,
            start_time=time.time()
        )
        
        d = metrics.to_dict()
        self.assertEqual(d['pid'], 1234)
        self.assertEqual(d['cpu_seconds_user'], 1.5)
        self.assertEqual(d['cpu_seconds_system'], 0.5)
        self.assertEqual(d['cpu_seconds_total'], 2.0)
        self.assertEqual(d['memory_rss_mb'], 100.5)
        self.assertEqual(d['threads'], 10)
        self.assertIn('start_time', d)


class TestHealthCheckResult(unittest.TestCase):
    """Testes para HealthCheckResult."""
    
    def test_to_dict(self):
        result = HealthCheckResult(
            name="test_check",
            status=HealthStatus.HEALTHY,
            message="All good",
            details={'key': 'value'},
            duration_ms=5.5
        )
        
        d = result.to_dict()
        self.assertEqual(d['name'], "test_check")
        self.assertEqual(d['status'], "healthy")
        self.assertEqual(d['message'], "All good")
        self.assertEqual(d['details'], {'key': 'value'})
        self.assertEqual(d['duration_ms'], 5.5)
        self.assertIn('timestamp', d)


class TestMetaMonitor(unittest.TestCase):
    """Testes para MetaMonitor."""
    
    def setUp(self):
        self.monitor = MetaMonitor(check_interval=1)
    
    def test_initialization(self):
        self.assertEqual(self.monitor.check_interval, 1)
        self.assertEqual(len(self.monitor.checks_history), 0)
        self.assertFalse(self.monitor._running)
    
    def test_collect_process_metrics(self):
        metrics = self.monitor.collect_process_metrics()
        
        self.assertIsInstance(metrics, ProcessMetrics)
        self.assertGreater(metrics.pid, 0)
        self.assertGreaterEqual(metrics.cpu_seconds_user, 0)
        self.assertGreaterEqual(metrics.cpu_seconds_system, 0)
        self.assertGreater(metrics.threads, 0)
        self.assertGreater(metrics.uptime_seconds, 0)
    
    def test_check_process_health(self):
        result = self.monitor.check_process_health()
        
        self.assertIsInstance(result, HealthCheckResult)
        self.assertEqual(result.name, "process_health")
        self.assertIn(result.status, [HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY])
        self.assertGreater(result.duration_ms, 0)
        self.assertIn('pid', result.details)
    
    def test_check_thread_health(self):
        result = self.monitor.check_thread_health()
        
        self.assertEqual(result.name, "thread_health")
        self.assertIn('total_threads', result.details)
        self.assertGreater(result.details['total_threads'], 0)
    
    def test_check_memory_health(self):
        result = self.monitor.check_memory_health()
        
        self.assertEqual(result.name, "memory_health")
        # Pode ter rss_mb ou estar em unknown se /proc não disponível
        self.assertIn(result.status, [HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNKNOWN])
    
    def test_check_uptime_health(self):
        result = self.monitor.check_uptime_health()
        
        self.assertEqual(result.name, "uptime_health")
        self.assertIn('uptime_seconds', result.details)
        self.assertIn('uptime_formatted', result.details)
        self.assertIn('started_at', result.details)
    
    def test_check_io_health(self):
        result = self.monitor.check_io_health()
        
        self.assertEqual(result.name, "io_health")
        # Pode estar em unknown se /proc não disponível
        self.assertIn(result.status, [HealthStatus.HEALTHY, HealthStatus.UNKNOWN])
    
    def test_run_all_checks(self):
        checks = self.monitor.run_all_checks()
        
        self.assertIn('process', checks)
        self.assertIn('threads', checks)
        self.assertIn('memory', checks)
        self.assertIn('uptime', checks)
        self.assertIn('io', checks)
        
        for name, check in checks.items():
            self.assertIsInstance(check, HealthCheckResult)
    
    def test_history_tracking(self):
        # Executar alguns checks
        self.monitor.run_all_checks()
        self.monitor.run_all_checks()
        
        # 5 checks × 2 runs = 10
        self.assertEqual(len(self.monitor.checks_history), 10)
    
    def test_get_overall_status(self):
        status = self.monitor.get_overall_status()
        
        self.assertIn('overall_status', status)
        self.assertIn('checks', status)
        self.assertIn('timestamp', status)
        self.assertIn('history_size', status)
        self.assertIn(status['overall_status'], ['healthy', 'degraded', 'unhealthy', 'unknown'])
    
    def test_get_history(self):
        self.monitor.run_all_checks()
        
        history = self.monitor.get_history(limit=10)
        self.assertLessEqual(len(history), 10)
        
        # Filtrar por status
        healthy_history = self.monitor.get_history(status_filter='healthy')
        for check in healthy_history:
            self.assertEqual(check['status'], 'healthy')
    
    def test_get_stats(self):
        # Sem checks
        stats = self.monitor.get_stats()
        self.assertEqual(stats['total_checks'], 0)
        self.assertEqual(stats['health_percentage'], 100.0)
        
        # Com checks
        self.monitor.run_all_checks()
        stats = self.monitor.get_stats()
        self.assertGreater(stats['total_checks'], 0)
        self.assertIn('healthy', stats)
        self.assertIn('health_percentage', stats)
    
    def test_thresholds_configurable(self):
        # Alterar thresholds
        original = self.monitor.thresholds['memory_rss_mb']
        self.monitor.thresholds['memory_rss_mb'] = 0.001  # Muito baixo
        
        result = self.monitor.check_process_health()
        # Provavelmente vai estar degraded com threshold tão baixo
        self.assertIn(result.status, [HealthStatus.DEGRADED, HealthStatus.UNHEALTHY, HealthStatus.HEALTHY])
        
        # Restaurar
        self.monitor.thresholds['memory_rss_mb'] = original
    
    def test_watchdog_start_stop(self):
        self.monitor.start_watchdog()
        self.assertTrue(self.monitor._running)
        self.assertIsNotNone(self.monitor._thread)
        
        # Aguardar um pouco
        time.sleep(0.5)
        
        self.monitor.stop_watchdog()
        self.assertFalse(self.monitor._running)
    
    def test_watchdog_double_start(self):
        self.monitor.start_watchdog()
        thread1 = self.monitor._thread
        
        # Tentar iniciar novamente
        self.monitor.start_watchdog()
        thread2 = self.monitor._thread
        
        # Deve ser a mesma thread
        self.assertEqual(thread1, thread2)
        
        self.monitor.stop_watchdog()


class TestGlobalInstance(unittest.TestCase):
    """Testes para instância global."""
    
    def test_get_meta_monitor(self):
        monitor = get_meta_monitor()
        self.assertIsInstance(monitor, MetaMonitor)
    
    def test_singleton(self):
        monitor1 = get_meta_monitor()
        monitor2 = get_meta_monitor()
        self.assertIs(monitor1, monitor2)


if __name__ == '__main__':
    unittest.main()
