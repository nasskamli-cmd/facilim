-- Migration 009 — Phase 3 : profilage multi-handicap + qualité CERFA
-- Ajoute les colonnes nécessaires aux nouveaux moteurs.

-- Profilage métier multi-handicap (Ajout 1)
ALTER TABLE dossiers ADD COLUMN profil_principal  TEXT DEFAULT '';
ALTER TABLE dossiers ADD COLUMN profil_secondaire TEXT DEFAULT '';
ALTER TABLE dossiers ADD COLUMN tags_detectes     TEXT DEFAULT '[]';

-- Textes narratifs CERFA (cerfa_narrative_engine)
ALTER TABLE dossiers ADD COLUMN texte_b_vie_quotidienne TEXT DEFAULT '';
ALTER TABLE dossiers ADD COLUMN texte_c_scolarite       TEXT DEFAULT '';
ALTER TABLE dossiers ADD COLUMN texte_d_situation_pro   TEXT DEFAULT '';
ALTER TABLE dossiers ADD COLUMN texte_e_projet_vie      TEXT DEFAULT '';

-- Score de maturité CERFA et alertes qualité (cerfa_quality_agent)
ALTER TABLE dossiers ADD COLUMN score_maturite_cerfa  INTEGER DEFAULT 0;
ALTER TABLE dossiers ADD COLUMN niveau_maturite        TEXT    DEFAULT '';
ALTER TABLE dossiers ADD COLUMN alertes_qualite_json   TEXT    DEFAULT '[]';
ALTER TABLE dossiers ADD COLUMN rapport_qualite_json   TEXT    DEFAULT '{}';

-- Index pour filtrage dashboard par niveau de maturité
CREATE INDEX IF NOT EXISTS idx_dossiers_niveau_maturite   ON dossiers(niveau_maturite);
CREATE INDEX IF NOT EXISTS idx_dossiers_profil_principal  ON dossiers(profil_principal);
