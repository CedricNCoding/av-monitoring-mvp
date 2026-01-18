# agent/src/storage.py
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

# ------------------------------------------------------------
# Default config (safe baseline)
# ------------------------------------------------------------
DEFAULT_CONFIG: Dict[str, Any] = {
    "site_name": "site-demo",
    "site_token": "change-me",
    "api_url": "http://backend:8000/ingest",
    # Collect / send cadence (adaptive is handled by collector; these are intervals)
    "reporting": {
        "ok_interval_s": 300,  # 5 min
        "ko_interval_s": 60,   # 60 sec
    },
    # Defaults for local scheduling/expectations (used by collector/scheduling)
    "policy": {
        "timezone": "Europe/Paris",
        "doubt_after_days": 2,  # backend can also override later; agent uses this local default
    },
    "devices": [
        {
            "ip": "8.8.8.8",
            "name": "DNS Google",
            "building": "HQ",
            "room": "N/A",
            "type": "network",
            "driver": "ping",
            # driver configs (optional)
            "snmp": {},
            "pjlink": {},
            # expectations / scheduling (optional)
            "expectations": {
                "always_on": False,
                "alert_after_s": 300,
                "schedule": {
                    "timezone": "Europe/Paris",
                    "rules": [
                        {"days": ["mon", "tue", "wed", "thu", "fri"], "start": "07:30", "end": "19:00"}
                    ],
                },
            },
        }
    ],
}


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _as_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _as_str(v: Any) -> str:
    try:
        return str(v)
    except Exception:
        return ""


def _as_int(v: Any, default: int) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    s = _as_str(v).strip().lower()
    return s in {"1", "true", "yes", "y", "on"}


def _norm_days(value: Any) -> List[str]:
    """
    Accept:
      - "mon,tue,wed"
      - ["mon","tue"]
      - ["Monday","Tue"] (we normalize known)
    """
    out: List[str] = []
    if not value:
        return out

    raw: List[str] = []
    if isinstance(value, str):
        raw = [p.strip() for p in value.split(",") if p.strip()]
    elif isinstance(value, list):
        raw = [str(p).strip() for p in value if str(p).strip()]

    mapping = {
        "monday": "mon",
        "mon": "mon",
        "tuesday": "tue",
        "tue": "tue",
        "wednesday": "wed",
        "wed": "wed",
        "thursday": "thu",
        "thu": "thu",
        "friday": "fri",
        "fri": "fri",
        "saturday": "sat",
        "sat": "sat",
        "sunday": "sun",
        "sun": "sun",
    }

    for d in raw:
        key = d.lower()
        if key in mapping:
            v = mapping[key]
            if v not in out:
                out.append(v)

    return out


def _norm_hhmm(v: Any) -> str:
    """
    Keep "HH:MM" if possible, else empty.
    """
    s = _as_str(v).strip()
    if not s:
        return ""
    if ":" not in s:
        return ""
    hh, mm = s.split(":", 1)
    try:
        h = int(hh)
        m = int(mm)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return f"{h:02d}:{m:02d}"
    except Exception:
        return ""
    return ""


def _normalize_schedule(schedule: Any, fallback_tz: str) -> Dict[str, Any]:
    """
    Normalized schedule schema:
      {
        "timezone": "Europe/Paris",
        "rules": [
           {"days": ["mon","tue"], "start":"07:30", "end":"19:00"},
           ...
        ]
      }
    """
    sch = _as_dict(schedule)

    tz = (_as_str(sch.get("timezone")) or "").strip() or fallback_tz or "UTC"
    rules_in = _as_list(sch.get("rules"))
    rules_out: List[Dict[str, Any]] = []

    for r in rules_in:
        rr = _as_dict(r)
        days = _norm_days(rr.get("days"))
        start = _norm_hhmm(rr.get("start"))
        end = _norm_hhmm(rr.get("end"))
        if not days or not start or not end:
            continue
        rules_out.append({"days": days, "start": start, "end": end})

    return {"timezone": tz, "rules": rules_out}


