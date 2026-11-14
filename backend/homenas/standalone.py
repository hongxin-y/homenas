"""Dependency-free local server used when FastAPI is not installed.

It intentionally exposes the same small read-only surface as the FastAPI app,
so the dashboard can be smoke-tested offline on a clean Windows workstation.
Production/NAS deployment should use ``homenas.main:app`` with FastAPI.
"""

from __future__ import annotations

import json
import mimetypes
import threading
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from .auth import AuthManager
from .collector import Collector
from .config import ADMIN_PASSWORD, DB_PATH, ELECTRICITY_PRICE_CNY_PER_KWH, FRONTEND_DIR, HOST, PORT, SESSION_TTL_SECONDS, ensure_runtime_dir
from .db import Database
from .integrations import mihomo_rule_draft, ping_target, select_mihomo_proxy
from .power_cost import parse_period, period_cost


class Runtime:
    def __init__(self, db_path: Optional[Path] = None) -> None:
        ensure_runtime_dir()
        self.db = Database(db_path or DB_PATH)
        self.collector = Collector(self.db)
        self.auth = AuthManager(ADMIN_PASSWORD, SESSION_TTL_SECONDS)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.loop, name="homenas-collector", daemon=True)

    def start(self) -> None:
        import asyncio

        asyncio.run(self.collector.start())
        self.thread.start()

    def loop(self) -> None:
        import asyncio

        while not self.stop.wait(5):
            asyncio.run(self.collector.collect_once())

    def close(self) -> None:
        self.stop.set()
        self.thread.join(timeout=2)
        import asyncio

        asyncio.run(self.collector.stop())
        self.db.close()


runtime = Runtime()


