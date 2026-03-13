"""
Uptime History com SQLite para Mengão Monitor 🦞
Armazena histórico de verificações para análise de uptime.
"""

import sqlite3
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple


class UptimeHistory:
    """Gerencia histórico de verificações em SQLite."""
    
    def __init__(self, db_path: str = "uptime.db"):
        self.db_path = db_path
        self._conn = None
        if db_path == ":memory:":
            self._conn = sqlite3.connect(db_path)
            self._init_db(self._conn)
        else:
            self._init_db()
    
    def _init_db(self, conn=None):
        """Cria tabelas se não existirem."""
        close_conn = False
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            close_conn = True
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    api_name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    status TEXT NOT NULL,
                    response_time REAL,
                    error TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_checks_api 
                ON checks(api_name, timestamp)
            """)
            
            conn.commit()
        finally:
            if close_conn:
                conn.close()
    
    def _get_conn(self):
        """Retorna conexão apropriada."""
        if self._conn:
            return self._conn
        return sqlite3.connect(self.db_path)
    
    def record_check(self, result: Dict):
        """Registra uma verificação."""
        conn = self._get_conn()
        # Aceita tanto 'response_time' quanto 'response_time_ms'
        response_time = result.get('response_time', result.get('response_time_ms'))
        
        if self._conn:
            # Reuse persistent connection for :memory:
            conn.execute(
                """INSERT INTO checks (api_name, url, status, response_time, error, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    result['name'],
                    result['url'],
                    result['status'],
                    response_time,
                    result.get('error'),
                    result.get('timestamp', datetime.now().isoformat())
                )
            )
            conn.commit()
        else:
            # File-based: open/close each time
            with conn as c:
                c.execute(
                    """INSERT INTO checks (api_name, url, status, response_time, error, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        result['name'],
                        result['url'],
                        result['status'],
                        response_time,
                        result.get('error'),
                        result.get('timestamp', datetime.now().isoformat())
                    )
                )
                c.commit()
    
    def get_uptime(self, api_name: str, hours: int = 24) -> float:
        """Calcula uptime percentual de uma API nas últimas N horas."""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        conn = self._get_conn()
        cursor = conn.execute(
            """SELECT 
                   COUNT(*) as total,
                   SUM(CASE WHEN status = 'online' THEN 1 ELSE 0 END) as online
               FROM checks 
               WHERE api_name = ? AND timestamp > ?""",
            (api_name, cutoff)
        )
        row = cursor.fetchone()
        
        if not self._conn:
            conn.close()
        
        total = row[0]
        online = row[1] or 0
        
        if total == 0:
            return 0.0
        
        return round((online / total) * 100, 2)
    
    def get_avg_response_time(self, api_name: str, hours: int = 24) -> Optional[float]:
        """Calcula tempo de resposta médio."""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        conn = self._get_conn()
        cursor = conn.execute(
            """SELECT AVG(response_time) 
               FROM checks 
               WHERE api_name = ? AND timestamp > ? AND response_time IS NOT NULL""",
            (api_name, cutoff)
        )
        row = cursor.fetchone()
        
        if not self._conn:
            conn.close()
        
        return round(row[0], 3) if row[0] else None
    
    def get_recent_checks(self, api_name: str, limit: int = 10) -> List[Dict]:
        """Retorna últimas verificações de uma API."""
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """SELECT * FROM checks 
               WHERE api_name = ? 
               ORDER BY timestamp DESC 
               LIMIT ?""",
            (api_name, limit)
        )
        
        result = [dict(row) for row in cursor.fetchall()]
        
        if not self._conn:
            conn.close()
        
        return result
    
    def get_all_apis_stats(self, hours: int = 24) -> Dict[str, Dict]:
        """Retorna stats de todas as APIs monitoradas."""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        conn = self._get_conn()
        cursor = conn.execute(
            """SELECT 
                   api_name,
                   COUNT(*) as total_checks,
                   SUM(CASE WHEN status = 'online' THEN 1 ELSE 0 END) as online_checks,
                   AVG(response_time) as avg_response_time,
                   MAX(timestamp) as last_check
               FROM checks 
               WHERE timestamp > ?
               GROUP BY api_name""",
            (cutoff,)
        )
        
        stats = {}
        for row in cursor.fetchall():
            api_name = row[0]
            total = row[1]
            online = row[2] or 0
            
            stats[api_name] = {
                'total_checks': total,
                'online_checks': online,
                'uptime_percent': round((online / total) * 100, 2) if total > 0 else 0,
                'avg_response_time': round(row[3], 3) if row[3] else None,
                'last_check': row[4]
            }
        
        if not self._conn:
            conn.close()
        
        return stats
    
    def cleanup_old_records(self, days: int = 30):
        """Remove registros mais antigos que N dias."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        conn = self._get_conn()
        cursor = conn.execute(
            "DELETE FROM checks WHERE timestamp < ?",
            (cutoff,)
        )
        deleted = cursor.rowcount
        conn.commit()
        
        if not self._conn:
            conn.close()
        
        return deleted
    
    def export_csv(self, output_file: str, hours: int = 24) -> int:
        """Exporta histórico para CSV."""
        import csv
        
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        conn = self._get_conn()
        cursor = conn.execute(
            """SELECT api_name, url, status, response_time, error, timestamp
               FROM checks 
               WHERE timestamp > ?
               ORDER BY timestamp DESC""",
            (cutoff,)
        )
        rows = cursor.fetchall()
        
        if not self._conn:
            conn.close()
        
        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['API', 'URL', 'Status', 'Response Time', 'Error', 'Timestamp'])
            writer.writerows(rows)
        
        return len(rows)
