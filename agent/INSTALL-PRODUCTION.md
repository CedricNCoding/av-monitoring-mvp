# Installation en production - Agent AV Monitoring

> **Guide d'installation sur Debian/Ubuntu vierge (sans dépendances préinstallées)**

## 🎯 Objectif

Installer l'agent AV Monitoring sur une machine Linux de production **sans Docker**, de manière **automatisée**, **reproductible** et **maintenable**.

## 📋 Prérequis système

### Machine cible
- **OS** : Debian 11+, Ubuntu 20.04+ ou compatible
- **systemd** : Requis
- **Accès root** : Nécessaire pour l'installation
- **Réseau** : Accès sortant HTTPS (port 443) vers le backend

### Ce qui est installé automatiquement
Le script d'installation installe **automatiquement** tout ce qui est nécessaire :
- ✅ Python 3 (si absent)
- ✅ python3-venv (pour l'environnement virtuel)
- ✅ python3-pip (gestionnaire de paquets Python)
- ✅ iputils-ping (commande ping)
- ✅ ca-certificates (certificats SSL/TLS)
- ✅ libcap2-bin (pour setcap)

**Aucune préparation manuelle n'est nécessaire !**

---

## 🚀 Installation

### Étape 1 : Obtenir le code source

**Option A** : Depuis une archive (recommandé pour production)
```bash
# Télécharger l'archive
wget https://releases.example.com/avmonitoring-agent-1.0.0.tar.gz

# Vérifier l'intégrité (optionnel mais recommandé)
sha256sum -c avmonitoring-agent-1.0.0.tar.gz.sha256

# Décompresser
tar -xzf avmonitoring-agent-1.0.0.tar.gz
cd avmonitoring-agent
```

**Option B** : Depuis Git (environnement de test uniquement)
```bash
git clone https://github.com/votre-org/av-monitoring-mvp.git
cd av-monitoring-mvp/agent
```

### Étape 2 : Lancer l'installation

```bash
cd scripts
sudo ./install.sh
```

### Ce que fait le script

Le script d'installation est **complètement automatisé** et effectue les opérations suivantes :

1. ✅ **Vérifie les prérequis** (systemd, gestionnaire de paquets)
2. ✅ **Installe les dépendances système** (Python, venv, pip, ping, ca-certificates, setcap)
3. ✅ **Crée l'utilisateur système** `avmonitoring` (sans shell, non privilégié)
4. ✅ **Crée les répertoires** nécessaires
5. ✅ **Copie le code source** vers `/opt/avmonitoring-agent`
6. ✅ **Crée un virtualenv Python** et installe les dépendances
7. ✅ **Crée la configuration initiale** (si absente)
8. ✅ **Configure les permissions** de sécurité
9. ✅ **Configure cap_net_raw** pour ping (si nécessaire)
10. ✅ **Installe le fichier d'environnement** système
11. ✅ **Installe le service systemd**
12. ✅ **Active le service** pour démarrage automatique

**Le script est idempotent** : vous pouvez le relancer sans risque.

### Étape 3 : Configurer l'agent

```bash
sudo nano /etc/avmonitoring/config.json
```

**Modifiez ces 3 paramètres obligatoires** :
```json
{
  "site_name": "mon-site-production",
  "site_token": "COLLER_LE_TOKEN_DU_BACKEND_ICI",
  "backend_url": "https://avmonitoring.example.com"
}
```

> 💡 Le token `site_token` est fourni par le backend lors de la création du site.

### Étape 4 : Démarrer le service

```bash
sudo systemctl start avmonitoring-agent
```

### Étape 5 : Vérifier le fonctionnement

```bash
# Vérifier le statut
sudo systemctl status avmonitoring-agent

# Consulter les logs
sudo journalctl -u avmonitoring-agent -f

# Vérification complète (optionnel)
sudo ./check-install.sh
```

**L'interface web** est accessible sur : `http://localhost:8080`

---

## 📂 Architecture installée

### Chemins des fichiers

| Composant | Chemin | Propriétaire | Permissions |
|-----------|--------|--------------|-------------|
| **Code source** | `/opt/avmonitoring-agent/` | avmonitoring:avmonitoring | 750 |
| **Virtualenv Python** | `/opt/avmonitoring-agent/venv/` | avmonitoring:avmonitoring | 750 |
| **Configuration** | `/etc/avmonitoring/config.json` | avmonitoring:avmonitoring | 640 |
| **Variables d'env** | `/etc/default/avmonitoring-agent` | root:root | 644 |
| **Données runtime** | `/var/lib/avmonitoring/` | avmonitoring:avmonitoring | 750 |
| **Logs** | `/var/log/avmonitoring/` | avmonitoring:avmonitoring | 750 |
| **Service systemd** | `/etc/systemd/system/avmonitoring-agent.service` | root:root | 644 |

### Variables d'environnement système

Le fichier `/etc/default/avmonitoring-agent` contient :

```bash
# Python path (requis pour les imports)
PYTHONPATH=/opt/avmonitoring-agent

# Chemin du fichier de configuration
AGENT_CONFIG=/etc/avmonitoring/config.json

# Intervalle de synchronisation avec le backend (en minutes)
CONFIG_SYNC_INTERVAL_MIN=5
```

Ces variables sont chargées automatiquement par systemd au démarrage du service.

---

## 🔧 Gestion du service

### Commandes de base

```bash
# Démarrer
sudo systemctl start avmonitoring-agent

# Arrêter
sudo systemctl stop avmonitoring-agent

# Redémarrer
sudo systemctl restart avmonitoring-agent

# Voir le statut
sudo systemctl status avmonitoring-agent

# Activer au démarrage (déjà fait par install.sh)
sudo systemctl enable avmonitoring-agent

# Désactiver au démarrage
sudo systemctl disable avmonitoring-agent
```

### Consulter les logs

```bash
# Logs en temps réel
sudo journalctl -u avmonitoring-agent -f

# 100 dernières lignes
sudo journalctl -u avmonitoring-agent -n 100

# Logs depuis aujourd'hui
sudo journalctl -u avmonitoring-agent --since today

# Filtrer les erreurs
sudo journalctl -u avmonitoring-agent | grep -i error
```

---

## 🔒 Sécurité

### Utilisateur système dédié

L'agent s'exécute avec un utilisateur système **non privilégié** :
- **Nom** : `avmonitoring`
- **Shell** : `/usr/sbin/nologin` (pas de connexion interactive)
- **Home** : Aucun
- **Groupe** : `avmonitoring`

### Mesures de sécurité systemd

Le service applique les restrictions suivantes :
```ini
NoNewPrivileges=true        # Pas d'élévation de privilèges
PrivateTmp=true             # Répertoire /tmp isolé
ProtectSystem=strict        # Système de fichiers en lecture seule
ProtectHome=true            # Répertoires utilisateurs inaccessibles
```

### Ping ICMP sans root

Le ping fonctionne sans privilèges root grâce à la capacité `cap_net_raw` :
```bash
# Vérifier la configuration
getcap /bin/ping
# Doit afficher : /bin/ping cap_net_raw=ep
```

Ceci est configuré automatiquement par le script d'installation.

---

## 🔄 Mise à jour

### Mise à jour du code

```bash
# 1. Arrêter le service
sudo systemctl stop avmonitoring-agent

# 2. Sauvegarder la configuration
sudo cp /etc/avmonitoring/config.json /etc/avmonitoring/config.json.backup

# 3. Décompresser la nouvelle version
tar -xzf avmonitoring-agent-1.1.0.tar.gz
cd avmonitoring-agent

# 4. Copier le nouveau code
sudo cp -r src/* /opt/avmonitoring-agent/src/

# 5. Mettre à jour les dépendances Python
sudo /opt/avmonitoring-agent/venv/bin/pip install -r requirements.txt

# 6. Redémarrer
sudo systemctl start avmonitoring-agent

# 7. Vérifier
sudo systemctl status avmonitoring-agent
```

### Mise à jour de la configuration

```bash
# Éditer
sudo nano /etc/avmonitoring/config.json

# Appliquer
sudo systemctl restart avmonitoring-agent
```

**Note** : La configuration n'est jamais écrasée lors d'une réinstallation.

---

## 🗑️ Désinstallation

### Désinstallation automatique

```bash
cd /opt/avmonitoring-agent/../scripts
sudo ./uninstall.sh
```

Le script propose de conserver ou supprimer les données et la configuration.

### Désinstallation manuelle

```bash
# Arrêter et désactiver
sudo systemctl stop avmonitoring-agent
sudo systemctl disable avmonitoring-agent

# Supprimer les fichiers systemd
sudo rm /etc/systemd/system/avmonitoring-agent.service
sudo rm /etc/default/avmonitoring-agent
sudo systemctl daemon-reload

# Supprimer le code
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

1. **Configuration invalide**
   ```bash
   # Vérifier la syntaxe JSON
   sudo python3 -c "import json; json.load(open('/etc/avmonitoring/config.json'))"
   ```

2. **Problème de permissions**
   ```bash
   sudo chown -R avmonitoring:avmonitoring /opt/avmonitoring-agent
   sudo chown -R avmonitoring:avmonitoring /etc/avmonitoring
   sudo chmod 640 /etc/avmonitoring/config.json
   ```

3. **Dépendances manquantes**
   ```bash
   sudo /opt/avmonitoring-agent/venv/bin/pip install -r /opt/avmonitoring-agent/../requirements.txt
   ```

### Le ping ne fonctionne pas

```bash
# Vérifier cap_net_raw
getcap /bin/ping

# Si absent, appliquer manuellement
sudo setcap cap_net_raw+ep /bin/ping
```

### L'agent ne communique pas avec le backend

1. **Vérifier la connectivité** :
   ```bash
   curl -v https://votre-backend.example.com
   ```

2. **Vérifier le token** :
   ```bash
   sudo grep site_token /etc/avmonitoring/config.json
   ```

3. **Vérifier les logs** :
   ```bash
   sudo journalctl -u avmonitoring-agent | grep -i "sync\|backend"
   ```

---

## 📊 Vérification de santé

### Script de vérification automatique

```bash
cd /opt/avmonitoring-agent/../scripts
sudo ./check-install.sh
```

Ce script vérifie :
- ✅ Prérequis système (Python, systemd)
- ✅ Fichiers installés
- ✅ Service actif
- ✅ Permissions correctes
- ✅ Configuration valide
- ✅ Connectivité backend

### Vérifications manuelles

```bash
# Service actif ?
systemctl is-active avmonitoring-agent

# Interface web accessible ?
curl -s http://localhost:8080 | head

# Ping fonctionne ?
su - avmonitoring -s /bin/sh -c "ping -c 1 8.8.8.8"

# Variables d'environnement chargées ?
sudo systemctl show avmonitoring-agent | grep Environment
```

---

## 🎯 Checklist post-installation

- [ ] Script `install.sh` exécuté sans erreur
- [ ] Configuration éditée (`site_token`, `backend_url`, `site_name`)
- [ ] Service démarré : `systemctl status avmonitoring-agent` → `active (running)`
- [ ] Pas d'erreur dans les logs : `journalctl -u avmonitoring-agent | grep -i error`
- [ ] Interface web accessible : `curl http://localhost:8080`
- [ ] Communication backend OK (vérifier dans les logs)
- [ ] Script de vérification OK : `./check-install.sh`

**✅ Installation réussie !**

---

## 📚 Documentation complémentaire

- **Guide complet** : [INSTALLATION.md](./INSTALLATION.md)
- **Guide rapide** : [QUICKSTART.md](./QUICKSTART.md)
- **Architecture** : [ARCHITECTURE.md](./ARCHITECTURE.md)
- **DSI** : [MEMO-DSI.md](./MEMO-DSI.md)

---

## 💡 Points clés pour la production

### ✅ Ce qui est automatique
- Installation des dépendances système
- Création de l'utilisateur et des répertoires
- Configuration du virtualenv Python
- Installation du service systemd
- Configuration de la sécurité (permissions, capabilities)

### ⚙️ Ce qui est manuel
- Édition de la configuration (3 lignes à modifier)
- Démarrage du service (1 commande)

### 🔒 Sécurité
- Exécution non-root (utilisateur `avmonitoring`)
- Isolation systemd (NoNewPrivileges, ProtectSystem)
- Pas de port exposé (interface localhost uniquement)
- Token sécurisé (permissions 640)

### 📊 Exploitation
- Logs centralisés (journald)
- Supervision via systemd
- Démarrage automatique au boot
- Redémarrage automatique en cas d'échec

---

**L'agent est prêt pour la production. Aucune dépendance Docker, aucun bricolage post-installation.**
