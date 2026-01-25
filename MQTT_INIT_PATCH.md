# Patch MQTT - Connexion au Démarrage de l'Agent

## Résumé

Ce patch active la connexion MQTT au démarrage de l'agent avmonitoring, avec logging détaillé et endpoint de monitoring `/mqtt/health`.

**Objectifs atteints :**
1. ✅ Log de configuration MQTT au startup (host/port/user/ca_path, jamais le password)
2. ✅ Tentative de connexion MQTT au démarrage (non-bloquante)
3. ✅ Endpoint GET `/mqtt/health` retournant l'état MQTT
4. ✅ Aucun blocage du collector si MQTT down (déjà garanti par lazy init)

---

## Modifications Apportées

### 1. `agent/src/mqtt_client.py`

#### A. Ajout de variables d'état
```python
# Dans __init__():
self._last_connect_ts: Optional[float] = None  # Timestamp dernière connexion réussie
self._last_error: Optional[str] = None          # Dernière erreur rencontrée
self._configured = False                        # True si env vars présentes

# Appel nouvelle méthode
self._check_configuration()
```

#### B. Nouvelle méthode `_check_configuration()`
```python
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
        self._last_error = "Missing credentials"
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
```

**Sortie au démarrage (si configuré) :**
```
MQTT configured: yes
  Host: localhost:8883
  User: avmonitoring
  Base topic: zigbee2mqtt
  CA cert: /etc/mosquitto/ca_certificates/ca.crt
  (Connection will be attempted on first use or via init_connection())
```

#### C. Modification de `connect()` pour tracer erreurs
```python
# Dans connect():
self._last_connect_ts = time.time()
self._last_error = None  # Clear previous errors

# Dans catch Exception:
error_msg = f"Connection failed: {e}"
self._last_error = error_msg
```

#### D. Modification de `_on_connect()` pour logger succès
```python
def _on_connect(self, client, userdata, flags, rc):
    if rc == 0:
        self._connected = True
        self._reconnect_delay = 5
        self._last_connect_ts = time.time()
        self._last_error = None
        print("MQTT connect OK")  # ← Log succès

        client.subscribe(f"{self._base_topic}/#")
        print(f"MQTT: Subscribed to {self._base_topic}/#")
    else:
        # ... gestion erreurs
        self._last_error = error_msg
```

#### E. Nouvelle méthode `init_connection()`
```python
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
```

#### F. Nouvelle méthode `get_health()`
```python
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
```

---

### 2. `agent/src/webapp.py`

#### A. Modification du `startup_event` existant
```python
@app.on_event("startup")
def startup_event():
    """
    Démarre automatiquement le thread de synchronisation ET le collector au démarrage de l'app.
    """
    # ... code existant sync + collector ...

    # ← AJOUT : Initialiser connexion MQTT (non-bloquant)
    try:
        from src.mqtt_client import get_mqtt_manager
        mqtt = get_mqtt_manager()
        mqtt.init_connection()
    except Exception as e:
        print(f"⚠️  MQTT initialization failed: {e}")
```

**Sortie au démarrage (si succès) :**
```
MQTT configured: yes
  Host: localhost:8883
  User: avmonitoring
  Base topic: zigbee2mqtt
  CA cert: /etc/mosquitto/ca_certificates/ca.crt
MQTT: Initiating connection at startup...
MQTT: Connecting to localhost:8883 (TLS)...
MQTT connect OK
MQTT: Subscribed to zigbee2mqtt/#
```

#### B. Nouvel endpoint `/mqtt/health`
```python
@app.get("/mqtt/health")
def mqtt_health():
    """
    Retourne l'état de santé de la connexion MQTT.

    Returns:
        JSON avec:
        - configured: bool (env vars présentes)
        - connected: bool (actuellement connecté)
        - last_connect_ts: float|None
        - last_error: str|None
        - last_message_ts: float|None
        - devices_in_cache: int
    """
    try:
        from src.mqtt_client import get_mqtt_manager
        mqtt = get_mqtt_manager()
        return mqtt.get_health()
    except Exception as e:
        return {
            "configured": False,
            "connected": False,
            "last_connect_ts": None,
            "last_error": f"Failed to get MQTT health: {e}",
            "last_message_ts": None,
            "devices_in_cache": 0,
            "mqtt_available": False
        }
```

---

## Commandes de Test

### 1. Restart Agent et Observer Logs

```bash
# Sur le serveur où l'agent tourne
sudo systemctl restart avmonitoring-agent
sudo journalctl -u avmonitoring-agent -f --no-pager
```

**Attendu dans logs (si MQTT configuré) :**
```
MQTT configured: yes
  Host: localhost:8883
  User: avmonitoring
  Base topic: zigbee2mqtt
  CA cert: /etc/mosquitto/ca_certificates/ca.crt
MQTT: Initiating connection at startup...
MQTT: Connecting to localhost:8883 (TLS)...
MQTT connect OK
MQTT: Subscribed to zigbee2mqtt/#
✅ Collector started successfully
```

