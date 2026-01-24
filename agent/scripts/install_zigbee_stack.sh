#!/bin/bash
# install_zigbee_stack.sh - Installation idempotente de la stack Zigbee (Mosquitto + Zigbee2MQTT)
# Compatible Debian/Ubuntu uniquement
# Nécessite: root privileges

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "  Installation Stack Zigbee"
echo "  Mosquitto + Zigbee2MQTT (TLS mandatory)"
echo "=========================================="
echo ""

# ------------------------------------------------------------
# 1. Vérification prérequis
# ------------------------------------------------------------

check_root() {
    if [ "$EUID" -ne 0 ]; then
        echo -e "${RED}✗ Erreur: Ce script doit être exécuté en root${NC}"
        echo "  Utilisez: sudo $0"
        exit 1
    fi
}

check_debian_based() {
    if ! command -v apt-get &> /dev/null; then
        echo -e "${RED}✗ Erreur: Seuls Debian/Ubuntu sont supportés pour cette stack${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓${NC} Système Debian/Ubuntu détecté"
}

# ------------------------------------------------------------
# 2. Backup configuration existante
# ------------------------------------------------------------

create_backup() {
    BACKUP_DIR="/root/zigbee_backup_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"

    # Backup config agent si existe
    if [ -f /etc/avmonitoring/config.json ]; then
        cp /etc/avmonitoring/config.json "$BACKUP_DIR/" 2>/dev/null || true
    fi
    if [ -f /etc/default/avmonitoring-agent ]; then
        cp /etc/default/avmonitoring-agent "$BACKUP_DIR/" 2>/dev/null || true
    fi

    echo -e "${GREEN}✓${NC} Backup créé: $BACKUP_DIR"
}

# ------------------------------------------------------------
# 3. Installation Mosquitto
# ------------------------------------------------------------

install_mosquitto() {
    if command -v mosquitto &> /dev/null; then
        echo -e "${GREEN}✓${NC} Mosquitto déjà installé ($(mosquitto -h 2>&1 | head -n1))"
        return
    fi

    echo "Installation de Mosquitto MQTT broker..."
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y mosquitto mosquitto-clients

    # Arrêter le service pour configuration
    systemctl stop mosquitto || true

    echo -e "${GREEN}✓${NC} Mosquitto installé"
}

# ------------------------------------------------------------
# 4. Installation Node.js LTS (pour Zigbee2MQTT)
# ------------------------------------------------------------

install_nodejs() {
    if command -v node &> /dev/null; then
        NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
        if [ "$NODE_VERSION" -ge 18 ]; then
            echo -e "${GREEN}✓${NC} Node.js déjà installé (version $(node -v))"
            return
        fi
    fi

    echo "Installation de Node.js LTS (20.x)..."

    # Installer curl si absent
    if ! command -v curl &> /dev/null; then
        apt-get install -y curl
    fi

    # NodeSource repository
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs

    echo -e "${GREEN}✓${NC} Node.js $(node -v) installé"
}

# ------------------------------------------------------------
# 5. Détection dongle USB Zigbee
# ------------------------------------------------------------

detect_zigbee_dongle() {
    DONGLE=""

    if [ -e /dev/ttyUSB0 ]; then
        DONGLE="/dev/ttyUSB0"
    elif [ -e /dev/ttyUSB1 ]; then
        DONGLE="/dev/ttyUSB1"
    elif [ -e /dev/ttyACM0 ]; then
        DONGLE="/dev/ttyACM0"
    elif [ -e /dev/ttyACM1 ]; then
        DONGLE="/dev/ttyACM1"
    fi

    if [ -z "$DONGLE" ]; then
        echo -e "${YELLOW}⚠${NC} Aucun dongle Zigbee détecté (/dev/ttyUSB* ou /dev/ttyACM*)"
        echo "  L'installation continuera, mais Zigbee2MQTT ne démarrera pas"
        echo "  Branchez le dongle puis exécutez: systemctl start zigbee2mqtt"
    else
        echo -e "${GREEN}✓${NC} Dongle Zigbee détecté: $DONGLE"
    fi
}

# ------------------------------------------------------------
# 6. Génération certificats TLS (self-signed)
# ------------------------------------------------------------

