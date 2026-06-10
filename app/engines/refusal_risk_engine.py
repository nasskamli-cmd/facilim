"""
app/engines/refusal_risk_engine.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FACILIM 90 — Moteur de risque de refus

Pour chaque droit demandé, évalue :
  - risque de refus : faible / moyen / élevé
  - pièces manquantes spécifiques
  - incohérences détectées
  - justification du niveau de risque

Usage :
  from app.engines.refusal_risk_engine import evaluer_risques_refus
  rapport = evaluer_risques_refus(donnees, profil_mdph="adulte")
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("facilim.engines.refusal_risk")


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RisqueDroit:
    droit:              str
    label:              str
    niveau_risque:      str     # "faible" | "moyen" | "élevé"
    justification:      str
    pieces_manquantes:  list[str]
    points_forts:       list[str]
    points_faibles:     list[str]
    conseils:           list[str]

    def to_dict(self) -> dict:
        return {
            "droit":            self.droit,
            "label":            self.label,
            "risque":           self.niveau_risque,
            "justification":    self.justification,
            "pieces_manquantes":self.pieces_manquantes,
            "points_forts":     self.points_forts,
            "points_faibles":   self.points_faibles,
            "conseils":         self.conseils[:2],
        }


@dataclass
class Incoherence:
    type_incoherence:   str
    droit_concerne:     str
    description:        str
    gravite:            str     # "critique" | "importante" | "mineure"
    resolution:         str

    def to_dict(self) -> dict:
        return {
            "type":         self.type_incoherence,
            "droit":        self.droit_concerne,
            "description":  self.description,
            "gravite":      self.gravite,
            "resolution":   self.resolution,
        }


@dataclass
class RapportRisques:
    risques_par_droit:  list[RisqueDroit]
    incoherences:       list[Incoherence]
    risque_global:      str     # "faible" | "moyen" | "élevé"
    nb_risques_eleves:  int
    nb_incoherences:    int

    def to_dict(self) -> dict:
        return {
            "risques":          [r.to_dict() for r in self.risques_par_droit],
            "incoherences":     [i.to_dict() for i in self.incoherences],
            "risque_global":    self.risque_global,
            "nb_eleves":        self.nb_risques_eleves,
            "nb_incoherences":  self.nb_incoherences,
        }


# ─────────────────────────────────────────────────────────────────────────────
# RÈGLES DE RISQUE PAR DROIT
# ─────────────────────────────────────────────────────────────────────────────

def _texte_analyse(donnees: dict) -> str:
    champs = [
        "diagnostics", "traitements", "impact_quotidien", "restrictions_emploi",
        "statut_emploi", "notes_pro", "texte_b_vie_quotidienne",
        "texte_d_situation_pro", "texte_e_projet_vie",
    ]
    return " ".join(str(donnees.get(c, "") or "") for c in champs).lower()


def _a_certificat(donnees: dict) -> bool:
    """Existence du certificat médical (le diagnostic/taux y vivent, pas dans Facilim)."""
    return bool(str(donnees.get("certificat_medical_date", "") or "").strip())


def _a_retentissement_fonctionnel(donnees: dict) -> bool:
    """
    Le RETENTISSEMENT FONCTIONNEL réellement collecté par Facilim (médical hors CERFA).
    La MDPH évalue ça, pas le diagnostic : besoins AVQ, impact quotidien, aides en place.
    """
    try:
        from app.services.collecte_schema import AVQ_CHAMPS, AVQ_BESOIN_AIDE
        if any(str(donnees.get(c, "") or "").strip().upper() in AVQ_BESOIN_AIDE for c in AVQ_CHAMPS):
            return True
    except Exception:
        pass
    txt = " ".join(str(donnees.get(c, "") or "") for c in (
        "impact_quotidien", "aides_en_place", "texte_b_vie_quotidienne",
        "restrictions_emploi", "difficultes_quotidiennes")).strip()
    return len(txt) > 20


def _risque_rqth(donnees: dict, texte: str) -> RisqueDroit:
    forts, faibles, pieces = [], [], []

    has_certif = _a_certificat(donnees)
    has_impact_emploi = bool(re.search(r"(restriction|impact|inaptitude|limitation).{0,20}(emploi|travail|poste)", texte))
    has_at = bool(re.search(r"accident.{0,15}travail|\bAT\b", texte))
    has_statut = bool(donnees.get("statut_emploi", ""))
    has_medecin_travail = bool(re.search(r"m[eé]decin.{0,10}travail|aptitude|inaptitude", texte))

    # Médical HORS CERFA : on n'exige PAS un diagnostic dans le dossier — on vérifie la
    # présence du CERTIFICAT (qui le porte), et on évalue le retentissement fonctionnel.
    if has_certif: forts.append("Certificat médical signalé")
    else: faibles.append("Certificat médical non signalé"); pieces.append("Certificat médical (cerfa 15695, < 1 an)")

    if has_impact_emploi: forts.append("Impact professionnel documenté")
    else: faibles.append("Impact sur l'emploi non objectivé"); pieces.append("Description limitations au travail")

    if has_statut: forts.append("Situation professionnelle renseignée")
    if has_medecin_travail: forts.append("Médecin du travail référencé")
    else: pieces.append("Avis/fiche médecin du travail (si en poste)")

    retraite = bool(re.search(r"retraite|plus de 62 ans", texte))
    if retraite: faibles.append("Retraite mentionnée — RQTH peu pertinente")

    score_forts = len(forts)
    if score_forts >= 3 and not retraite:
        risque = "faible"
        justif = "Impact professionnel documenté avec diagnostic — dossier solide"
    elif score_forts >= 2:
        risque = "moyen"
        justif = "Éléments partiels — renforcer l'objectivation de l'impact emploi"
    else:
        risque = "élevé"
        justif = "Impact emploi insuffisamment documenté — risque de refus RQTH"

    return RisqueDroit(
        droit="RQTH", label="Reconnaissance Qualité Travailleur Handicapé",
        niveau_risque=risque, justification=justif,
        pieces_manquantes=pieces[:3], points_forts=forts, points_faibles=faibles,
        conseils=["Joindre lettre médecin du travail", "Décrire les tâches impossibles"] if risque != "faible" else [],
    )


def _risque_aah(donnees: dict, texte: str) -> RisqueDroit:
    forts, faibles, pieces = [], [], []

    has_retentissement = _a_retentissement_fonctionnel(donnees)
    has_certif = _a_certificat(donnees)
    has_invalidite = bool(re.search(r"invalidit[eé]|pension d.invalidit[eé]|inapte", texte))
    has_restriction_emploi = bool(re.search(r"(restriction|inaptitude|impossib|ne peut plus|fatigab).{0,25}(emploi|travail|poste|activit)", texte))
    travaille = bool(re.search(r"travaille.{0,20}(actuellement|temps plein|CDI active)", texte))

    # AAH : la MDPH apprécie un taux >= 80 %, OU 50-79 % + restriction substantielle et
    # durable d'accès à l'emploi (RSDAE). Le TAUX est évalué par la MDPH d'après le
    # CERTIFICAT — Facilim ne le connaît pas et ne le réclame pas dans le dossier. Ce que
    # Facilim doit objectiver, c'est le RETENTISSEMENT FONCTIONNEL et la restriction d'emploi.
    if has_retentissement:
        forts.append("Retentissement fonctionnel documenté")
    else:
        faibles.append("Retentissement trop mince au regard de l'AAH")
        pieces.append("Décrire le retentissement au quotidien (besoins d'aide, activités empêchées)")

    if has_restriction_emploi or has_invalidite:
        forts.append("Restriction d'accès à l'emploi / invalidité documentée (favorable RSDAE)")
    else:
        faibles.append("Restriction substantielle et durable d'accès à l'emploi non objectivée (critère RSDAE 50-79 %)")

    if has_certif:
        forts.append("Certificat médical signalé")
    else:
        pieces.append("Certificat médical (cerfa 15695) — il porte le taux d'incapacité évalué par la MDPH")

    pieces.append("Avis d'imposition ou de non-imposition (ressources)")

    if travaille:
        faibles.append("Activité professionnelle actuelle — vérifier compatibilité ressources AAH")

    score_forts = len(forts)
    if score_forts >= 2 and has_retentissement:
        risque = "faible"
        justif = "Retentissement fonctionnel objectivé — dossier AAH crédible (la MDPH fixe le taux d'après le certificat)"
    elif has_retentissement:
        risque = "moyen"
        justif = "Retentissement présent mais restriction d'accès à l'emploi à objectiver (critère RSDAE)"
    else:
        risque = "élevé"
        justif = "Retentissement trop mince au regard de l'AAH — risque élevé de refus"

    return RisqueDroit(
        droit="AAH", label="Allocation aux Adultes Handicapés",
        niveau_risque=risque, justification=justif,
        pieces_manquantes=pieces[:3], points_forts=forts, points_faibles=faibles,
        conseils=["Étoffer le retentissement (activités empêchées, aides au quotidien)",
                  "Objectiver la restriction d'accès à l'emploi"] if risque != "faible" else [],
    )


def _risque_pch(donnees: dict, texte: str) -> RisqueDroit:
    forts, faibles, pieces = [], [], []

    has_aide_humaine = bool(re.search(r"aide.{0,20}(toilette|douche|matin|corps|hygi[eè]ne|habillage)", texte))
    has_avq = bool(re.search(r"tierce personne|aide quotidienne|fauteuil roulant|d[eé]pendance", texte))
    has_quantifie = bool(re.search(r"\d+.{0,10}(fois|heures?).{0,10}(par semaine|quotidien)", texte))
    has_autonomie_ok = bool(re.search(r"autonome|indépendant|se débrouille|vie seul.{0,20}sans aide", texte))

    if has_aide_humaine:
        forts.append("Besoin d'aide humaine pour soins corporels documenté")
    else:
        faibles.append("Aucune mention d'aide humaine pour les AVQ")
        pieces.append("Description des actes nécessitant aide (toilette, lever, alimentation...)")

    if has_avq:
        forts.append("Dépendance ou aide technique documentée")

    if has_quantifie:
        forts.append("Fréquence de l'aide quantifiée — favorable pour barème PCH")
    else:
        pieces.append("Fréquence hebdomadaire des aides (ex: aide 5x/semaine)")

    if has_autonomie_ok:
        faibles.append("Autonomie mentionnée — vérifier compatibilité avec demande PCH")

    pieces.append("Devis prestataire aide à domicile ou attestation d'aide actuelle")

    score_forts = len(forts)
    if score_forts >= 2 and not has_autonomie_ok:
        risque = "faible"
        justif = "Besoins d'aide documentés — dossier PCH crédible"
    elif score_forts >= 1:
        risque = "moyen"
        justif = "Aide humaine partiellement documentée — quantifier les actes et fréquences"
    else:
        risque = "élevé"
        justif = "PCH demandée sans preuve de besoin d'aide — risque de refus très élevé"

    return RisqueDroit(
        droit="PCH", label="Prestation de Compensation du Handicap",
        niveau_risque=risque, justification=justif,
        pieces_manquantes=pieces[:3], points_forts=forts, points_faibles=faibles,
        conseils=["Décrire actes AVQ impossibles seul", "Quantifier les besoins"] if risque != "faible" else [],
    )


def _risque_aeeh(donnees: dict, texte: str, profil_mdph: str) -> RisqueDroit:
    forts, faibles, pieces = [], [], []

    has_certif = _a_certificat(donnees)
    has_retentissement = _a_retentissement_fonctionnel(donnees)
    has_aesh = bool(re.search(r"AESH|AVS|tiers.?temps", texte, re.I))
    has_sessad = bool(re.search(r"SESSAD|suivi sp[eé]cialis[eé]", texte, re.I))
    has_gevasco = bool(re.search(r"GEVASCO|évaluation scolaire", texte, re.I))
    is_adulte = profil_mdph in ("adulte",)

    if is_adulte:
        faibles.append("AEEH demandée pour un profil adulte — incohérence majeure")

    # Médical hors CERFA : certificat (qui porte le diagnostic) + retentissement scolaire.
    if has_certif: forts.append("Certificat médical signalé")
    else: faibles.append("Certificat médical non signalé"); pieces.append("Certificat médical pédiatrique (cerfa 15695)")
    if has_retentissement: forts.append("Retentissement documenté")

    if has_aesh: forts.append("AESH ou tiers-temps documenté")
    else: pieces.append("Attestation AESH et nombre d'heures")

    if has_gevasco: forts.append("GEVASCO présent")
    else: pieces.append("GEVASCO (guide évaluation scolaire) — obligatoire")

    if has_sessad: forts.append("SESSAD référencé")

    if is_adulte:
        risque = "élevé"
        justif = "AEEH ne peut être attribuée qu'à une personne < 20 ans — incohérence de profil"
    elif len(forts) >= 2:
        risque = "faible"
        justif = "Retentissement scolaire et aménagements documentés — dossier AEEH solide"
    elif len(forts) >= 1:
        risque = "moyen"
        justif = "Éléments partiels — GEVASCO et AESH à compléter"
    else:
        risque = "élevé"
        justif = "AEEH sans preuves — GEVASCO et retentissement scolaire à objectiver"

    return RisqueDroit(
        droit="AEEH", label="Allocation Éducation Enfant Handicapé",
        niveau_risque=risque, justification=justif,
        pieces_manquantes=pieces[:3], points_forts=forts, points_faibles=faibles,
        conseils=["Joindre GEVASCO récent", "Attestation AESH"] if risque != "faible" else [],
    )


def _risque_cmi_stationnement(donnees: dict, texte: str) -> RisqueDroit:
    forts, faibles, pieces = [], [], []

    has_marche = bool(re.search(r"march.{0,20}(limit[eé]e?|difficile|\d+.{0,5}m[eè]tres?)", texte))
    has_aide_mobilite = bool(re.search(r"fauteuil roulant|canne|b[eé]quille|d[eé]ambulateur", texte))
    has_mesure = bool(re.search(r"\d+.{0,5}m[eè]tres?|p[eé]rim[eè]tre", texte))

    if has_marche: forts.append("Limitation de marche documentée")
    else: faibles.append("Limitation de marche non précisée"); pieces.append("Certificat médical avec périmètre de marche")

    if has_aide_mobilite: forts.append("Aide à la mobilité documentée")
    if has_mesure: forts.append("Distance de marche quantifiée — critère fort")
    else: pieces.append("Distance de marche précise (ex: < 200m)")

    risque = "faible" if len(forts) >= 2 else ("moyen" if len(forts) >= 1 else "élevé")
    justif = (
        "Marche objectivée — CMI stationnement solide" if risque == "faible" else
        "Distance de marche à préciser médicalement" if risque == "moyen" else
        "CMI sans preuve de limitation de marche"
    )

    return RisqueDroit(
        droit="CMI_STATIONNEMENT", label="CMI Stationnement",
        niveau_risque=risque, justification=justif,
        pieces_manquantes=pieces[:2], points_forts=forts, points_faibles=faibles,
        conseils=["Préciser la distance de marche en mètres"] if risque != "faible" else [],
    )


# ─────────────────────────────────────────────────────────────────────────────
# DÉTECTION DES INCOHÉRENCES
# ─────────────────────────────────────────────────────────────────────────────

def _detecter_incoherences(donnees: dict, profil_mdph: str, texte: str) -> list[Incoherence]:
    incoherences: list[Incoherence] = []
    droits = str(donnees.get("droits_demandes", "") or "").upper()

    # AEEH pour adulte
    if "AEEH" in droits and profil_mdph in ("adulte",):
        incoherences.append(Incoherence(
            type_incoherence="DROIT_PROFIL_INCOMPATIBLE",
            droit_concerne="AEEH",
            description="AEEH demandée pour un profil adulte — l'AEEH est réservée aux enfants < 20 ans",
            gravite="critique",
            resolution="Supprimer AEEH du dossier adulte. Si enfant dans le foyer, créer un dossier séparé.",
        ))

    # AAH + emploi temps plein actif
    if "AAH" in droits and re.search(r"travaille.{0,20}(actuellement|temps plein|en activité)", texte):
        incoherences.append(Incoherence(
            type_incoherence="RESSOURCES_INCOHERENTES",
            droit_concerne="AAH",
            description="AAH demandée mais activité professionnelle à temps plein mentionnée — vérifier compatibilité ressources",
            gravite="importante",
            resolution="Préciser le type d'emploi et les revenus. L'AAH est soumise à condition de ressources.",
        ))

    # PCH + autonomie complète déclarée
    if "PCH" in droits and re.search(r"(totalement|complètement|pleinement) autonome|vie seul.{0,20}sans aucune aide", texte):
        incoherences.append(Incoherence(
            type_incoherence="NEED_CONTRADICTION",
            droit_concerne="PCH",
            description="PCH demandée mais autonomie complète mentionnée — contradiction",
            gravite="critique",
            resolution="Clarifier : soit documenter les actes nécessitant aide, soit retirer la demande PCH.",
        ))

    # ESAT + projet milieu ordinaire prioritaire
    if "ESAT" in droits and re.search(r"milieu ordinaire.{0,30}(priorité|préférence|souhait)", texte):
        incoherences.append(Incoherence(
            type_incoherence="ORIENTATION_CONTRADICTOIRE",
            droit_concerne="ESAT",
            description="ESAT demandé mais milieu ordinaire mentionné comme priorité — à clarifier",
            gravite="importante",
            resolution="Préciser si l'orientation ESAT est une alternative ou le choix principal.",
        ))

    # MAS pour enfant
    if "MAS" in droits and profil_mdph in ("enfant",):
        incoherences.append(Incoherence(
            type_incoherence="DROIT_PROFIL_INCOMPATIBLE",
            droit_concerne="MAS",
            description="MAS (Maison d'Accueil Spécialisée) est réservée aux adultes ≥ 18 ans",
            gravite="critique",
            resolution="Pour un enfant polyhandicapé, l'orientation est EEAP et non MAS.",
        ))

    # RQTH + retraite
    if "RQTH" in droits and re.search(r"retraite.{0,20}(totale|définitive|depuis)", texte):
        incoherences.append(Incoherence(
            type_incoherence="DROIT_HORS_CONTEXTE",
            droit_concerne="RQTH",
            description="RQTH demandée alors que la retraite semble prise — RQTH peu utile en retraite",
            gravite="mineure",
            resolution="Vérifier si la personne est vraiment en retraite définitive. RQTH sert principalement en activité.",
        ))

    # AAH + PCH enfant (< 20 ans — AEEH compléments remplacent PCH)
    if "PCH" in droits and "AEEH" in droits and profil_mdph in ("enfant",):
        incoherences.append(Incoherence(
            type_incoherence="DOUBLE_PRESTATION",
            droit_concerne="PCH",
            description="PCH et AEEH demandées simultanément — non cumulables pour un même enfant (sauf transition 18-20 ans)",
            gravite="importante",
            resolution="Vérifier l'âge de l'enfant. AEEH pour < 20 ans, PCH pour ≥ 20 ans. Transition possible 18-20.",
        ))

    return incoherences


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────────────────────

_ANALYSEURS_DROITS = {
    "RQTH":              _risque_rqth,
    "AAH":               _risque_aah,
    "PCH":               _risque_pch,
    "CMI":               _risque_cmi_stationnement,
    "CMI_STATIONNEMENT": _risque_cmi_stationnement,
}


def evaluer_risques_refus(
    donnees: dict[str, Any],
    profil_mdph: str = "adulte",
) -> RapportRisques:
    """
    Évalue le risque de refus pour chaque droit demandé + détecte les incohérences.

    Returns:
        RapportRisques avec risques par droit et incohérences
    """
    texte = _texte_analyse(donnees)
    droits_raw = str(donnees.get("droits_demandes", "") or "").upper()
    droits_tokens = re.findall(r"[A-Z][A-Z_]+", droits_raw)

    risques: list[RisqueDroit] = []
    for tok in droits_tokens:
        analyseur = _ANALYSEURS_DROITS.get(tok)
        if analyseur:
            if tok == "AEEH":
                risques.append(_risque_aeeh(donnees, texte, profil_mdph))
            else:
                risques.append(analyseur(donnees, texte))
        else:
            # Droit sans analyseur spécifique — risque par défaut selon confiance
            risques.append(RisqueDroit(
                droit=tok, label=tok,
                niveau_risque="moyen",
                justification=f"{tok} demandé — vérifier les preuves spécifiques",
                pieces_manquantes=["Certificat médical récent"],
                points_forts=["Droit explicitement demandé"],
                points_faibles=[],
                conseils=[],
            ))

    # Toujours évaluer les droits fréquemment oubliés (si non demandés mais pertinents)
    if "AEEH" in droits_tokens and profil_mdph in ("enfant", "mixte"):
        if not any(r.droit == "AEEH" for r in risques):
            risques.append(_risque_aeeh(donnees, texte, profil_mdph))

    # Incohérences
    incoherences = _detecter_incoherences(donnees, profil_mdph, texte)

    # Risque global
    nb_eleves = sum(1 for r in risques if r.niveau_risque == "élevé")
    nb_incoher = len(incoherences)
    nb_critiques = sum(1 for i in incoherences if i.gravite == "critique")

    if nb_critiques > 0 or nb_eleves >= 2:
        risque_global = "élevé"
    elif nb_eleves >= 1 or nb_incoher >= 1:
        risque_global = "moyen"
    else:
        risque_global = "faible"

    return RapportRisques(
        risques_par_droit=sorted(risques, key=lambda r: {"faible": 2, "moyen": 1, "élevé": 0}[r.niveau_risque]),
        incoherences=incoherences,
        risque_global=risque_global,
        nb_risques_eleves=nb_eleves,
        nb_incoherences=nb_incoher,
    )
