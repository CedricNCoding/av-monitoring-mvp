# Architecture de déploiement - AV Monitoring Agent

## Vue d'ensemble

L'agent AV Monitoring est une application Python qui peut être déployée de deux manières :
- **Docker** : Pour le développement et les tests
- **Installation native** : Pour la production sur Linux (systemd)

## Architecture de déploiement en production

```
┌─────────────────────────────────────────────────────────────┐
│                    Serveur Linux (Ubuntu/Debian)            │
│                                                             │
│  ┌────────────────────────────────────────────────────┐   │
│  │              systemd                                │   │
│  │  ┌──────────────────────────────────────────────┐  │   │
│  │  │  avmonitoring-agent.service                  │  │   │
│  │  │  • Type: simple                              │  │   │
│  │  │  • User: avmonitoring (unprivileged)         │  │   │
│  │  │  • Restart: always                           │  │   │
│  │  │  • Auto-start: enabled                       │  │   │
│  │  └──────────────────────────────────────────────┘  │   │
│  └────────────────────────────────────────────────────┘   │
│                          ↓                                  │
│  ┌────────────────────────────────────────────────────┐   │
│  │  /opt/avmonitoring-agent/                         │   │
│  │  ├── src/                (code Python)            │   │
│  │  │   ├── webapp.py       (FastAPI app)           │   │
│  │  │   ├── collector.py    (monitoring logic)      │   │
│  │  │   ├── config_sync.py  (backend sync)          │   │
│  │  │   └── drivers/        (ping, SNMP, PJLink)    │   │
│  │  └── venv/               (Python virtualenv)      │   │
│  └────────────────────────────────────────────────────┘   │
│                          ↓                                  │
│  ┌────────────────────────────────────────────────────┐   │
│  │  /etc/avmonitoring/config.json                    │   │
│  │  • site_name                                       │   │
│  │  • site_token           (authentification)         │   │
│  │  • backend_url          (URL HTTPS)                │   │
│  │  • devices[]            (auto-sync depuis backend) │   │
│  └────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌────────────────────────────────────────────────────┐   │
│  │  Port 8080 (localhost)                             │   │
│  │  Interface web locale pour gestion des devices     │   │
│  └────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                          ↓ HTTPS (sortant)
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                    Backend AV Monitoring                    │
│                                                             │
│  • POST /ingest          (envoi des métriques)             │
│  • GET  /config/{token}  (récup. configuration)            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Composants principaux

### 1. Service systemd (`avmonitoring-agent.service`)
- **Rôle** : Démarrage automatique et supervision du processus
- **User** : `avmonitoring` (utilisateur système dédié, non privilégié)
- **WorkingDirectory** : `/opt/avmonitoring-agent`
- **ExecStart** : Lance webapp.py via le virtualenv Python
- **Restart** : Always (redémarrage automatique en cas d'échec)
- **Security** :
  - NoNewPrivileges (pas d'élévation de privilèges)
  - ProtectSystem=strict (système en lecture seule)
  - ProtectHome (répertoires utilisateurs inaccessibles)

### 2. Application Python (FastAPI)
- **webapp.py** : Interface web (port 8080, localhost only)
- **collector.py** : Collecte des métriques périodiques
- **config_sync.py** : Synchronisation config avec le backend (pull toutes les 5 min)
- **drivers/** : Modules de surveillance (ping, SNMP, PJLink)

### 3. Configuration
- **Fichier** : `/etc/avmonitoring/config.json`
- **Permissions** : 640 (avmonitoring:avmonitoring)
- **Contenu sensible** : `site_token` (ne jamais commiter)
- **Gestion** :
  - Configuration initiale manuelle
  - Synchronisation automatique des devices depuis le backend

### 4. Données et logs
- **Données** : `/var/lib/avmonitoring/` (état de l'agent, cache)
- **Logs** : Journald (`journalctl -u avmonitoring-agent`)
- **Logs fichiers** : `/var/log/avmonitoring/` (optionnel)

## Flux de fonctionnement

### Au démarrage
1. systemd démarre le service `avmonitoring-agent`
2. Le service lance Python avec `src/webapp.py`
3. webapp.py :
   - Charge la configuration depuis `/etc/avmonitoring/config.json`
   - Démarre l'interface web sur port 8080 (localhost)
   - Lance le thread de collecte (collector.py)
   - Lance le thread de synchronisation (config_sync.py)

### En fonctionnement normal
1. **Collecte** (collector.py) :
   - Interroge les devices toutes les X secondes (selon config)
   - Collecte : ping, SNMP metrics, PJLink status
   - Agrège les résultats

2. **Reporting** :
   - Envoie les métriques au backend via POST /ingest
   - Fréquence : 300s (OK) ou 60s (KO)
   - Headers : X-Site-Token pour l'authentification

3. **Synchronisation config** (config_sync.py) :
   - Pull la config depuis GET /config/{token} toutes les 5 min
   - Compare le hash MD5 de la config
   - Met à jour le fichier config.json si changement
   - Recharge la liste des devices dynamiquement

4. **Interface web** (webapp.py) :
   - Accessible sur http://localhost:8080
   - Permet d'ajouter/modifier/supprimer des devices localement
   - Affiche les métriques en temps réel
   - Configuration du site

## Sécurité

### Isolation
- **Utilisateur dédié** : `avmonitoring` (pas de shell, pas de home)
- **Privilèges minimaux** : Pas de sudo, pas de root
- **Namespaces** : PrivateTmp, ProtectSystem, ProtectHome

### Réseau
- **Port 8080** : Bind sur localhost uniquement (pas d'exposition externe)
- **Sortie HTTPS** : Vers le backend uniquement
- **Pas d'écoute** : Aucun port exposé au réseau

### Données sensibles
- **Token** : Stocké dans config.json (permissions 640)
- **Pas de secrets hardcodés** : Tout dans config.json
- **Logs** : Pas de tokens dans les logs

## Résilience

### Redémarrage automatique
- systemd redémarre le service si crash (Restart=always)
- Délai de 10s entre les tentatives (RestartSec=10)

### Autonomie en cas de perte backend
- L'agent continue avec sa configuration locale
- Tentatives de reconnexion automatiques (retry avec backoff)
- Pas de blocage si backend indisponible

### Gestion des erreurs
- Exceptions catchées et loggées
- Métriques collectées même si reporting échoue
- Bufferisation locale en cas de perte réseau (TODO)

## Installation et maintenance

### Installation
```bash
scripts/install.sh
```
- Crée utilisateur système
- Installe code dans /opt
- Configure systemd
- Active le service

### Mise à jour
```bash
# Arrêter le service
systemctl stop avmonitoring-agent

