"""
Metrics Aggregator v3.9 - Agregação temporal e detecção de anomalias.

Funcionalidades:
- Agregação em janelas temporais (1min, 5min, 15min, 1h, 1d)
- Detecção de anomalias via Z-Score e thresholds
- Trend analysis (crescente, decrescente, estável)
- Correlação entre métricas
- Alertas automáticos baseados em anomalias
"""

import time
import math
import threading
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Callable
from enum import Enum
from datetime import datetime


class AggregationWindow(Enum):
    """Janelas de agregação disponíveis."""
    MINUTE_1 = 60
    MINUTE_5 = 300
    MINUTE_15 = 900
    HOUR_1 = 3600
    DAY_1 = 86400


class TrendDirection(Enum):
    """Direção da tendência."""
    RISING = "rising"
    FALLING = "falling"
    STABLE = "stable"
    VOLATILE = "volatile"


class AnomalyType(Enum):
    """Tipos de anomalia detectáveis."""
    SPIKE = "spike"           # Valor muito acima da média
    DROP = "drop"             # Valor muito abaixo da média
    THRESHOLD = "threshold"   # Ultrapassou threshold absoluto
    TREND = "trend"           # Tendência anômala
    FLATLINE = "flatline"     # Valor não muda (possível erro)


@dataclass
class MetricPoint:
    """Ponto de métrica individual."""
    name: str
    value: float
    timestamp: float = field(default_factory=time.time)
    labels: Dict[str, str] = field(default_factory=dict)

    def age(self) -> float:
        """Idade do ponto em segundos."""
        return time.time() - self.timestamp


@dataclass
class AggregatedMetric:
    """Métrica agregada em janela temporal."""
    name: str
    window: AggregationWindow
    count: int
    min_val: float
    max_val: float
    mean: float
    median: float
    stddev: float
    p95: float
    p99: float
    sum_val: float
    first_ts: float
    last_ts: float

    @property
    def range_val(self) -> float:
        return self.max_val - self.min_val

    @property
    def duration(self) -> float:
        return self.last_ts - self.first_ts

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "window": self.window.name,
            "count": self.count,
            "min": self.min_val,
            "max": self.max_val,
            "mean": round(self.mean, 4),
            "median": round(self.median, 4),
            "stddev": round(self.stddev, 4),
            "p95": round(self.p95, 4),
            "p99": round(self.p99, 4),
            "sum": round(self.sum_val, 4),
            "range": round(self.range_val, 4),
            "duration_seconds": round(self.duration, 2),
        }


@dataclass
class Anomaly:
    """Anomalia detectada."""
    metric_name: str
    anomaly_type: AnomalyType
    value: float
    expected_range: Tuple[float, float]
    z_score: float
    timestamp: float
    severity: str  # low, medium, high, critical
    message: str

    def to_dict(self) -> Dict:
        return {
            "metric": self.metric_name,
            "type": self.anomaly_type.value,
            "value": round(self.value, 4),
            "expected_range": [round(self.expected_range[0], 4), round(self.expected_range[1], 4)],
            "z_score": round(self.z_score, 4),
            "timestamp": self.timestamp,
            "severity": self.severity,
            "message": self.message,
        }


@dataclass
class MetricThreshold:
    """Threshold configurável para métrica."""
    metric_name: str
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    z_score_threshold: float = 3.0
    flatline_tolerance: float = 0.001
    flatline_min_points: int = 10


