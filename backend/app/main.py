from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .db import SessionLocal, engine
from .models import Base, Site, Device

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AV Monitoring MVP Backend")


# ---------- DB dependency ----------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _now_utc():
    return datetime.now(timezone.utc)


# ---------- Admin ----------
@app.post("/admin/create-site")
def create_site(name: str, token: str, db: Session = Depends(get_db)):
    name = (name or "").strip()
    token = (token or "").strip()
    if not name or not token:
        raise HTTPException(status_code=400, detail="Missing name or token")

    existing = db.query(Site).filter(Site.name == name).first()
    if existing:
        return {"created": False, "site": name}

    s = Site(name=name, token=token)
    db.add(s)
    db.commit()
    return {"created": True, "site": name}


# ---------- Ingest ----------
@app.post("/ingest")
def ingest(
    payload: Dict[str, Any],
    x_site_token: Optional[str] = Header(default=None, alias="X-Site-Token"),
    db: Session = Depends(get_db),
):
    """
    Payload attendu:
    {
      "site_name": "site-demo",
      "devices": [
        {
          "ip": "192.168.1.241",
          "status": "online",
          "detail": "snmp_ok",
          "metrics": {...},
          "name": "...", "building": "...", "room": "...", "device_type": "...", "driver": "...", "check": "..."
        },
        ...
      ]
    }

    Auth: header X-Site-Token
    """
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

        # Champs “compatibles” avec votre backend actuel (qui mettait name=ip et type=unknown)
        # + prise en compte des nouveaux champs envoyés par l’agent si présents.
        incoming_name = (d.get("name") or "").strip() or ip
        incoming_type = (d.get("device_type") or d.get("type") or "unknown")
        incoming_type = str(incoming_type).strip() or "unknown"
        incoming_driver = (d.get("driver") or "ping").strip() or "ping"

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

        # Mise à jour
        dev.name = incoming_name
        dev.device_type = incoming_type
        dev.driver = incoming_driver
        dev.status = incoming_status
        dev.detail = incoming_detail
        dev.last_seen = now

        # ✅ NOUVEAU : stockage du “message SNMP” et métriques
        dev.metrics = incoming_metrics

        upserted += 1

    db.commit()
    return {"ok": True, "upserted": upserted}


# ---------- Devices list ----------
@app.get("/devices")
def list_devices(db: Session = Depends(get_db)):
    """
    Vue synthèse + inclut metrics pour debug (MVP).
    """
    rows = db.query(Device).order_by(Device.site_id.asc(), Device.ip.asc()).all()

    out: List[Dict[str, Any]] = []
    for d in rows:
        out.append(
            {
                "site_id": d.site_id,
                "name": d.name,
                "ip": d.ip,
                "type": d.device_type,
                "driver": d.driver,
                "status": d.status,
                "detail": d.detail,
                "metrics": d.metrics or {},  # ✅ visible ici
                "last_seen": d.last_seen.isoformat() if d.last_seen else None,
            }
        )
    return out


# ---------- Device detail (recommandé) ----------
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
        "status": d.status,
        "detail": d.detail,
        "metrics": d.metrics or {},
        "last_seen": d.last_seen.isoformat() if d.last_seen else None,
    }