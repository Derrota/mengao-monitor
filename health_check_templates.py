"""
Health Check Templates - Mengão Monitor v3.4

Templates pré-definidos para validar APIs comuns:
- REST APIs (status code, JSON schema, response time)
- GraphQL (query validation, error detection)
- Custom assertions (headers, body patterns, latency SLOs)

Uso:
    from health_check_templates import TemplateChecker, RESTTemplate
    
    checker = TemplateChecker()
    checker.register("my-api", RESTTemplate(
        url="https://api.example.com/health",
        expected_status=200,
        max_response_time=2.0,
        json_schema={"status": "ok", "version": str}
    ))
    
    result = checker.check("my-api")
    print(result.passed, result.message)
"""

import time
import json
import re
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union
from threading import Lock

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class AssertionType(Enum):
    """Tipos de assertions suportados."""
    STATUS_CODE = "status_code"
    RESPONSE_TIME = "response_time"
    JSON_SCHEMA = "json_schema"
    JSON_PATH = "json_path"
    HEADER = "header"
    BODY_CONTAINS = "body_contains"
    BODY_REGEX = "body_regex"
    CUSTOM = "custom"


class Severity(Enum):
    """Severidade de falha."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Assertion:
    """Uma assertion individual."""
    type: AssertionType
    expected: Any
    actual: Any = None
    passed: bool = False
    message: str = ""
    severity: Severity = Severity.ERROR
    
    def evaluate(self) -> bool:
        """Avalia a assertion."""
        if self.type == AssertionType.STATUS_CODE:
            if isinstance(self.expected, list):
                self.passed = self.actual in self.expected
            else:
                self.passed = self.actual == self.expected
            self.message = f"Status {self.actual} {'==' if self.passed else '!='} {self.expected}"
            
        elif self.type == AssertionType.RESPONSE_TIME:
            self.passed = self.actual <= self.expected
            self.message = f"Response time {self.actual:.3f}s {'<=' if self.passed else '>'} {self.expected}s"
            
        elif self.type == AssertionType.JSON_SCHEMA:
            self.passed = self._validate_json_schema(self.actual, self.expected)
            self.message = f"JSON schema {'valid' if self.passed else 'invalid'}"
            
        elif self.type == AssertionType.JSON_PATH:
            self.passed = self._check_json_path(self.actual, self.expected)
            self.message = f"JSON path check {'passed' if self.passed else 'failed'}"
            
        elif self.type == AssertionType.HEADER:
            header_name, expected_value = self.expected
            actual_value = self.actual.get(header_name) if isinstance(self.actual, dict) else None
            self.passed = actual_value is not None and (expected_value is None or actual_value == expected_value)
            self.message = f"Header '{header_name}' {'found' if self.passed else 'not found/mismatch'}"
            
        elif self.type == AssertionType.BODY_CONTAINS:
            self.passed = str(self.expected) in str(self.actual)
            self.message = f"Body {'contains' if self.passed else 'missing'} '{self.expected}'"
            
        elif self.type == AssertionType.BODY_REGEX:
            self.passed = bool(re.search(self.expected, str(self.actual)))
            self.message = f"Body regex {'matched' if self.passed else 'not matched'}"
            
        elif self.type == AssertionType.CUSTOM:
            if callable(self.expected):
                self.passed = self.expected(self.actual)
                self.message = f"Custom assertion {'passed' if self.passed else 'failed'}"
            else:
                self.passed = False
                self.message = "Custom assertion requires callable"
        
        return self.passed
    
    def _validate_json_schema(self, data: Any, schema: Dict) -> bool:
        """Validação simples de JSON schema (sem jsonschema lib)."""
        if not isinstance(schema, dict):
            return data == schema
        
        if not isinstance(data, dict):
            return False
        
        for key, expected_type in schema.items():
            if key not in data:
                return False
            
            if isinstance(expected_type, type):
                if not isinstance(data[key], expected_type):
                    return False
            elif isinstance(expected_type, dict):
                if not self._validate_json_schema(data[key], expected_type):
                    return False
            elif isinstance(expected_type, list):
                if not isinstance(data[key], list):
                    return False
                if expected_type and data[key]:
                    for item in data[key]:
                        if not self._validate_json_schema(item, expected_type[0]):
                            return False
            else:
                if data[key] != expected_type:
                    return False
        
        return True
    
    def _check_json_path(self, data: Any, path_config: Dict) -> bool:
        """Verifica valor em path específico do JSON."""
        path = path_config.get("path", "")
        expected = path_config.get("value")
        operator = path_config.get("operator", "eq")
        
        parts = path.split(".")
        current = data
        
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and part.isdigit():
                idx = int(part)
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return False
            else:
                return False
        
        if operator == "eq":
            return current == expected
        elif operator == "ne":
            return current != expected
        elif operator == "gt":
            return current > expected
        elif operator == "lt":
            return current < expected
        elif operator == "gte":
            return current >= expected
        elif operator == "lte":
            return current <= expected
        elif operator == "contains":
            return expected in current
        elif operator == "regex":
            return bool(re.search(expected, str(current)))
        
        return False


@dataclass
class CheckResult:
    """Resultado de um health check."""
    template_name: str
    url: str
    passed: bool
    timestamp: float
    response_time: float
    status_code: Optional[int] = None
    assertions: List[Assertion] = field(default_factory=list)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def passed_count(self) -> int:
        return sum(1 for a in self.assertions if a.passed)
    
    @property
    def failed_count(self) -> int:
        return sum(1 for a in self.assertions if not a.passed)
    
    @property
    def critical_failures(self) -> List[Assertion]:
        return [a for a in self.assertions if not a.passed and a.severity == Severity.CRITICAL]
    
    def to_dict(self) -> Dict:
        return {
            "template_name": self.template_name,
            "url": self.url,
            "passed": self.passed,
            "timestamp": self.timestamp,
            "response_time": self.response_time,
            "status_code": self.status_code,
            "assertions_total": len(self.assertions),
            "assertions_passed": self.passed_count,
            "assertions_failed": self.failed_count,
            "error": self.error,
            "metadata": self.metadata
        }


@dataclass
class BaseTemplate:
    """Template base para health checks."""
    name: str
    url: str
    method: str = "GET"
    headers: Dict[str, str] = field(default_factory=dict)
    timeout: float = 10.0
    assertions: List[Assertion] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_assertion(self, assertion: Assertion) -> "BaseTemplate":
        """Adiciona uma assertion ao template."""
        self.assertions.append(assertion)
        return self
    
    def check(self) -> CheckResult:
        """Executa o health check."""
        if not HAS_REQUESTS:
            return CheckResult(
                template_name=self.name,
                url=self.url,
                passed=False,
                timestamp=time.time(),
                response_time=0,
                error="requests library not installed"
            )
        
        start_time = time.time()
        result = CheckResult(
            template_name=self.name,
            url=self.url,
            passed=True,
            timestamp=start_time,
            response_time=0
        )
        
        try:
            response = requests.request(
                method=self.method,
                url=self.url,
                headers=self.headers,
                timeout=self.timeout
            )
            
            result.response_time = time.time() - start_time
            result.status_code = response.status_code
            
            # Parse response
            try:
                body = response.json()
            except (json.JSONDecodeError, ValueError):
                body = response.text
            
            headers = dict(response.headers)
            
            # Evaluate assertions
            for assertion in self.assertions:
                if assertion.type == AssertionType.STATUS_CODE:
                    assertion.actual = response.status_code
                elif assertion.type == AssertionType.RESPONSE_TIME:
                    assertion.actual = result.response_time
                elif assertion.type in (AssertionType.JSON_SCHEMA, AssertionType.JSON_PATH):
                    assertion.actual = body
                elif assertion.type == AssertionType.HEADER:
                    assertion.actual = headers
                elif assertion.type in (AssertionType.BODY_CONTAINS, AssertionType.BODY_REGEX):
                    assertion.actual = body if isinstance(body, str) else json.dumps(body)
                elif assertion.type == AssertionType.CUSTOM:
                    assertion.actual = {
                        "status_code": response.status_code,
                        "headers": headers,
                        "body": body,
                        "response_time": result.response_time
                    }
                
                assertion.evaluate()
            
            result.assertions = self.assertions
            result.passed = all(a.passed for a in self.assertions if a.severity in (Severity.ERROR, Severity.CRITICAL))
            result.metadata = {
                "content_length": len(response.content),
                "content_type": response.headers.get("Content-Type", "")
            }
            
        except requests.Timeout:
            result.error = f"Timeout after {self.timeout}s"
            result.passed = False
        except requests.ConnectionError as e:
            result.error = f"Connection error: {str(e)}"
            result.passed = False
        except Exception as e:
            result.error = f"Unexpected error: {str(e)}"
            result.passed = False
        
        return result


@dataclass
class RESTTemplate(BaseTemplate):
    """Template para APIs REST."""
    expected_status: Union[int, List[int]] = 200
    max_response_time: float = 5.0
    json_schema: Optional[Dict] = None
    json_paths: List[Dict] = field(default_factory=list)
    required_headers: List[str] = field(default_factory=list)
    body_contains: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Configura assertions baseado nos parâmetros."""
        # Status code
        self.add_assertion(Assertion(
            type=AssertionType.STATUS_CODE,
            expected=self.expected_status,
            severity=Severity.CRITICAL
        ))
        
        # Response time
        if self.max_response_time > 0:
            self.add_assertion(Assertion(
                type=AssertionType.RESPONSE_TIME,
                expected=self.max_response_time,
                severity=Severity.ERROR
            ))
        
        # JSON schema
        if self.json_schema:
            self.add_assertion(Assertion(
                type=AssertionType.JSON_SCHEMA,
                expected=self.json_schema,
                severity=Severity.ERROR
            ))
        
        # JSON paths
        for path_config in self.json_paths:
            self.add_assertion(Assertion(
                type=AssertionType.JSON_PATH,
                expected=path_config,
                severity=Severity.WARNING
            ))
        
        # Required headers
        for header in self.required_headers:
            self.add_assertion(Assertion(
                type=AssertionType.HEADER,
                expected=(header, None),
                severity=Severity.WARNING
            ))
        
        # Body contains
        for text in self.body_contains:
            self.add_assertion(Assertion(
                type=AssertionType.BODY_CONTAINS,
                expected=text,
                severity=Severity.ERROR
            ))


