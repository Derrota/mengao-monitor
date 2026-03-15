"""
Data Layer - Persistência unificada para Mengão Monitor 🦞

Abstração de dados com SQLite para:
- Health checks (histórico de verificações)
- Alerts (alertas ativos e resolvidos)
- Metrics (métricas coletadas)
- Incidents (incidentes e MTTR)
- System state (estado do sistema)

Thread-safe, migrations automáticas, zero dependências externas.
"""

import sqlite3
import json
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
from contextlib import contextmanager


class DataType(Enum):
    """Tipos de dados suportados."""
    HEALTH_CHECK = "health_check"
    ALERT = "alert"
    METRIC = "metric"
    INCIDENT = "incident"
    SYSTEM_STATE = "system_state"


@dataclass
class QueryFilter:
    """Filtro para queries."""
    api_name: Optional[str] = None
    status: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    limit: int = 100
    offset: int = 0
    order_by: str = "timestamp"
    order_dir: str = "DESC"


@dataclass
class DataLayerStats:
    """Estatísticas do data layer."""
    total_checks: int = 0
    total_alerts: int = 0
    total_metrics: int = 0
    total_incidents: int = 0
    db_size_bytes: int = 0
    last_vacuum: Optional[str] = None
    connections_active: int = 0


# Schema version atual
SCHEMA_VERSION = 1

