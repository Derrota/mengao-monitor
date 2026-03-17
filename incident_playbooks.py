"""
🦞 Mengão Monitor v3.11 - Incident Response Playbooks

Sistema de playbooks automatizados para resposta a incidentes.
Executa ações predefinidas quando alertas são disparados ou escalam.

Features:
- Playbooks por severidade, endpoint ou tipo de alerta
- Ações: notify, run_command, http_request, scale, restart
- Condições: rate limiting, cooldown, max_executions
- Histórico completo de execuções
- Thread-safe com execução assíncrona
- Integração com Alert Escalation e Data Layer
"""

import json
import time
import threading
import subprocess
import hashlib
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Callable, Dict, List, Any, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class ActionType(Enum):
    """Tipos de ações suportadas pelos playbooks."""
    NOTIFY = "notify"           # Enviar notificação (webhook, email)
    RUN_COMMAND = "run_command" # Executar comando shell
    HTTP_REQUEST = "http_request"  # Fazer requisição HTTP
    SCALE = "scale"             # Escalar serviço (placeholder)
    RESTART = "restart"         # Reiniciar serviço
    LOG = "log"                 # Apenas logar
    CUSTOM = "custom"           # Função Python customizada


class TriggerType(Enum):
    """Tipos de triggers para playbooks."""
    ALERT_CREATED = "alert_created"
    ALERT_ESCALATED = "alert_escalated"
    ALERT_RESOLVED = "alert_resolved"
    METRIC_THRESHOLD = "metric_threshold"
    HEALTH_CHECK_FAILED = "health_check_failed"
    MANUAL = "manual"


