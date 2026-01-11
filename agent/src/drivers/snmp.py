from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from pysnmp.hlapi import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    getCmd,
)

# OIDs "génériques" très utiles :
# sysDescr.0 : description de l’équipement (souvent contient marque/modèle)
SYS_DESCR_OID = "1.3.6.1.2.1.1.1.0"
# sysUpTime.0 : uptime SNMP (permet de valider réponse SNMP)
SYS_UPTIME_OID = "1.3.6.1.2.1.1.3.0"


def _snmp_get(ip: str, community: str, oid: str, port: int = 161, timeout_s: int = 1, retries: int = 1) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Retourne: (ok, value, error)
    """
    try:
        iterator = getCmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),  # v2c
            UdpTransportTarget((ip, port), timeout=timeout_s, retries=retries),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
        )

        error_indication, error_status, error_index, var_binds = next(iterator)

        if error_indication:
            return False, None, str(error_indication)

        if error_status:
            return False, None, f"{error_status.prettyPrint()} at {error_index}"

        # 1 OID => 1 valeur
        for _name, val in var_binds:
            return True, val.prettyPrint(), None

        return False, None, "empty_response"

    except Exception as e:
        return False, None, str(e)


def snmp_probe(device: Dict[str, Any]) -> Dict[str, Any]:
    """
    Probe SNMP générique :
    - tente sysUpTime et sysDescr
    - retourne un dict "résultat" utilisable dans collector.py
    """
    ip = (device.get("ip") or "").strip()
    snmp_cfg = device.get("snmp") or {}

    community = (snmp_cfg.get("community") or "public").strip()
    port = int(snmp_cfg.get("port") or 161)
    timeout_s = int(snmp_cfg.get("timeout_s") or 1)
    retries = int(snmp_cfg.get("retries") or 1)

    ok_uptime, uptime, err_uptime = _snmp_get(ip, community, SYS_UPTIME_OID, port, timeout_s, retries)
    ok_descr, descr, err_descr = _snmp_get(ip, community, SYS_DESCR_OID, port, timeout_s, retries)

    ok = ok_uptime or ok_descr
    return {
        "snmp_ok": ok,
        "sys_uptime": uptime if ok_uptime else None,
        "sys_descr": descr if ok_descr else None,
        "snmp_error": err_uptime or err_descr,
        "snmp_community": community,
        "snmp_port": port,
    }