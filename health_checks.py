"""
Health Checks Avançados para Mengão Monitor v2.6

Checks customizáveis:
- DNS Resolution
- SSL Certificate Validation
- TCP Port Check
- HTTP Headers Validation
- Response Time SLO
- JSON Response Validation
- Custom Script Execution
"""

import socket
import ssl
import time
import json
import subprocess
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, Dict, Any, List
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class CheckStatus(Enum):
    """Status de um health check."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class CheckResult:
    """Resultado de um health check."""
    name: str
    status: CheckStatus
    message: str
    duration_ms: float
    timestamp: datetime = field(default_factory=datetime.now)
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "duration_ms": round(self.duration_ms, 2),
            "timestamp": self.timestamp.isoformat(),
            "details": self.details
        }


class HealthCheck:
    """Base class para health checks."""
    
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.last_result: Optional[CheckResult] = None
        self.last_run: Optional[datetime] = None
        self.run_count: int = 0
        self.failure_count: int = 0
    
    def run(self) -> CheckResult:
        """Executa o health check."""
        start = time.monotonic()
        try:
            result = self._execute()
            duration_ms = (time.monotonic() - start) * 1000
            result.duration_ms = duration_ms
            result.timestamp = datetime.now()
            
            self.last_result = result
            self.last_run = datetime.now()
            self.run_count += 1
            
            if result.status != CheckStatus.HEALTHY:
                self.failure_count += 1
            
            return result
            
        except Exception as e:
            duration_ms = (time.monotonic() - start) * 1000
            result = CheckResult(
                name=self.name,
                status=CheckStatus.UNHEALTHY,
                message=f"Check failed: {str(e)}",
                duration_ms=duration_ms,
                details={"error": str(e), "error_type": type(e).__name__}
            )
            self.last_result = result
            self.last_run = datetime.now()
            self.run_count += 1
            self.failure_count += 1
            return result
    
    def _execute(self) -> CheckResult:
        """Implementação específica do check. Override em subclasses."""
        raise NotImplementedError
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do check."""
        return {
            "name": self.name,
            "description": self.description,
            "run_count": self.run_count,
            "failure_count": self.failure_count,
            "success_rate": (self.run_count - self.failure_count) / max(self.run_count, 1) * 100,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "last_status": self.last_result.status.value if self.last_result else None
        }


class DNSCheck(HealthCheck):
    """Verifica resolução DNS de um hostname."""
    
    def __init__(self, name: str, hostname: str, expected_ips: List[str] = None, timeout: float = 5.0):
        super().__init__(name, f"DNS resolution check for {hostname}")
        self.hostname = hostname
        self.expected_ips = expected_ips or []
        self.timeout = timeout
    
    def _execute(self) -> CheckResult:
        socket.setdefaulttimeout(self.timeout)
        try:
            resolved_ips = socket.gethostbyname_ex(self.hostname)[2]
            
            if not resolved_ips:
                return CheckResult(
                    name=self.name,
                    status=CheckStatus.UNHEALTHY,
                    message=f"DNS resolution failed for {self.hostname}",
                    duration_ms=0,
                    details={"hostname": self.hostname}
                )
            
            # Se IPs esperados foram definidos, verificar se algum bate
            if self.expected_ips:
                matching = set(resolved_ips) & set(self.expected_ips)
                if not matching:
                    return CheckResult(
                        name=self.name,
                        status=CheckStatus.DEGRADED,
                        message=f"DNS resolved but IPs don't match expected",
                        duration_ms=0,
                        details={
                            "hostname": self.hostname,
                            "resolved": resolved_ips,
                            "expected": self.expected_ips
                        }
                    )
            
            return CheckResult(
                name=self.name,
                status=CheckStatus.HEALTHY,
                message=f"DNS resolved: {', '.join(resolved_ips)}",
                duration_ms=0,
                details={"hostname": self.hostname, "resolved_ips": resolved_ips}
            )
            
        except socket.gaierror as e:
            return CheckResult(
                name=self.name,
                status=CheckStatus.UNHEALTHY,
                message=f"DNS resolution failed: {str(e)}",
                duration_ms=0,
                details={"hostname": self.hostname, "error": str(e)}
            )


