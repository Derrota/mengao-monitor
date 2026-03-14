"""
Example plugins for Mengão Monitor v2.5

Demonstrates how to create custom plugins.
"""

import json
import time
import ssl
import socket
from datetime import datetime
from pathlib import Path

from plugins import HealthCheckPlugin, AlertHandlerPlugin, ExporterPlugin, HookPlugin


# ─── Health Check: SSL Certificate Validator ─────────────────────────

class SSLCheckPlugin(HealthCheckPlugin):
    """Validates SSL certificate expiration for HTTPS endpoints."""
    
    name = "ssl_check"
    version = "1.0.0"
    description = "Checks SSL certificate expiration and validity"
    
    def __init__(self):
        super().__init__()
        self.warning_days = 30  # Warn if cert expires within 30 days
    
    def initialize(self, config: dict) -> None:
        super().initialize(config)
        self.warning_days = config.get("warning_days", 30)
    
    def check(self, api_name: str, url: str, config: dict = None) -> dict:
        """Check SSL certificate for the given URL."""
        if not url.startswith("https://"):
            return {
                "status": "ok",
                "message": "Not an HTTPS endpoint, skipping SSL check",
                "skipped": True,
            }
        
        try:
            # Extract hostname from URL
            hostname = url.split("://")[1].split("/")[0].split(":")[0]
            port = 443
            
            # Get certificate
            context = ssl.create_default_context()
            with socket.create_connection((hostname, port), timeout=10) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
            
            # Parse expiration
            not_after = cert.get("notAfter", "")
            if not_after:
                expires = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
                days_left = (expires - datetime.now()).days
                
                if days_left < 0:
                    return {
                        "status": "error",
                        "message": f"SSL certificate EXPIRED {abs(days_left)} days ago!",
                        "days_left": days_left,
                        "expires": expires.isoformat(),
                    }
                elif days_left < self.warning_days:
                    return {
                        "status": "degraded",
                        "message": f"SSL certificate expires in {days_left} days",
                        "days_left": days_left,
                        "expires": expires.isoformat(),
                    }
                else:
                    return {
                        "status": "ok",
                        "message": f"SSL certificate valid for {days_left} days",
                        "days_left": days_left,
                        "expires": expires.isoformat(),
                        "issuer": dict(x[0] for x in cert.get("issuer", [])).get("organizationName", "unknown"),
                    }
            
            return {
                "status": "degraded",
                "message": "Could not parse certificate expiration",
            }
            
        except ssl.SSLError as e:
            return {
                "status": "error",
                "message": f"SSL error: {str(e)}",
            }
        except socket.timeout:
            return {
                "status": "error",
                "message": "Connection timed out during SSL check",
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"SSL check failed: {str(e)}",
            }


# ─── Health Check: Response Time SLO ─────────────────────────────────

class ResponseTimeSLOPlugin(HealthCheckPlugin):
    """Checks if response time meets SLO thresholds."""
    
    name = "response_time_slo"
    version = "1.0.0"
    description = "Validates response time against SLO thresholds"
    
    def __init__(self):
        super().__init__()
        self.thresholds = {
            "fast": 200,      # < 200ms = fast
            "acceptable": 500, # < 500ms = acceptable
            "slow": 1000,      # < 1000ms = slow
            # >= 1000ms = critical
        }
    
    def initialize(self, config: dict) -> None:
        super().initialize(config)
        self.thresholds.update(config.get("thresholds", {}))
    
    def check(self, api_name: str, url: str, config: dict = None) -> dict:
        """Check response time (expects latency_ms in config from main monitor)."""
        # This plugin relies on the main monitor providing latency
        # In a real scenario, it would make its own request
        latency = config.get("latency_ms") if config else None
        
        if latency is None:
            return {
                "status": "ok",
                "message": "No latency data available",
                "skipped": True,
            }
        
        if latency < self.thresholds["fast"]:
            rating = "fast"
            status = "ok"
        elif latency < self.thresholds["acceptable"]:
            rating = "acceptable"
            status = "ok"
        elif latency < self.thresholds["slow"]:
            rating = "slow"
            status = "degraded"
        else:
            rating = "critical"
            status = "error"
        
        return {
            "status": status,
            "message": f"Response time: {latency}ms ({rating})",
            "latency_ms": latency,
            "rating": rating,
            "thresholds": self.thresholds,
        }


