# AV Monitoring Backend

Backend centralisé pour la solution AV Monitoring.

## Installation en production

Le backend s'installe sur un système Linux (Ubuntu/Debian) comme un service système natif.

**⚠️ Important** : Cette installation utilise une approche **native** (Python + systemd + PostgreSQL) et **non Docker**.
- ✅ Plus sécurisée (service avec utilisateur dédié non-root)
- ✅ Plus simple (pas de gestion de conteneurs)
- ✅ Meilleure performance
- ✅ Intégration système native (systemd, journalctl)

### Installation rapide

```bash
# 1. Télécharger le code
git clone https://github.com/CedricNCoding/av-monitoring-mvp.git
cd av-monitoring-mvp/backend

# 2. Lancer l'installation
cd scripts
sudo ./install.sh

# 3. Configurer le backend
sudo nano /etc/avmonitoring-backend/config.env
# Configurez : DB_PASSWORD, SECRET_KEY, etc.

# 4. Démarrer le service
sudo systemctl start avmonitoring-backend
```

### Documentation complète

📖 **[Guide d'installation complet](../docs/backend/INSTALLATION.md)**

Consultez également :
- **[Sécurité Backend](../docs/security/BACKEND.md)** - Architecture sécurisée, Cloudflare Zero Trust
- **[Sécurité Mosquitto](../docs/security/MOSQUITTO.md)** - Configuration MQTT sécurisée

## Architecture des fichiers

```
backend/
├── app/                    # Code source de l'application
│   ├── main.py            # Point d'entrée FastAPI
│   ├── models.py          # Modèles SQLAlchemy
│   ├── config.py          # Configuration
│   └── routes/            # Endpoints API
├── scripts/                # Scripts d'installation
│   └── install.sh         # Installation en production
└── requirements.txt       # Dépendances Python
```

## Chemins d'installation (production)

| Composant | Chemin |
|-----------|--------|
| Code source | `/opt/avmonitoring-backend/` |
| Configuration | `/etc/avmonitoring-backend/config.env` |
| Logs | `/var/log/avmonitoring-backend/` |
| Service systemd | `/etc/systemd/system/avmonitoring-backend.service` |
| Base de données | PostgreSQL (localhost:5432) |

## Commandes utiles

```bash
# Démarrer/Arrêter/Redémarrer
sudo systemctl start avmonitoring-backend
sudo systemctl stop avmonitoring-backend
sudo systemctl restart avmonitoring-backend

# Voir le statut
sudo systemctl status avmonitoring-backend

# Consulter les logs
sudo journalctl -u avmonitoring-backend -f

# Base de données
sudo -u postgres psql avmonitoring
```

## Prérequis

- **Python 3.10+**
- **PostgreSQL 12+**
- **systemd** (pour l'installation en production)
- **Traefik ou Nginx** (reverse proxy pour HTTPS)

## Support

Pour toute question ou problème, consultez la section "Dépannage" dans le [guide d'installation](../docs/backend/INSTALLATION.md).
