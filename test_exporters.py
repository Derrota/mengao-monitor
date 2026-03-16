"""
Testes para o módulo Exporters.
"""

import unittest
import time
import json
import csv
import os
import tempfile
import threading
from unittest.mock import patch, MagicMock

from exporters import (
    ExporterType, ExportStatus, ExportResult, MetricPoint, ExporterConfig,
    BaseExporter, PrometheusExporter, DatadogExporter, InfluxDBExporter,
    JSONFileExporter, CSVFileExporter, WebhookExporter, GrafanaExporter,
    ExporterManager, get_exporter_manager, reset_exporter_manager
)


class TestMetricPoint(unittest.TestCase):
    """Testes para MetricPoint."""

    def test_basic_creation(self):
        metric = MetricPoint(name="cpu_usage", value=75.5)
        self.assertEqual(metric.name, "cpu_usage")
        self.assertEqual(metric.value, 75.5)
        self.assertEqual(metric.labels, {})
        self.assertIsNone(metric.timestamp)
        self.assertEqual(metric.metric_type, "gauge")

    def test_with_labels(self):
        metric = MetricPoint(
            name="http_requests",
            value=100,
            labels={"method": "GET", "status": "200"}
        )
        self.assertEqual(metric.labels["method"], "GET")

    def test_to_dict(self):
        metric = MetricPoint(
            name="memory",
            value=1024,
            timestamp=1000000.0,
            metric_type="gauge"
        )
        d = metric.to_dict()
        self.assertEqual(d["name"], "memory")
        self.assertEqual(d["value"], 1024)
        self.assertEqual(d["timestamp"], 1000000.0)
        self.assertEqual(d["type"], "gauge")


class TestExportResult(unittest.TestCase):
    """Testes para ExportResult."""

    def test_to_dict(self):
        result = ExportResult(
            exporter_name="test",
            exporter_type="json_file",
            status=ExportStatus.SUCCESS,
            timestamp=1000000.0,
            duration_ms=50.0,
            metrics_count=10
        )
        d = result.to_dict()
        self.assertEqual(d["exporter_name"], "test")
        self.assertEqual(d["status"], "success")
        self.assertIn("timestamp_iso", d)

    def test_failed_result(self):
        result = ExportResult(
            exporter_name="test",
            exporter_type="prometheus",
            status=ExportStatus.FAILED,
            timestamp=time.time(),
            duration_ms=0,
            metrics_count=0,
            error="Connection refused"
        )
        self.assertEqual(result.status, ExportStatus.FAILED)
        self.assertEqual(result.error, "Connection refused")


class TestExporterConfig(unittest.TestCase):
    """Testes para ExporterConfig."""

    def test_defaults(self):
        config = ExporterConfig(name="test")
        self.assertTrue(config.enabled)
        self.assertEqual(config.interval_seconds, 60)
        self.assertEqual(config.batch_size, 100)
        self.assertEqual(config.retry_count, 3)

    def test_custom_values(self):
        config = ExporterConfig(
            name="custom",
            enabled=False,
            interval_seconds=30,
            labels={"env": "prod"},
            metric_filter=["cpu_"]
        )
        self.assertFalse(config.enabled)
        self.assertEqual(config.labels["env"], "prod")
        self.assertEqual(config.metric_filter, ["cpu_"])


