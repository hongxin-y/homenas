from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS metric_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL,
    unit TEXT,
    quality TEXT NOT NULL DEFAULT 'ok',
    source TEXT
);
CREATE INDEX IF NOT EXISTS idx_metric_samples_metric_ts
    ON metric_samples(metric, ts);
CREATE TABLE IF NOT EXISTS metric_aggregates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bucket_start TEXT NOT NULL,
    bucket_seconds INTEGER NOT NULL,
    metric TEXT NOT NULL,
    value_avg REAL,
    value_min REAL,
    value_max REAL,
    sample_count INTEGER NOT NULL DEFAULT 0,
    quality TEXT NOT NULL DEFAULT 'ok'
);
CREATE TABLE IF NOT EXISTS energy_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    domain TEXT NOT NULL,
    energy_j REAL,
    watts REAL,
    quality TEXT NOT NULL DEFAULT 'unavailable',
    source TEXT
);
CREATE INDEX IF NOT EXISTS idx_energy_records_ts_domain
    ON energy_records(ts, domain);
CREATE TABLE IF NOT EXISTS network_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    interface_name TEXT NOT NULL,
    rx_bytes REAL,
    tx_bytes REAL,
    rx_bytes_per_second REAL,
    tx_bytes_per_second REAL,
    quality TEXT NOT NULL DEFAULT 'ok'
);
CREATE TABLE IF NOT EXISTS disk_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    device TEXT,
    mountpoint TEXT,
    used_bytes INTEGER,
    total_bytes INTEGER,
    temperature_c REAL,
    smart_state TEXT,
    quality TEXT NOT NULL DEFAULT 'ok'
);
CREATE TABLE IF NOT EXISTS service_registry (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT,
    deployment TEXT,
    access_url TEXT,
    manifest_source TEXT,
    enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS service_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    status TEXT,
    health TEXT,
    detail TEXT
);
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT
);
CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    recovered_at TEXT,
    acknowledged INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS alert_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    event TEXT NOT NULL,
    detail TEXT
);
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password_digest TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'admin',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_digest TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT NOT NULL
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self._lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def add_metric_samples(self, samples: List[Dict[str, Any]]) -> None:
        if not samples:
            return
        with self._lock:
            self.conn.executemany(
                "INSERT INTO metric_samples(ts, metric, value, unit, quality, source) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        sample.get("ts") or utc_now(),
                        sample["metric"],
                        sample.get("value"),
                        sample.get("unit"),
                        sample.get("quality", "ok"),
                        sample.get("source"),
                    )
                    for sample in samples
                ],
            )
            self.conn.commit()

    def add_energy_samples(self, samples: List[Dict[str, Any]]) -> None:
        """Persist only valid perf intervals; unavailable samples are omitted."""
        valid = [sample for sample in samples if sample.get("quality") == "ok" and sample.get("joules") is not None]
        if not valid:
            return
        with self._lock:
            self.conn.executemany(
                "INSERT INTO energy_records(ts, domain, energy_j, watts, quality, source) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        sample.get("ts") or utc_now(),
                        sample["domain"],
                        sample.get("joules"),
                        sample.get("watts"),
                        sample.get("quality", "ok"),
                        sample.get("source", "perf/RAPL"),
                    )
                    for sample in valid
                ],
            )
            self.conn.commit()

    def energy_summary(self, day: Optional[str] = None) -> Dict[str, Any]:
        """Return local-calendar-day energy totals in J, Wh and kWh."""
        requested_day = day or datetime.now().astimezone().date().isoformat()
        with self._lock:
            rows = self.conn.execute(
                "SELECT domain, SUM(energy_j) AS joules, AVG(watts) AS average_watts, "
                "MAX(watts) AS peak_watts, COUNT(*) AS samples "
                "FROM energy_records WHERE quality='ok' AND date(ts, 'localtime') = ? GROUP BY domain",
                (requested_day,),
            ).fetchall()
        domains: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            joules = float(row["joules"] or 0.0)
            domains[row["domain"]] = {
                "joules": joules,
                "wh": joules / 3600.0,
                "kwh": joules / 3600000.0,
                "average_watts": float(row["average_watts"]) if row["average_watts"] is not None else None,
                "peak_watts": float(row["peak_watts"]) if row["peak_watts"] is not None else None,
                "samples": int(row["samples"]),
            }
        total_joules = sum(item["joules"] for item in domains.values()) if domains else None
        return {
            "available": bool(domains),
            "day": requested_day,
            "domains": domains,
            "total_joules": total_joules,
            "total_wh": total_joules / 3600.0 if total_joules is not None else None,
            "total_kwh": total_joules / 3600000.0 if total_joules is not None else None,
            "semantics": "仅累计有效 perf/RAPL 区间；各 domain 不应相加解释为插座功耗。",
        }

    def recent_metrics(self, metric: str, limit: int = 60) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT ts, metric, value, unit, quality, source FROM metric_samples "
                "WHERE metric = ? ORDER BY id DESC LIMIT ?",
                (metric, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def write_alerts(self, alerts: List[Dict[str, Any]]) -> None:
        now = utc_now()
        with self._lock:
            previous_active = {
                row["id"]
                for row in self.conn.execute("SELECT id FROM alerts WHERE recovered_at IS NULL").fetchall()
            }
            active_ids = set()
            for alert in alerts:
                alert_id = alert["id"]
                active_ids.add(alert_id)
                existing = self.conn.execute(
                    "SELECT first_seen, recovered_at FROM alerts WHERE id=?", (alert_id,)
                ).fetchone()
                event = "opened" if alert_id not in previous_active else "updated"
                first_seen = (
                    existing["first_seen"]
                    if existing is not None and existing["recovered_at"] is None
                    else alert.get("first_seen") or now
                )
                self.conn.execute(
                    """INSERT INTO alerts(id, severity, title, detail, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET severity=excluded.severity,
                    title=excluded.title, detail=excluded.detail, last_seen=excluded.last_seen,
                    recovered_at=NULL""",
                    (
                        alert_id,
                        alert["severity"],
                        alert["title"],
                        alert.get("detail"),
                        first_seen,
                        now,
                    ),
                )
                if event == "opened":
                    self.conn.execute(
                        "INSERT INTO alert_events(alert_id, ts, event, detail) VALUES (?, ?, ?, ?)",
                        (alert_id, now, event, alert.get("detail")),
                    )
            if active_ids:
                placeholders = ",".join("?" for _ in active_ids)
                self.conn.execute(
                    f"UPDATE alerts SET recovered_at=? WHERE recovered_at IS NULL AND id NOT IN ({placeholders})",
                    (now, *active_ids),
                )
            else:
                self.conn.execute(
                    "UPDATE alerts SET recovered_at=? WHERE recovered_at IS NULL", (now,)
                )
            recovered = previous_active - active_ids
            for alert_id in recovered:
                self.conn.execute(
                    "INSERT INTO alert_events(alert_id, ts, event, detail) VALUES (?, ?, ?, ?)",
                    (alert_id, now, "recovered", None),
                )
            self.conn.commit()

    def list_alerts(self, active_only: bool = False) -> List[Dict[str, Any]]:
        query = "SELECT * FROM alerts"
        params: tuple = ()
        if active_only:
            query += " WHERE recovered_at IS NULL"
        query += " ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, last_seen DESC"
        with self._lock:
            rows = self.conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def list_alert_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT alert_id, ts, event, detail FROM alert_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def audit(self, actor: str, action: str, detail: Optional[Dict[str, Any]] = None) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO audit_logs(ts, actor, action, detail) VALUES (?, ?, ?, ?)",
                (utc_now(), actor, action, json.dumps(detail or {}, ensure_ascii=False)),
            )
            self.conn.commit()

