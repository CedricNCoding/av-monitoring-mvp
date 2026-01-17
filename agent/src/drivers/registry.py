# agent/src/drivers/registry.py
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

# On importe les modules drivers. Chaque driver peut exposer
# une des fonctions suivantes : check(), run(), probe(), collect()
from src.drivers import ping as ping_driver
from src.drivers import snmp as snmp_driver
from src.drivers import pjlink as pjlink_driver


def _resolve_driver_fn(mod: Any) -> Optional[Callable[[Dict[str, Any]], Dict[str, Any]]]:
    """
    Retourne la fonction callable du driver en étant tolérant sur le nom.
    """
    for name in ("check", "run", "probe", "collect"):
        fn = getattr(mod, name, None)
        if callable(fn):
            return fn
    return None


_DRIVER_MODULES: Dict[str, Any] = {
    "ping": ping_driver,
    "snmp": snmp_driver,
    "pjlink": pjlink_driver,
}


def run_driver(driver: str, device: Dict[str, Any]) -> Dict[str, Any]:
    """
    Point d'entrée unique utilisé par collector.py.
    Retourne toujours un dict standardisé :
      { "status": "online|offline|unknown", "detail": "...|None", "metrics": {...} }
    """
    drv = (driver or device.get("driver") or "ping").strip().lower()
    mod = _DRIVER_MODULES.get(drv)
    if mod is None:
        return {"status": "unknown", "detail": f"unknown_driver:{drv}", "metrics": {}}

    fn = _resolve_driver_fn(mod)
    if fn is None:
        return {"status": "unknown", "detail": f"{drv}_no_entrypoint", "metrics": {}}

    try:
        out = fn(device)
        if not isinstance(out, dict):
            return {"status": "unknown", "detail": f"{drv}_bad_result", "metrics": {}}

        status = (out.get("status") or "unknown").strip().lower()
        detail = (out.get("detail") or "").strip() or None
        metrics = out.get("metrics") if isinstance(out.get("metrics"), dict) else {}

        return {"status": status, "detail": detail, "metrics": metrics}
    except Exception as e:
        # On évite de tuer le collector pour un seul device
        return {
            "status": "offline",
            "detail": f"{drv}_error:{e.__class__.__name__}",
            "metrics": {"error": str(e)},
        }


# Alias éventuel si du code plus ancien appelle "run"
def run(driver: str, device: Dict[str, Any]) -> Dict[str, Any]:
    return run_driver(driver, device)