# AV Monitoring Agent

Agent de surveillance pour la solution AV Monitoring.

## Installation en production (sans Docker)

L'agent peut être installé sur un système Linux (Ubuntu/Debian) comme un service système natif.

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

Consultez [INSTALLATION.md](./INSTALLATION.md) pour :
- Guide d'installation détaillé
- Configuration avancée
- Gestion du service systemd
- Dépannage
- Mise à jour
- Désinstallation

## Installation avec Docker

Pour un environnement de développement ou de test :

```bash
docker compose up -d
```

## Architecture des fichiers

```
agent/
├── src/                    # Code source de l'application
│   ├── webapp.py           # Interface web FastAPI
│   ├── collector.py        # Collecteur de métriques
│   ├── config_sync.py      # Synchronisation avec le backend
│   └── drivers/            # Drivers de surveillance (ping, SNMP, PJLink)
├── scripts/                # Scripts d'installation
│   ├── install.sh          # Installation en production
│   └── uninstall.sh        # Désinstallation
├── packaging/              # Fichiers de packaging
│   └── systemd/            # Service systemd
├── config.example.json     # Exemple de configuration
├── requirements.txt        # Dépendances Python
├── INSTALLATION.md         # Documentation d'installation complète
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

Pour toute question ou problème, consultez la section "Dépannage" dans [INSTALLATION.md](./INSTALLATION.md).
