# Sécurisation Mosquitto - Configuration DSI-Friendly

## Vue d'Ensemble

Ce document décrit les améliorations de sécurité appliquées à l'installation Mosquitto dans le projet AV Monitoring MVP, conformément aux exigences DSI (Direction des Systèmes d'Information).

---

## Changements Appliqués

### 1. Sécurisation du Password File

**Fichier :** `/etc/mosquitto/passwd`

**Avant :**
- Permissions : `0600` (root:root implicite)
- Problème : Trop restrictif, Mosquitto ne peut pas lire sous user `mosquitto`

**Après :**
```bash
Owner: root:mosquitto
Permissions: 0640
```

**Justification DSI :**
- `root` seul propriétaire → seul root peut modifier les passwords
- Groupe `mosquitto` en lecture → service peut authentifier les clients
- `0640` → rw-r----- (root écrit, mosquitto lit, others rien)
- Conforme principe du moindre privilège

**Implémentation :**
```bash
chown root:mosquitto /etc/mosquitto/passwd
chmod 640 /etc/mosquitto/passwd
```

### 2. Sécurisation des ACL

**Fichier :** `/etc/mosquitto/acl.conf`

**Avant :**
- Permissions : `0644` (lecture publique)
- Problème : Fichier sensible lisible par tous les users système

**Après :**
```bash
Owner: mosquitto:mosquitto
Permissions: 0600
```

**Justification DSI :**
- Fichier contient règles d'accès sensibles
- Seul le service Mosquitto doit pouvoir lire
- `0600` → rw------- (mosquitto seul)
- Aucun autre process système ne doit accéder aux ACL

**Implémentation :**
```bash
chown mosquitto:mosquitto /etc/mosquitto/acl.conf
chmod 600 /etc/mosquitto/acl.conf
```

### 3. Idempotence de la Création des Users

**Problème initial :**
```bash
# AVANT - Écrase le fichier à chaque exécution
mosquitto_passwd -c -b /etc/mosquitto/passwd admin "password"
```

**Solution :**
```bash
# Détection users existants
if grep -q "^admin:" /etc/mosquitto/passwd; then
    # Mise à jour sans -c (ne pas écraser)
    mosquitto_passwd -b /etc/mosquitto/passwd admin "$PASS"
else
    # Première création avec -c
    mosquitto_passwd -c -b /etc/mosquitto/passwd admin "$PASS"
fi
```

**Avantages :**
- Script relançable sans perte de données
- Passwords conservés si déjà générés
- Pas de rupture de service lors de mises à jour

### 4. Réutilisation des Credentials

**Fichier :** `/root/zigbee_credentials.txt`

**Logique :**
```bash
if [ -f /root/zigbee_credentials.txt ]; then
    # Réutiliser passwords existants
    source /root/zigbee_credentials.txt
else
    # Générer nouveaux passwords
    MQTT_PASS_ADMIN=$(openssl rand -base64 16)
    # ...
fi
```

**Avantages :**
- Idempotence garantie
- Pas de régénération inutile (casse connexions actives)
- Facilite rollback et debug

### 5. Validation Avant Restart

**Implémentation :**
```bash
# Validation 1 : Après écriture config
mosquitto -c /etc/mosquitto/mosquitto.conf -v >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "Erreur de configuration"
    exit 1
fi

# Validation 2 : Après ajout users
mosquitto -c /etc/mosquitto/mosquitto.conf -v >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "Erreur après ajout users"
    exit 1
fi

# Restart seulement si tout est valide
systemctl restart mosquitto
```

**Avantages :**
- Détection erreurs avant impact production
- Pas de rupture de service si config invalide
- Logs explicites en cas d'erreur

### 6. Vérification Post-Restart

**Implémentation :**
```bash
systemctl restart mosquitto
sleep 2

if ! systemctl is-active mosquitto &> /dev/null; then
    echo "Erreur: Mosquitto n'a pas démarré"
    journalctl -u mosquitto -n 20
    exit 1
fi
```

**Avantages :**
- Détection immédiate si service ne démarre pas
- Affichage logs pertinents pour debug
- Exit code non-zero pour CI/CD

---

## Structure des Permissions

### Résumé des Fichiers Sensibles

| Fichier | Owner | Group | Permissions | Justification |
|---------|-------|-------|-------------|---------------|
| `/etc/mosquitto/passwd` | root | mosquitto | 0640 | Root modifie, mosquitto lit |
| `/etc/mosquitto/acl.conf` | mosquitto | mosquitto | 0600 | Mosquitto seul |
| `/root/zigbee_credentials.txt` | root | root | 0600 | Root seul |
| `/etc/mosquitto/ca_certificates/ca.crt` | mosquitto | mosquitto | 0644 | Public (certificat CA) |
| `/etc/mosquitto/ca_certificates/server.key` | mosquitto | mosquitto | 0600 | Privée (clé serveur) |

### Principe du Moindre Privilège

Chaque fichier a les permissions **minimales** nécessaires :
- Password file : root écrit, mosquitto lit (0640)
- ACL : mosquitto seul (0600)
- Clés privées : propriétaire seul (0600)
- Certificats publics : lecture publique OK (0644)

