# Guide d'Installation : Agent AV Monitoring + Stack Zigbee

## 📋 Vue d'Ensemble

Ce guide décrit l'installation complète d'un agent AV Monitoring avec support Zigbee sur une machine Debian/Ubuntu neuve.

**Durée estimée :** 15-20 minutes

**Prérequis :**
- Machine Debian 11/12 ou Ubuntu 20.04/22.04/24.04
- Accès root (sudo)
- Connexion Internet
- Dongle Zigbee USB (si support Zigbee souhaité)

---

## 🎯 Architecture Déployée

```
┌─────────────────────────────────────────┐
│  Backend AV Monitoring (cloud/on-prem)  │
└────────────────┬────────────────────────┘
                 │ HTTPS
                 ↓
┌─────────────────────────────────────────┐
│         Agent AV Monitoring              │
│  - Collecte ping/SNMP/PJLink            │
│  - Collecte Zigbee (via MQTT)           │
│  - WebUI locale :8080                   │
└───────┬─────────────────────────────────┘
        │ MQTT TLS (localhost:8883)
        ↓
┌─────────────────────────────────────────┐
│  Stack Zigbee (optionnel)               │
│  - Mosquitto (broker MQTT)              │
│  - Zigbee2MQTT (bridge USB→MQTT)        │
│  - Dongle USB Zigbee                    │
└─────────────────────────────────────────┘
```

---

## 📦 Étape 1 : Installation de Base

### 1.1 Préparer le Système

```bash
# Se connecter en SSH à la machine cible
ssh user@agent-host

# Passer root
sudo -i

# Mettre à jour le système
apt update && apt upgrade -y

# Installer dépendances de base
apt install -y git python3 python3-pip python3-venv curl wget net-tools
```

### 1.2 Créer l'Utilisateur Agent

```bash
# Créer utilisateur système pour l'agent
useradd -r -s /bin/bash -d /opt/avmonitoring-agent -m avmonitoring

# Ajouter à certains groupes (pour accès réseau, USB, etc.)
usermod -aG dialout avmonitoring  # Pour accès USB série (Zigbee)
```

### 1.3 Cloner le Dépôt

```bash
# Cloner dans /opt
cd /opt
git clone https://github.com/CedricNCoding/av-monitoring-mvp.git avmonitoring-agent

# Ajuster permissions
chown -R avmonitoring:avmonitoring /opt/avmonitoring-agent
```

---

## 🐍 Étape 2 : Installation de l'Agent Python

### 2.1 Créer l'Environnement Virtuel

```bash
cd /opt/avmonitoring-agent/agent

# Créer venv
sudo -u avmonitoring python3 -m venv venv

# Activer et installer dépendances
sudo -u avmonitoring bash -c "source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt"
```

**Vérification :**
```bash
/opt/avmonitoring-agent/agent/venv/bin/python -c "import requests, fastapi, paho.mqtt.client; print('✓ Dépendances OK')"
```

### 2.2 Créer la Configuration Initiale

```bash
# Créer répertoire de config
mkdir -p /etc/avmonitoring

# Copier exemple de config
cp /opt/avmonitoring-agent/agent/config.example.json /etc/avmonitoring/config.json

# Éditer la configuration
nano /etc/avmonitoring/config.json
```

**Configuration minimale :**
```json
{
  "site_name": "mon-site-01",
  "backend_url": "https://backend.avmonitoring.example.com",
  "backend_token": "TOKEN_FOURNI_PAR_BACKEND",
  "poll_interval_sec": 300,
  "devices": []
}
```

**Remplacer :**
- `mon-site-01` → Nom du site/agent (unique)
- `https://backend...` → URL du backend
- `TOKEN_FOURNI_PAR_BACKEND` → Token d'authentification obtenu depuis le backend

**Permissions :**
```bash
chown avmonitoring:avmonitoring /etc/avmonitoring/config.json
chmod 600 /etc/avmonitoring/config.json
```

### 2.3 Installer le Service Systemd

```bash
# Copier le fichier de configuration du service
cp /opt/avmonitoring-agent/agent/packaging/default/avmonitoring-agent /etc/default/avmonitoring-agent

# Copier le service systemd
cp /opt/avmonitoring-agent/agent/packaging/avmonitoring-agent.service /etc/systemd/system/

# Recharger systemd
systemctl daemon-reload

# Activer le service (démarrage auto au boot)
systemctl enable avmonitoring-agent

# Démarrer le service
systemctl start avmonitoring-agent
```

