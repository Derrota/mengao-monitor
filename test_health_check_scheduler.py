"""
Testes para Health Check Scheduler v3.12
"""

import unittest
import time
import threading
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from health_check_scheduler import (
    HealthCheckScheduler,
    CronExpression,
    Schedule,
    ScheduleType,
    ScheduleStatus,
    ScheduleResult,
    get_scheduler,
    reset_scheduler
)


class TestCronExpression(unittest.TestCase):
    """Testes para o parser de expressões cron."""
    
    def test_parse_every_minute(self):
        """Testa */1 * * * * (todo minuto)."""
        cron = CronExpression("* * * * *")
        now = datetime(2026, 3, 17, 10, 30, 0)
        self.assertTrue(cron.matches(now))
    
    def test_parse_every_5_minutes(self):
        """Testa */5 * * * * (a cada 5 minutos)."""
        cron = CronExpression("*/5 * * * *")
        
        # Deve bater em minutos 0, 5, 10, 15, etc.
        self.assertTrue(cron.matches(datetime(2026, 3, 17, 10, 0, 0)))
        self.assertTrue(cron.matches(datetime(2026, 3, 17, 10, 5, 0)))
        self.assertTrue(cron.matches(datetime(2026, 3, 17, 10, 10, 0)))
        self.assertTrue(cron.matches(datetime(2026, 3, 17, 10, 15, 0)))
        
        # Não deve bater em outros minutos
        self.assertFalse(cron.matches(datetime(2026, 3, 17, 10, 1, 0)))
        self.assertFalse(cron.matches(datetime(2026, 3, 17, 10, 7, 0)))
        self.assertFalse(cron.matches(datetime(2026, 3, 17, 10, 13, 0)))
    
    def test_parse_specific_hour(self):
        """Testa 0 9 * * * (todo dia às 9h)."""
        cron = CronExpression("0 9 * * *")
        
        self.assertTrue(cron.matches(datetime(2026, 3, 17, 9, 0, 0)))
        self.assertFalse(cron.matches(datetime(2026, 3, 17, 9, 30, 0)))
        self.assertFalse(cron.matches(datetime(2026, 3, 17, 10, 0, 0)))
    
    def test_parse_weekday_range(self):
        """Testa 0 9 * * 1-5 (seg-sex às 9h)."""
        cron = CronExpression("0 9 * * 1-5")
        
        # Segunda (weekday=0 em Python, 1 em cron)
        self.assertTrue(cron.matches(datetime(2026, 3, 16, 9, 0, 0)))  # Segunda
        self.assertTrue(cron.matches(datetime(2026, 3, 17, 9, 0, 0)))  # Terça
        self.assertTrue(cron.matches(datetime(2026, 3, 18, 9, 0, 0)))  # Quarta
        self.assertTrue(cron.matches(datetime(2026, 3, 19, 9, 0, 0)))  # Quinta
        self.assertTrue(cron.matches(datetime(2026, 3, 20, 9, 0, 0)))  # Sexta
        
        # Sábado (weekday=5 em Python, 6 em cron)
        self.assertFalse(cron.matches(datetime(2026, 3, 21, 9, 0, 0)))  # Sábado
        # Domingo (weekday=6 em Python, 0 em cron)
        self.assertFalse(cron.matches(datetime(2026, 3, 22, 9, 0, 0)))  # Domingo
    
    def test_parse_list(self):
        """Testa 0 9,12,18 * * * (9h, 12h, 18h)."""
        cron = CronExpression("0 9,12,18 * * *")
        
        self.assertTrue(cron.matches(datetime(2026, 3, 17, 9, 0, 0)))
        self.assertTrue(cron.matches(datetime(2026, 3, 17, 12, 0, 0)))
        self.assertTrue(cron.matches(datetime(2026, 3, 17, 18, 0, 0)))
        self.assertFalse(cron.matches(datetime(2026, 3, 17, 10, 0, 0)))
        self.assertFalse(cron.matches(datetime(2026, 3, 17, 15, 0, 0)))
    
    def test_parse_step_with_range(self):
        """Testa 0-30/10 * * * * (a cada 10 min nos primeiros 30 min)."""
        cron = CronExpression("0-30/10 * * * *")
        
        self.assertTrue(cron.matches(datetime(2026, 3, 17, 10, 0, 0)))
        self.assertTrue(cron.matches(datetime(2026, 3, 17, 10, 10, 0)))
        self.assertTrue(cron.matches(datetime(2026, 3, 17, 10, 20, 0)))
        self.assertTrue(cron.matches(datetime(2026, 3, 17, 10, 30, 0)))
        self.assertFalse(cron.matches(datetime(2026, 3, 17, 10, 5, 0)))
        self.assertFalse(cron.matches(datetime(2026, 3, 17, 10, 35, 0)))
    
    def test_parse_day_of_month(self):
        """Testa 0 0 1 * * (dia 1 de cada mês)."""
        cron = CronExpression("0 0 1 * *")
        
        self.assertTrue(cron.matches(datetime(2026, 3, 1, 0, 0, 0)))
        self.assertTrue(cron.matches(datetime(2026, 4, 1, 0, 0, 0)))
        self.assertFalse(cron.matches(datetime(2026, 3, 2, 0, 0, 0)))
        self.assertFalse(cron.matches(datetime(2026, 3, 15, 0, 0, 0)))
    
    def test_parse_invalid_expression(self):
        """Testa expressão inválida."""
        with self.assertRaises(ValueError):
            CronExpression("invalid")
        
        with self.assertRaises(ValueError):
            CronExpression("* * * *")  # Falta campo
        
        with self.assertRaises(ValueError):
            CronExpression("* * * * * *")  # Campo extra
    
    def test_next_occurrence(self):
        """Testa cálculo de próxima ocorrência."""
        cron = CronExpression("*/5 * * * *")
        
        after = datetime(2026, 3, 17, 10, 3, 0)
        next_occ = cron.next_occurrence(after)
        
        # Deve ser 10:05
        self.assertEqual(next_occ.minute, 5)
        self.assertEqual(next_occ.hour, 10)
        self.assertEqual(next_occ.second, 0)
    
    def test_next_occurrence_hourly(self):
        """Testa próxima ocorrência horária."""
        cron = CronExpression("0 */2 * * *")
        
        after = datetime(2026, 3, 17, 10, 30, 0)
        next_occ = cron.next_occurrence(after)
        
        # Deve ser 12:00
        self.assertEqual(next_occ.hour, 12)
        self.assertEqual(next_occ.minute, 0)


