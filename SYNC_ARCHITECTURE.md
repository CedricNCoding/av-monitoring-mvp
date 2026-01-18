# Architecture de Synchronisation de Configuration

## Vue d'ensemble

Le système de synchronisation permet au **backend** d'être la **source de vérité** pour la configuration des équipements, tandis que les **agents** récupèrent automatiquement cette configuration par interrogation périodique (mode pull).

## Principes

### 1. Source de vérité: Backend
- Le backend stocke la configuration officielle de chaque site dans PostgreSQL
- Chaque équipement est défini avec:
  - Identité: IP, nom, bâtiment, étage, salle, type
  - Driver: ping, snmp, pjlink + configuration spécifique
  - Expectations: always_on, schedule, alert_after_s

### 2. Synchronisation Pull
- L'agent interroge le backend toutes les N minutes (défaut: 5 min)
- Comparaison par hash MD5 pour détecter les changements
- Mise à jour automatique si la configuration a changé
- **Résilience**: en cas d'erreur backend, l'agent continue avec sa config locale

### 3. Versioning par Hash MD5
- Chaque configuration est identifiée par un hash MD5
- Calculé de manière déterministe (JSON sorted keys)
- Permet une détection instantanée des changements

## Architecture Technique

### Backend

#### Modèle de données

**Table `sites`:**
```sql
- timezone: VARCHAR (ex: "Europe/Paris")
- doubt_after_days: INTEGER (défaut: 2)
- ok_interval_s: INTEGER (défaut: 300)
- ko_interval_s: INTEGER (défaut: 60)
- config_version: VARCHAR (hash MD5)
- config_updated_at: TIMESTAMP
```

**Table `devices`:**
```sql
- floor: VARCHAR (étage)
- driver_config: JSONB (config SNMP, PJLink, etc.)
- expectations: JSONB (always_on, schedule, alert_after_s)
```

#### Endpoint `/config/{site_token}`

**Requête:**
```
GET /config/{site_token}
```

**Réponse:**
```json
{
  "config_hash": "abc123def456...",
  "site_name": "Site Paris",
  "timezone": "Europe/Paris",
  "doubt_after_days": 2,
  "reporting": {
    "ok_interval_s": 300,
    "ko_interval_s": 60
  },
  "devices": [
    {
      "ip": "192.168.1.10",
      "name": "Projecteur Salle A",
      "building": "Bâtiment A",
      "floor": "1",
      "room": "Salle 101",
      "type": "projector",
      "driver": "pjlink",
      "snmp": {},
      "pjlink": {
        "password": "admin",
        "port": 4352,
        "timeout_s": 2
      },
      "expectations": {
        "always_on": false,
        "alert_after_s": 300,
        "schedule": {
          "timezone": "Europe/Paris",
          "rules": [
            {
              "days": ["mon", "tue", "wed", "thu", "fri"],
              "start": "08:00",
              "end": "18:00"
            }
          ]
        }
      }
    }
  ]
}
```

#### Calcul du Hash

Le hash est calculé sur:
```json
{
  "site_name": "...",
  "timezone": "...",
  "doubt_after_days": 2,
  "ok_interval_s": 300,
  "ko_interval_s": 60,
  "devices": [
    {
      "ip": "...",
      "name": "...",
      "building": "...",
      "floor": "...",
      "room": "...",
      "type": "...",
      "driver": "...",
      "driver_config": {...},
      "expectations": {...}
    }
  ]
}
```

Sérialisé en JSON avec `sort_keys=True`, puis hashé en MD5.

### Agent

#### Module `config_sync.py`

**Fonctions principales:**
- `sync_config_from_backend(cfg)`: Interroge le backend et met à jour si nécessaire
- `run_sync_loop(stop_flag, interval_minutes)`: Boucle de synchronisation
- `start_sync_thread(interval_minutes)`: Démarre le thread de sync
- `get_sync_status()`: Retourne l'état de la dernière sync

**État exposé:**
```json
{
  "last_sync_at": "2026-01-18T10:30:00+00:00",
  "last_sync_ok": true,
  "last_sync_error": null,
  "current_hash": "abc123...",
  "backend_hash": "abc123...",
  "config_updated_at": "2026-01-18T10:30:00+00:00"
}
```

#### Intégration dans `webapp.py`

Le thread de sync est démarré automatiquement au démarrage de l'application:
```python
@app.on_event("startup")
def startup_event():
    _sync_thread, _sync_stop_flag = start_sync_thread(interval_minutes=5)
```

#### Indicateur visuel dans l'UI

L'interface agent affiche:
- ✅ Status de la dernière sync (OK / Erreur)
- Timestamp de la dernière sync
- Hash de la config actuelle
- Message d'erreur éventuel

## Utilisation

### Configuration d'un équipement dans le backend

