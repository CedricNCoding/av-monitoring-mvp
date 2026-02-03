# Guide d'Installation et Configuration Zigbee

## Vue d'Ensemble

Ce guide couvre l'installation complète de la stack Zigbee pour le projet AV Monitoring Agent :
- **Mosquitto** : Broker MQTT avec support TLS (optionnel, recommandé pour production)
- **Zigbee2MQTT** : Bridge entre dongle USB Zigbee et MQTT
- **Agent AV Monitoring** : Driver Zigbee intégré

**Mode par défaut :** L'installation configure MQTT en mode non-TLS sur port 1883 (localhost uniquement) pour faciliter la mise en route. Le mode TLS sur port 8883 reste disponible pour la production.

**Avantages Zigbee :**
- Capteurs sans fil (température, humidité, CO2, etc.)
- Actionneurs (prises, relais, éclairage)
- Faible consommation (batteries longue durée)
- Réseau maillé (auto-réparation)

---

## Prérequis

### Matériel
- **Dongle USB Zigbee** compatible Zigbee2MQTT :
  - Recommandé : ConBee II, Sonoff Zigbee 3.0 USB Dongle Plus, SLZB-06
  - Voir liste complète : https://www.zigbee2mqtt.io/guide/adapters/
- **Serveur Debian/Ubuntu** (bare-metal, pas Docker)
- **Accès root** sur le serveur

### Logiciel
- Debian 11+ ou Ubuntu 20.04+
- Agent AV Monitoring déjà installé
- Connexion Internet pour téléchargement packages

---

## Installation Rapide

### 1. Télécharger le script d'installation

```bash
cd /opt/avmonitoring-agent/scripts
# Le script est déjà présent si vous avez cloné le repo
ls -la install_zigbee_stack.sh
```

### 2. Rendre le script exécutable

```bash
chmod +x install_zigbee_stack.sh check_zigbee_stack.sh
```

### 3. Brancher le dongle USB Zigbee

```bash
# Vérifier détection
ls /dev/ttyUSB* /dev/ttyACM*
# Devrait afficher : /dev/ttyUSB0 ou /dev/ttyACM0
```

### 4. Exécuter l'installation

```bash
sudo ./install_zigbee_stack.sh
```

**Durée estimée :** 5-10 minutes

Le script va :
1. Installer Mosquitto + Node.js
2. Générer certificats TLS auto-signés (pour usage ultérieur optionnel)
3. Créer 3 users MQTT (admin, zigbee2mqtt, avmonitoring)
4. Installer Zigbee2MQTT depuis GitHub
5. Configurer Mosquitto (port 1883 non-TLS + port 8883 TLS)
6. Configurer et démarrer les services systemd
7. Ajouter variables MQTT dans `/etc/default/avmonitoring-agent`
8. Redémarrer l'agent

### 5. Valider l'installation

```bash
sudo ./check_zigbee_stack.sh
```

Devrait afficher :
```
✓ Tests réussis:   40+
⚠ Avertissements:  0-2
✗ Tests échoués:   0
```

---

## Installation Manuelle (Pas à Pas)

**Note :** Cette installation configure Mosquitto en mode dual-listener :
- **Port 1883** (non-TLS, localhost uniquement) : Mode par défaut, facile à démarrer
- **Port 8883** (TLS) : Mode production recommandé, certificats auto-signés générés

Zigbee2MQTT et l'agent utilisent le port 1883 par défaut. Pour passer en TLS, modifiez simplement les configurations pour utiliser le port 8883.

### Étape 1 : Installer Mosquitto

```bash
sudo apt-get update
sudo apt-get install -y mosquitto mosquitto-clients
sudo systemctl stop mosquitto  # On configure avant de démarrer
```

### Étape 2 : Installer Node.js LTS

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo bash -
sudo apt-get install -y nodejs

# Vérifier
node -v  # Devrait afficher v20.x
```

### Étape 3 : Générer certificats TLS

```bash
CERT_DIR="/etc/mosquitto/ca_certificates"
sudo mkdir -p "$CERT_DIR"

