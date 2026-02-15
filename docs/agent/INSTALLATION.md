# Installation de l'agent AV Monitoring en production

Ce document décrit l'installation et l'exploitation de l'agent AV Monitoring sur un système Linux en production, **sans Docker**.

## 📋 Prérequis

### Système d'exploitation
- **Linux** : Ubuntu 20.04+, Debian 11+, ou distribution équivalente
- **systemd** : Requis pour la gestion du service
- **Accès root** : Nécessaire pour l'installation

### Logiciels requis
- **Python 3.10 ou supérieur**
- **pip** et **venv** (généralement inclus avec Python)

Installation des prérequis sur Ubuntu/Debian :
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv
```

### Réseau
- Accès sortant HTTPS vers le backend (port 443)
- Port 8080 (local) pour l'interface web de l'agent

---

## 🚀 Installation rapide

### 1. Télécharger le code
```bash
# Cloner le dépôt ou télécharger l'archive
git clone https://github.com/CedricNCoding/av-monitoring-mvp.git
cd av-monitoring-mvp/agent
```

Ou à partir d'une archive :
```bash
# Décompresser l'archive
tar -xzf avmonitoring-agent-X.Y.Z.tar.gz
cd avmonitoring-agent
```

### 2. Lancer l'installation
```bash
cd scripts
sudo ./install.sh
```

Le script va :
- ✅ Vérifier les prérequis (Python, systemd)
- ✅ Créer l'utilisateur système `avmonitoring`
- ✅ Créer les répertoires nécessaires
- ✅ Installer le code dans `/opt/avmonitoring-agent`
- ✅ Créer un environnement virtuel Python
- ✅ Installer les dépendances
- ✅ Copier le fichier de configuration exemple
- ✅ Installer et activer le service systemd

### 3. Configurer l'agent
```bash
sudo nano /etc/avmonitoring/config.json
```

**Paramètres obligatoires** :
```json
{
  "site_name": "nom-de-votre-site",
  "site_token": "VOTRE_TOKEN_ICI",
  "backend_url": "https://avmonitoring.example.com",
  "timezone": "Europe/Paris",
  "doubt_after_days": 2,
  "reporting": {
    "ok_interval_s": 300,
    "ko_interval_s": 60
  },
  "devices": []
}
```

> **Note** : Le token `site_token` est fourni par le backend lors de la création du site.

### 4. Démarrer le service
```bash
sudo systemctl start avmonitoring-agent
```

### 5. Vérifier le fonctionnement
```bash
# Vérifier le statut
sudo systemctl status avmonitoring-agent

# Consulter les logs
sudo journalctl -u avmonitoring-agent -f
```

---

## 📂 Structure des fichiers installés

| Chemin | Description | Permissions |
|--------|-------------|-------------|
| `/opt/avmonitoring-agent/` | Code source de l'application | `avmonitoring:avmonitoring` (750) |
| `/opt/avmonitoring-agent/venv/` | Environnement virtuel Python | `avmonitoring:avmonitoring` |
| `/etc/avmonitoring/config.json` | Fichier de configuration | `avmonitoring:avmonitoring` (640) |
| `/var/lib/avmonitoring/` | Données de l'application | `avmonitoring:avmonitoring` (750) |
| `/var/log/avmonitoring/` | Logs de l'application | `avmonitoring:avmonitoring` (750) |
| `/etc/systemd/system/avmonitoring-agent.service` | Service systemd | `root:root` (644) |

---

## 🔧 Gestion du service

### Commandes de base
```bash
# Démarrer le service
sudo systemctl start avmonitoring-agent

# Arrêter le service
sudo systemctl stop avmonitoring-agent

# Redémarrer le service
sudo systemctl restart avmonitoring-agent

# Voir le statut
sudo systemctl status avmonitoring-agent

# Activer au démarrage (déjà fait par le script d'installation)
sudo systemctl enable avmonitoring-agent

# Désactiver au démarrage
sudo systemctl disable avmonitoring-agent
```

### Consulter les logs
```bash
# Logs en temps réel
sudo journalctl -u avmonitoring-agent -f

# Logs des 100 dernières lignes
sudo journalctl -u avmonitoring-agent -n 100

# Logs depuis aujourd'hui
sudo journalctl -u avmonitoring-agent --since today

