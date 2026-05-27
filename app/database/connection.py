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
    """Initialise la connexion selon l'URL fournie par Settings."""
    global _DB_PATH
    if database_url.startswith("sqlite"):
        path_str = database_url.replace("sqlite:///", "").replace("sqlite://", "")
        _DB_PATH = Path(path_str).resolve()
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
    with get_connection() as conn:
        for statement in CREATE_TABLES_SQL:
            conn.execute(statement)
        for statement in CREATE_AUDIT_TABLES_SQL:
            conn.execute(statement)
    _initialized = True
    logger.info("[DB] Schéma initialisé.")
