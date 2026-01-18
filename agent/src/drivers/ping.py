# agent/src/drivers/ping.py
from __future__ import annotations

import platform
import subprocess
from typing import Any, Dict, Optional


def _ping_cmd(ip: str, timeout_s: int = 1, count: int = 1) -> list[str]:
    """
    Construit une commande ping portable (Linux/Windows/macOS).
    Dans notre contexte Docker Linux, on sera sur la branche Linux,
    mais c'est propre de rester tolérant.
    """
    system = (platform.system() or "").lower()

    # Linux/macOS: -c <count> ; timeout: Linux (-W seconds), macOS (-W milliseconds)
    if "windows" in system:
        # Windows: -n count ; -w timeout(ms)
        return ["ping", "-n", str(count), "-w", str(max(1, int(timeout_s * 1000))), ip]

    if "darwin" in system:
        # macOS: -W timeout en ms, -c count
        return ["ping", "-c", str(count), "-W", str(max(1, int(timeout_s * 1000))), ip]

    # Linux (default): -c count, -W timeout en secondes (per reply)
    return ["ping", "-c", str(count), "-W", str(max(1, int(timeout_s))), ip]


def collect(device: Dict[str, Any]) -> Dict[str, Any]:
    """
    Driver PING - convention d'entrypoint

    Le registry appelle collect(device_cfg) et attend un dict normalisé:
      {
        "status": "online"|"offline"|"unknown",
        "detail": str,
        "metrics": dict
      }

    Paramètres (dans device config):
      - ip: str (obligatoire)
      - timeout_s: int (optionnel, défaut 1)
      - count: int (optionnel, défaut 1)
    """
    ip = (device.get("ip") or "").strip()
    if not ip:
        return {"status": "unknown", "detail": "missing_ip", "metrics": {}}

    # tolérance: timeout peut être au niveau device["timeout_s"] ou device["ping"]["timeout_s"]
    timeout_s: int = 1
    count: int = 1

    try:
        timeout_s = int(device.get("timeout_s") or 1)
    except Exception:
        timeout_s = 1

    ping_cfg = device.get("ping") or {}
    if isinstance(ping_cfg, dict):
        try:
            timeout_s = int(ping_cfg.get("timeout_s") or timeout_s)
        except Exception:
            pass
        try:
            count = int(ping_cfg.get("count") or count)
        except Exception:
            pass

    timeout_s = max(1, timeout_s)
    count = max(1, min(5, count))  # garde-fou

    cmd = _ping_cmd(ip, timeout_s=timeout_s, count=count)

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=max(2, timeout_s + 2),
        )

        ok = proc.returncode == 0
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()

        if ok:
            return {
                "status": "online",
                "detail": "ping_ok",
                "metrics": {
                    "ping_cmd": " ".join(cmd),
                    "ping_out": out[:800],  # évite d'exploser la taille
                },
            }

        # offline: on garde un diagnostic court
        detail = "ping_failed"
        if err:
            detail = f"ping_failed: {err[:200]}"
        elif out:
            detail = f"ping_failed: {out.splitlines()[-1][:200]}"

        return {
            "status": "offline",
            "detail": detail,
            "metrics": {
                "ping_cmd": " ".join(cmd),
                "ping_out": out[:800],
                "ping_err": err[:400],
            },
        }

    except subprocess.TimeoutExpired:
        return {
            "status": "offline",
            "detail": f"ping_timeout_{timeout_s}s",
            "metrics": {"ping_cmd": " ".join(cmd)},
        }
    except FileNotFoundError:
        return {
            "status": "unknown",
            "detail": "ping_binary_not_found",
            "metrics": {},
        }
    except Exception as e:
        return {
            "status": "unknown",
            "detail": f"ping_error: {e.__class__.__name__}",
            "metrics": {},
        }