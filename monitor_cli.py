#!/usr/bin/env python3
"""
Mengão Monitor CLI v3.15
Interface unificada para gerenciar o Mengão Monitor.

Zero dependências externas — apenas stdlib Python.

Uso:
    python3 monitor_cli.py status
    python3 monitor_cli.py apis
    python3 monitor_cli.py check <api_name>
    python3 monitor_cli.py backup create
    python3 monitor_cli.py maintenance run
    python3 monitor_cli.py scheduler list
    python3 monitor_cli.py sla report
    python3 monitor_cli.py graph impact <api_name>
    python3 monitor_cli.py alerts
    python3 monitor_cli.py dashboard
"""

import argparse
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime

# ═══════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════

DEFAULT_HOST = "http://localhost:5000"
CONFIG_FILE = "cli_config.json"

def load_config():
    """Load CLI config (host, token)."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"host": DEFAULT_HOST, "token": None}

def save_config(config):
    """Save CLI config."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

# ═══════════════════════════════════════════════════════════════
# HTTP Client (zero deps)
# ═══════════════════════════════════════════════════════════════

class MonitorClient:
    """HTTP client for Mengão Monitor API."""

    def __init__(self, host=None, token=None):
        config = load_config()
        self.host = (host or config.get("host") or DEFAULT_HOST).rstrip('/')
        self.token = token or config.get("token")

    def _request(self, method, path, data=None):
        """Make HTTP request to monitor API."""
        url = f"{self.host}{path}"
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        body = json.dumps(data).encode() if data else None

        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else ""
            try:
                error_json = json.loads(error_body)
                return {"error": error_json.get("error", str(e)), "status": e.code}
            except json.JSONDecodeError:
                return {"error": error_body or str(e), "status": e.code}
        except urllib.error.URLError as e:
            return {"error": f"Connection failed: {e.reason}. Is the monitor running?"}
        except Exception as e:
            return {"error": str(e)}

    def get(self, path):
        return self._request("GET", path)

    def post(self, path, data=None):
        return self._request("POST", path, data)

    def delete(self, path):
        return self._request("DELETE", path)

# ═══════════════════════════════════════════════════════════════
# Formatters
# ═══════════════════════════════════════════════════════════════

# ANSI colors
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

def color(text, c):
    return f"{c}{text}{RESET}"

def status_icon(status):
    icons = {
        "healthy": color("●", GREEN),
        "degraded": color("●", YELLOW),
        "down": color("●", RED),
        "unknown": color("●", DIM),
        "open": color("OPEN", RED),
        "closed": color("CLOSED", GREEN),
        "half_open": color("HALF", YELLOW),
    }
    return icons.get(status, color("●", DIM))

def format_uptime(uptime_pct):
    if uptime_pct >= 99.9:
        return color(f"{uptime_pct:.2f}%", GREEN)
    elif uptime_pct >= 99.0:
        return color(f"{uptime_pct:.2f}%", YELLOW)
    else:
        return color(f"{uptime_pct:.2f}%", RED)

def format_time(seconds):
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.0f}m {seconds%60:.0f}s"
    else:
        return f"{seconds/3600:.0f}h {(seconds%3600)/60:.0f}m"

def format_timestamp(ts):
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    return str(ts)

def print_table(headers, rows, widths=None):
    """Print simple table without external deps."""
    if not widths:
        widths = [max(len(str(h)), max((len(str(r[i])) for r in rows), default=0)) + 2
                  for i, h in enumerate(headers)]

    header_line = "".join(color(str(h).ljust(w), BOLD + CYAN) for h, w in zip(headers, widths))
    print(header_line)
    print(color("─" * sum(widths), DIM))

    for row in rows:
        line = ""
        for i, cell in enumerate(row):
            line += str(cell).ljust(widths[i])
        print(line)

def print_json(data, indent=2):
    """Pretty print JSON."""
    print(json.dumps(data, indent=indent, default=str))

# ═══════════════════════════════════════════════════════════════
# Commands
# ═══════════════════════════════════════════════════════════════

