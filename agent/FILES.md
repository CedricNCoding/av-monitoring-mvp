# Liste des fichiers - AV Monitoring Agent

## Documentation

| Fichier | Description |
|---------|-------------|
| `README.md` | Présentation générale et guide rapide |
| `INSTALLATION.md` | Guide d'installation complet et détaillé (50+ pages) |
| `QUICKSTART.md` | Guide de démarrage rapide (5 minutes) |
| `ARCHITECTURE.md` | Documentation technique d'architecture |
| `MEMO-DSI.md` | Mémo de synthèse pour validation DSI |
| `CHANGELOG.md` | Historique des versions |
| `FILES.md` | Ce fichier (liste des fichiers) |

## Configuration

| Fichier | Description |
|---------|-------------|
| `config.example.json` | Exemple de configuration (template) |
| `VERSION` | Numéro de version actuel |
| `.gitignore` | Fichiers à exclure du dépôt Git |

## Scripts d'installation et maintenance

| Fichier | Description | Exécutable |
|---------|-------------|-----------|
| `scripts/install.sh` | Installation automatique en production | ✓ |
| `scripts/uninstall.sh` | Désinstallation propre | ✓ |
| `scripts/check-install.sh` | Vérification post-installation | ✓ |
| `scripts/create-release.sh` | Création d'archives de distribution | ✓ |

## Service systemd

| Fichier | Description |
|---------|-------------|
| `packaging/systemd/avmonitoring-agent.service` | Unit systemd pour le service |

## Code source

| Fichier | Description |
|---------|-------------|
| `src/webapp.py` | Application web FastAPI (port 8080) |
| `src/collector.py` | Collecteur de métriques |
| `src/config_sync.py` | Synchronisation avec le backend |
| `src/agent.py` | Agent historique (legacy) |
| `src/storage.py` | Gestion du stockage local |
| `src/sorting.py` | Tri et organisation des devices |
| `src/scheduling.py` | Ordonnancement des collectes |
| `src/drivers/ping.py` | Driver de surveillance ping |
| `src/drivers/snmp.py` | Driver de surveillance SNMP |
| `src/drivers/pjlink.py` | Driver de surveillance PJLink |
| `src/drivers/registry.py` | Registre des drivers |
| `src/templates/index.html` | Template HTML de l'interface web |

## Dépendances

| Fichier | Description |
|---------|-------------|
| `requirements.txt` | Dépendances Python |

## Docker (optionnel, pour dev/test)

| Fichier | Description |
|---------|-------------|
| `Dockerfile` | Image Docker (non utilisée en production) |

---

## Chemins d'installation en production

Après installation via `scripts/install.sh` :

| Composant | Chemin | Propriétaire | Permissions |
|-----------|--------|--------------|-------------|
| **Code** | `/opt/avmonitoring-agent/` | avmonitoring:avmonitoring | 750 |
| **Configuration** | `/etc/avmonitoring/config.json` | avmonitoring:avmonitoring | 640 |
| **Données** | `/var/lib/avmonitoring/` | avmonitoring:avmonitoring | 750 |
| **Logs** | `/var/log/avmonitoring/` | avmonitoring:avmonitoring | 750 |
| **Service** | `/etc/systemd/system/avmonitoring-agent.service` | root:root | 644 |

---

## Utilisation

### Pour un administrateur système

1. **Installation** : `sudo ./scripts/install.sh`
2. **Configuration** : `sudo nano /etc/avmonitoring/config.json`
3. **Démarrage** : `sudo systemctl start avmonitoring-agent`
4. **Vérification** : `sudo ./scripts/check-install.sh`

### Pour un développeur

1. **Lire** : `README.md` puis `INSTALLATION.md`
2. **Architecture** : `ARCHITECTURE.md`
3. **Code** : Explorer `src/`

### Pour une DSI (validation)

1. **Lire** : `MEMO-DSI.md` (synthèse complète)
2. **Vérifier** : Checklist dans le mémo
3. **Tester** : Installation sur environnement de qualification

---

**Tous les fichiers sont conçus pour une installation professionnelle en production sans Docker.**
