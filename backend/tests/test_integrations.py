import json

from homenas.integrations import parse_lsblk_json, parse_tailscale_status


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