**Si MQTT non configuré :**
```
MQTT configured: no (missing AVMVP_MQTT_USER or AVMVP_MQTT_PASS)
```

**Si erreur de connexion :**
```
MQTT configured: yes
  Host: localhost:8883
  User: avmonitoring
  ...
MQTT: Initiating connection at startup...
MQTT: Connecting to localhost:8883 (TLS)...
MQTT: Connection failed: [Errno 111] Connection refused
⚠️  MQTT initialization failed: ...
✅ Collector started successfully  # ← Collector continue quand même
```

### 2. Vérifier Connexion MQTT côté Mosquitto

```bash
# Voir logs Mosquitto pour connexion user 'avmonitoring'
sudo journalctl -u mosquitto -f --no-pager | grep "u'avmonitoring'"
```

**Attendu (si connexion OK) :**
```
New connection from ::1:XXXXX on port 8883.
New client connected from ::1:XXXXX as avmonitoring-agent (p5, c1, k60, u'avmonitoring').
```

### 3. Tester Endpoint `/mqtt/health`

```bash
# Depuis n'importe quelle machine pouvant accéder à l'agent
curl -s http://<agent-ip>:8080/mqtt/health | jq .
```

**Attendu (si connecté) :**
```json
{
  "configured": true,
  "connected": true,
  "last_connect_ts": 1737849123.456,
  "last_error": null,
  "last_message_ts": 1737849125.789,
  "devices_in_cache": 3,
  "mqtt_available": true
}
```

**Si erreur de connexion :**
```json
{
  "configured": true,
  "connected": false,
  "last_connect_ts": null,
  "last_error": "Connection failed: [Errno 111] Connection refused",
  "last_message_ts": null,
  "devices_in_cache": 0,
  "mqtt_available": true
}
```

**Si non configuré :**
```json
{
  "configured": false,
  "connected": false,
  "last_connect_ts": null,
  "last_error": "Missing credentials (AVMVP_MQTT_USER or AVMVP_MQTT_PASS)",
  "last_message_ts": null,
  "devices_in_cache": 0,
  "mqtt_available": true
}
```

### 4. Tester Robustesse : MQTT Down

```bash
# Arrêter Mosquitto
sudo systemctl stop mosquitto

# Attendre quelques secondes, puis vérifier endpoint health
curl -s http://<agent-ip>:8080/mqtt/health | jq .

# Vérifier que le collector continue de tourner
curl -s http://<agent-ip>:8080/ | grep "Collector"
```

**Attendu :**
- `/mqtt/health` retourne `connected: false` avec erreur
- Page principale affiche toujours le collector actif
- Devices ping/snmp/pjlink continuent d'être collectés (vérifier logs)

### 5. Test Pub/Sub Manuel (validation complète)

```bash
# Charger credentials
source /root/zigbee_credentials.txt

# Terminal 1 : Subscribe
mosquitto_sub -h localhost -p 8883 \
  --cafile /etc/mosquitto/ca_certificates/ca.crt \
  -u avmonitoring -P "$MQTT_PASS_AGENT" \
  -t 'avmvp/health/test' -v

# Terminal 2 : Publish
mosquitto_pub -h localhost -p 8883 \
  --cafile /etc/mosquitto/ca_certificates/ca.crt \
  -u avmonitoring -P "$MQTT_PASS_AGENT" \
  -t 'avmvp/health/test' -m 'agent_alive'
```

**Attendu Terminal 1 :**
```
avmvp/health/test agent_alive
```

**Attendu dans logs Mosquitto :**
```
New client connected from ::1:XXXXX as avmonitoring-agent (p5, c1, k60, u'avmonitoring').
```

---

## Validation de Non-Régression

### Test 1 : Agent sans MQTT configuré
```bash
# Retirer variables MQTT de /etc/default/avmonitoring-agent
sudo sed -i 's/^AVMVP_MQTT/#AVMVP_MQTT/g' /etc/default/avmonitoring-agent

# Redémarrer
sudo systemctl restart avmonitoring-agent

# Vérifier logs
sudo journalctl -u avmonitoring-agent -n 50 --no-pager
```

**Attendu :**
- Log "MQTT configured: no"
- Collector démarre quand même
- Pas d'erreur fatale

### Test 2 : MQTT configuré mais Mosquitto down
```bash
# Arrêter Mosquitto
sudo systemctl stop mosquitto

# Redémarrer agent
sudo systemctl restart avmonitoring-agent

# Vérifier logs
sudo journalctl -u avmonitoring-agent -n 50 --no-pager
```

**Attendu :**
- Log "MQTT configured: yes"
- Log "MQTT: Connection failed: [Errno 111] Connection refused"
- Collector démarre quand même
- Pas de crash

### Test 3 : Devices ping/snmp/pjlink non impactés
```bash
# Avec MQTT down ou non configuré
sudo systemctl restart avmonitoring-agent

# Attendre 1 cycle de collecte (5 min par défaut)
sleep 300

# Vérifier que devices non-zigbee sont toujours collectés
sudo journalctl -u avmonitoring-agent -n 200 --no-pager | grep "Ingesting"
```

