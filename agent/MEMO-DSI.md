# Mémo pour la DSI - AV Monitoring Agent

> **Document de synthèse pour validation d'installation en production**

## 📋 Résumé exécutif

L'agent AV Monitoring est une application Python qui surveille des équipements audiovisuels et remonte les métriques à un backend centralisé. Elle s'installe **comme un service système natif** sur Linux, **sans Docker**, avec un processus d'installation automatisé et sécurisé.

**Engagement qualité** :
- ✅ Installation en < 5 minutes
- ✅ Aucune interaction Docker/orchestrateur
- ✅ Démarrage automatique au boot
- ✅ Pas de dépendance au backend pour fonctionner
- ✅ Supervision via systemd
- ✅ Logs centralisés (journald)

---

## 🎯 Points clés pour la DSI

### Prérequis système
| Élément | Requis | Disponible sur |
|---------|--------|----------------|
| OS | Linux (systemd) | Ubuntu 20.04+, Debian 11+ |
| Python | 3.10+ | Installé par défaut |
| Init system | systemd | Standard sur Ubuntu/Debian |
| Accès root | Oui (installation uniquement) | - |
| Réseau sortant | HTTPS (443) | Vers le backend |

### Empreinte système
| Ressource | Consommation typique |
|-----------|---------------------|
| CPU | < 5% idle, < 20% peak |
| RAM | 50-100 MB |
| Disque (code) | < 10 MB |
| Disque (logs 30j) | < 100 MB |
| Réseau | < 1 KB/s moyen |

### Sécurité
- ✅ **Utilisateur dédié non privilégié** (`avmonitoring`)
- ✅ **Pas d'exécution root** (service systemd avec User=avmonitoring)
- ✅ **Isolation systemd** (NoNewPrivileges, ProtectSystem, ProtectHome)
- ✅ **Pas de port exposé** (interface web localhost:8080 uniquement)
- ✅ **Token sécurisé** (permissions 640 sur config.json)
- ✅ **Communications chiffrées** (HTTPS uniquement vers backend)

---

## 📦 Installation (pour un administrateur)

### Option A : Installation guidée (recommandée)
```bash
# 1. Décompresser l'archive
tar -xzf avmonitoring-agent-1.0.0.tar.gz
cd avmonitoring-agent/scripts

# 2. Installer
sudo ./install.sh

# 3. Configurer (éditer 3 lignes)
sudo nano /etc/avmonitoring/config.json

# 4. Démarrer
sudo systemctl start avmonitoring-agent

# 5. Vérifier
sudo ./check-install.sh
```

**Temps total : 5 minutes**

### Option B : Installation en une commande
```bash
curl -fsSL https://votre-serveur.com/install.sh | sudo bash
```

---

## 🗂️ Arborescence installée

```
/opt/avmonitoring-agent/        → Application (lecture seule)
├── src/                        → Code Python
└── venv/                       → Environnement virtuel

/etc/avmonitoring/              → Configuration
└── config.json                 → Fichier de config (640, sensible)

/var/lib/avmonitoring/          → Données runtime
/var/log/avmonitoring/          → Logs applicatifs (optionnel)

/etc/systemd/system/            → Service
└── avmonitoring-agent.service  → Unit systemd
```

**Propriétaire** : `avmonitoring:avmonitoring` (utilisateur système)

---

## 🔧 Opérations courantes

### Gestion du service
```bash
systemctl start avmonitoring-agent    # Démarrer
systemctl stop avmonitoring-agent     # Arrêter
systemctl restart avmonitoring-agent  # Redémarrer
systemctl status avmonitoring-agent   # Statut
```

### Consultation des logs
```bash
journalctl -u avmonitoring-agent -f           # Temps réel
journalctl -u avmonitoring-agent -n 100       # 100 dernières lignes
journalctl -u avmonitoring-agent --since today # Depuis aujourd'hui
```

