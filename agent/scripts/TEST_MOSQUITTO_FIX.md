# Test du Fix Mosquitto - install_zigbee_stack.sh

## Modifications Apportées

### 1. Couleur BLUE Ajoutée
- Ajout de la variable `BLUE='\033[0;34m'` pour les messages de progression

### 2. Validation Mosquitto Robuste (2 endroits)
**Problème:** Avec `set -e`, la commande `VALIDATION_OUTPUT=$(mosquitto ...)` qui échoue faisait sortir le script avant le `if [ $? -ne 0 ]`

**Solution:** Pattern robuste avec `set +e / set -e` :
```bash
set +e
VALIDATION_OUTPUT=$(mosquitto -c /etc/mosquitto/mosquitto.conf -v 2>&1)
VALIDATION_RC=$?
set -e

if [ $VALIDATION_RC -ne 0 ]; then
    echo -e "${RED}✗ Erreur: Configuration Mosquitto invalide${NC}"
    echo "Détails complets (30 premières lignes):"
    echo "$VALIDATION_OUTPUT" | head -n 30
    mosquitto_diagnostics  # Appel fonction de diagnostic
    exit 1
fi
```

Appliqué à:
- Validation initiale (après configuration listener/ACL)
- Validation finale (après ajout users MQTT)

### 3. Fonction de Diagnostic `mosquitto_diagnostics()`
Nouvelle fonction appelée en cas d'échec de validation :
```bash
mosquitto_diagnostics() {
    echo "[1/4] Logs récents du service:"
    journalctl -u mosquitto -n 50 --no-pager

    echo "[2/4] Fichiers de configuration:"
    ls -la /etc/mosquitto /etc/mosquitto/conf.d

    echo "[3/4] Permissions fichiers critiques:"
    ls -l /etc/mosquitto/passwd /etc/mosquitto/acl.conf

    echo "[4/4] Directives clés détectées:"
    grep -Rni "^listener|^include_dir|^allow_anonymous|^password_file|^acl_file|^persistence[^_]|^persistence_location" /etc/mosquitto/
}
```

### 4. Création /etc/mosquitto/passwd Plus Sûre
**Améliorations:**
- Vérification de l'existence avant `touch`
- Vérification que le groupe `mosquitto` existe avant `chown`
- Test de lecture par user `mosquitto` avec `sudo -u mosquitto test -r`
- Warning si mosquitto ne peut pas lire le fichier

```bash
# Créer password_file si absent
if [ ! -f /etc/mosquitto/passwd ]; then
    touch /etc/mosquitto/passwd
    echo -e "${GREEN}✓${NC} Fichier password créé"
else
    echo -e "${GREEN}✓${NC} Fichier password existe déjà"
fi

# Permissions finales garanties
if getent group mosquitto >/dev/null 2>&1; then
    chown root:mosquitto /etc/mosquitto/passwd 2>/dev/null || chown root:root /etc/mosquitto/passwd
else
    chown root:root /etc/mosquitto/passwd
fi
chmod 640 /etc/mosquitto/passwd

# Vérifier que mosquitto peut lire
if id mosquitto >/dev/null 2>&1; then
    if ! sudo -u mosquitto test -r /etc/mosquitto/passwd 2>/dev/null; then
        echo -e "${YELLOW}⚠${NC} Warning: user mosquitto cannot read passwd file"
    fi
fi
```

---

## Commandes de Test

### 1. Test Installation Complète
```bash
# Lancer le script (idempotent, peut être rejoué)
cd /opt/avmonitoring-agent
sudo bash agent/scripts/install_zigbee_stack.sh
```

**Attendu:**
- ✅ Aucun blocage sur "Validation de la configuration Mosquitto..."
- ✅ Affichage de 30 lignes d'erreur + diagnostics en cas de problème
- ✅ Messages BLUE pour les étapes du test MQTT
- ✅ Permissions correctes sur /etc/mosquitto/passwd (root:mosquitto 0640)

### 2. Vérifier Service Mosquitto
```bash
systemctl status mosquitto --no-pager -l
```

**Attendu:**
- Active (running)
- Aucune erreur de permissions
- Aucune erreur "duplicate persistence_location"

### 3. Valider Configuration Manuellement
```bash
sudo mosquitto -c /etc/mosquitto/mosquitto.conf -v
```

**Attendu:**
- Sortie propre avec version et config
- Aucune erreur "Error:" ou "Warning:"
- Mention de TLS/SSL configuré

