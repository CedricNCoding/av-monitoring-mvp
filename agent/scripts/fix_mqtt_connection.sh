#!/usr/bin/env bash
# fix_mqtt_connection.sh - Corriger la connexion MQTT de l'agent
# Usage: sudo bash fix_mqtt_connection.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Fix connexion MQTT Agent${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Vérifier que nous sommes root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}✗ Ce script doit être exécuté en tant que root${NC}"
    exit 1
fi

# 1. Lire le mot de passe depuis le fichier de credentials
CREDS_FILE="/root/zigbee_credentials.txt"
if [ ! -f "$CREDS_FILE" ]; then
    echo -e "${RED}✗ Fichier credentials manquant: $CREDS_FILE${NC}"
    exit 1
fi

echo "Lecture des credentials depuis $CREDS_FILE..."
source "$CREDS_FILE"

if [ -z "$MQTT_PASS_AGENT" ]; then
    echo -e "${RED}✗ MQTT_PASS_AGENT non défini dans $CREDS_FILE${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} Credentials chargés"

# 2. Backup du fichier de configuration
ENV_FILE="/etc/default/avmonitoring-agent"
BACKUP_FILE="${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"

if [ -f "$ENV_FILE" ]; then
    cp "$ENV_FILE" "$BACKUP_FILE"
    echo -e "${GREEN}✓${NC} Backup créé: $BACKUP_FILE"
else
    echo -e "${RED}✗ Fichier de configuration manquant: $ENV_FILE${NC}"
    exit 1
fi

# 3. Supprimer toutes les lignes MQTT existantes
echo "Nettoyage des variables MQTT existantes..."
sed -i '/AVMVP_MQTT_/d' "$ENV_FILE"
echo -e "${GREEN}✓${NC} Variables MQTT supprimées"

# 4. Ajouter les bonnes variables MQTT (sans TLS)
echo "Ajout des nouvelles variables MQTT..."
cat >> "$ENV_FILE" <<EOF

# Zigbee/MQTT Configuration (version non-TLS)
AVMVP_MQTT_HOST=localhost
AVMVP_MQTT_PORT=1883
AVMVP_MQTT_USER=avmonitoring
AVMVP_MQTT_PASS=${MQTT_PASS_AGENT}
AVMVP_MQTT_BASE_TOPIC=zigbee2mqtt
EOF

echo -e "${GREEN}✓${NC} Variables MQTT ajoutées"

# 5. Vérifier le fichier
echo ""
echo "Configuration MQTT actuelle:"
echo "----------------------------"
grep "AVMVP_MQTT_" "$ENV_FILE"
echo ""

# 6. Vérifier que Mosquitto est bien sur le port 1883
echo "Vérification du port MQTT 1883..."
if ss -tln | grep -q ':1883'; then
    echo -e "${GREEN}✓${NC} Port 1883 ouvert"
else
    echo -e "${YELLOW}⚠${NC} Port 1883 non ouvert, vérifiez Mosquitto"
fi

# 7. Tester la connexion MQTT
echo ""
echo "Test de connexion MQTT..."
if command -v mosquitto_sub &> /dev/null; then
    timeout 3 mosquitto_sub -h localhost -p 1883 \
        -u avmonitoring -P "${MQTT_PASS_AGENT}" \
        -t 'zigbee2mqtt/bridge/state' -C 1 2>&1 | grep -q "online" && \
        echo -e "${GREEN}✓${NC} Connexion MQTT OK" || \
        echo -e "${YELLOW}⚠${NC} Test MQTT échoué (mais config devrait être OK)"
else
    echo -e "${YELLOW}⚠${NC} mosquitto_sub non disponible, test skippé"
fi

# 8. Redémarrer l'agent
echo ""
echo "Redémarrage de l'agent AV Monitoring..."
systemctl restart avmonitoring-agent
sleep 2

# 9. Vérifier les logs de l'agent
echo ""
echo "Logs de l'agent (dernières lignes):"
echo "------------------------------------"
journalctl -u avmonitoring-agent -n 20 --no-pager | grep -E "MQTT|mqtt|Starting|Started"

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ Fix terminé !${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "Vérifications à faire:"
echo "1. L'agent doit afficher 'MQTT configured: yes'"
echo "2. L'agent doit afficher 'MQTT connect OK'"
echo "3. Le bouton 'Activer jumelage' doit être actif sur http://$(hostname -I | awk '{print $1}'):8080"
echo ""
echo "Si problème persiste, vérifiez:"
echo "  journalctl -u avmonitoring-agent -f"
echo "  journalctl -u mosquitto -f"
echo ""
