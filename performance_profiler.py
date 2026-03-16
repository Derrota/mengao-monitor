"""
Performance Profiler para Mengão Monitor v3.7

Mede tempo de execução, identifica gargalos e detecta regressões.
"""

import time
import threading
import functools
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from collections import defaultdict
from datetime import datetime, timedelta
import json


@dataclass
class ProfileEntry:
    """Uma entrada de profiling."""
    name: str
    duration_ms: float
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "duration_ms": round(self.duration_ms, 3),
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }


@dataclass
class ProfileStats:
    """Estatísticas agregadas de uma função/módulo."""
    name: str
    count: int
    total_ms: float
    avg_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    min_ms: float
    max_ms: float
    std_dev_ms: float
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "count": self.count,
            "total_ms": round(self.total_ms, 3),
            "avg_ms": round(self.avg_ms, 3),
            "p50_ms": round(self.p50_ms, 3),
            "p95_ms": round(self.p95_ms, 3),
            "p99_ms": round(self.p99_ms, 3),
            "min_ms": round(self.min_ms, 3),
            "max_ms": round(self.max_ms, 3),
            "std_dev_ms": round(self.std_dev_ms, 3)
        }


@dataclass
class RegressionAlert:
    """Alerta de regressão de performance."""
    name: str
    baseline_avg_ms: float
    current_avg_ms: float
    regression_pct: float
    threshold_pct: float
    detected_at: float
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "baseline_avg_ms": round(self.baseline_avg_ms, 3),
            "current_avg_ms": round(self.current_avg_ms, 3),
            "regression_pct": round(self.regression_pct, 2),
            "threshold_pct": round(self.threshold_pct, 2),
            "detected_at": self.detected_at
        }


