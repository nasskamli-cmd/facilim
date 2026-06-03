-- Migration 006 — Ajout colonne usager_id sur les tables existantes (base V1 → V2)
-- Idempotente : SQLite ignore "duplicate column name"

ALTER TABLE dossiers
    ADD COLUMN usager_id TEXT;

ALTER TABLE consentements
    ADD COLUMN usager_id TEXT;

CREATE INDEX IF NOT EXISTS idx_dossiers_usager
    ON dossiers (usager_id);

CREATE INDEX IF NOT EXISTS idx_consentements_usager
    ON consentements (usager_id);
