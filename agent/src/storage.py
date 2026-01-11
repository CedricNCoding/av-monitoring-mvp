# agent/src/storage.py
import json
import os
from typing import Any, Dict, List

DEFAULT_CONFIG: Dict[str, Any] = {
    "site_name": "site-demo",
    "site_token": "change-me",
    "api_url": "http://backend:8000/ingest",
    # Collecte / reporting (cadence)
    # - ok_interval_s : si tout est OK, on collecte moins souvent
    # - ko_interval_s : si au moins un équipement est KO, on collecte plus souvent
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
        },
        {
            "ip": "1.1.1.1",
            "name": "DNS Cloudflare",
            "building": "HQ",
            "room": "N/A",
            "type": "network",
            "driver": "ping",
        },
    ],
}


def _normalize_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migration douce : complète les champs manquants dans les anciens config.json
    sans forcer l'utilisateur à supprimer/recréer sa config.
    """
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

    # garde-fous
    # - ok_interval : au minimum 60s (évite de spammer inutilement)
    # - ko_interval : au minimum 15s (mais vous visez 60s)
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

        snmp_cfg = d.get("snmp") or {}
        if not isinstance(snmp_cfg, dict):
            snmp_cfg = {}

        driver = (d.get("driver") or "ping").strip()

        normalized_devices.append(
            {
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
                }
                if (driver == "snmp" or d.get("snmp"))
                else {},
            }
        )

    cfg["devices"] = normalized_devices
    return cfg


def load_config(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        # deep copy minimal (évite mutations du DEFAULT_CONFIG)
        return _normalize_config(json.loads(json.dumps(DEFAULT_CONFIG)))

    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    return _normalize_config(cfg)


def save_config(path: str, cfg: Dict[str, Any]) -> None:
    cfg = _normalize_config(cfg)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)