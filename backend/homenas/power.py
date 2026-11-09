"""Long-lived perf/RAPL collector.

``perf stat -I`` writes interval measurements to stderr.  This module keeps
one perf process alive, parses the machine-readable semicolon format, and
turns each valid interval into watts plus cumulative joules.  It deliberately
does not change perf permissions or kernel settings.
"""

from __future__ import annotations

import os
import queue
import re
import shutil
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


RAPL_EVENTS = (
    ("package", "power/energy-pkg/"),
    ("cores", "power/energy-cores/"),
    ("gpu", "power/energy-gpu/"),
    ("dram", "power/energy-ram/"),
    ("psys", "power/energy-psys/"),
)
RAPL_DOMAINS = tuple(item[0] for item in RAPL_EVENTS)
_EVENT_RE = re.compile(r"energy-(pkg|package|cores|core|gpu|ram|dram|psys)", re.IGNORECASE)
_NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_domain(event: str) -> Optional[str]:
    match = _EVENT_RE.search(str(event or ""))
    if not match:
        return None
    token = match.group(1).lower()
    return {"pkg": "package", "package": "package", "core": "cores", "dram": "dram"}.get(token, token)


def parse_perf_record(line: str) -> Optional[Dict[str, Any]]:
    """Parse one ``perf stat -x ';'`` interval line.

    Expected C-locale fields are ``timestamp;value;unit;event;runtime``.
    Perf diagnostics, blank lines, unsupported values and unrelated events are
    ignored without turning them into zeroes.
    """
    raw = str(line or "").strip()
    if not raw or raw.startswith("#"):
        return None
    fields = [field.strip() for field in raw.split(";")]
    if len(fields) < 4:
        return None
    timestamp_text, value_text, unit, event = fields[:4]
    domain = normalize_domain(event)
    if domain is None:
        return None
    if not _NUMBER_RE.match(timestamp_text):
        return {"available": False, "quality": "unavailable", "domain": domain, "reason": "perf timestamp unavailable", "raw": raw}
    timestamp_s = float(timestamp_text)
    if value_text.startswith("<") or not _NUMBER_RE.match(value_text):
        return {"available": False, "quality": "unavailable", "domain": domain, "timestamp_s": timestamp_s, "reason": "perf value unavailable", "raw": raw}
    return {
        "available": True,
        "quality": "ok",
        "domain": domain,
        "timestamp_s": timestamp_s,
        "joules": float(value_text),
        "unit": unit or "Joules",
        "runtime_percent": float(fields[4]) if len(fields) > 4 and _NUMBER_RE.match(fields[4]) else None,
        "raw": raw,
    }


