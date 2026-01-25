# agent/src/config_sync.py
"""
Module de synchronisation de la configuration agent depuis le backend.

L'agent interroge périodiquement le backend pour récupérer la configuration
officielle des équipements à monitorer. Si la configuration a changé,
elle est appliquée automatiquement.

Stratégie:
- Pull régulier (toutes les N minutes, configurable)
- Comparaison de hash MD5 pour détecter les changements
- Fallback sur config.json locale en cas d'indisponibilité backend
- Résilience: ne jamais planter si le backend est down
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests

from src.storage import save_config, load_config

CONFIG_PATH = os.getenv("AGENT_CONFIG", "/var/lib/avmonitoring/config.json")


# -------------------------------------------------------------------
# État de synchronisation (thread-safe)
# -------------------------------------------------------------------
_sync_lock = threading.Lock()
_sync_status: Dict[str, Any] = {
    "last_sync_at": None,           # ISO UTC
    "last_sync_ok": None,           # bool|None
    "last_sync_error": None,        # str|None
    "current_hash": None,           # MD5 hash actuel
    "backend_hash": None,           # MD5 hash du backend
    "config_updated_at": None,      # ISO UTC
}


def get_sync_status() -> Dict[str, Any]:
    """Retourne l'état de la dernière synchronisation."""
    with _sync_lock:
        return dict(_sync_status)


def _set_sync_status(**kwargs: Any) -> None:
    with _sync_lock:
        _sync_status.update(kwargs)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