def cmd_status(client, args):
    """Show monitor status."""
    data = client.get("/status")
    if "error" in data:
        print(color(f"❌ Error: {data['error']}", RED))
        return 1

    print(f"\n{BOLD}🦞 Mengão Monitor Status{RESET}")
    print(color("─" * 40, DIM))

    status = data.get("status", "unknown")
    print(f"  Status:     {status_icon(status)} {status}")
    print(f"  Uptime:     {format_time(data.get('uptime_seconds', 0))}")
    print(f"  APIs:       {data.get('total_apis', 0)} monitored")
    print(f"  Healthy:    {color(str(data.get('healthy_count', 0)), GREEN)}")
    print(f"  Down:       {color(str(data.get('down_count', 0)), RED)}")
    print(f"  Version:    {data.get('version', 'unknown')}")
    print(f"  Started:    {format_timestamp(data.get('started_at', 0))}")
    print()
    return 0

def cmd_apis(client, args):
    """List monitored APIs."""
    data = client.get("/apis")
    if "error" in data:
        print(color(f"❌ Error: {data['error']}", RED))
        return 1

    apis = data.get("apis", [])
    if not apis:
        print(color("No APIs configured.", YELLOW))
        return 0

    print(f"\n{BOLD}📡 Monitored APIs ({len(apis)}){RESET}\n")

    headers = ["Name", "Status", "Uptime", "Response", "Last Check"]
    rows = []
    for api in apis:
        name = api.get("name", "?")
        status = api.get("status", "unknown")
        uptime = api.get("uptime_percentage", 0)
        response = api.get("last_response_time", 0)
        last_check = format_timestamp(api.get("last_check", 0))

        rows.append([
            name,
            f"{status_icon(status)} {status}",
            format_uptime(uptime),
            f"{response:.0f}ms" if response else "—",
            last_check
        ])

    print_table(headers, rows)
    print()
    return 0

def cmd_check(client, args):
    """Run health check for specific API."""
    if not args.api_name:
        print(color("❌ Specify API name: monitor_cli.py check <api_name>", RED))
        return 1

    data = client.post(f"/check/{args.api_name}")
    if "error" in data:
        print(color(f"❌ Error: {data['error']}", RED))
        return 1

    status = data.get("status", "unknown")
    print(f"\n{BOLD}🔍 Health Check: {args.api_name}{RESET}")
    print(color("─" * 40, DIM))
    print(f"  Status:     {status_icon(status)} {status}")
    print(f"  Response:   {data.get('response_time', 0):.0f}ms")
    print(f"  Status Code: {data.get('status_code', '—')}")
    print(f"  Timestamp:  {format_timestamp(data.get('timestamp', 0))}")
    if data.get("error_message"):
        print(f"  Error:      {color(data['error_message'], RED)}")
    print()
    return 0

def cmd_backup(client, args):
    """Manage backups."""
    if args.backup_action == "create":
        data = client.post("/backup/create")
        if "error" in data:
            print(color(f"❌ Error: {data['error']}", RED))
            return 1
        print(f"\n{BOLD}💾 Backup Created{RESET}")
        print(f"  File:       {data.get('backup_file', '?')}")
        print(f"  Size:       {data.get('size_bytes', 0) / 1024:.1f} KB")
        print(f"  Verified:   {'✅' if data.get('verified') else '❌'}")
        print(f"  Duration:   {data.get('duration_seconds', 0):.2f}s")

    elif args.backup_action == "list":
        data = client.get("/backup/list")
        if "error" in data:
            print(color(f"❌ Error: {data['error']}", RED))
            return 1

        backups = data.get("backups", [])
        if not backups:
            print(color("No backups found.", YELLOW))
            return 0

        print(f"\n{BOLD}💾 Backups ({len(backups)}){RESET}\n")
        headers = ["File", "Size", "Created", "Verified"]
        rows = []
        for b in backups:
            rows.append([
                b.get("filename", "?"),
                f"{b.get('size_bytes', 0) / 1024:.1f} KB",
                format_timestamp(b.get("created_at", 0)),
                "✅" if b.get("verified") else "❌"
            ])
        print_table(headers, rows)

    elif args.backup_action == "restore":
        if not args.file:
            print(color("❌ Specify backup file: monitor_cli.py backup restore <file>", RED))
            return 1
        data = client.post("/backup/restore", {"file": args.file})
        if "error" in data:
            print(color(f"❌ Error: {data['error']}", RED))
            return 1
        print(f"\n{BOLD}💾 Backup Restored{RESET}")
        print(f"  File:       {data.get('backup_file', '?')}")
        print(f"  Verified:   {'✅' if data.get('verified') else '❌'}")

    elif args.backup_action == "stats":
        data = client.get("/backup/stats")
        if "error" in data:
            print(color(f"❌ Error: {data['error']}", RED))
            return 1
        print(f"\n{BOLD}💾 Backup Stats{RESET}")
        print_json(data)

    else:
        print(color("Usage: monitor_cli.py backup [create|list|restore|stats]", YELLOW))
        return 1

    print()
    return 0