generate_tls_certs() {
    CERT_DIR="/etc/mosquitto/ca_certificates"
    mkdir -p "$CERT_DIR"

    if [ -f "$CERT_DIR/ca.crt" ] && [ -f "$CERT_DIR/server.crt" ]; then
        echo -e "${GREEN}✓${NC} Certificats TLS déjà présents"
        return
    fi

    echo "Génération des certificats TLS (self-signed, validité 10 ans)..."

    # Génération CA (Certificate Authority)
    openssl req -new -x509 -days 3650 -extensions v3_ca \
        -keyout "$CERT_DIR/ca.key" -out "$CERT_DIR/ca.crt" \
        -subj "/CN=AV-Monitoring-CA" \
        -nodes 2>/dev/null

    # Génération certificat serveur
    openssl genrsa -out "$CERT_DIR/server.key" 2048 2>/dev/null
    openssl req -new -out "$CERT_DIR/server.csr" \
        -key "$CERT_DIR/server.key" \
        -subj "/CN=localhost" 2>/dev/null
    openssl x509 -req -in "$CERT_DIR/server.csr" \
        -CA "$CERT_DIR/ca.crt" -CAkey "$CERT_DIR/ca.key" \
        -CAcreateserial -out "$CERT_DIR/server.crt" -days 3650 2>/dev/null

    # Permissions
    chmod 644 "$CERT_DIR/ca.crt" "$CERT_DIR/server.crt"
    chmod 600 "$CERT_DIR/ca.key" "$CERT_DIR/server.key"
    chown -R mosquitto:mosquitto "$CERT_DIR" 2>/dev/null || true

    echo -e "${GREEN}✓${NC} Certificats TLS générés dans $CERT_DIR"
}

# ------------------------------------------------------------
# 7. Configuration Mosquitto (TLS + ACL)
# ------------------------------------------------------------

configure_mosquitto() {
    echo "Configuration de Mosquitto..."

    # Backup config si existe
    if [ -f /etc/mosquitto/conf.d/zigbee.conf ]; then
        mv /etc/mosquitto/conf.d/zigbee.conf /etc/mosquitto/conf.d/zigbee.conf.bak 2>/dev/null || true
    fi

    # Configuration listener TLS
    cat > /etc/mosquitto/conf.d/zigbee.conf <<'EOF'
# Zigbee2MQTT TLS listener (port 8883 uniquement)
listener 8883
certfile /etc/mosquitto/ca_certificates/server.crt
cafile /etc/mosquitto/ca_certificates/ca.crt
keyfile /etc/mosquitto/ca_certificates/server.key
require_certificate false
tls_version tlsv1.2

# Authentification obligatoire
allow_anonymous false
password_file /etc/mosquitto/passwd

# ACL (Access Control List)
acl_file /etc/mosquitto/acl.conf

# Persistence
persistence true
persistence_location /var/lib/mosquitto/

# Logs
log_dest syslog
log_type error
log_type warning
log_type notice
EOF

    # Configuration ACL
    cat > /etc/mosquitto/acl.conf <<'EOF'
# ACL Mosquitto pour Zigbee
# Format: user <username> puis topic read|write|readwrite <topic>

# User admin (gestion complète)
user admin
topic readwrite #

# User zigbee2mqtt (lecture/écriture sur ses topics)
user zigbee2mqtt
topic readwrite zigbee2mqtt/#

# User avmonitoring (lecture devices + écriture actions uniquement)
user avmonitoring
topic read zigbee2mqtt/#
topic write zigbee2mqtt/+/set
topic write zigbee2mqtt/bridge/request/#
EOF

    chmod 644 /etc/mosquitto/acl.conf

    # Création des utilisateurs MQTT
    if [ ! -f /etc/mosquitto/passwd ]; then
        touch /etc/mosquitto/passwd
        chmod 600 /etc/mosquitto/passwd
    fi

    # Générer mots de passe sécurisés
    MQTT_PASS_ADMIN=$(openssl rand -base64 16)
    MQTT_PASS_Z2M=$(openssl rand -base64 16)
    MQTT_PASS_AGENT=$(openssl rand -base64 16)

    # Créer les users (mosquitto_passwd écrase le fichier avec -c la première fois)
    mosquitto_passwd -c -b /etc/mosquitto/passwd admin "$MQTT_PASS_ADMIN"
    mosquitto_passwd -b /etc/mosquitto/passwd zigbee2mqtt "$MQTT_PASS_Z2M"
    mosquitto_passwd -b /etc/mosquitto/passwd avmonitoring "$MQTT_PASS_AGENT"

    # Sauvegarder les credentials
    cat > /root/zigbee_credentials.txt <<EOF
MQTT_PASS_ADMIN=$MQTT_PASS_ADMIN
MQTT_PASS_Z2M=$MQTT_PASS_Z2M
MQTT_PASS_AGENT=$MQTT_PASS_AGENT
EOF
    chmod 600 /root/zigbee_credentials.txt

    # Activer et démarrer Mosquitto
    systemctl enable mosquitto
    systemctl restart mosquitto

    echo -e "${GREEN}✓${NC} Mosquitto configuré (TLS port 8883, ACL active)"
    echo -e "${GREEN}✓${NC} Credentials sauvegardés: /root/zigbee_credentials.txt"
}

