"""Standalone collector entry point for the future systemd split.

The local API currently starts an in-process collector so the first version is
easy to run. This module exists for the reviewed systemd deployment shape and
does not open a network listener.
"""

from __future__ import annotations

import asyncio
import signal

from .collector import Collector
from .config import DB_PATH, ensure_runtime_dir
from .db import Database


async def run() -> None:
    ensure_runtime_dir()
    db = Database(DB_PATH)
    collector = Collector(db)
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            pass
    task = asyncio.create_task(collector.run())
    await stop.wait()
    await collector.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    db.close()


if __name__ == "__main__":
    asyncio.run(run())

