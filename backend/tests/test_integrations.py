import json

import homenas.integrations as integrations
from homenas.integrations import _replace_top_level_rules, parse_lsblk_json, parse_tailscale_status


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

