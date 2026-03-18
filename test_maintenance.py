"""
Testes para Maintenance Manager v3.13
30+ test cases cobrindo todas as funcionalidades.
"""

import os
import sys
import time
import json
import gzip
import sqlite3
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from maintenance import (
    MaintenanceTaskType,
    TaskStatus,
    MaintenanceTaskResult,
    MaintenanceTask,
    LogRotator,
    DatabaseCleaner,
    DiskMonitor,
    CacheEvictor,
    MaintenanceManager,
    get_maintenance_manager
)


class TestMaintenanceTaskResult(unittest.TestCase):
    """Testes para MaintenanceTaskResult."""

    def test_result_to_dict(self):
        result = MaintenanceTaskResult(
            task_name="test",
            task_type=MaintenanceTaskType.LOG_ROTATION,
            status=TaskStatus.COMPLETED,
            started_at=1000.0,
            finished_at=1001.0,
            duration_ms=1000.0,
            items_processed=10,
            items_removed=5,
            bytes_freed=1024
        )
        d = result.to_dict()
        self.assertEqual(d["task_name"], "test")
        self.assertEqual(d["task_type"], "log_rotation")
        self.assertEqual(d["status"], "completed")
        self.assertEqual(d["items_removed"], 5)

    def test_result_with_error(self):
        result = MaintenanceTaskResult(
            task_name="test",
            task_type=MaintenanceTaskType.DB_CLEANUP,
            status=TaskStatus.FAILED,
            started_at=1000.0,
            finished_at=1001.0,
            duration_ms=1000.0,
            error="Connection failed"
        )
        d = result.to_dict()
        self.assertEqual(d["error"], "Connection failed")
        self.assertEqual(d["status"], "failed")


class TestMaintenanceTask(unittest.TestCase):
    """Testes para MaintenanceTask."""

    def test_task_to_dict(self):
        task = MaintenanceTask(
            name="test_task",
            task_type=MaintenanceTaskType.LOG_ROTATION,
            interval_seconds=3600,
            max_age_days=7
        )
        d = task.to_dict()
        self.assertEqual(d["name"], "test_task")
        self.assertEqual(d["interval_seconds"], 3600)
        self.assertEqual(d["success_rate"], 0.0)

    def test_task_success_rate(self):
        task = MaintenanceTask(
            name="test",
            task_type=MaintenanceTaskType.DISK_MONITOR
        )
        task.run_count = 10
        task.success_count = 8
        d = task.to_dict()
        self.assertEqual(d["success_rate"], 80.0)