def cmd_maintenance(client, args):
    """Run maintenance tasks."""
    if args.maintenance_action == "run":
        data = client.post("/maintenance/run")
        if "error" in data:
            print(color(f"❌ Error: {data['error']}", RED))
            return 1
        print(f"\n{BOLD}🧹 Maintenance Run{RESET}")
        print(color("─" * 40, DIM))
        results = data.get("results", {})
        for task, result in results.items():
            icon = "✅" if result.get("success") else "❌"
            print(f"  {icon} {task}: {result.get('message', 'done')}")
        print(f"\n  Duration:   {data.get('duration_seconds', 0):.2f}s")

    elif args.maintenance_action == "status":
        data = client.get("/maintenance/status")
        if "error" in data:
            print(color(f"❌ Error: {data['error']}", RED))
            return 1
        print(f"\n{BOLD}🧹 Maintenance Status{RESET}")
        print_json(data)

    elif args.maintenance_action == "schedule":
        data = client.get("/maintenance/schedule")
        if "error" in data:
            print(color(f"❌ Error: {data['error']}", RED))
            return 1
        print(f"\n{BOLD}🧹 Maintenance Schedule{RESET}")
        print_json(data)

    else:
        print(color("Usage: monitor_cli.py maintenance [run|status|schedule]", YELLOW))
        return 1

    print()
    return 0

def cmd_scheduler(client, args):
    """Manage health check scheduler."""
    if args.scheduler_action == "list":
        data = client.get("/scheduler/schedules")
        if "error" in data:
            print(color(f"❌ Error: {data['error']}", RED))
            return 1

        schedules = data.get("schedules", [])
        if not schedules:
            print(color("No schedules configured.", YELLOW))
            return 0

        print(f"\n{BOLD}⏰ Health Check Schedules ({len(schedules)}){RESET}\n")
        headers = ["Name", "Type", "Schedule", "Enabled", "Last Run"]
        rows = []
        for s in schedules:
            rows.append([
                s.get("name", "?"),
                s.get("type", "?"),
                s.get("schedule", "?"),
                "✅" if s.get("enabled") else "❌",
                format_timestamp(s.get("last_run", 0)) if s.get("last_run") else "never"
            ])
        print_table(headers, rows)

    elif args.scheduler_action == "stats":
        data = client.get("/scheduler/stats")
        if "error" in data:
            print(color(f"❌ Error: {data['error']}", RED))
            return 1
        print(f"\n{BOLD}⏰ Scheduler Stats{RESET}")
        print_json(data)

    elif args.scheduler_action == "history":
        data = client.get("/scheduler/history")
        if "error" in data:
            print(color(f"❌ Error: {data['error']}", RED))
            return 1

        history = data.get("history", [])
        if not history:
            print(color("No execution history.", YELLOW))
            return 0

        print(f"\n{BOLD}⏰ Execution History (last {len(history)}){RESET}\n")
        headers = ["Schedule", "Status", "Duration", "Time"]
        rows = []
        for h in history[-20:]:
            status = "✅" if h.get("success") else "❌"
            rows.append([
                h.get("schedule_name", "?"),
                status,
                f"{h.get('duration_ms', 0):.0f}ms",
                format_timestamp(h.get("timestamp", 0))
            ])
        print_table(headers, rows)

    else:
        print(color("Usage: monitor_cli.py scheduler [list|stats|history]", YELLOW))
        return 1

    print()
    return 0