class TestPrometheusExporter(unittest.TestCase):
    """Testes para PrometheusExporter."""

    def setUp(self):
        config = ExporterConfig(name="prom_test")
        self.exporter = PrometheusExporter(
            config=config,
            pushgateway_url="http://localhost:9091",
            job_name="test_job"
        )

    def test_validate_config(self):
        self.assertTrue(self.exporter.validate_config())

    def test_validate_config_empty(self):
        config = ExporterConfig(name="bad")
        exporter = PrometheusExporter(config, "", "")
        self.assertFalse(exporter.validate_config())

    def test_export_success(self):
        metrics = [
            MetricPoint("cpu_usage", 75.5, {"host": "server1"}),
            MetricPoint("memory_mb", 1024, {"host": "server1"})
        ]
        result = self.exporter.export(metrics)
        self.assertEqual(result.status, ExportStatus.SUCCESS)
        self.assertEqual(result.metrics_count, 2)

    def test_export_empty(self):
        result = self.exporter.export([])
        self.assertEqual(result.status, ExportStatus.SKIPPED)

    def test_filter_metrics(self):
        self.exporter.config.metric_filter = ["cpu_"]
        metrics = [
            MetricPoint("cpu_usage", 75),
            MetricPoint("memory_mb", 1024)
        ]
        filtered = self.exporter.filter_metrics(metrics)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].name, "cpu_usage")

    def test_add_default_labels(self):
        self.exporter.config.labels = {"env": "prod", "region": "us-east"}
        metrics = [MetricPoint("test", 1, {"custom": "label"})]
        enriched = self.exporter.add_default_labels(metrics)
        self.assertEqual(enriched[0].labels["env"], "prod")
        self.assertEqual(enriched[0].labels["custom"], "label")


class TestDatadogExporter(unittest.TestCase):
    """Testes para DatadogExporter."""

    def setUp(self):
        config = ExporterConfig(name="dd_test")
        self.exporter = DatadogExporter(config, api_key="test_key_123")

    def test_validate_config(self):
        self.assertTrue(self.exporter.validate_config())

    def test_export_success(self):
        metrics = [MetricPoint("request_count", 100, {"service": "api"})]
        result = self.exporter.export(metrics)
        self.assertEqual(result.status, ExportStatus.SUCCESS)
        self.assertEqual(result.metrics_count, 1)


class TestInfluxDBExporter(unittest.TestCase):
    """Testes para InfluxDBExporter."""

    def setUp(self):
        config = ExporterConfig(name="influx_test")
        self.exporter = InfluxDBExporter(
            config,
            url="http://localhost:8086",
            database="mengao"
        )

    def test_validate_config(self):
        self.assertTrue(self.exporter.validate_config())

    def test_validate_config_empty(self):
        config = ExporterConfig(name="bad")
        exporter = InfluxDBExporter(config, "", "")
        self.assertFalse(exporter.validate_config())

    def test_export_success(self):
        metrics = [
            MetricPoint("temperature", 25.5, {"location": "dc1"}),
            MetricPoint("humidity", 60, {"location": "dc1"})
        ]
        result = self.exporter.export(metrics)
        self.assertEqual(result.status, ExportStatus.SUCCESS)
        self.assertEqual(result.metrics_count, 2)

    def test_export_without_labels(self):
        metrics = [MetricPoint("simple_metric", 42)]
        result = self.exporter.export(metrics)
        self.assertEqual(result.status, ExportStatus.SUCCESS)


