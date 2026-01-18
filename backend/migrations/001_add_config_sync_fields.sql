-- Migration: Ajout des champs de synchronisation config
-- Date: 2026-01-18
-- Description: Ajoute les champs nécessaires pour la synchronisation pull de configuration

-- Table sites: ajout des champs de configuration globale et versioning
ALTER TABLE sites
    ADD COLUMN IF NOT EXISTS timezone VARCHAR DEFAULT 'Europe/Paris' NOT NULL,
    ADD COLUMN IF NOT EXISTS doubt_after_days INTEGER DEFAULT 2 NOT NULL,
    ADD COLUMN IF NOT EXISTS ok_interval_s INTEGER DEFAULT 300 NOT NULL,
    ADD COLUMN IF NOT EXISTS ko_interval_s INTEGER DEFAULT 60 NOT NULL,
    ADD COLUMN IF NOT EXISTS config_version VARCHAR,
    ADD COLUMN IF NOT EXISTS config_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

-- Table devices: ajout des champs de configuration driver et expectations
ALTER TABLE devices
    ADD COLUMN IF NOT EXISTS floor VARCHAR,
    ADD COLUMN IF NOT EXISTS driver_config JSONB DEFAULT '{}' NOT NULL,
    ADD COLUMN IF NOT EXISTS expectations JSONB DEFAULT '{}' NOT NULL;

-- Mettre à jour les valeurs par défaut pour les sites existants
UPDATE sites
SET
    timezone = COALESCE(timezone, 'Europe/Paris'),
    doubt_after_days = COALESCE(doubt_after_days, 2),
    ok_interval_s = COALESCE(ok_interval_s, 300),
    ko_interval_s = COALESCE(ko_interval_s, 60),
    config_updated_at = COALESCE(config_updated_at, NOW())
WHERE timezone IS NULL OR doubt_after_days IS NULL OR ok_interval_s IS NULL OR ko_interval_s IS NULL;

-- Mettre à jour les valeurs par défaut pour les devices existants
UPDATE devices
SET
    driver_config = COALESCE(driver_config, '{}'::jsonb),
    expectations = COALESCE(expectations, '{}'::jsonb)
WHERE driver_config IS NULL OR expectations IS NULL;

-- Index pour optimiser les requêtes de synchronisation
CREATE INDEX IF NOT EXISTS idx_sites_config_version ON sites(config_version);
CREATE INDEX IF NOT EXISTS idx_sites_token ON sites(token);

-- Commentaires
COMMENT ON COLUMN sites.timezone IS 'Timezone du site pour les règles de scheduling';
COMMENT ON COLUMN sites.doubt_after_days IS 'Nombre de jours avant de passer en "doubt" après dernière collecte OK';
COMMENT ON COLUMN sites.ok_interval_s IS 'Intervalle de collecte en secondes quand tout va bien';
COMMENT ON COLUMN sites.ko_interval_s IS 'Intervalle de collecte en secondes en cas de problème';
COMMENT ON COLUMN sites.config_version IS 'Hash MD5 de la configuration complète du site (pour sync agent)';
COMMENT ON COLUMN sites.config_updated_at IS 'Date de dernière mise à jour de la configuration';

COMMENT ON COLUMN devices.floor IS 'Étage où se trouve l équipement';
COMMENT ON COLUMN devices.driver_config IS 'Configuration spécifique au driver (SNMP, PJLink, etc.)';
COMMENT ON COLUMN devices.expectations IS 'Règles de scheduling et alertes (always_on, schedule, alert_after_s)';