### 2.4 Vérifier le Service

```bash
# Status du service
systemctl status avmonitoring-agent

# Logs en direct
journalctl -u avmonitoring-agent -f

# Vérifier l'UI web
curl -I http://localhost:8080/
# Attendu : HTTP/1.1 200 OK
```

**Accès UI :** Ouvrir `http://<ip-agent>:8080` dans un navigateur.

---

## 📡 Étape 3 : Installation Stack Zigbee (Optionnel)

### 3.1 Vérifier le Dongle USB

```bash
# Lister les périphériques USB série
ls -la /dev/ttyUSB* /dev/ttyACM*

# Doit afficher quelque chose comme :
# crw-rw---- 1 root dialout 188, 0 Jan 25 10:00 /dev/ttyUSB0
```

**Si aucun device détecté :**
- Vérifier que le dongle est bien branché
- Essayer `dmesg | grep tty` pour voir les logs du kernel
- Redémarrer la machine si nécessaire

**Dongles testés et compatibles :**
- Sonoff Zigbee 3.0 USB Dongle Plus (ZBDongle-E)
- ConBee II
- CC2531 avec firmware Z-Stack

### 3.2 Lancer le Script d'Installation

```bash
cd /opt/avmonitoring-agent/agent/scripts

# Rendre exécutable
chmod +x install_zigbee_stack.sh

# Lancer l'installation (en root)
./install_zigbee_stack.sh
```

**Le script va :**
1. ✅ Installer Mosquitto (broker MQTT)
2. ✅ Installer Node.js 20.x
3. ✅ Détecter le dongle USB automatiquement
4. ✅ Générer certificats TLS auto-signés
5. ✅ Configurer Mosquitto (port 8883, TLS, ACL)
6. ✅ Créer 3 utilisateurs MQTT (admin, zigbee2mqtt, avmonitoring)
7. ✅ Installer Zigbee2MQTT dans /opt/zigbee2mqtt
8. ✅ Configurer et démarrer les services
9. ✅ Sauvegarder les credentials dans /root/zigbee_credentials.txt

**Durée :** 5-10 minutes (dépend de la connexion Internet)

### 3.3 Vérifier l'Installation Zigbee

```bash
# Lancer le script de validation
cd /opt/avmonitoring-agent/agent/scripts
./check_zigbee_stack.sh
```

**Résultat attendu :**
```
=========================================
  Tests réussis:   40+
  Avertissements:  0-2
  Tests échoués:   0
=========================================
```

**Vérifications manuelles :**
```bash
# 1. Services actifs
systemctl status mosquitto
systemctl status zigbee2mqtt
systemctl status avmonitoring-agent

# 2. Port MQTT ouvert
ss -tln | grep 8883
# Doit afficher : LISTEN sur 0.0.0.0:8883

# 3. Credentials MQTT
cat /root/zigbee_credentials.txt
# Doit afficher les 3 passwords générés

# 4. Test connexion MQTT
source /root/zigbee_credentials.txt
mosquitto_sub -h localhost -p 8883 \
  --cafile /etc/mosquitto/ca_certificates/ca.crt \
  -u avmonitoring -P "$MQTT_PASS_AGENT" \
  -t 'zigbee2mqtt/bridge/state' -C 1 -W 5

# Doit afficher : {"state":"online"}
```

### 3.4 Variables d'Environnement MQTT (Automatique)

Le script d'installation a automatiquement ajouté les variables MQTT dans `/etc/default/avmonitoring-agent` :

```bash
# Vérifier que les variables sont présentes
grep AVMVP_MQTT /etc/default/avmonitoring-agent

# Doit afficher (décommenté) :
# AVMVP_MQTT_HOST=localhost
# AVMVP_MQTT_PORT=8883
# AVMVP_MQTT_USER=avmonitoring
# AVMVP_MQTT_PASS=<mot_de_passe_généré>
# AVMVP_MQTT_TLS_CA=/etc/mosquitto/ca_certificates/ca.crt
# AVMVP_MQTT_BASE_TOPIC=zigbee2mqtt
```

