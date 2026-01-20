# backend/app/main.py
from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from .db import SessionLocal, engine
from .models import Base, Site, Device, DeviceEvent, DeviceAlert

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


def _count_verdicts(devices: List[Device]) -> Dict[str, int]:
    """
    Comptage des verdicts pour KPI.
    """
    fault = 0
    doubt = 0
    expected_off = 0
    ok = 0

    for d in devices:
        verdict = (d.verdict or _as_dict(d.metrics).get("verdict") or "").strip().lower()
        if verdict == "fault":
            fault += 1
        elif verdict == "doubt":
            doubt += 1
        elif verdict == "expected_off":
            expected_off += 1
        elif verdict == "ok":
            ok += 1

    return {"fault": fault, "doubt": doubt, "expected_off": expected_off, "ok": ok}


# ------------------------------------------------------------
# Event & Alert logic
# ------------------------------------------------------------
def record_event_and_alerts(
    db: Session,
    site: Site,
    device: Device,
    incoming_data: Dict[str, Any],
    now: datetime
) -> None:
    """
    Option A: écrire un event uniquement si (status, verdict, detail) change OU si last event > 60 minutes.
    Ouvrir/fermer/mettre à jour les alertes selon le verdict/status.
    """
    try:
        # Récupérer le dernier event pour ce device
        last_event = (
            db.query(DeviceEvent)
            .filter(DeviceEvent.device_id == device.id)
            .order_by(DeviceEvent.created_at.desc())
            .first()
        )

        # Déterminer si on doit écrire un nouvel event
        should_write_event = False
        if last_event is None:
            should_write_event = True
        else:
            # Vérifier si les valeurs ont changé
            status_changed = last_event.status != device.status
            verdict_changed = last_event.verdict != device.verdict
            detail_changed = last_event.detail != device.detail

            # Vérifier si le dernier event date de plus de 60 minutes
            time_threshold = 60 * 60  # 60 minutes en secondes
            time_diff = (now - last_event.created_at).total_seconds()
            time_exceeded = time_diff > time_threshold

            should_write_event = status_changed or verdict_changed or detail_changed or time_exceeded

        # Écrire l'event si nécessaire
        if should_write_event:
            event = DeviceEvent(
                device_id=device.id,
                site_id=site.id,
                ip=device.ip,
                name=device.name,
                building=device.building,
                room=device.room,
                device_type=device.device_type,
                driver=device.driver,
                status=device.status,
                verdict=device.verdict,
                detail=device.detail,
                metrics_json=_as_dict(device.metrics),
                created_at=now,
            )
            db.add(event)

        # Gestion des alertes
        # Récupérer l'alerte active (non fermée) pour ce device
        active_alert = (
            db.query(DeviceAlert)
            .filter(DeviceAlert.device_id == device.id)
            .filter(DeviceAlert.closed_at.is_(None))
            .first()
        )

        # Déterminer si on doit ouvrir une alerte (verdict == "fault" ou status == "offline" si pas de verdict)
        is_fault = device.verdict == "fault" if device.verdict else device.status == "offline"

        if is_fault:
            # Ouvrir ou mettre à jour l'alerte
            if active_alert is None:
                # Créer une nouvelle alerte
                severity = "critical" if device.verdict == "fault" else "warning"
                alert = DeviceAlert(
                    site_id=site.id,
                    device_id=device.id,
                    severity=severity,
                    opened_at=now,
                    last_seen_at=now,
                    status=device.status,
                    verdict=device.verdict,
                    detail=device.detail,
                )
                db.add(alert)
            else:
                # Mettre à jour l'alerte existante
                active_alert.last_seen_at = now
                active_alert.status = device.status
                active_alert.verdict = device.verdict
                active_alert.detail = device.detail
        else:
            # Fermer l'alerte si elle existe
            if active_alert is not None:
                active_alert.closed_at = now

        db.commit()

    except Exception as e:
        db.rollback()
        # Log l'erreur mais ne pas faire échouer l'ingest
        print(f"Error recording event/alert for device {device.ip}: {e}")


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

