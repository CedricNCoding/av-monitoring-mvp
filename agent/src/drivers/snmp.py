# agent/src/drivers/snmp.py
from __future__ import annotations

from typing import Any, Dict

from pysnmp.hlapi import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    getCmd,
)


# OIDs “classiques”
OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"
OID_SYS_UPTIME = "1.3.6.1.2.1.1.3.0"


def _as_int(v: Any, default: int) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _as_str(v: Any) -> str:
    try:
        return str(v)
    except Exception:
        return ""


def collect(device: Dict[str, Any]) -> Dict[str, Any]:
    """
    Driver SNMP - convention d'entrypoint

    Le registry appelle collect(device_cfg) et attend un dict normalisé:
      {
        "status": "online"|"offline"|"unknown",
        "detail": str,
        "metrics": dict
      }

    Config supportée:
      - ip: str (obligatoire)
      - snmp: { community, port, timeout_s, retries }
      - community/port/timeout_s/retries peuvent aussi être au niveau racine (tolérance)
    """
    ip = (device.get("ip") or "").strip()
    if not ip:
        return {"status": "unknown", "detail": "missing_ip", "metrics": {}}

    snmp_cfg = device.get("snmp") or {}
    if not isinstance(snmp_cfg, dict):
        snmp_cfg = {}

    community = (snmp_cfg.get("community") or device.get("community") or "public").strip() or "public"
    port = _as_int(snmp_cfg.get("port") or device.get("port") or 161, 161)
    timeout_s = _as_int(snmp_cfg.get("timeout_s") or device.get("timeout_s") or 1, 1)
    retries = _as_int(snmp_cfg.get("retries") or device.get("retries") or 1, 1)

    port = max(1, port)
    timeout_s = max(1, timeout_s)
    retries = max(0, retries)

    # Pysnmp: timeout en secondes, retries = nb de retries supplémentaires
    target = UdpTransportTarget((ip, port), timeout=float(timeout_s), retries=int(retries))

    # NOTE: SNMP v2c par défaut (mpModel=1)
    auth = CommunityData(community, mpModel=1)

    metrics: Dict[str, Any] = {
        "snmp_ok": False,
        "snmp_port": port,
        "community": community,
        "sys_descr": None,
        "sys_uptime": None,
        "snmp_error": None,
    }

    try:
        iterator = getCmd(
            SnmpEngine(),
            auth,
            target,
            ContextData(),
            ObjectType(ObjectIdentity(OID_SYS_DESCR)),
            ObjectType(ObjectIdentity(OID_SYS_UPTIME)),
        )

        errorIndication, errorStatus, errorIndex, varBinds = next(iterator)

        if errorIndication:
            # ex: timeout, unreachable, auth failure (parfois renvoyé ici)
            metrics["snmp_error"] = _as_str(errorIndication)
            return {"status": "offline", "detail": f"snmp_error: {metrics['snmp_error']}", "metrics": metrics}

        if errorStatus:
            # erreur SNMP sur un OID
            msg = f"{errorStatus.prettyPrint()} at {int(errorIndex)}"
            metrics["snmp_error"] = msg
            return {"status": "offline", "detail": f"snmp_error: {msg}", "metrics": metrics}

        # OK
        metrics["snmp_ok"] = True
        for oid, val in varBinds:
            oid_s = oid.prettyPrint()
            if oid_s == OID_SYS_DESCR:
                metrics["sys_descr"] = _as_str(val.prettyPrint())
            elif oid_s == OID_SYS_UPTIME:
                # souvent un TimeTicks => prettyPrint donne une valeur, mais on force int si possible
                try:
                    metrics["sys_uptime"] = int(val)
                except Exception:
                    metrics["sys_uptime"] = _as_int(val.prettyPrint(), 0)

        return {"status": "online", "detail": "snmp_ok", "metrics": metrics}

    except StopIteration:
        metrics["snmp_error"] = "snmp_no_response"
        return {"status": "offline", "detail": "snmp_no_response", "metrics": metrics}
    except Exception as e:
        metrics["snmp_error"] = f"{e.__class__.__name__}: {str(e)[:200]}"
        return {"status": "unknown", "detail": f"snmp_exception: {e.__class__.__name__}", "metrics": metrics}