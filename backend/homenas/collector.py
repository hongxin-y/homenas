from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from .config import COLLECT_INTERVAL_SECONDS
from .db import Database
from .metrics import CollectorState, collect_snapshot


async def _to_thread(func, *args):
    """Small asyncio.to_thread equivalent for Python 3.8."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args))


def metric_samples(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    system = snapshot["system"]
    memory = system["memory"]
    network = snapshot["network"]
    samples: List[Dict[str, Any]] = [
        {"metric": "cpu.percent", "value": system["cpu_percent"], "unit": "%", "source": "psutil", "ts": snapshot["timestamp"]},
        {"metric": "memory.percent", "value": memory["percent"], "unit": "%", "source": "psutil", "ts": snapshot["timestamp"]},
    ]
    if system.get("temperature_c") is not None:
        samples.append({"metric": "temperature.cpu", "value": system["temperature_c"], "unit": "°C", "source": "psutil", "ts": snapshot["timestamp"]})
    if network.get("physical_rx_bytes_per_second") is not None:
        samples.append({"metric": "network.rx", "value": network["physical_rx_bytes_per_second"], "unit": "bytes/s", "source": "psutil", "ts": snapshot["timestamp"]})
    if network.get("physical_tx_bytes_per_second") is not None:
        samples.append({"metric": "network.tx", "value": network["physical_tx_bytes_per_second"], "unit": "bytes/s", "source": "psutil", "ts": snapshot["timestamp"]})
    power = snapshot.get("power") or {}
    if power.get("package_watts") is not None:
        samples.append({"metric": "power.package", "value": power["package_watts"], "unit": "W", "source": power.get("source"), "ts": snapshot["timestamp"]})
    return samples


class Collector:
    def __init__(self, db: Database):
        self.db = db
        self.state = CollectorState()
        self.latest: Optional[Dict[str, Any]] = None
        self._stop = asyncio.Event()

    async def collect_once(self) -> Dict[str, Any]:
        snapshot = await _to_thread(collect_snapshot, self.state)
        self.latest = snapshot
        await _to_thread(self.db.add_metric_samples, metric_samples(snapshot))
        await _to_thread(self.db.write_alerts, snapshot["alerts"])
        return snapshot

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                await self.collect_once()
            except Exception as exc:  # keep dashboard alive when one sensor fails
                self.latest = {
                    "timestamp": None,
                    "collector_error": str(exc),
                    "alerts": [{"id": "collector-error", "severity": "critical", "title": "采集器异常", "detail": str(exc)}],
                }
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=COLLECT_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass

    async def stop(self) -> None:
        self._stop.set()