# Add session middleware for one-time token display
app.add_middleware(SessionMiddleware, secret_key=secrets.token_urlsafe(32))


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
# Purge system
# ------------------------------------------------------------
def purge_old_data() -> None:
    """
    Supprime les DeviceEvent et DeviceAlert closed plus vieux que EVENT_RETENTION_DAYS.
    """
    try:
        retention_days = int(os.getenv("EVENT_RETENTION_DAYS", "30"))
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        db = SessionLocal()
        try:
            # Supprimer les anciens events
            deleted_events = db.query(DeviceEvent).filter(
                DeviceEvent.created_at < cutoff_date
            ).delete(synchronize_session=False)

            # Supprimer les alertes fermées anciennes
            deleted_alerts = db.query(DeviceAlert).filter(
                DeviceAlert.closed_at.isnot(None),
                DeviceAlert.closed_at < cutoff_date
            ).delete(synchronize_session=False)

            db.commit()
            print(f"Purge completed: deleted {deleted_events} events and {deleted_alerts} closed alerts older than {retention_days} days")
        except Exception as e:
            db.rollback()
            print(f"Error during purge: {e}")
        finally:
            db.close()
    except Exception as e:
        print(f"Error in purge_old_data: {e}")


def run_purge_loop() -> None:
    """
    Boucle de purge qui s'exécute toutes les PURGE_INTERVAL_HOURS heures.
    """
    try:
        interval_hours = int(os.getenv("PURGE_INTERVAL_HOURS", "24"))
        interval_seconds = interval_hours * 3600

        while True:
            time.sleep(interval_seconds)
            purge_old_data()
    except Exception as e:
        print(f"Error in purge loop: {e}")


# Démarrer le thread de purge en daemon
purge_thread = threading.Thread(target=run_purge_loop, daemon=True)
purge_thread.start()

# Exécuter une purge au démarrage (après un court délai pour laisser le temps à la DB de se stabiliser)
def initial_purge():
    time.sleep(10)
    purge_old_data()

initial_purge_thread = threading.Thread(target=initial_purge, daemon=True)
initial_purge_thread.start()


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
# Admin API: delete site
# ------------------------------------------------------------
@app.post("/admin/delete-site")
def delete_site(site_id: int, db: Session = Depends(get_db)):
    """
    Supprime un site et tous ses équipements associés.
    """
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Supprimer tous les équipements du site
    db.query(Device).filter(Device.site_id == site_id).delete()

    # Supprimer le site
    db.delete(site)
    db.commit()

    return {"ok": True, "message": f"Site {site.name} deleted"}


