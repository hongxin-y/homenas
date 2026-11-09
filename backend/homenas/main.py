from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .auth import AuthManager
from .collector import Collector
from .config import ADMIN_PASSWORD, DB_PATH, FRONTEND_DIR, SESSION_TTL_SECONDS, ensure_runtime_dir
from .db import Database
from .integrations import ping_target


class LoginRequest(BaseModel):
    username: str = Field(default="admin", min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class PingRequest(BaseModel):
    target: str = Field(min_length=1, max_length=253)


def _bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    return token if scheme.lower() == "bearer" and token else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_runtime_dir()
    db = Database(DB_PATH)
    collector = Collector(db)
    auth = AuthManager(ADMIN_PASSWORD, SESSION_TTL_SECONDS)
    app.state.db = db
    app.state.collector = collector
    app.state.auth = auth
    await collector.collect_once()
    task = asyncio.create_task(collector.run())
    try:
        yield
    finally:
        await collector.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        db.close()


app = FastAPI(title="HomeNAS Dashboard", version="0.1.0", lifespan=lifespan)


def current_user(request: Request, authorization: Optional[str] = Header(default=None)) -> str:
    token = _bearer(authorization) or request.cookies.get("homenas_session")
    user = request.app.state.auth.user_for_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="需要登录")
    return user


@app.get("/api/health")
async def health(request: Request) -> Dict[str, Any]:
    collector = request.app.state.collector
    return {"status": "ok", "service": "homenas-api", "timestamp": collector.latest.get("timestamp") if collector.latest else None}


@app.post("/api/v1/auth/login")
@app.post("/api/auth/login")
async def login(payload: LoginRequest, request: Request, response: Response) -> Dict[str, Any]:
    client_key = request.client.host if request.client else "unknown"
    if not request.app.state.auth.login_allowed(client_key):
        raise HTTPException(status_code=429, detail="登录尝试过于频繁，请稍后再试")
    if payload.username != "admin" or not request.app.state.auth.verify_password(payload.password):
        request.app.state.auth.record_login_failure(client_key)
        request.app.state.db.audit("anonymous", "auth.login_failed", {"username": payload.username})
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    request.app.state.auth.clear_login_failures(client_key)
    token = request.app.state.auth.create_session(payload.username)
    request.app.state.db.audit(payload.username, "auth.login")
    response.set_cookie("homenas_session", token, httponly=True, samesite="lax", max_age=SESSION_TTL_SECONDS, path="/")
    return {"user": payload.username}


@app.post("/api/v1/auth/logout")
@app.post("/api/auth/logout")
async def logout(request: Request, response: Response, authorization: Optional[str] = Header(default=None)) -> Dict[str, bool]:
    token = _bearer(authorization) or request.cookies.get("homenas_session")
    user = request.app.state.auth.user_for_token(token)
    request.app.state.auth.revoke(token)
    if user:
        request.app.state.db.audit(user, "auth.logout")
    response.delete_cookie("homenas_session", path="/")
    return {"ok": True}


@app.get("/api/v1/auth/me")
@app.get("/api/auth/me")
async def me(user: str = Depends(current_user)) -> Dict[str, str]:
    return {"user": user}


def _snapshot(request: Request) -> Dict[str, Any]:
    snapshot = request.app.state.collector.latest
    if not snapshot:
        raise HTTPException(status_code=503, detail="采集器尚未准备好")
    return snapshot


