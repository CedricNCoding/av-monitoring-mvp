# Patch Sécurité Mosquitto - Résumé des Modifications

## 🎯 Objectif

Sécuriser l'installation Mosquitto selon les exigences DSI :
- Permissions strictes sur fichiers sensibles
- Idempotence totale du script
- Validation avant restart
- Principe du moindre privilège

---

## 📋 Fichiers Modifiés

### 1. `agent/scripts/install_zigbee_stack.sh`

**Modifications dans la fonction `configure_mosquitto()` :**

#### Changement 1 : Sécurisation ACL (lignes ~226-246)

**AVANT :**
```bash
cat > /etc/mosquitto/acl.conf <<'EOF'
# ACL content...
EOF

chmod 644 /etc/mosquitto/acl.conf
```

**APRÈS :**
```bash
# Backup si existe
if [ -f /etc/mosquitto/acl.conf ]; then
    cp /etc/mosquitto/acl.conf /etc/mosquitto/acl.conf.bak
fi

cat > /etc/mosquitto/acl.conf <<'EOF'
# ACL content with DSI comments...
EOF

# Permissions ACL : 0600 mosquitto:mosquitto (DSI-friendly)
chown mosquitto:mosquitto /etc/mosquitto/acl.conf
chmod 600 /etc/mosquitto/acl.conf
```

**Raison :** Fichier ACL sensible, doit être lisible uniquement par Mosquitto (0600 vs 0644).

---

#### Changement 2 : Sécurisation Password File (lignes ~270-300)

**AVANT :**
```bash
if [ ! -f /etc/mosquitto/passwd ]; then
    touch /etc/mosquitto/passwd
    chmod 600 /etc/mosquitto/passwd
fi

MQTT_PASS_ADMIN=$(openssl rand -base64 16)
# ...

mosquitto_passwd -c -b /etc/mosquitto/passwd admin "$MQTT_PASS_ADMIN"
# ... (écrase fichier à chaque fois)
```

**APRÈS :**
```bash
# Créer password_file si absent
if [ ! -f /etc/mosquitto/passwd ]; then
    touch /etc/mosquitto/passwd
fi

# Permissions : root:mosquitto 0640 (DSI-friendly)
chown root:mosquitto /etc/mosquitto/passwd
chmod 640 /etc/mosquitto/passwd

# Réutiliser credentials existants (idempotence)
if [ -f /root/zigbee_credentials.txt ]; then
    source /root/zigbee_credentials.txt
else
    MQTT_PASS_ADMIN=$(openssl rand -base64 16)
    # ...
fi

# Créer users de manière idempotente
if grep -q "^admin:" /etc/mosquitto/passwd; then
    # Mise à jour sans -c
    mosquitto_passwd -b /etc/mosquitto/passwd admin "$MQTT_PASS_ADMIN"
else
    # Première création avec -c
    mosquitto_passwd -c -b /etc/mosquitto/passwd admin "$MQTT_PASS_ADMIN"
fi
```

**Raisons :**
- Permissions `0640` au lieu de `0600` (mosquitto doit lire)
- Owner `root:mosquitto` (root modifie, mosquitto lit)
- Réutilisation credentials (idempotence)
- Pas de `-c` sur users existants (ne pas écraser)

---

#### Changement 3 : Validation Avant Restart (lignes ~290-310)

**AVANT :**
```bash
# Validation une seule fois
mosquitto -c /etc/mosquitto/mosquitto.conf -v 2>&1 | head -n 20

# Restart sans vérifier si succès
systemctl restart mosquitto
```

**APRÈS :**
```bash
# Validation 1 : Après config
if ! mosquitto -c /etc/mosquitto/mosquitto.conf -v >/dev/null 2>&1; then
    echo "Erreur de configuration"
    exit 1
fi

# ... ajout users ...

# Validation 2 : Après ajout users
if ! mosquitto -c /etc/mosquitto/mosquitto.conf -v >/dev/null 2>&1; then
    echo "Erreur après ajout users"
    exit 1
fi

# Restart SEULEMENT si validation OK
systemctl restart mosquitto

# Vérifier que le service a démarré
sleep 2
if ! systemctl is-active mosquitto &> /dev/null; then
    echo "Erreur: Mosquitto n'a pas démarré"
    journalctl -u mosquitto -n 20
    exit 1
fi
```

**Raisons :**
- Validation à 2 moments critiques
- Exit 1 si validation échoue (bloque installation)
- Vérification post-restart (service actif)
- Logs explicites en cas d'erreur

---

### 2. Nouveaux Fichiers Créés

#### `MOSQUITTO_SECURITY.md`
- Documentation complète des changements
- Justifications DSI
- Tests de validation
- Guide maintenance

#### `MOSQUITTO_SECURITY_PATCH.md`
- Résumé des modifications (ce fichier)
- Guide application du patch

---

## 🚀 Application du Patch

### Étape 1 : Pull des modifications

```bash
cd /opt/avmonitoring-agent
git pull origin main
```

### Étape 2 : Appliquer sur installation existante

```bash
# Si Mosquitto déjà installé et fonctionne
sudo /opt/avmonitoring-agent/scripts/install_zigbee_stack.sh
```

Le script :
- Détecte installation existante
- Réutilise credentials existants
- Corrige permissions automatiquement
- Valide avant restart

### Étape 3 : Vérifier permissions

