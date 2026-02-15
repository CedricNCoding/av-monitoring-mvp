# AV Monitoring MVP

Solution professionnelle de surveillance d'équipements audiovisuels pour salles de réunion, auditoriums et installations AV.

## 🎯 Présentation

**AV Monitoring** est une solution complète de monitoring pour équipements audiovisuels comprenant :

- **Backend centralisé** - API REST + Interface Web + Base de données PostgreSQL
- **Agents de surveillance** - Déployés sur sites distants pour collecter les métriques
- **Support multi-protocoles** - Ping, SNMP, PJLink, Zigbee
- **Interface intuitive** - Visualisation en temps réel de l'état des équipements
- **Alertes automatiques** - Détection proactive des pannes

## 📦 Composants

### Backend

Le backend centralise les données de tous les sites et fournit l'interface de gestion.

- **Technologie** : Python, FastAPI, PostgreSQL
- **Déploiement** : Systemd natif (sans Docker)
- **Sécurité** : Utilisateur dédié, firewall, support Cloudflare Zero Trust

📖 **[Documentation Backend](docs/backend/INSTALLATION.md)**

### Agent

L'agent se déploie sur chaque site pour surveiller les équipements locaux.

- **Technologie** : Python, FastAPI
- **Protocoles** : Ping, SNMP, PJLink, Zigbee (optionnel)
- **Interface locale** : Web UI sur port 8080
- **Déploiement** : Systemd natif (sans Docker)

📖 **[Documentation Agent](docs/agent/INSTALLATION.md)**

## 🚀 Installation rapide

### Backend

```bash
# Installation automatisée
cd backend/scripts
sudo ./install.sh

# Configuration
sudo nano /etc/avmonitoring-backend/config.env

# Démarrage
sudo systemctl start avmonitoring-backend
```

📖 **Guide complet : [docs/backend/INSTALLATION.md](docs/backend/INSTALLATION.md)**

### Agent

**Agent standard :**
```bash
# Installation
cd agent/scripts
sudo ./install.sh

# Configuration
sudo nano /etc/avmonitoring/config.json

# Démarrage
sudo systemctl start avmonitoring-agent
```

**Agent avec support Zigbee :**
```bash
# Installation agent + stack Zigbee
cd agent/scripts
sudo ./install_zigbee_stack.sh
```

📖 **Guides complets :**
- [Agent standard](docs/agent/INSTALLATION.md)
- [Agent + Zigbee](docs/agent/INSTALLATION_ZIGBEE.md)

## 📚 Documentation

Toute la documentation est centralisée dans le dossier **[docs/](docs/)**

### Installation

- **[Backend](docs/backend/INSTALLATION.md)** - Installation backend sur Linux
- **[Agent Standard](docs/agent/INSTALLATION.md)** - Agent ping/SNMP/PJLink
- **[Agent + Zigbee](docs/agent/INSTALLATION_ZIGBEE.md)** - Installation complète avec Zigbee
- **[Stack Zigbee](docs/agent/ZIGBEE_SETUP.md)** - Ajout Zigbee à un agent existant

### Sécurité

- **[Sécurité Backend](docs/security/BACKEND.md)** - Architecture sécurisée, Cloudflare, firewall
- **[Sécurité Mosquitto](docs/security/MOSQUITTO.md)** - Configuration MQTT sécurisée

### Technique

- **[Mémo DSI](docs/agent/MEMO-DSI.md)** - Mémo technique pour équipes DSI

## 🏗️ Architecture

```
┌────────────────────────────────────────────────┐
│           Internet / Cloudflare                │
│          (Authentification optionnelle)        │
└────────────────────┬───────────────────────────┘
                     │ HTTPS
                     ↓
┌────────────────────────────────────────────────┐
│              Backend (Cloud/On-prem)           │
│  ┌──────────────────────────────────────────┐ │
│  │ API REST (FastAPI)           Port 8000   │ │
│  │ Interface Web                            │ │
│  │ Base PostgreSQL              Port 5432   │ │
│  └──────────────────────────────────────────┘ │
└────────────────────┬───────────────────────────┘
                     │ HTTPS (Token)
          ┌──────────┴──────────┐
          ↓                     ↓
┌──────────────────┐   ┌──────────────────┐
│   Agent Site 1   │   │   Agent Site 2   │
│ ┌──────────────┐ │   │ ┌──────────────┐ │
│ │ Collecteur   │ │   │ │ Collecteur   │ │
│ │ - Ping       │ │   │ │ - SNMP       │ │
│ │ - SNMP       │ │   │ │ - PJLink     │ │
│ │ - PJLink     │ │   │ │ - Zigbee     │ │
│ │              │ │   │ │              │ │
│ │ WebUI :8080  │ │   │ │ WebUI :8080  │ │
│ └──────────────┘ │   │ └──────────────┘ │
└──────────────────┘   └──────────────────┘
```