# ------------------------------------------------------------
# Admin API: renew site token
# ------------------------------------------------------------
@app.post("/admin/renew-token")
def renew_site_token(site_id: int, db: Session = Depends(get_db)):
    """
    Génère un nouveau token pour un site existant.
    """
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Générer un nouveau token
    new_token = secrets.token_urlsafe(32)
    site.token = new_token
    db.commit()

    return {"ok": True, "site_id": site.id, "site": site.name, "token": new_token}


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
        incoming_floor = (d.get("floor") or "").strip()
        incoming_room = (d.get("room") or "").strip()

        incoming_status = (d.get("status") or "unknown").strip()
        incoming_detail = (d.get("detail") or "").strip() or None

        # verdict optionnel (ok/fault/expected_off/doubt/unknown)
        incoming_verdict = (d.get("verdict") or "").strip().lower() or None

        incoming_metrics = _as_dict(d.get("metrics") or {})

        # Extraire driver_config (snmp, pjlink) depuis le payload agent
        incoming_snmp = _as_dict(d.get("snmp") or {})
        incoming_pjlink = _as_dict(d.get("pjlink") or {})
        incoming_driver_config = {}
        if incoming_snmp:
            incoming_driver_config["snmp"] = incoming_snmp
        if incoming_pjlink:
            incoming_driver_config["pjlink"] = incoming_pjlink

        # Extraire expectations depuis le payload agent
        incoming_expectations = _as_dict(d.get("expectations") or {})

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
                driver_config=incoming_driver_config,
                expectations=incoming_expectations,
            )
            db.add(dev)

        # Champs standard
        dev.name = incoming_name
        dev.device_type = incoming_type
        dev.driver = incoming_driver
        dev.status = incoming_status
        dev.detail = incoming_detail
        dev.last_seen = now
        dev.building = incoming_building
        dev.floor = incoming_floor
        dev.room = incoming_room

        # driver_config et expectations
        dev.driver_config = incoming_driver_config
        dev.expectations = incoming_expectations

        # metrics
        dev.metrics = incoming_metrics

        # verdict
        if incoming_verdict:
            dev.verdict = incoming_verdict
        else:
            # Si pas de verdict dans le payload, on peut le récupérer depuis metrics
            dev.verdict = incoming_metrics.get("verdict", None)

        # last_ok_at : on garde la dernière fois où l'équipement est vu online
        if incoming_status.strip().lower() == "online":
            dev.last_ok_at = now

        # Commit le device avant de créer les events
        db.commit()
        db.refresh(dev)

        # Enregistrer l'event et gérer les alertes
        record_event_and_alerts(db, site, dev, d, now)

        upserted += 1

    return {"ok": True, "upserted": upserted}


