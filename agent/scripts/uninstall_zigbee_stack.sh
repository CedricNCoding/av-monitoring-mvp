#!/bin/bash
# uninstall_zigbee_stack.sh - Désinstallation propre de la stack Zigbee
# Supprime Mosquitto, Zigbee2MQTT et configuration MQTT de l'agent

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=========================================="
echo "  Désinstallation Stack Zigbee"
echo "=========================================="
echo ""

# Vérifier root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}✗ Erreur: Ce script doit être exécuté en root${NC}"
    exit 1
fi

# Confirmation
echo -e "${YELLOW}⚠ ATTENTION:${NC} Cette opération va supprimer:"
echo "  - Service Mosquitto MQTT"
echo "  - Service Zigbee2MQTT"
echo "  - Tous les appareils Zigbee jumelés"
echo "  - Configuration MQTT de l'agent"
echo ""
read -p "Continuer? (tapez 'oui' pour confirmer): " CONFIRM

if [ "$CONFIRM" != "oui" ]; then
    echo "Désinstallation annulée."
    exit 0
fi

echo ""

# ------------------------------------------------------------
# 1. Arrêter et désactiver services
# ------------------------------------------------------------

echo "Arrêt des services..."

if systemctl is-active zigbee2mqtt &> /dev/null; then
    systemctl stop zigbee2mqtt
    echo -e "${GREEN}✓${NC} Service zigbee2mqtt arrêté"
fi

if systemctl is-enabled zigbee2mqtt &> /dev/null; then
    systemctl disable zigbee2mqtt
    echo -e "${GREEN}✓${NC} Service zigbee2mqtt désactivé"
fi

if systemctl is-active mosquitto &> /dev/null; then
    systemctl stop mosquitto
    echo -e "${GREEN}✓${NC} Service mosquitto arrêté"
fi

if systemctl is-enabled mosquitto &> /dev/null; then
    systemctl disable mosquitto
    echo -e "${GREEN}✓${NC} Service mosquitto désactivé"
fi

echo ""

# ------------------------------------------------------------
# 2. Supprimer packages système
# ------------------------------------------------------------

echo "Suppression des packages..."

if command -v apt-get &> /dev/null; then
    if dpkg -l | grep -q "mosquitto"; then
        DEBIAN_FRONTEND=noninteractive apt-get remove --purge -y mosquitto mosquitto-clients
        echo -e "${GREEN}✓${NC} Mosquitto désinstallé"
    fi
fi

echo ""

# ------------------------------------------------------------
# 3. Supprimer Zigbee2MQTT
# ------------------------------------------------------------

echo "Suppression de Zigbee2MQTT..."

if [ -d /opt/zigbee2mqtt ]; then
    rm -rf /opt/zigbee2mqtt
    echo -e "${GREEN}✓${NC} Répertoire /opt/zigbee2mqtt supprimé"
fi

if [ -f /etc/systemd/system/zigbee2mqtt.service ]; then
    rm -f /etc/systemd/system/zigbee2mqtt.service
    systemctl daemon-reload
    echo -e "${GREEN}✓${NC} Service systemd zigbee2mqtt supprimé"
fi

echo ""

# ------------------------------------------------------------
# 4. Supprimer user système
# ------------------------------------------------------------

echo "Suppression user système..."

if id -u zigbee2mqtt &> /dev/null; then
    userdel zigbee2mqtt
    echo -e "${GREEN}✓${NC} User 'zigbee2mqtt' supprimé"
fi

echo ""

# ------------------------------------------------------------
# 5. Nettoyer configuration MQTT de l'agent
# ------------------------------------------------------------

echo "Nettoyage configuration agent..."

ENV_FILE="/etc/default/avmonitoring-agent"

if [ -f "$ENV_FILE" ]; then
    # Backup avant modification
    cp "$ENV_FILE" "$ENV_FILE.bak"

    # Supprimer les lignes MQTT (depuis commentaire jusqu'à dernière var)
    sed -i '/# Zigbee\/MQTT Configuration/,/^AVMVP_MQTT_BASE_TOPIC=/d' "$ENV_FILE"

    echo -e "${GREEN}✓${NC} Variables MQTT retirées de $ENV_FILE"
    echo -e "${GREEN}✓${NC} Backup sauvegardé: $ENV_FILE.bak"
fi

echo ""