```bash
# Password file
ls -la /etc/mosquitto/passwd
# Attendu : -rw-r----- 1 root mosquitto

# ACL file
ls -la /etc/mosquitto/acl.conf
# Attendu : -rw------- 1 mosquitto mosquitto
```

### Étape 4 : Tester service

```bash
# Vérifier Mosquitto actif
sudo systemctl status mosquitto

# Tester connexion
source /root/zigbee_credentials.txt
mosquitto_sub -h localhost -p 8883 \
  --cafile /etc/mosquitto/ca_certificates/ca.crt \
  -u avmonitoring -P "$MQTT_PASS_AGENT" \
  -t 'zigbee2mqtt/bridge/state' -C 1 -W 5
```

---

## ✅ Tests de Validation

### Test 1 : Permissions Correctes

```bash
#!/bin/bash
echo "=== Test Permissions ==="

# Password file
PERMS=$(stat -c %a /etc/mosquitto/passwd 2>/dev/null)
OWNER=$(stat -c %U:%G /etc/mosquitto/passwd 2>/dev/null)
echo "Password file : $OWNER $PERMS (attendu: root:mosquitto 640)"

# ACL file
PERMS=$(stat -c %a /etc/mosquitto/acl.conf 2>/dev/null)
OWNER=$(stat -c %U:%G /etc/mosquitto/acl.conf 2>/dev/null)
echo "ACL file : $OWNER $PERMS (attendu: mosquitto:mosquitto 600)"

# Credentials
PERMS=$(stat -c %a /root/zigbee_credentials.txt 2>/dev/null)
OWNER=$(stat -c %U:%G /root/zigbee_credentials.txt 2>/dev/null)
echo "Credentials : $OWNER $PERMS (attendu: root:root 600)"
```

### Test 2 : Idempotence

```bash
# Sauvegarder credentials actuels
source /root/zigbee_credentials.txt
OLD_PASS=$MQTT_PASS_AGENT

# Relancer script
sudo /opt/avmonitoring-agent/scripts/install_zigbee_stack.sh

# Vérifier passwords identiques
source /root/zigbee_credentials.txt
if [ "$OLD_PASS" = "$MQTT_PASS_AGENT" ]; then
    echo "✓ Idempotence OK : passwords conservés"
else
    echo "✗ Erreur : passwords changés"
fi
```

### Test 3 : Validation Config

```bash
# Doit passer sans erreur
sudo mosquitto -c /etc/mosquitto/mosquitto.conf -v
```

### Test 4 : Service Actif

```bash
# Doit afficher "active (running)"
sudo systemctl status mosquitto --no-pager
```

### Test 5 : ACL Fonctionnelles

```bash
source /root/zigbee_credentials.txt

# Test 1 : Lecture autorisée
mosquitto_sub -h localhost -p 8883 \
  --cafile /etc/mosquitto/ca_certificates/ca.crt \
  -u avmonitoring -P "$MQTT_PASS_AGENT" \
  -t 'zigbee2mqtt/bridge/state' -C 1 -W 2
# Attendu : Reçoit message ou timeout (OK)

# Test 2 : Écriture hors scope (doit échouer)
mosquitto_pub -h localhost -p 8883 \
  --cafile /etc/mosquitto/ca_certificates/ca.crt \
  -u avmonitoring -P "$MQTT_PASS_AGENT" \
  -t 'admin/test' -m 'test' 2>&1 | grep -i "not authorized"
# Attendu : "not authorized" (OK)
```

---

## 📊 Résumé des Changements

| Aspect | Avant | Après | Impact |
|--------|-------|-------|--------|
| **ACL permissions** | 0644 (public) | 0600 (mosquitto seul) | ✅ Sécurisé |
| **Password permissions** | 0600 root:root | 0640 root:mosquitto | ✅ Mosquitto peut lire |
| **Idempotence users** | ❌ Écrase à chaque fois | ✅ Réutilise existants | ✅ Pas de perte données |
| **Validation config** | 1 fois (partielle) | 2 fois (complète) | ✅ Détection erreurs |
| **Vérif post-restart** | ❌ Non | ✅ Oui (systemctl is-active) | ✅ Détection pannes |
| **Commentaires DSI** | ❌ Absents | ✅ Présents | ✅ Audit-friendly |

---

## 🔧 Rollback (si nécessaire)

Si problème après application du patch :

```bash
# 1. Restaurer backup ACL
sudo cp /etc/mosquitto/acl.conf.bak /etc/mosquitto/acl.conf

# 2. Restaurer backup Zigbee config
sudo cp /etc/mosquitto/conf.d/zigbee.conf.bak /etc/mosquitto/conf.d/zigbee.conf

# 3. Redémarrer Mosquitto
sudo systemctl restart mosquitto

# 4. Vérifier logs
sudo journalctl -u mosquitto -n 50
```

---

## 📖 Documentation Complète

Voir [`MOSQUITTO_SECURITY.md`](MOSQUITTO_SECURITY.md) pour :
- Justifications détaillées DSI
- Tests de validation complets
- Guide maintenance
- Troubleshooting

---

## ✨ Conclusion

Ce patch améliore la sécurité Mosquitto **sans casser l'existant** :
- ✅ Permissions strictes (DSI-friendly)
- ✅ Idempotence totale (rejouable)
- ✅ Validation systématique (pas de rupture service)
- ✅ Backward compatible (installations existantes OK)

**Le script est production-ready et audit-friendly !** 🚀
