-- Migration 008 — Infrastructure de traçabilité des validations CERFA
-- Deux tables : cerfa_validations (preuve formelle) + cerfa_audit_log (journal)
-- Colonne version dans dossiers pour versionning du contenu.
-- Idempotente. Erreur "duplicate column" gérée silencieusement par run_all().
-- RGPD : emails jamais en clair dans cerfa_audit_log (hash SHA256 + domaine uniquement).
-- organisation_id reporté à version SaaS multi-tenant.

-- ── Table 1 : Validations formelles (immuables) ──────────────────────────────
-- Une ligne par validation usager ou professionnel.
-- Jamais modifiée après insertion.
CREATE TABLE IF NOT EXISTS cerfa_validations (
    id                  TEXT    PRIMARY KEY,
    dossier_id          TEXT    NOT NULL,
    validated_by        TEXT    NOT NULL,
    canal               TEXT    NOT NULL,
    type_validation     TEXT    NOT NULL
                        CHECK (type_validation IN ('usager', 'professionnel')),
    validated_at        TEXT    NOT NULL,
    synthese_hash       TEXT    NOT NULL,
    cerfa_pdf_hash      TEXT,
    dossier_version     INTEGER NOT NULL DEFAULT 1,
    confirmation_texte  TEXT    NOT NULL,
    reponse_usager      TEXT    NOT NULL
                        CHECK (reponse_usager IN ('OUI', 'NON')),
    created_at          TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cerfa_validations_dossier
    ON cerfa_validations (dossier_id);
CREATE INDEX IF NOT EXISTS idx_cerfa_validations_date
    ON cerfa_validations (validated_at);
CREATE INDEX IF NOT EXISTS idx_cerfa_validations_type
    ON cerfa_validations (type_validation, dossier_id);

-- ── Table 2 : Journal d'audit métier (append-only) ───────────────────────────
-- Chronologie complète de tous les événements CERFA pour un dossier.
-- Jamais modifiée après insertion.
-- RGPD : emails non stockés en clair.
--        details_json contient uniquement email_hash (SHA256) + email_domaine.
CREATE TABLE IF NOT EXISTS cerfa_audit_log (
    id              TEXT    PRIMARY KEY,
    dossier_id      TEXT    NOT NULL,
    event_type      TEXT    NOT NULL
                    CHECK (event_type IN (
                        'generation_cerfa',
                        'telechargement_cerfa',
                        'previsualisation_cerfa',
                        'validation_usager',
                        'validation_professionnel',
                        'envoi_cerfa',
                        'modification_dossier'
                    )),
    event_at        TEXT    NOT NULL,
    canal           TEXT,
    acteur_id       TEXT,
    acteur_type     TEXT
                    CHECK (acteur_type IN ('usager', 'professionnel', 'systeme')),
    details_json    TEXT,
    created_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cerfa_audit_dossier
    ON cerfa_audit_log (dossier_id, event_at);

-- ── Colonne version dans dossiers ────────────────────────────────────────────
-- Incrémentée à chaque modification de synthese_json.
-- Permet de lier une validation à une version précise du contenu.
-- SQLite  : erreur "duplicate column name: version" → capturée par run_all() → WARNING bénin.
-- PostgreSQL : idem "already exists".
ALTER TABLE dossiers ADD COLUMN version INTEGER DEFAULT 1;
