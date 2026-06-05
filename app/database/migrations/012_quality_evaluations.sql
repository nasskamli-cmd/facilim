-- Migration 012 — Module Analytics V2.2
-- Table d'évaluations qualité terrain.
-- Totalement indépendante du pipeline CERFA.
-- Idempotente : CREATE TABLE IF NOT EXISTS garantit la sécurité du replay.

CREATE TABLE IF NOT EXISTS quality_evaluations (
    id                      TEXT PRIMARY KEY,

    -- ── Traçabilité ──────────────────────────────────────────────────
    dossier_id              TEXT,
    date_evaluation         TEXT NOT NULL,
    evaluateur              TEXT DEFAULT 'nassim',
    version_facilim         TEXT DEFAULT '',
    essms_source            TEXT DEFAULT '',
    created_at              TEXT NOT NULL,

    -- ── Profil du dossier ────────────────────────────────────────────
    profil_mdph             TEXT DEFAULT '',
    type_handicap           TEXT DEFAULT '',
    type_dossier            TEXT DEFAULT '',
    document_present        INTEGER DEFAULT 0,
    type_document           TEXT DEFAULT '',
    niveau_documentation    INTEGER DEFAULT 0,

    -- ── Notes sections (REAL, -1 = non applicable) ───────────────────
    score_b                 REAL DEFAULT -1,
    score_c                 REAL DEFAULT -1,
    score_d                 REAL DEFAULT -1,
    score_e                 REAL DEFAULT -1,
    score_global            REAL DEFAULT 0,
    score_maturite          INTEGER DEFAULT 0,

    -- ── Temps (minutes) ─────────────────────────────────────────────
    temps_correction        REAL DEFAULT 0,
    temps_correction_b      REAL DEFAULT 0,
    temps_correction_c      REAL DEFAULT 0,
    temps_correction_d      REAL DEFAULT 0,
    temps_correction_e      REAL DEFAULT 0,

    -- ── ROI ──────────────────────────────────────────────────────────
    temps_estime_sans_facilim REAL DEFAULT 0,
    temps_reel_avec_facilim   REAL DEFAULT 0,
    gain_temps              REAL DEFAULT 0,

    -- ── Taux de réécriture (%) ───────────────────────────────────────
    taux_reecriture_b       REAL DEFAULT 0,
    taux_reecriture_c       REAL DEFAULT 0,
    taux_reecriture_d       REAL DEFAULT 0,
    taux_reecriture_e       REAL DEFAULT 0,
    taux_reecriture_global  REAL DEFAULT 0,

    -- ── Performance extraction documentaire ──────────────────────────
    questions_supprimees    INTEGER DEFAULT 0,
    items_extraits          INTEGER DEFAULT 0,

    -- ── Niveau de validation ─────────────────────────────────────────
    niveau_validation       TEXT DEFAULT '',

    -- ── JSON ─────────────────────────────────────────────────────────
    erreurs_detectees       TEXT DEFAULT '[]',
    metadata                TEXT DEFAULT '{}'
);

-- Index analytiques
CREATE INDEX IF NOT EXISTS idx_qe_date      ON quality_evaluations(date_evaluation);
CREATE INDEX IF NOT EXISTS idx_qe_profil    ON quality_evaluations(profil_mdph);
CREATE INDEX IF NOT EXISTS idx_qe_niveau    ON quality_evaluations(niveau_validation);
CREATE INDEX IF NOT EXISTS idx_qe_version   ON quality_evaluations(version_facilim);
CREATE INDEX IF NOT EXISTS idx_qe_type_dos  ON quality_evaluations(type_dossier);
CREATE INDEX IF NOT EXISTS idx_qe_doc       ON quality_evaluations(document_present);
CREATE INDEX IF NOT EXISTS idx_qe_niv_doc   ON quality_evaluations(niveau_documentation);
CREATE INDEX IF NOT EXISTS idx_qe_essms     ON quality_evaluations(essms_source);
CREATE INDEX IF NOT EXISTS idx_qe_dossier   ON quality_evaluations(dossier_id);