**Redémarrer l'agent pour prendre en compte :**
```bash
systemctl restart avmonitoring-agent

# Vérifier logs MQTT
journalctl -u avmonitoring-agent -n 50 | grep -i mqtt
# Doit afficher : connexion MQTT réussie
```

---

## 🔗 Étape 4 : Jumelage des Appareils Zigbee

### 4.1 Accéder à l'Interface Zigbee2MQTT

**Option 1 : Via l'UI de l'agent (recommandé)**
- Ouvrir `http://<ip-agent>:8080`
- Scroller jusqu'à la section "📡 Gestion Zigbee"
- Cliquer sur "🔗 Activer jumelage (60s)"

**Option 2 : Via MQTT**
```bash
source /root/zigbee_credentials.txt
mosquitto_pub -h localhost -p 8883 \
  --cafile /etc/mosquitto/ca_certificates/ca.crt \
  -u admin -P "$MQTT_PASS_ADMIN" \
  -t 'zigbee2mqtt/bridge/request/permit_join' \
  -m '{"value": true, "time": 60}'
```

### 4.2 Jumeler un Appareil

**Procédure générale :**
1. Activer le mode jumelage (étape 4.1)
2. Mettre l'appareil Zigbee en mode pairing :
   - **Capteur de température** : Maintenir bouton reset 5s
   - **Ampoule** : Allumer/éteindre 6 fois rapidement
   - **Prise** : Maintenir bouton 5s
   - **Bouton** : Triple-clic rapide

3. Attendre la détection (10-30 secondes)
4. L'appareil apparaît dans l'UI avec un nom par défaut (ex: `0x00158d0001234567`)

### 4.3 Renommer l'Appareil

**Via l'UI :**
- Cliquer sur "Renommer" à côté de l'appareil
- Entrer un nom lisible : `bureau_capteur_temp` ou `salle_reunion_prise`

**Via MQTT :**
```bash
source /root/zigbee_credentials.txt
mosquitto_pub -h localhost -p 8883 \
  --cafile /etc/mosquitto/ca_certificates/ca.crt \
  -u admin -P "$MQTT_PASS_ADMIN" \
  -t 'zigbee2mqtt/bridge/request/device/rename' \
  -m '{"from": "0x00158d0001234567", "to": "bureau_capteur_temp"}'
```

### 4.4 Assigner une Localisation

**Via l'UI :**
- Cliquer sur "Assigner salle" à côté de l'appareil
- Remplir : Bâtiment / Étage / Salle
- Le device sera ajouté automatiquement à `config.json`

**Exemple de device Zigbee dans config.json :**
```json
{
  "ip": "zigbee:bureau_capteur_temp",
  "name": "Capteur température bureau",
  "driver": "zigbee",
  "type": "sensor",
  "building": "Bâtiment A",
  "floor": "2",
  "room": "Bureau 201",
  "zigbee": {
    "ieee_address": "0x00158d0001234567",
    "device_type": "temperature_sensor"
  }
}
```

---

## ✅ Étape 5 : Validation Complète

### 5.1 Vérifier les Services

```bash
# Tous les services doivent être "active (running)"
systemctl status avmonitoring-agent
systemctl status mosquitto          # Si stack Zigbee installée
systemctl status zigbee2mqtt        # Si stack Zigbee installée
```

### 5.2 Vérifier la Collecte

```bash
# Logs de collecte en direct
journalctl -u avmonitoring-agent -f

# Attendre un cycle de collecte (max 5 minutes)
# Doit afficher :
# - "Starting collection cycle"
# - Logs de probe() pour chaque device
# - "Ingesting X observations to backend"
```

### 5.3 Vérifier le Backend

**Depuis l'UI du backend :**
- Aller dans "Agents" → Chercher `mon-site-01`
- Vérifier que l'agent est "Online"
- Vérifier que les devices apparaissent
- Vérifier que les métriques remontent

**Depuis l'agent (API locale) :**
```bash
# Dernier status collecté
curl -s http://localhost:8080/status | jq '.'

# Liste des devices
curl -s http://localhost:8080/devices | jq '.'
```

### 5.4 Tester les Devices Zigbee

