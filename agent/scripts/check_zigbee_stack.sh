#!/bin/bash
# check_zigbee_stack.sh - Script de validation post-installation Zigbee
# Vérifie que Mosquitto, Zigbee2MQTT et l'agent sont correctement configurés

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PASSED=0
FAILED=0
WARNINGS=0

echo "=========================================="
echo "  Validation Stack Zigbee"
echo "=========================================="
echo ""

# Helper functions
check_pass() {
    echo -e "${GREEN}✓${NC} $1"
    ((PASSED++))
}

check_fail() {
    echo -e "${RED}✗${NC} $1"
    ((FAILED++))
}

check_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
    ((WARNINGS++))
}

# ------------------------------------------------------------
# 1. Services systemd
# ------------------------------------------------------------

echo -e "${BLUE}[1/12]${NC} Vérification services systemd..."

if systemctl is-active mosquitto &> /dev/null; then
    check_pass "Service mosquitto actif"
else
    check_fail "Service mosquitto NON actif (systemctl start mosquitto)"
fi

if systemctl is-enabled mosquitto &> /dev/null; then
    check_pass "Service mosquitto activé au boot"
else
    check_warn "Service mosquitto NON activé au boot (systemctl enable mosquitto)"
fi

if systemctl is-active zigbee2mqtt &> /dev/null; then
    check_pass "Service zigbee2mqtt actif"
else
    check_warn "Service zigbee2mqtt NON actif (dongle absent ou erreur config)"
fi

if systemctl is-active avmonitoring-agent &> /dev/null; then
    check_pass "Service avmonitoring-agent actif"
else
    check_warn "Service avmonitoring-agent NON actif"
fi

echo ""

# ------------------------------------------------------------
# 2. Ports réseau
# ------------------------------------------------------------

echo -e "${BLUE}[2/12]${NC} Vérification ports réseau..."

if command -v ss &> /dev/null; then
    if ss -tln | grep -q ':8883'; then
        check_pass "Port MQTT TLS 8883 en écoute"
    else
        check_fail "Port 8883 NON en écoute (vérifier mosquitto)"
    fi
else
    if netstat -tln 2>/dev/null | grep -q ':8883'; then
        check_pass "Port MQTT TLS 8883 en écoute"
    else
        check_fail "Port 8883 NON en écoute (vérifier mosquitto)"
    fi
fi

echo ""

# ------------------------------------------------------------
# 3. Certificats TLS
# ------------------------------------------------------------

echo -e "${BLUE}[3/12]${NC} Vérification certificats TLS..."

CERT_DIR="/etc/mosquitto/ca_certificates"

if [ -f "$CERT_DIR/ca.crt" ]; then
    check_pass "Certificat CA présent"

    # Vérifier validité
    if openssl x509 -in "$CERT_DIR/ca.crt" -noout -checkend 86400 &> /dev/null; then
        check_pass "Certificat CA valide (expire dans > 24h)"
    else
        check_fail "Certificat CA expiré ou expire bientôt"
    fi
else
    check_fail "Certificat CA absent ($CERT_DIR/ca.crt)"
fi

if [ -f "$CERT_DIR/server.crt" ]; then
    check_pass "Certificat serveur présent"
else
    check_fail "Certificat serveur absent ($CERT_DIR/server.crt)"
fi

if [ -f "$CERT_DIR/server.key" ]; then
    check_pass "Clé privée serveur présente"

    # Vérifier permissions
    PERMS=$(stat -c %a "$CERT_DIR/server.key" 2>/dev/null || stat -f %A "$CERT_DIR/server.key" 2>/dev/null)
    if [ "$PERMS" = "600" ]; then
        check_pass "Permissions clé privée correctes (600)"
    else
        check_warn "Permissions clé privée incorrectes ($PERMS, devrait être 600)"
    fi
else
    check_fail "Clé privée serveur absente ($CERT_DIR/server.key)"
fi

echo ""

# ------------------------------------------------------------
# 4. Configuration Mosquitto
# ------------------------------------------------------------

echo -e "${BLUE}[4/12]${NC} Vérification configuration Mosquitto..."

