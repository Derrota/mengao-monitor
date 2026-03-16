"""
Distributed Tracing + Correlation IDs - Mengão Monitor v3.10

Sistema de tracing distribuído para rastrear requests através de múltiplos
serviços e componentes. Suporta spans aninhados, correlation IDs, e export
para formatos Jaeger/Zipkin.

Uso:
    # Context manager (recomendado)
    with tracer.span("api_call", attributes={"endpoint": "/users"}) as span:
        result = api_call()
        span.set_attribute("status_code", 200)

    # Manual
    span = tracer.start_span("database_query")
    try:
        result = db.query()
        span.set_status(StatusCode.OK)
    except Exception as e:
        span.record_error(e)
        raise
    finally:
        span.end()

    # Decorator
    @tracer.trace("process_request")
    def handle_request(request_id):
        ...

    # Correlation ID
    with tracer.correlation_id("req-123"):
        # All spans created here will have correlation_id
        process_request()
"""

import time
import uuid
import threading
import functools
import json
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum
from contextvars import ContextVar
from contextlib import contextmanager


# Context variables for async-safe tracing
_current_span: ContextVar[Optional['Span']] = ContextVar('current_span', default=None)
_correlation_id: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)


class StatusCode(Enum):
    """Status codes for spans."""
    UNSET = "UNSET"
    OK = "OK"
    ERROR = "ERROR"


@dataclass
class SpanEvent:
    """An event within a span (like a log entry)."""
    name: str
    timestamp: float
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "timestamp": self.timestamp,
            "attributes": self.attributes
        }


@dataclass
class Span:
    """
    A single operation within a trace.
    
    Attributes:
        trace_id: ID do trace completo (shared across all spans)
        span_id: ID único deste span
        parent_span_id: ID do span pai (None se root)
        name: Nome da operação
        start_time: Timestamp de início
        end_time: Timestamp de fim (None se ainda ativo)
        status: Status da operação
        attributes: Key-value pairs de contexto
        events: Lista de eventos dentro do span
        correlation_id: ID para correlacionar com logs/métricas
    """
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    name: str
    start_time: float
    end_time: Optional[float] = None
    status: StatusCode = StatusCode.UNSET
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[SpanEvent] = field(default_factory=list)
    correlation_id: Optional[str] = None
    error: Optional[str] = None

    @property
    def duration_ms(self) -> Optional[float]:
        """Duration in milliseconds."""
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000

    @property
    def is_active(self) -> bool:
        """Whether this span is still active."""
        return self.end_time is None

    def set_attribute(self, key: str, value: Any) -> 'Span':
        """Set a span attribute."""
        self.attributes[key] = value
        return self

    def set_status(self, status: StatusCode, description: str = "") -> 'Span':
        """Set span status."""
        self.status = status
        if description:
            self.attributes["status_description"] = description
        return self

    def record_error(self, error: Exception) -> 'Span':
        """Record an error in this span."""
        self.status = StatusCode.ERROR
        self.error = f"{type(error).__name__}: {str(error)}"
        self.attributes["error.type"] = type(error).__name__
        self.attributes["error.message"] = str(error)
        return self

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> 'Span':
        """Add an event to this span."""
        self.events.append(SpanEvent(
            name=name,
            timestamp=time.time(),
            attributes=attributes or {}
        ))
        return self

    def end(self) -> 'Span':
        """End this span."""
        if self.end_time is None:
            self.end_time = time.time()
        return self

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "status": self.status.value,
            "attributes": self.attributes,
            "events": [e.to_dict() for e in self.events],
            "correlation_id": self.correlation_id,
            "error": self.error
        }

    def to_jaeger(self) -> Dict[str, Any]:
        """Export in Jaeger-compatible format."""
        return {
            "traceID": self.trace_id,
            "spanID": self.span_id,
            "operationName": self.name,
            "startTime": int(self.start_time * 1_000_000),  # microseconds
            "duration": int((self.duration_ms or 0) * 1000),  # microseconds
            "tags": [
                {"key": k, "value": str(v)}
                for k, v in self.attributes.items()
            ],
            "logs": [
                {
                    "timestamp": int(e.timestamp * 1_000_000),
                    "fields": [{"key": k, "value": str(v)} for k, v in e.attributes.items()]
                }
                for e in self.events
            ],
            "references": [
                {"refType": "CHILD_OF", "traceID": self.trace_id, "spanID": self.parent_span_id}
            ] if self.parent_span_id else []
        }