# ------------------------------------------------------------
# Config sync endpoint (Agent Pull)
# ------------------------------------------------------------
def _compute_config_hash(site: Site, devices: List[Device]) -> str:
    """
    Calcule un hash MD5 de la configuration complète du site.
    Ce hash permet à l'agent de détecter rapidement si la config a changé.
    """
    config_data = {
        "site_name": site.name,
        "timezone": site.timezone or "Europe/Paris",
        "doubt_after_days": site.doubt_after_days or 2,
        "ok_interval_s": site.ok_interval_s or 300,
        "ko_interval_s": site.ko_interval_s or 60,
        "devices": []
    }

    for d in sorted(devices, key=lambda x: x.ip):
        device_data = {
            "ip": d.ip,
            "name": d.name,
            "building": d.building or "",
            "floor": d.floor or "",
            "room": d.room or "",
            "type": d.device_type,
            "driver": d.driver,
            "driver_config": d.driver_config or {},
            "expectations": d.expectations or {},
        }
        config_data["devices"].append(device_data)

    # Serialization JSON déterministe
    json_str = json.dumps(config_data, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(json_str.encode('utf-8')).hexdigest()


@app.get("/config/{site_token}")
def get_config(site_token: str, db: Session = Depends(get_db)):
    """
    Endpoint de synchronisation pull pour l'agent.

    L'agent appelle cet endpoint régulièrement avec son token.
    Le backend répond avec:
    - config_hash: empreinte MD5 de la configuration
    - site_name, timezone, doubt_after_days, etc.
    - devices[]: liste complète des équipements avec leur configuration

    L'agent compare config_hash avec sa version locale et met à jour si nécessaire.
    """
    site = db.query(Site).filter(Site.token == site_token).first()
    if not site:
        raise HTTPException(status_code=404, detail="Invalid site token")

    devices = db.query(Device).filter(Device.site_id == site.id).all()

    # Calculer le hash de la config actuelle
    config_hash = _compute_config_hash(site, devices)

    # Mettre à jour le config_version dans la DB si changé
    if site.config_version != config_hash:
        site.config_version = config_hash
        site.config_updated_at = _now_utc()
        db.commit()

    # Construire la réponse
    devices_config = []
    for d in devices:
        driver_cfg = _as_dict(d.driver_config or {})
        expectations = _as_dict(d.expectations or {})

        device_data = {
            "ip": d.ip,
            "name": d.name,
            "building": d.building or "",
            "floor": d.floor or "",
            "room": d.room or "",
            "type": d.device_type,
            "driver": d.driver,
            "snmp": driver_cfg.get("snmp", {}),
            "pjlink": driver_cfg.get("pjlink", {}),
            "expectations": expectations,
        }
        devices_config.append(device_data)

    response = {
        "config_hash": config_hash,
        "site_name": site.name,
        "timezone": site.timezone or "Europe/Paris",
        "doubt_after_days": site.doubt_after_days or 2,
        "reporting": {
            "ok_interval_s": site.ok_interval_s or 300,
            "ko_interval_s": site.ko_interval_s or 60,
        },
        "devices": devices_config,
    }

    return response


# ------------------------------------------------------------
# Device management (CRUD)
# ------------------------------------------------------------
@app.post("/ui/devices/create")
def create_device(
    site_id: int = Form(...),
    ip: str = Form(...),
    name: str = Form(""),
    building: str = Form(""),
    floor: str = Form(""),
    room: str = Form(""),
    device_type: str = Form("unknown"),
    driver: str = Form("ping"),
    # SNMP
    snmp_community: str = Form("public"),
    snmp_port: int = Form(161),
    snmp_timeout_s: int = Form(1),
    snmp_retries: int = Form(1),
    # PJLink
    pjlink_password: str = Form(""),
    pjlink_port: int = Form(4352),
    pjlink_timeout_s: int = Form(2),
    # Expectations
    always_on: str = Form(""),
    alert_after_s: int = Form(300),
    sched_days: str = Form("mon,tue,wed,thu,fri"),
    sched_start: str = Form("07:30"),
    sched_end: str = Form("19:00"),
    sched_timezone: str = Form("Europe/Paris"),
    db: Session = Depends(get_db),
):
    """Crée un nouvel équipement."""
    ip = (ip or "").strip()
    if not ip:
        return RedirectResponse(f"/ui/agents/{site_id}/devices", status_code=303)

    # Vérifier si l'IP existe déjà pour ce site
    existing = db.query(Device).filter(Device.site_id == site_id, Device.ip == ip).first()
    if existing:
        return RedirectResponse(f"/ui/agents/{site_id}/devices", status_code=303)

    driver = (driver or "ping").strip().lower()

    # Driver configs
    snmp_block = {}
    if driver == "snmp":
        snmp_block = {
            "community": (snmp_community or "public").strip(),
            "port": max(1, snmp_port),
            "timeout_s": max(1, snmp_timeout_s),
            "retries": max(0, snmp_retries),
        }

    pj_block = {}
    if driver == "pjlink":
        pj_block = {
            "password": (pjlink_password or "").strip(),
            "port": max(1, pjlink_port),
            "timeout_s": max(1, pjlink_timeout_s),
        }

    driver_config = {}
    if snmp_block:
        driver_config["snmp"] = snmp_block
    if pj_block:
        driver_config["pjlink"] = pj_block

    # Expectations
    ao = (always_on or "").strip().lower() in {"1", "true", "on", "yes"}
    a_s = max(15, alert_after_s)

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

    expectations = {
        "always_on": ao,
        "alert_after_s": a_s,
        "schedule": schedule,
    }

    # Créer l'équipement
    new_device = Device(
        site_id=site_id,
        ip=ip,
        name=(name or "").strip(),
        building=(building or "").strip(),
        floor=(floor or "").strip(),
        room=(room or "").strip(),
        device_type=(device_type or "unknown").strip(),
        driver=driver,
        driver_config=driver_config,
        expectations=expectations,
        status="unknown",
    )

    db.add(new_device)
    db.commit()

    return RedirectResponse(f"/ui/agents/{site_id}/devices", status_code=303)


@app.post("/ui/devices/{device_id}/update")
def update_device_from_backend(
    device_id: int,
    ip: str = Form(...),
    name: str = Form(""),
    building: str = Form(""),
    floor: str = Form(""),
    room: str = Form(""),
    device_type: str = Form("unknown"),
    driver: str = Form("ping"),
    # SNMP
    snmp_community: str = Form("public"),
    snmp_port: int = Form(161),
    snmp_timeout_s: int = Form(1),
    snmp_retries: int = Form(1),
    # PJLink
    pjlink_password: str = Form(""),
    pjlink_port: int = Form(4352),
    pjlink_timeout_s: int = Form(2),
    db: Session = Depends(get_db),
):
    """Met à jour un équipement existant."""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    site_id = device.site_id
    ip = (ip or "").strip()
    if not ip:
        return RedirectResponse(f"/ui/agents/{site_id}/devices", status_code=303)

    # Vérifier collision IP (sauf si c'est la même IP)
    if ip != device.ip:
        existing = db.query(Device).filter(
            Device.site_id == site_id,
            Device.ip == ip,
            Device.id != device_id
        ).first()
        if existing:
            return RedirectResponse(f"/ui/agents/{site_id}/devices", status_code=303)

    driver = (driver or "ping").strip().lower()

    # Driver configs
    snmp_block = {}
    if driver == "snmp":
        snmp_block = {
            "community": (snmp_community or "public").strip(),
            "port": max(1, snmp_port),
            "timeout_s": max(1, snmp_timeout_s),
            "retries": max(0, snmp_retries),
        }

    pj_block = {}
    if driver == "pjlink":
        pj_block = {
            "password": (pjlink_password or "").strip(),
            "port": max(1, pjlink_port),
            "timeout_s": max(1, pjlink_timeout_s),
        }

    driver_config = {}
    if snmp_block:
        driver_config["snmp"] = snmp_block
    if pj_block:
        driver_config["pjlink"] = pj_block

    # Mettre à jour l'équipement
    device.ip = ip
    device.name = (name or "").strip()
    device.building = (building or "").strip()
    device.floor = (floor or "").strip()
    device.room = (room or "").strip()
    device.device_type = (device_type or "unknown").strip()
    device.driver = driver
    device.driver_config = driver_config

    db.commit()

    # Mettre à jour le config_hash pour déclencher la sync agent
    site = db.query(Site).filter(Site.id == site_id).first()
    if site:
        devices = db.query(Device).filter(Device.site_id == site_id).all()
        new_hash = _compute_config_hash(site, devices)
        site.config_version = new_hash
        site.config_updated_at = _now_utc()
        db.commit()

    return RedirectResponse(f"/ui/agents/{site_id}/devices?saved=1", status_code=303)


@app.post("/ui/devices/{device_id}/delete")
def delete_device(device_id: int, db: Session = Depends(get_db)):
    """Supprime un équipement et ses événements associés."""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    site_id = device.site_id

    # Supprimer d'abord tous les événements associés à cet équipement
    db.query(DeviceEvent).filter(DeviceEvent.device_id == device_id).delete()

    # Puis supprimer l'équipement
    db.delete(device)
    db.commit()

    return RedirectResponse(f"/ui/agents/{site_id}/devices", status_code=303)


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
# API : Device History & Uptime
# ------------------------------------------------------------
@app.get("/api/devices/{device_id}/history")
def api_device_history(device_id: int, days: int = 30, db: Session = Depends(get_db)):
    """Retourne l'historique d'états d'un équipement sur N jours."""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    cutoff = _now_utc() - timedelta(days=days)
    events = (
        db.query(DeviceEvent)
        .filter(DeviceEvent.device_id == device_id)
        .filter(DeviceEvent.created_at >= cutoff)
        .order_by(DeviceEvent.created_at.asc())
        .all()
    )

    return {
        "device_id": device_id,
        "device_name": device.name,
        "device_ip": device.ip,
        "period_days": days,
        "events": [
            {
                "timestamp": e.created_at.isoformat(),
                "status": e.status,
                "verdict": e.verdict,
                "detail": e.detail,
            }
            for e in events
        ],
    }


@app.get("/api/devices/{device_id}/uptime")
def api_device_uptime(device_id: int, days: int = 30, db: Session = Depends(get_db)):
    """Calcule le pourcentage de disponibilité d'un équipement sur N jours."""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    cutoff = _now_utc() - timedelta(days=days)
    events = (
        db.query(DeviceEvent)
        .filter(DeviceEvent.device_id == device_id)
        .filter(DeviceEvent.created_at >= cutoff)
        .order_by(DeviceEvent.created_at.asc())
        .all()
    )

    if not events:
        return {
            "device_id": device_id,
            "period_days": days,
            "uptime_percent": None,
            "total_events": 0,
            "online_events": 0,
            "offline_events": 0,
        }

    online_count = sum(1 for e in events if e.status == "online")
    offline_count = sum(1 for e in events if e.status == "offline")
    total = len(events)

    uptime_percent = round((online_count / total) * 100, 2) if total > 0 else 0

    return {
        "device_id": device_id,
        "device_name": device.name,
        "device_ip": device.ip,
        "period_days": days,
        "uptime_percent": uptime_percent,
        "total_events": total,
        "online_events": online_count,
        "offline_events": offline_count,
    }


@app.get("/api/sites/map-data")
def api_sites_map_data(db: Session = Depends(get_db)):
    """Retourne les données pour afficher une carte des sites."""
    sites = db.query(Site).all()

    map_data = []
    for site in sites:
        if not site.latitude or not site.longitude:
            continue  # Skip sites sans coordonnées

        # Compter les devices et leur statut
        devices = db.query(Device).filter(Device.site_id == site.id).all()
        total = len(devices)
        online = sum(1 for d in devices if d.status == "online")
        offline = sum(1 for d in devices if d.status == "offline")
        unknown = total - online - offline

        # Déterminer la couleur de la pin
        if offline > 0:
            color = "red"
        elif unknown > 0:
            color = "orange"
        else:
            color = "green"

        map_data.append({
            "site_id": site.id,
            "site_name": site.name,
            "address": site.address,
            "latitude": float(site.latitude),
            "longitude": float(site.longitude),
            "color": color,
            "devices_total": total,
            "devices_online": online,
            "devices_offline": offline,
            "devices_unknown": unknown,
        })

    return {"sites": map_data}


# ------------------------------------------------------------
# UI : Dashboard (ajouté)
# ------------------------------------------------------------
@app.get("/ui/dashboard", response_class=HTMLResponse)
def ui_dashboard(request: Request, db: Session = Depends(get_db)):
    sites = db.query(Site).order_by(Site.id.asc()).all()
    devices = db.query(Device).all()

    # KPIs globaux
    st = _count_statuses(devices)
    vd = _count_verdicts(devices)
    kpis = {
        "total_sites": len(sites),
        "total_devices": st["total"],
        "offline_devices": st["offline"],
        "unknown_devices": st["unknown"],
        "online_devices": st["online"],
        "faults": vd["fault"],
        "doubts": vd["doubt"],
        "expected_off": vd["expected_off"],
    }

    # Cards par site (pour dashboard.html)
    site_cards: List[Dict[str, Any]] = []
    for s in sites:
        site_devs = [d for d in devices if d.site_id == s.id]
        st_site = _count_statuses(site_devs)
        vd_site = _count_verdicts(site_devs)

        site_cards.append(
            {
                "id": s.id,
                "name": s.name,
                "device_count": st_site["total"],
                "offline_count": st_site["offline"],
                "unknown_count": st_site["unknown"],
                "fault_count": vd_site["fault"],
                "has_contact": bool(
                    s.contact_email or s.contact_phone or s.contact_first_name
                ),
            }
        )

    # Récupérer les 20 derniers événements
    recent_events_raw = (
        db.query(DeviceEvent)
        .order_by(DeviceEvent.created_at.desc())
        .limit(20)
        .all()
    )

    # Préparer les événements pour l'affichage
    recent_events = []
    for ev in recent_events_raw:
        # Récupérer le site pour avoir le nom
        site = db.query(Site).filter(Site.id == ev.site_id).first()
        site_name = site.name if site else f"Site #{ev.site_id}"

        recent_events.append({
            "id": ev.id,
            "site_name": site_name,
            "site_id": ev.site_id,
            "device_name": ev.name or ev.ip,
            "device_id": ev.device_id,
            "ip": ev.ip,
            "building": ev.building or "—",
            "room": ev.room or "—",
            "status": ev.status,
            "verdict": ev.verdict or "—",
            "detail": ev.detail or "",
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
        })

    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "kpis": kpis, "site_cards": site_cards, "recent_events": recent_events},
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

    # Récupérer le token one-time s'il existe dans la session
    new_token_data = request.session.pop("new_token", None)

    return templates.TemplateResponse(
        "agents.html",
        {"request": request, "sites": view, "new_token": new_token_data},
    )


