# agent/src/webapp.py
from __future__ import annotations

import os
import threading
from typing import Any, Dict, Optional

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


# ---------------------------------------------------------------------
# Collector control
# ---------------------------------------------------------------------
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


# ---------------------------------------------------------------------
# Status normalization helpers
# ---------------------------------------------------------------------
def _as_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _normalize_last_status(raw: Any) -> Dict[str, Any]:
    """
    Normalise le dict de statut pour éviter les incohérences template.

    Objectifs:
    - toujours renvoyer un dict (jamais None)
    - assurer la présence des clés attendues
    - exposer des alias backward compatibles:
        - next_collect_in_s <-> next_send_in_s
        - last_run_at <-> last_collect_at
        - last_send_ok stable
    """
    s = _as_dict(raw)

    # Valeurs usuelles venant de collector.py
    # next_collect_in_s: int|None
    # last_run_at: str|None (iso)
    # last_send_ok: bool|None
    # last_send_error: str|None

    next_collect = s.get("next_collect_in_s", None)
    if next_collect is None:
        # certains templates/anciennes versions utilisaient next_send_in_s
        next_collect = s.get("next_send_in_s", None)

    # last_run_at alias
    last_run_at = s.get("last_run_at", None)
    if last_run_at is None:
        last_run_at = s.get("last_collect_at", None)

    # last_send_ok est la clé principale
    last_send_ok = s.get("last_send_ok", None)
    # tolérance si une ancienne version utilisait une autre clé
    if last_send_ok is None and "send_ok" in s:
        last_send_ok = s.get("send_ok")

    last_send_error = s.get("last_send_error", None)
    if last_send_error is None and "send_error" in s:
        last_send_error = s.get("send_error")

    normalized: Dict[str, Any] = {
        # clés “canon”
        "next_collect_in_s": next_collect,
        "last_run_at": last_run_at,
        "last_send_ok": last_send_ok,
        "last_send_error": last_send_error,
    }

    # Alias backward compatibles
    normalized["next_send_in_s"] = normalized["next_collect_in_s"]
    normalized["last_collect_at"] = normalized["last_run_at"]

    # Conserve d'éventuelles infos additionnelles
    # (par ex. last_payload_size, last_post_status, etc.)
    for k, v in s.items():
        if k not in normalized:
            normalized[k] = v

    return normalized


# ---------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    cfg = load_config(CONFIG_PATH)

    raw = get_last_status()
    last_status = _normalize_last_status(raw)

    # compat template: certains index.html utilisent "status" au lieu de "last_status"
    context = {
        "request": request,
        "cfg": cfg,
        "running": collector_running(),
        "last_status": last_status,
        "status": last_status,  # alias
    }

    return templates.TemplateResponse("index.html", context)


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
    floor: str = Form(""),
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

    if any((d.get("ip") or "").strip() == ip for d in cfg["devices"]):
        return RedirectResponse("/", status_code=303)

    driver = (driver or "ping").strip().lower()

    # driver configs
    snmp_block: Dict[str, Any] = {}
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

    pj_block: Dict[str, Any] = {}
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

    schedule: Dict[str, Any] = {}
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
            "floor": (floor or "").strip(),
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
    floor: str = Form(""),
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
    if ip != original_ip and any((d.get("ip") or "").strip() == ip for d in devices):
        return RedirectResponse("/", status_code=303)

    driver = (driver or "ping").strip().lower()

    snmp_block: Dict[str, Any] = {}
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

    pj_block: Dict[str, Any] = {}
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

    schedule: Dict[str, Any] = {}
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
            d["floor"] = (floor or "").strip()
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