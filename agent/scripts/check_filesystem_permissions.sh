#!/bin/bash
# check_filesystem_permissions.sh - Diagnostic filesystem permissions
# Usage: sudo ./check_filesystem_permissions.sh

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=========================================="
echo "  AV Monitoring - Filesystem Diagnostic"
echo "=========================================="
echo ""

check_dir() {
    local path=$1
    local expected_owner=$2
    local expected_perms=$3
    local name=$4

    if [ -d "$path" ]; then
        actual_owner=$(stat -c "%U:%G" "$path" 2>/dev/null || stat -f "%Su:%Sg" "$path" 2>/dev/null)
        actual_perms=$(stat -c "%a" "$path" 2>/dev/null || stat -f "%OLp" "$path" 2>/dev/null)

        if [ "$actual_owner" = "$expected_owner" ] && [ "$actual_perms" = "$expected_perms" ]; then
            echo -e "${GREEN}✓${NC} $name"
            echo "   Path: $path"
            echo "   Owner: $actual_owner | Perms: $actual_perms"
        else
            echo -e "${RED}✗${NC} $name"
            echo "   Path: $path"
            echo "   Current:  $actual_owner | $actual_perms"
            echo "   Expected: $expected_owner | $expected_perms"
            echo "   Fix: sudo chown $expected_owner $path && sudo chmod $expected_perms $path"
        fi
    else
        echo -e "${YELLOW}⚠${NC} $name"
        echo "   Path: $path (absent)"
    fi
    echo ""
}

check_file() {
    local path=$1
    local expected_owner=$2
    local expected_perms=$3
    local name=$4

    if [ -f "$path" ]; then
        actual_owner=$(stat -c "%U:%G" "$path" 2>/dev/null || stat -f "%Su:%Sg" "$path" 2>/dev/null)
        actual_perms=$(stat -c "%a" "$path" 2>/dev/null || stat -f "%OLp" "$path" 2>/dev/null)

        if [ "$actual_owner" = "$expected_owner" ] && [ "$actual_perms" = "$expected_perms" ]; then
            echo -e "${GREEN}✓${NC} $name"
            echo "   Path: $path"
            echo "   Owner: $actual_owner | Perms: $actual_perms"
        else
            echo -e "${RED}✗${NC} $name"
            echo "   Path: $path"
            echo "   Current:  $actual_owner | $actual_perms"
            echo "   Expected: $expected_owner | $expected_perms"
            echo "   Fix: sudo chown $expected_owner $path && sudo chmod $expected_perms $path"
        fi
    else
        echo -e "${YELLOW}⚠${NC} $name"
        echo "   Path: $path (absent)"
    fi
    echo ""
}

# Vérifier directories
check_dir "/etc/avmonitoring" "root:root" "755" "Config Directory (templates)"
check_dir "/var/lib/avmonitoring" "avmonitoring:avmonitoring" "750" "Runtime Data Directory"
check_dir "/var/log/avmonitoring" "avmonitoring:avmonitoring" "750" "Logs Directory"
check_dir "/opt/avmonitoring-agent" "avmonitoring:avmonitoring" "755" "Application Directory"

# Vérifier fichiers clés
check_file "/var/lib/avmonitoring/config.json" "avmonitoring:avmonitoring" "640" "Active Config (runtime)"
check_file "/etc/avmonitoring/config.json.template" "root:root" "644" "Config Template"

# Vérifier variable d'environnement
echo "=========================================="
echo "  Environment Configuration"
echo "=========================================="
echo ""

if [ -f "/etc/default/avmonitoring-agent" ]; then
    AGENT_CONFIG=$(grep "^AGENT_CONFIG=" /etc/default/avmonitoring-agent | cut -d= -f2)
    if [ "$AGENT_CONFIG" = "/var/lib/avmonitoring/config.json" ]; then
        echo -e "${GREEN}✓${NC} AGENT_CONFIG variable"
        echo "   Value: $AGENT_CONFIG (correct)"
    else
        echo -e "${RED}✗${NC} AGENT_CONFIG variable"
        echo "   Current:  $AGENT_CONFIG"
        echo "   Expected: /var/lib/avmonitoring/config.json"
        echo "   Fix: Edit /etc/default/avmonitoring-agent"
    fi
else
    echo -e "${YELLOW}⚠${NC} /etc/default/avmonitoring-agent (absent)"
fi

echo ""

# Vérifier systemd ReadWritePaths
echo "=========================================="
echo "  Systemd Configuration"
echo "=========================================="
echo ""

if systemctl cat avmonitoring-agent &>/dev/null; then
    READWRITE=$(systemctl cat avmonitoring-agent | grep "^ReadWritePaths=" | cut -d= -f2)
    if [[ "$READWRITE" == *"/var/lib/avmonitoring"* ]] && [[ "$READWRITE" != *"/etc/avmonitoring"* ]]; then
        echo -e "${GREEN}✓${NC} ReadWritePaths"
        echo "   Value: $READWRITE"
    else
        echo -e "${RED}✗${NC} ReadWritePaths"
        echo "   Current: $READWRITE"
        echo "   Should contain: /var/lib/avmonitoring /var/log/avmonitoring"
        echo "   Should NOT contain: /etc/avmonitoring"
        echo "   Fix: Update service file and run 'sudo systemctl daemon-reload'"
    fi
else
    echo -e "${YELLOW}⚠${NC} Service avmonitoring-agent not found"
fi

echo ""

# Vérifier conflits config
echo "=========================================="
echo "  Config Location Check"
echo "=========================================="
echo ""

OLD_CONFIG="/etc/avmonitoring/config.json"
NEW_CONFIG="/var/lib/avmonitoring/config.json"

if [ -f "$OLD_CONFIG" ]; then
    echo -e "${YELLOW}⚠${NC} Old config found in /etc"
    echo "   This should be migrated to /var/lib"
    echo "   Run: sudo /opt/avmonitoring-agent/agent/scripts/migrate_config_to_var.sh"
else
    echo -e "${GREEN}✓${NC} No config in /etc (correct)"
fi

if [ -f "$NEW_CONFIG" ]; then
    echo -e "${GREEN}✓${NC} Config found in /var/lib (correct)"
else
    echo -e "${RED}✗${NC} No config in /var/lib"
    echo "   Run install_agent.sh to create it"
fi

echo ""
echo "=========================================="
echo "  Summary"
echo "=========================================="
echo ""
echo "For detailed documentation, see:"
echo "  /opt/avmonitoring-agent/docs/FILESYSTEM_ARCHITECTURE.md"
echo ""
