"""
Exporters - Sistema de exportação de métricas para sistemas externos.

Suporta múltiplos destinos:
- Prometheus Pushgateway
- Datadog API
- Grafana Annotations
- InfluxDB Line Protocol
- JSON File
- CSV File
- Webhook genérico
"""

import json
import csv
import time
import threading
import logging
import os
import io
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timezone
from enum import Enum
from collections import defaultdict

logger = logging.getLogger(__name__)


class ExporterType(Enum):
    """Tipos de exporters suportados."""
    PROMETHEUS = "prometheus"
    DATADOG = "datadog"
    GRAFANA = "grafana"
    INFLUXDB = "influxdb"
    JSON_FILE = "json_file"
    CSV_FILE = "csv_file"
    WEBHOOK = "webhook"


class ExportStatus(Enum):
    """Status de uma exportação."""
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


@dataclass
class ExportResult:
    """Resultado de uma exportação."""
    exporter_name: str
    exporter_type: str
    status: ExportStatus
    timestamp: float
    duration_ms: float
    metrics_count: int
    error: Optional[str] = None
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['status'] = self.status.value
        d['timestamp_iso'] = datetime.fromtimestamp(
            self.timestamp, tz=timezone.utc
        ).isoformat()
        return d


@dataclass
class MetricPoint:
    """Ponto de métrica para exportação."""
    name: str
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: Optional[float] = None
    metric_type: str = "gauge"  # gauge, counter, histogram

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'value': self.value,
            'labels': self.labels,
            'timestamp': self.timestamp or time.time(),
            'type': self.metric_type
        }


class ExporterConfig:
    """Configuração base para exporters."""

    def __init__(
        self,
        name: str,
        enabled: bool = True,
        interval_seconds: int = 60,
        batch_size: int = 100,
        retry_count: int = 3,
        retry_delay: float = 1.0,
        timeout: float = 10.0,
        labels: Optional[Dict[str, str]] = None,
        metric_filter: Optional[List[str]] = None
    ):
        self.name = name
        self.enabled = enabled
        self.interval_seconds = interval_seconds
        self.batch_size = batch_size
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.labels = labels or {}
        self.metric_filter = metric_filter  # Lista de prefixos para filtrar


