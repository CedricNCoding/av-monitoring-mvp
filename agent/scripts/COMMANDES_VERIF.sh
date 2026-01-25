#!/bin/bash
# Commandes de vérification après patch Mosquitto

echo "=========================================="
echo "  Vérification Installation Mosquitto"
echo "=========================================="
echo ""

echo "[1/4] Installation/Réinstallation du script..."
echo "Commande: sudo bash ./agent/scripts/install_zigbee_stack.sh"
echo ""
read -p "Lancer maintenant? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo bash ./agent/scripts/install_zigbee_stack.sh
fi
echo ""

echo "[2/4] Test validation manuelle Mosquitto (avec -d)..."
echo "Commande: sudo mosquitto -c /etc/mosquitto/mosquitto.conf -v -d; echo RC=\$?"
echo ""
read -p "Lancer maintenant? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo mosquitto -c /etc/mosquitto/mosquitto.conf -v -d
    echo "RC=$?"
fi
echo ""

echo "[3/4] Redémarrage et status du service..."
echo "Commandes:"
echo "  sudo systemctl restart mosquitto"
echo "  sudo systemctl status mosquitto --no-pager -l"
echo ""
read -p "Lancer maintenant? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo systemctl restart mosquitto
    echo ""
    sudo systemctl status mosquitto --no-pager -l
fi
echo ""

echo "[4/4] Test MQTT Pub/Sub avec user avmonitoring..."
echo "Commandes:"
echo "  source /root/zigbee_credentials.txt"
echo "  mosquitto_sub -h localhost -p 8883 --cafile /etc/mosquitto/ca_certificates/ca.crt -u avmonitoring -P \"\$MQTT_PASS_AGENT\" -t 'avmvp/health/test' -C 1 &"
echo "  sleep 1"
echo "  mosquitto_pub -h localhost -p 8883 --cafile /etc/mosquitto/ca_certificates/ca.crt -u avmonitoring -P \"\$MQTT_PASS_AGENT\" -t 'avmvp/health/test' -m 'test_ok'"
echo ""
echo "OU utiliser script autonome:"
echo "  sudo bash /opt/avmonitoring-agent/agent/scripts/test_mqtt_health.sh"
echo ""
read -p "Lancer test autonome maintenant? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if [ -f /root/zigbee_credentials.txt ]; then
        sudo bash /opt/avmonitoring-agent/agent/scripts/test_mqtt_health.sh
    else
        echo "Erreur: /root/zigbee_credentials.txt non trouvé"
        echo "Lancez d'abord install_zigbee_stack.sh"
    fi
fi
echo ""

echo "=========================================="
echo "  Vérifications Supplémentaires"
echo "=========================================="
echo ""

echo "Vérifier contenu zigbee.conf (tls_version présent):"
echo "  sudo cat /etc/mosquitto/conf.d/zigbee.conf | grep -E 'listener|tls_version|allow_anonymous'"
sudo cat /etc/mosquitto/conf.d/zigbee.conf 2>/dev/null | grep -E "listener|tls_version|allow_anonymous" || echo "Fichier non trouvé"
echo ""

echo "Vérifier permissions password file:"
echo "  stat -c '%a %U:%G' /etc/mosquitto/passwd"
stat -c "%a %U:%G" /etc/mosquitto/passwd 2>/dev/null || echo "Fichier non trouvé"
echo ""

echo "Vérifier nombre de users (doit être 3):"
echo "  wc -l /etc/mosquitto/passwd"
wc -l /etc/mosquitto/passwd 2>/dev/null || echo "Fichier non trouvé"
echo ""

echo "=========================================="
echo "✅ Tests terminés"
echo "=========================================="
