# Changelog

All notable changes to the AV Monitoring Agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2024-01-18

### Added
- 🚀 Support d'installation native sur Linux (Ubuntu/Debian) sans Docker
- 📦 Script d'installation automatique (`scripts/install.sh`)
- 🗑️ Script de désinstallation (`scripts/uninstall.sh`)
- ✅ Script de vérification post-installation (`scripts/check-install.sh`)
- 📚 Documentation complète d'installation (`INSTALLATION.md`)
- ⚡ Guide de démarrage rapide (`QUICKSTART.md`)
- 🏗️ Documentation d'architecture (`ARCHITECTURE.md`)
- 🔧 Service systemd (`avmonitoring-agent.service`)
- 📋 Fichier de configuration exemple (`config.example.json`)
- 🎁 Script de création de release (`scripts/create-release.sh`)
- 👤 Utilisateur système dédié (`avmonitoring`)
- 🔒 Mesures de sécurité (NoNewPrivileges, ProtectSystem, etc.)
- 📊 Logs via journald
- 🔄 Redémarrage automatique du service en cas de crash
- 🌐 Interface web locale (port 8080)
- 📡 Synchronisation automatique de la configuration depuis le backend
- 🔌 Support des drivers : ping, SNMP, PJLink
- 📈 Collecte et reporting de métriques

### Changed
- N/A (première version)

### Deprecated
- N/A (première version)

### Removed
- N/A (première version)

### Fixed
- N/A (première version)

### Security
- Isolation via utilisateur système dédié
- Pas d'exécution en root
- Permissions strictes sur les fichiers de configuration (640)
- Interface web accessible uniquement en localhost
- Token d'authentification sécurisé

---

## [Unreleased]

### Planned
- Support d'autres distributions Linux (RHEL, CentOS, etc.)
- Support d'autres init systems (OpenRC, runit)
- Script de mise à jour automatique
- Monitoring des performances de l'agent
- Bufferisation des métriques en cas de perte réseau
- Support de plusieurs backends (failover)
- API locale pour intégrations tierces
- Export des métriques au format Prometheus
- Support IPv6
- Configuration via variables d'environnement
- Packaging DEB/RPM
