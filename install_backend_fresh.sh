#!/usr/bin/env bash
# Script d'installation complète du backend AV Monitoring sur Ubuntu fraîche
# Usage: sudo bash install_backend_fresh.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Installation Backend AV Monitoring${NC}"
echo -e "${BLUE}  Ubuntu Fresh Install${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Vérifier qu'on est root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}✗ Ce script doit être exécuté en tant que root${NC}"
    echo "Usage: sudo bash $0"
    exit 1
fi

# Variables
BACKEND_DIR="/opt/avmonitoring-mvp"
DB_NAME="avmvp_db"
DB_USER="avmvp_user"
DB_PASSWORD="avmvp_secure_password_$(openssl rand -hex 8)"
BACKEND_PORT="8000"

# ------------------------------------------------------------
# 1. Mise à jour du système
# ------------------------------------------------------------
echo -e "${BLUE}[1/10]${NC} Mise à jour du système..."
apt-get update
apt-get upgrade -y
echo -e "${GREEN}✓${NC} Système à jour"

# ------------------------------------------------------------
# 2. Installation des dépendances système
# ------------------------------------------------------------
echo ""
echo -e "${BLUE}[2/10]${NC} Installation des dépendances système..."
apt-get install -y \
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

echo -e "${GREEN}✓${NC} Dépendances installées"

# ------------------------------------------------------------
# 3. Configuration PostgreSQL
# ------------------------------------------------------------
echo ""
echo -e "${BLUE}[3/10]${NC} Configuration de PostgreSQL..."

# Démarrer PostgreSQL
systemctl start postgresql
systemctl enable postgresql

# Créer la base de données et l'utilisateur
sudo -u postgres psql <<EOF
-- Créer l'utilisateur s'il n'existe pas, sinon mettre à jour le mot de passe
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_user WHERE usename = '${DB_USER}') THEN
        CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';
    ELSE
        ALTER USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';
    END IF;
END
\$\$;

-- Créer la base de données
DROP DATABASE IF EXISTS ${DB_NAME};
CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};

-- Donner tous les privilèges
GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};
EOF

echo -e "${GREEN}✓${NC} PostgreSQL configuré"
echo "   Database: ${DB_NAME}"
echo "   User: ${DB_USER}"
echo "   Password: ${DB_PASSWORD}"

# Sauvegarder les credentials
cat > /root/backend_credentials.txt <<EOF
# Credentials Backend AV Monitoring
DB_NAME=${DB_NAME}
DB_USER=${DB_USER}
DB_PASSWORD=${DB_PASSWORD}
DB_HOST=localhost
DB_PORT=5432
BACKEND_PORT=${BACKEND_PORT}
EOF

chmod 600 /root/backend_credentials.txt
echo -e "${GREEN}✓${NC} Credentials sauvegardés dans /root/backend_credentials.txt"

# ------------------------------------------------------------
# 4. Clonage du repository
# ------------------------------------------------------------
echo ""
echo -e "${BLUE}[4/10]${NC} Clonage du repository..."

if [ -d "$BACKEND_DIR" ]; then
    echo -e "${YELLOW}⚠${NC} Répertoire $BACKEND_DIR existe déjà"
    read -p "Voulez-vous le supprimer et réinstaller? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$BACKEND_DIR"
    else
        echo "Installation annulée"
        exit 1
    fi
fi

mkdir -p /opt
cd /opt

# Cloner le repository
git clone https://github.com/CedricNCoding/av-monitoring-mvp
cd av-monitoring-mvp

# Configurer git remote
git remote remove origin 2>/dev/null || true
git remote add av-monitoring-mvp https://github.com/CedricNCoding/av-monitoring-mvp
git fetch av-monitoring-mvp

echo -e "${GREEN}✓${NC} Repository cloné dans $BACKEND_DIR"

# ------------------------------------------------------------
# 5. Installation des dépendances Python (backend)
# ------------------------------------------------------------
echo ""
echo -e "${BLUE}[5/10]${NC} Installation des dépendances Python..."

cd "$BACKEND_DIR/backend"

# Créer environnement virtuel
python3 -m venv venv

# Activer et installer dépendances
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo -e "${GREEN}✓${NC} Dépendances Python installées"

# ------------------------------------------------------------
# 6. Configuration du backend
# ------------------------------------------------------------
echo ""
echo -e "${BLUE}[6/10]${NC} Configuration du backend..."

# Créer fichier .env
cat > "$BACKEND_DIR/backend/.env" <<EOF
# Backend Configuration
DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@localhost:5432/${DB_NAME}
BACKEND_PORT=${BACKEND_PORT}
LOG_LEVEL=info
EOF

chmod 600 "$BACKEND_DIR/backend/.env"

echo -e "${GREEN}✓${NC} Fichier .env créé"

# ------------------------------------------------------------
# 7. Création des tables de base de données
# ------------------------------------------------------------
echo ""
echo -e "${BLUE}[7/10]${NC} Création des tables de base de données..."

