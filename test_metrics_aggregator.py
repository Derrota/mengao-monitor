"""
Testes para Metrics Aggregator v3.9.
"""

import time
import threading
import unittest
from unittest.mock import MagicMock

from metrics_aggregator import (
    MetricsAggregator,
    AggregationWindow,
    AnomalyType,
    TrendDirection,
    MetricThreshold,
    MetricPoint,
    Anomaly,
    get_aggregator,
    reset_aggregator,
)


class TestMetricPoint(unittest.TestCase):
    """Testes para MetricPoint."""

    def test_creation(self):
        point = MetricPoint(name="cpu", value=75.5)
        self.assertEqual(point.name, "cpu")
        self.assertEqual(point.value, 75.5)
        self.assertIsInstance(point.timestamp, float)
        self.assertEqual(point.labels, {})

    def test_creation_with_labels(self):
        point = MetricPoint(name="http_requests", value=100, labels={"method": "GET", "status": "200"})
        self.assertEqual(point.labels["method"], "GET")

    def test_age(self):
        point = MetricPoint(name="test", value=1.0, timestamp=time.time() - 10)
        self.assertAlmostEqual(point.age(), 10, delta=1)


class TestMetricsAggregator(unittest.TestCase):
    """Testes para MetricsAggregator."""

    def setUp(self):
        self.agg = MetricsAggregator(max_points_per_metric=1000, anomaly_check_interval=1.0)

    def tearDown(self):
        self.agg.stop()

    def test_record_single_point(self):
        self.agg.record("cpu", 50.0)
        names = self.agg.get_metric_names()
        self.assertIn("cpu", names)

    def test_record_multiple_points(self):
        for i in range(10):
            self.agg.record("cpu", float(i * 10))
        self.assertEqual(len(self.agg._points["cpu"]), 10)

    def test_record_batch(self):
        metrics = [
            ("cpu", 50.0, None),
            ("memory", 80.0, None),
            ("disk", 60.0, None),
        ]
        self.agg.record_batch(metrics)
        names = self.agg.get_metric_names()
        self.assertIn("cpu", names)
        self.assertIn("memory", names)
        self.assertIn("disk", names)

    def test_max_points_limit(self):
        agg = MetricsAggregator(max_points_per_metric=5)
        for i in range(10):
            agg.record("test", float(i))
        self.assertEqual(len(agg._points["test"]), 5)
        # Deve manter os últimos 5
        values = [p.value for p in agg._points["test"]]
        self.assertEqual(values, [5.0, 6.0, 7.0, 8.0, 9.0])

    def test_aggregate_basic(self):
        for i in range(100):
            self.agg.record("response_time", float(i))
        agg = self.agg.aggregate("response_time", AggregationWindow.MINUTE_1)
        self.assertIsNotNone(agg)
        self.assertEqual(agg.count, 100)
        self.assertEqual(agg.min_val, 0.0)
        self.assertEqual(agg.max_val, 99.0)
        self.assertAlmostEqual(agg.mean, 49.5, delta=0.1)

    def test_aggregate_empty(self):
        agg = self.agg.aggregate("nonexistent", AggregationWindow.MINUTE_1)
        self.assertIsNone(agg)

    def test_aggregate_all_windows(self):
        for i in range(50):
            self.agg.record("test", float(i))
        result = self.agg.aggregate_all_windows("test")
        self.assertIn("MINUTE_1", result)
        self.assertIn("HOUR_1", result)

    def test_aggregate_to_dict(self):
        for i in range(20):
            self.agg.record("test", float(i))
        agg = self.agg.aggregate("test", AggregationWindow.MINUTE_1)
        d = agg.to_dict()
        self.assertEqual(d["name"], "test")
        self.assertEqual(d["count"], 20)
        self.assertIn("mean", d)
        self.assertIn("p95", d)
        self.assertIn("p99", d)

    def test_aggregate_percentiles(self):
        # 100 valores de 0 a 99
        for i in range(100):
            self.agg.record("test", float(i))
        agg = self.agg.aggregate("test", AggregationWindow.MINUTE_1)
        self.assertAlmostEqual(agg.p95, 95.0, delta=1)
        self.assertAlmostEqual(agg.p99, 99.0, delta=1)

    def test_aggregate_median(self):
        self.agg.record("test", 1.0)
        self.agg.record("test", 2.0)
        self.agg.record("test", 3.0)
        self.agg.record("test", 4.0)
        self.agg.record("test", 5.0)
        agg = self.agg.aggregate("test", AggregationWindow.MINUTE_1)
        self.assertEqual(agg.median, 3.0)

    def test_aggregate_caching(self):
        for i in range(10):
            self.agg.record("test", float(i))
        agg1 = self.agg.aggregate("test", AggregationWindow.MINUTE_1)
        agg2 = self.agg.aggregate("test", AggregationWindow.MINUTE_1)
        # Deve retornar o mesmo objeto (cache)
        self.assertIs(agg1, agg2)

    def test_aggregate_cache_invalidation(self):
        for i in range(10):
            self.agg.record("test", float(i))
        agg1 = self.agg.aggregate("test", AggregationWindow.MINUTE_1)
        # Novo registro deve invalidar cache
        self.agg.record("test", 999.0)
        agg2 = self.agg.aggregate("test", AggregationWindow.MINUTE_1)
        self.assertIsNot(agg1, agg2)
        self.assertEqual(agg2.count, 11)


