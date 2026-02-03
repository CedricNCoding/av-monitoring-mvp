#!/bin/bash
# install_zigbee_stack.sh - Installation idempotente de la stack Zigbee (Mosquitto + Zigbee2MQTT)
# Compatible Debian/Ubuntu uniquement
# Nécessite: root privileges

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

repair_mosquitto_config() {
    # Répare les installations cassées
    echo "Vérification et réparation automatique de la config Mosquitto..."
    local REPAIRED=false

    # 1. Supprimer directives persistence de conf.d/zigbee.conf (ne doivent être que dans mosquitto.conf)
    if [ -f /etc/mosquitto/conf.d/zigbee.conf ]; then
        if grep -q "persistence" /etc/mosquitto/conf.d/zigbee.conf; then
            echo "  ⚠️  Retrait directives persistence de conf.d/zigbee.conf..."
            sed -i '/^persistence /d' /etc/mosquitto/conf.d/zigbee.conf
            sed -i '/^persistence_location /d' /etc/mosquitto/conf.d/zigbee.conf
            sed -i '/^# Persistence$/d' /etc/mosquitto/conf.d/zigbee.conf
            REPAIRED=true
        fi
    fi

    # 2. Créer /etc/mosquitto/passwd si absent
    if [ ! -f /etc/mosquitto/passwd ]; then
        echo "  ⚠️  Création fichier /etc/mosquitto/passwd manquant..."
        touch /etc/mosquitto/passwd
        chown root:mosquitto /etc/mosquitto/passwd 2>/dev/null || chown root:root /etc/mosquitto/passwd
        chmod 640 /etc/mosquitto/passwd
        REPAIRED=true
    fi

    # 3. Créer /etc/mosquitto/acl.conf si absent
    if [ ! -f /etc/mosquitto/acl.conf ]; then
        echo "  ⚠️  Création fichier /etc/mosquitto/acl.conf manquant..."
        touch /etc/mosquitto/acl.conf
        chown mosquitto:mosquitto /etc/mosquitto/acl.conf
        chmod 600 /etc/mosquitto/acl.conf
        REPAIRED=true
    fi

    # 4. Corriger permissions passwd si incorrectes
    if [ -f /etc/mosquitto/passwd ]; then
        PERMS=$(stat -c %a /etc/mosquitto/passwd 2>/dev/null || stat -f %OLp /etc/mosquitto/passwd 2>/dev/null)
        if [ "$PERMS" != "640" ]; then
            echo "  ⚠️  Correction permissions /etc/mosquitto/passwd ($PERMS → 640)..."
            chmod 640 /etc/mosquitto/passwd
            REPAIRED=true
        fi

        OWNER=$(stat -c %U:%G /etc/mosquitto/passwd 2>/dev/null || stat -f %Su:%Sg /etc/mosquitto/passwd 2>/dev/null)
        if [[ "$OWNER" != "root:mosquitto" && "$OWNER" != "root:root" ]]; then
            echo "  ⚠️  Correction owner /etc/mosquitto/passwd ($OWNER → root:mosquitto)..."
            chown root:mosquitto /etc/mosquitto/passwd 2>/dev/null || chown root:root /etc/mosquitto/passwd
            REPAIRED=true
        fi
    fi

    # 5. Corriger permissions acl.conf si incorrectes
    if [ -f /etc/mosquitto/acl.conf ]; then
        PERMS=$(stat -c %a /etc/mosquitto/acl.conf 2>/dev/null || stat -f %OLp /etc/mosquitto/acl.conf 2>/dev/null)
        if [ "$PERMS" != "600" ]; then
            echo "  ⚠️  Correction permissions /etc/mosquitto/acl.conf ($PERMS → 600)..."
            chmod 600 /etc/mosquitto/acl.conf
            REPAIRED=true
        fi

        OWNER=$(stat -c %U:%G /etc/mosquitto/acl.conf 2>/dev/null || stat -f %Su:%Sg /etc/mosquitto/acl.conf 2>/dev/null)
        if [ "$OWNER" != "mosquitto:mosquitto" ]; then
            echo "  ⚠️  Correction owner /etc/mosquitto/acl.conf ($OWNER → mosquitto:mosquitto)..."
            chown mosquitto:mosquitto /etc/mosquitto/acl.conf
            REPAIRED=true
        fi
    fi

    if [ "$REPAIRED" = true ]; then
        echo -e "${GREEN}✓${NC} Réparations appliquées"
    else
        echo -e "${GREEN}✓${NC} Aucune réparation nécessaire"
    fi
}

