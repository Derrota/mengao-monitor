"""
Health Check Scheduler v3.12 - Mengão Monitor 🦞

Agenda health checks em horários específicos usando expressões cron-like.
Útil para checks que não precisam rodar constantemente (backups, verificações diárias, etc).

Features:
- Cron-like expressions (min, hour, day, month, weekday)
- One-shot schedules (executa uma vez e remove)
- Recurring schedules (executa repetidamente)
- Callbacks para resultados
- Thread-safe com RLock
- Zero dependências externas
"""

import re
import time
import threading
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json

logger = logging.getLogger(__name__)


class ScheduleType(Enum):
    """Tipos de agendamento."""
    RECURRING = "recurring"  # Recorrente (cron-like)
    ONE_SHOT = "one_shot"    # Executa uma vez


class ScheduleStatus(Enum):
    """Status do agendamento."""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ScheduleResult:
    """Resultado de uma execução agendada."""
    schedule_name: str
    executed_at: datetime
    success: bool
    duration_ms: float
    result: Optional[Dict] = None
    error: Optional[str] = None
    next_run: Optional[datetime] = None


@dataclass
class Schedule:
    """Agendamento de health check."""
    name: str
    check_name: str  # Nome do health check a ser executado
    schedule_type: ScheduleType
    cron_expression: Optional[str] = None  # Para RECURRING
    run_at: Optional[datetime] = None      # Para ONE_SHOT
    enabled: bool = True
    status: ScheduleStatus = ScheduleStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.now)
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    last_result: Optional[ScheduleResult] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Converte para dicionário."""
        return {
            "name": self.name,
            "check_name": self.check_name,
            "schedule_type": self.schedule_type.value,
            "cron_expression": self.cron_expression,
            "run_at": self.run_at.isoformat() if self.run_at else None,
            "enabled": self.enabled,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "run_count": self.run_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "last_result": {
                "executed_at": self.last_result.executed_at.isoformat(),
                "success": self.last_result.success,
                "duration_ms": self.last_result.duration_ms,
                "error": self.last_result.error
            } if self.last_result else None,
            "metadata": self.metadata
        }


class CronExpression:
    """
    Parser e avaliador de expressões cron-like.
    
    Formato: min hour day month weekday
    - * = qualquer valor
    - , = lista (ex: 1,3,5)
    - - = range (ex: 1-5)
    - / = step (ex: */5)
    - Números específicos (ex: 0, 1, 2, etc.)
    
    Exemplos:
    - "*/5 * * * *" = a cada 5 minutos
    - "0 */2 * * *" = a cada 2 horas
    - "0 9 * * 1-5" = 9h da manhã, seg-sex
    - "30 14 * * *" = 14:30 todo dia
    - "0 0 1 * *" = meia-noite no dia 1 de cada mês
    """
    
    FIELDS = [
        ("minute", 0, 59),
        ("hour", 0, 23),
        ("day", 1, 31),
        ("month", 1, 12),
        ("weekday", 0, 6),  # 0=domingo, 6=sábado
    ]
    
    def __init__(self, expression: str):
        self.expression = expression.strip()
        self.parsed_fields = self._parse()
    
    def _parse_field(self, field_str: str, min_val: int, max_val: int) -> Set[int]:
        """Parse um campo da expressão cron."""
        values = set()
        
        # Tratar * como range completo
        if field_str == "*":
            field_str = f"{min_val}-{max_val}"
        
        # Split por vírgula
        parts = field_str.split(",")
        
        for part in parts:
            part = part.strip()
            
            # Step (ex: */5, 1-10/2)
            if "/" in part:
                range_part, step_part = part.split("/", 1)
                step = int(step_part)
                
                if range_part == "*":
                    range_start, range_end = min_val, max_val
                elif "-" in range_part:
                    range_start, range_end = map(int, range_part.split("-", 1))
                else:
                    range_start = range_end = int(range_part)
                
                for v in range(range_start, range_end + 1, step):
                    if min_val <= v <= max_val:
                        values.add(v)
            
            # Range (ex: 1-5)
            elif "-" in part:
                start, end = map(int, part.split("-", 1))
                for v in range(start, end + 1):
                    if min_val <= v <= max_val:
                        values.add(v)
            
            # Valor específico
            else:
                v = int(part)
                if min_val <= v <= max_val:
                    values.add(v)
        
        return values
    
    def _parse(self) -> List[Set[int]]:
        """Parse a expressão cron completa."""
        parts = self.expression.split()
        if len(parts) != 5:
            raise ValueError(f"Expressão cron inválida: {self.expression}. Formato: min hour day month weekday")
        
        parsed = []
        for i, (field_name, min_val, max_val) in enumerate(self.FIELDS):
            try:
                values = self._parse_field(parts[i], min_val, max_val)
                parsed.append(values)
            except Exception as e:
                raise ValueError(f"Erro ao parsear campo '{field_name}' ({parts[i]}): {e}")
        
        return parsed
    
    def matches(self, dt: datetime) -> bool:
        """Verifica se um datetime corresponde à expressão."""
        minute, hour, day, month, weekday = self.parsed_fields
        
        # Ajustar weekday: Python usa 0=segunda, cron usa 0=domingo
        cron_weekday = (dt.weekday() + 1) % 7
        
        return (
            dt.minute in minute and
            dt.hour in hour and
            dt.day in day and
            dt.month in month and
            cron_weekday in weekday
        )
    
    def next_occurrence(self, after: datetime) -> datetime:
        """Calcula a próxima ocorrência após um datetime."""
        # Começa do próximo minuto
        current = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        
        # Limite de busca: 2 anos
        limit = after + timedelta(days=730)
        
        while current <= limit:
            if self.matches(current):
                return current
            current += timedelta(minutes=1)
        
        raise ValueError(f"Não foi possível encontrar próxima ocorrência para: {self.expression}")


class HealthCheckScheduler:
    """
    Scheduler de health checks com suporte a cron-like expressions.
    
    Features:
    - Agendamentos recorrentes (cron-like)
    - Agendamentos one-shot (executa uma vez)
    - Callbacks para resultados
    - Thread-safe
    - Histórico de execuções
    """
    
    def __init__(self, check_callback: Optional[Callable] = None, 
                 result_callback: Optional[Callable] = None):
        """
        Args:
            check_callback: Função para executar health check. 
                           Deve receber (check_name) e retornar dict com resultado.
            result_callback: Função chamada após cada execução.
                           Deve receber (ScheduleResult).
        """
        self._schedules: Dict[str, Schedule] = {}
        self._lock = threading.RLock()
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False
        self._check_interval = 30  # Verifica a cada 30 segundos
        self._check_callback = check_callback
        self._result_callback = result_callback
        self._history: List[ScheduleResult] = []
        self._max_history = 1000
        self._stats = {
            "total_runs": 0,
            "successful_runs": 0,
            "failed_runs": 0,
            "schedules_created": 0,
            "schedules_removed": 0,
        }
    
    def start(self) -> None:
        """Inicia o scheduler."""
        with self._lock:
            if self._running:
                return
            
            self._running = True
            self._worker_thread = threading.Thread(
                target=self._worker_loop,
                daemon=True,
                name="HealthCheckScheduler"
            )
            self._worker_thread.start()
            logger.info("Health Check Scheduler iniciado")
    
    def stop(self) -> None:
        """Para o scheduler."""
        with self._lock:
            if not self._running:
                return
            
            self._running = False
            if self._worker_thread:
                self._worker_thread.join(timeout=5)
            logger.info("Health Check Scheduler parado")
    
    def _worker_loop(self) -> None:
        """Loop principal do worker."""
        while self._running:
            try:
                self._check_and_execute()
            except Exception as e:
                logger.error(f"Erro no worker loop: {e}")
            
            # Sleep com verificação de running
            for _ in range(self._check_interval):
                if not self._running:
                    break
                time.sleep(1)
    
    def _check_and_execute(self) -> None:
        """Verifica e executa agendamentos pendentes."""
        now = datetime.now()
        
        with self._lock:
            schedules_to_run = []
            schedules_to_remove = []
            
            for name, schedule in self._schedules.items():
                if not schedule.enabled or schedule.status != ScheduleStatus.ACTIVE:
                    continue
                
                # Verificar se é hora de executar
                should_run = False
                
                if schedule.schedule_type == ScheduleType.ONE_SHOT:
                    if schedule.run_at and now >= schedule.run_at:
                        should_run = True
                        schedules_to_remove.append(name)
                elif schedule.schedule_type == ScheduleType.RECURRING:
                    if schedule.next_run and now >= schedule.next_run:
                        should_run = True
                
                if should_run:
                    schedules_to_run.append(schedule)
            
            # Remover one-shots
            for name in schedules_to_remove:
                self._schedules[name].status = ScheduleStatus.COMPLETED
        
        # Executar fora do lock
        for schedule in schedules_to_run:
            self._execute_schedule(schedule)
    
    def _execute_schedule(self, schedule: Schedule) -> None:
        """Executa um agendamento."""
        start_time = time.time()
        result = None
        
        try:
            if self._check_callback:
                check_result = self._check_callback(schedule.check_name)
                success = check_result.get("success", True)
                error = check_result.get("error")
            else:
                # Mock para testes
                check_result = {"status": "ok", "message": "Mock check"}
                success = True
                error = None
            
            duration_ms = (time.time() - start_time) * 1000
            
            result = ScheduleResult(
                schedule_name=schedule.name,
                executed_at=datetime.now(),
                success=success,
                duration_ms=duration_ms,
                result=check_result,
                error=error
            )
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            result = ScheduleResult(
                schedule_name=schedule.name,
                executed_at=datetime.now(),
                success=False,
                duration_ms=duration_ms,
                error=str(e)
            )
        
        # Atualizar schedule
        with self._lock:
            schedule.last_run = result.executed_at
            schedule.last_result = result
            schedule.run_count += 1
            
            if result.success:
                schedule.success_count += 1
                self._stats["successful_runs"] += 1
            else:
                schedule.failure_count += 1
                self._stats["failed_runs"] += 1
            
            self._stats["total_runs"] += 1
            
            # Calcular próxima execução para recorrentes
            if schedule.schedule_type == ScheduleType.RECURRING and schedule.cron_expression:
                try:
                    cron = CronExpression(schedule.cron_expression)
                    schedule.next_run = cron.next_occurrence(result.executed_at)
                    result.next_run = schedule.next_run
                except Exception as e:
                    logger.error(f"Erro ao calcular próxima execução: {e}")
                    schedule.status = ScheduleStatus.FAILED
            
            # Adicionar ao histórico
            self._history.append(result)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]
        
        # Callback
        if self._result_callback:
            try:
                self._result_callback(result)
            except Exception as e:
                logger.error(f"Erro no result callback: {e}")
        
        logger.info(f"Schedule '{schedule.name}' executado: success={result.success}, duration={result.duration_ms:.1f}ms")
    
    def add_recurring_schedule(self, name: str, check_name: str, cron_expression: str,
                              enabled: bool = True, metadata: Optional[Dict] = None) -> Schedule:
        """
        Adiciona um agendamento recorrente.
        
        Args:
            name: Nome único do agendamento
            check_name: Nome do health check a executar
            cron_expression: Expressão cron (min hour day month weekday)
            enabled: Se o agendamento está ativo
            metadata: Metadados adicionais
        
        Returns:
            Schedule criado
        """
        with self._lock:
            if name in self._schedules:
                raise ValueError(f"Agendamento '{name}' já existe")
            
            # Validar expressão cron
            cron = CronExpression(cron_expression)
            
            # Calcular próxima execução
            next_run = cron.next_occurrence(datetime.now())
            
            schedule = Schedule(
                name=name,
                check_name=check_name,
                schedule_type=ScheduleType.RECURRING,
                cron_expression=cron_expression,
                enabled=enabled,
                next_run=next_run,
                metadata=metadata or {}
            )
            
            self._schedules[name] = schedule
            self._stats["schedules_created"] += 1
            
            logger.info(f"Agendamento recorrente '{name}' criado: {cron_expression}, próxima={next_run}")
            return schedule
    
    def add_one_shot_schedule(self, name: str, check_name: str, run_at: datetime,
                             metadata: Optional[Dict] = None) -> Schedule:
        """
        Adiciona um agendamento one-shot (executa uma vez).
        
        Args:
            name: Nome único do agendamento
            check_name: Nome do health check a executar
            run_at: Quando executar
            metadata: Metadados adicionais
        
        Returns:
            Schedule criado
        """
        with self._lock:
            if name in self._schedules:
                raise ValueError(f"Agendamento '{name}' já existe")
            
            if run_at <= datetime.now():
                raise ValueError("run_at deve ser no futuro")
            
            schedule = Schedule(
                name=name,
                check_name=check_name,
                schedule_type=ScheduleType.ONE_SHOT,
                run_at=run_at,
                next_run=run_at,
                metadata=metadata or {}
            )
            
            self._schedules[name] = schedule
            self._stats["schedules_created"] += 1
            
            logger.info(f"Agendamento one-shot '{name}' criado: run_at={run_at}")
            return schedule
    
    def remove_schedule(self, name: str) -> bool:
        """Remove um agendamento."""
        with self._lock:
            if name not in self._schedules:
                return False
            
            del self._schedules[name]
            self._stats["schedules_removed"] += 1
            logger.info(f"Agendamento '{name}' removido")
            return True
    
    def enable_schedule(self, name: str) -> bool:
        """Habilita um agendamento."""
        with self._lock:
            if name not in self._schedules:
                return False
            
            self._schedules[name].enabled = True
            self._schedules[name].status = ScheduleStatus.ACTIVE
            
            # Recalcular próxima execução se for recorrente
            schedule = self._schedules[name]
            if schedule.schedule_type == ScheduleType.RECURRING and schedule.cron_expression:
                cron = CronExpression(schedule.cron_expression)
                schedule.next_run = cron.next_occurrence(datetime.now())
            
            return True
    
    def disable_schedule(self, name: str) -> bool:
        """Desabilita um agendamento."""
        with self._lock:
            if name not in self._schedules:
                return False
            
            self._schedules[name].enabled = False
            self._schedules[name].status = ScheduleStatus.PAUSED
            return True
    
    def get_schedule(self, name: str) -> Optional[Schedule]:
        """Obtém um agendamento pelo nome."""
        with self._lock:
            return self._schedules.get(name)
    
    def list_schedules(self, status_filter: Optional[ScheduleStatus] = None,
                      check_name_filter: Optional[str] = None) -> List[Schedule]:
        """Lista agendamentos com filtros opcionais."""
        with self._lock:
            schedules = list(self._schedules.values())
            
            if status_filter:
                schedules = [s for s in schedules if s.status == status_filter]
            
            if check_name_filter:
                schedules = [s for s in schedules if s.check_name == check_name_filter]
            
            return schedules
    
    def get_history(self, limit: int = 50, schedule_name: Optional[str] = None,
                   success_only: bool = False) -> List[ScheduleResult]:
        """Obtém histórico de execuções."""
        with self._lock:
            history = self._history[:]
            
            if schedule_name:
                history = [r for r in history if r.schedule_name == schedule_name]
            
            if success_only:
                history = [r for r in history if r.success]
            
            return history[-limit:]
    
    def get_stats(self) -> Dict:
        """Obtém estatísticas do scheduler."""
        with self._lock:
            active_count = sum(1 for s in self._schedules.values() if s.status == ScheduleStatus.ACTIVE)
            paused_count = sum(1 for s in self._schedules.values() if s.status == ScheduleStatus.PAUSED)
            
            return {
                "running": self._running,
                "total_schedules": len(self._schedules),
                "active_schedules": active_count,
                "paused_schedules": paused_count,
                "total_runs": self._stats["total_runs"],
                "successful_runs": self._stats["successful_runs"],
                "failed_runs": self._stats["failed_runs"],
                "schedules_created": self._stats["schedules_created"],
                "schedules_removed": self._stats["schedules_removed"],
                "history_size": len(self._history),
                "success_rate": (
                    self._stats["successful_runs"] / max(self._stats["total_runs"], 1) * 100
                )
            }
    
    def run_now(self, name: str) -> Optional[ScheduleResult]:
        """Executa um agendamento imediatamente."""
        with self._lock:
            schedule = self._schedules.get(name)
            if not schedule:
                return None
        
        # Executar fora do lock
        self._execute_schedule(schedule)
        return schedule.last_result


# Singleton
_scheduler_instance: Optional[HealthCheckScheduler] = None
_scheduler_lock = threading.Lock()


def get_scheduler(check_callback: Optional[Callable] = None,
                 result_callback: Optional[Callable] = None) -> HealthCheckScheduler:
    """Obtém instância singleton do scheduler."""
    global _scheduler_instance
    
    with _scheduler_lock:
        if _scheduler_instance is None:
            _scheduler_instance = HealthCheckScheduler(
                check_callback=check_callback,
                result_callback=result_callback
            )
        return _scheduler_instance


def reset_scheduler() -> None:
    """Reseta instância singleton (para testes)."""
    global _scheduler_instance
    
    with _scheduler_lock:
        if _scheduler_instance:
            _scheduler_instance.stop()
        _scheduler_instance = None
