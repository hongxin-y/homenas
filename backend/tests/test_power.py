import json
import socket
import threading
import time

from homenas.db import Database
from homenas.power import PerfRAPLCollector, parse_perf_record


def test_parse_perf_semicolon_record_and_domain_aliases():
    record = parse_perf_record("1.000992124;14.42;Joules;power/energy-pkg/;100.00")
    assert record["available"] is True
    assert record["domain"] == "package"
    assert record["joules"] == 14.42
    assert parse_perf_record("1.000992124;<not supported>;Joules;power/energy-gpu/;100.00")["available"] is False
    assert parse_perf_record("diagnostic line") is None


def test_collector_uses_actual_timestamp_delta_and_accumulates_energy():
    collector = PerfRAPLCollector()
    collector._handle_line("1.000000;14.42;Joules;power/energy-pkg/;100")
    collector._handle_line("2.250000;18.75;Joules;power/energy-pkg/;100")
    samples = collector.drain_samples()
    assert len(samples) == 2
    assert round(samples[0]["watts"], 3) == 14.42
    assert round(samples[1]["elapsed_s"], 3) == 1.25
    assert round(samples[1]["watts"], 3) == 15.0
    snapshot = collector.snapshot()
    assert round(snapshot["package_energy_j"], 2) == 33.17
    assert round(snapshot["package_energy_wh"], 5) == round(33.17 / 3600, 5)


def test_permission_error_is_unavailable_and_never_zero():
    collector = PerfRAPLCollector()
    collector._handle_line("Access to performance monitoring is limited")
    result = collector.snapshot()
    assert result["available"] is False
    assert result["package_watts"] is None
    assert result["collector_status"] == "permission_denied"


def test_collector_reads_long_lived_helper_socket(tmp_path, monkeypatch):
    if not hasattr(socket, "AF_UNIX"):
        return
    socket_path = tmp_path / "perf.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    server.listen(1)

    def serve_once():
        connection, _ = server.accept()
        with connection:
            connection.sendall(
                b"1.000000;14.42;Joules;power/energy-pkg/;100\n"
                b"2.000000;15.00;Joules;power/energy-pkg/;100\n"
            )
        server.close()

    thread = threading.Thread(target=serve_once, daemon=True)
    thread.start()
    monkeypatch.setenv("HOMENAS_PERF_SOCKET", str(socket_path))
    collector = PerfRAPLCollector(restart_delay=0.01)
    collector.ensure_running()
    deadline = time.time() + 1.0
    while time.time() < deadline and not collector.drain_samples():
        time.sleep(0.01)
    snapshot = collector.snapshot()
    collector.stop()
    thread.join(timeout=1)
    assert snapshot["package_watts"] == 15.0
    assert round(snapshot["package_energy_j"], 2) == 29.42


def test_energy_records_persist_and_daily_summary(tmp_path):
    db = Database(tmp_path / "power.db")
    db.add_energy_samples([
        {"ts": "2026-11-09T01:00:00+00:00", "domain": "package", "joules": 14.42, "watts": 14.42, "quality": "ok", "source": "perf/RAPL"},
        {"ts": "2026-11-09T01:00:01+00:00", "domain": "package", "joules": 18.75, "watts": 15.0, "quality": "ok", "source": "perf/RAPL"},
        {"ts": "2026-11-09T01:00:02+00:00", "domain": "psys", "joules": 4.47, "watts": 4.47, "quality": "ok", "source": "perf/RAPL"},
        {"ts": "2026-11-09T01:00:03+00:00", "domain": "gpu", "joules": None, "watts": None, "quality": "unavailable", "source": "perf/RAPL"},
    ])
    summary = db.energy_summary("2026-11-09")
    assert summary["available"] is True
    assert round(summary["domains"]["package"]["joules"], 2) == 33.17
    assert round(summary["domains"]["package"]["wh"], 5) == round(33.17 / 3600, 5)
    assert "gpu" not in summary["domains"]
    db.close()

