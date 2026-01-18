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

# Vérifier Python 3.10+
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗${NC} Python 3 n'est pas installé"
    echo "  Installez-le avec: sudo apt install python3 python3-pip python3-venv"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
REQUIRED_VERSION="3.10"
if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo -e "${RED}✗${NC} Python $REQUIRED_VERSION ou supérieur requis (version actuelle: $PYTHON_VERSION)"
    exit 1
fi

echo -e "${GREEN}✓${NC} Python $PYTHON_VERSION détecté"

# Vérifier systemd
if ! command -v systemctl &> /dev/null; then
    echo -e "${RED}✗${NC} systemd n'est pas disponible sur ce système"
    exit 1
fi

echo -e "${GREEN}✓${NC} systemd détecté"
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

# Copier le code source
cp -r "$AGENT_DIR/src" "$INSTALL_DIR/"
echo -e "${GREEN}✓${NC} Code source copié"

# Créer le virtualenv et installer les dépendances
echo -e "${YELLOW}➤${NC} Installation des dépendances Python..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$AGENT_DIR/requirements.txt"
echo -e "${GREEN}✓${NC} Dépendances installées"
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
        echo -e "${YELLOW}⚠${NC}  Aucun fichier config.example.json trouvé"
        echo "{}" > "$CONFIG_DIR/config.json"
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

# Installer le service systemd
echo -e "${YELLOW}➤${NC} Installation du service systemd..."
cp "$AGENT_DIR/packaging/systemd/${APP_NAME}.service" "$SERVICE_FILE"
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
echo "   sudo nano $CONFIG_DIR/config.json"
echo ""
echo "2. Configurez au minimum :"
echo "   - site_token    : Token fourni par le backend"
echo "   - backend_url   : URL du backend (ex: https://monitoring.example.com)"
echo "   - site_name     : Nom de votre site"
echo ""
echo "3. Démarrez le service :"
echo "   sudo systemctl start $APP_NAME"
echo ""
echo "4. Vérifiez le statut :"
echo "   sudo systemctl status $APP_NAME"
echo ""
echo "5. Consultez les logs :"
echo "   sudo journalctl -u $APP_NAME -f"
echo ""
echo -e "${YELLOW}Commandes utiles :${NC}"
echo "  Démarrer   : sudo systemctl start $APP_NAME"
echo "  Arrêter    : sudo systemctl stop $APP_NAME"
echo "  Redémarrer : sudo systemctl restart $APP_NAME"
echo "  Statut     : sudo systemctl status $APP_NAME"
echo "  Logs       : sudo journalctl -u $APP_NAME -f"
echo ""
echo -e "${YELLOW}Fichiers importants :${NC}"
echo "  Code        : $INSTALL_DIR"
echo "  Config      : $CONFIG_DIR/config.json"
echo "  Données     : $DATA_DIR"
echo "  Logs        : $LOG_DIR"
echo "  Service     : $SERVICE_FILE"
echo ""