# CA
sudo openssl req -new -x509 -days 3650 -extensions v3_ca \
  -keyout "$CERT_DIR/ca.key" -out "$CERT_DIR/ca.crt" \
  -subj "/CN=AV-Monitoring-CA" -nodes

# Certificat serveur
sudo openssl genrsa -out "$CERT_DIR/server.key" 2048
sudo openssl req -new -out "$CERT_DIR/server.csr" \
  -key "$CERT_DIR/server.key" -subj "/CN=localhost"
sudo openssl x509 -req -in "$CERT_DIR/server.csr" \
  -CA "$CERT_DIR/ca.crt" -CAkey "$CERT_DIR/ca.key" \
  -CAcreateserial -out "$CERT_DIR/server.crt" -days 3650

# Permissions
sudo chmod 644 "$CERT_DIR"/{ca.crt,server.crt}
sudo chmod 600 "$CERT_DIR"/{ca.key,server.key}
sudo chown -R mosquitto:mosquitto "$CERT_DIR"
```

### Étape 4 : Configurer Mosquitto

```bash
sudo tee /etc/mosquitto/conf.d/zigbee.conf <<EOF
# Listener non-TLS (localhost uniquement, pour dev/debug)
listener 1883 127.0.0.1
protocol mqtt

# Listener TLS (production, recommandé)
listener 8883 127.0.0.1
protocol mqtt
certfile /etc/mosquitto/ca_certificates/server.crt
cafile /etc/mosquitto/ca_certificates/ca.crt
keyfile /etc/mosquitto/ca_certificates/server.key
require_certificate false
tls_version tlsv1.2

# Authentification obligatoire (tous listeners)
allow_anonymous false
password_file /etc/mosquitto/passwd
acl_file /etc/mosquitto/acl.conf

# Persistence
persistence true
persistence_location /var/lib/mosquitto/
EOF

# ACL
sudo tee /etc/mosquitto/acl.conf <<EOF
user admin
topic readwrite #

user zigbee2mqtt
topic readwrite zigbee2mqtt/#

user avmonitoring
topic read zigbee2mqtt/#
topic write zigbee2mqtt/+/set
topic write zigbee2mqtt/bridge/request/#
EOF

# Créer users
sudo mosquitto_passwd -c /etc/mosquitto/passwd admin
sudo mosquitto_passwd /etc/mosquitto/passwd zigbee2mqtt
sudo mosquitto_passwd /etc/mosquitto/passwd avmonitoring

sudo systemctl enable mosquitto
sudo systemctl restart mosquitto
```

### Étape 5 : Installer Zigbee2MQTT

```bash
# User système
sudo useradd --system --no-create-home --shell /usr/sbin/nologin zigbee2mqtt

# Clone repo
sudo git clone --depth 1 https://github.com/Koenkk/zigbee2mqtt.git /opt/zigbee2mqtt
cd /opt/zigbee2mqtt
sudo npm ci --production

# Répertoires
sudo mkdir -p /var/lib/zigbee2mqtt /var/log/zigbee2mqtt
sudo chown -R zigbee2mqtt:zigbee2mqtt /opt/zigbee2mqtt /var/lib/zigbee2mqtt /var/log/zigbee2mqtt
```

### Étape 6 : Configurer Zigbee2MQTT

```bash
sudo tee /var/lib/zigbee2mqtt/configuration.yaml <<EOF
homeassistant: false
permit_join: false

mqtt:
  base_topic: zigbee2mqtt
  server: mqtt://localhost:1883
  user: zigbee2mqtt
  password: VOTRE_MOT_DE_PASSE_ICI
  keepalive: 60
  version: 4

serial:
  port: /dev/ttyUSB0

advanced:
  log_level: info
  log_output:
    - console
    - file
  log_file: /var/log/zigbee2mqtt/zigbee2mqtt.log
  pan_id: GENERATE
  network_key: GENERATE
  channel: 11

