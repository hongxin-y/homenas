"""Offline smoke test that needs only Python + psutil (no pip/network)."""

from __future__ import print_function

import json
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from homenas.metrics import CollectorState, collect_network, counter_rate, parse_perf_csv  # noqa: E402
from homenas.integrations import parse_lsblk_json, parse_tailscale_status  # noqa: E402
from homenas.db import Database  # noqa: E402
from homenas.auth import AuthManager  # noqa: E402
from homenas.standalone import Handler, Runtime  # noqa: E402


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    parsed = parse_perf_csv("1.25,,Joules,power/energy-pkg/,100\n<not supported>,,Joules,power/energy-ram/,100\n")
    assert_true(parsed["pkg"]["value"] == 1.25, "perf parser")
    assert_true(parsed["ram"]["value"] is None, "missing perf value must stay unavailable")
    assert_true(counter_rate((100, 1), 130, 4) == 10, "counter rate")
    assert_true(counter_rate((100, 1), 90, 4) is None, "counter reset")
    assert_true("interfaces" in collect_network(CollectorState()), "network collector")
    tailscale = parse_tailscale_status('{"Self":{"Online":true},"Peer":{"a":{"Online":true}}}')
    assert_true(tailscale["online_peer_count"] == 1, "tailscale parser")
    lsblk = parse_lsblk_json('{"blockdevices":[{"name":"sda","type":"disk","children":[{"name":"sda1","type":"part"}]}]}')
    assert_true([item["name"] for item in lsblk["devices"]] == ["sda", "sda1"], "lsblk parser")
    auth = AuthManager("secret", 60)
    for _ in range(5):
        auth.record_login_failure("smoke")
    assert_true(not auth.login_allowed("smoke"), "login rate limit")

    with tempfile.TemporaryDirectory() as folder:
        db = Database(Path(folder) / "wal.db")
        db.add_metric_samples([{"metric": "cpu.percent", "value": 42, "unit": "%", "source": "smoke"}])
        assert_true(db.recent_metrics("cpu.percent")[0]["value"] == 42, "sqlite metric")
        assert_true(db.conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal", "sqlite WAL")
        db.write_alerts([{"id": "smoke-alert", "severity": "warning", "title": "Smoke", "detail": "test"}])
        db.write_alerts([])
        assert_true({event["event"] for event in db.list_alert_events()} >= {"opened", "recovered"}, "alert history")
        db.close()
        runtime = Runtime(Path(folder) / "homenas.db")
        runtime.start()
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.runtime = runtime
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = "http://127.0.0.1:%s" % server.server_port
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
        try:
            with opener.open(base + "/api/health") as response:
                assert_true(json.loads(response.read())["status"] == "ok", "health endpoint")
            request = urllib.request.Request(base + "/api/auth/login", data=json.dumps({"username": "admin", "password": "admin"}).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
            with opener.open(request) as response:
                assert_true("homenas_session" in ";".join(response.headers.get_all("Set-Cookie") or []), "HttpOnly session cookie")
            request = urllib.request.Request(base + "/api/overview")
            with opener.open(request) as response:
                data = json.loads(response.read())
                assert_true("system" in data and "storage" in data and "network" in data, "overview endpoint")
            with opener.open(base + "/api/v1/system/summary") as response:
                assert_true("cpu_percent" in json.loads(response.read()), "v1 compatibility endpoint")
            with opener.open(base + "/api/v1/power/daily") as response:
                assert_true("total_wh" in json.loads(response.read()), "power daily endpoint")
            with opener.open(base + "/api/power/cost?start=2026-01-01&end=2026-01-01&tier=1") as response:
                cost = json.loads(response.read())
                assert_true("package_cost_cny" in cost and cost["tariff"]["id"] == "shanghai_residential_time_of_use", "power cost endpoint")
            request = urllib.request.Request(base + "/api/vpn/mihomo/rules/draft", data=json.dumps({"rules": ["DOMAIN-SUFFIX,example.com,Proxy"]}).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
            with opener.open(request) as response:
                assert_true(json.loads(response.read())["ok"] is True, "mihomo rule draft endpoint")
            request = urllib.request.Request(base + "/api/vpn/mihomo/select", data=json.dumps({"group": "Proxy", "node": "Node"}).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
            try:
                opener.open(request)
                raise AssertionError("read-only Mihomo select should be blocked")
            except urllib.error.HTTPError as error:
                assert_true(error.code == 403, "read-only Mihomo select guard")
            request = urllib.request.Request(base + "/api/vpn/ping", data=json.dumps({"target": "127.0.0.1"}).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
            with opener.open(request) as response:
                assert_true(json.loads(response.read())["status"] == "reachable", "authenticated ping endpoint")
        finally:
            server.shutdown()
            server.server_close()
            runtime.close()
    print("Smoke tests passed")


if __name__ == "__main__":
    main()

