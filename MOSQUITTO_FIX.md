# Fix : Erreur "Duplicate persistence_location" Mosquitto

## Problème Identifié

**Erreur rencontrée :**
```
Error: Duplicate persistence_location value in configuration.
Error found at /etc/mosquitto/conf.d/zigbee.conf:18.
Error found at /etc/mosquitto/mosquitto.conf:13.
```

**Cause :**
Le script `install_zigbee_stack.sh` ajoutait les directives `persistence` et `persistence_location` dans `/etc/mosquitto/conf.d/zigbee.conf`, alors qu'elles sont déjà présentes par défaut dans `/etc/mosquitto/mosquitto.conf`.

**Impact :** Mosquitto refuse de démarrer, installation Zigbee échoue.

---

## Correctifs Appliqués

### 1. Modifications dans `install_zigbee_stack.sh`

#### Changement 1 : Ajout fonction de réparation
```bash
repair_mosquitto_config() {
    # Répare les installations cassées où persistence_location est dupliqué.
    # Retire persistence et persistence_location de conf.d/zigbee.conf si présents.
    if [ -f /etc/mosquitto/conf.d/zigbee.conf ]; then
        if grep -q "persistence" /etc/mosquitto/conf.d/zigbee.conf; then
            echo "⚠️  Réparation : retrait directives persistence de conf.d/zigbee.conf..."
            sed -i '/^persistence /d' /etc/mosquitto/conf.d/zigbee.conf
            sed -i '/^persistence_location /d' /etc/mosquitto/conf.d/zigbee.conf
            sed -i '/^# Persistence$/d' /etc/mosquitto/conf.d/zigbee.conf
        fi
    fi
}
```

#### Changement 2 : Suppression des directives persistence de zigbee.conf

**AVANT (lignes 199-208) :**
```bash
# ACL (Access Control List)
acl_file /etc/mosquitto/acl.conf

# Persistence
persistence true
persistence_location /var/lib/mosquitto/

# Logs
log_dest syslog
```

**APRÈS :**
```bash
# ACL (Access Control List)
acl_file /etc/mosquitto/acl.conf

# Logs
log_dest syslog
```

Les directives `persistence` et `persistence_location` ont été **retirées** de `zigbee.conf`.

#### Changement 3 : Validation de la configuration

Ajout dans `configure_mosquitto()` :
```bash
# S'assurer que mosquitto.conf a les directives persistence (normalement présentes par défaut)
if ! grep -q "^persistence true" /etc/mosquitto/mosquitto.conf 2>/dev/null; then
    echo "Ajout directives persistence dans mosquitto.conf..."
    cat >> /etc/mosquitto/mosquitto.conf <<'EOF'

# Persistence (ajouté par install_zigbee_stack.sh)
persistence true
persistence_location /var/lib/mosquitto/
EOF
fi

# Validation de la configuration Mosquitto
echo "Validation de la configuration Mosquitto..."
if ! mosquitto -c /etc/mosquitto/mosquitto.conf -v 2>&1 | head -n 20; then
    echo -e "${RED}✗ Erreur: Configuration Mosquitto invalide${NC}"
    exit 1
fi
```

#### Changement 4 : Validation finale

Nouvelle fonction `final_validation()` appelée à la fin de `main()` :
- Valide la config Mosquitto
- Vérifie que le service est actif
- Vérifie que le port 8883 est ouvert
- Vérifie le service Zigbee2MQTT

### 2. Nouveau script : `repair_mosquitto_config.sh`

Script standalone pour réparer les installations déjà cassées :
- Détecte les directives en double
- Backup automatique avant modification
- Supprime les directives de `zigbee.conf`
- S'assure que `mosquitto.conf` les a
- Valide et redémarre Mosquitto

---

## Procédure de Réparation

### Pour installations déjà cassées

```bash
cd /opt/avmonitoring-agent/scripts

# Rendre exécutable
chmod +x repair_mosquitto_config.sh

# Exécuter
sudo ./repair_mosquitto_config.sh
```

