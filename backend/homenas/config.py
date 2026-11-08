from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = Path(os.getenv("HOMENAS_RUNTIME_DIR", str(PROJECT_ROOT / "runtime")))
DB_PATH = Path(os.getenv("HOMENAS_DB_PATH", str(RUNTIME_DIR / "homenas.db")))
FRONTEND_DIR = Path(os.getenv("HOMENAS_FRONTEND_DIR", str(PROJECT_ROOT / "frontend")))
HOST = os.getenv("HOMENAS_HOST", "127.0.0.1")
PORT = int(os.getenv("HOMENAS_PORT", "8787"))
ADMIN_PASSWORD = os.getenv("HOMENAS_ADMIN_PASSWORD", "admin")
COLLECT_INTERVAL_SECONDS = float(os.getenv("HOMENAS_COLLECT_INTERVAL", "5"))
SESSION_TTL_SECONDS = int(os.getenv("HOMENAS_SESSION_TTL", "28800"))


def ensure_runtime_dir() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

