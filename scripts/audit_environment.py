# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import psutil


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def binary(name: str) -> Dict[str, Any]:
    path = shutil.which(name)
    return {"installed": bool(path), "path": path}


def audit() -> Dict[str, Any]:
    is_linux = platform.system().lower() == "linux"
    vm = psutil.virtual_memory()
    disks = []
    for partition in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(partition.mountpoint)
        except OSError:
            continue
        disks.append({"device": partition.device, "mountpoint": partition.mountpoint, "fstype": partition.fstype, "total": usage.total, "used": usage.used, "free": usage.free, "percent": usage.percent})
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": socket.gethostname(),
        "confirmed_target_nas": is_linux,
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "python": sys.version.split()[0],
        "cpu": {"model": platform.processor(), "logical": psutil.cpu_count(), "physical": psutil.cpu_count(logical=False)},
        "memory": {"total": vm.total, "available": vm.available, "percent": vm.percent},
        "disks": disks,
        "network_interfaces": sorted(psutil.net_if_addrs().keys()),
        "binaries": {name: binary(name) for name in ["perf", "smartctl", "nvme", "tailscale", "mihomo", "docker", "systemctl", "nginx", "caddy"]},
        "sensors": {"temperature": hasattr(psutil, "sensors_temperatures"), "battery": hasattr(psutil, "sensors_battery") and psutil.sensors_battery() is not None},
        "linux_paths": {"sys_class_powercap": Path("/sys/class/powercap").exists(), "sys_class_power_supply": Path("/sys/class/power_supply").exists()},
        "constraints": [
            "此审计仅观察当前 Codex 终端所在主机。Windows 开发机不能代表 Debian NAS。",
            "未执行 systemctl、tailscale、mihomo、smartctl、perf、docker 等命令，不读取 Secret，不修改服务。",
        ],
    }


def _mb(value: Any) -> str:
    if value is None:
        return "Unavailable"
    return f"{float(value) / (1024 ** 2):,.1f} MiB"


def write_docs(report: Dict[str, Any]) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    status = "是" if report["confirmed_target_nas"] else "否"
    lines = [
        "# Phase 0 环境审计报告",
        "",
        f"生成时间（UTC）：`{report['generated_at']}`",
        f"主机名：`{report['host']}`",
        f"确认当前终端就是目标 Debian NAS：**{status}**",
        "",
        "> 当前工作站是 Windows 开发环境，因此以下结果只用于确认开发环境，不得当作目标 NAS 的硬件和服务事实。目标 NAS 需要在其本机重新执行同一脚本后再进入部署审计。",
        "",
        "## 已确认",
        "",
        f"- 平台：`{report['platform']}`",
        f"- Python：`{report['python']}`",
        f"- CPU：`{report['cpu']['model'] or 'Unavailable'}`，逻辑线程 `{report['cpu']['logical']}`，物理核心 `{report['cpu']['physical']}`",
        f"- 内存：总量 `{_mb(report['memory']['total'])}`，可用 `{_mb(report['memory']['available'])}`，当前使用率 `{report['memory']['percent']}%`",
        f"- 网卡：{', '.join(report['network_interfaces']) or 'Unavailable'}",
        f"- 温度传感器接口：`{report['sensors']['temperature']}`；电池对象：`{report['sensors']['battery']}`",
        "",
        "## 工具探测（未执行）",
        "",
        "| 工具 | 是否在 PATH | 路径 |",
    ]
    lines.append("|---|---:|---|")
    for name, value in report["binaries"].items():
        lines.append(f"| `{name}` | {'是' if value['installed'] else '否'} | `{value['path'] or 'Unavailable'}` |")
    lines += ["", "## 磁盘和文件系统（当前开发机）", "", "| 设备 | 挂载点 | 文件系统 | 使用率 |", "|---|---|---|---:|"]
    for disk in report["disks"]:
        lines.append(f"| `{disk['device']}` | `{disk['mountpoint']}` | `{disk['fstype']}` | {disk['percent']}% |")
    if not report["disks"]:
        lines.append("| Unavailable | Unavailable | Unavailable | — |")
    lines += [
        "",
        "## 未确认事实",
        "",
        "- Debian/Linux kernel、perf RAPL 事件、SMART 权限、Mihomo Controller、Tailscale 状态、Seafile 部署方式、Docker、systemd、现有反向代理和防火墙状态均未在目标 NAS 本机确认。",
        "- 本次没有安装包、启动服务、修改网络、读取敏感配置或重启任何现有服务。",
        "",
        "## 可复现命令",
        "",
        "```powershell",
        "python scripts\\audit_environment.py",
        "```",
        "",
    ]
    (DOCS / "environment-report.md").write_text("\n".join(lines), encoding="utf-8")

    (DOCS / "service-inventory-initial.md").write_text(
        """# 初始服务资产清单\n\n| 服务 | 当前结论 | 依据 |\n|---|---|---|\n| HomeNAS API | 本地开发中 | 项目自身健康端点 |\n| Seafile CE | 未确认 | 目标 NAS 需审计部署方式和健康地址 |\n| Mihomo | 未确认 | 只读探测二进制和固定 Controller 配置；不读取 Secret |\n| Tailscale | 未确认 | 只读探测二进制和状态接口 |\n| Docker | 未确认 | 目标 NAS 需检查 Docker 是否安装 |\n| 现有反向代理 | 未确认 | 不扫描、不修改监听配置 |\n\n端口开放不能单独证明服务身份；第一版只保留固定白名单服务条目。\n""",
        encoding="utf-8",
    )
    (DOCS / "network-and-access-report.md").write_text(
        """# 网络与访问报告\n\n- 本地开发 API 默认监听 `127.0.0.1:8787`。\n- 没有新增公网端口、修改防火墙、修改路由或接管现有反向代理。\n- 目标形态是先通过现有 VPN/Tailscale 访问 NAS，再由现有反向代理转发到 HomeNAS；这需要在目标机确认监听范围后单独评审。\n- Tailscale 虚拟接口和物理接口在数据模型中分开，不能盲目相加。\n""",
        encoding="utf-8",
    )
    (DOCS / "risks-and-decisions.md").write_text(
        """# 风险与决策\n\n+## 已做决策\n+\n+1. 先完成 Phase 0 只读审计，再考虑 NAS 部署。\n+2. API 和 Collector 分离；本地版 Collector 使用 psutil，perf/RAPL 仅保留解析器和诊断状态。\n+3. 缺失值使用 `null`/`Unavailable`，不以 0 代替。\n+4. Mihomo、Tailscale、Seafile、SMART、Docker 均为可选依赖，缺失时页面继续工作。\n+5. 所有管理能力当前关闭；没有任意命令执行、YAML 编辑、服务重启、路由或防火墙修改。\n+\n+## 待目标 NAS 审计后决定\n+\n+- perf 权限、RAPL 事件和长生命周期采集方案。\n+- SMART/nvme 的窄权限读取方案。\n+- Seafile 的实际健康端点和部署方式。\n+- Mihomo Controller 地址、只读 API 白名单和 Secret 存放位置。\n+- 现有反向代理接入位置。\n+\n+## 回滚\n+\n+当前没有 NAS 变更；停止本地 uvicorn 进程并删除 `runtime/` 即可清理本地运行状态。未来任何 NAS 变更必须先备份自身配置、明确影响和回滚命令，并单独批准。\n""",
        encoding="utf-8",
    )


if __name__ == "__main__":
    report = audit()
    write_docs(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Wrote reports to {DOCS}")

