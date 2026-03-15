"""
Tests for Health Check Templates - Mengão Monitor v3.4
"""

import unittest
import time
import json
from unittest.mock import patch, MagicMock
from health_check_templates import (
    Assertion, AssertionType, Severity, CheckResult,
    BaseTemplate, RESTTemplate, GraphQLTemplate, TemplateChecker,
    create_rest_template, create_graphql_template,
    create_kubernetes_healthz, create_elasticsearch_health
)


class TestAssertion(unittest.TestCase):
    """Testes para Assertion."""
    
    def test_status_code_exact(self):
        a = Assertion(type=AssertionType.STATUS_CODE, expected=200, actual=200)
        a.evaluate()
        self.assertTrue(a.passed)
        self.assertIn("200", a.message)
    
    def test_status_code_list(self):
        a = Assertion(type=AssertionType.STATUS_CODE, expected=[200, 201], actual=201)
        a.evaluate()
        self.assertTrue(a.passed)
    
    def test_status_code_fail(self):
        a = Assertion(type=AssertionType.STATUS_CODE, expected=200, actual=500)
        a.evaluate()
        self.assertFalse(a.passed)
    
    def test_response_time_pass(self):
        a = Assertion(type=AssertionType.RESPONSE_TIME, expected=2.0, actual=1.5)
        a.evaluate()
        self.assertTrue(a.passed)
    
    def test_response_time_fail(self):
        a = Assertion(type=AssertionType.RESPONSE_TIME, expected=1.0, actual=2.5)
        a.evaluate()
        self.assertFalse(a.passed)
    
    def test_json_schema_simple(self):
        a = Assertion(
            type=AssertionType.JSON_SCHEMA,
            expected={"status": str, "version": str},
            actual={"status": "ok", "version": "1.0"}
        )
        a.evaluate()
        self.assertTrue(a.passed)
    
    def test_json_schema_nested(self):
        a = Assertion(
            type=AssertionType.JSON_SCHEMA,
            expected={"data": {"id": int, "name": str}},
            actual={"data": {"id": 1, "name": "test"}}
        )
        a.evaluate()
        self.assertTrue(a.passed)
    
    def test_json_schema_fail_missing_key(self):
        a = Assertion(
            type=AssertionType.JSON_SCHEMA,
            expected={"status": str, "missing": str},
            actual={"status": "ok"}
        )
        a.evaluate()
        self.assertFalse(a.passed)
    
    def test_json_schema_fail_wrong_type(self):
        a = Assertion(
            type=AssertionType.JSON_SCHEMA,
            expected={"id": int},
            actual={"id": "not_int"}
        )
        a.evaluate()
        self.assertFalse(a.passed)
    
    def test_json_path_eq(self):
        a = Assertion(
            type=AssertionType.JSON_PATH,
            expected={"path": "data.id", "operator": "eq", "value": 42},
            actual={"data": {"id": 42}}
        )
        a.evaluate()
        self.assertTrue(a.passed)
    
    def test_json_path_gt(self):
        a = Assertion(
            type=AssertionType.JSON_PATH,
            expected={"path": "metrics.latency", "operator": "gt", "value": 100},
            actual={"metrics": {"latency": 150}}
        )
        a.evaluate()
        self.assertTrue(a.passed)
    
    def test_json_path_contains(self):
        a = Assertion(
            type=AssertionType.JSON_PATH,
            expected={"path": "message", "operator": "contains", "value": "success"},
            actual={"message": "operation success"}
        )
        a.evaluate()
        self.assertTrue(a.passed)
    
    def test_header_pass(self):
        a = Assertion(
            type=AssertionType.HEADER,
            expected=("Content-Type", None),
            actual={"Content-Type": "application/json"}
        )
        a.evaluate()
        self.assertTrue(a.passed)
    
    def test_header_with_value(self):
        a = Assertion(
            type=AssertionType.HEADER,
            expected=("X-Custom", "value123"),
            actual={"X-Custom": "value123"}
        )
        a.evaluate()
        self.assertTrue(a.passed)
    
    def test_header_fail(self):
        a = Assertion(
            type=AssertionType.HEADER,
            expected=("Missing-Header", None),
            actual={"Content-Type": "text/plain"}
        )
        a.evaluate()
        self.assertFalse(a.passed)
    
    def test_body_contains(self):
        a = Assertion(
            type=AssertionType.BODY_CONTAINS,
            expected="healthy",
            actual='{"status": "healthy"}'
        )
        a.evaluate()
        self.assertTrue(a.passed)
    
    def test_body_regex(self):
        a = Assertion(
            type=AssertionType.BODY_REGEX,
            expected=r"version:\s*\d+\.\d+",
            actual="version: 1.0"
        )
        a.evaluate()
        self.assertTrue(a.passed)
    
    def test_custom_callable(self):
        a = Assertion(
            type=AssertionType.CUSTOM,
            expected=lambda x: x.get("status_code") == 200,
            actual={"status_code": 200, "body": {}}
        )
        a.evaluate()
        self.assertTrue(a.passed)


