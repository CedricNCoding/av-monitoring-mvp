# Scripts d'Installation

Ce dossier contient les scripts d'installation et de maintenance de l'agent AV Monitoring.

## Scripts Disponibles

### 📦 Installation Agent

#### `install_agent.sh` - Installation automatique de l'agent

Installation complète de l'agent AV Monitoring en une seule commande.

**Utilisation :**
```bash
# Méthode 1 : Installation directe depuis GitHub
curl -sSL https://raw.githubusercontent.com/CedricNCoding/av-monitoring-mvp/main/agent/scripts/install_agent.sh | sudo bash

# Méthode 2 : Depuis le dépôt cloné
cd /opt/avmonitoring-agent/agent/scripts
sudo ./install_agent.sh
```

**Actions effectuées :**
- Vérification des prérequis (OS Debian/Ubuntu, Python 3.10+)
- Création de l'utilisateur système `avmonitoring`
- Clonage ou mise à jour du dépôt Git
- Création du venv Python et installation des dépendances
- Création des répertoires système (/var/lib/avmonitoring, /var/log/avmonitoring, /etc/avmonitoring)
- Installation du service systemd
- Configuration par défaut (à éditer ensuite)

**Après installation :**
```bash
# Éditer la configuration
nano /etc/avmonitoring/config.json

# Démarrer le service
systemctl start avmonitoring-agent

# Vérifier le status
systemctl status avmonitoring-agent
```

---

### 🗑️ Désinstallation Agent

#### `uninstall_agent.sh` - Désinstallation propre de l'agent

Supprime l'agent et ses données (conserve la configuration).

**Utilisation :**
```bash
cd /opt/avmonitoring-agent/agent/scripts
sudo ./uninstall_agent.sh
```

**Actions effectuées :**
- Arrêt et désactivation du service
- Suppression du code (/opt/avmonitoring-agent)
- Suppression des logs (/var/log/avmonitoring)
- Suppression des données (/var/lib/avmonitoring)
- Option de suppression de l'utilisateur
- Conservation de la configuration (/etc/avmonitoring)

---

### 📡 Stack Zigbee (Optionnel)

#### `install_zigbee_stack.sh` - Installation Mosquitto + Zigbee2MQTT

Installation complète de la stack Zigbee pour le monitoring de capteurs/actionneurs Zigbee.

**Prérequis :**
- Agent AV Monitoring déjà installé
- Dongle Zigbee USB branché

**Utilisation :**
```bash
cd /opt/avmonitoring-agent/agent/scripts
sudo ./install_zigbee_stack.sh
```

**Actions effectuées :**
- Installation de Mosquitto (broker MQTT)
- Installation de Node.js 20.x
- Détection automatique du dongle USB
- Génération de certificats TLS auto-signés
- Configuration Mosquitto (TLS, ACL, authentification)
- Installation de Zigbee2MQTT
- Création de 3 utilisateurs MQTT (admin, zigbee2mqtt, avmonitoring)
- Configuration et démarrage des services
- Sauvegarde des credentials dans /root/zigbee_credentials.txt

**Documentation complète :** [docs/ZIGBEE_SETUP.md](../../docs/ZIGBEE_SETUP.md)

---

#### `check_zigbee_stack.sh` - Validation de l'installation Zigbee

Script de validation avec 40+ tests pour vérifier que la stack Zigbee fonctionne correctement.

**Utilisation :**
```bash
cd /opt/avmonitoring-agent/agent/scripts
sudo ./check_zigbee_stack.sh
```

**Tests effectués :**
- Services systemd (mosquitto, zigbee2mqtt, avmonitoring-agent)
- Ports réseau (8883 ouvert)
- Certificats TLS (présence, permissions)
- Dongle USB (détection, permissions)
- Connexion MQTT (authentification, TLS)
- Configuration (syntaxe, cohérence)

---

#### `uninstall_zigbee_stack.sh` - Désinstallation de la stack Zigbee

Suppression complète de Mosquitto et Zigbee2MQTT.

**Utilisation :**
```bash
cd /opt/avmonitoring-agent/agent/scripts
sudo ./uninstall_zigbee_stack.sh
```

**Actions effectuées :**
- Arrêt des services mosquitto et zigbee2mqtt
- Désinstallation de Mosquitto
- Suppression de Zigbee2MQTT (/opt/zigbee2mqtt)
- Suppression des certificats
- Retrait des variables MQTT de /etc/default/avmonitoring-agent
- Conservation de la base de données Zigbee (optionnel)

---

## 📚 Documentation Complète

- [Guide d'installation Agent Standard](../../docs/agent/INSTALLATION.md)
- [Guide d'installation Agent + Zigbee](../../docs/agent/INSTALLATION_ZIGBEE.md)
- [Configuration Zigbee détaillée](../../docs/agent/ZIGBEE_SETUP.md)
- [Sécurité Mosquitto](../../docs/security/MOSQUITTO.md)
- [Mémo technique DSI](../../docs/agent/MEMO-DSI.md)

---

## 🆘 Support

En cas de problème :

```bash
# Logs agent
journalctl -u avmonitoring-agent -f

# Logs Mosquitto
journalctl -u mosquitto -f

# Logs Zigbee2MQTT
journalctl -u zigbee2mqtt -f

# Status global
systemctl status avmonitoring-agent mosquitto zigbee2mqtt
```

---

## ⚡ Démarrage Rapide (Nouveau Serveur)

```bash
# 1. Cloner le dépôt
git clone https://github.com/CedricNCoding/av-monitoring-mvp.git
cd av-monitoring-mvp/agent/scripts

# 2. Installer l'agent
sudo ./install.sh

# 3. Configurer
sudo nano /etc/avmonitoring/config.json

# 4. Démarrer
sudo systemctl start avmonitoring-agent

# 5. (Optionnel) Installer Zigbee
sudo ./install_zigbee_stack.sh
```

Accéder à l'UI : `http://<ip-agent>:8080`
