# backend/app/main.py
import json
import os
import secrets
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import (
    FastAPI,
    Depends,
    Header,
    HTTPException,
    Request,
    Form,
)
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .db import SessionLocal, engine
from .models import Base, Site, Device, DeviceEvent

# ---------------------------------------------------------------------
# INIT
# ---------------------------------------------------------------------

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AV Monitoring MVP Backend")
templates = Jinja2Templates(directory="app/templates")

# ---------------------------------------------------------------------
# Retention / Purge config
# ---------------------------------------------------------------------

def _env_int(name: str, default: int) -> int:
    try:
        v = int(str(os.getenv(name, "")).strip())
        return v
    except Exception:
        return default

EVENT_RETENTION_DAYS = _env_int("EVENT_RETENTION_DAYS", 90)      # ex: 90 jours
PURGE_INTERVAL_HOURS = _env_int("PURGE_INTERVAL_HOURS", 24)      # ex: toutes les 24h

# garde-fous
EVENT_RETENTION_DAYS = max(1, EVENT_RETENTION_DAYS)
PURGE_INTERVAL_HOURS = max(1, PURGE_INTERVAL_HOURS)

_purge_stop = {"stop": False}
_purge_thread: Optional[threading.Thread] = None

# ---------------------------------------------------------------------
# DB dependency
# ---------------------------------------------------------------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _now_utc():
    return datetime.now(timezone.utc)

# ---------------------------------------------------------------------
# Helpers UI
# ---------------------------------------------------------------------

def _uptime_centis_to_human(value: Any) -> str:
    if value is None:
        return ""
    try:
        n = int(str(value).strip())
    except Exception:
        return ""

    total_seconds = n // 100
    days = total_seconds // 86400
    rem = total_seconds % 86400
    hours = rem // 3600
    rem = rem % 3600
    minutes = rem // 60
    seconds = rem % 60

    parts = []
    if days:
        parts.append(f"{days}j")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


def _sys_descr_short(s: Any, max_len: int = 90) -> str:
    if not s:
        return ""
    txt = str(s).strip().replace("\n", " ")
    return txt if len(txt) <= max_len else (txt[: max_len - 1] + "…")


def _should_log_event(prev: Dict[str, Any], new: Dict[str, Any]) -> bool:
    if prev.get("status") != new.get("status"):
        return True
    if (prev.get("detail") or "") != (new.get("detail") or ""):
        return True
    if (prev.get("driver") or "") != (new.get("driver") or ""):
        return True

    prev_m = prev.get("metrics") or {}
    new_m = new.get("metrics") or {}
    if not isinstance(prev_m, dict):
        prev_m = {}
    if not isinstance(new_m, dict):
        new_m = {}

    for k in ("snmp_ok", "sys_uptime"):
        if (prev_m.get(k) or "") != (new_m.get(k) or ""):
            return True

    return False

# ---------------------------------------------------------------------
# Purge worker
# ---------------------------------------------------------------------

def purge_old_events_once(retention_days: int) -> int:
    """
    Supprime les events plus vieux que retention_days.
    Retourne le nombre de lignes supprimées.
    """
    cutoff = _now_utc() - timedelta(days=retention_days)

    db = SessionLocal()
    try:
        q = db.query(DeviceEvent).filter(DeviceEvent.created_at < cutoff)
        deleted = q.delete(synchronize_session=False)
        db.commit()
        return int(deleted or 0)
    except Exception as e:
        db.rollback()
        print(f"[purge] failed: {e}", flush=True)
        return 0
    finally:
        db.close()


def _purge_loop():
    print(
        f"[purge] started (retention_days={EVENT_RETENTION_DAYS}, interval_hours={PURGE_INTERVAL_HOURS})",
        flush=True,
    )

    # purge au démarrage (1 fois)
    deleted = purge_old_events_once(EVENT_RETENTION_DAYS)
    print(f"[purge] initial purge deleted={deleted}", flush=True)

    # boucle périodique
    sleep_s = PURGE_INTERVAL_HOURS * 3600
    while not _purge_stop.get("stop", False):
        # sommeil "interruptible"
        for _ in range(sleep_s):
            if _purge_stop.get("stop", False):
                break
            time.sleep(1)

        if _purge_stop.get("stop", False):
            break

        deleted = purge_old_events_once(EVENT_RETENTION_DAYS)
        print(f"[purge] periodic purge deleted={deleted}", flush=True)

    print("[purge] stopped", flush=True)


