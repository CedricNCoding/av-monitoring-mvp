from fastapi import FastAPI, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from .db import Base, engine, SessionLocal
from .models import Site, Device
from .schemas import TelemetryPayload

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AV Monitoring MVP")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/admin/create-site")
def create_site(name: str, token: str, db: Session = Depends(get_db)):
    exists = db.query(Site).filter(Site.name == name).first()
    if exists:
        return {"created": False, "reason": "already exists"}
    site = Site(name=name, token=token)
    db.add(site)
    db.commit()
    return {"created": True, "site": name}

@app.post("/ingest")
def ingest(payload: TelemetryPayload, x_site_token: str = Header(None), db: Session = Depends(get_db)):
    if not x_site_token:
        raise HTTPException(status_code=401, detail="Missing X-Site-Token header")

    site = db.query(Site).filter(Site.name == payload.site_name).first()
    if not site:
        raise HTTPException(status_code=401, detail="Unknown site (create it first)")
    if site.token != x_site_token:
        raise HTTPException(status_code=401, detail="Invalid site token")

    for d in payload.devices:
        dev = db.query(Device).filter(Device.site_id == site.id, Device.ip == d.ip).first()
        if not dev:
            dev = Device(
                site_id=site.id,
                name=d.ip,
                device_type="unknown",
                ip=d.ip,
                driver="auto",
            )
            db.add(dev)

        dev.status = d.status
        dev.detail = d.detail
        dev.last_seen = func.now()

    db.commit()
    return {"ingested": len(payload.devices)}

@app.get("/devices")
def list_devices(db: Session = Depends(get_db)):
    devs = db.query(Device).order_by(Device.site_id, Device.name).all()
    return [
        {
            "site_id": d.site_id,
            "name": d.name,
            "ip": d.ip,
            "type": d.device_type,
            "status": d.status,
            "detail": d.detail,
            "last_seen": d.last_seen,
        }
        for d in devs
    ]
