#!/usr/bin/env bash
# Installation Backend AV Monitoring
# Prérequis : repository déjà cloné dans /opt/av-monitoring-mvp
# Usage: sudo bash /opt/av-monitoring-mvp/backend/install.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Installation Backend AV Monitoring${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}✗ Exécuter en tant que root${NC}"
    exit 1
fi

BACKEND_DIR="/opt/av-monitoring-mvp/backend"
DB_NAME="avmvp_db"
DB_USER="avmvp_user"
DB_PASSWORD="avmvp_$(openssl rand -hex 8)"
BACKEND_PORT="8000"

# 1. Dépendances système
echo -e "${BLUE}[1/8]${NC} Installation dépendances système..."
apt-get update
apt-get install -y python3 python3-pip python3-venv postgresql postgresql-contrib
echo -e "${GREEN}✓${NC} Dépendances installées"

# 2. PostgreSQL
echo ""
echo -e "${BLUE}[2/8]${NC} Configuration PostgreSQL..."
systemctl start postgresql
systemctl enable postgresql

sudo -u postgres psql <<EOF
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_user WHERE usename = '${DB_USER}') THEN
        CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';
    END IF;
END \$\$;
DROP DATABASE IF EXISTS ${DB_NAME};
CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};
GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};
\q
EOF

cat > /root/backend_credentials.txt <<EOF
DB_NAME=${DB_NAME}
DB_USER=${DB_USER}
DB_PASSWORD=${DB_PASSWORD}
BACKEND_PORT=${BACKEND_PORT}
DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@localhost:5432/${DB_NAME}
EOF
chmod 600 /root/backend_credentials.txt
echo -e "${GREEN}✓${NC} PostgreSQL configuré (credentials: /root/backend_credentials.txt)"

# 3. Python venv
echo ""
echo -e "${BLUE}[3/8]${NC} Création environnement Python..."
cd "$BACKEND_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo -e "${GREEN}✓${NC} Python configuré"

# 4. Fichier .env
echo ""
echo -e "${BLUE}[4/8]${NC} Création fichier .env..."
cat > "$BACKEND_DIR/.env" <<EOF
DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@localhost:5432/${DB_NAME}
BACKEND_PORT=${BACKEND_PORT}
LOG_LEVEL=info
EOF
chmod 600 "$BACKEND_DIR/.env"
echo -e "${GREEN}✓${NC} Fichier .env créé"

# 5. Création tables
echo ""
echo -e "${BLUE}[5/8]${NC} Création tables base de données..."
cd "$BACKEND_DIR"
export PYTHONPATH="$BACKEND_DIR:$PYTHONPATH"
./venv/bin/python3 << 'PYEOF'
import sys
sys.path.insert(0, '/opt/av-monitoring-mvp/backend')
from app.database import engine, Base
from app.models import Site, Device, Observation
Base.metadata.create_all(engine)
print('Tables créées avec succès')
PYEOF
echo -e "${GREEN}✓${NC} Tables créées"

# 6. Migrations
echo ""
echo -e "${BLUE}[6/8]${NC} Application migrations..."
if [ -f "$BACKEND_DIR/migrations/add_driver_config_updated_at.sql" ]; then
    sudo -u postgres psql -d ${DB_NAME} -f "$BACKEND_DIR/migrations/add_driver_config_updated_at.sql"
    echo -e "${GREEN}✓${NC} Migration appliquée"
else
    echo -e "${YELLOW}⚠${NC} Fichier migration non trouvé (skip)"
fi

# 7. Service systemd
echo ""
echo -e "${BLUE}[7/8]${NC} Configuration service systemd..."
cat > /etc/systemd/system/avmonitoring-backend.service <<EOF
[Unit]
Description=AV Monitoring Backend API
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=${BACKEND_DIR}
Environment="PATH=${BACKEND_DIR}/venv/bin"
EnvironmentFile=${BACKEND_DIR}/.env
ExecStart=${BACKEND_DIR}/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port ${BACKEND_PORT}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable avmonitoring-backend
echo -e "${GREEN}✓${NC} Service créé"

# 8. Démarrage
echo ""
echo -e "${BLUE}[8/8]${NC} Démarrage backend..."
systemctl start avmonitoring-backend
sleep 5

if systemctl is-active --quiet avmonitoring-backend; then
    echo -e "${GREEN}✓${NC} Backend démarré"
else
    echo -e "${RED}✗${NC} Erreur démarrage"
    journalctl -u avmonitoring-backend -n 30 --no-pager
    exit 1
fi

# Tests
echo ""
echo "Vérification API..."
sleep 5
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:${BACKEND_PORT}/docs 2>/dev/null || echo "000")
if [ "$RESPONSE" = "200" ]; then
    echo -e "${GREEN}✓${NC} API répond"
else
    echo -e "${YELLOW}⚠${NC} API code HTTP: $RESPONSE"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✓ Installation terminée !${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Backend AV Monitoring installé"
echo ""
echo "Informations:"
echo "  - URL: http://$(hostname -I | awk '{print $1}'):${BACKEND_PORT}/docs"
echo "  - Credentials: /root/backend_credentials.txt"
echo ""
echo "Commandes utiles:"
echo "  - Logs: journalctl -u avmonitoring-backend -f"
echo "  - Restart: systemctl restart avmonitoring-backend"
echo "  - Status: systemctl status avmonitoring-backend"
echo ""
