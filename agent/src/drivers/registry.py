# agent/src/drivers/registry.py
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from src.drivers.ping import probe as ping_probe
from src.drivers.snmp import probe as snmp_probe
from src.drivers.pjlink import probe as pjlink_probe

# Type signature commune à nos drivers:
# - device: dict (config device)
# - retourne un dict d'observation (au minimum: status, detail, metrics...)
DriverFn = Callable[[Dict[str, Any]], Dict[str, Any]]


def get_registry() -> Dict[str, DriverFn]:
    """
    Registre officiel des drivers.

    IMPORTANT:
    - Les clés doivent être stables (ping/snmp/pjlink)
    - Les fonctions doivent exposer une entrypoint homogène : probe(device) -> result dict
    """
    return {
        "ping": ping_probe,
        "snmp": snmp_probe,
        "pjlink": pjlink_probe,
    }


def run_driver(driver: str, device: Dict[str, Any]) -> Dict[str, Any]:
    """
    Entry-point stable attendu par collector.py.

    - driver: nom du driver (string)
    - device: bloc device de la config
    Retour:
      dict avec a minima:
        - status: "online"|"offline"|"unknown"
        - detail: str optionnel
        - metrics: dict optionnel
    """
    dname = (driver or "").strip().lower() or (device.get("driver") or "ping").strip().lower()

    fn: Optional[DriverFn] = get_registry().get(dname)
    if fn is None:
        return {
            "status": "unknown",
            "detail": f"unknown_driver:{dname}",
            "metrics": {},
        }

    try:
        out = fn(device)
    except Exception as e:
        return {
            "status": "unknown",
            "detail": f"driver_error:{dname}:{e.__class__.__name__}:{e}",
            "metrics": {},
        }

    # Normalisation minimale (évite les KeyError plus loin)
    if not isinstance(out, dict):
        return {"status": "unknown", "detail": f"driver_invalid_return:{dname}", "metrics": {}}

    out.setdefault("status", "unknown")
    out.setdefault("detail", None)
    out.setdefault("metrics", {} if isinstance(out.get("metrics"), dict) else {})

    return out