# Architecture Filesystem - AV Monitoring Agent

## 📁 Vue d'Ensemble

Ce document décrit l'architecture filesystem de l'agent AV Monitoring, conforme aux standards FHS (Filesystem Hierarchy Standard) et aux exigences DSI pour les systèmes Debian/systemd.

---

## 🎯 Principes de Design

### 1. Séparation Runtime / Configuration

```
/etc/avmonitoring/          ← Templates immutables (root:root, 644)
/var/lib/avmonitoring/      ← Données modifiables (avmonitoring:avmonitoring, 750)
/var/log/avmonitoring/      ← Logs (avmonitoring:avmonitoring, 750)
/opt/avmonitoring-agent/    ← Code applicatif (avmonitoring:avmonitoring, 755)
```

### 2. Principe du Moindre Privilège

- **Service systemd** : Tourne sous l'utilisateur `avmonitoring` (non-root)
- **ProtectSystem=strict** : `/etc`, `/usr`, `/boot` en lecture seule
- **ReadWritePaths** : Uniquement `/var/lib/avmonitoring` et `/var/log/avmonitoring`

### 3. Idempotence & Migration

- Installation répétable sans perte de données
- Migration automatique `/etc → /var/lib` si config trouvée dans `/etc`
- Backup horodaté avant toute migration

---

## 📂 Structure Détaillée

### `/etc/avmonitoring/` - Configuration Système (Read-Only)

**Propriétaire :** `root:root`
**Permissions :** `755` (dossier), `644` (fichiers)
**Rôle :** Templates, exemples, configs système immuables

```
/etc/avmonitoring/
├── config.json.template        # Template de config (référence)
└── [futurs fichiers système]
```

**⚠️ IMPORTANT :**
Ce dossier ne doit **JAMAIS** contenir de données runtime modifiables.
Tout fichier ici est considéré comme un template ou une configuration système.

---

### `/var/lib/avmonitoring/` - Données Runtime (Read-Write)

**Propriétaire :** `avmonitoring:avmonitoring`
**Permissions :** `750` (dossier), `640` (fichiers)
**Rôle :** Configuration active, données d'application

```
/var/lib/avmonitoring/
├── config.json                 # Config ACTIVE (writable par l'agent)
├── cache/                      # (futur) Cache MQTT, états devices
└── [autres données runtime]
```

**Variable d'environnement :**
```bash
AGENT_CONFIG=/var/lib/avmonitoring/config.json
```

**Accès :**
- L'agent lit et écrit dans ce dossier
- systemd autorise l'écriture via `ReadWritePaths=/var/lib/avmonitoring`
- Aucun autre processus ne devrait y accéder

---

### `/var/log/avmonitoring/` - Logs (Write-Only)

**Propriétaire :** `avmonitoring:avmonitoring`
**Permissions :** `750`
**Rôle :** Logs applicatifs (si log vers fichier au lieu de journald)

```
/var/log/avmonitoring/
├── agent.log                   # (optionnel) Log principal
└── [autres logs]
```

**Note :** L'agent utilise actuellement journald (pas de fichiers ici), mais le dossier est préparé pour usage futur.

---

### `/opt/avmonitoring-agent/` - Code Applicatif

**Propriétaire :** `avmonitoring:avmonitoring`
**Permissions :** `755` (dossiers), `644` (fichiers), `755` (exécutables)
**Rôle :** Code source, venv Python, scripts

```
/opt/avmonitoring-agent/
├── agent/
│   ├── src/                    # Code Python
│   ├── venv/                   # Environnement virtuel Python
│   ├── packaging/              # Configs systemd, environnement
│   └── scripts/                # Scripts d'installation
└── [autres dossiers]
```

---

## 🔐 Permissions en Détail

### Matrice des Permissions

