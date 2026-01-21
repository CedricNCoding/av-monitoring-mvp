-- Script pour réparer les SNMP community corrompues (null ou vides)
-- À exécuter sur le serveur de production

-- 1. Voir les devices SNMP avec community null ou vide
SELECT
    id,
    ip,
    name,
    driver,
    driver_config->'snmp'->>'community' as current_community
FROM devices
WHERE driver = 'snmp'
  AND (
    driver_config->'snmp'->>'community' IS NULL
    OR driver_config->'snmp'->>'community' = ''
    OR driver_config->'snmp'->>'community' = 'none'
  );

-- 2. Réparer en mettant "public" par défaut (à adapter si tu veux une autre valeur)
UPDATE devices
SET driver_config = jsonb_set(
    COALESCE(driver_config, '{}'::jsonb),
    '{snmp,community}',
    '"public"'::jsonb
)
WHERE driver = 'snmp'
  AND (
    driver_config->'snmp'->>'community' IS NULL
    OR driver_config->'snmp'->>'community' = ''
    OR driver_config->'snmp'->>'community' = 'none'
  );

-- 3. Vérifier que c'est corrigé
SELECT
    id,
    ip,
    name,
    driver,
    driver_config->'snmp'->>'community' as fixed_community
FROM devices
WHERE driver = 'snmp';
