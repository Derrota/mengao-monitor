"""
Mengão Monitor - System Metrics Module
Collects system metrics and exports them in Prometheus format.
"""

import os
import time
import psutil
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class SystemMetrics:
    """System metrics data class."""
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used_mb: float = 0.0
    memory_total_mb: float = 0.0
    disk_percent: float = 0.0
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0
    network_bytes_sent: int = 0
    network_bytes_recv: int = 0
    process_count: int = 0
    boot_time: float = 0.0
    uptime_seconds: float = 0.0
    timestamp: str = ""


class SystemMetricsCollector:
    """Collects and manages system metrics."""
    
    def __init__(self):
        self.start_time = time.time()
        self.last_network = psutil.net_io_counters()
        self.last_time = time.time()
    
    def collect(self) -> SystemMetrics:
        """Collect current system metrics."""
        # CPU
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        # Memory
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_used_mb = memory.used / 1024 / 1024
        memory_total_mb = memory.total / 1024 / 1024
        
        # Disk
        disk = psutil.disk_usage('/')
        disk_percent = disk.percent
        disk_used_gb = disk.used / 1024 / 1024 / 1024
        disk_total_gb = disk.total / 1024 / 1024 / 1024
        
        # Network
        network = psutil.net_io_counters()
        network_bytes_sent = network.bytes_sent
        network_bytes_recv = network.bytes_recv
        
        # Process
        process_count = len(psutil.pids())
        
        # Boot time and uptime
        boot_time = psutil.boot_time()
        uptime_seconds = time.time() - boot_time
        
        return SystemMetrics(
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_used_mb=round(memory_used_mb, 2),
            memory_total_mb=round(memory_total_mb, 2),
            disk_percent=disk_percent,
            disk_used_gb=round(disk_used_gb, 2),
            disk_total_gb=round(disk_total_gb, 2),
            network_bytes_sent=network_bytes_sent,
            network_bytes_recv=network_bytes_recv,
            process_count=process_count,
            boot_time=boot_time,
            uptime_seconds=round(uptime_seconds, 2),
            timestamp=datetime.now().isoformat()
        )
    
    def to_prometheus(self, metrics: SystemMetrics) -> str:
        """Convert metrics to Prometheus format."""
        lines = [
            "# HELP mengao_system_cpu_percent CPU usage percentage",
            "# TYPE mengao_system_cpu_percent gauge",
            f"mengao_system_cpu_percent {metrics.cpu_percent}",
            "",
            "# HELP mengao_system_memory_percent Memory usage percentage",
            "# TYPE mengao_system_memory_percent gauge",
            f"mengao_system_memory_percent {metrics.memory_percent}",
            "",
            "# HELP mengao_system_memory_used_mb Memory used in MB",
            "# TYPE mengao_system_memory_used_mb gauge",
            f"mengao_system_memory_used_mb {metrics.memory_used_mb}",
            "",
            "# HELP mengao_system_memory_total_mb Total memory in MB",
            "# TYPE mengao_system_memory_total_mb gauge",
            f"mengao_system_memory_total_mb {metrics.memory_total_mb}",
            "",
            "# HELP mengao_system_disk_percent Disk usage percentage",
            "# TYPE mengao_system_disk_percent gauge",
            f"mengao_system_disk_percent {metrics.disk_percent}",
            "",
            "# HELP mengao_system_disk_used_gb Disk used in GB",
            "# TYPE mengao_system_disk_used_gb gauge",
            f"mengao_system_disk_used_gb {metrics.disk_used_gb}",
            "",
            "# HELP mengao_system_disk_total_gb Total disk in GB",
            "# TYPE mengao_system_disk_total_gb gauge",
            f"mengao_system_disk_total_gb {metrics.disk_total_gb}",
            "",
            "# HELP mengao_system_network_bytes_sent Network bytes sent",
            "# TYPE mengao_system_network_bytes_sent counter",
            f"mengao_system_network_bytes_sent {metrics.network_bytes_sent}",
            "",
            "# HELP mengao_system_network_bytes_recv Network bytes received",
            "# TYPE mengao_system_network_bytes_recv counter",
            f"mengao_system_network_bytes_recv {metrics.network_bytes_recv}",
            "",
            "# HELP mengao_system_process_count Number of processes",
            "# TYPE mengao_system_process_count gauge",
            f"mengao_system_process_count {metrics.process_count}",
            "",
            "# HELP mengao_system_uptime_seconds System uptime in seconds",
            "# TYPE mengao_system_uptime_seconds gauge",
            f"mengao_system_uptime_seconds {metrics.uptime_seconds}",
        ]
        
        return "\n".join(lines)
    
    def to_dict(self, metrics: SystemMetrics) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "cpu_percent": metrics.cpu_percent,
            "memory_percent": metrics.memory_percent,
            "memory_used_mb": metrics.memory_used_mb,
            "memory_total_mb": metrics.memory_total_mb,
            "disk_percent": metrics.disk_percent,
            "disk_used_gb": metrics.disk_used_gb,
            "disk_total_gb": metrics.disk_total_gb,
            "network_bytes_sent": metrics.network_bytes_sent,
            "network_bytes_recv": metrics.network_bytes_recv,
            "process_count": metrics.process_count,
            "uptime_seconds": metrics.uptime_seconds,
            "timestamp": metrics.timestamp
        }