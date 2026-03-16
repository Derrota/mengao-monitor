"""
Test suite for Distributed Tracing (v3.10)
"""

import unittest
import time
import json
from tracing import (
    Tracer, Span, StatusCode, SpanEvent,
    tracer, get_current_span, get_correlation_id,
    _current_span, _correlation_id
)


class TestSpan(unittest.TestCase):
    """Test Span class."""

    def test_span_creation(self):
        """Span is created with correct attributes."""
        span = Span(
            trace_id="abc123",
            span_id="def456",
            parent_span_id=None,
            name="test_operation",
            start_time=time.time()
        )
        self.assertEqual(span.trace_id, "abc123")
        self.assertEqual(span.span_id, "def456")
        self.assertIsNone(span.parent_span_id)
        self.assertEqual(span.name, "test_operation")
        self.assertIsNone(span.end_time)
        self.assertTrue(span.is_active)

    def test_span_duration(self):
        """Span calculates duration correctly."""
        span = Span(
            trace_id="t1",
            span_id="s1",
            parent_span_id=None,
            name="test",
            start_time=1000.0
        )
        self.assertIsNone(span.duration_ms)
        
        span.end_time = 1001.5
        self.assertEqual(span.duration_ms, 1500.0)

    def test_span_set_attribute(self):
        """set_attribute returns self for chaining."""
        span = Span(
            trace_id="t1",
            span_id="s1",
            parent_span_id=None,
            name="test",
            start_time=time.time()
        )
        result = span.set_attribute("key", "value")
        self.assertIs(result, span)
        self.assertEqual(span.attributes["key"], "value")

    def test_span_set_status(self):
        """set_status updates span status."""
        span = Span(
            trace_id="t1",
            span_id="s1",
            parent_span_id=None,
            name="test",
            start_time=time.time()
        )
        span.set_status(StatusCode.OK)
        self.assertEqual(span.status, StatusCode.OK)

    def test_span_set_status_with_description(self):
        """set_status with description adds attribute."""
        span = Span(
            trace_id="t1",
            span_id="s1",
            parent_span_id=None,
            name="test",
            start_time=time.time()
        )
        span.set_status(StatusCode.ERROR, "Something went wrong")
        self.assertEqual(span.attributes["status_description"], "Something went wrong")

    def test_span_record_error(self):
        """record_error sets error status and attributes."""
        span = Span(
            trace_id="t1",
            span_id="s1",
            parent_span_id=None,
            name="test",
            start_time=time.time()
        )
        error = ValueError("test error")
        span.record_error(error)
        
        self.assertEqual(span.status, StatusCode.ERROR)
        self.assertEqual(span.error, "ValueError: test error")
        self.assertEqual(span.attributes["error.type"], "ValueError")
        self.assertEqual(span.attributes["error.message"], "test error")

    def test_span_add_event(self):
        """add_event adds event to span."""
        span = Span(
            trace_id="t1",
            span_id="s1",
            parent_span_id=None,
            name="test",
            start_time=time.time()
        )
        span.add_event("checkpoint", {"step": 1})
        
        self.assertEqual(len(span.events), 1)
        self.assertEqual(span.events[0].name, "checkpoint")
        self.assertEqual(span.events[0].attributes["step"], 1)

    def test_span_end(self):
        """end() sets end_time and marks span as inactive."""
        span = Span(
            trace_id="t1",
            span_id="s1",
            parent_span_id=None,
            name="test",
            start_time=time.time()
        )
        self.assertTrue(span.is_active)
        
        span.end()
        self.assertIsNotNone(span.end_time)
        self.assertFalse(span.is_active)

    def test_span_to_dict(self):
        """to_dict serializes span correctly."""
        span = Span(
            trace_id="t1",
            span_id="s1",
            parent_span_id="p1",
            name="test",
            start_time=1000.0,
            end_time=1001.0,
            correlation_id="c1"
        )
        span.set_attribute("key", "value")
        span.set_status(StatusCode.OK)
        
        d = span.to_dict()
        self.assertEqual(d["trace_id"], "t1")
        self.assertEqual(d["span_id"], "s1")
        self.assertEqual(d["parent_span_id"], "p1")
        self.assertEqual(d["name"], "test")
        self.assertEqual(d["duration_ms"], 1000.0)
        self.assertEqual(d["status"], "OK")
        self.assertEqual(d["attributes"]["key"], "value")
        self.assertEqual(d["correlation_id"], "c1")

    def test_span_to_jaeger(self):
        """to_jaeger exports in Jaeger format."""
        span = Span(
            trace_id="abc123",
            span_id="def456",
            parent_span_id="parent789",
            name="test_op",
            start_time=1000.0,
            end_time=1001.5
        )
        span.set_attribute("http.method", "GET")
        
        jaeger = span.to_jaeger()
        self.assertEqual(jaeger["traceID"], "abc123")
        self.assertEqual(jaeger["spanID"], "def456")
        self.assertEqual(jaeger["operationName"], "test_op")
        self.assertEqual(jaeger["startTime"], 1000_000_000)  # microseconds
        self.assertEqual(jaeger["duration"], 1500_000)  # microseconds
        self.assertTrue(any(t["key"] == "http.method" for t in jaeger["tags"]))


