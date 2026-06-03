"""
app/database/models.py — Schéma relationnel complet Facilim.

Principes RGPD/HDS appliqués :
- Données médicales dans table séparée (medical_data) chiffrées au repos
- UUID partout pour éviter l'énumération
- Timestamps UTC systématiques
- Soft delete (deleted_at) plutôt que suppression physique
- Champs de traçabilité de consentement intégrés
"""

from __future__ import annotations

# ─── DDL SQLite (compatible PostgreSQL avec ajustements mineurs) ──────────────

CREATE_TABLES_SQL: list[str] = [

    # ── Organisations (ESSMS, associations) ─────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS organisations (
        id                  TEXT PRIMARY KEY,          -- UUID
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
        actif               INTEGER NOT NULL DEFAULT 1,
        created_at          TEXT NOT NULL,
        updated_at          TEXT NOT NULL
    )
    """,

    # ── Utilisateurs Dashboard (professionnels ESSMS) ─────────────────────
    """
    CREATE TABLE IF NOT EXISTS utilisateurs (
        id                  TEXT PRIMARY KEY,
        organisation_id     TEXT REFERENCES organisations(id),
        email               TEXT NOT NULL UNIQUE,
        password_hash       TEXT NOT NULL,
        prenom              TEXT,
        nom                 TEXT,
        role                TEXT NOT NULL DEFAULT 'EDUCATEUR',
        -- Rôles : SUPER_ADMIN | ADMIN_ESSMS | EDUCATEUR | LECTEUR
        actif               INTEGER NOT NULL DEFAULT 1,
        derniere_connexion  TEXT,
        created_at          TEXT NOT NULL,
        updated_at          TEXT NOT NULL,
        deleted_at          TEXT
    )
    """,

    # ── Usagers (personnes accompagnées) ────────────────────────────────────
    # Les données PII sont chiffrées (voir security/encryption.py)
    """
    CREATE TABLE IF NOT EXISTS usagers (
        id                  TEXT PRIMARY KEY,
        organisation_id     TEXT REFERENCES organisations(id),
        -- Données identitaires chiffrées (préfixe ENC:: si chiffré)
        telephone_enc       TEXT NOT NULL,             -- canal WhatsApp principal
        email_enc           TEXT,
        nom_enc             TEXT,
        prenom_enc          TEXT,
        date_naissance_enc  TEXT,
        adresse_enc         TEXT,
        code_postal         TEXT,
        commune             TEXT,
        departement_code    TEXT,
        -- Identifiant public non-chiffré pour les opérations
        reference_interne   TEXT UNIQUE,               -- généré : FAC-XXXXXX
        langue_preferee     TEXT DEFAULT 'fr',
        canal_prefere       TEXT DEFAULT 'whatsapp',   -- whatsapp|sms|email|portail
        -- Représentation légale
        representant_legal_id   TEXT REFERENCES usagers(id),
        type_representation     TEXT,  -- TUTELLE|CURATELLE|SAUVEGARDE|PARENT|MANDATAIRE
        -- Statuts
        est_mineur          INTEGER NOT NULL DEFAULT 0,
        est_majeur_protege  INTEGER NOT NULL DEFAULT 0,
        actif               INTEGER NOT NULL DEFAULT 1,
        created_at          TEXT NOT NULL,
        updated_at          TEXT NOT NULL,
        deleted_at          TEXT
    )
    """,

    # ── Consentements RGPD ───────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS consentements (
        id                  TEXT PRIMARY KEY,
        usager_id           TEXT NOT NULL REFERENCES usagers(id),
        version_politique   TEXT NOT NULL DEFAULT '1.0',
        -- Granularité des finalités
        consent_traitement_dossier  INTEGER NOT NULL DEFAULT 0,
        consent_partage_mdph        INTEGER NOT NULL DEFAULT 0,
        consent_partage_essms       INTEGER NOT NULL DEFAULT 0,
        consent_notifications       INTEGER NOT NULL DEFAULT 0,
        consent_amelioration_service INTEGER NOT NULL DEFAULT 0,
        -- Preuve légale
        canal_recueil       TEXT NOT NULL,  -- whatsapp|sms|portail|papier|verbal
        ip_address          TEXT,
        user_agent          TEXT,
        texte_affiche_hash  TEXT NOT NULL,  -- SHA256 du texte de consentement affiché
        -- Validité
        accorde_le          TEXT NOT NULL,
        expire_le           TEXT,
        retire_le           TEXT,          -- si retrait du consentement
        -- Représentation légale
        donne_par_representant  INTEGER NOT NULL DEFAULT 0,
        representant_id         TEXT REFERENCES usagers(id),
        created_at          TEXT NOT NULL
    )
    """,

    # ── Sessions utilisateur (Dashboard) ────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS sessions_dashboard (
        id                  TEXT PRIMARY KEY,
        utilisateur_id      TEXT NOT NULL REFERENCES utilisateurs(id),
        token_hash          TEXT NOT NULL UNIQUE,
        ip_address          TEXT,
        user_agent          TEXT,
        expire_at           TEXT NOT NULL,
        revoked_at          TEXT,
        created_at          TEXT NOT NULL
    )
    """,

    # ── Sessions WhatsApp (état conversationnel) ─────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS sessions_whatsapp (
        id                  TEXT PRIMARY KEY,
        usager_id           TEXT REFERENCES usagers(id),
        telephone           TEXT NOT NULL,
        dossier_id          TEXT,              -- lié au dossier actif
        persona_actif       TEXT DEFAULT 'intake',  -- état logique interne
        etape_courante      TEXT,
        contexte_json       TEXT DEFAULT '{}',
        derniere_activite   TEXT NOT NULL,
        created_at          TEXT NOT NULL
    )
    """,

    # ── Dossiers MDPH ──────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS dossiers (
        id                  TEXT PRIMARY KEY,
        usager_id           TEXT NOT NULL REFERENCES usagers(id),
        organisation_id     TEXT REFERENCES organisations(id),
        educateur_id        TEXT REFERENCES utilisateurs(id),
        -- Identification
        reference           TEXT UNIQUE NOT NULL,  -- FAC-DOS-XXXXXX
        departement_code    TEXT NOT NULL,
        type_dossier        TEXT NOT NULL DEFAULT 'INITIAL',  -- INITIAL|RENOUVELLEMENT|RECOURS
        -- Cycle de vie
        statut              TEXT NOT NULL DEFAULT 'BROUILLON',
        -- BROUILLON → EN_COLLECTE → EN_ANALYSE → INCOMPLET → COMPLET → SOUMIS → CLOS
        -- Scoring
        score_completude    INTEGER DEFAULT 0,  -- 0-100
        score_confiance     REAL DEFAULT 0.0,   -- 0.0-1.0
        -- Droits identifiés
        droits_identifies_json  TEXT DEFAULT '[]',
        -- Flags
        flag_humain_requis  INTEGER NOT NULL DEFAULT 0,
        raison_flag         TEXT,
        urgence             INTEGER NOT NULL DEFAULT 0,  -- 0|1|2 (normal|urgent|critique)
        -- Documents
        certificat_medical_present  INTEGER NOT NULL DEFAULT 0,
        -- Contenu (non-PII, non-médical)
        synthese_json       TEXT DEFAULT '{}',
        questions_json      TEXT DEFAULT '[]',
        -- Historique conversationnel chiffré
        conversation_json   TEXT DEFAULT '[]',
        -- Autodétermination
        has_autodetermination_conflict  INTEGER NOT NULL DEFAULT 0,
        conflict_history_json           TEXT DEFAULT '[]',
        -- Navigation par onglets (état conversationnel)
        contexte_navigation_json        TEXT DEFAULT '{}',
        -- CERFA
        cerfa_version       TEXT,
        cerfa_genere_le     TEXT,
        cerfa_chemin        TEXT,
        -- Soumission
        soumis_le           TEXT,
        clos_le             TEXT,
        -- Traçabilité
        created_at          TEXT NOT NULL,
        updated_at          TEXT NOT NULL,
        deleted_at          TEXT
    )
    """,

    # ── Données médicales (table isolée + chiffrée) ──────────────────────────
    """
    CREATE TABLE IF NOT EXISTS donnees_medicales (
        id                  TEXT PRIMARY KEY,
        dossier_id          TEXT NOT NULL UNIQUE REFERENCES dossiers(id),
        -- Tout le contenu est chiffré
        diagnostics_enc     TEXT,   -- JSON chiffré
        traitements_enc     TEXT,   -- JSON chiffré
        medecin_enc         TEXT,   -- JSON chiffré
        actes_vie_quotidienne_enc TEXT,
        historique_mdph_enc TEXT,
        texte_brut_enc      TEXT,   -- texte original du bilan ESSMS
        texte_anon_enc      TEXT,   -- texte anonymisé
        -- Méta-données non-chiffrées
        actes_detectes_json TEXT DEFAULT '[]',
        created_at          TEXT NOT NULL,
        updated_at          TEXT NOT NULL
    )
    """,

    # ── Pièces justificatives ───────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS pieces_justificatives (
        id                  TEXT PRIMARY KEY,
        dossier_id          TEXT NOT NULL REFERENCES dossiers(id),
        type_piece          TEXT NOT NULL,
        -- CERTIFICAT_MEDICAL|JUSTIFICATIF_IDENTITE|JUSTIFICATIF_DOMICILE|
        -- BILAN_FONCTIONNEL|PLAN_AIDE|AUTRE
        nom_fichier_original TEXT,
        chemin_stockage     TEXT,       -- chemin interne (chiffré si sensible)
        mime_type           TEXT,
        taille_octets       INTEGER,
        -- Validation OCR/IA
        ocr_effectue        INTEGER NOT NULL DEFAULT 0,
        score_confiance_ocr REAL,
        flag_validation_humaine INTEGER NOT NULL DEFAULT 0,
        validee_par         TEXT REFERENCES utilisateurs(id),
        validee_le          TEXT,
        -- Traçabilité
        uploaded_par        TEXT,   -- 'whatsapp'|utilisateur_id
        created_at          TEXT NOT NULL,
        updated_at          TEXT NOT NULL,
        deleted_at          TEXT
    )
    """,

    # ── Scoring et analyse réglementaire ────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS analyses_scoring (
        id                  TEXT PRIMARY KEY,
        dossier_id          TEXT NOT NULL REFERENCES dossiers(id),
        -- Source
        moteur              TEXT NOT NULL DEFAULT 'jade',  -- jade|heuristique|humain
        version_moteur      TEXT,
        -- Résultats
        score_global        INTEGER,   -- 0-100
        statut_analyse      TEXT,      -- COMPLET|INCOMPLET|NON_CALCULÉ
        -- Justification réglementaire (RAG strict)
        sources_juridiques_json TEXT DEFAULT '[]',
        -- Structure: [{article, texte_extrait, version_reglementaire, date_reference}]
        elements_probants_json  TEXT DEFAULT '[]',
        elements_manquants_json TEXT DEFAULT '[]',
        droits_identifies_json  TEXT DEFAULT '[]',
        synthese_agents_json    TEXT DEFAULT '{}',
        recommandation          TEXT,
        -- Human-in-the-loop
        confiance               REAL,
        flag_revue_humaine      INTEGER NOT NULL DEFAULT 0,
        validee_par             TEXT REFERENCES utilisateurs(id),
        validee_le              TEXT,
        -- Traçabilité
        created_at              TEXT NOT NULL
    )
    """,

    # ── Alertes et flags ────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS alertes (
        id                  TEXT PRIMARY KEY,
        dossier_id          TEXT NOT NULL REFERENCES dossiers(id),
        usager_id           TEXT REFERENCES usagers(id),
        destinataire_id     TEXT REFERENCES utilisateurs(id),
        type_alerte         TEXT NOT NULL,
        -- PIECE_MANQUANTE|FLAG_HUMAIN|EXPIRATION_PROCHE|URGENCE|OCR_FAIBLE|
        -- JURIDIQUE_INCERTAIN|RENOUVELLEMENT|RELANCE
        severite            TEXT NOT NULL DEFAULT 'NORMALE',  -- NORMALE|HAUTE|CRITIQUE
        titre               TEXT NOT NULL,
        description         TEXT,
        metadonnees_json    TEXT DEFAULT '{}',
        acquittee           INTEGER NOT NULL DEFAULT 0,
        acquittee_par       TEXT REFERENCES utilisateurs(id),
        acquittee_le        TEXT,
        created_at          TEXT NOT NULL,
        expire_at           TEXT
    )
    """,

    # ── Relances planifiées ─────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS relances (
        id                  TEXT PRIMARY KEY,
        dossier_id          TEXT NOT NULL REFERENCES dossiers(id),
        usager_id           TEXT NOT NULL REFERENCES usagers(id),
        canal               TEXT NOT NULL,  -- whatsapp|sms|email
        type_relance        TEXT NOT NULL,  -- PIECES_MANQUANTES|RENOUVELLEMENT|EXPIRATION
        message_envoye      TEXT,
        planifiee_le        TEXT NOT NULL,
        envoyee_le          TEXT,
        statut              TEXT NOT NULL DEFAULT 'PLANIFIEE',
        -- PLANIFIEE|ENVOYEE|ECHOUEE|ANNULEE
        tentatives          INTEGER NOT NULL DEFAULT 0,
        created_at          TEXT NOT NULL
    )
    """,

    # ── Mandats ESSMS ────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS mandats (
        id                  TEXT PRIMARY KEY,
        usager_id           TEXT NOT NULL REFERENCES usagers(id),
        organisation_id     TEXT NOT NULL REFERENCES organisations(id),
        educateur_id        TEXT REFERENCES utilisateurs(id),
        type_mandat         TEXT NOT NULL DEFAULT 'ACCOMPAGNEMENT',
        -- ACCOMPAGNEMENT|GESTION_DOSSIER|REPRESENTATION_TOTALE
        accorde_le          TEXT NOT NULL,
        expire_le           TEXT,
        retire_le           TEXT,
        preuve_json         TEXT DEFAULT '{}',
        created_at          TEXT NOT NULL
    )
    """,

    # ─── Index de performance ────────────────────────────────────────────────
    "CREATE INDEX IF NOT EXISTS idx_dossiers_usager ON dossiers (usager_id)",
    "CREATE INDEX IF NOT EXISTS idx_dossiers_statut ON dossiers (statut, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_dossiers_flag ON dossiers (flag_humain_requis)",
    "CREATE INDEX IF NOT EXISTS idx_usagers_telephone ON usagers (telephone_enc)",
    "CREATE INDEX IF NOT EXISTS idx_consentements_usager ON consentements (usager_id)",
    "CREATE INDEX IF NOT EXISTS idx_alertes_dossier ON alertes (dossier_id, acquittee)",
    "CREATE INDEX IF NOT EXISTS idx_alertes_destinataire ON alertes (destinataire_id, acquittee)",
    "CREATE INDEX IF NOT EXISTS idx_pieces_dossier ON pieces_justificatives (dossier_id)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_wa_tel ON sessions_whatsapp (telephone)",
]
