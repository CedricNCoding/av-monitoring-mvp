# Fix - Configuration par défaut invalide

## 🐛 Problème identifié

Lors de l'installation, le fichier `/etc/avmonitoring/config.json` était créé avec :
```json
{
  "backend_url": "https://avmonitoring.example.com"
}
```

**Résultat** : L'agent essayait de se connecter à `avmonitoring.example.com` qui n'existe pas, causant des erreurs DNS :
```
ConnectionError: Failed to resolve 'avmonitoring.example.com'
```

## ✅ Corrections apportées

### 1. Config par défaut plus claire

**Avant** :
```json
{
  "site_name": "site-demo",
  "site_token": "CHANGE_ME_AFTER_INSTALL",
  "backend_url": "https://avmonitoring.example.com"
}
```

**Après** :
```json
{
  "_comment": "IMPORTANT: Configurez site_token, backend_url et site_name avant de démarrer",
  "site_name": "CHANGE_ME",
  "site_token": "CHANGE_ME",
  "backend_url": "https://CHANGE_ME/ingest"
}
```

### 2. Détection automatique des valeurs non configurées

Le collector détecte maintenant automatiquement :
- ✅ `"CHANGE_ME"` dans les valeurs
- ✅ `"example.com"` dans l'URL
- ✅ Valeurs vides

Et affiche des messages d'erreur explicites :
- `backend_url_not_configured`
- `site_token_not_configured`
- `site_name_not_configured`

## 📦 Fichiers modifiés

1. **[config.example.json](config.example.json)** - Template plus clair avec `CHANGE_ME`
2. **[scripts/install.sh](scripts/install.sh#L180-L194)** - Config par défaut mise à jour
3. **[src/collector.py](src/collector.py#L241-L257)** - Détection des valeurs non configurées

## 🎯 Bénéfices

- ✅ Plus d'erreur DNS avec `example.com`
- ✅ Messages d'erreur clairs si la config n'est pas modifiée
- ✅ Impossible de rater la configuration
- ✅ Logs explicites : "backend_url_not_configured" au lieu de "Failed to resolve"

## 📝 Note pour l'utilisateur

Après l'installation, il faut **TOUJOURS** éditer `/etc/avmonitoring/config.json` :

```bash
sudo nano /etc/avmonitoring/config.json
```

Et remplacer :
- `"site_name": "CHANGE_ME"` → Nom du site
- `"site_token": "CHANGE_ME"` → Token depuis le backend
- `"backend_url": "https://CHANGE_ME/ingest"` → URL réelle (ex: `https://avmonitoring.rouni.eu/ingest`)

Puis redémarrer :
```bash
sudo systemctl restart avmonitoring-agent
```

## 📊 Version

- **Inclus dans** : Version 1.1.1
- **Date** : 2024-01-18