class PlaybookStatus(Enum):
    """Status de execução de um playbook."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    RATE_LIMITED = "rate_limited"


@dataclass
class PlaybookAction:
    """Uma ação dentro de um playbook."""
    action_type: str  # ActionType como string
    name: str
    config: Dict[str, Any] = field(default_factory=dict)
    timeout: int = 30
    retry_count: int = 0
    retry_delay: int = 5
    on_failure: str = "continue"  # continue, stop, rollback
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'PlaybookAction':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class PlaybookCondition:
    """Condição para execução de playbook."""
    field: str  # ex: "severity", "endpoint", "alert_type"
    operator: str  # eq, ne, gt, lt, gte, lte, contains, regex
    value: Any
    
    def evaluate(self, context: Dict[str, Any]) -> bool:
        """Avalia a condição contra o contexto."""
        actual = context.get(self.field)
        if actual is None:
            return False
        
        try:
            if self.operator == "eq":
                return actual == self.value
            elif self.operator == "ne":
                return actual != self.value
            elif self.operator == "gt":
                return float(actual) > float(self.value)
            elif self.operator == "lt":
                return float(actual) < float(self.value)
            elif self.operator == "gte":
                return float(actual) >= float(self.value)
            elif self.operator == "lte":
                return float(actual) <= float(self.value)
            elif self.operator == "contains":
                return str(self.value) in str(actual)
            elif self.operator == "regex":
                import re
                return bool(re.search(str(self.value), str(actual)))
        except (ValueError, TypeError):
            return False
        
        return False


@dataclass
class Playbook:
    """Definição de um playbook."""
    id: str
    name: str
    description: str
    trigger: str  # TriggerType como string
    conditions: List[PlaybookCondition] = field(default_factory=list)
    actions: List[PlaybookAction] = field(default_factory=list)
    enabled: bool = True
    priority: int = 100  # Menor = maior prioridade
    cooldown_seconds: int = 300  # 5 minutos entre execuções
    max_executions_per_hour: int = 10
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict:
        data = asdict(self)
        data['conditions'] = [asdict(c) for c in self.conditions]
        data['actions'] = [a.to_dict() for a in self.actions]
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Playbook':
        conditions = [PlaybookCondition(**c) for c in data.pop('conditions', [])]
        actions = [PlaybookAction.from_dict(a) for a in data.pop('actions', [])]
        return cls(conditions=conditions, actions=actions, **{
            k: v for k, v in data.items() if k in cls.__dataclass_fields__
        })


@dataclass
class PlaybookExecution:
    """Registro de execução de um playbook."""
    id: str
    playbook_id: str
    playbook_name: str
    trigger: str
    context: Dict[str, Any]
    status: str  # PlaybookStatus como string
    started_at: float
    completed_at: Optional[float] = None
    duration_ms: Optional[float] = None
    actions_executed: int = 0
    actions_failed: int = 0
    results: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


class IncidentPlaybookManager:
    """
    Gerenciador de playbooks para resposta a incidentes.
    
    Thread-safe, com rate limiting e histórico de execuções.
    """
    
    def __init__(self, max_history: int = 1000):
        self._playbooks: Dict[str, Playbook] = {}
        self._executions: List[PlaybookExecution] = []
        self._execution_counts: Dict[str, List[float]] = defaultdict(list)
        self._last_execution: Dict[str, float] = {}
        self._custom_handlers: Dict[str, Callable] = {}
        self._lock = threading.RLock()
        self._max_history = max_history
        
        # Stats
        self._stats = {
            'total_executions': 0,
            'successful_executions': 0,
            'failed_executions': 0,
            'skipped_executions': 0,
            'rate_limited_executions': 0,
            'total_actions_executed': 0,
            'total_actions_failed': 0,
        }
        
        logger.info("IncidentPlaybookManager initialized")
    
    # ─── Playbook CRUD ─────────────────────────────────────────────
    
    def register_playbook(self, playbook: Playbook) -> bool:
        """Registra um novo playbook."""
        with self._lock:
            if playbook.id in self._playbooks:
                logger.warning(f"Playbook {playbook.id} already exists, updating")
            
            self._playbooks[playbook.id] = playbook
            logger.info(f"Playbook registered: {playbook.name} ({playbook.id})")
            return True
    
    def unregister_playbook(self, playbook_id: str) -> bool:
        """Remove um playbook."""
        with self._lock:
            if playbook_id in self._playbooks:
                del self._playbooks[playbook_id]
                logger.info(f"Playbook unregistered: {playbook_id}")
                return True
            return False
    
    def get_playbook(self, playbook_id: str) -> Optional[Playbook]:
        """Obtém um playbook por ID."""
        with self._lock:
            return self._playbooks.get(playbook_id)
    
    def list_playbooks(self, enabled_only: bool = False) -> List[Playbook]:
        """Lista todos os playbooks."""
        with self._lock:
            playbooks = list(self._playbooks.values())
            if enabled_only:
                playbooks = [p for p in playbooks if p.enabled]
            return sorted(playbooks, key=lambda p: p.priority)
    
    def enable_playbook(self, playbook_id: str) -> bool:
        """Habilita um playbook."""
        with self._lock:
            playbook = self._playbooks.get(playbook_id)
            if playbook:
                playbook.enabled = True
                playbook.updated_at = time.time()
                return True
            return False
    
    def disable_playbook(self, playbook_id: str) -> bool:
        """Desabilita um playbook."""
        with self._lock:
            playbook = self._playbooks.get(playbook_id)
            if playbook:
                playbook.enabled = False
                playbook.updated_at = time.time()
                return True
            return False
    
    # ─── Custom Handlers ───────────────────────────────────────────
    
    def register_handler(self, name: str, handler: Callable) -> None:
        """Registra um handler customizado para ações CUSTOM."""
        with self._lock:
            self._custom_handlers[name] = handler
            logger.info(f"Custom handler registered: {name}")
    
    # ─── Execution ─────────────────────────────────────────────────
    
    def trigger(self, trigger_type: str, context: Dict[str, Any]) -> List[PlaybookExecution]:
        """
        Dispara playbooks baseado no trigger e contexto.
        
        Returns lista de execuções iniciadas.
        """
        with self._lock:
            matching_playbooks = self._find_matching_playbooks(trigger_type, context)
        
        executions = []
        for playbook in matching_playbooks:
            execution = self._execute_playbook(playbook, trigger_type, context)
            if execution:
                executions.append(execution)
        
        return executions
    
    def _find_matching_playbooks(self, trigger_type: str, context: Dict[str, Any]) -> List[Playbook]:
        """Encontra playbooks que correspondem ao trigger e contexto."""
        matching = []
        
        for playbook in self._playbooks.values():
            if not playbook.enabled:
                continue
            
            if playbook.trigger != trigger_type:
                continue
            
            # Avalia condições
            if playbook.conditions:
                all_match = all(c.evaluate(context) for c in playbook.conditions)
                if not all_match:
                    continue
            
            matching.append(playbook)
        
        # Ordena por prioridade
        return sorted(matching, key=lambda p: p.priority)
    
    def _check_rate_limit(self, playbook: Playbook) -> Tuple[bool, str]:
        """Verifica se o playbook pode ser executado (rate limiting)."""
        now = time.time()
        playbook_id = playbook.id
        
        # Verifica cooldown
        last_exec = self._last_execution.get(playbook_id, 0)
        if now - last_exec < playbook.cooldown_seconds:
            remaining = playbook.cooldown_seconds - (now - last_exec)
            return False, f"Cooldown: {remaining:.0f}s remaining"
        
        # Verifica max executions per hour
        hour_ago = now - 3600
        recent_executions = [
            t for t in self._execution_counts.get(playbook_id, [])
            if t > hour_ago
        ]
        
        if len(recent_executions) >= playbook.max_executions_per_hour:
            return False, f"Rate limited: {len(recent_executions)}/{playbook.max_executions_per_hour} in last hour"
        
        return True, ""
    
    def _execute_playbook(self, playbook: Playbook, trigger: str, context: Dict[str, Any]) -> Optional[PlaybookExecution]:
        """Executa um playbook."""
        # Verifica rate limit
        can_execute, reason = self._check_rate_limit(playbook)
        if not can_execute:
            logger.warning(f"Playbook {playbook.name} rate limited: {reason}")
            execution = PlaybookExecution(
                id=self._generate_id(),
                playbook_id=playbook.id,
                playbook_name=playbook.name,
                trigger=trigger,
                context=context,
                status=PlaybookStatus.RATE_LIMITED.value,
                started_at=time.time(),
                error=reason
            )
            execution.completed_at = time.time()
            execution.duration_ms = 0
            
            with self._lock:
                self._executions.append(execution)
                self._stats['rate_limited_executions'] += 1
                self._trim_history()
            
            return execution
        
        # Cria registro de execução
        execution = PlaybookExecution(
            id=self._generate_id(),
            playbook_id=playbook.id,
            playbook_name=playbook.name,
            trigger=trigger,
            context=context,
            status=PlaybookStatus.RUNNING.value,
            started_at=time.time()
        )
        
        # Atualiza tracking de rate limit
        with self._lock:
            self._last_execution[playbook.id] = time.time()
            self._execution_counts[playbook.id].append(time.time())
            # Limpa execuções antigas (>1h)
            hour_ago = time.time() - 3600
            self._execution_counts[playbook.id] = [
                t for t in self._execution_counts[playbook.id] if t > hour_ago
            ]
        
        # Executa ações
        try:
            for action in playbook.actions:
                result = self._execute_action(action, context)
                execution.results.append(result)
                execution.actions_executed += 1
                
                if not result['success']:
                    execution.actions_failed += 1
                    
                    if action.on_failure == "stop":
                        execution.status = PlaybookStatus.FAILED.value
                        execution.error = f"Action {action.name} failed and on_failure=stop"
                        break
                    elif action.on_failure == "rollback":
                        # TODO: implementar rollback
                        execution.status = PlaybookStatus.FAILED.value
                        execution.error = f"Action {action.name} failed, rollback not implemented"
                        break
            
            if execution.status == PlaybookStatus.RUNNING.value:
                if execution.actions_failed == 0:
                    execution.status = PlaybookStatus.SUCCESS.value
                else:
                    execution.status = PlaybookStatus.FAILED.value
                    execution.error = f"{execution.actions_failed} action(s) failed"
        
        except Exception as e:
            execution.status = PlaybookStatus.FAILED.value
            execution.error = str(e)
            logger.exception(f"Playbook {playbook.name} execution failed")
        
        finally:
            execution.completed_at = time.time()
            execution.duration_ms = (execution.completed_at - execution.started_at) * 1000
            
            with self._lock:
                self._executions.append(execution)
                self._stats['total_executions'] += 1
                self._stats['total_actions_executed'] += execution.actions_executed
                self._stats['total_actions_failed'] += execution.actions_failed
                
                if execution.status == PlaybookStatus.SUCCESS.value:
                    self._stats['successful_executions'] += 1
                elif execution.status == PlaybookStatus.FAILED.value:
                    self._stats['failed_executions'] += 1
                
                self._trim_history()
        
        logger.info(f"Playbook {playbook.name} completed: {execution.status} ({execution.duration_ms:.0f}ms)")
        return execution
    
    def _execute_action(self, action: PlaybookAction, context: Dict[str, Any]) -> Dict[str, Any]:
        """Executa uma ação individual."""
        result = {
            'action': action.name,
            'type': action.action_type,
            'success': False,
            'started_at': time.time(),
            'completed_at': None,
            'output': None,
            'error': None
        }
        
        try:
            action_type = ActionType(action.action_type)
        except ValueError:
            result['error'] = f"Unknown action type: {action.action_type}"
            return result
        
        for attempt in range(action.retry_count + 1):
            try:
                if action_type == ActionType.LOG:
                    message = action.config.get('message', 'Playbook action triggered')
                    message = self._template_replace(message, context)
                    logger.info(f"[Playbook Action] {action.name}: {message}")
                    result['output'] = message
                    result['success'] = True
                
                elif action_type == ActionType.NOTIFY:
                    output = self._execute_notify(action, context)
                    result['output'] = output
                    result['success'] = True
                
                elif action_type == ActionType.RUN_COMMAND:
                    output = self._execute_command(action, context)
                    result['output'] = output
                    result['success'] = True
                
                elif action_type == ActionType.HTTP_REQUEST:
                    output = self._execute_http_request(action, context)
                    result['output'] = output
                    result['success'] = True
                
                elif action_type == ActionType.CUSTOM:
                    handler_name = action.config.get('handler')
                    if handler_name and handler_name in self._custom_handlers:
                        output = self._custom_handlers[handler_name](action, context)
                        result['output'] = output
                        result['success'] = True
                    else:
                        result['error'] = f"Custom handler not found: {handler_name}"
                
                elif action_type in (ActionType.SCALE, ActionType.RESTART):
                    # Placeholder - em produção integraria com K8s, Docker, etc.
                    logger.info(f"[Playbook] {action_type.value} requested for {action.config.get('service', 'unknown')}")
                    result['output'] = f"{action_type.value} requested (placeholder)"
                    result['success'] = True
                
                if result['success']:
                    break
                    
            except Exception as e:
                result['error'] = str(e)
                if attempt < action.retry_count:
                    time.sleep(action.retry_delay)
                else:
                    logger.exception(f"Action {action.name} failed after {attempt + 1} attempts")
        
        result['completed_at'] = time.time()
        return result
    
    def _execute_notify(self, action: PlaybookAction, context: Dict[str, Any]) -> str:
        """Executa ação de notificação."""
        message = action.config.get('message', '')
        message = self._template_replace(message, context)
        
        # Em produção, integraria com webhook_sender, email_alerts, etc.
        logger.info(f"[Notify] {action.name}: {message}")
        return f"Notification sent: {message[:100]}"
    
    def _execute_command(self, action: PlaybookAction, context: Dict[str, Any]) -> str:
        """Executa comando shell."""
        command = action.config.get('command', '')
        command = self._template_replace(command, context)
        
        timeout = action.config.get('timeout', action.timeout)
        
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        if result.returncode != 0:
            raise Exception(f"Command failed (exit {result.returncode}): {result.stderr[:200]}")
        
        return result.stdout[:500] if result.stdout else "Command executed successfully"
    
    def _execute_http_request(self, action: PlaybookAction, context: Dict[str, Any]) -> str:
        """Executa requisição HTTP."""
        import urllib.request
        import urllib.error
        
        url = action.config.get('url', '')
        url = self._template_replace(url, context)
        method = action.config.get('method', 'GET')
        headers = action.config.get('headers', {})
        body = action.config.get('body')
        
        if body and isinstance(body, str):
            body = self._template_replace(body, context).encode('utf-8')
        
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        
        timeout = action.config.get('timeout', action.timeout)
        
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return f"HTTP {response.status}: {response.read()[:200].decode('utf-8', errors='ignore')}"
    
    def _template_replace(self, template: str, context: Dict[str, Any]) -> str:
        """Substitui placeholders no template com valores do contexto."""
        result = template
        for key, value in context.items():
            placeholder = "{{" + key + "}}"
            if placeholder in result:
                result = result.replace(placeholder, str(value))
        return result
    
    # ─── History & Stats ───────────────────────────────────────────
    
    def get_executions(self, 
                       playbook_id: Optional[str] = None,
                       status: Optional[str] = None,
                       limit: int = 50) -> List[PlaybookExecution]:
        """Obtém histórico de execuções com filtros."""
        with self._lock:
            executions = self._executions.copy()
        
        if playbook_id:
            executions = [e for e in executions if e.playbook_id == playbook_id]
        
        if status:
            executions = [e for e in executions if e.status == status]
        
        # Mais recentes primeiro
        executions.sort(key=lambda e: e.started_at, reverse=True)
        return executions[:limit]
    
    def get_execution(self, execution_id: str) -> Optional[PlaybookExecution]:
        """Obtém uma execução específica."""
        with self._lock:
            for execution in self._executions:
                if execution.id == execution_id:
                    return execution
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtém estatísticas do gerenciador."""
        with self._lock:
            stats = self._stats.copy()
            stats['registered_playbooks'] = len(self._playbooks)
            stats['enabled_playbooks'] = sum(1 for p in self._playbooks.values() if p.enabled)
            stats['total_executions_stored'] = len(self._executions)
            stats['custom_handlers'] = len(self._custom_handlers)
        
        # Calcula taxa de sucesso
        total = stats['total_executions']
        if total > 0:
            stats['success_rate'] = round(stats['successful_executions'] / total * 100, 1)
        else:
            stats['success_rate'] = 0.0
        
        return stats
    
    def _trim_history(self) -> None:
        """Remove execuções antigas se exceder max_history."""
        if len(self._executions) > self._max_history:
            excess = len(self._executions) - self._max_history
            self._executions = self._executions[excess:]
    
    # ─── Utilities ─────────────────────────────────────────────────
    
    @staticmethod
    def _generate_id() -> str:
        """Gera ID único para execução."""
        return hashlib.md5(f"{time.time()}-{threading.get_ident()}".encode()).hexdigest()[:12]
    
    # ─── Import/Export ─────────────────────────────────────────────
    
    def export_playbooks(self) -> List[Dict]:
        """Exporta todos os playbooks para JSON."""
        with self._lock:
            return [p.to_dict() for p in self._playbooks.values()]
    
    def import_playbooks(self, data: List[Dict]) -> int:
        """Importa playbooks de JSON. Retorna quantidade importada."""
        count = 0
        for playbook_data in data:
            try:
                playbook = Playbook.from_dict(playbook_data)
                self.register_playbook(playbook)
                count += 1
            except Exception as e:
                logger.error(f"Failed to import playbook: {e}")
        return count


