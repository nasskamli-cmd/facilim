"""
database.py — Couche de persistance SQLite pour MDPH-Backbone.

Remplace le dictionnaire en mémoire (_dossiers_store) par une vraie base de données
qui survit aux redémarrages du serveur.

SQLite est une base de données légère stockée dans un seul fichier sur le disque.
Aucune installation requise — elle est incluse dans Python.

En production, cette couche pourra être migrée vers PostgreSQL sans toucher
au reste du code — seul ce fichier change.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Chemin du fichier de base de données.
# En production Railway, DATABASE_PATH=/data/mdph_dossiers.db (volume persistant).
# En local, on utilise le répertoire de ce fichier.
_DB_PATH = Path(os.environ.get("DATABASE_PATH", Path(__file__).parent / "mdph_dossiers.db"))


def _migrate_add_column(column_definition: str) -> None:
    """Ajoute une colonne à la table dossiers si elle n'existe pas déjà."""
    col_name = column_definition.split()[0]
    with _get_connection() as conn:
        try:
            conn.execute(f"ALTER TABLE dossiers ADD COLUMN {column_definition}")
            conn.commit()
            logger.info(f"Migration : colonne '{col_name}' ajoutée.")
        except Exception:
            pass  # La colonne existe déjà


def _get_connection() -> sqlite3.Connection:
    """
    Ouvre une connexion à la base de données SQLite.
    Le paramètre check_same_thread=False est nécessaire pour FastAPI
    qui utilise plusieurs threads en parallèle.
    """
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row  # Permet d'accéder aux colonnes par leur nom
    return conn


