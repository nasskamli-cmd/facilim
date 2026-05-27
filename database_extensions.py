"""
database_extensions.py — Extension de la couche SQLite pour les nouveaux agents Facilim.

Ce fichier N'ÉCRASE PAS database.py existant.
Il ajoute les nouvelles tables et colonnes nécessaires aux agents V2 :
  - relances          : historique des relances Mathilde
  - logs_agents       : traçabilité des actions agents
  - scores_historique : historique des scores Maya

Et étend la table dossiers avec :
  - urgence, langue_preferee, agent_actuel, type_dossier
  - nb_relances, statut_relance, derniere_relance_at
  - score_actuel, score_potentiel, score_suggestion, taux_incapacite
  - donnees_normalisees_json (Camille)

Appeler init_extensions() au démarrage, après database.init_db().
"""

import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger("facilim.db_ext")

_DB_PATH = Path(__file__).parent / "mdph_dossiers.db"


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _add_column_safe(conn: sqlite3.Connection, table: str, column_def: str):
    """Ajoute une colonne si elle n'existe pas déjà (migration non-destructive)."""
    col_name = column_def.split()[0]
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
        conn.commit()
        logger.info(f"[DB_EXT] Colonne '{col_name}' ajoutée à '{table}'.")
    except sqlite3.OperationalError:
        pass  # Colonne déjà présente