frontend:
  port: 8080
  host: 127.0.0.1
EOF

sudo chown zigbee2mqtt:zigbee2mqtt /var/lib/zigbee2mqtt/configuration.yaml
sudo chmod 640 /var/lib/zigbee2mqtt/configuration.yaml
```

### Étape 7 : Service systemd Zigbee2MQTT

```bash
sudo tee /etc/systemd/system/zigbee2mqtt.service <<EOF
[Unit]
Description=Zigbee2MQTT
After=network.target mosquitto.service
Wants=mosquitto.service

[Service]
Type=simple
User=zigbee2mqtt
Group=zigbee2mqtt
WorkingDirectory=/opt/zigbee2mqtt
ExecStart=/usr/bin/node index.js
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable zigbee2mqtt
sudo systemctl start zigbee2mqtt
```

### Étape 8 : Configurer l'agent

```bash
# Ajouter variables MQTT (mode non-TLS par défaut)
sudo tee -a /etc/default/avmonitoring-agent <<EOF

# Zigbee/MQTT Configuration
AVMVP_MQTT_HOST=localhost
AVMVP_MQTT_PORT=1883
AVMVP_MQTT_USER=avmonitoring
AVMVP_MQTT_PASS=VOTRE_MOT_DE_PASSE_ICI
AVMVP_MQTT_BASE_TOPIC=zigbee2mqtt

# TLS optionnel (décommentez pour activer mode sécurisé sur port 8883)
# AVMVP_MQTT_PORT=8883
# AVMVP_MQTT_TLS_CA=/etc/mosquitto/ca_certificates/ca.crt
EOF

# Redémarrer agent
sudo systemctl restart avmonitoring-agent
```

---

## Utilisation

### 1. Pairer un appareil Zigbee

**Via l'interface web :**
1. Ouvrir `http://<ip-agent>:8080`
2. Aller dans section "Gestion Zigbee"
3. Cliquer sur "Activer jumelage (60 secondes)"
4. Appuyer sur le bouton de pairing de l'appareil Zigbee
5. L'appareil apparaît dans la liste

**Via ligne de commande :**
```bash
mosquitto_pub -h localhost -p 8883 \
  --cafile /etc/mosquitto/ca_certificates/ca.crt \
  -u avmonitoring -P 'password' \
  -t 'zigbee2mqtt/bridge/request/permit_join' \
  -m '{"value": true, "time": 60}'
```

### 2. Renommer un appareil

**Via l'interface web :**
1. Cliquer sur "Renommer" à côté de l'appareil
2. Entrer le nouveau nom (ex: `capteur_salle_101`)
3. Valider

**Via ligne de commande :**
```bash
mosquitto_pub -h localhost -p 8883 \
  --cafile /etc/mosquitto/ca_certificates/ca.crt \
  -u avmonitoring -P 'password' \
  -t 'zigbee2mqtt/bridge/request/device/rename' \
  -m '{"from": "0x00124b001f2e3a4b", "to": "capteur_salle_101"}'
```

### 3. Assigner à une salle

1. Cliquer sur "Assigner salle"
2. Renseigner : Bâtiment, Étage, Salle
3. L'appareil apparaît maintenant dans l'inventaire principal avec sa localisation

### 4. Surveiller l'état

**Logs Zigbee2MQTT :**
```bash
sudo journalctl -u zigbee2mqtt -f
```

**Logs agent (connexion MQTT) :**
```bash
sudo journalctl -u avmonitoring-agent -f | grep -i mqtt
```

**Tester connexion MQTT :**
```bash
source /root/zigbee_credentials.txt
mosquitto_sub -h localhost -p 8883 \
  --cafile /etc/mosquitto/ca_certificates/ca.crt \
  -u avmonitoring -P "$MQTT_PASS_AGENT" \
  -t 'zigbee2mqtt/#' -v
```

---

## Troubleshooting