class TestCheckResult(unittest.TestCase):
    """Testes para CheckResult."""
    
    def test_passed_count(self):
        result = CheckResult(
            template_name="test",
            url="http://test",
            passed=True,
            timestamp=time.time(),
            response_time=1.0,
            assertions=[
                Assertion(AssertionType.STATUS_CODE, 200, 200, True),
                Assertion(AssertionType.RESPONSE_TIME, 2.0, 1.0, True),
                Assertion(AssertionType.BODY_CONTAINS, "ok", "not_here", False)
            ]
        )
        self.assertEqual(result.passed_count, 2)
        self.assertEqual(result.failed_count, 1)
    
    def test_critical_failures(self):
        result = CheckResult(
            template_name="test",
            url="http://test",
            passed=False,
            timestamp=time.time(),
            response_time=1.0,
            assertions=[
                Assertion(AssertionType.STATUS_CODE, 200, 500, False, severity=Severity.CRITICAL),
                Assertion(AssertionType.RESPONSE_TIME, 2.0, 3.0, False, severity=Severity.ERROR)
            ]
        )
        critical = result.critical_failures
        self.assertEqual(len(critical), 1)
        self.assertEqual(critical[0].type, AssertionType.STATUS_CODE)
    
    def test_to_dict(self):
        result = CheckResult(
            template_name="test",
            url="http://test",
            passed=True,
            timestamp=time.time(),
            response_time=1.5,
            status_code=200
        )
        d = result.to_dict()
        self.assertEqual(d["template_name"], "test")
        self.assertEqual(d["response_time"], 1.5)


class TestBaseTemplate(unittest.TestCase):
    """Testes para BaseTemplate."""
    
    def test_add_assertion(self):
        template = BaseTemplate(name="test", url="http://test")
        assertion = Assertion(AssertionType.STATUS_CODE, 200)
        template.add_assertion(assertion)
        self.assertEqual(len(template.assertions), 1)
    
    def test_chaining(self):
        template = BaseTemplate(name="test", url="http://test")
        result = template.add_assertion(Assertion(AssertionType.STATUS_CODE, 200))
        self.assertIs(result, template)


class TestRESTTemplate(unittest.TestCase):
    """Testes para RESTTemplate."""
    
    def test_basic_creation(self):
        template = RESTTemplate(
            name="api-test",
            url="https://api.example.com/health",
            expected_status=200,
            max_response_time=2.0
        )
        self.assertEqual(template.name, "api-test")
        self.assertEqual(template.url, "https://api.example.com/health")
        # Should have status + response time assertions
        self.assertEqual(len(template.assertions), 2)
    
    def test_with_json_schema(self):
        template = RESTTemplate(
            name="api-test",
            url="https://api.example.com",
            json_schema={"status": str, "version": str}
        )
        # status + response_time + json_schema
        self.assertEqual(len(template.assertions), 3)
    
    def test_with_multiple_options(self):
        template = RESTTemplate(
            name="complex",
            url="https://api.example.com",
            expected_status=[200, 201],
            max_response_time=3.0,
            required_headers=["X-Request-Id"],
            body_contains=["success"]
        )
        # status + response_time + header + body_contains
        self.assertEqual(len(template.assertions), 4)
    
    @patch('health_check_templates.requests')
    def test_check_success(self, mock_requests):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_response.text = '{"status": "ok"}'
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.content = b'{"status": "ok"}'
        mock_requests.request.return_value = mock_response
        
        template = RESTTemplate(
            name="test",
            url="http://test.local",
            expected_status=200,
            max_response_time=5.0
        )
        
        result = template.check()
        self.assertTrue(result.passed)
        self.assertEqual(result.status_code, 200)
    
    @patch('health_check_templates.requests')
    def test_check_timeout(self, mock_requests):
        # Create a proper Timeout exception class
        class MockTimeout(Exception):
            pass
        
        # Set Timeout before side_effect
        mock_requests.Timeout = MockTimeout
        mock_requests.request.side_effect = MockTimeout("Connection timed out")
        
        template = RESTTemplate(
            name="test",
            url="http://timeout.local",
            expected_status=200
        )
        
        result = template.check()
        self.assertFalse(result.passed)
        self.assertIsNotNone(result.error)
        self.assertIn("Timeout", result.error)


