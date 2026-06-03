"""
app/database/connection.py — Abstraction de connexion base de données.

SQLite en développement, PostgreSQL en production.
Le reste du code ne connaît que cette couche — migration transparente.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

logger = logging.getLogger("facilim.database")

_DB_PATH: Path | None = None
_initialized: bool = False


def configure(database_url: str) -> None:
    """
    Initialise la connexion selon l'URL fournie par Settings.

    Priorité pour le chemin SQLite :
      1. Variable d'env DATABASE_PATH (absolue) — présente sur Railway avec /data/
      2. DATABASE_URL résolue normalement
    """
    import os
    global _DB_PATH

    if database_url.startswith("sqlite"):
        path_str = database_url.replace("sqlite:///", "").replace("sqlite://", "")
        resolved = Path(path_str).resolve()

        # Sur Railway : DATABASE_PATH pointe vers le volume persistant /data/
        # On utilise mdph_dossiers_v3.db pour éviter tout conflit avec l'ancienne V1.
        env_path = os.environ.get("DATABASE_PATH", "").strip()
        if env_path and not str(resolved).startswith("/data"):
            volume_dir = Path(env_path).parent
            _DB_PATH = volume_dir / "mdph_dossiers_v3.db"
            logger.info(f"[DB] SQLite | path={_DB_PATH} (volume V3)")
        else:
            _DB_PATH = resolved
            logger.info(f"[DB] SQLite | path={_DB_PATH}")
    else:
        raise NotImplementedError(
            "PostgreSQL non encore connecté — configurez asyncpg dans connection.py "
            "et migrez les requêtes de models.py."
        )


def _get_raw_connection() -> sqlite3.Connection:
    if _DB_PATH is None:
        raise RuntimeError("Base de données non configurée — appelez configure() d'abord.")
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    """Context manager — commit automatique, rollback sur exception."""
    conn = _get_raw_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_schema() -> None:
    """Crée toutes les tables si elles n'existent pas."""
    global _initialized
    if _initialized:
        return
    from app.database.models import CREATE_TABLES_SQL
    from app.database.audit_models import CREATE_AUDIT_TABLES_SQL
    import sqlite3 as _sqlite3
    with get_connection() as conn:
        for statement in CREATE_TABLES_SQL:
            try:
                conn.execute(statement)
            except _sqlite3.OperationalError as e:
                msg = str(e).lower()
                # Tolérer : colonne déjà présente, index sur colonne absente (V1 → V2)
                if "duplicate column" in msg or "already exists" in msg or "no such column" in msg:
                    logger.warning("[DB] Schéma init ignoré (base existante) : %s", e)
                else:
                    raise
        for statement in CREATE_AUDIT_TABLES_SQL:
            try:
                conn.execute(statement)
            except _sqlite3.OperationalError as e:
                msg = str(e).lower()
                if "duplicate column" in msg or "already exists" in msg or "no such column" in msg:
                    logger.warning("[DB] Audit init ignoré : %s", e)
                else:
                    raise
    _initialized = True
    logger.info("[DB] Schéma initialisé.")