---

## ACL Configurées

### User `admin` (usage interne)
```conf
user admin
topic readwrite #
```
- Accès total (wildcard `#`)
- Usage : debug, monitoring interne

### User `zigbee2mqtt` (service Zigbee2MQTT)
```conf
user zigbee2mqtt
topic readwrite zigbee2mqtt/#
```
- Accès restreint au namespace `zigbee2mqtt/*`
- Lecture/écriture sur ses propres topics uniquement

### User `avmonitoring` (agent AV Monitoring)
```conf
user avmonitoring
topic read zigbee2mqtt/#
topic write zigbee2mqtt/+/set
topic write zigbee2mqtt/bridge/request/#
```
- **Lecture** : tous les topics Zigbee (devices, états)
- **Écriture** : uniquement actions (`/set`) et requests (`/bridge/request/*`)
- **Pas d'accès** : topics admin, config, autres namespaces
- Conforme exigence DSI : moindre privilège

---

## Tests de Validation

### 1. Vérifier Permissions

```bash
# Password file
ls -la /etc/mosquitto/passwd
# Attendu : -rw-r----- 1 root mosquitto

# ACL file
ls -la /etc/mosquitto/acl.conf
# Attendu : -rw------- 1 mosquitto mosquitto

# Credentials
ls -la /root/zigbee_credentials.txt
# Attendu : -rw------- 1 root root
```

### 2. Valider Configuration

```bash
sudo mosquitto -c /etc/mosquitto/mosquitto.conf -v
# Attendu : Aucune erreur, affiche "Config loaded"
```

### 3. Tester Authentification

```bash
# User valide
mosquitto_sub -h localhost -p 8883 \
  --cafile /etc/mosquitto/ca_certificates/ca.crt \
  -u avmonitoring -P "password" \
  -t 'zigbee2mqtt/#' -C 1 -W 2

# User invalide (doit échouer)
mosquitto_sub -h localhost -p 8883 \
  --cafile /etc/mosquitto/ca_certificates/ca.crt \
  -u fake -P "fake" \
  -t '#' -C 1 -W 2
# Attendu : Connection refused (not authorized)
```

### 4. Tester ACL

```bash
# User avmonitoring : lecture OK
mosquitto_sub -h localhost -p 8883 \
  --cafile /etc/mosquitto/ca_certificates/ca.crt \
  -u avmonitoring -P "password" \
  -t 'zigbee2mqtt/bridge/state' -C 1 -W 2
# Attendu : Reçoit le message

# User avmonitoring : écriture hors scope (doit échouer)
mosquitto_pub -h localhost -p 8883 \
  --cafile /etc/mosquitto/ca_certificates/ca.crt \
  -u avmonitoring -P "password" \
  -t 'admin/test' -m 'test'
# Attendu : Publish refused (ACL deny)
```

### 5. Tester Idempotence

```bash
# Exécuter 2 fois
sudo /opt/avmonitoring-agent/scripts/install_zigbee_stack.sh
sudo /opt/avmonitoring-agent/scripts/install_zigbee_stack.sh

# Vérifier
source /root/zigbee_credentials.txt
echo $MQTT_PASS_AGENT
# Attendu : même password les 2 fois

# Vérifier service
systemctl status mosquitto
# Attendu : active (running), pas de restart loops
```

---

## Conformité DSI

### ✅ Checklist Sécurité

- [x] **Moindre privilège** : Chaque user a le minimum de droits nécessaires
- [x] **Séparation des responsabilités** : root/mosquitto/avmonitoring ont des rôles distincts
- [x] **Fichiers sensibles protégés** : Permissions 0600 ou 0640 selon besoin
- [x] **Authentification obligatoire** : `allow_anonymous false`
- [x] **TLS mandatory** : Port 8883 uniquement, pas de 1883 en clair
- [x] **ACL restrictives** : Pas d'accès wildcard sauf admin
- [x] **Validation config** : Avant tout restart
- [x] **Logs explicites** : En cas d'erreur, affichage détails
- [x] **Idempotence** : Script relançable sans casser l'existant
- [x] **Backup automatique** : Avant modification fichiers existants
- [x] **Exit codes propres** : Non-zero en cas d'erreur

### 📋 Audit Trail

Tous les changements sont tracés :
- Backup automatique dans `/etc/mosquitto/conf.d/*.bak`
- Credentials sauvegardés dans `/root/zigbee_credentials.txt`
- Logs systemd : `journalctl -u mosquitto`
- Validation config avant restart (logs stdout)

---

## Troubleshooting

### Problème : "Permission denied" sur password file

```bash
# Symptôme
journalctl -u mosquitto | grep -i permission

# Cause
# Permissions incorrectes sur /etc/mosquitto/passwd

# Solution
sudo chown root:mosquitto /etc/mosquitto/passwd
sudo chmod 640 /etc/mosquitto/passwd
sudo systemctl restart mosquitto
```

### Problème : User ne peut pas se connecter

