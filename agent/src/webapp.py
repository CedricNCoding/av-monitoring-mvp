# agent/src/webapp.py
from __future__ import annotations

import os
import threading
from typing import Any, Dict, Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.storage import load_config, save_config, ensure_runtime_dir
from src.collector import run_forever, get_last_status, get_last_results
from src.config_sync import start_sync_thread, get_sync_status

# Determine config path with proper fallback
CONFIG_PATH = os.getenv("AGENT_CONFIG", "/var/lib/avmonitoring/config.json")

# Log config path for debugging
print(f"🔧 Agent config path: {CONFIG_PATH}")

# Ensure runtime directory exists and is writable (fail fast if not)
try:
    ensure_runtime_dir(CONFIG_PATH)
except RuntimeError as e:
    print(f"❌ FATAL: {e}")
    import sys
    sys.exit(1)

app = FastAPI(title="AV Agent - Local Admin")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

_stop_flag = {"stop": True}
_thread: Optional[threading.Thread] = None

# Config sync
_sync_thread: Optional[threading.Thread] = None
_sync_stop_flag: Optional[Dict[str, bool]] = None


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

    # Récupérer les derniers résultats de collecte
    last_results = get_last_results()

    # Récupérer l'état de la synchronisation config
    sync_status = get_sync_status()

    # Context Zigbee (état MQTT + liste devices)
    zigbee_status = {"connected": False, "last_update": None}
    zigbee_devices = []
    try:
        from src.mqtt_client import get_mqtt_manager
        mqtt = get_mqtt_manager()
        zigbee_status = {
            "connected": mqtt.is_connected(),
            "last_update": mqtt.get_last_message_time(),
        }
        # Récupérer liste complète depuis bridge/devices
        all_devices = mqtt.get_all_devices()
        # Enrichir avec infos du cache
        for dev in all_devices:
            fn = dev.get("friendly_name", "")
            if not fn or fn == "Coordinator":
                continue  # Skip coordinator
            # Récupérer état depuis cache
            state = mqtt.get_device_state(fn)
            zigbee_devices.append({
                "friendly_name": fn,
                "ieee_address": dev.get("ieee_address", ""),
                "type": dev.get("type", "unknown"),
                "model_id": dev.get("model_id", ""),
                "manufacturer": dev.get("manufacturer", ""),
                "last_seen": state.get("last_seen") if state else None,
                "last_seen_relative": None,  # TODO: calculer "il y a X min"
                "battery": state.get("battery") if state else None,
                "linkquality": state.get("linkquality") if state else None,
            })
    except Exception as e:
        # MQTT non disponible ou erreur, ignorer silencieusement
        print(f"Zigbee context error (non-blocking): {e}")

    # compat template: certains index.html utilisent "status" au lieu de "last_status"
    context = {
        "request": request,
        "cfg": cfg,
        "running": collector_running(),
        "last_status": last_status,
        "status": last_status,  # alias
        "last_results": last_results,  # résultats par IP
        "sync_status": sync_status,  # état de la sync config
        "zigbee_status": zigbee_status,  # état MQTT Zigbee
        "zigbee_devices": zigbee_devices,  # liste devices Zigbee
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


@app.post("/sync/trigger")
def trigger_sync():
    """Force une synchronisation immédiate de la configuration."""
    from src.config_sync import sync_config_from_backend

    cfg = load_config(CONFIG_PATH)
    try:
        sync_config_from_backend(cfg)
    except Exception as e:
        print(f"⚠️  Manual sync failed: {e}")

    return RedirectResponse("/", status_code=303)


# ---------------------------------------------------------------------
# Endpoint MQTT Health
# ---------------------------------------------------------------------
@app.get("/mqtt/health")
def mqtt_health():
    """
    Retourne l'état de santé de la connexion MQTT.

    Returns:
        JSON avec:
        - configured: bool (env vars présentes)
        - connected: bool (actuellement connecté)
        - last_connect_ts: float|None (timestamp dernière connexion réussie)
        - last_error: str|None (dernière erreur rencontrée)
        - last_message_ts: float|None (timestamp dernier message reçu)
        - devices_in_cache: int (nombre de devices en cache)
    """
    try:
        from src.mqtt_client import get_mqtt_manager
        mqtt = get_mqtt_manager()
        return mqtt.get_health()
    except Exception as e:
        return {
            "configured": False,
            "connected": False,
            "last_connect_ts": None,
            "last_error": f"Failed to get MQTT health: {e}",
            "last_message_ts": None,
            "devices_in_cache": 0,
            "mqtt_available": False
        }


# ---------------------------------------------------------------------
# Endpoints Zigbee
# ---------------------------------------------------------------------
@app.post("/zigbee/permit_join")
def zigbee_permit_join():
    """Active le mode pairing Zigbee (60 secondes)."""
    try:
        from src.mqtt_client import get_mqtt_manager
        mqtt = get_mqtt_manager()
        mqtt.permit_join(60)
    except Exception as e:
        print(f"⚠️  Permit join failed: {e}")

    return RedirectResponse("/", status_code=303)


@app.post("/zigbee/rename")
def zigbee_rename(
    friendly_name: str = Form(...),
    new_name: str = Form(...)
):
    """Renomme un device Zigbee (via Z2M bridge)."""
    try:
        from src.mqtt_client import get_mqtt_manager
        mqtt = get_mqtt_manager()

        # Publier request rename vers Zigbee2MQTT
        mqtt.rename_device(friendly_name, new_name)

        # Mettre à jour config.json (changer ip)
        cfg = load_config(CONFIG_PATH)
        for dev in cfg.get("devices", []):
            if dev.get("ip") == f"zigbee:{friendly_name}":
                dev["ip"] = f"zigbee:{new_name}"
                # Mettre à jour aussi le name si c'était le même
                if dev.get("name") == friendly_name:
                    dev["name"] = new_name
                break
        save_config(CONFIG_PATH, cfg)

    except Exception as e:
        print(f"⚠️  Rename failed: {e}")

    return RedirectResponse("/", status_code=303)


@app.post("/zigbee/assign_room")
def zigbee_assign_room(
    friendly_name: str = Form(...),
    building: str = Form(""),
    floor: str = Form(""),
    room: str = Form("")
):
    """Assigne localisation (building/floor/room) à un device Zigbee."""
    try:
        cfg = load_config(CONFIG_PATH)

        # Trouver ou créer device
        device = None
        for dev in cfg.get("devices", []):
            if dev.get("ip") == f"zigbee:{friendly_name}":
                device = dev
                break

        if not device:
            # Créer nouveau device dans config
            device = {
                "ip": f"zigbee:{friendly_name}",
                "name": friendly_name,
                "driver": "zigbee",
                "type": "sensor",
                "building": "",
                "floor": "",
                "room": "",
                "snmp": {},
                "pjlink": {},
                "zigbee": {
                    "ieee_address": "",
                    "device_type": "unknown"
                },
                "expectations": {
                    "always_on": False,
                    "alert_after_s": 3600,  # 1h pour capteurs Zigbee
                    "schedule": {}
                }
            }
            cfg.setdefault("devices", []).append(device)

        # Mettre à jour localisation
        device["building"] = building.strip()
        device["floor"] = floor.strip()
        device["room"] = room.strip()

        save_config(CONFIG_PATH, cfg)

    except Exception as e:
        print(f"⚠️  Assign room failed: {e}")

    return RedirectResponse("/", status_code=303)


@app.get("/zigbee/device/{friendly_name}")
def zigbee_device_details(request: Request, friendly_name: str):
    """Page de détails d'un device Zigbee avec états et actions."""
    try:
        from src.mqtt_client import get_mqtt_manager
        mqtt = get_mqtt_manager()

        # Récupérer l'état actuel depuis le cache MQTT
        state = mqtt.get_device_state(friendly_name)

        # Récupérer la config du device si elle existe
        cfg = load_config(CONFIG_PATH)
        device_config = None
        for dev in cfg.get("devices", []):
            if dev.get("ip") == f"zigbee:{friendly_name}":
                device_config = dev
                break

        # Récupérer les infos depuis bridge/devices
        bridge_devices = mqtt.get_bridge_devices()
        device_info = None
        for dev in bridge_devices:
            if dev.get("friendly_name") == friendly_name:
                device_info = dev
                break

        return templates.TemplateResponse(
            "zigbee_device.html",
            {
                "request": request,
                "friendly_name": friendly_name,
                "state": state or {},
                "device_config": device_config,
                "device_info": device_info,
                "mqtt_connected": mqtt.is_connected(),
            },
        )
    except Exception as e:
        print(f"⚠️  Device details failed: {e}")
        return RedirectResponse("/", status_code=303)


@app.post("/zigbee/device/{friendly_name}/action")
def zigbee_device_action(
    request: Request,
    friendly_name: str,
    action: str = Form(...),
    value: str = Form(None)
):
    """Exécute une action sur un device Zigbee (ON/OFF, brightness, etc.)."""
    try:
        from src.mqtt_client import get_mqtt_manager
        mqtt = get_mqtt_manager()

        # Construire le payload selon l'action
        payload = {}
        if action == "toggle":
            payload = {"state": "TOGGLE"}
        elif action == "on":
            payload = {"state": "ON"}
        elif action == "off":
            payload = {"state": "OFF"}
        elif action == "brightness" and value:
            payload = {"brightness": int(value)}
        elif action == "color_temp" and value:
            payload = {"color_temp": int(value)}
        else:
            payload = {action: value}

        # Publier l'action
        mqtt.publish_action(friendly_name, payload)

    except Exception as e:
        print(f"⚠️  Device action failed: {e}")

    # Rediriger vers la page de détails du device
    return RedirectResponse(f"/zigbee/device/{friendly_name}", status_code=303)


@app.post("/zigbee/remove")
def zigbee_remove(ieee_address: str = Form(...)):
    """Supprime un device du réseau Zigbee."""
    try:
        from src.mqtt_client import get_mqtt_manager
        mqtt = get_mqtt_manager()

        # Publier request remove vers Zigbee2MQTT
        mqtt.remove_device(ieee_address, force=False)

        # Retirer de config.json (optionnel, recherche par ieee_address)
        cfg = load_config(CONFIG_PATH)
        devices = cfg.get("devices", [])
        cfg["devices"] = [
            d for d in devices
            if d.get("zigbee", {}).get("ieee_address", "") != ieee_address
        ]
        save_config(CONFIG_PATH, cfg)

    except Exception as e:
        print(f"⚠️  Remove device failed: {e}")

    return RedirectResponse("/", status_code=303)


# ---------------------------------------------------------------------
# Startup: démarrer le thread de synchronisation config
# ---------------------------------------------------------------------
@app.on_event("startup")
def startup_event():
    """
    Démarre automatiquement le thread de synchronisation ET le collector au démarrage de l'app.
    """
    global _sync_thread, _sync_stop_flag

    # Démarrer le thread de synchronisation config
    if _sync_thread is None or not _sync_thread.is_alive():
        # Lire l'intervalle de sync depuis une variable d'environnement (défaut: 5 min)
        try:
            sync_interval = int(os.getenv("CONFIG_SYNC_INTERVAL_MIN", "5"))
        except Exception:
            sync_interval = 5

        _sync_thread, _sync_stop_flag = start_sync_thread(interval_minutes=sync_interval)
        print(f"✅ Config sync thread started (interval: {sync_interval} min)")

    # Démarrer automatiquement le collector
    print("🚀 Starting collector automatically...")
    ensure_collector_running()
    if collector_running():
        print("✅ Collector started successfully")
    else:
        print("⚠️  Collector failed to start (check configuration)")

    # Initialiser connexion MQTT (non-bloquant)
    try:
        from src.mqtt_client import get_mqtt_manager
        mqtt = get_mqtt_manager()
        mqtt.init_connection()
    except Exception as e:
        print(f"⚠️  MQTT initialization failed: {e}")


@app.on_event("shutdown")
def shutdown_event():
    """
    Arrête proprement le thread de synchronisation ET le collector.
    """
    global _sync_stop_flag, _stop_flag

    # Arrêter le collector
    if _stop_flag is not None:
        print("🛑 Stopping collector...")
        _stop_flag["stop"] = True

    # Arrêter la sync config
    if _sync_stop_flag is not None:
        _sync_stop_flag["stop"] = True
        print("🛑 Config sync thread stopped")