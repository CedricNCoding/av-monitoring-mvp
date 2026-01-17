# agent/src/storage.py
import json
import os
from typing import Any, Dict, List

DEFAULT_CONFIG: Dict[str, Any] = {
    "site_name": "site-demo",
    "site_token": "change-me",
    "api_url": "http://backend:8000/ingest",
    "reporting": {
        # si tout est OK => interval plus long
        "ok_interval_s": 300,   # 5 minutes par défaut
        # si au moins un équipement est KO => interval plus court
        "ko_interval_s": 60,    # 60 secondes par défaut
    },
    "detection": {
        # délai minimal avant de déclarer un KO “réel” (anti faux positifs)
        "default_alert_after_s": 300  # 5 minutes
    },
    "devices": [
        {
            "ip": "8.8.8.8",
            "name": "DNS Google",
            "building": "HQ",
            "room": "N/A",
            "type": "network",
            "driver": "ping",
            "expectations": {
                "always_on": False,
                "alert_after_s": 120,
                "schedule": {
                    "timezone": "Europe/Paris",
                    "rules": [
                        {"days": ["mon", "tue", "wed", "thu", "fri"], "start": "00:00", "end": "23:59"}
                    ],
                },
            },
        },
    ],
}


def _normalize_schedule(s: Any) -> Dict[str, Any]:
    if not isinstance(s, dict):
        return {}
    tz = (s.get("timezone") or "Europe/Paris").strip() or "Europe/Paris"
    rules = s.get("rules") or []
    if not isinstance(rules, list):
        rules = []

    norm_rules = []
    for r in rules:
        if not isinstance(r, dict):
            continue
        days = r.get("days") or []
        if not isinstance(days, list):
            days = []
        days_norm = []
        for d in days:
            ds = str(d).strip().lower()
            if ds in {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}:
                days_norm.append(ds)

        start = str(r.get("start") or "").strip()
        end = str(r.get("end") or "").strip()
        if not start or not end or not days_norm:
            continue

        norm_rules.append({"days": days_norm, "start": start, "end": end})

    return {"timezone": tz, "rules": norm_rules}


def _normalize_expectations(d: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    exp = d.get("expectations") or {}
    if not isinstance(exp, dict):
        exp = {}

    always_on = bool(exp.get("always_on", False))

    # alert_after_s : délai avant KO “réel”
    default_alert = int((cfg.get("detection") or {}).get("default_alert_after_s") or 300)
    try:
        alert_after_s = int(exp.get("alert_after_s") or default_alert)
    except Exception:
        alert_after_s = default_alert
    alert_after_s = max(15, alert_after_s)

    schedule = _normalize_schedule(exp.get("schedule"))
    # Schedule optionnel : si vide => “attendu ON” tout le temps (sauf always_on gère la sévérité)
    return {
        "always_on": always_on,
        "alert_after_s": alert_after_s,
        "schedule": schedule,
    }


def _normalize_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(cfg, dict):
        cfg = {}

    cfg.setdefault("site_name", DEFAULT_CONFIG["site_name"])
    cfg.setdefault("site_token", DEFAULT_CONFIG["site_token"])
    cfg.setdefault("api_url", DEFAULT_CONFIG["api_url"])

    # reporting
    cfg.setdefault("reporting", {})
    if not isinstance(cfg["reporting"], dict):
        cfg["reporting"] = {}

    cfg["reporting"].setdefault("ok_interval_s", DEFAULT_CONFIG["reporting"]["ok_interval_s"])
    cfg["reporting"].setdefault("ko_interval_s", DEFAULT_CONFIG["reporting"]["ko_interval_s"])

    try:
        cfg["reporting"]["ok_interval_s"] = max(60, int(cfg["reporting"]["ok_interval_s"]))
    except Exception:
        cfg["reporting"]["ok_interval_s"] = DEFAULT_CONFIG["reporting"]["ok_interval_s"]

    try:
        cfg["reporting"]["ko_interval_s"] = max(15, int(cfg["reporting"]["ko_interval_s"]))
    except Exception:
        cfg["reporting"]["ko_interval_s"] = DEFAULT_CONFIG["reporting"]["ko_interval_s"]

    # detection
    cfg.setdefault("detection", {})
    if not isinstance(cfg["detection"], dict):
        cfg["detection"] = {}
    cfg["detection"].setdefault("default_alert_after_s", DEFAULT_CONFIG["detection"]["default_alert_after_s"])
    try:
        cfg["detection"]["default_alert_after_s"] = max(15, int(cfg["detection"]["default_alert_after_s"]))
    except Exception:
        cfg["detection"]["default_alert_after_s"] = DEFAULT_CONFIG["detection"]["default_alert_after_s"]

    # devices
    devices = cfg.get("devices", [])
    if not isinstance(devices, list):
        devices = []

    normalized_devices: List[Dict[str, Any]] = []
    for d in devices:
        if not isinstance(d, dict):
            continue

        ip = (d.get("ip") or "").strip()
        if not ip:
            continue

        snmp_cfg = d.get("snmp") or {}
        if not isinstance(snmp_cfg, dict):
            snmp_cfg = {}

        pj_cfg = d.get("pjlink") or {}
        if not isinstance(pj_cfg, dict):
            pj_cfg = {}

        driver = (d.get("driver") or "ping").strip().lower()
        if driver not in {"ping", "snmp", "pjlink"}:
            driver = "ping"

        norm_d = {
            "ip": ip,
            "name": (d.get("name") or "").strip(),
            "building": (d.get("building") or "").strip(),
            "room": (d.get("room") or "").strip(),
            "type": (d.get("type") or d.get("device_type") or "unknown").strip(),
            "driver": driver,
            "snmp": {
                "community": (snmp_cfg.get("community") or "public").strip(),
                "port": int(snmp_cfg.get("port") or 161),
                "timeout_s": int(snmp_cfg.get("timeout_s") or 1),
                "retries": int(snmp_cfg.get("retries") or 1),
            } if (driver == "snmp" or d.get("snmp")) else {},
            "pjlink": {
                "password": (pj_cfg.get("password") or "").strip(),
                "port": int(pj_cfg.get("port") or 4352),
                "timeout_s": int(pj_cfg.get("timeout_s") or 2),
            } if (driver == "pjlink" or d.get("pjlink")) else {},
        }

        norm_d["expectations"] = _normalize_expectations(d, cfg)
        normalized_devices.append(norm_d)

    cfg["devices"] = normalized_devices
    return cfg


def load_config(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return _normalize_config(json.loads(json.dumps(DEFAULT_CONFIG)))

    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    return _normalize_config(cfg)


def save_config(path: str, cfg: Dict[str, Any]) -> None:
    cfg = _normalize_config(cfg)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)