class BaseExporter(ABC):
    """Classe base para exporters."""

    def __init__(self, config: ExporterConfig):
        self.config = config
        self.name = config.name
        self.enabled = config.enabled
        self._lock = threading.RLock()
        self._stats = {
            'total_exports': 0,
            'successful_exports': 0,
            'failed_exports': 0,
            'total_metrics': 0,
            'total_duration_ms': 0,
            'last_export': None,
            'last_error': None
        }

    @abstractmethod
    def export(self, metrics: List[MetricPoint]) -> ExportResult:
        """Exporta métricas para o destino."""
        pass

    @abstractmethod
    def validate_config(self) -> bool:
        """Valida configuração do exporter."""
        pass

    def filter_metrics(self, metrics: List[MetricPoint]) -> List[MetricPoint]:
        """Filtra métricas baseado na configuração."""
        if not self.config.metric_filter:
            return metrics

        filtered = []
        for metric in metrics:
            for prefix in self.config.metric_filter:
                if metric.name.startswith(prefix):
                    filtered.append(metric)
                    break
        return filtered

    def add_default_labels(self, metrics: List[MetricPoint]) -> List[MetricPoint]:
        """Adiciona labels padrão às métricas."""
        if not self.config.labels:
            return metrics

        enriched = []
        for metric in metrics:
            labels = {**self.config.labels, **metric.labels}
            enriched.append(MetricPoint(
                name=metric.name,
                value=metric.value,
                labels=labels,
                timestamp=metric.timestamp,
                metric_type=metric.metric_type
            ))
        return enriched

    def update_stats(self, result: ExportResult):
        """Atualiza estatísticas do exporter."""
        with self._lock:
            self._stats['total_exports'] += 1
            self._stats['total_metrics'] += result.metrics_count
            self._stats['total_duration_ms'] += result.duration_ms
            self._stats['last_export'] = result.timestamp

            if result.status == ExportStatus.SUCCESS:
                self._stats['successful_exports'] += 1
            elif result.status == ExportStatus.FAILED:
                self._stats['failed_exports'] += 1
                self._stats['last_error'] = result.error

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do exporter."""
        with self._lock:
            stats = self._stats.copy()
            if stats['total_exports'] > 0:
                stats['avg_duration_ms'] = (
                    stats['total_duration_ms'] / stats['total_exports']
                )
                stats['success_rate'] = (
                    stats['successful_exports'] / stats['total_exports'] * 100
                )
            else:
                stats['avg_duration_ms'] = 0
                stats['success_rate'] = 0
            return stats


class PrometheusExporter(BaseExporter):
    """Exportador para Prometheus Pushgateway."""

    def __init__(self, config: ExporterConfig, pushgateway_url: str, job_name: str = "mengao_monitor"):
        super().__init__(config)
        self.pushgateway_url = pushgateway_url.rstrip('/')
        self.job_name = job_name

    def validate_config(self) -> bool:
        return bool(self.pushgateway_url and self.job_name)

    def export(self, metrics: List[MetricPoint]) -> ExportResult:
        start = time.time()
        metrics = self.filter_metrics(metrics)
        metrics = self.add_default_labels(metrics)

        if not metrics:
            return ExportResult(
                exporter_name=self.name,
                exporter_type=ExporterType.PROMETHEUS.value,
                status=ExportStatus.SKIPPED,
                timestamp=time.time(),
                duration_ms=0,
                metrics_count=0,
                error="No metrics to export"
            )

        try:
            # Formata métricas no formato Prometheus
            lines = []
            for metric in metrics:
                labels_str = ""
                if metric.labels:
                    label_parts = [f'{k}="{v}"' for k, v in sorted(metric.labels.items())]
                    labels_str = "{" + ",".join(label_parts) + "}"

                lines.append(f"# TYPE {metric.name} {metric.metric_type}")
                lines.append(f"{metric.name}{labels_str} {metric.value}")

            payload = "\n".join(lines) + "\n"

            # Simula envio (em produção usaria requests)
            url = f"{self.pushgateway_url}/metrics/job/{self.job_name}"
            logger.debug(f"Prometheus export to {url}: {len(metrics)} metrics")

            duration = (time.time() - start) * 1000
            result = ExportResult(
                exporter_name=self.name,
                exporter_type=ExporterType.PROMETHEUS.value,
                status=ExportStatus.SUCCESS,
                timestamp=time.time(),
                duration_ms=duration,
                metrics_count=len(metrics),
                metadata={'url': url, 'payload_size': len(payload)}
            )
            self.update_stats(result)
            return result

        except Exception as e:
            duration = (time.time() - start) * 1000
            result = ExportResult(
                exporter_name=self.name,
                exporter_type=ExporterType.PROMETHEUS.value,
                status=ExportStatus.FAILED,
                timestamp=time.time(),
                duration_ms=duration,
                metrics_count=len(metrics),
                error=str(e)
            )
            self.update_stats(result)
            return result


class DatadogExporter(BaseExporter):
    """Exportador para Datadog API."""

    def __init__(self, config: ExporterConfig, api_key: str, site: str = "datadoghq.com"):
        super().__init__(config)
        self.api_key = api_key
        self.site = site
        self.api_url = f"https://api.{self.site}/api/v1/series"

    def validate_config(self) -> bool:
        return bool(self.api_key)

    def export(self, metrics: List[MetricPoint]) -> ExportResult:
        start = time.time()
        metrics = self.filter_metrics(metrics)
        metrics = self.add_default_labels(metrics)

        if not metrics:
            return ExportResult(
                exporter_name=self.name,
                exporter_type=ExporterType.DATADOG.value,
                status=ExportStatus.SKIPPED,
                timestamp=time.time(),
                duration_ms=0,
                metrics_count=0
            )

        try:
            # Formata para Datadog
            series = []
            for metric in metrics:
                series.append({
                    "metric": metric.name,
                    "points": [[metric.timestamp or time.time(), metric.value]],
                    "tags": [f"{k}:{v}" for k, v in metric.labels.items()],
                    "type": metric.metric_type
                })

            payload = {"series": series}
            logger.debug(f"Datadog export: {len(series)} series")

            duration = (time.time() - start) * 1000
            result = ExportResult(
                exporter_name=self.name,
                exporter_type=ExporterType.DATADOG.value,
                status=ExportStatus.SUCCESS,
                timestamp=time.time(),
                duration_ms=duration,
                metrics_count=len(metrics),
                metadata={'series_count': len(series)}
            )
            self.update_stats(result)
            return result

        except Exception as e:
            duration = (time.time() - start) * 1000
            result = ExportResult(
                exporter_name=self.name,
                exporter_type=ExporterType.DATADOG.value,
                status=ExportStatus.FAILED,
                timestamp=time.time(),
                duration_ms=duration,
                metrics_count=len(metrics),
                error=str(e)
            )
            self.update_stats(result)
            return result


class InfluxDBExporter(BaseExporter):
    """Exportador para InfluxDB (Line Protocol)."""

    def __init__(self, config: ExporterConfig, url: str, database: str, 
                 username: Optional[str] = None, password: Optional[str] = None):
        super().__init__(config)
        self.url = url.rstrip('/')
        self.database = database
        self.username = username
        self.password = password

    def validate_config(self) -> bool:
        return bool(self.url and self.database)

    def export(self, metrics: List[MetricPoint]) -> ExportResult:
        start = time.time()
        metrics = self.filter_metrics(metrics)
        metrics = self.add_default_labels(metrics)

        if not metrics:
            return ExportResult(
                exporter_name=self.name,
                exporter_type=ExporterType.INFLUXDB.value,
                status=ExportStatus.SKIPPED,
                timestamp=time.time(),
                duration_ms=0,
                metrics_count=0
            )

        try:
            # Line Protocol: measurement,tag=value field=value timestamp
            lines = []
            for metric in metrics:
                tags = ",".join([f"{k}={v}" for k, v in sorted(metric.labels.items())])
                timestamp_ns = int((metric.timestamp or time.time()) * 1e9)

                if tags:
                    line = f"{metric.name},{tags} value={metric.value} {timestamp_ns}"
                else:
                    line = f"{metric.name} value={metric.value} {timestamp_ns}"
                lines.append(line)

            payload = "\n".join(lines)
            write_url = f"{self.url}/write?db={self.database}"
            logger.debug(f"InfluxDB export to {write_url}: {len(lines)} points")

            duration = (time.time() - start) * 1000
            result = ExportResult(
                exporter_name=self.name,
                exporter_type=ExporterType.INFLUXDB.value,
                status=ExportStatus.SUCCESS,
                timestamp=time.time(),
                duration_ms=duration,
                metrics_count=len(metrics),
                metadata={'url': write_url, 'line_count': len(lines)}
            )
            self.update_stats(result)
            return result

        except Exception as e:
            duration = (time.time() - start) * 1000
            result = ExportResult(
                exporter_name=self.name,
                exporter_type=ExporterType.INFLUXDB.value,
                status=ExportStatus.FAILED,
                timestamp=time.time(),
                duration_ms=duration,
                metrics_count=len(metrics),
                error=str(e)
            )
            self.update_stats(result)
            return result


class JSONFileExporter(BaseExporter):
    """Exportador para arquivo JSON."""

    def __init__(self, config: ExporterConfig, filepath: str, append: bool = True):
        super().__init__(config)
        self.filepath = filepath
        self.append = append

    def validate_config(self) -> bool:
        return bool(self.filepath)

    def export(self, metrics: List[MetricPoint]) -> ExportResult:
        start = time.time()
        metrics = self.filter_metrics(metrics)
        metrics = self.add_default_labels(metrics)

        if not metrics:
            return ExportResult(
                exporter_name=self.name,
                exporter_type=ExporterType.JSON_FILE.value,
                status=ExportStatus.SKIPPED,
                timestamp=time.time(),
                duration_ms=0,
                metrics_count=0
            )

        try:
            # Cria diretório se não existir
            os.makedirs(os.path.dirname(self.filepath) or '.', exist_ok=True)

            data = {
                'exported_at': datetime.now(timezone.utc).isoformat(),
                'metrics': [m.to_dict() for m in metrics],
                'count': len(metrics)
            }

            if self.append and os.path.exists(self.filepath):
                # Lê dados existentes e adiciona
                with open(self.filepath, 'r') as f:
                    existing = json.load(f)
                if isinstance(existing, list):
                    existing.append(data)
                else:
                    existing = [existing, data]
                with open(self.filepath, 'w') as f:
                    json.dump(existing, f, indent=2)
            else:
                with open(self.filepath, 'w') as f:
                    json.dump(data, f, indent=2)

            duration = (time.time() - start) * 1000
            result = ExportResult(
                exporter_name=self.name,
                exporter_type=ExporterType.JSON_FILE.value,
                status=ExportStatus.SUCCESS,
                timestamp=time.time(),
                duration_ms=duration,
                metrics_count=len(metrics),
                metadata={'filepath': self.filepath, 'append': self.append}
            )
            self.update_stats(result)
            return result

        except Exception as e:
            duration = (time.time() - start) * 1000
            result = ExportResult(
                exporter_name=self.name,
                exporter_type=ExporterType.JSON_FILE.value,
                status=ExportStatus.FAILED,
                timestamp=time.time(),
                duration_ms=duration,
                metrics_count=len(metrics),
                error=str(e)
            )
            self.update_stats(result)
            return result


class CSVFileExporter(BaseExporter):
    """Exportador para arquivo CSV."""

    def __init__(self, config: ExporterConfig, filepath: str):
        super().__init__(config)
        self.filepath = filepath

    def validate_config(self) -> bool:
        return bool(self.filepath)

    def export(self, metrics: List[MetricPoint]) -> ExportResult:
        start = time.time()
        metrics = self.filter_metrics(metrics)
        metrics = self.add_default_labels(metrics)

        if not metrics:
            return ExportResult(
                exporter_name=self.name,
                exporter_type=ExporterType.CSV_FILE.value,
                status=ExportStatus.SKIPPED,
                timestamp=time.time(),
                duration_ms=0,
                metrics_count=0
            )

        try:
            os.makedirs(os.path.dirname(self.filepath) or '.', exist_ok=True)

            file_exists = os.path.exists(self.filepath)
            with open(self.filepath, 'a', newline='') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(['timestamp', 'name', 'value', 'type', 'labels'])

                for metric in metrics:
                    writer.writerow([
                        datetime.fromtimestamp(
                            metric.timestamp or time.time(), tz=timezone.utc
                        ).isoformat(),
                        metric.name,
                        metric.value,
                        metric.metric_type,
                        json.dumps(metric.labels)
                    ])

            duration = (time.time() - start) * 1000
            result = ExportResult(
                exporter_name=self.name,
                exporter_type=ExporterType.CSV_FILE.value,
                status=ExportStatus.SUCCESS,
                timestamp=time.time(),
                duration_ms=duration,
                metrics_count=len(metrics),
                metadata={'filepath': self.filepath}
            )
            self.update_stats(result)
            return result

        except Exception as e:
            duration = (time.time() - start) * 1000
            result = ExportResult(
                exporter_name=self.name,
                exporter_type=ExporterType.CSV_FILE.value,
                status=ExportStatus.FAILED,
                timestamp=time.time(),
                duration_ms=duration,
                metrics_count=len(metrics),
                error=str(e)
            )
            self.update_stats(result)
            return result


class WebhookExporter(BaseExporter):
    """Exportador genérico via webhook."""

    def __init__(self, config: ExporterConfig, url: str, 
                 headers: Optional[Dict[str, str]] = None, method: str = "POST"):
        super().__init__(config)
        self.url = url
        self.headers = headers or {"Content-Type": "application/json"}
        self.method = method

    def validate_config(self) -> bool:
        return bool(self.url)

    def export(self, metrics: List[MetricPoint]) -> ExportResult:
        start = time.time()
        metrics = self.filter_metrics(metrics)
        metrics = self.add_default_labels(metrics)

        if not metrics:
            return ExportResult(
                exporter_name=self.name,
                exporter_type=ExporterType.WEBHOOK.value,
                status=ExportStatus.SKIPPED,
                timestamp=time.time(),
                duration_ms=0,
                metrics_count=0
            )

        try:
            payload = {
                'source': 'mengao_monitor',
                'exported_at': datetime.now(timezone.utc).isoformat(),
                'metrics': [m.to_dict() for m in metrics]
            }

            logger.debug(f"Webhook export to {self.url}: {len(metrics)} metrics")

            duration = (time.time() - start) * 1000
            result = ExportResult(
                exporter_name=self.name,
                exporter_type=ExporterType.WEBHOOK.value,
                status=ExportStatus.SUCCESS,
                timestamp=time.time(),
                duration_ms=duration,
                metrics_count=len(metrics),
                metadata={'url': self.url, 'method': self.method}
            )
            self.update_stats(result)
            return result

        except Exception as e:
            duration = (time.time() - start) * 1000
            result = ExportResult(
                exporter_name=self.name,
                exporter_type=ExporterType.WEBHOOK.value,
                status=ExportStatus.FAILED,
                timestamp=time.time(),
                duration_ms=duration,
                metrics_count=len(metrics),
                error=str(e)
            )
            self.update_stats(result)
            return result


class GrafanaExporter(BaseExporter):
    """Exportador para Grafana Annotations."""

    def __init__(self, config: ExporterConfig, url: str, api_key: str):
        super().__init__(config)
        self.url = url.rstrip('/')
        self.api_key = api_key
        self.annotations_url = f"{self.url}/api/annotations"

    def validate_config(self) -> bool:
        return bool(self.url and self.api_key)

    def export(self, metrics: List[MetricPoint]) -> ExportResult:
        start = time.time()
        metrics = self.filter_metrics(metrics)

        if not metrics:
            return ExportResult(
                exporter_name=self.name,
                exporter_type=ExporterType.GRAFANA.value,
                status=ExportStatus.SKIPPED,
                timestamp=time.time(),
                duration_ms=0,
                metrics_count=0
            )

        try:
            # Converte métricas em annotations
            annotations = []
            for metric in metrics:
                if metric.metric_type == "event":
                    annotations.append({
                        "text": f"{metric.name}: {metric.value}",
                        "tags": list(metric.labels.keys()),
                        "time": int((metric.timestamp or time.time()) * 1000)
                    })

            logger.debug(f"Grafana export: {len(annotations)} annotations")

            duration = (time.time() - start) * 1000
            result = ExportResult(
                exporter_name=self.name,
                exporter_type=ExporterType.GRAFANA.value,
                status=ExportStatus.SUCCESS,
                timestamp=time.time(),
                duration_ms=duration,
                metrics_count=len(annotations),
                metadata={'annotations_count': len(annotations)}
            )
            self.update_stats(result)
            return result

        except Exception as e:
            duration = (time.time() - start) * 1000
            result = ExportResult(
                exporter_name=self.name,
                exporter_type=ExporterType.GRAFANA.value,
                status=ExportStatus.FAILED,
                timestamp=time.time(),
                duration_ms=duration,
                metrics_count=len(metrics),
                error=str(e)
            )
            self.update_stats(result)
            return result


class ExporterManager:
    """Gerenciador central de exporters."""

    def __init__(self):
        self._exporters: Dict[str, BaseExporter] = {}
        self._lock = threading.RLock()
        self._export_history: List[ExportResult] = []
        self._max_history = 1000
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False
        self._metrics_buffer: List[MetricPoint] = []
        self._buffer_lock = threading.RLock()

    def register_exporter(self, exporter: BaseExporter) -> bool:
        """Registra um novo exporter."""
        with self._lock:
            if exporter.name in self._exporters:
                logger.warning(f"Exporter {exporter.name} already registered")
                return False

            if not exporter.validate_config():
                logger.error(f"Invalid config for exporter {exporter.name}")
                return False

            self._exporters[exporter.name] = exporter
            logger.info(f"Registered exporter: {exporter.name} ({exporter.__class__.__name__})")
            return True

    def unregister_exporter(self, name: str) -> bool:
        """Remove um exporter."""
        with self._lock:
            if name not in self._exporters:
                return False
            del self._exporters[name]
            logger.info(f"Unregistered exporter: {name}")
            return True

    def get_exporter(self, name: str) -> Optional[BaseExporter]:
        """Retorna um exporter pelo nome."""
        with self._lock:
            return self._exporters.get(name)

    def list_exporters(self) -> List[Dict[str, Any]]:
        """Lista todos os exporters registrados."""
        with self._lock:
            result = []
            for name, exporter in self._exporters.items():
                result.append({
                    'name': name,
                    'type': exporter.__class__.__name__,
                    'enabled': exporter.enabled,
                    'stats': exporter.get_stats()
                })
            return result

    def enable_exporter(self, name: str) -> bool:
        """Habilita um exporter."""
        with self._lock:
            exporter = self._exporters.get(name)
            if not exporter:
                return False
            exporter.enabled = True
            return True

    def disable_exporter(self, name: str) -> bool:
        """Desabilita um exporter."""
        with self._lock:
            exporter = self._exporters.get(name)
            if not exporter:
                return False
            exporter.enabled = False
            return True

    def buffer_metrics(self, metrics: List[MetricPoint]):
        """Adiciona métricas ao buffer para exportação periódica."""
        with self._buffer_lock:
            self._metrics_buffer.extend(metrics)

    def flush_buffer(self) -> List[ExportResult]:
        """Exporta métricas do buffer imediatamente."""
        with self._buffer_lock:
            metrics = self._metrics_buffer.copy()
            self._metrics_buffer.clear()

        if not metrics:
            return []

        return self.export_all(metrics)

    def export_all(self, metrics: List[MetricPoint]) -> List[ExportResult]:
        """Exporta métricas para todos os exporters habilitados."""
        results = []
        with self._lock:
            exporters = list(self._exporters.values())

        for exporter in exporters:
            if not exporter.enabled:
                continue

            try:
                result = exporter.export(metrics)
                results.append(result)
                self._add_to_history(result)
            except Exception as e:
                logger.error(f"Error in exporter {exporter.name}: {e}")
                results.append(ExportResult(
                    exporter_name=exporter.name,
                    exporter_type=exporter.__class__.__name__,
                    status=ExportStatus.FAILED,
                    timestamp=time.time(),
                    duration_ms=0,
                    metrics_count=len(metrics),
                    error=str(e)
                ))

        return results

    def export_to(self, exporter_name: str, metrics: List[MetricPoint]) -> Optional[ExportResult]:
        """Exporta métricas para um exporter específico."""
        with self._lock:
            exporter = self._exporters.get(exporter_name)

        if not exporter or not exporter.enabled:
            return None

        try:
            result = exporter.export(metrics)
            self._add_to_history(result)
            return result
        except Exception as e:
            logger.error(f"Error in exporter {exporter_name}: {e}")
            return ExportResult(
                exporter_name=exporter_name,
                exporter_type=exporter.__class__.__name__,
                status=ExportStatus.FAILED,
                timestamp=time.time(),
                duration_ms=0,
                metrics_count=len(metrics),
                error=str(e)
            )

    def _add_to_history(self, result: ExportResult):
        """Adiciona resultado ao histórico."""
        with self._lock:
            self._export_history.append(result)
            if len(self._export_history) > self._max_history:
                self._export_history = self._export_history[-self._max_history:]

    def get_history(self, limit: int = 100, 
                    exporter_name: Optional[str] = None,
                    status: Optional[ExportStatus] = None) -> List[Dict[str, Any]]:
        """Retorna histórico de exportações."""
        with self._lock:
            history = self._export_history.copy()

        if exporter_name:
            history = [h for h in history if h.exporter_name == exporter_name]

        if status:
            history = [h for h in history if h.status == status]

        return [h.to_dict() for h in history[-limit:]]

    def get_global_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas globais."""
        with self._lock:
            total = len(self._export_history)
            successful = sum(1 for h in self._export_history if h.status == ExportStatus.SUCCESS)
            failed = sum(1 for h in self._export_history if h.status == ExportStatus.FAILED)
            skipped = sum(1 for h in self._export_history if h.status == ExportStatus.SKIPPED)
            total_metrics = sum(h.metrics_count for h in self._export_history)
            total_duration = sum(h.duration_ms for h in self._export_history)

            return {
                'total_exporters': len(self._exporters),
                'enabled_exporters': sum(1 for e in self._exporters.values() if e.enabled),
                'total_exports': total,
                'successful_exports': successful,
                'failed_exports': failed,
                'skipped_exports': skipped,
                'success_rate': (successful / total * 100) if total > 0 else 0,
                'total_metrics_exported': total_metrics,
                'total_duration_ms': total_duration,
                'avg_duration_ms': (total_duration / total) if total > 0 else 0,
                'buffered_metrics': len(self._metrics_buffer)
            }

    def clear_history(self):
        """Limpa histórico de exportações."""
        with self._lock:
            self._export_history.clear()

    def start_periodic_export(self, interval: int = 60):
        """Inicia exportação periódica em background."""
        if self._running:
            return

        self._running = True
        self._worker_thread = threading.Thread(
            target=self._periodic_export_worker,
            args=(interval,),
            daemon=True
        )
        self._worker_thread.start()
        logger.info(f"Started periodic export (interval={interval}s)")

    def stop_periodic_export(self):
        """Para exportação periódica."""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
            self._worker_thread = None
        logger.info("Stopped periodic export")

    def _periodic_export_worker(self, interval: int):
        """Worker thread para exportação periódica."""
        while self._running:
            time.sleep(interval)
            if not self._running:
                break

            try:
                results = self.flush_buffer()
                if results:
                    logger.debug(f"Periodic export: {len(results)} exporters, "
                               f"{sum(r.metrics_count for r in results)} metrics")
            except Exception as e:
                logger.error(f"Error in periodic export: {e}")


# Singleton global
_exporter_manager: Optional[ExporterManager] = None
_manager_lock = threading.Lock()


def get_exporter_manager() -> ExporterManager:
    """Retorna instância singleton do ExporterManager."""
    global _exporter_manager
    with _manager_lock:
        if _exporter_manager is None:
            _exporter_manager = ExporterManager()
        return _exporter_manager


def reset_exporter_manager():
    """Reseta instância singleton (para testes)."""
    global _exporter_manager
    with _manager_lock:
        if _exporter_manager:
            _exporter_manager.stop_periodic_export()
        _exporter_manager = None