class TestAnomalyDetection(unittest.TestCase):
    """Testes para detecção de anomalias."""

    def setUp(self):
        self.agg = MetricsAggregator(max_points_per_metric=1000, z_score_threshold=3.0)

    def tearDown(self):
        self.agg.stop()

    def test_no_anomaly_normal_data(self):
        # Dados normais com distribuição gaussiana
        import random
        random.seed(42)
        for _ in range(100):
            self.agg.record("test", random.gauss(50, 5))
        anomalies = self.agg.detect_anomalies("test")
        self.assertEqual(len(anomalies), 0)

    def test_spike_detection(self):
        # Dados normais + spike
        for i in range(50):
            self.agg.record("test", 50.0)
        self.agg.record("test", 200.0)  # Spike!
        anomalies = self.agg.detect_anomalies("test")
        self.assertTrue(any(a.anomaly_type == AnomalyType.SPIKE for a in anomalies))

    def test_drop_detection(self):
        # Dados normais + drop
        for i in range(50):
            self.agg.record("test", 50.0)
        self.agg.record("test", -50.0)  # Drop!
        anomalies = self.agg.detect_anomalies("test")
        self.assertTrue(any(a.anomaly_type == AnomalyType.DROP for a in anomalies))

    def test_threshold_max(self):
        self.agg.set_threshold(MetricThreshold(metric_name="cpu", max_val=90.0))
        for i in range(20):
            self.agg.record("cpu", 50.0)
        self.agg.record("cpu", 95.0)  # Acima do threshold
        anomalies = self.agg.detect_anomalies("cpu")
        self.assertTrue(any(a.anomaly_type == AnomalyType.THRESHOLD for a in anomalies))

    def test_threshold_min(self):
        self.agg.set_threshold(MetricThreshold(metric_name="temp", min_val=10.0))
        for i in range(20):
            self.agg.record("temp", 20.0)
        self.agg.record("temp", 5.0)  # Abaixo do threshold
        anomalies = self.agg.detect_anomalies("temp")
        self.assertTrue(any(a.anomaly_type == AnomalyType.THRESHOLD for a in anomalies))

    def test_flatline_detection(self):
        # Mesmo valor repetido
        for _ in range(15):
            self.agg.record("test", 42.0)
        anomalies = self.agg.detect_anomalies("test")
        self.assertTrue(any(a.anomaly_type == AnomalyType.FLATLINE for a in anomalies))

    def test_no_flatline_with_variation(self):
        # Valores com variação
        for i in range(15):
            self.agg.record("test", 42.0 + i * 0.1)
        anomalies = self.agg.detect_anomalies("test")
        self.assertFalse(any(a.anomaly_type == AnomalyType.FLATLINE for a in anomalies))

    def test_custom_z_threshold(self):
        self.agg.set_threshold(MetricThreshold(metric_name="test", z_score_threshold=2.0))
        # Valores com desvio moderado
        for i in range(30):
            self.agg.record("test", 50.0)
        self.agg.record("test", 55.0)  # Desvio moderado
        anomalies = self.agg.detect_anomalies("test")
        # Com threshold 2.0, 55 pode ser anomalia dependendo do stddev

    def test_insufficient_data(self):
        self.agg.record("test", 1.0)
        self.agg.record("test", 2.0)
        anomalies = self.agg.detect_anomalies("test")
        self.assertEqual(len(anomalies), 0)

    def test_detect_all_anomalies(self):
        self.agg.record("cpu", 50.0)
        self.agg.record("memory", 80.0)
        result = self.agg.detect_all_anomalies()
        self.assertIsInstance(result, dict)

    def test_anomaly_callback(self):
        callback = MagicMock()
        self.agg.on_anomaly(callback)
        for i in range(50):
            self.agg.record("test", 50.0)
        self.agg.record("test", 200.0)  # Spike
        self.agg.detect_anomalies("test")
        self.assertTrue(callback.called)

    def test_recent_anomalies(self):
        for i in range(50):
            self.agg.record("test", 50.0)
        self.agg.record("test", 200.0)
        self.agg.detect_anomalies("test")
        recent = self.agg.get_recent_anomalies(limit=10)
        self.assertIsInstance(recent, list)
        if recent:
            self.assertIn("metric", recent[0])
            self.assertIn("type", recent[0])

    def test_recent_anomalies_filter_by_metric(self):
        for i in range(50):
            self.agg.record("cpu", 50.0)
            self.agg.record("memory", 80.0)
        self.agg.record("cpu", 200.0)
        self.agg.detect_all_anomalies()
        cpu_anomalies = self.agg.get_recent_anomalies(metric_name="cpu")
        for a in cpu_anomalies:
            self.assertEqual(a["metric"], "cpu")

    def test_recent_anomalies_filter_by_severity(self):
        for i in range(50):
            self.agg.record("test", 50.0)
        self.agg.record("test", 500.0)  # Extreme spike
        self.agg.detect_anomalies("test")
        critical = self.agg.get_recent_anomalies(severity="critical")
        for a in critical:
            self.assertEqual(a["severity"], "critical")


