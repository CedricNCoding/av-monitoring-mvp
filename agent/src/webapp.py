# agent/src/webapp.py
import os
import threading
from typing import Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.storage import load_config, save_config
from src.collector import run_forever, get_last_status

CONFIG_PATH = os.getenv("AGENT_CONFIG", "/agent/config/config.json")

app = FastAPI(title="AV Agent - Local Admin")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

_stop_flag = {"stop": True}
_thread: Optional[threading.Thread] = None


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
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "cfg": cfg, "running": collector_running(), "last_status": last_status},
    )


@app.post("/settings")
def update_settings(
    api_url: str = Form(...),
    site_name: str = Form(...),
    site_token: str = Form(...),
    ok_interval_s: int = Form(300),
    ko_interval_s: int = Form(60),
):
    cfg = load_config(CONFIG_PATH)
    cfg["api_url"] = (api_url or "").strip()
    cfg["site_name"] = (site_name or "").strip()
    cfg["site_token"] = (site_token or "").strip()

    cfg.setdefault("reporting", {})
    cfg["reporting"]["ok_interval_s"] = max(60, int(ok_interval_s))
    cfg["reporting"]["ko_interval_s"] = max(15, int(ko_interval_s))

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
    # SNMP
    snmp_community: str = Form("public"),
    snmp_port: str = Form("161"),
    snmp_timeout_s: str = Form("1"),
    snmp_retries: str = Form("1"),
    # PJLINK
    pjlink_password: str = Form(""),
    pjlink_port: str = Form("4352"),
    pjlink_timeout_s: str = Form("2"),
    # expectations
    always_on: str = Form(""),
    alert_after_s: str = Form("300"),
    sched_days: str = Form("mon,tue,wed,thu,fri"),
    sched_start: str = Form("07:30"),
    sched_end: str = Form("19:00"),
    sched_timezone: str = Form("Europe/Paris"),
):
    cfg = load_config(CONFIG_PATH)
    cfg.setdefault("devices", [])

    ip = (ip or "").strip()
    if not ip:
        return RedirectResponse("/", status_code=303)
    if any(d.get("ip") == ip for d in cfg["devices"]):
        return RedirectResponse("/", status_code=303)

    driver = (driver or "ping").strip().lower()

    # driver configs
    snmp_block = {}
    if driver == "snmp":
        try:
            port = int(snmp_port)
        except Exception:
            port = 161
        try:
            timeout_i = int(snmp_timeout_s)
        except Exception:
            timeout_i = 1
        try:
            retries_i = int(snmp_retries)
        except Exception:
            retries_i = 1
        snmp_block = {
            "community": (snmp_community or "public").strip(),
            "port": port,
            "timeout_s": max(1, timeout_i),
            "retries": max(0, retries_i),
        }

    pj_block = {}
    if driver == "pjlink":
        try:
            port = int(pjlink_port)
        except Exception:
            port = 4352
        try:
            timeout_i = int(pjlink_timeout_s)
        except Exception:
            timeout_i = 2
        pj_block = {
            "password": (pjlink_password or "").strip(),
            "port": port,
            "timeout_s": max(1, timeout_i),
        }

    # expectations
    ao = (always_on or "").strip().lower() in {"1", "true", "on", "yes"}
    try:
        a_s = int(alert_after_s)
    except Exception:
        a_s = 300
    a_s = max(15, a_s)

    days = []
    for part in (sched_days or "").split(","):
        p = part.strip().lower()
        if p in {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}:
            days.append(p)

    schedule = {}
    if days and (sched_start or "").strip() and (sched_end or "").strip():
        schedule = {
            "timezone": (sched_timezone or "Europe/Paris").strip() or "Europe/Paris",
            "rules": [{"days": days, "start": (sched_start or "").strip(), "end": (sched_end or "").strip()}],
        }

    cfg["devices"].append(
        {
            "ip": ip,
            "name": (name or "").strip(),
            "building": (building or "").strip(),
            "room": (room or "").strip(),
            "type": (device_type or "unknown").strip(),
            "driver": driver,
            "snmp": snmp_block,
            "pjlink": pj_block,
            "expectations": {
                "always_on": ao,
                "alert_after_s": a_s,
                "schedule": schedule,
            },
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
    # SNMP
    snmp_community: str = Form("public"),
    snmp_port: str = Form("161"),
    snmp_timeout_s: str = Form("1"),
    snmp_retries: str = Form("1"),
    # PJLINK
    pjlink_password: str = Form(""),
    pjlink_port: str = Form("4352"),
    pjlink_timeout_s: str = Form("2"),
    # expectations
    always_on: str = Form(""),
    alert_after_s: str = Form("300"),
    sched_days: str = Form("mon,tue,wed,thu,fri"),
    sched_start: str = Form("07:30"),
    sched_end: str = Form("19:00"),
    sched_timezone: str = Form("Europe/Paris"),
):
    cfg = load_config(CONFIG_PATH)
    devices = cfg.get("devices", [])

    original_ip = (original_ip or "").strip()
    ip = (ip or "").strip()
    if not original_ip or not ip:
        return RedirectResponse("/", status_code=303)

    # collision si on change l'IP vers une autre déjà existante
    if ip != original_ip and any(d.get("ip") == ip for d in devices):
        return RedirectResponse("/", status_code=303)

    driver = (driver or "ping").strip().lower()

    snmp_block = {}
    if driver == "snmp":
        try:
            port = int(snmp_port)
        except Exception:
            port = 161
        try:
            timeout_i = int(snmp_timeout_s)
        except Exception:
            timeout_i = 1
        try:
            retries_i = int(snmp_retries)
        except Exception:
            retries_i = 1
        snmp_block = {
            "community": (snmp_community or "public").strip(),
            "port": port,
            "timeout_s": max(1, timeout_i),
            "retries": max(0, retries_i),
        }

    pj_block = {}
    if driver == "pjlink":
        try:
            port = int(pjlink_port)
        except Exception:
            port = 4352
        try:
            timeout_i = int(pjlink_timeout_s)
        except Exception:
            timeout_i = 2
        pj_block = {
            "password": (pjlink_password or "").strip(),
            "port": port,
            "timeout_s": max(1, timeout_i),
        }

    ao = (always_on or "").strip().lower() in {"1", "true", "on", "yes"}
    try:
        a_s = int(alert_after_s)
    except Exception:
        a_s = 300
    a_s = max(15, a_s)

    days = []
    for part in (sched_days or "").split(","):
        p = part.strip().lower()
        if p in {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}:
            days.append(p)

    schedule = {}
    if days and (sched_start or "").strip() and (sched_end or "").strip():
        schedule = {
            "timezone": (sched_timezone or "Europe/Paris").strip() or "Europe/Paris",
            "rules": [{"days": days, "start": (sched_start or "").strip(), "end": (sched_end or "").strip()}],
        }

    for d in devices:
        if (d.get("ip") or "").strip() == original_ip:
            d["ip"] = ip
            d["name"] = (name or "").strip()
            d["building"] = (building or "").strip()
            d["room"] = (room or "").strip()
            d["type"] = (device_type or "unknown").strip()
            d["driver"] = driver
            d["snmp"] = snmp_block
            d["pjlink"] = pj_block
            d["expectations"] = {
                "always_on": ao,
                "alert_after_s": a_s,
                "schedule": schedule,
            }
            break

    cfg["devices"] = devices
    save_config(CONFIG_PATH, cfg)
    return RedirectResponse("/", status_code=303)


@app.post("/devices/delete")
def delete_device(ip: str = Form(...)):
    cfg = load_config(CONFIG_PATH)
    ip = (ip or "").strip()
    cfg["devices"] = [d for d in cfg.get("devices", []) if (d.get("ip") or "").strip() != ip]
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