class TestJSONFileExporter(unittest.TestCase):
    """Testes para JSONFileExporter."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.filepath = os.path.join(self.temp_dir, "metrics.json")
        config = ExporterConfig(name="json_test")
        self.exporter = JSONFileExporter(config, self.filepath)

    def tearDown(self):
        if os.path.exists(self.filepath):
            os.remove(self.filepath)
        os.rmdir(self.temp_dir)

    def test_validate_config(self):
        self.assertTrue(self.exporter.validate_config())

    def test_export_creates_file(self):
        metrics = [MetricPoint("test_metric", 42)]
        result = self.exporter.export(metrics)
        self.assertEqual(result.status, ExportStatus.SUCCESS)
        self.assertTrue(os.path.exists(self.filepath))

    def test_export_content(self):
        metrics = [MetricPoint("cpu", 75.5, {"host": "web1"})]
        self.exporter.export(metrics)

        with open(self.filepath, 'r') as f:
            data = json.load(f)

        self.assertEqual(data["count"], 1)
        self.assertEqual(data["metrics"][0]["name"], "cpu")

    def test_export_append_mode(self):
        metrics1 = [MetricPoint("metric1", 1)]
        metrics2 = [MetricPoint("metric2", 2)]

        self.exporter.export(metrics1)
        self.exporter.export(metrics2)

        with open(self.filepath, 'r') as f:
            data = json.load(f)

        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)

    def test_export_overwrite_mode(self):
        self.exporter.append = False
        metrics1 = [MetricPoint("metric1", 1)]
        metrics2 = [MetricPoint("metric2", 2)]

        self.exporter.export(metrics1)
        self.exporter.export(metrics2)

        with open(self.filepath, 'r') as f:
            data = json.load(f)

        self.assertIsInstance(data, dict)
        self.assertEqual(data["count"], 1)


class TestCSVFileExporter(unittest.TestCase):
    """Testes para CSVFileExporter."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.filepath = os.path.join(self.temp_dir, "metrics.csv")
        config = ExporterConfig(name="csv_test")
        self.exporter = CSVFileExporter(config, self.filepath)

    def tearDown(self):
        if os.path.exists(self.filepath):
            os.remove(self.filepath)
        os.rmdir(self.temp_dir)

    def test_validate_config(self):
        self.assertTrue(self.exporter.validate_config())

    def test_export_creates_file(self):
        metrics = [MetricPoint("test", 42)]
        result = self.exporter.export(metrics)
        self.assertEqual(result.status, ExportStatus.SUCCESS)
        self.assertTrue(os.path.exists(self.filepath))

    def test_export_header(self):
        metrics = [MetricPoint("test", 42)]
        self.exporter.export(metrics)

        with open(self.filepath, 'r') as f:
            reader = csv.reader(f)
            header = next(reader)

        self.assertEqual(header[0], "timestamp")
        self.assertEqual(header[1], "name")

    def test_export_appends(self):
        metrics1 = [MetricPoint("metric1", 1)]
        metrics2 = [MetricPoint("metric2", 2)]

        self.exporter.export(metrics1)
        self.exporter.export(metrics2)

        with open(self.filepath, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Header + 2 data rows
        self.assertEqual(len(rows), 3)


class TestWebhookExporter(unittest.TestCase):
    """Testes para WebhookExporter."""

    def setUp(self):
        config = ExporterConfig(name="webhook_test")
        self.exporter = WebhookExporter(
            config,
            url="https://example.com/webhook",
            headers={"Authorization": "Bearer token"}
        )

    def test_validate_config(self):
        self.assertTrue(self.exporter.validate_config())

    def test_export_success(self):
        metrics = [MetricPoint("alert", 1, {"severity": "high"})]
        result = self.exporter.export(metrics)
        self.assertEqual(result.status, ExportStatus.SUCCESS)


class TestGrafanaExporter(unittest.TestCase):
    """Testes para GrafanaExporter."""

    def setUp(self):
        config = ExporterConfig(name="grafana_test")
        self.exporter = GrafanaExporter(
            config,
            url="http://localhost:3000",
            api_key="test_key"
        )

    def test_validate_config(self):
        self.assertTrue(self.exporter.validate_config())

    def test_export_skips_non_events(self):
        metrics = [MetricPoint("cpu", 75, metric_type="gauge")]
        result = self.exporter.export(metrics)
        # Gauge não vira annotation
        self.assertEqual(result.metrics_count, 0)

    def test_export_events(self):
        metrics = [MetricPoint("deploy", 1, metric_type="event")]
        result = self.exporter.export(metrics)
        self.assertEqual(result.metrics_count, 1)


class TestExporterManager(unittest.TestCase):
    """Testes para ExporterManager."""

    def setUp(self):
        self.manager = ExporterManager()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        self.manager.stop_periodic_export()
        # Limpa arquivos temporários
        for f in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, f))
        os.rmdir(self.temp_dir)

    def _create_json_exporter(self, name="test_json"):
        config = ExporterConfig(name=name)
        filepath = os.path.join(self.temp_dir, f"{name}.json")
        return JSONFileExporter(config, filepath)

    def test_register_exporter(self):
        exporter = self._create_json_exporter()
        result = self.manager.register_exporter(exporter)
        self.assertTrue(result)

    def test_register_duplicate(self):
        exporter = self._create_json_exporter()
        self.manager.register_exporter(exporter)
        result = self.manager.register_exporter(exporter)
        self.assertFalse(result)

    def test_unregister_exporter(self):
        exporter = self._create_json_exporter()
        self.manager.register_exporter(exporter)
        result = self.manager.unregister_exporter("test_json")
        self.assertTrue(result)

    def test_unregister_nonexistent(self):
        result = self.manager.unregister_exporter("nonexistent")
        self.assertFalse(result)

    def test_get_exporter(self):
        exporter = self._create_json_exporter()
        self.manager.register_exporter(exporter)
        retrieved = self.manager.get_exporter("test_json")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "test_json")

    def test_list_exporters(self):
        e1 = self._create_json_exporter("e1")
        e2 = self._create_json_exporter("e2")
        self.manager.register_exporter(e1)
        self.manager.register_exporter(e2)

        exporters = self.manager.list_exporters()
        self.assertEqual(len(exporters), 2)

    def test_enable_disable(self):
        exporter = self._create_json_exporter()
        self.manager.register_exporter(exporter)

        self.manager.disable_exporter("test_json")
        self.assertFalse(exporter.enabled)

        self.manager.enable_exporter("test_json")
        self.assertTrue(exporter.enabled)

    def test_export_all(self):
        exporter = self._create_json_exporter()
        self.manager.register_exporter(exporter)

        metrics = [MetricPoint("test", 42)]
        results = self.manager.export_all(metrics)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, ExportStatus.SUCCESS)

    def test_export_all_skips_disabled(self):
        exporter = self._create_json_exporter()
        exporter.enabled = False
        self.manager.register_exporter(exporter)

        metrics = [MetricPoint("test", 42)]
        results = self.manager.export_all(metrics)

        self.assertEqual(len(results), 0)

    def test_export_to_specific(self):
        e1 = self._create_json_exporter("e1")
        e2 = self._create_json_exporter("e2")
        self.manager.register_exporter(e1)
        self.manager.register_exporter(e2)

        metrics = [MetricPoint("test", 42)]
        result = self.manager.export_to("e1", metrics)

        self.assertIsNotNone(result)
        self.assertEqual(result.exporter_name, "e1")

    def test_export_to_nonexistent(self):
        result = self.manager.export_to("nonexistent", [])
        self.assertIsNone(result)

    def test_history(self):
        exporter = self._create_json_exporter()
        self.manager.register_exporter(exporter)

        metrics = [MetricPoint("test", 42)]
        self.manager.export_all(metrics)

        history = self.manager.get_history()
        self.assertEqual(len(history), 1)

    def test_history_filter_by_exporter(self):
        e1 = self._create_json_exporter("e1")
        e2 = self._create_json_exporter("e2")
        self.manager.register_exporter(e1)
        self.manager.register_exporter(e2)

        metrics = [MetricPoint("test", 42)]
        self.manager.export_to("e1", metrics)
        self.manager.export_to("e2", metrics)

        history = self.manager.get_history(exporter_name="e1")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["exporter_name"], "e1")

    def test_history_filter_by_status(self):
        exporter = self._create_json_exporter()
        self.manager.register_exporter(exporter)

        metrics = [MetricPoint("test", 42)]
        self.manager.export_all(metrics)

        history = self.manager.get_history(status=ExportStatus.SUCCESS)
        self.assertEqual(len(history), 1)

        history = self.manager.get_history(status=ExportStatus.FAILED)
        self.assertEqual(len(history), 0)

    def test_global_stats(self):
        exporter = self._create_json_exporter()
        self.manager.register_exporter(exporter)

        metrics = [MetricPoint("test", 42)]
        self.manager.export_all(metrics)

        stats = self.manager.get_global_stats()
        self.assertEqual(stats["total_exporters"], 1)
        self.assertEqual(stats["enabled_exporters"], 1)
        self.assertEqual(stats["total_exports"], 1)
        self.assertEqual(stats["successful_exports"], 1)
        self.assertEqual(stats["success_rate"], 100.0)

    def test_buffer_metrics(self):
        exporter = self._create_json_exporter()
        self.manager.register_exporter(exporter)

        metrics = [MetricPoint("buffered", 100)]
        self.manager.buffer_metrics(metrics)

        stats = self.manager.get_global_stats()
        self.assertEqual(stats["buffered_metrics"], 1)

    def test_flush_buffer(self):
        exporter = self._create_json_exporter()
        self.manager.register_exporter(exporter)

        metrics = [MetricPoint("buffered", 100)]
        self.manager.buffer_metrics(metrics)

        results = self.manager.flush_buffer()
        self.assertEqual(len(results), 1)

        stats = self.manager.get_global_stats()
        self.assertEqual(stats["buffered_metrics"], 0)

    def test_clear_history(self):
        exporter = self._create_json_exporter()
        self.manager.register_exporter(exporter)

        metrics = [MetricPoint("test", 42)]
        self.manager.export_all(metrics)

        self.manager.clear_history()
        history = self.manager.get_history()
        self.assertEqual(len(history), 0)


