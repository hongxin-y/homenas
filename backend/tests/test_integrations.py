import json

import homenas.integrations as integrations
from homenas.integrations import (
    MihomoTrafficTracker,
    _replace_top_level_rules,
    aggregate_mihomo_domain,
    parse_lsblk_json,
    parse_tailscale_status,
)


def test_tailscale_parser_returns_counts_without_peer_identity():
    result = parse_tailscale_status(json.dumps({
        "Self": {"Online": True, "TailscaleIPs": ["100.64.0.1"]},
        "Peer": {"node-a": {"Online": True}, "node-b": {"Online": False}},
    }))
    assert result["online"] is True
    assert result["peer_count"] == 2
    assert result["online_peer_count"] == 1
    assert "node-a" not in result


def test_tailscale_parser_rejects_invalid_json():
    result = parse_tailscale_status("not-json")
    assert result["online"] is None
    assert result["quality"] == "unavailable"


def test_lsblk_parser_flattens_read_only_inventory():
    result = parse_lsblk_json('{"blockdevices":[{"name":"sda","type":"disk","size":"1T","ro":false,"children":[{"name":"sda1","type":"part","mountpoints":["/srv"]}]}]}')
    assert result["available"] is True
    assert [item["name"] for item in result["devices"]] == ["sda", "sda1"]


def test_mihomo_traffic_tracker_uses_deltas_and_aggregates_subdomains():
    tracker = MihomoTrafficTracker()
    first = tracker.sample({
        "connections": [
            {"id": "one", "metadata": {"host": "api.example.com"}, "upload": 100, "download": 500},
            {"id": "two", "metadata": {"host": "www.example.com"}, "upload": 50, "download": 200},
        ]
    }, sampled_at="2026-01-01T00:00:00+00:00")
    assert first["_sample_records"] == []
    second = tracker.sample({
        "connections": [
            {"id": "one", "metadata": {"host": "api.example.com"}, "upload": 300, "download": 900},
            {"id": "two", "metadata": {"host": "www.example.com"}, "upload": 100, "download": 300},
        ]
    }, sampled_at="2026-01-01T00:00:05+00:00")
    assert second["interval_upload_bytes"] == 250
    assert second["interval_download_bytes"] == 500
    assert [row["domain"] for row in second["_sample_records"]] == ["example.com", "example.com"]
    assert aggregate_mihomo_domain("edge.example.co.uk") == "example.co.uk"


def test_mihomo_traffic_tracker_treats_counter_reset_as_new_interval():
    tracker = MihomoTrafficTracker()
    tracker.sample({"connections": [{"id": "one", "metadata": {"host": "example.com"}, "upload": 100, "download": 100}]})
    result = tracker.sample({"connections": [{"id": "one", "metadata": {"host": "example.com"}, "upload": 10, "download": 25}]})
    assert result["interval_upload_bytes"] == 10
    assert result["interval_download_bytes"] == 25


def test_collect_mihomo_accepts_null_connections_as_empty_snapshot(monkeypatch):
    monkeypatch.setattr(integrations, "EXTERNAL_PROBES", True)
    monkeypatch.setenv("HOMENAS_MIHOMO_CONTROLLER", "http://127.0.0.1:9090")

    def controller_json(_controller, path, _secret, timeout=3.0):
        if path == "/version":
            return {"version": "1.0.0"}
        if path == "/configs":
            return {"mode": "rule"}
        if path == "/rules":
            return {"rules": []}
        if path == "/proxies":
            return {"proxies": {}, "providers": {}}
        if path == "/connections":
            return {"downloadTotal": 0, "uploadTotal": 0, "connections": None}
        raise AssertionError(path)

    monkeypatch.setattr(integrations, "_controller_json", controller_json)
    result = integrations.collect_mihomo(MihomoTrafficTracker())
    assert result["traffic"]["available"] is True
    assert result["traffic"]["connection_count"] == 0


def test_replace_top_level_rules_preserves_neighboring_config():
    source = "mixed-port: 7890\nrules:\n  - DOMAIN-SUFFIX,old.example,Proxy\n  - MATCH,DIRECT\nlog-level: info\n"
    result = _replace_top_level_rules(source, ["DOMAIN-SUFFIX,new.example,Proxy", "MATCH,DIRECT"])
    assert "old.example" not in result
    assert '  - "DOMAIN-SUFFIX,new.example,Proxy"' in result
    assert "log-level: info" in result
    compact = _replace_top_level_rules("rules: []\nmode: rule\n", ["MATCH,DIRECT"])
    assert compact.count("rules:") == 1


def test_mihomo_rules_apply_backups_and_rolls_back_on_reload_failure(tmp_path, monkeypatch):
    config = tmp_path / "mihomo.yaml"
    config.write_text("rules:\n  - DOMAIN-SUFFIX,old.example,Proxy\nmode: rule\n", encoding="utf-8")
    monkeypatch.setattr(integrations, "MIHOMO_MUTATIONS_ENABLED", True)
    monkeypatch.setattr(integrations, "EXTERNAL_PROBES", True)
    monkeypatch.setattr(integrations, "MIHOMO_CONFIG_PATH", str(config))
    monkeypatch.setenv("HOMENAS_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("HOMENAS_MIHOMO_CONTROLLER", "http://127.0.0.1:9090")
    monkeypatch.setattr(integrations, "_controller_call", lambda *args, **kwargs: {"ok": False, "body": {}, "detail": "offline"})
    result = integrations.mihomo_rules_apply(["DOMAIN-SUFFIX,new.example,Proxy"])
    assert result["status"] == "reload-failed"
    assert "old.example" in config.read_text(encoding="utf-8")
    assert list((tmp_path / "runtime" / "mihomo-backups").glob("*.bak"))


def test_mihomo_rules_apply_uses_controller_reload_query(tmp_path, monkeypatch):
    config = tmp_path / "mihomo.yaml"
    config.write_text("rules:\n  - MATCH,DIRECT\n", encoding="utf-8")
    monkeypatch.setattr(integrations, "MIHOMO_MUTATIONS_ENABLED", True)
    monkeypatch.setattr(integrations, "EXTERNAL_PROBES", True)
    monkeypatch.setattr(integrations, "MIHOMO_CONFIG_PATH", str(config))
    monkeypatch.setenv("HOMENAS_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("HOMENAS_MIHOMO_CONTROLLER", "http://127.0.0.1:9090")
    calls = []

    def controller_call(*args, **kwargs):
        calls.append((args, kwargs))
        return {"ok": True, "body": {}}

    monkeypatch.setattr(integrations, "_controller_call", controller_call)
    result = integrations.mihomo_rules_apply(["DOMAIN-SUFFIX,new.example,Proxy"])
    assert result["ok"] is True
    assert calls[0][0][1] == "/configs?force=true"
    assert calls[0][1]["payload"] == {"path": "", "payload": ""}
    assert "new.example" in config.read_text(encoding="utf-8")

