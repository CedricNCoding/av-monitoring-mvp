import os
import time
import requests
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, Any, List, Optional

from src.storage import load_config
from src.drivers.registry import probe_device

CONFIG_PATH = os.getenv("AGENT_CONFIG", "/agent/config/config.json")

_state_lock = Lock()

_last_run_at: Optional[str] = None
_last_payload: Optional[List[Dict[str, Any]]] = None
_last_collect_error: Optional[str] = None

_last_send_at: Optional[str] = None
_last_send_ok: Optional[bool] = None
_last_send_error: Optional[str] = None

_next_collect_in_s: Optional[int] = None


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


def _has_any_ko(devices_payload: List[Dict[str, Any]]) -> bool:
    for d in devices_payload:
        status = (d.get("status") or "").strip().lower()
        if status != "online":
            return True
    return False


def _read_intervals(cfg: Dict[str, Any]) -> Dict[str, int]:
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
    return {"ok": ok_s, "ko": ko_s}


def collect(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    for d in cfg.get("devices", []):
        if not isinstance(d, dict):
            continue

        ip = (d.get("ip") or "").strip()
        if not ip:
            continue

        # Inventaire
        payload = {
            "ip": ip,
            "name": (d.get("name") or "").strip() or ip,
            "building": (d.get("building") or "").strip(),
            "room": (d.get("room") or "").strip(),
            "type": (d.get("type") or d.get("device_type") or "unknown").strip(),
            "driver": (d.get("driver") or "ping").strip().lower(),
            "driver_cfg": d.get("driver_cfg") or {},
        }

        # Probe driver
        result = probe_device(payload)

        out.append(
            {
                "ip": ip,
                "name": payload["name"],
                "building": payload["building"],
                "room": payload["room"],
                "type": payload["type"],
                "driver": payload["driver"],
                "status": result.get("status") or "unknown",
                "detail": result.get("detail") or "",
                "metrics": result.get("metrics") or {},
            }
        )

    return out


def send(cfg: Dict[str, Any], devices_payload: List[Dict[str, Any]]) -> None:
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
    remaining = max(0, int(seconds))
    while remaining > 0 and not stop_flag.get("stop", True):
        step = 1 if remaining > 1 else remaining
        time.sleep(step)
        remaining -= step


def run_forever(stop_flag: dict) -> None:
    global _last_run_at, _last_payload, _last_collect_error
    global _last_send_at, _last_send_ok, _last_send_error
    global _next_collect_in_s

    while not stop_flag.get("stop", True):
        cfg = load_config(CONFIG_PATH)
        intervals = _read_intervals(cfg)

        # 1) collecte
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
                _next_collect_in_s = intervals["ko"]

            print(f"[collector] collect failed: {e}", flush=True)
            _sleep_with_stop(stop_flag, intervals["ko"])
            continue

        # 2) envoi
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

        # 3) cadence adaptative
        any_ko = _has_any_ko(devices)
        next_collect = intervals["ko"] if any_ko else intervals["ok"]

        with _state_lock:
            _next_collect_in_s = next_collect

        print(f"[collector] next collect in {next_collect}s (mode={'KO' if any_ko else 'OK'})", flush=True)
        _sleep_with_stop(stop_flag, next_collect)