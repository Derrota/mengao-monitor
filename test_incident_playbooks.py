"""
🦞 Testes para Incident Playbooks v3.11

Cobertura:
- Playbook CRUD
- Condições e triggers
- Rate limiting e cooldown
- Execução de ações (LOG, NOTIFY, RUN_COMMAND, HTTP_REQUEST)
- Custom handlers
- Histórico e estatísticas
- Import/Export
- Templates
"""

import unittest
import time
import threading
from unittest.mock import patch, MagicMock

from incident_playbooks import (
    ActionType,
    TriggerType,
    PlaybookStatus,
    PlaybookAction,
    PlaybookCondition,
    Playbook,
    PlaybookExecution,
    IncidentPlaybookManager,
    create_endpoint_down_playbook,
    create_high_latency_playbook,
)


class TestPlaybookCondition(unittest.TestCase):
    """Testes para PlaybookCondition."""
    
    def test_eq_operator(self):
        cond = PlaybookCondition("severity", "eq", 3)
        self.assertTrue(cond.evaluate({"severity": 3}))
        self.assertFalse(cond.evaluate({"severity": 2}))
    
    def test_ne_operator(self):
        cond = PlaybookCondition("status", "ne", "ok")
        self.assertTrue(cond.evaluate({"status": "error"}))
        self.assertFalse(cond.evaluate({"status": "ok"}))
    
    def test_gt_operator(self):
        cond = PlaybookCondition("response_time", "gt", 1000)
        self.assertTrue(cond.evaluate({"response_time": 2000}))
        self.assertFalse(cond.evaluate({"response_time": 500}))
    
    def test_lt_operator(self):
        cond = PlaybookCondition("uptime", "lt", 99.0)
        self.assertTrue(cond.evaluate({"uptime": 98.5}))
        self.assertFalse(cond.evaluate({"uptime": 99.5}))
    
    def test_gte_lte_operators(self):
        cond_gte = PlaybookCondition("value", "gte", 10)
        self.assertTrue(cond_gte.evaluate({"value": 10}))
        self.assertTrue(cond_gte.evaluate({"value": 11}))
        self.assertFalse(cond_gte.evaluate({"value": 9}))
        
        cond_lte = PlaybookCondition("value", "lte", 10)
        self.assertTrue(cond_lte.evaluate({"value": 10}))
        self.assertTrue(cond_lte.evaluate({"value": 9}))
        self.assertFalse(cond_lte.evaluate({"value": 11}))
    
    def test_contains_operator(self):
        cond = PlaybookCondition("message", "contains", "timeout")
        self.assertTrue(cond.evaluate({"message": "Connection timeout occurred"}))
        self.assertFalse(cond.evaluate({"message": "Connection successful"}))
    
    def test_regex_operator(self):
        cond = PlaybookCondition("endpoint", "regex", r"^https://.*")
        self.assertTrue(cond.evaluate({"endpoint": "https://api.example.com"}))
        self.assertFalse(cond.evaluate({"endpoint": "http://api.example.com"}))
    
    def test_missing_field(self):
        cond = PlaybookCondition("severity", "eq", 3)
        self.assertFalse(cond.evaluate({"other_field": 3}))
    
    def test_invalid_comparison(self):
        cond = PlaybookCondition("value", "gt", "not_a_number")
        self.assertFalse(cond.evaluate({"value": 100}))


class TestPlaybookAction(unittest.TestCase):
    """Testes para PlaybookAction."""
    
    def test_to_dict(self):
        action = PlaybookAction(
            action_type="log",
            name="Test Action",
            config={"message": "test"},
            timeout=60
        )
        data = action.to_dict()
        self.assertEqual(data['action_type'], "log")
        self.assertEqual(data['name'], "Test Action")
        self.assertEqual(data['timeout'], 60)
    
    def test_from_dict(self):
        data = {
            "action_type": "notify",
            "name": "Notify Team",
            "config": {"webhook": "https://example.com"},
            "timeout": 30,
            "retry_count": 2
        }
        action = PlaybookAction.from_dict(data)
        self.assertEqual(action.action_type, "notify")
        self.assertEqual(action.retry_count, 2)


