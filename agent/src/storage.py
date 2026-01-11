import json
import os
from typing import Any, Dict, List


DEFAULT_CONFIG: Dict[str, Any] = {
    "site_name": "site-demo",
    "site_token": "change-me",
    "api_url": "http://backend:8000/ingest",
    "devices": [
        {
            "ip": "8.8.8.8",
            "name": "DNS Google",
            "building": "HQ",
            "room": "N/A",
            "type": "network",
            "driver": "ping",
            "snmp": {},
        },
        {
            "ip": "1.1.1.1",
            "name": "DNS Cloudflare",
            "building": "HQ",
            "room": "N/A",
            "type": "network",
            "driver": "ping",
            "snmp": {},
        },
    ],
}


def _to_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _normalize_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(cfg, dict):
        cfg = {}

    cfg.setdefault("site_name", DEFAULT_CONFIG["site_name"])
    cfg.setdefault("site_token", DEFAULT_CONFIG["site_token"])
    cfg.setdefault("api_url", DEFAULT_CONFIG["api_url"])

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

        driver = (d.get("driver") or "ping").strip()

        snmp_cfg = d.get("snmp") or {}
        if not isinstance(snmp_cfg, dict):
            snmp_cfg = {}

        normalized = {
            "ip": ip,
            "name": (d.get("name") or "").strip(),
            "building": (d.get("building") or "").strip(),
            "room": (d.get("room") or "").strip(),
            "type": (d.get("type") or d.get("device_type") or "unknown").strip(),
            "driver": driver,
            "snmp": {},
        }

        # SNMP uniquement si driver == "snmp"
        if driver == "snmp":
            normalized["snmp"] = {
                "community": (snmp_cfg.get("community") or "public").strip() or "public",
                "port": _to_int(snmp_cfg.get("port"), 161),
                "timeout_s": _to_int(snmp_cfg.get("timeout_s"), 1),
                "retries": _to_int(snmp_cfg.get("retries"), 1),
            }

        normalized_devices.append(normalized)

    cfg["devices"] = normalized_devices
    return cfg


def load_config(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        # copie profonde
        return _normalize_config(json.loads(json.dumps(DEFAULT_CONFIG)))

    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    return _normalize_config(cfg)


def save_config(path: str, cfg: Dict[str, Any]) -> None:
    cfg = _normalize_config(cfg)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)