### Modification de la configuration
```bash
# Éditer
sudo nano /etc/avmonitoring/config.json

# Appliquer
sudo systemctl restart avmonitoring-agent
```

### Vérification de santé
```bash
# Status service
systemctl is-active avmonitoring-agent

# Interface web (local)
curl -s http://localhost:8080 | head

# Script de vérification complet
cd /opt/avmonitoring-agent/../scripts
sudo ./check-install.sh
```

---

## 📊 Supervision

### Indicateurs à monitorer
1. **Service actif** : `systemctl is-active avmonitoring-agent` → doit retourner `active`
2. **Logs d'erreur** : `journalctl -u avmonitoring-agent | grep -c ERROR` → doit être proche de 0
3. **Connectivité backend** : Vérifier dans les logs "sync OK"
4. **Port 8080** : `ss -tuln | grep 8080` → doit montrer un listener

### Alertes recommandées
- ⚠️ Service down (systemctl is-active → inactive)
- ⚠️ Trop d'erreurs dans les logs (> 10 sur 5 min)
- ⚠️ Pas de sync backend depuis > 10 min

### Intégration avec outils existants
- **Nagios/Icinga** : Check `systemctl is-active`
- **Prometheus** : Métriques exportées par l'agent (TODO)
- **Centreon** : Plugin systemd standard
- **ELK/Splunk** : Ingestion depuis journald

---

## 🔐 Aspects sécurité pour audit

### Conformité
- ✅ Principe du moindre privilège (utilisateur non-root)
- ✅ Pas d'élévation de privilèges (NoNewPrivileges)
- ✅ Système de fichiers protégé (ProtectSystem=strict)
- ✅ Isolation des données (PrivateTmp)
- ✅ Communications chiffrées (HTTPS/TLS)
- ✅ Authentification par token (pas de mot de passe)

### Données sensibles
| Donnée | Emplacement | Protection |
|--------|-------------|------------|
| Token d'authentification | `/etc/avmonitoring/config.json` | Permissions 640, propriétaire avmonitoring |
| Logs | journald | Permissions système standard |
| Métriques | RAM (pas de stockage disque) | - |

### Flux réseau
- **Sortant** : HTTPS vers backend (port 443)
- **Entrant** : Aucun (interface web localhost uniquement)

### Surface d'attaque
- Minimale : aucun port exposé au réseau
- Interface web accessible uniquement en local (127.0.0.1:8080)
- Pas de services privileged

---

## 🚨 Procédures d'incident

### Le service ne démarre pas
```bash
# 1. Consulter les logs
sudo journalctl -u avmonitoring-agent -n 50

# 2. Vérifier la configuration
sudo python3 -c "import json; json.load(open('/etc/avmonitoring/config.json'))"

# 3. Vérifier les permissions
sudo chown -R avmonitoring:avmonitoring /opt/avmonitoring-agent
sudo chown -R avmonitoring:avmonitoring /etc/avmonitoring

# 4. Tenter un redémarrage
sudo systemctl restart avmonitoring-agent
```

### Le service redémarre en boucle
```bash
# Consulter les logs en temps réel
sudo journalctl -u avmonitoring-agent -f

# Identifier l'erreur récurrente
sudo journalctl -u avmonitoring-agent | grep ERROR | tail -20

# Désactiver temporairement si critique
sudo systemctl stop avmonitoring-agent
sudo systemctl disable avmonitoring-agent
```

### Perte de connectivité backend
- L'agent continue à fonctionner normalement avec sa config locale
- Il tentera de se reconnecter automatiquement
- Pas d'intervention nécessaire (résilient par design)

---

## 🔄 Mise à jour