```bash
# Lister les devices Zigbee détectés
mosquitto_sub -h localhost -p 8883 \
  --cafile /etc/mosquitto/ca_certificates/ca.crt \
  -u avmonitoring -P "$(grep MQTT_PASS_AGENT /root/zigbee_credentials.txt | cut -d= -f2)" \
  -t 'zigbee2mqtt/#' -C 10

# Doit afficher les messages des devices (temperature, battery, linkquality, etc.)
```

---

## 🔧 Étape 6 : Configuration Avancée (Optionnel)

### 6.1 Ajouter des Devices Ping/SNMP/PJLink

**Éditer la config :**
```bash
nano /etc/avmonitoring/config.json
```

**Exemples de devices :**

```json
{
  "devices": [
    {
      "ip": "192.168.1.10",
      "name": "Switch Core",
      "driver": "snmp",
      "type": "switch",
      "building": "Bâtiment A",
      "floor": "RDC",
      "room": "Salle serveur",
      "snmp": {
        "version": "2c",
        "community": "public"
      }
    },
    {
      "ip": "192.168.1.50",
      "name": "Vidéoprojecteur Salle 1",
      "driver": "pjlink",
      "type": "projector",
      "building": "Bâtiment B",
      "floor": "1",
      "room": "Salle de conf 1",
      "pjlink": {
        "password": "admin"
      }
    },
    {
      "ip": "8.8.8.8",
      "name": "Test Internet",
      "driver": "ping",
      "type": "network",
      "building": "External",
      "floor": "",
      "room": ""
    }
  ]
}
```

**Redémarrer l'agent :**
```bash
systemctl restart avmonitoring-agent
```

### 6.2 Ajuster l'Intervalle de Collecte

**Éditer `/etc/avmonitoring/config.json` :**
```json
{
  "poll_interval_sec": 180
}
```
- Valeur par défaut : `300` (5 minutes)
- Minimum recommandé : `60` (1 minute)
- Maximum recommandé : `600` (10 minutes)

### 6.3 Configurer le Niveau de Logs

**Éditer `/etc/default/avmonitoring-agent` :**
```bash
LOG_LEVEL=INFO
```

Valeurs possibles : `DEBUG`, `INFO`, `WARNING`, `ERROR`

**Redémarrer :**
```bash
systemctl restart avmonitoring-agent
```

---

## 🐛 Troubleshooting

### Problème 1 : Agent ne démarre pas

**Symptômes :**
```bash
systemctl status avmonitoring-agent
# Active: failed (Result: exit-code)
```

**Diagnostic :**
```bash
journalctl -u avmonitoring-agent -n 100 --no-pager
```

**Causes fréquentes :**
1. **Erreur de syntaxe JSON** : Vérifier `config.json` avec `jq . /etc/avmonitoring/config.json`
2. **Permissions** : Vérifier `chown avmonitoring:avmonitoring /etc/avmonitoring/config.json`
3. **Dépendances manquantes** : Réinstaller avec `pip install -r requirements.txt`

### Problème 2 : Mosquitto refuse de démarrer

**Symptômes :**
```bash
systemctl status mosquitto
# Active: failed
```

**Diagnostic :**
```bash
journalctl -u mosquitto -n 50 --no-pager
```

**Erreur : "Duplicate persistence_location"**
```bash
# Lancer le script de réparation
cd /opt/avmonitoring-agent/agent/scripts
./repair_mosquitto_config.sh
```

**Erreur : "Error loading CA certificate"**
```bash
# Régénérer les certificats
cd /etc/mosquitto/ca_certificates
openssl req -new -x509 -days 3650 -extensions v3_ca -keyout ca.key -out ca.crt -subj "/CN=Mosquitto CA" -nodes
openssl req -new -nodes -x509 -out server.crt -keyout server.key -days 3650 -subj "/CN=localhost"

# Permissions
chown mosquitto:mosquitto /etc/mosquitto/ca_certificates/*
chmod 600 /etc/mosquitto/ca_certificates/*.key

systemctl restart mosquitto
```

### Problème 3 : Zigbee2MQTT ne voit pas le dongle

**Symptômes :**
```bash
journalctl -u zigbee2mqtt -n 50
# Error: Failed to connect to adapter
```

