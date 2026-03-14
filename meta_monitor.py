"""
Meta-Monitoring para Mengão Monitor 🦞
Monitora a saúde do próprio processo: uptime, memória, threads, response time.
v2.7: Meta-monitoring com self-diagnostics e watchdog.
Sem dependências externas — apenas módulos padrão do Python.
"""

import os
import time
import threading
import resource
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum


class HealthStatus(Enum):
    """Status de saúde do meta-monitor."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ProcessMetrics:
    """Métricas do processo atual."""
    pid: int
    cpu_seconds_user: float
    cpu_seconds_system: float
    memory_rss_mb: float
    memory_vms_mb: float
    threads: int
    uptime_seconds: float
    start_time: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'pid': self.pid,
            'cpu_seconds_user': round(self.cpu_seconds_user, 2),
            'cpu_seconds_system': round(self.cpu_seconds_system, 2),
            'cpu_seconds_total': round(self.cpu_seconds_user + self.cpu_seconds_system, 2),
            'memory_rss_mb': round(self.memory_rss_mb, 2),
            'memory_vms_mb': round(self.memory_vms_mb, 2),
            'threads': self.threads,
            'uptime_seconds': round(self.uptime_seconds, 2),
            'start_time': datetime.fromtimestamp(self.start_time).isoformat()
        }


@dataclass
class HealthCheckResult:
    """Resultado de um health check individual."""
    name: str
    status: HealthStatus
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    duration_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'status': self.status.value,
            'message': self.message,
            'details': self.details,
            'timestamp': self.timestamp,
            'duration_ms': round(self.duration_ms, 2)
        }


class MetaMonitor:
    """Monitora a saúde do próprio Mengão Monitor."""
    
    def __init__(self, check_interval: int = 30):
        self.check_interval = check_interval
        self.pid = os.getpid()
        self.start_time = time.time()
        self.checks_history: List[HealthCheckResult] = []
        self.max_history = 1000
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # Thresholds configuráveis
        self.thresholds = {
            'memory_rss_mb': 500.0,  # Alerta se > 500MB
            'threads': 50,  # Alerta se > 50 threads
            'uptime_seconds': 0,  # 0 = sem alerta de uptime
        }
    
    def collect_process_metrics(self) -> ProcessMetrics:
        """Coleta métricas do processo atual usando módulos padrão."""
        try:
            # Resource usage
            usage = resource.getrusage(resource.RUSAGE_SELF)
            
            # Memory info from /proc/self/status (Linux)
            memory_rss_mb = 0.0
            memory_vms_mb = 0.0
            
            try:
                with open('/proc/self/status', 'r') as f:
                    for line in f:
                        if line.startswith('VmRSS:'):
                            # VmRSS:    12345 kB
                            parts = line.split()
                            if len(parts) >= 2:
                                memory_rss_mb = float(parts[1]) / 1024
                        elif line.startswith('VmSize:'):
                            parts = line.split()
                            if len(parts) >= 2:
                                memory_vms_mb = float(parts[1]) / 1204
            except (FileNotFoundError, IOError, ValueError):
                # Fallback: estimate from resource module
                # ru_maxrss is in KB on Linux
                memory_rss_mb = usage.ru_maxrss / 1024
            
            # Threads
            threads = threading.active_count()
            
            # Uptime
            uptime = time.time() - self.start_time
            
            return ProcessMetrics(
                pid=self.pid,
                cpu_seconds_user=usage.ru_utime,
                cpu_seconds_system=usage.ru_stime,
                memory_rss_mb=memory_rss_mb,
                memory_vms_mb=memory_vms_mb,
                threads=threads,
                uptime_seconds=uptime,
                start_time=self.start_time
            )
        except Exception as e:
            # Fallback metrics
            return ProcessMetrics(
                pid=self.pid,
                cpu_seconds_user=0.0,
                cpu_seconds_system=0.0,
                memory_rss_mb=0.0,
                memory_vms_mb=0.0,
                threads=threading.active_count(),
                uptime_seconds=time.time() - self.start_time,
                start_time=self.start_time
            )
    
    def check_process_health(self) -> HealthCheckResult:
        """Verifica saúde geral do processo."""
        start = time.time()
        metrics = self.collect_process_metrics()
        
        issues = []
        status = HealthStatus.HEALTHY
        
        # Verificar memória RSS
        if metrics.memory_rss_mb > self.thresholds['memory_rss_mb']:
            issues.append(f"Memória alta: {metrics.memory_rss_mb:.1f}MB")
            status = HealthStatus.DEGRADED
        
        # Verificar threads
        if metrics.threads > self.thresholds['threads']:
            issues.append(f"Muitas threads: {metrics.threads}")
            status = HealthStatus.DEGRADED
        
        message = "Processo saudável" if not issues else "; ".join(issues)
        duration = (time.time() - start) * 1000
        
        return HealthCheckResult(
            name="process_health",
            status=status,
            message=message,
            details=metrics.to_dict(),
            duration_ms=duration
        )
    
    def check_thread_health(self) -> HealthCheckResult:
        """Verifica saúde das threads."""
        start = time.time()
        
        threads = threading.enumerate()
        thread_info = []
        
        for t in threads:
            thread_info.append({
                'name': t.name,
                'daemon': t.daemon,
                'alive': t.is_alive(),
                'ident': t.ident
            })
        
        # Verificar threads mortas
        dead_threads = [t for t in threads if not t.is_alive()]
        
        status = HealthStatus.HEALTHY
        message = f"{len(threads)} threads ativas"
        
        if dead_threads:
            status = HealthStatus.DEGRADED
            message += f", {len(dead_threads)} mortas"
        
        duration = (time.time() - start) * 1000
        
        return HealthCheckResult(
            name="thread_health",
            status=status,
            message=message,
            details={
                'total_threads': len(threads),
                'alive_threads': len(threads) - len(dead_threads),
                'dead_threads': len(dead_threads),
                'threads': thread_info
            },
            duration_ms=duration
        )
    
    def check_memory_health(self) -> HealthCheckResult:
        """Verifica detalhes de memória via /proc."""
        start = time.time()
        
        details = {}
        status = HealthStatus.HEALTHY
        message = "Memória OK"
        
        try:
            # Ler /proc/self/status para info detalhada
            with open('/proc/self/status', 'r') as f:
                for line in f:
                    if line.startswith('VmRSS:'):
                        parts = line.split()
                        if len(parts) >= 2:
                            details['rss_mb'] = round(float(parts[1]) / 1024, 2)
                    elif line.startswith('VmSize:'):
                        parts = line.split()
                        if len(parts) >= 2:
                            details['vms_mb'] = round(float(parts[1]) / 1024, 2)
                    elif line.startswith('VmData:'):
                        parts = line.split()
                        if len(parts) >= 2:
                            details['data_mb'] = round(float(parts[1]) / 1024, 2)
                    elif line.startswith('VmStk:'):
                        parts = line.split()
                        if len(parts) >= 2:
                            details['stack_mb'] = round(float(parts[1]) / 1024, 2)
                    elif line.startswith('Threads:'):
                        parts = line.split()
                        if len(parts) >= 2:
                            details['threads'] = int(parts[1])
            
            # System memory from /proc/meminfo
            with open('/proc/meminfo', 'r') as f:
                meminfo = {}
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        key = parts[0].rstrip(':')
                        value = float(parts[1])
                        meminfo[key] = value
                
                if 'MemTotal' in meminfo:
                    details['system_total_mb'] = round(meminfo['MemTotal'] / 1024, 2)
                if 'MemAvailable' in meminfo:
                    details['system_available_mb'] = round(meminfo['MemAvailable'] / 1024, 2)
                if 'MemFree' in meminfo:
                    details['system_free_mb'] = round(meminfo['MemFree'] / 1024, 2)
                
                # Calcular percentual de uso do sistema
                if 'MemTotal' in meminfo and 'MemAvailable' in meminfo:
                    used = meminfo['MemTotal'] - meminfo['MemAvailable']
                    details['system_percent'] = round((used / meminfo['MemTotal']) * 100, 2)
            
            rss_mb = details.get('rss_mb', 0)
            if rss_mb > self.thresholds['memory_rss_mb']:
                status = HealthStatus.DEGRADED
                message = f"Alto uso de memória: {rss_mb:.1f}MB"
            else:
                message = f"Memória OK: {rss_mb:.1f}MB RSS"
                
        except (FileNotFoundError, IOError, ValueError) as e:
            status = HealthStatus.UNKNOWN
            message = f"Não foi possível acessar informações de memória: {e}"
        
        duration = (time.time() - start) * 1000
        
        return HealthCheckResult(
            name="memory_health",
            status=status,
            message=message,
            details=details,
            duration_ms=duration
        )
    
    def check_uptime_health(self) -> HealthCheckResult:
        """Verifica uptime e estabilidade."""
        start = time.time()
        
        uptime = time.time() - self.start_time
        uptime_td = timedelta(seconds=int(uptime))
        
        # Formatar uptime
        days = uptime_td.days
        hours, remainder = divmod(uptime_td.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if days > 0:
            uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"
        elif hours > 0:
            uptime_str = f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            uptime_str = f"{minutes}m {seconds}s"
        else:
            uptime_str = f"{seconds}s"
        
        # Verificar histórico de checks
        recent_checks = len([c for c in self.checks_history[-100:] 
                           if c.status != HealthStatus.HEALTHY])
        
        status = HealthStatus.HEALTHY
        message = f"Uptime: {uptime_str}"
        
        if recent_checks > 10:
            status = HealthStatus.DEGRADED
            message += f" ({recent_checks} issues nos últimos 100 checks)"
        
        duration = (time.time() - start) * 1000
        
        return HealthCheckResult(
            name="uptime_health",
            status=status,
            message=message,
            details={
                'uptime_seconds': round(uptime, 2),
                'uptime_formatted': uptime_str,
                'started_at': datetime.fromtimestamp(self.start_time).isoformat(),
                'recent_issues': recent_checks
            },
            duration_ms=duration
        )
    
    def check_io_health(self) -> HealthCheckResult:
        """Verifica I/O do processo via /proc/self/io."""
        start = time.time()
        
        details = {}
        status = HealthStatus.HEALTHY
        message = "I/O OK"
        
        try:
            with open('/proc/self/io', 'r') as f:
                for line in f:
                    parts = line.split(':')
                    if len(parts) == 2:
                        key = parts[0].strip()
                        value = int(parts[1].strip())
                        
                        # Converter para MB
                        if key in ('read_bytes', 'write_bytes'):
                            details[f'{key}_mb'] = round(value / 1024 / 1024, 2)
                        else:
                            details[key] = value
            
            message = f"I/O: {details.get('read_bytes_mb', 0):.1f}MB read, {details.get('write_bytes_mb', 0):.1f}MB written"
            
        except (FileNotFoundError, IOError, ValueError) as e:
            status = HealthStatus.UNKNOWN
            message = f"Não foi possível acessar informações de I/O: {e}"
        
        duration = (time.time() - start) * 1000
        
        return HealthCheckResult(
            name="io_health",
            status=status,
            message=message,
            details=details,
            duration_ms=duration
        )
    
    def run_all_checks(self) -> Dict[str, HealthCheckResult]:
        """Executa todos os health checks."""
        checks = {
            'process': self.check_process_health(),
            'threads': self.check_thread_health(),
            'memory': self.check_memory_health(),
            'uptime': self.check_uptime_health(),
            'io': self.check_io_health(),
        }
        
        # Adicionar ao histórico
        with self._lock:
            for check in checks.values():
                self.checks_history.append(check)
            
            # Manter apenas últimos N checks
            if len(self.checks_history) > self.max_history:
                self.checks_history = self.checks_history[-self.max_history:]
        
        return checks
    
    def get_overall_status(self) -> Dict[str, Any]:
        """Retorna status geral do meta-monitor."""
        checks = self.run_all_checks()
        
        # Determinar status geral
        statuses = [c.status for c in checks.values()]
        
        if HealthStatus.UNHEALTHY in statuses:
            overall = HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            overall = HealthStatus.DEGRADED
        elif HealthStatus.UNKNOWN in statuses:
            overall = HealthStatus.UNKNOWN
        else:
            overall = HealthStatus.HEALTHY
        
        return {
            'overall_status': overall.value,
            'checks': {name: check.to_dict() for name, check in checks.items()},
            'timestamp': datetime.now().isoformat(),
            'history_size': len(self.checks_history)
        }
    
    def get_history(self, limit: int = 100, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retorna histórico de health checks."""
        with self._lock:
            history = self.checks_history[-limit:]
            
            if status_filter:
                history = [c for c in history if c.status.value == status_filter]
            
            return [c.to_dict() for c in history]
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do meta-monitor."""
        with self._lock:
            total = len(self.checks_history)
            
            if total == 0:
                return {
                    'total_checks': 0,
                    'healthy': 0,
                    'degraded': 0,
                    'unhealthy': 0,
                    'unknown': 0,
                    'health_percentage': 100.0
                }
            
            status_counts = {}
            for check in self.checks_history:
                status = check.status.value
                status_counts[status] = status_counts.get(status, 0) + 1
            
            healthy = status_counts.get('healthy', 0)
            health_percentage = (healthy / total) * 100
            
            return {
                'total_checks': total,
                'healthy': healthy,
                'degraded': status_counts.get('degraded', 0),
                'unhealthy': status_counts.get('unhealthy', 0),
                'unknown': status_counts.get('unknown', 0),
                'health_percentage': round(health_percentage, 2)
            }
    
    def start_watchdog(self):
        """Inicia thread watchdog que verifica saúde periodicamente."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._watchdog_loop, daemon=True, name="meta-watchdog")
        self._thread.start()
    
    def stop_watchdog(self):
        """Para thread watchdog."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
    
    def _watchdog_loop(self):
        """Loop principal do watchdog."""
        while self._running:
            try:
                self.run_all_checks()
            except Exception as e:
                # Log error mas continua
                pass
            
            time.sleep(self.check_interval)


# Instância global
meta_monitor = MetaMonitor()


def get_meta_monitor() -> MetaMonitor:
    """Retorna instância global do meta-monitor."""
    return meta_monitor
