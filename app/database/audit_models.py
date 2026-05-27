"""
app/database/audit_models.py — Tables d'audit immuables.

Ces tables sont en append-only : jamais de UPDATE, jamais de DELETE.
Elles constituent le journal légal et réglementaire de la plateforme.
Compatibles avec les exigences HDS (traçabilité des accès aux données de santé).
"""

from __future__ import annotations

CREATE_AUDIT_TABLES_SQL: list[str] = [

    # ── Journal d'événements métier ──────────────────────────────────────────
    # Chaque action significative dans le système produit un événement.
    """
    CREATE TABLE IF NOT EXISTS audit_events (
        id              TEXT PRIMARY KEY,
        -- Contexte
        dossier_id      TEXT,
        usager_id       TEXT,
        utilisateur_id  TEXT,
        organisation_id TEXT,
        -- Événement
        type_evenement  TEXT NOT NULL,
        -- DOSSIER_CREE|DOSSIER_MIS_A_JOUR|DOCUMENT_RECU|OCR_EFFECTUE|
        -- SCORING_EFFECTUE|FLAG_CREE|ALERTE_ENVOYEE|CONSENTEMENT_DONNE|
        -- CONSENTEMENT_RETIRE|DONNEE_EXPORTEE|DONNEE_SUPPRIMEE|
        -- WHATSAPP_RECU|WHATSAPP_ENVOYE|EMAIL_ENVOYE|SMS_ENVOYE|
        -- CONNEXION_DASHBOARD|DECONNEXION|ACCES_DOSSIER|
        -- VALIDATION_HUMAINE|CERFA_GENERE|DOSSIER_SOUMIS|DOSSIER_CLOS
        canal           TEXT,  -- whatsapp|sms|email|dashboard|api
        sous_type       TEXT,
        -- Données de l'événement (JSON — non-chiffré pour searchability)
        payload_json    TEXT DEFAULT '{}',
        -- Contexte technique
        ip_address      TEXT,
        user_agent      TEXT,
        session_id      TEXT,
        -- Idempotence
        idempotency_key TEXT UNIQUE,
        -- Timestamp immuable
        created_at      TEXT NOT NULL
    )
    """,

    # ── Journal d'accès aux données de santé (exigence HDS) ─────────────────
    """
    CREATE TABLE IF NOT EXISTS audit_acces_sante (
        id              TEXT PRIMARY KEY,
        utilisateur_id  TEXT,
        usager_id       TEXT,
        dossier_id      TEXT,
        table_accedee   TEXT NOT NULL,  -- donnees_medicales|pieces_justificatives
        operation       TEXT NOT NULL,  -- READ|WRITE|DELETE|EXPORT
        champs_accedes  TEXT,           -- liste des colonnes
        justification   TEXT,           -- motif professionnel (obligatoire HDS)
        ip_address      TEXT,
        created_at      TEXT NOT NULL
    )
    """,

    # ── Historique des consentements ─────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS audit_consentements (
        id              TEXT PRIMARY KEY,
        consentement_id TEXT NOT NULL,
        usager_id       TEXT NOT NULL,
        action          TEXT NOT NULL,  -- DONNE|MODIFIE|RETIRE|EXPIRE
        version_politique TEXT NOT NULL,
        details_json    TEXT DEFAULT '{}',
        canal           TEXT,
        ip_address      TEXT,
        created_at      TEXT NOT NULL
    )
    """,

    # ── Journal des modifications de données (before/after) ─────────────────
    """
    CREATE TABLE IF NOT EXISTS audit_modifications (
        id              TEXT PRIMARY KEY,
        table_name      TEXT NOT NULL,
        record_id       TEXT NOT NULL,
        champ_modifie   TEXT NOT NULL,
        valeur_avant    TEXT,   -- NULL si création
        valeur_apres    TEXT,   -- NULL si suppression
        modifie_par     TEXT,   -- utilisateur_id ou 'system'
        raison          TEXT,
        created_at      TEXT NOT NULL
    )
    """,

    # ── Logs des agents IA ───────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS audit_agents (
        id              TEXT PRIMARY KEY,
        dossier_id      TEXT,
        agent_nom       TEXT NOT NULL,
        agent_niveau    TEXT,
        action          TEXT NOT NULL,
        input_hash      TEXT,   -- SHA256 de l'entrée (pas le contenu brut)
        output_hash     TEXT,   -- SHA256 de la sortie
        score_confiance REAL,
        tokens_utilises INTEGER,
        duree_ms        INTEGER,
        flag_genere     INTEGER NOT NULL DEFAULT 0,
        created_at      TEXT NOT NULL
    )
    """,

    # ── Index audit ──────────────────────────────────────────────────────────
    "CREATE INDEX IF NOT EXISTS idx_audit_events_dossier ON audit_events (dossier_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_audit_events_type ON audit_events (type_evenement, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_audit_acces_utilisateur ON audit_acces_sante (utilisateur_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_audit_modifications_record ON audit_modifications (table_name, record_id)",
    "CREATE INDEX IF NOT EXISTS idx_audit_agents_dossier ON audit_agents (dossier_id, created_at)",
]