class TestGraphQLTemplate(unittest.TestCase):
    """Testes para GraphQLTemplate."""
    
    def test_creation(self):
        template = GraphQLTemplate(
            name="gql-test",
            url="https://api.example.com/graphql",
            query="{ users { id name } }"
        )
        self.assertEqual(template.method, "POST")
        self.assertEqual(template.headers.get("Content-Type"), "application/json")
    
    def test_default_query(self):
        template = GraphQLTemplate(
            name="gql-test",
            url="https://api.example.com/graphql"
        )
        self.assertEqual(template.query, "{ __typename }")
    
    @patch('health_check_templates.requests')
    def test_check_success(self, mock_requests):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"__typename": "Query"}}
        mock_response.headers = {}
        mock_requests.post.return_value = mock_response
        
        template = GraphQLTemplate(
            name="gql-test",
            url="http://test.local/graphql"
        )
        
        result = template.check()
        self.assertTrue(result.passed)
    
    @patch('health_check_templates.requests')
    def test_check_graphql_errors(self, mock_requests):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": None,
            "errors": [{"message": "Field not found"}]
        }
        mock_response.headers = {}
        mock_requests.post.return_value = mock_response
        
        template = GraphQLTemplate(
            name="gql-test",
            url="http://test.local/graphql"
        )
        
        result = template.check()
        self.assertFalse(result.passed)
        self.assertIn("GraphQL errors", result.error)


class TestTemplateChecker(unittest.TestCase):
    """Testes para TemplateChecker."""
    
    def setUp(self):
        self.checker = TemplateChecker()
    
    def test_register(self):
        template = RESTTemplate(name="test", url="http://test")
        self.checker.register("test", template)
        self.assertIn("test", self.checker.get_template_names())
    
    def test_unregister(self):
        template = RESTTemplate(name="test", url="http://test")
        self.checker.register("test", template)
        result = self.checker.unregister("test")
        self.assertTrue(result)
        self.assertNotIn("test", self.checker.get_template_names())
    
    def test_unregister_nonexistent(self):
        result = self.checker.unregister("nonexistent")
        self.assertFalse(result)
    
    @patch('health_check_templates.requests')
    def test_check(self, mock_requests):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        mock_response.text = '{"ok": true}'
        mock_response.headers = {}
        mock_response.content = b'{"ok": true}'
        mock_requests.request.return_value = mock_response
        
        template = RESTTemplate(name="test", url="http://test")
        self.checker.register("test", template)
        
        result = self.checker.check("test")
        self.assertIsNotNone(result)
        self.assertTrue(result.passed)
    
    def test_check_nonexistent(self):
        result = self.checker.check("nonexistent")
        self.assertIsNone(result)
    
    @patch('health_check_templates.requests')
    def test_check_all(self, mock_requests):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        mock_response.text = '{"ok": true}'
        mock_response.headers = {}
        mock_response.content = b'{"ok": true}'
        mock_requests.request.return_value = mock_response
        
        self.checker.register("api1", RESTTemplate(name="api1", url="http://api1"))
        self.checker.register("api2", RESTTemplate(name="api2", url="http://api2"))
        
        results = self.checker.check_all()
        self.assertEqual(len(results), 2)
    
    @patch('health_check_templates.requests')
    def test_history(self, mock_requests):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        mock_response.text = '{"ok": true}'
        mock_response.headers = {}
        mock_response.content = b'{"ok": true}'
        mock_requests.request.return_value = mock_response
        
        template = RESTTemplate(name="test", url="http://test")
        self.checker.register("test", template)
        
        # Run 3 checks
        for _ in range(3):
            self.checker.check("test")
        
        history = self.checker.get_history("test")
        self.assertEqual(len(history), 3)
    
    @patch('health_check_templates.requests')
    def test_uptime(self, mock_requests):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        mock_response.text = '{"ok": true}'
        mock_response.headers = {}
        mock_response.content = b'{"ok": true}'
        mock_requests.request.return_value = mock_response
        
        template = RESTTemplate(name="test", url="http://test")
        self.checker.register("test", template)
        
        # All pass
        for _ in range(5):
            self.checker.check("test")
        
        uptime = self.checker.get_uptime("test")
        self.assertEqual(uptime, 100.0)
    
    def test_uptime_no_history(self):
        uptime = self.checker.get_uptime("nonexistent")
        self.assertIsNone(uptime)
    
    @patch('health_check_templates.requests')
    def test_stats(self, mock_requests):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        mock_response.text = '{"ok": true}'
        mock_response.headers = {}
        mock_response.content = b'{"ok": true}'
        mock_requests.request.return_value = mock_response
        
        self.checker.register("test", RESTTemplate(name="test", url="http://test"))
        self.checker.check("test")
        
        stats = self.checker.get_stats()
        self.assertEqual(stats["total_checks"], 1)
        self.assertEqual(stats["passed"], 1)
        self.assertEqual(stats["templates_count"], 1)


