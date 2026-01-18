#!/bin/bash
set -e

# Couleurs pour l'affichage
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
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
ENV_FILE="/etc/default/${APP_NAME}"

echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Installation de l'agent AV Monitoring${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""

# Vérifications préalables
echo -e "${YELLOW}➤${NC} Vérification des prérequis..."

# Vérifier que le script est exécuté en root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}✗${NC} Ce script doit être exécuté avec les privilèges root (sudo)"
    exit 1
fi

# Vérifier systemd
if ! command -v systemctl &> /dev/null; then
    echo -e "${RED}✗${NC} systemd n'est pas disponible sur ce système"
    exit 1
fi

echo -e "${GREEN}✓${NC} systemd détecté"

# Détecter l'OS pour savoir quelle commande utiliser
if command -v apt-get &> /dev/null; then
    PKG_MANAGER="apt-get"
    PKG_UPDATE="apt-get update -qq"
    PKG_INSTALL="apt-get install -y -qq"
elif command -v yum &> /dev/null; then
    PKG_MANAGER="yum"
    PKG_UPDATE="yum check-update || true"
    PKG_INSTALL="yum install -y -q"
else
    echo -e "${RED}✗${NC} Gestionnaire de paquets non supporté (apt-get ou yum requis)"
    exit 1
fi

echo -e "${GREEN}✓${NC} Gestionnaire de paquets: $PKG_MANAGER"
echo ""

# Installer les dépendances système
echo -e "${YELLOW}➤${NC} Installation des dépendances système..."
echo "  Mise à jour des dépôts..."
$PKG_UPDATE > /dev/null 2>&1

PACKAGES_TO_INSTALL=""

# Vérifier Python 3
if ! command -v python3 &> /dev/null; then
    PACKAGES_TO_INSTALL="$PACKAGES_TO_INSTALL python3"
fi

# Vérifier python3-venv
if ! python3 -m venv --help &> /dev/null 2>&1; then
    PACKAGES_TO_INSTALL="$PACKAGES_TO_INSTALL python3-venv"
fi

# Vérifier python3-pip
if ! command -v pip3 &> /dev/null && ! python3 -m pip --version &> /dev/null 2>&1; then
    PACKAGES_TO_INSTALL="$PACKAGES_TO_INSTALL python3-pip"
fi

# Vérifier ping
if ! command -v ping &> /dev/null; then
    PACKAGES_TO_INSTALL="$PACKAGES_TO_INSTALL iputils-ping"
fi

# Vérifier ca-certificates
if [ ! -d /etc/ssl/certs ] || [ -z "$(ls -A /etc/ssl/certs)" ]; then
    PACKAGES_TO_INSTALL="$PACKAGES_TO_INSTALL ca-certificates"
fi

# Vérifier libcap2-bin (pour setcap)
if ! command -v setcap &> /dev/null; then
    PACKAGES_TO_INSTALL="$PACKAGES_TO_INSTALL libcap2-bin"
fi

if [ -n "$PACKAGES_TO_INSTALL" ]; then
    echo "  Installation de:$PACKAGES_TO_INSTALL"
    $PKG_INSTALL $PACKAGES_TO_INSTALL
    echo -e "${GREEN}✓${NC} Dépendances système installées"
else
    echo -e "${GREEN}✓${NC} Toutes les dépendances sont déjà installées"
fi

# Vérifier la version Python après installation
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
REQUIRED_VERSION="3.10"
if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo -e "${YELLOW}⚠${NC}  Python $PYTHON_VERSION détecté (< $REQUIRED_VERSION recommandé)"
    echo "    L'installation continue mais des problèmes peuvent survenir"
else
    echo -e "${GREEN}✓${NC} Python $PYTHON_VERSION détecté"
fi
echo ""

# Créer l'utilisateur système si nécessaire
echo -e "${YELLOW}➤${NC} Configuration de l'utilisateur système..."
if ! id "$APP_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$APP_USER"
    echo -e "${GREEN}✓${NC} Utilisateur $APP_USER créé"
else
    echo -e "${GREEN}✓${NC} Utilisateur $APP_USER existe déjà"
fi
echo ""

