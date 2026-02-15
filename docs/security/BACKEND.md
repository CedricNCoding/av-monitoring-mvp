# Guide de sécurité AV Monitoring

Ce document décrit les mesures de sécurité mises en place pour le backend AV Monitoring.

## 📊 Niveau de sécurité actuel

**Niveau : Standard Pro (7/10)**

Adapté pour :
- ✅ PME et startups
- ✅ Données d'entreprise standard
- ✅ Infrastructure critique non-publique
- ✅ Déploiement professionnel

## 🛡️ Mesures de sécurité appliquées

### 1. Architecture en couches

```
Internet
   │
   ▼
┌─────────────────────────────────┐
│ Cloudflare Zero Trust           │  ← Authentification (optionnel)
│ - Authentification SSO          │
│ - Protection DDoS               │
│ - WAF (Web Application Firewall)│
└────────────┬────────────────────┘
             │ HTTPS
             ▼
┌─────────────────────────────────┐
│ Traefik (Reverse Proxy)         │  ← Terminaison SSL/TLS
│ - Certificats Let's Encrypt     │
│ - HTTPS uniquement              │
│ - Headers de sécurité           │
└────────────┬────────────────────┘
             │ HTTP localhost
             ▼
┌─────────────────────────────────┐
│ Backend FastAPI (systemd)       │  ← Application
│ - User non-root (avmvp)         │
│ - Écoute 127.0.0.1:8000         │
│ - Directives systemd hardening  │
└────────────┬────────────────────┘
             │ localhost
             ▼
┌─────────────────────────────────┐
│ PostgreSQL                      │  ← Base de données
│ - Écoute localhost uniquement   │
│ - Pas accessible Internet       │
│ - Utilisateur dédié             │
└─────────────────────────────────┘
```

### 2. Principe du moindre privilège

#### Service backend
- ✅ Tourne avec utilisateur `avmvp` (non-root)
- ✅ Pas de shell (`/bin/false`)
- ✅ Permissions limitées sur `/opt/av-monitoring-mvp`
- ✅ Directives systemd de sécurité activées :
  - `NoNewPrivileges=true` : Ne peut pas élever ses privilèges
  - `PrivateTmp=true` : Répertoire /tmp isolé
  - `ProtectSystem=strict` : Système de fichiers en lecture seule
  - `ProtectHome=true` : Pas d'accès aux répertoires home
  - `ReadWritePaths=/opt/av-monitoring-mvp/backend` : Écriture limitée

#### PostgreSQL
- ✅ Utilisateur dédié `avmvp_user`
- ✅ Permissions limitées à la base `avmvp_db`
- ✅ Écoute uniquement sur `localhost`

### 3. Isolation réseau

#### Backend
- ✅ Écoute UNIQUEMENT sur `127.0.0.1:8000`
- ✅ Pas accessible directement depuis Internet
- ✅ Accessible uniquement via Traefik (reverse proxy)

#### PostgreSQL
- ✅ `listen_addresses = 'localhost'`
- ✅ Port 5432 non exposé publiquement
- ✅ Communication locale uniquement

#### Firewall (ufw)
```bash
Port 22   (SSH)   : ✅ Ouvert
Port 80   (HTTP)  : ✅ Ouvert (redirection HTTPS)
Port 443  (HTTPS) : ✅ Ouvert (Traefik)
Port 8000 (Backend) : ❌ Fermé (localhost uniquement)
Port 5432 (PostgreSQL) : ❌ Fermé (localhost uniquement)
Tout le reste : ❌ Fermé par défaut
```

### 4. Chiffrement