class PerformanceProfiler:
    """
    Profiler de performance para Mengão Monitor.
    
    Features:
    - Medição de tempo de execução com decorator ou context manager
    - Estatísticas agregadas (avg, p50, p95, p99)
    - Detecção de regressão automática
    - Histórico com limite configurável
    - Thread-safe
    """
    
    def __init__(
        self,
        max_history: int = 10000,
        regression_threshold_pct: float = 20.0,
        regression_window: int = 100
    ):
        """
        Args:
            max_history: Máximo de entradas no histórico
            regression_threshold_pct: % de aumento para considerar regressão
            regression_window: Número de amostras para baseline
        """
        self.max_history = max_history
        self.regression_threshold_pct = regression_threshold_pct
        self.regression_window = regression_window
        
        self._entries: Dict[str, List[ProfileEntry]] = defaultdict(list)
        self._baselines: Dict[str, float] = {}
        self._regressions: List[RegressionAlert] = []
        self._lock = threading.RLock()
        self._enabled = True
        
        # Stats
        self._stats = {
            "total_profiles": 0,
            "regressions_detected": 0,
            "started_at": time.time()
        }
    
    @property
    def enabled(self) -> bool:
        return self._enabled
    
    def enable(self):
        """Habilita profiling."""
        self._enabled = True
    
    def disable(self):
        """Desabilita profiling (overhead zero)."""
        self._enabled = False
    
    def record(self, name: str, duration_ms: float, metadata: Optional[Dict] = None):
        """
        Registra uma medição.
        
        Args:
            name: Nome da função/módulo
            duration_ms: Duração em milissegundos
            metadata: Metadados opcionais
        """
        if not self._enabled:
            return
        
        entry = ProfileEntry(
            name=name,
            duration_ms=duration_ms,
            timestamp=time.time(),
            metadata=metadata or {}
        )
        
        with self._lock:
            entries = self._entries[name]
            entries.append(entry)
            
            # Trim histórico
            if len(entries) > self.max_history:
                self._entries[name] = entries[-self.max_history:]
            
            self._stats["total_profiles"] += 1
            
            # Verificar regressão
            self._check_regression(name, duration_ms)
    
    def _check_regression(self, name: str, current_ms: float):
        """Verifica se houve regressão comparado ao baseline."""
        entries = self._entries[name]
        
        # Precisa de amostras suficientes
        if len(entries) < self.regression_window:
            return
        
        # Calcular baseline (primeiras N amostras)
        baseline_entries = entries[:self.regression_window]
        baseline_avg = statistics.mean(e.duration_ms for e in baseline_entries)
        
        # Calcular média recente (últimas N amostras)
        recent_entries = entries[-self.regression_window:]
        recent_avg = statistics.mean(e.duration_ms for e in recent_entries)
        
        # Verificar regressão
        if baseline_avg > 0:
            regression_pct = ((recent_avg - baseline_avg) / baseline_avg) * 100
            
            if regression_pct > self.regression_threshold_pct:
                alert = RegressionAlert(
                    name=name,
                    baseline_avg_ms=baseline_avg,
                    current_avg_ms=recent_avg,
                    regression_pct=regression_pct,
                    threshold_pct=self.regression_threshold_pct,
                    detected_at=time.time()
                )
                
                with self._lock:
                    self._regressions.append(alert)
                    self._stats["regressions_detected"] += 1
                    
                    # Atualizar baseline para evitar alertas repetidos
                    self._baselines[name] = recent_avg
    
    def get_stats(self, name: str) -> Optional[ProfileStats]:
        """Retorna estatísticas de uma função/módulo."""
        with self._lock:
            entries = self._entries.get(name)
            if not entries:
                return None
            
            durations = [e.duration_ms for e in entries]
            durations.sort()
            
            count = len(durations)
            total = sum(durations)
            avg = total / count
            
            # Percentis
            p50_idx = int(count * 0.50)
            p95_idx = int(count * 0.95)
            p99_idx = int(count * 0.99)
            
            return ProfileStats(
                name=name,
                count=count,
                total_ms=total,
                avg_ms=avg,
                p50_ms=durations[p50_idx],
                p95_ms=durations[min(p95_idx, count - 1)],
                p99_ms=durations[min(p99_idx, count - 1)],
                min_ms=durations[0],
                max_ms=durations[-1],
                std_dev_ms=statistics.stdev(durations) if count > 1 else 0.0
            )
    
    def get_all_stats(self) -> List[ProfileStats]:
        """Retorna estatísticas de todas as funções/módulos."""
        with self._lock:
            names = list(self._entries.keys())
        
        stats = []
        for name in names:
            s = self.get_stats(name)
            if s:
                stats.append(s)
        
        # Ordenar por total_ms (maior impacto primeiro)
        stats.sort(key=lambda x: x.total_ms, reverse=True)
        return stats
    
    def get_regressions(self, limit: int = 50) -> List[RegressionAlert]:
        """Retorna alertas de regressão recentes."""
        with self._lock:
            return self._regressions[-limit:]
    
    def get_bottlenecks(self, top_n: int = 5) -> List[ProfileStats]:
        """Identifica os maiores gargalos (por tempo total)."""
        all_stats = self.get_all_stats()
        return all_stats[:top_n]
    
    def get_slowest(self, top_n: int = 5) -> List[ProfileStats]:
        """Identifica as funções mais lentas (por p95)."""
        all_stats = self.get_all_stats()
        all_stats.sort(key=lambda x: x.p95_ms, reverse=True)
        return all_stats[:top_n]
    
    def get_history(
        self,
        name: str,
        limit: int = 100,
        since_seconds: Optional[float] = None
    ) -> List[ProfileEntry]:
        """Retorna histórico de medições."""
        with self._lock:
            entries = self._entries.get(name, [])
        
        if since_seconds:
            cutoff = time.time() - since_seconds
            entries = [e for e in entries if e.timestamp >= cutoff]
        
        return entries[-limit:]
    
    def get_global_stats(self) -> Dict:
        """Retorna estatísticas globais do profiler."""
        with self._lock:
            return {
                **self._stats,
                "tracked_functions": len(self._entries),
                "total_entries": sum(len(e) for e in self._entries.values()),
                "enabled": self._enabled,
                "uptime_seconds": time.time() - self._stats["started_at"]
            }
    
    def generate_report(self) -> Dict:
        """Gera relatório completo de performance."""
        bottlenecks = self.get_bottlenecks(10)
        slowest = self.get_slowest(10)
        regressions = self.get_regressions(20)
        
        return {
            "timestamp": time.time(),
            "global_stats": self.get_global_stats(),
            "bottlenecks": [b.to_dict() for b in bottlenecks],
            "slowest_functions": [s.to_dict() for s in slowest],
            "regressions": [r.to_dict() for r in regressions],
            "recommendations": self._generate_recommendations(bottlenecks, slowest, regressions)
        }
    
    def _generate_recommendations(
        self,
        bottlenecks: List[ProfileStats],
        slowest: List[ProfileStats],
        regressions: List[RegressionAlert]
    ) -> List[str]:
        """Gera recomendações baseadas nos dados."""
        recs = []
        
        # Bottlenecks
        if bottlenecks:
            top = bottlenecks[0]
            recs.append(
                f"🔥 Gargalo principal: {top.name} consome {top.total_ms:.1f}ms "
                f"({top.count} chamadas, {top.avg_ms:.1f}ms avg)"
            )
        
        # Funções lentas
        slow_p95 = [s for s in slowest if s.p95_ms > 100]
        if slow_p95:
            names = ", ".join(s.name for s in slow_p95[:3])
            recs.append(f"⚠️ Funções com p95 > 100ms: {names}")
        
        # Regressões
        if regressions:
            latest = regressions[-1]
            recs.append(
                f"📉 Regressão detectada em {latest.name}: "
                f"+{latest.regression_pct:.1f}% vs baseline"
            )
        
        # Alta variabilidade
        high_variance = [s for s in bottlenecks if s.std_dev_ms > s.avg_ms * 0.5]
        if high_variance:
            names = ", ".join(s.name for s in high_variance[:3])
            recs.append(f"📊 Alta variabilidade em: {names} (std_dev > 50% do avg)")
        
        if not recs:
            recs.append("✅ Performance estável. Nenhuma ação necessária.")
        
        return recs
    
    def reset(self):
        """Reseta todos os dados."""
        with self._lock:
            self._entries.clear()
            self._baselines.clear()
            self._regressions.clear()
            self._stats = {
                "total_profiles": 0,
                "regressions_detected": 0,
                "started_at": time.time()
            }
    
    def export_json(self, filepath: str):
        """Exporta dados para JSON."""
        report = self.generate_report()
        with open(filepath, "w") as f:
            json.dump(report, f, indent=2)


