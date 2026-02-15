#!/usr/bin/env bash
# Script de sauvegarde de la base de données AV Monitoring Backend
# Usage: sudo ./backup.sh [destination_directory]

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Backup Base de Données AV Monitoring${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Vérifier qu'on est root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}✗ Ce script doit être exécuté en tant que root${NC}"
    echo "Usage: sudo $0 [destination_directory]"
    exit 1
fi

# Configuration
DB_NAME="avmvp_db"
DB_USER="avmvp_user"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${1:-/var/backups/avmonitoring}"
BACKUP_FILE="${BACKUP_DIR}/avmvp_db_${TIMESTAMP}.sql"
BACKUP_FILE_COMPRESSED="${BACKUP_FILE}.gz"

echo -e "${BLUE}Configuration :${NC}"
echo "  Base de données : ${DB_NAME}"
echo "  Utilisateur     : ${DB_USER}"
echo "  Destination     : ${BACKUP_DIR}"
echo ""

# Créer le répertoire de backup si nécessaire
if [ ! -d "$BACKUP_DIR" ]; then
    echo -e "${YELLOW}⚠${NC}  Création du répertoire ${BACKUP_DIR}..."
    mkdir -p "$BACKUP_DIR"
    chown avmvp:avmvp "$BACKUP_DIR"
    chmod 750 "$BACKUP_DIR"
fi

# Vérifier que PostgreSQL est actif
if ! systemctl is-active --quiet postgresql; then
    echo -e "${RED}✗ PostgreSQL n'est pas actif${NC}"
    echo "Démarrez PostgreSQL : sudo systemctl start postgresql"
    exit 1
fi

echo -e "${BLUE}Sauvegarde en cours...${NC}"

# Créer le dump
if sudo -u postgres pg_dump "$DB_NAME" > "$BACKUP_FILE" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Dump créé : ${BACKUP_FILE}"

    # Afficher la taille
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo -e "${GREEN}✓${NC} Taille : ${SIZE}"

    # Compresser le dump
    echo -e "${BLUE}Compression...${NC}"
    if gzip "$BACKUP_FILE"; then
        SIZE_COMPRESSED=$(du -h "$BACKUP_FILE_COMPRESSED" | cut -f1)
        echo -e "${GREEN}✓${NC} Backup compressé : ${BACKUP_FILE_COMPRESSED}"
        echo -e "${GREEN}✓${NC} Taille finale : ${SIZE_COMPRESSED}"

        # Ajuster les permissions
        chown avmvp:avmvp "$BACKUP_FILE_COMPRESSED"
        chmod 640 "$BACKUP_FILE_COMPRESSED"

        echo ""
        echo -e "${GREEN}========================================${NC}"
        echo -e "${GREEN}  Backup réussi !${NC}"
        echo -e "${GREEN}========================================${NC}"
        echo ""
        echo "Fichier : ${BACKUP_FILE_COMPRESSED}"
        echo ""
        echo "Pour restaurer ce backup :"
        echo "  sudo ./restore.sh ${BACKUP_FILE_COMPRESSED}"
        echo ""
    else
        echo -e "${YELLOW}⚠${NC}  Compression échouée, backup non compressé conservé"
        echo "Fichier : ${BACKUP_FILE}"
    fi
else
    echo -e "${RED}✗ Échec de la sauvegarde${NC}"
    echo "Vérifiez que la base de données existe :"
    echo "  sudo -u postgres psql -l | grep ${DB_NAME}"
    exit 1
fi

# Nettoyer les anciens backups (garder les 30 derniers jours)
echo -e "${BLUE}Nettoyage des anciens backups...${NC}"
find "$BACKUP_DIR" -name "avmvp_db_*.sql.gz" -type f -mtime +30 -delete 2>/dev/null || true
BACKUP_COUNT=$(find "$BACKUP_DIR" -name "avmvp_db_*.sql.gz" -type f | wc -l)
echo -e "${GREEN}✓${NC} Backups conservés : ${BACKUP_COUNT}"

echo ""
echo -e "${BLUE}Astuce :${NC} Planifiez des backups automatiques avec cron :"
echo "  # Backup quotidien à 2h du matin"
echo "  0 2 * * * /opt/avmonitoring-backend/backend/scripts/backup.sh"
echo ""