class TestPlaybook(unittest.TestCase):
    """Testes para Playbook."""
    
    def test_to_dict(self):
        playbook = Playbook(
            id="test_pb",
            name="Test Playbook",
            description="A test",
            trigger="alert_created",
            conditions=[
                PlaybookCondition("severity", "gte", 2)
            ],
            actions=[
                PlaybookAction(action_type="log", name="Log it")
            ]
        )
        data = playbook.to_dict()
        self.assertEqual(data['id'], "test_pb")
        self.assertEqual(len(data['conditions']), 1)
        self.assertEqual(len(data['actions']), 1)
    
    def test_from_dict(self):
        data = {
            "id": "imported_pb",
            "name": "Imported",
            "description": "Imported playbook",
            "trigger": "metric_threshold",
            "conditions": [{"field": "value", "operator": "gt", "value": 100}],
            "actions": [{"action_type": "log", "name": "Log", "config": {}}],
            "enabled": True,
            "priority": 50
        }
        playbook = Playbook.from_dict(data)
        self.assertEqual(playbook.id, "imported_pb")
        self.assertEqual(len(playbook.conditions), 1)
        self.assertEqual(playbook.priority, 50)


class TestIncidentPlaybookManager(unittest.TestCase):
    """Testes para IncidentPlaybookManager."""
    
    def setUp(self):
        self.manager = IncidentPlaybookManager(max_history=100)
    
    def test_register_playbook(self):
        playbook = Playbook(
            id="test_1",
            name="Test",
            description="Test",
            trigger="alert_created"
        )
        result = self.manager.register_playbook(playbook)
        self.assertTrue(result)
        self.assertIsNotNone(self.manager.get_playbook("test_1"))
    
    def test_unregister_playbook(self):
        playbook = Playbook(id="test_2", name="Test", description="Test", trigger="manual")
        self.manager.register_playbook(playbook)
        
        result = self.manager.unregister_playbook("test_2")
        self.assertTrue(result)
        self.assertIsNone(self.manager.get_playbook("test_2"))
    
    def test_unregister_nonexistent(self):
        result = self.manager.unregister_playbook("nonexistent")
        self.assertFalse(result)
    
    def test_list_playbooks(self):
        pb1 = Playbook(id="pb1", name="A", description="", trigger="manual", priority=200)
        pb2 = Playbook(id="pb2", name="B", description="", trigger="manual", priority=50)
        pb3 = Playbook(id="pb3", name="C", description="", trigger="manual", enabled=False)
        
        self.manager.register_playbook(pb1)
        self.manager.register_playbook(pb2)
        self.manager.register_playbook(pb3)
        
        all_playbooks = self.manager.list_playbooks()
        self.assertEqual(len(all_playbooks), 3)
        
        enabled_only = self.manager.list_playbooks(enabled_only=True)
        self.assertEqual(len(enabled_only), 2)
        
        # Verifica ordenação por prioridade
        self.assertEqual(enabled_only[0].id, "pb2")  # priority 50
    
    def test_enable_disable(self):
        playbook = Playbook(id="toggle", name="Toggle", description="", trigger="manual")
        self.manager.register_playbook(playbook)
        
        self.manager.disable_playbook("toggle")
        self.assertFalse(self.manager.get_playbook("toggle").enabled)
        
        self.manager.enable_playbook("toggle")
        self.assertTrue(self.manager.get_playbook("toggle").enabled)
    
    def test_trigger_matching(self):
        playbook = Playbook(
            id="match_test",
            name="Match Test",
            description="",
            trigger="alert_created",
            conditions=[
                PlaybookCondition("severity", "gte", 3)
            ],
            actions=[
                PlaybookAction(action_type="log", name="Log", config={"message": "matched"})
            ]
        )
        self.manager.register_playbook(playbook)
        
        # Contexto que não corresponde
        executions = self.manager.trigger("alert_created", {"severity": 1, "endpoint": "test"})
        self.assertEqual(len(executions), 0)
        
        # Contexto que corresponde
        executions = self.manager.trigger("alert_created", {"severity": 3, "endpoint": "test"})
        self.assertEqual(len(executions), 1)
        self.assertEqual(executions[0].status, "success")
    
    def test_trigger_wrong_type(self):
        playbook = Playbook(
            id="type_test",
            name="Type Test",
            description="",
            trigger="alert_created",
            actions=[PlaybookAction(action_type="log", name="Log")]
        )
        self.manager.register_playbook(playbook)
        
        executions = self.manager.trigger("manual", {})
        self.assertEqual(len(executions), 0)
    
    def test_log_action(self):
        playbook = Playbook(
            id="log_test",
            name="Log Test",
            description="",
            trigger="manual",
            actions=[
                PlaybookAction(
                    action_type="log",
                    name="Test Log",
                    config={"message": "Hello {{name}}"}
                )
            ]
        )
        self.manager.register_playbook(playbook)
        
        executions = self.manager.trigger("manual", {"name": "Flamengo"})
        self.assertEqual(len(executions), 1)
        self.assertEqual(executions[0].status, "success")
        self.assertEqual(executions[0].actions_executed, 1)
        self.assertIn("Hello Flamengo", executions[0].results[0]['output'])
    
    def test_command_action(self):
        playbook = Playbook(
            id="cmd_test",
            name="Command Test",
            description="",
            trigger="manual",
            actions=[
                PlaybookAction(
                    action_type="run_command",
                    name="Echo Test",
                    config={"command": "echo 'Mengao'"}
                )
            ]
        )
        self.manager.register_playbook(playbook)
        
        executions = self.manager.trigger("manual", {})
        self.assertEqual(len(executions), 1)
        self.assertEqual(executions[0].status, "success")
        self.assertIn("Mengao", executions[0].results[0]['output'])
    
    def test_command_action_failure(self):
        playbook = Playbook(
            id="cmd_fail",
            name="Command Fail",
            description="",
            trigger="manual",
            actions=[
                PlaybookAction(
                    action_type="run_command",
                    name="Failing Command",
                    config={"command": "exit 1"},
                    on_failure="continue"
                ),
                PlaybookAction(
                    action_type="log",
                    name="Still Runs",
                    config={"message": "continued after failure"}
                )
            ]
        )
        self.manager.register_playbook(playbook)
        
        executions = self.manager.trigger("manual", {})
        self.assertEqual(len(executions), 1)
        self.assertEqual(executions[0].status, "failed")
        self.assertEqual(executions[0].actions_executed, 2)
        self.assertEqual(executions[0].actions_failed, 1)
    
    def test_command_action_stop_on_failure(self):
        playbook = Playbook(
            id="cmd_stop",
            name="Stop on Fail",
            description="",
            trigger="manual",
            actions=[
                PlaybookAction(
                    action_type="run_command",
                    name="Failing Command",
                    config={"command": "exit 1"},
                    on_failure="stop"
                ),
                PlaybookAction(
                    action_type="log",
                    name="Should Not Run",
                    config={"message": "should not see this"}
                )
            ]
        )
        self.manager.register_playbook(playbook)
        
        executions = self.manager.trigger("manual", {})
        self.assertEqual(len(executions), 1)
        self.assertEqual(executions[0].status, "failed")
        self.assertEqual(executions[0].actions_executed, 1)  # Second action didn't run
    
    def test_custom_handler(self):
        def my_handler(action, context):
            return f"Custom: {context.get('value', 'none')}"
        
        self.manager.register_handler("my_handler", my_handler)
        
        playbook = Playbook(
            id="custom_test",
            name="Custom Test",
            description="",
            trigger="manual",
            actions=[
                PlaybookAction(
                    action_type="custom",
                    name="Custom Action",
                    config={"handler": "my_handler"}
                )
            ]
        )
        self.manager.register_playbook(playbook)
        
        executions = self.manager.trigger("manual", {"value": "test123"})
        self.assertEqual(len(executions), 1)
        self.assertEqual(executions[0].status, "success")
        self.assertIn("Custom: test123", executions[0].results[0]['output'])
    
    def test_custom_handler_not_found(self):
        playbook = Playbook(
            id="missing_handler",
            name="Missing Handler",
            description="",
            trigger="manual",
            actions=[
                PlaybookAction(
                    action_type="custom",
                    name="Missing",
                    config={"handler": "nonexistent"}
                )
            ]
        )
        self.manager.register_playbook(playbook)
        
        executions = self.manager.trigger("manual", {})
        self.assertEqual(len(executions), 1)
        self.assertEqual(executions[0].status, "failed")
    
    def test_rate_limiting_cooldown(self):
        playbook = Playbook(
            id="cooldown_test",
            name="Cooldown Test",
            description="",
            trigger="manual",
            cooldown_seconds=3600,  # 1 hour
            actions=[PlaybookAction(action_type="log", name="Log")]
        )
        self.manager.register_playbook(playbook)
        
        # Primeira execução deve funcionar
        executions = self.manager.trigger("manual", {})
        self.assertEqual(len(executions), 1)
        self.assertEqual(executions[0].status, "success")
        
        # Segunda execução deve ser rate limited
        executions = self.manager.trigger("manual", {})
        self.assertEqual(len(executions), 1)
        self.assertEqual(executions[0].status, "rate_limited")
    
    def test_rate_limiting_max_per_hour(self):
        playbook = Playbook(
            id="max_hour_test",
            name="Max Per Hour",
            description="",
            trigger="manual",
            cooldown_seconds=0,
            max_executions_per_hour=2,
            actions=[PlaybookAction(action_type="log", name="Log")]
        )
        self.manager.register_playbook(playbook)
        
        # Primeiras 2 execuções devem funcionar
        self.manager.trigger("manual", {})
        self.manager.trigger("manual", {})
        
        # Terceira deve ser rate limited
        executions = self.manager.trigger("manual", {})
        self.assertEqual(executions[0].status, "rate_limited")
    
    def test_multiple_playbooks_triggered(self):
        pb1 = Playbook(
            id="multi_1",
            name="First",
            description="",
            trigger="alert_created",
            priority=200,
            actions=[PlaybookAction(action_type="log", name="Log 1")]
        )
        pb2 = Playbook(
            id="multi_2",
            name="Second",
            description="",
            trigger="alert_created",
            priority=100,
            actions=[PlaybookAction(action_type="log", name="Log 2")]
        )
        
        self.manager.register_playbook(pb1)
        self.manager.register_playbook(pb2)
        
        executions = self.manager.trigger("alert_created", {"severity": 1})
        self.assertEqual(len(executions), 2)
        
        # Deve executar na ordem de prioridade (100 antes de 200)
        self.assertEqual(executions[0].playbook_id, "multi_2")
        self.assertEqual(executions[1].playbook_id, "multi_1")
    
    def test_get_executions(self):
        playbook = Playbook(
            id="history_test",
            name="History",
            description="",
            trigger="manual",
            cooldown_seconds=0,
            actions=[PlaybookAction(action_type="log", name="Log")]
        )
        self.manager.register_playbook(playbook)
        
        # Gera algumas execuções
        for i in range(5):
            self.manager.trigger("manual", {"i": i})
            time.sleep(0.01)  # Pequena pausa para garantir timestamps diferentes
        
        # Busca todas
        all_executions = self.manager.get_executions()
        self.assertEqual(len(all_executions), 5)
        
        # Busca por playbook
        pb_executions = self.manager.get_executions(playbook_id="history_test")
        self.assertEqual(len(pb_executions), 5)
        
        # Busca por status
        success_executions = self.manager.get_executions(status="success")
        self.assertEqual(len(success_executions), 5)
        
        # Com limite
        limited = self.manager.get_executions(limit=3)
        self.assertEqual(len(limited), 3)
    
    def test_get_execution_by_id(self):
        playbook = Playbook(
            id="by_id_test",
            name="By ID",
            description="",
            trigger="manual",
            actions=[PlaybookAction(action_type="log", name="Log")]
        )
        self.manager.register_playbook(playbook)
        
        executions = self.manager.trigger("manual", {})
        exec_id = executions[0].id
        
        found = self.manager.get_execution(exec_id)
        self.assertIsNotNone(found)
        self.assertEqual(found.id, exec_id)
        
        not_found = self.manager.get_execution("nonexistent")
        self.assertIsNone(not_found)
    
    def test_stats(self):
        playbook = Playbook(
            id="stats_test",
            name="Stats",
            description="",
            trigger="manual",
            cooldown_seconds=0,
            actions=[PlaybookAction(action_type="log", name="Log")]
        )
        self.manager.register_playbook(playbook)
        
        # Algumas execuções
        self.manager.trigger("manual", {})
        self.manager.trigger("manual", {})
        
        stats = self.manager.get_stats()
        self.assertEqual(stats['registered_playbooks'], 1)
        self.assertEqual(stats['enabled_playbooks'], 1)
        self.assertEqual(stats['total_executions'], 2)
        self.assertEqual(stats['successful_executions'], 2)
        self.assertEqual(stats['success_rate'], 100.0)
    
    def test_export_import(self):
        pb1 = Playbook(
            id="export_1",
            name="Export 1",
            description="",
            trigger="manual",
            conditions=[PlaybookCondition("x", "eq", 1)],
            actions=[PlaybookAction(action_type="log", name="Log")]
        )
        pb2 = Playbook(
            id="export_2",
            name="Export 2",
            description="",
            trigger="manual",
            actions=[PlaybookAction(action_type="log", name="Log")]
        )
        
        self.manager.register_playbook(pb1)
        self.manager.register_playbook(pb2)
        
        # Exporta
        exported = self.manager.export_playbooks()
        self.assertEqual(len(exported), 2)
        
        # Novo manager importa
        new_manager = IncidentPlaybookManager()
        count = new_manager.import_playbooks(exported)
        self.assertEqual(count, 2)
        
        # Verifica
        self.assertIsNotNone(new_manager.get_playbook("export_1"))
        self.assertIsNotNone(new_manager.get_playbook("export_2"))
    
    def test_max_history(self):
        manager = IncidentPlaybookManager(max_history=5)
        playbook = Playbook(
            id="trim_test",
            name="Trim",
            description="",
            trigger="manual",
            cooldown_seconds=0,
            actions=[PlaybookAction(action_type="log", name="Log")]
        )
        manager.register_playbook(playbook)
        
        # Gera mais execuções que o limite
        for i in range(10):
            manager.trigger("manual", {"i": i})
        
        # Deve ter apenas 5 (max_history)
        executions = manager.get_executions(limit=100)
        self.assertEqual(len(executions), 5)
    
    def test_thread_safety(self):
        playbook = Playbook(
            id="thread_test",
            name="Thread Test",
            description="",
            trigger="manual",
            cooldown_seconds=0,
            max_executions_per_hour=100,  # Limite alto para teste
            actions=[PlaybookAction(action_type="log", name="Log")]
        )
        self.manager.register_playbook(playbook)
        
        errors = []
        
        def trigger_many():
            try:
                for _ in range(20):
                    self.manager.trigger("manual", {})
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=trigger_many) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        self.assertEqual(len(errors), 0)
        
        stats = self.manager.get_stats()
        self.assertEqual(stats['total_executions'], 80)


