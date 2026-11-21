#!/usr/bin/env python3
"""Minimal root helper for the fixed HomeNAS Mihomo rules operation.

The HomeNAS API never sends a path, command or Mihomo secret. The helper owns
the fixed config path, validates rule lines again, creates a root-owned backup,
atomically replaces only the top-level rules list, and asks Mihomo to reload.
"""

from __future__ import annotations

import json
import os
import re
import signal
import socketserver
import stat
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SOCKET_PATH = Path(os.getenv("HOMENAS_MIHOMO_HELPER_SOCKET", "/run/homenas-mihomo/rules.sock"))
CONFIG_PATH = Path(os.getenv("HOMENAS_MIHOMO_CONFIG_PATH", "/etc/mihomo/config.yaml"))
BACKUP_DIR = Path(os.getenv("HOMENAS_MIHOMO_BACKUP_DIR", "/var/lib/homenas/mihomo-backups"))
CONTROLLER = os.getenv("HOMENAS_MIHOMO_CONTROLLER", "http://127.0.0.1:9090").rstrip("/")
SECRET_FILE = os.getenv("HOMENAS_MIHOMO_SECRET_FILE", "").strip()
API_USER = os.getenv("HOMENAS_API_USER", "hongxin")
MAX_RULES = 500


def _secret() -> str:
    if SECRET_FILE:
        try:
            return Path(SECRET_FILE).read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return os.getenv("HOMENAS_MIHOMO_SECRET", "")


def _normalize_rules(value: Any) -> Tuple[List[str], List[str]]:
    values = value if isinstance(value, list) else []
    clean: List[str] = []
    errors: List[str] = []
    if len(values) > MAX_RULES:
        return [], [f"规则数量不能超过 {MAX_RULES} 条"]
    for index, raw in enumerate(values, start=1):
        line = str(raw).strip()
        if not line:
            continue
        if len(line) > 1024 or "\r" in line or "\n" in line:
            errors.append(f"第 {index} 行长度或字符无效")
            continue
        if not line.startswith("#") and len(line.split(",")) < 2:
            errors.append(f"第 {index} 行不是可识别的 Mihomo 规则格式")
            continue
        clean.append(line)
    return clean, errors


def _replace_top_level_rules(text: str, rules: List[str]) -> str:
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if re.match(r"^rules\s*:", line)), None)
    replacement = ["rules:"] + [f"  - {json.dumps(rule, ensure_ascii=False)}" for rule in rules]
    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(replacement)
    elif not re.match(r"^rules\s*:\s*(?:#.*)?$", lines[start]):
        lines[start:start + 1] = replacement
    else:
        end = start + 1
        while end < len(lines):
            if re.match(r"^[^\s#][^:]*\s*:", lines[end]):
                break
            end += 1
        lines[start:end] = replacement
    return "\n".join(lines).rstrip("\n") + "\n"


def _atomic_write(path: Path, content: bytes, mode: int) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.homenas-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _reload() -> Tuple[bool, str]:
    request = Request(
        CONTROLLER + "/configs?force=true",
        data=json.dumps({"path": "", "payload": ""}).encode("utf-8"),
        method="PUT",
        headers={"Content-Type": "application/json"},
    )
    secret = _secret()
    if secret:
        request.add_header("Authorization", "Bearer " + secret)
    try:
        with urlopen(request, timeout=5):
            return True, ""
    except (OSError, HTTPError, URLError) as exc:
        return False, str(exc)


def apply_rules(value: Any) -> Dict[str, Any]:
    rules, errors = _normalize_rules(value)
    if errors or not rules:
        return {"ok": False, "status": "invalid-rules", "errors": errors or ["至少需要一条规则"], "detail": "规则未写入"}
    if not CONFIG_PATH.is_absolute() or CONFIG_PATH.is_symlink() or not CONFIG_PATH.is_file():
        return {"ok": False, "status": "config-unavailable", "detail": "固定 Mihomo 配置文件不可用"}
    try:
        original = CONFIG_PATH.read_bytes()
        mode = stat.S_IMODE(CONFIG_PATH.stat().st_mode)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(BACKUP_DIR, 0o700)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = BACKUP_DIR / f"{CONFIG_PATH.name}.{stamp}.bak"
        backup.write_bytes(original)
        os.chmod(backup, 0o600)
        updated = _replace_top_level_rules(original.decode("utf-8"), rules).encode("utf-8")
        _atomic_write(CONFIG_PATH, updated, mode)
    except (OSError, UnicodeDecodeError) as exc:
        return {"ok": False, "status": "write-failed", "detail": f"配置文件写入失败：{exc}"}
    ok, detail = _reload()
    if not ok:
        try:
            _atomic_write(CONFIG_PATH, original, mode)
        except OSError:
            return {"ok": False, "status": "rollback-failed", "detail": "reload 失败且自动回滚失败", "backup": backup.name}
        return {"ok": False, "status": "reload-failed", "detail": f"Mihomo reload 失败，配置已回滚：{detail}", "backup": backup.name}
    return {"ok": True, "status": "applied", "persistent": True, "count": len(rules), "backup": backup.name, "detail": f"已写入 {len(rules)} 条规则并 reload Mihomo"}


class RequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        try:
            raw = self.rfile.readline(2 * 1024 * 1024)
            body = json.loads(raw.decode("utf-8"))
            result = apply_rules(body.get("rules", [])) if body.get("action") == "apply_rules" else {"ok": False, "status": "invalid-action", "detail": "不支持的 helper 操作"}
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            result = {"ok": False, "status": "invalid-request", "detail": "helper 请求格式无效"}
        self.wfile.write((json.dumps(result, ensure_ascii=False) + "\n").encode("utf-8"))


# Windows does not expose UnixStreamServer. Keeping the fallback only makes
# the pure validation/writeback functions importable for local tests; main()
# still refuses to start outside a POSIX NAS.
_UnixStreamServer = getattr(socketserver, "UnixStreamServer", socketserver.TCPServer)


class UnixServer(socketserver.ThreadingMixIn, _UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> None:
    if os.name != "posix" or not hasattr(socketserver, "UnixStreamServer"):
        raise SystemExit("Mihomo helper requires a POSIX Unix socket")
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        SOCKET_PATH.unlink()
    except FileNotFoundError:
        pass
    server = UnixServer(str(SOCKET_PATH), RequestHandler)
    os.chmod(SOCKET_PATH, 0o660)
    try:
        import grp
        import pwd
        os.chown(SOCKET_PATH, pwd.getpwnam(API_USER).pw_uid, grp.getgrnam(API_USER).gr_gid)
    except (ImportError, KeyError, OSError):
        pass
    def request_shutdown(_signum: int, _frame: Any) -> None:
        # socketserver.shutdown() must run from a different thread than
        # serve_forever(); calling it directly from a signal handler deadlocks
        # the helper during a normal systemd stop/restart.
        threading.Thread(target=server.shutdown, name="homenas-mihomo-helper-stop", daemon=True).start()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        try:
            SOCKET_PATH.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
