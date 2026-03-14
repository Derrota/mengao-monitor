"""
Mengão Monitor - Configuration Module
Handles YAML/JSON config loading with validation and defaults.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


@dataclass
class APIEndpoint:
    """Configuration for a single API endpoint to monitor."""
    name: str
    url: str
    method: str = "GET"
    timeout: int = 10
    expected_status: int = 200
    headers: Dict[str, str] = field(default_factory=dict)
    body: Optional[str] = None
    interval: int = 60  # seconds
    enabled: bool = True
    tags: List[str] = field(default_factory=list)

    def validate(self) -> List[str]:
        """Validate endpoint configuration, return list of errors."""
        errors = []
        if not self.name:
            errors.append("Endpoint name is required")
        if not self.url:
            errors.append("Endpoint URL is required")
        if not self.url.startswith(("http://", "https://")):
            errors.append(f"Invalid URL scheme: {self.url}")
        if self.method not in ("GET", "POST", "PUT", "DELETE", "HEAD", "PATCH"):
            errors.append(f"Invalid HTTP method: {self.method}")
        if self.timeout < 1:
            errors.append("Timeout must be at least 1 second")
        if self.interval < 5:
            errors.append("Interval must be at least 5 seconds")
        return errors


@dataclass
class WebhookConfig:
    """Configuration for webhook notifications."""
    platform: str  # discord, slack, telegram, generic
    url: str
    enabled: bool = True
    events: List[str] = field(default_factory=lambda: ["down", "up", "slow"])
    cooldown: int = 300  # seconds between repeated alerts
    min_severity: str = "warning"  # info, warning, critical

    def validate(self) -> List[str]:
        errors = []
        if self.platform not in ("discord", "slack", "telegram", "generic"):
            errors.append(f"Invalid platform: {self.platform}")
        if not self.url:
            errors.append("Webhook URL is required")
        if self.min_severity not in ("info", "warning", "critical"):
            errors.append(f"Invalid severity: {self.min_severity}")
        return errors


@dataclass
class DashboardConfig:
    """Configuration for the web dashboard."""
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8080
    refresh_interval: int = 30  # seconds
    theme: str = "dark"  # dark, light
    title: str = "Mengão Monitor"

    def validate(self) -> List[str]:
        errors = []
        if self.port < 1 or self.port > 65535:
            errors.append(f"Invalid port: {self.port}")
        if self.refresh_interval < 5:
            errors.append("Refresh interval must be at least 5 seconds")
        return errors


@dataclass
class HistoryConfig:
    """Configuration for uptime history tracking."""
    enabled: bool = True
    db_path: str = "uptime_history.db"
    retention_days: int = 90
    export_format: str = "csv"  # csv, json

    def validate(self) -> List[str]:
        errors = []
        if self.retention_days < 1:
            errors.append("Retention must be at least 1 day")
        if self.export_format not in ("csv", "json"):
            errors.append(f"Invalid export format: {self.export_format}")
        return errors


@dataclass
class EmailConfig:
    """Configuration for email alerts."""
    enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    username: str = ""
    password: str = ""
    from_email: str = ""
    to_emails: List[str] = field(default_factory=list)
    use_tls: bool = True
    events: List[str] = field(default_factory=lambda: ["down", "up"])
    cooldown: int = 300  # seconds between alerts for same endpoint

    def validate(self) -> List[str]:
        errors = []
        if self.enabled:
            if not self.smtp_host:
                errors.append("SMTP host is required when email is enabled")
            if self.smtp_port < 1 or self.smtp_port > 65535:
                errors.append(f"Invalid SMTP port: {self.smtp_port}")
            if not self.username:
                errors.append("Email username is required")
            if not self.password:
                errors.append("Email password is required")
            if not self.from_email:
                errors.append("From email address is required")
            if not self.to_emails:
                errors.append("At least one recipient email is required")
            if self.cooldown < 0:
                errors.append("Cooldown cannot be negative")
        return errors


@dataclass
class WebSocketConfig:
    """Configuration for WebSocket server (v3.0)."""
    enabled: bool = False
    host: str = "localhost"
    port: int = 8082
    ping_interval: int = 30  # seconds
    ping_timeout: int = 10  # seconds
    max_history: int = 100  # max messages in history

    def validate(self) -> List[str]:
        errors = []
        if self.port < 1 or self.port > 65535:
            errors.append(f"Invalid WebSocket port: {self.port}")
        if self.ping_interval < 5:
            errors.append("Ping interval must be at least 5 seconds")
        if self.ping_timeout < 1:
            errors.append("Ping timeout must be at least 1 second")
        if self.max_history < 10:
            errors.append("Max history must be at least 10")
        return errors


@dataclass
class MonitorConfig:
    """Main configuration for Mengão Monitor."""
    endpoints: List[APIEndpoint] = field(default_factory=list)
    webhooks: List[WebhookConfig] = field(default_factory=list)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    history: HistoryConfig = field(default_factory=HistoryConfig)
    email: EmailConfig = field(default_factory=EmailConfig)
    websocket: WebSocketConfig = field(default_factory=WebSocketConfig)  # v3.0 🆕
    
    # Global settings
    log_level: str = "INFO"
    log_format: str = "json"  # json, text
    metrics_enabled: bool = True
    metrics_port: int = 9090
    user_agent: str = "MengaoMonitor/1.5"

    def validate(self) -> List[str]:
        """Validate entire configuration."""
        errors = []
        
        if not self.endpoints:
            errors.append("At least one endpoint is required")
        
        for i, ep in enumerate(self.endpoints):
            ep_errors = ep.validate()
            for err in ep_errors:
                errors.append(f"Endpoint [{i}] {ep.name}: {err}")
        
        for i, wh in enumerate(self.webhooks):
            wh_errors = wh.validate()
            for err in wh_errors:
                errors.append(f"Webhook [{i}] {wh.platform}: {err}")
        
        dash_errors = self.dashboard.validate()
        errors.extend([f"Dashboard: {e}" for e in dash_errors])
        
        hist_errors = self.history.validate()
        errors.extend([f"History: {e}" for e in hist_errors])
        
        ws_errors = self.websocket.validate()
        errors.extend([f"WebSocket: {e}" for e in ws_errors])
        
        if self.log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            errors.append(f"Invalid log level: {self.log_level}")
        
        if self.metrics_port < 1 or self.metrics_port > 65535:
            errors.append(f"Invalid metrics port: {self.metrics_port}")
        
        return errors


def _parse_endpoint(data: Dict[str, Any]) -> APIEndpoint:
    """Parse endpoint from dict."""
    return APIEndpoint(
        name=data.get("name", ""),
        url=data.get("url", ""),
        method=data.get("method", "GET").upper(),
        timeout=data.get("timeout", 10),
        expected_status=data.get("expected_status", 200),
        headers=data.get("headers", {}),
        body=data.get("body"),
        interval=data.get("interval", 60),
        enabled=data.get("enabled", True),
        tags=data.get("tags", []),
    )


def _parse_webhook(data: Dict[str, Any]) -> WebhookConfig:
    """Parse webhook from dict."""
    return WebhookConfig(
        platform=data.get("platform", "generic"),
        url=data.get("url", ""),
        enabled=data.get("enabled", True),
        events=data.get("events", ["down", "up", "slow"]),
        cooldown=data.get("cooldown", 300),
        min_severity=data.get("min_severity", "warning"),
    )


def _parse_dashboard(data: Dict[str, Any]) -> DashboardConfig:
    """Parse dashboard config from dict."""
    return DashboardConfig(
        enabled=data.get("enabled", True),
        host=data.get("host", "0.0.0.0"),
        port=data.get("port", 8080),
        refresh_interval=data.get("refresh_interval", 30),
        theme=data.get("theme", "dark"),
        title=data.get("title", "Mengão Monitor"),
    )


def _parse_email(data: Dict[str, Any]) -> EmailConfig:
    """Parse email config from dict."""
    return EmailConfig(
        enabled=data.get("enabled", False),
        smtp_host=data.get("smtp_host", "smtp.gmail.com"),
        smtp_port=data.get("smtp_port", 587),
        username=data.get("username", ""),
        password=data.get("password", ""),
        from_email=data.get("from_email", ""),
        to_emails=data.get("to_emails", []),
        use_tls=data.get("use_tls", True),
        events=data.get("events", ["down", "up"]),
        cooldown=data.get("cooldown", 300),
    )


def _parse_history(data: Dict[str, Any]) -> HistoryConfig:
    """Parse history config from dict."""
    return HistoryConfig(
        enabled=data.get("enabled", True),
        db_path=data.get("db_path", "uptime_history.db"),
        retention_days=data.get("retention_days", 90),
        export_format=data.get("export_format", "csv"),
    )


def _parse_websocket(data: Dict[str, Any]) -> WebSocketConfig:
    """Parse WebSocket config from dict (v3.0)."""
    return WebSocketConfig(
        enabled=data.get("enabled", False),
        host=data.get("host", "localhost"),
        port=data.get("port", 8082),
        ping_interval=data.get("ping_interval", 30),
        ping_timeout=data.get("ping_timeout", 10),
        max_history=data.get("max_history", 100),
    )


def load_config(path: str = "config.json") -> MonitorConfig:
    """
    Load configuration from JSON or YAML file.
    
    Args:
        path: Path to config file
        
    Returns:
        MonitorConfig instance
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid
    """
    config_path = Path(path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    
    with open(config_path, "r") as f:
        if path.endswith((".yaml", ".yml")):
            if not HAS_YAML:
                raise ImportError("PyYAML required for YAML configs: pip install pyyaml")
            data = yaml.safe_load(f)
        else:
            data = json.load(f)
    
    return parse_config(data)


def parse_config(data: Dict[str, Any]) -> MonitorConfig:
    """
    Parse configuration from dict.
    
    Args:
        data: Configuration dictionary
        
    Returns:
        MonitorConfig instance
        
    Raises:
        ValueError: If configuration is invalid
    """
    config = MonitorConfig(
        endpoints=[_parse_endpoint(ep) for ep in data.get("endpoints", [])],
        webhooks=[_parse_webhook(wh) for wh in data.get("webhooks", [])],
        dashboard=_parse_dashboard(data.get("dashboard", {})),
        history=_parse_history(data.get("history", {})),
        email=_parse_email(data.get("email", {})),
        websocket=_parse_websocket(data.get("websocket", {})),  # v3.0 🆕
        log_level=data.get("log_level", "INFO").upper(),
        log_format=data.get("log_format", "json"),
        metrics_enabled=data.get("metrics_enabled", True),
        metrics_port=data.get("metrics_port", 9090),
        user_agent=data.get("user_agent", "MengaoMonitor/1.3"),
    )
    
    errors = config.validate()
    if errors:
        raise ValueError("Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))
    
    return config


def create_sample_config(path: str = "config.sample.json") -> None:
    """Create a sample configuration file."""
    sample = {
        "endpoints": [
            {
                "name": "API Principal",
                "url": "https://api.exemplo.com/health",
                "method": "GET",
                "timeout": 10,
                "expected_status": 200,
                "interval": 60,
                "tags": ["produção", "api"]
            },
            {
                "name": "Site Flamengo",
                "url": "https://www.flamengo.com.br",
                "method": "GET",
                "timeout": 15,
                "expected_status": 200,
                "interval": 120,
                "tags": ["flamengo", "site"]
            }
        ],
        "webhooks": [
            {
                "platform": "discord",
                "url": "https://discord.com/api/webhooks/...",
                "enabled": True,
                "events": ["down", "up"],
                "cooldown": 300
            }
        ],
        "dashboard": {
            "enabled": True,
            "host": "0.0.0.0",
            "port": 8080,
            "refresh_interval": 30,
            "theme": "dark",
            "title": "Mengão Monitor"
        },
        "history": {
            "enabled": True,
            "db_path": "uptime_history.db",
            "retention_days": 90
        },
        "websocket": {
            "enabled": False,
            "host": "localhost",
            "port": 8082,
            "ping_interval": 30,
            "ping_timeout": 10,
            "max_history": 100
        },
        "log_level": "INFO",
        "log_format": "json",
        "metrics_enabled": True,
        "metrics_port": 9090
    }
    
    with open(path, "w") as f:
        json.dump(sample, f, indent=2, ensure_ascii=False)
    
    print(f"Sample config created: {path}")


if __name__ == "__main__":
    create_sample_config()