# Vérifier si le fichier d'initialisation existe
if [ -f "$BACKEND_DIR/backend/app/database.py" ] && [ -f "$BACKEND_DIR/backend/app/models.py" ]; then
    # Créer les tables via Python
    cd "$BACKEND_DIR/backend"
    source venv/bin/activate

    python3 <<EOF
import sys
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

try:
    Base.metadata.create_all(engine)
    print("✓ Tables créées avec succès")
    sys.exit(0)
except Exception as e:
    print(f"✗ Erreur lors de la création des tables: {e}")
    sys.exit(1)
EOF

    echo -e "${GREEN}✓${NC} Tables de base de données créées"
else
    echo -e "${YELLOW}⚠${NC} Fichiers de modèles non trouvés, skip création des tables"
fi

# Appliquer la migration pour driver_config_updated_at
if [ -f "$BACKEND_DIR/backend/migrations/add_driver_config_updated_at.sql" ]; then
    echo "Application de la migration driver_config_updated_at..."
    sudo -u postgres psql -d ${DB_NAME} -f "$BACKEND_DIR/backend/migrations/add_driver_config_updated_at.sql"
    echo -e "${GREEN}✓${NC} Migration appliquée"
fi

# ------------------------------------------------------------
# 8. Création du service systemd
# ------------------------------------------------------------
echo ""
echo -e "${BLUE}[8/10]${NC} Création du service systemd..."

cat > /etc/systemd/system/avmonitoring-backend.service <<EOF
[Unit]
Description=AV Monitoring Backend API
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=${BACKEND_DIR}/backend
Environment="PATH=${BACKEND_DIR}/backend/venv/bin"
EnvironmentFile=${BACKEND_DIR}/backend/.env
ExecStart=${BACKEND_DIR}/backend/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port ${BACKEND_PORT}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Recharger systemd
systemctl daemon-reload
systemctl enable avmonitoring-backend

echo -e "${GREEN}✓${NC} Service systemd créé"

# ------------------------------------------------------------
# 9. Démarrage du backend
# ------------------------------------------------------------
echo ""
echo -e "${BLUE}[9/10]${NC} Démarrage du backend..."

systemctl start avmonitoring-backend
sleep 3

# Vérifier le statut
if systemctl is-active --quiet avmonitoring-backend; then
    echo -e "${GREEN}✓${NC} Backend démarré avec succès"
else
    echo -e "${RED}✗ Backend n'a pas démarré correctement${NC}"
    echo "Logs:"
    journalctl -u avmonitoring-backend -n 20 --no-pager
    exit 1
fi

# ------------------------------------------------------------
# 10. Vérification et tests
# ------------------------------------------------------------
echo ""
echo -e "${BLUE}[10/10]${NC} Vérification et tests..."

# Attendre que le backend soit prêt
echo "Attente du démarrage complet (10 secondes)..."
sleep 10

# Test de l'API
echo "Test de l'API backend..."
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:${BACKEND_PORT}/docs || echo "000")

if [ "$RESPONSE" = "200" ]; then
    echo -e "${GREEN}✓${NC} API backend répond correctement"
else
    echo -e "${YELLOW}⚠${NC} API backend ne répond pas comme attendu (code: $RESPONSE)"
    echo "Vérifiez manuellement: http://$(hostname -I | awk '{print $1}'):${BACKEND_PORT}/docs"
fi

# Test de la base de données
echo "Test de la connexion à la base de données..."
sudo -u postgres psql -d ${DB_NAME} -c "SELECT 1;" > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Connexion à la base de données OK"
else
    echo -e "${RED}✗ Problème de connexion à la base de données${NC}"
fi

# ------------------------------------------------------------
# Résumé
# ------------------------------------------------------------
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ Installation terminée !${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "Backend AV Monitoring installé avec succès"
echo ""
echo "Informations importantes:"
echo "  - URL API: http://$(hostname -I | awk '{print $1}'):${BACKEND_PORT}"
echo "  - Documentation API: http://$(hostname -I | awk '{print $1}'):${BACKEND_PORT}/docs"
echo "  - Base de données: ${DB_NAME}"
echo "  - Utilisateur DB: ${DB_USER}"
echo "  - Credentials: /root/backend_credentials.txt"
echo ""
echo "Commandes utiles:"
echo "  - Voir les logs: journalctl -u avmonitoring-backend -f"
echo "  - Redémarrer: systemctl restart avmonitoring-backend"
echo "  - Statut: systemctl status avmonitoring-backend"
echo "  - Arrêter: systemctl stop avmonitoring-backend"
echo ""
echo "Prochaines étapes:"
echo "  1. Tester l'API: curl http://localhost:${BACKEND_PORT}/docs"
echo "  2. Créer un site via l'API ou l'interface web"
echo "  3. Installer l'agent sur les machines à monitorer"
echo ""

# Afficher les logs récents
echo "Logs récents du backend:"
echo "------------------------"
journalctl -u avmonitoring-backend -n 15 --no-pager | tail -10

echo ""
echo -e "${GREEN}Installation réussie !${NC}"
