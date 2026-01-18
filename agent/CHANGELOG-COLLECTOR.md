# Changelog - Démarrage automatique du collector

## 🎯 Problème résolu

**Avant** : Le service systemd démarrait l'interface web, mais le collector ne démarrait **jamais automatiquement**. Les équipements remontaient tous "offline" côté backend car aucune collecte n'était active.

**Cause** : Le collector ne démarrait que lors d'un clic manuel sur le bouton "Start" dans l'interface web.

**Après** : Le collector démarre automatiquement au lancement du service, comme en Docker.

---

## 📝 Changements effectués

### Fichier modifié : `src/webapp.py`

#### 1. Fonction `startup_event()` (ligne 449)

**Avant** :
```python
@app.on_event("startup")
def startup_event():
    """
    Démarre automatiquement le thread de synchronisation au démarrage de l'app.
    """
    # Démarrait uniquement la sync config
    _sync_thread, _sync_stop_flag = start_sync_thread(...)
```

**Après** :
```python
@app.on_event("startup")
def startup_event():
    """
    Démarre automatiquement le thread de synchronisation ET le collector.
    """
    # 1. Démarre la sync config
    _sync_thread, _sync_stop_flag = start_sync_thread(...)

    # 2. Démarre le collector automatiquement
    print("🚀 Starting collector automatically...")
    ensure_collector_running()
    if collector_running():
        print("✅ Collector started successfully")
    else:
        print("⚠️  Collector failed to start (check configuration)")
```

#### 2. Fonction `shutdown_event()` (ligne 475)

**Avant** :
```python
@app.on_event("shutdown")
def shutdown_event():
    """
    Arrête proprement le thread de synchronisation.
    """
    # Arrêtait uniquement la sync config
    _sync_stop_flag["stop"] = True
```

**Après** :
```python
@app.on_event("shutdown")
def shutdown_event():
    """
    Arrête proprement le thread de synchronisation ET le collector.
    """
    # 1. Arrêter le collector
    print("🛑 Stopping collector...")
    _stop_flag["stop"] = True

    # 2. Arrêter la sync config
    _sync_stop_flag["stop"] = True
```

---

## ✅ Comportement attendu après modification

### Au démarrage du service

```bash
sudo systemctl start avmonitoring-agent
```

**Logs visibles** (via `journalctl -u avmonitoring-agent -f`) :
```
✅ Config sync thread started (interval: 5 min)
🚀 Starting collector automatically...
✅ Collector started successfully
🔄 [Collector] Starting collection cycle...
📊 [Collector] Device 192.168.1.1 (ping) → online
📊 [Collector] Device 192.168.1.2 (snmp) → online
📤 [Collector] Sending 2 device states to backend...
✅ [Collector] Data sent successfully
```

### Vérification du fonctionnement

```bash
# 1. Vérifier que le service tourne
sudo systemctl status avmonitoring-agent
# Doit afficher : active (running)

# 2. Vérifier les logs
sudo journalctl -u avmonitoring-agent -n 50
# Doit contenir : "✅ Collector started successfully"
# Doit contenir : "Starting collection cycle"

# 3. Vérifier l'interface web
curl http://localhost:8080
# L'interface doit afficher que le collector est actif
```

### Côté backend

Les équipements doivent maintenant remonter leur statut réel :
- ✅ Équipements en ligne → affichés "online"
- ✅ Équipements hors ligne → affichés "offline"
- ✅ Métriques collectées et envoyées périodiquement

---

## 🔄 Compatibilité

### Docker
✅ **Inchangé** : Le comportement Docker reste identique (le collector démarre toujours automatiquement en Docker)

### Installation native (systemd)
✅ **Corrigé** : Le collector démarre maintenant automatiquement comme en Docker

### Interface web
✅ **Préservée** : Le bouton "Start/Stop" fonctionne toujours pour contrôle manuel si besoin

---

## 🐛 Dépannage

### Le collector ne démarre pas

**Vérifier la configuration** :
```bash
sudo cat /etc/avmonitoring/config.json
```

La configuration doit contenir au minimum :
```json
{
  "site_name": "mon-site",
  "site_token": "TOKEN_VALIDE",
  "backend_url": "https://backend.example.com"
}
```

**Vérifier les logs d'erreur** :
```bash
sudo journalctl -u avmonitoring-agent | grep -i error
```

**Erreurs courantes** :
- `⚠️ Collector failed to start` → Vérifier la configuration
- `Connection refused` → Vérifier que le backend est accessible
- `401 Unauthorized` → Vérifier le token

### Redémarrer le service

```bash
sudo systemctl restart avmonitoring-agent
```

---

## 📊 Impact

| Aspect | Avant | Après |
|--------|-------|-------|
| **Collecte** | Manuelle (bouton UI) | Automatique au démarrage |
| **Statuts backend** | Tous offline | Statuts réels |
| **Intervention** | Requise à chaque démarrage | Aucune |
| **Production-ready** | ❌ Non | ✅ Oui |

---

## 🎉 Résultat

**L'agent est maintenant production-ready** :
- ✅ Installation → Configuration → Démarrage service → **Collecte active automatiquement**
- ✅ Aucun clic dans l'UI requis
- ✅ Comportement identique à Docker
- ✅ Logs clairs pour vérification

**Date** : 2024-01-18
**Version** : 1.1.0
