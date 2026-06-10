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

from app.services.field_status import (
    est_a_completer_pro,
    est_refuse,
    marquer_a_completer_pro,
    marquer_refus,
    phrase_de_refus,
    phrase_ne_sait_pas,
)
from app.services.collecte_schema import criticite_champ

logger = logging.getLogger("facilim.services.refus")

TYPE_ALERTE = "CHAMP_NON_COMMUNIQUE"
TYPE_ALERTE_PRO = "CHAMP_A_COMPLETER_PRO"


def _message_famille(label: str) -> str:
    return (
        "Pas de souci, vous n'êtes pas obligé de répondre à cette question. "
        "Sachez simplement que cette information aide la MDPH à traiter votre dossier, "
        "et que son absence peut en ralentir l'étude. Nous continuons, et vous pourrez "
        "toujours la communiquer plus tard si vous le souhaitez."
    )


def _message_famille_delegue(label: str) -> str:
    return (
        "Pas de souci si vous n'avez pas cette information sous la main. Je la transmets "
        "au professionnel qui suit votre dossier : il pourra la compléter. On continue."
    )


def _creer_alerte_pro(db: Any, dossier_id: str, label: str, bloquant: bool,
                      motif: str = "refus") -> None:
    severite = "HAUTE" if bloquant else "NORMALE"
    if motif == "delegue":
        type_alerte = TYPE_ALERTE_PRO
        titre = f"Champ à compléter par le pro : {label}"
        description = (
            f"La personne ne dispose pas de l'information « {label} ». À compléter par le "
            "professionnel (document, dossier, vérification). "
            + ("Champ critique : finalisation à valider par le professionnel."
               if bloquant else "Information signalée — n'empêche pas la collecte.")
        )
    else:
        type_alerte = TYPE_ALERTE
        titre = f"Champ non communiqué : {label}"
        description = (
            f"La personne a préféré ne pas communiquer « {label} ». "
            + ("Champ critique : la finalisation du dossier reste à valider par le professionnel."
               if bloquant else "Information signalée — n'empêche pas la finalisation.")
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
            type_alerte,
            severite,
            titre,
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


def traiter_ne_sait_pas_eventuel(
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
    Si le message exprime « je ne sais pas » (absence d'information, distincte
    d'un refus), DÉLÈGUE le champ visé au professionnel (statut « à compléter par
    pro ») : on ne le repose plus à l'usager — ce qui évite les boucles et les
    abandons — mais il reste EXIGÉ et VISIBLE (alerte pro + synthèse de complétude).
    On n'invente jamais de valeur. Retourne l'id du champ délégué, ou None.
    """
    if not phrase_ne_sait_pas(text):
        return None

    cible = None
    for cid in (manquants_ids_avant or [])[:2]:
        if (not donnees.get(cid) and not est_refuse(donnees, cid)
                and not est_a_completer_pro(donnees, cid)):
            cible = cid
            break
    if not cible:
        return None

    label = id_to_label.get(cible, cible)
    bloquant = criticite_champ(cible) == "bloquant"

    marquer_a_completer_pro(donnees, cible, raison=text)

    try:
        _creer_alerte_pro(db, dossier_id, label, bloquant, motif="delegue")
    except Exception as e:
        logger.warning("[A_COMPLETER_PRO] création alerte pro échouée : %s", e)

    try:
        if wa is not None and phone_wa:
            wa.send_text(phone_wa, _message_famille_delegue(label),
                         dossier_id=dossier_id, db_conn=db)
    except Exception as e:
        logger.warning("[A_COMPLETER_PRO] envoi message famille échoué : %s", e)

    logger.info("[A_COMPLETER_PRO] champ=%s délégué pro bloquant=%s dossier=%s",
                cible, bloquant, dossier_id)
    return cible