if [ -f /etc/mosquitto/conf.d/zigbee.conf ]; then
    check_pass "Fichier config Mosquitto présent"

    # Vérifier TLS activé
    if grep -q "listener 8883" /etc/mosquitto/conf.d/zigbee.conf; then
        check_pass "Listener TLS 8883 configuré"
    else
        check_fail "Listener TLS 8883 NON configuré"
    fi

    # Vérifier auth obligatoire
    if grep -q "allow_anonymous false" /etc/mosquitto/conf.d/zigbee.conf; then
        check_pass "Authentification obligatoire activée"
    else
        check_fail "Authentification anonyme autorisée (RISQUE SÉCURITÉ)"
    fi
else
    check_fail "Config Mosquitto absente (/etc/mosquitto/conf.d/zigbee.conf)"
fi

if [ -f /etc/mosquitto/passwd ]; then
    check_pass "Fichier passwords Mosquitto présent"

    # Vérifier users
    if grep -q "^avmonitoring:" /etc/mosquitto/passwd; then
        check_pass "User 'avmonitoring' configuré"
    else
        check_fail "User 'avmonitoring' absent du fichier passwords"
    fi

    if grep -q "^zigbee2mqtt:" /etc/mosquitto/passwd; then
        check_pass "User 'zigbee2mqtt' configuré"
    else
        check_fail "User 'zigbee2mqtt' absent du fichier passwords"
    fi
else
    check_fail "Fichier passwords absent (/etc/mosquitto/passwd)"
fi

if [ -f /etc/mosquitto/acl.conf ]; then
    check_pass "Fichier ACL Mosquitto présent"
else
    check_warn "Fichier ACL absent (pas de restriction d'accès)"
fi

echo ""

# ------------------------------------------------------------
# 5. Dongle USB Zigbee
# ------------------------------------------------------------

echo -e "${BLUE}[5/12]${NC} Vérification dongle USB Zigbee..."

if [ -e /dev/ttyUSB0 ] || [ -e /dev/ttyUSB1 ] || [ -e /dev/ttyACM0 ] || [ -e /dev/ttyACM1 ]; then
    DONGLE=$(ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | head -n1)
    check_pass "Dongle détecté: $DONGLE"

    # Vérifier permissions
    if [ -r "$DONGLE" ]; then
        check_pass "Dongle accessible en lecture"
    else
        check_warn "Dongle non accessible (permissions?)"
    fi
else
    check_warn "Aucun dongle détecté (brancher un dongle USB Zigbee)"
fi

echo ""

# ------------------------------------------------------------
# 6. Installation Zigbee2MQTT
# ------------------------------------------------------------

echo -e "${BLUE}[6/12]${NC} Vérification installation Zigbee2MQTT..."

if [ -d /opt/zigbee2mqtt ]; then
    check_pass "Répertoire Zigbee2MQTT présent"

    if [ -f /opt/zigbee2mqtt/index.js ]; then
        check_pass "Fichier principal Zigbee2MQTT présent"
    else
        check_fail "Fichier index.js absent (installation incomplète)"
    fi

    if [ -d /opt/zigbee2mqtt/node_modules ]; then
        check_pass "Dépendances Node.js installées"
    else
        check_fail "node_modules absent (exécuter: cd /opt/zigbee2mqtt && npm ci)"
    fi
else
    check_fail "Zigbee2MQTT non installé (/opt/zigbee2mqtt absent)"
fi

if id -u zigbee2mqtt &> /dev/null; then
    check_pass "User système 'zigbee2mqtt' existe"
else
    check_fail "User système 'zigbee2mqtt' absent"
fi

if [ -d /var/lib/zigbee2mqtt ]; then
    check_pass "Répertoire data Zigbee2MQTT présent"
else
    check_warn "Répertoire /var/lib/zigbee2mqtt absent"
fi

echo ""

# ------------------------------------------------------------
# 7. Configuration Zigbee2MQTT
# ------------------------------------------------------------

echo -e "${BLUE}[7/12]${NC} Vérification configuration Zigbee2MQTT..."

CONFIG_FILE="/var/lib/zigbee2mqtt/configuration.yaml"