## 🔧 Stack technique

- **Backend** : Python 3.10+, FastAPI, PostgreSQL, SQLAlchemy
- **Agent** : Python 3.10+, FastAPI
- **Déploiement** : Systemd natif (pas de Docker)
- **Protocoles** : HTTP/HTTPS, SNMP v2c, PJLink, MQTT (Zigbee)
- **OS** : Linux (Ubuntu/Debian)

## 🔒 Sécurité

Le projet implémente des mesures de sécurité professionnelles :

- ✅ **Isolation des services** - Utilisateurs système dédiés non-root
- ✅ **Réseau** - Binding localhost uniquement pour services internes
- ✅ **Firewall** - Configuration ufw restrictive
- ✅ **Systemd** - Protections NoNewPrivileges, ProtectSystem, ProtectHome
- ✅ **Authentification** - Token API + support Cloudflare Zero Trust
- ✅ **TLS/HTTPS** - Communication chiffrée

**Niveau de sécurité : 7-8/10** (Standard Pro)

Consultez **[docs/security/BACKEND.md](docs/security/BACKEND.md)** pour les détails.

## 📋 Prérequis

### Backend
- Linux (Ubuntu 20.04+, Debian 11+)
- Python 3.10+
- PostgreSQL 12+
- Accès root (installation)

### Agent
- Linux (Ubuntu 20.04+, Debian 11+)
- Python 3.10+
- Accès root (installation)
- Optionnel : Dongle Zigbee USB (pour support Zigbee)

## 🎯 Cas d'usage

- ✅ Surveillance d'équipements audiovisuels (vidéoprojecteurs, écrans, amplis)
- ✅ Monitoring d'environnement via capteurs Zigbee (température, humidité, CO2)
- ✅ Gestion multi-sites avec backend centralisé
- ✅ Alertes automatiques en cas de panne
- ✅ Interface Web pour visualisation temps réel

## 📊 Fonctionnalités

### Protocoles supportés

| Protocole | Description | Équipements typiques |
|-----------|-------------|---------------------|
| **Ping** | Test de connectivité réseau | Tous équipements IP |
| **SNMP** | Monitoring réseau avancé | Switches, équipements réseau |
| **PJLink** | Protocole vidéoprojecteurs | Projecteurs, écrans professionnels |
| **Zigbee** | Capteurs et actionneurs sans fil | Capteurs température/humidité/CO2 |

### Métriques collectées

- État de santé (OK/KO/DOUBT)
- Temps de réponse réseau
- Température, heures de fonctionnement lampe (PJLink)
- Données capteurs Zigbee (température, humidité, CO2, etc.)

## 🛠️ Commandes utiles

### Backend
```bash
# Statut
sudo systemctl status avmonitoring-backend

# Logs
sudo journalctl -u avmonitoring-backend -f

# Redémarrage
sudo systemctl restart avmonitoring-backend
```

### Agent
```bash
# Statut
sudo systemctl status avmonitoring-agent

# Logs
sudo journalctl -u avmonitoring-agent -f

# Interface Web locale
http://localhost:8080
```

## 📝 Structure du projet

```
av-monitoring-mvp/
├── README.md                    # Ce fichier
├── docs/                        # Documentation complète
│   ├── backend/                 # Docs backend
│   ├── agent/                   # Docs agent
│   └── security/                # Guides sécurité
├── backend/                     # Code backend
│   ├── app/                     # Application FastAPI
│   └── scripts/                 # Scripts d'installation
└── agent/                       # Code agent
    ├── src/                     # Application FastAPI
    ├── scripts/                 # Scripts d'installation
    └── packaging/               # Fichiers systemd
```

## 🤝 Contribution

Pour contribuer au projet :
1. Respecter la structure de documentation dans `docs/`
2. Tester les installations sur système propre (VM/container)
3. Documenter les changements significatifs
4. Suivre les guidelines de sécurité

## 📞 Support

### Documentation
Consultez **[docs/README.md](docs/README.md)** pour l'index complet de la documentation.

### Dépannage
Chaque guide d'installation contient une section "Dépannage" :
- [Dépannage Backend](docs/backend/INSTALLATION.md#-d%C3%A9pannage)
- [Dépannage Agent](docs/agent/INSTALLATION.md#-d%C3%A9pannage)

### Logs
```bash
# Backend
sudo journalctl -u avmonitoring-backend -n 100

# Agent
sudo journalctl -u avmonitoring-agent -n 100
```

## 📄 Licence

Ce projet est un MVP (Minimum Viable Product) à des fins de démonstration.

---

**Version :** 1.0.0
**Dernière mise à jour :** Février 2026
**Auteur :** CedricNCoding
