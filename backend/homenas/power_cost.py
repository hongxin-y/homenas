"""Electricity cost estimates derived from CPU Package RAPL only."""

from __future__ import annotations

from datetime import date, datetime, time, timezone, timedelta
from typing import Any, Dict, Iterable, Optional, Tuple


DEFAULT_PRICE_CNY_PER_KWH = 0.60
HOURS_PER_YEAR = 24.0 * 365.0
SHANGHAI_TARIFF = {
    "id": "shanghai_residential_time_of_use",
    "name": "上海市居民一户一表分时电价",
    "timezone": "Asia/Shanghai",
    "periods": [
        {"label": "peak", "name": "峰", "start": "06:00", "end": "22:00", "prices": [0.617, 0.677, 0.977]},
        {"label": "valley", "name": "谷", "start": "22:00", "end": "06:00", "prices": [0.307, 0.337, 0.487]},
    ],
    "tiers": [
        {"tier": 1, "name": "第一档", "annual_kwh": "0-3120"},
        {"tier": 2, "name": "第二档", "annual_kwh": "3120-4800"},
        {"tier": 3, "name": "第三档", "annual_kwh": ">4800"},
    ],
}


def normalize_price(value: Any, default: float = DEFAULT_PRICE_CNY_PER_KWH) -> float:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return float(default)
    if price <= 0 or price > 1000:
        return float(default)
    return round(price, 4)


def normalize_tier(value: Any, default: int = 1) -> int:
    try:
        tier = int(value)
    except (TypeError, ValueError):
        return default
    return tier if tier in (1, 2, 3) else default


def shanghai_tariff(tier: Any = 1) -> Dict[str, Any]:
    selected = normalize_tier(tier)
    result = dict(SHANGHAI_TARIFF)
    result["tier"] = selected
    result["tier_name"] = SHANGHAI_TARIFF["tiers"][selected - 1]["name"]
    return result


def _local_time(value: Any) -> time:
    if isinstance(value, datetime):
        current = value
    else:
        text = str(value or "")
        try:
            current = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            current = datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        current = current.astimezone(ZoneInfo("Asia/Shanghai"))
    except (ImportError, KeyError):
        current = current.astimezone(timezone(timedelta(hours=8)))
    return current.time()


def tariff_band(value: Any, tariff: Optional[Dict[str, Any]] = None) -> Tuple[str, str, float]:
    config = tariff or shanghai_tariff(1)
    local = _local_time(value)
    minutes = local.hour * 60 + local.minute
    for period in config.get("periods", []):
        start_hour, start_minute = (int(part) for part in period["start"].split(":"))
        end_hour, end_minute = (int(part) for part in period["end"].split(":"))
        start = start_hour * 60 + start_minute
        end = end_hour * 60 + end_minute
        matches = start <= minutes < end if start < end else minutes >= start or minutes < end
        if matches:
            tier = normalize_tier(config.get("tier", 1))
            return period["label"], period["name"], float(period["prices"][tier - 1])
    return "flat", "平", normalize_price(config.get("flat_price"), DEFAULT_PRICE_CNY_PER_KWH)


def _records_cost(records: Iterable[Tuple[str, float]], tariff: Dict[str, Any]) -> Dict[str, Any]:
    bands: Dict[str, Dict[str, Any]] = {}
    for timestamp, joules in records:
        label, name, price = tariff_band(timestamp, tariff)
        item = bands.setdefault(label, {"label": label, "name": name, "price_cny_per_kwh": price, "joules": 0.0})
        item["joules"] += float(joules or 0.0)
    total_kwh = 0.0
    total_cost = 0.0
    for item in bands.values():
        item["kwh"] = item["joules"] / 3600000.0
        item["cost_cny"] = item["kwh"] * item["price_cny_per_kwh"]
        total_kwh += item["kwh"]
        total_cost += item["cost_cny"]
    return {"bands": bands, "package_kwh": total_kwh if bands else None, "package_cost_cny": total_cost if bands else None}


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