def _normalize_expectations(exp: Any, fallback_tz: str) -> Dict[str, Any]:
    """
    Normalized expectations schema:
      {
        "always_on": bool,
        "alert_after_s": int,
        "schedule": { ... }   # optional
      }
    """
    e = _as_dict(exp)

    always_on = _truthy(e.get("always_on") if "always_on" in e else e.get("critical"))
    alert_after_s = _as_int(e.get("alert_after_s") if "alert_after_s" in e else e.get("alert_after"), 300)
    alert_after_s = max(15, alert_after_s)

    schedule = e.get("schedule")
    sch_norm = _normalize_schedule(schedule, fallback_tz) if schedule else {}

    out: Dict[str, Any] = {"always_on": always_on, "alert_after_s": alert_after_s}
    if sch_norm.get("rules"):
        out["schedule"] = sch_norm
    else:
        # keep empty schedule if none (do not force)
        out["schedule"] = sch_norm if sch_norm else {}

    return out


def _normalize_driver_blocks(device: Dict[str, Any]) -> None:
    """
    Make sure driver configs are present and correctly typed.
    """
    driver = (_as_str(device.get("driver")) or "ping").strip().lower()
    device["driver"] = driver

    # SNMP block
    snmp = _as_dict(device.get("snmp"))
    if driver == "snmp" or snmp:
        snmp_out = {
            "community": (_as_str(snmp.get("community")) or "public").strip() or "public",
            "port": max(1, _as_int(snmp.get("port"), 161)),
            "timeout_s": max(1, _as_int(snmp.get("timeout_s"), 1)),
            "retries": max(0, _as_int(snmp.get("retries"), 1)),
        }
        device["snmp"] = snmp_out
    else:
        device["snmp"] = {}

    # PJLINK block
    pj = _as_dict(device.get("pjlink"))
    # backward keys
    if not pj:
        # accept legacy flat keys if present
        if any(k in device for k in ("pjlink_password", "pjlink_port", "pjlink_timeout_s", "password", "port", "timeout_s")):
            pj = {
                "password": device.get("pjlink_password") or device.get("password") or "",
                "port": device.get("pjlink_port") or device.get("port") or 4352,
                "timeout_s": device.get("pjlink_timeout_s") or device.get("timeout_s") or 2,
            }

    if driver == "pjlink" or pj:
        pj_out = {
            "password": (_as_str(pj.get("password")) or "").strip(),
            "port": max(1, _as_int(pj.get("port"), 4352)),
            "timeout_s": max(1, _as_int(pj.get("timeout_s"), 2)),
        }
        device["pjlink"] = pj_out
    else:
        device["pjlink"] = {}