def cmd_sla(client, args):
    """SLA reporting."""
    if args.sla_action == "report":
        endpoint = args.endpoint or ""
        path = f"/sla/report/{endpoint}" if endpoint else "/sla/reports"
        data = client.get(path)
        if "error" in data:
            print(color(f"❌ Error: {data['error']}", RED))
            return 1

        if endpoint:
            print(f"\n{BOLD}📊 SLA Report: {endpoint}{RESET}")
            print(color("─" * 40, DIM))
            print(f"  Uptime:     {format_uptime(data.get('uptime_percentage', 0))}")
            print(f"  Avg RT:     {data.get('avg_response_time', 0):.0f}ms")
            print(f"  P95 RT:     {data.get('p95_response_time', 0):.0f}ms")
            print(f"  P99 RT:     {data.get('p99_response_time', 0):.0f}ms")
            print(f"  Incidents:  {data.get('total_incidents', 0)}")
            print(f"  MTTR:       {format_time(data.get('mttr_seconds', 0))}")
            breaches = data.get('sla_breaches', 0)
            breach_color = RED if breaches > 0 else GREEN
            print(f"  Breaches:   {color(str(breaches), breach_color)}")
        else:
            reports = data.get("reports", {})
            print(f"\n{BOLD}📊 SLA Reports (All Endpoints){RESET}\n")
            for name, report in reports.items():
                uptime = report.get("uptime_percentage", 0)
                print(f"  {name}: {format_uptime(uptime)} uptime, "
                      f"{report.get('avg_response_time', 0):.0f}ms avg, "
                      f"{report.get('total_incidents', 0)} incidents")

    elif args.sla_action == "incidents":
        data = client.get("/sla/incidents")
        if "error" in data:
            print(color(f"❌ Error: {data['error']}", RED))
            return 1

        incidents = data.get("incidents", [])
        if not incidents:
            print(color("No incidents recorded.", GREEN))
            return 0

        print(f"\n{BOLD}🚨 Incidents ({len(incidents)}){RESET}\n")
        headers = ["API", "Severity", "Status", "Duration", "Started"]
        rows = []
        for inc in incidents[-20:]:
            severity = inc.get("severity", "?")
            sev_color = RED if severity == "critical" else YELLOW if severity == "high" else ""
            rows.append([
                inc.get("api_name", "?"),
                f"{color(severity, sev_color)}" if sev_color else severity,
                "✅ resolved" if inc.get("resolved") else "🔴 active",
                format_time(inc.get("duration_seconds", 0)) if inc.get("resolved") else "ongoing",
                format_timestamp(inc.get("started_at", 0))
            ])
        print_table(headers, rows)

    elif args.sla_action == "targets":
        data = client.get("/sla/targets")
        if "error" in data:
            print(color(f"❌ Error: {data['error']}", RED))
            return 1
        print(f"\n{BOLD}📊 SLA Targets{RESET}")
        print_json(data)

    else:
        print(color("Usage: monitor_cli.py sla [report|incidents|targets]", YELLOW))
        return 1

    print()
    return 0

