# Documentation AV Monitoring

Documentation complète du projet AV Monitoring - Solution de surveillance d'équipements audiovisuels.

## 📚 Index de la documentation

### Backend

- **[Installation Backend](backend/INSTALLATION.md)** - Guide complet d'installation du backend sur Linux (systemd, PostgreSQL, sécurité)

### Agent

- **[Installation Agent Standard](agent/INSTALLATION.md)** - Installation de l'agent de surveillance (ping, SNMP, PJLink)
- **[Installation Agent + Zigbee](agent/INSTALLATION_ZIGBEE.md)** - Installation complète agent + stack Zigbee (Mosquitto + Zigbee2MQTT)
- **[Configuration Stack Zigbee](agent/ZIGBEE_SETUP.md)** - Installation de la stack Zigbee seule (ajout à un agent existant)
- **[Mémo Technique DSI](agent/MEMO-DSI.md)** - Mémo technique pour les équipes DSI

### Sécurité

- **[Sécurité Backend](security/BACKEND.md)** - Mesures de sécurité pour le backend (architecture, Cloudflare Zero Trust, firewall)
- **[Sécurité Mosquitto](security/MOSQUITTO.md)** - Configuration sécurisée de Mosquitto MQTT

## 🚀 Démarrage rapide

### Installation Backend

```bash
# Consulter la documentation
cat docs/backend/INSTALLATION.md
```

### Installation Agent

**Agent standard (ping, SNMP, PJLink) :**
```bash
cd agent/scripts
sudo ./install.sh
# Puis configurer : sudo nano /etc/avmonitoring/config.json
```

**Agent avec Zigbee :**
```bash
cd agent/scripts
sudo ./install_zigbee_stack.sh
# Puis configurer agent et Zigbee2MQTT
```

## 📖 Guides par cas d'usage

| Besoin | Documentation |
|--------|---------------|
| Installer le backend | [backend/INSTALLATION.md](backend/INSTALLATION.md) |
| Installer un agent de surveillance | [agent/INSTALLATION.md](agent/INSTALLATION.md) |
| Ajouter le support Zigbee | [agent/ZIGBEE_SETUP.md](agent/ZIGBEE_SETUP.md) |
| Installation tout-en-un agent + Zigbee | [agent/INSTALLATION_ZIGBEE.md](agent/INSTALLATION_ZIGBEE.md) |
| Sécuriser le déploiement | [security/BACKEND.md](security/BACKEND.md) |
| Configuration Mosquitto sécurisée | [security/MOSQUITTO.md](security/MOSQUITTO.md) |
| Mémo technique pour DSI | [agent/MEMO-DSI.md](agent/MEMO-DSI.md) |

## 🏗️ Architecture

```
┌──────────────────────────────────────┐
│         Backend (Cloud/On-prem)      │
│  - API REST                          │
│  - PostgreSQL                        │
│  - Interface Web                     │
└────────────────┬─────────────────────┘
                 │ HTTPS
                 ↓
┌──────────────────────────────────────┐
│           Agent (Site distant)       │
│  - Collecte ping/SNMP/PJLink         │
│  - Collecte Zigbee (optionnel)       │
│  - Interface Web locale :8080        │
└──────────────────────────────────────┘
```

## 🔒 Sécurité

Le projet est conçu avec la sécurité en priorité :
- ✅ Services systemd non-root (utilisateurs dédiés)
- ✅ Binding localhost-only pour services internes
- ✅ Firewall configuré (ufw)
- ✅ Authentification par token
- ✅ Support Cloudflare Zero Trust (optionnel)
- ✅ TLS/HTTPS

Consultez [security/BACKEND.md](security/BACKEND.md) pour les détails.

## 💡 Support

Pour toute question, consulter :
1. Les guides d'installation détaillés dans ce dossier
2. Les sections "Dépannage" dans chaque guide
3. Les logs système : `sudo journalctl -u <service>`

---

**Documentation mise à jour :** Février 2026