@dataclass
class GraphQLTemplate(BaseTemplate):
    """Template para APIs GraphQL."""
    query: str = ""
    variables: Dict = field(default_factory=dict)
    expected_status: int = 200
    max_response_time: float = 5.0
    expect_no_errors: bool = True
    data_paths: List[Dict] = field(default_factory=list)
    
    def __post_init__(self):
        """Configura para GraphQL."""
        self.method = "POST"
        self.headers.setdefault("Content-Type", "application/json")
        
        if not self.query:
            self.query = "{ __typename }"
    
    def check(self) -> CheckResult:
        """Executa health check GraphQL."""
        if not HAS_REQUESTS:
            return CheckResult(
                template_name=self.name,
                url=self.url,
                passed=False,
                timestamp=time.time(),
                response_time=0,
                error="requests library not installed"
            )
        
        # Build GraphQL payload
        payload = {
            "query": self.query,
            "variables": self.variables
        }
        
        start_time = time.time()
        result = CheckResult(
            template_name=self.name,
            url=self.url,
            passed=True,
            timestamp=start_time,
            response_time=0
        )
        
        try:
            response = requests.post(
                url=self.url,
                json=payload,
                headers=self.headers,
                timeout=self.timeout
            )
            
            result.response_time = time.time() - start_time
            result.status_code = response.status_code
            
            try:
                body = response.json()
            except (json.JSONDecodeError, ValueError):
                result.error = "Invalid JSON response"
                result.passed = False
                return result
            
            # Check status
            if response.status_code != self.expected_status:
                result.passed = False
                result.error = f"Expected status {self.expected_status}, got {response.status_code}"
            
            # Check response time
            if result.response_time > self.max_response_time:
                result.passed = False
                if result.error:
                    result.error += f"; Response time {result.response_time:.3f}s > {self.max_response_time}s"
                else:
                    result.error = f"Response time {result.response_time:.3f}s > {self.max_response_time}s"
            
            # Check for GraphQL errors
            if self.expect_no_errors and "errors" in body:
                result.passed = False
                errors = body["errors"]
                error_msgs = [e.get("message", str(e)) for e in errors]
                if result.error:
                    result.error += f"; GraphQL errors: {', '.join(error_msgs)}"
                else:
                    result.error = f"GraphQL errors: {', '.join(error_msgs)}"
            
            # Check data paths
            for path_config in self.data_paths:
                path = path_config.get("path", "")
                expected = path_config.get("value")
                
                data = body.get("data", {})
                parts = path.split(".")
                current = data
                
                path_ok = True
                for part in parts:
                    if isinstance(current, dict) and part in current:
                        current = current[part]
                    else:
                        path_ok = False
                        break
                
                if not path_ok or (expected is not None and current != expected):
                    result.passed = False
                    if result.error:
                        result.error += f"; Data path '{path}' check failed"
                    else:
                        result.error = f"Data path '{path}' check failed"
            
            result.assertions = [
                Assertion(
                    type=AssertionType.STATUS_CODE,
                    expected=self.expected_status,
                    actual=response.status_code,
                    passed=response.status_code == self.expected_status
                ),
                Assertion(
                    type=AssertionType.RESPONSE_TIME,
                    expected=self.max_response_time,
                    actual=result.response_time,
                    passed=result.response_time <= self.max_response_time
                )
            ]
            
            if self.expect_no_errors:
                has_errors = "errors" in body
                result.assertions.append(Assertion(
                    type=AssertionType.CUSTOM,
                    expected=lambda x: not has_errors,
                    actual=body,
                    passed=not has_errors,
                    message=f"GraphQL {'has' if has_errors else 'no'} errors"
                ))
            
        except Exception as e:
            result.error = f"Error: {str(e)}"
            result.passed = False
        
        return result