if [ -f "$CONFIG_FILE" ]; then
    check_pass "Fichier config Zigbee2MQTT présent"

    # Vérifier MQTT TLS
    if grep -q "mqtts://" "$CONFIG_FILE"; then
        check_pass "MQTT TLS (mqtts) configuré"
    else
        check_fail "MQTT en clair (mqtt://) - RISQUE SÉCURITÉ"
    fi

    # Vérifier CA cert
    if grep -q "ca: /etc/mosquitto/ca_certificates/ca.crt" "$CONFIG_FILE"; then
        check_pass "Certificat CA configuré dans Z2M"
    else
        check_warn "CA cert non configuré (connexion TLS échouera)"
    fi
else
    check_fail "Configuration Zigbee2MQTT absente ($CONFIG_FILE)"
fi

echo ""

# ------------------------------------------------------------
# 8. Logs Zigbee2MQTT
# ------------------------------------------------------------

echo -e "${BLUE}[8/12]${NC} Vérification logs Zigbee2MQTT..."

if systemctl is-active zigbee2mqtt &> /dev/null; then
    # Vérifier connexion MQTT
    if journalctl -u zigbee2mqtt -n 100 --no-pager 2>/dev/null | grep -q "MQTT connected"; then
        check_pass "Zigbee2MQTT connecté à MQTT"
    else
        check_warn "Zigbee2MQTT pas encore connecté (vérifier logs)"
    fi

    # Vérifier démarrage Zigbee
    if journalctl -u zigbee2mqtt -n 100 --no-pager 2>/dev/null | grep -q "Zigbee: started"; then
        check_pass "Stack Zigbee démarrée"
    else
        check_warn "Stack Zigbee non démarrée (dongle absent?)"
    fi

    # Vérifier erreurs récentes
    ERROR_COUNT=$(journalctl -u zigbee2mqtt -n 50 --no-pager --since "5 minutes ago" 2>/dev/null | grep -c "error" || echo 0)
    if [ "$ERROR_COUNT" -eq 0 ]; then
        check_pass "Aucune erreur récente dans logs Z2M"
    else
        check_warn "Erreurs détectées dans logs ($ERROR_COUNT dans les 5 dernières min)"
    fi
else
    check_warn "Service zigbee2mqtt non actif, logs non vérifiés"
fi

echo ""

# ------------------------------------------------------------
# 9. Variables environnement agent
# ------------------------------------------------------------

echo -e "${BLUE}[9/12]${NC} Vérification variables environnement agent..."

ENV_FILE="/etc/default/avmonitoring-agent"

if [ -f "$ENV_FILE" ]; then
    check_pass "Fichier env agent présent"

    if grep -q "AVMVP_MQTT_HOST" "$ENV_FILE"; then
        check_pass "Variable AVMVP_MQTT_HOST configurée"
    else
        check_fail "Variable AVMVP_MQTT_HOST absente"
    fi

    if grep -q "AVMVP_MQTT_PASS" "$ENV_FILE"; then
        check_pass "Variable AVMVP_MQTT_PASS configurée"
    else
        check_fail "Variable AVMVP_MQTT_PASS absente"
    fi

    if grep -q "AVMVP_MQTT_TLS_CA" "$ENV_FILE"; then
        check_pass "Variable AVMVP_MQTT_TLS_CA configurée"
    else
        check_fail "Variable AVMVP_MQTT_TLS_CA absente"
    fi

    # Vérifier permissions
    PERMS=$(stat -c %a "$ENV_FILE" 2>/dev/null || stat -f %A "$ENV_FILE" 2>/dev/null)
    if [ "$PERMS" = "640" ] || [ "$PERMS" = "600" ]; then
        check_pass "Permissions fichier env correctes ($PERMS)"
    else
        check_warn "Permissions fichier env ($PERMS, devrait être 640 ou 600)"
    fi
else
    check_fail "Fichier env agent absent ($ENV_FILE)"
fi

echo ""

# ------------------------------------------------------------
# 10. Connectivité MQTT (test réel)
# ------------------------------------------------------------

echo -e "${BLUE}[10/12]${NC} Test de connexion MQTT..."