# -------------------------------------------------------------------
# Calcul du hash local
# -------------------------------------------------------------------
def _compute_local_hash(cfg: Dict[str, Any]) -> str:
    """
    Calcule le hash MD5 de la configuration locale.
    Doit correspondre à la même méthode que le backend.
    """
    config_data = {
        "site_name": cfg.get("site_name", ""),
        "timezone": cfg.get("policy", {}).get("timezone", "Europe/Paris"),
        "doubt_after_days": cfg.get("policy", {}).get("doubt_after_days", 2),
        "ok_interval_s": cfg.get("reporting", {}).get("ok_interval_s", 300),
        "ko_interval_s": cfg.get("reporting", {}).get("ko_interval_s", 60),
        "devices": []
    }

    devices = cfg.get("devices", [])
    if not isinstance(devices, list):
        devices = []

    for d in sorted(devices, key=lambda x: x.get("ip", "")):
        device_data = {
            "ip": d.get("ip", ""),
            "name": d.get("name", ""),
            "building": d.get("building", ""),
            "floor": d.get("floor", ""),
            "room": d.get("room", ""),
            "type": d.get("type", "unknown"),
            "driver": d.get("driver", "ping"),
            "driver_config": {
                "snmp": d.get("snmp", {}),
                "pjlink": d.get("pjlink", {}),
            },
            "expectations": d.get("expectations", {}),
        }
        config_data["devices"].append(device_data)

    # Serialization JSON déterministe
    json_str = json.dumps(config_data, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(json_str.encode('utf-8')).hexdigest()


# -------------------------------------------------------------------
# Synchronisation avec le backend
# -------------------------------------------------------------------
def sync_config_from_backend(cfg: Dict[str, Any]) -> bool:
    """
    Interroge le backend pour récupérer la configuration officielle.

    Returns:
        True si la config a été mise à jour, False sinon.
    """
    # Support both "backend_url" (new) and "api_url" (legacy) for backward compatibility
    # If backend_url contains CHANGE_ME or example.com, fallback to api_url
    backend_url = (cfg.get("backend_url") or "").strip()
    api_url_legacy = (cfg.get("api_url") or "").strip()

    if backend_url and "CHANGE_ME" not in backend_url and "example.com" not in backend_url:
        api_url = backend_url
    else:
        api_url = api_url_legacy

    site_token = (cfg.get("site_token") or "").strip()

    if not api_url or not site_token:
        _set_sync_status(
            last_sync_at=_iso(_now_utc()),
            last_sync_ok=False,
            last_sync_error="missing_backend_url_or_site_token",
        )
        print("⚠️  Config sync skipped: missing backend_url or site_token")
        return False

    # Construire l'URL de l'endpoint /config/<token>
    # On remplace /ingest par /config/<token> dans l'URL
    if "/ingest" in api_url:
        base_url = api_url.replace("/ingest", "")
    else:
        # Fallback: extraire la base URL
        from urllib.parse import urlparse
        parsed = urlparse(api_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

    config_url = f"{base_url}/config/{site_token}"

    try:
        print(f"🔄 Fetching config from {config_url}...")
        r = requests.get(config_url, timeout=10)
        r.raise_for_status()
        backend_config = r.json()

        backend_hash = backend_config.get("config_hash", "")
        current_hash = _compute_local_hash(cfg)

        _set_sync_status(
            last_sync_at=_iso(_now_utc()),
            last_sync_ok=True,
            last_sync_error=None,
            current_hash=current_hash,
            backend_hash=backend_hash,
        )

        if backend_hash == current_hash:
            print(f"✅ Config is up-to-date (hash: {current_hash[:8]}...)")
            return False

        # Config a changé, on applique
        print(f"📥 Config changed! Updating from backend...")
        print(f"   Old hash: {current_hash[:8]}...")
        print(f"   New hash: {backend_hash[:8]}...")

        # Construire la nouvelle config locale
        # Préserver backend_url locale si elle est valide, sinon reconstruire depuis base_url
        current_backend_url = cfg.get("backend_url", "").strip()
        current_api_url = cfg.get("api_url", "").strip()

        # Utiliser l'URL locale si elle est valide (pas CHANGE_ME, pas example.com, pas localhost/backend)
        if current_backend_url and \
           "CHANGE_ME" not in current_backend_url and \
           "example.com" not in current_backend_url and \
           "localhost" not in current_backend_url and \
           "backend:" not in current_backend_url:
            backend_url_to_save = current_backend_url
        elif current_api_url and \
             "CHANGE_ME" not in current_api_url and \
             "example.com" not in current_api_url and \
             "localhost" not in current_api_url and \
             "backend:" not in current_api_url:
            backend_url_to_save = current_api_url
        else:
            # Fallback : reconstruire depuis base_url (qui a servi pour la sync)
            backend_url_to_save = f"{base_url}/ingest"

        new_config = {
            "site_name": backend_config.get("site_name", cfg.get("site_name", "")),
            "site_token": site_token,
            "backend_url": backend_url_to_save,  # Preserve valid local URL or reconstruct
            "policy": {
                "timezone": backend_config.get("timezone", "Europe/Paris"),
                "doubt_after_days": backend_config.get("doubt_after_days", 2),
            },
            "reporting": backend_config.get("reporting", {
                "ok_interval_s": 300,
                "ko_interval_s": 60,
            }),
            "devices": [],
        }

        # Mapper les devices du backend vers le format agent
        # Créer un index des devices locaux par IP pour préserver snmp.community et pjlink.password
        local_devices_by_ip = {dev.get("ip"): dev for dev in cfg.get("devices", []) if dev.get("ip")}

        for d in backend_config.get("devices", []):
            ip = d.get("ip", "")
            local_device = local_devices_by_ip.get(ip, {})

            # Fusionner SNMP : backend + préserver community locale si absente/invalide du backend
            snmp_backend = d.get("snmp") or {}
            snmp_local = local_device.get("snmp") or {}
            snmp_merged = dict(snmp_backend) if isinstance(snmp_backend, dict) else {}

            # Stratégie de fusion pour community:
            # 1. Si backend a une valeur valide (non None, non vide, non "none") -> utiliser backend
            # 2. Sinon, si local a une valeur valide -> utiliser local
            # 3. Sinon, utiliser "public" par défaut
            backend_community = snmp_merged.get("community")
            local_community = snmp_local.get("community") if isinstance(snmp_local, dict) else None

            if backend_community and backend_community != "none" and backend_community.strip():
                # Backend a une valeur valide
                snmp_merged["community"] = backend_community.strip()
                print(f"  📡 {ip}: Using backend SNMP community: {snmp_merged['community']}")
            elif local_community and local_community != "none" and local_community.strip():
                # Local a une valeur valide
                snmp_merged["community"] = local_community.strip()
                print(f"  💾 {ip}: Preserving local SNMP community: {snmp_merged['community']}")
            else:
                # Aucune valeur valide, fallback sur "public"
                snmp_merged["community"] = "public"
                print(f"  ⚠️  {ip}: No valid SNMP community, using default: public")

            # Fusionner PJLink : backend + préserver password local si absent/invalide du backend
            pjlink_backend = d.get("pjlink") or {}
            pjlink_local = local_device.get("pjlink") or {}
            pjlink_merged = dict(pjlink_backend) if isinstance(pjlink_backend, dict) else {}

            # Stratégie de fusion pour password (peut être vide volontairement)
            backend_password = pjlink_merged.get("password")
            local_password = pjlink_local.get("password") if isinstance(pjlink_local, dict) else None

            if backend_password is not None and backend_password != "none":
                # Backend a défini un password (peut être vide)
                pjlink_merged["password"] = backend_password
            elif local_password is not None and local_password != "none":
                # Local a un password
                pjlink_merged["password"] = local_password
            else:
                # Pas de password
                pjlink_merged["password"] = ""

            device = {
                "ip": ip,
                "name": d.get("name", ""),
                "building": d.get("building", ""),
                "floor": d.get("floor", ""),
                "room": d.get("room", ""),
                "type": d.get("type", "unknown"),
                "driver": d.get("driver", "ping"),
                "snmp": snmp_merged,
                "pjlink": pjlink_merged,
                "expectations": d.get("expectations", {}),
            }
            new_config["devices"].append(device)

        # Sauvegarder la nouvelle config
        save_config(CONFIG_PATH, new_config)

        _set_sync_status(
            config_updated_at=_iso(_now_utc()),
            current_hash=backend_hash,
        )

        print(f"✅ Config updated successfully! {len(new_config['devices'])} devices configured.")
        return True

    except requests.exceptions.RequestException as e:
        _set_sync_status(
            last_sync_at=_iso(_now_utc()),
            last_sync_ok=False,
            last_sync_error=f"request_error: {e.__class__.__name__}: {e}",
        )
        print(f"⚠️  Config sync failed (network): {e.__class__.__name__}: {e}")
        print(f"   → Continuing with local config.json")
        return False

    except Exception as e:
        _set_sync_status(
            last_sync_at=_iso(_now_utc()),
            last_sync_ok=False,
            last_sync_error=f"{e.__class__.__name__}: {e}",
        )
        print(f"⚠️  Config sync failed: {e.__class__.__name__}: {e}")
        print(f"   → Continuing with local config.json")
        return False


# -------------------------------------------------------------------
# Loop de synchronisation périodique
# -------------------------------------------------------------------
def run_sync_loop(stop_flag: Dict[str, bool], interval_minutes: int = 5) -> None:
    """
    Boucle de synchronisation qui s'exécute toutes les N minutes.

    Args:
        stop_flag: dictionnaire avec clé "stop" pour arrêter la boucle
        interval_minutes: fréquence de synchronisation en minutes
    """
    interval_seconds = interval_minutes * 60

    print(f"🚀 Config sync loop started (interval: {interval_minutes} min)")

    # Première sync immédiate au démarrage (après 10 secondes)
    time.sleep(10)

    while True:
        if stop_flag.get("stop"):
            print("🛑 Config sync loop stopped")
            break

        try:
            cfg = load_config(CONFIG_PATH)
            updated = sync_config_from_backend(cfg)

            # Si la config a été mise à jour, on peut déclencher un reload
            # du collector (optionnel, le collector rechargera au prochain cycle)
            if updated:
                print("📢 Config updated, collector will reload on next cycle")

        except Exception as e:
            print(f"⚠️  Error in sync loop: {e.__class__.__name__}: {e}")

        # Attendre avant la prochaine sync
        for _ in range(interval_seconds):
            if stop_flag.get("stop"):
                break
            time.sleep(1)


# -------------------------------------------------------------------
# Démarrage du thread de sync
# -------------------------------------------------------------------
def start_sync_thread(interval_minutes: int = 5) -> tuple[threading.Thread, Dict[str, bool]]:
    """
    Démarre le thread de synchronisation périodique.

    Args:
        interval_minutes: fréquence de synchronisation en minutes

    Returns:
        (thread, stop_flag): le thread et le flag pour l'arrêter
    """
    stop_flag = {"stop": False}
    thread = threading.Thread(
        target=run_sync_loop,
        args=(stop_flag, interval_minutes),
        daemon=True
    )
    thread.start()
    return thread, stop_flag
