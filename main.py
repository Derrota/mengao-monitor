"""
Mengão Monitor - Main Entry Point
Orchestrates all components: config, logging, metrics, webhooks, history.
v2.1: API REST + Hot-reload de configuração
"""

import argparse
import json
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from config import MonitorConfig, load_config, create_sample_config, EmailConfig
from logger import setup_logging, get_logger, get_api_logger, get_webhook_logger, LogContext
from metrics import PrometheusMetrics, start_metrics_server
from webhooks import WebhookSender
from history import UptimeHistory
from email_alerts import EmailAlerter
from health import update_state, set_webhook_sender, start_health_server
from api_manager import endpoint_manager, start_api_server, EndpointRuntime
from config_watcher import ConfigWatcher, ConfigDiff


class MengaoMonitor:
    """Main monitor class. v2.1 with API + Hot-reload."""

    def __init__(self, config: MonitorConfig, config_path: str = "config.json"):
        self.config = config
        self.config_path = config_path
        self.logger = get_logger("main")
        self.api_logger = get_api_logger()
        self.webhook_logger = get_webhook_logger()
        
        # Metrics
        self.metrics = PrometheusMetrics()
        for ep in config.endpoints:
            self.metrics.register_endpoint(ep.name, ep.url)
        
        # Webhooks
        webhooks_config = [
            {"type": wh.platform, "url": wh.url, "enabled": wh.enabled}
            for wh in config.webhooks
        ]
        self.webhook_sender = WebhookSender(webhooks_config)
        set_webhook_sender(self.webhook_sender)
        
        # History
        self.history: Optional[UptimeHistory] = None
        if config.history.enabled:
            self.history = UptimeHistory(config.history.db_path)
        
        # Email alerts
        self.email_alerter: Optional[EmailAlerter] = None
        if config.email.enabled:
            self.email_alerter = EmailAlerter(config.email)
            if self.email_alerter.enabled:
                self.logger.info(f"📧 Email alerts enabled → {', '.join(config.email.to_emails)}")
        
        # State
        self.running = False
        self.start_time = time.time()
        self.checks_count = 0
        self.errors_count = 0
        
        # Previous status for change detection
        self.previous_status: dict = {}
        
        # Config watcher (hot-reload)
        self.config_watcher = ConfigWatcher(
            config_path=config_path,
            callback=self._on_config_reload,
            check_interval=10
        )
        self.config_watcher.on_reload_start(self._on_reload_start)
        self.config_watcher.on_reload_success(self._on_reload_success)
        self.config_watcher.on_reload_error(self._on_reload_error)
        
        # Load endpoints into API manager
        self._sync_endpoints_to_api_manager()
        
        # Register API manager change callback
        endpoint_manager.on_change(self._on_endpoint_change)

    def _sync_endpoints_to_api_manager(self):
        """Sincroniza endpoints do config para o API manager."""
        for ep in self.config.endpoints:
            endpoint_manager.add_endpoint({
                'name': ep.name,
                'url': ep.url,
                'method': ep.method,
                'timeout': ep.timeout,
                'expected_status': ep.expected_status,
                'interval': ep.interval,
                'enabled': ep.enabled,
                'tags': list(ep.tags) if ep.tags else [],
                'headers': dict(ep.headers) if ep.headers else {},
                'body': ep.body,
            })

    def _on_config_reload(self, new_config: dict):
        """Callback para hot-reload de config."""
        self.logger.info("🔄 Hot-reload: Processing config changes...")
        
        # TODO: Implement full config reload
        # For now, just log the change
        if 'endpoints' in new_config:
            diff = ConfigDiff.endpoints_diff(
                [ep.__dict__ for ep in self.config.endpoints],
                new_config['endpoints']
            )
            self.logger.info(f"  Added: {len(diff['added'])} endpoints")
            self.logger.info(f"  Removed: {len(diff['removed'])} endpoints")
            self.logger.info(f"  Modified: {len(diff['modified'])} endpoints")

    def _on_reload_start(self, config_path):
        """Callback para início de reload."""
        self.logger.info(f"🔄 Config change detected: {config_path}")

    def _on_reload_success(self, new_config):
        """Callback para reload bem-sucedido."""
        self.logger.info("✅ Config reloaded successfully")

    def _on_reload_error(self, error):
        """Callback para erro de reload."""
        self.logger.error(f"❌ Config reload failed: {error}")

    def _on_endpoint_change(self, action: str, name: str):
        """Callback para mudanças via API."""
        self.logger.info(f"🔧 API: Endpoint '{name}' {action}")
        
        if action == 'added':
            endpoint = endpoint_manager.get_endpoint(name)
            if endpoint:
                self.metrics.register_endpoint(endpoint.name, endpoint.url)
        
        # Config watcher (hot-reload)
        self.config_watcher = ConfigWatcher(
            config_path=config_path,
            callback=self._on_config_reload,
            check_interval=10
        )
        self.config_watcher.on_reload_start(self._on_reload_start)
        self.config_watcher.on_reload_success(self._on_reload_success)
        self.config_watcher.on_reload_error(self._on_reload_error)
        
        # Load endpoints into API manager
        self._sync_endpoints_to_api_manager()
        
        # Register API manager change callback
        endpoint_manager.on_change(self._on_endpoint_change)

    def check_endpoint(self, endpoint_config) -> dict:
        """
        Check a single API endpoint.
        
        Returns:
            dict with check results
        """
        name = endpoint_config.name
        url = endpoint_config.url
        
        self.api_logger.check_started(name, url)
        
        result = {
            "name": name,
            "url": url,
            "status": "unknown",
            "status_code": 0,
            "response_time_ms": 0,
            "error": None,
            "timestamp": datetime.now().isoformat(),
        }
        
        try:
            start = time.time()
            response = requests.request(
                method=endpoint_config.method,
                url=url,
                timeout=endpoint_config.timeout,
                headers=endpoint_config.headers,
                data=endpoint_config.body,
            )
            elapsed_ms = (time.time() - start) * 1000
            
            result["status_code"] = response.status_code
            result["response_time_ms"] = round(elapsed_ms, 2)
            
            if response.status_code == endpoint_config.expected_status:
                result["status"] = "online"
                self.api_logger.check_success(name, response.status_code, elapsed_ms)
                
                # Check if slow
                if elapsed_ms > 1000:  # 1s threshold
                    self.api_logger.check_slow(name, elapsed_ms, 1000)
            else:
                result["status"] = "error"
                result["error"] = f"Status {response.status_code} (expected {endpoint_config.expected_status})"
                self.api_logger.check_failure(name, result["error"], response.status_code)
                
        except requests.exceptions.Timeout:
            result["status"] = "timeout"
            result["error"] = f"Timeout after {endpoint_config.timeout}s"
            self.api_logger.check_failure(name, result["error"])
            
        except requests.exceptions.ConnectionError as e:
            result["status"] = "offline"
            result["error"] = f"Connection error: {str(e)[:100]}"
            self.api_logger.check_failure(name, result["error"])
            
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)[:200]
            self.api_logger.check_failure(name, result["error"])
        
        return result

    def handle_status_change(self, endpoint_name: str, old_status: str, new_status: str, result: dict) -> None:
        """Handle endpoint status change - send alerts."""
        if old_status == new_status:
            return
        
        self.api_logger.status_change(endpoint_name, old_status, new_status)
        
        # Determine event type
        if new_status == "online":
            event = "up"
        elif new_status in ("offline", "timeout"):
            event = "down"
        else:
            event = "error"
        
        # Send webhook
        try:
            self.webhook_sender.send(result, self.logger)
            self.webhook_logger.sent("configured", event, endpoint_name)
        except Exception as e:
            self.webhook_logger.failed("configured", event, str(e))
        
        # Send email alert (only for down/recovery)
        if self.email_alerter and self.email_alerter.enabled:
            try:
                if new_status != "online":
                    self.email_alerter.send_alert(
                        api_name=endpoint_name,
                        url=result.get("url", ""),
                        error=result.get("error", "Unknown"),
                        status_code=result.get("status_code")
                    )
                elif old_status != "unknown" and old_status != "online":
                    # Recovery
                    self.email_alerter.send_recovery(
                        api_name=endpoint_name,
                        url=result.get("url", ""),
                        response_time_ms=result.get("response_time_ms", 0)
                    )
            except Exception as e:
                self.logger.error(f"Email alert failed: {e}")

    def run_check_cycle(self) -> None:
        """Run one check cycle for all endpoints."""
        with LogContext(self.logger, cycle=self.checks_count):
            self.logger.info(f"Starting check cycle #{self.checks_count}")
            
            for endpoint in self.config.endpoints:
                if not endpoint.enabled:
                    continue
                
                result = self.check_endpoint(endpoint)
                
                # Record metrics
                success = result["status"] == "online"
                self.metrics.record_check(
                    endpoint.name,
                    success,
                    result["response_time_ms"],
                    result["status_code"],
                )
                
                # Detect status change
                old_status = self.previous_status.get(endpoint.name, "unknown")
                self.handle_status_change(endpoint.name, old_status, result["status"], result)
                self.previous_status[endpoint.name] = result["status"]
                
                # Record history
                if self.history:
                    try:
                        self.history.record_check(result)
                    except Exception as e:
                        self.logger.error(f"Failed to record history: {e}")
                
                if not success:
                    self.errors_count += 1
            
            self.checks_count += 1
            self.logger.info(f"Check cycle complete. Next in {self._get_min_interval()}s")

    def _get_min_interval(self) -> int:
        """Get minimum check interval from endpoints."""
        return min((ep.interval for ep in self.config.endpoints if ep.enabled), default=60)

    def run(self) -> None:
        """Main run loop."""
        self.running = True
        
        self.logger.info("=" * 60)
        self.logger.info("🦞 MENGÃO MONITOR v2.1 INICIADO")
        self.logger.info("=" * 60)
        self.logger.info(f"Endpoints: {len([e for e in self.config.endpoints if e.enabled])}")
        self.logger.info(f"Webhooks: {len([w for w in self.config.webhooks if w.enabled])}")
        self.logger.info(f"Dashboard: {'enabled' if self.config.dashboard.enabled else 'disabled'}")
        self.logger.info(f"History: {'enabled' if self.config.history.enabled else 'disabled'}")
        self.logger.info(f"Metrics: {'enabled' if self.config.metrics_enabled else 'disabled'}")
        self.logger.info(f"API Manager: enabled on :8081")
        self.logger.info(f"Hot-reload: enabled (10s interval)")
        
        # Start metrics server
        if self.config.metrics_enabled:
            server = start_metrics_server(
                self.metrics,
                host=self.config.dashboard.host,
                port=self.config.metrics_port,
            )
            self.logger.info(f"📊 Metrics server on :{self.config.metrics_port}/metrics")
        
        # Start API server
        start_api_server(port=8081)
        self.logger.info(f"🔧 API server on :8081/api/v1/endpoints")
        
        # Start config watcher
        self.config_watcher.start()
        self.logger.info(f"👁️ Config watcher started: {self.config_path}")
        
        # Signal handling
        def shutdown(signum, frame):
            self.logger.info("Shutdown signal received")
            self.running = False
        
        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)
        
        # Main loop
        while self.running:
            try:
                self.run_check_cycle()
                
                # Sleep until next cycle
                interval = self._get_min_interval()
                for _ in range(interval):
                    if not self.running:
                        break
                    time.sleep(1)
                    
            except Exception as e:
                self.logger.error(f"Error in check cycle: {e}", exc_info=True)
                time.sleep(10)
        
        # Cleanup
        self.config_watcher.stop()
        self.logger.info("🦞 Mengão Monitor stopped")

    def run_once(self) -> None:
        """Run a single check cycle and exit."""
        self.logger.info("Running single check cycle...")
        self.run_check_cycle()
        
        # Print summary
        print("\n🦞 Mengão Monitor - Check Results\n")
        for name, status in self.previous_status.items():
            icon = "✅" if status == "online" else "❌"
            print(f"  {icon} {name}: {status}")
        print()

    def show_stats(self) -> None:
        """Show statistics and exit."""
        if not self.history:
            print("History is disabled")
            return
        
        stats = self.history.get_all_apis_stats(hours=24)
        
        print("\n🦞 Mengão Monitor - Statistics (24h)\n")
        for api_name, data in stats.items():
            uptime = data.get("uptime_percent", 0)
            icon = "✅" if uptime >= 99 else "⚠️" if uptime >= 95 else "❌"
            print(f"  {icon} {api_name}")
            print(f"     Uptime: {uptime}%")
            print(f"     Checks: {data.get('total_checks', 0)}")
            avg = data.get("avg_response_time")
            print(f"     Avg Response: {avg if avg else 'N/A'}s")
            print()