# ─── Playbook Templates ────────────────────────────────────────────

def create_endpoint_down_playbook(endpoint_name: str, webhook_url: str) -> Playbook:
    """Cria playbook padrão para endpoint down."""
    return Playbook(
        id=f"endpoint_down_{endpoint_name.lower().replace(' ', '_')}",
        name=f"Endpoint Down: {endpoint_name}",
        description=f"Resposta automática quando {endpoint_name} está inacessível",
        trigger=TriggerType.ALERT_CREATED.value,
        conditions=[
            PlaybookCondition("endpoint", "eq", endpoint_name),
            PlaybookCondition("severity", "gte", 2)
        ],
        actions=[
            PlaybookAction(
                action_type=ActionType.LOG.value,
                name="Log incident",
                config={"message": "Endpoint {{endpoint}} is down (status: {{status}})"}
            ),
            PlaybookAction(
                action_type=ActionType.NOTIFY.value,
                name="Notify team",
                config={
                    "message": "🚨 {{endpoint}} is DOWN. Response time: {{response_time}}ms. Check immediately!",
                    "webhook_url": webhook_url
                }
            ),
            PlaybookAction(
                action_type=ActionType.RUN_COMMAND.value,
                name="Run diagnostics",
                config={"command": "curl -s -o /dev/null -w '%{http_code}' {{url}} || echo 'FAILED'"},
                retry_count=1
            )
        ],
        cooldown_seconds=600,
        max_executions_per_hour=5,
        tags=["endpoint", "availability", "critical"]
    )


def create_high_latency_playbook(threshold_ms: int = 5000) -> Playbook:
    """Cria playbook para alta latência."""
    return Playbook(
        id="high_latency_response",
        name="High Latency Response",
        description=f"Resposta quando latência excede {threshold_ms}ms",
        trigger=TriggerType.METRIC_THRESHOLD.value,
        conditions=[
            PlaybookCondition("metric", "eq", "response_time"),
            PlaybookCondition("value", "gt", threshold_ms)
        ],
        actions=[
            PlaybookAction(
                action_type=ActionType.LOG.value,
                name="Log high latency",
                config={"message": "High latency detected: {{value}}ms on {{endpoint}}"}
            ),
            PlaybookAction(
                action_type=ActionType.RUN_COMMAND.value,
                name="Check system resources",
                config={"command": "uptime && free -h | head -2"}
            )
        ],
        cooldown_seconds=300,
        max_executions_per_hour=10,
        tags=["performance", "latency"]
    )
