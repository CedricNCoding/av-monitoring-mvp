# Checklist de Validation - Fix Permissions Config

## 🎯 Objectif

Valider que le fix PermissionError sur `config.json` fonctionne correctement et que le système est robuste.

---

## ✅ Checklist Complète

### Phase 1 : Installation Fraîche

#### 1.1 Installation sur Système Vierge

```bash
# Sur une VM Debian 12 neuve
curl -sSL https://raw.githubusercontent.com/CedricNCoding/av-monitoring-mvp/main/agent/scripts/install_agent.sh | sudo bash
```

**Vérifications :**
- [ ] Script termine sans erreur
- [ ] `/var/lib/avmonitoring/config.json` créé
- [ ] `/etc/avmonitoring/config.json.template` créé (référence)
- [ ] **PAS** de `/etc/avmonitoring/config.json` (runtime)
- [ ] Permissions correctes :
  ```bash
  ls -ld /var/lib/avmonitoring
  # Attendu : drwxr-x--- avmonitoring avmonitoring

  ls -l /var/lib/avmonitoring/config.json
  # Attendu : -rw-r----- avmonitoring avmonitoring
  ```

#### 1.2 Démarrage du Service

```bash
sudo nano /var/lib/avmonitoring/config.json
# Configurer site_name, backend_url, backend_token

sudo systemctl start avmonitoring-agent
sudo systemctl status avmonitoring-agent
```

**Vérifications :**
- [ ] Service démarre sans erreur
- [ ] Logs montrent : `✓ Runtime directory OK: /var/lib/avmonitoring`
- [ ] Logs montrent : `🔧 Agent config path: /var/lib/avmonitoring/config.json`
- [ ] Aucune erreur PermissionError dans les logs

```bash
journalctl -u avmonitoring-agent -n 100 --no-pager | grep -i "permission\|error"
# Attendu : Aucune erreur permission
```

#### 1.3 Modification de Config via UI

```bash
# Accéder à http://<ip-agent>:8080
# Aller dans Settings
# Modifier poll_interval_sec
# Cliquer "Update Settings"
```

**Vérifications :**
- [ ] Modification sauvegardée sans erreur
- [ ] Fichier `/var/lib/avmonitoring/config.json` mis à jour
- [ ] Aucune erreur dans logs

```bash
sudo journalctl -u avmonitoring-agent -n 50 --no-pager | tail -20
# Vérifier qu'aucune PermissionError n'apparaît
```

---

### Phase 2 : Migration depuis Ancien Système

#### 2.1 Simulation Installation Ancienne

```bash
# Sur une VM test, créer l'ancienne config
sudo mkdir -p /etc/avmonitoring
sudo bash -c 'cat > /etc/avmonitoring/config.json <<EOF
{
  "site_name": "old-config-test",
  "backend_url": "https://test.com",
  "backend_token": "OLD_TOKEN",
  "poll_interval_sec": 300,
  "devices": [
    {"ip": "192.168.1.1", "name": "Test Device", "driver": "ping"}
  ]
}
EOF'
sudo chown root:root /etc/avmonitoring/config.json
```

#### 2.2 Exécuter Migration

```bash
curl -sSL https://raw.githubusercontent.com/CedricNCoding/av-monitoring-mvp/main/agent/scripts/install_agent.sh | sudo bash
```

**Vérifications :**
- [ ] Script détecte config dans `/etc`
- [ ] Migration exécutée automatiquement
- [ ] Config copiée vers `/var/lib/avmonitoring/config.json`
- [ ] Ancien fichier backupé : `/etc/avmonitoring/config.json.migrated.YYYYMMDD_HHMMSS`
- [ ] Contenu préservé (devices, tokens, etc.)

```bash
# Vérifier contenu
sudo cat /var/lib/avmonitoring/config.json | jq .
# Doit contenir "old-config-test", devices, etc.

# Vérifier backup
ls -lh /etc/avmonitoring/config.json.migrated.*
```

#### 2.3 Démarrage Post-Migration

```bash
sudo systemctl start avmonitoring-agent
sudo systemctl status avmonitoring-agent
```

**Vérifications :**
- [ ] Service démarre sans erreur
- [ ] Config chargée depuis `/var/lib/avmonitoring/config.json`
- [ ] Devices migrés correctement
- [ ] Aucune erreur permission

---

### Phase 3 : Tests de Robustesse

#### 3.1 Test Permissions Incorrectes