# Fonction de diagnostic Mosquitto en cas d'échec
mosquitto_diagnostics() {
    echo ""
    echo "=========================================="
    echo "  Diagnostic Mosquitto"
    echo "=========================================="
    echo ""

    echo "[1/5] Contenu /etc/mosquitto/conf.d/zigbee.conf (120 premières lignes):"
    if [ -f /etc/mosquitto/conf.d/zigbee.conf ]; then
        nl -ba /etc/mosquitto/conf.d/zigbee.conf | sed -n '1,120p'
    else
        echo "  zigbee.conf absent"
    fi
    echo ""

    echo "[2/5] Logs récents du service (120 lignes):"
    journalctl -u mosquitto -n 120 --no-pager -o cat 2>/dev/null || echo "  Logs non disponibles"
    echo ""

    echo "[3/5] Fichiers de configuration:"
    ls -la /etc/mosquitto /etc/mosquitto/conf.d 2>/dev/null || echo "  Dossiers non accessibles"
    echo ""

    echo "[4/5] Permissions fichiers critiques:"
    [ -f /etc/mosquitto/passwd ] && ls -l /etc/mosquitto/passwd || echo "  passwd: absent"
    [ -f /etc/mosquitto/acl.conf ] && ls -l /etc/mosquitto/acl.conf || echo "  acl.conf: absent"
    echo ""

    echo "[5/5] Directives clés détectées:"
    grep -Rni "^listener\|^include_dir\|^allow_anonymous\|^password_file\|^acl_file\|^persistence[^_]\|^persistence_location\|^tls_version" /etc/mosquitto/ 2>/dev/null | head -n 30 || echo "  Aucune directive trouvée"
    echo ""
    echo "=========================================="
}