def create_default_config(path: str = "config.json") -> None:
    """Create a default configuration file."""
    default = {
        "endpoints": [
            {
                "name": "Flamengo Site",
                "url": "https://www.flamengo.com.br",
                "method": "GET",
                "timeout": 15,
                "expected_status": 200,
                "interval": 120,
                "tags": ["flamengo", "site"]
            }
        ],
        "webhooks": [],
        "dashboard": {
            "enabled": True,
            "port": 8080,
            "theme": "dark"
        },
        "history": {
            "enabled": True,
            "db_path": "uptime_history.db"
        },
        "log_level": "INFO",
        "log_format": "text",
        "metrics_enabled": True,
        "metrics_port": 9090
    }
    
    with open(path, "w") as f:
        json.dump(default, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Default config created: {path}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="🦞 Mengão Monitor v2.1 - API Monitoring Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mengao-monitor                    # Run with config.json
  mengao-monitor -c config.yaml    # Run with YAML config
  mengao-monitor --check           # Single check and exit
  mengao-monitor --stats           # Show 24h statistics
  mengao-monitor --init            # Create default config
  mengao-monitor --sample          # Create sample config

API Endpoints (runtime):
  GET  /api/v1/endpoints           # List all endpoints
  POST /api/v1/endpoints           # Add new endpoint
  GET  /api/v1/endpoints/<name>    # Get endpoint details
  PUT  /api/v1/endpoints/<name>    # Update endpoint
  DELETE /api/v1/endpoints/<name>  # Remove endpoint
  POST /api/v1/endpoints/<name>/pause  # Pause endpoint
  POST /api/v1/endpoints/<name>/resume # Resume endpoint
  GET  /api/v1/stats               # Manager statistics
        """,
    )
    
    parser.add_argument("-c", "--config", default="config.json", help="Config file path (JSON or YAML)")
    parser.add_argument("--check", action="store_true", help="Run single check cycle and exit")
    parser.add_argument("--stats", action="store_true", help="Show statistics and exit")
    parser.add_argument("--init", action="store_true", help="Create default config.json")
    parser.add_argument("--sample", action="store_true", help="Create sample config with all options")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Override log level")
    parser.add_argument("--log-format", choices=["json", "text"], help="Override log format")
    
    args = parser.parse_args()
    
    # One-shot commands
    if args.init:
        create_default_config()
        return
    
    if args.sample:
        create_sample_config()
        return
    
    # Load config
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print(f"❌ Config not found: {args.config}")
        print("💡 Run with --init to create default config")
        sys.exit(1)
    except ValueError as e:
        print(f"❌ Config error:\n{e}")
        sys.exit(1)
    except ImportError as e:
        print(f"❌ {e}")
        sys.exit(1)
    
    # Override settings from CLI
    if args.log_level:
        config.log_level = args.log_level
    if args.log_format:
        config.log_format = args.log_format
    
    # Setup logging
    setup_logging(level=config.log_level, format_type=config.log_format)
    
    # Create monitor
    monitor = MengaoMonitor(config, config_path=args.config)
    
    # Run
    if args.stats:
        monitor.show_stats()
    elif args.check:
        monitor.run_once()
    else:
        monitor.run()


if __name__ == "__main__":
    main()
