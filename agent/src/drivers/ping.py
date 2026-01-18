# agent/src/drivers/ping.py
from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(x: Any, default: int) -> int:
    try:
        return int(str(x).strip())
    except Exception:
        return default


def _parse_rtt_ms(ping_output: str) -> Optional[float]:
    """
    Tente d'extraire un RTT moyen depuis la sortie de ping.
    Supporte principalement la sortie Linux.
    Exemple: "rtt min/avg/max/mdev = 0.123/0.456/0.789/0.012 ms"
    """
    if not ping_output:
        return None

    m = re.search(r"=\s*([\d\.]+)/([\d\.]+)/([\d\.]+)/", ping_output)
    if m:
        try:
            return float(m.group(2))
        except Exception:
            return None
    return None


def _run_ping(ip: str, timeout_s: int = 1, count: int = 1) -> Tuple[bool, str, Optional[float]]:
    """
    Ping Linux:
    -c <count> : nombre de paquets
    -W <timeout> : timeout en secondes (pour chaque paquet)
    """
    timeout_s = max(1, int(timeout_s))
    count = max(1, int(count))

    # IMPORTANT: commande ping dans container linux
    cmd = ["ping", "-c", str(count), "-W", str(timeout_s), ip]

    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s * count + 2,
        )
        out = (p.stdout or "") + "\n" + (p.stderr or "")
        ok = (p.returncode == 0)
        rtt = _parse_rtt_ms(out) if ok else None
        return ok, out.strip(), rtt
    except subprocess.TimeoutExpired:
        return False, "ping timeout", None
    except FileNotFoundError:
        return False, "ping binary not found", None
    except Exception as e:
        return False, f"ping error: {e}", None


def probe(device: Dict[str, Any]) -> Dict[str, Any]:
    """
    Entrypoint standard attendu par drivers/registry.py

    Input: device dict (au minimum {"ip": "..."}).
    Output: dict standard:
      {
        "status": "online"|"offline"|"unknown",
        "detail": "<string|None>",
        "metrics": { ... }
      }
    """
    ip = (device.get("ip") or "").strip()
    if not ip:
        return {"status": "unknown", "detail": "missing ip", "metrics": {"ts": _now_utc_iso()}}

    # Options (si présentes dans config)
    # - ping: {"timeout_s": 1, "count": 1}
    ping_cfg = device.get("ping") if isinstance(device.get("ping"), dict) else {}
    timeout_s = _safe_int(ping_cfg.get("timeout_s"), 1)
    count = _safe_int(ping_cfg.get("count"), 1)

    ok, raw, rtt_ms = _run_ping(ip, timeout_s=timeout_s, count=count)

    metrics: Dict[str, Any] = {
        "ts": _now_utc_iso(),
        "ping_ok": ok,
        "ping_timeout_s": timeout_s,
        "ping_count": count,
    }
    if rtt_ms is not None:
        metrics["ping_rtt_avg_ms"] = rtt_ms

    if ok:
        return {"status": "online", "detail": None, "metrics": metrics}

    # Limiter la taille du détail pour éviter d'exploser l'UI/DB
    detail = raw.strip()
    if len(detail) > 280:
        detail = detail[:279] + "…"

    return {"status": "offline", "detail": detail or "ping failed", "metrics": metrics}


# -------------------------------------------------------------------
# Compatibilité backward
# -------------------------------------------------------------------
def collect(device: Dict[str, Any]) -> Dict[str, Any]:
    """
    Alias historique si d'autres morceaux de code utilisent collect().
    """
    return probe(device)