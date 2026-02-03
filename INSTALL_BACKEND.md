# Installation Backend AV Monitoring - Ubuntu Fresh Install

Guide complet d'installation du backend AV Monitoring sur une machine Ubuntu fraîchement installée.

## Option 1 : Installation automatique (Recommandé)

### Sur votre machine locale

```bash
# Copier le script sur le serveur Ubuntu
scp install_backend_fresh.sh root@<IP_SERVEUR>:/root/
```

### Sur le serveur Ubuntu

```bash
# Se connecter en SSH
ssh root@<IP_SERVEUR>

# Exécuter le script
bash /root/install_backend_fresh.sh
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

# Se connecter à PostgreSQL
sudo -u postgres psql

# Dans psql, créer la base et l'utilisateur
CREATE USER avmvp_user WITH PASSWORD 'votre_mot_de_passe_securise';
CREATE DATABASE avmvp_db OWNER avmvp_user;
GRANT ALL PRIVILEGES ON DATABASE avmvp_db TO avmvp_user;
\q
```

**Note** : Remplacez `votre_mot_de_passe_securise` par un mot de passe fort.

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
from app.database import engine, Base
from app.models import Site, Device, Observation

Base.metadata.create_all(engine)
print("✓ Tables créées")
EOF
```

### 8. Appliquer les migrations

```bash
# Migration pour la synchronisation bidirectionnelle
sudo -u postgres psql -d avmvp_db -f /opt/av-monitoring-mvp/backend/migrations/add_driver_config_updated_at.sql
```

### 9. Créer le service systemd

```bash
sudo cat > /etc/systemd/system/avmonitoring-backend.service <<EOF
[Unit]
Description=AV Monitoring Backend API
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/av-monitoring-mvp/backend
Environment="PATH=/opt/av-monitoring-mvp/backend/venv/bin"
EnvironmentFile=/opt/av-monitoring-mvp/backend/.env
ExecStart=/opt/av-monitoring-mvp/backend/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Recharger et activer
sudo systemctl daemon-reload
sudo systemctl enable avmonitoring-backend
```

### 10. Démarrer le backend

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

## Configuration du pare-feu (optionnel)

Si vous utilisez ufw :

```bash
sudo ufw allow 8000/tcp comment "AV Monitoring Backend"
sudo ufw reload
```

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
python3 -c "from app.database import engine, Base; from app.models import *; Base.metadata.create_all(engine)"

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

## Architecture

```
┌─────────────────────────────────────┐
│   Ubuntu Server (Backend)           │
│                                      │
│  ┌────────────────────────────────┐ │
│  │  FastAPI (port 8000)           │ │
│  │  /opt/av-monitoring-mvp/backend│ │
│  └──────────┬─────────────────────┘ │
│             │                        │
│  ┌──────────▼─────────────────────┐ │
│  │  PostgreSQL (port 5432)        │ │
│  │  Database: avmvp_db            │ │
│  └────────────────────────────────┘ │
└─────────────────────────────────────┘
            ▲
            │ HTTP POST /ingest
            │
┌───────────┴─────────────────────────┐
│   Agents (machines distantes)       │
│   - Collectent données devices      │
│   - Envoient vers backend           │
└─────────────────────────────────────┘
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
