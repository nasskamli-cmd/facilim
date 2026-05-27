"""
app/engines/case_state_engine.py — Machine à états du dossier MDPH.

Le dossier suit un cycle de vie strict et traçable.
Chaque transition est :
  - validée (les transitions invalides sont rejetées)
  - journalisée dans audit_events
  - persistée atomiquement en base

Cycle de vie :
  BROUILLON → EN_COLLECTE → EN_ANALYSE → INCOMPLET → COMPLET → SOUMIS → CLOS
                                              ↑___________|
                                         (boucle collecte)
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.audit.event_logger import log_event

logger = logging.getLogger("facilim.engines.case_state")


# ── Définition de la machine à états ────────────────────────────────────────

class DossierStatut:
    BROUILLON    = "BROUILLON"
    EN_COLLECTE  = "EN_COLLECTE"
    EN_ANALYSE   = "EN_ANALYSE"
    INCOMPLET    = "INCOMPLET"
    COMPLET      = "COMPLET"
    SOUMIS       = "SOUMIS"
    CLOS         = "CLOS"


_TRANSITIONS_VALIDES: dict[str, set[str]] = {
    DossierStatut.BROUILLON:   {DossierStatut.EN_COLLECTE},
    DossierStatut.EN_COLLECTE: {DossierStatut.EN_ANALYSE},
    DossierStatut.EN_ANALYSE:  {DossierStatut.INCOMPLET, DossierStatut.COMPLET},
    DossierStatut.INCOMPLET:   {DossierStatut.EN_COLLECTE, DossierStatut.COMPLET},
    DossierStatut.COMPLET:     {DossierStatut.SOUMIS},
    DossierStatut.SOUMIS:      {DossierStatut.CLOS},
    DossierStatut.CLOS:        set(),  # état terminal
}


class TransitionInvalide(Exception):
    pass


def can_transition(statut_actuel: str, statut_cible: str) -> bool:
    """Vérifie si la transition d'état est valide."""
    return statut_cible in _TRANSITIONS_VALIDES.get(statut_actuel, set())


def transition_dossier(
    dossier_id: str,
    statut_actuel: str,
    statut_cible: str,
    *,
    raison: str | None = None,
    utilisateur_id: str | None = None,
    canal: str | None = None,
    db_conn: Any,
) -> str:
    """
    Effectue une transition d'état du dossier.

    Args:
        dossier_id: ID du dossier
        statut_actuel: Statut courant
        statut_cible: Statut souhaité
        raison: Motif de la transition
        utilisateur_id: Acteur de la transition
        canal: Canal déclencheur

    Returns:
        Nouveau statut (= statut_cible si succès)

    Raises:
        TransitionInvalide: Si la transition est refusée
    """
    if not can_transition(statut_actuel, statut_cible):
        msg = (
            f"Transition invalide : {statut_actuel} → {statut_cible} "
            f"pour le dossier {dossier_id[:8]}"
        )
        logger.error(f"[STATE] {msg}")
        raise TransitionInvalide(msg)

    now = datetime.now(timezone.utc).isoformat()

    # Mise à jour de la base
    db_conn.execute(
        "UPDATE dossiers SET statut = ?, updated_at = ? WHERE id = ?",
        (statut_cible, now, dossier_id),
    )

    # Champs spéciaux selon l'état cible
    if statut_cible == DossierStatut.SOUMIS:
        db_conn.execute(
            "UPDATE dossiers SET soumis_le = ? WHERE id = ?",
            (now, dossier_id),
        )
    elif statut_cible == DossierStatut.CLOS:
        db_conn.execute(
            "UPDATE dossiers SET clos_le = ? WHERE id = ?",
            (now, dossier_id),
        )

    # Audit immuable
    log_event(
        f"DOSSIER_{statut_cible}",
        dossier_id=dossier_id,
        utilisateur_id=utilisateur_id,
        canal=canal,
        payload={
            "de":    statut_actuel,
            "vers":  statut_cible,
            "raison": raison,
        },
        db_conn=db_conn,
    )

    logger.info(
        f"[STATE] {statut_actuel} → {statut_cible}"
        f" | dossier={dossier_id[:8]}"
        + (f" | canal={canal}" if canal else "")
    )

    return statut_cible


def create_dossier(
    usager_id: str,
    departement_code: str,
    organisation_id: str | None = None,
    educateur_id: str | None = None,
    type_dossier: str = "INITIAL",
    db_conn: Any = None,
) -> str:
    """
    Crée un nouveau dossier MDPH en état BROUILLON.

    Returns:
        dossier_id
    """
    from app.security.encryption import generate_reference

    dossier_id  = str(uuid.uuid4())
    reference   = generate_reference("FAC-DOS")
    now         = datetime.now(timezone.utc).isoformat()

    db_conn.execute(
        """
        INSERT INTO dossiers
            (id, usager_id, organisation_id, educateur_id, reference,
             departement_code, type_dossier, statut, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'BROUILLON', ?, ?)
        """,
        (
            dossier_id, usager_id, organisation_id, educateur_id,
            reference, departement_code, type_dossier, now, now,
        ),
    )

    log_event(
        "DOSSIER_CREE",
        dossier_id=dossier_id,
        usager_id=usager_id,
        utilisateur_id=educateur_id,
        payload={
            "reference":        reference,
            "departement_code": departement_code,
            "type_dossier":     type_dossier,
        },
        db_conn=db_conn,
    )

    logger.info(
        f"[STATE] Dossier créé | id={dossier_id[:8]} | ref={reference} | dept={departement_code}"
    )
    return dossier_id


def update_scoring(
    dossier_id: str,
    score: int,
    confiance: float,
    droits_identifies: list[str],
    flag_humain: bool,
    raison_flag: str | None,
    db_conn: Any,
) -> None:
    """Met à jour le scoring d'un dossier après analyse."""
    now = datetime.now(timezone.utc).isoformat()
    db_conn.execute(
        """
        UPDATE dossiers SET
            score_completude      = ?,
            score_confiance       = ?,
            droits_identifies_json = ?,
            flag_humain_requis    = ?,
            raison_flag           = ?,
            updated_at            = ?
        WHERE id = ?
        """,
        (
            score,
            confiance,
            json.dumps(droits_identifies, ensure_ascii=False),
            1 if flag_humain else 0,
            raison_flag,
            now,
            dossier_id,
        ),
    )


def create_flag_humain(
    dossier_id: str,
    raison: str,
    educateur_id: str | None,
    severite: str = "HAUTE",
    db_conn: Any = None,
) -> str:
    """Crée un flag human-in-the-loop pour validation obligatoire."""
    alerte_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    db_conn.execute(
        """
        UPDATE dossiers SET
            flag_humain_requis = 1,
            raison_flag        = ?,
            updated_at         = ?
        WHERE id = ?
        """,
        (raison, now, dossier_id),
    )

    db_conn.execute(
        """
        INSERT INTO alertes
            (id, dossier_id, destinataire_id, type_alerte, severite, titre, description, created_at)
        VALUES (?, ?, ?, 'FLAG_HUMAIN', ?, 'Validation humaine requise', ?, ?)
        """,
        (alerte_id, dossier_id, educateur_id, severite, raison, now),
    )

    log_event(
        "FLAG_HUMAIN_CREE",
        dossier_id=dossier_id,
        utilisateur_id=educateur_id,
        payload={"raison": raison, "severite": severite},
        db_conn=db_conn,
    )

    logger.warning(
        f"[STATE] FLAG HUMAIN | dossier={dossier_id[:8]} | raison={raison[:80]}"
    )
    return alerte_id
