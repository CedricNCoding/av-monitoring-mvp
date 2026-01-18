#!/bin/bash

# Script de vérification post-installation
# Permet de valider rapidement que l'agent est correctement installé et fonctionne

# Couleurs
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="avmonitoring-agent"
INSTALL_DIR="/opt/${APP_NAME}"
CONFIG_FILE="/etc/avmonitoring/config.json"

echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Vérification de l'installation AV Monitoring Agent${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""

# Compteur de tests
PASSED=0
FAILED=0

# Fonction de test
test_check() {
    local test_name="$1"
    local test_command="$2"

    echo -n "  • $test_name... "

    if eval "$test_command" &>/dev/null; then
        echo -e "${GREEN}✓${NC}"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}✗${NC}"
        ((FAILED++))
        return 1
    fi
}

# Tests
echo -e "${YELLOW}Vérifications système :${NC}"
test_check "Python 3.10+ installé" "python3 -c 'import sys; exit(0 if sys.version_info >= (3, 10) else 1)'"
test_check "systemd disponible" "command -v systemctl"
test_check "Utilisateur avmonitoring existe" "id avmonitoring"
echo ""

echo -e "${YELLOW}Vérifications des fichiers :${NC}"
test_check "Répertoire d'installation" "test -d $INSTALL_DIR"
test_check "Code source présent" "test -f $INSTALL_DIR/src/webapp.py"
test_check "Environnement virtuel" "test -d $INSTALL_DIR/venv"
test_check "Fichier de configuration" "test -f $CONFIG_FILE"
test_check "Service systemd" "test -f /etc/systemd/system/${APP_NAME}.service"
echo ""

echo -e "${YELLOW}Vérifications du service :${NC}"
test_check "Service activé (boot)" "systemctl is-enabled $APP_NAME"
test_check "Service en cours d'exécution" "systemctl is-active $APP_NAME"
echo ""

echo -e "${YELLOW}Vérifications réseau :${NC}"
test_check "Port 8080 en écoute" "ss -tuln | grep -q ':8080'"

# Vérifier la connectivité vers le backend
if [ -f "$CONFIG_FILE" ]; then
    BACKEND_URL=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['backend_url'])" 2>/dev/null || echo "")
    if [ -n "$BACKEND_URL" ]; then
        test_check "Connectivité backend ($BACKEND_URL)" "curl -sf --max-time 5 $BACKEND_URL/health || curl -sf --max-time 5 $BACKEND_URL"
    fi
fi
echo ""

# Vérifications de configuration
echo -e "${YELLOW}Vérifications de la configuration :${NC}"
if [ -f "$CONFIG_FILE" ]; then
    # Vérifier le JSON
    if python3 -c "import json; json.load(open('$CONFIG_FILE'))" 2>/dev/null; then
        echo -e "  • Format JSON valide... ${GREEN}✓${NC}"
        ((PASSED++))

        # Vérifier les champs obligatoires
        SITE_TOKEN=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('site_token', ''))" 2>/dev/null)
        if [[ "$SITE_TOKEN" != "CHANGE_ME_AFTER_INSTALL" ]] && [[ -n "$SITE_TOKEN" ]]; then
            echo -e "  • site_token configuré... ${GREEN}✓${NC}"
            ((PASSED++))
        else
            echo -e "  • site_token configuré... ${RED}✗${NC} (token par défaut ou vide)"
            ((FAILED++))
        fi

        BACKEND_URL=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('backend_url', ''))" 2>/dev/null)
        if [[ -n "$BACKEND_URL" ]]; then
            echo -e "  • backend_url configuré... ${GREEN}✓${NC}"
            ((PASSED++))
        else
            echo -e "  • backend_url configuré... ${RED}✗${NC}"
            ((FAILED++))
        fi
    else
        echo -e "  • Format JSON valide... ${RED}✗${NC}"
        ((FAILED++))
    fi
else
    echo -e "  • Fichier de configuration... ${RED}✗${NC} (absent)"
    ((FAILED++))
fi
echo ""

# Vérifications des logs
echo -e "${YELLOW}Logs récents (5 dernières lignes) :${NC}"
if systemctl is-active --quiet $APP_NAME; then
    sudo journalctl -u $APP_NAME -n 5 --no-pager | sed 's/^/  /'
    echo ""

    # Vérifier s'il y a des erreurs récentes
    ERROR_COUNT=$(sudo journalctl -u $APP_NAME --since "5 minutes ago" | grep -ci error || echo "0")
    if [ "$ERROR_COUNT" -gt 0 ]; then
        echo -e "  ${YELLOW}⚠${NC}  $ERROR_COUNT erreur(s) dans les logs des 5 dernières minutes"
        echo -e "  ${YELLOW}⚠${NC}  Consultez : sudo journalctl -u $APP_NAME | grep -i error"
        echo ""
    fi
fi

# Résumé
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Résumé${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  Tests réussis : ${GREEN}$PASSED${NC}"
echo -e "  Tests échoués : ${RED}$FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ L'agent est correctement installé et fonctionne !${NC}"
    echo ""
    echo -e "${YELLOW}Prochaines étapes :${NC}"
    echo "  • Interface web : http://localhost:8080"
    echo "  • Logs en direct : sudo journalctl -u $APP_NAME -f"
    echo ""
    exit 0
else
    echo -e "${RED}✗ Des problèmes ont été détectés${NC}"
    echo ""
    echo -e "${YELLOW}Actions recommandées :${NC}"
    if ! systemctl is-active --quiet $APP_NAME; then
        echo "  1. Vérifier les logs : sudo journalctl -u $APP_NAME -n 50"
        echo "  2. Redémarrer le service : sudo systemctl restart $APP_NAME"
    fi
    if [[ "$SITE_TOKEN" == "CHANGE_ME_AFTER_INSTALL" ]] || [[ -z "$SITE_TOKEN" ]]; then
        echo "  3. Configurer le token : sudo nano $CONFIG_FILE"
    fi
    echo "  4. Consulter la documentation : INSTALLATION.md"
    echo ""
    exit 1
fi
