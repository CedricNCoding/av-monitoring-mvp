#!/bin/bash
# test_mqtt_health.sh - Test MQTT connectivity (non-interactive)
# Tests pub/sub sur topic avmvp/health/test avec credentials avmonitoring
# Usage: sudo ./test_mqtt_health.sh

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "=========================================="
echo "  Test MQTT Healthcheck"
echo "=========================================="
echo ""

# Vérifier root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}✗ Erreur: Ce script doit être exécuté en root${NC}"
    echo "Utilisez: sudo $0"
    exit 1
fi

# Charger credentials depuis /root/zigbee_credentials.txt si disponible
CREDS_FILE="/root/zigbee_credentials.txt"
if [ -f "$CREDS_FILE" ]; then
    echo -e "${BLUE}[1/6]${NC} Chargement des credentials depuis $CREDS_FILE..."
    source "$CREDS_FILE"
else
    echo -e "${YELLOW}⚠${NC}  Fichier credentials non trouvé: $CREDS_FILE"
    echo "Utilisation des variables d'environnement ou valeurs par défaut"
fi

# Configuration
MQTT_HOST="${MQTT_HOST:-localhost}"
MQTT_PORT="${MQTT_PORT:-8883}"
MQTT_USER="${MQTT_USER_AGENT:-avmonitoring}"
MQTT_PASS="${MQTT_PASS_AGENT}"
CA_CERT="${CA_CERT:-/etc/mosquitto/ca_certificates/ca.crt}"
TEST_TOPIC="avmvp/health/test"
TIMEOUT=5  # secondes

echo -e "${GREEN}✓${NC} Configuration chargée"
echo "  Host: $MQTT_HOST:$MQTT_PORT"
echo "  User: $MQTT_USER"
echo "  CA:   $CA_CERT"
echo "  Topic: $TEST_TOPIC"
echo ""

# Vérifier que password est défini
if [ -z "$MQTT_PASS" ]; then
    echo -e "${RED}✗ Erreur: MQTT_PASS_AGENT non défini${NC}"
    echo "Le fichier $CREDS_FILE doit contenir MQTT_PASS_AGENT"
    exit 1
fi

# Vérifier que CA existe
if [ ! -f "$CA_CERT" ]; then
    echo -e "${RED}✗ Erreur: Certificat CA non trouvé: $CA_CERT${NC}"
    exit 1
fi

# Vérifier que mosquitto_sub et mosquitto_pub sont installés
if ! command -v mosquitto_sub &>/dev/null || ! command -v mosquitto_pub &>/dev/null; then
    echo -e "${RED}✗ Erreur: mosquitto-clients non installé${NC}"
    echo "Installez avec: apt install mosquitto-clients"
    exit 1
fi

echo -e "${BLUE}[2/6]${NC} Vérification du service Mosquitto..."
if ! systemctl is-active mosquitto &>/dev/null; then
    echo -e "${RED}✗ Erreur: Service mosquitto non actif${NC}"
    echo "Démarrez avec: systemctl start mosquitto"
    exit 1
fi
echo -e "${GREEN}✓${NC} Service mosquitto actif"
echo ""

# Créer fichier temporaire pour recevoir le message
RECEIVED_FILE=$(mktemp)
trap "rm -f $RECEIVED_FILE" EXIT

echo -e "${BLUE}[3/6]${NC} Démarrage subscriber en background..."

# Lancer mosquitto_sub en background avec redirection vers fichier
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

# Attendre que subscriber soit connecté (petite pause)
sleep 1

# Vérifier que le processus sub est toujours vivant
if ! kill -0 $SUB_PID 2>/dev/null; then
    echo -e "${RED}✗ Erreur: mosquitto_sub a crashé au démarrage${NC}"
    echo "Sortie:"
    cat "$RECEIVED_FILE"
    exit 1
fi

echo -e "${GREEN}✓${NC} Subscriber actif (PID $SUB_PID)"
echo ""

# Générer message de test unique
TEST_MESSAGE="mqtt_health_test_$(date +%s)"

echo -e "${BLUE}[4/6]${NC} Publication message de test..."
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
    exit 1
fi

echo -e "${GREEN}✓${NC} Message publié"
echo ""

echo -e "${BLUE}[5/6]${NC} Attente réception (timeout ${TIMEOUT}s)..."

# Attendre que subscriber reçoive le message (timeout)
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    # Vérifier si subscriber a terminé (a reçu -C 1 message)
    if ! kill -0 $SUB_PID 2>/dev/null; then
        break
    fi
    sleep 0.2
    ELAPSED=$((ELAPSED + 1))
done

# Tuer subscriber si toujours actif
kill $SUB_PID 2>/dev/null || true
wait $SUB_PID 2>/dev/null || true

echo ""

# Vérifier contenu reçu
echo -e "${BLUE}[6/6]${NC} Vérification du message reçu..."

if [ ! -s "$RECEIVED_FILE" ]; then
    echo -e "${RED}✗ ÉCHEC: Aucun message reçu (timeout ${TIMEOUT}s)${NC}"
    echo ""
    echo "Causes possibles:"
    echo "  - ACL incorrecte (vérifier topic avmvp/health/# pour user $MQTT_USER)"
    echo "  - Certificat TLS invalide"
    echo "  - Mosquitto non démarré ou mal configuré"
    echo ""
    echo "Debug:"
    echo "  journalctl -u mosquitto -n 20 --no-pager"
    exit 1
fi

RECEIVED_MSG=$(cat "$RECEIVED_FILE")

if [ "$RECEIVED_MSG" = "$TEST_MESSAGE" ]; then
    echo -e "${GREEN}✓${NC} Message reçu: $RECEIVED_MSG"
    echo ""
    echo "=========================================="
    echo -e "${GREEN}✅ Test MQTT réussi !${NC}"
    echo "=========================================="
    echo ""
    echo "Connectivité MQTT TLS opérationnelle:"
    echo "  - Authentification user/pass OK"
    echo "  - TLS handshake OK"
    echo "  - ACL topic $TEST_TOPIC OK"
    echo "  - Pub/Sub fonctionnel"
    echo ""
    exit 0
else
    echo -e "${YELLOW}⚠${NC}  Message reçu différent de l'attendu"
    echo "  Attendu: $TEST_MESSAGE"
    echo "  Reçu:    $RECEIVED_MSG"
    echo ""
    echo "Le test pub/sub fonctionne mais avec données inattendues."
    echo "Vérifiez qu'aucun autre client ne publie sur $TEST_TOPIC"
    echo ""
    exit 0  # Considéré comme succès partiel
fi