class SSLCheck(HealthCheck):
    """Verifica certificado SSL de um host."""
    
    def __init__(self, name: str, hostname: str, port: int = 443, 
                 warn_days: int = 30, critical_days: int = 7):
        super().__init__(name, f"SSL certificate check for {hostname}:{port}")
        self.hostname = hostname
        self.port = port
        self.warn_days = warn_days
        self.critical_days = critical_days
    
    def _execute(self) -> CheckResult:
        context = ssl.create_default_context()
        
        with socket.create_connection((self.hostname, self.port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=self.hostname) as ssock:
                cert = ssock.getpeercert()
                
                # Parse expiry
                not_after = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z')
                days_remaining = (not_after - datetime.now()).days
                
                # Parse issuer
                issuer = dict(x[0] for x in cert['issuer'])
                
                # Parse subject
                subject = dict(x[0] for x in cert['subject'])
                
                # Verificar SANs
                sans = []
                for type_value in cert.get('subjectAltName', []):
                    sans.append({"type": type_value[0], "value": type_value[1]})
                
                details = {
                    "hostname": self.hostname,
                    "issuer": issuer.get('organizationName', 'Unknown'),
                    "subject": subject.get('commonName', 'Unknown'),
                    "not_before": cert['notBefore'],
                    "not_after": cert['notAfter'],
                    "days_remaining": days_remaining,
                    "sans": sans,
                    "serial_number": cert.get('serialNumber', 'Unknown')
                }
                
                if days_remaining <= self.critical_days:
                    status = CheckStatus.UNHEALTHY
                    message = f"SSL certificate expires in {days_remaining} days! (CRITICAL)"
                elif days_remaining <= self.warn_days:
                    status = CheckStatus.DEGRADED
                    message = f"SSL certificate expires in {days_remaining} days (WARNING)"
                else:
                    status = CheckStatus.HEALTHY
                    message = f"SSL certificate valid, {days_remaining} days remaining"
                
                return CheckResult(
                    name=self.name,
                    status=status,
                    message=message,
                    duration_ms=0,
                    details=details
                )


class TCPCheck(HealthCheck):
    """Verifica se uma porta TCP está aberta."""
    
    def __init__(self, name: str, host: str, port: int, timeout: float = 5.0):
        super().__init__(name, f"TCP port check for {host}:{port}")
        self.host = host
        self.port = port
        self.timeout = timeout
    
    def _execute(self) -> CheckResult:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        
        try:
            start = time.monotonic()
            result = sock.connect_ex((self.host, self.port))
            connect_time = (time.monotonic() - start) * 1000
            
            if result == 0:
                return CheckResult(
                    name=self.name,
                    status=CheckStatus.HEALTHY,
                    message=f"Port {self.port} is open",
                    duration_ms=0,
                    details={
                        "host": self.host,
                        "port": self.port,
                        "connect_time_ms": round(connect_time, 2)
                    }
                )
            else:
                return CheckResult(
                    name=self.name,
                    status=CheckStatus.UNHEALTHY,
                    message=f"Port {self.port} is closed or filtered",
                    duration_ms=0,
                    details={
                        "host": self.host,
                        "port": self.port,
                        "error_code": result
                    }
                )
        finally:
            sock.close()


class HTTPHeaderCheck(HealthCheck):
    """Verifica headers HTTP específicos na resposta."""
    
    def __init__(self, name: str, url: str, expected_headers: Dict[str, str],
                 method: str = "GET", timeout: float = 10.0):
        super().__init__(name, f"HTTP header check for {url}")
        self.url = url
        self.expected_headers = expected_headers
        self.method = method
        self.timeout = timeout
    
    def _execute(self) -> CheckResult:
        import requests
        
        response = requests.request(self.method, self.url, timeout=self.timeout)
        
        missing = []
        mismatched = []
        matched = []
        
        for header, expected_value in self.expected_headers.items():
            actual_value = response.headers.get(header)
            
            if actual_value is None:
                missing.append(header)
            elif expected_value and expected_value.lower() not in actual_value.lower():
                mismatched.append({
                    "header": header,
                    "expected": expected_value,
                    "actual": actual_value
                })
            else:
                matched.append(header)
        
        if missing or mismatched:
            status = CheckStatus.UNHEALTHY if missing else CheckStatus.DEGRADED
            messages = []
            if missing:
                messages.append(f"Missing headers: {', '.join(missing)}")
            if mismatched:
                messages.append(f"Mismatched headers: {len(mismatched)}")
            
            return CheckResult(
                name=self.name,
                status=status,
                message="; ".join(messages),
                duration_ms=0,
                details={
                    "url": self.url,
                    "status_code": response.status_code,
                    "missing": missing,
                    "mismatched": mismatched,
                    "matched": matched
                }
            )
        
        return CheckResult(
            name=self.name,
            status=CheckStatus.HEALTHY,
            message=f"All {len(matched)} headers matched",
            duration_ms=0,
            details={
                "url": self.url,
                "status_code": response.status_code,
                "matched": matched
            }
        )


class ResponseTimeSLOCheck(HealthCheck):
    """Verifica se o tempo de resposta está dentro do SLO."""
    
    def __init__(self, name: str, url: str, slo_ms: float,
                 method: str = "GET", timeout: float = 10.0,
                 warn_threshold: float = 0.8):
        super().__init__(name, f"Response time SLO check for {url}")
        self.url = url
        self.slo_ms = slo_ms
        self.method = method
        self.timeout = timeout
        self.warn_threshold = warn_threshold  # % do SLO para warning
    
    def _execute(self) -> CheckResult:
        import requests
        
        start = time.monotonic()
        response = requests.request(self.method, self.url, timeout=self.timeout)
        duration_ms = (time.monotonic() - start) * 1000
        
        slo_percentage = (duration_ms / self.slo_ms) * 100
        
        details = {
            "url": self.url,
            "response_time_ms": round(duration_ms, 2),
            "slo_ms": self.slo_ms,
            "slo_percentage": round(slo_percentage, 1),
            "status_code": response.status_code
        }
        
        if duration_ms > self.slo_ms:
            return CheckResult(
                name=self.name,
                status=CheckStatus.UNHEALTHY,
                message=f"SLO violated: {duration_ms:.0f}ms > {self.slo_ms:.0f}ms ({slo_percentage:.0f}%)",
                duration_ms=0,
                details=details
            )
        elif duration_ms > self.slo_ms * self.warn_threshold:
            return CheckResult(
                name=self.name,
                status=CheckStatus.DEGRADED,
                message=f"Approaching SLO limit: {duration_ms:.0f}ms ({slo_percentage:.0f}% of {self.slo_ms:.0f}ms)",
                duration_ms=0,
                details=details
            )
        
        return CheckResult(
            name=self.name,
            status=CheckStatus.HEALTHY,
            message=f"Response time OK: {duration_ms:.0f}ms ({slo_percentage:.0f}% of SLO)",
            duration_ms=0,
            details=details
        )


class JSONResponseCheck(HealthCheck):
    """Valida estrutura e valores de uma resposta JSON."""
    
    def __init__(self, name: str, url: str, 
                 expected_fields: Dict[str, Any] = None,
                 required_fields: List[str] = None,
                 json_path_checks: Dict[str, Any] = None,
                 method: str = "GET", timeout: float = 10.0):
        super().__init__(name, f"JSON response check for {url}")
        self.url = url
        self.expected_fields = expected_fields or {}
        self.required_fields = required_fields or []
        self.json_path_checks = json_path_checks or {}
        self.method = method
        self.timeout = timeout
    
    def _execute(self) -> CheckResult:
        import requests
        
        response = requests.request(self.method, self.url, timeout=self.timeout)
        
        try:
            data = response.json()
        except ValueError:
            return CheckResult(
                name=self.name,
                status=CheckStatus.UNHEALTHY,
                message="Response is not valid JSON",
                duration_ms=0,
                details={"url": self.url, "status_code": response.status_code}
            )
        
        issues = []
        
        # Verificar campos obrigatórios
        for field in self.required_fields:
            if not self._get_nested_value(data, field):
                issues.append(f"Missing required field: {field}")
        
        # Verificar valores esperados
        for field, expected in self.expected_fields.items():
            actual = self._get_nested_value(data, field)
            if actual != expected:
                issues.append(f"Field '{field}': expected {expected}, got {actual}")
        
        # Verificar json path checks
        for path, condition in self.json_path_checks.items():
            value = self._get_nested_value(data, path)
            if not self._evaluate_condition(value, condition):
                issues.append(f"Path '{path}' failed condition: {condition}")
        
        if issues:
            return CheckResult(
                name=self.name,
                status=CheckStatus.UNHEALTHY,
                message=f"{len(issues)} validation issues found",
                duration_ms=0,
                details={
                    "url": self.url,
                    "issues": issues,
                    "response_sample": str(data)[:500]
                }
            )
        
        return CheckResult(
            name=self.name,
            status=CheckStatus.HEALTHY,
            message="JSON response validated successfully",
            duration_ms=0,
            details={
                "url": self.url,
                "fields_checked": len(self.expected_fields) + len(self.required_fields)
            }
        )
    
    def _get_nested_value(self, data: Any, path: str) -> Any:
        """Obtém valor de um path aninhado (ex: 'data.user.name')."""
        keys = path.split('.')
        current = data
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list) and key.isdigit():
                current = current[int(key)]
            else:
                return None
        return current
    
    def _evaluate_condition(self, value: Any, condition: Any) -> bool:
        """Avalia uma condição contra um valor."""
        if isinstance(condition, dict):
            if "gt" in condition:
                return value > condition["gt"]
            if "lt" in condition:
                return value < condition["lt"]
            if "gte" in condition:
                return value >= condition["gte"]
            if "lte" in condition:
                return value <= condition["lte"]
            if "contains" in condition:
                return condition["contains"] in str(value)
            if "regex" in condition:
                import re
                return bool(re.search(condition["regex"], str(value)))
        return value == condition


