# agent/src/drivers/registry.py
from __future__ import annotations

from typing import Any, Dict, Callable, Optional

# Import drivers
from src.drivers.ping import check_ping
from src.drivers.snmp import check_snmp
from src.drivers.pjlink import check_pjlink


DriverFn = Callable[[Dict[str, Any]], Dict[str, Any]]


_DRIVERS: Dict[str, DriverFn] = {
    "ping": check_ping,
    "snmp": check_snmp,
    "pjlink": check_pjlink,
}


def run_driver(driver: str, device: Dict[str, Any]) -> Dict[str, Any]:
    """
    API stable attendue par collector.py

    Retourne un dict normalisé au minimum:
    {
      "status": "online|offline|unknown",
      "detail": "...",
      "metrics": {...}
    }
    """
    drv = (driver or device.get("driver") or "ping").strip().lower()
    fn = _DRIVERS.get(drv)

    if fn is None:
        return {
            "status": "unknown",
            "detail": f"unknown_driver:{drv}",
            "metrics": {},
        }

    try:
        out = fn(device)
        if not isinstance(out, dict):
            return {"status": "unknown", "detail": f"{drv}_bad_result", "metrics": {}}

        # Normalisation minimale
        status = (out.get("status") or "unknown").strip().lower()
        detail = (out.get("detail") or "").strip() or None
        metrics = out.get("metrics") if isinstance(out.get("metrics"), dict) else {}

        return {
            "status": status,
            "detail": detail,
            "metrics": metrics,
        }
    except Exception as e:
        return {
            "status": "offline",
            "detail": f"{drv}_error:{e.__class__.__name__}",
            "metrics": {"error": str(e)},
        }


# Compat: si du code appelle "run" au lieu de "run_driver"
def run(driver: str, device: Dict[str, Any]) -> Dict[str, Any]:
    return run_driver(driver, device)