@app.on_event("startup")
def _startup():
    global _purge_thread
    if _purge_thread is None or not _purge_thread.is_alive():
        _purge_stop["stop"] = False
        _purge_thread = threading.Thread(target=_purge_loop, daemon=True)
        _purge_thread.start()


@app.on_event("shutdown")
def _shutdown():
    _purge_stop["stop"] = True

# ---------------------------------------------------------------------
# ADMIN / SITES API
# ---------------------------------------------------------------------

@app.post("/admin/create-site")
def create_site(name: str, token: Optional[str] = None, db: Session = Depends(get_db)):
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Missing name")

    existing = db.query(Site).filter(Site.name == name).first()
    if existing:
        return {
            "created": False,
            "site_id": existing.id,
            "site": existing.name,
            "token": existing.token,
        }

    if not token:
        token = secrets.token_urlsafe(32)

    s = Site(name=name, token=token)
    db.add(s)
    db.commit()
    db.refresh(s)

    return {"created": True, "site_id": s.id, "site": s.name, "token": s.token}

# ---------------------------------------------------------------------
# INGEST (AGENT → BACKEND)
# ---------------------------------------------------------------------

@app.post("/ingest")
def ingest(
    payload: Dict[str, Any],
    x_site_token: Optional[str] = Header(default=None, alias="X-Site-Token"),
    db: Session = Depends(get_db),
):
    if not x_site_token:
        raise HTTPException(status_code=401, detail="Missing X-Site-Token")

    site_name = (payload.get("site_name") or "").strip()
    devices = payload.get("devices") or []

    if not site_name or not isinstance(devices, list):
        raise HTTPException(status_code=400, detail="Invalid payload")

    site = db.query(Site).filter(Site.name == site_name).first()
    if not site:
        raise HTTPException(status_code=404, detail="Unknown site_name")

    if site.token != x_site_token:
        raise HTTPException(status_code=401, detail="Invalid site token")

    now = _now_utc()
    upserted = 0

    for d in devices:
        if not isinstance(d, dict):
            continue

        ip = (d.get("ip") or "").strip()
        if not ip:
            continue

        dev = (
            db.query(Device)
            .filter(Device.site_id == site.id)
            .filter(Device.ip == ip)
            .first()
        )

        is_new = False
        if dev is None:
            dev = Device(site_id=site.id, ip=ip)
            db.add(dev)
            db.flush()  # garantit dev.id
            is_new = True

        prev_snapshot = {
            "status": dev.status,
            "detail": dev.detail,
            "driver": dev.driver,
            "metrics": dev.metrics or {},
        }

        incoming = {
            "name": (d.get("name") or ip).strip(),
            "type": str(d.get("type") or d.get("device_type") or "unknown").strip() or "unknown",
            "driver": (d.get("driver") or "ping").strip() or "ping",
            "building": (d.get("building") or "").strip(),
            "room": (d.get("room") or "").strip(),
            "status": (d.get("status") or "unknown").strip() or "unknown",
            "detail": (d.get("detail") or None),
            "metrics": d.get("metrics") or {},
        }
        if not isinstance(incoming["metrics"], dict):
            incoming["metrics"] = {}

        dev.name = incoming["name"]
        dev.device_type = incoming["type"]
        dev.driver = incoming["driver"]
        dev.building = incoming["building"]
        dev.room = incoming["room"]
        dev.status = incoming["status"]
        dev.detail = incoming["detail"]
        dev.metrics = incoming["metrics"]
        dev.last_seen = now

        if is_new or _should_log_event(prev_snapshot, incoming):
            ev = DeviceEvent(
                device_id=dev.id,
                site_id=site.id,
                ip=ip,
                status=incoming["status"],
                detail=incoming["detail"],
                metrics=incoming["metrics"],
            )
            db.add(ev)

        upserted += 1

    db.commit()
    return {"ok": True, "upserted": upserted}

# ---------------------------------------------------------------------
# API DEVICES (JSON)
# ---------------------------------------------------------------------