class TestTrendAnalysis(unittest.TestCase):
    """Testes para análise de tendência."""

    def setUp(self):
        self.agg = MetricsAggregator()

    def tearDown(self):
        self.agg.stop()

    def test_rising_trend(self):
        # Valores crescentes
        for i in range(20):
            self.agg.record("test", float(i))
        trend = self.agg.get_trend("test", AggregationWindow.MINUTE_1)
        self.assertIsNotNone(trend)
        self.assertEqual(trend["direction"], "rising")

    def test_falling_trend(self):
        # Valores decrescentes
        for i in range(20, 0, -1):
            self.agg.record("test", float(i))
        trend = self.agg.get_trend("test", AggregationWindow.MINUTE_1)
        self.assertIsNotNone(trend)
        self.assertEqual(trend["direction"], "falling")

    def test_stable_trend(self):
        # Valores estáveis
        for _ in range(20):
            self.agg.record("test", 50.0)
        trend = self.agg.get_trend("test", AggregationWindow.MINUTE_1)
        self.assertIsNotNone(trend)
        self.assertEqual(trend["direction"], "stable")

    def test_volatile_trend(self):
        # Valores voláteis
        values = [10, 90, 20, 80, 30, 70, 40, 60, 50, 50, 10, 90, 20, 80, 30, 70]
        for v in values:
            self.agg.record("test", float(v))
        trend = self.agg.get_trend("test", AggregationWindow.MINUTE_1)
        self.assertIsNotNone(trend)
        self.assertEqual(trend["direction"], "volatile")

    def test_insufficient_data_for_trend(self):
        self.agg.record("test", 1.0)
        trend = self.agg.get_trend("test", AggregationWindow.MINUTE_1)
        self.assertIsNone(trend)

    def test_trend_strength(self):
        # Crescimento forte
        for i in range(20):
            self.agg.record("test", float(i * 10))
        trend = self.agg.get_trend("test", AggregationWindow.MINUTE_1)
        self.assertGreater(trend["strength"], 0.5)