#### En transit
- ✅ HTTPS obligatoire (Traefik + Let's Encrypt)
- ✅ TLS 1.2+ uniquement
- ✅ Ciphers sécurisés
- ✅ HSTS (HTTP Strict Transport Security) recommandé

#### Au repos
- ⚠️ Données en base PostgreSQL NON chiffrées
- ⚠️ `driver_config` contient mots de passe SNMP/PJLink en clair
- 📝 Recommandation : Chiffrer les champs sensibles si données très critiques

### 5. Authentification

#### Interface web et API (`/ui/*`, `/api/*`, `/admin/*`)
- ✅ Protection via Cloudflare Zero Trust (recommandé)
  - Authentification SSO (Google, GitHub, Email OTP, etc.)
  - 2FA supporté
  - Logs d'audit complets
- 📝 Alternative : BasicAuth Traefik (moins sécurisé)

#### Agents (`/ingest`, `/config/*`)
- ✅ Tokens uniques par site (générés via `secrets.token_urlsafe(32)`)
- ✅ Validation côté backend
- ✅ Header `X-Site-Token` ou token dans URL

### 6. Gestion des secrets

#### Variables d'environnement
```bash
# /opt/av-monitoring-mvp/backend/.env
DATABASE_URL=postgresql://avmvp_user:mot_de_passe_fort@localhost/avmvp_db
SESSION_SECRET=secret_genere_aleatoirement
```

- ✅ Fichier `.env` avec permissions `600` (lecture/écriture propriétaire uniquement)
- ✅ Propriétaire : `avmvp:avmvp`
- ⚠️ Secrets en clair dans le fichier (recommandation : utiliser un vault pour production critique)

#### Tokens agents
- ✅ Générés aléatoirement (32 bytes URL-safe)
- ✅ Stockés en base PostgreSQL
- ⚠️ Pas de rotation automatique
- 📝 Recommandation : Rotation manuelle régulière via `/admin/renew-token`

### 7. Protection contre les attaques

#### DDoS
- ✅ Cloudflare (si configuré) : Protection edge
- ✅ Traefik : Rate limiting possible
- 📝 Recommandation : Configurer rate limiting sur `/ingest`

#### Injection SQL
- ✅ SQLAlchemy ORM utilisé (paramétrage automatique)
- ✅ Pas de requêtes SQL brutes avec input utilisateur

#### XSS (Cross-Site Scripting)
- ✅ FastAPI échappe automatiquement les templates Jinja2
- ✅ Headers de sécurité (via Traefik)

#### CSRF (Cross-Site Request Forgery)
- ⚠️ Pas de protection CSRF actuellement
- 📝 Impact limité car authentification par tokens pour agents
- 📝 Recommandation : Ajouter CSRF tokens pour interface web si utilisation intensive

#### Directory Traversal
- ✅ Pas de lecture de fichiers basée sur input utilisateur

### 8. Logs et audit

#### Logs système
```bash
# Logs backend
journalctl -u avmonitoring-backend -f

# Logs PostgreSQL
/var/log/postgresql/postgresql-*.log
```

#### Logs applicatifs
- ✅ FastAPI logs les requêtes
- ✅ Timestamps UTC
- 📝 Recommandation : Centraliser les logs (Loki, Elasticsearch, etc.)

#### Logs d'accès (avec Cloudflare Zero Trust)
- ✅ Qui a accédé à quoi et quand
- ✅ Tentatives d'authentification échouées
- ✅ Géolocalisation des accès

### 9. Mises à jour de sécurité

#### Système
```bash
# Mises à jour automatiques (recommandé)
sudo apt install unattended-upgrades -y
sudo dpkg-reconfigure --priority=low unattended-upgrades
```

#### Dépendances Python
```bash
# Vérifier les vulnérabilités
pip install safety
safety check

# Mettre à jour
cd /opt/av-monitoring-mvp/backend
source venv/bin/activate
pip install --upgrade -r requirements.txt
sudo systemctl restart avmonitoring-backend
```

#### PostgreSQL
```bash
sudo apt update
sudo apt upgrade postgresql
```

### 10. Backups

#### Base de données
```bash
# Backup quotidien (cron)
0 2 * * * /usr/bin/pg_dump -U avmvp_user avmvp_db | gzip > /backups/avmvp_$(date +\%Y\%m\%d).sql.gz

# Rétention 30 jours
find /backups/avmvp_*.sql.gz -mtime +30 -delete
```

- 📝 Recommandation : Backup chiffré sur stockage distant

## 🚨 Points d'attention

### Risques résiduels

#### 🟡 Moyenne priorité

1. **Pas de chiffrement des données sensibles en DB**
   - `driver_config` contient mots de passe SNMP/PJLink en clair
   - **Mitigation** : PostgreSQL accessible uniquement en localhost
   - **Solution** : Chiffrer avec `cryptography.fernet`

2. **Pas de rotation automatique des tokens**
   - Tokens agents permanents
   - **Mitigation** : Tokens longs et aléatoires
   - **Solution** : Endpoint `/admin/renew-token` manuel

3. **Pas de RBAC (Role-Based Access Control)**
   - Tous les utilisateurs authentifiés = admin
   - **Mitigation** : Limitation du nombre d'utilisateurs
   - **Solution** : Implémenter rôles (admin/viewer) avec Cloudflare Groups

4. **Pas de rate limiting strict**
   - `/ingest` peut être spammé avec un token valide
   - **Mitigation** : Cloudflare rate limiting
   - **Solution** : Configurer rate limiting Cloudflare WAF

5. **Session middleware avec secret aléatoire**
   - Secret régénéré à chaque redémarrage
   - **Mitigation** : Peu d'impact car Cloudflare gère les sessions
   - **Solution** : Stocker `SESSION_SECRET` dans `.env`

#### 🟢 Faible priorité

6. **Pas de monitoring de sécurité**
   - Pas d'alertes sur comportements suspects
   - **Solution** : Fail2ban, OSSEC, ou Cloudflare Alerts

7. **Backups non chiffrés**
   - Dumps PostgreSQL en clair
   - **Solution** : Chiffrer avec GPG avant stockage

## 📋 Checklist de sécurité

### Déploiement initial

- [x] Utilisateur système dédié `avmvp` créé
- [x] Service systemd avec directives de sécurité
- [x] Backend écoute uniquement sur localhost
- [x] PostgreSQL écoute uniquement sur localhost
- [x] Firewall configuré (SSH, HTTP, HTTPS uniquement)
- [x] Fichier `.env` avec permissions 600
- [x] HTTPS via Traefik + Let's Encrypt
- [ ] Cloudflare Zero Trust configuré (recommandé)
- [ ] Rate limiting activé (recommandé)

### Maintenance régulière

- [ ] Mises à jour système automatiques activées
- [ ] Rotation manuelle tokens agents (trimestrielle)
- [ ] Vérification logs système (hebdomadaire)
- [ ] Vérification vulnérabilités Python (`safety check`, mensuelle)
- [ ] Backup base de données (quotidien automatique)
- [ ] Test de restauration backup (mensuel)
- [ ] Revue des accès Cloudflare (mensuelle)

### Audit de sécurité

- [ ] Scan de ports (`nmap`) - tout fermé sauf 22, 80, 443
- [ ] Test d'accès PostgreSQL externe - doit échouer
- [ ] Test d'accès backend direct (port 8000) - doit échouer
- [ ] Test d'authentification interface web - doit demander login
- [ ] Vérification permissions fichiers (`find /opt/av-monitoring-mvp -type f -perm /o+w`)

## 🎯 Recommandations selon le contexte

### Environnement de test/dev
**Niveau actuel : Suffisant**
- Configuration actuelle largement suffisante

### PME/Startup (données standard)
**Niveau actuel + Cloudflare Zero Trust : Recommandé**
- Ajouter Cloudflare Zero Trust
- Activer rate limiting
- Backups quotidiens

### Entreprise (données sensibles)
**Niveau Professional requis**
- Tout ce qui précède +
- Chiffrement driver_config en DB
- RBAC avec rôles admin/viewer
- Monitoring de sécurité (OSSEC/Wazuh)
- Backups chiffrés hors site
- Rotation automatique tokens

### Infrastructure critique/réglementée
**Niveau Enterprise requis**
- Tout ce qui précède +
- HSM (Hardware Security Module) pour secrets
- Audit complet avec logs centralisés
- Conformité SOC2/ISO27001
- Pen-testing régulier

## 📚 Ressources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Cloudflare Zero Trust](https://developers.cloudflare.com/cloudflare-one/)
- [Traefik Security](https://doc.traefik.io/traefik/https/overview/)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [PostgreSQL Security](https://www.postgresql.org/docs/current/security.html)

## 🆘 En cas d'incident de sécurité

1. **Isoler** : Couper l'accès réseau si nécessaire
2. **Logger** : Sauvegarder tous les logs
3. **Analyser** : Identifier la faille
4. **Corriger** : Appliquer le patch
5. **Communiquer** : Notifier les utilisateurs si données exposées
6. **Rotation** : Régénérer tous les tokens/secrets
7. **Post-mortem** : Documenter et améliorer

---

**Version** : 1.0
**Date** : 2026-02-15
**Dernière révision** : 2026-02-15