def cmd_graph(client, args):
    """Dependency graph operations."""
    if args.graph_action == "impact":
        if not args.api_name:
            print(color("❌ Specify API name: monitor_cli.py graph impact <api_name>", RED))
            return 1
        data = client.get(f"/graph/impact/{args.api_name}")
        if "error" in data:
            print(color(f"❌ Error: {data['error']}", RED))
            return 1

        print(f"\n{BOLD}🔗 Impact Analysis: {args.api_name}{RESET}")
        print(color("─" * 40, DIM))
        severity = data.get("severity", "unknown")
        sev_colors = {"low": GREEN, "medium": YELLOW, "high": RED, "critical": RED}
        print(f"  Severity:   {color(severity.upper(), sev_colors.get(severity, DIM))}")
        print(f"  Direct:     {len(data.get('direct_impact', []))} services")
        print(f"  Transitivo: {len(data.get('transitive_impact', []))} services")
        if data.get("direct_impact"):
            print(f"  Affected:   {', '.join(data['direct_impact'])}")
        if data.get("transitive_impact"):
            print(f"  Transitivo: {', '.join(data['transitive_impact'])}")

    elif args.graph_action == "topology":
        data = client.get("/graph/topology")
        if "error" in data:
            print(color(f"❌ Error: {data['error']}", RED))
            return 1
        print(f"\n{BOLD}🔗 Dependency Topology{RESET}")
        print_json(data)

    elif args.graph_action == "critical":
        data = client.get("/graph/critical")
        if "error" in data:
            print(color(f"❌ Error: {data['error']}", RED))
            return 1
        print(f"\n{BOLD}🔗 Critical Paths{RESET}")
        print_json(data)

    elif args.graph_action == "cycles":
        data = client.get("/graph/cycles")
        if "error" in data:
            print(color(f"❌ Error: {data['error']}", RED))
            return 1
        cycles = data.get("cycles", [])
        if cycles:
            print(color(f"⚠️  {len(cycles)} circular dependencies detected!", RED))
            for cycle in cycles:
                print(f"  → {' → '.join(cycle)}")
        else:
            print(color("✅ No circular dependencies.", GREEN))

    else:
        print(color("Usage: monitor_cli.py graph [impact|topology|critical|cycles]", YELLOW))
        return 1

    print()
    return 0

def cmd_alerts(client, args):
    """Show recent alerts."""
    data = client.get("/alerts")
    if "error" in data:
        print(color(f"❌ Error: {data['error']}", RED))
        return 1

    alerts = data.get("alerts", [])
    if not alerts:
        print(color("✅ No active alerts.", GREEN))
        return 0

    print(f"\n{BOLD}🚨 Active Alerts ({len(alerts)}){RESET}\n")
    headers = ["API", "Level", "Message", "Since"]
    rows = []
    for a in alerts[-20:]:
        level = a.get("level", "info")
        level_colors = {"critical": RED, "error": RED, "warning": YELLOW, "info": BLUE}
        rows.append([
            a.get("api_name", "?"),
            color(level.upper(), level_colors.get(level, DIM)),
            a.get("message", "?")[:50],
            format_timestamp(a.get("timestamp", 0))
        ])
    print_table(headers, rows)
    print()
    return 0

def cmd_dashboard(client, args):
    """Open dashboard URL."""
    data = client.get("/status")
    if "error" in data:
        print(color(f"❌ Error: {data['error']}", RED))
        return 1

    print(f"\n{BOLD}🖥️  Dashboard{RESET}")
    print(f"  URL: {client.host}/")
    print(f"  WebSocket: ws://{client.host.replace('http://', '')}/ws")
    print()
    return 0

def cmd_config(client, args):
    """Configure CLI."""
    if args.config_action == "set-host":
        config = load_config()
        config["host"] = args.value
        save_config(config)
        print(color(f"✅ Host set to: {args.value}", GREEN))

    elif args.config_action == "set-token":
        config = load_config()
        config["token"] = args.value
        save_config(config)
        print(color("✅ Token configured.", GREEN))

    elif args.config_action == "show":
        config = load_config()
        print(f"\n{BOLD}⚙️  CLI Config{RESET}")
        print(f"  Host:  {config.get('host', DEFAULT_HOST)}")
        token = config.get('token')
        print(f"  Token: {'*' * 8 + token[-4:] if token and len(token) > 4 else 'not set'}")
        print()

    else:
        print(color("Usage: monitor_cli.py config [set-host|set-token|show]", YELLOW))
        return 1

    return 0

def cmd_metrics(client, args):
    """Show Prometheus metrics."""
    data = client.get("/metrics")
    if "error" in data:
        print(color(f"❌ Error: {data['error']}", RED))
        return 1
    print(f"\n{BOLD}📈 Metrics{RESET}")
    print_json(data)
    print()
    return 0

