#!/bin/bash
set -e

# Couleurs
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Déploiement Hotfix 1.1.1 - Bug backend_url${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""

# Vérifier root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}✗${NC} Ce script doit être exécuté avec les privilèges root (sudo)"
    exit 1
fi

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
AGENT_DIR="$(dirname "$SCRIPT_DIR")"
INSTALL_DIR="/opt/avmonitoring-agent"

echo -e "${YELLOW}➤${NC} Vérification des fichiers..."

if [ ! -f "$AGENT_DIR/src/collector.py" ]; then
    echo -e "${RED}✗${NC} Fichier src/collector.py non trouvé dans $AGENT_DIR"
    exit 1
fi

if [ ! -f "$AGENT_DIR/src/config_sync.py" ]; then
    echo -e "${RED}✗${NC} Fichier src/config_sync.py non trouvé dans $AGENT_DIR"
    exit 1
fi

echo -e "${GREEN}✓${NC} Fichiers trouvés"
echo ""

# Sauvegarder la config
echo -e "${YELLOW}➤${NC} Sauvegarde de la configuration..."
if [ -f "/etc/avmonitoring/config.json" ]; then
    cp /etc/avmonitoring/config.json /etc/avmonitoring/config.json.backup-$(date +%Y%m%d-%H%M%S)
    echo -e "${GREEN}✓${NC} Configuration sauvegardée"
else
    echo -e "${YELLOW}⚠${NC}  Aucune configuration à sauvegarder"
fi
echo ""

# Arrêter le service
echo -e "${YELLOW}➤${NC} Arrêt du service..."
systemctl stop avmonitoring-agent
echo -e "${GREEN}✓${NC} Service arrêté"
echo ""

# Déployer les fichiers
echo -e "${YELLOW}➤${NC} Déploiement des fichiers corrigés..."
cp "$AGENT_DIR/src/collector.py" "$INSTALL_DIR/src/"
cp "$AGENT_DIR/src/config_sync.py" "$INSTALL_DIR/src/"
echo -e "${GREEN}✓${NC} Fichiers déployés"
echo ""

# Restaurer les permissions
echo -e "${YELLOW}➤${NC} Restauration des permissions..."
chown -R avmonitoring:avmonitoring "$INSTALL_DIR/src/"
echo -e "${GREEN}✓${NC} Permissions restaurées"
echo ""

# Démarrer le service
echo -e "${YELLOW}➤${NC} Démarrage du service..."
systemctl start avmonitoring-agent
echo -e "${GREEN}✓${NC} Service démarré"
echo ""

# Attendre que le service démarre
echo -e "${YELLOW}➤${NC} Attente du démarrage (5 secondes)..."
sleep 5
echo ""

# Vérifier le statut
echo -e "${YELLOW}➤${NC} Vérification du statut..."
if systemctl is-active --quiet avmonitoring-agent; then
    echo -e "${GREEN}✓${NC} Service actif"
else
    echo -e "${RED}✗${NC} Service inactif ! Vérifiez les logs :"
    echo -e "   ${BLUE}sudo journalctl -u avmonitoring-agent -n 50${NC}"
    exit 1
fi
echo ""

echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Hotfix déployé avec succès !${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Vérifications recommandées :${NC}"
echo ""
echo "1. Consulter les logs en temps réel :"
echo "   ${BLUE}sudo journalctl -u avmonitoring-agent -f${NC}"
echo ""
echo "2. Vérifier que la collecte démarre :"
echo "   ${BLUE}sudo journalctl -u avmonitoring-agent -n 50 | grep -E 'Collector|collect'${NC}"
echo ""
echo "3. Vous devriez voir :"
echo "   - ✅ Collector started successfully"
echo "   - 🔄 [Collector] Starting collection cycle..."
echo "   - 📊 [Collector] Device X.X.X.X (ping) → online/offline"
echo "   - 📤 [Collector] Sending N device states to backend..."
echo "   - ✅ [Collector] Data sent successfully"
echo ""
echo "4. Vérifier côté backend que les équipements remontent leur statut"
echo ""