if [ -f /root/zigbee_credentials.txt ]; then
    source /root/zigbee_credentials.txt

    if command -v mosquitto_sub &> /dev/null; then
        # Test connexion avec timeout
        if timeout 5 mosquitto_sub -h localhost -p 8883 \
            --cafile /etc/mosquitto/ca_certificates/ca.crt \
            -u avmonitoring -P "$MQTT_PASS_AGENT" \
            -t 'zigbee2mqtt/bridge/state' -C 1 &> /dev/null; then
            check_pass "Connexion MQTT TLS réussie (user: avmonitoring)"
        else
            check_fail "Connexion MQTT échouée (credentials incorrects ou broker down)"
        fi
    else
        check_warn "mosquitto_sub absent, test de connexion ignoré"
    fi
else
    check_warn "Fichier credentials absent (/root/zigbee_credentials.txt)"
fi

echo ""

# ------------------------------------------------------------
# 11. Agent AV Monitoring (logs MQTT)
# ------------------------------------------------------------

echo -e "${BLUE}[11/12]${NC} Vérification logs agent..."

if systemctl is-active avmonitoring-agent &> /dev/null; then
    # Vérifier erreurs récentes
    ERROR_COUNT=$(journalctl -u avmonitoring-agent -n 100 --no-pager --since "5 minutes ago" 2>/dev/null | grep -ci "error\|exception\|traceback" || echo 0)

    if [ "$ERROR_COUNT" -eq 0 ]; then
        check_pass "Aucune erreur récente dans logs agent"
    else
        check_warn "Erreurs détectées dans logs agent ($ERROR_COUNT dans les 5 dernières min)"
    fi

    # Vérifier import driver zigbee (si déjà implémenté)
    if [ -f /opt/avmonitoring-agent/src/drivers/zigbee.py ]; then
        check_pass "Driver zigbee.py présent"
    else
        check_warn "Driver zigbee.py pas encore implémenté (phase 2)"
    fi
else
    check_warn "Agent non actif, logs non vérifiés"
fi

echo ""

# ------------------------------------------------------------
# 12. Node.js et npm
# ------------------------------------------------------------

echo -e "${BLUE}[12/12]${NC} Vérification environnement Node.js..."

if command -v node &> /dev/null; then
    NODE_VERSION=$(node -v)
    check_pass "Node.js installé ($NODE_VERSION)"

    NODE_MAJOR=$(echo "$NODE_VERSION" | cut -d'v' -f2 | cut -d'.' -f1)
    if [ "$NODE_MAJOR" -ge 18 ]; then
        check_pass "Version Node.js compatible (>= 18.x)"
    else
        check_fail "Version Node.js trop ancienne ($NODE_VERSION, requis >= 18.x)"
    fi
else
    check_fail "Node.js non installé"
fi

if command -v npm &> /dev/null; then
    NPM_VERSION=$(npm -v)
    check_pass "npm installé ($NPM_VERSION)"
else
    check_fail "npm non installé"
fi

echo ""

# ------------------------------------------------------------
# Résumé final
# ------------------------------------------------------------

echo "=========================================="
echo "  Résumé de la validation"
echo "=========================================="
echo -e "${GREEN}✓ Tests réussis:${NC}   $PASSED"
echo -e "${YELLOW}⚠ Avertissements:${NC}  $WARNINGS"
echo -e "${RED}✗ Tests échoués:${NC}   $FAILED"
echo ""

if [ $FAILED -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✅ Stack Zigbee parfaitement configurée !${NC}"
    exit 0
elif [ $FAILED -eq 0 ]; then
    echo -e "${YELLOW}⚠ Stack Zigbee fonctionnelle avec quelques avertissements${NC}"
    echo "Consultez les messages ci-dessus pour optimiser la configuration."
    exit 0
else
    echo -e "${RED}❌ Problèmes détectés dans la configuration${NC}"
    echo "Corrigez les erreurs (✗) avant de continuer."
    echo ""
    echo "Pour plus de détails:"
    echo "  journalctl -u mosquitto -n 50"
    echo "  journalctl -u zigbee2mqtt -n 50"
    echo "  journalctl -u avmonitoring-agent -n 50"
    exit 1
fi
