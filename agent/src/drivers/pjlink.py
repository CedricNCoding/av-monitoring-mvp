# agent/src/drivers/pjlink.py
from __future__ import annotations

import socket
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _safe_int(x: Any, default: int) -> int:
    try:
        return int(str(x).strip())
    except Exception:
        return default


def _recv_line(sock: socket.socket, max_bytes: int = 4096) -> str:
    """
    PJLink parle en lignes ASCII finissant par \\r.
    """
    data = b""
    while len(data) < max_bytes:
        chunk = sock.recv(1)
        if not chunk:
            break
        data += chunk
        if chunk == b"\r":
            break
    try:
        return data.decode("ascii", errors="ignore").strip()
    except Exception:
        return ""


def _send_line(sock: socket.socket, line: str) -> None:
    if not line.endswith("\r"):
        line = line + "\r"
    sock.sendall(line.encode("ascii", errors="ignore"))


def _pjlink_handshake(sock: socket.socket, password: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Retourne (ok, auth_used, error)

    Serveur renvoie typiquement:
      - "PJLINK 0" => pas d'auth
      - "PJLINK 1 <salt>" => auth MD5(salt+password) à préfixer à la commande
    """
    hello = _recv_line(sock)
    if not hello.startswith("PJLINK"):
        return False, None, f"invalid handshake: {hello or 'empty'}"

    parts = hello.split()
    if len(parts) < 2:
        return False, None, f"invalid handshake: {hello}"

    mode = parts[1].strip()
    if mode == "0":
        return True, "none", None

    if mode == "1":
        # auth required
        if len(parts) < 3:
            return False, None, f"auth required but no salt: {hello}"
        salt = parts[2].strip()
        if not password:
            return False, None, "auth required but password missing"
        try:
            import hashlib

            token = hashlib.md5((salt + password).encode("ascii", errors="ignore")).hexdigest()
            return True, "md5", token
        except Exception as e:
            return False, None, f"auth md5 failed: {e}"

    return False, None, f"unsupported auth mode: {hello}"


def _pjlink_cmd(sock: socket.socket, cmd: str, auth_prefix: Optional[str]) -> str:
    """
    Envoie une commande PJLink et lit la réponse.
    Si auth_prefix est un hex MD5, on préfixe: <md5><cmd>
    """
    if auth_prefix and auth_prefix != "none":
        line = f"{auth_prefix}{cmd}"
    else:
        line = cmd
    _send_line(sock, line)
    return _recv_line(sock)


def _parse_power_response(resp: str) -> Tuple[bool, Optional[int], Optional[str]]:
    """
    Réponse attendue:
      - "%1POWR=0" (OFF)
      - "%1POWR=1" (ON)
      - "%1POWR=2" (cooling)
      - "%1POWR=3" (warm-up)
      - "%1POWR=ERR1" etc.
    """
    if not resp:
        return False, None, "empty response"

    if "ERR" in resp:
        return False, None, resp

    if "=" not in resp:
        return False, None, resp

    _, v = resp.split("=", 1)
    v = v.strip()

    try:
        return True, int(v), None
    except Exception:
        return False, None, resp


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

    Convention utilisée ici:
      - Si le projecteur est joignable PJLink -> status="online"
      - Sinon -> status="offline" (car c'est bien l'équipement qui ne répond pas au protocole)
      - Les états POWR sont dans metrics["pjlink_power"]
    """
    ip = (device.get("ip") or "").strip()
    if not ip:
        return {"status": "unknown", "detail": "missing ip", "metrics": {"ts": _now_utc_iso()}}

    pj = _as_dict(device.get("pjlink"))
    port = _safe_int(pj.get("port"), 4352)
    timeout_s = _safe_int(pj.get("timeout_s"), 2)
    password = (pj.get("password") or "").strip()

    metrics: Dict[str, Any] = {
        "ts": _now_utc_iso(),
        "pjlink_ok": False,
        "pjlink_port": port,
        "pjlink_timeout_s": timeout_s,
    }

    try:
        with socket.create_connection((ip, port), timeout=max(1, timeout_s)) as sock:
            sock.settimeout(max(1, timeout_s))

            ok, auth_used, auth_token_or_err = _pjlink_handshake(sock, password)
            if not ok:
                detail = (auth_token_or_err or "pjlink handshake failed").strip()
                metrics["pjlink_error"] = detail
                return {"status": "offline", "detail": detail, "metrics": metrics}

            if auth_used == "md5":
                auth_prefix = auth_token_or_err  # md5 hex
            else:
                auth_prefix = None

            # Power status
            resp = _pjlink_cmd(sock, "%1POWR ?", auth_prefix)
            ok2, power_val, perr = _parse_power_response(resp)

            metrics["pjlink_ok"] = True
            metrics["pjlink_auth"] = auth_used or "unknown"
            metrics["pjlink_raw_powr"] = resp

            if ok2:
                metrics["pjlink_power"] = power_val
                # Optionnel: interprétation simple
                metrics["pjlink_power_label"] = {
                    0: "off",
                    1: "on",
                    2: "cooling",
                    3: "warmup",
                }.get(power_val, "unknown")
            else:
                metrics["pjlink_power"] = None
                metrics["pjlink_error"] = (perr or "unknown").strip()

            # Si on arrive ici, PJLink répond => online
            return {"status": "online", "detail": None, "metrics": metrics}

    except (ConnectionRefusedError, TimeoutError, socket.timeout) as e:
        detail = f"pjlink connect timeout/refused: {e}".strip()
        if len(detail) > 280:
            detail = detail[:279] + "…"
        metrics["pjlink_error"] = detail
        return {"status": "offline", "detail": detail, "metrics": metrics}
    except OSError as e:
        detail = f"pjlink socket error: {e}".strip()
        if len(detail) > 280:
            detail = detail[:279] + "…"
        metrics["pjlink_error"] = detail
        return {"status": "offline", "detail": detail, "metrics": metrics}
    except Exception as e:
        detail = f"pjlink error: {e}".strip()
        if len(detail) > 280:
            detail = detail[:279] + "…"
        metrics["pjlink_error"] = detail
        return {"status": "offline", "detail": detail, "metrics": metrics}


# -------------------------------------------------------------------
# Compatibilité backward
# -------------------------------------------------------------------
def collect(device: Dict[str, Any]) -> Dict[str, Any]:
    return probe(device)