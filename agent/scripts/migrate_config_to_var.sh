#!/bin/bash
# migrate_config_to_var.sh - Migrate config.json from /etc to /var/lib
# Automatically called by install_agent.sh, can also be run manually
# Idempotent: safe to run multiple times

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

OLD_CONFIG="/etc/avmonitoring/config.json"
NEW_CONFIG="/var/lib/avmonitoring/config.json"
AGENT_USER="avmonitoring"

echo "=========================================="
echo "  Migration Config: /etc → /var/lib"
echo "=========================================="
echo ""

# Check if migration is needed
if [ ! -f "$OLD_CONFIG" ]; then
    echo -e "${BLUE}ℹ${NC}  No config found in /etc/avmonitoring, nothing to migrate"
    exit 0
fi

if [ -f "$NEW_CONFIG" ]; then
    echo -e "${YELLOW}⚠${NC}  Config already exists in /var/lib/avmonitoring"
    echo "   Old: $OLD_CONFIG"
    echo "   New: $NEW_CONFIG (already migrated)"

    # Ask user what to do
    read -p "Keep existing /var/lib config? (yes/no): " KEEP_NEW
    if [ "$KEEP_NEW" != "yes" ]; then
        echo "Migration cancelled by user"
        exit 0
    fi

    # Backup old config but don't overwrite new one
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP="$OLD_CONFIG.pre-migration.$TIMESTAMP"
    cp "$OLD_CONFIG" "$BACKUP"
    echo -e "${GREEN}✓${NC} Old config backed up: $BACKUP"
    echo -e "${BLUE}ℹ${NC}  Keeping current /var/lib config (no overwrite)"
    exit 0
fi

# Perform migration
echo -e "${BLUE}[1/4]${NC} Creating /var/lib/avmonitoring directory..."
mkdir -p /var/lib/avmonitoring
echo -e "${GREEN}✓${NC} Directory created"

echo -e "${BLUE}[2/4]${NC} Copying config from /etc to /var/lib..."
cp "$OLD_CONFIG" "$NEW_CONFIG"
echo -e "${GREEN}✓${NC} Config copied"

echo -e "${BLUE}[3/4]${NC} Setting permissions..."
chown "$AGENT_USER:$AGENT_USER" /var/lib/avmonitoring
chown "$AGENT_USER:$AGENT_USER" "$NEW_CONFIG"
chmod 750 /var/lib/avmonitoring
chmod 640 "$NEW_CONFIG"
echo -e "${GREEN}✓${NC} Permissions set"

echo -e "${BLUE}[4/4]${NC} Backing up old config..."
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP="$OLD_CONFIG.migrated.$TIMESTAMP"
mv "$OLD_CONFIG" "$BACKUP"
echo -e "${GREEN}✓${NC} Old config backed up: $BACKUP"

echo ""
echo "=========================================="
echo -e "${GREEN}✅ Migration completed successfully${NC}"
echo "=========================================="
echo ""
echo "Config locations:"
echo "  New (active): $NEW_CONFIG"
echo "  Backup:       $BACKUP"
echo ""
echo "The agent will now read from /var/lib/avmonitoring/config.json"
echo ""
