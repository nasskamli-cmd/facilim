-- Migration 010 — Sprint 5 : moteur d'analyse de situation
-- Stocke l'analyse de situation et la note d'appui à l'évaluation.

ALTER TABLE dossiers ADD COLUMN analyse_situation_json TEXT DEFAULT '{}';
ALTER TABLE dossiers ADD COLUMN synthese_situation      TEXT DEFAULT '';
ALTER TABLE dossiers ADD COLUMN niveau_confiance_analyse TEXT DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_dossiers_niveau_confiance ON dossiers(niveau_confiance_analyse);
