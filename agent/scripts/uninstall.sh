#!/bin/bash
set -e

# Couleurs pour l'affichage
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="avmonitoring-agent"
APP_USER="avmonitoring"
APP_GROUP="avmonitoring"
INSTALL_DIR="/opt/${APP_NAME}"
CONFIG_DIR="/etc/avmonitoring"
DATA_DIR="/var/lib/avmonitoring"
LOG_DIR="/var/log/avmonitoring"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"

echo -e "${RED}═══════════════════════════════════════════════════════${NC}"
echo -e "${RED}  Désinstallation de l'agent AV Monitoring${NC}"
echo -e "${RED}═══════════════════════════════════════════════════════${NC}"
echo ""

# Vérifier que le script est exécuté en root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}✗${NC} Ce script doit être exécuté avec les privilèges root (sudo)"
    exit 1
fi

# Demander confirmation
echo -e "${YELLOW}⚠  ATTENTION : Cette opération va :${NC}"
echo "   - Arrêter et désactiver le service"
echo "   - Supprimer le code de l'application"
echo "   - Supprimer l'utilisateur système"
echo ""
echo -e "${YELLOW}⚠  Les données suivantes seront CONSERVÉES :${NC}"
echo "   - Configuration : $CONFIG_DIR"
echo "   - Données       : $DATA_DIR"
echo "   - Logs          : $LOG_DIR"
echo ""
read -p "Voulez-vous continuer ? (oui/non) : " -r
echo
if [[ ! $REPLY =~ ^[Oo][Uu][Ii]$ ]]; then
    echo "Désinstallation annulée."
    exit 0
fi

# Arrêter le service s'il est en cours d'exécution
echo -e "${YELLOW}➤${NC} Arrêt du service..."
if systemctl is-active --quiet "$APP_NAME"; then
    systemctl stop "$APP_NAME"
    echo -e "${GREEN}✓${NC} Service arrêté"
else
    echo -e "${GREEN}✓${NC} Service déjà arrêté"
fi

# Désactiver le service
echo -e "${YELLOW}➤${NC} Désactivation du service..."
if systemctl is-enabled --quiet "$APP_NAME"; then
    systemctl disable "$APP_NAME"
    echo -e "${GREEN}✓${NC} Service désactivé"
else
    echo -e "${GREEN}✓${NC} Service déjà désactivé"
fi

# Supprimer le fichier de service
echo -e "${YELLOW}➤${NC} Suppression du service systemd..."
if [ -f "$SERVICE_FILE" ]; then
    rm -f "$SERVICE_FILE"
    systemctl daemon-reload
    echo -e "${GREEN}✓${NC} Service systemd supprimé"
else
    echo -e "${GREEN}✓${NC} Fichier de service déjà supprimé"
fi
echo ""

# Supprimer les fichiers de l'application
echo -e "${YELLOW}➤${NC} Suppression des fichiers de l'application..."
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    echo -e "${GREEN}✓${NC} Répertoire d'installation supprimé"
else
    echo -e "${GREEN}✓${NC} Répertoire d'installation déjà supprimé"
fi
echo ""

# Supprimer l'utilisateur système
echo -e "${YELLOW}➤${NC} Suppression de l'utilisateur système..."
if id "$APP_USER" &>/dev/null; then
    userdel "$APP_USER"
    echo -e "${GREEN}✓${NC} Utilisateur $APP_USER supprimé"
else
    echo -e "${GREEN}✓${NC} Utilisateur déjà supprimé"
fi
echo ""

# Proposer la suppression des données
echo -e "${YELLOW}➤${NC} Gestion des données..."
echo ""
read -p "Voulez-vous également supprimer la configuration et les données ? (oui/non) : " -r
echo
if [[ $REPLY =~ ^[Oo][Uu][Ii]$ ]]; then
    if [ -d "$CONFIG_DIR" ]; then
        rm -rf "$CONFIG_DIR"
        echo -e "${GREEN}✓${NC} Configuration supprimée"
    fi
    if [ -d "$DATA_DIR" ]; then
        rm -rf "$DATA_DIR"
        echo -e "${GREEN}✓${NC} Données supprimées"
    fi
    if [ -d "$LOG_DIR" ]; then
        rm -rf "$LOG_DIR"
        echo -e "${GREEN}✓${NC} Logs supprimés"
    fi
else
    echo -e "${YELLOW}⚠${NC}  Données conservées :"
    echo "   - Configuration : $CONFIG_DIR"
    echo "   - Données       : $DATA_DIR"
    echo "   - Logs          : $LOG_DIR"
    echo ""
    echo "   Pour les supprimer manuellement :"
    echo "   sudo rm -rf $CONFIG_DIR $DATA_DIR $LOG_DIR"
fi
echo ""

echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Désinstallation terminée${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""