class TestLogRotator(unittest.TestCase):
    """Testes para LogRotator."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.rotator = LogRotator(self.temp_dir, max_size_mb=1, max_age_days=1, max_files=5)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_rotate_empty_dir(self):
        result = self.rotator.rotate()
        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertEqual(result.items_processed, 0)

    def test_rotate_nonexistent_dir(self):
        rotator = LogRotator("/nonexistent/path")
        result = rotator.rotate()
        self.assertEqual(result.status, TaskStatus.SKIPPED)
        self.assertIn("not found", result.error)

    def test_rotate_small_logs(self):
        # Criar logs pequenos (não devem ser rotacionados)
        for i in range(3):
            with open(os.path.join(self.temp_dir, f"app{i}.log"), 'w') as f:
                f.write("small log content\n")

        result = self.rotator.rotate()
        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertEqual(result.items_processed, 3)
        # Logs pequenos não devem ser deletados
        self.assertEqual(len(os.listdir(self.temp_dir)), 3)

    def test_rotate_large_log(self):
        # Criar log grande (> 1MB)
        large_file = os.path.join(self.temp_dir, "large.log")
        with open(large_file, 'w') as f:
            f.write("x" * (2 * 1024 * 1024))  # 2MB

        result = self.rotator.rotate()
        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertIn("large.log", result.details["rotated"])

    def test_rotate_old_logs(self):
        # Criar log antigo
        old_file = os.path.join(self.temp_dir, "old.log")
        with open(old_file, 'w') as f:
            f.write("old log\n")
        # Tornar antigo (2 dias atrás)
        os.utime(old_file, (time.time() - 2*86400, time.time() - 2*86400))

        result = self.rotator.rotate()
        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertIn("old.log", result.details["deleted"])

    def test_compress_rotated_log(self):
        large_file = os.path.join(self.temp_dir, "compress.log")
        with open(large_file, 'w') as f:
            f.write("x" * (2 * 1024 * 1024))

        self.rotator.rotate()

        # Verificar se arquivo comprimido existe
        gz_files = [f for f in os.listdir(self.temp_dir) if f.endswith('.gz')]
        self.assertTrue(len(gz_files) > 0)


class TestDatabaseCleaner(unittest.TestCase):
    """Testes para DatabaseCleaner."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self._create_test_db()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_test_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE health_checks (
                id INTEGER PRIMARY KEY,
                timestamp REAL,
                api_name TEXT,
                status TEXT
            )
        """)
        # Inserir dados
        now = time.time()
        for i in range(100):
            ts = now - (i * 86400)  # Cada registro 1 dia mais antigo
            cursor.execute(
                "INSERT INTO health_checks (timestamp, api_name, status) VALUES (?, ?, ?)",
                (ts, f"api_{i}", "ok")
            )
        conn.commit()
        conn.close()

    def test_cleanup_removes_old_records(self):
        cleaner = DatabaseCleaner(self.db_path)
        result = cleaner.cleanup_table("health_checks", "timestamp", max_age_days=30)

        self.assertEqual(result.status, TaskStatus.COMPLETED)
        # Deve remover ~70 registros (mais de 30 dias)
        self.assertTrue(result.items_removed > 60)
        self.assertTrue(result.items_removed < 80)

    def test_cleanup_nonexistent_db(self):
        cleaner = DatabaseCleaner("/nonexistent/db.sqlite")
        result = cleaner.cleanup_table("health_checks", "timestamp", max_age_days=30)
        self.assertEqual(result.status, TaskStatus.SKIPPED)

    def test_get_table_stats(self):
        cleaner = DatabaseCleaner(self.db_path)
        stats = cleaner.get_table_stats("health_checks", "timestamp")

        self.assertEqual(stats["total_records"], 100)
        self.assertIsNotNone(stats["oldest_timestamp"])
        self.assertIsNotNone(stats["newest_timestamp"])

    def test_cleanup_vacuum(self):
        cleaner = DatabaseCleaner(self.db_path)

        # Inserir mais dados para ter diferença visível
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = time.time()
        for i in range(1000):
            cursor.execute(
                "INSERT INTO health_checks (timestamp, api_name, status) VALUES (?, ?, ?)",
                (now - (i * 86400), f"bulk_{i}", "ok")
            )
        conn.commit()
        conn.close()

        size_before = os.path.getsize(self.db_path)
        cleaner.cleanup_table("health_checks", "timestamp", max_age_days=10)
        size_after = os.path.getsize(self.db_path)
        # VACUUM deve reduzir tamanho (ou manter se já pequeno)
        self.assertLessEqual(size_after, size_before)


class TestDiskMonitor(unittest.TestCase):
    """Testes para DiskMonitor."""

    def test_check_root_path(self):
        monitor = DiskMonitor(["/"])
        result = monitor.check()

        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertTrue(len(result.details["disks"]) > 0)
        self.assertIn("percent_used", result.details["disks"][0])

    def test_check_nonexistent_path(self):
        monitor = DiskMonitor(["/nonexistent"])
        result = monitor.check()

        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertIn("error", result.details["disks"][0])

    def test_check_multiple_paths(self):
        monitor = DiskMonitor(["/", "/tmp"])
        result = monitor.check()

        self.assertEqual(result.items_processed, 2)
        self.assertEqual(len(result.details["disks"]), 2)

    def test_warning_threshold(self):
        # Com threshold muito baixo, deve marcar warning
        monitor = DiskMonitor(["/"], warning_threshold=1, critical_threshold=99)
        result = monitor.check()

        disk = result.details["disks"][0]
        self.assertEqual(disk["alert"], "WARNING")


class TestCacheEvictor(unittest.TestCase):
    """Testes para CacheEvictor."""

    def test_evict_large_cache(self):
        cache = {f"key_{i}": f"value_{i}" for i in range(2000)}
        evictor = CacheEvictor({
            "test_cache": {
                "cache_obj": cache,
                "max_size": 1000
            }
        })

        result = evictor.evict()
        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertTrue(result.items_removed > 0)
        self.assertEqual(len(cache), 0)  # Cache deve ter sido limpo

    def test_evict_small_cache(self):
        cache = {f"key_{i}": f"value_{i}" for i in range(100)}
        evictor = CacheEvictor({
            "test_cache": {
                "cache_obj": cache,
                "max_size": 1000
            }
        })

        result = evictor.evict()
        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertEqual(result.items_removed, 0)
        self.assertEqual(len(cache), 100)  # Cache não deve ter sido limpo

    def test_evict_none_cache(self):
        evictor = CacheEvictor({
            "missing_cache": {
                "cache_obj": None,
                "max_size": 1000
            }
        })

        result = evictor.evict()
        self.assertEqual(result.status, TaskStatus.COMPLETED)


class TestMaintenanceManager(unittest.TestCase):
    """Testes para MaintenanceManager."""

    def setUp(self):
        MaintenanceManager.reset()
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.log_dir = os.path.join(self.temp_dir, "logs")
        os.makedirs(self.log_dir, exist_ok=True)
        self._create_test_db()

    def tearDown(self):
        MaintenanceManager.reset()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_test_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE health_checks (
                id INTEGER PRIMARY KEY,
                timestamp REAL,
                api_name TEXT
            )
        """)
        now = time.time()
        for i in range(50):
            cursor.execute(
                "INSERT INTO health_checks (timestamp, api_name) VALUES (?, ?)",
                (now - (i * 86400), f"api_{i}")
            )
        conn.commit()
        conn.close()

    def test_singleton(self):
        manager1 = MaintenanceManager()
        manager2 = MaintenanceManager()
        self.assertIs(manager1, manager2)

    def test_add_task(self):
        manager = MaintenanceManager()
        task = MaintenanceTask(
            name="test",
            task_type=MaintenanceTaskType.DISK_MONITOR,
            interval_seconds=60
        )
        manager.add_task(task)
        self.assertEqual(len(manager.get_all_tasks()), 1)

    def test_remove_task(self):
        manager = MaintenanceManager()
        task = MaintenanceTask(
            name="test",
            task_type=MaintenanceTaskType.DISK_MONITOR
        )
        manager.add_task(task)
        result = manager.remove_task("test")
        self.assertTrue(result)
        self.assertEqual(len(manager.get_all_tasks()), 0)

    def test_remove_nonexistent_task(self):
        manager = MaintenanceManager()
        result = manager.remove_task("nonexistent")
        self.assertFalse(result)

    def test_setup_log_rotation(self):
        manager = MaintenanceManager()
        manager.setup_log_rotation(self.log_dir)

        task = manager.get_task("log_rotation")
        self.assertIsNotNone(task)
        self.assertEqual(task.task_type, MaintenanceTaskType.LOG_ROTATION)

    def test_setup_db_cleanup(self):
        manager = MaintenanceManager()
        manager.setup_db_cleanup(self.db_path, [
            ("health_checks", "timestamp", 30)
        ])

        task = manager.get_task("db_cleanup_health_checks")
        self.assertIsNotNone(task)
        self.assertEqual(task.task_type, MaintenanceTaskType.DB_CLEANUP)

    def test_setup_disk_monitor(self):
        manager = MaintenanceManager()
        manager.setup_disk_monitor(["/"])

        task = manager.get_task("disk_monitor")
        self.assertIsNotNone(task)

    def test_run_disk_monitor_task(self):
        manager = MaintenanceManager()
        manager.setup_disk_monitor(["/"])

        result = manager.run_task("disk_monitor")
        self.assertIsNotNone(result)
        self.assertEqual(result.status, TaskStatus.COMPLETED)

    def test_run_log_rotation_task(self):
        manager = MaintenanceManager()
        manager.setup_log_rotation(self.log_dir)

        # Criar um log
        with open(os.path.join(self.log_dir, "test.log"), 'w') as f:
            f.write("test\n")

        result = manager.run_task("log_rotation")
        self.assertIsNotNone(result)
        self.assertEqual(result.status, TaskStatus.COMPLETED)

    def test_run_db_cleanup_task(self):
        manager = MaintenanceManager()
        manager.setup_db_cleanup(self.db_path, [
            ("health_checks", "timestamp", 10)
        ])

        result = manager.run_task("db_cleanup_health_checks")
        self.assertIsNotNone(result)
        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertTrue(result.items_removed > 0)

    def test_run_custom_task(self):
        manager = MaintenanceManager()
        called = []

        def custom_callback():
            called.append(True)

        task = MaintenanceTask(
            name="custom",
            task_type=MaintenanceTaskType.CUSTOM,
            callback=custom_callback
        )
        manager.add_task(task)

        result = manager.run_task("custom")
        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertEqual(len(called), 1)

    def test_run_disabled_task(self):
        manager = MaintenanceManager()
        task = MaintenanceTask(
            name="disabled",
            task_type=MaintenanceTaskType.DISK_MONITOR,
            enabled=False
        )
        manager.add_task(task)

        result = manager.run_task("disabled")
        self.assertIsNone(result)

    def test_history(self):
        manager = MaintenanceManager()
        manager.setup_disk_monitor(["/"])

        manager.run_task("disk_monitor")
        manager.run_task("disk_monitor")

        history = manager.get_history("disk_monitor")
        self.assertEqual(len(history), 2)

    def test_history_limit(self):
        manager = MaintenanceManager()
        manager.setup_disk_monitor(["/"])

        for _ in range(10):
            manager.run_task("disk_monitor")

        history = manager.get_history(limit=5)
        self.assertEqual(len(history), 5)

    def test_stats(self):
        manager = MaintenanceManager()
        manager.setup_disk_monitor(["/"])

        manager.run_task("disk_monitor")

        stats = manager.get_stats()
        self.assertEqual(stats["total_runs"], 1)
        self.assertEqual(stats["successful_runs"], 1)
        self.assertEqual(stats["tasks_configured"], 1)

    def test_run_all_pending(self):
        manager = MaintenanceManager()
        manager.setup_disk_monitor(["/"], interval_seconds=0)  # Sempre pendente

        results = manager.run_all_pending()
        self.assertTrue(len(results) > 0)

    def test_worker_start_stop(self):
        manager = MaintenanceManager()
        manager.start()
        self.assertTrue(manager._running)
        time.sleep(0.1)
        manager.stop()
        self.assertFalse(manager._running)

    def test_get_maintenance_manager(self):
        manager = MaintenanceManager()
        retrieved = get_maintenance_manager()
        self.assertIs(manager, retrieved)


