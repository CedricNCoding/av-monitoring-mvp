# agent/src/collector.py
import os
import time
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

import requests

from src.storage import load_config
from src.drivers.registry import run_driver

CONFIG_PATH = os.getenv("AGENT_CONFIG", "/agent/config/config.json")

_state_lock = Lock()

_last_run_at: Optional[str] = None
_last_payload: Optional[List[Dict[str, Any]]] = None
_last_collect_error: Optional[str] = None

_last_send_at: Optional[str] = None
_last_send_ok: Optional[bool] = None
_last_send_error: Optional[str] = None

_next_collect_in_s: Optional[int] = None

# suivi anti faux positifs : moment où on a vu l'offline “attendu ON”
_offline_since: Dict[str, float] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_last_status() -> Dict[str, Any]:
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


def _parse_hhmm(s: str) -> Tuple[int, int]:
    parts = s.strip().split(":")
    if len(parts) != 2:
        raise ValueError("Invalid HH:MM")
    h = int(parts[0])
    m = int(parts[1])
    if h < 0 or h > 23 or m < 0 or m > 59:
        raise ValueError("Invalid HH:MM range")
    return h, m


def _weekday_short(dt_local: datetime) -> str:
    # python: Monday=0
    mapping = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    return mapping[dt_local.weekday()]


def _is_in_schedule(device: Dict[str, Any], utc_now: datetime) -> bool:
    exp = device.get("expectations") or {}
    if not isinstance(exp, dict):
        return True

    schedule = exp.get("schedule") or {}
    if not isinstance(schedule, dict):
        return True

    rules = schedule.get("rules") or []
    if not isinstance(rules, list) or len(rules) == 0:
        return True  # pas de schedule => attendu ON tout le temps

    tz_name = (schedule.get("timezone") or "Europe/Paris").strip() or "Europe/Paris"
    try:
        from zoneinfo import ZoneInfo
        local_now = utc_now.astimezone(ZoneInfo(tz_name))
    except Exception:
        local_now = utc_now  # fallback UTC

    wd = _weekday_short(local_now)

    for r in rules:
        if not isinstance(r, dict):
            continue
        days = r.get("days") or []
        if not isinstance(days, list):
            continue
        if wd not in [str(x).strip().lower() for x in days]:
            continue

        start = (r.get("start") or "").strip()
        end = (r.get("end") or "").strip()
        if not start or not end:
            continue

        try:
            sh, sm = _parse_hhmm(start)
            eh, em = _parse_hhmm(end)
        except Exception:
            continue

        start_min = sh * 60 + sm
        end_min = eh * 60 + em
        now_min = local_now.hour * 60 + local_now.minute

        if start_min <= end_min:
            # plage “normale” dans la journée
            if start_min <= now_min <= end_min:
                return True
        else:
            # plage qui chevauche minuit (ex: 22:00 -> 06:00)
            if now_min >= start_min or now_min <= end_min:
                return True

    return False


def _alert_after_s(device: Dict[str, Any], cfg: Dict[str, Any]) -> int:
    exp = device.get("expectations") or {}
    if not isinstance(exp, dict):
        exp = {}
    v = exp.get("alert_after_s")
    if v is None:
        v = ((cfg.get("detection") or {}).get("default_alert_after_s") or 300)
    try:
        n = int(v)
    except Exception:
        n = 300
    return max(15, n)


def _always_on(device: Dict[str, Any]) -> bool:
    exp = device.get("expectations") or {}
    if not isinstance(exp, dict):
        return False
    return bool(exp.get("always_on", False))


