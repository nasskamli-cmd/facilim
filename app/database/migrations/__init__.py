"""
app/database/migrations/__init__.py — Système de migrations SQL Facilim.

Architecture duale SQLite / PostgreSQL :

  SQLite (dev local) :
    - Les tables sont créées par initialize_schema() via models.py
    - Migration 001 (DDL PostgreSQL) est automatiquement marquée appliquée
      si les tables existent déjà
    - Seules les migrations ALTER TABLE (002+) sont exécutées réellement

  PostgreSQL (prod Railway) :
    - Migration 001 crée le schéma complet
    - Les migrations suivantes ajoutent des colonnes avec ALTER TABLE

Idempotence garantie :
  - Une table schema_migrations enregistre chaque migration appliquée
  - Relancer run_all() est toujours sans effet sur les migrations passées
  - Les colonnes déjà présentes génèrent un warning, pas une erreur

Usage :
  python -c "from app.database.migrations import run_all; run_all()"
  railway run python -c "from app.database.migrations import run_all; run_all()"
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("facilim.migrations")

_MIGRATIONS_DIR = Path(__file__).parent

# Migration 001 = DDL PostgreSQL pur. Sur SQLite, les tables sont créées
# par initialize_schema() (models.py). On la marque comme pré-appliquée.
_SQLITE_SKIP_VERSIONS = {"001"}


# ── Connexion ─────────────────────────────────────────────────────────────────

def _open_connection() -> tuple[Any, str]:
    """
    Ouvre une connexion DB depuis DATABASE_URL (env var).
    Retourne (connexion, "sqlite" | "postgresql").
    """
    database_url = os.environ.get("DATABASE_URL", "sqlite:///./mdph_dossiers.db")

    if database_url.startswith("sqlite"):
        path_str = database_url.replace("sqlite:///", "").replace("sqlite://", "")
        db_path = Path(path_str).resolve()
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=OFF")  # requis pour ALTER TABLE sans contraintes
        logger.info(f"[MIGRATE] SQLite -> {db_path}")
        return conn, "sqlite"

    try:
        import psycopg2
        conn = psycopg2.connect(database_url)
        conn.autocommit = False
        logger.info("[MIGRATE] PostgreSQL connecte")
        return conn, "postgresql"
    except ImportError:
        raise RuntimeError(
            "psycopg2 non installe. Ajoutez psycopg2-binary au requirements.txt."
        )


# ── Table de suivi ─────────────────────────────────────────────────────────────

_CREATE_TRACKING_SQLITE = """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        version     TEXT NOT NULL UNIQUE,
        filename    TEXT NOT NULL,
        applied_at  TEXT NOT NULL
    )
"""

_CREATE_TRACKING_PG = """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        id          SERIAL PRIMARY KEY,
        version     TEXT NOT NULL UNIQUE,
        filename    TEXT NOT NULL,
        applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
