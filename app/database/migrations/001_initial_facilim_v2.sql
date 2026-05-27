-- migrations/001_initial_facilim_v2.sql
-- Migration initiale Facilim v2
-- À exécuter sur une base PostgreSQL vierge pour la mise en production

-- Extension UUID (PostgreSQL uniquement)
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── organisations ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS organisations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nom                 TEXT NOT NULL,
    siret               TEXT,
    finess              TEXT,
    type_structure      TEXT NOT NULL DEFAULT 'ESSMS',
    adresse             TEXT,
    code_postal         TEXT,
    commune             TEXT,
    departement_code    TEXT NOT NULL,
    email_contact       TEXT,
    telephone           TEXT,
    actif               BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── utilisateurs ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS utilisateurs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id     UUID REFERENCES organisations(id),
    email               TEXT NOT NULL UNIQUE,
    password_hash       TEXT NOT NULL,
    prenom              TEXT,
    nom                 TEXT,
    role                TEXT NOT NULL DEFAULT 'EDUCATEUR'
                        CHECK (role IN ('SUPER_ADMIN','ADMIN_ESSMS','EDUCATEUR','LECTEUR')),
    actif               BOOLEAN NOT NULL DEFAULT TRUE,
    derniere_connexion  TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at          TIMESTAMPTZ
);

-- ── usagers ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS usagers (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id         UUID REFERENCES organisations(id),
    telephone_enc           TEXT NOT NULL,
    email_enc               TEXT,
    nom_enc                 TEXT,
    prenom_enc              TEXT,
    date_naissance_enc      TEXT,
    adresse_enc             TEXT,
    code_postal             TEXT,
    commune                 TEXT,
    departement_code        TEXT,
    reference_interne       TEXT UNIQUE,
    langue_preferee         TEXT DEFAULT 'fr',
    canal_prefere           TEXT DEFAULT 'whatsapp',
    representant_legal_id   UUID REFERENCES usagers(id),
    type_representation     TEXT,
    est_mineur              BOOLEAN NOT NULL DEFAULT FALSE,
    est_majeur_protege      BOOLEAN NOT NULL DEFAULT FALSE,
    actif                   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at              TIMESTAMPTZ
);

-- ── consentements ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS consentements (
    id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usager_id                       UUID NOT NULL REFERENCES usagers(id),
    version_politique               TEXT NOT NULL DEFAULT '1.0',
    consent_traitement_dossier      BOOLEAN NOT NULL DEFAULT FALSE,
    consent_partage_mdph            BOOLEAN NOT NULL DEFAULT FALSE,
    consent_partage_essms           BOOLEAN NOT NULL DEFAULT FALSE,
    consent_notifications           BOOLEAN NOT NULL DEFAULT FALSE,
    consent_amelioration_service    BOOLEAN NOT NULL DEFAULT FALSE,
    canal_recueil                   TEXT NOT NULL,
    ip_address                      TEXT,
    user_agent                      TEXT,
    texte_affiche_hash              TEXT NOT NULL,
    accorde_le                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expire_le                       TIMESTAMPTZ,
    retire_le                       TIMESTAMPTZ,
    donne_par_representant          BOOLEAN NOT NULL DEFAULT FALSE,
    representant_id                 UUID REFERENCES usagers(id),
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── dossiers ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dossiers (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usager_id                   UUID NOT NULL REFERENCES usagers(id),
    organisation_id             UUID REFERENCES organisations(id),
    educateur_id                UUID REFERENCES utilisateurs(id),
    reference                   TEXT UNIQUE NOT NULL,
    departement_code            TEXT NOT NULL,
    type_dossier                TEXT NOT NULL DEFAULT 'INITIAL',
    statut                      TEXT NOT NULL DEFAULT 'BROUILLON',
    score_completude            INTEGER DEFAULT 0,
    score_confiance             REAL DEFAULT 0.0,
    droits_identifies_json      JSONB DEFAULT '[]'::jsonb,
    flag_humain_requis          BOOLEAN NOT NULL DEFAULT FALSE,
    raison_flag                 TEXT,
    urgence                     SMALLINT NOT NULL DEFAULT 0,
    certificat_medical_present  BOOLEAN NOT NULL DEFAULT FALSE,
    synthese_json               JSONB DEFAULT '{}'::jsonb,
    questions_json              JSONB DEFAULT '[]'::jsonb,
    conversation_json           JSONB DEFAULT '[]'::jsonb,
    cerfa_version               TEXT,
    cerfa_genere_le             TIMESTAMPTZ,
    cerfa_chemin                TEXT,
    soumis_le                   TIMESTAMPTZ,
    clos_le                     TIMESTAMPTZ,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at                  TIMESTAMPTZ
);

-- ── donnees_medicales ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS donnees_medicales (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossier_id                  UUID NOT NULL UNIQUE REFERENCES dossiers(id),
    diagnostics_enc             TEXT,
    traitements_enc             TEXT,
    medecin_enc                 TEXT,
    actes_vie_quotidienne_enc   TEXT,
    historique_mdph_enc         TEXT,
    texte_brut_enc              TEXT,
    texte_anon_enc              TEXT,
    actes_detectes_json         JSONB DEFAULT '[]'::jsonb,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── audit_events (append-only) ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossier_id          UUID,
    usager_id           UUID,
    utilisateur_id      UUID,
    organisation_id     UUID,
    type_evenement      TEXT NOT NULL,
    canal               TEXT,
    sous_type           TEXT,
    payload_json        JSONB DEFAULT '{}'::jsonb,
    ip_address          TEXT,
    user_agent          TEXT,
    session_id          TEXT,
    idempotency_key     TEXT UNIQUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Index critiques ────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_dossiers_usager     ON dossiers (usager_id);
CREATE INDEX IF NOT EXISTS idx_dossiers_statut     ON dossiers (statut, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_dossiers_flag       ON dossiers (flag_humain_requis) WHERE flag_humain_requis = TRUE;
CREATE INDEX IF NOT EXISTS idx_usagers_telephone   ON usagers (telephone_enc);
CREATE INDEX IF NOT EXISTS idx_audit_dossier       ON audit_events (dossier_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_type          ON audit_events (type_evenement, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_consentements_usager ON consentements (usager_id);