### Procédure standard
```bash
# 1. Télécharger la nouvelle version
wget https://releases.example.com/avmonitoring-agent-1.1.0.tar.gz

# 2. Vérifier l'intégrité
sha256sum -c avmonitoring-agent-1.1.0.tar.gz.sha256

# 3. Arrêter le service
sudo systemctl stop avmonitoring-agent

# 4. Sauvegarder la configuration
sudo cp /etc/avmonitoring/config.json /etc/avmonitoring/config.json.backup

# 5. Extraire et copier les nouveaux fichiers
tar -xzf avmonitoring-agent-1.1.0.tar.gz
sudo cp -r avmonitoring-agent/src/* /opt/avmonitoring-agent/src/

# 6. Mettre à jour les dépendances
sudo /opt/avmonitoring-agent/venv/bin/pip install -r avmonitoring-agent/requirements.txt

# 7. Redémarrer
sudo systemctl start avmonitoring-agent

# 8. Vérifier
sudo systemctl status avmonitoring-agent
```

### Rollback en cas de problème
```bash
# Restaurer l'ancienne version depuis sauvegarde
# (documentation complète dans INSTALLATION.md)
```

---

## 🗑️ Désinstallation

### Désinstallation propre
```bash
cd /opt/avmonitoring-agent/../scripts
sudo ./uninstall.sh
```

Le script propose de conserver ou supprimer les données/config.

### Désinstallation manuelle (fallback)
```bash
sudo systemctl stop avmonitoring-agent
sudo systemctl disable avmonitoring-agent
sudo rm /etc/systemd/system/avmonitoring-agent.service
sudo systemctl daemon-reload
sudo rm -rf /opt/avmonitoring-agent
sudo userdel avmonitoring
# Optionnel : sudo rm -rf /etc/avmonitoring /var/lib/avmonitoring /var/log/avmonitoring
```

---

## 📞 Support et documentation

### Documentation disponible
- [INSTALLATION.md](./INSTALLATION.md) - Guide d'installation détaillé
- [QUICKSTART.md](./QUICKSTART.md) - Démarrage rapide 5 min
- [ARCHITECTURE.md](./ARCHITECTURE.md) - Architecture technique
- [CHANGELOG.md](./CHANGELOG.md) - Historique des versions

### Scripts fournis
- `install.sh` - Installation automatique
- `uninstall.sh` - Désinstallation propre
- `check-install.sh` - Vérification post-installation
- `create-release.sh` - Création d'archives de distribution

### Contact support
En cas de problème, fournir :
```bash
# Collecter les infos
python3 --version
cat /etc/os-release | grep PRETTY_NAME
systemctl status avmonitoring-agent
sudo journalctl -u avmonitoring-agent -n 50 --no-pager
sudo cat /etc/avmonitoring/config.json | sed 's/"site_token".*/"site_token": "***MASKED***",/'
```

---

## ✅ Checklist de validation DSI

Avant mise en production :

- [ ] Prérequis système vérifiés (Python 3.10+, systemd)
- [ ] Installation testée sur environnement de qualification
- [ ] Script `check-install.sh` exécuté avec succès
- [ ] Service démarre et redémarre automatiquement
- [ ] Logs consultables via journald
- [ ] Configuration sécurisée (permissions 640)
- [ ] Aucun port exposé au réseau (vérification netstat/ss)
- [ ] Communication backend fonctionnelle (HTTPS)
- [ ] Supervision mise en place (alertes service down)
- [ ] Procédure de sauvegarde définie (config.json)
- [ ] Procédure de mise à jour documentée
- [ ] Procédure de rollback testée
- [ ] Documentation archivée pour l'équipe d'exploitation

---

## 💼 Engagement de support

- Installation en < 5 minutes
- Aucune dépendance Docker/Kubernetes
- Compatibilité garantie Ubuntu 20.04+ et Debian 11+
- Pas de modification système invasive
- Désinstallation propre sans résidus

**Cette solution respecte les standards d'exploitation IT classiques et s'intègre dans un environnement de production traditionnel.**

---

**Date du document** : 2024-01-18
**Version agent** : 1.0.0
**Cible** : Ubuntu 20.04+, Debian 11+