def cmd_websocket(client, args):
    """WebSocket status."""
    data = client.get("/websocket/status")
    if "error" in data:
        print(color(f"❌ Error: {data['error']}", RED))
        return 1

    print(f"\n{BOLD}🔌 WebSocket Status{RESET}")
    print(color("─" * 40, DIM))
    print(f"  Running:    {'✅' if data.get('running') else '❌'}")
    print(f"  Clients:    {data.get('total_clients', 0)}")
    print(f"  Messages:   {data.get('total_messages', 0)}")
    print(f"  Errors:     {data.get('total_errors', 0)}")
    print()
    return 0

# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="🦞 Mengão Monitor CLI v3.15",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s status                    # Monitor status
  %(prog)s apis                      # List all APIs
  %(prog)s check my-api              # Health check specific API
  %(prog)s backup create             # Create backup
  %(prog)s backup list               # List backups
  %(prog)s maintenance run           # Run maintenance tasks
  %(prog)s scheduler list            # List schedules
  %(prog)s sla report                # SLA report all
  %(prog)s sla report my-api         # SLA report specific
  %(prog)s graph impact my-api       # Impact analysis
  %(prog)s alerts                    # Show active alerts
  %(prog)s config set-host http://host:5000
        """
    )

    parser.add_argument("--host", help="Monitor host URL")
    parser.add_argument("--token", help="Auth token")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # status
    subparsers.add_parser("status", help="Show monitor status")

    # apis
    subparsers.add_parser("apis", help="List monitored APIs")

    # check
    check_parser = subparsers.add_parser("check", help="Run health check")
    check_parser.add_argument("api_name", help="API name to check")

    # backup
    backup_parser = subparsers.add_parser("backup", help="Manage backups")
    backup_parser.add_argument("backup_action", choices=["create", "list", "restore", "stats"])
    backup_parser.add_argument("file", nargs="?", help="Backup file for restore")

    # maintenance
    maint_parser = subparsers.add_parser("maintenance", help="Maintenance tasks")
    maint_parser.add_argument("maintenance_action", choices=["run", "status", "schedule"])

    # scheduler
    sched_parser = subparsers.add_parser("scheduler", help="Health check scheduler")
    sched_parser.add_argument("scheduler_action", choices=["list", "stats", "history"])

    # sla
    sla_parser = subparsers.add_parser("sla", help="SLA reporting")
    sla_parser.add_argument("sla_action", choices=["report", "incidents", "targets"])
    sla_parser.add_argument("endpoint", nargs="?", help="Specific endpoint")

    # graph
    graph_parser = subparsers.add_parser("graph", help="Dependency graph")
    graph_parser.add_argument("graph_action", choices=["impact", "topology", "critical", "cycles"])
    graph_parser.add_argument("api_name", nargs="?", help="API name for impact analysis")

    # alerts
    subparsers.add_parser("alerts", help="Show active alerts")

    # dashboard
    subparsers.add_parser("dashboard", help="Dashboard info")

    # metrics
    subparsers.add_parser("metrics", help="Show metrics")

    # websocket
    subparsers.add_parser("websocket", help="WebSocket status")

    # config
    config_parser = subparsers.add_parser("config", help="Configure CLI")
    config_parser.add_argument("config_action", choices=["set-host", "set-token", "show"])
    config_parser.add_argument("value", nargs="?", help="Config value")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    client = MonitorClient(host=args.host, token=args.token)

    commands = {
        "status": cmd_status,
        "apis": cmd_apis,
        "check": cmd_check,
        "backup": cmd_backup,
        "maintenance": cmd_maintenance,
        "scheduler": cmd_scheduler,
        "sla": cmd_sla,
        "graph": cmd_graph,
        "alerts": cmd_alerts,
        "dashboard": cmd_dashboard,
        "metrics": cmd_metrics,
        "websocket": cmd_websocket,
        "config": cmd_config,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(client, args)
    else:
        parser.print_help()
        return 1

if __name__ == "__main__":
    sys.exit(main())