@app.get("/api/overview")
async def overview(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    snapshot = _snapshot(request)
    history = request.app.state.collector.state.history
    return {
        "timestamp": snapshot["timestamp"],
        "system": snapshot["system"],
        "power": snapshot["power"],
        "storage": snapshot["storage"],
        "network": snapshot["network"],
        "services": snapshot["services"],
        "vpn": snapshot["vpn"],
        "alerts": snapshot["alerts"],
        "history": [
            {"timestamp": item.get("timestamp"), "cpu_percent": item.get("system", {}).get("cpu_percent"), "memory_percent": item.get("system", {}).get("memory", {}).get("percent"), "rx": item.get("network", {}).get("physical_rx_bytes_per_second"), "tx": item.get("network", {}).get("physical_tx_bytes_per_second"), "power_watts": item.get("power", {}).get("package_watts")}
            for item in history
        ],
    }


@app.get("/api/system")
async def system(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    return _snapshot(request)["system"]


@app.get("/api/power")
async def power(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    return _snapshot(request)["power"]


@app.get("/api/storage")
async def storage(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    return _snapshot(request)["storage"]


@app.get("/api/network")
async def network(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    return _snapshot(request)["network"]


@app.get("/api/vpn")
async def vpn(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    return _snapshot(request)["vpn"]


@app.post("/api/vpn/ping")
async def vpn_ping(payload: PingRequest, request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    result = await asyncio.to_thread(ping_target, payload.target)
    request.app.state.db.audit(user, "vpn.ping", {"target": result.get("target"), "status": result.get("status")})
    return result


@app.get("/api/seafile")
async def seafile(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    return _snapshot(request).get("seafile", {"healthy": None, "reason": "unavailable"})


@app.get("/api/services")
async def services(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    return {"services": _snapshot(request)["services"]}


@app.get("/api/alerts")
async def alerts(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    return {"alerts": request.app.state.db.list_alerts(), "events": request.app.state.db.list_alert_events()}


@app.get("/api/metrics/{metric}")
async def metrics(metric: str, request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    allowed = {"cpu.percent", "memory.percent", "temperature.cpu", "network.rx", "network.tx", "power.package", "power.cores", "power.gpu", "power.dram", "power.psys"}
    if metric not in allowed:
        raise HTTPException(status_code=404, detail="未知指标")
    return {"metric": metric, "samples": request.app.state.db.recent_metrics(metric)}


# Read-only v1 compatibility surface from the Starter Pack API outline. The
# short /api routes above remain the browser-facing first-version contract.
@app.get("/health", include_in_schema=False)
@app.get("/api/v1/health", include_in_schema=False)
async def v1_health(request: Request) -> Dict[str, Any]:
    return await health(request)


@app.get("/api/v1/system/summary")
async def v1_system_summary(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    return _snapshot(request)["system"]


@app.get("/api/v1/system/cpu")
async def v1_system_cpu(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    system_data = _snapshot(request)["system"]
    return {key: system_data[key] for key in ("cpu_percent", "per_cpu_percent", "cpu_frequency_mhz", "load_average")}


@app.get("/api/v1/system/memory")
async def v1_system_memory(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    system_data = _snapshot(request)["system"]
    return {"memory": system_data["memory"], "swap": system_data["swap"]}


@app.get("/api/v1/system/temperatures")
async def v1_system_temperatures(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    system_data = _snapshot(request)["system"]
    return {"cpu_c": system_data.get("temperature_c"), "source": system_data.get("temperature_source")}


@app.get("/api/v1/system/processes")
async def v1_system_processes(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    processes = _snapshot(request)["system"].get("top_processes", [])
    return {"top_cpu": processes, "top_memory": sorted(processes, key=lambda item: item["memory_percent"], reverse=True), "quality": "ok" if processes else "unavailable"}


@app.get("/api/v1/power/current")
async def v1_power_current(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    return _snapshot(request)["power"]


@app.get("/api/v1/power/history")
async def v1_power_history(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    return {"samples": request.app.state.db.recent_metrics("power.package")}


@app.get("/api/v1/power/daily")
async def v1_power_daily(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    return request.app.state.db.energy_summary()


@app.get("/api/v1/storage/devices")
async def v1_storage_devices(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    storage_data = _snapshot(request)["storage"]
    return {"devices": storage_data.get("disks", []), "inventory": storage_data.get("disk_inventory")}


@app.get("/api/v1/storage/filesystems")
async def v1_storage_filesystems(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    return {"filesystems": _snapshot(request)["storage"].get("filesystems", [])}


@app.get("/api/v1/storage/devices/{device_id}/smart")
async def v1_storage_smart(request: Request, device_id: str, user: str = Depends(current_user)) -> Dict[str, Any]:
    return {"device": device_id, **_snapshot(request)["storage"].get("smart", {})}


@app.get("/api/v1/network/interfaces")
async def v1_network_interfaces(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    return {"interfaces": _snapshot(request)["network"].get("interfaces", [])}


@app.get("/api/v1/network/traffic")
async def v1_network_traffic(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    network_data = _snapshot(request)["network"]
    return {key: network_data.get(key) for key in ("physical_rx_bytes_per_second", "physical_tx_bytes_per_second", "note")}


@app.get("/api/v1/network/connections")
async def v1_network_connections(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    return {"connections": _snapshot(request)["network"].get("tcp_connection_counts", {}), "quality": "ok"}


@app.get("/api/v1/vpn/mihomo/status")
async def v1_mihomo_status(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    return _snapshot(request)["vpn"]["mihomo"]


@app.get("/api/v1/vpn/mihomo/proxies")
async def v1_mihomo_proxies(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    return _snapshot(request)["vpn"]["mihomo"].get("proxies", {})


@app.get("/api/v1/vpn/mihomo/traffic")
async def v1_mihomo_traffic(user: str = Depends(current_user)) -> Dict[str, Any]:
    return {"available": False, "samples": [], "reason": "只读 Controller 集成尚未配置"}


@app.get("/api/v1/vpn/mihomo/connections")
async def v1_mihomo_connections(user: str = Depends(current_user)) -> Dict[str, Any]:
    return {"connections": [], "reason": "只读 Controller 集成尚未配置"}


@app.get("/api/v1/vpn/tailscale/status")
async def v1_tailscale_status(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    return _snapshot(request)["vpn"]["tailscale"]


@app.get("/api/v1/vpn/tailscale/peers")
async def v1_tailscale_peers(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    tailscale_data = _snapshot(request)["vpn"]["tailscale"]
    return {"peer_count": tailscale_data.get("peer_count"), "online_peer_count": tailscale_data.get("online_peer_count"), "peers": tailscale_data.get("peers", [])}


@app.get("/api/v1/services")
async def v1_services(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    return {"services": _snapshot(request).get("services", [])}


@app.get("/api/v1/alerts")
async def v1_alerts(request: Request, user: str = Depends(current_user)) -> Dict[str, Any]:
    return {"alerts": request.app.state.db.list_alerts(), "events": request.app.state.db.list_alert_events()}


@app.websocket("/api/ws")
async def websocket_updates(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await asyncio.sleep(5)
            snapshot = websocket.app.state.collector.latest
            if snapshot:
                await websocket.send_json({"timestamp": snapshot["timestamp"], "system": snapshot["system"], "power": snapshot.get("power"), "alerts": snapshot["alerts"]})
    except (WebSocketDisconnect, asyncio.CancelledError):
        return


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend_fallback(path: str) -> FileResponse:
        candidate = FRONTEND_DIR / path
        if candidate.is_file() and FRONTEND_DIR in candidate.parents:
            return FileResponse(str(candidate))
        return FileResponse(str(FRONTEND_DIR / "index.html"))