# ------------------------------------------------------------
# 8. Installation Zigbee2MQTT
# ------------------------------------------------------------

install_zigbee2mqtt() {
    Z2M_DIR="/opt/zigbee2mqtt"

    if [ -d "$Z2M_DIR" ]; then
        echo -e "${GREEN}✓${NC} Zigbee2MQTT déjà installé dans $Z2M_DIR"
        return
    fi

    echo "Installation de Zigbee2MQTT..."

    # Installer git si absent
    if ! command -v git &> /dev/null; then
        apt-get install -y git
    fi

    # Créer user système
    if ! id -u zigbee2mqtt &> /dev/null; then
        useradd --system --no-create-home --shell /usr/sbin/nologin zigbee2mqtt
        echo -e "${GREEN}✓${NC} User système 'zigbee2mqtt' créé"
    fi

    # Clone repository
    git clone --depth 1 https://github.com/Koenkk/zigbee2mqtt.git "$Z2M_DIR"
    cd "$Z2M_DIR"

    # Installer dépendances
    npm ci --production --quiet

    # Créer répertoires data et logs
    mkdir -p /var/lib/zigbee2mqtt
    mkdir -p /var/log/zigbee2mqtt
    chown -R zigbee2mqtt:zigbee2mqtt /var/lib/zigbee2mqtt /var/log/zigbee2mqtt
    chown -R zigbee2mqtt:zigbee2mqtt "$Z2M_DIR"

    echo -e "${GREEN}✓${NC} Zigbee2MQTT installé"
}

# ------------------------------------------------------------
# 9. Configuration Zigbee2MQTT
# ------------------------------------------------------------

configure_zigbee2mqtt() {
    source /root/zigbee_credentials.txt

    CONFIG_FILE="/var/lib/zigbee2mqtt/configuration.yaml"

    if [ -f "$CONFIG_FILE" ]; then
        echo -e "${YELLOW}⚠${NC} Configuration Zigbee2MQTT existe déjà, backup créé"
        cp "$CONFIG_FILE" "$CONFIG_FILE.bak"
    fi

    echo "Configuration de Zigbee2MQTT..."

    cat > "$CONFIG_FILE" <<EOF
# Zigbee2MQTT Configuration
homeassistant: false
permit_join: false

mqtt:
  base_topic: zigbee2mqtt
  server: mqtts://localhost:8883
  ca: /etc/mosquitto/ca_certificates/ca.crt
  reject_unauthorized: true
  user: zigbee2mqtt
  password: ${MQTT_PASS_Z2M}
  keepalive: 60
  version: 5

serial:
  port: ${DONGLE:-/dev/ttyUSB0}
  adapter: auto

advanced:
  log_level: info
  log_output:
    - console
    - file
  log_file: /var/log/zigbee2mqtt/zigbee2mqtt.log
  log_rotation: true
  pan_id: GENERATE
  network_key: GENERATE
  channel: 11

frontend:
  port: 8080
  host: 127.0.0.1

device_options:
  legacy: false
EOF

    chown zigbee2mqtt:zigbee2mqtt "$CONFIG_FILE"
    chmod 640 "$CONFIG_FILE"

    echo -e "${GREEN}✓${NC} Zigbee2MQTT configuré"
}

# ------------------------------------------------------------
# 10. Installation systemd service Zigbee2MQTT
# ------------------------------------------------------------

install_zigbee2mqtt_service() {
    SERVICE_FILE="/etc/systemd/system/zigbee2mqtt.service"

    if [ -f "$SERVICE_FILE" ]; then
        echo -e "${GREEN}✓${NC} Service zigbee2mqtt.service déjà présent"
    else
        cat > "$SERVICE_FILE" <<'EOF'
[Unit]
Description=Zigbee2MQTT
After=network.target mosquitto.service
Wants=mosquitto.service

[Service]
Type=simple
User=zigbee2mqtt
Group=zigbee2mqtt
WorkingDirectory=/opt/zigbee2mqtt
ExecStart=/usr/bin/node index.js
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=zigbee2mqtt

# Security
NoNewPrivileges=true
PrivateTmp=true
ReadWritePaths=/var/lib/zigbee2mqtt /var/log/zigbee2mqtt

[Install]
WantedBy=multi-user.target
EOF
        echo -e "${GREEN}✓${NC} Service systemd zigbee2mqtt.service créé"
    fi

    systemctl daemon-reload
    systemctl enable zigbee2mqtt

    # Démarrer uniquement si dongle présent
    if [ -n "$DONGLE" ]; then
        systemctl start zigbee2mqtt
        echo -e "${GREEN}✓${NC} Service zigbee2mqtt démarré"
    else
        echo -e "${YELLOW}⚠${NC} Service zigbee2mqtt non démarré (aucun dongle détecté)"
        echo "  Branchez le dongle puis: systemctl start zigbee2mqtt"
    fi
}

