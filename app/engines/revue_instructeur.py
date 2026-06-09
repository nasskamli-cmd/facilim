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


def controles_coherence(donnees: dict[str, Any], profil: str) -> list[dict[str, Any]]:
    """
    Contrôles de cohérence d'un instructeur senior, au niveau des DONNÉES
    (déterministe, sans LLM). Ce sont les « drapeaux rouges » classiques qui font
    rejeter ou affaiblir un dossier MDPH.
    """
    alertes: list[dict[str, Any]] = []
    diag    = str(donnees.get("diagnostics", "") or "").strip()
    impact  = str(donnees.get("impact_quotidien", "") or "").strip()
    droits  = donnees.get("droits_demandes") or donnees.get("droits")
    attentes = (
        str(donnees.get("attentes_usager", "") or "").strip()
        or str(donnees.get("projet_de_vie", "") or "").strip()
    )

    # 1. Diagnostic sans conséquence fonctionnelle — cause n°1 de refus.
    if diag and not impact:
        alertes.append({
            "niveau": "ROUGE",
            "label": ("Un diagnostic est indiqué mais aucune conséquence sur la vie "
                      "quotidienne n'est décrite. La MDPH évalue le retentissement, "
                      "pas le diagnostic seul."),
        })
    # 2. Aucune demande de droit → le dossier n'a pas d'objet.
    if not droits:
        alertes.append({
            "niveau": "ROUGE",
            "label": "Aucune demande de droit ou de prestation n'est renseignée.",
        })
    # 3. Projet de vie / attentes absents (section E).
    if not attentes:
        alertes.append({
            "niveau": "ORANGE",
            "label": ("Le projet de vie et les attentes vis-à-vis de la MDPH ne sont "
                      "pas exprimés (section E)."),
        })

    # 4. Donnée collectée mais à risque de ne pas être reportée sur le CERFA.
    #    Garantit qu'aucune information recueillie ne se perd silencieusement entre
    #    la collecte et le formulaire (jonction dictionnaire → remplissage).
    try:
        from app.services.cerfa_dictionary import champs_a_risque_de_perte
        for r in champs_a_risque_de_perte(donnees, profil):
            alertes.append({
                "niveau": "ROUGE",
                "label": (f"Information collectée non reportée sur le CERFA "
                          f"({r['id']}) : {r['raison']}. À vérifier avant transmission."),
            })
    except Exception as _e:
        logger.debug("[REVUE] contrôle de couverture non bloquant : %s", _e)

    return alertes


def analyses_expertes(donnees: dict[str, Any], profil: str) -> dict[str, Any]:
    """
    Réveille les deux moteurs experts, en LECTURE SEULE et sans décider des droits :
      - risque de refus par droit + incohérences (refusal_risk_engine)
      - robustesse du dossier sur 100 + axes d'amélioration (dossier_strength_engine)
    Tout est non bloquant : une erreur d'un moteur n'interrompt pas la revue.
    Retourne un dict consolidé, vide en cas d'indisponibilité.
    """
    out: dict[str, Any] = {
        "risque_global": "", "robustesse": None,
        "axes": [], "incoherences_critiques": [],
    }
    try:
        from app.engines.refusal_risk_engine import evaluer_risques_refus
        rr = evaluer_risques_refus(donnees, profil)
        out["risque_global"] = rr.risque_global
        out["incoherences_critiques"] = [
            i.description for i in rr.incoherences if i.gravite == "critique"
        ]
    except Exception as e:
        logger.debug("[REVUE] moteur risque de refus indisponible : %s", e)
    try:
        from app.engines.dossier_strength_engine import noter_robustesse
        rb = noter_robustesse(donnees, profil)
        out["robustesse"] = rb.score_global
        out["axes"] = list(rb.axes_amelioration or [])[:6]
    except Exception as e:
        logger.debug("[REVUE] moteur robustesse indisponible : %s", e)
    return out


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
    coherence = controles_coherence(donnees, profil)
    expert = analyses_expertes(donnees, profil)
    _risque_eleve = expert.get("risque_global") == "élevé"
    if not pts and not coherence and not _risque_eleve and not expert.get("incoherences_critiques"):
        logger.info("[REVUE] dossier=%s : aucun point d'attention", dossier_id)
        return {"points": [], "coherence": [], "bloquants": 0, "expert": expert}

    bloquants = [p for p in pts if p["bloquant"]]
    rouges = [c for c in coherence if c.get("niveau") == "ROUGE"]

    # 1. Alerte au professionnel (tableau de bord) — réutilise la table `alertes`
    try:
        if db is not None:
            parties = []
            if pts:
                parties.append("À compléter : " + " ; ".join(p["label"] for p in pts[:10]))
            if coherence:
                parties.append("Cohérence : " + " ; ".join(c["label"] for c in coherence[:6]))
            if expert.get("robustesse") is not None:
                parties.append(f"Robustesse estimée : {expert['robustesse']}/100")
            if expert.get("risque_global"):
                parties.append(f"Risque de refus : {expert['risque_global']}")
            if expert.get("incoherences_critiques"):
                parties.append("Incohérences : " + " ; ".join(expert["incoherences_critiques"][:4]))
            if expert.get("axes"):
                parties.append("Axes d'amélioration : " + " ; ".join(expert["axes"][:4]))
            description = " | ".join(parties)[:1000]
            severite = "HAUTE" if (bloquants or rouges or _risque_eleve
                                    or expert.get("incoherences_critiques")) else "NORMALE"
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
                    f"Revue instructeur : {len(pts) + len(coherence)} point(s) d'attention",
                    description,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
    except Exception as e:
        logger.warning("[REVUE] alerte pro échouée : %s", e)

    # 2. Message bienveillant à la famille (optionnel) — seulement sur les champs manquants
    if notifier_famille and wa is not None and phone and pts:
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
        "[REVUE] dossier=%s : %d champ(s) vide(s) (%d bloquant), %d cohérence (%d rouge)",
        dossier_id, len(pts), len(bloquants), len(coherence), len(rouges),
    )
    return {
        "points": pts,
        "coherence": coherence,
        "bloquants": len(bloquants) + len(rouges),
        "expert": expert,
    }
