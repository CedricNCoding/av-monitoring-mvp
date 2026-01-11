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


def _to_int(value: str, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _snmp_block(driver: str, community: str, port: str, timeout_s: str, retries: str) -> dict:
    """
    Construit le bloc SNMP stocké dans config.json.
    Si driver != snmp => bloc vide.
    """
    if (driver or "").strip() != "snmp":
        return {}

    return {
        "community": (community or "public").strip() or "public",
        "port": _to_int(port, 161),
        "timeout_s": _to_int(timeout_s, 1),
        "retries": _to_int(retries, 1),
    }


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

        # Normalisation SNMP
        sn = d.get("snmp")
        if not isinstance(sn, dict):
            sn = {}
        d["snmp"] = {
            "community": (sn.get("community") or "public"),
            "port": _to_int(sn.get("port", 161), 161),
            "timeout_s": _to_int(sn.get("timeout_s", 1), 1),
            "retries": _to_int(sn.get("retries", 1), 1),
        } if d.get("driver") == "snmp" else {}

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
    snmp_community: str = Form("public"),
    snmp_port: str = Form("161"),
    snmp_timeout_s: str = Form("1"),
    snmp_retries: str = Form("1"),
):
    cfg = load_config(CONFIG_PATH)
    cfg.setdefault("devices", [])

    ip = ip.strip()
    driver = driver.strip()

    if not ip:
        return RedirectResponse("/", status_code=303)

    # Anti-doublon sur IP
    if any(d.get("ip") == ip for d in cfg["devices"]):
        return RedirectResponse("/", status_code=303)

    cfg["devices"].append(
        {
            "ip": ip,
            "name": name.strip(),
            "building": building.strip(),
            "room": room.strip(),
            "type": device_type.strip(),
            "driver": driver,
            "snmp": _snmp_block(driver, snmp_community, snmp_port, snmp_timeout_s, snmp_retries),
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
    snmp_community: str = Form("public"),
    snmp_port: str = Form("161"),
    snmp_timeout_s: str = Form("1"),
    snmp_retries: str = Form("1"),
):
    cfg = load_config(CONFIG_PATH)
    devices = cfg.get("devices", [])

    original_ip = original_ip.strip()
    ip = ip.strip()
    driver = driver.strip()

    if not original_ip or not ip:
        return RedirectResponse("/", status_code=303)

    # Si l'IP change, empêcher collision avec une autre entrée
    if ip != original_ip and any(d.get("ip") == ip for d in devices):
        return RedirectResponse("/", status_code=303)

    for d in devices:
        if d.get("ip") == original_ip:
            d["ip"] = ip
            d["name"] = name.strip()
            d["building"] = building.strip()
            d["room"] = room.strip()
            d["type"] = device_type.strip()
            d["driver"] = driver
            d["snmp"] = _snmp_block(driver, snmp_community, snmp_port, snmp_timeout_s, snmp_retries)
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