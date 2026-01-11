import os
import threading

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.storage import load_config, save_config
from src.collector import run_forever, get_last_status

CONFIG_PATH = os.getenv("AGENT_CONFIG", "/agent/config/config.json")

app = FastAPI(title="AV Agent - Local Admin")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

_stop_flag = {"stop": True}
_thread: threading.Thread | None = None


def collector_running() -> bool:
    return _thread is not None and _thread.is_alive() and not _stop_flag["stop"]


def ensure_collector_running() -> None:
    global _thread
    if collector_running():
        return
    _stop_flag["stop"] = False
    _thread = threading.Thread(target=run_forever, args=(_stop_flag,), daemon=True)
    _thread.start()


def stop_collector() -> None:
    _stop_flag["stop"] = True


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    cfg = load_config(CONFIG_PATH)
    last_status = get_last_status()

    # Normalise device_cfg (compat)
    for d in cfg.get("devices", []):
        d.setdefault("name", "")
        d.setdefault("building", "")
        d.setdefault("room", "")
        d.setdefault("type", "unknown")
        d.setdefault("driver", "ping")
        d.setdefault("driver_cfg", {})
        if not isinstance(d["driver_cfg"], dict):
            d["driver_cfg"] = {}

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "cfg": cfg,
            "running": collector_running(),
            "last_status": last_status,
        },
    )


@app.post("/settings")
def update_settings(
    site_name: str = Form(...),
    site_token: str = Form(...),
    api_url: str = Form(...),
):
    cfg = load_config(CONFIG_PATH)
    cfg["site_name"] = site_name.strip()
    cfg["site_token"] = site_token.strip()
    cfg["api_url"] = api_url.strip()
    save_config(CONFIG_PATH, cfg)
    return RedirectResponse("/", status_code=303)


@app.post("/devices/add")
def add_device(
    ip: str = Form(...),
    name: str = Form(""),
    building: str = Form(""),
    room: str = Form(""),
    device_type: str = Form("unknown"),
    driver: str = Form("ping"),
    pjlink_password: str = Form(""),
    pjlink_port: str = Form("4352"),
    pjlink_timeout_s: str = Form("2"),
):
    cfg = load_config(CONFIG_PATH)
    cfg.setdefault("devices", [])

    ip = ip.strip()
    if not ip:
        return RedirectResponse("/", status_code=303)

    if any(d.get("ip") == ip for d in cfg["devices"]):
        return RedirectResponse("/", status_code=303)

    driver = (driver or "ping").strip().lower()
    driver_cfg = {}

    if driver == "pjlink":
        try:
            port = int(pjlink_port)
        except Exception:
            port = 4352
        try:
            timeout_s = int(pjlink_timeout_s)
        except Exception:
            timeout_s = 2

        driver_cfg = {
            "password": (pjlink_password or "").strip(),
            "port": port,
            "timeout_s": timeout_s,
        }

    cfg["devices"].append(
        {
            "ip": ip,
            "name": name.strip(),
            "building": building.strip(),
            "room": room.strip(),
            "type": device_type.strip(),
            "driver": driver,
            "driver_cfg": driver_cfg,
        }
    )
    save_config(CONFIG_PATH, cfg)
    return RedirectResponse("/", status_code=303)


@app.post("/devices/update")
def update_device(
    original_ip: str = Form(...),
    ip: str = Form(...),
    name: str = Form(""),
    building: str = Form(""),
    room: str = Form(""),
    device_type: str = Form("unknown"),
    driver: str = Form("ping"),
    pjlink_password: str = Form(""),
    pjlink_port: str = Form("4352"),
    pjlink_timeout_s: str = Form("2"),
):
    cfg = load_config(CONFIG_PATH)
    devices = cfg.get("devices", [])

    original_ip = original_ip.strip()
    ip = ip.strip()
    if not original_ip or not ip:
        return RedirectResponse("/", status_code=303)

    if ip != original_ip and any(d.get("ip") == ip for d in devices):
        return RedirectResponse("/", status_code=303)

    driver = (driver or "ping").strip().lower()
    driver_cfg = {}

    if driver == "pjlink":
        try:
            port = int(pjlink_port)
        except Exception:
            port = 4352
        try:
            timeout_s = int(pjlink_timeout_s)
        except Exception:
            timeout_s = 2

        driver_cfg = {
            "password": (pjlink_password or "").strip(),
            "port": port,
            "timeout_s": timeout_s,
        }

    for d in devices:
        if d.get("ip") == original_ip:
            d["ip"] = ip
            d["name"] = name.strip()
            d["building"] = building.strip()
            d["room"] = room.strip()
            d["type"] = device_type.strip()
            d["driver"] = driver
            d["driver_cfg"] = driver_cfg
            break

    cfg["devices"] = devices
    save_config(CONFIG_PATH, cfg)
    return RedirectResponse("/", status_code=303)


@app.post("/devices/delete")
def delete_device(ip: str = Form(...)):
    cfg = load_config(CONFIG_PATH)
    ip = ip.strip()
    cfg["devices"] = [d for d in cfg.get("devices", []) if d.get("ip") != ip]
    save_config(CONFIG_PATH, cfg)
    return RedirectResponse("/", status_code=303)


@app.post("/collector/start")
def start_collector():
    ensure_collector_running()
    return RedirectResponse("/", status_code=303)


@app.post("/collector/stop")
def stop_collector_route():
    stop_collector()
    return RedirectResponse("/", status_code=303)