class Handler(BaseHTTPRequestHandler):
    server_version = "HomeNASLocal/0.1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    @property
    def app_runtime(self) -> Runtime:
        return self.server.runtime  # type: ignore[attr-defined]

    def json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            value = json.loads(raw.decode("utf-8"))
            return value if isinstance(value, dict) else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}

    def write_json(self, payload: Dict[str, Any], status: int = 200, headers: Optional[Dict[str, str]] = None) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def token_user(self) -> Optional[str]:
        scheme, _, token = self.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer":
            cookie = SimpleCookie()
            cookie.load(self.headers.get("Cookie", ""))
            token = cookie.get("homenas_session").value if cookie.get("homenas_session") else ""
        if scheme.lower() != "bearer":
            return self.app_runtime.auth.user_for_token(token)
        return self.app_runtime.auth.user_for_token(token)

    def require_user(self) -> bool:
        if self.token_user():
            return True
        self.write_json({"detail": "需要登录"}, 401)
        return False

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        path = {
            "/api/v1/auth/login": "/api/auth/login",
            "/api/v1/auth/logout": "/api/auth/logout",
        }.get(path, path)
        if path == "/api/auth/login":
            body = self.json_body()
            client_key = self.client_address[0]
            if not self.app_runtime.auth.login_allowed(client_key):
                self.write_json({"detail": "登录尝试过于频繁，请稍后再试"}, 429)
                return
            if body.get("username") != "admin" or not self.app_runtime.auth.verify_password(str(body.get("password", ""))):
                self.app_runtime.auth.record_login_failure(client_key)
                self.write_json({"detail": "用户名或密码错误"}, 401)
                return
            self.app_runtime.auth.clear_login_failures(client_key)
            token = self.app_runtime.auth.create_session("admin")
            self.write_json({"user": "admin"}, headers={"Set-Cookie": "homenas_session=%s; Max-Age=28800; Path=/; HttpOnly; SameSite=Lax" % token})
            return
        if path == "/api/auth/logout":
            _, _, token = self.headers.get("Authorization", "").partition(" ")
            if not token:
                cookie = SimpleCookie()
                cookie.load(self.headers.get("Cookie", ""))
                token = cookie.get("homenas_session").value if cookie.get("homenas_session") else ""
            self.app_runtime.auth.revoke(token)
            self.write_json({"ok": True}, headers={"Set-Cookie": "homenas_session=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax"})
            return
        if path == "/api/vpn/ping":
            if not self.require_user():
                return
            body = self.json_body()
            result = ping_target(str(body.get("target", "")))
            self.app_runtime.db.audit(self.token_user() or "admin", "vpn.ping", {"target": result.get("target"), "status": result.get("status")})
            self.write_json(result)
            return
        if path == "/api/vpn/mihomo/select":
            if not self.require_user():
                return
            body = self.json_body()
            result = select_mihomo_proxy(str(body.get("group", "")), str(body.get("node", "")))
            self.app_runtime.db.audit(self.token_user() or "admin", "mihomo.select", {"group": body.get("group"), "node": body.get("node"), "status": result.get("status")})
            status = 200 if result.get("ok") else (403 if result.get("status") == "read-only" else 400)
            self.write_json(result, status)
            return
        if path == "/api/vpn/mihomo/rules/draft":
            if not self.require_user():
                return
            body = self.json_body()
            result = mihomo_rule_draft(body.get("rules", []))
            self.app_runtime.db.audit(self.token_user() or "admin", "mihomo.rules_draft", {"count": result.get("count"), "ok": result.get("ok")})
            self.write_json(result)
            return
        self.write_json({"detail": "Not found"}, 404)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        path = {
            "/health": "/api/health",
            "/api/v1/health": "/api/health",
            "/api/v1/auth/me": "/api/auth/me",
            "/api/v1/system/summary": "/api/system",
            "/api/v1/system/cpu": "/api/system",
            "/api/v1/system/memory": "/api/system",
            "/api/v1/system/temperatures": "/api/system",
            "/api/v1/power/current": "/api/power",
            "/api/v1/power/daily": "/api/power/daily",
            "/api/v1/power/cost": "/api/power/cost",
            "/api/v1/storage/filesystems": "/api/storage",
            "/api/v1/storage/devices": "/api/storage",
            "/api/v1/network/interfaces": "/api/network",
            "/api/v1/network/traffic": "/api/network",
            "/api/v1/vpn/mihomo/status": "/api/vpn",
            "/api/v1/vpn/tailscale/status": "/api/vpn",
            "/api/v1/services": "/api/services",
            "/api/v1/alerts": "/api/alerts",
        }.get(path, path)
        if path == "/api/health":
            latest = self.app_runtime.collector.latest or {}
            self.write_json({"status": "ok", "service": "homenas-local", "timestamp": latest.get("timestamp")})
            return
        if path == "/api/auth/me":
            if self.require_user():
                self.write_json({"user": self.token_user()})
            return
        if path == "/api/overview":
            if not self.require_user():
                return
            latest = self.app_runtime.collector.latest or {}
            history = self.app_runtime.collector.state.history
            self.write_json({
                **latest,
                "history": [
                    {"timestamp": x.get("timestamp"), "cpu_percent": x.get("system", {}).get("cpu_percent"), "memory_percent": x.get("system", {}).get("memory", {}).get("percent"), "rx": x.get("network", {}).get("physical_rx_bytes_per_second"), "tx": x.get("network", {}).get("physical_tx_bytes_per_second"), "power_watts": x.get("power", {}).get("package_watts")}
                    for x in history
                ],
            })
            return
        if path == "/api/power/daily":
            if self.require_user():
                self.write_json(self.app_runtime.db.energy_summary())
            return
        if path == "/api/power/cost":
            if not self.require_user():
                return
            try:
                start, end = parse_period((query.get("start") or [None])[0], (query.get("end") or [None])[0])
            except ValueError as exc:
                self.write_json({"detail": str(exc)}, 400)
                return
            price_value = (query.get("price") or [None])[0]
            try:
                price = float(price_value) if price_value is not None else ELECTRICITY_PRICE_CNY_PER_KWH
            except ValueError:
                price = ELECTRICITY_PRICE_CNY_PER_KWH
            summary = self.app_runtime.db.energy_period(start, end)
            self.write_json(period_cost(summary, price, start, end))
            return
        if path == "/api/alerts":
            if self.require_user():
                self.write_json({"alerts": self.app_runtime.db.list_alerts(), "events": self.app_runtime.db.list_alert_events()})
            return
        if path in {"/api/system", "/api/power", "/api/storage", "/api/network", "/api/vpn", "/api/seafile", "/api/services"}:
            if not self.require_user():
                return
            latest = self.app_runtime.collector.latest or {}
            key = path.rsplit("/", 1)[-1]
            payload = {"services": latest.get("services", [])} if key == "services" else latest.get(key, {})
            self.write_json(payload)
            return
        if path.startswith("/static/") or path == "/" or not path.startswith("/api/"):
            relative = "index.html" if path == "/" else path[1:]
            candidate = (FRONTEND_DIR / relative).resolve()
            if FRONTEND_DIR.resolve() not in candidate.parents and candidate != FRONTEND_DIR.resolve() / "index.html":
                self.write_json({"detail": "Not found"}, 404)
                return
            if candidate.is_file():
                data = candidate.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(str(candidate))[0] or "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
        self.write_json({"detail": "Not found"}, 404)


def serve(host: str = HOST, port: int = PORT) -> None:
    runtime.start()
    server = ThreadingHTTPServer((host, port), Handler)
    server.runtime = runtime  # type: ignore[attr-defined]
    print(f"HomeNAS local fallback server listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        runtime.close()


if __name__ == "__main__":
    serve()