# Mettre à jour le code
cp -r nouvelle-version/src/* /opt/avmonitoring-agent/src/

# Mettre à jour les dépendances
/opt/avmonitoring-agent/venv/bin/pip install -r requirements.txt

# Redémarrer
systemctl start avmonitoring-agent
```

### Désinstallation
```bash
scripts/uninstall.sh
```
- Arrête et désactive le service
- Supprime le code
- Supprime l'utilisateur
- Option : conserver ou supprimer les données

## Performance et dimensionnement

### Ressources typiques
- **CPU** : < 5% (idle), < 20% (collecte)
- **RAM** : 50-100 MB
- **Disque** : < 10 MB (code + dépendances), < 100 MB (logs sur 30j)
- **Réseau** : < 1 KB/s en moyenne

### Capacité
- Jusqu'à 1000 devices par agent (testé)
- Intervalle de collecte : configurable (minimum 15s recommandé)

## Logs et monitoring

### Logs systemd
```bash
# Temps réel
journalctl -u avmonitoring-agent -f

# Dernières 100 lignes
journalctl -u avmonitoring-agent -n 100

# Filtrer les erreurs
journalctl -u avmonitoring-agent | grep ERROR
```

### Métriques applicatives
- Nombre de devices surveillés
- Taux de succès/échec par device
- Temps de collecte
- Statut de la connexion backend

## Dépendances externes

### Système
- Python 3.10+
- systemd
- OpenSSL/TLS (pour HTTPS)

### Python (requirements.txt)
- fastapi
- uvicorn
- requests
- pysnmp (optionnel, pour driver SNMP)
- jinja2 (templating)

## Points d'attention pour la production

### Pare-feu
- **Sortie** : Autoriser HTTPS vers le backend
- **Entrée** : Aucun port à ouvrir (interface locale uniquement)

### Supervision
- Monitorer le statut du service : `systemctl is-active avmonitoring-agent`
- Alerter si service down
- Monitorer les logs d'erreur
- Vérifier la connectivité backend

### Sauvegarde
- **Obligatoire** : `/etc/avmonitoring/config.json` (contient le token)
- **Optionnel** : `/var/lib/avmonitoring/` (données locales)
- **Non nécessaire** : `/opt/avmonitoring-agent/` (code, réinstallable)

### Rotation des logs
- Journald gère automatiquement la rotation
- Configurer la rétention dans `/etc/systemd/journald.conf`
- Exemple : `SystemMaxUse=200M` pour limiter à 200 MB

---

**Document technique destiné aux équipes d'exploitation et aux DSI**