| Chemin | Owner | Group | Permissions | systemd ReadWrite |
|--------|-------|-------|-------------|-------------------|
| `/etc/avmonitoring/` | root | root | 755 | ❌ Non (read-only via ProtectSystem) |
| `/etc/avmonitoring/*.template` | root | root | 644 | ❌ Non |
| `/var/lib/avmonitoring/` | avmonitoring | avmonitoring | 750 | ✅ Oui |
| `/var/lib/avmonitoring/config.json` | avmonitoring | avmonitoring | 640 | ✅ Oui |
| `/var/log/avmonitoring/` | avmonitoring | avmonitoring | 750 | ✅ Oui |
| `/opt/avmonitoring-agent/` | avmonitoring | avmonitoring | 755 | ❌ Non (read-only code) |

### Vérification des Permissions

```bash
# Script de diagnostic
sudo bash <<'EOF'
echo "=== Permissions AV Monitoring Agent ==="
echo ""

check_dir() {
    local path=$1
    local expected_owner=$2
    local expected_perms=$3

    if [ -d "$path" ]; then
        actual_owner=$(stat -c "%U:%G" "$path" 2>/dev/null || stat -f "%Su:%Sg" "$path" 2>/dev/null)
        actual_perms=$(stat -c "%a" "$path" 2>/dev/null || stat -f "%A" "$path" 2>/dev/null | tail -c 4)

        if [ "$actual_owner" = "$expected_owner" ] && [ "$actual_perms" = "$expected_perms" ]; then
            echo "✓ $path ($actual_owner $actual_perms)"
        else
            echo "✗ $path ($actual_owner $actual_perms) - Expected: $expected_owner $expected_perms"
        fi
    else
        echo "⚠ $path (absent)"
    fi
}

check_dir "/etc/avmonitoring" "root:root" "755"
check_dir "/var/lib/avmonitoring" "avmonitoring:avmonitoring" "750"
check_dir "/var/log/avmonitoring" "avmonitoring:avmonitoring" "750"
check_dir "/opt/avmonitoring-agent" "avmonitoring:avmonitoring" "755"

echo ""
echo "=== Fichier Config ==="
if [ -f "/var/lib/avmonitoring/config.json" ]; then
    ls -lh /var/lib/avmonitoring/config.json
else
    echo "⚠ Config absente dans /var/lib/avmonitoring"
fi

if [ -f "/etc/avmonitoring/config.json" ]; then
    echo "⚠ Config trouvée dans /etc (devrait être migrée)"
    ls -lh /etc/avmonitoring/config.json
fi
EOF
```

---

## 🔄 Migration depuis `/etc/avmonitoring/`

### Contexte

Les versions antérieures de l'agent stockaient la config dans `/etc/avmonitoring/config.json`. Cela causait des `PermissionError` avec `ProtectSystem=strict`.

### Processus de Migration

La migration est **automatique** lors de l'installation/upgrade via `install_agent.sh`.

**Étapes :**
1. Détection de `/etc/avmonitoring/config.json`
2. Copie vers `/var/lib/avmonitoring/config.json`
3. Backup de l'ancien fichier : `/etc/avmonitoring/config.json.migrated.YYYYMMDD_HHMMSS`
4. Mise à jour de `AGENT_CONFIG` dans `/etc/default/avmonitoring-agent`

**Migration manuelle (si nécessaire) :**
```bash
cd /opt/avmonitoring-agent/agent/scripts
sudo ./migrate_config_to_var.sh
```

---

## 🚨 Troubleshooting

### Erreur : `PermissionError: Cannot write to /var/lib/avmonitoring`

**Cause :** Permissions incorrectes sur `/var/lib/avmonitoring`

**Diagnostic :**
```bash
ls -ld /var/lib/avmonitoring
# Attendu : drwxr-x--- 2 avmonitoring avmonitoring
```

**Fix :**
```bash
sudo chown -R avmonitoring:avmonitoring /var/lib/avmonitoring
sudo chmod 750 /var/lib/avmonitoring
sudo chmod 640 /var/lib/avmonitoring/config.json
sudo systemctl restart avmonitoring-agent
```

---

### Erreur : `RuntimeError: Runtime directory not writable`

**Cause :** Le service ne peut pas écrire dans `/var/lib/avmonitoring`

