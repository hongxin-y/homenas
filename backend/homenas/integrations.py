"""Fixed, read-only integrations for optional NAS services.

Every command here is an explicit argv list with a short timeout. There is no
shell interpolation and no endpoint supplied by the browser. External probes
are opt-in with ``HOMENAS_ENABLE_EXTERNAL_PROBES=1`` so local development never
accidentally touches a user's running services.
"""

from __future__ import annotations

import json
import os
import ipaddress
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import quote
from urllib.error import URLError
from urllib.request import Request, urlopen


EXTERNAL_PROBES = os.getenv("HOMENAS_ENABLE_EXTERNAL_PROBES", "0") == "1"
MIHOMO_MUTATIONS_ENABLED = os.getenv("HOMENAS_ENABLE_MIHOMO_MUTATIONS", "0") == "1"


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


def _controller_call(controller: str, path: str, secret: str = "", method: str = "GET", payload: Optional[Dict[str, Any]] = None, timeout: float = 3.0) -> Dict[str, Any]:
    """Call a fixed Mihomo Controller endpoint without exposing credentials."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = Request(controller.rstrip("/") + path, data=body, method=method)
    if body is not None:
        request.add_header("Content-Type", "application/json")
    if secret:
        request.add_header("Authorization", "Bearer " + secret)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            body_json = json.loads(raw) if raw else {}
        return {"ok": True, "status": response.status, "body": body_json if isinstance(body_json, dict) else {}}
    except (OSError, URLError, ValueError, UnicodeDecodeError) as exc:
        return {"ok": False, "status": None, "body": {}, "detail": str(exc)}


def _controller_json(controller: str, path: str, secret: str = "", timeout: float = 3.0) -> Dict[str, Any]:
    result = _controller_call(controller, path, secret=secret, timeout=timeout)
    body = result.get("body")
    return body if isinstance(body, dict) else {}


def _mihomo_rules(body: Dict[str, Any]) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for raw in body.get("rules") or []:
        if not isinstance(raw, dict):
            continue
        extra = raw.get("extra") if isinstance(raw.get("extra"), dict) else {}
        rows.append({
            "index": raw.get("index"),
            "type": raw.get("type"),
            "payload": raw.get("payload"),
            "proxy": raw.get("proxy"),
            "size": raw.get("size"),
            "disabled": bool(extra.get("disabled", False)),
            "hit_count": extra.get("hitCount", 0),
            "hit_at": extra.get("hitAt"),
            "miss_count": extra.get("missCount", 0),
            "miss_at": extra.get("missAt"),
        })
    return {"available": bool(rows or "rules" in body), "count": len(rows), "rules": rows, "source": "mihomo /rules"}


def _mihomo_proxies(body: Dict[str, Any]) -> Dict[str, Any]:
    proxies = body.get("proxies") if isinstance(body.get("proxies"), dict) else {}
    groups: List[Dict[str, Any]] = []
    nodes: List[Dict[str, Any]] = []
    group_types = {"Selector", "URLTest", "Fallback", "LoadBalance", "Relay", "Smart"}
    for name, raw in proxies.items():
        if not isinstance(raw, dict):
            continue
        kind = raw.get("type") or "Unknown"
        all_nodes = raw.get("all") if isinstance(raw.get("all"), list) else []
        if kind in group_types:
            groups.append({
                "name": name,
                "type": kind,
                "now": raw.get("now"),
                "node_count": len(all_nodes),
                # Keep enough names for a human to inspect a large regional
                # group in the dashboard; this remains metadata-only and
                # does not expose controller credentials.
                "nodes": all_nodes[:200],
                "nodes_truncated": len(all_nodes) > 200,
            })
        else:
            history = raw.get("history") if isinstance(raw.get("history"), list) else []
            delay = history[-1].get("delay") if history and isinstance(history[-1], dict) else None
            nodes.append({
                "name": name,
                "type": kind,
                "alive": raw.get("alive"),
                "udp": raw.get("udp"),
                "delay_ms": delay,
            })
    groups.sort(key=lambda item: str(item["name"]))
    nodes.sort(key=lambda item: str(item["name"]))
    return {
        "available": bool(body),
        "count": len(nodes),
        "group_count": len(groups),
        "groups": groups,
        "nodes": nodes,
        "source": "mihomo /proxies",
    }


def _valid_mihomo_name(value: str) -> bool:
    return bool(value and len(value) <= 256 and not any(ord(ch) < 32 for ch in value))


def select_mihomo_proxy(group: str, node: str) -> Dict[str, Any]:
    """Select a node only when an explicit mutation opt-in is enabled."""
    group = str(group or "").strip()
    node = str(node or "").strip()
    if not _valid_mihomo_name(group) or not _valid_mihomo_name(node):
        return {"ok": False, "status": "invalid-input", "detail": "代理组或节点名称无效"}
    if not MIHOMO_MUTATIONS_ENABLED:
        return {"ok": False, "status": "read-only", "detail": "项目当前保持 Mihomo 只读；未启用配置变更"}
    controller = os.getenv("HOMENAS_MIHOMO_CONTROLLER", "").strip().rstrip("/")
    secret = os.getenv("HOMENAS_MIHOMO_SECRET", "")
    if not controller or not EXTERNAL_PROBES:
        return {"ok": False, "status": "unavailable", "detail": "Controller 外部探测未启用或未配置"}
    result = _controller_call(controller, "/proxies/" + quote(group, safe=""), secret=secret, method="PUT", payload={"name": node})
    if not result.get("ok"):
        return {"ok": False, "status": "controller-error", "detail": "Controller 节点切换失败"}
    return {"ok": True, "status": "selected", "group": group, "node": node, "detail": "节点切换请求已发送"}


def mihomo_rule_draft(rules: Any) -> Dict[str, Any]:
    """Validate a rule draft without writing any Mihomo configuration."""
    if isinstance(rules, str):
        values = rules.splitlines()
    elif isinstance(rules, list):
        values = [str(item) for item in rules]
    else:
        values = []
    clean: List[str] = []
    errors: List[str] = []
    for index, raw in enumerate(values, start=1):
        line = raw.strip()
        if not line:
            continue
        if len(line) > 1024 or "\r" in line or "\n" in line:
            errors.append(f"第 {index} 行长度或字符无效")
            continue
        if not line.startswith("#") and len(line.split(",")) < 2:
            errors.append(f"第 {index} 行不是可识别的 Mihomo 规则格式")
            continue
        clean.append(line)
    return {
        "ok": not errors and bool(clean),
        "rules": clean,
        "count": len(clean),
        "errors": errors,
        "apply_enabled": False,
        "detail": "规则草稿仅在 HomeNAS 本地校验，当前不会写入 Mihomo 配置。",
    }


def _valid_ping_target(target: str) -> bool:
    if not target or len(target) > 253 or any(ch.isspace() for ch in target):
        return False
    try:
        ipaddress.ip_address(target)
        return True
    except ValueError:
        pass
    return bool(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", target)) and ".." not in target


def ping_target(target: str) -> Dict[str, Any]:
    """Run one bounded, shell-free ICMP probe requested by an authenticated user."""
    target = str(target or "").strip()
    if not _valid_ping_target(target):
        return {"ok": False, "target": target[:253], "status": "invalid-target", "detail": "请输入合法的 IP 地址或主机名"}
    ping = shutil.which("ping")
    if not ping:
        return {"ok": False, "target": target, "status": "unavailable", "detail": "系统未安装 ping"}
    argv = [ping, "-n", "1", "-w", "2000", target] if os.name == "nt" else [ping, "-c", "1", "-W", "2", target]
    result = fixed_command(argv, timeout=4.0)
    output = (result.get("stdout") or "") + "\n" + (result.get("stderr") or "")
    match = re.search(r"(?:time|时间)[=<]\s*([0-9]+(?:\.[0-9]+)?)\s*ms", output, re.IGNORECASE)
    if result.get("ok"):
        return {"ok": True, "target": target, "status": "reachable", "latency_ms": float(match.group(1)) if match else None, "detail": "Ping 成功"}
    return {"ok": False, "target": target, "status": "unreachable", "latency_ms": float(match.group(1)) if match else None, "detail": "目标无响应或 ICMP 被拦截"}


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


def _tailscale_peer_summary(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    peers = data.get("Peer") or {}
    rows: List[Dict[str, Any]] = []
    if not isinstance(peers, dict):
        return rows
    for peer in peers.values():
        if not isinstance(peer, dict):
            continue
        dns_name = str(peer.get("DNSName") or peer.get("HostName") or "").rstrip(".")
        rows.append({
            "name": str(peer.get("HostName") or dns_name or "Unnamed peer"),
            "dns_name": dns_name or None,
            "online": peer.get("Online") if isinstance(peer.get("Online"), bool) else None,
            "last_seen": peer.get("LastSeen"),
            "relay": peer.get("CurAddr") or peer.get("Relay") or None,
            "exit_node": bool(peer.get("ExitNode")),
        })
    return sorted(rows, key=lambda row: (not bool(row.get("online")), str(row.get("name"))))


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
    try:
        payload = json.loads(probe["stdout"])
        result["peers"] = _tailscale_peer_summary(payload)
    except (TypeError, ValueError):
        result["peers"] = []
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
        "version": None,
        "config": {},
        "rules": {"available": False, "count": 0, "rules": [], "reason": "Controller 未连接"},
        "proxies": {"available": False, "count": 0, "group_count": 0, "groups": [], "nodes": [], "reason": "Controller 未连接"},
        "detail": "Secret 仅在服务器环境变量中使用；浏览器不会收到 Secret。",
        "mutation_enabled": MIHOMO_MUTATIONS_ENABLED,
        "mutation_detail": "节点切换需要显式启用 HOMENAS_ENABLE_MIHOMO_MUTATIONS；规则编辑当前仅支持本地草稿。",
    }
    if not controller or not EXTERNAL_PROBES:
        result["reason"] = "Controller 外部探测未启用或未配置"
        return result
    # Only fixed read-only endpoints are called. No browser-provided URL or path.
    version = _controller_json(controller, "/version", secret)
    if not version:
        result["controller_available"] = False
        result["reason"] = "Controller version endpoint unavailable"
        return result
    result["controller_available"] = True
    result["version"] = version.get("version")
    configs = _controller_json(controller, "/configs", secret)
    result["mode"] = configs.get("mode")
    result["config"] = {
        key: configs.get(key)
        for key in ("port", "socks-port", "redir-port", "tproxy-port", "mixed-port", "allow-lan", "bind-address", "tun")
        if key in configs
    }
    result["rules"] = _mihomo_rules(_controller_json(controller, "/rules", secret))
    result["proxies"] = _mihomo_proxies(_controller_json(controller, "/proxies", secret))
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