# ─── Alert Handler: Console Logger ───────────────────────────────────

class ConsoleAlertPlugin(AlertHandlerPlugin):
    """Logs alerts to console/stdout."""
    
    name = "console_alert"
    version = "1.0.0"
    description = "Prints alerts to console with color coding"
    
    COLORS = {
        "ok": "\033[92m",       # Green
        "degraded": "\033[93m",  # Yellow
        "error": "\033[91m",     # Red
        "reset": "\033[0m",
    }
    
    def initialize(self, config: dict) -> None:
        super().initialize(config)
        self.use_colors = config.get("use_colors", True)
    
    def send_alert(self, alert: dict) -> bool:
        """Print alert to console."""
        status = alert.get("status", "unknown")
        formatted = self.format_alert(alert)
        
        if self.use_colors:
            color = self.COLORS.get(status, "")
            reset = self.COLORS["reset"]
            print(f"{color}[ALERT] {formatted}{reset}")
        else:
            print(f"[ALERT] {formatted}")
        
        return True


# ─── Alert Handler: File Logger ──────────────────────────────────────

class FileAlertPlugin(AlertHandlerPlugin):
    """Logs alerts to a file."""
    
    name = "file_alert"
    version = "1.0.0"
    description = "Writes alerts to a log file"
    
    def initialize(self, config: dict) -> None:
        super().initialize(config)
        self.log_file = config.get("log_file", "alerts.log")
        self.log_path = Path(self.log_file)
    
    def send_alert(self, alert: dict) -> bool:
        """Append alert to log file."""
        try:
            formatted = self.format_alert(alert)
            timestamp = datetime.now().isoformat()
            
            with open(self.log_path, "a") as f:
                f.write(f"{timestamp} [{alert.get('status', 'unknown')}] {formatted}\n")
            
            return True
        except Exception as e:
            print(f"FileAlert error: {e}")
            return False


# ─── Exporter: JSON File ─────────────────────────────────────────────

class JSONExporterPlugin(ExporterPlugin):
    """Exports metrics to a JSON file."""
    
    name = "json_exporter"
    version = "1.0.0"
    description = "Exports metrics to JSON files"
    
    def initialize(self, config: dict) -> None:
        super().initialize(config)
        self.export_dir = Path(config.get("export_dir", "./metrics_export"))
        self.export_dir.mkdir(parents=True, exist_ok=True)
    
    def export(self, metrics: dict) -> bool:
        """Export metrics to a timestamped JSON file."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = self.export_dir / f"metrics_{timestamp}.json"
            
            with open(filename, "w") as f:
                json.dump(metrics, f, indent=2, default=str)
            
            # Also write to latest.json
            latest = self.export_dir / "latest.json"
            with open(latest, "w") as f:
                json.dump(metrics, f, indent=2, default=str)
            
            return True
        except Exception as e:
            print(f"JSONExporter error: {e}")
            return False


# ─── Hook: Startup/Shutdown Logger ───────────────────────────────────

class LifecycleHookPlugin(HookPlugin):
    """Logs lifecycle events."""
    
    name = "lifecycle_hook"
    version = "1.0.0"
    description = "Logs startup, shutdown, and other lifecycle events"
    
    def initialize(self, config: dict) -> None:
        super().initialize(config)
        self.register_hook("startup", self._on_startup)
        self.register_hook("shutdown", self._on_shutdown)
        self.register_hook("before_check", self._on_before_check)
        self.register_hook("after_check", self._on_after_check)
    
    def _on_startup(self, **kwargs) -> str:
        msg = f"Mengão Monitor started at {datetime.now().isoformat()}"
        print(f"[LIFECYCLE] {msg}")
        return msg
    
    def _on_shutdown(self, **kwargs) -> str:
        msg = f"Mengão Monitor shutting down at {datetime.now().isoformat()}"
        print(f"[LIFECYCLE] {msg}")
        return msg
    
    def _on_before_check(self, api_name: str = None, **kwargs) -> str:
        msg = f"Checking {api_name or 'unknown API'}..."
        return msg
    
    def _on_after_check(self, api_name: str = None, status: str = None, **kwargs) -> str:
        msg = f"Check complete: {api_name or 'unknown'} = {status or 'unknown'}"
        return msg