# ------------------------------------------------------------
# 11. Configuration agent AV Monitoring
# ------------------------------------------------------------

configure_agent_mqtt() {
    source /root/zigbee_credentials.txt

    ENV_FILE="/etc/default/avmonitoring-agent"

    if [ ! -f "$ENV_FILE" ]; then
        echo -e "${YELLOW}⚠${NC} Fichier $ENV_FILE absent, création..."
        mkdir -p /etc/default
        touch "$ENV_FILE"
    fi

    # Vérifier si déjà configuré
    if grep -q "AVMVP_MQTT_HOST" "$ENV_FILE"; then
        echo -e "${GREEN}✓${NC} Variables MQTT déjà présentes dans $ENV_FILE"
        return
    fi

    echo "Ajout des variables MQTT dans $ENV_FILE..."

    cat >> "$ENV_FILE" <<EOF

# Zigbee/MQTT Configuration (ajouté par install_zigbee_stack.sh)
AVMVP_MQTT_HOST=localhost
AVMVP_MQTT_PORT=8883
AVMVP_MQTT_USER=avmonitoring
AVMVP_MQTT_PASS=${MQTT_PASS_AGENT}
AVMVP_MQTT_TLS_CA=/etc/mosquitto/ca_certificates/ca.crt
AVMVP_MQTT_BASE_TOPIC=zigbee2mqtt
EOF

    chmod 640 "$ENV_FILE"
    chown root:avmonitoring "$ENV_FILE" 2>/dev/null || true

    # Redémarrer agent si actif
    if systemctl is-active avmonitoring-agent &> /dev/null; then
        echo "Redémarrage de l'agent AV Monitoring..."
        systemctl restart avmonitoring-agent
        echo -e "${GREEN}✓${NC} Agent redémarré avec config MQTT"
    else
        echo -e "${YELLOW}⚠${NC} Agent AV Monitoring non actif, démarrez-le manuellement"
    fi
}

# ------------------------------------------------------------
# 12. Résumé final
# ------------------------------------------------------------

show_summary() {
    echo ""
    echo "=========================================="
    echo -e "${GREEN}✅ Installation Zigbee terminée !${NC}"
    echo "=========================================="
    echo ""
    echo "Credentials MQTT sauvegardés: /root/zigbee_credentials.txt"
    echo "Backup config créé: $BACKUP_DIR"
    echo ""
    echo "Prochaines étapes:"
    echo "1. Vérifier services:"
    echo "   systemctl status mosquitto"
    echo "   systemctl status zigbee2mqtt"
    echo ""
    echo "2. Tester connexion MQTT:"
    echo "   source /root/zigbee_credentials.txt"
    echo "   mosquitto_sub -h localhost -p 8883 \\"
    echo "     --cafile /etc/mosquitto/ca_certificates/ca.crt \\"
    echo "     -u avmonitoring -P \"\$MQTT_PASS_AGENT\" \\"
    echo "     -t 'zigbee2mqtt/bridge/state' -C 1"
    echo ""
    echo "3. Vérifier agent:"
    echo "   systemctl status avmonitoring-agent"
    echo "   journalctl -u avmonitoring-agent -n 50"
    echo ""
    echo "4. Accéder interface Zigbee2MQTT (optionnel):"
    echo "   ssh -L 8080:localhost:8080 root@<votre-serveur>"
    echo "   Puis ouvrir: http://localhost:8080"
    echo ""
    echo "5. Exécuter validation complète:"
    echo "   bash /opt/avmonitoring-agent/scripts/check_zigbee_stack.sh"
    echo ""
}

# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

main() {
    check_root
    check_debian_based
    create_backup

    install_mosquitto
    install_nodejs
    detect_zigbee_dongle
    generate_tls_certs
    configure_mosquitto

    install_zigbee2mqtt
    configure_zigbee2mqtt
    install_zigbee2mqtt_service

    configure_agent_mqtt

    show_summary
}

# Exécution
main
