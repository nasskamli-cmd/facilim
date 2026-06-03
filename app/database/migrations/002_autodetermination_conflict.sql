-- Migration 002 — Suivi des conflits d'autodetermination
-- Colonnes sans NOT NULL pour compatibilite SQLite (toutes versions).
-- La contrainte est appliquee via la valeur DEFAULT (0 = pas de conflit).

ALTER TABLE dossiers
    ADD COLUMN has_autodetermination_conflict INTEGER DEFAULT 0;

ALTER TABLE dossiers
    ADD COLUMN conflict_history_json TEXT DEFAULT '[]';

CREATE INDEX IF NOT EXISTS idx_dossiers_conflict
    ON dossiers (has_autodetermination_conflict);