class TestTracer(unittest.TestCase):
    """Test Tracer class."""

    def setUp(self):
        self.tracer = Tracer(service_name="test-service")
        _current_span.set(None)
        _correlation_id.set(None)

    def tearDown(self):
        self.tracer.clear()
        _current_span.set(None)
        _correlation_id.set(None)

    def test_start_span(self):
        """start_span creates a root span."""
        span = self.tracer.start_span("operation")
        
        self.assertIsNotNone(span.trace_id)
        self.assertIsNotNone(span.span_id)
        self.assertIsNone(span.parent_span_id)
        self.assertEqual(span.name, "operation")
        self.assertTrue(span.is_active)

    def test_start_span_with_attributes(self):
        """start_span accepts attributes."""
        span = self.tracer.start_span("op", {"key": "value"})
        self.assertEqual(span.attributes["key"], "value")

    def test_start_span_with_correlation_id(self):
        """start_span accepts correlation_id."""
        span = self.tracer.start_span("op", correlation_id="corr-123")
        self.assertEqual(span.correlation_id, "corr-123")

    def test_nested_spans(self):
        """Nested spans share trace_id and have parent_span_id."""
        root = self.tracer.start_span("root")
        _current_span.set(root)
        
        child = self.tracer.start_span("child")
        
        self.assertEqual(child.trace_id, root.trace_id)
        self.assertEqual(child.parent_span_id, root.span_id)

    def test_span_context_manager(self):
        """span() context manager works correctly."""
        with self.tracer.span("operation") as span:
            self.assertTrue(span.is_active)
            self.assertEqual(get_current_span(), span)
        
        self.assertFalse(span.is_active)
        self.assertEqual(span.status, StatusCode.OK)

    def test_span_context_manager_error(self):
        """span() records errors."""
        with self.assertRaises(ValueError):
            with self.tracer.span("operation") as span:
                raise ValueError("test error")
        
        self.assertEqual(span.status, StatusCode.ERROR)
        self.assertIn("ValueError", span.error)

    def test_correlation_id_context(self):
        """correlation_id() sets ID in context."""
        with self.tracer.correlation_id("corr-123") as cid:
            self.assertEqual(cid, "corr-123")
            self.assertEqual(get_correlation_id(), "corr-123")
            
            span = self.tracer.start_span("op")
            self.assertEqual(span.correlation_id, "corr-123")
        
        self.assertIsNone(get_correlation_id())

    def test_correlation_id_auto_generated(self):
        """correlation_id() generates ID if not provided."""
        with self.tracer.correlation_id() as cid:
            self.assertIsNotNone(cid)
            self.assertTrue(len(cid) > 0)

    def test_trace_decorator(self):
        """@trace decorator creates spans."""
        @self.tracer.trace("decorated_op")
        def my_function(x, y):
            return x + y
        
        result = my_function(1, 2)
        self.assertEqual(result, 3)
        
        spans = self.tracer.get_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "decorated_op")
        self.assertEqual(spans[0].attributes["function"], "my_function")

    def test_trace_decorator_error(self):
        """@trace decorator records errors."""
        @self.tracer.trace("failing_op")
        def failing_function():
            raise RuntimeError("boom")
        
        with self.assertRaises(RuntimeError):
            failing_function()
        
        spans = self.tracer.get_spans()
        self.assertEqual(spans[0].status, StatusCode.ERROR)

    def test_get_spans_by_trace_id(self):
        """get_spans filters by trace_id."""
        with self.tracer.span("op1"):
            pass
        
        with self.tracer.span("op2"):
            pass
        
        spans = self.tracer.get_spans()
        self.assertEqual(len(spans), 2)
        
        trace_id = spans[0].trace_id
        filtered = self.tracer.get_spans(trace_id=trace_id)
        self.assertEqual(len(filtered), 1)

    def test_get_spans_by_correlation_id(self):
        """get_spans filters by correlation_id."""
        with self.tracer.correlation_id("corr-1"):
            self.tracer.start_span("op1").end()
        
        with self.tracer.correlation_id("corr-2"):
            self.tracer.start_span("op2").end()
        
        filtered = self.tracer.get_spans(correlation_id="corr-1")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].correlation_id, "corr-1")

    def test_get_spans_limit(self):
        """get_spans respects limit."""
        for i in range(10):
            self.tracer.start_span(f"op{i}").end()
        
        spans = self.tracer.get_spans(limit=5)
        self.assertEqual(len(spans), 5)

    def test_get_trace(self):
        """get_trace returns all spans for a trace."""
        with self.tracer.span("root") as root:
            trace_id = root.trace_id
            self.tracer.start_span("child1").end()
            self.tracer.start_span("child2").end()
        
        trace = self.tracer.get_trace(trace_id)
        self.assertEqual(len(trace), 3)

    def test_get_stats(self):
        """get_stats returns correct statistics."""
        with self.tracer.span("op1"):
            pass
        with self.tracer.span("op2"):
            pass
        
        with self.assertRaises(ValueError):
            with self.tracer.span("op3"):
                raise ValueError("error")
        
        stats = self.tracer.get_stats()
        self.assertEqual(stats["service_name"], "test-service")
        self.assertEqual(stats["total_spans"], 3)
        self.assertEqual(stats["errors"], 1)
        self.assertEqual(stats["total_traces"], 3)

    def test_export_jaeger(self):
        """export_jaeger returns Jaeger format."""
        with self.tracer.span("operation") as span:
            span.set_attribute("http.method", "GET")
        
        trace_id = span.trace_id
        jaeger = self.tracer.export_jaeger(trace_id)
        
        self.assertEqual(len(jaeger), 1)
        self.assertEqual(jaeger[0]["operationName"], "operation")

    def test_export_json(self):
        """export_json returns valid JSON."""
        with self.tracer.span("operation"):
            pass
        
        trace_id = self.tracer.get_spans()[0].trace_id
        json_str = self.tracer.export_json(trace_id)
        
        parsed = json.loads(json_str)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["name"], "operation")

    def test_clear(self):
        """clear removes all spans."""
        self.tracer.start_span("op").end()
        self.assertEqual(len(self.tracer.get_spans()), 1)
        
        self.tracer.clear()
        self.assertEqual(len(self.tracer.get_spans()), 0)
        
        stats = self.tracer.get_stats()
        self.assertEqual(stats["total_spans"], 0)

    def test_max_spans_limit(self):
        """Tracer limits stored spans."""
        self.tracer._max_spans = 5
        
        for i in range(10):
            self.tracer.start_span(f"op{i}").end()
        
        self.assertEqual(len(self.tracer._spans), 5)


