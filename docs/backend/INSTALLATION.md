# Installation Backend AV Monitoring - Ubuntu Fresh Install

Guide complet d'installation du backend AV Monitoring sur une machine Ubuntu fraîchement installée.

**⚠️ Important** : Cette installation utilise une approche **native** (Python + systemd) et **non Docker**.
- ✅ Plus sécurisée (PostgreSQL et backend non exposés)
- ✅ Plus simple (pas de gestion de conteneurs)
- ✅ Meilleure performance
- ✅ Mises à jour sécurité via `apt`

**Architecture** : Traefik (reverse proxy) → Backend systemd (localhost:8000) → PostgreSQL (localhost:5432)

## Option 1 : Installation automatique (Recommandé)

### Sur votre machine locale

```bash
# Cloner le dépôt ou télécharger l'archive
git clone https://github.com/CedricNCoding/av-monitoring-mvp.git
cd av-monitoring-mvp

# Copier le projet sur le serveur Ubuntu
scp -r . root@<IP_SERVEUR>:/root/av-monitoring-mvp/
```

### Sur le serveur Ubuntu

```bash
# Se connecter en SSH
ssh root@<IP_SERVEUR>

# Exécuter le script d'installation
cd /root/av-monitoring-mvp/backend/scripts
bash ./install.sh
```

Le script va :
1. ✅ Mettre à jour le système
2. ✅ Installer Python, PostgreSQL, Git, etc.
3. ✅ Configurer PostgreSQL avec une base de données dédiée
4. ✅ Cloner le repository
5. ✅ Installer les dépendances Python
6. ✅ Créer les tables de base de données
7. ✅ Configurer le service systemd
8. ✅ Démarrer le backend
9. ✅ Vérifier que tout fonctionne

**Durée estimée : 5-10 minutes**

---

## Option 2 : Installation manuelle

Si vous préférez comprendre chaque étape ou si le script échoue :

### 1. Mise à jour du système

```bash
sudo apt-get update
sudo apt-get upgrade -y
```

### 2. Installation des dépendances

```bash
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    postgresql \
    postgresql-contrib \
    git \
    curl \
    vim \
    htop \
    net-tools
```

### 3. Configuration PostgreSQL

```bash
# Démarrer PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Sécuriser PostgreSQL (écoute uniquement sur localhost)
sudo sed -i "s/#listen_addresses = 'localhost'/listen_addresses = 'localhost'/g" /etc/postgresql/*/main/postgresql.conf
sudo sed -i "s/listen_addresses = '\*'/listen_addresses = 'localhost'/g" /etc/postgresql/*/main/postgresql.conf

# Redémarrer pour appliquer
sudo systemctl restart postgresql

# Se connecter à PostgreSQL
sudo -u postgres psql

# Dans psql, créer la base et l'utilisateur
CREATE USER avmvp_user WITH PASSWORD 'votre_mot_de_passe_securise';
CREATE DATABASE avmvp_db OWNER avmvp_user;
GRANT ALL PRIVILEGES ON DATABASE avmvp_db TO avmvp_user;
\c avmvp_db
GRANT ALL ON SCHEMA public TO avmvp_user;
\q
```

**Note** : Remplacez `votre_mot_de_passe_securise` par un mot de passe fort.

**Sécurité** : PostgreSQL écoute maintenant UNIQUEMENT sur localhost (pas accessible depuis Internet).

### 4. Cloner le repository

```bash
cd /opt
sudo git clone https://github.com/CedricNCoding/av-monitoring-mvp
cd av-monitoring-mvp

# Configurer le remote
sudo git remote remove origin 2>/dev/null || true
sudo git remote add av-monitoring-mvp https://github.com/CedricNCoding/av-monitoring-mvp
```

### 5. Configurer l'environnement Python

```bash
cd /opt/av-monitoring-mvp/backend

# Créer l'environnement virtuel
python3 -m venv venv

# Activer l'environnement
source venv/bin/activate

# Installer les dépendances
pip install --upgrade pip
pip install -r requirements.txt
```

### 6. Créer le fichier .env

