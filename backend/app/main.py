# backend/app/main.py
from __future__ import annotations

import json
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .db import SessionLocal, engine
from .models import Base, Site, Device

templates = Jinja2Templates(directory="app/templates")


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _uptime_centis_to_human(value: Any) -> str:
    """
    sysUpTime SNMP est en centièmes de seconde.
    """
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

    parts: List[str] = []
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


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_getattr(obj: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(obj, name)
    except Exception:
        return default


def _safe_setattr(obj: Any, name: str, value: Any) -> None:
    try:
        if hasattr(obj, name):
            setattr(obj, name, value)
    except Exception:
        pass


def _norm_status(v: Any) -> str:
    s = (str(v or "").strip().lower()) or "unknown"
    if s not in {"online", "offline", "unknown"}:
        return s
    return s


def _count_statuses(devices: List[Device]) -> Dict[str, int]:
    """
    Comptage standardisé pour KPI.
    """
    online = 0
    offline = 0
    unknown = 0

    for d in devices:
        st = _norm_status(d.status)
        if st == "online":
            online += 1
        elif st == "offline":
            offline += 1
        else:
            unknown += 1

    return {"online": online, "offline": offline, "unknown": unknown, "total": len(devices)}


# ------------------------------------------------------------
# DB dependency
# ------------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ------------------------------------------------------------
# App + DB init retry
# ------------------------------------------------------------
app = FastAPI(title="AV Monitoring MVP Backend")


def _init_db_with_retry(max_wait_s: int = 25) -> None:
    """
    En Docker, le backend peut démarrer avant postgres.
    On attend un peu avant d'échouer.
    """
    start = time.time()
    last_err: Optional[Exception] = None
    while time.time() - start < max_wait_s:
        try:
            Base.metadata.create_all(bind=engine)
            return
        except Exception as e:
            last_err = e
            time.sleep(1)
    if last_err:
        raise last_err


_init_db_with_retry()


# ------------------------------------------------------------
# Root
# ------------------------------------------------------------
@app.get("/", include_in_schema=False)
def root():
    # UI par défaut
    return RedirectResponse(url="/ui/dashboard", status_code=302)


# ------------------------------------------------------------
# Health
# ------------------------------------------------------------
@app.get("/health")
def health():
    return {"ok": True, "ts": _now_utc().isoformat()}


# ------------------------------------------------------------
# Admin API: create site (token auto si non fourni)
# ------------------------------------------------------------
@app.post("/admin/create-site")
def create_site(name: str, token: str | None = None, db: Session = Depends(get_db)):
    """
    API simple (peut être appelée à la main ou via un petit front).
    - Si le site existe => retourne son token (utile)
    - Sinon => crée et retourne le token généré
    """
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


# ------------------------------------------------------------
# Ingest (Agent -> Backend)
# ------------------------------------------------------------
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
        incoming_type = str(d.get("device_type") or d.get("type") or "unknown").strip() or "unknown"
        incoming_driver = (d.get("driver") or "ping").strip() or "ping"

        incoming_building = (d.get("building") or "").strip()
        incoming_room = (d.get("room") or "").strip()

        incoming_status = (d.get("status") or "unknown").strip()
        incoming_detail = (d.get("detail") or "").strip() or None

        # verdict optionnel (ok/fault/expected_off/doubt/unknown)
        incoming_verdict = (d.get("verdict") or "").strip().lower() or None

        incoming_metrics = _as_dict(d.get("metrics") or {})

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

        # Champs standard
        dev.name = incoming_name
        dev.device_type = incoming_type
        dev.driver = incoming_driver
        dev.status = incoming_status
        dev.detail = incoming_detail
        dev.last_seen = now

        # Champs optionnels selon ton models.py / migrations
        _safe_setattr(dev, "building", incoming_building)
        _safe_setattr(dev, "room", incoming_room)

        # metrics : si colonne présente -> set. Sinon -> on les ignore (mais on ne casse pas).
        if hasattr(dev, "metrics"):
            _safe_setattr(dev, "metrics", incoming_metrics)

        # verdict : si colonne présente -> set; sinon, on le met dans metrics["verdict"] si possible
        if incoming_verdict:
            if hasattr(dev, "verdict"):
                _safe_setattr(dev, "verdict", incoming_verdict)
            else:
                if hasattr(dev, "metrics"):
                    m = _as_dict(_safe_getattr(dev, "metrics", {}) or {})
                    m["verdict"] = incoming_verdict
                    _safe_setattr(dev, "metrics", m)

        # last_ok_at : on garde la dernière fois où l'équipement est vu online
        if incoming_status.strip().lower() == "online":
            _safe_setattr(dev, "last_ok_at", now)

        upserted += 1

    db.commit()
    return {"ok": True, "upserted": upserted}


# ------------------------------------------------------------
# API JSON
# ------------------------------------------------------------
@app.get("/devices")
def list_devices(db: Session = Depends(get_db)):
    rows = db.query(Device).order_by(Device.site_id.asc(), Device.ip.asc()).all()
    out: List[Dict[str, Any]] = []

    for d in rows:
        metrics = _as_dict(_safe_getattr(d, "metrics", {}) or {})
        out.append(
            {
                "id": d.id,
                "site_id": d.site_id,
                "name": d.name,
                "ip": d.ip,
                "type": d.device_type,
                "driver": d.driver,
                "building": (_safe_getattr(d, "building", "") or "").strip(),
                "room": (_safe_getattr(d, "room", "") or "").strip(),
                "status": d.status,
                "detail": d.detail,
                "verdict": (_safe_getattr(d, "verdict", None) or metrics.get("verdict")),
                "metrics": metrics,
                "last_seen": d.last_seen.isoformat() if d.last_seen else None,
                "last_ok_at": (
                    _safe_getattr(d, "last_ok_at", None).isoformat()
                    if _safe_getattr(d, "last_ok_at", None)
                    else None
                ),
            }
        )
    return out


@app.get("/devices/{device_id}")
def device_detail(device_id: int, db: Session = Depends(get_db)):
    d = db.query(Device).filter(Device.id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")

    metrics = _as_dict(_safe_getattr(d, "metrics", {}) or {})
    return {
        "id": d.id,
        "site_id": d.site_id,
        "name": d.name,
        "ip": d.ip,
        "type": d.device_type,
        "driver": d.driver,
        "building": (_safe_getattr(d, "building", "") or "").strip(),
        "room": (_safe_getattr(d, "room", "") or "").strip(),
        "status": d.status,
        "detail": d.detail,
        "verdict": (_safe_getattr(d, "verdict", None) or metrics.get("verdict")),
        "metrics": metrics,
        "last_seen": d.last_seen.isoformat() if d.last_seen else None,
        "last_ok_at": (
            _safe_getattr(d, "last_ok_at", None).isoformat()
            if _safe_getattr(d, "last_ok_at", None)
            else None
        ),
    }


# ------------------------------------------------------------
# UI : Dashboard (ajouté)
# ------------------------------------------------------------
@app.get("/ui/dashboard", response_class=HTMLResponse)
def ui_dashboard(request: Request, db: Session = Depends(get_db)):
    sites = db.query(Site).order_by(Site.id.asc()).all()
    devices = db.query(Device).all()

    # KPIs globaux
    st = _count_statuses(devices)
    kpis = {
        "total_sites": len(sites),
        "total_devices": st["total"],
        "offline_devices": st["offline"],
        "unknown_devices": st["unknown"],
        "online_devices": st["online"],
    }

    # Cards par site (pour dashboard.html)
    site_cards: List[Dict[str, Any]] = []
    for s in sites:
        site_devs = [d for d in devices if d.site_id == s.id]
        st_site = _count_statuses(site_devs)

        site_cards.append(
            {
                "id": s.id,
                "name": s.name,
                "device_count": st_site["total"],
                "offline_count": st_site["offline"],
                # "has_contact" est prévu dans votre template, mais pas encore modélisé.
                # On reste explicite et non bloquant.
                "has_contact": bool(_safe_getattr(s, "contact", None) or _safe_getattr(s, "email", None)),
            }
        )

    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "kpis": kpis, "site_cards": site_cards},
    )