def period_cost(summary: Dict[str, Any], price_cny_per_kwh: float, start: str, end: str, records: Optional[Iterable[Tuple[str, float]]] = None, tariff: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    price = normalize_price(price_cny_per_kwh)
    package_kwh = _package_energy(summary)
    tariff_result = _records_cost(records, tariff) if tariff is not None and records is not None else None
    if tariff_result is not None and tariff_result["package_kwh"] is not None:
        package_kwh = tariff_result["package_kwh"]
        package_cost = tariff_result["package_cost_cny"]
    else:
        package_cost = package_kwh * price if package_kwh is not None else None
    return {
        "available": package_kwh is not None,
        "start": start,
        "end": end,
        "price_cny_per_kwh": price if tariff is None else None,
        "package_kwh": package_kwh,
        "package_cost_cny": package_cost,
        "domains": summary.get("domains", {}),
        "tariff": tariff,
        "bands": tariff_result["bands"] if tariff_result is not None else {},
        "semantics": "电费只按 CPU Package 能耗估算；Cores、GPU、DRAM、PSys 分开显示，不能相加为插座电费。",
    }


def current_cost(power: Dict[str, Any], daily: Dict[str, Any], price_cny_per_kwh: float, daily_tariff: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    price = normalize_price(price_cny_per_kwh)
    watts = power.get("package_watts")
    current_available = watts is not None
    current_watts = float(watts) if current_available else None
    current_kwh_per_day = current_watts * 24.0 / 1000.0 if current_watts is not None else None
    daily_kwh = _package_energy(daily)
    tariff_result = daily_tariff
    tariff = tariff_result.get("tariff") if isinstance(tariff_result, dict) else None
    current_band = tariff_band(datetime.now(timezone.utc), tariff) if tariff is not None else ("flat", "平", price)
    current_rate = current_band[2]
    daily_cost = tariff_result.get("package_cost_cny") if tariff_result is not None else (daily_kwh * price if daily_kwh is not None else None)
    if daily_kwh is not None:
        annual_kwh = daily_kwh * 365.0
        annual_basis = "today_package"
    elif current_kwh_per_day is not None:
        annual_kwh = current_kwh_per_day * 365.0
        annual_basis = "current_package_watts"
    else:
        annual_kwh = None
        annual_basis = None
    if daily_kwh is not None and daily_cost is not None:
        annual_cost = daily_cost * 365.0
    elif annual_kwh is not None:
        annual_cost = annual_kwh * (current_rate if tariff is not None else price)
    else:
        annual_cost = None
    return {
        "price_cny_per_kwh": price if tariff is None else None,
        "current_rate_cny_per_kwh": current_rate,
        "current_band": {"label": current_band[0], "name": current_band[1]},
        "price_source": "上海居民分时电价（第一/二/三档可配置）" if tariff is not None else "HOMENAS_ELECTRICITY_PRICE_CNY_PER_KWH 或默认 0.60",
        "current": {
            "available": current_available,
            "package_watts": current_watts,
            "cny_per_hour": current_watts / 1000.0 * current_rate if current_watts is not None else None,
            "kwh_per_day": current_kwh_per_day,
            "cny_per_day": current_kwh_per_day * current_rate if current_kwh_per_day is not None else None,
            "kwh_per_year": current_watts * HOURS_PER_YEAR / 1000.0 if current_watts is not None else None,
            "cny_per_year": current_watts * HOURS_PER_YEAR / 1000.0 * current_rate if current_watts is not None else None,
        },
        "daily": {
            "available": daily_kwh is not None,
            "package_kwh": daily_kwh,
            "cny": daily_cost,
            "day": daily.get("day"),
        },
        "annualized": {
            "available": annual_kwh is not None,
            "basis": annual_basis,
            "package_kwh": annual_kwh,
            "cny": annual_cost,
        },
        "tariff": tariff,
        "semantics": "电费只按 CPU Package 能耗估算；不代表整机插座电费。",
    }