class TestMaintenanceManagerEdgeCases(unittest.TestCase):
    """Testes de edge cases."""

    def setUp(self):
        MaintenanceManager.reset()

    def tearDown(self):
        MaintenanceManager.reset()

    def test_custom_task_exception(self):
        manager = MaintenanceManager()

        def failing_callback():
            raise ValueError("Test error")

        task = MaintenanceTask(
            name="failing",
            task_type=MaintenanceTaskType.CUSTOM,
            callback=failing_callback
        )
        manager.add_task(task)

        result = manager.run_task("failing")
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertIn("Test error", result.error)

    def test_task_without_callback(self):
        manager = MaintenanceManager()
        task = MaintenanceTask(
            name="no_callback",
            task_type=MaintenanceTaskType.CUSTOM
        )
        manager.add_task(task)

        result = manager.run_task("no_callback")
        self.assertIsNone(result)

    def test_max_history_limit(self):
        manager = MaintenanceManager()
        manager.max_history = 5
        manager.setup_disk_monitor(["/"])

        for _ in range(10):
            manager.run_task("disk_monitor")

        self.assertEqual(len(manager.history), 5)

    def test_multiple_db_tables(self):
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test.db")

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE alerts (id INTEGER PRIMARY KEY, timestamp REAL)")
            cursor.execute("CREATE TABLE metrics (id INTEGER PRIMARY KEY, timestamp REAL)")
            now = time.time()
            for i in range(20):
                cursor.execute("INSERT INTO alerts (timestamp) VALUES (?)", (now - i*86400,))
                cursor.execute("INSERT INTO metrics (timestamp) VALUES (?)", (now - i*86400,))
            conn.commit()
            conn.close()

            manager = MaintenanceManager()
            manager.setup_db_cleanup(db_path, [
                ("alerts", "timestamp", 10),
                ("metrics", "timestamp", 10)
            ])

            self.assertIsNotNone(manager.get_task("db_cleanup_alerts"))
            self.assertIsNotNone(manager.get_task("db_cleanup_metrics"))

            result1 = manager.run_task("db_cleanup_alerts")
            result2 = manager.run_task("db_cleanup_metrics")

            self.assertEqual(result1.status, TaskStatus.COMPLETED)
            self.assertEqual(result2.status, TaskStatus.COMPLETED)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