class PerfRAPLCollector:
    """Keep one perf process alive and expose thread-safe samples/snapshots."""

    def __init__(self, interval_ms: int = 1000, restart_delay: float = 5.0) -> None:
        self.interval_ms = int(interval_ms)
        self.restart_delay = float(restart_delay)
        self.enabled = os.getenv("HOMENAS_ENABLE_PERF_RAPL", "1") == "1" and os.name == "posix"
        self.perf_path = shutil.which("perf")
        self.sleep_path = shutil.which("sleep") or "/bin/sleep"
        self._process: Optional[subprocess.Popen[str]] = None
        self._reader: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._latest: Dict[str, Dict[str, Any]] = {}
        self._totals_j: Dict[str, float] = {domain: 0.0 for domain in RAPL_DOMAINS}
        self._previous_timestamp: Dict[str, float] = {}
        self._next_restart = 0.0
        self._backoff = self.restart_delay
        self._stopping = False
        self.status = "disabled" if not self.enabled else "not_started"
        self.last_error: Optional[str] = None

    @property
    def command(self) -> List[str]:
        command: List[str] = [self.perf_path or "perf", "stat", "-a", "-I", str(self.interval_ms), "-x", ";"]
        for _, event in RAPL_EVENTS:
            command.extend(("-e", event))
        # A long-lived child gives the reader a stable process. It is restarted
        # after exit and does not require a shell or an infinite shell loop.
        command.extend(("--", self.sleep_path, "86400"))
        return command

    def ensure_running(self) -> None:
        with self._lock:
            if self._stopping or not self.enabled:
                return
            if not self.perf_path:
                self.status = "unavailable"
                self.last_error = "perf binary not found"
                return
            if self._process is not None and self._process.poll() is None:
                return
            if time.monotonic() < self._next_restart:
                return
            self._start_locked()

    def _start_locked(self) -> None:
        self._previous_timestamp.clear()
        self._latest.clear()
        env = os.environ.copy()
        env["LC_ALL"] = "C"
        env["LANG"] = "C"
        try:
            process = subprocess.Popen(
                self.command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                close_fds=True,
                start_new_session=(os.name == "posix"),
                env=env,
            )
        except (OSError, ValueError) as exc:
            self._process = None
            self.status = "error"
            self.last_error = str(exc)
            self._next_restart = time.monotonic() + self._backoff
            return
        self._process = process
        self.status = "starting"
        self.last_error = None
        self._reader = threading.Thread(target=self._read_stderr, args=(process,), name="homenas-perf-rapl", daemon=True)
        self._reader.start()

    def _read_stderr(self, process: subprocess.Popen[str]) -> None:
        try:
            if process.stderr is not None:
                for line in process.stderr:
                    self._handle_line(line)
        finally:
            returncode = process.poll()
            if returncode is None:
                try:
                    returncode = process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    returncode = None
            with self._lock:
                if self._process is not process:
                    return
                self._process = None
                if self._stopping:
                    self.status = "stopped"
                    return
                if returncode not in (None, 0):
                    self.status = "permission_denied" if self._looks_like_permission_error(self.last_error) else "exited"
                    if not self.last_error:
                        self.last_error = f"perf exited with code {returncode}"
                else:
                    self.status = "exited"
                    self.last_error = "perf process exited"
                self._next_restart = time.monotonic() + self._backoff
                self._backoff = min(self._backoff * 2, 60.0)

    @staticmethod
    def _looks_like_permission_error(message: Optional[str]) -> bool:
        text = str(message or "").lower()
        return any(token in text for token in ("permission", "paranoid", "perf_event", "cap_perfmon", "access to performance"))

    def _handle_line(self, line: str) -> None:
        record = parse_perf_record(line)
        if record is None:
            lowered = str(line).lower()
            if any(token in lowered for token in ("permission", "paranoid", "perf_event", "access to performance")):
                with self._lock:
                    self.last_error = "perf permission denied; CAP_PERFMON or an approved perf policy is required"
                    self.status = "permission_denied"
                    self._latest.clear()
            return
        domain = record["domain"]
        if not record.get("available"):
            with self._lock:
                self.last_error = record.get("reason") or "perf sample unavailable"
                self.status = "sample_unavailable"
                self._latest.pop(domain, None)
            return
        timestamp_s = float(record["timestamp_s"])
        with self._lock:
            previous = self._previous_timestamp.get(domain)
            elapsed_s = timestamp_s if previous is None else timestamp_s - previous
            self._previous_timestamp[domain] = timestamp_s
            if elapsed_s <= 0 or elapsed_s > 60 or record["joules"] < 0:
                self.last_error = "perf sample interval invalid"
                return
            joules = float(record["joules"])
            watts = joules / elapsed_s
            self._totals_j[domain] += joules
            sample = {
                "ts": utc_now(),
                "domain": domain,
                "joules": joules,
                "elapsed_s": elapsed_s,
                "watts": watts,
                "quality": "ok",
                "source": "perf/RAPL",
                "perf_timestamp_s": timestamp_s,
                "raw": record.get("raw"),
            }
            self._latest[domain] = sample
            self._queue.put(sample)
            self.status = "running"
            self.last_error = None
            self._backoff = self.restart_delay

    def drain_samples(self, limit: int = 5000) -> List[Dict[str, Any]]:
        samples: List[Dict[str, Any]] = []
        for _ in range(limit):
            try:
                samples.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return samples

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            domains: Dict[str, Dict[str, Any]] = {}
            for domain in RAPL_DOMAINS:
                latest = self._latest.get(domain)
                if latest is None:
                    domains[domain] = {"available": False, "value": None, "quality": "unavailable", "source": "perf/RAPL", "reason": self.last_error or "等待首次有效采样", "event": dict(RAPL_EVENTS)[domain]}
                    continue
                total_j = self._totals_j[domain]
                domains[domain] = {
                    "available": True,
                    "value": latest["watts"],
                    "watts": latest["watts"],
                    "joules_interval": latest["joules"],
                    "elapsed_seconds": latest["elapsed_s"],
                    "energy_j": total_j,
                    "energy_wh": total_j / 3600.0,
                    "energy_kwh": total_j / 3600000.0,
                    "unit": "W",
                    "quality": latest["quality"],
                    "source": latest["source"],
                    "event": dict(RAPL_EVENTS)[domain],
                    "timestamp": latest["ts"],
                }
            package = domains["package"]
            available = any(item.get("available") for item in domains.values())
            reason = None if available else (self.last_error or "等待 perf RAPL 首次有效采样")
            return {
                "available": available,
                "source": "perf/RAPL",
                "collector_status": self.status,
                "reason": reason,
                "domains": domains,
                "package_watts": package.get("watts") if package.get("available") else None,
                "package_energy_j": package.get("energy_j") if package.get("available") else None,
                "package_energy_wh": package.get("energy_wh") if package.get("available") else None,
                "package_energy_kwh": package.get("energy_kwh") if package.get("available") else None,
                "psys_experimental": True,
                "semantics": "Package 是 CPU 封装功耗；Cores、GPU、DRAM、PSys 不相加。PSys 仅作实验性指标，不代表插座功耗。",
            }

    def stop(self) -> None:
        with self._lock:
            self._stopping = True
            process = self._process
            self._process = None
        if process is not None and process.poll() is None:
            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()
                process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                except OSError:
                    pass
        reader = self._reader
        if reader is not None and reader.is_alive():
            reader.join(timeout=3)
        with self._lock:
            self.status = "stopped"

