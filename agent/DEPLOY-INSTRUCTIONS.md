# Instructions de déploiement - Hotfix 1.1.1

## 🔥 Bug critique identifié et corrigé

### Le problème
Tes équipements restent "offline" car le code cherchait `cfg.get("api_url")` mais ta configuration utilise `backend_url`.

**Preuve dans ta config** :
```json
{
  "api_url": "https://avmonitoring.rouni.eu/ingest",  // ← Le code cherchait ça
  "backend_url": ...  // ← Mais la doc demandait ça
}
```

**Résultat** : `api_url` était vide pour les nouvelles installations → pas d'envoi au backend → équipements offline.

### La solution
J'ai corrigé 2 fichiers pour accepter **les deux formats** (`backend_url` ET `api_url`) :
- ✅ [src/collector.py](src/collector.py#L237)
- ✅ [src/config_sync.py](src/config_sync.py#L119)

---

## 📦 Comment déployer le hotfix

### Option 1 : Script automatique (recommandé)

Sur la machine distante (Debian) :

```bash
# 1. Copier les fichiers corrigés depuis ta machine locale
# (depuis ta machine locale)
cd /Users/cedric/Documents/av-monitoring-mvp/agent
scp src/collector.py src/config_sync.py root@debian:~/agent/src/
scp scripts/hotfix-1.1.1-deploy.sh root@debian:~/agent/scripts/

# 2. Se connecter à la machine distante
ssh root@debian

# 3. Déployer le hotfix
cd ~/agent/scripts
sudo ./hotfix-1.1.1-deploy.sh
```

Le script va :
1. Sauvegarder ta config actuelle
2. Arrêter le service
3. Copier les fichiers corrigés dans `/opt/avmonitoring-agent/src/`
4. Restaurer les permissions
5. Redémarrer le service
6. Vérifier que tout fonctionne

### Option 2 : Déploiement manuel

```bash
# Sur la machine distante (Debian)

# 1. Sauvegarder
sudo cp /etc/avmonitoring/config.json /etc/avmonitoring/config.json.backup

# 2. Arrêter
sudo systemctl stop avmonitoring-agent

# 3. Copier les fichiers
sudo cp ~/agent/src/collector.py /opt/avmonitoring-agent/src/
sudo cp ~/agent/src/config_sync.py /opt/avmonitoring-agent/src/

# 4. Permissions
sudo chown -R avmonitoring:avmonitoring /opt/avmonitoring-agent/src/

# 5. Démarrer
sudo systemctl start avmonitoring-agent

# 6. Vérifier
sudo journalctl -u avmonitoring-agent -f
```

---

## ✅ Vérification

### 1. Les logs doivent maintenant montrer la collecte

```bash
sudo journalctl -u avmonitoring-agent -n 100 | grep -E "Collector|collect"
```

**Logs attendus** :
```
🚀 Starting collector automatically...
✅ Collector started successfully
🔄 Starting collection cycle...
📊 Device 1.1.1.1 (ping) → online
📊 Device 192.168.1.254 (ping) → online
📊 Device 8.8.8.8 (ping) → online
📤 Sending 3 device states to backend...
✅ Data sent successfully
```

### 2. Vérifier côté backend

Va sur https://avmonitoring.rouni.eu/ui/agents/ et vérifie que :
- Les 3 équipements (1.1.1.1, 192.168.1.254, 8.8.8.8) remontent leur statut réel
- Ils ne sont plus bloqués en "offline"
- Les timestamps sont récents

### 3. Si ça ne marche toujours pas

Envoie-moi les logs complets :
```bash
sudo journalctl -u avmonitoring-agent -n 200 --no-pager
```

---

## 📊 Résumé des fichiers modifiés

### src/collector.py (ligne 237)

**Avant** :
```python
api_url = (cfg.get("api_url") or "").strip()
```

**Après** :
```python
# Support both "backend_url" (new) and "api_url" (legacy)
api_url = (cfg.get("backend_url") or cfg.get("api_url") or "").strip()
```

### src/config_sync.py (ligne 119)

**Avant** :
```python
api_url = (cfg.get("api_url") or "").strip()
```

**Après** :
```python
# Support both "backend_url" (new) and "api_url" (legacy)
api_url = (cfg.get("backend_url") or cfg.get("api_url") or "").strip()
```

### src/config_sync.py (ligne 173)

**Avant** :
```python
"api_url": api_url,
```

**Après** :
```python
"backend_url": api_url,  # Always save as "backend_url" (normalized)
```

---

## 🎯 Backward compatibility

Le code accepte maintenant **les deux formats** :
- ✅ `"backend_url": "https://..."` (nouveau, recommandé)
- ✅ `"api_url": "https://..."` (ancien, toujours supporté)

Si les deux sont présents, `backend_url` a la priorité.

---

## 📝 Documentation mise à jour

- [CHANGELOG.md](CHANGELOG.md) - Version 1.1.1 ajoutée
- [HOTFIX-1.1.1.md](HOTFIX-1.1.1.md) - Détails techniques du bug
- Ce fichier - Instructions de déploiement

---

## 🚀 Après le déploiement

Une fois le hotfix déployé :

1. **Attends 1-2 minutes** pour que la première collecte se lance
2. **Vérifie les logs** : `sudo journalctl -u avmonitoring-agent -f`
3. **Vérifie le backend** : Les équipements doivent remonter leur statut
4. **Confirme-moi** que ça marche

Si tout fonctionne, les équipements devraient remonter leur statut toutes les 5 minutes (300s par défaut si tous online).
