# agent/src/drivers/zigbee.py
"""
Driver Zigbee pour collecte d'état via MQTT/Zigbee2MQTT.

Interface standardisée (compatible avec ping, snmp, pjlink):
- probe(device: Dict) -> Dict {"status", "detail", "metrics"}

Logique:
- last_seen < 60 min → online
- last_seen >= 60 min → offline
- MQTT down ou device absent → unknown

Aucune exception levée (isolation garantie).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

try:
    from src.mqtt_client import get_mqtt_manager
    MQTT_CLIENT_AVAILABLE = True
except ImportError:
    MQTT_CLIENT_AVAILABLE = False


def probe(device: Dict[str, Any]) -> Dict[str, Any]:
    """
    Entrypoint driver Zigbee (interface standard).

    Args:
        device: Config device avec:
            - ip: Format "zigbee:<friendly_name>" (OBLIGATOIRE)
            - driver: "zigbee"
            - zigbee: {...} bloc optionnel

    Returns:
        Dict:
            - status: "online" | "offline" | "unknown"
            - detail: str | None (raison status)
            - metrics: Dict (battery, linkquality, sensors, etc.)

    Garantie: Aucune exception levée (registry.py wrappe mais par sécurité).
    """

    # Vérifier si mqtt_client disponible
    if not MQTT_CLIENT_AVAILABLE:
        return {
            "status": "unknown",
            "detail": "mqtt_client_not_available",
            "metrics": {"error": "paho-mqtt not installed"}
        }

    # Extraction friendly_name depuis ip
    ip = device.get("ip", "").strip()
    if not ip.startswith("zigbee:"):
        return {
            "status": "unknown",
            "detail": "invalid_zigbee_ip_format",
            "metrics": {"expected_format": "zigbee:<friendly_name>"}
        }

    friendly_name = ip[7:]  # Retire "zigbee:" prefix

    if not friendly_name:
        return {
            "status": "unknown",
            "detail": "empty_friendly_name",
            "metrics": {}
        }

    # Récupération gestionnaire MQTT (singleton)
    try:
        mqtt = get_mqtt_manager()
    except Exception as e:
        return {
            "status": "unknown",
            "detail": f"mqtt_manager_error:{e}",
            "metrics": {}
        }

    # Vérifier connexion MQTT
    if not mqtt.is_connected():
        return {
            "status": "unknown",
            "detail": "mqtt_disconnected",
            "metrics": {"mqtt_connected": False}
        }

    # Récupérer état device depuis cache
    try:
        state = mqtt.get_device_state(friendly_name)
    except Exception as e:
        return {
            "status": "unknown",
            "detail": f"cache_read_error:{e}",
            "metrics": {}
        }

    if not state:
        return {
            "status": "unknown",
            "detail": "device_not_in_cache",
            "metrics": {
                "mqtt_connected": True,
                "hint": "Device not paired or not sending updates"
            }
        }

    # Initialiser métriques
    now = datetime.now(timezone.utc)
    metrics: Dict[str, Any] = {
        "ts": now.isoformat(),
        "mqtt_connected": True,
    }

    # -----------------------------------------------------------
    # Détermination status online/offline (basé sur last_seen)
    # -----------------------------------------------------------

    status = "unknown"
    detail = None

    last_seen_str = state.get("last_seen")
    if last_seen_str:
        try:
            # Parse ISO timestamp (Zigbee2MQTT format: "2026-01-24T10:30:00+01:00" ou "...Z")
            last_seen_dt = datetime.fromisoformat(last_seen_str.replace("Z", "+00:00"))

            # Calculer delta en minutes
            delta_seconds = (now - last_seen_dt).total_seconds()
            delta_minutes = delta_seconds / 60

            metrics["last_seen"] = last_seen_str
            metrics["last_seen_minutes_ago"] = round(delta_minutes, 1)

            # Seuil: 60 minutes
            if delta_minutes < 60:
                status = "online"
            else:
                status = "offline"
                detail = f"last_seen_{int(delta_minutes)}min_ago"

        except (ValueError, TypeError) as e:
            # Format last_seen invalide
            status = "unknown"
            detail = f"invalid_last_seen_format:{e}"
            metrics["last_seen_raw"] = last_seen_str
    else:
        # Pas de last_seen dans payload (device coordinateur ou bridge?)
        status = "unknown"
        detail = "no_last_seen_field"

    # -----------------------------------------------------------
    # Extraction métriques additionnelles
    # -----------------------------------------------------------

    # Battery (0-100%)
    if "battery" in state:
        try:
            metrics["battery"] = int(state["battery"])
        except (ValueError, TypeError):
            metrics["battery"] = state["battery"]

    # Link quality (0-255)
    if "linkquality" in state:
        try:
            metrics["linkquality"] = int(state["linkquality"])
        except (ValueError, TypeError):
            metrics["linkquality"] = state["linkquality"]

    # State (ON/OFF pour switches/lights)
    if "state" in state:
        metrics["state"] = str(state["state"]).upper()

    # Brightness (pour lumières dimmables)
    if "brightness" in state:
        try:
            metrics["brightness"] = int(state["brightness"])
        except (ValueError, TypeError):
            pass

    # Color temperature (pour lumières)
    if "color_temp" in state:
        try:
            metrics["color_temp"] = int(state["color_temp"])
        except (ValueError, TypeError):
            pass

    # -----------------------------------------------------------
    # Capteurs génériques (température, humidité, etc.)
    # -----------------------------------------------------------

    sensor_fields = [
        "temperature",       # °C
        "humidity",          # %
        "pressure",          # hPa
        "co2",               # ppm
        "voc",               # ppb (Volatile Organic Compounds)
        "pm25",              # µg/m³ (particules fines)
        "illuminance",       # lux
        "illuminance_lux",
        "occupancy",         # bool
        "contact",           # bool (porte/fenêtre)
        "water_leak",        # bool
        "smoke",             # bool
        "tamper",            # bool
        "vibration",         # bool
        "action",            # str (bouton pressé)
        "click",             # str
        "power",             # W (consommation)
        "energy",            # kWh (compteur)
        "current",           # A
        "voltage",           # V
    ]

    for field in sensor_fields:
        if field in state:
            value = state[field]

            # Convertir booléens en vrais bools Python
            if isinstance(value, bool):
                metrics[field] = value
            elif isinstance(value, str) and value.lower() in ["true", "false"]:
                metrics[field] = (value.lower() == "true")
            else:
                # Valeur numérique ou string, garder tel quel
                try:
                    # Tenter conversion numérique si possible
                    if isinstance(value, (int, float)):
                        metrics[field] = value
                    elif isinstance(value, str):
                        # Garder en string (ex: "single", "double" pour action)
                        metrics[field] = value
                except:
                    metrics[field] = value

    # -----------------------------------------------------------
    # Flags additionnels
    # -----------------------------------------------------------

    # Cache stale (> 5 min)
    if state.get("stale"):
        metrics["cache_stale"] = True
        metrics["cache_age_seconds"] = state.get("cache_age_seconds", 0)

    # Voltage batterie (si disponible)
    if "voltage" in state and "battery" in state:
        # voltage déjà dans metrics, laisser tel quel
        pass

    # -----------------------------------------------------------
    # Retour résultat
    # -----------------------------------------------------------

    return {
        "status": status,
        "detail": detail,
        "metrics": metrics,
    }


# ------------------------------------------------------------
# Helper pour actions (optionnel, pas utilisé par probe())
# ------------------------------------------------------------

def action_on(device: Dict[str, Any]) -> bool:
    """
    Envoie commande ON à un device Zigbee (switch/light).

    Args:
        device: Config device avec ip="zigbee:<friendly_name>"

    Returns:
        bool: True si commande envoyée, False sinon
    """
    if not MQTT_CLIENT_AVAILABLE:
        return False

    ip = device.get("ip", "")
    if not ip.startswith("zigbee:"):
        return False

    friendly_name = ip[7:]

    try:
        mqtt = get_mqtt_manager()
        return mqtt.publish_action(friendly_name, {"state": "ON"})
    except Exception as e:
        print(f"Zigbee action_on error: {e}")
        return False


def action_off(device: Dict[str, Any]) -> bool:
    """
    Envoie commande OFF à un device Zigbee (switch/light).

    Args:
        device: Config device avec ip="zigbee:<friendly_name>"

    Returns:
        bool: True si commande envoyée, False sinon
    """
    if not MQTT_CLIENT_AVAILABLE:
        return False

    ip = device.get("ip", "")
    if not ip.startswith("zigbee:"):
        return False

    friendly_name = ip[7:]

    try:
        mqtt = get_mqtt_manager()
        return mqtt.publish_action(friendly_name, {"state": "OFF"})
    except Exception as e:
        print(f"Zigbee action_off error: {e}")
        return False


def action_toggle(device: Dict[str, Any]) -> bool:
    """
    Toggle ON/OFF (lit état actuel puis inverse).

    Args:
        device: Config device avec ip="zigbee:<friendly_name>"

    Returns:
        bool: True si commande envoyée, False sinon
    """
    if not MQTT_CLIENT_AVAILABLE:
        return False

    ip = device.get("ip", "")
    if not ip.startswith("zigbee:"):
        return False

    friendly_name = ip[7:]

    try:
        mqtt = get_mqtt_manager()

        # Lire état actuel
        state = mqtt.get_device_state(friendly_name)
        if not state:
            return False

        current_state = state.get("state", "").upper()

        # Inverser
        new_state = "OFF" if current_state == "ON" else "ON"

        return mqtt.publish_action(friendly_name, {"state": new_state})
    except Exception as e:
        print(f"Zigbee action_toggle error: {e}")
        return False
