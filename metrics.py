"""
Mengão Monitor - Prometheus Metrics Module
Exports monitoring metrics in Prometheus format.
"""

import time
from typing import Dict, Optional
from dataclasses import dataclass, field
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading


@dataclass
class EndpointMetrics:
    """Metrics for a single endpoint."""
    name: str
    url: str
    checks_total: int = 0
    checks_success: int = 0
    checks_failed: int = 0
    response_time_sum: float = 0.0
    response_time_count: int = 0
    last_response_time: float = 0.0
    last_status_code: int = 0
    last_check_timestamp: float = 0.0
    current_status: int = 1  # 1 = up, 0 = down
    uptime_seconds: float = 0.0
    downtime_seconds: float = 0.0
    last_status_change: float = field(default_factory=time.time)

    @property
    def uptime_percentage(self) -> float:
        if self.checks_total == 0:
            return 100.0
        return (self.checks_success / self.checks_total) * 100

    @property
    def avg_response_time(self) -> float:
        if self.response_time_count == 0:
            return 0.0
        return self.response_time_sum / self.response_time_count


class PrometheusMetrics:
    """Prometheus-compatible metrics exporter."""

    def __init__(self, service_name: str = "mengao_monitor"):
        self.service_name = service_name
        self.endpoints: Dict[str, EndpointMetrics] = {}
        self.start_time = time.time()
        self._lock = threading.Lock()

    def register_endpoint(self, name: str, url: str) -> None:
        """Register an endpoint for metrics tracking."""
        with self._lock:
            if name not in self.endpoints:
                self.endpoints[name] = EndpointMetrics(name=name, url=url)

    def record_check(
        self,
        name: str,
        success: bool,
        response_time_ms: float,
        status_code: int = 0,
    ) -> None:
        """Record a check result."""
        with self._lock:
            if name not in self.endpoints:
                return

            ep = self.endpoints[name]
            ep.checks_total += 1
            ep.response_time_sum += response_time_ms
            ep.response_time_count += 1
            ep.last_response_time = response_time_ms
            ep.last_status_code = status_code
            ep.last_check_timestamp = time.time()

            old_status = ep.current_status

            if success:
                ep.checks_success += 1
                ep.current_status = 1
            else:
                ep.checks_failed += 1
                ep.current_status = 0

            # Update uptime/downtime
            now = time.time()
            elapsed = now - ep.last_status_change
            if old_status == 1:
                ep.uptime_seconds += elapsed
            else:
                ep.downtime_seconds += elapsed
            ep.last_status_change = now

    def get_metrics_text(self) -> str:
        """Generate Prometheus text format metrics."""
        lines = []
        
        # Uptime gauge
        lines.append("# HELP mengao_monitor_uptime_seconds Mengao Monitor process uptime")
        lines.append("# TYPE mengao_monitor_uptime_seconds gauge")
        lines.append(f"mengao_monitor_uptime_seconds {time.time() - self.start_time:.1f}")

        if not self.endpoints:
            return "\n".join(lines)

        # Endpoint up gauge
        lines.append("")
        lines.append("# HELP mengao_monitor_endpoint_up Whether endpoint is up (1) or down (0)")
        lines.append("# TYPE mengao_monitor_endpoint_up gauge")
        for ep in self.endpoints.values():
            lines.append(f'mengao_monitor_endpoint_up{{name="{ep.name}",url="{ep.url}"}} {ep.current_status}')

        # Checks total counter
        lines.append("")
        lines.append("# HELP mengao_monitor_checks_total Total number of checks performed")
        lines.append("# TYPE mengao_monitor_checks_total counter")
        for ep in self.endpoints.values():
            lines.append(f'mengao_monitor_checks_total{{name="{ep.name}",result="success"}} {ep.checks_success}')
            lines.append(f'mengao_monitor_checks_total{{name="{ep.name}",result="failure"}} {ep.checks_failed}')

        # Response time histogram (simplified)
        lines.append("")
        lines.append("# HELP mengao_monitor_response_time_ms Response time in milliseconds")
        lines.append("# TYPE mengao_monitor_response_time_ms gauge")
        for ep in self.endpoints.values():
            lines.append(f'mengao_monitor_response_time_ms{{name="{ep.name}",type="last"}} {ep.last_response_time:.2f}')
            lines.append(f'mengao_monitor_response_time_ms{{name="{ep.name}",type="avg"}} {ep.avg_response_time:.2f}')

        # Uptime percentage
        lines.append("")
        lines.append("# HELP mengao_monitor_uptime_percentage Uptime percentage")
        lines.append("# TYPE mengao_monitor_uptime_percentage gauge")
        for ep in self.endpoints.values():
            lines.append(f'mengao_monitor_uptime_percentage{{name="{ep.name}"}} {ep.uptime_percentage:.2f}')

        # Last status code
        lines.append("")
        lines.append("# HELP mengao_monitor_last_status_code Last HTTP status code received")
        lines.append("# TYPE mengao_monitor_last_status_code gauge")
        for ep in self.endpoints.values():
            lines.append(f'mengao_monitor_last_status_code{{name="{ep.name}"}} {ep.last_status_code}')

        # Last check timestamp
        lines.append("")
        lines.append("# HELP mengao_monitor_last_check_timestamp Unix timestamp of last check")
        lines.append("# TYPE mengao_monitor_last_check_timestamp gauge")
        for ep in self.endpoints.values():
            lines.append(f'mengao_monitor_last_check_timestamp{{name="{ep.name}"}} {ep.last_check_timestamp:.0f}')

        return "\n".join(lines)

    def get_summary(self) -> Dict:
        """Get metrics summary as dict."""
        return {
            "uptime_seconds": time.time() - self.start_time,
            "endpoints": {
                name: {
                    "url": ep.url,
                    "up": bool(ep.current_status),
                    "checks_total": ep.checks_total,
                    "uptime_percentage": ep.uptime_percentage,
                    "avg_response_time_ms": ep.avg_response_time,
                    "last_response_time_ms": ep.last_response_time,
                    "last_status_code": ep.last_status_code,
                }
                for name, ep in self.endpoints.items()
            },
        }


class MetricsHandler(BaseHTTPRequestHandler):
    """HTTP handler for Prometheus metrics endpoint."""

    metrics: Optional[PrometheusMetrics] = None

    def do_GET(self) -> None:
        if self.path == "/metrics":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.end_headers()
            if self.metrics:
                self.wfile.write(self.metrics.get_metrics_text().encode())
        elif self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"healthy","service":"mengao-monitor"}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args) -> None:
        """Suppress default HTTP logging."""
        pass


def start_metrics_server(
    metrics: PrometheusMetrics,
    host: str = "0.0.0.0",
    port: int = 9090,
) -> HTTPServer:
    """
    Start Prometheus metrics HTTP server in background thread.
    
    Args:
        metrics: PrometheusMetrics instance
        host: Bind address
        port: Bind port
        
    Returns:
        HTTPServer instance (already running in thread)
    """
    MetricsHandler.metrics = metrics
    server = HTTPServer((host, port), MetricsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


if __name__ == "__main__":
    # Demo metrics
    m = PrometheusMetrics()
    m.register_endpoint("flamengo.com", "https://www.flamengo.com.br")
    m.register_endpoint("api.test", "https://api.test.com/health")
    
    # Simulate some checks
    m.record_check("flamengo.com", True, 142.5, 200)
    m.record_check("flamengo.com", True, 156.3, 200)
    m.record_check("api.test", False, 5000.0, 0)
    m.record_check("api.test", True, 89.2, 200)
    
    print(m.get_metrics_text())