class TestHealthCheckScheduler(unittest.TestCase):
    """Testes para o Health Check Scheduler."""
    
    def setUp(self):
        """Setup para cada teste."""
        reset_scheduler()
        self.callback_results = []
        self.check_callback = Mock(return_value={"success": True, "status": "ok"})
        self.result_callback = Mock(side_effect=lambda r: self.callback_results.append(r))
        self.scheduler = HealthCheckScheduler(
            check_callback=self.check_callback,
            result_callback=self.result_callback
        )
    
    def tearDown(self):
        """Cleanup após cada teste."""
        self.scheduler.stop()
        reset_scheduler()
    
    def test_add_recurring_schedule(self):
        """Testa adição de agendamento recorrente."""
        schedule = self.scheduler.add_recurring_schedule(
            name="test_recurring",
            check_name="api_health",
            cron_expression="*/5 * * * *"
        )
        
        self.assertEqual(schedule.name, "test_recurring")
        self.assertEqual(schedule.check_name, "api_health")
        self.assertEqual(schedule.schedule_type, ScheduleType.RECURRING)
        self.assertEqual(schedule.cron_expression, "*/5 * * * *")
        self.assertTrue(schedule.enabled)
        self.assertEqual(schedule.status, ScheduleStatus.ACTIVE)
        self.assertIsNotNone(schedule.next_run)
    
    def test_add_one_shot_schedule(self):
        """Testa adição de agendamento one-shot."""
        run_at = datetime.now() + timedelta(hours=1)
        
        schedule = self.scheduler.add_one_shot_schedule(
            name="test_one_shot",
            check_name="backup_check",
            run_at=run_at
        )
        
        self.assertEqual(schedule.name, "test_one_shot")
        self.assertEqual(schedule.check_name, "backup_check")
        self.assertEqual(schedule.schedule_type, ScheduleType.ONE_SHOT)
        self.assertEqual(schedule.run_at, run_at)
        self.assertEqual(schedule.next_run, run_at)
    
    def test_add_duplicate_schedule(self):
        """Testa adição de agendamento duplicado."""
        self.scheduler.add_recurring_schedule(
            name="duplicate",
            check_name="test",
            cron_expression="* * * * *"
        )
        
        with self.assertRaises(ValueError):
            self.scheduler.add_recurring_schedule(
                name="duplicate",
                check_name="test2",
                cron_expression="*/5 * * * *"
            )
    
    def test_add_one_shot_in_past(self):
        """Testa one-shot com data no passado."""
        with self.assertRaises(ValueError):
            self.scheduler.add_one_shot_schedule(
                name="past",
                check_name="test",
                run_at=datetime.now() - timedelta(hours=1)
            )
    
    def test_remove_schedule(self):
        """Testa remoção de agendamento."""
        self.scheduler.add_recurring_schedule(
            name="to_remove",
            check_name="test",
            cron_expression="* * * * *"
        )
        
        result = self.scheduler.remove_schedule("to_remove")
        self.assertTrue(result)
        
        schedule = self.scheduler.get_schedule("to_remove")
        self.assertIsNone(schedule)
    
    def test_remove_nonexistent(self):
        """Testa remoção de agendamento inexistente."""
        result = self.scheduler.remove_schedule("nonexistent")
        self.assertFalse(result)
    
    def test_enable_disable_schedule(self):
        """Testa habilitar/desabilitar agendamento."""
        self.scheduler.add_recurring_schedule(
            name="toggle",
            check_name="test",
            cron_expression="* * * * *"
        )
        
        # Desabilitar
        result = self.scheduler.disable_schedule("toggle")
        self.assertTrue(result)
        
        schedule = self.scheduler.get_schedule("toggle")
        self.assertFalse(schedule.enabled)
        self.assertEqual(schedule.status, ScheduleStatus.PAUSED)
        
        # Habilitar
        result = self.scheduler.enable_schedule("toggle")
        self.assertTrue(result)
        
        schedule = self.scheduler.get_schedule("toggle")
        self.assertTrue(schedule.enabled)
        self.assertEqual(schedule.status, ScheduleStatus.ACTIVE)
    
    def test_list_schedules(self):
        """Testa listagem de agendamentos."""
        self.scheduler.add_recurring_schedule(
            name="sched1",
            check_name="test1",
            cron_expression="* * * * *"
        )
        self.scheduler.add_recurring_schedule(
            name="sched2",
            check_name="test2",
            cron_expression="*/5 * * * *"
        )
        self.scheduler.disable_schedule("sched2")
        
        # Listar todos
        all_schedules = self.scheduler.list_schedules()
        self.assertEqual(len(all_schedules), 2)
        
        # Filtrar por status
        active = self.scheduler.list_schedules(status_filter=ScheduleStatus.ACTIVE)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].name, "sched1")
        
        paused = self.scheduler.list_schedules(status_filter=ScheduleStatus.PAUSED)
        self.assertEqual(len(paused), 1)
        self.assertEqual(paused[0].name, "sched2")
        
        # Filtrar por check_name
        test1 = self.scheduler.list_schedules(check_name_filter="test1")
        self.assertEqual(len(test1), 1)
    
    def test_run_now(self):
        """Testa execução imediata."""
        self.scheduler.add_recurring_schedule(
            name="run_now",
            check_name="test_check",
            cron_expression="* * * * *"
        )
        
        result = self.scheduler.run_now("run_now")
        
        self.assertIsNotNone(result)
        self.assertEqual(result.schedule_name, "run_now")
        self.assertTrue(result.success)
        self.check_callback.assert_called_once_with("test_check")
    
    def test_run_now_nonexistent(self):
        """Testa execução imediata de agendamento inexistente."""
        result = self.scheduler.run_now("nonexistent")
        self.assertIsNone(result)
    
    def test_get_history(self):
        """Testa obtenção de histórico."""
        self.scheduler.add_recurring_schedule(
            name="hist_test",
            check_name="test",
            cron_expression="* * * * *"
        )
        
        # Executar algumas vezes
        self.scheduler.run_now("hist_test")
        self.scheduler.run_now("hist_test")
        
        history = self.scheduler.get_history()
        self.assertEqual(len(history), 2)
        self.assertTrue(all(r.schedule_name == "hist_test" for r in history))
    
    def test_get_history_with_filters(self):
        """Testa histórico com filtros."""
        self.scheduler.add_recurring_schedule(
            name="sched_a",
            check_name="test",
            cron_expression="* * * * *"
        )
        self.scheduler.add_recurring_schedule(
            name="sched_b",
            check_name="test",
            cron_expression="* * * * *"
        )
        
        self.scheduler.run_now("sched_a")
        self.scheduler.run_now("sched_b")
        
        # Filtrar por nome
        history_a = self.scheduler.get_history(schedule_name="sched_a")
        self.assertEqual(len(history_a), 1)
        self.assertEqual(history_a[0].schedule_name, "sched_a")
        
        # Filtrar por sucesso
        success_history = self.scheduler.get_history(success_only=True)
        self.assertEqual(len(success_history), 2)
    
    def test_get_stats(self):
        """Testa obtenção de estatísticas."""
        self.scheduler.add_recurring_schedule(
            name="stats_test",
            check_name="test",
            cron_expression="* * * * *"
        )
        
        self.scheduler.run_now("stats_test")
        
        stats = self.scheduler.get_stats()
        
        self.assertFalse(stats["running"])  # Não iniciado
        self.assertEqual(stats["total_schedules"], 1)
        self.assertEqual(stats["active_schedules"], 1)
        self.assertEqual(stats["total_runs"], 1)
        self.assertEqual(stats["successful_runs"], 1)
        self.assertEqual(stats["failed_runs"], 0)
        self.assertEqual(stats["success_rate"], 100.0)
    
    def test_worker_execution(self):
        """Testa execução pelo worker thread."""
        # Usar cron que executa no próximo minuto
        self.scheduler.add_recurring_schedule(
            name="worker_test",
            check_name="test",
            cron_expression="* * * * *"  # Todo minuto
        )
        
        # Iniciar scheduler
        self.scheduler.start()
        
        # Aguardar um pouco (máximo 70s para pegar próximo minuto)
        # Para teste, vamos forçar execução
        time.sleep(2)
        
        # Verificar se worker está rodando
        stats = self.scheduler.get_stats()
        self.assertTrue(stats["running"])
    
    def test_callback_called(self):
        """Testa se callback é chamado após execução."""
        self.scheduler.add_recurring_schedule(
            name="callback_test",
            check_name="test",
            cron_expression="* * * * *"
        )
        
        self.scheduler.run_now("callback_test")
        
        self.assertEqual(len(self.callback_results), 1)
        self.assertEqual(self.callback_results[0].schedule_name, "callback_test")
        self.assertTrue(self.callback_results[0].success)
    
    def test_schedule_to_dict(self):
        """Testa serialização de schedule para dict."""
        schedule = self.scheduler.add_recurring_schedule(
            name="dict_test",
            check_name="test",
            cron_expression="*/5 * * * *",
            metadata={"priority": "high"}
        )
        
        data = schedule.to_dict()
        
        self.assertEqual(data["name"], "dict_test")
        self.assertEqual(data["check_name"], "test")
        self.assertEqual(data["schedule_type"], "recurring")
        self.assertEqual(data["cron_expression"], "*/5 * * * *")
        self.assertEqual(data["metadata"]["priority"], "high")
    
    def test_failed_check(self):
        """Testa execução com falha."""
        self.check_callback.return_value = {
            "success": False,
            "error": "Connection timeout"
        }
        
        self.scheduler.add_recurring_schedule(
            name="fail_test",
            check_name="failing_check",
            cron_expression="* * * * *"
        )
        
        result = self.scheduler.run_now("fail_test")
        
        self.assertFalse(result.success)
        self.assertEqual(result.error, "Connection timeout")
        
        stats = self.scheduler.get_stats()
        self.assertEqual(stats["failed_runs"], 1)
    
    def test_callback_exception(self):
        """Testa exceção no callback."""
        bad_callback = Mock(side_effect=Exception("Callback error"))
        scheduler = HealthCheckScheduler(
            check_callback=self.check_callback,
            result_callback=bad_callback
        )
        
        scheduler.add_recurring_schedule(
            name="callback_error",
            check_name="test",
            cron_expression="* * * * *"
        )
        
        # Não deve levantar exceção
        result = scheduler.run_now("callback_error")
        self.assertTrue(result.success)


class TestSingleton(unittest.TestCase):
    """Testes para o padrão singleton."""
    
    def tearDown(self):
        reset_scheduler()
    
    def test_get_scheduler_singleton(self):
        """Testa que get_scheduler retorna mesma instância."""
        scheduler1 = get_scheduler()
        scheduler2 = get_scheduler()
        
        self.assertIs(scheduler1, scheduler2)
    
    def test_reset_scheduler(self):
        """Testa reset do singleton."""
        scheduler1 = get_scheduler()
        scheduler1.start()
        
        reset_scheduler()
        
        scheduler2 = get_scheduler()
        self.assertIsNot(scheduler1, scheduler2)


if __name__ == "__main__":
    unittest.main()