**Diagnostic :**
```bash
# Vérifier le device USB
ls -la /dev/ttyUSB* /dev/ttyACM*

# Vérifier permissions
ls -la /dev/ttyUSB0
# Doit être : crw-rw---- 1 root dialout

# Vérifier que zigbee2mqtt est dans le groupe dialout
groups zigbee2mqtt
```

**Solution :**
```bash
# Ajouter au groupe dialout
usermod -aG dialout zigbee2mqtt

# Redémarrer
systemctl restart zigbee2mqtt
```

### Problème 4 : Devices Zigbee "offline" mais visibles

**Causes possibles :**
1. **Batterie faible** : Remplacer la pile
2. **Hors de portée** : Rapprocher du coordinateur ou ajouter routeurs Zigbee
3. **Interférences** : Éloigner le dongle des sources WiFi 2.4GHz

**Diagnostic :**
```bash
# Vérifier linkquality
mosquitto_sub -h localhost -p 8883 \
  --cafile /etc/mosquitto/ca_certificates/ca.crt \
  -u avmonitoring -P "$(grep MQTT_PASS_AGENT /root/zigbee_credentials.txt | cut -d= -f2)" \
  -t 'zigbee2mqtt/nom_du_device' -C 1

# linkquality < 50 → mauvaise liaison
# linkquality > 100 → bonne liaison
```

### Problème 5 : Backend ne reçoit pas les données

**Diagnostic :**
```bash
# Vérifier logs d'ingest
journalctl -u avmonitoring-agent -n 100 | grep ingest

# Vérifier connectivité backend
curl -I https://backend.avmonitoring.example.com/health
```

**Causes fréquentes :**
1. **Token invalide** : Vérifier `backend_token` dans config.json
2. **Firewall** : Vérifier que le port 443 sortant est ouvert
3. **URL incorrecte** : Vérifier `backend_url`

---

## 📚 Ressources Complémentaires

**Documentation détaillée :**
- [ZIGBEE_SETUP.md](ZIGBEE_SETUP.md) - Guide complet Zigbee
- [MOSQUITTO_SECURITY.md](../MOSQUITTO_SECURITY.md) - Détails sécurité Mosquitto
- [MOSQUITTO_FIX.md](../MOSQUITTO_FIX.md) - Résolution problèmes Mosquitto

**Scripts utiles :**
- `agent/scripts/install_zigbee_stack.sh` - Installation stack Zigbee
- `agent/scripts/check_zigbee_stack.sh` - Validation installation
- `agent/scripts/repair_mosquitto_config.sh` - Réparation config Mosquitto
- `agent/scripts/uninstall_zigbee_stack.sh` - Désinstallation propre

**Commandes rapides :**
```bash
# Statut global
systemctl status avmonitoring-agent mosquitto zigbee2mqtt

# Logs en direct
journalctl -u avmonitoring-agent -f

# Redémarrage complet
systemctl restart avmonitoring-agent mosquitto zigbee2mqtt

# Test MQTT
source /root/zigbee_credentials.txt
mosquitto_sub -h localhost -p 8883 --cafile /etc/mosquitto/ca_certificates/ca.crt -u avmonitoring -P "$MQTT_PASS_AGENT" -t '#' -C 10
```

---

## ✨ Checklist Finale

- [ ] Système Debian/Ubuntu à jour
- [ ] Agent installé et service actif
- [ ] Config initiale créée (site_name, backend_url, backend_token)
- [ ] UI accessible sur :8080
- [ ] Backend reçoit les données de l'agent
- [ ] Stack Zigbee installée (si souhaité)
- [ ] Mosquitto + Zigbee2MQTT services actifs
- [ ] Dongle USB détecté
- [ ] Devices Zigbee jumelés et renommés
- [ ] Devices assignés aux salles
- [ ] Collecte Zigbee fonctionnelle
- [ ] Backup des credentials dans /root/zigbee_credentials.txt
- [ ] Documentation conservée pour maintenance

**Installation terminée !** 🎉

L'agent est maintenant opérationnel et collecte les données vers le backend. Les devices Zigbee sont surveillés en temps réel.

**Support :**
- Logs : `journalctl -u avmonitoring-agent -f`
- UI locale : `http://<ip-agent>:8080`
- Configuration : `/etc/avmonitoring/config.json`
- Credentials MQTT : `/root/zigbee_credentials.txt`
