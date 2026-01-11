# agent/src/drivers/ping.py
import subprocess


def ping(ip: str, timeout_s: int = 1) -> bool:
    try:
        r = subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout_s), ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return r.returncode == 0
    except Exception:
        return False