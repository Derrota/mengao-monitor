#!/usr/bin/env python3
"""
Test suite for Mengão Monitor CLI v3.15
"""

import unittest
import json
import sys
import os
import tempfile
from unittest.mock import patch, MagicMock
from io import StringIO

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from monitor_cli import (
    MonitorClient, load_config, save_config,
    status_icon, format_uptime, format_time, format_timestamp,
    color, print_table, print_json,
    cmd_status, cmd_apis, cmd_check, cmd_backup,
    cmd_maintenance, cmd_scheduler, cmd_sla, cmd_graph,
    cmd_alerts, cmd_dashboard, cmd_config, cmd_metrics, cmd_websocket,
    RED, GREEN, YELLOW, BLUE, BOLD, DIM, RESET
)


class TestFormatters(unittest.TestCase):
    """Test formatting functions."""

    def test_status_icon_healthy(self):
        icon = status_icon("healthy")
        self.assertIn("●", icon)

    def test_status_icon_down(self):
        icon = status_icon("down")
        self.assertIn("●", icon)

    def test_status_icon_open(self):
        icon = status_icon("open")
        self.assertIn("OPEN", icon)

    def test_status_icon_closed(self):
        icon = status_icon("closed")
        self.assertIn("CLOSED", icon)

    def test_format_uptime_high(self):
        result = format_uptime(99.95)
        self.assertIn("99.95%", result)

    def test_format_uptime_medium(self):
        result = format_uptime(99.5)
        self.assertIn("99.50%", result)

    def test_format_uptime_low(self):
        result = format_uptime(95.0)
        self.assertIn("95.00%", result)

    def test_format_time_ms(self):
        result = format_time(0.5)
        self.assertEqual(result, "500ms")

    def test_format_time_seconds(self):
        result = format_time(5.5)
        self.assertEqual(result, "5.5s")

    def test_format_time_minutes(self):
        result = format_time(125)
        self.assertIn("m", result)
        self.assertIn("s", result)

    def test_format_time_hours(self):
        result = format_time(7380)
        self.assertIn("h", result)
        self.assertIn("m", result)

    def test_format_timestamp_int(self):
        result = format_timestamp(1710000000)
        self.assertIn("2024", result)

    def test_format_timestamp_string(self):
        result = format_timestamp("2024-01-01")
        self.assertEqual(result, "2024-01-01")

    def test_color(self):
        result = color("test", RED)
        self.assertIn("test", result)
        self.assertIn(RED, result)
        self.assertIn(RESET, result)


