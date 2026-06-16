"""
SLA Reporter v2.9 - Mengão Monitor
Gera relatórios de SLA automáticos com uptime, response time, incidents.
"""

import time
import json
import csv
import io
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import threading


@dataclass
class SLAMetrics:
    """Métricas de SLA para um endpoint."""
    endpoint_name: str
    period_start: str
    period_end: str
    total_checks: int = 0
    successful_checks: int = 0
    failed_checks: int = 0
    uptime_percent: float = 100.0
    avg_response_time_ms: float = 0.0
    p95_response_time_ms: float = 0.0
    p99_response_time_ms: float = 0.0
    max_response_time_ms: float = 0.0
    min_response_time_ms: float = 0.0
    incidents: int = 0
    total_downtime_seconds: float = 0.0
    mttr_seconds: float = 0.0  # Mean Time To Recovery
    sla_target_percent: float = 99.9
    sla_compliant: bool = True
    sla_breach_count: int = 0


@dataclass
class Incident:
    """Registro de incidente."""
    endpoint_name: str
    start_time: str
    end_time: Optional[str] = None
    duration_seconds: float = 0.0
    reason: str = ""
    resolved: bool = False


@dataclass
class SLAWindow:
    """Métrica de SLA em uma janela temporal."""
    window_start: str
    window_end: str
    total_checks: int = 0
    successful_checks: int = 0
    failed_checks: int = 0
    uptime_percent: float = 100.0
    avg_response_time_ms: float = 0.0
    p95_response_time_ms: float = 0.0


@dataclass
class DegradationAlert:
    """Alerta de tendência de degradação de SLA."""
    endpoint_name: str
    severity: str
    reason: str
    previous_uptime_percent: float
    current_uptime_percent: float
    previous_p95_ms: float
    current_p95_ms: float
    detected_at: str


