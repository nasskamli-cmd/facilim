-- Migration 007 — Mise à niveau complète V1 → V2
-- Ajoute toutes les colonnes V2 manquantes sur les tables existantes.
-- Idempotente : SQLite ignore silencieusement "duplicate column name".

-- ── Table usagers ────────────────────────────────────────────────────────────
ALTER TABLE usagers ADD COLUMN organisation_id TEXT;
ALTER TABLE usagers ADD COLUMN email_enc TEXT;
ALTER TABLE usagers ADD COLUMN nom_enc TEXT;
ALTER TABLE usagers ADD COLUMN prenom_enc TEXT;
ALTER TABLE usagers ADD COLUMN date_naissance_enc TEXT;
ALTER TABLE usagers ADD COLUMN adresse_enc TEXT;
ALTER TABLE usagers ADD COLUMN code_postal TEXT;
ALTER TABLE usagers ADD COLUMN commune TEXT;
ALTER TABLE usagers ADD COLUMN departement_code TEXT;
ALTER TABLE usagers ADD COLUMN reference_interne TEXT;
ALTER TABLE usagers ADD COLUMN langue_preferee TEXT DEFAULT 'fr';
ALTER TABLE usagers ADD COLUMN canal_prefere TEXT DEFAULT 'whatsapp';
ALTER TABLE usagers ADD COLUMN representant_legal_id TEXT;
ALTER TABLE usagers ADD COLUMN type_representation TEXT;
ALTER TABLE usagers ADD COLUMN est_mineur INTEGER DEFAULT 0;
ALTER TABLE usagers ADD COLUMN est_majeur_protege INTEGER DEFAULT 0;
ALTER TABLE usagers ADD COLUMN actif INTEGER DEFAULT 1;
ALTER TABLE usagers ADD COLUMN deleted_at TEXT;

-- ── Table dossiers ───────────────────────────────────────────────────────────
ALTER TABLE dossiers ADD COLUMN organisation_id TEXT;
ALTER TABLE dossiers ADD COLUMN educateur_id TEXT;
ALTER TABLE dossiers ADD COLUMN usager_id TEXT;
ALTER TABLE dossiers ADD COLUMN reference TEXT;
ALTER TABLE dossiers ADD COLUMN statut TEXT DEFAULT 'EN_COLLECTE';
ALTER TABLE dossiers ADD COLUMN type_demande TEXT;
ALTER TABLE dossiers ADD COLUMN departement_code TEXT;
ALTER TABLE dossiers ADD COLUMN numero_dossier_mdph TEXT;
ALTER TABLE dossiers ADD COLUMN score_completude INTEGER DEFAULT 0;
ALTER TABLE dossiers ADD COLUMN droits_identifies_json TEXT DEFAULT '[]';
ALTER TABLE dossiers ADD COLUMN synthese_json TEXT DEFAULT '{}';
ALTER TABLE dossiers ADD COLUMN questions_json TEXT DEFAULT '[]';
ALTER TABLE dossiers ADD COLUMN conversation_json TEXT DEFAULT '[]';
ALTER TABLE dossiers ADD COLUMN flag_humain_requis INTEGER DEFAULT 0;
ALTER TABLE dossiers ADD COLUMN urgence TEXT DEFAULT 'normal';
ALTER TABLE dossiers ADD COLUMN notes_pro TEXT;
ALTER TABLE dossiers ADD COLUMN deleted_at TEXT;
ALTER TABLE dossiers ADD COLUMN updated_at TEXT;
ALTER TABLE dossiers ADD COLUMN created_at TEXT;

-- ── Index utiles ─────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_dossiers_usager ON dossiers (usager_id);
CREATE INDEX IF NOT EXISTS idx_dossiers_statut ON dossiers (statut);
CREATE INDEX IF NOT EXISTS idx_usagers_telephone ON usagers (telephone_enc);