"""


def _ensure_tracking_table(conn: Any, dialect: str) -> None:
    sql = _CREATE_TRACKING_SQLITE if dialect == "sqlite" else _CREATE_TRACKING_PG
    conn.execute(sql)
    if dialect == "sqlite":
        conn.commit()


def _is_applied(conn: Any, version: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM schema_migrations WHERE version = ?", (version,)
    ).fetchone()
    return row is not None


def _mark_applied(conn: Any, version: str, filename: str, dialect: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations (version, filename, applied_at) "
        "VALUES (?, ?, ?)",
        (version, filename, now),
    )
    if dialect == "sqlite":
        conn.commit()


# ── Fichiers SQL ───────────────────────────────────────────────────────────────

def _list_sql_files() -> list[tuple[str, Path]]:
    """Retourne les fichiers NNN_xxx.sql triés par numéro."""
    pattern = re.compile(r"^(\d{3})_.+\.sql$")
    return sorted(
        ((m.group(1), f) for f in _MIGRATIONS_DIR.iterdir() if (m := pattern.match(f.name))),
        key=lambda x: x[0],
    )


# ── Application d'une migration ───────────────────────────────────────────────

def _apply(conn: Any, version: str, filepath: Path, dialect: str) -> list[str]:
    """
    Exécute chaque instruction du fichier SQL.
    Tolère les colonnes/tables déjà existantes (idempotence).
    Retourne la liste des erreurs bloquantes (vide = succès).
    """
    sql_text = filepath.read_text(encoding="utf-8")
    statements = [
        s.strip()
        for s in sql_text.split(";")
        if s.strip() and not s.strip().startswith("--")
    ]

    blocking_errors: list[str] = []

    for stmt in statements:
        # Détermine si c'est une instruction DDL structurelle
        stmt_upper = stmt.upper().lstrip()
        is_alter   = stmt_upper.startswith("ALTER TABLE")
        is_index   = stmt_upper.startswith("CREATE INDEX") or stmt_upper.startswith("CREATE UNIQUE INDEX")

        try:
            conn.execute(stmt)
            # Sur SQLite : commit après chaque ALTER TABLE pour rendre la colonne
            # visible aux instructions suivantes (ex: CREATE INDEX sur nouvelle colonne)
            if dialect == "sqlite" and is_alter:
                conn.commit()
        except Exception as exc:
            msg = str(exc).lower()
            benign = (
                "duplicate column" in msg      # SQLite  : colonne déjà présente
                or "already exists" in msg     # Postgres : table/index déjà présent
                or (is_index and "no such column" in msg)  # index sur colonne absente = ignoré
            )
            if benign:
                logger.warning("[MIGRATE] Ignore (deja applique) : %s...", stmt[:70])
            else:
                blocking_errors.append(f"{stmt[:70]}... -> {exc}")

    return blocking_errors


# ── SQLite : pré-marquage de la migration 001 ─────────────────────────────────

def _sqlite_bootstrap_001(conn: Any) -> bool:
    """
    Sur SQLite, vérifie si les tables principales existent déjà
    (créées par initialize_schema / models.py).
    Si oui, marque la migration 001 comme appliquée sans rien toucher.
    Retourne True si le pré-marquage a été effectué.
    """
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='dossiers'"
    ).fetchone()
    if row:
        _mark_applied(conn, "001", "001_initial_facilim_v2.sql (pre-marked, SQLite)", "sqlite")
        logger.info(
            "[MIGRATE] SQLite : tables deja presentes -> migration 001 marquee sans execution"
        )
        return True
    return False


# ── SQLite : s'assurer que le schema de base existe ───────────────────────────

def _sqlite_ensure_base_schema() -> None:
    """
    Appelle initialize_schema() pour créer les tables si elles n'existent pas.
    Nécessite que DATABASE_URL et ENCRYPTION_KEY soient dans l'environnement.
    """
    try:
        from app.config.settings import get_settings
        from app.database import connection as db_module
        from app.security import encryption

        s = get_settings()
        if s.encryption_key:
            encryption.initialize(s.encryption_key)
        db_module.configure(s.database_url)
        db_module.initialize_schema()
        logger.info("[MIGRATE] SQLite : initialize_schema() OK")
    except Exception as exc:
        logger.warning(
            "[MIGRATE] initialize_schema() indisponible (%s) "
            "-> les tables doivent deja exister", exc
        )


# ── Point d'entrée public ──────────────────────────────────────────────────────

def run_all(verbose: bool = True) -> dict[str, list[str]]:
    """
    Applique toutes les migrations SQL en attente, dans l'ordre.
    Idempotent.

    Returns:
        {"applied": [...noms de fichiers...],
         "skipped": [...],
         "errors":  [...]}
    """
    if verbose:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)-8s | %(message)s",
        )

    conn, dialect = _open_connection()
    _ensure_tracking_table(conn, dialect)

    # Sur SQLite : s'assurer que les tables de base existent
    if dialect == "sqlite":
        _sqlite_ensure_base_schema()
        if not _is_applied(conn, "001"):
            _sqlite_bootstrap_001(conn)

    sql_files = _list_sql_files()
    applied: list[str] = []
    skipped: list[str] = []
    errors:  list[str] = []

    for version, filepath in sql_files:
        # Sur SQLite, on saute les migrations 001 (DDL PostgreSQL)
        if dialect == "sqlite" and version in _SQLITE_SKIP_VERSIONS:
            skipped.append(filepath.name + " (SQLite : schema gere par models.py)")
            continue

        if _is_applied(conn, version):
            skipped.append(filepath.name)
            logger.info("[MIGRATE] -- %s (deja appliquee)", filepath.name)
            continue

        logger.info("[MIGRATE] Application : %s ...", filepath.name)
        errs = _apply(conn, version, filepath, dialect)

        if errs:
            for e in errs:
                logger.error("[MIGRATE] ERREUR %s : %s", filepath.name, e)
            errors.extend(errs)
            conn.rollback() if dialect == "postgresql" else None
            break  # stoppe sur erreur bloquante

        _mark_applied(conn, version, filepath.name, dialect)
        if dialect == "postgresql":
            conn.commit()
        applied.append(filepath.name)
        logger.info("[MIGRATE] OK : %s", filepath.name)

    conn.close()

    # Bilan (ASCII pur pour compatibilite Windows cp1252)
    sep = "-" * 56
    print(f"\n{sep}")
    print("  Facilim -- Bilan des migrations")
    print(sep)
    print(f"  Appliquees  : {len(applied)}")
    for f in applied:
        print(f"    + {f}")
    print(f"  Ignorees    : {len(skipped)}")
    for f in skipped:
        print(f"    - {f}")
    if errors:
        print(f"  ERREURS     : {len(errors)}")
        for e in errors:
            print(f"    ! {e}")
    print(f"{sep}\n")

    return {"applied": applied, "skipped": skipped, "errors": errors}


def status() -> None:
    """Affiche l'etat des migrations sans rien appliquer."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    conn, dialect = _open_connection()
    _ensure_tracking_table(conn, dialect)

    sql_files = _list_sql_files()
    rows = conn.execute(
        "SELECT version FROM schema_migrations"
    ).fetchall()
    applied_versions = {r[0] for r in rows}

    sep = "-" * 56
    print(f"\n{sep}")
    print("  Facilim -- Etat des migrations")
    print(sep)
    for version, filepath in sql_files:
        mark = "OK" if version in applied_versions else "EN ATTENTE"
        print(f"  [{mark:^10}]  {filepath.name}")
    print(f"{sep}\n")
    conn.close()


if __name__ == "__main__":
    run_all()