```bash
# Vérifier user existe
sudo cat /etc/mosquitto/passwd | grep avmonitoring

# Vérifier ACL
sudo cat /etc/mosquitto/acl.conf | grep -A 5 "user avmonitoring"

# Tester connexion
source /root/zigbee_credentials.txt
mosquitto_sub -h localhost -p 8883 \
  --cafile /etc/mosquitto/ca_certificates/ca.crt \
  -u avmonitoring -P "$MQTT_PASS_AGENT" \
  -t 'zigbee2mqtt/bridge/state' -C 1 -W 5 -d
# -d (debug) affiche les détails de connexion
```

### Problème : ACL refuse connexion légitime

```bash
# Vérifier permissions ACL file
ls -la /etc/mosquitto/acl.conf
# Doit être : -rw------- 1 mosquitto mosquitto

# Si incorrect :
sudo chown mosquitto:mosquitto /etc/mosquitto/acl.conf
sudo chmod 600 /etc/mosquitto/acl.conf
sudo systemctl restart mosquitto
```

---

## Maintenance

### Rotation des Passwords

```bash
# 1. Générer nouveaux passwords
MQTT_PASS_AGENT=$(openssl rand -base64 16)

# 2. Mettre à jour Mosquitto
sudo mosquitto_passwd -b /etc/mosquitto/passwd avmonitoring "$MQTT_PASS_AGENT"

# 3. Mettre à jour credentials file
sudo sed -i "s/^MQTT_PASS_AGENT=.*/MQTT_PASS_AGENT=$MQTT_PASS_AGENT/" /root/zigbee_credentials.txt

# 4. Mettre à jour agent
sudo sed -i "s/^AVMVP_MQTT_PASS=.*/AVMVP_MQTT_PASS=$MQTT_PASS_AGENT/" /etc/default/avmonitoring-agent

# 5. Redémarrer services
sudo systemctl restart mosquitto
sudo systemctl restart avmonitoring-agent
```

### Audit des Permissions

```bash
# Script de vérification
cat > /tmp/audit_mosquitto_perms.sh <<'EOF'
#!/bin/bash
echo "=== Audit Permissions Mosquitto ==="
echo ""

check_file() {
    FILE=$1
    EXPECTED_OWNER=$2
    EXPECTED_GROUP=$3
    EXPECTED_PERMS=$4

    if [ ! -f "$FILE" ]; then
        echo "✗ $FILE absent"
        return 1
    fi

    ACTUAL_PERMS=$(stat -c %a "$FILE" 2>/dev/null || stat -f %A "$FILE" 2>/dev/null)
    ACTUAL_OWNER=$(stat -c %U "$FILE" 2>/dev/null || stat -f %Su "$FILE" 2>/dev/null)
    ACTUAL_GROUP=$(stat -c %G "$FILE" 2>/dev/null || stat -f %Sg "$FILE" 2>/dev/null)

    if [ "$ACTUAL_OWNER" = "$EXPECTED_OWNER" ] && \
       [ "$ACTUAL_GROUP" = "$EXPECTED_GROUP" ] && \
       [ "$ACTUAL_PERMS" = "$EXPECTED_PERMS" ]; then
        echo "✓ $FILE : $ACTUAL_OWNER:$ACTUAL_GROUP $ACTUAL_PERMS"
    else
        echo "✗ $FILE : $ACTUAL_OWNER:$ACTUAL_GROUP $ACTUAL_PERMS (attendu: $EXPECTED_OWNER:$EXPECTED_GROUP $EXPECTED_PERMS)"
    fi
}

check_file "/etc/mosquitto/passwd" "root" "mosquitto" "640"
check_file "/etc/mosquitto/acl.conf" "mosquitto" "mosquitto" "600"
check_file "/root/zigbee_credentials.txt" "root" "root" "600"
check_file "/etc/mosquitto/ca_certificates/ca.crt" "mosquitto" "mosquitto" "644"
check_file "/etc/mosquitto/ca_certificates/server.key" "mosquitto" "mosquitto" "600"

echo ""
echo "=== Fin Audit ==="
EOF

chmod +x /tmp/audit_mosquitto_perms.sh
sudo /tmp/audit_mosquitto_perms.sh
```

---

## Références

- **Mosquitto Documentation** : https://mosquitto.org/man/mosquitto-conf-5.html
- **ACL Best Practices** : https://mosquitto.org/man/mosquitto-acl-5.html
- **OWASP IoT Security** : https://owasp.org/www-project-internet-of-things/
- **Principe du Moindre Privilège** : https://en.wikipedia.org/wiki/Principle_of_least_privilege

---

## Résumé

Les améliorations de sécurité appliquées garantissent :
- ✅ Conformité exigences DSI
- ✅ Protection fichiers sensibles (ACL, passwords, clés)
- ✅ Idempotence totale du script d'installation
- ✅ Validation systématique avant restart
- ✅ Principe du moindre privilège respecté
- ✅ Traçabilité complète (backups, logs, credentials)

L'installation Mosquitto est maintenant **production-ready** et **audit-friendly**.