**Via API (à implémenter):**
```bash
POST /admin/devices
{
  "site_id": 1,
  "ip": "192.168.1.20",
  "name": "Projecteur B",
  "building": "Bâtiment B",
  "floor": "2",
  "room": "Salle 201",
  "type": "projector",
  "driver": "pjlink",
  "driver_config": {
    "pjlink": {
      "password": "admin",
      "port": 4352,
      "timeout_s": 2
    }
  },
  "expectations": {
    "always_on": false,
    "alert_after_s": 300,
    "schedule": {
      "timezone": "Europe/Paris",
      "rules": [
        {"days": ["mon", "tue", "wed", "thu", "fri"], "start": "08:00", "end": "18:00"}
      ]
    }
  }
}
```

**Via UI (à implémenter):**
- Interface web dans le backend pour gérer les équipements
- CRUD complet: Create, Read, Update, Delete

### Comportement de l'agent

1. **Démarrage:**
   - Charge `config.json` locale (fallback)
   - Démarre le thread de sync
   - Première sync après 10 secondes

2. **Sync périodique:**
   - Toutes les 5 minutes (configurable via `CONFIG_SYNC_INTERVAL_MIN`)
   - Compare le hash local avec le hash backend
   - Si différent → télécharge et applique la nouvelle config
   - Si identique → rien ne change

3. **Résilience:**
   - En cas d'erreur réseau → continue avec la config locale
   - En cas d'erreur backend → continue avec la config locale
   - Logs détaillés pour le diagnostic

4. **Mise à jour transparente:**
   - La config est sauvegardée dans `config.json`
   - Le collector la rechargera au prochain cycle
   - Aucun redémarrage nécessaire

## Variables d'environnement

### Backend
Aucune variable supplémentaire nécessaire.

### Agent
- `CONFIG_SYNC_INTERVAL_MIN`: Intervalle de sync en minutes (défaut: 5)
- `AGENT_CONFIG`: Chemin du fichier config.json (défaut: `/agent/config/config.json`)

## Migration

### 1. Appliquer le script SQL

```bash
psql -h localhost -U av_user -d av_monitoring < backend/migrations/001_add_config_sync_fields.sql
```

Ou via Docker:
```bash
docker exec -i av-monitoring-backend-1 psql -U av_user -d av_monitoring < backend/migrations/001_add_config_sync_fields.sql
```

### 2. Redémarrer les services

```bash
docker-compose restart
```

### 3. Vérifier la sync

- Ouvrir l'UI agent: `http://localhost:8080`
- Vérifier la section "🔄 Sync Backend"
- Doit afficher "✅ OK" après quelques secondes

## Logs

### Backend
```
✅ Config sync endpoint called by site Paris (hash: abc123...)
```

### Agent
```
🚀 Config sync loop started (interval: 5 min)
🔄 Fetching config from http://backend:8000/config/...
✅ Config is up-to-date (hash: abc123...)
```

Ou en cas de changement:
```
🔄 Fetching config from http://backend:8000/config/...
📥 Config changed! Updating from backend...
   Old hash: abc123...
   New hash: def456...
✅ Config updated successfully! 12 devices configured.
📢 Config updated, collector will reload on next cycle
```

## Tests

### Test manuel

1. **Créer un équipement dans le backend** (via SQL temporairement):
```sql
INSERT INTO devices (site_id, name, ip, device_type, driver, building, floor, room, driver_config, expectations)
VALUES (
  1,
  'Test Device',
  '192.168.1.99',
  'projector',
  'ping',
  'Building A',
  '1',
  'Room 101',
  '{}'::jsonb,
  '{"always_on": false, "alert_after_s": 300}'::jsonb
);
```

2. **Attendre 5 minutes** (ou moins si interval configuré)

3. **Vérifier dans l'UI agent:**
   - L'équipement doit apparaître automatiquement
   - Le hash doit avoir changé

4. **Supprimer l'équipement du backend:**
```sql
DELETE FROM devices WHERE ip = '192.168.1.99';
```

5. **Attendre la prochaine sync:**
   - L'équipement doit disparaître de l'agent

## Prochaines étapes

1. ✅ Endpoint `/config/{token}` (backend)
2. ✅ Module `config_sync.py` (agent)
3. ✅ Intégration dans webapp.py
4. ✅ UI sync status
5. ✅ Migration SQL
6. ⏳ UI backend pour gérer les équipements (CRUD)
7. ⏳ Tests automatisés
8. ⏳ Documentation utilisateur finale

## Sécurité

- **Authentification:** Token par site (existant)
- **Pas de push:** Aucun webhook, aucune notification push
- **Résilience:** L'agent ne plante jamais si le backend est down
- **Audit:** Le `config_updated_at` permet de tracer les changements

## Performances

- **Fréquence:** 5 min par défaut (configurable)
- **Payload:** Léger (~few KB par site)
- **Hash:** Calcul rapide O(n) avec n = nb devices
- **Cache:** Aucun cache nécessaire, la comparaison de hash est instantanée