# Logs d'une période spécifique
sudo journalctl -u avmonitoring-agent --since "2024-01-18 10:00" --until "2024-01-18 11:00"
```

---

## ⚙️ Configuration détaillée

### Fichier de configuration
Le fichier `/etc/avmonitoring/config.json` contient tous les paramètres de l'agent.

```json
{
  "site_name": "site-demo",
  "site_token": "VOTRE_TOKEN_BACKEND",
  "backend_url": "https://monitoring.example.com",
  "timezone": "Europe/Paris",
  "doubt_after_days": 2,
  "reporting": {
    "ok_interval_s": 300,
    "ko_interval_s": 60
  },
  "devices": []
}
```

#### Paramètres

| Paramètre | Type | Description | Valeur par défaut |
|-----------|------|-------------|-------------------|
| `site_name` | string | Nom du site (identifiant) | Obligatoire |
| `site_token` | string | Token d'authentification backend | Obligatoire |
| `backend_url` | string | URL du backend (HTTPS) | Obligatoire |
| `timezone` | string | Fuseau horaire | `"Europe/Paris"` |
| `doubt_after_days` | int | Jours avant statut "doubt" | `2` |
| `reporting.ok_interval_s` | int | Intervalle de reporting si tout va bien (secondes) | `300` (5 min) |
| `reporting.ko_interval_s` | int | Intervalle de reporting en cas d'erreur (secondes) | `60` (1 min) |
| `devices` | array | Liste des équipements (gérée automatiquement) | `[]` |

### Modification de la configuration

Après modification du fichier de configuration :
```bash
# Redémarrer le service pour prendre en compte les changements
sudo systemctl restart avmonitoring-agent
```

---

## 🌐 Accès à l'interface web locale

L'agent expose une interface web locale sur le port **8080** :
- URL : `http://localhost:8080`
- Accessible uniquement depuis la machine locale
- Permet de :
  - Visualiser l'état des équipements
  - Ajouter/modifier/supprimer des équipements
  - Voir les métriques en temps réel

---

## 🔒 Sécurité

### Utilisateur système dédié
L'agent s'exécute avec un utilisateur système dédié `avmonitoring` :
- Pas de shell de connexion (`/usr/sbin/nologin`)
- Pas de répertoire home
- Privilèges limités aux répertoires de l'application

### Mesures de sécurité systemd
Le service systemd applique plusieurs restrictions :
- `NoNewPrivileges=true` : Empêche l'élévation de privilèges
- `PrivateTmp=true` : Répertoire /tmp isolé
- `ProtectSystem=strict` : Système de fichiers en lecture seule
- `ProtectHome=true` : Répertoires utilisateurs inaccessibles

### Fichiers sensibles
Le fichier de configuration contient le token d'authentification :
- Permissions : `640` (lecture/écriture propriétaire, lecture groupe uniquement)
- Propriétaire : `avmonitoring:avmonitoring`
- **Ne jamais commiter ce fichier dans un dépôt Git**

---

## 🔄 Mise à jour

### Mise à jour du code
```bash
# 1. Arrêter le service
sudo systemctl stop avmonitoring-agent

# 2. Sauvegarder la configuration
sudo cp /etc/avmonitoring/config.json /etc/avmonitoring/config.json.backup

# 3. Télécharger la nouvelle version
cd /tmp
git clone https://github.com/CedricNCoding/av-monitoring-mvp.git
# ou décompresser l'archive

# 4. Copier le nouveau code
sudo cp -r /tmp/av-monitoring-mvp/agent/src/* /opt/avmonitoring-agent/src/

# 5. Mettre à jour les dépendances
sudo /opt/avmonitoring-agent/venv/bin/pip install -r /tmp/av-monitoring-mvp/agent/requirements.txt

# 6. Restaurer la configuration
sudo cp /etc/avmonitoring/config.json.backup /etc/avmonitoring/config.json

# 7. Redémarrer le service
sudo systemctl start avmonitoring-agent

# 8. Vérifier le fonctionnement
sudo systemctl status avmonitoring-agent
```

---

## 🗑️ Désinstallation

### Désinstallation complète
```bash
cd scripts
sudo ./uninstall.sh
```

Le script va :
- Arrêter et désactiver le service
- Supprimer le code de l'application
- Supprimer l'utilisateur système
- Vous proposer de conserver ou supprimer les données

