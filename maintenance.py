"""
Mengão Monitor v3.13 - Automated Maintenance System
Sistema de manutenção automatizada: log rotation, DB cleanup, cache eviction, disk monitoring.

Zero dependências externas — apenas stdlib.
"""

import os
import time
import glob
import shutil
import sqlite3
import threading
import gzip
import json
from dataclasses import dataclass, field
from typing import Optional, Callable, Dict, List, Any, Tuple
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict


class MaintenanceTaskType(Enum):
    """Tipos de tarefas de manutenção."""
    LOG_ROTATION = "log_rotation"
    DB_CLEANUP = "db_cleanup"
    CACHE_EVICTION = "cache_eviction"
    HEALTH_CHECK_PRUNING = "health_check_pruning"
    DISK_MONITOR = "disk_monitor"
    CUSTOM = "custom"


class TaskStatus(Enum):
    """Status de execução de uma tarefa."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class MaintenanceTaskResult:
    """Resultado de uma tarefa de manutenção."""
    task_name: str
    task_type: MaintenanceTaskType
    status: TaskStatus
    started_at: float
    finished_at: float
    duration_ms: float
    items_processed: int = 0
    items_removed: int = 0
    bytes_freed: int = 0
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_name": self.task_name,
            "task_type": self.task_type.value,
            "status": self.status.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "items_processed": self.items_processed,
            "items_removed": self.items_removed,
            "bytes_freed": self.bytes_freed,
            "error": self.error,
            "details": self.details
        }


@dataclass
class MaintenanceTask:
    """Definição de uma tarefa de manutenção."""
    name: str
    task_type: MaintenanceTaskType
    enabled: bool = True
    interval_seconds: int = 3600  # 1 hora por padrão
    max_age_days: Optional[int] = None
    max_size_mb: Optional[int] = None
    target_path: Optional[str] = None
    db_path: Optional[str] = None
    table_name: Optional[str] = None
    callback: Optional[Callable] = None
    last_run: float = 0.0
    last_result: Optional[MaintenanceTaskResult] = None
    run_count: int = 0
    success_count: int = 0
    failure_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "task_type": self.task_type.value,
            "enabled": self.enabled,
            "interval_seconds": self.interval_seconds,
            "max_age_days": self.max_age_days,
            "max_size_mb": self.max_size_mb,
            "target_path": self.target_path,
            "db_path": self.db_path,
            "table_name": self.table_name,
            "last_run": self.last_run,
            "last_run_ago": time.time() - self.last_run if self.last_run > 0 else None,
            "run_count": self.run_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": (self.success_count / self.run_count * 100) if self.run_count > 0 else 0.0
        }


class LogRotator:
    """Rotação automática de logs baseada em tamanho e idade."""

    def __init__(self, log_dir: str, max_size_mb: int = 10, max_age_days: int = 7,
                 max_files: int = 10, compress: bool = True):
        self.log_dir = log_dir
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.max_age_days = max_age_days
        self.max_files = max_files
        self.compress = compress

    def rotate(self) -> MaintenanceTaskResult:
        """Executa rotação de logs."""
        started = time.time()
        items_processed = 0
        items_removed = 0
        bytes_freed = 0
        details = {"rotated": [], "deleted": [], "compressed": []}

        try:
            if not os.path.isdir(self.log_dir):
                return MaintenanceTaskResult(
                    task_name="log_rotation",
                    task_type=MaintenanceTaskType.LOG_ROTATION,
                    status=TaskStatus.SKIPPED,
                    started_at=started,
                    finished_at=time.time(),
                    duration_ms=(time.time() - started) * 1000,
                    error=f"Log directory not found: {self.log_dir}"
                )

            # Encontrar arquivos de log
            log_files = []
            for f in os.listdir(self.log_dir):
                filepath = os.path.join(self.log_dir, f)
                if os.path.isfile(filepath) and (f.endswith('.log') or f.endswith('.log.gz')):
                    stat = os.stat(filepath)
                    log_files.append((filepath, stat.st_size, stat.st_mtime))

            items_processed = len(log_files)

            # Rotacionar logs grandes
            for filepath, size, mtime in log_files:
                if filepath.endswith('.gz'):
                    continue

                if size > self.max_size_bytes:
                    rotated_path = self._rotate_file(filepath)
                    if rotated_path:
                        details["rotated"].append(os.path.basename(filepath))
                        items_removed += 1

            # Deletar logs antigos
            cutoff_time = time.time() - (self.max_age_days * 86400)
            all_files = []
            for f in os.listdir(self.log_dir):
                filepath = os.path.join(self.log_dir, f)
                if os.path.isfile(filepath):
                    stat = os.stat(filepath)
                    all_files.append((filepath, stat.st_size, stat.st_mtime))

            # Ordenar por mtime (mais recente primeiro)
            all_files.sort(key=lambda x: x[2], reverse=True)

            for filepath, size, mtime in all_files:
                # Deletar se muito antigo
                if mtime < cutoff_time:
                    bytes_freed += size
                    os.remove(filepath)
                    details["deleted"].append(os.path.basename(filepath))
                    items_removed += 1
                # Deletar se exceder max_files
                elif len(details["deleted"]) + len(details["rotated"]) > self.max_files:
                    bytes_freed += size
                    os.remove(filepath)
                    details["deleted"].append(os.path.basename(filepath))
                    items_removed += 1

            finished = time.time()
            return MaintenanceTaskResult(
                task_name="log_rotation",
                task_type=MaintenanceTaskType.LOG_ROTATION,
                status=TaskStatus.COMPLETED,
                started_at=started,
                finished_at=finished,
                duration_ms=(finished - started) * 1000,
                items_processed=items_processed,
                items_removed=items_removed,
                bytes_freed=bytes_freed,
                details=details
            )

        except Exception as e:
            finished = time.time()
            return MaintenanceTaskResult(
                task_name="log_rotation",
                task_type=MaintenanceTaskType.LOG_ROTATION,
                status=TaskStatus.FAILED,
                started_at=started,
                finished_at=finished,
                duration_ms=(finished - started) * 1000,
                items_processed=items_processed,
                error=str(e),
                details=details
            )

    def _rotate_file(self, filepath: str) -> Optional[str]:
        """Rotaciona um arquivo de log."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            rotated_path = f"{filepath}.{timestamp}"

            if self.compress:
                rotated_path += ".gz"
                with open(filepath, 'rb') as f_in:
                    with gzip.open(rotated_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
            else:
                shutil.copy2(filepath, rotated_path)

            # Truncar arquivo original
            with open(filepath, 'w') as f:
                f.write(f"[Log rotated at {datetime.now().isoformat()}]\n")

            return rotated_path
        except Exception:
            return None


class DatabaseCleaner:
    """Limpeza automática de dados antigos em SQLite."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def cleanup_table(self, table_name: str, timestamp_column: str,
                      max_age_days: int, batch_size: int = 1000) -> MaintenanceTaskResult:
        """Remove registros antigos de uma tabela."""
        started = time.time()
        items_processed = 0
        items_removed = 0
        details = {"table": table_name, "batches": 0}

        try:
            if not os.path.isfile(self.db_path):
                return MaintenanceTaskResult(
                    task_name=f"db_cleanup_{table_name}",
                    task_type=MaintenanceTaskType.DB_CLEANUP,
                    status=TaskStatus.SKIPPED,
                    started_at=started,
                    finished_at=time.time(),
                    duration_ms=(time.time() - started) * 1000,
                    error=f"Database not found: {self.db_path}"
                )

            cutoff_time = time.time() - (max_age_days * 86400)
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Contar registros a remover
            cursor.execute(
                f"SELECT COUNT(*) FROM {table_name} WHERE {timestamp_column} < ?",
                (cutoff_time,)
            )
            total_to_remove = cursor.fetchone()[0]
            items_processed = total_to_remove

            # Remover em batches usando subquery
            while True:
                cursor.execute(
                    f"DELETE FROM {table_name} WHERE rowid IN "
                    f"(SELECT rowid FROM {table_name} WHERE {timestamp_column} < ? LIMIT ?)",
                    (cutoff_time, batch_size)
                )
                removed = cursor.rowcount
                if removed == 0:
                    break
                items_removed += removed
                details["batches"] += 1
                conn.commit()

            # Commit final antes do VACUUM
            conn.commit()

            # VACUUM para recuperar espaço (deve ser fora de transação)
            size_before = os.path.getsize(self.db_path)
            conn.isolation_level = None  # Autocommit mode para VACUUM
            cursor.execute("VACUUM")
            conn.isolation_level = ""  # Voltar ao padrão
            size_after = os.path.getsize(self.db_path)
            bytes_freed = size_before - size_after

            conn.close()

            finished = time.time()
            return MaintenanceTaskResult(
                task_name=f"db_cleanup_{table_name}",
                task_type=MaintenanceTaskType.DB_CLEANUP,
                status=TaskStatus.COMPLETED,
                started_at=started,
                finished_at=finished,
                duration_ms=(finished - started) * 1000,
                items_processed=items_processed,
                items_removed=items_removed,
                bytes_freed=bytes_freed,
                details=details
            )

        except Exception as e:
            finished = time.time()
            return MaintenanceTaskResult(
                task_name=f"db_cleanup_{table_name}",
                task_type=MaintenanceTaskType.DB_CLEANUP,
                status=TaskStatus.FAILED,
                started_at=started,
                finished_at=finished,
                duration_ms=(finished - started) * 1000,
                items_processed=items_processed,
                error=str(e),
                details=details
            )

    def get_table_stats(self, table_name: str, timestamp_column: str) -> Dict[str, Any]:
        """Retorna estatísticas de uma tabela."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Total de registros
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            total = cursor.fetchone()[0]

            # Registro mais antigo
            cursor.execute(f"SELECT MIN({timestamp_column}) FROM {table_name}")
            oldest = cursor.fetchone()[0]

            # Registro mais recente
            cursor.execute(f"SELECT MAX({timestamp_column}) FROM {table_name}")
            newest = cursor.fetchone()[0]

            conn.close()

            return {
                "table": table_name,
                "total_records": total,
                "oldest_timestamp": oldest,
                "newest_timestamp": newest,
                "oldest_age_hours": (time.time() - oldest) / 3600 if oldest else None
            }
        except Exception as e:
            return {"table": table_name, "error": str(e)}


class DiskMonitor:
    """Monitoramento de espaço em disco."""

    def __init__(self, paths: List[str], warning_threshold: int = 80,
                 critical_threshold: int = 90):
        self.paths = paths
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold

    def check(self) -> MaintenanceTaskResult:
        """Verifica espaço em disco."""
        started = time.time()
        details = {"disks": []}
        status = TaskStatus.COMPLETED

        try:
            for path in self.paths:
                try:
                    usage = shutil.disk_usage(path)
                    percent_used = (usage.used / usage.total) * 100

                    disk_info = {
                        "path": path,
                        "total_gb": round(usage.total / (1024**3), 2),
                        "used_gb": round(usage.used / (1024**3), 2),
                        "free_gb": round(usage.free / (1024**3), 2),
                        "percent_used": round(percent_used, 1)
                    }

                    if percent_used >= self.critical_threshold:
                        disk_info["alert"] = "CRITICAL"
                        status = TaskStatus.FAILED
                    elif percent_used >= self.warning_threshold:
                        disk_info["alert"] = "WARNING"
                    else:
                        disk_info["alert"] = "OK"

                    details["disks"].append(disk_info)
                except Exception as e:
                    details["disks"].append({"path": path, "error": str(e)})

            finished = time.time()
            return MaintenanceTaskResult(
                task_name="disk_monitor",
                task_type=MaintenanceTaskType.DISK_MONITOR,
                status=status,
                started_at=started,
                finished_at=finished,
                duration_ms=(finished - started) * 1000,
                items_processed=len(self.paths),
                details=details
            )

        except Exception as e:
            finished = time.time()
            return MaintenanceTaskResult(
                task_name="disk_monitor",
                task_type=MaintenanceTaskType.DISK_MONITOR,
                status=TaskStatus.FAILED,
                started_at=started,
                finished_at=finished,
                duration_ms=(finished - started) * 1000,
                error=str(e),
                details=details
            )


class CacheEvictor:
    """Limpeza automática de caches internos."""

    def __init__(self, caches: Dict[str, Dict[str, Any]]):
        """
        caches: dict de nome -> {"cache_obj": obj, "max_age_seconds": int, "max_size": int}
        O cache_obj deve ter método .clear() e opcionalmente .keys() ou .items()
        """
        self.caches = caches

    def evict(self) -> MaintenanceTaskResult:
        """Executa limpeza de caches."""
        started = time.time()
        items_removed = 0
        details = {"caches": []}

        try:
            for name, config in self.caches.items():
                cache_obj = config.get("cache_obj")
                max_age = config.get("max_age_seconds", 3600)
                max_size = config.get("max_size", 1000)

                cache_info = {"name": name}

                if cache_obj is None:
                    cache_info["status"] = "skipped"
                    cache_info["reason"] = "no cache object"
                    details["caches"].append(cache_info)
                    continue

                # Verificar tamanho
                try:
                    if hasattr(cache_obj, "__len__"):
                        size = len(cache_obj)
                        cache_info["size_before"] = size

                        if size > max_size:
                            # Limpar cache se muito grande
                            cache_obj.clear()
                            cache_info["cleared"] = True
                            cache_info["reason"] = f"size {size} > max {max_size}"
                            items_removed += size
                        else:
                            cache_info["cleared"] = False
                            cache_info["reason"] = "within limits"
                except Exception as e:
                    cache_info["error"] = str(e)

                details["caches"].append(cache_info)

            finished = time.time()
            return MaintenanceTaskResult(
                task_name="cache_eviction",
                task_type=MaintenanceTaskType.CACHE_EVICTION,
                status=TaskStatus.COMPLETED,
                started_at=started,
                finished_at=finished,
                duration_ms=(finished - started) * 1000,
                items_removed=items_removed,
                details=details
            )

        except Exception as e:
            finished = time.time()
            return MaintenanceTaskResult(
                task_name="cache_eviction",
                task_type=MaintenanceTaskType.CACHE_EVICTION,
                status=TaskStatus.FAILED,
                started_at=started,
                finished_at=finished,
                duration_ms=(finished - started) * 1000,
                error=str(e),
                details=details
            )


class MaintenanceManager:
    """Gerenciador central de manutenção automatizada."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, db_path: Optional[str] = None, log_dir: Optional[str] = None):
        if self._initialized:
            return
        self._initialized = True

        self.db_path = db_path
        self.log_dir = log_dir
        self.tasks: Dict[str, MaintenanceTask] = {}
        self.history: List[MaintenanceTaskResult] = []
        self.max_history = 1000
        self._lock = threading.RLock()
        self._worker = None
        self._running = False
        self._check_interval = 60  # Check a cada 60s

        # Stats
        self.stats = {
            "total_runs": 0,
            "successful_runs": 0,
            "failed_runs": 0,
            "total_bytes_freed": 0,
            "total_items_removed": 0,
            "started_at": time.time()
        }

        # Componentes
        self.log_rotator = None
        self.db_cleaner = None
        self.disk_monitor = None
        self.cache_evictor = None

    def setup_log_rotation(self, log_dir: str, max_size_mb: int = 10,
                           max_age_days: int = 7, max_files: int = 10,
                           interval_seconds: int = 3600):
        """Configura rotação automática de logs."""
        self.log_dir = log_dir
        self.log_rotator = LogRotator(log_dir, max_size_mb, max_age_days, max_files)

        task = MaintenanceTask(
            name="log_rotation",
            task_type=MaintenanceTaskType.LOG_ROTATION,
            interval_seconds=interval_seconds,
            max_age_days=max_age_days,
            max_size_mb=max_size_mb,
            target_path=log_dir
        )
        self.add_task(task)

    def setup_db_cleanup(self, db_path: str, tables: List[Tuple[str, str, int]],
                         interval_seconds: int = 86400):
        """
        Configura limpeza automática de banco.
        tables: lista de (table_name, timestamp_column, max_age_days)
        """
        self.db_path = db_path
        self.db_cleaner = DatabaseCleaner(db_path)

        for table_name, timestamp_column, max_age_days in tables:
            task = MaintenanceTask(
                name=f"db_cleanup_{table_name}",
                task_type=MaintenanceTaskType.DB_CLEANUP,
                interval_seconds=interval_seconds,
                max_age_days=max_age_days,
                db_path=db_path,
                table_name=table_name
            )
            self.add_task(task)

    def setup_disk_monitor(self, paths: List[str], warning_threshold: int = 80,
                           critical_threshold: int = 90, interval_seconds: int = 300):
        """Configura monitoramento de disco."""
        self.disk_monitor = DiskMonitor(paths, warning_threshold, critical_threshold)

        task = MaintenanceTask(
            name="disk_monitor",
            task_type=MaintenanceTaskType.DISK_MONITOR,
            interval_seconds=interval_seconds
        )
        self.add_task(task)

    def setup_cache_eviction(self, caches: Dict[str, Dict[str, Any]],
                             interval_seconds: int = 1800):
        """Configura limpeza automática de caches."""
        self.cache_evictor = CacheEvictor(caches)

        task = MaintenanceTask(
            name="cache_eviction",
            task_type=MaintenanceTaskType.CACHE_EVICTION,
            interval_seconds=interval_seconds
        )
        self.add_task(task)

    def add_task(self, task: MaintenanceTask):
        """Adiciona uma tarefa de manutenção."""
        with self._lock:
            self.tasks[task.name] = task

    def remove_task(self, name: str) -> bool:
        """Remove uma tarefa."""
        with self._lock:
            if name in self.tasks:
                del self.tasks[name]
                return True
            return False

    def get_task(self, name: str) -> Optional[MaintenanceTask]:
        """Retorna uma tarefa pelo nome."""
        return self.tasks.get(name)

    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """Retorna todas as tarefas."""
        return [t.to_dict() for t in self.tasks.values()]

    def run_task(self, name: str) -> Optional[MaintenanceTaskResult]:
        """Executa uma tarefa específica."""
        task = self.tasks.get(name)
        if not task or not task.enabled:
            return None

        result = None
        task.run_count += 1

        try:
            if task.task_type == MaintenanceTaskType.LOG_ROTATION and self.log_rotator:
                result = self.log_rotator.rotate()
            elif task.task_type == MaintenanceTaskType.DB_CLEANUP and self.db_cleaner:
                result = self.db_cleaner.cleanup_table(
                    task.table_name, "timestamp", task.max_age_days or 30
                )
            elif task.task_type == MaintenanceTaskType.DISK_MONITOR and self.disk_monitor:
                result = self.disk_monitor.check()
            elif task.task_type == MaintenanceTaskType.CACHE_EVICTION and self.cache_evictor:
                result = self.cache_evictor.evict()
            elif task.callback:
                # Tarefa customizada
                started = time.time()
                try:
                    task.callback()
                    result = MaintenanceTaskResult(
                        task_name=task.name,
                        task_type=task.task_type,
                        status=TaskStatus.COMPLETED,
                        started_at=started,
                        finished_at=time.time(),
                        duration_ms=(time.time() - started) * 1000
                    )
                except Exception as e:
                    result = MaintenanceTaskResult(
                        task_name=task.name,
                        task_type=task.task_type,
                        status=TaskStatus.FAILED,
                        started_at=started,
                        finished_at=time.time(),
                        duration_ms=(time.time() - started) * 1000,
                        error=str(e)
                    )

            if result:
                task.last_run = time.time()
                task.last_result = result

                if result.status == TaskStatus.COMPLETED:
                    task.success_count += 1
                else:
                    task.failure_count += 1

                self._record_result(result)

        except Exception as e:
            task.failure_count += 1
            result = MaintenanceTaskResult(
                task_name=task.name,
                task_type=task.task_type,
                status=TaskStatus.FAILED,
                started_at=time.time(),
                finished_at=time.time(),
                duration_ms=0,
                error=str(e)
            )
            self._record_result(result)

        return result

    def run_all_pending(self) -> List[MaintenanceTaskResult]:
        """Executa todas as tarefas pendentes."""
        results = []
        now = time.time()

        for name, task in list(self.tasks.items()):
            if not task.enabled:
                continue

            if now - task.last_run >= task.interval_seconds:
                result = self.run_task(name)
                if result:
                    results.append(result)

        return results

    def _record_result(self, result: MaintenanceTaskResult):
        """Registra resultado no histórico."""
        with self._lock:
            self.history.append(result)
            self.stats["total_runs"] += 1

            if result.status == TaskStatus.COMPLETED:
                self.stats["successful_runs"] += 1
            else:
                self.stats["failed_runs"] += 1

            self.stats["total_bytes_freed"] += result.bytes_freed
            self.stats["total_items_removed"] += result.items_removed

            # Limitar histórico
            if len(self.history) > self.max_history:
                self.history = self.history[-self.max_history:]

    def get_history(self, task_name: Optional[str] = None,
                    limit: int = 50) -> List[Dict[str, Any]]:
        """Retorna histórico de execuções."""
        with self._lock:
            history = self.history
            if task_name:
                history = [r for r in history if r.task_name == task_name]
            return [r.to_dict() for r in history[-limit:]]

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do maintenance manager."""
        with self._lock:
            uptime = time.time() - self.stats["started_at"]
            return {
                **self.stats,
                "uptime_hours": round(uptime / 3600, 2),
                "tasks_configured": len(self.tasks),
                "tasks_enabled": sum(1 for t in self.tasks.values() if t.enabled),
                "history_size": len(self.history),
                "success_rate": (
                    self.stats["successful_runs"] / self.stats["total_runs"] * 100
                    if self.stats["total_runs"] > 0 else 0.0
                ),
                "total_mb_freed": round(self.stats["total_bytes_freed"] / (1024*1024), 2)
            }

    def start(self):
        """Inicia worker thread de manutenção."""
        if self._running:
            return
        self._running = True
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def stop(self):
        """Para worker thread."""
        self._running = False
        if self._worker:
            self._worker.join(timeout=5)

    def _worker_loop(self):
        """Loop principal do worker."""
        while self._running:
            try:
                self.run_all_pending()
            except Exception:
                pass
            time.sleep(self._check_interval)

    @classmethod
    def reset(cls):
        """Reset singleton (para testes)."""
        with cls._lock:
            cls._instance = None


def get_maintenance_manager() -> Optional[MaintenanceManager]:
    """Retorna instância singleton do maintenance manager."""
    return MaintenanceManager._instance