class SLAReporter:
    """Gerador de relatórios de SLA."""
    
    def __init__(self, history_db=None):
        """
        Args:
            history_db: Instância de HistoryDB (opcional, para dados reais)
        """
        self.history_db = history_db
        self._lock = threading.Lock()
        self._incidents: Dict[str, List[Incident]] = defaultdict(list)
        self._sla_targets: Dict[str, float] = {}  # endpoint -> target %
        self._default_sla_target = 99.9
    
    def set_sla_target(self, endpoint_name: str, target_percent: float):
        """Define target de SLA para um endpoint."""
        with self._lock:
            self._sla_targets[endpoint_name] = target_percent
    
    def get_sla_target(self, endpoint_name: str) -> float:
        """Retorna target de SLA para um endpoint."""
        with self._lock:
            return self._sla_targets.get(endpoint_name, self._default_sla_target)
    
    def record_incident(self, endpoint_name: str, reason: str = "") -> Incident:
        """Registra início de um incidente."""
        with self._lock:
            incident = Incident(
                endpoint_name=endpoint_name,
                start_time=datetime.utcnow().isoformat() + "Z",
                reason=reason
            )
            self._incidents[endpoint_name].append(incident)
            return incident
    
    def resolve_incident(self, endpoint_name: str) -> Optional[Incident]:
        """Resolve o último incidente aberto de um endpoint."""
        with self._lock:
            incidents = self._incidents.get(endpoint_name, [])
            for incident in reversed(incidents):
                if not incident.resolved:
                    incident.end_time = datetime.utcnow().isoformat() + "Z"
                    incident.resolved = True
                    # Calcular duração
                    start = datetime.fromisoformat(incident.start_time.replace("Z", ""))
                    end = datetime.fromisoformat(incident.end_time.replace("Z", ""))
                    incident.duration_seconds = (end - start).total_seconds()
                    return incident
            return None
    
    def get_open_incidents(self, endpoint_name: Optional[str] = None) -> List[Incident]:
        """Retorna incidentes abertos."""
        with self._lock:
            open_incidents = []
            endpoints = [endpoint_name] if endpoint_name else self._incidents.keys()
            for name in endpoints:
                for incident in self._incidents.get(name, []):
                    if not incident.resolved:
                        open_incidents.append(incident)
            return open_incidents
    
    def generate_report(
        self,
        endpoint_name: str,
        period_hours: int = 24,
        checks_data: Optional[List[Dict]] = None
    ) -> SLAMetrics:
        """
        Gera relatório de SLA para um endpoint.
        
        Args:
            endpoint_name: Nome do endpoint
            period_hours: Período em horas (padrão: 24h)
            checks_data: Lista de checks (opcional, usa history_db se não fornecido)
        
        Returns:
            SLAMetrics com métricas calculadas
        """
        now = datetime.utcnow()
        period_start = now - timedelta(hours=period_hours)
        
        # Obter dados de checks
        if checks_data is None:
            checks_data = self._get_checks_from_db(endpoint_name, period_start, now)
        
        if not checks_data:
            return SLAMetrics(
                endpoint_name=endpoint_name,
                period_start=period_start.isoformat() + "Z",
                period_end=now.isoformat() + "Z",
                sla_target_percent=self.get_sla_target(endpoint_name)
            )
        
        # Calcular métricas
        total = len(checks_data)
        successful = sum(1 for c in checks_data if c.get("status") == "success" or c.get("up", False))
        failed = total - successful
        uptime = (successful / total * 100) if total > 0 else 100.0
        
        # Response times
        response_times = [
            c.get("response_time_ms", c.get("response_time", 0))
            for c in checks_data
            if c.get("response_time_ms") or c.get("response_time")
        ]
        response_times.sort()
        
        avg_rt = sum(response_times) / len(response_times) if response_times else 0
        p95_idx = int(len(response_times) * 0.95)
        p99_idx = int(len(response_times) * 0.99)
        p95_rt = response_times[p95_idx] if response_times else 0
        p99_rt = response_times[p99_idx] if response_times else 0
        max_rt = max(response_times) if response_times else 0
        min_rt = min(response_times) if response_times else 0
        
        # Incidentes
        incidents = self._incidents.get(endpoint_name, [])
        period_incidents = [
            i for i in incidents
            if datetime.fromisoformat(i.start_time.replace("Z", "")) >= period_start
        ]
        incident_count = len(period_incidents)
        
        # Downtime total
        total_downtime = sum(
            i.duration_seconds for i in period_incidents if i.resolved
        )
        
        # MTTR (Mean Time To Recovery)
        resolved_incidents = [i for i in period_incidents if i.resolved and i.duration_seconds > 0]
        mttr = (
            sum(i.duration_seconds for i in resolved_incidents) / len(resolved_incidents)
            if resolved_incidents else 0
        )
        
        # SLA compliance
        sla_target = self.get_sla_target(endpoint_name)
        sla_compliant = uptime >= sla_target
        
        # SLA breach count (vezes que uptime ficou abaixo do target em janelas de 1h)
        sla_breach_count = self._calculate_breach_count(checks_data, sla_target, period_hours)
        
        return SLAMetrics(
            endpoint_name=endpoint_name,
            period_start=period_start.isoformat() + "Z",
            period_end=now.isoformat() + "Z",
            total_checks=total,
            successful_checks=successful,
            failed_checks=failed,
            uptime_percent=round(uptime, 4),
            avg_response_time_ms=round(avg_rt, 2),
            p95_response_time_ms=round(p95_rt, 2),
            p99_response_time_ms=round(p99_rt, 2),
            max_response_time_ms=round(max_rt, 2),
            min_response_time_ms=round(min_rt, 2),
            incidents=incident_count,
            total_downtime_seconds=round(total_downtime, 2),
            mttr_seconds=round(mttr, 2),
            sla_target_percent=sla_target,
            sla_compliant=sla_compliant,
            sla_breach_count=sla_breach_count
        )
    
    def generate_multi_endpoint_report(
        self,
        endpoint_names: List[str],
        period_hours: int = 24
    ) -> Dict[str, SLAMetrics]:
        """Gera relatório para múltiplos endpoints."""
        reports = {}
        for name in endpoint_names:
            reports[name] = self.generate_report(name, period_hours)
        return reports
    
    def export_json(self, report: SLAMetrics) -> str:
        """Exporta relatório como JSON."""
        return json.dumps(asdict(report), indent=2, ensure_ascii=False)
    
    def export_windows_json(self, windows: List[SLAWindow]) -> str:
        """Exporta janelas móveis como JSON."""
        return json.dumps([asdict(w) for w in windows], indent=2, ensure_ascii=False)
    
    def export_alerts_json(self, alerts: List[DegradationAlert]) -> str:
        """Exporta alertas de degradação como JSON."""
        return json.dumps([asdict(a) for a in alerts], indent=2, ensure_ascii=False)
    
    def export_csv(self, report: SLAMetrics) -> str:
        """Exporta relatório como CSV."""
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow(["Metric", "Value"])
        
        # Data
        data = asdict(report)
        for key, value in data.items():
            writer.writerow([key, value])
        
        return output.getvalue()
    
    def export_html(self, report: SLAMetrics) -> str:
        """Exporta relatório como HTML (dashboard-style)."""
        status_color = "#00ff00" if report.sla_compliant else "#ff0000"
        status_text = "COMPLIANT" if report.sla_compliant else "BREACH"
        
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SLA Report: {report.endpoint_name}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #0a0a0a;
            color: #e0e0e0;
            padding: 40px;
            max-width: 1200px;
            margin: 0 auto;
        }}
        .header {{
            border-bottom: 2px solid #dc143c;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        .header h1 {{
            color: #dc143c;
            margin: 0;
        }}
        .header .period {{
            color: #888;
            font-size: 0.9rem;
        }}
        .status-badge {{
            display: inline-block;
            padding: 8px 20px;
            background: {status_color};
            color: #000;
            font-weight: bold;
            border-radius: 4px;
            margin: 10px 0;
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }}
        .metric-card {{
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 8px;
            padding: 20px;
        }}
        .metric-card h3 {{
            color: #888;
            font-size: 0.85rem;
            text-transform: uppercase;
            margin: 0 0 10px 0;
        }}
        .metric-card .value {{
            font-size: 2rem;
            font-weight: bold;
            color: #fff;
        }}
        .metric-card .value.good {{ color: #00ff00; }}
        .metric-card .value.warn {{ color: #ffaa00; }}
        .metric-card .value.bad {{ color: #ff0000; }}
        .table-container {{
            margin: 30px 0;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #333;
        }}
        th {{
            background: #1a1a1a;
            color: #888;
            text-transform: uppercase;
            font-size: 0.8rem;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #333;
            color: #666;
            font-size: 0.85rem;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 SLA Report: {report.endpoint_name}</h1>
        <div class="period">
            {report.period_start} → {report.period_end}
        </div>
        <div class="status-badge">{status_text}</div>
    </div>
    
    <div class="metrics-grid">
        <div class="metric-card">
            <h3>Uptime</h3>
            <div class="value {'good' if report.uptime_percent >= 99.9 else 'warn' if report.uptime_percent >= 99.0 else 'bad'}">
                {report.uptime_percent:.2f}%
            </div>
        </div>
        <div class="metric-card">
            <h3>SLA Target</h3>
            <div class="value">{report.sla_target_percent}%</div>
        </div>
        <div class="metric-card">
            <h3>Avg Response Time</h3>
            <div class="value">{report.avg_response_time_ms:.1f}ms</div>
        </div>
        <div class="metric-card">
            <h3>P95 Response Time</h3>
            <div class="value">{report.p95_response_time_ms:.1f}ms</div>
        </div>
        <div class="metric-card">
            <h3>Incidents</h3>
            <div class="value {'good' if report.incidents == 0 else 'bad'}">
                {report.incidents}
            </div>
        </div>
        <div class="metric-card">
            <h3>Total Downtime</h3>
            <div class="value">{report.total_downtime_seconds:.0f}s</div>
        </div>
        <div class="metric-card">
            <h3>MTTR</h3>
            <div class="value">{report.mttr_seconds:.0f}s</div>
        </div>
        <div class="metric-card">
            <h3>SLA Breaches</h3>
            <div class="value {'good' if report.sla_breach_count == 0 else 'bad'}">
                {report.sla_breach_count}
            </div>
        </div>
    </div>
    
    <div class="table-container">
        <h2>Detailed Metrics</h2>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            <tr><td>Total Checks</td><td>{report.total_checks}</td></tr>
            <tr><td>Successful Checks</td><td>{report.successful_checks}</td></tr>
            <tr><td>Failed Checks</td><td>{report.failed_checks}</td></tr>
            <tr><td>Min Response Time</td><td>{report.min_response_time_ms:.1f}ms</td></tr>
            <tr><td>Max Response Time</td><td>{report.max_response_time_ms:.1f}ms</td></tr>
            <tr><td>P99 Response Time</td><td>{report.p99_response_time_ms:.1f}ms</td></tr>
        </table>
    </div>
    
    <div class="footer">
        Generated by Mengão Monitor v2.9 • {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
    </div>
</body>
</html>"""
    
    def _get_checks_from_db(
        self,
        endpoint_name: str,
        start: datetime,
        end: datetime
    ) -> List[Dict]:
        """Obtém checks do history_db."""
        if not self.history_db:
            return []
        
        try:
            # Assumindo que history_db tem método get_checks
            return self.history_db.get_checks(
                endpoint_name=endpoint_name,
                start_time=start,
                end_time=end
            )
        except (AttributeError, Exception):
            return []
    
    def _calculate_breach_count(
        self,
        checks_data: List[Dict],
        sla_target: float,
        period_hours: int
    ) -> int:
        """Calcula quantas janelas de 1h ficaram abaixo do SLA target."""
        if not checks_data:
            return 0
        
        # Agrupar checks por hora
        hourly_checks: Dict[str, List[Dict]] = defaultdict(list)
        for check in checks_data:
            ts = check.get("timestamp", check.get("checked_at", ""))
            if ts:
                hour_key = ts[:13]  # YYYY-MM-DDTHH
                hourly_checks[hour_key].append(check)
        
        # Contar breaches
        breach_count = 0
        for hour, checks in hourly_checks.items():
            successful = sum(
                1 for c in checks
                if c.get("status") == "success" or c.get("up", False)
            )
            total = len(checks)
            uptime = (successful / total * 100) if total > 0 else 100
            if uptime < sla_target:
                breach_count += 1
        
        return breach_count
    
    def _parse_check_time(self, check: Dict) -> Optional[datetime]:
        """Normaliza timestamp de checks vindos de fontes diferentes."""
        timestamp = (
            check.get("timestamp")
            or check.get("checked_at")
            or check.get("time")
            or check.get("created_at")
        )
        if not timestamp:
            return None
        try:
            return datetime.fromisoformat(str(timestamp).replace("Z", ""))
        except (ValueError, TypeError):
            return None
    
    def _check_success(self, check: Dict) -> bool:
        """Normaliza status de sucesso."""
        return check.get("status") == "success" or bool(check.get("up", False))
    
    def _calculate_window_metrics(self, checks: List[Dict], sla_target: float) -> SLAWindow:
        """Calcula métricas de uma janela isolada."""
        total = len(checks)
        successful = sum(1 for c in checks if self._check_success(c))
        failed = total - successful
        uptime = (successful / total * 100) if total > 0 else 100.0
        
        response_times = [
            c.get("response_time_ms", c.get("response_time", 0))
            for c in checks
            if c.get("response_time_ms") or c.get("response_time")
        ]
        response_times.sort()
        
        if not response_times:
            avg_rt = p95_rt = 0.0
        else:
            avg_rt = sum(response_times) / len(response_times)
            p95_idx = min(len(response_times) - 1, int(len(response_times) * 0.95))
            p95_rt = response_times[p95_idx]
        
        return SLAWindow(
            window_start="",
            window_end="",
            total_checks=total,
            successful_checks=successful,
            failed_checks=failed,
            uptime_percent=round(uptime, 4),
            avg_response_time_ms=round(avg_rt, 2),
            p95_response_time_ms=round(p95_rt, 2)
        )
    
    def generate_moving_windows(
        self,
        checks_data: List[Dict],
        window_minutes: int = 60,
        step_minutes: int = 15
    ) -> List[SLAWindow]:
        """Gera janelas móveis de SLA para análise de tendência.
        
        Útil para detectar degradação antes do SLA diário explodir.
        Exemplo: janela de 60 minutos avançando de 15 em 15 minutos.
        """
        if not checks_data:
            return []
        
        timestamps = [self._parse_check_time(c) for c in checks_data]
        timestamps = [t for t in timestamps if t is not None]
        if not timestamps:
            return []
        
        start = min(timestamps)
        end = max(timestamps)
        window = timedelta(minutes=window_minutes)
        step = timedelta(minutes=step_minutes)
        
        windows: List[SLAWindow] = []
        cursor = start
        while cursor <= end:
            window_end = cursor + window
            window_checks = [
                c for c in checks_data
                if (parsed := self._parse_check_time(c)) and cursor <= parsed < window_end
            ]
            metrics = self._calculate_window_metrics(window_checks, self._default_sla_target)
            metrics.window_start = cursor.isoformat() + "Z"
            metrics.window_end = window_end.isoformat() + "Z"
            windows.append(metrics)
            cursor += step
        
        return windows
    
    def detect_degradation(
        self,
        checks_data: List[Dict],
        window_minutes: int = 60,
        step_minutes: int = 15,
        uptime_drop_threshold: float = 2.0,
        p95_increase_percent: float = 25.0,
        min_windows: int = 2
    ) -> List[DegradationAlert]:
        """Detecta tendência de degradação comparando janelas móveis consecutivas."""
        windows = self.generate_moving_windows(checks_data, window_minutes, step_minutes)
        if len(windows) < min_windows:
            return []
        
        alerts: List[DegradationAlert] = []
        previous = windows[0]
        
        for current in windows[1:]:
            uptime_drop = previous.uptime_percent - current.uptime_percent
            p95_increase = (
                ((current.p95_response_time_ms - previous.p95_response_time_ms)
                 / previous.p95_response_time_ms * 100)
                if previous.p95_response_time_ms > 0 else 0
            )
            
            reasons = []
            severity = "WARN"
            
            if uptime_drop >= uptime_drop_threshold:
                reasons.append(f"uptime caiu {uptime_drop:.2f} pontos percentuais")
                severity = "CRITICAL" if current.uptime_percent < 99.0 else severity
            
            if p95_increase >= p95_increase_percent:
                reasons.append(f"p95 subiu {p95_increase:.1f}%")
            
            if reasons:
                alerts.append(DegradationAlert(
                    endpoint_name="",
                    severity=severity,
                    reason="; ".join(reasons),
                    previous_uptime_percent=previous.uptime_percent,
                    current_uptime_percent=current.uptime_percent,
                    previous_p95_ms=previous.p95_response_time_ms,
                    current_p95_ms=current.p95_response_time_ms,
                    detected_at=datetime.utcnow().isoformat() + "Z"
                ))
            
            previous = current
        
        return alerts
    
    def get_stats(self) -> Dict:
        """Retorna estatísticas do reporter."""
        with self._lock:
            total_incidents = sum(len(incidents) for incidents in self._incidents.values())
            open_incidents = sum(
                1 for incidents in self._incidents.values()
                for i in incidents if not i.resolved
            )
            return {
                "endpoints_tracked": len(self._incidents),
                "total_incidents": total_incidents,
                "open_incidents": open_incidents,
                "resolved_incidents": total_incidents - open_incidents,
                "sla_targets": dict(self._sla_targets),
                "default_sla_target": self._default_sla_target
            }
