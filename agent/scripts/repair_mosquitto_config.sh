#!/bin/bash
# repair_mosquitto_config.sh - Répare la configuration Mosquitto en cas d'erreur de duplication persistence_location
# Utilisation: sudo ./repair_mosquitto_config.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=========================================="
echo "  Réparation Configuration Mosquitto"
echo "=========================================="
echo ""

# Vérifier root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}✗ Erreur: Ce script doit être exécuté en root${NC}"
    exit 1
fi

# Backup de sécurité
BACKUP_DIR="/root/mosquitto_repair_backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

if [ -d /etc/mosquitto ]; then
    cp -r /etc/mosquitto "$BACKUP_DIR/"
    echo -e "${GREEN}✓${NC} Backup créé: $BACKUP_DIR"
fi

# Diagnostic
echo ""
echo "Diagnostic de la configuration actuelle..."
echo ""

CONF_FILE="/etc/mosquitto/conf.d/zigbee.conf"
MAIN_CONF="/etc/mosquitto/mosquitto.conf"

if [ ! -f "$CONF_FILE" ]; then
    echo -e "${YELLOW}⚠${NC} Fichier $CONF_FILE absent (rien à réparer)"
    exit 0
fi

# Vérifier si persistence_location est dupliqué
DUPLICATE_FOUND=false

if grep -q "^persistence_location" "$CONF_FILE" 2>/dev/null; then
    echo -e "${YELLOW}⚠${NC} Trouvé 'persistence_location' dans $CONF_FILE"
    DUPLICATE_FOUND=true
fi

if grep -q "^persistence true" "$CONF_FILE" 2>/dev/null; then
    echo -e "${YELLOW}⚠${NC} Trouvé 'persistence true' dans $CONF_FILE"
    DUPLICATE_FOUND=true
fi

if [ "$DUPLICATE_FOUND" = false ]; then
    echo -e "${GREEN}✓${NC} Aucune duplication détectée, configuration OK"

    # Valider quand même
    echo ""
    echo "Validation de la configuration..."
    if mosquitto -c "$MAIN_CONF" -v >/dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Configuration Mosquitto valide"
        exit 0
    else
        echo -e "${RED}✗${NC} Configuration Mosquitto invalide:"
        mosquitto -c "$MAIN_CONF" -v 2>&1 | grep -i error | head -n 5
        exit 1
    fi
fi

# Réparation
echo ""
echo "Réparation en cours..."
echo ""

# Retirer les directives persistence de zigbee.conf
echo -n "Suppression directives persistence de $CONF_FILE... "
sed -i '/^persistence /d' "$CONF_FILE"
sed -i '/^persistence_location /d' "$CONF_FILE"
sed -i '/^# Persistence$/d' "$CONF_FILE"
echo -e "${GREEN}✓${NC}"

# S'assurer que mosquitto.conf a les directives
echo -n "Vérification directives dans $MAIN_CONF... "
if ! grep -q "^persistence true" "$MAIN_CONF" 2>/dev/null; then
    cat >> "$MAIN_CONF" <<'EOF'

# Persistence (ajouté par repair_mosquitto_config.sh)
persistence true
persistence_location /var/lib/mosquitto/
EOF
    echo -e "${GREEN}✓ ajoutées${NC}"
else
    echo -e "${GREEN}✓ déjà présentes${NC}"
fi

# Validation
echo ""
echo "Validation de la configuration réparée..."
if mosquitto -c "$MAIN_CONF" -v >/dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Configuration Mosquitto valide"
else
    echo -e "${RED}✗${NC} Configuration toujours invalide:"
    mosquitto -c "$MAIN_CONF" -v 2>&1 | grep -i error | head -n 5
    echo ""
    echo "Restauration du backup..."
    cp -r "$BACKUP_DIR/mosquitto/"* /etc/mosquitto/
    exit 1
fi

# Redémarrer Mosquitto
echo ""
echo "Redémarrage de Mosquitto..."
systemctl daemon-reload
systemctl restart mosquitto

sleep 2

if systemctl is-active mosquitto &> /dev/null; then
    echo -e "${GREEN}✓${NC} Mosquitto redémarré avec succès"
else
    echo -e "${RED}✗${NC} Mosquitto n'a pas démarré"
    echo "Logs:"
    journalctl -u mosquitto -n 20 --no-pager
    exit 1
fi

echo ""
echo "=========================================="
echo -e "${GREEN}✅ Réparation terminée avec succès !${NC}"
echo "=========================================="
echo ""
echo "Backup conservé: $BACKUP_DIR"
echo ""
echo "Commandes de vérification:"
echo "  systemctl status mosquitto"
echo "  journalctl -u mosquitto -n 50"
echo ""