def _normalize_device(d: Dict[str, Any], fallback_tz: str) -> Optional[Dict[str, Any]]:
    if not isinstance(d, dict):
        return None

    ip = (_as_str(d.get("ip")) or "").strip()
    if not ip:
        return None

    # standard identity fields
    device: Dict[str, Any] = {
        "ip": ip,
        "name": (_as_str(d.get("name")) or "").strip(),
        "building": (_as_str(d.get("building")) or "").strip(),
        "room": (_as_str(d.get("room")) or "").strip(),
        "type": (_as_str(d.get("type") or d.get("device_type") or "unknown") or "unknown").strip(),
        "driver": (_as_str(d.get("driver")) or "ping").strip().lower(),
    }

    # driver blocks
    device["snmp"] = _as_dict(d.get("snmp"))
    device["pjlink"] = _as_dict(d.get("pjlink"))
    _normalize_driver_blocks(device)

    # expectations (new) OR legacy fields critical/expected_on
    exp_in = d.get("expectations")

    # Legacy mapping:
    #  - critical => always_on
    #  - expected_on => schedule.rules  (we accept list of {"start","end"} but without days => default all week)
    if not exp_in and ("critical" in d or "expected_on" in d):
        legacy_always_on = _truthy(d.get("critical"))
        legacy_expected_on = d.get("expected_on")
        sch = {}
        if isinstance(legacy_expected_on, list) and legacy_expected_on:
            rules = []
            for item in legacy_expected_on:
                if isinstance(item, dict):
                    st = _norm_hhmm(item.get("start"))
                    en = _norm_hhmm(item.get("end"))
                    if st and en:
                        rules.append({"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "start": st, "end": en})
                elif isinstance(item, str) and "-" in item:
                    a, b = item.split("-", 1)
                    st = _norm_hhmm(a)
                    en = _norm_hhmm(b)
                    if st and en:
                        rules.append({"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "start": st, "end": en})
            if rules:
                sch = {"timezone": fallback_tz or "UTC", "rules": rules}

        exp_in = {"always_on": legacy_always_on, "alert_after_s": 300, "schedule": sch}

    device["expectations"] = _normalize_expectations(exp_in, fallback_tz)

    return device


# ------------------------------------------------------------
# Normalize config (migration douce)
# ------------------------------------------------------------
def _normalize_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migration douce : complète les champs manquants dans les anciens config.json
    sans forcer l'utilisateur à supprimer/recréer sa config.
    """
    if not isinstance(cfg, dict):
        cfg = {}

    # main identity + api
    cfg.setdefault("site_name", DEFAULT_CONFIG["site_name"])
    cfg.setdefault("site_token", DEFAULT_CONFIG["site_token"])
    cfg.setdefault("api_url", DEFAULT_CONFIG["api_url"])

    # reporting
    cfg.setdefault("reporting", {})
    if not isinstance(cfg["reporting"], dict):
        cfg["reporting"] = {}

    cfg["reporting"].setdefault("ok_interval_s", DEFAULT_CONFIG["reporting"]["ok_interval_s"])
    cfg["reporting"].setdefault("ko_interval_s", DEFAULT_CONFIG["reporting"]["ko_interval_s"])

    # guardrails
    cfg["reporting"]["ok_interval_s"] = max(60, _as_int(cfg["reporting"].get("ok_interval_s"), DEFAULT_CONFIG["reporting"]["ok_interval_s"]))
    cfg["reporting"]["ko_interval_s"] = max(15, _as_int(cfg["reporting"].get("ko_interval_s"), DEFAULT_CONFIG["reporting"]["ko_interval_s"]))

    # policy (timezone + doubt)
    cfg.setdefault("policy", {})
    if not isinstance(cfg["policy"], dict):
        cfg["policy"] = {}

    cfg["policy"].setdefault("timezone", DEFAULT_CONFIG["policy"]["timezone"])
    cfg["policy"].setdefault("doubt_after_days", DEFAULT_CONFIG["policy"]["doubt_after_days"])

    tz = (_as_str(cfg["policy"].get("timezone")) or "").strip() or DEFAULT_CONFIG["policy"]["timezone"]
    cfg["policy"]["timezone"] = tz
    cfg["policy"]["doubt_after_days"] = max(0, _as_int(cfg["policy"].get("doubt_after_days"), DEFAULT_CONFIG["policy"]["doubt_after_days"]))

    # devices
    devices_in = cfg.get("devices", [])
    if not isinstance(devices_in, list):
        devices_in = []

    normalized_devices: List[Dict[str, Any]] = []
    for d in devices_in:
        nd = _normalize_device(d, tz)
        if nd is not None:
            normalized_devices.append(nd)

    cfg["devices"] = normalized_devices
    return cfg


# ------------------------------------------------------------
# Public API
# ------------------------------------------------------------
def load_config(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        # deep copy safe
        return _normalize_config(json.loads(json.dumps(DEFAULT_CONFIG)))

    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    return _normalize_config(cfg)


def save_config(path: str, cfg: Dict[str, Any]) -> None:
    cfg = _normalize_config(cfg)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # atomic-ish write (avoid corrupted json on power loss)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

    os.replace(tmp_path, path)