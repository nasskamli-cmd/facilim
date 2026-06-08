"""
app/services/refus_handler.py — Traitement d'un refus de champ par la famille.

Quand la famille refuse de communiquer un champ :
  1. on enregistre le statut « refusé » (jamais d'invention) ;
  2. on lui envoie un message bienveillant rappelant l'incidence possible ;
  3. on crée une alerte pour le professionnel dans le tableau de bord.

Aucune nouvelle table : l'alerte réutilise la table `alertes` existante.
Tout est non bloquant : une erreur ici n'interrompt jamais la conversation.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.services.field_status import phrase_de_refus, marquer_refus, est_refuse
from app.services.collecte_schema import criticite_champ

logger = logging.getLogger("facilim.services.refus")

TYPE_ALERTE = "CHAMP_NON_COMMUNIQUE"


def _message_famille(label: str) -> str:
    return (
        "Pas de souci, vous n'êtes pas obligé de répondre à cette question. "
        "Sachez simplement que cette information aide la MDPH à traiter votre dossier, "
        "et que son absence peut en ralentir l'étude. Nous continuons, et vous pourrez "
        "toujours la communiquer plus tard si vous le souhaitez."
    )


def _creer_alerte_pro(db: Any, dossier_id: str, label: str, bloquant: bool) -> None:
    severite = "HAUTE" if bloquant else "NORMALE"
    description = (
        f"La personne a préféré ne pas communiquer « {label} ». "
        + (
            "Champ critique : la finalisation du dossier reste à valider par le professionnel."
            if bloquant
            else "Information signalée — n'empêche pas la finalisation."
        )
    )
    db.execute(
        """
        INSERT INTO alertes
            (id, dossier_id, usager_id, destinataire_id, type_alerte, severite,
             titre, description, created_at, acquittee)
        VALUES (?, ?, NULL, NULL, ?, ?, ?, ?, ?, 0)
        """,
        (
            str(uuid.uuid4()),
            dossier_id,
            TYPE_ALERTE,
            severite,
            f"Champ non communiqué : {label}",
            description,
            datetime.now(timezone.utc).isoformat(),
        ),
    )


def traiter_refus_eventuel(
    donnees: dict[str, Any],
    text: str,
    manquants_ids_avant: list[str],
    id_to_label: dict[str, str],
    wa: Any,
    db: Any,
    dossier_id: str,
    phone_wa: str,
) -> str | None:
    """
    Si le message exprime un refus, marque le champ concerné, prévient la famille
    et alerte le professionnel. Retourne l'id du champ refusé, ou None.

    Le champ visé est le premier champ obligatoire qui venait d'être demandé
    (parmi `manquants_ids_avant`) et qui reste non renseigné.
    """
    if not phrase_de_refus(text):
        return None

    cible = None
    for cid in (manquants_ids_avant or [])[:2]:
        if not donnees.get(cid) and not est_refuse(donnees, cid):
            cible = cid
            break
    if not cible:
        return None

    label = id_to_label.get(cible, cible)
    bloquant = criticite_champ(cible) == "bloquant"

    # 1. Enregistrer le refus (la valeur du champ reste vide)
    marquer_refus(donnees, cible, text)

    # 2. Alerte professionnel (non bloquant)
    try:
        _creer_alerte_pro(db, dossier_id, label, bloquant)
    except Exception as e:
        logger.warning("[REFUS] création alerte pro échouée : %s", e)

    # 3. Message bienveillant à la famille (non bloquant)
    try:
        if wa is not None and phone_wa:
            wa.send_text(phone_wa, _message_famille(label),
                         dossier_id=dossier_id, db_conn=db)
    except Exception as e:
        logger.warning("[REFUS] envoi message famille échoué : %s", e)

    logger.info("[REFUS] champ=%s bloquant=%s dossier=%s", cible, bloquant, dossier_id)
    return cible
