# agent/src/drivers/pjlink.py
import hashlib
import socket
from typing import Any, Dict, Optional, Tuple


DEFAULT_PORT = 4352


def _recv_line(sock: socket.socket, timeout_s: int) -> str:
    sock.settimeout(timeout_s)
    buf = b""
    while True:
        chunk = sock.recv(1)
        if not chunk:
            break
        buf += chunk
        if buf.endswith(b"\r") or buf.endswith(b"\n"):
            break
        if len(buf) > 4096:
            break
    return buf.decode("utf-8", errors="replace").strip()


def _send(sock: socket.socket, s: str) -> None:
    sock.sendall(s.encode("utf-8"))


def _parse_handshake(line: str) -> Tuple[int, Optional[str]]:
    """
    PJLINK 0
    PJLINK 1 <salt>
    """
    parts = (line or "").strip().split()
    if len(parts) < 2 or parts[0].upper() != "PJLINK":
        return (0, None)
    try:
        auth = int(parts[1])
    except Exception:
        auth = 0
    salt = parts[2] if (auth == 1 and len(parts) >= 3) else None
    return (auth, salt)


def _wrap_cmd(cmd: str) -> str:
    cmd = cmd.strip()
    if not cmd.startswith("%1"):
        cmd = "%1" + cmd
    if not cmd.endswith("\r"):
        cmd = cmd + "\r"
    return cmd


def _query(sock: socket.socket, auth: int, salt: Optional[str], password: str, cmd: str, timeout_s: int) -> str:
    """
    En PJLink auth=1 : on envoie MD5(salt+password) + "%1XXXX ?\r"
    En auth=0 : on envoie "%1XXXX ?\r"
    """
    payload = _wrap_cmd(cmd)
    if auth == 1:
        token = hashlib.md5((salt or "" + (password or "")).encode("utf-8")).hexdigest()
        payload = token + payload
    _send(sock, payload)
    return _recv_line(sock, timeout_s)


def _pjlink_cmd_response_value(line: str) -> str:
    # Ex: "%1POWR=1" -> "1"
    if "=" in (line or ""):
        return line.split("=", 1)[1].strip()
    return (line or "").strip()


def probe(device: Dict[str, Any]) -> Dict[str, Any]:
    """
    Probe PJLink minimal et robuste.
    Retour standard:
      status: online/offline/unknown
      detail: pjlink_ok / pjlink_auth_failed / pjlink_timeout / ...
      metrics: { power_state, lamp_hours, name, inf1, inf2, class }
    """
    ip = (device.get("ip") or "").strip()
    cfg = device.get("driver_cfg") or {}
    if not isinstance(cfg, dict):
        cfg = {}

    port = int(cfg.get("port") or DEFAULT_PORT)
    timeout_s = int(cfg.get("timeout_s") or 2)
    password = (cfg.get("password") or "").strip()

    metrics: Dict[str, Any] = {
        "pjlink_port": str(port),
    }

    if not ip:
        return {"status": "unknown", "detail": "pjlink_missing_ip", "metrics": metrics}

    try:
        with socket.create_connection((ip, port), timeout=timeout_s) as sock:
            # Handshake
            hello = _recv_line(sock, timeout_s)
            auth, salt = _parse_handshake(hello)

            metrics["pjlink_auth"] = str(auth)

            # Test commande "CLSS ?" (classe PJLink)
            resp_clss = _query(sock, auth, salt, password, "CLSS ?", timeout_s)
            # Si auth incorrect, certains proj renvoient ERR ou refusent
            if "ERR" in (resp_clss or "").upper():
                return {"status": "online", "detail": f"pjlink_err:{resp_clss}", "metrics": metrics}

            clss_val = _pjlink_cmd_response_value(resp_clss)
            metrics["pjlink_class"] = clss_val

            # Power
            resp_powr = _query(sock, auth, salt, password, "POWR ?", timeout_s)
            powr_val = _pjlink_cmd_response_value(resp_powr)
            # 0=off, 1=on, 2=cooling, 3=warm-up (selon PJLink)
            metrics["power_state"] = powr_val

            # NAME (nom PJLink)
            resp_name = _query(sock, auth, salt, password, "NAME ?", timeout_s)
            metrics["pjlink_name"] = _pjlink_cmd_response_value(resp_name)

            # INF1/INF2 : infos fabricant / modèle (selon implémentation)
            resp_inf1 = _query(sock, auth, salt, password, "INF1 ?", timeout_s)
            resp_inf2 = _query(sock, auth, salt, password, "INF2 ?", timeout_s)
            metrics["inf1"] = _pjlink_cmd_response_value(resp_inf1)
            metrics["inf2"] = _pjlink_cmd_response_value(resp_inf2)

            # LAMP ? : heures de lampe (peut renvoyer plusieurs paires)
            resp_lamp = _query(sock, auth, salt, password, "LAMP ?", timeout_s)
            lamp_val = _pjlink_cmd_response_value(resp_lamp)
            # souvent : "123 0" (heures + état) ou "123 0 456 0"
            metrics["lamp_raw"] = lamp_val

            # Heures lisibles (best-effort)
            try:
                parts = lamp_val.split()
                if len(parts) >= 1:
                    metrics["lamp_hours"] = parts[0]
            except Exception:
                pass

            # Status
            # Si on a pu poser CLSS/POWR : online
            detail = "pjlink_ok"
            # détail plus parlant : état power
            if powr_val == "0":
                detail = "pjlink_ok_power_off"
            elif powr_val == "1":
                detail = "pjlink_ok_power_on"
            elif powr_val == "2":
                detail = "pjlink_ok_cooling"
            elif powr_val == "3":
                detail = "pjlink_ok_warmup"

            return {"status": "online", "detail": detail, "metrics": metrics}

    except socket.timeout:
        return {"status": "offline", "detail": "pjlink_timeout", "metrics": metrics}
    except ConnectionRefusedError:
        return {"status": "offline", "detail": "pjlink_conn_refused", "metrics": metrics}
    except OSError as e:
        return {"status": "offline", "detail": f"pjlink_oserror:{str(e)[:120]}", "metrics": metrics}
    except Exception as e:
        return {"status": "unknown", "detail": f"pjlink_error:{str(e)[:120]}", "metrics": metrics}