configure_mosquitto() {
    echo "Configuration de Mosquitto..."

    # Réparer config existante si cassée
    repair_mosquitto_config

    # Backup config si existe
    if [ -f /etc/mosquitto/conf.d/zigbee.conf ]; then
        cp /etc/mosquitto/conf.d/zigbee.conf /etc/mosquitto/conf.d/zigbee.conf.bak 2>/dev/null || true
    fi

    # Configuration listeners (TLS + non-TLS pour debugging)
    # IMPORTANT: Ne PAS inclure persistence/persistence_location ici (déjà dans mosquitto.conf)
    cat > /etc/mosquitto/conf.d/zigbee.conf <<'EOF'
# Zigbee2MQTT MQTT listeners
# Managed by install_zigbee_stack.sh - Do not edit manually

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

    # Configuration ACL (Access Control List)
    # Sécurité DSI : fichier ACL en lecture seule pour mosquitto uniquement
    echo "Configuration ACL Mosquitto..."

    # Backup si fichier existe
    if [ -f /etc/mosquitto/acl.conf ]; then
        cp /etc/mosquitto/acl.conf /etc/mosquitto/acl.conf.bak 2>/dev/null || true
    fi

    cat > /etc/mosquitto/acl.conf <<'EOF'
# ACL Mosquitto pour Zigbee
# Format: user <username> puis topic read|write|readwrite <topic>
# Sécurité : principe du moindre privilège (least privilege)

# User admin (gestion complète - usage interne uniquement)
user admin
topic readwrite #

# User zigbee2mqtt (lecture/écriture uniquement sur ses topics)
user zigbee2mqtt
topic readwrite zigbee2mqtt/#

# User avmonitoring (lecture devices + écriture actions + healthcheck)
# Conforme exigences DSI : pas d'accès admin, scope restreint
user avmonitoring
topic read zigbee2mqtt/#
topic write zigbee2mqtt/+/set
topic write zigbee2mqtt/bridge/request/#
topic readwrite avmvp/health/#
EOF

    # Permissions ACL : 0600 mosquitto:mosquitto (DSI-friendly)
    # Justification : fichier sensible contenant règles d'accès
    chown mosquitto:mosquitto /etc/mosquitto/acl.conf
    chmod 600 /etc/mosquitto/acl.conf
    echo -e "${GREEN}✓${NC} ACL configuré (mosquitto:mosquitto 0600)"

    # S'assurer que mosquitto.conf a les directives persistence (normalement présentes par défaut)
    # Si absentes, les ajouter (idempotent)
    if ! grep -q "^persistence true" /etc/mosquitto/mosquitto.conf 2>/dev/null; then
        echo "Ajout directives persistence dans mosquitto.conf..."
        cat >> /etc/mosquitto/mosquitto.conf <<'EOF'

# Persistence (ajouté par install_zigbee_stack.sh)
persistence true
persistence_location /var/lib/mosquitto/
EOF
    fi

    # Validation de la configuration Mosquitto (avant toute création de users)
    echo "Validation de la configuration Mosquitto..."

    # Désactiver temporairement set -e pour capturer proprement l'erreur
    # IMPORTANT: utiliser -v -d (verbose + daemonize test) pour validation complète TLS
    set +e
    VALIDATION_OUTPUT=$(mosquitto -c /etc/mosquitto/mosquitto.conf -v -d 2>&1)
    VALIDATION_RC=$?
    set -e

    if [ $VALIDATION_RC -ne 0 ]; then
        echo -e "${RED}✗ Erreur: Configuration Mosquitto invalide (RC=$VALIDATION_RC)${NC}"
        echo ""
        echo "Sortie complète mosquitto -v -d:"
        echo "$VALIDATION_OUTPUT"
        echo ""
        mosquitto_diagnostics
        exit 1
    fi
    echo -e "${GREEN}✓${NC} Configuration Mosquitto valide"

    # ========================================================================
    # Gestion des utilisateurs MQTT (password_file)
    # Sécurité DSI : permissions strictes, idempotence garantie
    # ========================================================================

    echo "Configuration des utilisateurs MQTT..."

    # Créer password_file si absent ou vide (0 octet)
    PASSWD_EMPTY=false
    if [ ! -f /etc/mosquitto/passwd ]; then
        touch /etc/mosquitto/passwd
        PASSWD_EMPTY=true
        echo -e "${GREEN}✓${NC} Fichier password créé"
    elif [ ! -s /etc/mosquitto/passwd ]; then
        # Fichier existe mais vide (0 octet) → recréer users
        PASSWD_EMPTY=true
        echo -e "${YELLOW}⚠${NC} Fichier password vide détecté, recréation des users..."
    else
        echo -e "${GREEN}✓${NC} Fichier password existe et contient des données"
    fi

    # Permissions password_file : root:root 0640 (évite warnings futures versions Mosquitto)
    # Justification :
    # - root:root → seul root peut modifier, mosquitto lit via capabilities systemd
    # - 0640 → lecture/écriture root, lecture groupe, rien pour others
    # - Évite warnings sur ownership dans Mosquitto 2.x+
    chown root:root /etc/mosquitto/passwd
    chmod 640 /etc/mosquitto/passwd

    # Gestion idempotente des credentials
    # Si /root/zigbee_credentials.txt existe, réutiliser les passwords (idempotent)
    # Sinon, générer de nouveaux passwords
    if [ -f /root/zigbee_credentials.txt ]; then
        echo "Credentials existants détectés, réutilisation..."
        source /root/zigbee_credentials.txt
    else
        echo "Génération de nouveaux credentials sécurisés..."
        MQTT_PASS_ADMIN=$(openssl rand -base64 16)
        MQTT_PASS_Z2M=$(openssl rand -base64 16)
        MQTT_PASS_AGENT=$(openssl rand -base64 16)
    fi

    # Créer/Mettre à jour les users de manière idempotente
    # Note : mosquitto_passwd -b (batch mode) met à jour si user existe, crée sinon
    # Ne pas utiliser -c (create) qui écrase le fichier !

    # Vérifier si users existent déjà
    USER_EXISTS=false
    if [ "$PASSWD_EMPTY" = false ] && grep -q "^admin:" /etc/mosquitto/passwd 2>/dev/null; then
        USER_EXISTS=true
        echo "Users MQTT déjà présents, mise à jour si nécessaire..."
    else
        echo "Création des users MQTT..."
    fi

    # Mise à jour/création users (sans -c pour ne pas écraser, sauf si vide)
    if [ "$USER_EXISTS" = false ]; then
        # Première création ou fichier vide : utiliser -c uniquement pour le premier user
        mosquitto_passwd -c -b /etc/mosquitto/passwd admin "$MQTT_PASS_ADMIN"
        mosquitto_passwd -b /etc/mosquitto/passwd zigbee2mqtt "$MQTT_PASS_Z2M"
        mosquitto_passwd -b /etc/mosquitto/passwd avmonitoring "$MQTT_PASS_AGENT"
    else
        # Mise à jour : pas de -c
        mosquitto_passwd -b /etc/mosquitto/passwd admin "$MQTT_PASS_ADMIN" 2>/dev/null || true
        mosquitto_passwd -b /etc/mosquitto/passwd zigbee2mqtt "$MQTT_PASS_Z2M" 2>/dev/null || true
        mosquitto_passwd -b /etc/mosquitto/passwd avmonitoring "$MQTT_PASS_AGENT" 2>/dev/null || true
    fi

    # Réappliquer permissions après modification (mosquitto_passwd peut les changer)
    # IMPORTANT: root:root pour éviter warnings Mosquitto 2.x+
    chown root:root /etc/mosquitto/passwd
    chmod 640 /etc/mosquitto/passwd

    # Sauvegarder les credentials (root-only, 0600)
    cat > /root/zigbee_credentials.txt <<EOF
# Credentials MQTT Zigbee (généré par install_zigbee_stack.sh)
# Fichier sensible : permissions 0600, ownership root:root
MQTT_PASS_ADMIN=$MQTT_PASS_ADMIN
MQTT_PASS_Z2M=$MQTT_PASS_Z2M
MQTT_PASS_AGENT=$MQTT_PASS_AGENT
EOF
    chmod 600 /root/zigbee_credentials.txt
    chown root:root /root/zigbee_credentials.txt

    echo -e "${GREEN}✓${NC} Users MQTT configurés (root:mosquitto 0640)"

    # ========================================================================
    # Validation finale AVANT restart (critique)
    # ========================================================================

    echo "Validation finale configuration Mosquitto..."

    # Désactiver temporairement set -e pour capturer proprement l'erreur
    # IMPORTANT: utiliser -v -d (verbose + daemonize test) pour validation complète TLS
    set +e
    VALIDATION_OUTPUT=$(mosquitto -c /etc/mosquitto/mosquitto.conf -v -d 2>&1)
    VALIDATION_RC=$?
    set -e

    if [ $VALIDATION_RC -ne 0 ]; then
        echo -e "${RED}✗ Erreur: Configuration invalide après ajout users (RC=$VALIDATION_RC)${NC}"
        echo ""
        echo "Sortie complète mosquitto -v -d:"
        echo "$VALIDATION_OUTPUT"
        echo ""
        mosquitto_diagnostics
        exit 1
    fi
    echo -e "${GREEN}✓${NC} Configuration finale valide"

    # Activer et démarrer Mosquitto (seulement après validation)
    systemctl enable mosquitto
    systemctl restart mosquitto

    # Vérifier que le service a bien démarré
    sleep 2
    if ! systemctl is-active mosquitto &> /dev/null; then
        echo -e "${RED}✗ Erreur: Mosquitto n'a pas démarré${NC}"
        echo "Logs:"
        journalctl -u mosquitto -n 20 --no-pager
        exit 1
    fi

    echo -e "${GREEN}✓${NC} Mosquitto configuré et démarré (TLS port 8883, ACL active)"
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
  server: mqtt://localhost:1883
  user: zigbee2mqtt
  password: ${MQTT_PASS_Z2M}
  keepalive: 60
  version: 4

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
AVMVP_MQTT_PORT=1883
AVMVP_MQTT_USER=avmonitoring
AVMVP_MQTT_PASS=${MQTT_PASS_AGENT}
AVMVP_MQTT_BASE_TOPIC=zigbee2mqtt
# TLS optionnel (utilisez port 8883 + décommentez ligne suivante pour activer)
# AVMVP_MQTT_PORT=8883
# AVMVP_MQTT_TLS_CA=/etc/mosquitto/ca_certificates/ca.crt
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
# 12. Test MQTT Healthcheck (pub/sub non-interactif)
# ------------------------------------------------------------

test_mqtt_health() {
    echo ""
    echo "=========================================="
    echo "  Test MQTT Healthcheck (pub/sub)"
    echo "=========================================="
    echo ""

    # Charger credentials
    source /root/zigbee_credentials.txt

    # Configuration
    MQTT_HOST="localhost"
    MQTT_PORT="8883"
    MQTT_USER="avmonitoring"
    MQTT_PASS="$MQTT_PASS_AGENT"
    CA_CERT="/etc/mosquitto/ca_certificates/ca.crt"
    TEST_TOPIC="avmvp/health/test"
    TIMEOUT=5

    echo "Configuration:"
    echo "  Host: $MQTT_HOST:$MQTT_PORT"
    echo "  User: $MQTT_USER"
    echo "  Topic: $TEST_TOPIC"
    echo ""

    # Vérifier que mosquitto-clients est installé
    if ! command -v mosquitto_sub &>/dev/null || ! command -v mosquitto_pub &>/dev/null; then
        echo -e "${YELLOW}⚠${NC}  mosquitto-clients non installé, skip test MQTT"
        echo "Installez avec: apt install mosquitto-clients"
        return 0  # Non bloquant
    fi

    # Vérifier que Mosquitto est actif
    if ! systemctl is-active mosquitto &>/dev/null; then
        echo -e "${YELLOW}⚠${NC}  Service mosquitto non actif, skip test"
        return 0  # Non bloquant
    fi

    # Créer fichier temporaire pour recevoir message
    RECEIVED_FILE=$(mktemp)
    trap "rm -f $RECEIVED_FILE" RETURN

    echo -e "${BLUE}[1/4]${NC} Démarrage subscriber en background..."

    # Lancer mosquitto_sub en background
    mosquitto_sub \
        -h "$MQTT_HOST" \
        -p "$MQTT_PORT" \
        --cafile "$CA_CERT" \
        -u "$MQTT_USER" \
        -P "$MQTT_PASS" \
        -t "$TEST_TOPIC" \
        -C 1 \
        > "$RECEIVED_FILE" 2>&1 &

    SUB_PID=$!

    # Attendre que subscriber soit connecté
    sleep 1

    # Vérifier que subscriber est toujours vivant
    if ! kill -0 $SUB_PID 2>/dev/null; then
        echo -e "${RED}✗ Erreur: mosquitto_sub a crashé${NC}"
        cat "$RECEIVED_FILE" 2>/dev/null | head -n 5
        return 1  # Bloquant
    fi

    echo -e "${GREEN}✓${NC} Subscriber actif (PID $SUB_PID)"

    # Générer message de test unique
    TEST_MESSAGE="mqtt_test_$(date +%s)"

    echo -e "${BLUE}[2/4]${NC} Publication message de test..."
    echo "  Message: $TEST_MESSAGE"

    # Publier message
    if ! mosquitto_pub \
        -h "$MQTT_HOST" \
        -p "$MQTT_PORT" \
        --cafile "$CA_CERT" \
        -u "$MQTT_USER" \
        -P "$MQTT_PASS" \
        -t "$TEST_TOPIC" \
        -m "$TEST_MESSAGE" 2>&1; then
        echo -e "${RED}✗ Erreur: échec publication MQTT${NC}"
        kill $SUB_PID 2>/dev/null || true
        return 1  # Bloquant
    fi

    echo -e "${GREEN}✓${NC} Message publié"

    echo -e "${BLUE}[3/4]${NC} Attente réception (timeout ${TIMEOUT}s)..."

    # Attendre que subscriber reçoive le message
    ELAPSED=0
    while [ $ELAPSED -lt $TIMEOUT ]; do
        if ! kill -0 $SUB_PID 2>/dev/null; then
            break  # Subscriber a terminé
        fi
        sleep 0.2
        ELAPSED=$((ELAPSED + 1))
    done

    # Tuer subscriber si toujours actif
    kill $SUB_PID 2>/dev/null || true
    wait $SUB_PID 2>/dev/null || true

    echo -e "${BLUE}[4/4]${NC} Vérification message reçu..."

    # Vérifier contenu
    if [ ! -s "$RECEIVED_FILE" ]; then
        echo -e "${RED}✗ ÉCHEC: Aucun message reçu (timeout ${TIMEOUT}s)${NC}"
        echo ""
        echo "Causes possibles:"
        echo "  - ACL incorrecte (vérifier topic avmvp/health/# dans /etc/mosquitto/acl.conf)"
        echo "  - Certificat TLS invalide"
        echo "  - Problème de connexion MQTT"
        echo ""
        echo "Debug:"
        echo "  journalctl -u mosquitto -n 20 --no-pager"
        return 1  # Bloquant
    fi

    RECEIVED_MSG=$(cat "$RECEIVED_FILE")

    if [ "$RECEIVED_MSG" = "$TEST_MESSAGE" ]; then
        echo -e "${GREEN}✓${NC} Message reçu: $RECEIVED_MSG"
        echo ""
        echo -e "${GREEN}✅ Test MQTT pub/sub réussi !${NC}"
        echo ""
        echo "Vérifications OK:"
        echo "  - Authentification user/pass"
        echo "  - TLS handshake"
        echo "  - ACL topic $TEST_TOPIC"
        echo "  - Pub/Sub fonctionnel"
        echo ""
        return 0
    else
        echo -e "${YELLOW}⚠${NC}  Message reçu différent de l'attendu"
        echo "  Attendu: $TEST_MESSAGE"
        echo "  Reçu:    $RECEIVED_MSG"
        echo ""
        return 0  # Non bloquant (test partiel réussi)
    fi
}

# ------------------------------------------------------------
# 13. Validation finale
# ------------------------------------------------------------

final_validation() {
    echo ""
    echo "=========================================="
    echo "  Validation finale de l'installation"
    echo "=========================================="
    echo ""

    local ERRORS=0

    # 1. Valider config Mosquitto
    echo -n "Configuration Mosquitto... "
    if mosquitto -c /etc/mosquitto/mosquitto.conf -v >/dev/null 2>&1; then
        echo -e "${GREEN}✓${NC}"
    else
        echo -e "${RED}✗${NC}"
        echo "Erreur de configuration Mosquitto:"
        mosquitto -c /etc/mosquitto/mosquitto.conf -v 2>&1 | grep -i error | head -n 5
        ((ERRORS++))
    fi

    # 2. Vérifier service Mosquitto
    echo -n "Service Mosquitto... "
    if systemctl is-active mosquitto &> /dev/null; then
        echo -e "${GREEN}✓ actif${NC}"
    else
        echo -e "${RED}✗ non actif${NC}"
        ((ERRORS++))
    fi

    # 3. Vérifier port MQTT
    echo -n "Port MQTT 8883... "
    if ss -tln 2>/dev/null | grep -q ':8883' || netstat -tln 2>/dev/null | grep -q ':8883'; then
        echo -e "${GREEN}✓ en écoute${NC}"
    else
        echo -e "${RED}✗ non ouvert${NC}"
        ((ERRORS++))
    fi

    # 4. Vérifier service Zigbee2MQTT (warning uniquement si dongle présent)
    echo -n "Service Zigbee2MQTT... "
    if systemctl is-active zigbee2mqtt &> /dev/null; then
        echo -e "${GREEN}✓ actif${NC}"
    elif [ -n "$DONGLE" ]; then
        echo -e "${YELLOW}⚠ non actif (dongle détecté mais service down)${NC}"
    else
        echo -e "${YELLOW}⚠ non actif (normal, pas de dongle)${NC}"
    fi

    echo ""
    if [ $ERRORS -gt 0 ]; then
        echo -e "${RED}✗ Installation terminée avec $ERRORS erreur(s)${NC}"
        echo "Consultez les logs: journalctl -u mosquitto -n 50"
        return 1
    else
        echo -e "${GREEN}✅ Validation réussie !${NC}"
        return 0
    fi
}

# ------------------------------------------------------------
# 14. Résumé final
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
    echo "2. Tester connexion MQTT (script automatique):"
    echo "   bash /opt/avmonitoring-agent/agent/scripts/test_mqtt_health.sh"
    echo ""
    echo "   Ou test manuel:"
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

    # Validation finale avant résumé
    final_validation

    # Test MQTT healthcheck (pub/sub)
    test_mqtt_health

    show_summary
}

# Exécution
main
