# agent/src/drivers/snmp.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(x: Any, default: int) -> int:
    try:
        return int(str(x).strip())
    except Exception:
        return default


def _as_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _snmp_get_sys(ip: str, community: str, port: int, timeout_s: int, retries: int) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """
    Fait un GET minimal sur:
      - sysDescr.0   (1.3.6.1.2.1.1.1.0)
      - sysUpTime.0  (1.3.6.1.2.1.1.3.0)

    Retour:
      (ok, metrics, error)
    """
    # Import lazy pour éviter crash au démarrage si la dépendance n'est pas présente
    try:
        from pysnmp.hlapi import (  # type: ignore
            SnmpEngine,
            CommunityData,
            UdpTransportTarget,
            ContextData,
            ObjectType,
            ObjectIdentity,
            getCmd,
        )
    except Exception as e:
        return False, {}, f"pysnmp not available: {e}"

    sys_descr_oid = "1.3.6.1.2.1.1.1.0"
    sys_uptime_oid = "1.3.6.1.2.1.1.3.0"

    try:
        it = getCmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),  # SNMPv2c
            UdpTransportTarget((ip, port), timeout=max(1, timeout_s), retries=max(0, retries)),
            ContextData(),
            ObjectType(ObjectIdentity(sys_descr_oid)),
            ObjectType(ObjectIdentity(sys_uptime_oid)),
        )

        errorIndication, errorStatus, errorIndex, varBinds = next(it)

        if errorIndication:
            return False, {}, str(errorIndication)

        if errorStatus:
            return False, {}, f"{errorStatus.prettyPrint()} at {errorIndex}"

        metrics: Dict[str, Any] = {"snmp_ok": True, "snmp_port": port}
        for name, val in varBinds:
            oid = name.prettyPrint()
            v = val.prettyPrint()
            if oid == sys_descr_oid:
                metrics["sys_descr"] = v
            elif oid == sys_uptime_oid:
                # sysUpTime = centièmes de secondes (souvent un integer)
                try:
                    metrics["sys_uptime"] = int(v)
                except Exception:
                    metrics["sys_uptime"] = v

        return True, metrics, None

    except StopIteration:
        return False, {}, "snmp: no response"
    except Exception as e:
        return False, {}, f"snmp error: {e}"


def probe(device: Dict[str, Any]) -> Dict[str, Any]:
    """
    Entrypoint standard attendu par drivers/registry.py

    Input: device dict
    Output:
      {
        "status": "online"|"offline"|"unknown",
        "detail": "<string|None>",
        "metrics": { ... }
      }
    """
    ip = (device.get("ip") or "").strip()
    if not ip:
        return {"status": "unknown", "detail": "missing ip", "metrics": {"ts": _now_utc_iso()}}

    snmp_cfg = _as_dict(device.get("snmp"))
    community = (snmp_cfg.get("community") or "public").strip() or "public"
    port = _safe_int(snmp_cfg.get("port"), 161)
    timeout_s = _safe_int(snmp_cfg.get("timeout_s"), 1)
    retries = _safe_int(snmp_cfg.get("retries"), 1)

    ok, m, err = _snmp_get_sys(ip, community, port, timeout_s, retries)

    metrics: Dict[str, Any] = {
        "ts": _now_utc_iso(),
        "snmp_ok": ok,
        "snmp_port": port,
        "snmp_timeout_s": timeout_s,
        "snmp_retries": retries,
    }
    # merge metrics sysDescr/sysUpTime si présents
    if isinstance(m, dict):
        metrics.update(m)

    if ok:
        return {"status": "online", "detail": None, "metrics": metrics}

    detail = (err or "snmp failed").strip()
    if len(detail) > 280:
        detail = detail[:279] + "…"

    # SNMP KO => on considère offline (connectivité/agent)
    return {"status": "offline", "detail": detail, "metrics": metrics}


# -------------------------------------------------------------------
# Compatibilité backward
# -------------------------------------------------------------------
def collect(device: Dict[str, Any]) -> Dict[str, Any]:
    return probe(device)