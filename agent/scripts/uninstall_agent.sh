#!/bin/bash
# uninstall_agent.sh - Désinstallation de l'agent AV Monitoring
# Utilisation: sudo ./uninstall_agent.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

INSTALL_DIR="/opt/avmonitoring-agent"
CONFIG_DIR="/etc/avmonitoring"
DATA_DIR="/var/lib/avmonitoring"
LOG_DIR="/var/log/avmonitoring"
AGENT_USER="avmonitoring"

echo "=========================================="
echo "  Désinstallation Agent AV Monitoring"
echo "=========================================="
echo ""

# Vérifier root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}✗ Erreur: Ce script doit être exécuté en root${NC}"
    exit 1
fi

# Confirmation
echo -e "${YELLOW}⚠ ATTENTION: Cette action va supprimer :${NC}"
echo "  - Le service avmonitoring-agent"
echo "  - Le code dans $INSTALL_DIR"
echo "  - Les logs dans $LOG_DIR"
echo "  - Les données dans $DATA_DIR"
echo ""
echo -e "${YELLOW}⚠ La configuration ($CONFIG_DIR) sera CONSERVÉE${NC}"
echo ""
read -p "Confirmer la désinstallation ? (oui/non) : " CONFIRM

if [ "$CONFIRM" != "oui" ]; then
    echo "Désinstallation annulée."
    exit 0
fi

echo ""
echo "Désinstallation en cours..."
echo ""

# Arrêter et désactiver le service
if systemctl is-active avmonitoring-agent &>/dev/null; then
    echo -n "Arrêt du service... "
    systemctl stop avmonitoring-agent
    echo -e "${GREEN}✓${NC}"
fi

if systemctl is-enabled avmonitoring-agent &>/dev/null; then
    echo -n "Désactivation du service... "
    systemctl disable avmonitoring-agent > /dev/null 2>&1
    echo -e "${GREEN}✓${NC}"
fi

# Supprimer le service systemd
if [ -f /etc/systemd/system/avmonitoring-agent.service ]; then
    echo -n "Suppression du service systemd... "
    rm -f /etc/systemd/system/avmonitoring-agent.service
    rm -f /etc/default/avmonitoring-agent
    systemctl daemon-reload
    echo -e "${GREEN}✓${NC}"
fi

# Supprimer le code
if [ -d "$INSTALL_DIR" ]; then
    echo -n "Suppression du code... "
    rm -rf "$INSTALL_DIR"
    echo -e "${GREEN}✓${NC}"
fi

# Supprimer les logs
if [ -d "$LOG_DIR" ]; then
    echo -n "Suppression des logs... "
    rm -rf "$LOG_DIR"
    echo -e "${GREEN}✓${NC}"
fi

# Supprimer les données
if [ -d "$DATA_DIR" ]; then
    echo -n "Suppression des données... "
    rm -rf "$DATA_DIR"
    echo -e "${GREEN}✓${NC}"
fi

# Supprimer l'utilisateur (optionnel)
if id "$AGENT_USER" &>/dev/null; then
    read -p "Supprimer l'utilisateur $AGENT_USER ? (oui/non) : " DELETE_USER
    if [ "$DELETE_USER" = "oui" ]; then
        echo -n "Suppression de l'utilisateur... "
        userdel "$AGENT_USER" 2>/dev/null || true
        echo -e "${GREEN}✓${NC}"
    else
        echo -e "${YELLOW}⚠${NC} Utilisateur $AGENT_USER conservé"
    fi
fi

echo ""
echo "=========================================="
echo -e "${GREEN}✅ Désinstallation terminée${NC}"
echo "=========================================="
echo ""

if [ -d "$CONFIG_DIR" ]; then
    echo -e "${YELLOW}Configuration conservée:${NC} $CONFIG_DIR"
    echo "Pour supprimer la config : rm -rf $CONFIG_DIR"
    echo ""
fi

echo "Pour réinstaller l'agent :"
echo "  curl -sSL https://raw.githubusercontent.com/CedricNCoding/av-monitoring-mvp/main/agent/scripts/install_agent.sh | sudo bash"
echo ""
