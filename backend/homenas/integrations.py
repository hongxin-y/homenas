"""Fixed, read-only integrations for optional NAS services.

Every command here is an explicit argv list with a short timeout. There is no
shell interpolation and no endpoint supplied by the browser. External probes
are opt-in with ``HOMENAS_ENABLE_EXTERNAL_PROBES=1`` so local development never
accidentally touches a user's running services.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any, Dict, List, Sequence
from urllib.error import URLError
from urllib.request import Request, urlopen


EXTERNAL_PROBES = os.getenv("HOMENAS_ENABLE_EXTERNAL_PROBES", "0") == "1"


def fixed_command(argv: Sequence[str], timeout: float = 3.0) -> Dict[str, Any]:
    """Run a pre-defined read-only command without invoking a shell."""
    try:
        completed = subprocess.run(
            list(argv),
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "returncode": None, "stdout": "", "stderr": str(exc)}
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def parse_tailscale_status(payload: str) -> Dict[str, Any]:
    """Reduce tailscale JSON to browser-safe health facts; omit peer names/IPs."""
    try:
        data = json.loads(payload)
    except (TypeError, ValueError):
        return {"online": None, "quality": "unavailable", "reason": "invalid tailscale JSON"}
    self_node = data.get("Self") or {}
    peers = data.get("Peer") or {}
    online = bool(self_node.get("Online")) if "Online" in self_node else None
    addresses = self_node.get("TailscaleIPs") or []
    online_peers = sum(1 for peer in peers.values() if peer.get("Online") is True) if isinstance(peers, dict) else 0
    return {
        "online": online,
        "self_ip_available": bool(addresses),
        "peer_count": len(peers) if isinstance(peers, dict) else 0,
        "online_peer_count": online_peers,
        "quality": "ok",
        "source": "tailscale status --json",
    }


def collect_tailscale() -> Dict[str, Any]:
    path = shutil.which("tailscale")
    result: Dict[str, Any] = {
        "available": bool(path),
        "path": path,
        "online": None,
        "peer_count": None,
        "online_peer_count": None,
        "detail": "只读状态；不执行 tailscale up/down/logout。",
    }
    if not path or not EXTERNAL_PROBES:
        result["reason"] = "外部探测未启用" if path else "tailscale 未安装"
        return result
    probe = fixed_command([path, "status", "--json"], timeout=4)
    if not probe["ok"]:
        result["reason"] = "tailscale status 不可用"
        return result
    result.update(parse_tailscale_status(probe["stdout"]))
    return result


def collect_mihomo() -> Dict[str, Any]:
    path = shutil.which("mihomo") or shutil.which("clash")
    controller = os.getenv("HOMENAS_MIHOMO_CONTROLLER", "").strip().rstrip("/")
    secret = os.getenv("HOMENAS_MIHOMO_SECRET", "")
    result: Dict[str, Any] = {
        "available": bool(path),
        "path": path,
        "controller_available": None,
        "mode": None,
        "detail": "Secret 仅在服务器环境变量中使用；浏览器不会收到 Secret。",
    }
    if not controller or not EXTERNAL_PROBES:
        result["reason"] = "Controller 外部探测未启用或未配置"
        return result
    # Only a fixed read-only version endpoint is called. No browser-provided URL.
    request = Request(controller + "/version", method="GET")
    if secret:
        request.add_header("Authorization", "Bearer " + secret)
    try:
        with urlopen(request, timeout=3) as response:
            body = json.loads(response.read().decode("utf-8"))
        result["controller_available"] = True
        result["version"] = body.get("version") if isinstance(body, dict) else None
    except (OSError, URLError, ValueError):
        result["controller_available"] = False
        result["reason"] = "Controller version endpoint unavailable"
    return result


def collect_seafile() -> Dict[str, Any]:
    endpoint = os.getenv("HOMENAS_SEAFILE_HEALTH_URL", "").strip()
    result: Dict[str, Any] = {
        "configured": bool(endpoint),
        "healthy": None,
        "detail": "只执行配置的 HTTP GET 健康检查，不修改 Seafile 数据。",
    }
    if not endpoint or not EXTERNAL_PROBES:
        result["reason"] = "Seafile 健康端点未配置或外部探测未启用"
        return result
    if not endpoint.startswith(("http://", "https://")):
        result["reason"] = "健康端点必须是 http(s)"
        return result
    try:
        request = Request(endpoint, method="GET")
        with urlopen(request, timeout=3) as response:
            result["status_code"] = response.status
            result["healthy"] = 200 <= response.status < 400
    except (OSError, URLError):
        result["healthy"] = False
        result["reason"] = "health endpoint unavailable"
    return result


def discover_systemd_services() -> Dict[str, Any]:
    if not EXTERNAL_PROBES or not shutil.which("systemctl"):
        return {"available": False, "services": [], "reason": "systemd 探测未启用或 systemctl 不存在"}
    probe = fixed_command(["systemctl", "list-units", "--type=service", "--state=running", "--no-legend", "--no-pager"], timeout=4)
    if not probe["ok"]:
        return {"available": False, "services": [], "reason": "systemctl 查询失败"}
    names: List[str] = []
    for line in probe["stdout"].splitlines():
        parts = line.split()
        if parts:
            names.append(parts[0])
    return {"available": True, "services": names, "source": "systemctl"}


def discover_docker_services() -> Dict[str, Any]:
    if not EXTERNAL_PROBES or not shutil.which("docker"):
        return {"available": False, "containers": [], "reason": "Docker 探测未启用或 docker 不存在"}
    probe = fixed_command(["docker", "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}"], timeout=4)
    if not probe["ok"]:
        return {"available": False, "containers": [], "reason": "Docker socket 不可用或权限不足"}
    containers = []
    for line in probe["stdout"].splitlines():
        name, _, rest = line.partition("\t")
        image, _, status = rest.partition("\t")
        containers.append({"name": name, "image": image, "status": status})
    return {"available": True, "containers": containers, "source": "docker ps"}


def discover_block_devices() -> Dict[str, Any]:
    """Read physical/partition inventory with lsblk JSON; never mutates disks."""
    if not shutil.which("lsblk"):
        return {"available": False, "devices": [], "reason": "lsblk 未安装"}
    probe = fixed_command(["lsblk", "-J", "-o", "NAME,TYPE,SIZE,MODEL,FSTYPE,MOUNTPOINTS,RO"], timeout=4)
    if not probe["ok"]:
        return {"available": False, "devices": [], "reason": "lsblk 查询失败"}
    return parse_lsblk_json(probe["stdout"])


def parse_lsblk_json(payload: str) -> Dict[str, Any]:
    try:
        raw = json.loads(payload)
    except ValueError:
        return {"available": False, "devices": [], "reason": "lsblk 返回无法解析"}

    def flatten(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for item in items:
            result.append({
                "name": item.get("name"),
                "type": item.get("type"),
                "size": item.get("size"),
                "model": item.get("model"),
                "fstype": item.get("fstype"),
                "mountpoints": item.get("mountpoints") or [],
                "read_only": item.get("ro"),
            })
            result.extend(flatten(item.get("children") or []))
        return result

    return {"available": True, "devices": flatten(raw.get("blockdevices") or []), "source": "lsblk"}

