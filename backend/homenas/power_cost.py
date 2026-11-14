"""Electricity cost estimates derived from CPU Package RAPL only."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional, Tuple


DEFAULT_PRICE_CNY_PER_KWH = 0.60
HOURS_PER_YEAR = 24.0 * 365.0


def normalize_price(value: Any, default: float = DEFAULT_PRICE_CNY_PER_KWH) -> float:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return float(default)
    if price <= 0 or price > 1000:
        return float(default)
    return round(price, 4)


def parse_period(start: Optional[str], end: Optional[str]) -> Tuple[str, str]:
    today = date.today().isoformat()
    start_value = str(start or today)
    end_value = str(end or start_value)
    try:
        start_date = date.fromisoformat(start_value)
        end_date = date.fromisoformat(end_value)
    except ValueError as exc:
        raise ValueError("日期必须使用 YYYY-MM-DD 格式") from exc
    if end_date < start_date:
        raise ValueError("结束日期不能早于开始日期")
    if (end_date - start_date).days > 3660:
        raise ValueError("查询范围不能超过 10 年")
    return start_date.isoformat(), end_date.isoformat()


def _package_energy(summary: Dict[str, Any]) -> Optional[float]:
    package = (summary.get("domains") or {}).get("package")
    if not isinstance(package, dict) or package.get("kwh") is None:
        return None
    return float(package["kwh"])


def period_cost(summary: Dict[str, Any], price_cny_per_kwh: float, start: str, end: str) -> Dict[str, Any]:
    price = normalize_price(price_cny_per_kwh)
    package_kwh = _package_energy(summary)
    return {
        "available": package_kwh is not None,
        "start": start,
        "end": end,
        "price_cny_per_kwh": price,
        "package_kwh": package_kwh,
        "package_cost_cny": package_kwh * price if package_kwh is not None else None,
        "domains": summary.get("domains", {}),
        "semantics": "电费只按 CPU Package 能耗估算；Cores、GPU、DRAM、PSys 分开显示，不能相加为插座电费。",
    }


def current_cost(power: Dict[str, Any], daily: Dict[str, Any], price_cny_per_kwh: float) -> Dict[str, Any]:
    price = normalize_price(price_cny_per_kwh)
    watts = power.get("package_watts")
    current_available = watts is not None
    current_watts = float(watts) if current_available else None
    current_kwh_per_day = current_watts * 24.0 / 1000.0 if current_watts is not None else None
    daily_kwh = _package_energy(daily)
    if daily_kwh is not None:
        annual_kwh = daily_kwh * 365.0
        annual_basis = "today_package"
    elif current_kwh_per_day is not None:
        annual_kwh = current_kwh_per_day * 365.0
        annual_basis = "current_package_watts"
    else:
        annual_kwh = None
        annual_basis = None
    return {
        "price_cny_per_kwh": price,
        "price_source": "HOMENAS_ELECTRICITY_PRICE_CNY_PER_KWH 或默认 0.60",
        "current": {
            "available": current_available,
            "package_watts": current_watts,
            "cny_per_hour": current_watts / 1000.0 * price if current_watts is not None else None,
            "kwh_per_day": current_kwh_per_day,
            "cny_per_day": current_kwh_per_day * price if current_kwh_per_day is not None else None,
            "kwh_per_year": current_watts * HOURS_PER_YEAR / 1000.0 if current_watts is not None else None,
            "cny_per_year": current_watts * HOURS_PER_YEAR / 1000.0 * price if current_watts is not None else None,
        },
        "daily": {
            "available": daily_kwh is not None,
            "package_kwh": daily_kwh,
            "cny": daily_kwh * price if daily_kwh is not None else None,
            "day": daily.get("day"),
        },
        "annualized": {
            "available": annual_kwh is not None,
            "basis": annual_basis,
            "package_kwh": annual_kwh,
            "cny": annual_kwh * price if annual_kwh is not None else None,
        },
        "semantics": "电费只按 CPU Package 能耗估算；不代表整机插座电费。",
    }
