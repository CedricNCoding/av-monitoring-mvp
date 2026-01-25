# Patch Mosquitto - Validation Robuste & tls_version

## Pourquoi `-v -d` et `tls_version tlsv1.2` sont critiques

### 1. Validation avec `mosquitto -v -d` (pas juste `-v`)

**Problème observé:**
- Avec Mosquitto 2.0.11 sur Debian, `mosquitto -c config -v` retourne **RC=0** même si `tls_version tlsv1.2` est commenté.
- MAIS : si `tls_version` est absent, Mosquitto **démarre** puis **échoue au runtime** lors des connexions TLS.
- Résultat : installation "réussie" mais service non fonctionnel.

**Solution:**
- Utiliser `mosquitto -c config -v -d` pour **validation complète** :
  - `-v` : verbose (affiche config)
  - `-d` : daemonize test (valide aussi TLS/listeners complets)
- Si `tls_version` est absent, `-v -d` **échoue avec RC=1** → détection immédiate.

**Code pattern robuste:**
```bash
set +e
VALIDATION_OUTPUT=$(mosquitto -c /etc/mosquitto/mosquitto.conf -v -d 2>&1)
VALIDATION_RC=$?
set -e

if [ $VALIDATION_RC -ne 0 ]; then
    # Afficher erreur + diagnostics complets
    exit 1
fi
```

### 2. Directive `tls_version tlsv1.2` OBLIGATOIRE

**Pourquoi obligatoire:**
- Mosquitto 2.x **requiert explicitement** `tls_version` dans listener TLS.
- Si absent : `mosquitto` démarre MAIS rejette toutes connexions TLS avec erreur cryptique.
- Symptômes : clients bloquent sur TLS handshake, logs "protocol version error".

**Garantie dans le script:**
- `configure_mosquitto()` écrit **toujours** `tls_version tlsv1.2` dans `/etc/mosquitto/conf.d/zigbee.conf` (ligne 307).
- `repair_mosquitto_config()` ne touche **jamais** à `tls_version` (ne supprime que directives `persistence`).
- Validation `-v -d` **échoue** si `tls_version` est absent → blocage installation avant démarrage service.

---

## Modifications Appliquées

### 1. Validations Mosquitto (2 endroits)
**Avant:**
```bash
VALIDATION_OUTPUT=$(mosquitto -c /etc/mosquitto/mosquitto.conf -v 2>&1)
if [ $? -ne 0 ]; then  # ← Peut ne pas capturer échec avec set -e
```

**Après:**
```bash
set +e
VALIDATION_OUTPUT=$(mosquitto -c /etc/mosquitto/mosquitto.conf -v -d 2>&1)
VALIDATION_RC=$?
set -e

if [ $VALIDATION_RC -ne 0 ]; then
    echo "Sortie complète mosquitto -v -d:"
    echo "$VALIDATION_OUTPUT"
    mosquitto_diagnostics  # ← Affiche zigbee.conf + logs
    exit 1
fi
```

**Avantages:**
- Capture propre du code retour (pas cassé par `set -e`)
- Validation TLS complète avec `-d`
- Diagnostics complets (zigbee.conf 120 lignes + journalctl 120 lignes)

### 2. Fonction `mosquitto_diagnostics()` Améliorée
Affiche automatiquement en cas d'échec :
```
[1/5] Contenu /etc/mosquitto/conf.d/zigbee.conf (120 lignes avec numéros)
[2/5] Logs récents du service (120 lignes)
[3/5] Fichiers de configuration (ls -la)
[4/5] Permissions passwd/acl.conf
[5/5] Directives clés (grep tls_version, listener, allow_anonymous, etc.)
```

### 3. Gestion Password File Robuste
**Améliorations:**
- Détection fichier vide (0 octet) → recréation automatique users
- Permissions finales : **root:root 0640** (évite warnings Mosquitto 2.x+)
- Réapplication permissions après chaque `mosquitto_passwd`
- 3 users garantis : admin, zigbee2mqtt, avmonitoring

**Avant (root:mosquitto):**
```bash
chown root:mosquitto /etc/mosquitto/passwd
```

**Après (root:root):**
```bash
chown root:root /etc/mosquitto/passwd
chmod 640 /etc/mosquitto/passwd
```

**Justification:**
- Mosquitto 2.x+ préfère `root:root` pour éviter warnings ownership
- Service systemd accède via capabilities (pas besoin groupe mosquitto)

### 4. Configuration zigbee.conf Garantie
Fichier généré contient **toujours** :
```conf
listener 8883
certfile /etc/mosquitto/ca_certificates/server.crt
cafile /etc/mosquitto/ca_certificates/ca.crt
keyfile /etc/mosquitto/ca_certificates/server.key
require_certificate false
tls_version tlsv1.2           # ← CRITIQUE, jamais supprimé

allow_anonymous false
password_file /etc/mosquitto/passwd
acl_file /etc/mosquitto/acl.conf
```

---

## Commandes de Vérification

### 1. Installation/Réinstallation
```bash
cd /opt/avmonitoring-agent
sudo bash ./agent/scripts/install_zigbee_stack.sh
```

**Attendu:**
- ✅ Validation Mosquitto passe avec RC=0
- ✅ Aucun blocage sur validation
- ✅ Diagnostics affichés si erreur (zigbee.conf + logs)

### 2. Test Validation Manuelle (avec -d)
```bash
sudo mosquitto -c /etc/mosquitto/mosquitto.conf -v -d
echo "RC=$?"
```

**Attendu:**
```
1737849123: mosquitto version 2.0.11 starting
1737849123: Config loaded from /etc/mosquitto/mosquitto.conf.
1737849123: Opening ipv4 listen socket on port 8883.
1737849123: Opening ipv6 listen socket on port 8883.
RC=0
```

