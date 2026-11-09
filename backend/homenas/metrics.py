from __future__ import annotations

import platform
import shutil
import socket
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

import psutil

from .integrations import (
    EXTERNAL_PROBES,
    collect_mihomo,
    collect_seafile,
    collect_tailscale,
    discover_block_devices,
    discover_docker_services,
    discover_systemd_services,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def unavailable(reason: str, source: str = "collector") -> Dict[str, Any]:
    return {"available": False, "value": None, "quality": "unavailable", "source": source, "reason": reason}


def parse_perf_csv(text: str) -> Dict[str, Dict[str, Any]]:
    """Parse perf stat -x, output without depending on human-readable columns.

    Supported examples include ``1.234,,Joules,power/energy-pkg/,100.0`` and
    ``<not supported>,,Joules,power/energy-pkg/,100``.  Invalid/missing values
    remain unavailable instead of becoming zero.
    """
    result: Dict[str, Dict[str, Any]] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = [part.strip() for part in line.split(",")]
        if len(fields) < 4:
            continue
        value_text, unit, event = fields[0], fields[2], fields[3]
        key = event.replace("power/energy-", "").replace("/", "")
        if not key:
            continue
        if value_text.startswith("<") or value_text in {"", "-", "nan", "NaN"}:
            result[key] = unavailable("perf returned no value", "perf")
            result[key]["unit"] = unit or "J"
            continue
        try:
            value = float(value_text)
        except ValueError:
            result[key] = unavailable("perf value was not numeric", "perf")
            result[key]["unit"] = unit or "J"
            continue
        result[key] = {
            "available": True,
            "value": value,
            "unit": unit or "J",
            "quality": "ok",
            "source": "perf",
        }
    return result


def counter_rate(previous: Optional[Tuple[float, float]], current: float, now: float) -> Optional[float]:
    """Return units per second, treating reboot/reset/decrease as unavailable."""
    if previous is None:
        return None
    old_value, old_time = previous
    elapsed = now - old_time
    if elapsed <= 0 or current < old_value:
        return None
    return (current - old_value) / elapsed


def _temperature_reading() -> Tuple[Optional[float], Optional[str]]:
    try:
        temperatures = psutil.sensors_temperatures(fahrenheit=False)
    except (AttributeError, OSError):
        return None, None
    values: List[Tuple[float, str]] = []
    preferred: List[Tuple[float, str]] = []
    for label, entries in temperatures.items():
        for entry in entries:
            current = getattr(entry, "current", None)
            if isinstance(current, (int, float)):
                pair = (float(current), str(label))
                values.append(pair)
                if any(token in str(label).lower() for token in ("coretemp", "k10temp", "cpu")):
                    preferred.append(pair)
    selected = preferred or values
    return max(selected, key=lambda item: item[0]) if selected else (None, None)


def _battery() -> Dict[str, Any]:
    try:
        battery = psutil.sensors_battery()
    except (AttributeError, OSError):
        battery = None
    if battery is None:
        return unavailable("battery sensor not available", "psutil")
    return {
        "available": True,
        "percent": round(float(battery.percent), 1) if battery.percent is not None else None,
        "charging": battery.power_plugged,
        "seconds_left": battery.secsleft if battery.secsleft >= 0 else None,
        "quality": "ok",
        "source": "psutil",
    }


def _top_processes(limit: int = 10) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        processes = psutil.process_iter(attrs=["pid", "name", "cpu_percent", "memory_percent"])
        for process in processes:
            try:
                info = process.info
                if info.get("pid") == 0 or (info.get("name") or "").lower() == "system idle process":
                    continue
                rows.append({
                    "pid": info.get("pid"),
                    "name": info.get("name") or "Unavailable",
                    "cpu_percent": round(float(info.get("cpu_percent") or 0), 1),
                    "memory_percent": round(float(info.get("memory_percent") or 0), 2),
                })
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                continue
    except (OSError, psutil.Error):
        return []
    return sorted(rows, key=lambda item: item["cpu_percent"], reverse=True)[:limit]


def collect_system() -> Dict[str, Any]:
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()
    cpu_percent = psutil.cpu_percent(interval=None)
    per_cpu = psutil.cpu_percent(interval=None, percpu=True)
    try:
        freq = psutil.cpu_freq()
    except (AttributeError, OSError):
        freq = None
    try:
        load = list(psutil.getloadavg())
    except (AttributeError, OSError):
        load = []
    boot_time = psutil.boot_time()
    temperature, temperature_source = _temperature_reading()
    return {
        "platform": platform.platform(),
        "os": platform.system(),
        "hostname": socket.gethostname(),
        "kernel": platform.release(),
        "cpu_model": platform.processor() or "Unavailable",
        "cpu_percent": round(cpu_percent, 1),
        "per_cpu_percent": [round(item, 1) for item in per_cpu],
        "cpu_frequency_mhz": round(freq.current, 1) if freq and freq.current else None,
        "load_average": [round(item, 2) for item in load],
        "memory": {
            "total_bytes": vm.total,
            "used_bytes": vm.used,
            "available_bytes": vm.available,
            "percent": round(vm.percent, 1),
            "cached_bytes": getattr(vm, "cached", None),
        },
        "swap": {
            "total_bytes": swap.total,
            "used_bytes": swap.used,
            "free_bytes": swap.free,
            "percent": round(swap.percent, 1),
        },
        "temperature_c": temperature,
        "temperature_source": temperature_source,
        "uptime_seconds": max(0, int(time.time() - boot_time)),
        "battery": _battery(),
        "top_processes": _top_processes(),
    }


def collect_storage() -> Dict[str, Any]:
    filesystems: List[Dict[str, Any]] = []
    seen = set()
    try:
        partitions = psutil.disk_partitions(all=False)
    except (OSError, PermissionError):
        partitions = []
    for partition in partitions:
        mountpoint = partition.mountpoint
        if mountpoint in seen:
            continue
        seen.add(mountpoint)
        try:
            usage = psutil.disk_usage(mountpoint)
        except (OSError, PermissionError):
            continue
        filesystems.append(
            {
                "device": partition.device,
                "mountpoint": mountpoint,
                "fstype": partition.fstype,
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
                "percent": round(usage.percent, 1),
                "quality": "ok",
            }
        )
    block_devices = discover_block_devices()
    return {
        "filesystems": filesystems,
        "disks": block_devices.get("devices", []),
        "disk_inventory": block_devices,
        "smart": unavailable("SMART inventory requires Linux smartctl and device permissions", "smartctl"),
    }


class CollectorState:
    def __init__(self) -> None:
        self.previous_network: Dict[str, Tuple[float, float, float, float]] = {}
        self.previous_power: Dict[str, Tuple[float, float]] = {}
        self.history: Deque[Dict[str, Any]] = deque(maxlen=60)


def collect_network(state: CollectorState) -> Dict[str, Any]:
    now = time.monotonic()
    interfaces: List[Dict[str, Any]] = []
    try:
        counters = psutil.net_io_counters(pernic=True)
    except (OSError, PermissionError):
        counters = {}
    try:
        addresses_by_name = psutil.net_if_addrs()
    except (OSError, PermissionError):
        addresses_by_name = {}
    for name, counter in counters.items():
        previous = state.previous_network.get(name)
        rx_rate = counter_rate((previous[0], previous[2]), float(counter.bytes_recv), now) if previous else None
        tx_rate = counter_rate((previous[1], previous[2]), float(counter.bytes_sent), now) if previous else None
        state.previous_network[name] = (float(counter.bytes_recv), float(counter.bytes_sent), now, now)
        lower = name.lower()
        kind = "loopback" if lower.startswith("lo") or lower == "loopback" else (
            "tailscale" if lower.startswith(("tailscale", "ts")) else (
                "virtual" if lower.startswith(("docker", "veth", "br-", "zt")) else "physical"
            )
        )
        addresses = addresses_by_name.get(name, [])
        ipv4 = [item.address for item in addresses if item.family == getattr(psutil, "AF_INET", object())]
        ipv6 = [item.address.split("%", 1)[0] for item in addresses if item.family == getattr(psutil, "AF_INET6", object())]
        mac_family = getattr(psutil, "AF_LINK", None)
        mac = next((item.address for item in addresses if mac_family is not None and item.family == mac_family), None)
        interfaces.append(
            {
                "name": name,
                "kind": kind,
                "ipv4": ipv4,
                "ipv6": ipv6,
                "mac": mac,
                "bytes_recv": counter.bytes_recv,
                "bytes_sent": counter.bytes_sent,
                "packets_recv": counter.packets_recv,
                "packets_sent": counter.packets_sent,
                "errors_in": counter.errin,
                "errors_out": counter.errout,
                "rx_bytes_per_second": rx_rate,
                "tx_bytes_per_second": tx_rate,
            }
        )
    total_rx = sum(item["rx_bytes_per_second"] or 0 for item in interfaces if item["kind"] == "physical")
    total_tx = sum(item["tx_bytes_per_second"] or 0 for item in interfaces if item["kind"] == "physical")
    connection_counts: Dict[str, int] = {}
    try:
        for connection in psutil.net_connections(kind="tcp"):
            status = connection.status or "UNKNOWN"
            connection_counts[status] = connection_counts.get(status, 0) + 1
    except (OSError, PermissionError, psutil.AccessDenied):
        connection_counts = {}
    return {
        "interfaces": interfaces,
        "physical_rx_bytes_per_second": total_rx if interfaces else None,
        "physical_tx_bytes_per_second": total_tx if interfaces else None,
        "tcp_connection_counts": connection_counts,
        "note": "仅汇总 physical 接口；Tailscale 与虚拟接口单独展示，避免重复计数。",
    }


def collect_power(state: Optional[CollectorState] = None) -> Dict[str, Any]:
    # Reading energy_uj is safe and does not require invoking perf or changing
    # kernel permissions. Watts become available after two samples.
    domains: Dict[str, Dict[str, Any]] = {}
    now = time.monotonic()
    powercap = Path("/sys/class/powercap")
    if powercap.exists():
        for energy_file in powercap.glob("**/energy_uj"):
            try:
                value = int(energy_file.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                continue
            domain = energy_file.parent.name.lower().replace("intel-rapl:", "package-")
            watts = None
            if state is not None:
                watts = counter_rate(state.previous_power.get(domain), float(value), now)
                state.previous_power[domain] = (float(value), now)
            domains[domain] = {
                "available": watts is not None,
                "energy_uj": value,
                "watts": round(watts / 1_000_000, 3) if watts is not None else None,
                "unit": "W",
                "source": "sysfs-energy_uj",
                "quality": "ok" if watts is not None else "warming-up",
            }
    available_domains = [item for item in domains.values() if item.get("available")]
    return {
        "available": bool(available_domains),
        "source": "sysfs-energy_uj" if domains else "powercap",
        "reason": None if available_domains else ("等待第二次能量采样" if domains else "系统未提供 /sys/class/powercap 能量计"),
        "domains": domains,
        "package_watts": round(sum(item.get("watts") or 0 for item in available_domains), 3) if available_domains else None,
        "semantics": "Package/Cores/GPU/DRAM 不可直接相加；这里是 CPU/SoC 能量计，不等于插座输入功耗。",
    }


def _binary_status(binary: str) -> Dict[str, Any]:
    path = shutil.which(binary)
    if path:
        return {"available": True, "path": path, "status": "detected"}
    return {"available": False, "path": None, "status": "not-installed"}


def collect_vpn() -> Dict[str, Any]:
    mihomo = collect_mihomo()
    tailscale = collect_tailscale()
    return {
        "mihomo": mihomo,
        "tailscale": tailscale,
    }


def collect_services(seafile: Optional[Dict[str, Any]] = None, vpn: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    docker = _binary_status("docker")
    seafile = seafile or collect_seafile()
    vpn = vpn or collect_vpn()
    systemd = discover_systemd_services()
    docker_inventory = discover_docker_services()
    services = [
        {"name": "HomeNAS API", "category": "系统", "deployment": "本地开发", "status": "healthy", "health": "ok", "source": "built-in"},
        {"name": "Seafile CE", "category": "文件服务", "deployment": "unknown", "status": "healthy" if seafile.get("healthy") else "unknown", "health": "ok" if seafile.get("healthy") else "unavailable", "source": "configured HTTP health check" if seafile.get("configured") else "awaiting NAS audit"},
        {"name": "Mihomo", "category": "出站代理", "deployment": "unknown", "status": "healthy" if vpn["mihomo"].get("controller_available") else "unknown", "health": "ok" if vpn["mihomo"].get("controller_available") else "unavailable", "source": "fixed read-only Controller probe"},
        {"name": "Tailscale", "category": "远程访问 VPN", "deployment": "unknown", "status": "healthy" if vpn["tailscale"].get("online") is True else ("offline" if vpn["tailscale"].get("online") is False else "unknown"), "health": "ok" if vpn["tailscale"].get("online") is True else "unavailable", "source": "fixed read-only status probe"},
        {"name": "Docker", "category": "运行时", "deployment": "host", "status": "available" if docker["available"] else "not-installed", "health": "ok" if docker_inventory.get("available") else "unknown", "source": "docker ps" if docker_inventory.get("available") else "binary/socket probe"},
    ]
    if systemd.get("available"):
        for unit in systemd["services"]:
            if any(token in unit.lower() for token in ("seafile", "mihomo", "tailscale", "docker")) and unit not in {"mihomo.service", "tailscaled.service", "docker.service"}:
                services.append({"name": unit, "category": "systemd", "deployment": "systemd", "status": "healthy", "health": "unknown", "source": "systemctl"})
    return services


def collect_alerts(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []
    memory = snapshot["system"]["memory"]
    if memory["percent"] >= 90:
        alerts.append({"id": "memory-high", "severity": "warning", "title": "内存使用率较高", "detail": f"当前 {memory['percent']}%"})
    for fs in snapshot["storage"]["filesystems"]:
        if fs["percent"] >= 95:
            alerts.append({"id": f"disk-critical:{fs['mountpoint']}", "severity": "critical", "title": "文件系统空间严重不足", "detail": f"{fs['mountpoint']} 使用率 {fs['percent']}%"})
        elif fs["percent"] >= 85:
            alerts.append({"id": f"disk-warning:{fs['mountpoint']}", "severity": "warning", "title": "文件系统空间偏高", "detail": f"{fs['mountpoint']} 使用率 {fs['percent']}%"})
    temperature = snapshot["system"].get("temperature_c")
    if temperature is not None and temperature >= 95:
        alerts.append({"id": "cpu-temp-critical", "severity": "critical", "title": "CPU 温度过高", "detail": f"{temperature:.1f}°C"})
    elif temperature is not None and temperature >= 85:
        alerts.append({"id": "cpu-temp-warning", "severity": "warning", "title": "CPU 温度偏高", "detail": f"{temperature:.1f}°C"})
    if EXTERNAL_PROBES:
        tailscale = snapshot.get("vpn", {}).get("tailscale", {})
        if tailscale.get("available") and tailscale.get("online") is False:
            alerts.append({"id": "tailscale-offline", "severity": "warning", "title": "Tailscale 本机离线", "detail": "只读状态接口报告本机离线"})
        mihomo = snapshot.get("vpn", {}).get("mihomo", {})
        if mihomo.get("controller_available") is False:
            alerts.append({"id": "mihomo-unavailable", "severity": "warning", "title": "Mihomo Controller 不可用", "detail": "固定只读 version endpoint 无响应"})
        seafile = snapshot.get("seafile", {})
        if seafile.get("configured") and seafile.get("healthy") is False:
            alerts.append({"id": "seafile-unhealthy", "severity": "warning", "title": "Seafile 健康检查失败", "detail": "配置的只读健康端点不可用"})
    return alerts


def collect_snapshot(state: CollectorState, power_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    vpn = collect_vpn()
    seafile = collect_seafile()
    services = collect_services(seafile, vpn)
    snapshot = {
        "timestamp": utc_now(),
        "system": collect_system(),
        "power": power_override if power_override is not None else collect_power(state),
        "storage": collect_storage(),
        "network": collect_network(state),
        "vpn": vpn,
        "seafile": seafile,
        "services": services,
    }
    snapshot["alerts"] = collect_alerts(snapshot)
    # Keep only chart fields in the rolling history. The full snapshot contains
    # Mihomo nodes/rules and would otherwise multiply its memory footprint every
    # five seconds without providing any historical value to the dashboard.
    state.history.append({
        "timestamp": snapshot["timestamp"],
        "system": {
            "cpu_percent": snapshot["system"].get("cpu_percent"),
            "memory": {"percent": snapshot["system"].get("memory", {}).get("percent")},
        },
        "power": {"package_watts": snapshot["power"].get("package_watts")},
        "network": {
            "physical_rx_bytes_per_second": snapshot["network"].get("physical_rx_bytes_per_second"),
            "physical_tx_bytes_per_second": snapshot["network"].get("physical_tx_bytes_per_second"),
        },
    })
    return snapshot