class TestCorrelation(unittest.TestCase):
    """Testes para correlação entre métricas."""

    def setUp(self):
        self.agg = MetricsAggregator()

    def tearDown(self):
        self.agg.stop()

    def test_positive_correlation(self):
        # Métricas que crescem juntas (com timestamps espaçados)
        now = time.time()
        for i in range(50):
            ts = now + i * 2  # 2s entre cada ponto
            self.agg._points["cpu"].append(MetricPoint(name="cpu", value=float(i), timestamp=ts))
            self.agg._points["memory"].append(MetricPoint(name="memory", value=float(i * 1.5), timestamp=ts))
        self.agg._stats["total_points"] += 100
        corr = self.agg.correlate("cpu", "memory", AggregationWindow.MINUTE_1)
        self.assertIsNotNone(corr)
        self.assertGreater(corr["correlation"], 0.8)
        self.assertEqual(corr["strength"], "strong")
        self.assertEqual(corr["direction"], "positive")

    def test_negative_correlation(self):
        # Métricas opostas (com timestamps espaçados)
        now = time.time()
        for i in range(50):
            ts = now + i * 2
            self.agg._points["free_memory"].append(MetricPoint(name="free_memory", value=100.0 - float(i), timestamp=ts))
            self.agg._points["used_memory"].append(MetricPoint(name="used_memory", value=float(i), timestamp=ts))
        self.agg._stats["total_points"] += 100
        corr = self.agg.correlate("free_memory", "used_memory", AggregationWindow.MINUTE_1)
        self.assertIsNotNone(corr)
        self.assertLess(corr["correlation"], -0.8)
        self.assertEqual(corr["direction"], "negative")

    def test_no_correlation(self):
        # Métricas independentes
        import random
        random.seed(42)
        for _ in range(50):
            self.agg.record("metric_a", random.uniform(0, 100))
            self.agg.record("metric_b", random.uniform(0, 100))
        corr = self.agg.correlate("metric_a", "metric_b", AggregationWindow.MINUTE_1)
        # Pode ser None se não houver buckets suficientes, ou correlação baixa
        if corr:
            self.assertIn(corr["strength"], ["none", "weak"])

    def test_missing_metric(self):
        self.agg.record("cpu", 50.0)
        corr = self.agg.correlate("cpu", "nonexistent", AggregationWindow.MINUTE_1)
        self.assertIsNone(corr)

    def test_insufficient_data(self):
        self.agg.record("a", 1.0)
        self.agg.record("b", 2.0)
        corr = self.agg.correlate("a", "b", AggregationWindow.MINUTE_1)
        self.assertIsNone(corr)


class TestThreshold(unittest.TestCase):
    """Testes para configuração de thresholds."""

    def setUp(self):
        self.agg = MetricsAggregator()

    def tearDown(self):
        self.agg.stop()

    def test_set_threshold(self):
        thresh = MetricThreshold(metric_name="cpu", min_val=0, max_val=100, z_score_threshold=2.5)
        self.agg.set_threshold(thresh)
        self.assertIn("cpu", self.agg._thresholds)

    def test_threshold_update(self):
        self.agg.set_threshold(MetricThreshold(metric_name="cpu", max_val=90))
        self.agg.set_threshold(MetricThreshold(metric_name="cpu", max_val=95))
        self.assertEqual(self.agg._thresholds["cpu"].max_val, 95)


