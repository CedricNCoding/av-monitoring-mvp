# Guide de démarrage rapide - AV Monitoring Agent

> **Pour les administrateurs système pressés** 🚀

## Installation en 5 minutes

### 1. Prérequis (1 min)
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install -y python3 python3-pip python3-venv

# Vérifier la version Python (>= 3.10 requis)
python3 --version
```

### 2. Installation (2 min)
```bash
# Télécharger et décompresser
tar -xzf avmonitoring-agent-X.Y.Z.tar.gz
cd avmonitoring-agent/scripts

# Installer
sudo ./install.sh
```

### 3. Configuration (1 min)
```bash
# Éditer la configuration
sudo nano /etc/avmonitoring/config.json
```

**Modifiez ces 3 lignes** :
```json
{
  "site_name": "mon-site",
  "site_token": "COLLER_LE_TOKEN_ICI",
  "backend_url": "https://monitoring.example.com"
}
```

> 💡 Le token se récupère depuis l'interface backend lors de la création du site

### 4. Démarrage (1 min)
```bash
# Démarrer
sudo systemctl start avmonitoring-agent

# Vérifier
sudo systemctl status avmonitoring-agent
```

✅ **C'est tout !** L'agent est opérationnel.

---

## Vérification rapide

```bash
# Tout vérifier en une commande
cd scripts
sudo ./check-install.sh
```

---

## Accès à l'interface

- **URL** : http://localhost:8080
- **Accessible** : Uniquement depuis le serveur local
- **Permet** : Ajouter/modifier des équipements, voir les métriques

---

## Commandes essentielles

| Action | Commande |
|--------|----------|
| Démarrer | `sudo systemctl start avmonitoring-agent` |
| Arrêter | `sudo systemctl stop avmonitoring-agent` |
| Redémarrer | `sudo systemctl restart avmonitoring-agent` |
| Statut | `sudo systemctl status avmonitoring-agent` |
| Logs temps réel | `sudo journalctl -u avmonitoring-agent -f` |
| Vérifier l'installation | `cd scripts && sudo ./check-install.sh` |

---

## En cas de problème

### Le service ne démarre pas
```bash
# Voir les logs
sudo journalctl -u avmonitoring-agent -n 50

# Corriger les permissions
sudo chown -R avmonitoring:avmonitoring /opt/avmonitoring-agent
sudo chown -R avmonitoring:avmonitoring /etc/avmonitoring
```

### Erreur de connexion au backend
```bash
# Tester la connectivité
curl https://votre-backend.example.com

# Vérifier le token dans la config
sudo cat /etc/avmonitoring/config.json | grep site_token
```

### Le token n'est pas accepté
1. Vérifier qu'il correspond exactement au token du backend (pas d'espace)
2. Redémarrer le service : `sudo systemctl restart avmonitoring-agent`

---

## Structure des fichiers

```
/opt/avmonitoring-agent/     → Code de l'application
/etc/avmonitoring/           → Configuration (éditable)
/var/lib/avmonitoring/       → Données
/var/log/avmonitoring/       → Logs
```

---

## Documentation complète

👉 Consultez [INSTALLATION.md](./INSTALLATION.md) pour :
- Configuration avancée
- Sécurité
- Mise à jour
- Désinstallation
- Dépannage détaillé

---

## Checklist post-installation

- [ ] Service démarré : `systemctl status avmonitoring-agent` → `active (running)`
- [ ] Interface accessible : `curl -s http://localhost:8080 | head`
- [ ] Pas d'erreur dans les logs : `journalctl -u avmonitoring-agent | grep -i error`
- [ ] Communication backend OK : vérifier les logs de sync
- [ ] Équipements ajoutés via l'interface web

**✓ Installation réussie !**

---

## Support rapide

**Informations à fournir** en cas de problème :
```bash
# Collecter les infos système
python3 --version
cat /etc/os-release | grep PRETTY_NAME
systemctl status avmonitoring-agent
sudo journalctl -u avmonitoring-agent -n 30 --no-pager
```

---

**Temps total d'installation : ~5 minutes** ⏱️
