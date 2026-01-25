#!/bin/bash
# install_agent.sh - Installation autonome de l'agent AV Monitoring
# Utilisation: sudo ./install_agent.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

INSTALL_DIR="/opt/avmonitoring-agent"
AGENT_DIR="$INSTALL_DIR/agent"
CONFIG_DIR="/etc/avmonitoring"
DATA_DIR="/var/lib/avmonitoring"
LOG_DIR="/var/log/avmonitoring"
AGENT_USER="avmonitoring"
GIT_REPO="https://github.com/CedricNCoding/av-monitoring-mvp.git"

echo "=========================================="
echo "  Installation Agent AV Monitoring"
echo "=========================================="
echo ""

# Vérifier root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}✗ Erreur: Ce script doit être exécuté en root${NC}"
    echo "Utilisez: sudo $0"
    exit 1
fi

# Vérifier OS
if [ ! -f /etc/debian_version ]; then
    echo -e "${RED}✗ Erreur: Ce script est conçu pour Debian/Ubuntu${NC}"
    exit 1
fi

echo -e "${BLUE}[1/10]${NC} Vérification des prérequis..."

# Installer dépendances système
apt-get update -qq
apt-get install -y git python3 python3-pip python3-venv curl wget net-tools > /dev/null 2>&1

# Vérifier version Python
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || [ "$PYTHON_MINOR" -lt 10 ]; then
    echo -e "${RED}✗ Python 3.10+ requis (trouvé: $PYTHON_VERSION)${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} Python $PYTHON_VERSION détecté"

echo -e "${BLUE}[2/10]${NC} Création de l'utilisateur système..."

# Créer utilisateur avmonitoring SANS créer le home (-M au lieu de -m)
if ! id "$AGENT_USER" &>/dev/null; then
    useradd -r -s /bin/bash -d "$INSTALL_DIR" -M "$AGENT_USER"
    usermod -aG dialout "$AGENT_USER"  # Pour accès USB série (Zigbee)
    echo -e "${GREEN}✓${NC} Utilisateur $AGENT_USER créé"
else
    echo -e "${YELLOW}⚠${NC} Utilisateur $AGENT_USER existe déjà"
    # S'assurer qu'il est dans le groupe dialout
    usermod -aG dialout "$AGENT_USER" 2>/dev/null || true
fi

echo -e "${BLUE}[3/10]${NC} Téléchargement du code..."

# Cloner ou mettre à jour le dépôt
if [ -d "$INSTALL_DIR/.git" ]; then
    echo -e "${YELLOW}⚠${NC} Dépôt existant, mise à jour..."
    cd "$INSTALL_DIR"
    git fetch origin
    git reset --hard origin/main
    git pull origin main
else
    if [ -d "$INSTALL_DIR" ]; then
        echo -e "${YELLOW}⚠${NC} Dossier existant (non-git), suppression..."
        rm -rf "$INSTALL_DIR"
    fi
    git clone "$GIT_REPO" "$INSTALL_DIR"
fi

echo -e "${GREEN}✓${NC} Code téléchargé"

# Ajuster les permissions AVANT de créer le venv
chown -R "$AGENT_USER:$AGENT_USER" "$INSTALL_DIR"

echo -e "${BLUE}[4/10]${NC} Création de l'environnement virtuel Python..."

# Créer venv
cd "$AGENT_DIR"

# Si venv existe avec mauvaises permissions, le supprimer
if [ -d "venv" ]; then
    if [ ! -O "venv" ] || [ "$(stat -c %U venv 2>/dev/null || stat -f %Su venv 2>/dev/null)" != "$AGENT_USER" ]; then
        echo -e "${YELLOW}⚠${NC} Venv existant avec mauvaises permissions, suppression..."
        rm -rf venv
    else
        echo -e "${YELLOW}⚠${NC} Venv existe déjà, conservation"
    fi
fi

if [ ! -d "venv" ]; then
    sudo -u "$AGENT_USER" python3 -m venv venv
    echo -e "${GREEN}✓${NC} Venv créé"
fi

echo -e "${BLUE}[5/10]${NC} Installation des dépendances Python..."

# Installer dépendances
sudo -u "$AGENT_USER" bash -c "source venv/bin/activate && pip install --upgrade pip -q && pip install -r requirements.txt -q"
echo -e "${GREEN}✓${NC} Dépendances installées"

echo -e "${BLUE}[6/10]${NC} Création des répertoires système..."

# Créer répertoires
mkdir -p "$CONFIG_DIR" "$DATA_DIR" "$LOG_DIR"
chown -R "$AGENT_USER:$AGENT_USER" "$DATA_DIR" "$LOG_DIR"
echo -e "${GREEN}✓${NC} Répertoires créés"

echo -e "${BLUE}[7/10]${NC} Migration et configuration initiale..."

