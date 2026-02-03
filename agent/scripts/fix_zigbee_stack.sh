#!/usr/bin/env bash
# fix_zigbee_stack.sh - Diagnostic et remise en ordre de la stack Zigbee
# Usage: sudo bash fix_zigbee_stack.sh

set -e

# Vérifier qu'on utilise bien bash
if [ -z "$BASH_VERSION" ]; then
    echo "Erreur: Ce script nécessite bash. Utilisez: bash $0"
    exit 1
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Diagnostic et remise en ordre Zigbee${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# ========================================
# 1. DIAGNOSTIC
# ========================================

echo -e "${YELLOW}[1/5] Vérification des services...${NC}"
echo ""

# Mosquitto
echo -n "  Mosquitto: "
if systemctl is-active mosquitto &>/dev/null; then
    echo -e "${GREEN}✓ Running${NC}"
    MOSQUITTO_OK=1
else
    echo -e "${RED}✗ Stopped${NC}"
    MOSQUITTO_OK=0
fi

# Zigbee2MQTT
echo -n "  Zigbee2MQTT: "
if systemctl is-active zigbee2mqtt &>/dev/null; then
    echo -e "${GREEN}✓ Running${NC}"
    Z2M_OK=1
else
    echo -e "${RED}✗ Stopped${NC}"
    Z2M_OK=0
fi

# Agent
echo -n "  AV Agent: "
if systemctl is-active avmonitoring-agent &>/dev/null; then
    echo -e "${GREEN}✓ Running${NC}"
    AGENT_OK=1
else
    echo -e "${RED}✗ Stopped${NC}"
    AGENT_OK=0
fi

echo ""
echo -e "${YELLOW}[2/5] Vérification des ports MQTT...${NC}"
echo ""

# Ports
echo -n "  Port 1883 (non-TLS): "
if ss -tln | grep -q '127.0.0.1:1883'; then
    echo -e "${GREEN}✓ Listening${NC}"
    PORT_1883_OK=1
else
    echo -e "${RED}✗ Not listening${NC}"
    PORT_1883_OK=0
fi

echo -n "  Port 8883 (TLS): "
if ss -tln | grep -q '127.0.0.1:8883'; then
    echo -e "${GREEN}✓ Listening${NC}"
    PORT_8883_OK=1
else
    echo -e "${RED}✗ Not listening${NC}"
    PORT_8883_OK=0
fi

echo ""
echo -e "${YELLOW}[3/5] Vérification des fichiers de configuration...${NC}"
echo ""

# Config Mosquitto
echo -n "  /etc/mosquitto/conf.d/zigbee.conf: "
if [ -f /etc/mosquitto/conf.d/zigbee.conf ]; then
    echo -e "${GREEN}✓ Exists${NC}"
    MOSQUITTO_CONF_OK=1
else
    echo -e "${RED}✗ Missing${NC}"
    MOSQUITTO_CONF_OK=0
fi

# Config Zigbee2MQTT
echo -n "  /var/lib/zigbee2mqtt/configuration.yaml: "
if [ -f /var/lib/zigbee2mqtt/configuration.yaml ]; then
    echo -e "${GREEN}✓ Exists${NC}"
    Z2M_CONF_OK=1
else
    echo -e "${RED}✗ Missing${NC}"
    Z2M_CONF_OK=0
fi

# Variables MQTT agent
echo -n "  Variables MQTT dans /etc/default/avmonitoring-agent: "
if grep -q "AVMVP_MQTT_HOST" /etc/default/avmonitoring-agent 2>/dev/null; then
    echo -e "${GREEN}✓ Present${NC}"
    AGENT_MQTT_VARS_OK=1
else
    echo -e "${RED}✗ Missing${NC}"
    AGENT_MQTT_VARS_OK=0
fi

echo ""
echo -e "${YELLOW}[4/5] Vérification des credentials...${NC}"
echo ""

# Credentials file
echo -n "  /root/zigbee_credentials.txt: "
if [ -f /root/zigbee_credentials.txt ]; then
    echo -e "${GREEN}✓ Exists${NC}"
    CREDS_OK=1
    source /root/zigbee_credentials.txt 2>/dev/null || true
else
    echo -e "${RED}✗ Missing${NC}"
    CREDS_OK=0
fi

# Password file Mosquitto
echo -n "  /etc/mosquitto/passwd: "
if [ -f /etc/mosquitto/passwd ]; then
    echo -e "${GREEN}✓ Exists${NC}"
    PASSWD_OK=1
else
    echo -e "${RED}✗ Missing${NC}"
    PASSWD_OK=0
fi

echo ""
echo -e "${YELLOW}[5/5] Test de connexion MQTT...${NC}"
echo ""

if [ "$MOSQUITTO_OK" = "1" ] && [ "$CREDS_OK" = "1" ]; then
    echo -n "  Test mosquitto_sub: "
    if timeout 3 mosquitto_sub -h localhost -p 1883 \
        -u avmonitoring -P "${MQTT_PASS_AGENT:-}" \
        -t 'zigbee2mqtt/bridge/state' -C 1 &>/dev/null; then
        echo -e "${GREEN}✓ OK${NC}"
        MQTT_TEST_OK=1
    else
        echo -e "${RED}✗ Failed${NC}"
        MQTT_TEST_OK=0
    fi
else
    echo -e "${YELLOW}  Skipped (Mosquitto not running or credentials missing)${NC}"
    MQTT_TEST_OK=0
fi

# ========================================
# 2. RÉSUMÉ DIAGNOSTIC
# ========================================

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Résumé du diagnostic${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

TOTAL_ISSUES=0

[ "$MOSQUITTO_OK" = "0" ] && TOTAL_ISSUES=$((TOTAL_ISSUES + 1))
[ "$Z2M_OK" = "0" ] && TOTAL_ISSUES=$((TOTAL_ISSUES + 1))
[ "$AGENT_OK" = "0" ] && TOTAL_ISSUES=$((TOTAL_ISSUES + 1))
[ "$PORT_1883_OK" = "0" ] && TOTAL_ISSUES=$((TOTAL_ISSUES + 1))
[ "$MOSQUITTO_CONF_OK" = "0" ] && TOTAL_ISSUES=$((TOTAL_ISSUES + 1))
[ "$Z2M_CONF_OK" = "0" ] && TOTAL_ISSUES=$((TOTAL_ISSUES + 1))
[ "$AGENT_MQTT_VARS_OK" = "0" ] && TOTAL_ISSUES=$((TOTAL_ISSUES + 1))
[ "$CREDS_OK" = "0" ] && TOTAL_ISSUES=$((TOTAL_ISSUES + 1))
[ "$PASSWD_OK" = "0" ] && TOTAL_ISSUES=$((TOTAL_ISSUES + 1))
[ "$MQTT_TEST_OK" = "0" ] && TOTAL_ISSUES=$((TOTAL_ISSUES + 1))

if [ $TOTAL_ISSUES -eq 0 ]; then
    echo -e "${GREEN}✓ Tout est OK ! Aucun problème détecté.${NC}"
    exit 0
else
    echo -e "${YELLOW}⚠ $TOTAL_ISSUES problème(s) détecté(s)${NC}"
    echo ""
fi

# ========================================
# 3. PROPOSER LES CORRECTIONS
# ========================================

echo -e "${YELLOW}Voulez-vous appliquer les corrections automatiques ? (y/n)${NC}"
read -r APPLY_FIX

if [ "$APPLY_FIX" != "y" ] && [ "$APPLY_FIX" != "Y" ]; then
    echo "Aucune correction appliquée."
    exit 0
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Application des corrections${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# ========================================
# 4. CORRECTIONS
# ========================================

# Correction 1: Credentials manquants
if [ "$CREDS_OK" = "0" ]; then
    echo -e "${YELLOW}[Fix] Régénération des credentials MQTT...${NC}"

    MQTT_PASS_ADMIN=$(openssl rand -base64 24)
    MQTT_PASS_Z2M=$(openssl rand -base64 24)
    MQTT_PASS_AGENT=$(openssl rand -base64 24)

    cat > /root/zigbee_credentials.txt <<EOF
# Credentials MQTT Zigbee Stack
# Généré le $(date)

MQTT_PASS_ADMIN=${MQTT_PASS_ADMIN}
MQTT_PASS_Z2M=${MQTT_PASS_Z2M}
MQTT_PASS_AGENT=${MQTT_PASS_AGENT}
EOF
    chmod 600 /root/zigbee_credentials.txt
    echo -e "${GREEN}  ✓ Credentials générés${NC}"

    # Recréer password file
    touch /etc/mosquitto/passwd
    mosquitto_passwd -b /etc/mosquitto/passwd admin "$MQTT_PASS_ADMIN"
    mosquitto_passwd -b /etc/mosquitto/passwd zigbee2mqtt "$MQTT_PASS_Z2M"
    mosquitto_passwd -b /etc/mosquitto/passwd avmonitoring "$MQTT_PASS_AGENT"
    chown mosquitto:mosquitto /etc/mosquitto/passwd
    chmod 640 /etc/mosquitto/passwd
    echo -e "${GREEN}  ✓ Password file mis à jour${NC}"

    PASSWD_OK=1
fi

# Correction 2: Config Mosquitto manquante
if [ "$MOSQUITTO_CONF_OK" = "0" ]; then
    echo -e "${YELLOW}[Fix] Recréation de la configuration Mosquitto...${NC}"

    mkdir -p /etc/mosquitto/ca_certificates

    cat > /etc/mosquitto/conf.d/zigbee.conf <<'EOF'
# Zigbee2MQTT MQTT listeners
# Managed by fix_zigbee_stack.sh

# Listener non-TLS (localhost uniquement, pour debugging et dev)
listener 1883 127.0.0.1
protocol mqtt

# Listener TLS (production, recommandé)
listener 8883 127.0.0.1
protocol mqtt
certfile /etc/mosquitto/ca_certificates/server.crt
cafile /etc/mosquitto/ca_certificates/ca.crt
keyfile /etc/mosquitto/ca_certificates/server.key
require_certificate false
tls_version tlsv1.2

# Authentification obligatoire (tous listeners)
allow_anonymous false
password_file /etc/mosquitto/passwd

# ACL (Access Control List)
acl_file /etc/mosquitto/acl.conf

# Logs
log_dest syslog
log_type error
log_type warning
log_type notice
EOF

    # ACL
    cat > /etc/mosquitto/acl.conf <<'EOF'
# ACL Zigbee2MQTT

user admin
topic readwrite #

user zigbee2mqtt
topic readwrite zigbee2mqtt/#

user avmonitoring
topic read zigbee2mqtt/#
topic write zigbee2mqtt/+/set
topic write zigbee2mqtt/bridge/request/#
EOF

    chown mosquitto:mosquitto /etc/mosquitto/conf.d/zigbee.conf
    chown mosquitto:mosquitto /etc/mosquitto/acl.conf

    echo -e "${GREEN}  ✓ Configuration Mosquitto recréée${NC}"
    MOSQUITTO_CONF_OK=1
fi

# Correction 3: Config Zigbee2MQTT manquante ou incorrecte
if [ "$Z2M_CONF_OK" = "0" ] || [ "$Z2M_OK" = "0" ]; then
    echo -e "${YELLOW}[Fix] Mise à jour de la configuration Zigbee2MQTT...${NC}"

    # Charger credentials
    if [ -f /root/zigbee_credentials.txt ]; then
        source /root/zigbee_credentials.txt
    fi

    mkdir -p /var/lib/zigbee2mqtt

    # Détecter dongle
    DONGLE=""
    if [ -e /dev/ttyUSB0 ]; then
        DONGLE="/dev/ttyUSB0"
    elif [ -e /dev/ttyACM0 ]; then
        DONGLE="/dev/ttyACM0"
    else
        DONGLE="/dev/ttyUSB0"
        echo -e "${YELLOW}  ⚠ Dongle USB non détecté, utilisation par défaut: /dev/ttyUSB0${NC}"
    fi

    cat > /var/lib/zigbee2mqtt/configuration.yaml <<EOF
# Zigbee2MQTT Configuration
homeassistant: false
permit_join: false

mqtt:
  base_topic: zigbee2mqtt
  server: mqtt://localhost:1883
  user: zigbee2mqtt
  password: ${MQTT_PASS_Z2M}
  keepalive: 60
  version: 4

serial:
  port: ${DONGLE}
  adapter: auto

advanced:
  log_level: info
  log_output:
    - console
    - file
  log_file: /var/log/zigbee2mqtt/zigbee2mqtt.log
  pan_id: GENERATE
  network_key: GENERATE
  channel: 11

frontend:
  port: 8080
  host: 127.0.0.1
EOF

    chown -R zigbee2mqtt:zigbee2mqtt /var/lib/zigbee2mqtt
    echo -e "${GREEN}  ✓ Configuration Zigbee2MQTT mise à jour${NC}"
    Z2M_CONF_OK=1
fi

# Correction 4: Variables MQTT agent manquantes
if [ "$AGENT_MQTT_VARS_OK" = "0" ]; then
    echo -e "${YELLOW}[Fix] Ajout des variables MQTT dans l'agent...${NC}"

    # Charger credentials
    if [ -f /root/zigbee_credentials.txt ]; then
        source /root/zigbee_credentials.txt
    fi

    # Retirer anciennes variables si présentes
    sed -i '/AVMVP_MQTT_/d' /etc/default/avmonitoring-agent 2>/dev/null || true

    cat >> /etc/default/avmonitoring-agent <<EOF

# Zigbee/MQTT Configuration (ajouté par fix_zigbee_stack.sh)
AVMVP_MQTT_HOST=localhost
AVMVP_MQTT_PORT=1883
AVMVP_MQTT_USER=avmonitoring
AVMVP_MQTT_PASS=${MQTT_PASS_AGENT}
AVMVP_MQTT_BASE_TOPIC=zigbee2mqtt
# TLS optionnel (utilisez port 8883 + décommentez ligne suivante pour activer)
# AVMVP_MQTT_PORT=8883
# AVMVP_MQTT_TLS_CA=/etc/mosquitto/ca_certificates/ca.crt
EOF

    chmod 640 /etc/default/avmonitoring-agent
    chown root:avmonitoring /etc/default/avmonitoring-agent 2>/dev/null || true

    echo -e "${GREEN}  ✓ Variables MQTT ajoutées${NC}"
    AGENT_MQTT_VARS_OK=1
fi

# ========================================
# 5. REDÉMARRAGE DES SERVICES
# ========================================

echo ""
echo -e "${YELLOW}[Restart] Redémarrage des services...${NC}"

# Mosquitto
if [ "$MOSQUITTO_OK" = "0" ] || [ "$MOSQUITTO_CONF_OK" = "0" ]; then
    echo -n "  Mosquitto: "
    systemctl restart mosquitto
    sleep 2
    if systemctl is-active mosquitto &>/dev/null; then
        echo -e "${GREEN}✓ Started${NC}"
    else
        echo -e "${RED}✗ Failed to start${NC}"
        echo -e "${RED}  Logs: journalctl -u mosquitto -n 20${NC}"
    fi
fi

# Zigbee2MQTT
if [ "$Z2M_OK" = "0" ] || [ "$Z2M_CONF_OK" = "0" ]; then
    echo -n "  Zigbee2MQTT: "
    systemctl restart zigbee2mqtt
    sleep 3
    if systemctl is-active zigbee2mqtt &>/dev/null; then
        echo -e "${GREEN}✓ Started${NC}"
    else
        echo -e "${RED}✗ Failed to start${NC}"
        echo -e "${RED}  Logs: journalctl -u zigbee2mqtt -n 20${NC}"
    fi
fi

# Agent
if [ "$AGENT_OK" = "0" ] || [ "$AGENT_MQTT_VARS_OK" = "0" ]; then
    echo -n "  AV Agent: "
    systemctl restart avmonitoring-agent
    sleep 2
    if systemctl is-active avmonitoring-agent &>/dev/null; then
        echo -e "${GREEN}✓ Started${NC}"
    else
        echo -e "${RED}✗ Failed to start${NC}"
        echo -e "${RED}  Logs: journalctl -u avmonitoring-agent -n 20${NC}"
    fi
fi

# ========================================
# 6. TEST FINAL
# ========================================

echo ""
echo -e "${YELLOW}[Test] Vérification finale...${NC}"
sleep 3

# Test MQTT
echo -n "  Connexion MQTT: "
if [ -f /root/zigbee_credentials.txt ]; then
    source /root/zigbee_credentials.txt
    if timeout 5 mosquitto_sub -h localhost -p 1883 \
        -u avmonitoring -P "${MQTT_PASS_AGENT}" \
        -t 'zigbee2mqtt/bridge/state' -C 1 &>/dev/null; then
        echo -e "${GREEN}✓ OK${NC}"
    else
        echo -e "${RED}✗ Failed${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Credentials manquants${NC}"
fi

# ========================================
# 7. RÉSUMÉ FINAL
# ========================================

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Résumé final${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

echo "Services:"
systemctl is-active mosquitto &>/dev/null && echo -e "  Mosquitto: ${GREEN}✓ Running${NC}" || echo -e "  Mosquitto: ${RED}✗ Stopped${NC}"
systemctl is-active zigbee2mqtt &>/dev/null && echo -e "  Zigbee2MQTT: ${GREEN}✓ Running${NC}" || echo -e "  Zigbee2MQTT: ${RED}✗ Stopped${NC}"
systemctl is-active avmonitoring-agent &>/dev/null && echo -e "  AV Agent: ${GREEN}✓ Running${NC}" || echo -e "  AV Agent: ${RED}✗ Stopped${NC}"

echo ""
echo "Prochaines étapes:"
echo "  1. Vérifier l'interface web: http://$(hostname -I | awk '{print $1}'):8080"
echo "  2. Aller dans la section 'Gestion Zigbee'"
echo "  3. Cliquer sur 'Activer jumelage' pour ajouter des appareils"
echo ""
echo "Logs utiles:"
echo "  - journalctl -u mosquitto -f"
echo "  - journalctl -u zigbee2mqtt -f"
echo "  - journalctl -u avmonitoring-agent -f"
echo ""
echo -e "${GREEN}Script terminé !${NC}"
