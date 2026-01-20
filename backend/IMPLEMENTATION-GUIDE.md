# Guide d'implémentation - Carte & Graphiques

## ✅ Modifications Backend terminées

### 1. Modèle de données (`app/models.py`)
Ajouté à la classe `Site` :
```python
address = Column(String, nullable=True)
latitude = Column(String, nullable=True)
longitude = Column(String, nullable=True)
```

### 2. Endpoints API créés (`app/main.py`)

#### POST `/ui/agents/{site_id}/location`
Permet de mettre à jour l'adresse et coordonnées GPS d'un site.

#### GET `/api/devices/{device_id}/history?days=30`
Retourne l'historique des états d'un équipement.
```json
{
  "device_id": 1,
  "device_name": "Projecteur A",
  "events": [
    {"timestamp": "2024-01-18T10:00:00+00:00", "status": "online", "verdict": "ok"},
    ...
  ]
}
```

#### GET `/api/devices/{device_id}/uptime?days=30`
Calcule le pourcentage de disponibilité.
```json
{
  "device_id": 1,
  "uptime_percent": 98.5,
  "total_events": 1000,
  "online_events": 985,
  "offline_events": 15
}
```

#### GET `/api/sites/map-data`
Retourne les données pour la carte interactive.
```json
{
  "sites": [
    {
      "site_id": 1,
      "site_name": "Campus A",
      "address": "123 Rue Example, Paris",
      "latitude": 48.8566,
      "longitude": 2.3522,
      "color": "green",
      "devices_total": 10,
      "devices_online": 9,
      "devices_offline": 1
    }
  ]
}
```

---

## 📝 Modifications Frontend à faire

### 1. Migration de la base de données

```bash
# Sur le serveur de production
docker exec -it backend_container /bin/bash

# Puis dans le container
python -c "from app.db import engine; from app.models import Base; Base.metadata.create_all(bind=engine)"
```

Ou via SQL direct :
```sql
ALTER TABLE sites ADD COLUMN address VARCHAR;
ALTER TABLE sites ADD COLUMN latitude VARCHAR;
ALTER TABLE sites ADD COLUMN longitude VARCHAR;
```

### 2. Modifier `app/templates/dashboard.html`

#### Ajouter Leaflet.js dans le `<head>` :
```html
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
```

#### Ajouter la carte dans le body (après les KPIs) :
```html
<!-- Carte des sites -->
<div class="card">
  <h2>📍 Carte des sites</h2>
  <div id="map" style="height: 500px; border-radius: 8px;"></div>
</div>

<script>
// Initialiser la carte (centré sur Paris par défaut)
const map = L.map('map').setView([48.8566, 2.3522], 6);

// Ajouter le fond de carte OpenStreetMap
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '© OpenStreetMap'
}).addTo(map);

// Charger les données des sites
fetch('/api/sites/map-data')
  .then(res => res.json())
  .then(data => {
    data.sites.forEach(site => {
      // Créer une icône colorée selon le statut
      const icon = L.divIcon({
        className: 'custom-marker',
        html: `<div style="background-color: ${site.color}; width: 20px; height: 20px; border-radius: 50%; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3);"></div>`,
        iconSize: [20, 20]
      });

      // Ajouter le marker
      const marker = L.marker([site.latitude, site.longitude], { icon }).addTo(map);

      // Popup avec infos
      marker.bindPopup(`
        <b>${site.site_name}</b><br>
        ${site.address || 'Adresse non renseignée'}<br><br>
        <b>Équipements:</b><br>
        🟢 Online: ${site.devices_online}<br>
        🔴 Offline: ${site.devices_offline}<br>
        ⚪ Unknown: ${site.devices_unknown}<br>
        <a href="/ui/agents/${site.site_id}/devices">Voir détails →</a>
      `);
    });

    // Ajuster la vue pour afficher tous les markers
    if (data.sites.length > 0) {
      const bounds = L.latLngBounds(data.sites.map(s => [s.latitude, s.longitude]));
      map.fitBounds(bounds, { padding: [50, 50] });
    }
  });
</script>
```

### 3. Modifier `app/templates/agent_devices.html`

Ajouter un formulaire pour l'adresse dans la section de configuration du site :