### 4. Vérifier Permissions Fichiers Critiques
```bash
ls -la /etc/mosquitto/passwd /etc/mosquitto/acl.conf
```

**Attendu:**
```
-rw-r----- 1 root     mosquitto  XXX ... /etc/mosquitto/passwd
-rw------- 1 mosquitto mosquitto  XXX ... /etc/mosquitto/acl.conf
```

### 5. Test MQTT Pub/Sub (nouveau script standalone)
```bash
sudo bash /opt/avmonitoring-agent/agent/scripts/test_mqtt_health.sh
```

**Attendu:**
- ✅ Test MQTT pub/sub réussi
- Authentification user/pass OK
- TLS handshake OK
- ACL topic avmvp/health/test OK

### 6. Test Idempotence
```bash
# Relancer le script 2 fois de suite
sudo bash agent/scripts/install_zigbee_stack.sh
sudo bash agent/scripts/install_zigbee_stack.sh
```

**Attendu:**
- Aucune erreur
- Messages "✓ déjà installé/configuré"
- Passwords conservés (même contenu dans /root/zigbee_credentials.txt)

### 7. Test Robustesse avec Config Cassée (optionnel)
```bash
# Casser volontairement la config
sudo echo "invalid_directive true" >> /etc/mosquitto/conf.d/zigbee.conf

# Relancer le script
sudo bash agent/scripts/install_zigbee_stack.sh
```

**Attendu:**
- ❌ Validation échoue proprement (pas de blocage)
- 📋 Diagnostic complet affiché :
  - Logs journalctl
  - Liste fichiers conf.d
  - Permissions passwd/acl.conf
  - Directives clés détectées (avec "invalid_directive" visible)
- 🛑 Exit 1 avec message clair

---

## Vérifications Post-Installation

### Checklist Obligatoire
- [ ] Service mosquitto actif : `systemctl is-active mosquitto`
- [ ] Port 8883 en écoute : `ss -tln | grep 8883`
- [ ] Validation config OK : `mosquitto -c /etc/mosquitto/mosquitto.conf -v`
- [ ] Permissions passwd : `stat -c "%a %U:%G" /etc/mosquitto/passwd` → `640 root:mosquitto`
- [ ] Permissions acl.conf : `stat -c "%a %U:%G" /etc/mosquitto/acl.conf` → `600 mosquitto:mosquitto`
- [ ] Test MQTT pub/sub : `/opt/avmonitoring-agent/agent/scripts/test_mqtt_health.sh` → PASS
- [ ] Credentials sauvegardés : `test -f /root/zigbee_credentials.txt && echo OK`

### Diagnostic en Cas d'Échec
```bash
# Logs Mosquitto
journalctl -u mosquitto -n 100 --no-pager

# Configuration active
mosquitto -c /etc/mosquitto/mosquitto.conf -v 2>&1 | head -n 50

# Permissions complètes
ls -laR /etc/mosquitto/

# Directives problématiques
grep -Rni "persistence" /etc/mosquitto/
```

---

## Rollback si Nécessaire

Si l'installation échoue complètement :

```bash
# 1. Arrêter services
sudo systemctl stop mosquitto zigbee2mqtt

# 2. Restaurer backup (créé automatiquement par le script)
BACKUP=$(ls -td /root/zigbee_backup_* | head -n 1)
sudo cp $BACKUP/config.json /etc/avmonitoring/ 2>/dev/null || true
sudo cp $BACKUP/avmonitoring-agent /etc/default/ 2>/dev/null || true

# 3. Supprimer config Mosquitto cassée
sudo rm -f /etc/mosquitto/conf.d/zigbee.conf

# 4. Redémarrer Mosquitto par défaut
sudo systemctl restart mosquitto

# 5. Relancer le script après investigation
```

---

## Résumé des Garanties

✅ **Robustesse** : Validation Mosquitto ne bloque plus avec `set -e`
✅ **Diagnostic** : Messages d'erreur complets (30 lignes + journalctl + ls + grep)
✅ **Idempotence** : Script rejouable N fois sans casser l'existant
✅ **Sécurité** : Permissions DSI-friendly (root:mosquitto 0640 pour passwd)
✅ **Visibilité** : Couleur BLUE pour progression, fonction de diagnostic automatique
✅ **Testabilité** : Script autonome test_mqtt_health.sh pour validation MQTT

---

**Testeur :** _______________
**Date :** _______________
**Résultat :** ⬜ PASS  ⬜ FAIL

**Si FAIL, détails :**
_______________________________________
_______________________________________
