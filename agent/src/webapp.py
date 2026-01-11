# agent/src/webapp.py
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

    # Normalise les anciens devices (compatibilité)
    for d in cfg.get("devices", []):
        d.setdefault("name", "")
        d.setdefault("building", "")
        d.setdefault("room", "")
        d.setdefault("type", "unknown")
        d.setdefault("driver", "ping")
        d.setdefault("snmp", {})

    cfg.setdefault("reporting", {})
    cfg["reporting"].setdefault("ok_interval_s", 3600)
    cfg["reporting"].setdefault("ko_interval_s", 60)

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
    ok_interval_s: int = Form(3600),
    ko_interval_s: int = Form(60),
):
    cfg = load_config(CONFIG_PATH)
    cfg["site_name"] = site_name.strip()
    cfg["site_token"] = site_token.strip()
    cfg["api_url"] = api_url.strip()

    cfg.setdefault("reporting", {})
    cfg["reporting"]["ok_interval_s"] = int(ok_interval_s)
    cfg["reporting"]["ko_interval_s"] = int(ko_interval_s)

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
    snmp_community: str = Form("public"),
    snmp_port: int = Form(161),
    snmp_timeout_s: int = Form(1),
    snmp_retries: int = Form(1),
):
    cfg = load_config(CONFIG_PATH)
    cfg.setdefault("devices", [])

    ip = ip.strip()
    if not ip:
        return RedirectResponse("/", status_code=303)

    if any(d.get("ip") == ip for d in cfg["devices"]):
        return RedirectResponse("/", status_code=303)

    device = {
        "ip": ip,
        "name": name.strip(),
        "building": building.strip(),
        "room": room.strip(),
        "type": device_type.strip(),
        "driver": driver.strip(),
    }

    if driver.strip() == "snmp":
        device["snmp"] = {
            "community": snmp_community.strip() or "public",
            "port": int(snmp_port),
            "timeout_s": int(snmp_timeout_s),
            "retries": int(snmp_retries),
        }

    cfg["devices"].append(device)
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
    snmp_community: str = Form("public"),
    snmp_port: int = Form(161),
    snmp_timeout_s: int = Form(1),
    snmp_retries: int = Form(1),
):
    cfg = load_config(CONFIG_PATH)
    devices = cfg.get("devices", [])

    original_ip = original_ip.strip()
    ip = ip.strip()
    if not original_ip or not ip:
        return RedirectResponse("/", status_code=303)

    if ip != original_ip and any(d.get("ip") == ip for d in devices):
        return RedirectResponse("/", status_code=303)

    for d in devices:
        if d.get("ip") == original_ip:
            d["ip"] = ip
            d["name"] = name.strip()
            d["building"] = building.strip()
            d["room"] = room.strip()
            d["type"] = device_type.strip()
            d["driver"] = driver.strip()

            if driver.strip() == "snmp":
                d["snmp"] = {
                    "community": snmp_community.strip() or "public",
                    "port": int(snmp_port),
                    "timeout_s": int(snmp_timeout_s),
                    "retries": int(snmp_retries),
                }
            else:
                d["snmp"] = {}

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