"""
Mengão Monitor - Structured Logging Module
JSON logging for production, text for development.
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class JSONFormatter(logging.Formatter):
    """Format log records as JSON for structured logging."""

    def __init__(self, service: str = "mengao-monitor"):
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add extra fields from record
        for key, value in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "message", "pathname", "process", "processName", "relativeCreated",
                "thread", "threadName", "exc_info", "exc_text", "stack_info",
            ):
                log_entry[key] = value

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable text formatter for development."""

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[41m",  # Red background
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        color = self.COLORS.get(record.levelname, "")
        
        msg = f"{color}[{timestamp}] {record.levelname:8s} {record.name}: {record.getMessage()}{self.RESET}"
        
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        
        return msg


def setup_logging(
    level: str = "INFO",
    format_type: str = "json",
    service: str = "mengao-monitor",
) -> logging.Logger:
    """
    Set up structured logging.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_type: "json" for production, "text" for development
        service: Service name for log identification
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("mengao_monitor")
    logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers
    logger.handlers.clear()
    
    handler = logging.StreamHandler(sys.stdout)
    
    if format_type == "json":
        handler.setFormatter(JSONFormatter(service=service))
    else:
        handler.setFormatter(TextFormatter())
    
    logger.addHandler(handler)
    logger.propagate = False
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a child logger with the given name."""
    return logging.getLogger(f"mengao_monitor.{name}")


class LogContext:
    """Context manager for adding structured fields to log records."""

    def __init__(self, logger: logging.Logger, **kwargs: Any):
        self.logger = logger
        self.extra = kwargs
        self.old_factory = logging.getLogRecordFactory()

    def __enter__(self) -> "LogContext":
        old_factory = self.old_factory

        def record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
            record = old_factory(*args, **kwargs)
            for key, value in self.extra.items():
                setattr(record, key, value)
            return record

        logging.setLogRecordFactory(record_factory)
        return self

    def __exit__(self, *args: Any) -> None:
        logging.setLogRecordFactory(self.old_factory)


class APICheckLogger:
    """Specialized logger for API check events."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def check_started(self, endpoint: str, url: str) -> None:
        self.logger.info(
            "API check started",
            extra={"event": "check_started", "endpoint": endpoint, "url": url},
        )

    def check_success(
        self,
        endpoint: str,
        status_code: int,
        response_time_ms: float,
    ) -> None:
        self.logger.info(
            "API check successful",
            extra={
                "event": "check_success",
                "endpoint": endpoint,
                "status_code": status_code,
                "response_time_ms": round(response_time_ms, 2),
            },
        )

    def check_failure(
        self,
        endpoint: str,
        error: str,
        status_code: Optional[int] = None,
    ) -> None:
        extra = {
            "event": "check_failure",
            "endpoint": endpoint,
            "error": error,
        }
        if status_code:
            extra["status_code"] = status_code
        self.logger.error("API check failed", extra=extra)

    def check_slow(
        self,
        endpoint: str,
        response_time_ms: float,
        threshold_ms: float,
    ) -> None:
        self.logger.warning(
            "API response slow",
            extra={
                "event": "check_slow",
                "endpoint": endpoint,
                "response_time_ms": round(response_time_ms, 2),
                "threshold_ms": threshold_ms,
            },
        )

    def status_change(
        self,
        endpoint: str,
        old_status: str,
        new_status: str,
    ) -> None:
        self.logger.info(
            "API status changed",
            extra={
                "event": "status_change",
                "endpoint": endpoint,
                "old_status": old_status,
                "new_status": new_status,
            },
        )


class WebhookLogger:
    """Specialized logger for webhook events."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def sent(self, platform: str, event: str, endpoint: str) -> None:
        self.logger.info(
            "Webhook sent",
            extra={
                "event": "webhook_sent",
                "platform": platform,
                "webhook_event": event,
                "endpoint": endpoint,
            },
        )

    def failed(self, platform: str, event: str, error: str) -> None:
        self.logger.error(
            "Webhook failed",
            extra={
                "event": "webhook_failed",
                "platform": platform,
                "webhook_event": event,
                "error": error,
            },
        )

    def cooldown(self, platform: str, endpoint: str, remaining_seconds: int) -> None:
        self.logger.debug(
            "Webhook in cooldown",
            extra={
                "event": "webhook_cooldown",
                "platform": platform,
                "endpoint": endpoint,
                "remaining_seconds": remaining_seconds,
            },
        )


# Convenience instances
def get_api_logger() -> APICheckLogger:
    return APICheckLogger(get_logger("api_check"))


def get_webhook_logger() -> WebhookLogger:
    return WebhookLogger(get_logger("webhook"))


if __name__ == "__main__":
    # Demo logging
    logger = setup_logging(level="DEBUG", format_type="text")
    
    api_log = get_api_logger()
    api_log.check_started("flamengo.com", "https://www.flamengo.com.br")
    api_log.check_success("flamengo.com", 200, 142.5)
    api_log.check_slow("api.exemplo.com", 2500.0, 1000.0)
    api_log.check_failure("api.queda.com", "Connection timeout")
    api_log.status_change("flamengo.com", "up", "down")
    
    wh_log = get_webhook_logger()
    wh_log.sent("discord", "down", "api.queda.com")
    wh_log.cooldown("discord", "api.queda.com", 245)