class TestStats(unittest.TestCase):
    """Testes para estatísticas do agregador."""

    def setUp(self):
        self.agg = MetricsAggregator()

    def tearDown(self):
        self.agg.stop()

    def test_initial_stats(self):
        stats = self.agg.get_stats()
        self.assertEqual(stats["total_points"], 0)
        self.assertEqual(stats["total_anomalies"], 0)
        self.assertEqual(stats["metrics_tracked"], 0)
        self.assertFalse(stats["running"])

    def test_stats_after_recording(self):
        for i in range(10):
            self.agg.record("test", float(i))
        stats = self.agg.get_stats()
        self.assertEqual(stats["total_points"], 10)
        self.assertEqual(stats["metrics_tracked"], 1)

    def test_stats_after_anomaly(self):
        for i in range(50):
            self.agg.record("test", 50.0)
        self.agg.record("test", 200.0)
        self.agg.detect_anomalies("test")
        stats = self.agg.get_stats()
        self.assertGreater(stats["total_anomalies"], 0)


class TestClearMetric(unittest.TestCase):
    """Testes para limpeza de métricas."""

    def setUp(self):
        self.agg = MetricsAggregator()

    def tearDown(self):
        self.agg.stop()

    def test_clear_existing(self):
        for i in range(10):
            self.agg.record("test", float(i))
        count = self.agg.clear_metric("test")
        self.assertEqual(count, 10)
        self.assertNotIn("test", self.agg.get_metric_names())

    def test_clear_nonexistent(self):
        count = self.agg.clear_metric("nonexistent")
        self.assertEqual(count, 0)


class TestWorkerThread(unittest.TestCase):
    """Testes para worker thread de anomalias."""

    def test_start_stop(self):
        agg = MetricsAggregator(anomaly_check_interval=0.1)
        agg.start()
        self.assertTrue(agg._running)
        time.sleep(0.2)
        agg.stop()
        self.assertFalse(agg._running)

    def test_double_start(self):
        agg = MetricsAggregator()
        agg.start()
        agg.start()  # Deve ser idempotente
        self.assertTrue(agg._running)
        agg.stop()

    def test_worker_detects_anomalies(self):
        agg = MetricsAggregator(anomaly_check_interval=0.1, z_score_threshold=2.0)
        # Registra dados normais
        for i in range(50):
            agg.record("test", 50.0)
        agg.start()
        time.sleep(0.2)
        # Adiciona spike
        agg.record("test", 200.0)
        time.sleep(0.3)
        stats = agg.get_stats()
        agg.stop()
        # Worker deve ter detectado anomalia
        self.assertGreater(stats["total_anomalies"], 0)


class TestSingleton(unittest.TestCase):
    """Testes para padrão singleton."""

    def tearDown(self):
        reset_aggregator()

    def test_get_aggregator(self):
        agg1 = get_aggregator()
        agg2 = get_aggregator()
        self.assertIs(agg1, agg2)

    def test_reset_aggregator(self):
        agg1 = get_aggregator()
        reset_aggregator()
        agg2 = get_aggregator()
        self.assertIsNot(agg1, agg2)


class TestAggregatedMetric(unittest.TestCase):
    """Testes para AggregatedMetric."""

    def test_to_dict(self):
        from metrics_aggregator import AggregatedMetric
        agg = AggregatedMetric(
            name="test",
            window=AggregationWindow.MINUTE_1,
            count=100,
            min_val=0.0,
            max_val=99.0,
            mean=49.5,
            median=50.0,
            stddev=28.87,
            p95=95.0,
            p99=99.0,
            sum_val=4950.0,
            first_ts=1000.0,
            last_ts=1060.0,
        )
        d = agg.to_dict()
        self.assertEqual(d["name"], "test")
        self.assertEqual(d["count"], 100)
        self.assertEqual(d["range"], 99.0)
        self.assertEqual(d["duration_seconds"], 60.0)


if __name__ == "__main__":
    unittest.main()
