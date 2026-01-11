import os
import time
import subprocess
import requests
from typing import Dict, Any, List

from src.storage import load_config

CONFIG_PATH = os.getenv("AGENT_CONFIG", "/agent/config/config.json")

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

def collect(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for d in cfg.get("devices", []):
        ip = d.get("ip")
        driver = d.get("driver", "ping")

        if not ip:
            continue

        if driver == "ping":
            ok = _ping(ip, 1)
            out.append({
                "ip": ip,
                "status": "online" if ok else "offline",
                "detail": "ping_ok" if ok else "ping_failed",
                "metrics": {}
            })
        else:
            out.append({
                "ip": ip,
                "status": "unknown",
                "detail": f"driver_not_implemented:{driver}",
                "metrics": {}
            })

    return out

def send(cfg: Dict[str, Any], devices_payload: List[Dict[str, Any]]) -> None:
    api_url = cfg.get("api_url")
    site_name = cfg.get("site_name")
    site_token = cfg.get("site_token")

    if not api_url or not site_name or not site_token:
        raise RuntimeError("Missing api_url/site_name/site_token in config")

    payload = {"site_name": site_name, "devices": devices_payload}
    headers = {"X-Site-Token": site_token}

    r = requests.post(api_url, json=payload, headers=headers, timeout=5)
    r.raise_for_status()

def run_forever(stop_flag: dict, interval_s: int = 10) -> None:
    while not stop_flag.get("stop", True):
        cfg = load_config(CONFIG_PATH)
        try:
            devices = collect(cfg)
            send(cfg, devices)
            print(f"[collector] sent {len(devices)} devices", flush=True)
        except Exception as e:
            print(f"[collector] send failed: {e}", flush=True)
        time.sleep(interval_s)