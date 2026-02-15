#!/usr/bin/env bash
# Script de restauration de la base de données AV Monitoring Backend
# Usage: sudo ./restore.sh <backup_file.sql.gz>

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Restore Base de Données AV Monitoring${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Vérifier qu'on est root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}✗ Ce script doit être exécuté en tant que root${NC}"
    echo "Usage: sudo $0 <backup_file.sql.gz>"
    exit 1
fi

# Vérifier qu'un fichier de backup est fourni
if [ -z "$1" ]; then
    echo -e "${RED}✗ Fichier de backup manquant${NC}"
    echo ""
    echo "Usage: sudo $0 <backup_file.sql.gz>"
    echo ""
    echo "Backups disponibles :"
    find /var/backups/avmonitoring -name "avmvp_db_*.sql.gz" -type f -exec ls -lh {} \; 2>/dev/null | tail -10 || echo "  Aucun backup trouvé"
    echo ""
    exit 1
fi

BACKUP_FILE="$1"

# Vérifier que le fichier existe
if [ ! -f "$BACKUP_FILE" ]; then
    echo -e "${RED}✗ Fichier introuvable : ${BACKUP_FILE}${NC}"
    exit 1
fi

# Configuration
DB_NAME="avmvp_db"
DB_USER="avmvp_user"

echo -e "${BLUE}Configuration :${NC}"
echo "  Base de données : ${DB_NAME}"
echo "  Utilisateur     : ${DB_USER}"
echo "  Fichier backup  : ${BACKUP_FILE}"
SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "  Taille          : ${SIZE}"
echo ""

# Vérifier que PostgreSQL est actif
if ! systemctl is-active --quiet postgresql; then
    echo -e "${RED}✗ PostgreSQL n'est pas actif${NC}"
    echo "Démarrez PostgreSQL : sudo systemctl start postgresql"
    exit 1
fi

# Vérifier que la base de données existe
if ! sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
    echo -e "${RED}✗ La base de données ${DB_NAME} n'existe pas${NC}"
    echo "Créez-la d'abord avec le script d'installation"
    exit 1
fi

# ⚠️ AVERTISSEMENT
echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}  ⚠️  AVERTISSEMENT${NC}"
echo -e "${YELLOW}========================================${NC}"
echo ""
echo "Cette opération va :"
echo "  1. Arrêter le service backend"
echo "  2. SUPPRIMER toutes les données actuelles"
echo "  3. Restaurer les données du backup"
echo "  4. Redémarrer le service backend"
echo ""
echo -e "${YELLOW}Toutes les données actuelles seront perdues !${NC}"
echo ""

# Demander confirmation
read -p "Voulez-vous continuer ? (tapez 'oui' pour confirmer) : " CONFIRM

if [ "$CONFIRM" != "oui" ]; then
    echo ""
    echo -e "${BLUE}Restauration annulée.${NC}"
    exit 0
fi

echo ""
echo -e "${BLUE}Restauration en cours...${NC}"

# Étape 1 : Arrêter le service backend
echo -e "${BLUE}1/4${NC} Arrêt du service backend..."
if systemctl is-active --quiet avmonitoring-backend; then
    systemctl stop avmonitoring-backend
    echo -e "${GREEN}✓${NC} Service arrêté"
else
    echo -e "${YELLOW}⚠${NC}  Service déjà arrêté"
fi

# Étape 2 : Décompresser si nécessaire
TEMP_SQL="/tmp/avmvp_restore_$$.sql"

echo -e "${BLUE}2/4${NC} Préparation du fichier de restauration..."
if [[ "$BACKUP_FILE" == *.gz ]]; then
    gunzip -c "$BACKUP_FILE" > "$TEMP_SQL"
    echo -e "${GREEN}✓${NC} Fichier décompressé"
else
    cp "$BACKUP_FILE" "$TEMP_SQL"
    echo -e "${GREEN}✓${NC} Fichier copié"
fi

# Étape 3 : Restaurer la base de données
echo -e "${BLUE}3/4${NC} Restauration de la base de données..."

# Supprimer et recréer la base
sudo -u postgres psql -c "DROP DATABASE IF EXISTS ${DB_NAME};" 2>/dev/null
sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};" 2>/dev/null
echo -e "${GREEN}✓${NC} Base de données recréée"

# Importer le dump
if sudo -u postgres psql "$DB_NAME" < "$TEMP_SQL" >/dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Données restaurées"

    # Vérifier le nombre de tables
    TABLE_COUNT=$(sudo -u postgres psql -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" | tr -d ' ')
    echo -e "${GREEN}✓${NC} Tables restaurées : ${TABLE_COUNT}"
else
    echo -e "${RED}✗ Échec de la restauration${NC}"
    rm -f "$TEMP_SQL"
    exit 1
fi

# Nettoyer le fichier temporaire
rm -f "$TEMP_SQL"

# Étape 4 : Redémarrer le service backend
echo -e "${BLUE}4/4${NC} Redémarrage du service backend..."
systemctl start avmonitoring-backend

# Attendre que le service démarre
sleep 2

if systemctl is-active --quiet avmonitoring-backend; then
    echo -e "${GREEN}✓${NC} Service redémarré"
else
    echo -e "${RED}✗ Le service n'a pas démarré correctement${NC}"
    echo "Vérifiez les logs : sudo journalctl -u avmonitoring-backend -n 50"
    exit 1
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Restauration réussie !${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "La base de données a été restaurée depuis :"
echo "  ${BACKUP_FILE}"
echo ""
echo "Vérifiez que tout fonctionne :"
echo "  sudo systemctl status avmonitoring-backend"
echo "  sudo journalctl -u avmonitoring-backend -n 20"
echo ""
