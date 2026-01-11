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

# Pour debug/UX : prochaine collecte prévue
_next_collect_in_s: Optional[int] = None


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
            "next_collect_in_s": _next_collect_in_s,
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


def _has_any_ko(devices_payload: List[Dict[str, Any]]) -> bool:
    """
    Règle MVP :
      - si un device a status != 'online' => KO
    """
    for d in devices_payload:
        status = (d.get("status") or "").strip().lower()
        if status != "online":
            return True
    return False


def _read_reporting_intervals(cfg: Dict[str, Any]) -> Dict[str, int]:
    """
    Lit cfg['reporting']['ok_interval_s'] et cfg['reporting']['ko_interval_s'].
    Dans votre projet, ces champs existent déjà.

    Ici on les utilise pour la collecte adaptative :
      - OK => 300s
      - KO => 60s

    Garde-fous :
      - OK min 60
      - KO min 15
    """
    reporting = cfg.get("reporting") or {}
    if not isinstance(reporting, dict):
        reporting = {}

    ok_s = reporting.get("ok_interval_s", 300)
    ko_s = reporting.get("ko_interval_s", 60)

    try:
        ok_s = int(ok_s)
    except Exception:
        ok_s = 300

    try:
        ko_s = int(ko_s)
    except Exception:
        ko_s = 60

    ok_s = max(60, ok_s)
    ko_s = max(15, ko_s)

    return {"ok_interval_s": ok_s, "ko_interval_s": ko_s}


def collect(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Collecte l'état de chaque équipement selon son driver.
    Retourne la liste des devices avec status/detail/metrics + les champs d'inventaire.
    """
    out: List[Dict[str, Any]] = []

    for d in cfg.get("devices", []):
        if not isinstance(d, dict):
            continue

        ip = (d.get("ip") or "").strip()
        if not ip:
            continue

        driver = (d.get("driver") or "ping").strip()

        # Champs inventaire (pour backend)
        name = (d.get("name") or "").strip() or ip
        building = (d.get("building") or "").strip()
        room = (d.get("room") or "").strip()
        dev_type = (d.get("type") or d.get("device_type") or "unknown").strip()

        # --- Driver PING ---
        if driver == "ping":
            ok = _ping(ip, 1)
            out.append(
                {
                    "ip": ip,
                    "name": name,
                    "building": building,
                    "room": room,
                    "type": dev_type,
                    "driver": "ping",
                    "status": "online" if ok else "offline",
                    "detail": "ping_ok" if ok else "ping_failed",
                    "metrics": {},
                }
            )
            continue

        # --- Driver SNMP + fallback ping ---
        if driver == "snmp":
            probe = snmp_probe(d)

            if probe.get("snmp_ok"):
                out.append(
                    {
                        "ip": ip,
                        "name": name,
                        "building": building,
                        "room": room,
                        "type": dev_type,
                        "driver": "snmp",
                        "status": "online",
                        "detail": "snmp_ok",
                        "metrics": {
                            "snmp_ok": "true",
                            "sys_descr": probe.get("sys_descr") or "",
                            "sys_uptime": probe.get("sys_uptime") or "",
                            "snmp_port": str(probe.get("snmp_port") or ""),
                        },
                    }
                )
            else:
                ping_ok = _ping(ip, 1)
                out.append(
                    {
                        "ip": ip,
                        "name": name,
                        "building": building,
                        "room": room,
                        "type": dev_type,
                        "driver": "snmp",
                        "status": "online" if ping_ok else "offline",
                        "detail": "ping_ok_fallback" if ping_ok else "snmp_failed_and_ping_failed",
                        "metrics": {
                            "snmp_ok": "false",
                            "snmp_error": (probe.get("snmp_error") or "")[:300],
                            "sys_descr": probe.get("sys_descr") or "",
                            "snmp_port": str(probe.get("snmp_port") or ""),
                        },
                    }
                )
            continue

        # --- Driver inconnu ---
        out.append(
            {
                "ip": ip,
                "name": name,
                "building": building,
                "room": room,
                "type": dev_type,
                "driver": driver,
                "status": "unknown",
                "detail": f"driver_not_implemented:{driver}",
                "metrics": {},
            }
        )

    return out


def send(cfg: Dict[str, Any], devices_payload: List[Dict[str, Any]]) -> None:
    """
    Envoi au backend (vous dites que c'est déjà OK, on ne change pas le protocole).
    """
    api_url = (cfg.get("api_url") or "").strip()
    site_name = (cfg.get("site_name") or "").strip()
    site_token = (cfg.get("site_token") or "").strip()

    if not api_url or not site_name or not site_token:
        raise RuntimeError("Missing api_url/site_name/site_token in config")

    payload = {"site_name": site_name, "devices": devices_payload}
    headers = {"X-Site-Token": site_token}

    r = requests.post(api_url, json=payload, headers=headers, timeout=5)
    r.raise_for_status()


def _sleep_with_stop(stop_flag: dict, seconds: int) -> None:
    """
    Sleep interrompable : permet d'arrêter rapidement le collector via stop_flag.
    """
    remaining = max(0, int(seconds))
    while remaining > 0 and not stop_flag.get("stop", True):
        step = 1 if remaining > 1 else remaining
        time.sleep(step)
        remaining -= step


def run_forever(stop_flag: dict) -> None:
    """
    Boucle principale.

    ✅ Collecte adaptative :
      - si tout ONLINE => collecte toutes les 5 minutes (300s)
      - si au moins un KO => collecte toutes les 60 secondes

    Remarque :
      - l'envoi est appelé après chaque collecte (comme avant). Vous avez indiqué
        que la partie envoi est OK : on conserve ce comportement.
    """
    global _last_run_at, _last_payload, _last_collect_error
    global _last_send_at, _last_send_ok, _last_send_error
    global _next_collect_in_s

    while not stop_flag.get("stop", True):
        cfg = load_config(CONFIG_PATH)

        intervals = _read_reporting_intervals(cfg)
        ok_interval = intervals["ok_interval_s"]   # par défaut 300 si vous l'avez mis dans storage.py
        ko_interval = intervals["ko_interval_s"]   # par défaut 60

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

            # En cas d'erreur de collecte, on repasse en cadence "rapide"
            with _state_lock:
                _next_collect_in_s = ko_interval
            _sleep_with_stop(stop_flag, ko_interval)
            continue

        # 2) Envoi (inchangé)
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

        # 3) Choix cadence collecte
        any_ko = _has_any_ko(devices)
        next_collect = ko_interval if any_ko else ok_interval

        with _state_lock:
            _next_collect_in_s = next_collect

        print(
            f"[collector] next collect in {next_collect}s (mode={'KO' if any_ko else 'OK'})",
            flush=True,
        )

        _sleep_with_stop(stop_flag, next_collect)