class TemplateChecker:
    """Gerenciador de templates de health check."""
    
    def __init__(self):
        self.templates: Dict[str, BaseTemplate] = {}
        self.history: Dict[str, List[CheckResult]] = {}
        self.lock = Lock()
        self.stats = {
            "total_checks": 0,
            "passed": 0,
            "failed": 0,
            "total_response_time": 0
        }
    
    def register(self, name: str, template: BaseTemplate) -> None:
        """Registra um template."""
        with self.lock:
            self.templates[name] = template
            if name not in self.history:
                self.history[name] = []
    
    def unregister(self, name: str) -> bool:
        """Remove um template."""
        with self.lock:
            if name in self.templates:
                del self.templates[name]
                return True
            return False
    
    def check(self, name: str) -> Optional[CheckResult]:
        """Executa check de um template específico."""
        with self.lock:
            template = self.templates.get(name)
        
        if not template:
            return None
        
        result = template.check()
        
        with self.lock:
            self.history[name].append(result)
            # Keep last 100 results
            if len(self.history[name]) > 100:
                self.history[name] = self.history[name][-100:]
            
            self.stats["total_checks"] += 1
            self.stats["total_response_time"] += result.response_time
            if result.passed:
                self.stats["passed"] += 1
            else:
                self.stats["failed"] += 1
        
        return result
    
    def check_all(self) -> Dict[str, CheckResult]:
        """Executa check de todos os templates."""
        results = {}
        for name in list(self.templates.keys()):
            result = self.check(name)
            if result:
                results[name] = result
        return results
    
    def get_history(self, name: str, limit: int = 10) -> List[CheckResult]:
        """Obtém histórico de checks."""
        with self.lock:
            history = self.history.get(name, [])
            return history[-limit:]
    
    def get_uptime(self, name: str, window: int = 100) -> Optional[float]:
        """Calcula uptime percentual."""
        with self.lock:
            history = self.history.get(name, [])
        
        if not history:
            return None
        
        recent = history[-window:]
        passed = sum(1 for r in recent if r.passed)
        return (passed / len(recent)) * 100
    
    def get_stats(self) -> Dict:
        """Retorna estatísticas do checker."""
        with self.lock:
            stats = self.stats.copy()
            stats["templates_count"] = len(self.templates)
            if stats["total_checks"] > 0:
                stats["avg_response_time"] = stats["total_response_time"] / stats["total_checks"]
            else:
                stats["avg_response_time"] = 0
            return stats
    
    def get_template_names(self) -> List[str]:
        """Lista nomes dos templates registrados."""
        with self.lock:
            return list(self.templates.keys())