### Problème : Mosquitto ne démarre pas

**Symptômes :**
```bash
sudo systemctl status mosquitto
# Active: failed
```

**Solutions :**
```bash
# Vérifier logs
sudo journalctl -u mosquitto -n 50

# Vérifier config
sudo mosquitto -c /etc/mosquitto/mosquitto.conf -v

# Vérifier certificats
ls -la /etc/mosquitto/ca_certificates/
sudo openssl x509 -in /etc/mosquitto/ca_certificates/ca.crt -noout -text
```

### Problème : Zigbee2MQTT ne démarre pas

**Symptômes :**
```bash
sudo systemctl status zigbee2mqtt
# Active: failed
```

**Solutions :**

1. **Vérifier dongle USB :**
```bash
ls -la /dev/ttyUSB* /dev/ttyACM*
# Si absent : brancher le dongle

# Vérifier permissions
sudo usermod -a -G dialout zigbee2mqtt
```

2. **Vérifier config MQTT :**
```bash
# Logs
sudo journalctl -u zigbee2mqtt -n 100

# Chercher "MQTT connected"
# Si absent : vérifier password dans configuration.yaml
```

3. **Tester MQTT manuellement :**
```bash
mosquitto_pub -h localhost -p 8883 \
  --cafile /etc/mosquitto/ca_certificates/ca.crt \
  -u zigbee2mqtt -P 'password_z2m' \
  -t 'test' -m 'hello'
```

### Problème : Agent ne se connecte pas à MQTT

**Symptômes :**
- Section Zigbee affiche "Déconnecté"
- Logs agent : "MQTT connection failed"

**Solutions :**
```bash
# Vérifier variables env
sudo systemctl show avmonitoring-agent | grep AVMVP_MQTT

# Vérifier fichier env
sudo cat /etc/default/avmonitoring-agent | grep MQTT

# Tester connexion manuellement (mode non-TLS)
source /etc/default/avmonitoring-agent
mosquitto_sub -h $AVMVP_MQTT_HOST -p ${AVMVP_MQTT_PORT:-1883} \
  -u $AVMVP_MQTT_USER -P "$AVMVP_MQTT_PASS" \
  -t '#' -C 1

# Ou si TLS activé (port 8883)
# mosquitto_sub -h $AVMVP_MQTT_HOST -p 8883 \
#   --cafile $AVMVP_MQTT_TLS_CA \
#   -u $AVMVP_MQTT_USER -P "$AVMVP_MQTT_PASS" \
#   -t '#' -C 1
```

### Problème : Appareils Zigbee offline

**Symptômes :**
- Statut "offline" dans UI
- last_seen > 60 min

**Causes possibles :**
1. **Batterie faible** : Vérifier niveau batterie (< 20% = critique)
2. **Hors de portée** : Distance max ~10-15m à travers murs
3. **Interférences** : WiFi 2.4GHz, micro-ondes, etc.
4. **Routeur Zigbee manquant** : Ajouter prises alimentées pour étendre le réseau

**Solutions :**
```bash
# Vérifier réseau Zigbee (mode non-TLS par défaut)
mosquitto_sub -h localhost -p 1883 \
  -u avmonitoring -P 'password' \
  -t 'zigbee2mqtt/bridge/devices' -C 1 | jq .

# Vérifier qualité signal (linkquality)
# < 50 = mauvais, > 100 = bon

# Ajouter routeur Zigbee (prise alimentée) entre coordinator et capteur
```

### Problème : Certificats TLS expirés

**Symptômes :**
- "Certificate verify failed"
- Connexion MQTT refusée

**Solution :**
```bash
# Vérifier expiration
sudo openssl x509 -in /etc/mosquitto/ca_certificates/ca.crt \
  -noout -dates

# Si expiré : regénérer (étape 3 installation manuelle)
```

---

## Commandes Utiles

### Status services

```bash
sudo systemctl status mosquitto
sudo systemctl status zigbee2mqtt
sudo systemctl status avmonitoring-agent
```