```bash
cd /opt/av-monitoring-mvp/backend

cat > .env <<EOF
DATABASE_URL=postgresql://avmvp_user:votre_mot_de_passe_securise@localhost:5432/avmvp_db
BACKEND_PORT=8000
LOG_LEVEL=info
EOF

chmod 600 .env
```

**Note** : Remplacez le mot de passe par celui choisi à l'étape 3.

### 7. Créer les tables de base de données

```bash
cd /opt/av-monitoring-mvp/backend
source venv/bin/activate

python3 <<EOF
import os
from pathlib import Path

# Charger le fichier .env
env_file = Path('.env')
if env_file.exists():
    for line in env_file.read_text().strip().split('\n'):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ[key.strip()] = value.strip()

from app.db import engine, Base
from app.models import *

Base.metadata.create_all(engine)
print("✓ Tables créées")
EOF
```

### 8. Créer un utilisateur système dédié (SÉCURITÉ)

```bash
# Créer un utilisateur non-privilégié pour le backend
sudo useradd -r -s /bin/false -d /opt/av-monitoring-mvp -M avmvp

# Donner les permissions sur le dossier
sudo chown -R avmvp:avmvp /opt/av-monitoring-mvp

# Sécuriser le fichier .env
sudo chmod 600 /opt/av-monitoring-mvp/backend/.env
sudo chown avmvp:avmvp /opt/av-monitoring-mvp/backend/.env
```

**Sécurité** : Le backend tournera avec un utilisateur non-root sans shell (principe du moindre privilège).

### 9. Créer le service systemd

```bash
sudo cat > /etc/systemd/system/avmonitoring-backend.service <<EOF
[Unit]
Description=AV Monitoring Backend API
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=avmvp
Group=avmvp
WorkingDirectory=/opt/av-monitoring-mvp/backend
Environment="PATH=/opt/av-monitoring-mvp/backend/venv/bin"
EnvironmentFile=/opt/av-monitoring-mvp/backend/.env

# Écouter UNIQUEMENT sur localhost (Traefik gère le reverse proxy)
ExecStart=/opt/av-monitoring-mvp/backend/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers

Restart=always
RestartSec=10

# Sécurité renforcée
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/av-monitoring-mvp/backend

[Install]
WantedBy=multi-user.target
EOF

# Recharger et activer
sudo systemctl daemon-reload
sudo systemctl enable avmonitoring-backend
```

**Sécurité** :
- Service tourne avec l'utilisateur `avmvp` (non-root)
- Écoute uniquement sur `127.0.0.1` (localhost) - Traefik gère le reverse proxy
- Directives de sécurité systemd activées (`NoNewPrivileges`, `ProtectSystem`, etc.)

### 11. Démarrer le backend

```bash
sudo systemctl start avmonitoring-backend

# Vérifier le statut
sudo systemctl status avmonitoring-backend

# Voir les logs
journalctl -u avmonitoring-backend -f
```

### 11. Tester l'installation

```bash
# Test de l'API
curl http://localhost:8000/docs

# Doit retourner la page HTML de la documentation Swagger
```

Ouvrez dans un navigateur : `http://<IP_SERVEUR>:8000/docs`

---

## Configuration Traefik (Reverse Proxy)

Le backend écoute uniquement sur `127.0.0.1:8000`. Traefik doit faire le reverse proxy.

### Configuration Traefik

Si Traefik n'est pas encore installé :

```bash
# Installer Traefik
sudo apt install traefik -y

# OU via Docker (si vous utilisez Traefik en conteneur)
# Voir la documentation Traefik pour l'installation
```

### Configuration pour le backend AV Monitoring

**Fichier de configuration dynamique** (`/etc/traefik/dynamic/avmonitoring.yml` ou via labels Docker) :

```yaml
http:
  routers:
    avmonitoring-backend:
      rule: "Host(`avmonitoring.rouni.eu`)"
      entryPoints:
        - websecure
      service: avmonitoring-backend
      tls:
        certResolver: letsencrypt

  services:
    avmonitoring-backend:
      loadBalancer:
        servers:
          - url: "http://127.0.0.1:8000"
```

**OU si Traefik est en Docker avec le backend en systemd** :