# ------------------------------------------------------------
# 6. Redémarrer agent (sans Zigbee)
# ------------------------------------------------------------

echo "Redémarrage de l'agent..."

if systemctl is-active avmonitoring-agent &> /dev/null; then
    systemctl restart avmonitoring-agent
    echo -e "${GREEN}✓${NC} Agent redémarré (configuration Zigbee retirée)"
else
    echo -e "${YELLOW}⚠${NC} Agent non actif, redémarrage ignoré"
fi

echo ""

# ------------------------------------------------------------
# 7. Proposer suppression des données (optionnel)
# ------------------------------------------------------------

echo -e "${YELLOW}Données persistantes détectées:${NC}"
echo ""

REMOVE_DATA="non"

if [ -d /var/lib/zigbee2mqtt ]; then
    echo "  - /var/lib/zigbee2mqtt (réseau Zigbee, appareils jumelés)"
    read -p "Supprimer /var/lib/zigbee2mqtt? (oui/non): " CONFIRM_DATA
    if [ "$CONFIRM_DATA" = "oui" ]; then
        REMOVE_DATA="oui"
    fi
fi

if [ -d /var/log/zigbee2mqtt ]; then
    echo "  - /var/log/zigbee2mqtt (logs)"
    if [ "$REMOVE_DATA" = "oui" ]; then
        rm -rf /var/log/zigbee2mqtt
        echo -e "${GREEN}✓${NC} Logs Zigbee2MQTT supprimés"
    fi
fi

if [ "$REMOVE_DATA" = "oui" ]; then
    rm -rf /var/lib/zigbee2mqtt
    echo -e "${GREEN}✓${NC} Données Zigbee2MQTT supprimées"
else
    echo -e "${YELLOW}⚠${NC} Données conservées (pour réinstallation ultérieure)"
fi

echo ""

if [ -d /etc/mosquitto ]; then
    echo "  - /etc/mosquitto (config broker, certificats TLS)"
    read -p "Supprimer /etc/mosquitto? (oui/non): " CONFIRM_MOSQ
    if [ "$CONFIRM_MOSQ" = "oui" ]; then
        rm -rf /etc/mosquitto
        echo -e "${GREEN}✓${NC} Configuration Mosquitto supprimée"
    else
        echo -e "${YELLOW}⚠${NC} Configuration Mosquitto conservée"
    fi
fi

echo ""

if [ -f /root/zigbee_credentials.txt ]; then
    echo "  - /root/zigbee_credentials.txt (credentials MQTT)"
    read -p "Supprimer credentials? (oui/non): " CONFIRM_CRED
    if [ "$CONFIRM_CRED" = "oui" ]; then
        rm -f /root/zigbee_credentials.txt
        echo -e "${GREEN}✓${NC} Credentials supprimés"
    else
        echo -e "${YELLOW}⚠${NC} Credentials conservés"
    fi
fi

echo ""

# ------------------------------------------------------------
# 8. Nettoyer devices Zigbee de config.json
# ------------------------------------------------------------

echo "Nettoyage config.json..."

CONFIG_JSON="/etc/avmonitoring/config.json"

if [ -f "$CONFIG_JSON" ]; then
    # Vérifier si des devices zigbee existent
    if grep -q '"driver": "zigbee"' "$CONFIG_JSON"; then
        echo -e "${YELLOW}⚠ Devices Zigbee détectés dans config.json${NC}"
        echo "  Vous devez les retirer manuellement:"
        echo "  vi $CONFIG_JSON"
        echo "  (supprimer devices avec \"driver\": \"zigbee\")"
    else
        echo -e "${GREEN}✓${NC} Aucun device Zigbee dans config.json"
    fi
else
    echo -e "${YELLOW}⚠${NC} Fichier config.json absent"
fi

echo ""

# ------------------------------------------------------------
# Résumé
# ------------------------------------------------------------

echo "=========================================="
echo -e "${GREEN}✅ Désinstallation terminée${NC}"
echo "=========================================="
echo ""
echo "Services supprimés:"
echo "  ✓ mosquitto"
echo "  ✓ zigbee2mqtt"
echo ""
echo "L'agent AV Monitoring continue de fonctionner normalement."
echo "Seul le support Zigbee a été retiré."
echo ""
echo "Pour réinstaller la stack Zigbee:"
echo "  bash /opt/avmonitoring-agent/scripts/install_zigbee_stack.sh"
echo ""