### Désinstallation manuelle
Si le script de désinstallation n'est pas disponible :
```bash
# Arrêter et désactiver le service
sudo systemctl stop avmonitoring-agent
sudo systemctl disable avmonitoring-agent

# Supprimer le service systemd
sudo rm /etc/systemd/system/avmonitoring-agent.service
sudo systemctl daemon-reload

# Supprimer les fichiers
sudo rm -rf /opt/avmonitoring-agent

# Supprimer l'utilisateur
sudo userdel avmonitoring

# (Optionnel) Supprimer les données
sudo rm -rf /etc/avmonitoring
sudo rm -rf /var/lib/avmonitoring
sudo rm -rf /var/log/avmonitoring
```

---

## 🐛 Dépannage

### Le service ne démarre pas

**Vérifier les logs** :
```bash
sudo journalctl -u avmonitoring-agent -n 50
```

**Erreurs courantes** :

1. **Python introuvable**
   ```
   Erreur : python3: command not found
   Solution : sudo apt install python3
   ```

2. **Dépendances manquantes**
   ```
   Erreur : ModuleNotFoundError: No module named 'fastapi'
   Solution : sudo /opt/avmonitoring-agent/venv/bin/pip install -r requirements.txt
   ```

3. **Fichier de configuration invalide**
   ```
   Erreur : JSONDecodeError
   Solution : Vérifier la syntaxe JSON dans /etc/avmonitoring/config.json
   ```

4. **Problème de permissions**
   ```bash
   sudo chown -R avmonitoring:avmonitoring /opt/avmonitoring-agent
   sudo chown -R avmonitoring:avmonitoring /etc/avmonitoring
   sudo chown -R avmonitoring:avmonitoring /var/lib/avmonitoring
   ```

### Le service se relance en boucle

Consulter les logs pour identifier la cause :
```bash
sudo journalctl -u avmonitoring-agent -f
```

### L'agent ne communique pas avec le backend

1. **Vérifier la connectivité** :
   ```bash
   curl https://votre-backend.example.com/config/VOTRE_TOKEN
   ```

2. **Vérifier le token** :
   - Le token dans `/etc/avmonitoring/config.json` doit correspondre à celui du backend
   - Le token ne doit pas être le token par défaut `"CHANGE_ME_AFTER_INSTALL"`

3. **Vérifier les logs** :
   ```bash
   sudo journalctl -u avmonitoring-agent | grep -i error
   ```

---

## 📊 Surveillance

### Vérifier que le service fonctionne
```bash
# Status du service
sudo systemctl is-active avmonitoring-agent

# Vérifier qu'il répond sur le port 8080
curl -s http://localhost:8080 | head -n 10
```

### Intégration avec un système de monitoring

Le service peut être surveillé via :
- **systemd** : `systemctl is-active avmonitoring-agent`
- **Logs** : Analyse des logs avec logrotate, rsyslog, etc.
- **HTTP** : Check de santé sur `http://localhost:8080`
- **Prometheus** : Métriques exposées par l'agent (si implémenté)

---

## 📝 Support

### Informations pour un ticket de support

Lorsque vous ouvrez un ticket, fournissez :
```bash
# Version Python
python3 --version

# Version de l'OS
cat /etc/os-release

# Status du service
sudo systemctl status avmonitoring-agent

# Logs récents
sudo journalctl -u avmonitoring-agent -n 100 --no-pager

# Configuration (en masquant le token)
sudo cat /etc/avmonitoring/config.json | sed 's/"site_token".*/"site_token": "***MASKED***",/'
```

---

## 🎯 Checklist d'installation pour DSI

- [ ] Python 3.10+ installé
- [ ] systemd disponible
- [ ] Script `install.sh` exécuté avec succès
- [ ] Fichier `/etc/avmonitoring/config.json` configuré avec le bon token
- [ ] Service `avmonitoring-agent` démarré
- [ ] Service `avmonitoring-agent` activé au boot
- [ ] Logs vérifiés : aucune erreur
- [ ] Interface web accessible sur `http://localhost:8080`
- [ ] Communication avec le backend vérifiée
- [ ] Documentation archivée pour référence future

---

## 📚 Ressources supplémentaires

- **Code source** : `/opt/avmonitoring-agent/src/`
- **Documentation API** : `http://localhost:8080/docs` (Swagger UI)
- **Logs systemd** : `sudo journalctl -u avmonitoring-agent`

---

**Installation réalisée avec succès ?** Le service devrait maintenant être opérationnel et redémarrer automatiquement au boot de la machine.