class HealthCheckManager:
    """Gerenciador de health checks."""
    
    def __init__(self):
        self.checks: Dict[str, HealthCheck] = {}
        self.history: List[Dict[str, Any]] = []
        self.max_history = 1000
    
    def register(self, check: HealthCheck) -> None:
        """Registra um health check."""
        self.checks[check.name] = check
        logger.info(f"Health check registered: {check.name}")
    
    def unregister(self, name: str) -> bool:
        """Remove um health check."""
        if name in self.checks:
            del self.checks[name]
            logger.info(f"Health check unregistered: {name}")
            return True
        return False
    
    def run_check(self, name: str) -> Optional[CheckResult]:
        """Executa um check específico."""
        check = self.checks.get(name)
        if not check:
            return None
        
        result = check.run()
        self._add_to_history(result)
        return result
    
    def run_all(self) -> Dict[str, CheckResult]:
        """Executa todos os checks."""
        results = {}
        for name, check in self.checks.items():
            result = check.run()
            results[name] = result
            self._add_to_history(result)
        return results
    
    def get_status(self) -> Dict[str, Any]:
        """Retorna status geral de todos os checks."""
        results = self.run_all()
        
        healthy = sum(1 for r in results.values() if r.status == CheckStatus.HEALTHY)
        degraded = sum(1 for r in results.values() if r.status == CheckStatus.DEGRADED)
        unhealthy = sum(1 for r in results.values() if r.status == CheckStatus.UNHEALTHY)
        
        overall = CheckStatus.HEALTHY
        if unhealthy > 0:
            overall = CheckStatus.UNHEALTHY
        elif degraded > 0:
            overall = CheckStatus.DEGRADED
        
        return {
            "overall_status": overall.value,
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total": len(results),
                "healthy": healthy,
                "degraded": degraded,
                "unhealthy": unhealthy
            },
            "checks": {name: r.to_dict() for name, r in results.items()}
        }
    
    def get_check_stats(self, name: str) -> Optional[Dict[str, Any]]:
        """Retorna estatísticas de um check específico."""
        check = self.checks.get(name)
        return check.get_stats() if check else None
    
    def get_all_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas de todos os checks."""
        return {
            name: check.get_stats()
            for name, check in self.checks.items()
        }
    
    def get_history(self, name: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Retorna histórico de execuções."""
        history = self.history
        if name:
            history = [h for h in history if h.get("name") == name]
        return history[-limit:]
    
    def _add_to_history(self, result: CheckResult) -> None:
        """Adiciona resultado ao histórico."""
        self.history.append(result.to_dict())
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
    
    def create_from_config(self, config: Dict[str, Any]) -> None:
        """Cria checks a partir de configuração."""
        check_types = {
            "dns": DNSCheck,
            "ssl": SSLCheck,
            "tcp": TCPCheck,
            "http_header": HTTPHeaderCheck,
            "response_time_slo": ResponseTimeSLOCheck,
            "json_response": JSONResponseCheck
        }
        
        for check_config in config.get("health_checks", []):
            check_type = check_config.get("type")
            if check_type in check_types:
                check_class = check_types[check_type]
                params = {k: v for k, v in check_config.items() if k != "type"}
                check = check_class(**params)
                self.register(check)