Créer un fichier de configuration dynamique :

```bash
sudo mkdir -p /etc/traefik/dynamic
sudo cat > /etc/traefik/dynamic/avmonitoring.yml <<EOF
http:
  routers:
    avmonitoring:
      rule: "Host(\`avmonitoring.rouni.eu\`)"
      entryPoints:
        - websecure
      service: avmonitoring-service
      tls:
        certResolver: letsencrypt

  services:
    avmonitoring-service:
      loadBalancer:
        servers:
          - url: "http://host.docker.internal:8000"
EOF
```

**Note** : Utilisez `host.docker.internal:8000` si Traefik est en Docker, sinon `127.0.0.1:8000`.

### Vérifier la configuration

```bash
# Tester que le backend répond en local
curl http://127.0.0.1:8000/health

# Doit retourner : {"ok": true, ...}

# Tester via Traefik (depuis l'extérieur)
curl https://avmonitoring.rouni.eu/health

# Doit retourner : {"ok": true, ...}
```

---

## Configuration du pare-feu (IMPORTANT)

Configuration sécurisée du pare-feu :

```bash
# Installer ufw si nécessaire
sudo apt install ufw -y

# Autoriser SSH (IMPORTANT : à faire avant d'activer le firewall !)
sudo ufw allow 22/tcp comment "SSH"

# Autoriser HTTP/HTTPS pour Traefik
sudo ufw allow 80/tcp comment "HTTP Traefik"
sudo ufw allow 443/tcp comment "HTTPS Traefik"

# NE PAS exposer le port 8000 (backend accessible uniquement en localhost)
# NE PAS exposer le port 5432 (PostgreSQL accessible uniquement en localhost)

# Bloquer tout le reste par défaut
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Activer le firewall
sudo ufw --force enable

# Vérifier les règles
sudo ufw status verbose
```

**Sécurité** :
- ✅ Port 8000 (backend) NON exposé - accessible uniquement via localhost
- ✅ Port 5432 (PostgreSQL) NON exposé - accessible uniquement via localhost
- ✅ Seuls HTTP/HTTPS (Traefik) et SSH sont accessibles depuis Internet

---

## Commandes utiles

### Gestion du service

```bash
# Démarrer
sudo systemctl start avmonitoring-backend

# Arrêter
sudo systemctl stop avmonitoring-backend

# Redémarrer
sudo systemctl restart avmonitoring-backend

# Statut
sudo systemctl status avmonitoring-backend

# Activer au démarrage
sudo systemctl enable avmonitoring-backend

# Désactiver au démarrage
sudo systemctl disable avmonitoring-backend
```

### Logs

```bash
# Logs en temps réel
journalctl -u avmonitoring-backend -f

# 100 dernières lignes
journalctl -u avmonitoring-backend -n 100

# Logs depuis aujourd'hui
journalctl -u avmonitoring-backend --since today
```

### Base de données

```bash
# Se connecter à la base
sudo -u postgres psql -d avmvp_db

# Lister les tables
\dt

# Voir le nombre de sites
SELECT COUNT(*) FROM sites;

# Voir le nombre de devices
SELECT COUNT(*) FROM devices;

# Voir les dernières observations
SELECT * FROM observations ORDER BY ts DESC LIMIT 10;
```

### Mise à jour du code

```bash
cd /opt/av-monitoring-mvp/backend

# Arrêter le backend
sudo systemctl stop avmonitoring-backend

# Pull les derniers changements
git stash  # Si modifications locales
git pull av-monitoring-mvp main
git stash pop  # Restaurer modifications locales

# Réinstaller les dépendances (si requirements.txt a changé)
source venv/bin/activate
pip install -r requirements.txt

# Redémarrer
sudo systemctl start avmonitoring-backend
```

---

## Dépannage

### Le backend ne démarre pas

```bash
# Vérifier les logs
journalctl -u avmonitoring-backend -n 50

# Vérifier le fichier .env
cat /opt/av-monitoring-mvp/backend/.env

# Tester manuellement
cd /opt/av-monitoring-mvp/backend
source venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Erreur de connexion PostgreSQL

```bash
# Vérifier que PostgreSQL tourne
sudo systemctl status postgresql