```html
<!-- Localisation du site -->
<div class="card">
  <h2>📍 Localisation</h2>
  <form method="post" action="/ui/agents/{{ site.id }}/location">
    <div class="form-group">
      <label>Adresse</label>
      <input type="text" name="address" value="{{ site.address or '' }}" placeholder="123 Rue Example, 75001 Paris">
    </div>
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
      <div class="form-group">
        <label>Latitude</label>
        <input type="text" name="latitude" value="{{ site.latitude or '' }}" placeholder="48.8566">
      </div>
      <div class="form-group">
        <label>Longitude</label>
        <input type="text" name="longitude" value="{{ site.longitude or '' }}" placeholder="2.3522">
      </div>
    </div>
    <button type="submit" class="btn">Enregistrer</button>
    <small class="muted">Astuce: utilisez <a href="https://www.latlong.net/" target="_blank">latlong.net</a> pour obtenir les coordonnées</small>
  </form>
</div>
```

### 4. Modifier `app/templates/device_detail.html`

#### Ajouter Chart.js dans le `<head>` :
```html
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
```

#### Ajouter le graphique dans le body :
```html
<!-- Historique -->
<div class="card">
  <h2>📊 Historique (30 derniers jours)</h2>
  <canvas id="historyChart" style="max-height: 300px;"></canvas>
</div>

<!-- Disponibilité -->
<div class="card">
  <h2>⏱️ Disponibilité</h2>
  <div id="uptime-stats"></div>
</div>

<script>
const deviceId = {{ device.id }};

// Charger l'uptime
fetch(`/api/devices/${deviceId}/uptime?days=30`)
  .then(res => res.json())
  .then(data => {
    document.getElementById('uptime-stats').innerHTML = `
      <div style="font-size: 48px; font-weight: bold; color: ${data.uptime_percent > 95 ? '#22c55e' : '#ef4444'};">
        ${data.uptime_percent}%
      </div>
      <div class="muted">Sur les ${data.period_days} derniers jours</div>
      <div style="margin-top: 16px;">
        <div>🟢 Online: ${data.online_events} événements</div>
        <div>🔴 Offline: ${data.offline_events} événements</div>
      </div>
    `;
  });

// Charger l'historique et créer le graphique
fetch(`/api/devices/${deviceId}/history?days=30`)
  .then(res => res.json())
  .then(data => {
    const ctx = document.getElementById('historyChart').getContext('2d');

    // Grouper par jour
    const dailyData = {};
    data.events.forEach(e => {
      const day = e.timestamp.split('T')[0];
      if (!dailyData[day]) dailyData[day] = { online: 0, offline: 0 };
      if (e.status === 'online') dailyData[day].online++;
      else dailyData[day].offline++;
    });

    const labels = Object.keys(dailyData);
    const onlineData = labels.map(day => dailyData[day].online);
    const offlineData = labels.map(day => dailyData[day].offline);

    new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Online',
            data: onlineData,
            borderColor: '#22c55e',
            backgroundColor: 'rgba(34, 197, 94, 0.1)',
            fill: true
          },
          {
            label: 'Offline',
            data: offlineData,
            borderColor: '#ef4444',
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            fill: true
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: { beginAtZero: true }
        }
      }
    });
  });
</script>
```

---

## 🚀 Déploiement

### 1. Commiter les changements
```bash
cd /Users/cedric/Documents/av-monitoring-mvp/backend
git add .
git commit -m "feat: add map + history + uptime endpoints"
git push
```

### 2. Sur le serveur de production
```bash
git pull
docker-compose down
docker-compose up -d --build
```

### 3. Appliquer la migration DB
```sql
-- Via psql ou pgAdmin
ALTER TABLE sites ADD COLUMN IF NOT EXISTS address VARCHAR;
ALTER TABLE sites ADD COLUMN IF NOT EXISTS latitude VARCHAR;
ALTER TABLE sites ADD COLUMN IF NOT EXISTS longitude VARCHAR;
```

### 4. Tester
- Dashboard : https://avmonitoring.rouni.eu/ui/dashboard
- API carte : https://avmonitoring.rouni.eu/api/sites/map-data
- API historique : https://avmonitoring.rouni.eu/api/devices/1/history
- API uptime : https://avmonitoring.rouni.eu/api/devices/1/uptime

---

## 📌 Notes

- La carte utilise OpenStreetMap (gratuit, pas de clé API nécessaire)
- Pour obtenir lat/long : https://www.latlong.net/
- Les couleurs de pins : vert (tout OK), orange (unknown), rouge (offline)
- L'historique conserve 30 jours par défaut (configurable via `?days=N`)
- Le graphique agrège par jour pour plus de lisibilité