# SQL de criação das tabelas
SCHEMA_SQL = """
-- Tabela de versão do schema
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Health checks
CREATE TABLE IF NOT EXISTS health_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_name TEXT NOT NULL,
    url TEXT NOT NULL,
    status TEXT NOT NULL,
    response_time_ms REAL,
    status_code INTEGER,
    error TEXT,
    metadata TEXT,  -- JSON
    timestamp TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_checks_api ON health_checks(api_name, timestamp);
CREATE INDEX IF NOT EXISTS idx_checks_status ON health_checks(status, timestamp);
CREATE INDEX IF NOT EXISTS idx_checks_timestamp ON health_checks(timestamp);

-- Alerts
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id TEXT UNIQUE NOT NULL,
    api_name TEXT NOT NULL,
    level TEXT NOT NULL,  -- L1, L2, L3
    status TEXT NOT NULL,  -- active, acknowledged, resolved, expired
    message TEXT NOT NULL,
    details TEXT,  -- JSON
    created_at TEXT NOT NULL,
    acknowledged_at TEXT,
    resolved_at TEXT,
    expires_at TEXT,
    escalation_count INTEGER DEFAULT 0,
    last_escalation TEXT,
    metadata TEXT  -- JSON
);

CREATE INDEX IF NOT EXISTS idx_alerts_api ON alerts(api_name, status);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status, created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_alert_id ON alerts(alert_id);

-- Metrics (time-series)
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    labels TEXT,  -- JSON dict
    timestamp TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(metric_name, timestamp);
CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics(timestamp);

-- Incidents
CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT UNIQUE NOT NULL,
    api_name TEXT NOT NULL,
    severity TEXT NOT NULL,  -- low, medium, high, critical
    status TEXT NOT NULL,  -- open, investigating, resolved
    title TEXT NOT NULL,
    description TEXT,
    started_at TEXT NOT NULL,
    detected_at TEXT,
    resolved_at TEXT,
    mttr_seconds REAL,
    root_cause TEXT,
    resolution TEXT,
    metadata TEXT  -- JSON
);

CREATE INDEX IF NOT EXISTS idx_incidents_api ON incidents(api_name, status);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status, started_at);

-- System state (key-value)
CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    value_type TEXT DEFAULT 'string',  -- string, int, float, json
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


class DataLayer:
    """
    Camada de persistência unificada.
    
    Features:
    - Thread-safe com connection pooling
    - Migrations automáticas
    - Queries tipadas
    - Backup/restore
    - Zero dependências externas (apenas stdlib)
    """
    
    def __init__(self, db_path: str = "mengao_monitor.db", 
                 auto_vacuum: bool = True,
                 vacuum_interval_hours: int = 24):
        """
        Inicializa data layer.
        
        Args:
            db_path: Caminho do banco SQLite (ou ":memory:")
            auto_vacuum: Se deve fazer VACUUM automático
            vacuum_interval_hours: Intervalo entre VACUUMs
        """
        self.db_path = db_path
        self.auto_vacuum = auto_vacuum
        self.vacuum_interval_hours = vacuum_interval_hours
        self._local = threading.local()
        self._lock = threading.RLock()
        self._stats = DataLayerStats()
        
        # Inicializa schema
        self._init_db()
        
        # Registra métricas iniciais
        self._update_stats()
    
    def _get_conn(self) -> sqlite3.Connection:
        """Retorna conexão thread-local com schema inicializado."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0
            )
            self._local.conn.row_factory = sqlite3.Row
            # PRAGMAs para performance
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn.execute("PRAGMA cache_size=-64000")  # 64MB
            self._local.conn.execute("PRAGMA foreign_keys=ON")
            
            # Garante que schema existe nesta conexão
            cursor = self._local.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='health_checks'"
            )
            if cursor.fetchone() is None:
                self._local.conn.executescript(SCHEMA_SQL)
                self._local.conn.execute(
                    "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
                    (SCHEMA_VERSION,)
                )
                self._local.conn.commit()
        
        return self._local.conn
    
    @contextmanager
    def _transaction(self):
        """Context manager para transações."""
        conn = self._get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    
    def _init_db(self):
        """Inicializa banco e aplica migrations."""
        with self._lock:
            conn = self._get_conn()  # Garante schema criado
            self._update_stats()
    
    def _migrate(self, conn: sqlite3.Connection, from_version: int):
        """Aplica migrations."""
        # Placeholder para migrations futuras
        # if from_version < 2:
        #     conn.execute("ALTER TABLE ...")
        #     conn.execute("INSERT INTO schema_version (version) VALUES (2)")
        
        conn.execute(
            "INSERT INTO schema_version (version) VALUES (?)",
            (SCHEMA_VERSION,)
        )
        conn.commit()
    
    def _update_stats(self):
        """Atualiza estatísticas internas."""
        try:
            conn = self._get_conn()
            
            cursor = conn.execute("SELECT COUNT(*) FROM health_checks")
            self._stats.total_checks = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM alerts")
            self._stats.total_alerts = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM metrics")
            self._stats.total_metrics = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM incidents")
            self._stats.total_incidents = cursor.fetchone()[0]
            
            if self.db_path != ":memory:" and os.path.exists(self.db_path):
                self._stats.db_size_bytes = os.path.getsize(self.db_path)
        except Exception:
            pass  # Stats são best-effort
    
    # ==================== HEALTH CHECKS ====================
    
    def record_check(self, api_name: str, url: str, status: str,
                     response_time_ms: Optional[float] = None,
                     status_code: Optional[int] = None,
                     error: Optional[str] = None,
                     metadata: Optional[Dict] = None,
                     timestamp: Optional[str] = None) -> int:
        """
        Registra um health check.
        
        Returns:
            ID do registro inserido
        """
        ts = timestamp or datetime.now().isoformat()
        
        with self._lock:
            with self._transaction() as conn:
                cursor = conn.execute(
                    """INSERT INTO health_checks 
                       (api_name, url, status, response_time_ms, status_code, error, metadata, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (api_name, url, status, response_time_ms, status_code, 
                     error, json.dumps(metadata) if metadata else None, ts)
                )
                self._stats.total_checks += 1
                return cursor.lastrowid
    
    def get_checks(self, qf: Optional[QueryFilter] = None) -> List[Dict]:
        """Busca health checks com filtros."""
        qf = qf or QueryFilter()
        
        conditions = []
        params = []
        
        if qf.api_name:
            conditions.append("api_name = ?")
            params.append(qf.api_name)
        
        if qf.status:
            conditions.append("status = ?")
            params.append(qf.status)
        
        if qf.start_time:
            conditions.append("timestamp >= ?")
            params.append(qf.start_time)
        
        if qf.end_time:
            conditions.append("timestamp <= ?")
            params.append(qf.end_time)
        
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        
        # Valida order_by para evitar SQL injection
        valid_columns = {"timestamp", "api_name", "status", "response_time_ms", "id"}
        order_by = qf.order_by if qf.order_by in valid_columns else "timestamp"
        order_dir = "DESC" if qf.order_dir.upper() == "DESC" else "ASC"
        
        sql = f"""
            SELECT * FROM health_checks 
            {where}
            ORDER BY {order_by} {order_dir}
            LIMIT ? OFFSET ?
        """
        params.extend([qf.limit, qf.offset])
        
        conn = self._get_conn()
        cursor = conn.execute(sql, params)
        
        results = []
        for row in cursor.fetchall():
            d = dict(row)
            if d.get('metadata'):
                d['metadata'] = json.loads(d['metadata'])
            results.append(d)
        
        return results
    
    def get_uptime(self, api_name: str, hours: int = 24) -> float:
        """Calcula uptime percentual."""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        conn = self._get_conn()
        cursor = conn.execute(
            """SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'up' THEN 1 ELSE 0 END) as up_count
               FROM health_checks
               WHERE api_name = ? AND timestamp >= ?""",
            (api_name, cutoff)
        )
        row = cursor.fetchone()
        
        total = row['total']
        if total == 0:
            return 100.0  # Sem dados = assume OK
        
        return round((row['up_count'] / total) * 100, 2)
    
    def get_avg_response_time(self, api_name: str, hours: int = 24) -> Optional[float]:
        """Calcula tempo médio de resposta."""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        conn = self._get_conn()
        cursor = conn.execute(
            """SELECT AVG(response_time_ms) as avg_time
               FROM health_checks
               WHERE api_name = ? AND timestamp >= ? AND response_time_ms IS NOT NULL""",
            (api_name, cutoff)
        )
        row = cursor.fetchone()
        
        return round(row['avg_time'], 2) if row['avg_time'] else None
    
    def get_percentile_response_time(self, api_name: str, percentile: int = 95, 
                                     hours: int = 24) -> Optional[float]:
        """Calcula percentil de tempo de resposta (p50, p95, p99)."""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        conn = self._get_conn()
        cursor = conn.execute(
            """SELECT response_time_ms
               FROM health_checks
               WHERE api_name = ? AND timestamp >= ? AND response_time_ms IS NOT NULL
               ORDER BY response_time_ms""",
            (api_name, cutoff)
        )
        times = [row['response_time_ms'] for row in cursor.fetchall()]
        
        if not times:
            return None
        
        idx = int(len(times) * (percentile / 100))
        return round(times[min(idx, len(times) - 1)], 2)
    
    # ==================== ALERTS ====================
    
    def record_alert(self, alert_id: str, api_name: str, level: str,
                     message: str, status: str = "active",
                     details: Optional[Dict] = None,
                     expires_at: Optional[str] = None,
                     metadata: Optional[Dict] = None) -> int:
        """Registra um alerta."""
        now = datetime.now().isoformat()
        
        with self._lock:
            with self._transaction() as conn:
                cursor = conn.execute(
                    """INSERT OR REPLACE INTO alerts
                       (alert_id, api_name, level, status, message, details, 
                        created_at, expires_at, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (alert_id, api_name, level, status, message,
                     json.dumps(details) if details else None,
                     now, expires_at, json.dumps(metadata) if metadata else None)
                )
                self._stats.total_alerts += 1
                return cursor.lastrowid
    
    def update_alert_status(self, alert_id: str, status: str) -> bool:
        """Atualiza status de um alerta."""
        now = datetime.now().isoformat()
        
        with self._lock:
            with self._transaction() as conn:
                if status == "acknowledged":
                    cursor = conn.execute(
                        "UPDATE alerts SET status = ?, acknowledged_at = ? WHERE alert_id = ?",
                        (status, now, alert_id)
                    )
                elif status == "resolved":
                    cursor = conn.execute(
                        "UPDATE alerts SET status = ?, resolved_at = ? WHERE alert_id = ?",
                        (status, now, alert_id)
                    )
                else:
                    cursor = conn.execute(
                        "UPDATE alerts SET status = ? WHERE alert_id = ?",
                        (status, alert_id)
                    )
                return cursor.rowcount > 0
    
    def get_alerts(self, api_name: Optional[str] = None, 
                   status: Optional[str] = None,
                   limit: int = 50) -> List[Dict]:
        """Busca alertas."""
        conditions = []
        params = []
        
        if api_name:
            conditions.append("api_name = ?")
            params.append(api_name)
        
        if status:
            conditions.append("status = ?")
            params.append(status)
        
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        
        conn = self._get_conn()
        cursor = conn.execute(
            f"SELECT * FROM alerts {where} ORDER BY created_at DESC LIMIT ?",
            params + [limit]
        )
        
        results = []
        for row in cursor.fetchall():
            d = dict(row)
            if d.get('details'):
                d['details'] = json.loads(d['details'])
            if d.get('metadata'):
                d['metadata'] = json.loads(d['metadata'])
            results.append(d)
        
        return results
    
    def escalate_alert(self, alert_id: str, new_level: str) -> bool:
        """Escala um alerta para novo nível."""
        now = datetime.now().isoformat()
        
        with self._lock:
            with self._transaction() as conn:
                cursor = conn.execute(
                    """UPDATE alerts 
                       SET level = ?, escalation_count = escalation_count + 1, 
                           last_escalation = ?
                       WHERE alert_id = ? AND status = 'active'""",
                    (new_level, now, alert_id)
                )
                return cursor.rowcount > 0
    
    # ==================== METRICS ====================
    
    def record_metric(self, metric_name: str, metric_value: float,
                      labels: Optional[Dict] = None,
                      timestamp: Optional[str] = None) -> int:
        """Registra uma métrica."""
        ts = timestamp or datetime.now().isoformat()
        
        with self._lock:
            with self._transaction() as conn:
                cursor = conn.execute(
                    """INSERT INTO metrics (metric_name, metric_value, labels, timestamp)
                       VALUES (?, ?, ?, ?)""",
                    (metric_name, metric_value, 
                     json.dumps(labels) if labels else None, ts)
                )
                self._stats.total_metrics += 1
                return cursor.lastrowid
    
    def get_metrics(self, metric_name: str, 
                    start_time: Optional[str] = None,
                    end_time: Optional[str] = None,
                    labels: Optional[Dict] = None,
                    limit: int = 1000) -> List[Dict]:
        """Busca métricas."""
        conditions = ["metric_name = ?"]
        params = [metric_name]
        
        if start_time:
            conditions.append("timestamp >= ?")
            params.append(start_time)
        
        if end_time:
            conditions.append("timestamp <= ?")
            params.append(end_time)
        
        where = "WHERE " + " AND ".join(conditions)
        
        conn = self._get_conn()
        cursor = conn.execute(
            f"SELECT * FROM metrics {where} ORDER BY timestamp DESC LIMIT ?",
            params + [limit]
        )
        
        results = []
        for row in cursor.fetchall():
            d = dict(row)
            if d.get('labels'):
                d['labels'] = json.loads(d['labels'])
            
            # Filtra por labels se especificado
            if labels:
                row_labels = d.get('labels', {})
                if all(row_labels.get(k) == v for k, v in labels.items()):
                    results.append(d)
            else:
                results.append(d)
        
        return results
    
    def get_metric_aggregate(self, metric_name: str, 
                             aggregation: str = "avg",
                             hours: int = 24) -> Optional[float]:
        """Agrega métricas (avg, sum, min, max, count)."""
        valid_aggs = {"avg": "AVG", "sum": "SUM", "min": "MIN", "max": "MAX", "count": "COUNT"}
        agg_func = valid_aggs.get(aggregation.lower(), "AVG")
        
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        conn = self._get_conn()
        cursor = conn.execute(
            f"SELECT {agg_func}(metric_value) as result FROM metrics WHERE metric_name = ? AND timestamp >= ?",
            (metric_name, cutoff)
        )
        row = cursor.fetchone()
        
        return round(row['result'], 4) if row['result'] is not None else None
    
    # ==================== INCIDENTS ====================
    
    def record_incident(self, incident_id: str, api_name: str, severity: str,
                        title: str, description: Optional[str] = None,
                        status: str = "open",
                        started_at: Optional[str] = None,
                        metadata: Optional[Dict] = None) -> int:
        """Registra um incidente."""
        now = datetime.now().isoformat()
        
        with self._lock:
            with self._transaction() as conn:
                cursor = conn.execute(
                    """INSERT OR REPLACE INTO incidents
                       (incident_id, api_name, severity, status, title, description,
                        started_at, detected_at, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (incident_id, api_name, severity, status, title, description,
                     started_at or now, now, json.dumps(metadata) if metadata else None)
                )
                self._stats.total_incidents += 1
                return cursor.lastrowid
    
    def resolve_incident(self, incident_id: str, resolution: str,
                         root_cause: Optional[str] = None) -> bool:
        """Resolve um incidente e calcula MTTR."""
        now = datetime.now().isoformat()
        
        with self._lock:
            with self._transaction() as conn:
                # Busca started_at para calcular MTTR
                cursor = conn.execute(
                    "SELECT started_at FROM incidents WHERE incident_id = ?",
                    (incident_id,)
                )
                row = cursor.fetchone()
                
                mttr_seconds = None
                if row and row['started_at']:
                    started = datetime.fromisoformat(row['started_at'])
                    resolved = datetime.now()
                    mttr_seconds = (resolved - started).total_seconds()
                
                cursor = conn.execute(
                    """UPDATE incidents 
                       SET status = 'resolved', resolved_at = ?, resolution = ?,
                           root_cause = ?, mttr_seconds = ?
                       WHERE incident_id = ?""",
                    (now, resolution, root_cause, mttr_seconds, incident_id)
                )
                return cursor.rowcount > 0
    
    def get_incidents(self, api_name: Optional[str] = None,
                      status: Optional[str] = None,
                      limit: int = 50) -> List[Dict]:
        """Busca incidentes."""
        conditions = []
        params = []
        
        if api_name:
            conditions.append("api_name = ?")
            params.append(api_name)
        
        if status:
            conditions.append("status = ?")
            params.append(status)
        
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        
        conn = self._get_conn()
        cursor = conn.execute(
            f"SELECT * FROM incidents {where} ORDER BY started_at DESC LIMIT ?",
            params + [limit]
        )
        
        results = []
        for row in cursor.fetchall():
            d = dict(row)
            if d.get('metadata'):
                d['metadata'] = json.loads(d['metadata'])
            results.append(d)
        
        return results
    
    def get_mttr(self, api_name: Optional[str] = None, hours: int = 168) -> Optional[float]:
        """Calcula MTTR médio (default: última semana)."""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        conditions = ["status = 'resolved'", "mttr_seconds IS NOT NULL", "resolved_at >= ?"]
        params = [cutoff]
        
        if api_name:
            conditions.append("api_name = ?")
            params.append(api_name)
        
        where = "WHERE " + " AND ".join(conditions)
        
        conn = self._get_conn()
        cursor = conn.execute(
            f"SELECT AVG(mttr_seconds) as avg_mttr FROM incidents {where}",
            params
        )
        row = cursor.fetchone()
        
        return round(row['avg_mttr'], 2) if row['avg_mttr'] else None
    
    # ==================== SYSTEM STATE ====================
    
    def set_state(self, key: str, value: Any, value_type: Optional[str] = None):
        """Armazena estado do sistema."""
        if value_type is None:
            if isinstance(value, bool):
                value_type = "bool"
                value = str(value)
            elif isinstance(value, int):
                value_type = "int"
                value = str(value)
            elif isinstance(value, float):
                value_type = "float"
                value = str(value)
            elif isinstance(value, (dict, list)):
                value_type = "json"
                value = json.dumps(value)
            else:
                value_type = "string"
                value = str(value)
        else:
            value = str(value)
        
        with self._lock:
            with self._transaction() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO system_state (key, value, value_type, updated_at)
                       VALUES (?, ?, ?, ?)""",
                    (key, value, value_type, datetime.now().isoformat())
                )
    
    def get_state(self, key: str, default: Any = None) -> Any:
        """Recupera estado do sistema."""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT value, value_type FROM system_state WHERE key = ?",
            (key,)
        )
        row = cursor.fetchone()
        
        if row is None:
            return default
        
        value, value_type = row['value'], row['value_type']
        
        if value_type == "int":
            return int(value)
        elif value_type == "float":
            return float(value)
        elif value_type == "bool":
            return value.lower() == "true"
        elif value_type == "json":
            return json.loads(value)
        else:
            return value
    
    def delete_state(self, key: str) -> bool:
        """Remove estado."""
        with self._lock:
            with self._transaction() as conn:
                cursor = conn.execute("DELETE FROM system_state WHERE key = ?", (key,))
                return cursor.rowcount > 0
    
    # ==================== MAINTENANCE ====================
    
    def vacuum(self):
        """Executa VACUUM para reorganizar banco."""
        with self._lock:
            conn = self._get_conn()
            conn.execute("VACUUM")
            self._stats.last_vacuum = datetime.now().isoformat()
            self._update_stats()
    
    def cleanup_old_data(self, days: int = 30):
        """Remove dados antigos."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        with self._lock:
            with self._transaction() as conn:
                # Health checks antigos
                conn.execute("DELETE FROM health_checks WHERE timestamp < ?", (cutoff,))
                
                # Métricas antigas
                conn.execute("DELETE FROM metrics WHERE timestamp < ?", (cutoff,))
                
                # Alertas resolvidos antigos
                conn.execute(
                    "DELETE FROM alerts WHERE status = 'resolved' AND resolved_at < ?",
                    (cutoff,)
                )
                
                # Incidentes resolvidos antigos
                conn.execute(
                    "DELETE FROM incidents WHERE status = 'resolved' AND resolved_at < ?",
                    (cutoff,)
                )
            
            self._update_stats()
    
    def get_stats(self) -> DataLayerStats:
        """Retorna estatísticas do data layer."""
        self._update_stats()
        return self._stats
    
    def backup(self, backup_path: str) -> bool:
        """Cria backup do banco."""
        if self.db_path == ":memory:":
            return False
        
        try:
            import shutil
            shutil.copy2(self.db_path, backup_path)
            return True
        except Exception:
            return False
    
    def close(self):
        """Fecha conexões."""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
