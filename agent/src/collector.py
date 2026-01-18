# agent/src/collector.py
from __future__ import annotations

import inspect
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests

from src.storage import load_config
from src.drivers.registry import run_driver
from src.scheduling import (
    classify_observation,
    compute_next_collect_interval_s,
    device_policy_from_config,
)

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
    # backward compat (anciennes clés possibles côté template/UI)
    "next_send_in_s": None,       # int|None
}

# Derniers résultats de collecte par IP
_last_results: Dict[str, Dict[str, Any]] = {}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def get_last_status() -> Dict[str, Any]:
    # copie défensive
    with _lock:
        return dict(_last_status)


def get_last_results() -> Dict[str, Dict[str, Any]]:
    """Retourne les derniers résultats de collecte par IP."""
    with _lock:
        return dict(_last_results)


def _set_status(**kwargs: Any) -> None:
    with _lock:
        _last_status.update(kwargs)
        # backward compat : si next_collect_in_s est set, on set aussi next_send_in_s
        if "next_collect_in_s" in kwargs and "next_send_in_s" not in kwargs:
            _last_status["next_send_in_s"] = kwargs.get("next_collect_in_s")


# -------------------------------------------------------------------
# Compat helper: classify_observation signature
# -------------------------------------------------------------------
def _classify_with_compat(**kwargs: Any) -> str:
    """
    Appelle classify_observation() en restant compatible avec plusieurs signatures historiques.

    Nouveau (attendu):
      classify_observation(now_utc, tz_name, policy, observed_status, last_ok_utc, doubt_after_days)

    Ancien possible:
      - timezone=... ou tz=...
      - ou pas de param de timezone du tout (fallback interne)
    """
    sig = inspect.signature(classify_observation)
    params = set(sig.parameters.keys())

    call_kwargs = dict(kwargs)

    # tz_name -> timezone / tz / drop
    if "tz_name" in call_kwargs and "tz_name" not in params:
        tz = call_kwargs.pop("tz_name")
        if "timezone" in params:
            call_kwargs["timezone"] = tz
        elif "tz" in params:
            call_kwargs["tz"] = tz
        # sinon on ne passe rien (fallback dans scheduling)

    # nettoyage kwargs non supportés
    for k in list(call_kwargs.keys()):
        if k not in params:
            call_kwargs.pop(k, None)

    return classify_observation(**call_kwargs)


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

    # param "doute" côté agent (fallback)
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

        # 1) run driver (ne doit jamais faire tomber toute la boucle)
        obs: Dict[str, Any]
        try:
            obs = run_driver(driver, dev_cfg)  # normalisé par registry
            if not isinstance(obs, dict):
                obs = {"status": "unknown", "detail": "driver_return_not_dict", "metrics": {}}
        except Exception as e:
            obs = {
                "status": "unknown",
                "detail": f"{e.__class__.__name__}: {e}",
                "metrics": {"driver_error": True},
            }

        status = (obs.get("status") or "unknown").strip().lower()
        detail = (obs.get("detail") or "").strip() or None
        metrics = obs.get("metrics") if isinstance(obs.get("metrics"), dict) else {}

        # 2) Verdict (anti-faux positifs) + last_ok_utc
        last_ok_utc: Optional[datetime] = None

        # On supporte plusieurs emplacements possibles:
        # - metrics["_last_ok_utc"] (ce que tu utilises)
        # - dev_cfg["_last_ok_utc"] (si déjà stocké côté config)
        # - dev_cfg["last_ok_utc"]  (au cas où)
        prev_last_ok = (
            metrics.get("_last_ok_utc")
            or dev_cfg.get("_last_ok_utc")
            or dev_cfg.get("last_ok_utc")
        )

        if isinstance(prev_last_ok, str) and prev_last_ok.strip():
            try:
                last_ok_utc = datetime.fromisoformat(prev_last_ok.replace("Z", "+00:00"))
            except Exception:
                last_ok_utc = None

        if status == "online":
            last_ok_utc = now
            # stocke dans metrics (remonte au backend si tu veux)
            metrics["_last_ok_utc"] = now.isoformat()
            # stocke dans dev_cfg en mémoire (utile pendant le run)
            dev_cfg["_last_ok_utc"] = now.isoformat()

        policy = device_policy_from_config(dev_cfg)

        # compat signature scheduling
        verdict = _classify_with_compat(
            now_utc=now,
            tz_name=tz_name,
            policy=policy,
            observed_status=status,
            last_ok_utc=last_ok_utc,
            doubt_after_days=doubt_after_days,
        )

        if verdict == "fault":
            any_fault = True

        device_result = {
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

        out_devices.append(device_result)

        # Stocker le résultat pour l'UI
        with _lock:
            _last_results[ip] = device_result

    return {"devices": out_devices, "any_fault": any_fault}


def _send_to_backend(cfg: Dict[str, Any], devices_payload: Dict[str, Any]) -> None:
    """
    Envoi POST vers backend ingest.
    Met à jour _last_status en fonction du résultat.
    """
    # Support both "backend_url" (new) and "api_url" (legacy) for backward compatibility
    api_url = (cfg.get("backend_url") or cfg.get("api_url") or "").strip()
    site_name = (cfg.get("site_name") or "").strip()
    site_token = (cfg.get("site_token") or "").strip()

    if not api_url or not site_name or not site_token:
        _set_status(
            last_send_at=_iso(_now_utc()),
            last_send_ok=False,
            last_send_error="missing_backend_url_or_site_credentials",
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
            _set_status(next_collect_in_s=None, next_send_in_s=None)
            time.sleep(0.5)
            continue

        cfg = load_config(CONFIG_PATH)

        # run
        now = _now_utc()
        _set_status(last_run_at=_iso(now))

        collected = _collect_once(cfg)

        # interval adaptatif
        reporting = cfg.get("reporting") or {}
        try:
            ok_interval_s = int(reporting.get("ok_interval_s") or 300)
        except Exception:
            ok_interval_s = 300
        try:
            ko_interval_s = int(reporting.get("ko_interval_s") or 60)
        except Exception:
            ko_interval_s = 60

        next_interval = compute_next_collect_interval_s(
            any_fault=bool(collected.get("any_fault")),
            ok_interval_s=ok_interval_s,
            ko_interval_s=ko_interval_s,
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
            time.sleep(1)
            remaining -= 1
            _set_status(next_collect_in_s=remaining)

        # si on a interrompu via stop, on repasse dans la boucle (qui mettra next_collect_in_s=None)
        continue