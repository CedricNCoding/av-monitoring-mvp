import json
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Depends, Header, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .db import SessionLocal, engine
from .models import Base, Site, Device

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AV Monitoring MVP Backend")
templates = Jinja2Templates(directory="app/templates")


# ---------- DB dependency ----------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _now_utc():
    return datetime.now(timezone.utc)


# ---------- Helpers UI ----------
def _uptime_centis_to_human(value: Any) -> str:
    if value is None:
        return ""
    try:
        n = int(str(value).strip())
    except Exception:
        return ""

    total_seconds = n // 100  # sysUpTime = centièmes de seconde
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


# ---------- Admin ----------
@app.post("/admin/create-site")
def create_site(name: str, token: str | None = None, db: Session = Depends(get_db)):
    name = (name or "").strip()
    token = (token or "").strip() if token else None

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


# ---------- Ingest ----------
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

        incoming_name = (d.get("name") or "").strip() or ip
        incoming_type = (
            str(d.get("device_type") or d.get("type") or "unknown").strip()
            or "unknown"
        )
        incoming_driver = (d.get("driver") or "ping").strip() or "ping"

        incoming_building = (d.get("building") or "").strip()
        incoming_room = (d.get("room") or "").strip()

        incoming_status = (d.get("status") or "unknown").strip()
        incoming_detail = (d.get("detail") or "").strip() or None

        incoming_metrics = d.get("metrics") or {}
        if not isinstance(incoming_metrics, dict):
            incoming_metrics = {}

        dev = (
            db.query(Device)
            .filter(Device.site_id == site.id)
            .filter(Device.ip == ip)
            .first()
        )

        if dev is None:
            dev = Device(
                site_id=site.id,
                ip=ip,
                name=incoming_name,
                device_type=incoming_type,
                driver=incoming_driver,
            )
            db.add(dev)

        dev.name = incoming_name
        dev.device_type = incoming_type
        dev.driver = incoming_driver

        dev.building = incoming_building
        dev.room = incoming_room

        dev.status = incoming_status
        dev.detail = incoming_detail
        dev.metrics = incoming_metrics
        dev.last_seen = now

        upserted += 1

    db.commit()
    return {"ok": True, "upserted": upserted}


# ---------- API ----------
@app.get("/devices")
def list_devices(db: Session = Depends(get_db)):
    rows = db.query(Device).order_by(Device.site_id.asc(), Device.ip.asc()).all()
    out: List[Dict[str, Any]] = []
    for d in rows:
        out.append(
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
        )
    return out


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


# ---------- UI : Agents ----------
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


# ---------- UI : Devices by Agent, tri bâtiment/salle ----------
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
        building = d.building.strip() if d.building else ""
        room = d.room.strip() if d.room else ""
        building = building or "—"
        room = room or "—"

        m = d.metrics or {}
        if not isinstance(m, dict):
            m = {}

        m_view = dict(m)
        m_view["uptime_human"] = _uptime_centis_to_human(m.get("sys_uptime"))
        m_view["sys_descr_short"] = _sys_descr_short(m.get("sys_descr"))

        dv = {
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
            "metrics": m_view,
        }

        grouped.setdefault(building, {}).setdefault(room, []).append(dv)

    return templates.TemplateResponse(
        "agent_devices.html",
        {"request": request, "site": {"id": site.id, "name": site.name}, "grouped": grouped},
    )


# ---------- UI : Device detail ----------
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
        {"request": request, "device": device_view, "metrics": m_view, "metrics_json": metrics_json},
    )


# ---------- UI : Sites (création + token auto) ----------
@app.get("/ui/sites", response_class=HTMLResponse)
def ui_sites(request: Request, db: Session = Depends(get_db)):
    rows = db.query(Site).order_by(Site.id.asc()).all()
    return templates.TemplateResponse(
        "sites.html",
        {"request": request, "sites": rows, "created": None, "error": None},
    )


@app.post("/ui/sites/create", response_class=HTMLResponse)
def ui_sites_create(request: Request, name: str = Form(...), db: Session = Depends(get_db)):
    name = (name or "").strip()

    if not name:
        rows = db.query(Site).order_by(Site.id.asc()).all()
        return templates.TemplateResponse(
            "sites.html",
            {"request": request, "sites": rows, "created": None, "error": "Nom vide"},
        )

    existing = db.query(Site).filter(Site.name == name).first()
    if existing:
        rows = db.query(Site).order_by(Site.id.asc()).all()
        return templates.TemplateResponse(
            "sites.html",
            {
                "request": request,
                "sites": rows,
                "created": {
                    "site_id": existing.id,
                    "site": existing.name,
                    "token": existing.token,
                    "already": True,
                },
                "error": None,
            },
        )

    token = secrets.token_urlsafe(32)
    s = Site(name=name, token=token)
    db.add(s)
    db.commit()
    db.refresh(s)

    rows = db.query(Site).order_by(Site.id.asc()).all()
    return templates.TemplateResponse(
        "sites.html",
        {
            "request": request,
            "sites": rows,
            "created": {"site_id": s.id, "site": s.name, "token": s.token, "already": False},
            "error": None,
        },
    )