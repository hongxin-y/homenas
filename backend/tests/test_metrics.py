from homenas.db import Database
from homenas.metrics import CollectorState, collect_network, counter_rate, parse_perf_csv


def test_parse_perf_csv_preserves_unavailable_values():
    parsed = parse_perf_csv(
        "1.25,,Joules,power/energy-pkg/,100\n"
        "<not supported>,,Joules,power/energy-ram/,100\n"
        "bad,,Joules,power/energy-gpu/,100\n"
    )
    assert parsed["pkg"]["available"] is True
    assert parsed["pkg"]["value"] == 1.25
    assert parsed["ram"]["value"] is None
    assert parsed["gpu"]["value"] is None


def test_counter_rate_handles_reset_and_first_sample():
    assert counter_rate(None, 10, 10) is None
    assert counter_rate((100, 1), 130, 4) == 10
    assert counter_rate((100, 1), 90, 4) is None


def test_network_collector_does_not_crash_and_separates_interfaces():
    state = CollectorState()
    snapshot = collect_network(state)
    assert "interfaces" in snapshot
    assert all(item["kind"] in {"physical", "virtual", "loopback", "tailscale"} for item in snapshot["interfaces"])


def test_sqlite_wal_and_metrics(tmp_path):
    db = Database(tmp_path / "homenas.db")
    db.add_metric_samples([{"metric": "cpu.percent", "value": 42, "unit": "%", "source": "test"}])
    assert db.recent_metrics("cpu.percent")[0]["value"] == 42
    assert db.conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    db.close()