def collect(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    utc_now = datetime.now(timezone.utc)

    for d in cfg.get("devices", []):
        if not isinstance(d, dict):
            continue

        ip = (d.get("ip") or "").strip()
        if not ip:
            continue

        driver = (d.get("driver") or "ping").strip().lower()
        name = (d.get("name") or "").strip() or ip
        building = (d.get("building") or "").strip()
        room = (d.get("room") or "").strip()
        device_type = (d.get("type") or d.get("device_type") or "unknown").strip() or "unknown"

        in_schedule = _is_in_schedule(d, utc_now)
        always_on = _always_on(d)
        threshold_s = _alert_after_s(d, cfg)

        # exécution driver (ping/snmp/pjlink)
        probe = run_driver(driver, d)

        ok = bool(probe.get("ok", False))
        detail = (probe.get("detail") or "").strip()
        metrics = probe.get("metrics") or {}
        if not isinstance(metrics, dict):
            metrics = {}

        status = "unknown"
        final_detail = detail or None

        if ok:
            status = "online"
            _offline_since.pop(ip, None)
        else:
            # 1) hors schedule => OFF attendu (sauf always_on)
            if (not always_on) and (not in_schedule):
                status = "offline_expected"
                final_detail = final_detail or "scheduled_off"
                _offline_since.pop(ip, None)
            else:
                # 2) dans schedule OU always_on => on démarre le compteur anti-faux positifs
                now_ts = time.time()
                if ip not in _offline_since:
                    _offline_since[ip] = now_ts

                age = now_ts - _offline_since[ip]

                if always_on and age >= 15:
                    # always_on: plus strict
                    status = "offline_suspect"
                    final_detail = final_detail or "always_on_violation"
                else:
                    if age >= threshold_s:
                        status = "offline_suspect"
                        final_detail = final_detail or "offline_threshold_reached"
                    else:
                        status = "offline_transient"
                        final_detail = final_detail or f"grace_period:{int(threshold_s - age)}s"

                metrics["offline_age_s"] = str(int(age))
                metrics["alert_after_s"] = str(int(threshold_s))
                metrics["in_schedule"] = "true" if in_schedule else "false"
                metrics["always_on"] = "true" if always_on else "false"

        out.append(
            {
                "ip": ip,
                "name": name,
                "building": building,
                "room": room,
                "type": device_type,
                "driver": driver,
                "status": status,
                "detail": final_detail,
                "metrics": metrics,
            }
        )

    return out


def _pick_interval(cfg: Dict[str, Any], devices_payload: List[Dict[str, Any]]) -> Dict[str, int]:
    rep = cfg.get("reporting") or {}
    if not isinstance(rep, dict):
        rep = {}
    ok_i = int(rep.get("ok_interval_s") or 300)
    ko_i = int(rep.get("ko_interval_s") or 60)
    ok_i = max(60, ok_i)
    ko_i = max(15, ko_i)

    # “KO” si au moins un suspect/transient/unknown (mais pas offline_expected)
    any_problem = False
    for d in devices_payload:
        st = (d.get("status") or "").strip().lower()
        if st in {"offline_suspect", "offline_transient", "unknown"}:
            any_problem = True
            break

    return {"ok": ok_i, "ko": ko_i, "pick": (ko_i if any_problem else ok_i)}


def send(cfg: Dict[str, Any], devices_payload: List[Dict[str, Any]]) -> None:
    api_url = (cfg.get("api_url") or "").strip()
    site_name = (cfg.get("site_name") or "").strip()
    site_token = (cfg.get("site_token") or "").strip()

    if not api_url or not site_name or not site_token:
        raise RuntimeError("Missing api_url/site_name/site_token in config")

    payload = {"site_name": site_name, "devices": devices_payload}
    headers = {"X-Site-Token": site_token}

    r = requests.post(api_url, json=payload, headers=headers, timeout=8)
    r.raise_for_status()


def run_forever(stop_flag: dict, interval_s: int = 10) -> None:
    """
    interval_s devient “tick” (petit sommeil) mais l'interval réel est piloté par ok/ko.
    """
    global _last_run_at, _last_payload, _last_collect_error
    global _last_send_at, _last_send_ok, _last_send_error
    global _next_collect_in_s

    next_send_ts = 0.0

    while not stop_flag.get("stop", True):
        cfg = load_config(CONFIG_PATH)

        # si pas encore le moment d'envoyer, on met à jour le “compte à rebours” et on dort un peu
        now_ts = time.time()
        if next_send_ts > now_ts:
            with _state_lock:
                _next_collect_in_s = int(max(0, next_send_ts - now_ts))
            time.sleep(min(interval_s, max(1, next_send_ts - now_ts)))
            continue

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
            time.sleep(interval_s)
            continue

        # 2) Envoi
        try:
            send(cfg, devices)
            with _state_lock:
                _last_send_at = _now_iso()
                _last_send_ok = True
                _last_send_error = None
        except Exception as e:
            with _state_lock:
                _last_send_at = _now_iso()
                _last_send_ok = False
                _last_send_error = str(e)

        # 3) Prochain envoi (ok/ko)
        intervals = _pick_interval(cfg, devices)
        next_collect = int(intervals["pick"])
        next_send_ts = time.time() + next_collect

        with _state_lock:
            _next_collect_in_s = next_collect

        # petit sleep pour éviter boucle chaude
        time.sleep(1)