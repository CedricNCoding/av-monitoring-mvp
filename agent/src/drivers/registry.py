# agent/src/drivers/registry.py
from typing import Any, Dict

from src.drivers.ping import ping
from src.drivers.pjlink import probe as pjlink_probe
from src.drivers.snmp import snmp_probe


def probe_device(device: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retourne toujours:
      { status, detail, metrics }
    """
    driver = (device.get("driver") or "ping").strip().lower()
    ip = (device.get("ip") or "").strip()

    # Driver PING
    if driver == "ping":
        ok = ping(ip, 1)
        return {
            "status": "online" if ok else "offline",
            "detail": "ping_ok" if ok else "ping_failed",
            "metrics": {},
        }

    # Driver SNMP
    if driver == "snmp":
        probe = snmp_probe(device)
        if probe.get("snmp_ok"):
            return {
                "status": "online",
                "detail": "snmp_ok",
                "metrics": {
                    "snmp_ok": "true",
                    "sys_descr": probe.get("sys_descr") or "",
                    "sys_uptime": probe.get("sys_uptime") or "",
                    "snmp_port": str(probe.get("snmp_port") or ""),
                },
            }

        # fallback ping
        ping_ok = ping(ip, 1)
        return {
            "status": "online" if ping_ok else "offline",
            "detail": "ping_ok_fallback" if ping_ok else "snmp_failed_and_ping_failed",
            "metrics": {
                "snmp_ok": "false",
                "snmp_error": (probe.get("snmp_error") or "")[:300],
                "sys_descr": probe.get("sys_descr") or "",
                "snmp_port": str(probe.get("snmp_port") or ""),
            },
        }

    # Driver PJLINK
    if driver == "pjlink":
        return pjlink_probe(device)

    return {
        "status": "unknown",
        "detail": f"driver_not_implemented:{driver}",
        "metrics": {},
    }