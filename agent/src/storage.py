# agent/src/storage.py
import json
import os
from typing import Any, Dict, List

DEFAULT_CONFIG: Dict[str, Any] = {
    "site_name": "site-demo",
    "site_token": "change-me",
    "api_url": "http://backend:8000/ingest",
    "reporting": {
        "ok_interval_s": 300,   # 5 minutes
        "ko_interval_s": 60,    # 1 minute
    },
    "devices": [
        {
            "ip": "8.8.8.8",
            "name": "DNS Google",
            "building": "HQ",
            "room": "N/A",
            "type": "network",
            "driver": "ping",
            "driver_cfg": {},
        },
        {
            "ip": "1.1.1.1",
            "name": "DNS Cloudflare",
            "building": "HQ",
            "room": "N/A",
            "type": "network",
            "driver": "ping",
            "driver_cfg": {},
        },
    ],
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

        driver = (d.get("driver") or "ping").strip().lower()

        # driver_cfg (générique)
        driver_cfg = d.get("driver_cfg") or {}
        if not isinstance(driver_cfg, dict):
            driver_cfg = {}

        # SNMP compat ancienne structure
        snmp_cfg = d.get("snmp") or {}
        if not isinstance(snmp_cfg, dict):
            snmp_cfg = {}

        # Normalisation SNMP dans driver_cfg si besoin
        if driver == "snmp" or d.get("snmp"):
            driver_cfg.setdefault("community", (snmp_cfg.get("community") or driver_cfg.get("community") or "public"))
            driver_cfg.setdefault("port", int(snmp_cfg.get("port") or driver_cfg.get("port") or 161))
            driver_cfg.setdefault("timeout_s", int(snmp_cfg.get("timeout_s") or driver_cfg.get("timeout_s") or 1))
            driver_cfg.setdefault("retries", int(snmp_cfg.get("retries") or driver_cfg.get("retries") or 1))

        # Normalisation PJLink
        if driver == "pjlink":
            driver_cfg.setdefault("port", int(driver_cfg.get("port") or 4352))
            driver_cfg.setdefault("timeout_s", int(driver_cfg.get("timeout_s") or 2))
            # password peut être vide (auth PJLINK 0) => OK
            driver_cfg.setdefault("password", (driver_cfg.get("password") or "").strip())

        normalized_devices.append(
            {
                "ip": ip,
                "name": (d.get("name") or "").strip(),
                "building": (d.get("building") or "").strip(),
                "room": (d.get("room") or "").strip(),
                "type": (d.get("type") or d.get("device_type") or "unknown").strip(),
                "driver": driver,
                "driver_cfg": driver_cfg,
            }
        )

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