class Tracer:
    """
    Distributed tracer for Mengão Monitor.
    
    Thread-safe and context-aware. Supports nested spans, correlation IDs,
    and export to multiple formats.
    """

    def __init__(self, service_name: str = "mengao-monitor"):
        self.service_name = service_name
        self._spans: List[Span] = []
        self._lock = threading.RLock()
        self._max_spans = 10000
        self._stats = {
            "total_spans": 0,
            "active_spans": 0,
            "errors": 0,
            "traces": set()
        }

    def _generate_id(self) -> str:
        """Generate a unique ID (16 hex chars)."""
        return uuid.uuid4().hex[:16]

    def start_span(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None
    ) -> Span:
        """
        Start a new span.
        
        If there's a current span, the new span becomes its child.
        If there's a correlation ID in context, it's inherited.
        """
        current = _current_span.get()
        cid = correlation_id or _correlation_id.get()

        span = Span(
            trace_id=current.trace_id if current else self._generate_id(),
            span_id=self._generate_id(),
            parent_span_id=current.span_id if current else None,
            name=name,
            start_time=time.time(),
            attributes=attributes or {},
            correlation_id=cid
        )

        with self._lock:
            self._spans.append(span)
            self._stats["total_spans"] += 1
            self._stats["active_spans"] += 1
            self._stats["traces"].add(span.trace_id)

            # Trim old spans
            if len(self._spans) > self._max_spans:
                self._spans = self._spans[-self._max_spans:]

        return span

    def end_span(self, span: Span) -> None:
        """End a span and update stats."""
        span.end()
        with self._lock:
            self._stats["active_spans"] -= 1
            if span.status == StatusCode.ERROR:
                self._stats["errors"] += 1

    @contextmanager
    def span(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None
    ):
        """
        Context manager for creating a span.
        
        Usage:
            with tracer.span("operation", {"key": "value"}) as span:
                do_work()
                span.set_attribute("result", "ok")
        """
        span = self.start_span(name, attributes, correlation_id)
        token = _current_span.set(span)
        try:
            yield span
            if span.status == StatusCode.UNSET:
                span.set_status(StatusCode.OK)
        except Exception as e:
            span.record_error(e)
            raise
        finally:
            self.end_span(span)
            _current_span.reset(token)

    @contextmanager
    def correlation_id(self, cid: Optional[str] = None):
        """
        Context manager for setting a correlation ID.
        
        All spans created within this context will have the correlation ID.
        
        Usage:
            with tracer.correlation_id("req-123"):
                process_request()
        """
        cid = cid or self._generate_id()
        token = _correlation_id.set(cid)
        try:
            yield cid
        finally:
            _correlation_id.reset(token)

    def trace(
        self,
        name: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None
    ):
        """
        Decorator for tracing a function.
        
        Usage:
            @tracer.trace("process_request")
            def handle_request(req):
                ...
        """
        def decorator(func: Callable) -> Callable:
            span_name = name or func.__name__

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                with self.span(span_name, attributes) as span:
                    span.set_attribute("function", func.__name__)
                    span.set_attribute("module", func.__module__)
                    return func(*args, **kwargs)

            return wrapper
        return decorator

    def get_spans(
        self,
        trace_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Span]:
        """Get spans with optional filters."""
        with self._lock:
            spans = self._spans

            if trace_id:
                spans = [s for s in spans if s.trace_id == trace_id]
            if correlation_id:
                spans = [s for s in spans if s.correlation_id == correlation_id]

            return spans[-limit:]

    def get_trace(self, trace_id: str) -> List[Span]:
        """Get all spans for a trace."""
        return self.get_spans(trace_id=trace_id)

    def get_stats(self) -> Dict[str, Any]:
        """Get tracer statistics."""
        with self._lock:
            return {
                "service_name": self.service_name,
                "total_spans": self._stats["total_spans"],
                "active_spans": self._stats["active_spans"],
                "total_traces": len(self._stats["traces"]),
                "errors": self._stats["errors"],
                "spans_in_memory": len(self._spans)
            }

    def export_jaeger(self, trace_id: str) -> List[Dict[str, Any]]:
        """Export a trace in Jaeger format."""
        spans = self.get_trace(trace_id)
        return [s.to_jaeger() for s in spans]

    def export_json(self, trace_id: str) -> str:
        """Export a trace as JSON string."""
        spans = self.get_trace(trace_id)
        return json.dumps([s.to_dict() for s in spans], indent=2)

    def clear(self) -> None:
        """Clear all spans (for testing)."""
        with self._lock:
            self._spans.clear()
            self._stats = {
                "total_spans": 0,
                "active_spans": 0,
                "errors": 0,
                "traces": set()
            }


# Global tracer instance
tracer = Tracer()


def get_current_span() -> Optional[Span]:
    """Get the current active span."""
    return _current_span.get()


def get_correlation_id() -> Optional[str]:
    """Get the current correlation ID."""
    return _correlation_id.get()


def set_correlation_id(cid: str) -> None:
    """Set the correlation ID in context."""
    _correlation_id.set(cid)