def init_extensions() -> None:
    """
    Crée les nouvelles tables et étend la table dossiers.
    Idempotent — peut être appelé plusieurs fois sans danger.
    """
    with _get_connection() as conn:

        # ── Table relances ────────────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS relances (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                dossier_id       TEXT NOT NULL,
                numero_relance   INTEGER NOT NULL,
                canal            TEXT DEFAULT 'whatsapp',
                message_envoye   TEXT,
                reponse_recue    TEXT,
                statut           TEXT DEFAULT 'envoyee',
                forcee_par       TEXT,
                planifiee_pour   TEXT,
                envoyee_le       TEXT,
                created_at       TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_relances_dossier
            ON relances (dossier_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_relances_planifiee
            ON relances (planifiee_pour, statut)
        """)

        # ── Table logs_agents ─────────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS logs_agents (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_nom    TEXT NOT NULL,
                agent_niveau TEXT,
                niveau       TEXT DEFAULT 'INFO',
                dossier_id   TEXT,
                message      TEXT NOT NULL,
                metadata     TEXT,
                created_at   TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_logs_dossier
            ON logs_agents (dossier_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_logs_agent
            ON logs_agents (agent_nom)
        """)

        # ── Table scores_historique ───────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scores_historique (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                dossier_id      TEXT NOT NULL,
                score           REAL NOT NULL,
                score_potentiel REAL,
                suggestion      TEXT,
                justification   TEXT,
                rag_sources     TEXT,
                created_at      TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_scores_dossier
            ON scores_historique (dossier_id)
        """)

        conn.commit()

    # ── Nouvelles colonnes dans dossiers ──────────────────────────────────────
    with _get_connection() as conn:
        # Dispatch & workflow
        _add_column_safe(conn, "dossiers", "urgence TEXT DEFAULT 'normal'")
        _add_column_safe(conn, "dossiers", "langue_preferee TEXT DEFAULT 'fr'")
        _add_column_safe(conn, "dossiers", "agent_actuel TEXT")
        _add_column_safe(conn, "dossiers", "type_dossier TEXT")
        _add_column_safe(conn, "dossiers", "cellule_assignee TEXT")
        _add_column_safe(conn, "dossiers", "manager_local TEXT")

        # Relances
        _add_column_safe(conn, "dossiers", "nb_relances INTEGER DEFAULT 0")
        _add_column_safe(conn, "dossiers", "statut_relance TEXT")
        _add_column_safe(conn, "dossiers", "derniere_relance_at TEXT")

        # Scoring Maya
        _add_column_safe(conn, "dossiers", "score_actuel REAL")
        _add_column_safe(conn, "dossiers", "score_potentiel REAL")
        _add_column_safe(conn, "dossiers", "score_suggestion TEXT")
        _add_column_safe(conn, "dossiers", "score_justification TEXT")
        _add_column_safe(conn, "dossiers", "taux_incapacite TEXT")
        _add_column_safe(conn, "dossiers", "taux_justification TEXT")
        _add_column_safe(conn, "dossiers", "rag_sources TEXT")

        # Camille
        _add_column_safe(conn, "dossiers", "donnees_normalisees_json TEXT")

        # Inès
        _add_column_safe(conn, "dossiers", "nom_enfant_chiffre TEXT")
        _add_column_safe(conn, "dossiers", "prenom_enfant_chiffre TEXT")
        _add_column_safe(conn, "dossiers", "telephone_famille_chiffre TEXT")
        _add_column_safe(conn, "dossiers", "email_famille_chiffre TEXT")

    logger.info("[DB_EXT] Extensions DB initialisées.")


# ── Helpers pour les nouveaux agents ─────────────────────────────────────────

def save_score(dossier_id: str, score: float, potentiel: float,
               suggestion: str = "", justification: str = "", sources: list = None):
    """Enregistre un score dans l'historique."""
    import json as _json
    now = datetime.now(timezone.utc).isoformat()
    with _get_connection() as conn:
        conn.execute("""
            INSERT INTO scores_historique
              (dossier_id, score, score_potentiel, suggestion, justification, rag_sources, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            dossier_id, score, potentiel, suggestion, justification,
            _json.dumps(sources or [], ensure_ascii=False),
            now,
        ))
        conn.execute("""
            UPDATE dossiers SET
                score_actuel=?, score_potentiel=?,
                score_suggestion=?, score_justification=?,
                updated_at=?
            WHERE dossier_id=?
        """, (score, potentiel, suggestion, justification, now, dossier_id))
        conn.commit()


def get_dossiers_a_relancer() -> list[dict]:
    """
    Retourne les dossiers INCOMPLET ou EN_COURS sans réponse depuis > 24h
    et avec moins de 3 relances envoyées.
    """
    with _get_connection() as conn:
        rows = conn.execute("""
            SELECT dossier_id, telephone_famille, email_famille,
                   nb_relances, derniere_relance_at, statut, langue_preferee
            FROM dossiers
            WHERE statut IN ('INCOMPLET', 'EN_COURS')
              AND (nb_relances IS NULL OR nb_relances < 3)
              AND (
                   derniere_relance_at IS NULL
                OR datetime(derniere_relance_at) < datetime('now', '-24 hours')
              )
            ORDER BY updated_at ASC
        """).fetchall()
    return [dict(r) for r in rows]


def get_relances_par_dossier(dossier_id: str) -> list[dict]:
    """Retourne l'historique des relances d'un dossier."""
    with _get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM relances WHERE dossier_id=? ORDER BY created_at ASC",
            (dossier_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def save_dossier_agent_fields(dossier_id: str, fields: dict):
    """
    Met à jour les champs agents dans la table dossiers de façon sûre.
    Seuls les champs connus (colonnes existantes) sont mis à jour.
    """
    import json as _json
    now = datetime.now(timezone.utc).isoformat()

    allowed = {
        "urgence", "langue_preferee", "agent_actuel", "type_dossier",
        "cellule_assignee", "manager_local",
        "nb_relances", "statut_relance", "derniere_relance_at",
        "score_actuel", "score_potentiel", "score_suggestion",
        "score_justification", "taux_incapacite", "taux_justification",
        "donnees_normalisees_json",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return

    set_clause = ", ".join(f"{k}=?" for k in updates)
    values     = list(updates.values()) + [now, dossier_id]

    with _get_connection() as conn:
        try:
            conn.execute(
                f"UPDATE dossiers SET {set_clause}, updated_at=? WHERE dossier_id=?",
                values,
            )
            conn.commit()
        except Exception as e:
            logger.error(f"[DB_EXT] save_dossier_agent_fields : {e}")
