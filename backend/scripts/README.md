# Scripts Backend AV Monitoring

Scripts d'administration pour le backend AV Monitoring.

## 📋 Scripts disponibles

### `install.sh` - Installation du backend

Installation complète du backend sur un système Ubuntu/Debian.

**Utilisation :**
```bash
cd backend/scripts
sudo ./install.sh
```

**Actions effectuées :**
- Installation de Python 3, PostgreSQL, Git
- Création de l'utilisateur système `avmvp`
- Configuration de la base de données PostgreSQL
- Installation des dépendances Python
- Configuration du service systemd
- Démarrage automatique du service

**Prérequis :**
- Ubuntu 20.04+ ou Debian 11+
- Accès root

📖 **Documentation complète :** [Guide d'installation](../../docs/backend/INSTALLATION.md)

---

### `backup.sh` - Sauvegarde de la base de données

Créer un backup complet de la base de données PostgreSQL.

**Utilisation :**
```bash
# Backup dans le répertoire par défaut (/var/backups/avmonitoring)
sudo ./backup.sh

# Backup dans un répertoire personnalisé
sudo ./backup.sh /chemin/vers/backups
```

**Fonctionnalités :**
- ✅ Dump complet de la base de données
- ✅ Compression automatique (gzip)
- ✅ Nom de fichier horodaté (`avmvp_db_20260215_143000.sql.gz`)
- ✅ Nettoyage automatique (conserve 30 derniers jours)
- ✅ Permissions sécurisées (640, avmvp:avmvp)

**Sortie :**
```
/var/backups/avmonitoring/avmvp_db_20260215_143000.sql.gz
```

**Backup automatique avec cron :**
```bash
# Éditer la crontab
sudo crontab -e

# Ajouter : backup quotidien à 2h du matin
0 2 * * * /opt/avmonitoring-backend/backend/scripts/backup.sh
```

---

### `restore.sh` - Restauration de la base de données

Restaurer la base de données depuis un backup.

**⚠️ ATTENTION : Cette opération supprime toutes les données actuelles !**

**Utilisation :**
```bash
sudo ./restore.sh /chemin/vers/backup.sql.gz
```

**Exemple :**
```bash
# Lister les backups disponibles
ls -lh /var/backups/avmonitoring/

# Restaurer un backup spécifique
sudo ./restore.sh /var/backups/avmonitoring/avmvp_db_20260215_143000.sql.gz
```

**Actions effectuées :**
1. Arrêt du service backend
2. Suppression de la base de données actuelle
3. Création d'une nouvelle base vide
4. Import des données du backup
5. Redémarrage du service backend

**Confirmation requise :**
Le script demande de taper `oui` pour confirmer la restauration.

---

## 🔄 Scénarios d'utilisation

### Migration vers un nouveau serveur

**Sur l'ancien serveur :**
```bash
# Créer un backup
cd /opt/avmonitoring-backend/backend/scripts
sudo ./backup.sh

# Copier le backup vers le nouveau serveur
scp /var/backups/avmonitoring/avmvp_db_*.sql.gz root@nouveau-serveur:/tmp/
```

**Sur le nouveau serveur :**
```bash
# Installer le backend
cd /chemin/vers/av-monitoring-mvp/backend/scripts
sudo ./install.sh

# Configurer
sudo nano /etc/avmonitoring-backend/config.env

# Restaurer les données
sudo ./restore.sh /tmp/avmvp_db_*.sql.gz
```

---

### Restauration après erreur

```bash
# 1. Identifier le dernier backup valide
ls -lht /var/backups/avmonitoring/ | head -5

# 2. Restaurer
cd /opt/avmonitoring-backend/backend/scripts
sudo ./restore.sh /var/backups/avmonitoring/avmvp_db_20260215_020000.sql.gz

# 3. Vérifier
sudo systemctl status avmonitoring-backend
sudo journalctl -u avmonitoring-backend -n 20
```

---

### Test de restauration (bonne pratique)

```bash
# Tester régulièrement vos backups !

# 1. Créer un backup
sudo ./backup.sh /tmp/test-backup

# 2. Restaurer sur un serveur de test
# (Ne jamais tester sur la production)
scp /tmp/test-backup/avmvp_db_*.sql.gz test-server:/tmp/
ssh test-server "cd /opt/avmonitoring-backend/backend/scripts && sudo ./restore.sh /tmp/avmvp_db_*.sql.gz"

# 3. Vérifier l'intégrité des données restaurées
```

---

## 📂 Emplacements

| Élément | Chemin |
|---------|--------|
| Scripts | `/opt/avmonitoring-backend/backend/scripts/` |
| Backups par défaut | `/var/backups/avmonitoring/` |
| Configuration | `/etc/avmonitoring-backend/config.env` |
| Logs | `journalctl -u avmonitoring-backend` |

---

## 🔒 Sécurité

### Permissions des backups

Les backups sont créés avec des permissions restrictives :
- **Propriétaire** : `avmvp:avmvp`
- **Permissions** : `640` (rw-r-----)
- Seuls root et l'utilisateur avmvp peuvent lire

### Stockage sécurisé

**Recommandations :**
- ✅ Stocker les backups sur un volume séparé
- ✅ Chiffrer les backups contenant des données sensibles
- ✅ Copier les backups hors serveur (S3, NAS, etc.)
- ✅ Tester régulièrement les restaurations

**Exemple avec chiffrement GPG :**
```bash
# Créer un backup chiffré
sudo ./backup.sh /tmp/backup
gpg --symmetric --cipher-algo AES256 /tmp/backup/avmvp_db_*.sql.gz

# Copier vers stockage distant
aws s3 cp /tmp/backup/avmvp_db_*.sql.gz.gpg s3://mes-backups/
```

---

## 🆘 Dépannage

### Le backup échoue

```bash
# Vérifier que PostgreSQL fonctionne
sudo systemctl status postgresql

# Vérifier que la base existe
sudo -u postgres psql -l | grep avmvp_db

# Vérifier l'espace disque
df -h /var/backups
```

### La restauration échoue

```bash
# Vérifier le fichier de backup
gunzip -t /chemin/vers/backup.sql.gz

# Vérifier les logs PostgreSQL
sudo journalctl -u postgresql -n 50

# Vérifier les permissions
ls -l /chemin/vers/backup.sql.gz
```

### Le service ne redémarre pas après restauration

```bash
# Voir les logs détaillés
sudo journalctl -u avmonitoring-backend -n 100

# Vérifier la configuration
sudo nano /etc/avmonitoring-backend/config.env

# Redémarrer manuellement
sudo systemctl restart avmonitoring-backend
```

---

## 📊 Monitoring des backups

### Vérifier le dernier backup

```bash
# Date du dernier backup
ls -lt /var/backups/avmonitoring/ | head -2

# Taille des backups
du -sh /var/backups/avmonitoring/
```

### Script de vérification (alerting)

```bash
#!/bin/bash
# Vérifier qu'un backup a été créé dans les dernières 24h

BACKUP_DIR="/var/backups/avmonitoring"
LAST_BACKUP=$(find "$BACKUP_DIR" -name "avmvp_db_*.sql.gz" -type f -mtime -1 | wc -l)

if [ "$LAST_BACKUP" -eq 0 ]; then
    echo "ALERTE : Aucun backup dans les dernières 24h !"
    # Envoyer une notification (email, Slack, etc.)
fi
```

---

## 📚 Documentation

- **[Installation Backend](../../docs/backend/INSTALLATION.md)** - Guide d'installation complet
- **[Sécurité](../../docs/security/BACKEND.md)** - Mesures de sécurité
- **[README Backend](../README.md)** - Vue d'ensemble du backend

---

**Besoin d'aide ?** Consultez les logs : `sudo journalctl -u avmonitoring-backend -f`