### Logs en temps réel

```bash
# Tout
sudo journalctl -f

# Mosquitto uniquement
sudo journalctl -u mosquitto -f

# Zigbee2MQTT uniquement
sudo journalctl -u zigbee2mqtt -f

# Agent uniquement
sudo journalctl -u avmonitoring-agent -f
```

### Lister appareils Zigbee

```bash
source /root/zigbee_credentials.txt
mosquitto_sub -h localhost -p 8883 \
  --cafile /etc/mosquitto/ca_certificates/ca.crt \
  -u avmonitoring -P "$MQTT_PASS_AGENT" \
  -t 'zigbee2mqtt/bridge/devices' -C 1 | jq .
```

### Redémarrer stack complète

```bash
sudo systemctl restart mosquitto
sudo systemctl restart zigbee2mqtt
sudo systemctl restart avmonitoring-agent
```

---

## Désinstallation

### Désinstallation propre (garde données)

```bash
cd /opt/avmonitoring-agent/scripts
sudo ./uninstall_zigbee_stack.sh
```

Le script demande confirmation avant de supprimer :
- Services (mosquitto, zigbee2mqtt)
- Configuration MQTT de l'agent
- Optionnel : données Zigbee (/var/lib/zigbee2mqtt)

### Désinstallation complète (supprime tout)

```bash
sudo systemctl stop mosquitto zigbee2mqtt
sudo apt-get remove --purge mosquitto mosquitto-clients
sudo rm -rf /opt/zigbee2mqtt /var/lib/zigbee2mqtt /var/log/zigbee2mqtt
sudo rm -rf /etc/mosquitto
sudo userdel zigbee2mqtt
```

---

## Conseils de Production

### 1. Certificats PKI (au lieu de self-signed)

Pour production, utiliser Let's Encrypt ou PKI interne :
```bash
# Exemple Let's Encrypt
sudo certbot certonly --standalone -d mqtt.example.com
sudo cp /etc/letsencrypt/live/mqtt.example.com/fullchain.pem \
  /etc/mosquitto/ca_certificates/server.crt
sudo cp /etc/letsencrypt/live/mqtt.example.com/privkey.pem \
  /etc/mosquitto/ca_certificates/server.key
```

### 2. Monitoring Mosquitto

```bash
# Installer Mosquitto stats plugin
sudo apt-get install mosquitto-dev

# Surveiller connexions actives
watch -n 5 'sudo systemctl status mosquitto'
```

### 3. Backup configuration Zigbee

```bash
# Sauvegarder réseau Zigbee (coordinator database)
sudo cp /var/lib/zigbee2mqtt/database.db \
  /backup/zigbee2mqtt-db-$(date +%Y%m%d).db

# Planifier sauvegarde automatique
sudo crontab -e
# Ajouter : 0 2 * * * cp /var/lib/zigbee2mqtt/database.db ...
```

### 4. Limites systemd (CPU/Mémoire)

```bash
sudo systemctl edit zigbee2mqtt

# Ajouter :
[Service]
MemoryLimit=512M
CPUQuota=50%
```

---

## Support

### Ressources officielles

- **Zigbee2MQTT** : https://www.zigbee2mqtt.io/
- **Mosquitto** : https://mosquitto.org/documentation/
- **Compatibilité dongles** : https://www.zigbee2mqtt.io/guide/adapters/

### Logs de debug

Si problème persistant, collecter :
```bash
sudo journalctl -u mosquitto -n 200 --no-pager > /tmp/mosquitto.log
sudo journalctl -u zigbee2mqtt -n 200 --no-pager > /tmp/zigbee2mqtt.log
sudo journalctl -u avmonitoring-agent -n 200 --no-pager > /tmp/agent.log
sudo ./check_zigbee_stack.sh > /tmp/validation.log 2>&1
```

Puis envoyer les 4 fichiers `/tmp/*.log` pour analyse.
