"""
app/engines/revue_instructeur.py — Revue « instructeur senior » du dossier MDPH.

Relit le dossier prêt avec un regard critique, comme un instructeur MDPH le ferait :
  - repère les champs APPLICABLES au profil mais restés VIDES (jamais inventés) ;
  - distingue les champs critiques (bloquants) des champs simplement signalés ;
  - produit des POINTS D'ATTENTION, routés vers le professionnel (alerte tableau de
    bord) et, en option, vers la famille (message bienveillant WhatsApp).

CADRE (garde-fous) :
  - Lecture seule : ne modifie JAMAIS le dossier ni le CERFA.
  - Ne décide JAMAIS des droits ni de l'éligibilité.
  - N'invente RIEN : signale ce qui manque, ne le comble pas.
  - La validation humaine reste obligatoire ; aucun envoi automatique à la MDPH.

v1 : 100 % déterministe (aucun appel LLM) — fiable, gratuit, instantané. Les
jugements plus fins (qualité d'une justification) viendront s'y greffer ensuite,
via les moteurs experts déjà présents (comité d'agents, agent qualité CERFA).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("facilim.engines.revue_instructeur")

TYPE_ALERTE = "REVUE_INSTRUCTEUR"


def points_d_attention(donnees: dict[str, Any], profil: str) -> list[dict[str, Any]]:
    """
    Champs APPLICABLES au profil (via le dictionnaire CERFA), obligatoires, mais
    restés vides et non refusés. Un champ refusé est déjà traité par ailleurs.
    """
    from app.services.collecte_schema import checklist_for, criticite_champ
    from app.services.field_status import est_refuse

    pts: list[dict[str, Any]] = []
    for item in checklist_for(profil):
        if not item.get("requis", True):
            continue
        cid = item["id"]
        cond = item.get("condition")
        if cond:
            val = str(donnees.get(cond["champ"], "")).lower()
            if not val.startswith(str(cond["valeur"]).lower()):
                continue  # condition non remplie → champ non applicable ici
        if est_refuse(donnees, cid):
            continue
        if not donnees.get(cid):
            pts.append({
                "id": cid,
                "label": item.get("label", cid),
                "bloquant": criticite_champ(cid) == "bloquant",
            })
    return pts


def revue_dossier(
    donnees: dict[str, Any],
    profil: str,
    dossier_id: str,
    db: Any | None = None,
    wa: Any | None = None,
    phone: str | None = None,
    notifier_famille: bool = False,
) -> dict[str, Any]:
    """
    Lance la revue. Crée une alerte professionnel s'il y a des points d'attention,
    et (optionnellement) un message bienveillant à la famille. Non bloquant.
    Retourne {"points": [...], "bloquants": n}.
    """
    pts = points_d_attention(donnees, profil)
    if not pts:
        logger.info("[REVUE] dossier=%s : aucun point d'attention", dossier_id)
        return {"points": [], "bloquants": 0}

    bloquants = [p for p in pts if p["bloquant"]]

    # 1. Alerte au professionnel (tableau de bord) — réutilise la table `alertes`
    try:
        if db is not None:
            libelles = " ; ".join(p["label"] for p in pts[:12])
            description = f"Points à compléter avant dépôt : {libelles}"
            severite = "HAUTE" if bloquants else "NORMALE"
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
                    f"Revue instructeur : {len(pts)} point(s) d'attention",
                    description,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
    except Exception as e:
        logger.warning("[REVUE] alerte pro échouée : %s", e)

    # 2. Message bienveillant à la famille (optionnel)
    if notifier_famille and wa is not None and phone:
        try:
            manquants = ", ".join(p["label"] for p in pts[:6])
            msg = (
                "Avant de finaliser votre dossier, j'attire votre attention sur quelques "
                "informations encore manquantes qui pourraient peser sur son traitement : "
                f"{manquants}. Vous pouvez les compléter quand vous le souhaitez, "
                "et un professionnel vérifiera l'ensemble."
            )
            wa.send_text(phone, msg, dossier_id=dossier_id, db_conn=db)
        except Exception as e:
            logger.warning("[REVUE] message famille échoué : %s", e)

    logger.info(
        "[REVUE] dossier=%s : %d point(s), %d bloquant(s)",
        dossier_id, len(pts), len(bloquants),
    )
    return {"points": pts, "bloquants": len(bloquants)}