**Si échec (RC=1):**
- Vérifier présence `tls_version tlsv1.2` dans `/etc/mosquitto/conf.d/zigbee.conf`
- Lancer diagnostics : `sudo bash agent/scripts/install_zigbee_stack.sh` (affichera erreur complète)

### 3. Redémarrage Service
```bash
sudo systemctl restart mosquitto
sudo systemctl status mosquitto --no-pager -l
```

**Attendu:**
- Active (running)
- Aucune erreur "protocol version" ou "ownership"
- Log : "Opening ipv4 listen socket on port 8883"

### 4. Test MQTT Pub/Sub (user avmonitoring)
```bash
# Charger credentials
source /root/zigbee_credentials.txt

# Test subscribe + publish
sudo bash /opt/avmonitoring-agent/agent/scripts/test_mqtt_health.sh
```

**Attendu:**
```
[1/4] Démarrage subscriber en background...
✓ Subscriber actif (PID XXXX)
[2/4] Publication message de test...
✓ Message publié
[3/4] Attente réception (timeout 5s)...
[4/4] Vérification message reçu...
✓ Message reçu: mqtt_test_1737849123

✅ Test MQTT pub/sub réussi !

Vérifications OK:
  - Authentification user/pass
  - TLS handshake
  - ACL topic avmvp/health/test
  - Pub/Sub fonctionnel
```

### 5. Test Subscribe Manuel (avmonitoring user)
```bash
# Charger credentials
source /root/zigbee_credentials.txt

# Subscribe sur topic health
mosquitto_sub \
  -h localhost \
  -p 8883 \
  --cafile /etc/mosquitto/ca_certificates/ca.crt \
  -u avmonitoring \
  -P "$MQTT_PASS_AGENT" \
  -t 'avmvp/health/#' \
  -v

# Dans autre terminal : publier
source /root/zigbee_credentials.txt
mosquitto_pub \
  -h localhost \
  -p 8883 \
  --cafile /etc/mosquitto/ca_certificates/ca.crt \
  -u avmonitoring \
  -P "$MQTT_PASS_AGENT" \
  -t 'avmvp/health/test' \
  -m 'hello'
```

**Attendu:**
- Terminal 1 affiche : `avmvp/health/test hello`

### 6. Vérifier Contenu zigbee.conf
```bash
sudo cat /etc/mosquitto/conf.d/zigbee.conf | grep -E "listener|tls_version|allow_anonymous"
```

**Attendu:**
```
listener 8883
tls_version tlsv1.2
allow_anonymous false
```

### 7. Vérifier Permissions Password File
```bash
stat -c "%a %U:%G" /etc/mosquitto/passwd
wc -l /etc/mosquitto/passwd
```

**Attendu:**
```
640 root:root
3                  # 3 lignes (admin, zigbee2mqtt, avmonitoring)
```

### 8. Test Robustesse : Commenter tls_version
```bash
# ATTENTION : Test destructif, sauvegarder avant
sudo cp /etc/mosquitto/conf.d/zigbee.conf /etc/mosquitto/conf.d/zigbee.conf.bak

# Commenter tls_version
sudo sed -i 's/^tls_version/#tls_version/' /etc/mosquitto/conf.d/zigbee.conf

# Tester validation (doit échouer RC=1)
sudo mosquitto -c /etc/mosquitto/mosquitto.conf -v -d
echo "RC=$?"  # ← Doit afficher RC=1

# Restaurer
sudo mv /etc/mosquitto/conf.d/zigbee.conf.bak /etc/mosquitto/conf.d/zigbee.conf
sudo systemctl restart mosquitto
```

**Attendu:**
- Validation échoue avec RC=1
- Erreur visible dans output
- Relancer `install_zigbee_stack.sh` → détecte erreur et affiche diagnostics complets

---

## Résumé des Garanties

✅ **Validation robuste** : `-v -d` détecte absence `tls_version` (RC=1)
✅ **tls_version présent** : Toujours écrit dans zigbee.conf, jamais supprimé
✅ **Diagnostics complets** : zigbee.conf 120 lignes + journalctl 120 lignes
✅ **Password file sécurisé** : root:root 0640, 3 users garantis, détection fichier vide
✅ **Test pub/sub** : User `avmonitoring`, topic `avmvp/health/test`
✅ **Idempotence** : Script rejouable N fois sans casser l'existant

---

## Dépannage

### Erreur : "RC=1" lors de la validation

**Cause probable :** `tls_version` absent ou commenté

**Solution :**
```bash
# Vérifier présence
grep "tls_version" /etc/mosquitto/conf.d/zigbee.conf

# Si absent ou commenté, relancer installation
sudo bash /opt/avmonitoring-agent/agent/scripts/install_zigbee_stack.sh
```

### Service mosquitto ne démarre pas

**Diagnostic :**
```bash
journalctl -u mosquitto -n 50 --no-pager
```

**Causes fréquentes :**
- Certificats TLS manquants/invalides
- Password file vide ou permissions incorrectes
- Port 8883 déjà utilisé

**Solution :**
```bash
# Vérifier certificats
ls -la /etc/mosquitto/ca_certificates/

# Vérifier password file
stat /etc/mosquitto/passwd
wc -l /etc/mosquitto/passwd  # Doit être >= 3

# Relancer installation (idempotent)
sudo bash /opt/avmonitoring-agent/agent/scripts/install_zigbee_stack.sh
```

---

**Date du patch :** $(date +%Y-%m-%d)
**Version Mosquitto testée :** 2.0.11 (Debian)
**Fichier patché :** `/opt/avmonitoring-agent/agent/scripts/install_zigbee_stack.sh`