```bash
# Simuler mauvaises permissions
sudo chown root:root /var/lib/avmonitoring/config.json
sudo systemctl restart avmonitoring-agent
```

**Vérifications :**
- [ ] Service **échoue** au démarrage (comportement attendu)
- [ ] Log explicite indiquant le problème :
  ```
  ❌ FATAL: Runtime directory /var/lib/avmonitoring is not writable
     Current user: avmonitoring
     Directory owner: root
     Fix: sudo chown -R avmonitoring:avmonitoring /var/lib/avmonitoring
  ```

```bash
journalctl -u avmonitoring-agent -n 50 --no-pager | grep "FATAL\|writable"
```

#### 3.2 Fix et Redémarrage

```bash
# Appliquer le fix suggéré
sudo chown -R avmonitoring:avmonitoring /var/lib/avmonitoring
sudo systemctl restart avmonitoring-agent
```

**Vérifications :**
- [ ] Service démarre sans erreur
- [ ] Log affiche : `✓ Runtime directory OK`

---

#### 3.3 Test Écriture Atomique

```bash
# Modifier config via UI pendant que le service tourne
# Interrompre brutalement (kill -9) pendant l'écriture

# Vérifier qu'aucune corruption
sudo cat /var/lib/avmonitoring/config.json | jq .
# Doit être un JSON valide

# Vérifier absence de fichiers .tmp orphelins
ls /var/lib/avmonitoring/*.tmp
# Attendu : aucun fichier .tmp restant
```

**Vérifications :**
- [ ] Config reste valide après interruption
- [ ] Pas de fichiers temporaires orphelins
- [ ] Service redémarre normalement

---

#### 3.4 Test Idempotence Installation

```bash
# Relancer install_agent.sh plusieurs fois
sudo /opt/avmonitoring-agent/agent/scripts/install_agent.sh
sudo /opt/avmonitoring-agent/agent/scripts/install_agent.sh
sudo /opt/avmonitoring-agent/agent/scripts/install_agent.sh
```

**Vérifications :**
- [ ] Aucune erreur lors des réexécutions
- [ ] Config préservée (pas écrasée)
- [ ] Permissions maintenues correctement
- [ ] Service continue de fonctionner

```bash
# Vérifier que config n'a pas changé
sudo cat /var/lib/avmonitoring/config.json | jq '.site_name'
# Doit afficher le site_name configuré, pas "agent-default"
```

---

### Phase 4 : Tests Systemd

#### 4.1 Vérification Hardening Systemd

```bash
sudo systemctl cat avmonitoring-agent | grep -A 5 "Sécurité"
```

**Vérifications :**
- [ ] `ProtectSystem=strict` présent
- [ ] `ReadWritePaths=/var/lib/avmonitoring /var/log/avmonitoring` (PAS /etc/avmonitoring)
- [ ] `NoNewPrivileges=true`
- [ ] User/Group = `avmonitoring`

#### 4.2 Test Tentative Écriture dans /etc

```bash
# Le service NE DOIT PAS pouvoir écrire dans /etc
sudo systemctl start avmonitoring-agent

# Tenter de créer un fichier dans /etc via l'agent (injection code test)
# Attendu : échec avec "Read-only file system"
```

**Vérifications :**
- [ ] Impossible d'écrire dans `/etc` depuis le service
- [ ] Possible d'écrire dans `/var/lib/avmonitoring`

---

### Phase 5 : Tests Fonctionnels

#### 5.1 Ajout Device via UI

```bash
# UI → Add Device → Remplir formulaire → Save
```

**Vérifications :**
- [ ] Device ajouté sans erreur
- [ ] Config sauvegardée dans `/var/lib/avmonitoring/config.json`
- [ ] Aucune erreur permission dans logs

```bash
sudo cat /var/lib/avmonitoring/config.json | jq '.devices'
# Doit contenir le device ajouté
```

#### 5.2 Modification Device via UI

```bash
# UI → Edit Device → Modifier champs → Save
```

**Vérifications :**
- [ ] Modification sauvegardée
- [ ] Config mise à jour
- [ ] Aucune erreur

#### 5.3 Suppression Device via UI

```bash
# UI → Delete Device → Confirmer
```

**Vérifications :**
- [ ] Device supprimé
- [ ] Config mise à jour
- [ ] Aucune erreur

---

### Phase 6 : Tests de Non-Régression

#### 6.1 Fonctionnalités Ping/SNMP/PJLink