class TestFactoryFunctions(unittest.TestCase):
    """Testes para funções factory."""
    
    def test_create_rest_template(self):
        template = create_rest_template(
            name="my-api",
            url="https://api.example.com",
            expected_status=200,
            max_response_time=2.0
        )
        self.assertIsInstance(template, RESTTemplate)
        self.assertEqual(template.name, "my-api")
    
    def test_create_graphql_template(self):
        template = create_graphql_template(
            name="my-gql",
            url="https://api.example.com/graphql",
            query="{ users { id } }"
        )
        self.assertIsInstance(template, GraphQLTemplate)
        self.assertEqual(template.query, "{ users { id } }")
    
    def test_create_kubernetes_healthz(self):
        template = create_kubernetes_healthz("http://localhost:8080/healthz")
        self.assertEqual(template.name, "k8s-healthz")
        self.assertIn("kubernetes", template.tags)
    
    def test_create_elasticsearch_health(self):
        template = create_elasticsearch_health("http://localhost:9200")
        self.assertEqual(template.name, "elasticsearch")
        self.assertIn("/_cluster/health", template.url)


class TestEdgeCases(unittest.TestCase):
    """Testes de edge cases."""
    
    def test_json_path_array_index(self):
        a = Assertion(
            type=AssertionType.JSON_PATH,
            expected={"path": "items.0.name", "operator": "eq", "value": "first"},
            actual={"items": [{"name": "first"}, {"name": "second"}]}
        )
        a.evaluate()
        self.assertTrue(a.passed)
    
    def test_json_path_out_of_bounds(self):
        a = Assertion(
            type=AssertionType.JSON_PATH,
            expected={"path": "items.10.name", "operator": "eq", "value": "x"},
            actual={"items": [{"name": "first"}]}
        )
        a.evaluate()
        self.assertFalse(a.passed)
    
    def test_json_schema_empty_dict(self):
        a = Assertion(
            type=AssertionType.JSON_SCHEMA,
            expected={},
            actual={"anything": "goes"}
        )
        a.evaluate()
        self.assertTrue(a.passed)
    
    def test_json_schema_list_validation(self):
        a = Assertion(
            type=AssertionType.JSON_SCHEMA,
            expected={"items": [{"id": int}]},
            actual={"items": [{"id": 1}, {"id": 2}]}
        )
        a.evaluate()
        self.assertTrue(a.passed)
    
    def test_custom_non_callable(self):
        a = Assertion(
            type=AssertionType.CUSTOM,
            expected="not_callable",
            actual={}
        )
        a.evaluate()
        self.assertFalse(a.passed)
    
    @patch('health_check_templates.HAS_REQUESTS', False)
    def test_check_without_requests(self):
        template = RESTTemplate(name="test", url="http://test")
        result = template.check()
        self.assertFalse(result.passed)
        self.assertIn("requests library not installed", result.error)


if __name__ == "__main__":
    unittest.main()