@app.get("/devices")
def list_devices(db: Session = Depends(get_db)):
    rows = db.query(Device).order_by(Device.site_id.asc(), Device.ip.asc()).all()
    return [
        {
            "id": d.id,
            "site_id": d.site_id,
            "name": d.name,
            "ip": d.ip,
            "type": d.device_type,
            "driver": d.driver,
            "building": d.building,
            "room": d.room,
            "status": d.status,
            "detail": d.detail,
            "metrics": d.metrics or {},
            "last_seen": d.last_seen.isoformat() if d.last_seen else None,
        }
        for d in rows
    ]


@app.get("/devices/{device_id}")
def device_detail(device_id: int, db: Session = Depends(get_db)):
    d = db.query(Device).filter(Device.id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")

    return {
        "id": d.id,
        "site_id": d.site_id,
        "name": d.name,
        "ip": d.ip,
        "type": d.device_type,
        "driver": d.driver,
        "building": d.building,
        "room": d.room,
        "status": d.status,
        "detail": d.detail,
        "metrics": d.metrics or {},
        "last_seen": d.last_seen.isoformat() if d.last_seen else None,
    }


@app.get("/devices/{device_id}/events")
def device_events(device_id: int, limit: int = 100, db: Session = Depends(get_db)):
    rows = (
        db.query(DeviceEvent)
        .filter(DeviceEvent.device_id == device_id)
        .order_by(DeviceEvent.created_at.desc())
        .limit(min(max(limit, 1), 500))
        .all()
    )
    return [
        {
            "id": e.id,
            "device_id": e.device_id,
            "site_id": e.site_id,
            "ip": e.ip,
            "status": e.status,
            "detail": e.detail,
            "metrics": e.metrics or {},
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in rows
    ]

# ---------------------------------------------------------------------
# UI DASHBOARD
# ---------------------------------------------------------------------

@app.get("/ui", response_class=HTMLResponse)
def ui_dashboard(request: Request, db: Session = Depends(get_db)):
    sites = db.query(Site).order_by(Site.id.asc()).all()
    devices = db.query(Device).all()

    site_cards = []
    for s in sites:
        s_devs = [d for d in devices if d.site_id == s.id]
        offline = sum(1 for d in s_devs if (d.status or "").lower() == "offline")
        site_cards.append({
            "id": s.id,
            "name": s.name,
            "device_count": len(s_devs),
            "offline_count": offline,
            "has_contact": bool((s.contact_email or "").strip() or (s.contact_phone or "").strip()),
        })

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "kpis": {
                "total_sites": len(sites),
                "total_devices": len(devices),
                "offline_devices": sum(1 for d in devices if (d.status or "").lower() == "offline"),
                "unknown_devices": sum(1 for d in devices if (d.status or "").lower() == "unknown"),
            },
            "site_cards": site_cards,
        },
    )

# ---------------------------------------------------------------------
# UI SITES
# ---------------------------------------------------------------------

@app.get("/ui/sites", response_class=HTMLResponse)
def ui_sites(request: Request, db: Session = Depends(get_db)):
    sites = db.query(Site).order_by(Site.id.asc()).all()
    return templates.TemplateResponse(
        "sites.html",
        {"request": request, "sites": sites},
    )