# Instância global (singleton pattern)
_global_profiler: Optional[PerformanceProfiler] = None


def get_profiler() -> PerformanceProfiler:
    """Retorna instância global do profiler."""
    global _global_profiler
    if _global_profiler is None:
        _global_profiler = PerformanceProfiler()
    return _global_profiler


def profile(name: Optional[str] = None, metadata: Optional[Dict] = None):
    """
    Decorator para profiling automático.
    
    Uso:
        @profile()
        def minha_funcao():
            pass
        
        @profile("custom_name", metadata={"version": "3.7"})
        def outra_funcao():
            pass
    """
    def decorator(func: Callable) -> Callable:
        profile_name = name or f"{func.__module__}.{func.__name__}"
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            profiler = get_profiler()
            
            if not profiler.enabled:
                return func(*args, **kwargs)
            
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                profiler.record(profile_name, duration_ms, metadata)
        
        return wrapper
    return decorator


class ProfileContext:
    """
    Context manager para profiling.
    
    Uso:
        with ProfileContext("meu_bloco"):
            # código a ser medido
            pass
    """
    
    def __init__(self, name: str, metadata: Optional[Dict] = None):
        self.name = name
        self.metadata = metadata
        self.profiler = get_profiler()
        self.start = None
    
    def __enter__(self):
        if self.profiler.enabled:
            self.start = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.profiler.enabled and self.start is not None:
            duration_ms = (time.perf_counter() - self.start) * 1000
            self.profiler.record(self.name, duration_ms, self.metadata)
        return False
