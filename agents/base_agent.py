"""
agents/base_agent.py — Classe de base pour tous les agents Facilim.

Chaque agent a un prénom, un niveau hiérarchique et une méthode run().
Toutes les actions sont tracées dans les logs avec le prénom de l'agent.
"""
import logging
import json
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("facilim.agents")


class BaseAgent:
    """
    Contrat minimal de chaque agent Facilim.

    Attributs de classe à surcharger :
        NOM     : prénom humain (ex: "Camille")
        NIVEAU  : code niveau (ex: "N1")
        ROLE    : description courte du rôle
    """
    NOM    : str = "Inconnu"
    NIVEAU : str = "N?"
    ROLE   : str = ""

    def __init__(self, db_conn=None, settings=None):
        self.db       = db_conn   # connexion SQLite ou session async PG
        self.settings = settings
        self._log     = logging.getLogger(f"facilim.agents.{self.NOM.lower()}")

    # ── Logging tracé ────────────────────────────────────────────────────────

    def log_info(self, msg: str, dossier_id: str | None = None, **extra):
        prefix = f"[{self.NIVEAU}][{self.NOM}]"
        if dossier_id:
            prefix += f"[DOS:{dossier_id[:8]}]"
        self._log.info(f"{prefix} {msg}", extra=extra or {})
        self._write_db_log("INFO", msg, dossier_id, extra)

    def log_warning(self, msg: str, dossier_id: str | None = None, **extra):
        prefix = f"[{self.NIVEAU}][{self.NOM}]"
        if dossier_id:
            prefix += f"[DOS:{dossier_id[:8]}]"
        self._log.warning(f"{prefix} {msg}", extra=extra or {})
        self._write_db_log("WARNING", msg, dossier_id, extra)

    def log_error(self, msg: str, dossier_id: str | None = None, **extra):
        prefix = f"[{self.NIVEAU}][{self.NOM}]"
        if dossier_id:
            prefix += f"[DOS:{dossier_id[:8]}]"
        self._log.error(f"{prefix} {msg}", extra=extra or {})
        self._write_db_log("ERROR", msg, dossier_id, extra)

    def _write_db_log(self, niveau: str, msg: str, dossier_id: str | None, meta: dict):
        """Insère un log en base (table logs_agents si disponible)."""
        if self.db is None:
            return
        try:
            self.db.execute("""
                INSERT INTO logs_agents (agent_nom, agent_niveau, niveau, dossier_id, message, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                self.NOM, self.NIVEAU, niveau, dossier_id,
                msg,
                json.dumps(meta, ensure_ascii=False) if meta else None,
                datetime.now(timezone.utc).isoformat(),
            ))
            self.db.commit()
        except Exception:
            pass  # ne jamais faire planter l'agent à cause du log

    # ── Interface publique ────────────────────────────────────────────────────

    def run(self, dossier: dict[str, Any], **kwargs) -> dict[str, Any]:
        """
        Point d'entrée de l'agent.
        Retourne le dossier enrichi avec les modifications de l'agent.
        À surcharger dans chaque sous-classe.
        """
        raise NotImplementedError(f"{self.NOM}.run() doit être implémenté.")

    def __repr__(self) -> str:
        return f"<Agent {self.NOM} | {self.NIVEAU} | {self.ROLE}>"
