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
    Champs APPLICABLES au profil, obligatoires, et NON fournis. Chacun est rendu
    VISIBLE avec son état — 'en_attente' (à reposer à l'usager), 'a_completer_pro'
    (l'usager ne sait pas → au professionnel) ou 'refuse' (refus explicite). On ne
    masque AUCUN champ exigé : un champ délégué ou refusé reste signalé au pro.
    """
    from app.services.collecte_schema import checklist_for, condition_remplie, criticite_champ
    from app.services.field_status import statut_champ

    pts: list[dict[str, Any]] = []
    for item in checklist_for(profil):
        if not item.get("requis", True):
            continue
        cid = item["id"]
        if not condition_remplie(donnees, item.get("condition")):
            continue  # condition non remplie → champ non applicable ici
        etat = statut_champ(donnees, cid)
        if etat == "fourni":
            continue
        pts.append({
            "id": cid,
            "label": item.get("label", cid),
            "etat": etat,                       # en_attente | a_completer_pro | refuse
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

    # 3 bis. Certificat médical : pièce obligatoire et de moins d'un an pour la MDPH.
    _cert = str(donnees.get("certificat_medical_date", "") or "").strip().lower()
    if not _cert:
        alertes.append({
            "niveau": "ORANGE",
            "label": ("Aucun certificat médical n'est signalé. La MDPH exige un certificat "
                      "médical (cerfa 15695) de moins d'un an pour instruire la demande."),
        })
    else:
        import re as _re
        from datetime import datetime as _dt
        _sans_cert = any(w in _cert for w in ("non", "pas de", "aucun", "sans"))
        # N'extraire l'année QUE depuis une VRAIE date (JJ/MM/AAAA ou MM/AAAA),
        # jamais depuis un millésime isolé noyé dans une phrase (« médecin qui me
        # suit depuis 2015 ») : sinon fausse alerte « plus d'un an » sur un
        # certificat pourtant récent.
        _md = _re.search(r"\b(?:\d{1,2}[/\-.])?\d{1,2}[/\-.]((?:19|20)\d{2})\b", _cert)
        _annee_cert = int(_md.group(1)) if _md else None
        if _sans_cert:
            alertes.append({
                "niveau": "ORANGE",
                "label": ("La personne indique ne pas avoir de certificat médical. Il faudra "
                          "en obtenir un (cerfa 15695, moins d'un an) avant la transmission."),
            })
        elif _annee_cert is not None and (_dt.now().year - _annee_cert) > 1:
            alertes.append({
                "niveau": "ORANGE",
                "label": (f"Le certificat médical daterait de {_annee_cert} : possiblement de plus "
                          f"d'un an. La MDPH exige un certificat de moins d'un an, à vérifier."),
            })

    # 3 ter. Cohérence âge ↔ droit (page 17). Avant 20 ans c'est l'AEEH, à partir
    #        de 20 ans l'AAH : une demande hors tranche est une faute classique
    #        (une demande qui ne produira aucune case cochable sur le CERFA).
    _droits_txt = ""
    if isinstance(droits, str):
        _droits_txt = droits.upper()
    elif isinstance(droits, dict):
        _droits_txt = " ".join(k.upper() for k, v in droits.items() if v)
    elif isinstance(droits, (list, tuple)):
        _droits_txt = " ".join(str(d).upper() for d in droits)

    _age = None
    _ddn = str(donnees.get("date_naissance", "") or "").strip()
    try:
        if _ddn and "/" in _ddn:
            from datetime import date as _date
            _jj, _mm, _aa = _ddn.split("/")
            _age = (_date.today() - _date(int(_aa), int(_mm), int(_jj))).days // 365
    except Exception:
        _age = None

    if _age is not None and "AAH" in _droits_txt and _age < 20:
        alertes.append({
            "niveau": "ROUGE",
            "label": (f"AAH demandée mais la personne a {_age} ans (moins de 20) : avant "
                      "20 ans, c'est l'AEEH qui s'applique, pas l'AAH."),
        })
    if _age is not None and "AEEH" in _droits_txt and _age >= 20:
        alertes.append({
            "niveau": "ROUGE",
            "label": (f"AEEH demandée mais la personne a {_age} ans (20 ou plus) : à partir "
                      "de 20 ans, c'est l'AAH qui s'applique, pas l'AEEH."),
        })

    # 3 quater. Une AAH oblige la MDPH à évaluer la RQTH + l'orientation pro :
    #           le volet professionnel (section D) doit être renseigné.
    if "AAH" in _droits_txt and (_age is None or _age >= 20):
        _a_volet_pro = ("RQTH" in _droits_txt) or any(
            str(donnees.get(k, "") or "").strip()
            for k in ("projet_professionnel", "situation_professionnelle", "statut_emploi")
        )
        if not _a_volet_pro:
            alertes.append({
                "niveau": "ORANGE",
                "label": ("Une AAH est demandée : la MDPH évalue alors obligatoirement la "
                          "RQTH et l'orientation professionnelle. Le volet professionnel "
                          "(section D) doit être renseigné."),
            })

    # 3 quinquies. CMI demandée sans préciser le type → aucune case cochable.
    _cmi_type = (
        donnees.get("cmi_priorite") or donnees.get("cmi_invalidite")
        or donnees.get("cmi_stationnement")
    )
    if "CMI" in _droits_txt and not _cmi_type and not any(
        t in _droits_txt for t in ("INVALIDITE", "PRIORITE", "STATIONNEMENT")
    ):
        alertes.append({
            "niveau": "ORANGE",
            "label": ("Une CMI est demandée sans préciser le type (invalidité/priorité ou "
                      "stationnement) : aucune case ne pourra être cochée. À qualifier."),
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


def validite_dossier(donnees: dict[str, Any], profil: str) -> dict[str, Any]:
    """
    Validité MÉTIER d'un dossier (« ouvre des droits »), distincte du taux de
    remplissage. Conforme à la cartographie : un dossier est « prêt » seulement si
      - au moins une demande de droit est exprimée,
      - toute orientation professionnelle est justifiée (projet renseigné, page 16),
      - aucune donnée critique refusée ne bloque la finalisation.
    (La fidélité du récit et l'absence de données prescripteur sont garanties en
     amont : garde-fou anti-invention du narratif et cloisonnement à l'extraction.)
    Retourne {"pret": bool, "criteres": {...}, "manquants": [str]}.
    """
    droits = donnees.get("droits_demandes") or donnees.get("droits")
    droits_txt = ""
    if isinstance(droits, str):
        droits_txt = droits.upper()
    elif isinstance(droits, dict):
        droits_txt = " ".join(k.upper() for k, v in droits.items() if v)
    elif isinstance(droits, (list, tuple)):
        droits_txt = " ".join(str(d).upper() for d in droits)

    au_moins_une_demande = bool(droits_txt.strip())

    _orient_tokens = ("ORIENTATION PROFESSIONNELLE", "ORIENTATION PRO", "RQTH",
                      "CRP", "ESRP", "CPO", "ESPO", "UEROS", "ESAT", "RECLASSEMENT")
    orientation_demandee = any(t in droits_txt for t in _orient_tokens)
    _a_projet = any(
        str(donnees.get(k, "") or "").strip()
        for k in ("projet_professionnel", "projet_orientation", "situation_professionnelle")
    )
    orientation_justifiee = (not orientation_demandee) or _a_projet

    try:
        from app.services.field_status import finalisation_bloquee, statut_champ
        from app.services.conversation.base import CHAMPS_COEUR_SOLIDITE
        pas_de_blocage = not finalisation_bloquee(donnees)
        # Dossier SOLIDE : le cœur substantiel (retentissement + attentes + projet)
        # est réellement FOURNI — pas vide, pas seulement délégué/refusé. Empêche
        # qu'un dossier creux (« une demande et rien d'autre ») passe en « prêt ».
        coeur_manquant = [c for c in CHAMPS_COEUR_SOLIDITE
                          if statut_champ(donnees, c) != "fourni"]
        dossier_solide = not coeur_manquant
    except Exception:
        pas_de_blocage = True
        dossier_solide = True
        coeur_manquant = []

    manquants: list[str] = []
    if not au_moins_une_demande:
        manquants.append("aucune demande de droit exprimée")
    if not orientation_justifiee:
        manquants.append("orientation professionnelle non justifiée (projet à préciser, page 16)")
    if not pas_de_blocage:
        manquants.append("un champ critique a été refusé (finalisation bloquée)")
    if not dossier_solide:
        manquants.append("cœur du dossier incomplet (retentissement / attentes / projet) : "
                         + ", ".join(coeur_manquant))

    return {
        "pret": (au_moins_une_demande and orientation_justifiee
                 and pas_de_blocage and dossier_solide),
        "criteres": {
            "au_moins_une_demande": au_moins_une_demande,
            "orientation_justifiee": orientation_justifiee,
            "pas_de_blocage": pas_de_blocage,
            "dossier_solide": dossier_solide,
        },
        "manquants": manquants,
    }


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
    validite = validite_dossier(donnees, profil)
    _risque_eleve = expert.get("risque_global") == "élevé"
    if not pts and not coherence and not _risque_eleve and not expert.get("incoherences_critiques"):
        logger.info("[REVUE] dossier=%s : aucun point d'attention", dossier_id)
        return {"points": [], "coherence": [], "bloquants": 0, "expert": expert, "validite": validite}

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
            # Ne reposer à la famille QUE les champs encore en attente (ni refusés,
            # ni délégués au pro) — ces derniers restent visibles côté professionnel.
            _a_reposer = [p for p in pts if p.get("etat") == "en_attente"]
            manquants = ", ".join(p["label"] for p in _a_reposer[:6])
            if manquants:  # rien à reposer à la famille → pas de message
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
        "validite": validite,
    }