# Créer les répertoires
echo -e "${YELLOW}➤${NC} Création des répertoires..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$CONFIG_DIR"
mkdir -p "$DATA_DIR"
mkdir -p "$LOG_DIR"
echo -e "${GREEN}✓${NC} Répertoires créés"
echo ""

# Copier les fichiers de l'application
echo -e "${YELLOW}➤${NC} Installation des fichiers de l'application..."
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
AGENT_DIR="$(dirname "$SCRIPT_DIR")"

# Vérifier que le code source existe
if [ ! -d "$AGENT_DIR/src" ]; then
    echo -e "${RED}✗${NC} Répertoire src/ non trouvé dans $AGENT_DIR"
    echo "    Le script doit être exécuté depuis le répertoire de l'agent"
    exit 1
fi

# Copier le code source
cp -r "$AGENT_DIR/src" "$INSTALL_DIR/"
echo -e "${GREEN}✓${NC} Code source copié"

# Créer le virtualenv et installer les dépendances
echo -e "${YELLOW}➤${NC} Installation des dépendances Python..."
if [ ! -f "$AGENT_DIR/requirements.txt" ]; then
    echo -e "${RED}✗${NC} Fichier requirements.txt non trouvé"
    exit 1
fi

echo "  Création de l'environnement virtuel..."
python3 -m venv "$INSTALL_DIR/venv"

echo "  Installation des dépendances (cela peut prendre quelques minutes)..."
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$AGENT_DIR/requirements.txt"
echo -e "${GREEN}✓${NC} Dépendances Python installées"
echo ""

# Créer le fichier de configuration si nécessaire
echo -e "${YELLOW}➤${NC} Configuration de l'agent..."
if [ ! -f "$CONFIG_DIR/config.json" ]; then
    if [ -f "$AGENT_DIR/config.example.json" ]; then
        cp "$AGENT_DIR/config.example.json" "$CONFIG_DIR/config.json"
        echo -e "${GREEN}✓${NC} Fichier de configuration créé depuis l'exemple"
        echo -e "${YELLOW}⚠${NC}  IMPORTANT : Éditez $CONFIG_DIR/config.json et configurez :"
        echo "     - site_token (récupérez-le depuis le backend)"
        echo "     - backend_url"
        echo "     - site_name"
    else
        # Créer une config minimale
        cat > "$CONFIG_DIR/config.json" << 'EOF'
{
  "site_name": "site-demo",
  "site_token": "CHANGE_ME_AFTER_INSTALL",
  "backend_url": "https://avmonitoring.example.com",
  "timezone": "Europe/Paris",
  "doubt_after_days": 2,
  "reporting": {
    "ok_interval_s": 300,
    "ko_interval_s": 60
  },
  "devices": []
}
EOF
        echo -e "${GREEN}✓${NC} Fichier de configuration créé (configuration par défaut)"
        echo -e "${YELLOW}⚠${NC}  IMPORTANT : Éditez $CONFIG_DIR/config.json et configurez :"
        echo "     - site_token (récupérez-le depuis le backend)"
        echo "     - backend_url"
        echo "     - site_name"
    fi
else
    echo -e "${GREEN}✓${NC} Fichier de configuration existe déjà (non modifié)"
fi
echo ""

# Définir les permissions
echo -e "${YELLOW}➤${NC} Configuration des permissions..."
chown -R "$APP_USER:$APP_GROUP" "$INSTALL_DIR"
chown -R "$APP_USER:$APP_GROUP" "$CONFIG_DIR"
chown -R "$APP_USER:$APP_GROUP" "$DATA_DIR"
chown -R "$APP_USER:$APP_GROUP" "$LOG_DIR"
chmod 750 "$INSTALL_DIR"
chmod 750 "$CONFIG_DIR"
chmod 640 "$CONFIG_DIR/config.json"
echo -e "${GREEN}✓${NC} Permissions configurées"
echo ""

# Configurer cap_net_raw pour ping
echo -e "${YELLOW}➤${NC} Configuration des capacités réseau pour ping..."
PING_PATH=$(which ping)
if [ -n "$PING_PATH" ]; then
    # Vérifier si cap_net_raw est déjà configuré
    if getcap "$PING_PATH" 2>/dev/null | grep -q "cap_net_raw"; then
        echo -e "${GREEN}✓${NC} cap_net_raw déjà configuré sur $PING_PATH"
    else
        setcap cap_net_raw+ep "$PING_PATH"
        echo -e "${GREEN}✓${NC} cap_net_raw configuré sur $PING_PATH"
    fi
