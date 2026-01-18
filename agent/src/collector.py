# agent/src/collector.py
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests

from src.storage import load_config
from src.drivers.registry import run_driver
from src.scheduling import device_policy_from_config, classify_observation, compute_next_collect_interval_s

CONFIG_PATH = os.getenv("AGENT_CONFIG", "/agent/config/config.json")


# -------------------------------------------------------------------
# Etat exposé à l'UI (thread-safe via lock)
# -------------------------------------------------------------------
_lock = threading.Lock()

_last_status: Dict[str, Any] = {
    "last_run_at": None,          # ISO UTC
    "last_send_at": None,         # ISO UTC
    "last_send_ok": None,         # bool|None
    "last_send_error": None,      # str|None
    "next_collect_in_s": None,    # int|None
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def get_last_status() -> Dict[str, Any]:
    # copie défensive
    with _lock:
        return dict(_last_status)


def _set_status(**kwargs: Any) -> None:
    with _lock:
        _last_status.update(kwargs)


# -------------------------------------------------------------------
# Collect + Send
# -------------------------------------------------------------------
def _collect_once(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Exécute une collecte sur tous les devices.
    Retourne:
      {
        "devices": [ {ip,name,building,room,type,driver,status,detail,metrics,verdict}, ... ],
        "any_fault": bool,
      }
    """
    devices_cfg = cfg.get("devices") or []
    if not isinstance(devices_cfg, list):
        devices_cfg = []

    tz_name = (cfg.get("timezone") or "Europe/Paris").strip() or "Europe/Paris"

    # param "doute" côté agent (fallback) ; idéalement tu le rendras paramétrable backend plus tard.
    try:
        doubt_after_days = int(cfg.get("doubt_after_days") or 2)
    except Exception:
        doubt_after_days = 2
    doubt_after_days = max(0, doubt_after_days)

    now = _now_utc()

    out_devices = []
    any_fault = False

    for dev_cfg in devices_cfg:
        if not isinstance(dev_cfg, dict):
            continue

        ip = (dev_cfg.get("ip") or "").strip()
        if not ip:
            continue

        name = (dev_cfg.get("name") or "").strip() or ip
        building = (dev_cfg.get("building") or "").strip()
        room = (dev_cfg.get("room") or "").strip()
        dtype = (dev_cfg.get("type") or dev_cfg.get("device_type") or "unknown").strip() or "unknown"
        driver = (dev_cfg.get("driver") or "ping").strip().lower() or "ping"

        # 1) run driver
        obs = run_driver(driver, dev_cfg)  # normalisé par registry
        status = (obs.get("status") or "unknown").strip().lower()
        detail = (obs.get("detail") or "").strip() or None
        metrics = obs.get("metrics") if isinstance(obs.get("metrics"), dict) else {}

        # 2) verdict (anti-faux positifs)
        # last_ok_utc: on peut le stocker dans metrics (approche simple, sans DB locale)
        # - si online => on met à jour "last_ok_utc"
        # - si offline => on réutilise le précédent si présent
        last_ok_utc: Optional[datetime] = None
        prev_last_ok = metrics.get("_last_ok_utc") or dev_cfg.get("_last_ok_utc")  # tolérant
        if isinstance(prev_last_ok, str):
            try:
                last_ok_utc = datetime.fromisoformat(prev_last_ok.replace("Z", "+00:00"))
            except Exception:
                last_ok_utc = None

        if status == "online":
            last_ok_utc = now
            metrics["_last_ok_utc"] = now.isoformat()

        policy = device_policy_from_config(dev_cfg)
        verdict = classify_observation(
            now_utc=now,
            tz_name=tz_name,
            policy=policy,
            observed_status=status,
            last_ok_utc=last_ok_utc,
            doubt_after_days=doubt_after_days,
        )

        if verdict == "fault":
            any_fault = True

        out_devices.append(
            {
                "ip": ip,
                "name": name,
                "building": building,
                "room": room,
                "type": dtype,
                "driver": driver,
                "status": status,
                "detail": detail,
                "metrics": metrics,
                "verdict": verdict,
            }
        )

    return {"devices": out_devices, "any_fault": any_fault}


def _send_to_backend(cfg: Dict[str, Any], devices_payload: Dict[str, Any]) -> None:
    """
    Envoi POST vers backend ingest.
    Met à jour _last_status en fonction du résultat.
    """
    api_url = (cfg.get("api_url") or "").strip()
    site_name = (cfg.get("site_name") or "").strip()
    site_token = (cfg.get("site_token") or "").strip()

    if not api_url or not site_name or not site_token:
        _set_status(
            last_send_at=_iso(_now_utc()),
            last_send_ok=False,
            last_send_error="missing_api_url_or_site_credentials",
        )
        return

    payload = {
        "site_name": site_name,
        "devices": devices_payload.get("devices") or [],
    }

    headers = {
        "Content-Type": "application/json",
        "X-Site-Token": site_token,
    }

    try:
        r = requests.post(api_url, json=payload, headers=headers, timeout=8)
        r.raise_for_status()
        _set_status(
            last_send_at=_iso(_now_utc()),
            last_send_ok=True,
            last_send_error=None,
        )
    except Exception as e:
        _set_status(
            last_send_at=_iso(_now_utc()),
            last_send_ok=False,
            last_send_error=f"{e.__class__.__name__}: {e}",
        )


# -------------------------------------------------------------------
# Loop
# -------------------------------------------------------------------
def run_forever(stop_flag: Dict[str, bool]) -> None:
    """
    Boucle de collecte:
    - collecte (drivers)
    - calcule intervalle adaptatif (OK vs KO)
    - envoie au backend
    - dort jusqu'au prochain cycle, mais s'interrompt si stop_flag["stop"] == True
    """
    while True:
        if stop_flag.get("stop"):
            _set_status(next_collect_in_s=None)
            time.sleep(0.5)
            continue

        cfg = load_config(CONFIG_PATH)

        # run
        now = _now_utc()
        _set_status(last_run_at=_iso(now))

        collected = _collect_once(cfg)

        # interval adaptatif
        reporting = cfg.get("reporting") or {}
        ok_interval_s = reporting.get("ok_interval_s") or 300
        ko_interval_s = reporting.get("ko_interval_s") or 60

        next_interval = compute_next_collect_interval_s(
            any_fault=bool(collected.get("any_fault")),
            ok_interval_s=int(ok_interval_s),
            ko_interval_s=int(ko_interval_s),
        )

        # expose UI "prochain cycle"
        _set_status(next_collect_in_s=int(next_interval))

        # send
        _send_to_backend(cfg, collected)

        # sleep with countdown (UI-friendly) + stop support
        remaining = int(next_interval)
        while remaining > 0:
            if stop_flag.get("stop"):
                break
            # on décrémente et met à jour l'UI (approx seconde)
            time.sleep(1)
            remaining -= 1
            _set_status(next_collect_in_s=remaining)