# ------------------------------------------------------------
# UI : Agents
# ------------------------------------------------------------
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


# ------------------------------------------------------------
# UI : Devices by Agent (tri bâtiment / salle + KPIs)
# ------------------------------------------------------------
@app.get("/ui/agents/{site_id}/devices", response_class=HTMLResponse)
def ui_agent_devices(request: Request, site_id: int, db: Session = Depends(get_db)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    rows = db.query(Device).filter(Device.site_id == site_id).all()

    # KPIs site (utiles pour un header / résumé)
    st_site = _count_statuses(rows)

    # Verdicts (si présents)
    fault = 0
    expected_off = 0
    doubt = 0
    for d in rows:
        m = _as_dict(_safe_getattr(d, "metrics", {}) or {})
        verdict = (_safe_getattr(d, "verdict", None) or m.get("verdict") or "").strip().lower()
        if verdict == "fault":
            fault += 1
        elif verdict == "expected_off":
            expected_off += 1
        elif verdict == "doubt":
            doubt += 1

    kpis = {
        "total_devices": st_site["total"],
        "online_devices": st_site["online"],
        "offline_devices": st_site["offline"],
        "unknown_devices": st_site["unknown"],
        "fault_devices": fault,
        "expected_off_devices": expected_off,
        "doubt_devices": doubt,
    }

    def _key(d: Device):
        b = ((_safe_getattr(d, "building", "") or "").strip() or "—").lower()
        r = ((_safe_getattr(d, "room", "") or "").strip() or "—").lower()
        return (b, r, (d.ip or "").lower())

    rows_sorted = sorted(rows, key=_key)

    grouped: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

    for d in rows_sorted:
        building = (_safe_getattr(d, "building", "") or "").strip() or "—"
        room = (_safe_getattr(d, "room", "") or "").strip() or "—"

        m = _as_dict(_safe_getattr(d, "metrics", {}) or {})
        verdict = (_safe_getattr(d, "verdict", None) or m.get("verdict") or "").strip()

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
            "building": building,
            "room": room,
            "status": d.status,
            "detail": d.detail,
            "verdict": verdict,
            "last_seen": d.last_seen.isoformat() if d.last_seen else None,
            "last_ok_at": (
                _safe_getattr(d, "last_ok_at", None).isoformat()
                if _safe_getattr(d, "last_ok_at", None)
                else None
            ),
            "metrics": m_view,
        }

        grouped.setdefault(building, {}).setdefault(room, []).append(dv)

    return templates.TemplateResponse(
        "agent_devices.html",
        {
            "request": request,
            "site": {"id": site.id, "name": site.name},
            "grouped": grouped,
            "kpis": kpis,  # <-- ajouté (corrige KPI à 0 côté template si vous l’affichez)
        },
    )


# ------------------------------------------------------------
# UI : Device detail
# ------------------------------------------------------------
@app.get("/ui/devices/{device_id}", response_class=HTMLResponse)
def ui_device_detail(request: Request, device_id: int, db: Session = Depends(get_db)):
    d = db.query(Device).filter(Device.id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")

    m = _as_dict(_safe_getattr(d, "metrics", {}) or {})
    verdict = (_safe_getattr(d, "verdict", None) or m.get("verdict") or "").strip()

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
        "building": (_safe_getattr(d, "building", "") or "").strip(),
        "room": (_safe_getattr(d, "room", "") or "").strip(),
        "status": d.status,
        "detail": d.detail,
        "verdict": verdict,
        "last_seen": d.last_seen.isoformat() if d.last_seen else None,
        "last_ok_at": (
            _safe_getattr(d, "last_ok_at", None).isoformat()
            if _safe_getattr(d, "last_ok_at", None)
            else None
        ),
    }

    return templates.TemplateResponse(
        "device_detail.html",
        {"request": request, "device": device_view, "metrics": m_view, "metrics_json": metrics_json},
    )