class TestTemplates(unittest.TestCase):
    """Testes para templates de playbook."""
    
    def test_endpoint_down_playbook(self):
        playbook = create_endpoint_down_playbook("Minha API", "https://webhook.example.com")
        
        self.assertEqual(playbook.trigger, "alert_created")
        self.assertEqual(len(playbook.conditions), 2)
        self.assertEqual(len(playbook.actions), 3)
        self.assertIn("endpoint", playbook.tags)
        
        # Verifica condições
        self.assertEqual(playbook.conditions[0].field, "endpoint")
        self.assertEqual(playbook.conditions[0].operator, "eq")
        self.assertEqual(playbook.conditions[0].value, "Minha API")
    
    def test_high_latency_playbook(self):
        playbook = create_high_latency_playbook(threshold_ms=3000)
        
        self.assertEqual(playbook.trigger, "metric_threshold")
        self.assertEqual(len(playbook.conditions), 2)
        self.assertEqual(len(playbook.actions), 2)
        
        # Verifica threshold
        self.assertEqual(playbook.conditions[1].value, 3000)


class TestEnums(unittest.TestCase):
    """Testes para enums."""
    
    def test_action_types(self):
        self.assertEqual(ActionType.LOG.value, "log")
        self.assertEqual(ActionType.NOTIFY.value, "notify")
        self.assertEqual(ActionType.RUN_COMMAND.value, "run_command")
        self.assertEqual(ActionType.HTTP_REQUEST.value, "http_request")
        self.assertEqual(ActionType.SCALE.value, "scale")
        self.assertEqual(ActionType.RESTART.value, "restart")
        self.assertEqual(ActionType.CUSTOM.value, "custom")
    
    def test_trigger_types(self):
        self.assertEqual(TriggerType.ALERT_CREATED.value, "alert_created")
        self.assertEqual(TriggerType.ALERT_ESCALATED.value, "alert_escalated")
        self.assertEqual(TriggerType.MANUAL.value, "manual")
    
    def test_playbook_statuses(self):
        self.assertEqual(PlaybookStatus.PENDING.value, "pending")
        self.assertEqual(PlaybookStatus.RUNNING.value, "running")
        self.assertEqual(PlaybookStatus.SUCCESS.value, "success")
        self.assertEqual(PlaybookStatus.FAILED.value, "failed")
        self.assertEqual(PlaybookStatus.RATE_LIMITED.value, "rate_limited")


if __name__ == '__main__':
    unittest.main()