**Diagnostic :**
```bash
# Vérifier que systemd autorise l'écriture
sudo systemctl cat avmonitoring-agent | grep ReadWritePaths
# Doit contenir : ReadWritePaths=/var/lib/avmonitoring /var/log/avmonitoring

# Vérifier owner du dossier
sudo stat -c "%U:%G %a" /var/lib/avmonitoring
# Attendu : avmonitoring:avmonitoring 750
```

**Fix :**
```bash
# 1. Vérifier systemd service
sudo cp /opt/avmonitoring-agent/agent/packaging/systemd/avmonitoring-agent.service /etc/systemd/system/
sudo systemctl daemon-reload

# 2. Fixer permissions
sudo chown -R avmonitoring:avmonitoring /var/lib/avmonitoring
sudo chmod 750 /var/lib/avmonitoring

# 3. Redémarrer
sudo systemctl restart avmonitoring-agent
```

---

### Erreur : Config trouvée dans `/etc` ET `/var/lib`

**Cause :** Migration incomplète ou config manuelle créée dans `/etc`

**Diagnostic :**
```bash
ls -lh /etc/avmonitoring/config.json
ls -lh /var/lib/avmonitoring/config.json
```

**Fix :**
```bash
# Déterminer quelle config est la plus récente
ls -lt /etc/avmonitoring/config.json /var/lib/avmonitoring/config.json

# Si /etc est plus récente, la copier
sudo cp /etc/avmonitoring/config.json /var/lib/avmonitoring/config.json
sudo chown avmonitoring:avmonitoring /var/lib/avmonitoring/config.json
sudo chmod 640 /var/lib/avmonitoring/config.json

# Backup ancien fichier /etc
sudo mv /etc/avmonitoring/config.json /etc/avmonitoring/config.json.migrated.$(date +%Y%m%d)

# Redémarrer
sudo systemctl restart avmonitoring-agent
```

---

## 📝 Bonnes Pratiques

### ✅ DO

1. **Toujours utiliser `/var/lib/avmonitoring/config.json`** pour la config active
2. **Éditer la config via l'UI web** ou avec les bonnes permissions :
   ```bash
   sudo -u avmonitoring nano /var/lib/avmonitoring/config.json
   ```
3. **Vérifier les permissions après toute intervention manuelle**
4. **Utiliser le script de migration** pour les upgrades

### ❌ DON'T

1. **Ne PAS créer de config dans `/etc/avmonitoring/`** (sauf templates)
2. **Ne PAS éditer la config en tant que root** sans `chown` après
3. **Ne PAS donner 777** aux dossiers (sécurité)
4. **Ne PAS désactiver `ProtectSystem=strict`** dans le service systemd

---

## 🔗 Références

- [FHS 3.0](https://refspecs.linuxfoundation.org/FHS_3.0/fhs/index.html) - Filesystem Hierarchy Standard
- [systemd.exec - ProtectSystem](https://www.freedesktop.org/software/systemd/man/systemd.exec.html#ProtectSystem=)
- [Debian Policy - File System Layout](https://www.debian.org/doc/debian-policy/ch-opersys.html#file-system-layout)

---

## 📞 Support

En cas de problème persistant, collecter les infos suivantes :

```bash
# Diagnostic complet
{
  echo "=== Permissions ===" &&
  ls -ld /etc/avmonitoring /var/lib/avmonitoring /var/log/avmonitoring &&
  echo "" &&
  echo "=== Config location ===" &&
  grep AGENT_CONFIG /etc/default/avmonitoring-agent &&
  echo "" &&
  echo "=== Systemd ReadWritePaths ===" &&
  systemctl cat avmonitoring-agent | grep ReadWritePaths &&
  echo "" &&
  echo "=== Agent logs (dernières 50 lignes) ===" &&
  journalctl -u avmonitoring-agent -n 50 --no-pager
} > /tmp/avmonitoring-filesystem-diagnostic.log

cat /tmp/avmonitoring-filesystem-diagnostic.log
```

Envoyer ce fichier de diagnostic pour analyse.