class TestGlobalTracer(unittest.TestCase):
    """Test global tracer instance."""

    def test_global_tracer_exists(self):
        """Global tracer is available."""
        self.assertIsInstance(tracer, Tracer)
        self.assertEqual(tracer.service_name, "mengao-monitor")

    def test_global_tracer_works(self):
        """Global tracer creates spans."""
        tracer.clear()
        
        with tracer.span("test") as span:
            self.assertIsNotNone(span.trace_id)
        
        tracer.clear()


class TestSpanEvent(unittest.TestCase):
    """Test SpanEvent class."""

    def test_event_to_dict(self):
        """SpanEvent serializes correctly."""
        event = SpanEvent(
            name="checkpoint",
            timestamp=1000.0,
            attributes={"step": 1}
        )
        
        d = event.to_dict()
        self.assertEqual(d["name"], "checkpoint")
        self.assertEqual(d["timestamp"], 1000.0)
        self.assertEqual(d["attributes"]["step"], 1)


class TestIntegration(unittest.TestCase):
    """Integration tests for tracing system."""

    def setUp(self):
        self.tracer = Tracer(service_name="integration-test")
        _current_span.set(None)
        _correlation_id.set(None)

    def tearDown(self):
        self.tracer.clear()
        _current_span.set(None)
        _correlation_id.set(None)

    def test_full_request_trace(self):
        """Simulate a full request with nested spans."""
        with self.tracer.correlation_id("req-123") as cid:
            with self.tracer.span("http_request", {"method": "GET", "path": "/api/users"}) as http_span:
                # Simulate auth check
                with self.tracer.span("auth_check") as auth_span:
                    auth_span.set_attribute("user_id", "42")
                    time.sleep(0.001)  # Simulate work
                
                # Simulate database query
                with self.tracer.span("db_query") as db_span:
                    db_span.set_attribute("query", "SELECT * FROM users")
                    db_span.add_event("query_start")
                    time.sleep(0.001)
                    db_span.add_event("query_end", {"rows": 10})
                
                # Simulate cache lookup
                with self.tracer.span("cache_lookup") as cache_span:
                    cache_span.set_attribute("hit", False)
                
                http_span.set_status(StatusCode.OK)
                http_span.set_attribute("status_code", 200)
        
        # Verify trace structure
        spans = self.tracer.get_spans(correlation_id=cid)
        self.assertEqual(len(spans), 4)
        
        # All spans share trace_id
        trace_ids = set(s.trace_id for s in spans)
        self.assertEqual(len(trace_ids), 1)
        
        # All spans have correlation_id
        for span in spans:
            self.assertEqual(span.correlation_id, cid)
        
        # Root span has no parent
        root = [s for s in spans if s.parent_span_id is None][0]
        self.assertEqual(root.name, "http_request")
        
        # Child spans have parent
        children = [s for s in spans if s.parent_span_id is not None]
        self.assertEqual(len(children), 3)
        for child in children:
            self.assertEqual(child.parent_span_id, root.span_id)

    def test_error_propagation(self):
        """Errors are recorded and propagated."""
        with self.assertRaises(RuntimeError):
            with self.tracer.span("outer") as outer:
                with self.tracer.span("inner") as inner:
                    raise RuntimeError("inner failed")
        
        self.assertEqual(inner.status, StatusCode.ERROR)
        # Outer also gets ERROR because exception propagated through it
        self.assertEqual(outer.status, StatusCode.ERROR)

    def test_concurrent_traces(self):
        """Multiple concurrent traces don't interfere."""
        import threading
        
        results = []
        
        def worker(name, cid):
            with self.tracer.correlation_id(cid):
                with self.tracer.span(f"work_{name}") as span:
                    results.append((name, span.trace_id, span.correlation_id))
        
        t1 = threading.Thread(target=worker, args=("A", "corr-a"))
        t2 = threading.Thread(target=worker, args=("B", "corr-b"))
        
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        
        self.assertEqual(len(results), 2)
        # Different correlation IDs
        cids = set(r[2] for r in results)
        self.assertEqual(len(cids), 2)
        # Different trace IDs
        tids = set(r[1] for r in results)
        self.assertEqual(len(tids), 2)


if __name__ == "__main__":
    unittest.main()