# Tester la connexion
sudo -u postgres psql -d avmvp_db -c "SELECT 1;"

# Vérifier les credentials dans .env
grep DATABASE_URL /opt/av-monitoring-mvp/backend/.env
```

### Port 8000 déjà utilisé

```bash
# Voir ce qui utilise le port
sudo netstat -tlnp | grep 8000

# Ou avec ss
sudo ss -tlnp | grep 8000

# Modifier le port dans .env
sudo nano /opt/av-monitoring-mvp/backend/.env
# Changer BACKEND_PORT=8000 en BACKEND_PORT=8001 (ou autre)

# Redémarrer
sudo systemctl restart avmonitoring-backend
```

### Réinitialiser la base de données

**⚠️ ATTENTION : Ceci supprime toutes les données**

```bash
sudo -u postgres psql <<EOF
DROP DATABASE IF EXISTS avmvp_db;
CREATE DATABASE avmvp_db OWNER avmvp_user;
GRANT ALL PRIVILEGES ON DATABASE avmvp_db TO avmvp_user;
EOF

# Recréer les tables
cd /opt/av-monitoring-mvp/backend
source venv/bin/activate

# Charger .env et créer les tables
python3 <<EOF
import os
from pathlib import Path

# Charger le fichier .env
env_file = Path('.env')
if env_file.exists():
    for line in env_file.read_text().strip().split('\n'):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ[key.strip()] = value.strip()

from app.db import engine, Base
from app.models import *
Base.metadata.create_all(engine)
EOF

# Appliquer les migrations
sudo -u postgres psql -d avmvp_db -f migrations/add_driver_config_updated_at.sql
```

---

## Prochaines étapes

Une fois le backend installé et fonctionnel :

1. **Créer un site** via l'API ou l'interface web
2. **Noter le site_token** généré
3. **Installer l'agent** sur les machines à monitorer
4. **Configurer l'agent** avec le site_token et l'URL du backend

---

## Architecture sécurisée

```
Internet
   │
   │ HTTPS (443)
   ▼
┌────────────────────────────────────────────┐
│  Traefik (Reverse Proxy + SSL)            │
│  - Gère HTTPS/certificats                  │
│  - Peut ajouter Cloudflare Zero Trust      │
└──────────────┬─────────────────────────────┘
               │ HTTP (localhost)
               ▼
┌─────────────────────────────────────┐
│   Ubuntu Server (Backend)           │
│                                      │
│  ┌────────────────────────────────┐ │
│  │  FastAPI (127.0.0.1:8000)      │ │
│  │  User: avmvp (non-root)        │ │
│  │  /opt/av-monitoring-mvp/backend│ │
│  └──────────┬─────────────────────┘ │
│             │ localhost             │
│  ┌──────────▼─────────────────────┐ │
│  │  PostgreSQL (localhost:5432)   │ │
│  │  Database: avmvp_db            │ │
│  │  User: avmvp_user              │ │
│  └────────────────────────────────┘ │
└─────────────────────────────────────┘
            ▲
            │ HTTPS POST /ingest
            │
┌───────────┴─────────────────────────┐
│   Agents (machines distantes)       │
│   - Collectent données devices      │
│   - Envoient vers backend via HTTPS │
└─────────────────────────────────────┘

Sécurité :
✅ Backend écoute UNIQUEMENT sur localhost (pas exposé directement)
✅ PostgreSQL écoute UNIQUEMENT sur localhost (pas accessible Internet)
✅ Firewall bloque tout sauf 22, 80, 443
✅ Service backend tourne en user non-root (avmvp)
✅ Traefik gère SSL/TLS et reverse proxy
```

---

## Support

En cas de problème :
1. Vérifier les logs : `journalctl -u avmonitoring-backend -n 100`
2. Vérifier le statut : `systemctl status avmonitoring-backend`
3. Tester l'API : `curl http://localhost:8000/docs`
4. Vérifier PostgreSQL : `sudo systemctl status postgresql`

---

**Version** : 1.0
**Date** : 2026-02-03
