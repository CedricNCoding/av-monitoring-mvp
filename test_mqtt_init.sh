#!/bin/bash
# Script de test MQTT - Connexion au démarrage

echo "=========================================="
echo "  Test MQTT - Connexion au Démarrage"
echo "=========================================="
echo ""

# Couleurs
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Variables
AGENT_HOST="${AGENT_HOST:-localhost}"
AGENT_PORT="${AGENT_PORT:-8080}"

echo "[1/5] Redémarrage de l'agent..."
sudo systemctl restart avmonitoring-agent
echo -e "${GREEN}✓${NC} Agent redémarré"
echo ""

echo "[2/5] Attente démarrage (10s)..."
sleep 10
echo ""

echo "[3/5] Vérification logs agent (MQTT configured)..."
sudo journalctl -u avmonitoring-agent -n 100 --no-pager | grep "MQTT configured"
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Configuration MQTT détectée dans logs"
else
    echo -e "${YELLOW}⚠${NC} Pas de 'MQTT configured' dans logs"
fi
echo ""

echo "[4/5] Vérification logs agent (MQTT connect OK)..."
sudo journalctl -u avmonitoring-agent -n 100 --no-pager | grep "MQTT connect OK"
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Connexion MQTT réussie"
else
    echo -e "${YELLOW}⚠${NC} Pas de 'MQTT connect OK' - vérifier si MQTT configuré et Mosquitto actif"
    echo ""
    echo "Logs MQTT récents:"
    sudo journalctl -u avmonitoring-agent -n 50 --no-pager | grep -i mqtt | tail -10
fi
echo ""

echo "[5/5] Test endpoint /mqtt/health..."
HEALTH=$(curl -s http://${AGENT_HOST}:${AGENT_PORT}/mqtt/health)
echo "$HEALTH" | jq . 2>/dev/null

if [ $? -eq 0 ]; then
    CONFIGURED=$(echo "$HEALTH" | jq -r '.configured')
    CONNECTED=$(echo "$HEALTH" | jq -r '.connected')
    LAST_ERROR=$(echo "$HEALTH" | jq -r '.last_error')

    echo ""
    if [ "$CONFIGURED" = "true" ]; then
        echo -e "${GREEN}✓${NC} MQTT configuré"
    else
        echo -e "${RED}✗${NC} MQTT non configuré"
    fi

    if [ "$CONNECTED" = "true" ]; then
        echo -e "${GREEN}✓${NC} MQTT connecté"
    else
        echo -e "${RED}✗${NC} MQTT non connecté"
        if [ "$LAST_ERROR" != "null" ]; then
            echo "  Erreur: $LAST_ERROR"
        fi
    fi
else
    echo -e "${RED}✗${NC} Endpoint /mqtt/health non accessible ou erreur JSON"
fi

echo ""
echo "=========================================="
echo "  Vérifications Supplémentaires"
echo "=========================================="
echo ""

echo "Vérifier connexion Mosquitto (user avmonitoring):"
echo "  sudo journalctl -u mosquitto -n 50 --no-pager | grep \"u'avmonitoring'\""
echo ""
sudo journalctl -u mosquitto -n 50 --no-pager | grep "u'avmonitoring'" | tail -5

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Connexion détectée dans logs Mosquitto"
else
    echo -e "${YELLOW}⚠${NC} Aucune connexion 'avmonitoring' détectée dans logs Mosquitto"
fi

echo ""
echo "Vérifier que collector continue de tourner:"
echo "  sudo journalctl -u avmonitoring-agent -n 50 --no-pager | grep 'Collector'"
echo ""
sudo journalctl -u avmonitoring-agent -n 50 --no-pager | grep -i collector | tail -3

echo ""
echo "=========================================="
echo "✅ Tests terminés"
echo "=========================================="
echo ""
echo "Pour logs en temps réel:"
echo "  sudo journalctl -u avmonitoring-agent -f --no-pager"
echo ""
echo "Pour tester pub/sub manuel:"
echo "  source /root/zigbee_credentials.txt"
echo "  mosquitto_sub -h localhost -p 8883 --cafile /etc/mosquitto/ca_certificates/ca.crt -u avmonitoring -P \"\$MQTT_PASS_AGENT\" -t 'avmvp/health/test' -v"