class TestConfig(unittest.TestCase):
    """Test config load/save."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.temp_dir, "cli_config.json")

    def tearDown(self):
        if os.path.exists(self.config_file):
            os.remove(self.config_file)
        os.rmdir(self.temp_dir)

    def test_save_and_load_config(self):
        config = {"host": "http://test:5000", "token": "secret123"}
        with open(self.config_file, 'w') as f:
            json.dump(config, f)

        loaded = json.load(open(self.config_file))
        self.assertEqual(loaded["host"], "http://test:5000")
        self.assertEqual(loaded["token"], "secret123")


class TestMonitorClient(unittest.TestCase):
    """Test MonitorClient HTTP operations."""

    def test_client_init_default(self):
        client = MonitorClient()
        self.assertIsNotNone(client.host)

    def test_client_init_custom_host(self):
        client = MonitorClient(host="http://custom:9000")
        self.assertEqual(client.host, "http://custom:9000")

    def test_client_init_strips_trailing_slash(self):
        client = MonitorClient(host="http://test:5000/")
        self.assertEqual(client.host, "http://test:5000")

    def test_client_with_token(self):
        client = MonitorClient(host="http://test:5000", token="abc123")
        self.assertEqual(client.token, "abc123")

    @patch('monitor_cli.urllib.request.urlopen')
    def test_client_get_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status": "ok"}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = MonitorClient(host="http://test:5000")
        result = client.get("/status")
        self.assertEqual(result["status"], "ok")

    @patch('monitor_cli.urllib.request.urlopen')
    def test_client_post_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"created": true}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = MonitorClient(host="http://test:5000")
        result = client.post("/backup/create")
        self.assertTrue(result["created"])

    @patch('monitor_cli.urllib.request.urlopen')
    def test_client_connection_error(self, mock_urlopen):
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("Connection refused")

        client = MonitorClient(host="http://test:5000")
        result = client.get("/status")
        self.assertIn("error", result)
        self.assertIn("Connection failed", result["error"])

    @patch('monitor_cli.urllib.request.urlopen')
    def test_client_http_error(self, mock_urlopen):
        from urllib.error import HTTPError
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"error": "not found"}'
        error = HTTPError("http://test:5000/api", 404, "Not Found", {}, mock_resp)
        mock_urlopen.side_effect = error

        client = MonitorClient(host="http://test:5000")
        result = client.get("/nonexistent")
        self.assertIn("error", result)
        self.assertEqual(result["status"], 404)


class TestCommands(unittest.TestCase):
    """Test CLI command handlers."""

    def setUp(self):
        self.client = MonitorClient(host="http://test:5000")

    @patch.object(MonitorClient, 'get')
    def test_cmd_status_success(self, mock_get):
        mock_get.return_value = {
            "status": "healthy",
            "uptime_seconds": 3600,
            "total_apis": 5,
            "healthy_count": 4,
            "down_count": 1,
            "version": "3.14",
            "started_at": 1710000000
        }
        args = MagicMock()
        result = cmd_status(self.client, args)
        self.assertEqual(result, 0)

    @patch.object(MonitorClient, 'get')
    def test_cmd_status_error(self, mock_get):
        mock_get.return_value = {"error": "Connection failed"}
        args = MagicMock()
        result = cmd_status(self.client, args)
        self.assertEqual(result, 1)

    @patch.object(MonitorClient, 'get')
    def test_cmd_apis_success(self, mock_get):
        mock_get.return_value = {
            "apis": [
                {"name": "api1", "status": "healthy", "uptime_percentage": 99.9,
                 "last_response_time": 150, "last_check": 1710000000},
                {"name": "api2", "status": "down", "uptime_percentage": 95.0,
                 "last_response_time": 0, "last_check": 1710000000}
            ]
        }
        args = MagicMock()
        result = cmd_apis(self.client, args)
        self.assertEqual(result, 0)

    @patch.object(MonitorClient, 'get')
    def test_cmd_apis_empty(self, mock_get):
        mock_get.return_value = {"apis": []}
        args = MagicMock()
        result = cmd_apis(self.client, args)
        self.assertEqual(result, 0)

    @patch.object(MonitorClient, 'post')
    def test_cmd_check_success(self, mock_post):
        mock_post.return_value = {
            "status": "healthy",
            "response_time": 120,
            "status_code": 200,
            "timestamp": 1710000000
        }
        args = MagicMock()
        args.api_name = "my-api"
        result = cmd_check(self.client, args)
        self.assertEqual(result, 0)

    @patch.object(MonitorClient, 'post')
    def test_cmd_check_no_name(self, mock_post):
        args = MagicMock()
        args.api_name = None
        result = cmd_check(self.client, args)
        self.assertEqual(result, 1)

    @patch.object(MonitorClient, 'post')
    def test_cmd_backup_create(self, mock_post):
        mock_post.return_value = {
            "backup_file": "backup_20240101.db.gz",
            "size_bytes": 102400,
            "verified": True,
            "duration_seconds": 1.5
        }
        args = MagicMock()
        args.backup_action = "create"
        result = cmd_backup(self.client, args)
        self.assertEqual(result, 0)

    @patch.object(MonitorClient, 'get')
    def test_cmd_backup_list(self, mock_get):
        mock_get.return_value = {
            "backups": [
                {"filename": "backup1.db.gz", "size_bytes": 51200,
                 "created_at": 1710000000, "verified": True},
                {"filename": "backup2.db.gz", "size_bytes": 102400,
                 "created_at": 1710000000, "verified": False}
            ]
        }
        args = MagicMock()
        args.backup_action = "list"
        result = cmd_backup(self.client, args)
        self.assertEqual(result, 0)

    @patch.object(MonitorClient, 'get')
    def test_cmd_backup_list_empty(self, mock_get):
        mock_get.return_value = {"backups": []}
        args = MagicMock()
        args.backup_action = "list"
        result = cmd_backup(self.client, args)
        self.assertEqual(result, 0)

    @patch.object(MonitorClient, 'post')
    def test_cmd_backup_restore(self, mock_post):
        mock_post.return_value = {
            "backup_file": "backup1.db.gz",
            "verified": True
        }
        args = MagicMock()
        args.backup_action = "restore"
        args.file = "backup1.db.gz"
        result = cmd_backup(self.client, args)
        self.assertEqual(result, 0)

    @patch.object(MonitorClient, 'post')
    def test_cmd_backup_restore_no_file(self, mock_post):
        args = MagicMock()
        args.backup_action = "restore"
        args.file = None
        result = cmd_backup(self.client, args)
        self.assertEqual(result, 1)

    @patch.object(MonitorClient, 'post')
    def test_cmd_maintenance_run(self, mock_post):
        mock_post.return_value = {
            "results": {
                "log_rotation": {"success": True, "message": "Rotated 3 files"},
                "db_cleanup": {"success": True, "message": "Cleaned 500 rows"}
            },
            "duration_seconds": 2.5
        }
        args = MagicMock()
        args.maintenance_action = "run"
        result = cmd_maintenance(self.client, args)
        self.assertEqual(result, 0)

    @patch.object(MonitorClient, 'get')
    def test_cmd_scheduler_list(self, mock_get):
        mock_get.return_value = {
            "schedules": [
                {"name": "ssl-check", "type": "recurring", "schedule": "0 */6 * * *",
                 "enabled": True, "last_run": 1710000000}
            ]
        }
        args = MagicMock()
        args.scheduler_action = "list"
        result = cmd_scheduler(self.client, args)
        self.assertEqual(result, 0)

    @patch.object(MonitorClient, 'get')
    def test_cmd_scheduler_list_empty(self, mock_get):
        mock_get.return_value = {"schedules": []}
        args = MagicMock()
        args.scheduler_action = "list"
        result = cmd_scheduler(self.client, args)
        self.assertEqual(result, 0)

    @patch.object(MonitorClient, 'get')
    def test_cmd_sla_report_all(self, mock_get):
        mock_get.return_value = {
            "reports": {
                "api1": {"uptime_percentage": 99.9, "avg_response_time": 150, "total_incidents": 2},
                "api2": {"uptime_percentage": 98.5, "avg_response_time": 300, "total_incidents": 5}
            }
        }
        args = MagicMock()
        args.sla_action = "report"
        args.endpoint = None
        result = cmd_sla(self.client, args)
        self.assertEqual(result, 0)

    @patch.object(MonitorClient, 'get')
    def test_cmd_sla_report_specific(self, mock_get):
        mock_get.return_value = {
            "uptime_percentage": 99.95,
            "avg_response_time": 120,
            "p95_response_time": 250,
            "p99_response_time": 500,
            "total_incidents": 1,
            "mttr_seconds": 300,
            "sla_breaches": 0
        }
        args = MagicMock()
        args.sla_action = "report"
        args.endpoint = "my-api"
        result = cmd_sla(self.client, args)
        self.assertEqual(result, 0)

    @patch.object(MonitorClient, 'get')
    def test_cmd_sla_incidents(self, mock_get):
        mock_get.return_value = {
            "incidents": [
                {"api_name": "api1", "severity": "critical", "resolved": True,
                 "duration_seconds": 300, "started_at": 1710000000}
            ]
        }
        args = MagicMock()
        args.sla_action = "incidents"
        result = cmd_sla(self.client, args)
        self.assertEqual(result, 0)

    @patch.object(MonitorClient, 'get')
    def test_cmd_sla_incidents_empty(self, mock_get):
        mock_get.return_value = {"incidents": []}
        args = MagicMock()
        args.sla_action = "incidents"
        result = cmd_sla(self.client, args)
        self.assertEqual(result, 0)

    @patch.object(MonitorClient, 'get')
    def test_cmd_graph_impact(self, mock_get):
        mock_get.return_value = {
            "severity": "high",
            "direct_impact": ["service-b", "service-c"],
            "transitive_impact": ["service-d"]
        }
        args = MagicMock()
        args.graph_action = "impact"
        args.api_name = "service-a"
        result = cmd_graph(self.client, args)
        self.assertEqual(result, 0)

    @patch.object(MonitorClient, 'get')
    def test_cmd_graph_impact_no_name(self, mock_get):
        args = MagicMock()
        args.graph_action = "impact"
        args.api_name = None
        result = cmd_graph(self.client, args)
        self.assertEqual(result, 1)

    @patch.object(MonitorClient, 'get')
    def test_cmd_graph_cycles_none(self, mock_get):
        mock_get.return_value = {"cycles": []}
        args = MagicMock()
        args.graph_action = "cycles"
        result = cmd_graph(self.client, args)
        self.assertEqual(result, 0)

    @patch.object(MonitorClient, 'get')
    def test_cmd_graph_cycles_found(self, mock_get):
        mock_get.return_value = {"cycles": [["a", "b", "a"]]}
        args = MagicMock()
        args.graph_action = "cycles"
        result = cmd_graph(self.client, args)
        self.assertEqual(result, 0)

    @patch.object(MonitorClient, 'get')
    def test_cmd_alerts_with_alerts(self, mock_get):
        mock_get.return_value = {
            "alerts": [
                {"api_name": "api1", "level": "critical", "message": "API down",
                 "timestamp": 1710000000}
            ]
        }
        args = MagicMock()
        result = cmd_alerts(self.client, args)
        self.assertEqual(result, 0)

    @patch.object(MonitorClient, 'get')
    def test_cmd_alerts_empty(self, mock_get):
        mock_get.return_value = {"alerts": []}
        args = MagicMock()
        result = cmd_alerts(self.client, args)
        self.assertEqual(result, 0)

    @patch.object(MonitorClient, 'get')
    def test_cmd_dashboard(self, mock_get):
        mock_get.return_value = {"status": "healthy"}
        args = MagicMock()
        result = cmd_dashboard(self.client, args)
        self.assertEqual(result, 0)

    @patch.object(MonitorClient, 'get')
    def test_cmd_metrics(self, mock_get):
        mock_get.return_value = {"http_requests_total": 1000}
        args = MagicMock()
        result = cmd_metrics(self.client, args)
        self.assertEqual(result, 0)

    @patch.object(MonitorClient, 'get')
    def test_cmd_websocket(self, mock_get):
        mock_get.return_value = {
            "running": True,
            "total_clients": 3,
            "total_messages": 500,
            "total_errors": 0
        }
        args = MagicMock()
        result = cmd_websocket(self.client, args)
        self.assertEqual(result, 0)

    def test_cmd_config_set_host(self):
        with patch('monitor_cli.save_config') as mock_save:
            args = MagicMock()
            args.config_action = "set-host"
            args.value = "http://newhost:5000"
            result = cmd_config(self.client, args)
            self.assertEqual(result, 0)
            mock_save.assert_called_once()

    def test_cmd_config_set_token(self):
        with patch('monitor_cli.save_config') as mock_save:
            args = MagicMock()
            args.config_action = "set-token"
            args.value = "newtoken123"
            result = cmd_config(self.client, args)
            self.assertEqual(result, 0)
            mock_save.assert_called_once()

    def test_cmd_config_show(self):
        with patch('monitor_cli.load_config') as mock_load:
            mock_load.return_value = {"host": "http://test:5000", "token": "secret"}
            args = MagicMock()
            args.config_action = "show"
            result = cmd_config(self.client, args)
            self.assertEqual(result, 0)


class TestPrintTable(unittest.TestCase):
    """Test table printing."""

    def test_print_table_basic(self):
        headers = ["Name", "Status"]
        rows = [["api1", "healthy"], ["api2", "down"]]
        # Should not raise
        print_table(headers, rows)

    def test_print_json_basic(self):
        data = {"status": "ok", "count": 5}
        # Should not raise
        print_json(data)


if __name__ == "__main__":
    unittest.main()
