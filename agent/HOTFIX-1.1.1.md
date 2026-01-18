# Hotfix 1.1.1 - Correction du bug backend_url vs api_url

## 🐛 Bug critique identifié

### Symptôme
- Le collector démarre mais ne collecte jamais
- Aucun log de collecte visible dans journalctl
- Les équipements restent "offline" côté backend
- Message dans les logs : "✅ Collector started successfully" mais aucune activité ensuite

### Cause racine
Le code utilisait `cfg.get("api_url")` mais la configuration utilise `backend_url`.
Résultat : `api_url` est vide, donc le collector ne peut pas envoyer au backend.

### Fichiers affectés
1. **`src/collector.py:236`** - Cherchait `api_url` uniquement
2. **`src/config_sync.py:118`** - Cherchait `api_url` uniquement
3. **`src/config_sync.py:173`** - Sauvegardait comme `api_url`

## ✅ Corrections apportées

### 1. src/collector.py (ligne 236-245)

**Avant** :
```python
api_url = (cfg.get("api_url") or "").strip()
# ...
if not api_url or not site_name or not site_token:
    _set_status(
        last_send_at=_iso(_now_utc()),
        last_send_ok=False,
        last_send_error="missing_api_url_or_site_credentials",
    )
```

**Après** :
```python
# Support both "backend_url" (new) and "api_url" (legacy) for backward compatibility
api_url = (cfg.get("backend_url") or cfg.get("api_url") or "").strip()
# ...
if not api_url or not site_name or not site_token:
    _set_status(
        last_send_at=_iso(_now_utc()),
        last_send_ok=False,
        last_send_error="missing_backend_url_or_site_credentials",
    )
```

### 2. src/config_sync.py (ligne 118-128)

**Avant** :
```python
api_url = (cfg.get("api_url") or "").strip()
# ...
if not api_url or not site_token:
    _set_sync_status(
        last_sync_at=_iso(_now_utc()),
        last_sync_ok=False,
        last_sync_error="missing_api_url_or_site_token",
    )
    print("⚠️  Config sync skipped: missing api_url or site_token")
```

**Après** :
```python
# Support both "backend_url" (new) and "api_url" (legacy) for backward compatibility
api_url = (cfg.get("backend_url") or cfg.get("api_url") or "").strip()
# ...
if not api_url or not site_token:
    _set_sync_status(
        last_sync_at=_iso(_now_utc()),
        last_sync_ok=False,
        last_sync_error="missing_backend_url_or_site_token",
    )
    print("⚠️  Config sync skipped: missing backend_url or site_token")
```

### 3. src/config_sync.py (ligne 173)

**Avant** :
```python
"api_url": api_url,
```

**Après** :
```python
"backend_url": api_url,  # Always save as "backend_url" (normalized)
```

## 📦 Déploiement

### Sur la machine distante

```bash
# 1. Sauvegarder la config actuelle
sudo cp /etc/avmonitoring/config.json /etc/avmonitoring/config.json.backup

# 2. Arrêter le service
sudo systemctl stop avmonitoring-agent

# 3. Copier les fichiers corrigés
sudo cp src/collector.py /opt/avmonitoring-agent/src/
sudo cp src/config_sync.py /opt/avmonitoring-agent/src/

# 4. Vérifier les permissions
sudo chown -R avmonitoring:avmonitoring /opt/avmonitoring-agent/src/

# 5. Démarrer le service
sudo systemctl start avmonitoring-agent

# 6. Vérifier les logs
sudo journalctl -u avmonitoring-agent -f
```

### Logs attendus après le déploiement

```
🚀 Starting collector automatically...
✅ Collector started successfully
🔄 [Collector] Starting collection cycle...
📊 [Collector] Device 1.1.1.1 (ping) → online
📊 [Collector] Device 192.168.1.254 (ping) → online
📊 [Collector] Device 8.8.8.8 (ping) → online
📤 [Collector] Sending 3 device states to backend...
✅ [Collector] Data sent successfully
```

## 🔍 Vérification

### Vérifier que la collecte fonctionne

```bash
# Attendre 30 secondes puis vérifier les logs
sudo journalctl -u avmonitoring-agent -n 50 | grep -E "Collector|collect|sending|sent"
```

### Vérifier côté backend

Les équipements devraient maintenant remonter leur statut réel (online/offline) au lieu de rester bloqués offline.

## 📊 Impact

| Aspect | Avant | Après |
|--------|-------|-------|
| **Configuration** | `api_url` uniquement | `backend_url` ET `api_url` (compatibilité) |
| **Collecte** | ❌ Bloquée (api_url vide) | ✅ Fonctionne |
| **Backend** | Équipements offline | Statuts réels |
| **Backward compatibility** | ❌ Non | ✅ Oui (accepte les 2 formats) |

## 🎯 Version

- **Version** : 1.1.1
- **Date** : 2024-01-18
- **Type** : Hotfix critique
- **Priorité** : Haute (bloquant production)
