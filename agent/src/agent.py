import os
import json
import time
import subprocess
import requests

API_URL = os.getenv("API_URL", "http://backend:8000/ingest")
SITE_NAME = os.getenv("SITE_NAME", "site-demo")
SITE_TOKEN = os.getenv("SITE_TOKEN", "change-me")
DEVICES = json.loads(os.getenv("DEVICES_JSON", "[]"))

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

def collect():
    out = []
    for d in DEVICES:
        ip = d["ip"]
        ok = ping(ip, 1)
        out.append({
            "ip": ip,
            "status": "online" if ok else "offline",
            "detail": "ping_ok" if ok else "ping_failed",
            "metrics": {}
        })
    return out

def send(devices):
    payload = {"site_name": SITE_NAME, "devices": devices}
    headers = {"X-Site-Token": SITE_TOKEN}
    r = requests.post(API_URL, json=payload, headers=headers, timeout=5)
    r.raise_for_status()

def main():
    while True:
        devices = collect()
        try:
            send(devices)
            print(f"Sent {len(devices)} devices")
        except Exception as e:
            print(f"Send failed: {e}")
        time.sleep(10)

if __name__ == "__main__":
    main()