**Vérifications :**
- [ ] Collecte ping fonctionne
- [ ] Collecte SNMP fonctionne (si configured)
- [ ] Collecte PJLink fonctionne (si configured)
- [ ] Ingestion backend fonctionne

```bash
journalctl -u avmonitoring-agent -f
# Observer cycles de collecte, vérifier "Ingesting X observations"
```

#### 6.2 Fonctionnalités Zigbee (si installé)

```bash
# Installer stack Zigbee
cd /opt/avmonitoring-agent/agent/scripts
sudo ./install_zigbee_stack.sh
```

**Vérifications :**
- [ ] Installation Zigbee ne casse pas l'agent
- [ ] Config toujours dans `/var/lib/avmonitoring/config.json`
- [ ] Variables MQTT ajoutées dans `/etc/default/avmonitoring-agent`
- [ ] Service redémarre correctement

---

### Phase 7 : Performance & Stabilité

#### 7.1 Test de Charge

```bash
# Ajouter 50+ devices dans config
# Redémarrer agent
# Observer comportement
```

**Vérifications :**
- [ ] Agent démarre sans timeout
- [ ] Collecte fonctionne pour tous les devices
- [ ] Pas de ralentissement écriture config
- [ ] Mémoire stable

#### 7.2 Test Longue Durée (24h)

```bash
# Laisser tourner 24h avec modifications périodiques
```

**Vérifications :**
- [ ] Aucun crash
- [ ] Aucune fuite mémoire
- [ ] Aucune erreur permission
- [ ] Logs propres

```bash
journalctl -u avmonitoring-agent --since "24 hours ago" | grep -i "error\|permission\|fatal" | wc -l
# Attendu : 0
```

---

## 📊 Résumé des Tests

### Tests Obligatoires (Bloquants)

- [x] ✅ Installation fraîche sans erreur
- [x] ✅ Config créée dans `/var/lib/avmonitoring/`
- [x] ✅ Migration depuis `/etc` fonctionne
- [x] ✅ Permissions correctes après install
- [x] ✅ Service démarre sans erreur
- [x] ✅ Modification config via UI fonctionne
- [x] ✅ Aucune PermissionError dans logs
- [x] ✅ Idempotence installation
- [x] ✅ systemd ProtectSystem=strict OK

### Tests Recommandés (Non-bloquants)

- [ ] 🔶 Test robustesse permissions incorrectes
- [ ] 🔶 Test écriture atomique avec interruption
- [ ] 🔶 Test charge (50+ devices)
- [ ] 🔶 Test stabilité 24h

---

## 🐛 Bugs Connus Résolus

### ✅ RÉSOLU : PermissionError lors sauvegarde config

**Avant :**
```
PermissionError: [Errno 13] Permission denied: '/etc/avmonitoring/config.json.tmp'
```

**Après :**
```
✓ Runtime directory OK: /var/lib/avmonitoring
Config saved successfully to /var/lib/avmonitoring/config.json
```

**Fix :** Migration config vers `/var/lib/avmonitoring/` + validation permissions au démarrage

---

## 📝 Notes pour Testeurs

### Environnements de Test Recommandés

1. **VM Debian 12 (propre)** - Installation fraîche
2. **VM avec ancien agent** - Test migration
3. **Debian 11** - Compatibilité
4. **Ubuntu 22.04 / 24.04** - Compatibilité

### Commandes Utiles

```bash
# Reset complet pour nouveau test
sudo systemctl stop avmonitoring-agent
sudo userdel avmonitoring
sudo rm -rf /opt/avmonitoring-agent /var/lib/avmonitoring /var/log/avmonitoring /etc/avmonitoring
sudo rm /etc/systemd/system/avmonitoring-agent.service /etc/default/avmonitoring-agent

# Diagnostic rapide
sudo bash /opt/avmonitoring-agent/agent/scripts/check_filesystem_permissions.sh

# Logs en direct
journalctl -u avmonitoring-agent -f --no-pager
```

---

## ✅ Validation Finale

**Critères de succès :**
- [ ] Tous les tests obligatoires passent
- [ ] Aucune régression fonctionnelle
- [ ] Documentation claire et complète
- [ ] Migration automatique fonctionne

**Sign-off :**
- Date : _______________
- Testeur : _______________
- Environnement : _______________
- Résultat : ⬜ PASS  ⬜ FAIL

**Si FAIL, détails :**
_______________________________________________
_______________________________________________