# Migration automatique depuis /etc si nécessaire
if [ -f "$CONFIG_DIR/config.json" ]; then
    echo -e "${YELLOW}⚠${NC} Config trouvée dans /etc/avmonitoring, migration vers /var/lib..."
    if [ -f "$AGENT_DIR/scripts/migrate_config_to_var.sh" ]; then
        bash "$AGENT_DIR/scripts/migrate_config_to_var.sh" || true
    else
        # Migration inline si le script n'existe pas
        if [ ! -f "$DATA_DIR/config.json" ]; then
            cp "$CONFIG_DIR/config.json" "$DATA_DIR/config.json"
            TIMESTAMP=$(date +%Y%m%d_%H%M%S)
            mv "$CONFIG_DIR/config.json" "$CONFIG_DIR/config.json.migrated.$TIMESTAMP"
            echo -e "${GREEN}✓${NC} Config migrée vers $DATA_DIR/config.json"
        fi
    fi
fi

# Créer config.json dans /var/lib si elle n'existe pas
if [ ! -f "$DATA_DIR/config.json" ]; then
    cat > "$DATA_DIR/config.json" <<'EOF'
{
  "site_name": "agent-default",
  "backend_url": "https://backend.avmonitoring.example.com",
  "backend_token": "CHANGE_ME",
  "poll_interval_sec": 300,
  "devices": []
}
EOF
    chown "$AGENT_USER:$AGENT_USER" "$DATA_DIR/config.json"
    chmod 640 "$DATA_DIR/config.json"
    echo -e "${GREEN}✓${NC} Config créée: $DATA_DIR/config.json"
    echo -e "${YELLOW}⚠${NC} IMPORTANT: Éditez la config avant de démarrer l'agent !"
else
    echo -e "${YELLOW}⚠${NC} Config existe déjà dans $DATA_DIR, conservation"
fi

# Créer template en lecture seule dans /etc pour référence
if [ ! -f "$CONFIG_DIR/config.json.template" ]; then
    mkdir -p "$CONFIG_DIR"
    cat > "$CONFIG_DIR/config.json.template" <<'EOF'
{
  "site_name": "agent-default",
  "backend_url": "https://backend.avmonitoring.example.com",
  "backend_token": "CHANGE_ME",
  "poll_interval_sec": 300,
  "devices": []
}
EOF
    chmod 644 "$CONFIG_DIR/config.json.template"
    echo -e "${GREEN}✓${NC} Template créé: $CONFIG_DIR/config.json.template"
fi

echo -e "${BLUE}[8/10]${NC} Installation du service systemd..."

# Copier fichiers systemd
cp "$AGENT_DIR/packaging/default/avmonitoring-agent" /etc/default/avmonitoring-agent
cp "$AGENT_DIR/packaging/systemd/avmonitoring-agent.service" /etc/systemd/system/

# Recharger systemd
systemctl daemon-reload
echo -e "${GREEN}✓${NC} Service systemd installé"

echo -e "${BLUE}[9/10]${NC} Activation du service..."

# Activer le service
systemctl enable avmonitoring-agent > /dev/null 2>&1
echo -e "${GREEN}✓${NC} Service activé (démarrage automatique au boot)"

echo -e "${BLUE}[10/10]${NC} Ajustement des permissions finales..."

# Permissions finales
chown -R "$AGENT_USER:$AGENT_USER" "$INSTALL_DIR"
echo -e "${GREEN}✓${NC} Permissions ajustées"

echo ""
echo "=========================================="
echo -e "${GREEN}✅ Installation terminée avec succès !${NC}"
echo "=========================================="
echo ""

# Afficher instructions post-installation
if [ ! -f "$CONFIG_DIR/.configured" ]; then
    echo -e "${YELLOW}⚠ Configuration requise avant le premier démarrage :${NC}"
    echo ""
    echo "1. Éditez la configuration :"
    echo "   nano $CONFIG_DIR/config.json"
    echo ""
    echo "   Modifiez :"
    echo "   - site_name       → Nom unique de l'agent"
    echo "   - backend_url     → URL du backend"
    echo "   - backend_token   → Token d'authentification"
    echo ""
    echo "2. Démarrez le service :"
    echo "   systemctl start avmonitoring-agent"
    echo ""
    echo "3. Vérifiez le status :"
    echo "   systemctl status avmonitoring-agent"
    echo ""
    echo "4. Accédez à l'UI locale :"
    echo "   http://$(hostname -I | awk '{print $1}'):8080"
    echo ""
else
    echo "Le service est prêt à démarrer :"
    echo "  systemctl start avmonitoring-agent"
    echo ""
fi

echo "Logs en direct :"
echo "  journalctl -u avmonitoring-agent -f"
echo ""

echo "Pour installer la stack Zigbee (optionnel) :"
echo "  cd $AGENT_DIR/scripts"
echo "  ./install_zigbee_stack.sh"
echo ""

# Résumé des chemins
echo "Chemins d'installation :"
echo "  Code:         $INSTALL_DIR"
echo "  Config:       $CONFIG_DIR/config.json"
echo "  Données:      $DATA_DIR"
echo "  Logs:         $LOG_DIR"
echo "  Service:      /etc/systemd/system/avmonitoring-agent.service"
echo ""
