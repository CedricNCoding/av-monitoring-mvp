# agent/src/mqtt_client.py
"""
Client MQTT singleton pour communication avec Zigbee2MQTT.

Architecture:
- Un seul client MQTT pour tous les devices Zigbee (singleton pattern)
- Thread background pour message loop (paho.mqtt)
- Cache d'état thread-safe avec TTL 5 min
- Reconnexion automatique avec backoff exponentiel
- TLS mandatory (pas de fallback en clair)

Usage:
    from src.mqtt_client import get_mqtt_manager
    mqtt = get_mqtt_manager()
    state = mqtt.get_device_state("living_room_sensor")
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    print("WARNING: paho-mqtt not installed. Zigbee support disabled.")


class MQTTClientManager:
    """
    Gestionnaire singleton pour client MQTT Zigbee2MQTT.

    Thread-safe, auto-reconnect, état en cache.
    """

    _instance: Optional[MQTTClientManager] = None
    _lock_instance = threading.Lock()

    def __init__(self):
        """
        Initialisation (appelé une seule fois via get_instance()).
        """
        if not MQTT_AVAILABLE:
            self._client = None
            self._connected = False
            self._configured = False
            self._last_error = "paho-mqtt not installed"
            return

        self._client: Optional[mqtt.Client] = None
        self._state_cache: Dict[str, Dict[str, Any]] = {}
        self._bridge_devices: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._connected = False
        self._thread: Optional[threading.Thread] = None
        self._reconnect_delay = 5  # secondes
        self._stop_flag = False
        self._connection_attempted = False
        self._last_message_time: Optional[float] = None
        self._last_connect_ts: Optional[float] = None
        self._last_error: Optional[str] = None
        self._configured = False  # True si env vars présentes

        # Check configuration at init (don't connect yet)
        self._check_configuration()

    def _check_configuration(self):
        """
        Vérifie si les variables d'environnement MQTT sont présentes.
        Log la configuration sans connecter.
        """
        host = os.getenv("AVMVP_MQTT_HOST")
        port = os.getenv("AVMVP_MQTT_PORT")
        user = os.getenv("AVMVP_MQTT_USER")
        password = os.getenv("AVMVP_MQTT_PASS")
        ca_path = os.getenv("AVMVP_MQTT_TLS_CA")
        base_topic = os.getenv("AVMVP_MQTT_BASE_TOPIC", "zigbee2mqtt")

        if not user or not password:
            print("MQTT configured: no (missing AVMVP_MQTT_USER or AVMVP_MQTT_PASS)")
            self._configured = False
            self._last_error = "Missing credentials (AVMVP_MQTT_USER or AVMVP_MQTT_PASS)"
            return

        if not ca_path or not os.path.exists(ca_path):
            print(f"MQTT configured: no (CA certificate not found: {ca_path})")
            self._configured = False
            self._last_error = f"CA certificate not found: {ca_path}"
            return

        # Configuration valide
        self._configured = True
        print("MQTT configured: yes")
        print(f"  Host: {host or 'localhost'}:{port or '8883'}")
        print(f"  User: {user}")
        print(f"  Base topic: {base_topic}")
        print(f"  CA cert: {ca_path}")
        print("  (Connection will be attempted on first use or via init_connection())")

    @classmethod
    def get_instance(cls) -> MQTTClientManager:
        """
        Récupère l'instance singleton (thread-safe).
        """
        if cls._instance is None:
            with cls._lock_instance:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _ensure_connected(self) -> bool:
        """
        S'assure que la connexion MQTT est établie (lazy init).

        Returns:
            bool: True si connecté, False sinon
        """
        if not MQTT_AVAILABLE:
            return False

        if self._connected and self._client is not None:
            return True

        if self._connection_attempted:
            # Déjà tenté, échec, pas de retry immédiat
            return False

        # Première tentative de connexion
        return self.connect()

    def connect(self) -> bool:
        """
        Initialise la connexion MQTT TLS.

        Lit les variables d'environnement:
        - AVMVP_MQTT_HOST (default: localhost)
        - AVMVP_MQTT_PORT (default: 8883)
        - AVMVP_MQTT_USER (obligatoire)
        - AVMVP_MQTT_PASS (obligatoire)
        - AVMVP_MQTT_TLS_CA (obligatoire)
        - AVMVP_MQTT_BASE_TOPIC (default: zigbee2mqtt)

        Returns:
            bool: True si connexion réussie, False sinon
        """
        if not MQTT_AVAILABLE:
            return False

        self._connection_attempted = True

        # Lecture env vars
        host = os.getenv("AVMVP_MQTT_HOST", "localhost")
        port_str = os.getenv("AVMVP_MQTT_PORT", "8883")
        user = os.getenv("AVMVP_MQTT_USER")
        password = os.getenv("AVMVP_MQTT_PASS")
        ca_path = os.getenv("AVMVP_MQTT_TLS_CA")
        self._base_topic = os.getenv("AVMVP_MQTT_BASE_TOPIC", "zigbee2mqtt")

        try:
            port = int(port_str)
        except ValueError:
            print(f"MQTT: Invalid port '{port_str}', using default 8883")
            port = 8883

        # Validation credentials
        if not user or not password:
            print("MQTT: Missing credentials (AVMVP_MQTT_USER or AVMVP_MQTT_PASS)")
            return False

        if not ca_path or not os.path.exists(ca_path):
            print(f"MQTT: CA certificate not found ({ca_path})")
            return False

        try:
            # Créer client paho
            self._client = mqtt.Client(client_id="avmonitoring-agent")

            # Authentification
            self._client.username_pw_set(user, password)

            # TLS (mandatory)
            self._client.tls_set(ca_certs=ca_path)

            # Callbacks
            self._client.on_connect = self._on_connect
            self._client.on_message = self._on_message
            self._client.on_disconnect = self._on_disconnect

            # Connexion
            self._client.connect(host, port, keepalive=60)

            # Démarrer thread background
            self._stop_flag = False
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

            print(f"MQTT: Connecting to {host}:{port} (TLS)...")
            self._last_connect_ts = time.time()
            self._last_error = None  # Clear previous errors
            return True

        except Exception as e:
            error_msg = f"Connection failed: {e}"
            print(f"MQTT: {error_msg}")
            self._connected = False
            self._client = None
            self._last_error = error_msg
            return False

    def _loop(self):
        """
        Boucle background pour traiter messages MQTT.

        Gère reconnexion automatique avec backoff exponentiel.
        """
        if not self._client:
            return

        while not self._stop_flag:
            try:
                rc = self._client.loop(timeout=1.0)
                if rc != 0:
                    # Erreur dans loop, attendre avant retry
                    time.sleep(self._reconnect_delay)
                    self._reconnect_delay = min(60, self._reconnect_delay * 2)
            except Exception as e:
                print(f"MQTT: Loop error: {e}")
                time.sleep(self._reconnect_delay)
                self._reconnect_delay = min(60, self._reconnect_delay * 2)

    def _on_connect(self, client, userdata, flags, rc):
        """
        Callback paho: connexion établie.
        """
        if rc == 0:
            self._connected = True
            self._reconnect_delay = 5  # Reset backoff
            self._last_connect_ts = time.time()
            self._last_error = None
            print("MQTT connect OK")

            # Subscribe à tous les topics Zigbee2MQTT
            client.subscribe(f"{self._base_topic}/#")
            print(f"MQTT: Subscribed to {self._base_topic}/#")
        else:
            self._connected = False
            error_msg = {
                1: "Connection refused - incorrect protocol version",
                2: "Connection refused - invalid client identifier",
                3: "Connection refused - server unavailable",
                4: "Connection refused - bad username or password",
                5: "Connection refused - not authorized"
            }.get(rc, f"Connection refused - code {rc}")
            self._last_error = error_msg
            print(f"MQTT: {error_msg}")

    def _on_message(self, client, userdata, msg):
        """
        Callback paho: message reçu.

        Parse les topics:
        - zigbee2mqtt/<friendly_name> → état device
        - zigbee2mqtt/bridge/devices → liste complète devices
        - zigbee2mqtt/bridge/state → état broker
        """
        try:
            topic = msg.topic
            payload_raw = msg.payload.decode("utf-8")

            # Ignorer topics non-JSON
            if not payload_raw or payload_raw[0] not in ['{', '[']:
                return

            payload = json.loads(payload_raw)

            self._last_message_time = time.time()

            # Topic: bridge/devices (liste complète)
            if topic == f"{self._base_topic}/bridge/devices":
                with self._lock:
                    self._bridge_devices = payload
                print(f"MQTT: Received bridge/devices ({len(payload)} devices)")

            # Topic: device state (zigbee2mqtt/<friendly_name>)
            elif topic.startswith(f"{self._base_topic}/") and "/" not in topic[len(self._base_topic)+1:]:
                friendly_name = topic[len(self._base_topic)+1:]

                # Ignorer topics spéciaux
                if friendly_name in ["bridge", "coordinator"]:
                    return

                # Stocker état dans cache
                with self._lock:
                    key = f"zigbee:{friendly_name}"
                    self._state_cache[key] = {
                        **payload,
                        "friendly_name": friendly_name,
                        "cached_at": time.time()
                    }

            # Topic: bridge/state (online/offline)
            elif topic == f"{self._base_topic}/bridge/state":
                state = payload.get("state", "unknown")
                print(f"MQTT: Zigbee2MQTT bridge state: {state}")

        except json.JSONDecodeError:
            # Payload non-JSON, ignorer
            pass
        except Exception as e:
            print(f"MQTT: Message parsing error: {e}")

    def _on_disconnect(self, client, userdata, rc):
        """
        Callback paho: déconnexion.
        """
        self._connected = False
        if rc != 0:
            print(f"MQTT: Unexpected disconnection (code {rc}), will retry...")

    def is_connected(self) -> bool:
        """
        Vérifie si le client MQTT est connecté.

        Returns:
            bool: True si connecté
        """
        if not MQTT_AVAILABLE:
            return False
        return self._connected

    def get_device_state(self, friendly_name: str) -> Optional[Dict[str, Any]]:
        """
        Récupère l'état d'un device depuis le cache (thread-safe).

        Args:
            friendly_name: Nom du device (ex: "living_room_sensor")

        Returns:
            Dict avec état du device, ou None si absent/stale
            Champs possibles:
            - last_seen: ISO timestamp
            - battery: 0-100
            - linkquality: 0-255
            - temperature, humidity, co2, etc.
            - state: "ON" ou "OFF" (pour switches)
            - cached_at: timestamp cache
            - stale: True si cache expiré (> 5 min)
        """
        if not MQTT_AVAILABLE:
            return None

        # Lazy connect
        if not self._ensure_connected():
            return None

        try:
            with self._lock:
                key = f"zigbee:{friendly_name}" if not friendly_name.startswith("zigbee:") else friendly_name
                state = self._state_cache.get(key)

                if not state:
                    return None

                # Vérifier TTL (5 min = 300s)
                age = time.time() - state.get("cached_at", 0)
                if age > 300:
                    # Cache expiré mais on retourne quand même (stale data > no data)
                    state["stale"] = True
                    state["cache_age_seconds"] = int(age)

                return dict(state)  # Copie défensive

        except Exception as e:
            print(f"MQTT: Cache read error: {e}")
            return None

    def get_all_devices(self) -> List[Dict[str, Any]]:
        """
        Récupère la liste complète des devices Zigbee depuis bridge/devices.

        Returns:
            List de dicts avec infos devices:
            - friendly_name
            - ieee_address
            - type (ex: "Router", "EndDevice")
            - model_id
            - manufacturer
            - supported (bool)
        """
        if not MQTT_AVAILABLE:
            return []

        if not self._ensure_connected():
            return []

        try:
            with self._lock:
                return list(self._bridge_devices)  # Copie défensive
        except Exception as e:
            print(f"MQTT: Error reading bridge devices: {e}")
            return []

    def publish_action(self, friendly_name: str, action: Dict[str, Any]) -> bool:
        """
        Publie une action sur un device (ex: ON/OFF).

        Args:
            friendly_name: Nom du device
            action: Dict avec commande, ex: {"state": "ON"}

        Returns:
            bool: True si publish réussi (note: pas de confirmation Z2M en V1)
        """
        if not MQTT_AVAILABLE:
            return False

        if not self._ensure_connected():
            return False

        if not self._client:
            return False

        try:
            topic = f"{self._base_topic}/{friendly_name}/set"
            payload = json.dumps(action)
            self._client.publish(topic, payload)
            print(f"MQTT: Published to {topic}: {payload}")
            return True
        except Exception as e:
            print(f"MQTT: Publish error: {e}")
            return False

    def permit_join(self, duration: int = 60) -> bool:
        """
        Active le mode pairing Zigbee (permit_join).

        Args:
            duration: Durée en secondes (default: 60)

        Returns:
            bool: True si commande envoyée
        """
        if not MQTT_AVAILABLE:
            return False

        if not self._ensure_connected():
            return False

        if not self._client:
            return False

        try:
            topic = f"{self._base_topic}/bridge/request/permit_join"
            payload = json.dumps({"value": True, "time": duration})
            self._client.publish(topic, payload)
            print(f"MQTT: Permit join enabled for {duration}s")
            return True
        except Exception as e:
            print(f"MQTT: Permit join error: {e}")
            return False

    def rename_device(self, old_name: str, new_name: str) -> bool:
        """
        Renomme un device Zigbee (via Z2M bridge).

        Args:
            old_name: Ancien friendly_name
            new_name: Nouveau friendly_name

        Returns:
            bool: True si commande envoyée
        """
        if not MQTT_AVAILABLE:
            return False

        if not self._ensure_connected():
            return False

        if not self._client:
            return False

        try:
            topic = f"{self._base_topic}/bridge/request/device/rename"
            payload = json.dumps({"from": old_name, "to": new_name})
            self._client.publish(topic, payload)
            print(f"MQTT: Rename device {old_name} → {new_name}")
            return True
        except Exception as e:
            print(f"MQTT: Rename error: {e}")
            return False

    def remove_device(self, ieee_address: str, force: bool = False) -> bool:
        """
        Supprime un device du réseau Zigbee.

        Args:
            ieee_address: Adresse IEEE du device (ex: "0x00124b001f2e3a4b")
            force: Force la suppression même si device injoignable

        Returns:
            bool: True si commande envoyée
        """
        if not MQTT_AVAILABLE:
            return False

        if not self._ensure_connected():
            return False

        if not self._client:
            return False

        try:
            topic = f"{self._base_topic}/bridge/request/device/remove"
            payload = json.dumps({"id": ieee_address, "force": force})
            self._client.publish(topic, payload)
            print(f"MQTT: Remove device {ieee_address} (force={force})")
            return True
        except Exception as e:
            print(f"MQTT: Remove error: {e}")
            return False

    def get_last_message_time(self) -> Optional[float]:
        """
        Retourne le timestamp du dernier message MQTT reçu.

        Utile pour diagnostiquer connexion stale.

        Returns:
            float: timestamp Unix, ou None si aucun message reçu
        """
        return self._last_message_time

    def init_connection(self) -> bool:
        """
        Initialise la connexion MQTT de manière non-bloquante.

        Utilisé au démarrage de l'application pour tenter de se connecter
        immédiatement (au lieu d'attendre le premier probe()).

        Returns:
            bool: True si connexion démarrée (pas forcément connecté yet)
        """
        if not self._configured:
            print("MQTT: Not configured, skipping connection")
            return False

        if self._connected:
            print("MQTT: Already connected")
            return True

        if self._connection_attempted:
            print("MQTT: Connection already attempted (check logs for errors)")
            return False

        print("MQTT: Initiating connection at startup...")
        return self.connect()

    def get_health(self) -> Dict[str, Any]:
        """
        Retourne l'état de santé MQTT pour monitoring.

        Returns:
            Dict avec:
            - configured: bool (env vars présentes)
            - connected: bool (actuellement connecté)
            - last_connect_ts: float|None (timestamp dernière connexion réussie)
            - last_error: str|None (dernière erreur rencontrée)
            - last_message_ts: float|None (timestamp dernier message reçu)
            - devices_in_cache: int (nombre de devices en cache)
        """
        with self._lock:
            return {
                "configured": self._configured,
                "connected": self._connected,
                "last_connect_ts": self._last_connect_ts,
                "last_error": self._last_error,
                "last_message_ts": self._last_message_time,
                "devices_in_cache": len(self._state_cache),
                "mqtt_available": MQTT_AVAILABLE
            }

    def stop(self):
        """
        Arrête le client MQTT (ferme connexion, arrête thread).

        Utilisé uniquement pour tests ou shutdown propre.
        """
        if not MQTT_AVAILABLE:
            return

        self._stop_flag = True
        if self._client:
            self._client.disconnect()
            self._client.loop_stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        print("MQTT: Client stopped")


# ------------------------------------------------------------
# Helper function pour accès global
# ------------------------------------------------------------

def get_mqtt_manager() -> MQTTClientManager:
    """
    Récupère l'instance singleton du gestionnaire MQTT.

    Usage:
        from src.mqtt_client import get_mqtt_manager
        mqtt = get_mqtt_manager()
        if mqtt.is_connected():
            state = mqtt.get_device_state("living_room_sensor")
    """
    return MQTTClientManager.get_instance()
