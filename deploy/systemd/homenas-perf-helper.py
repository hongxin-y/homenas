#!/usr/bin/env python3
"""Root-only HomeNAS RAPL helper.

The Debian target kernel uses ``perf_event_paranoid=3``.  On that policy the
target's kernel requires the privileged perf invocation even when an
unprivileged process has CAP_PERFMON.  This helper keeps only that invocation
privileged and forwards its machine-readable stderr over a local Unix socket.
The HomeNAS API remains a separate non-root process.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
from pathlib import Path
from typing import Optional


SOCKET_PATH = Path(os.getenv("HOMENAS_PERF_SOCKET", "/run/homenas-perf/perf.sock"))
PERF_PATH = os.getenv("HOMENAS_PERF_BIN", "/usr/bin/perf")
SLEEP_PATH = "/bin/sleep"
EVENTS = (
    "power/energy-pkg/",
    "power/energy-cores/",
    "power/energy-gpu/",
    "power/energy-ram/",
    "power/energy-psys/",
)
STOP = False
ACTIVE: Optional[subprocess.Popen[bytes]] = None
SERVER: Optional[socket.socket] = None


def command() -> list[str]:
    args = [PERF_PATH, "stat", "-a", "-I", "1000", "-x", ";"]
    for event in EVENTS:
        args.extend(("-e", event))
    args.extend(("--", SLEEP_PATH, "86400"))
    return args


def terminate_process() -> None:
    global ACTIVE
    process = ACTIVE
    ACTIVE = None
    if process is None or process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
        except OSError:
            pass


def handle_signal(_signum: int, _frame: object) -> None:
    global STOP
    STOP = True
    terminate_process()
    if SERVER is not None:
        try:
            SERVER.close()
        except OSError:
            pass


def serve_client(connection: socket.socket) -> None:
    global ACTIVE
    environment = os.environ.copy()
    environment["LC_ALL"] = "C"
    environment["LANG"] = "C"
    process = subprocess.Popen(
        command(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=environment,
        close_fds=True,
    )
    ACTIVE = process
    try:
        if process.stderr is not None:
            for line in process.stderr:
                try:
                    connection.sendall(line)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    break
    finally:
        terminate_process()


def main() -> int:
    global SERVER
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        SOCKET_PATH.unlink()
    except FileNotFoundError:
        pass
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    SERVER = server
    server.bind(str(SOCKET_PATH))
    os.chmod(SOCKET_PATH, 0o660)
    server.listen(1)
    server.settimeout(1.0)
    try:
        while not STOP:
            try:
                connection, _ = server.accept()
            except socket.timeout:
                continue
            except OSError:
                if STOP:
                    break
                raise
            with connection:
                serve_client(connection)
    finally:
        terminate_process()
        try:
            server.close()
        except OSError:
            pass
        try:
            SOCKET_PATH.unlink()
        except FileNotFoundError:
            pass
    return 0


signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)


if __name__ == "__main__":
    raise SystemExit(main())
