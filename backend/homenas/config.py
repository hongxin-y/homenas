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
try:
    ELECTRICITY_PRICE_CNY_PER_KWH = float(os.getenv("HOMENAS_ELECTRICITY_PRICE_CNY_PER_KWH", "0.60"))
except ValueError:
    ELECTRICITY_PRICE_CNY_PER_KWH = 0.60
try:
    ELECTRICITY_TARIFF_TIER = int(os.getenv("HOMENAS_ELECTRICITY_TARIFF_TIER", "1"))
except ValueError:
    ELECTRICITY_TARIFF_TIER = 1
if ELECTRICITY_TARIFF_TIER not in (1, 2, 3):
    ELECTRICITY_TARIFF_TIER = 1


def ensure_runtime_dir() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