Le script :
1. Crée un backup automatique
2. Retire les directives en double
3. Valide la config
4. Redémarre Mosquitto

### Pour nouvelles installations

Le script `install_zigbee_stack.sh` corrigé :
1. Détecte automatiquement les configs cassées
2. Les répare avant de continuer
3. Valide la config avant de terminer
4. Ne créera plus de duplication

---

## Commandes de Test (Post-Fix)

### 1. Valider configuration Mosquitto
```bash
sudo mosquitto -c /etc/mosquitto/mosquitto.conf -v
```

**Résultat attendu :**
```
1706184123: mosquitto version 2.x starting
1706184123: Config loaded from /etc/mosquitto/mosquitto.conf
1706184123: Opening ipv4 listen socket on port 1883.
1706184123: Opening ipv6 listen socket on port 1883.
```

**Aucune ligne "Error: Duplicate persistence_location"**

### 2. Vérifier fichiers de configuration

```bash
# Vérifier zigbee.conf (NE DOIT PAS contenir persistence)
sudo grep -n "persistence" /etc/mosquitto/conf.d/zigbee.conf
# Résultat attendu : rien (ou grep: no match)

# Vérifier mosquitto.conf (DOIT contenir persistence)
sudo grep -n "persistence" /etc/mosquitto/mosquitto.conf
# Résultat attendu :
#   13:persistence true
#   14:persistence_location /var/lib/mosquitto/
```

### 3. Redémarrer services

```bash
sudo systemctl daemon-reload
sudo systemctl restart mosquitto
```

### 4. Vérifier status

```bash
sudo systemctl status mosquitto --no-pager -l
```

**Résultat attendu :**
```
● mosquitto.service - Mosquitto MQTT Broker
     Loaded: loaded
     Active: active (running)
```

### 5. Vérifier logs

```bash
sudo journalctl -u mosquitto -n 100 --no-pager -o cat
```

**Rechercher :**
- ✅ "mosquitto version X.X starting"
- ✅ "Config loaded from /etc/mosquitto/mosquitto.conf"
- ✅ "Opening ipv4 listen socket on port 8883"
- ❌ **PAS** de "Error: Duplicate"

### 6. Tester connexion MQTT

```bash
# Installer client si absent
sudo apt-get install -y mosquitto-clients

# Tester (remplacer password par celui de /root/zigbee_credentials.txt)
source /root/zigbee_credentials.txt 2>/dev/null || true

mosquitto_sub -h localhost -p 8883 \
  --cafile /etc/mosquitto/ca_certificates/ca.crt \
  -u avmonitoring -P "${MQTT_PASS_AGENT:-test}" \
  -t 'zigbee2mqtt/bridge/state' -C 1 -W 5
```

**Résultat attendu :**
```json
{"state":"online"}
```

ou timeout si Zigbee2MQTT pas encore démarré (normal).

### 7. Validation complète

```bash
cd /opt/avmonitoring-agent/scripts
sudo ./check_zigbee_stack.sh
```

**Résultat attendu :**
```
✓ Tests réussis:   40+
⚠ Avertissements:  0-2
✗ Tests échoués:   0
```

---

## Vérification de la Configuration

### Structure correcte des fichiers

**`/etc/mosquitto/mosquitto.conf` (extrait) :**
```conf
# Directives globales
pid_file /run/mosquitto/mosquitto.pid

user mosquitto
max_queued_messages 1000

# Persistence (DOIT être ici)
persistence true
persistence_location /var/lib/mosquitto/

# Charger configs additionnelles
include_dir /etc/mosquitto/conf.d
```

**`/etc/mosquitto/conf.d/zigbee.conf` :**
```conf
# Zigbee2MQTT TLS listener (port 8883 uniquement)
# Managed by install_zigbee_stack.sh - Do not edit manually

listener 8883
certfile /etc/mosquitto/ca_certificates/server.crt
cafile /etc/mosquitto/ca_certificates/ca.crt
keyfile /etc/mosquitto/ca_certificates/server.key
require_certificate false
tls_version tlsv1.2

# Authentification obligatoire
allow_anonymous false
password_file /etc/mosquitto/passwd

# ACL (Access Control List)
acl_file /etc/mosquitto/acl.conf

# Logs
log_dest syslog
log_type error
log_type warning
log_type notice
```