# ------------------------------------------------------------
# UI : Create Site
# ------------------------------------------------------------
@app.post("/ui/sites/create")
def ui_create_site(
    request: Request,
    name: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Crée un nouveau site via l'interface web et stocke le token dans la session.
    """
    name = (name or "").strip()
    if not name:
        return RedirectResponse("/ui/agents", status_code=303)

    # Vérifier si le site existe déjà
    existing = db.query(Site).filter(Site.name == name).first()
    if existing:
        return RedirectResponse("/ui/agents", status_code=303)

    # Créer le site avec un token généré
    token = secrets.token_urlsafe(32)
    site = Site(name=name, token=token)
    db.add(site)
    db.commit()
    db.refresh(site)

    # Stocker le token dans la session pour l'afficher une seule fois
    request.session["new_token"] = {
        "site_id": site.id,
        "site_name": site.name,
        "token": token
    }

    return RedirectResponse("/ui/agents", status_code=303)


# ------------------------------------------------------------
# UI : Delete Site
# ------------------------------------------------------------
@app.post("/ui/sites/delete")
def ui_delete_site(
    site_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """
    Supprime un site via l'interface web.
    """
    site = db.query(Site).filter(Site.id == site_id).first()
    if site:
        # Supprimer tous les équipements du site
        db.query(Device).filter(Device.site_id == site_id).delete()
        # Supprimer le site
        db.delete(site)
        db.commit()

    return RedirectResponse("/ui/agents", status_code=303)


# ------------------------------------------------------------
# UI : Renew Token
# ------------------------------------------------------------
@app.post("/ui/sites/renew-token")
def ui_renew_token(
    request: Request,
    site_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """
    Renouvelle le token d'un site via l'interface web.
    """
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        return RedirectResponse("/ui/agents", status_code=303)

    # Générer un nouveau token
    new_token = secrets.token_urlsafe(32)
    site.token = new_token
    db.commit()

    # Stocker le token dans la session pour l'afficher une seule fois
    request.session["new_token"] = {
        "site_id": site.id,
        "site_name": site.name,
        "token": new_token,
        "renewed": True
    }

    return RedirectResponse("/ui/agents", status_code=303)


# ------------------------------------------------------------
# UI : Update Site Contact
# ------------------------------------------------------------
@app.post("/ui/agents/{site_id}/contact")
def ui_update_site_contact(
    site_id: int,
    contact_first_name: str = Form(""),
    contact_last_name: str = Form(""),
    contact_title: str = Form(""),
    contact_email: str = Form(""),
    contact_phone: str = Form(""),
    db: Session = Depends(get_db)
):
    """Met à jour les informations de contact d'un site."""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    site.contact_first_name = (contact_first_name or "").strip() or None
    site.contact_last_name = (contact_last_name or "").strip() or None
    site.contact_title = (contact_title or "").strip() or None
    site.contact_email = (contact_email or "").strip() or None
    site.contact_phone = (contact_phone or "").strip() or None

    db.commit()

    return RedirectResponse(f"/ui/agents/{site_id}/devices?saved=1", status_code=303)


# ------------------------------------------------------------
# UI : Update Site Reporting Intervals
# ------------------------------------------------------------
@app.post("/ui/agents/{site_id}/reporting")
def ui_update_site_reporting(
    site_id: int,
    ok_interval_s: int = Form(...),
    ko_interval_s: int = Form(...),
    db: Session = Depends(get_db)
):
    """Met à jour les intervalles de reporting d'un site."""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Validation des valeurs
    site.ok_interval_s = max(60, ok_interval_s)
    site.ko_interval_s = max(15, ko_interval_s)

    db.commit()

    # Mettre à jour le config_version pour déclencher la sync agent
    devices = db.query(Device).filter(Device.site_id == site.id).all()
    new_hash = _compute_config_hash(site, devices)
    site.config_version = new_hash
    site.config_updated_at = _now_utc()
    db.commit()

    return RedirectResponse(f"/ui/agents/{site_id}/devices?saved=1", status_code=303)


# ------------------------------------------------------------
# UI : Update Site Location
# ------------------------------------------------------------
@app.post("/ui/agents/{site_id}/location")
def ui_update_site_location(
    site_id: int,
    address: str = Form(""),
    latitude: str = Form(""),
    longitude: str = Form(""),
    db: Session = Depends(get_db)
):
    """Met à jour la localisation géographique d'un site."""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    site.address = (address or "").strip() or None
    site.latitude = (latitude or "").strip() or None
    site.longitude = (longitude or "").strip() or None

    db.commit()

    return RedirectResponse(f"/ui/agents/{site_id}/devices?saved=1", status_code=303)


# ------------------------------------------------------------
# UI : Devices by Agent (tri bâtiment / salle + KPIs)
# ------------------------------------------------------------
@app.get("/ui/agents/{site_id}/devices", response_class=HTMLResponse)
def ui_agent_devices(request: Request, site_id: int, saved: int = 0, db: Session = Depends(get_db)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    rows = db.query(Device).filter(Device.site_id == site_id).all()

    # KPIs site (utiles pour un header / résumé)
    st_site = _count_statuses(rows)
    vd_site = _count_verdicts(rows)

    kpis = {
        "total_devices": st_site["total"],
        "online_devices": st_site["online"],
        "offline_devices": st_site["offline"],
        "unknown_devices": st_site["unknown"],
        "fault_devices": vd_site["fault"],
        "expected_off_devices": vd_site["expected_off"],
        "doubt_devices": vd_site["doubt"],
    }

    def _key(d: Device):
        b = ((_safe_getattr(d, "building", "") or "").strip() or "—").lower()
        r = ((_safe_getattr(d, "room", "") or "").strip() or "—").lower()
        return (b, r, (d.ip or "").lower())

    rows_sorted = sorted(rows, key=_key)

    grouped: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

    for d in rows_sorted:
        building = (d.building or "").strip() or "—"
        room = (d.room or "").strip() or "—"

        m = _as_dict(d.metrics or {})
        verdict = (d.verdict or m.get("verdict") or "").strip()

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
            "last_ok_at": d.last_ok_at.isoformat() if d.last_ok_at else None,
            "metrics": m_view,
        }

        grouped.setdefault(building, {}).setdefault(room, []).append(dv)

    return templates.TemplateResponse(
        "agent_devices.html",
        {
            "request": request,
            "site": site,  # Passer l'objet site complet pour accéder aux champs de config
            "grouped": grouped,
            "kpis": kpis,
            "saved": saved == 1,
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

    m = _as_dict(d.metrics or {})
    verdict = (d.verdict or m.get("verdict") or "").strip()

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
        "building": (d.building or "").strip(),
        "room": (d.room or "").strip(),
        "status": d.status,
        "detail": d.detail,
        "verdict": verdict,
        "last_seen": d.last_seen.isoformat() if d.last_seen else None,
        "last_ok_at": d.last_ok_at.isoformat() if d.last_ok_at else None,
    }

    return templates.TemplateResponse(
        "device_detail.html",
        {"request": request, "device": device_view, "metrics": m_view, "metrics_json": metrics_json},
    )