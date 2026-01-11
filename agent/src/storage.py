import json
import os
from typing import Any, Dict

DEFAULT_CONFIG: Dict[str, Any] = {
    "site_name": "site-demo",
    "site_token": "change-me",
    "api_url": "http://backend:8000/ingest",
    "devices": [
        {"ip": "8.8.8.8", "type": "test", "driver": "ping"},
        {"ip": "1.1.1.1", "type": "test", "driver": "ping"},
    ],
}

def load_config(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return DEFAULT_CONFIG.copy()
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(path: str, cfg: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)