**Note :** Aucune directive `persistence` ou `persistence_location` dans `zigbee.conf`.

---

## Rollback (si nécessaire)

Si le fix cause des problèmes :

```bash
# 1. Restaurer backup (créé par repair_mosquitto_config.sh)
BACKUP=$(ls -td /root/mosquitto_repair_backup_* 2>/dev/null | head -n1)
if [ -n "$BACKUP" ]; then
    sudo cp -r "$BACKUP/mosquitto/"* /etc/mosquitto/
    sudo systemctl restart mosquitto
fi

# 2. Ou restaurer backup de install_zigbee_stack.sh
BACKUP=$(ls -td /root/zigbee_backup_* 2>/dev/null | head -n1)
if [ -n "$BACKUP" ]; then
    sudo cp "$BACKUP/avmonitoring-agent" /etc/default/ 2>/dev/null || true
    sudo systemctl restart avmonitoring-agent
fi
```

---

## Bonnes Pratiques Mosquitto

### Séparation des responsabilités

**`mosquitto.conf` (config globale) :**
- `persistence`, `persistence_location`
- `pid_file`, `user`, `max_queued_messages`
- `include_dir` pour charger conf.d

**`conf.d/*.conf` (configs spécifiques) :**
- `listener` (ports, TLS)
- `allow_anonymous`, `password_file`, `acl_file`
- `log_dest`, `log_type`

**Règle d'or :** Chaque directive ne doit apparaître qu'**une seule fois** dans l'ensemble de la configuration (sauf `log_type` qui peut être répété).

---

## Résumé des Fichiers Modifiés

```
agent/scripts/install_zigbee_stack.sh    - Corrigé (suppression persistence de zigbee.conf)
agent/scripts/repair_mosquitto_config.sh - Nouveau (script de réparation)
MOSQUITTO_FIX.md                         - Nouveau (ce document)
```

---

## Validation Finale

Après application du fix, exécuter dans l'ordre :

```bash
# 1. Valider config
sudo mosquitto -c /etc/mosquitto/mosquitto.conf -v

# 2. Redémarrer
sudo systemctl daemon-reload
sudo systemctl restart mosquitto

# 3. Vérifier status
sudo systemctl status mosquitto --no-pager -l

# 4. Vérifier logs
sudo journalctl -u mosquitto -n 100 --no-pager -o cat | grep -i error

# 5. Tester connexion
mosquitto_sub -h localhost -p 8883 \
  --cafile /etc/mosquitto/ca_certificates/ca.crt \
  -u test -P test -t '#' -C 1 -W 2 2>&1

# 6. Validation complète
sudo /opt/avmonitoring-agent/scripts/check_zigbee_stack.sh
```

**Tous les tests doivent passer sans erreur.**

---

## Support

En cas de problème persistant après le fix :

```bash
# Collecter logs de diagnostic
{
  echo "=== Mosquitto Config ==="
  sudo cat /etc/mosquitto/mosquitto.conf
  echo ""
  echo "=== Zigbee Config ==="
  sudo cat /etc/mosquitto/conf.d/zigbee.conf
  echo ""
  echo "=== Mosquitto Validation ==="
  sudo mosquitto -c /etc/mosquitto/mosquitto.conf -v 2>&1
  echo ""
  echo "=== Mosquitto Status ==="
  sudo systemctl status mosquitto --no-pager -l
  echo ""
  echo "=== Mosquitto Logs ==="
  sudo journalctl -u mosquitto -n 50 --no-pager
} > /tmp/mosquitto_diagnostic.log

cat /tmp/mosquitto_diagnostic.log
```

Envoyer `/tmp/mosquitto_diagnostic.log` pour analyse.
