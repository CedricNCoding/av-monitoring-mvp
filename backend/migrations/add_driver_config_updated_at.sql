-- Migration: Add driver_config_updated_at column to devices table
-- Date: 2026-02-03
-- Purpose: Track timestamp of driver_config modifications for bidirectional sync

ALTER TABLE devices
ADD COLUMN IF NOT EXISTS driver_config_updated_at TIMESTAMP WITH TIME ZONE;

-- Optionally set initial value for existing rows to current timestamp
-- UPDATE devices SET driver_config_updated_at = NOW() WHERE driver_config_updated_at IS NULL;