# Factory functions para conveniência

def create_rest_template(
    name: str,
    url: str,
    expected_status: Union[int, List[int]] = 200,
    max_response_time: float = 5.0,
    json_schema: Optional[Dict] = None,
    **kwargs
) -> RESTTemplate:
    """Cria template REST rapidamente."""
    return RESTTemplate(
        name=name,
        url=url,
        expected_status=expected_status,
        max_response_time=max_response_time,
        json_schema=json_schema,
        **kwargs
    )


def create_graphql_template(
    name: str,
    url: str,
    query: str = "",
    max_response_time: float = 5.0,
    **kwargs
) -> GraphQLTemplate:
    """Cria template GraphQL rapidamente."""
    return GraphQLTemplate(
        name=name,
        url=url,
        query=query,
        max_response_time=max_response_time,
        **kwargs
    )


# Presets comuns

def create_kubernetes_healthz(url: str, name: str = "k8s-healthz") -> RESTTemplate:
    """Template para healthz do Kubernetes."""
    return RESTTemplate(
        name=name,
        url=url,
        expected_status=200,
        max_response_time=1.0,
        tags=["kubernetes", "healthz"]
    )


def create_elasticsearch_health(url: str, name: str = "elasticsearch") -> RESTTemplate:
    """Template para health check do Elasticsearch."""
    return RESTTemplate(
        name=name,
        url=f"{url}/_cluster/health",
        expected_status=200,
        max_response_time=3.0,
        json_schema={"status": str, "cluster_name": str},
        json_paths=[
            {"path": "status", "operator": "ne", "value": "red"}
        ],
        tags=["elasticsearch", "database"]
    )


def create_postgres_health(url: str, name: str = "postgres") -> RESTTemplate:
    """Template para health check via endpoint HTTP do PostgreSQL."""
    return RESTTemplate(
        name=name,
        url=url,
        expected_status=200,
        max_response_time=2.0,
        body_contains=["ok", "healthy", "up"],
        tags=["postgres", "database"]
    )
