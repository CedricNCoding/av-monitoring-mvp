# AV Monitoring Agent

Agent de surveillance pour la solution AV Monitoring.

## Installation en production

L'agent s'installe sur un système Linux (Ubuntu/Debian) comme un service système natif.

**⚠️ Important** : Cette installation utilise une approche **native** (Python + systemd) et **non Docker**.
- ✅ Plus sécurisée (service avec utilisateur dédié non-root)
- ✅ Plus simple (pas de gestion de conteneurs)
- ✅ Meilleure performance
- ✅ Intégration système native (systemd, journalctl)

### Installation rapide

```bash
# 1. Télécharger le code
git clone https://github.com/CedricNCoding/av-monitoring-mvp.git
cd av-monitoring-mvp/agent

# 2. Lancer l'installation
cd scripts
sudo ./install.sh

# 3. Configurer l'agent
sudo nano /etc/avmonitoring/config.json
# Configurez : site_token, backend_url, site_name

# 4. Démarrer le service
sudo systemctl start avmonitoring-agent
```

### Documentation complète

📖 **[Guide d'installation complet](../docs/agent/INSTALLATION.md)**

Consultez également :
- **[Installation avec Zigbee](../docs/agent/INSTALLATION_ZIGBEE.md)** - Agent + Mosquitto + Zigbee2MQTT
- **[Configuration Zigbee](../docs/agent/ZIGBEE_SETUP.md)** - Ajout Zigbee à un agent existant
- **[Mémo DSI](../docs/agent/MEMO-DSI.md)** - Mémo technique pour équipes DSI

## Architecture des fichiers

```
agent/
├── src/                    # Code source de l'application
│   ├── webapp.py           # Interface web FastAPI
│   ├── collector.py        # Collecteur de métriques
│   ├── config_sync.py      # Synchronisation avec le backend
│   └── drivers/            # Drivers de surveillance (ping, SNMP, PJLink)
├── scripts/                # Scripts d'installation
│   ├── install.sh          # Installation agent standard
│   ├── uninstall.sh        # Désinstallation
│   ├── install_zigbee_stack.sh   # Installation stack Zigbee
│   └── uninstall_zigbee_stack.sh # Désinstallation stack Zigbee
├── packaging/              # Fichiers de packaging
│   └── systemd/            # Service systemd
├── config.example.json     # Exemple de configuration
├── requirements.txt        # Dépendances Python
└── README.md               # Ce fichier
```

## Chemins d'installation (production)

| Composant | Chemin |
|-----------|--------|
| Code source | `/opt/avmonitoring-agent/` |
| Configuration | `/etc/avmonitoring/config.json` |
| Données | `/var/lib/avmonitoring/` |
| Logs | `/var/log/avmonitoring/` |
| Service systemd | `/etc/systemd/system/avmonitoring-agent.service` |

## Commandes utiles

```bash
# Démarrer/Arrêter/Redémarrer
sudo systemctl start avmonitoring-agent
sudo systemctl stop avmonitoring-agent
sudo systemctl restart avmonitoring-agent

# Voir le statut
sudo systemctl status avmonitoring-agent

# Consulter les logs
sudo journalctl -u avmonitoring-agent -f

# Interface web locale
http://localhost:8080
```

## Prérequis

- **Python 3.10+**
- **systemd** (pour l'installation en production)
- **Connexion sortante HTTPS** vers le backend

## Support

Pour toute question ou problème, consultez la section "Dépannage" dans le [guide d'installation](../docs/agent/INSTALLATION.md).