def init_db() -> None:
    """
    Crée la table des dossiers si elle n'existe pas encore.
    À appeler une seule fois au démarrage du serveur.
    """
    with _get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dossiers (
                dossier_id           TEXT PRIMARY KEY,
                telephone_famille    TEXT NOT NULL,
                departement_code     TEXT NOT NULL,
                educateur_id         TEXT,
                statut               TEXT NOT NULL DEFAULT 'EN_COURS',
                langue_famille       TEXT,
                analyse_json         TEXT DEFAULT '{}',
                questions_json       TEXT DEFAULT '[]',
                reponses_json        TEXT DEFAULT '[]',
                whatsapp_envoye      INTEGER DEFAULT 0,
                email_famille        TEXT,
                nom_enfant           TEXT,
                prenom_enfant        TEXT,
                ddn_enfant           TEXT,
                adresse_enfant       TEXT,
                cp_enfant            TEXT,
                commune_enfant       TEXT,
                questions_en_attente INTEGER DEFAULT 0,
                photos_json          TEXT DEFAULT '[]',
                created_at           TEXT NOT NULL,
                updated_at           TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_telephone
            ON dossiers (telephone_famille, statut)
        """)
        conn.commit()

    # Migrations : ajouter les nouvelles colonnes sur les bases existantes
    _migrate_add_column("email_famille TEXT")
    _migrate_add_column("nom_enfant TEXT")
    _migrate_add_column("prenom_enfant TEXT")
    _migrate_add_column("ddn_enfant TEXT")
    _migrate_add_column("adresse_enfant TEXT")
    _migrate_add_column("cp_enfant TEXT")
    _migrate_add_column("commune_enfant TEXT")
    _migrate_add_column("questions_en_attente INTEGER DEFAULT 0")
    _migrate_add_column("photos_json TEXT DEFAULT '[]'")
    _migrate_add_column("cerfa_reponses_json TEXT DEFAULT '{}'")
    _migrate_add_column("deleted_at TEXT")
    # Colonnes critiques — dialogue CERFA et email médical
    _migrate_add_column("cerfa_dialogue_demarre INTEGER DEFAULT 0")
    _migrate_add_column("email_medical_recu INTEGER DEFAULT 0")
    _migrate_add_column("email_medical_recu_at TEXT")
    _migrate_add_column("email_medical_contenu TEXT")
    _migrate_add_column("email_medical_sender TEXT")
    _migrate_add_column("pdf_genere INTEGER DEFAULT 0")
    _migrate_add_column("pdf_bytes BLOB")
    _migrate_add_column("cerfa_bytes BLOB")

    logger.info(f"Base de données initialisée | fichier={_DB_PATH}")


def save_dossier(dossier: dict[str, Any]) -> None:
    """
    Sauvegarde ou met à jour un dossier dans la base de données.
    Si le dossier_id existe déjà, il est mis à jour. Sinon, il est créé.
    """
    with _get_connection() as conn:
        conn.execute("""
            INSERT INTO dossiers
                (dossier_id, telephone_famille, departement_code, educateur_id,
                 statut, langue_famille, analyse_json, questions_json,
                 reponses_json, whatsapp_envoye, email_famille,
                 nom_enfant, prenom_enfant, ddn_enfant,
                 adresse_enfant, cp_enfant, commune_enfant,
                 questions_en_attente, photos_json, cerfa_reponses_json,
                 cerfa_dialogue_demarre, email_medical_recu, email_medical_recu_at,
                 email_medical_contenu, email_medical_sender,
                 pdf_genere, pdf_bytes, cerfa_bytes,
                 created_at, updated_at)
            VALUES
                (:dossier_id, :telephone_famille, :departement_code, :educateur_id,
                 :statut, :langue_famille, :analyse_json, :questions_json,
                 :reponses_json, :whatsapp_envoye, :email_famille,
                 :nom_enfant, :prenom_enfant, :ddn_enfant,
                 :adresse_enfant, :cp_enfant, :commune_enfant,
                 :questions_en_attente, :photos_json, :cerfa_reponses_json,
                 :cerfa_dialogue_demarre, :email_medical_recu, :email_medical_recu_at,
                 :email_medical_contenu, :email_medical_sender,
                 :pdf_genere, :pdf_bytes, :cerfa_bytes,
                 :created_at, :updated_at)
            ON CONFLICT(dossier_id) DO UPDATE SET
                statut                 = excluded.statut,
                langue_famille         = excluded.langue_famille,
                analyse_json           = excluded.analyse_json,
                questions_json         = excluded.questions_json,
                reponses_json          = excluded.reponses_json,
                whatsapp_envoye        = excluded.whatsapp_envoye,
                email_famille          = excluded.email_famille,
                nom_enfant             = excluded.nom_enfant,
                prenom_enfant          = excluded.prenom_enfant,
                ddn_enfant             = excluded.ddn_enfant,
                adresse_enfant         = excluded.adresse_enfant,
                cp_enfant              = excluded.cp_enfant,
                commune_enfant         = excluded.commune_enfant,
                questions_en_attente   = excluded.questions_en_attente,
                photos_json            = excluded.photos_json,
                cerfa_reponses_json    = excluded.cerfa_reponses_json,
                cerfa_dialogue_demarre = excluded.cerfa_dialogue_demarre,
                email_medical_recu     = excluded.email_medical_recu,
                email_medical_recu_at  = excluded.email_medical_recu_at,
                email_medical_contenu  = excluded.email_medical_contenu,
                email_medical_sender   = excluded.email_medical_sender,
                pdf_genere             = excluded.pdf_genere,
                pdf_bytes              = excluded.pdf_bytes,
                cerfa_bytes            = excluded.cerfa_bytes,
                updated_at             = excluded.updated_at
        """, {
            "dossier_id":              dossier["dossier_id"],
            "telephone_famille":       dossier["telephone_famille"],
            "departement_code":        dossier["departement_code"],
            "educateur_id":            dossier.get("educateur_id"),
            "statut":                  dossier.get("statut", "EN_COURS"),
            "langue_famille":          dossier.get("langue_famille"),
            "analyse_json":            json.dumps(dossier.get("analyse") or {}, ensure_ascii=False),
            "questions_json":          json.dumps(dossier.get("questions_falc_envoyees") or [], ensure_ascii=False),
            "reponses_json":           json.dumps(dossier.get("historique_reponses") or [], ensure_ascii=False),
            "whatsapp_envoye":         1 if dossier.get("whatsapp_envoye") else 0,
            "email_famille":           dossier.get("email_famille"),
            "nom_enfant":              dossier.get("nom_enfant"),
            "prenom_enfant":           dossier.get("prenom_enfant"),
            "ddn_enfant":              dossier.get("ddn_enfant"),
            "adresse_enfant":          dossier.get("adresse_enfant"),
            "cp_enfant":               dossier.get("cp_enfant"),
            "commune_enfant":          dossier.get("commune_enfant"),
            "questions_en_attente":    dossier.get("questions_en_attente", 0),
            "photos_json":             json.dumps(dossier.get("photos") or [], ensure_ascii=False),
            "cerfa_reponses_json":     json.dumps(dossier.get("cerfa_reponses") or {}, ensure_ascii=False),
            "cerfa_dialogue_demarre":  dossier.get("cerfa_dialogue_demarre", 0),
            "email_medical_recu":      dossier.get("email_medical_recu", 0),
            "email_medical_recu_at":   dossier.get("email_medical_recu_at", ""),
            "email_medical_contenu":   dossier.get("email_medical_contenu", ""),
            "email_medical_sender":    dossier.get("email_medical_sender", ""),
            "pdf_genere":              dossier.get("pdf_genere", 0),
            "pdf_bytes":               dossier.get("pdf_bytes", None),
            "cerfa_bytes":             dossier.get("cerfa_bytes", None),
            "created_at":              dossier["created_at"],
            "updated_at":              dossier["updated_at"],
        })
        conn.commit()
    logger.debug(f"Dossier sauvegardé | id={dossier['dossier_id']} | statut={dossier.get('statut')}")


def get_dossier_by_id(dossier_id: str) -> dict[str, Any] | None:
    """Récupère un dossier par son identifiant unique (exact ou préfixe)."""
    with _get_connection() as conn:
        # Recherche exacte d'abord
        row = conn.execute(
            "SELECT * FROM dossiers WHERE dossier_id = ?", (dossier_id,)
        ).fetchone()
        if row:
            return _row_to_dict(row)
        # Fallback : recherche par préfixe (utile quand l'ID est tronqué)
        row = conn.execute(
            "SELECT * FROM dossiers WHERE dossier_id LIKE ? LIMIT 1", (dossier_id + "%",)
        ).fetchone()
    return _row_to_dict(row) if row else None


def get_active_dossier_by_phone(phone_number: str) -> dict[str, Any] | None:
    """
    Récupère le dossier actif (EN_COURS ou INCOMPLET) associé à un numéro de téléphone.
    Priorité au plus récent.
    """
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM dossiers WHERE telephone_famille = ? "
            "AND statut IN ('INCOMPLET', 'EN_COURS', 'DROITS_A_VALIDER', 'PRET_POUR_REVUE') "
            "AND deleted_at IS NULL "
            "ORDER BY updated_at DESC LIMIT 1",
            (phone_number,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def count_dossiers_actifs(educateur_id: str | None = None) -> int:
    """
    Retourne le nombre de dossiers actifs (statut EN_COURS ou INCOMPLET).
    Utilisé pour contrôler le quota avant création d'un nouveau dossier.
    """
    with _get_connection() as conn:
        if educateur_id is not None:
            row = conn.execute(
                "SELECT COUNT(*) FROM dossiers "
                "WHERE statut IN ('EN_COURS', 'INCOMPLET') "
                "AND educateur_id = ?",
                (educateur_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) FROM dossiers "
                "WHERE statut IN ('EN_COURS', 'INCOMPLET')"
            ).fetchone()
    return row[0] if row else 0


def purge_dossier_pii(dossier_id: str) -> None:
    """
    Supprime les données personnelles d'un dossier COMPLET (conformité RGPD).

    Conserve : dossier_id, departement_code, statut, created_at, updated_at.
    Efface   : nom, prénom, téléphone, email, adresse, DDN, langue,
               historique des réponses WhatsApp, texte brut dans l'analyse.

    À appeler juste après que le PDF a été envoyé avec succès.
    """
    dossier = get_dossier_by_id(dossier_id)
    if not dossier:
        return

    # Nettoyage du bloc analyse (conserver droits, score, recommandation)
    analyse = dossier.get("analyse") or {}
    analyse.pop("_texte_anon", None)
    analyse.pop("texte_brut", None)

    now = datetime.now(timezone.utc).isoformat()

    with _get_connection() as conn:
        conn.execute("""
            UPDATE dossiers SET
                telephone_famille    = '[SUPPRIMÉ]',
                email_famille        = NULL,
                nom_enfant           = NULL,
                prenom_enfant        = NULL,
                ddn_enfant           = NULL,
                adresse_enfant       = NULL,
                cp_enfant            = NULL,
                commune_enfant       = NULL,
                langue_famille       = NULL,
                reponses_json        = '[]',
                analyse_json         = ?,
                questions_en_attente = 0,
                updated_at           = ?
            WHERE dossier_id = ?
        """, (json.dumps(analyse, ensure_ascii=False), now, dossier_id))
        conn.commit()

    logger.info(f"Données personnelles supprimées (RGPD) | dossier={dossier_id}")


def list_dossiers() -> list[dict[str, Any]]:
    """
    Retourne tous les dossiers non supprimés, triés du plus récent au plus ancien.
    Utilisé par le tableau de bord.
    """
    with _get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM dossiers WHERE deleted_at IS NULL ORDER BY updated_at DESC"
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def soft_delete_dossier(dossier_id: str, deleted_by: str | None = None) -> bool:
    """
    Suppression logique d'un dossier (RGPD-safe). Pose deleted_at au lieu de DELETE physique.
    Retourne True si le dossier existait et a été marqué supprimé.
    """
    now = datetime.now(timezone.utc).isoformat()
    with _get_connection() as conn:
        cur = conn.execute(
            "UPDATE dossiers SET deleted_at = ?, updated_at = ? WHERE dossier_id = ? AND deleted_at IS NULL",
            (now, now, dossier_id),
        )
        conn.commit()
    existed = cur.rowcount > 0
    if existed:
        logger.info(f"Dossier supprimé (soft) | id={dossier_id} | par={deleted_by}")
    return existed


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """
    Convertit une ligne SQLite en dictionnaire Python.
    Rehydrate les champs JSON stockés en texte.
    """
    d = dict(row)
    d["analyse"]                 = json.loads(d.pop("analyse_json") or "{}")
    d["questions_falc_envoyees"] = json.loads(d.pop("questions_json") or "[]")
    d["historique_reponses"]     = json.loads(d.pop("reponses_json") or "[]")
    d["whatsapp_envoye"]         = bool(d["whatsapp_envoye"])
    d["photos"]                  = json.loads(d.pop("photos_json", None) or "[]")
    d["cerfa_reponses"]          = json.loads(d.pop("cerfa_reponses_json", None) or "{}")
    d["cerfa_dialogue_demarre"]  = bool(d.get("cerfa_dialogue_demarre", 0))
    d["email_medical_recu"]      = bool(d.get("email_medical_recu", 0))
    d["pdf_genere"]              = bool(d.get("pdf_genere", 0))
    # pdf_bytes et cerfa_bytes restent en bytes (BLOB) ou None
    d.setdefault("questions_en_attente", 0)
    d.setdefault("email_medical_recu_at", None)
    d.setdefault("email_medical_contenu", None)
    d.setdefault("email_medical_sender", None)
    d.setdefault("pdf_bytes", None)
    d.setdefault("cerfa_bytes", None)
    return d
