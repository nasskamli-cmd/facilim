"""
app/audit/event_logger.py — Journal d'événements immuable.

Chaque événement est :
  - horodaté en UTC
  - identifié par un UUID unique
  - associé au contexte métier (dossier, usager, utilisateur)
  - persisté en append-only dans audit_events
  - loggé dans le logger Python

Le système est idempotent via idempotency_key.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("facilim.audit")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_idempotency_key(
    type_evenement: str,
    payload: dict[str, Any],
    timestamp: str,
) -> str:
    content = f"{type_evenement}:{json.dumps(payload, sort_keys=True)}:{timestamp}"
    return hashlib.sha256(content.encode()).hexdigest()[:32]


def log_event(
    type_evenement: str,
    *,
    dossier_id: str | None = None,
    usager_id: str | None = None,
    utilisateur_id: str | None = None,
    organisation_id: str | None = None,
    canal: str | None = None,
    sous_type: str | None = None,
    payload: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    session_id: str | None = None,
    db_conn: Any | None = None,
) -> str:
    """
    Enregistre un événement dans le journal d'audit.

    Returns:
        event_id (UUID str)
    """
    event_id = str(uuid.uuid4())
    now = _now_iso()
    payload = payload or {}
    idempotency_key = _build_idempotency_key(type_evenement, payload, now)

    event_data = {
        "id":               event_id,
        "type_evenement":   type_evenement,
        "dossier_id":       dossier_id,
        "usager_id":        usager_id,
        "utilisateur_id":   utilisateur_id,
        "organisation_id":  organisation_id,
        "canal":            canal,
        "sous_type":        sous_type,
        "payload_json":     json.dumps(payload, ensure_ascii=False),
        "ip_address":       ip_address,
        "user_agent":       user_agent,
        "session_id":       session_id,
        "idempotency_key":  idempotency_key,
        "created_at":       now,
    }

    # Log Python (toujours)
    logger.info(
        f"[AUDIT] {type_evenement}"
        + (f" | dossier={dossier_id[:8]}" if dossier_id else "")
        + (f" | usager={usager_id[:8]}" if usager_id else "")
        + (f" | canal={canal}" if canal else "")
    )

    # Persistance DB si connexion fournie
    if db_conn is not None:
        try:
            db_conn.execute(
                """
                INSERT OR IGNORE INTO audit_events
                    (id, dossier_id, usager_id, utilisateur_id, organisation_id,
                     type_evenement, canal, sous_type, payload_json,
                     ip_address, user_agent, session_id, idempotency_key, created_at)
                VALUES
                    (:id, :dossier_id, :usager_id, :utilisateur_id, :organisation_id,
                     :type_evenement, :canal, :sous_type, :payload_json,
                     :ip_address, :user_agent, :session_id, :idempotency_key, :created_at)
                """,
                event_data,
            )
        except Exception as e:
            logger.error(f"[AUDIT] Échec persistance événement {type_evenement}: {e}")

    return event_id


def log_medical_access(
    utilisateur_id: str,
    dossier_id: str,
    operation: str,
    justification: str,
    champs_accedes: list[str] | None = None,
    ip_address: str | None = None,
    db_conn: Any | None = None,
) -> None:
    """Journal HDS spécifique aux accès aux données de santé."""
    record = {
        "id":               str(uuid.uuid4()),
        "utilisateur_id":   utilisateur_id,
        "usager_id":        None,
        "dossier_id":       dossier_id,
        "table_accedee":    "donnees_medicales",
        "operation":        operation,
        "champs_accedes":   json.dumps(champs_accedes or []),
        "justification":    justification,
        "ip_address":       ip_address,
        "created_at":       _now_iso(),
    }
    logger.info(f"[AUDIT-HDS] {operation} | dossier={dossier_id[:8]} | user={utilisateur_id[:8]}")
    if db_conn is not None:
        try:
            db_conn.execute(
                """
                INSERT INTO audit_acces_sante
                    (id, utilisateur_id, usager_id, dossier_id, table_accedee,
                     operation, champs_accedes, justification, ip_address, created_at)
                VALUES
                    (:id, :utilisateur_id, :usager_id, :dossier_id, :table_accedee,
                     :operation, :champs_accedes, :justification, :ip_address, :created_at)
                """,
                record,
            )
        except Exception as e:
            logger.error(f"[AUDIT-HDS] Échec persistance : {e}")


def log_agent_action(
    agent_nom: str,
    action: str,
    *,
    dossier_id: str | None = None,
    agent_niveau: str | None = None,
    input_hash: str | None = None,
    output_hash: str | None = None,
    score_confiance: float | None = None,
    tokens_utilises: int | None = None,
    duree_ms: int | None = None,
    flag_genere: bool = False,
    db_conn: Any | None = None,
) -> None:
    """Journal des actions des agents IA."""
    record = {
        "id":               str(uuid.uuid4()),
        "dossier_id":       dossier_id,
        "agent_nom":        agent_nom,
        "agent_niveau":     agent_niveau,
        "action":           action,
        "input_hash":       input_hash,
        "output_hash":      output_hash,
        "score_confiance":  score_confiance,
        "tokens_utilises":  tokens_utilises,
        "duree_ms":         duree_ms,
        "flag_genere":      1 if flag_genere else 0,
        "created_at":       _now_iso(),
    }
    logger.debug(f"[AUDIT-AGENT] {agent_nom} | {action}" + (f" | dossier={dossier_id[:8]}" if dossier_id else ""))
    if db_conn is not None:
        try:
            db_conn.execute(
                """
                INSERT INTO audit_agents
                    (id, dossier_id, agent_nom, agent_niveau, action,
                     input_hash, output_hash, score_confiance, tokens_utilises,
                     duree_ms, flag_genere, created_at)
                VALUES
                    (:id, :dossier_id, :agent_nom, :agent_niveau, :action,
                     :input_hash, :output_hash, :score_confiance, :tokens_utilises,
                     :duree_ms, :flag_genere, :created_at)
                """,
                record,
            )
        except Exception as e:
            logger.error(f"[AUDIT-AGENT] Échec persistance : {e}")
