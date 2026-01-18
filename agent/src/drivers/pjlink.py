# agent/src/drivers/pjlink.py
from __future__ import annotations

import socket
from hashlib import md5
from typing import Any, Dict, Tuple


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


def _recv_line(sock: socket.socket, max_bytes: int = 4096) -> str:
    """
    PJLink répond en ASCII/UTF-8 avec des fins de ligne \r\n.
    On lit jusqu'à \n ou jusqu'au max.
    """
    data = b""
    while len(data) < max_bytes:
        chunk = sock.recv(1)
        if not chunk:
            break
        data += chunk
        if chunk == b"\n":
            break
    try:
        return data.decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""


def _send_line(sock: socket.socket, line: str) -> None:
    if not line.endswith("\r\n"):
        line = line + "\r\n"
    sock.sendall(line.encode("utf-8", errors="ignore"))


def _pjlink_handshake(sock: socket.socket, password: str) -> Tuple[bool, str, str]:
    """
    PJLINK handshake.
    Exemple de greeting:
      "PJLINK 0"                 -> pas d'auth
      "PJLINK 1 89ABCDEF"        -> auth required, salt/challenge = 89ABCDEF

    Retour:
      (auth_required_ok, challenge, greeting)
    """
    greeting = _recv_line(sock)
    if not greeting.upper().startswith("PJLINK"):
        return False, "", greeting

    parts = greeting.split()
    if len(parts) < 2:
        return False, "", greeting

    mode = parts[1].strip()
    if mode == "0":
        return True, "", greeting

    # mode "1" : auth obligatoire
    if mode == "1" and len(parts) >= 3:
        challenge = parts[2].strip()
        if not password:
            return False, challenge, greeting
        return True, challenge, greeting

    return False, "", greeting


def _pjlink_auth_prefix(challenge: str, password: str) -> str:
    """
    Pour PJLink v1: prefix = MD5(challenge + password)
    """
    h = md5()
    h.update((challenge + password).encode("utf-8", errors="ignore"))
    return h.hexdigest()


def _parse_pjlink_kv(resp: str) -> Tuple[str, str]:
    """
    Réponses typiques:
      "%1POWR=0" / "%1POWR=1"
      "%1POWR=ERR1" ...
    """
    resp = (resp or "").strip()
    if "=" not in resp:
        return resp, ""
    k, v = resp.split("=", 1)
    return k.strip(), v.strip()


def collect(device: Dict[str, Any]) -> Dict[str, Any]:
    """
    Driver PJLink - convention d'entrypoint

    Retour normalisé:
      {
        "status": "online"|"offline"|"unknown",
        "detail": str,
        "metrics": dict
      }

    Config supportée:
      - ip: str (obligatoire)
      - pjlink: { password, port, timeout_s }
      - ou au niveau racine (tolérance): password/port/timeout_s
    """
    ip = (device.get("ip") or "").strip()
    if not ip:
        return {"status": "unknown", "detail": "missing_ip", "metrics": {}}

    pj_cfg = device.get("pjlink") or {}
    if not isinstance(pj_cfg, dict):
        pj_cfg = {}

    password = (pj_cfg.get("password") or device.get("pjlink_password") or device.get("password") or "").strip()
    port = _as_int(pj_cfg.get("port") or device.get("pjlink_port") or device.get("port") or 4352, 4352)
    timeout_s = _as_int(pj_cfg.get("timeout_s") or device.get("pjlink_timeout_s") or device.get("timeout_s") or 2, 2)

    port = max(1, port)
    timeout_s = max(1, timeout_s)

    metrics: Dict[str, Any] = {
        "pjlink_ok": False,
        "pjlink_port": port,
        "pjlink_power": None,   # 0/1/2 selon PJLink (off/on/cooling/warming selon modèles)
        "pjlink_class": None,   # souvent "%1"
        "pjlink_greeting": None,
        "pjlink_error": None,
    }

    try:
        with socket.create_connection((ip, port), timeout=timeout_s) as sock:
            sock.settimeout(timeout_s)

            ok, challenge, greeting = _pjlink_handshake(sock, password)
            metrics["pjlink_greeting"] = greeting

            if not ok:
                metrics["pjlink_error"] = "pjlink_auth_required_missing_password" if challenge else "pjlink_bad_greeting"
                return {"status": "offline", "detail": metrics["pjlink_error"], "metrics": metrics}

            auth_prefix = ""
            if challenge:
                auth_prefix = _pjlink_auth_prefix(challenge, password)

            # Commande: power status
            # PJLink: "POWR ?" -> réponse "%1POWR=0|1|2|3|ERRx"
            cmd = f"{auth_prefix}%1POWR ?"
            _send_line(sock, cmd)
            resp = _recv_line(sock)

            k, v = _parse_pjlink_kv(resp)
            metrics["pjlink_class"] = k[:2] if k.startswith("%") else None

            if "ERR" in v.upper():
                metrics["pjlink_error"] = f"pjlink_{v.lower()}"
                return {"status": "offline", "detail": metrics["pjlink_error"], "metrics": metrics}

            # v est normalement "0" ou "1" (parfois 2/3)
            try:
                metrics["pjlink_power"] = int(v)
            except Exception:
                metrics["pjlink_power"] = v

            metrics["pjlink_ok"] = True

            # Mapping simple: si on arrive à parler PJLink => online.
            # L'état power, lui, sert aux métriques (et potentiellement à la logique côté expectations).
            return {"status": "online", "detail": "pjlink_ok", "metrics": metrics}

    except (socket.timeout, TimeoutError):
        metrics["pjlink_error"] = "pjlink_timeout"
        return {"status": "offline", "detail": "pjlink_timeout", "metrics": metrics}
    except OSError as e:
        metrics["pjlink_error"] = f"oserror: {_as_str(e)[:120]}"
        return {"status": "offline", "detail": "pjlink_unreachable", "metrics": metrics}
    except Exception as e:
        metrics["pjlink_error"] = f"{e.__class__.__name__}: {_as_str(e)[:200]}"
        return {"status": "unknown", "detail": f"pjlink_exception: {e.__class__.__name__}", "metrics": metrics}