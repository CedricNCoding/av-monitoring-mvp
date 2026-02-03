#!/usr/bin/env bash
# Script de mise à jour du backend avec support sync bidirectionnelle
# Usage: bash deploy_backend_update.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Mise à jour Backend AV Monitoring${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Vérifier qu'on est root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}✗ Ce script doit être exécuté en tant que root${NC}"
    exit 1
fi

BACKEND_DIR="/opt/avmonitoring-mvp/backend"

# 1. Vérifier que le backend est installé
if [ ! -d "$BACKEND_DIR" ]; then
    echo -e "${RED}✗ Backend non trouvé dans $BACKEND_DIR${NC}"
    echo "Voulez-vous faire une installation complète?"
    exit 1
fi

cd "$BACKEND_DIR"

# 2. Backup de la base de données
echo -e "${BLUE}[1/6]${NC} Backup de la base de données..."
BACKUP_FILE="/tmp/avmvp_backup_$(date +%Y%m%d_%H%M%S).sql"
sudo -u postgres pg_dump avmvp_db > "$BACKUP_FILE"
echo -e "${GREEN}✓${NC} Backup créé: $BACKUP_FILE"

# 3. Arrêter le backend
echo ""
echo -e "${BLUE}[2/6]${NC} Arrêt du backend..."
systemctl stop avmonitoring-backend
echo -e "${GREEN}✓${NC} Backend arrêté"

# 4. Pull les derniers changements
echo ""
echo -e "${BLUE}[3/6]${NC} Récupération des derniers changements..."
if [ -d ".git" ]; then
    # Stash les modifications locales
    git stash 2>/dev/null || true

    # Pull
    git pull av-monitoring-mvp main
    echo -e "${GREEN}✓${NC} Code mis à jour"

    # Restaurer les modifications locales si nécessaire
    git stash pop 2>/dev/null || true
else
    echo -e "${YELLOW}⚠${NC} Pas un repository git"
fi

# 5. Appliquer la migration SQL
echo ""
echo -e "${BLUE}[4/6]${NC} Application de la migration SQL..."
if [ -f "migrations/add_driver_config_updated_at.sql" ]; then
    sudo -u postgres psql -d avmvp_db -f migrations/add_driver_config_updated_at.sql
    echo -e "${GREEN}✓${NC} Migration appliquée"
else
    echo -e "${YELLOW}⚠${NC} Fichier de migration non trouvé"
fi

# 6. Démarrer le backend
echo ""
echo -e "${BLUE}[5/6]${NC} Démarrage du backend..."
systemctl start avmonitoring-backend
sleep 3

# 7. Vérifier le statut
echo ""
echo -e "${BLUE}[6/6]${NC} Vérification du statut..."
if systemctl is-active --quiet avmonitoring-backend; then
    echo -e "${GREEN}✓${NC} Backend démarré avec succès"
else
    echo -e "${RED}✗ Backend n'a pas démarré correctement${NC}"
    echo "Logs:"
    journalctl -u avmonitoring-backend -n 20 --no-pager
    exit 1
fi

# 8. Vérifier les logs récents
echo ""
echo "Logs récents du backend:"
echo "------------------------"
journalctl -u avmonitoring-backend -n 10 --no-pager | grep -E "Started|ERROR|WARNING" || true

# 9. Test de l'API
echo ""
echo "Test de l'API backend..."
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} API backend répond"
else
    echo -e "${YELLOW}⚠${NC} API backend ne répond pas (peut être normal si endpoint /health n'existe pas)"
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ Mise à jour terminée !${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "Backup de la base de données: $BACKUP_FILE"
echo ""
echo "Commandes utiles:"
echo "  - Voir les logs: journalctl -u avmonitoring-backend -f"
echo "  - Redémarrer: systemctl restart avmonitoring-backend"
echo "  - Statut: systemctl status avmonitoring-backend"
echo ""