@app.get("/ui/sites/{site_id}", response_class=HTMLResponse)
def ui_site_detail(request: Request, site_id: int, db: Session = Depends(get_db)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    devices = (
        db.query(Device)
        .filter(Device.site_id == site_id)
        .order_by(Device.building.asc(), Device.room.asc(), Device.ip.asc())
        .all()
    )

    return templates.TemplateResponse(
        "site_detail.html",
        {"request": request, "site": site, "devices": devices},
    )


@app.post("/ui/sites/{site_id}/contact", response_class=HTMLResponse)
def ui_site_update_contact(
    request: Request,
    site_id: int,
    contact_first_name: str = Form(""),
    contact_last_name: str = Form(""),
    contact_title: str = Form(""),
    contact_email: str = Form(""),
    contact_phone: str = Form(""),
    db: Session = Depends(get_db),
):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    site.contact_first_name = contact_first_name.strip()
    site.contact_last_name = contact_last_name.strip()
    site.contact_title = contact_title.strip()
    site.contact_email = contact_email.strip()
    site.contact_phone = contact_phone.strip()
    db.commit()

    devices = (
        db.query(Device)
        .filter(Device.site_id == site_id)
        .order_by(Device.building.asc(), Device.room.asc(), Device.ip.asc())
        .all()
    )

    return templates.TemplateResponse(
        "site_detail.html",
        {"request": request, "site": site, "devices": devices, "saved": True},
    )

# ---------------------------------------------------------------------
# UI AGENTS / DEVICES
# ---------------------------------------------------------------------

@app.get("/ui/agents", response_class=HTMLResponse)
def ui_agents(request: Request, db: Session = Depends(get_db)):
    sites = db.query(Site).order_by(Site.id.asc()).all()
    view = []
    for s in sites:
        count = db.query(Device).filter(Device.site_id == s.id).count()
        view.append({"id": s.id, "name": s.name, "device_count": count})

    return templates.TemplateResponse(
        "agents.html",
        {"request": request, "sites": view},
    )


@app.get("/ui/agents/{site_id}/devices", response_class=HTMLResponse)
def ui_agent_devices(request: Request, site_id: int, db: Session = Depends(get_db)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    rows = (
        db.query(Device)
        .filter(Device.site_id == site_id)
        .order_by(Device.building.asc(), Device.room.asc(), Device.ip.asc())
        .all()
    )

    grouped: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for d in rows:
        building = (d.building or "").strip() or "—"
        room = (d.room or "").strip() or "—"

        m = d.metrics or {}
        if not isinstance(m, dict):
            m = {}

        m_view = dict(m)
        m_view["uptime_human"] = _uptime_centis_to_human(m.get("sys_uptime"))
        m_view["sys_descr_short"] = _sys_descr_short(m.get("sys_descr"))

        grouped.setdefault(building, {}).setdefault(room, []).append({
            "id": d.id,
            "name": d.name,
            "ip": d.ip,
            "device_type": d.device_type,
            "driver": d.driver,
            "status": d.status,
            "detail": d.detail,
            "last_seen": d.last_seen.isoformat() if d.last_seen else None,
            "metrics": m_view,
        })

    return templates.TemplateResponse(
        "agent_devices.html",
        {"request": request, "site": {"id": site.id, "name": site.name}, "grouped": grouped},
    )

# ---------------------------------------------------------------------
# UI DEVICE DETAIL (WITH HISTORY)
# ---------------------------------------------------------------------

@app.get("/ui/devices/{device_id}", response_class=HTMLResponse)
def ui_device_detail(request: Request, device_id: int, db: Session = Depends(get_db)):
    d = db.query(Device).filter(Device.id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")

    m = d.metrics or {}
    if not isinstance(m, dict):
        m = {}

    m_view = dict(m)
    m_view["uptime_human"] = _uptime_centis_to_human(m.get("sys_uptime"))
    m_view["sys_descr_short"] = _sys_descr_short(m.get("sys_descr"))
    metrics_json = json.dumps(m_view, indent=2, ensure_ascii=False)

    events = (
        db.query(DeviceEvent)
        .filter(DeviceEvent.device_id == device_id)
        .order_by(DeviceEvent.created_at.desc())
        .limit(50)
        .all()
    )

    events_view = []
    for e in events:
        em = e.metrics or {}
        if not isinstance(em, dict):
            em = {}
        events_view.append({
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "status": e.status,
            "detail": e.detail,
            "uptime_human": _uptime_centis_to_human(em.get("sys_uptime")),
            "sys_descr_short": _sys_descr_short(em.get("sys_descr")),
            "snmp_ok": em.get("snmp_ok"),
        })

    device_view = {
        "id": d.id,
        "site_id": d.site_id,
        "name": d.name,
        "ip": d.ip,
        "device_type": d.device_type,
        "driver": d.driver,
        "building": d.building,
        "room": d.room,
        "status": d.status,
        "detail": d.detail,
        "last_seen": d.last_seen.isoformat() if d.last_seen else None,
    }

    return templates.TemplateResponse(
        "device_detail.html",
        {
            "request": request,
            "device": device_view,
            "metrics": m_view,
            "metrics_json": metrics_json,
            "events": events_view,
            "retention_days": EVENT_RETENTION_DAYS,
        },
    )