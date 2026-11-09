"""Dependency-light Perf/RAPL parser and persistence smoke test."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from homenas.db import Database  # noqa: E402
from homenas.power import PerfRAPLCollector, parse_perf_record  # noqa: E402


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    record = parse_perf_record("1.000992124;14.42;Joules;power/energy-pkg/;100.00")
    check(record and record["domain"] == "package", "semicolon parser")
    collector = PerfRAPLCollector()
    collector._handle_line("1.000000;14.42;Joules;power/energy-pkg/;100")
    collector._handle_line("2.250000;18.75;Joules;power/energy-pkg/;100")
    samples = collector.drain_samples()
    check(round(samples[1]["elapsed_s"], 3) == 1.25, "actual interval")
    check(round(samples[1]["watts"], 3) == 15.0, "watts conversion")
    check(round(collector.snapshot()["package_energy_j"], 2) == 33.17, "energy accumulation")
    collector._handle_line("Access to performance monitoring is limited")
    check(collector.snapshot()["package_watts"] is None, "permission unavailable")
    with tempfile.TemporaryDirectory() as folder:
        db = Database(Path(folder) / "energy.db")
        db.add_energy_samples([{"ts": "2026-11-09T01:00:00+00:00", "domain": "package", "joules": 33.17, "watts": 15, "quality": "ok", "source": "perf/RAPL"}])
        summary = db.energy_summary("2026-11-09")
        check(round(summary["total_wh"], 5) == round(33.17 / 3600, 5), "sqlite energy summary")
        db.close()
    print("Perf/RAPL smoke tests passed")


if __name__ == "__main__":
    main()