class MetricsAggregator:
    """
    Agregador de métricas com detecção de anomalias.

    Armazena pontos de métrica em buffers circulares e mantém
    agregações em múltiplas janelas temporais.
    """

    def __init__(
        self,
        max_points_per_metric: int = 10000,
        anomaly_check_interval: float = 60.0,
        z_score_threshold: float = 3.0,
    ):
        self._lock = threading.RLock()
        self._max_points = max_points_per_metric
        self._z_threshold = z_score_threshold
        self._check_interval = anomaly_check_interval

        # Buffers de pontos por métrica
        self._points: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=self._max_points)
        )

        # Agregações cacheadas por janela
        self._aggregations: Dict[str, Dict[AggregationWindow, AggregatedMetric]] = defaultdict(dict)

        # Thresholds configuráveis
        self._thresholds: Dict[str, MetricThreshold] = {}

        # Anomalias recentes
        self._anomalies: deque = deque(maxlen=1000)

        # Callbacks para anomalias
        self._anomaly_callbacks: List[Callable[[Anomaly], None]] = []

        # Stats
        self._stats = {
            "total_points": 0,
            "total_anomalies": 0,
            "metrics_tracked": 0,
            "last_anomaly_check": 0,
            "started_at": time.time(),
        }

        # Worker thread para detecção de anomalias
        self._running = False
        self._worker: Optional[threading.Thread] = None

    def start(self) -> None:
        """Inicia worker de detecção de anomalias."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._worker = threading.Thread(
                target=self._anomaly_detection_loop,
                daemon=True,
                name="metrics-aggregator-worker",
            )
            self._worker.start()

    def stop(self) -> None:
        """Para worker de detecção."""
        with self._lock:
            self._running = False
        if self._worker:
            self._worker.join(timeout=5.0)

    def record(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Registra um ponto de métrica."""
        point = MetricPoint(
            name=name,
            value=value,
            timestamp=time.time(),
            labels=labels or {},
        )
        with self._lock:
            self._points[name].append(point)
            self._stats["total_points"] += 1
            self._stats["metrics_tracked"] = len(self._points)
            # Invalida cache de agregações para esta métrica
            if name in self._aggregations:
                del self._aggregations[name]

    def record_batch(self, metrics: List[Tuple[str, float, Optional[Dict[str, str]]]]) -> None:
        """Registra múltiplos pontos de uma vez."""
        now = time.time()
        with self._lock:
            for name, value, labels in metrics:
                point = MetricPoint(name=name, value=value, timestamp=now, labels=labels or {})
                self._points[name].append(point)
                self._stats["total_points"] += 1
            self._stats["metrics_tracked"] = len(self._points)
            # Invalida cache
            for name, _, _ in metrics:
                if name in self._aggregations:
                    del self._aggregations[name]

    def aggregate(
        self,
        metric_name: str,
        window: AggregationWindow,
        since: Optional[float] = None,
    ) -> Optional[AggregatedMetric]:
        """
        Agrega métrica em janela temporal.

        Args:
            metric_name: Nome da métrica
            window: Janela de agregação
            since: Timestamp mínimo (default: agora - window)

        Returns:
            AggregatedMetric ou None se sem dados
        """
        with self._lock:
            # Verifica cache
            if metric_name in self._aggregations:
                cached = self._aggregations[metric_name].get(window)
                if cached and (time.time() - cached.last_ts) < window.value * 0.1:
                    return cached

            points = self._points.get(metric_name)
            if not points:
                return None

            cutoff = since or (time.time() - window.value)
            values = [p.value for p in points if p.timestamp >= cutoff]

            if not values:
                return None

            sorted_vals = sorted(values)
            n = len(sorted_vals)

            # Calcula estatísticas
            mean = statistics.mean(values)
            median = statistics.median(values)
            stddev = statistics.stdev(values) if n > 1 else 0.0

            # Percentis
            p95_idx = int(n * 0.95)
            p99_idx = int(n * 0.99)
            p95 = sorted_vals[min(p95_idx, n - 1)]
            p99 = sorted_vals[min(p99_idx, n - 1)]

            # Timestamps dos pontos usados
            relevant = [p for p in points if p.timestamp >= cutoff]
            first_ts = min(p.timestamp for p in relevant)
            last_ts = max(p.timestamp for p in relevant)

            agg = AggregatedMetric(
                name=metric_name,
                window=window,
                count=n,
                min_val=sorted_vals[0],
                max_val=sorted_vals[-1],
                mean=mean,
                median=median,
                stddev=stddev,
                p95=p95,
                p99=p99,
                sum_val=sum(values),
                first_ts=first_ts,
                last_ts=last_ts,
            )

            # Cacheia
            self._aggregations[metric_name][window] = agg
            return agg

    def aggregate_all_windows(self, metric_name: str) -> Dict[str, Optional[Dict]]:
        """Agrega métrica em todas as janelas disponíveis."""
        result = {}
        for window in AggregationWindow:
            agg = self.aggregate(metric_name, window)
            result[window.name] = agg.to_dict() if agg else None
        return result

    def detect_anomalies(self, metric_name: str) -> List[Anomaly]:
        """
        Detecta anomalias em uma métrica.

        Usa Z-Score para outliers, verifica thresholds,
        detecta flatlines e analisa tendência.
        """
        anomalies = []
        with self._lock:
            points = self._points.get(metric_name)
            if not points or len(points) < 5:
                return anomalies

            values = [p.value for p in points]
            recent_values = values[-50:]  # Últimos 50 pontos

            if len(recent_values) < 5:
                return anomalies

            mean = statistics.mean(recent_values)
            stddev = statistics.stdev(recent_values) if len(recent_values) > 1 else 0.0
            latest = values[-1]
            latest_ts = points[-1].timestamp

            # 1. Z-Score check
            if stddev > 0:
                z_score = abs(latest - mean) / stddev
                threshold = self._z_threshold
                if metric_name in self._thresholds:
                    threshold = self._thresholds[metric_name].z_score_threshold

                if z_score > threshold:
                    anomaly_type = AnomalyType.SPIKE if latest > mean else AnomalyType.DROP
                    severity = self._severity_from_zscore(z_score)
                    anomalies.append(Anomaly(
                        metric_name=metric_name,
                        anomaly_type=anomaly_type,
                        value=latest,
                        expected_range=(mean - threshold * stddev, mean + threshold * stddev),
                        z_score=z_score,
                        timestamp=latest_ts,
                        severity=severity,
                        message=f"{metric_name}: {anomaly_type.value} detected (z={z_score:.2f}, value={latest:.2f}, expected={mean:.2f}±{threshold*stddev:.2f})",
                    ))

            # 2. Threshold check
            if metric_name in self._thresholds:
                thresh = self._thresholds[metric_name]
                if thresh.max_val is not None and latest > thresh.max_val:
                    anomalies.append(Anomaly(
                        metric_name=metric_name,
                        anomaly_type=AnomalyType.THRESHOLD,
                        value=latest,
                        expected_range=(thresh.min_val or float("-inf"), thresh.max_val),
                        z_score=0,
                        timestamp=latest_ts,
                        severity="high",
                        message=f"{metric_name}: above max threshold ({latest:.2f} > {thresh.max_val})",
                    ))
                if thresh.min_val is not None and latest < thresh.min_val:
                    anomalies.append(Anomaly(
                        metric_name=metric_name,
                        anomaly_type=AnomalyType.THRESHOLD,
                        value=latest,
                        expected_range=(thresh.min_val, thresh.max_val or float("inf")),
                        z_score=0,
                        timestamp=latest_ts,
                        severity="high",
                        message=f"{metric_name}: below min threshold ({latest:.2f} < {thresh.min_val})",
                    ))

            # 3. Flatline detection
            flatline_tol = 0.001
            flatline_min = 10
            if metric_name in self._thresholds:
                thresh = self._thresholds[metric_name]
                flatline_tol = thresh.flatline_tolerance
                flatline_min = thresh.flatline_min_points

            if len(recent_values) >= flatline_min:
                last_n = recent_values[-flatline_min:]
                if max(last_n) - min(last_n) < flatline_tol:
                    anomalies.append(Anomaly(
                        metric_name=metric_name,
                        anomaly_type=AnomalyType.FLATLINE,
                        value=latest,
                        expected_range=(mean - stddev, mean + stddev),
                        z_score=0,
                        timestamp=latest_ts,
                        severity="medium",
                        message=f"{metric_name}: flatline detected (no variation in last {flatline_min} points)",
                    ))

        # Armazena e notifica
        for anomaly in anomalies:
            with self._lock:
                self._anomalies.append(anomaly)
                self._stats["total_anomalies"] += 1
            for callback in self._anomaly_callbacks:
                try:
                    callback(anomaly)
                except Exception:
                    pass

        return anomalies

    def detect_all_anomalies(self) -> Dict[str, List[Dict]]:
        """Detecta anomalias em todas as métricas."""
        result = {}
        with self._lock:
            metric_names = list(self._points.keys())
        for name in metric_names:
            anomalies = self.detect_anomalies(name)
            if anomalies:
                result[name] = [a.to_dict() for a in anomalies]
        return result

    def get_trend(self, metric_name: str, window: AggregationWindow = AggregationWindow.HOUR_1) -> Optional[Dict]:
        """
        Analisa tendência de uma métrica.

        Divide a janela em 4 quadrantes e compara médias.
        """
        with self._lock:
            points = self._points.get(metric_name)
            if not points or len(points) < 8:
                return None

            cutoff = time.time() - window.value
            values = [(p.timestamp, p.value) for p in points if p.timestamp >= cutoff]

            if len(values) < 8:
                return None

        # Divide em 4 quartis
        n = len(values)
        q_size = n // 4
        quarters = []
        for i in range(4):
            start = i * q_size
            end = start + q_size if i < 3 else n
            q_values = [v for _, v in values[start:end]]
            quarters.append(statistics.mean(q_values))

        # Calcula tendência
        diffs = [quarters[i+1] - quarters[i] for i in range(3)]
        avg_diff = statistics.mean(diffs)

        # Determina direção
        overall_stddev = statistics.stdev([v for _, v in values]) if len(values) > 1 else 0
        overall_mean = statistics.mean([v for _, v in values])
        
        if overall_stddev == 0:
            direction = TrendDirection.STABLE
        else:
            # Verifica se há alternância (volatilidade)
            sign_changes = sum(1 for d in diffs if (d > 0) != (diffs[0] > 0)) if diffs else 0
            is_volatile = sign_changes >= 2 or (overall_stddev > overall_mean * 0.3)
            
            if is_volatile and not (all(d > 0 for d in diffs) or all(d < 0 for d in diffs)):
                direction = TrendDirection.VOLATILE
            elif all(abs(d) < overall_stddev * 0.15 for d in diffs):
                direction = TrendDirection.STABLE
            elif all(d > 0 for d in diffs):
                direction = TrendDirection.RISING
            elif all(d < 0 for d in diffs):
                direction = TrendDirection.FALLING
            else:
                direction = TrendDirection.VOLATILE

        # Força da tendência (0-1)
        if overall_stddev > 0:
            strength = min(1.0, abs(avg_diff) / overall_stddev)
        else:
            strength = 0.0

        return {
            "metric": metric_name,
            "window": window.name,
            "direction": direction.value,
            "strength": round(strength, 4),
            "quarters": [round(q, 4) for q in quarters],
            "avg_change": round(avg_diff, 4),
            "points_analyzed": n,
        }

    def correlate(self, metric_a: str, metric_b: str, window: AggregationWindow = AggregationWindow.HOUR_1) -> Optional[Dict]:
        """
        Calcula correlação de Pearson entre duas métricas.
        """
        with self._lock:
            points_a = self._points.get(metric_a)
            points_b = self._points.get(metric_b)
            if not points_a or not points_b:
                return None

            cutoff = time.time() - window.value

            # Alinha por timestamp (bucket de 1s para dados gravados juntos)
            # Usa range total dos dados se window for maior que dados
            all_timestamps_a = [p.timestamp for p in points_a if p.timestamp >= cutoff]
            all_timestamps_b = [p.timestamp for p in points_b if p.timestamp >= cutoff]
            
            if not all_timestamps_a or not all_timestamps_b:
                return None
            
            # Determina bucket size baseado no range total
            min_ts = min(min(all_timestamps_a), min(all_timestamps_b))
            max_ts = max(max(all_timestamps_a), max(all_timestamps_b))
            total_range = max_ts - min_ts
            
            # Se range muito pequeno (<1s), usa bucket de 0.1s
            if total_range < 1.0:
                bucket_size = 0.1
            elif total_range < 60:
                bucket_size = max(0.5, total_range / 20)  # ~20 buckets
            else:
                bucket_size = 5.0

            buckets_a: Dict[int, List[float]] = defaultdict(list)
            buckets_b: Dict[int, List[float]] = defaultdict(list)

            for p in points_a:
                if p.timestamp >= cutoff:
                    bucket = int(p.timestamp / bucket_size)
                    buckets_a[bucket].append(p.value)

            for p in points_b:
                if p.timestamp >= cutoff:
                    bucket = int(p.timestamp / bucket_size)
                    buckets_b[bucket].append(p.value)

            # Interseção de buckets
            common_buckets = set(buckets_a.keys()) & set(buckets_b.keys())
            if len(common_buckets) < 3:
                return None

            # Médias por bucket
            vals_a = [statistics.mean(buckets_a[b]) for b in sorted(common_buckets)]
            vals_b = [statistics.mean(buckets_b[b]) for b in sorted(common_buckets)]

        # Correlação de Pearson
        n = len(vals_a)
        mean_a = statistics.mean(vals_a)
        mean_b = statistics.mean(vals_b)
        stddev_a = statistics.stdev(vals_a) if n > 1 else 0
        stddev_b = statistics.stdev(vals_b) if n > 1 else 0

        if stddev_a == 0 or stddev_b == 0:
            correlation = 0.0
        else:
            covariance = sum((vals_a[i] - mean_a) * (vals_b[i] - mean_b) for i in range(n)) / n
            correlation = covariance / (stddev_a * stddev_b)

        # Interpretação
        abs_corr = abs(correlation)
        if abs_corr > 0.8:
            strength = "strong"
        elif abs_corr > 0.5:
            strength = "moderate"
        elif abs_corr > 0.3:
            strength = "weak"
        else:
            strength = "none"

        direction = "positive" if correlation > 0 else "negative"

        return {
            "metric_a": metric_a,
            "metric_b": metric_b,
            "window": window.name,
            "correlation": round(correlation, 4),
            "strength": strength,
            "direction": direction,
            "buckets_used": n,
        }

    def set_threshold(self, threshold: MetricThreshold) -> None:
        """Configura threshold para uma métrica."""
        with self._lock:
            self._thresholds[threshold.metric_name] = threshold

    def on_anomaly(self, callback: Callable[[Anomaly], None]) -> None:
        """Registra callback para anomalias detectadas."""
        with self._lock:
            self._anomaly_callbacks.append(callback)

    def get_recent_anomalies(
        self,
        limit: int = 50,
        metric_name: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> List[Dict]:
        """Retorna anomalias recentes com filtros."""
        with self._lock:
            anomalies = list(self._anomalies)

        if metric_name:
            anomalies = [a for a in anomalies if a.metric_name == metric_name]
        if severity:
            anomalies = [a for a in anomalies if a.severity == severity]

        # Mais recentes primeiro
        anomalies.sort(key=lambda a: a.timestamp, reverse=True)
        return [a.to_dict() for a in anomalies[:limit]]

    def get_metric_names(self) -> List[str]:
        """Lista nomes de todas as métricas rastreadas."""
        with self._lock:
            return list(self._points.keys())

    def get_stats(self) -> Dict:
        """Estatísticas do agregador."""
        with self._lock:
            return {
                **self._stats,
                "metrics_tracked": len(self._points),
                "thresholds_configured": len(self._thresholds),
                "anomaly_callbacks": len(self._anomaly_callbacks),
                "running": self._running,
                "uptime_seconds": round(time.time() - self._stats["started_at"], 2),
            }

    def clear_metric(self, metric_name: str) -> int:
        """Remove todos os pontos de uma métrica. Retorna quantidade removida."""
        with self._lock:
            if metric_name in self._points:
                count = len(self._points[metric_name])
                del self._points[metric_name]
                if metric_name in self._aggregations:
                    del self._aggregations[metric_name]
                return count
            return 0

    def _severity_from_zscore(self, z_score: float) -> str:
        """Determina severidade baseada no Z-Score."""
        if z_score > 5:
            return "critical"
        elif z_score > 4:
            return "high"
        elif z_score > 3:
            return "medium"
        else:
            return "low"

    def _anomaly_detection_loop(self) -> None:
        """Worker thread para detecção periódica de anomalias."""
        while self._running:
            try:
                time.sleep(self._check_interval)
                if not self._running:
                    break
                self.detect_all_anomalies()
                with self._lock:
                    self._stats["last_anomaly_check"] = time.time()
            except Exception:
                pass


# Instância global (singleton pattern)
_instance: Optional[MetricsAggregator] = None
_instance_lock = threading.Lock()


def get_aggregator(**kwargs) -> MetricsAggregator:
    """Retorna instância global do agregador."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = MetricsAggregator(**kwargs)
        return _instance


def reset_aggregator() -> None:
    """Reseta instância global (para testes)."""
    global _instance
    with _instance_lock:
        if _instance:
            _instance.stop()
        _instance = None