**Attendu :**
- Log "Ingesting X observations" présent
- Devices ping/snmp/pjlink dans les résultats

---

## Troubleshooting

### Problème : "MQTT configured: no" malgré env vars présentes

**Diagnostic :**
```bash
# Vérifier que /etc/default/avmonitoring-agent est bien sourcé
sudo systemctl cat avmonitoring-agent | grep EnvironmentFile

# Vérifier contenu
sudo cat /etc/default/avmonitoring-agent | grep AVMVP_MQTT

# Vérifier que les lignes ne sont pas commentées
sudo grep "^AVMVP_MQTT" /etc/default/avmonitoring-agent
```

**Solution :**
```bash
# Décommenter les lignes
sudo sed -i 's/^#AVMVP_MQTT/AVMVP_MQTT/g' /etc/default/avmonitoring-agent

# Reload systemd + restart
sudo systemctl daemon-reload
sudo systemctl restart avmonitoring-agent
```

### Problème : "Connection failed: [Errno 111] Connection refused"

**Diagnostic :**
```bash
# Vérifier que Mosquitto écoute sur 8883
ss -tln | grep 8883

# Vérifier service Mosquitto
sudo systemctl status mosquitto
```

**Solution :**
```bash
# Démarrer Mosquitto si arrêté
sudo systemctl start mosquitto

# Tester connexion manuelle
source /root/zigbee_credentials.txt
mosquitto_pub -h localhost -p 8883 \
  --cafile /etc/mosquitto/ca_certificates/ca.crt \
  -u avmonitoring -P "$MQTT_PASS_AGENT" \
  -t 'test' -m 'ok'
```

### Problème : "Connection refused - bad username or password"

**Diagnostic :**
```bash
# Vérifier que user avmonitoring existe dans passwd file
sudo grep "^avmonitoring:" /etc/mosquitto/passwd

# Vérifier que password dans env vars correspond
source /root/zigbee_credentials.txt
echo "MQTT_PASS_AGENT=$MQTT_PASS_AGENT"
```

**Solution :**
```bash
# Recréer le password
source /root/zigbee_credentials.txt
sudo mosquitto_passwd -b /etc/mosquitto/passwd avmonitoring "$MQTT_PASS_AGENT"

# Redémarrer Mosquitto
sudo systemctl restart mosquitto

# Relancer agent
sudo systemctl restart avmonitoring-agent
```

---

## Résumé des Garanties

✅ **Logging au startup** : Configuration MQTT loggée (host/port/user/ca_path)
✅ **Connexion non-bloquante** : Tentative de connexion MQTT au démarrage, n'empêche pas le démarrage du collector
✅ **Endpoint de monitoring** : GET `/mqtt/health` retourne état détaillé
✅ **Isolation collector** : Si MQTT down, le collector continue de fonctionner (ping/snmp/pjlink)
✅ **Logs succès** : "MQTT connect OK" affiché en cas de connexion réussie
✅ **Logs erreur** : Erreurs MQTT loggées avec WARNING (pas FATAL)
✅ **Monitoring Mosquitto** : Logs Mosquitto montrent "New client ... u'avmonitoring'" si connexion OK

---

## Fichiers Modifiés

1. **agent/src/mqtt_client.py**
   - Ajout `_last_connect_ts`, `_last_error`, `_configured`
   - Ajout `_check_configuration()` pour logging config
   - Ajout `init_connection()` pour connexion explicite au startup
   - Ajout `get_health()` pour endpoint monitoring
   - Modification `connect()` et `_on_connect()` pour tracer erreurs/succès

2. **agent/src/webapp.py**
   - Modification `startup_event()` pour appeler `mqtt.init_connection()`
   - Ajout endpoint `GET /mqtt/health`

**Aucune modification dans :**
- `src/collector.py` (isolation déjà garantie par lazy init)
- `src/drivers/zigbee.py` (utilise déjà mqtt_client via lazy init)

---

## Déploiement

```bash
# Sur le serveur agent
cd /opt/avmonitoring-agent

# Backup avant patch
sudo cp agent/src/mqtt_client.py agent/src/mqtt_client.py.bak
sudo cp agent/src/webapp.py agent/src/webapp.py.bak

# Appliquer le patch (déjà fait via modifications manuelles)

# Redémarrer agent
sudo systemctl restart avmonitoring-agent

# Vérifier logs
sudo journalctl -u avmonitoring-agent -f --no-pager

# Tester endpoint health
curl -s http://localhost:8080/mqtt/health | jq .

# Vérifier connexion Mosquitto
sudo journalctl -u mosquitto | grep "u'avmonitoring'"
```

---

**Date du patch :** $(date +%Y-%m-%d)
**Version Agent :** AV Monitoring MVP
**Fichiers patchés :**
- `/opt/avmonitoring-agent/agent/src/mqtt_client.py`
- `/opt/avmonitoring-agent/agent/src/webapp.py`
