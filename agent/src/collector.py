import os
import time
import subprocess
import requests
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, Any, List, Optional

from src.storage import load_config
from src.drivers.snmp import snmp_probe

CONFIG_PATH = os.getenv("AGENT_CONFIG", "/agent/config/config.json")

# ---------- ÉTAT PARTAGÉ (pour affichage dans l'UI) ----------
_state_lock = Lock()

_last_run_at: Optional[str] = None
_last_payload: Optional[List[Dict[str, Any]]] = None
_last_collect_error: Optional[str] = None

_last_send_at: Optional[str] = None
_last_send_ok: Optional[bool] = None
_last_send_error: Optional[str] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_last_status() -> Dict[str, Any]:
    """
    Utilisé par la web UI (webapp.py) pour afficher :
    - dernière collecte
    - dernier payload
    - dernier envoi (OK/KO)
    - erreurs éventuelles
    """
    with _state_lock:
        return {
            "last_run_at": _last_run_at,
            "last_payload": _last_payload,
            "last_collect_error": _last_collect_error,
            "last_send_at": _last_send_at,
            "last_send_ok": _last_send_ok,
            "last_send_error": _last_send_error,
        }


def _ping(ip: str, timeout_s: int = 1) -> bool:
    try:
        r = subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout_s), ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return r.returncode == 0
    except Exception:
        return False


def _base_device_fields(d: Dict[str, Any]) -> Dict[str, Any]:
    """
    Champs d'inventaire remontés dans le payload pour UX + backend.
    (Ne casse pas le backend si celui-ci ignore des champs additionnels,
    car le backend actuel stocke a minima ip/status/detail/metrics.)
    """
    return {
        "name": (d.get("name") or "").strip(),
        "building": (d.get("building") or "").strip(),
        "room": (d.get("room") or "").strip(),
        "device_type": (d.get("type") or d.get("device_type") or "unknown").strip(),
        "driver": (d.get("driver") or "ping").strip(),
    }


def collect(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    for d in cfg.get("devices", []):
        ip = (d.get("ip") or "").strip()
        driver = (d.get("driver") or "ping").strip()

        if not ip:
            continue

        base = _base_device_fields(d)

        # --- Driver PING ---
        if driver == "ping":
            ok = _ping(ip, 1)
            out.append({
                "ip": ip,
                "check": "ping",
                **base,
                "status": "online" if ok else "offline",
                "detail": "ping_ok" if ok else "ping_failed",
                "metrics": {}
            })
            continue

        # --- Driver SNMP avec fallback PING ---
        if driver == "snmp":
            probe = snmp_probe(d)

            if probe.get("snmp_ok"):
                # SNMP OK => ONLINE (même si ICMP peut être bloqué)
                out.append({
                    "ip": ip,
                    "check": "snmp",
                    **base,
                    "status": "online",
                    "detail": "snmp_ok",
                    "metrics": {
                        "snmp_ok": "true",
                        "sys_descr": probe.get("sys_descr") or "",
                        "sys_uptime": probe.get("sys_uptime") or "",
                        "snmp_port": str(probe.get("snmp_port") or ""),
                    }
                })
            else:
                # SNMP KO => fallback ping
                ping_ok = _ping(ip, 1)
                out.append({
                    "ip": ip,
                    "check": "snmp+ping_fallback",
                    **base,
                    "status": "online" if ping_ok else "offline",
                    "detail": "ping_ok_fallback" if ping_ok else "snmp_failed_and_ping_failed",
                    "metrics": {
                        "snmp_ok": "false",
                        "snmp_error": (probe.get("snmp_error") or "")[:300],
                        "sys_descr": probe.get("sys_descr") or "",
                        "snmp_port": str(probe.get("snmp_port") or ""),
                    }
                })

            continue

        # --- Driver inconnu ---
        out.append({
            "ip": ip,
            "check": "unknown",
            **base,
            "status": "unknown",
            "detail": f"driver_not_implemented:{driver}",
            "metrics": {}
        })

    return out


def send(cfg: Dict[str, Any], devices_payload: List[Dict[str, Any]]) -> None:
    api_url = (cfg.get("api_url") or "").strip()
    site_name = (cfg.get("site_name") or "").strip()
    site_token = (cfg.get("site_token") or "").strip()

    if not api_url or not site_name or not site_token:
        raise RuntimeError("Missing api_url/site_name/site_token in config")

    payload = {"site_name": site_name, "devices": devices_payload}
    headers = {"X-Site-Token": site_token}

    r = requests.post(api_url, json=payload, headers=headers, timeout=5)
    r.raise_for_status()


def run_forever(stop_flag: dict, interval_s: int = 10) -> None:
    """
    Boucle principale.
    Mise à jour de l'état partagé après chaque collecte / envoi pour affichage UI.
    """
    global _last_run_at, _last_payload, _last_collect_error
    global _last_send_at, _last_send_ok, _last_send_error

    while not stop_flag.get("stop", True):
        cfg = load_config(CONFIG_PATH)

        # 1) Collecte
        try:
            devices = collect(cfg)
            with _state_lock:
                _last_run_at = _now_iso()
                _last_payload = devices
                _last_collect_error = None
        except Exception as e:
            with _state_lock:
                _last_run_at = _now_iso()
                _last_payload = None
                _last_collect_error = str(e)
            print(f"[collector] collect failed: {e}", flush=True)
            time.sleep(interval_s)
            continue

        # 2) Envoi
        try:
            send(cfg, devices)
            with _state_lock:
                _last_send_at = _now_iso()
                _last_send_ok = True
                _last_send_error = None
            print(f"[collector] sent {len(devices)} devices", flush=True)
        except Exception as e:
            with _state_lock:
                _last_send_at = _now_iso()
                _last_send_ok = False
                _last_send_error = str(e)
            print(f"[collector] send failed: {e}", flush=True)

        time.sleep(interval_s)