class TestSingleton(unittest.TestCase):
    """Testes para singleton global."""

    def tearDown(self):
        reset_exporter_manager()

    def test_get_singleton(self):
        manager1 = get_exporter_manager()
        manager2 = get_exporter_manager()
        self.assertIs(manager1, manager2)

    def test_reset_singleton(self):
        manager1 = get_exporter_manager()
        reset_exporter_manager()
        manager2 = get_exporter_manager()
        self.assertIsNot(manager1, manager2)


class TestExportResultStats(unittest.TestCase):
    """Testes para atualização de stats dos exporters."""

    def test_stats_update_success(self):
        config = ExporterConfig(name="test")
        exporter = JSONFileExporter(config, "/tmp/test.json")

        result = ExportResult(
            exporter_name="test",
            exporter_type="json_file",
            status=ExportStatus.SUCCESS,
            timestamp=time.time(),
            duration_ms=50,
            metrics_count=10
        )
        exporter.update_stats(result)

        stats = exporter.get_stats()
        self.assertEqual(stats["total_exports"], 1)
        self.assertEqual(stats["successful_exports"], 1)
        self.assertEqual(stats["total_metrics"], 10)

    def test_stats_update_failure(self):
        config = ExporterConfig(name="test")
        exporter = JSONFileExporter(config, "/tmp/test.json")

        result = ExportResult(
            exporter_name="test",
            exporter_type="json_file",
            status=ExportStatus.FAILED,
            timestamp=time.time(),
            duration_ms=0,
            metrics_count=0,
            error="Disk full"
        )
        exporter.update_stats(result)

        stats = exporter.get_stats()
        self.assertEqual(stats["failed_exports"], 1)
        self.assertEqual(stats["last_error"], "Disk full")

    def test_avg_duration_calculation(self):
        config = ExporterConfig(name="test")
        exporter = JSONFileExporter(config, "/tmp/test.json")

        for duration in [10, 20, 30]:
            result = ExportResult(
                exporter_name="test",
                exporter_type="json_file",
                status=ExportStatus.SUCCESS,
                timestamp=time.time(),
                duration_ms=duration,
                metrics_count=1
            )
            exporter.update_stats(result)

        stats = exporter.get_stats()
        self.assertEqual(stats["avg_duration_ms"], 20.0)
        self.assertEqual(stats["success_rate"], 100.0)


class TestThreadSafety(unittest.TestCase):
    """Testes de thread safety."""

    def test_concurrent_export(self):
        manager = ExporterManager()
        config = ExporterConfig(name="thread_test")
        exporter = JSONFileExporter(config, "/dev/null")
        manager.register_exporter(exporter)

        errors = []

        def export_worker():
            try:
                for _ in range(10):
                    metrics = [MetricPoint("concurrent", 42)]
                    manager.export_all(metrics)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=export_worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)
        stats = manager.get_global_stats()
        self.assertEqual(stats["total_exports"], 50)


if __name__ == '__main__':
    unittest.main()