else
    echo -e "${YELLOW}⚠${NC}  ping non trouvé, capacités non configurées"
fi
echo ""

# Installer le fichier d'environnement
echo -e "${YELLOW}➤${NC} Installation du fichier d'environnement..."
if [ -f "$AGENT_DIR/packaging/default/${APP_NAME}" ]; then
    cp "$AGENT_DIR/packaging/default/${APP_NAME}" "$ENV_FILE"
    echo -e "${GREEN}✓${NC} Fichier d'environnement installé: $ENV_FILE"
else
    # Créer un fichier d'environnement par défaut
    cat > "$ENV_FILE" << EOF
# Configuration file for avmonitoring-agent service
PYTHONPATH=/opt/avmonitoring-agent
AGENT_CONFIG=/etc/avmonitoring/config.json
CONFIG_SYNC_INTERVAL_MIN=5
EOF
    echo -e "${GREEN}✓${NC} Fichier d'environnement créé: $ENV_FILE"
fi
echo ""

# Installer le service systemd
echo -e "${YELLOW}➤${NC} Installation du service systemd..."
if [ -f "$AGENT_DIR/packaging/systemd/${APP_NAME}.service" ]; then
    cp "$AGENT_DIR/packaging/systemd/${APP_NAME}.service" "$SERVICE_FILE"
else
    echo -e "${RED}✗${NC} Fichier de service systemd non trouvé"
    exit 1
fi
systemctl daemon-reload
echo -e "${GREEN}✓${NC} Service systemd installé"
echo ""

# Activer et démarrer le service
echo -e "${YELLOW}➤${NC} Activation du service..."
systemctl enable "$APP_NAME"
echo -e "${GREEN}✓${NC} Service activé (démarrage automatique au boot)"
echo ""

echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Installation terminée avec succès !${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Prochaines étapes :${NC}"
echo ""
echo "1. Éditez la configuration :"
echo "   ${BLUE}sudo nano $CONFIG_DIR/config.json${NC}"
echo ""
echo "2. Configurez au minimum :"
echo "   - ${BLUE}site_token${NC}    : Token fourni par le backend"
echo "   - ${BLUE}backend_url${NC}   : URL du backend (ex: https://monitoring.example.com)"
echo "   - ${BLUE}site_name${NC}     : Nom de votre site"
echo ""
echo "3. Démarrez le service :"
echo "   ${BLUE}sudo systemctl start $APP_NAME${NC}"
echo ""
echo "4. Vérifiez le statut :"
echo "   ${BLUE}sudo systemctl status $APP_NAME${NC}"
echo ""
echo "5. Consultez les logs :"
echo "   ${BLUE}sudo journalctl -u $APP_NAME -f${NC}"
echo ""
echo "6. Vérifiez l'installation (optionnel) :"
echo "   ${BLUE}sudo $SCRIPT_DIR/check-install.sh${NC}"
echo ""
echo -e "${YELLOW}Commandes utiles :${NC}"
echo "  Démarrer   : ${BLUE}sudo systemctl start $APP_NAME${NC}"
echo "  Arrêter    : ${BLUE}sudo systemctl stop $APP_NAME${NC}"
echo "  Redémarrer : ${BLUE}sudo systemctl restart $APP_NAME${NC}"
echo "  Statut     : ${BLUE}sudo systemctl status $APP_NAME${NC}"
echo "  Logs       : ${BLUE}sudo journalctl -u $APP_NAME -f${NC}"
echo ""
echo -e "${YELLOW}Fichiers importants :${NC}"
echo "  Code        : ${BLUE}$INSTALL_DIR${NC}"
echo "  Config      : ${BLUE}$CONFIG_DIR/config.json${NC}"
echo "  Env vars    : ${BLUE}$ENV_FILE${NC}"
echo "  Données     : ${BLUE}$DATA_DIR${NC}"
echo "  Logs        : ${BLUE}$LOG_DIR${NC}"
echo "  Service     : ${BLUE}$SERVICE_FILE${NC}"
echo ""
