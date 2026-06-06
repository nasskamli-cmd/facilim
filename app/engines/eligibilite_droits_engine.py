"""
app/engines/eligibilite_droits_engine.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FACILIM 60 — Moteur 1 : Éligibilité estimée aux droits MDPH

Analyse la compatibilité d'un dossier avec chacun des 22 droits MDPH.

RÈGLE ABSOLUE :
  Ce moteur ne décide jamais.
  Il signale des compatibilités probables.
  Toute conclusion est formulée avec "semble compatible avec",
  "pourrait relever de", "éléments compatibles avec", "à vérifier".

Usage :
  from app.engines.eligibilite_droits_engine import analyser_eligibilite
  resultat = analyser_eligibilite(donnees, profil_mdph="adulte", profil_handicap="moteur")
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

logger = logging.getLogger("facilim.engines.eligibilite")


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURES DE DONNÉES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AnalyseEligibilite:
    """Analyse de compatibilité pour un droit MDPH."""
    droit:                          str
    label:                          str
    applicable_profil:              bool    # Le droit est-il pertinent pour ce profil ?
    eligibilite_estimee:            int     # 0-100 (score de compatibilité, PAS une décision)
    niveau_confiance:               str     # "faible" | "moyenne" | "haute"
    forces:                         list[str]
    faiblesses:                     list[str]
    justificatifs_manquants:        list[str]
    questions_complementaires:      list[str]
    probabilite_estimee_obtention:  str     # "faible" | "moyenne" | "forte" | "très forte"
    signaux_detectes:               list[str]   # fragments de texte ayant déclenché
    droit_demande:                  bool    # Déjà dans droits_demandes ?


@dataclass
class ResultatEligibiliteComplete:
    """Résultat complet de l'analyse d'éligibilité pour tous les droits."""
    analyses:               dict[str, AnalyseEligibilite]
    droits_demandes:        list[str]
    droits_omis_probables:  list[str]   # Droits compatibles non demandés
    droits_non_applicables: list[str]
    synthese:               str


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _age_approx(date_naissance: str) -> int | None:
    """Calcule l'âge approximatif depuis une date de naissance JJ/MM/AAAA."""
    try:
        parts = date_naissance.replace("-", "/").split("/")
        if len(parts) == 3:
            annee = int(parts[2]) if len(parts[2]) == 4 else int(parts[0])
            return date.today().year - annee
    except Exception:
        pass
    return None


def _construire_texte(donnees: dict[str, Any]) -> str:
    """Construit un texte d'analyse complet depuis toutes les sources."""
    champs = [
        "diagnostics", "traitements", "impact_quotidien", "restrictions_emploi",
        "statut_emploi", "projet_orientation", "droits_demandes", "historique_mdph",
        "aidant_besoins", "notes_pro", "texte_b_vie_quotidienne", "texte_c_scolarite",
        "texte_d_situation_pro", "texte_e_projet_vie", "situation_scolaire",
        "expression_directe", "mode_vie", "type_protection",
    ]
    parties = []
    for c in champs:
        v = donnees.get(c)
        if v:
            parties.append(str(v))

    # Verbatims
    for c in ["_verbatim_b", "_verbatim_c", "_verbatim_d", "_verbatim_e"]:
        lst = donnees.get(c) or []
        if isinstance(lst, list):
            parties.extend(str(x) for x in lst)

    # Document knowledge
    dk = donnees.get("_document_knowledge") or {}
    for categorie in dk.values():
        if isinstance(categorie, list):
            for item in categorie:
                if isinstance(item, dict) and item.get("valeur"):
                    parties.append(str(item["valeur"]))

    return " ".join(parties).lower()


def _signal(texte: str, patterns: list[str]) -> tuple[bool, str]:
    """Détecte si un des patterns est présent, retourne (trouvé, fragment)."""
    for p in patterns:
        m = re.search(p, texte, re.IGNORECASE)
        if m:
            start = max(0, m.start() - 25)
            end = min(len(texte), m.end() + 40)
            return True, texte[start:end].strip()
    return False, ""


def _score_to_proba(score: int) -> str:
    if score >= 80: return "très forte"
    if score >= 60: return "forte"
    if score >= 35: return "moyenne"
    return "faible"


def _score_to_confiance(score: int, n_signaux_forts: int) -> str:
    if n_signaux_forts >= 3 and score >= 60: return "haute"
    if n_signaux_forts >= 1 and score >= 35: return "moyenne"
    return "faible"


def _droits_demandes_set(donnees: dict) -> set[str]:
    """Retourne l'ensemble des droits déjà demandés (normalisé)."""
    raw = str(donnees.get("droits_demandes", "") or "").upper()
    tokens = re.findall(r"[A-ZÉÈÊÀÂÎÔÛàâêîôûéèêÀÉ\-]+", raw)
    return set(tokens)


# ─────────────────────────────────────────────────────────────────────────────
# ANALYSEURS PAR DROIT
# ─────────────────────────────────────────────────────────────────────────────

def _analyser_aah(donnees: dict, texte: str, age: int | None,
                  profil_mdph: str, droits_set: set) -> AnalyseEligibilite:
    label = "Allocation aux Adultes Handicapés (AAH)"
    applicable = profil_mdph in ("adulte", "protege", "mixte")
    if not applicable or (age is not None and (age < 20 or age > 60)):
        return AnalyseEligibilite(
            droit="AAH", label=label, applicable_profil=False,
            eligibilite_estimee=0, niveau_confiance="faible",
            forces=[], faiblesses=[], justificatifs_manquants=[],
            questions_complementaires=[], probabilite_estimee_obtention="faible",
            signaux_detectes=[], droit_demande="AAH" in droits_set,
        )

    score = 0
    forces, faiblesses, signaux = [], [], []

    # Signaux forts (+20 à +25)
    found, frag = _signal(texte, [r"arr[eê]t longue dur[eé]e", r"arr[eê]t.{0,20}travail.{0,20}\d ans?",
                                    r"incapacit[eé].{0,20}permanente", r"inaptitude"])
    if found: score += 22; forces.append("Arrêt de travail ou incapacité permanente documentée"); signaux.append(frag)

    found2, frag2 = _signal(texte, [r"pension.{0,15}invalidit[eé]", r"invalidit[eé].{0,10}(2|deuxi[eè]me|3|troisi[eè]me)",
                                      r"2[eè]me.{0,10}cat[eé]gorie", r"3[eè]me.{0,10}cat[eé]gorie"])
    if found2: score += 20; forces.append("Pension d'invalidité potentiellement compatible avec AAH différentielle"); signaux.append(frag2)

    found3, frag3 = _signal(texte, [r"licenci[eé].{0,15}inaptitude", r"inapte.{0,15}poste",
                                      r"ne peut plus travailler", r"impossible.{0,15}reprendre.{0,15}travail"])
    if found3: score += 18; forces.append("Inaptitude au travail déclarée"); signaux.append(frag3)

    # Signaux moyens (+8 à +12)
    found4, frag4 = _signal(texte, [r"fibromyalgie", r"scl[eé]rose", r"maladie chronique",
                                      r"syndrome.{0,15}fatigue", r"parkinson", r"cancer", r"lupus"])
    if found4: score += 10; forces.append("Pathologie chronique sévère compatible avec critères AAH"); signaux.append(frag4)

    found5, _ = _signal(texte, [r"sans emploi.{0,20}\d.{0,5}(ans?|mois)", r"n'?a? pas travaill[eé].{0,20}\d",
                                  r"sans activit[eé] depuis"])
    if found5: score += 8; forces.append("Inactivité professionnelle prolongée documentée")

    found6, _ = _signal(texte, [r"taux.{0,10}(80|90|100)\s*%", r"taux d.incapacit[eé].{0,15}(80|90|100)"])
    if found6: score += 25; forces.append("Taux d'incapacité ≥ 80% évoqué — forte compatibilité AAH 1")

    # Signaux négatifs
    found_neg, _ = _signal(texte, [r"travaille.{0,15}(actuellement|temps plein|CDI|à plein temps)",
                                     r"emploi.{0,15}compatible"])
    if found_neg: score -= 15; faiblesses.append("Activité professionnelle actuelle mentionnée — vérifier compatibilité")

    # Faiblesses si signaux absents
    if not found and not found3: faiblesses.append("Durée et nature de l'incapacité à préciser pour appuyer la demande")
    if not found6: faiblesses.append("Taux d'incapacité permanente non documenté")

    score = max(0, min(100, score))
    n_forts = sum([found, found2, found3, found6])

    return AnalyseEligibilite(
        droit="AAH", label=label, applicable_profil=True,
        eligibilite_estimee=score, niveau_confiance=_score_to_confiance(score, n_forts),
        forces=forces, faiblesses=faiblesses,
        justificatifs_manquants=[
            "Certificat médical détaillant l'incapacité permanente",
            "Avis d'imposition ou de non-imposition",
            "Attestation d'arrêt de travail ou de liquidation/invalidité",
        ],
        questions_complementaires=[
            "Un médecin a-t-il estimé votre taux d'incapacité permanente ? Si oui, quel pourcentage ?",
            "Percevez-vous une pension d'invalidité ? De quelle catégorie ?",
            "Depuis combien de temps exactement êtes-vous sans emploi ou en arrêt ?",
        ],
        probabilite_estimee_obtention=_score_to_proba(score),
        signaux_detectes=[s for s in signaux if s],
        droit_demande="AAH" in droits_set,
    )


def _analyser_pch(donnees: dict, texte: str, age: int | None,
                  profil_mdph: str, droits_set: set) -> AnalyseEligibilite:
    label = "Prestation de Compensation du Handicap (PCH)"
    applicable = profil_mdph in ("adulte", "enfant", "protege", "mixte")
    if not applicable or (age is not None and age > 75):
        return AnalyseEligibilite(
            droit="PCH", label=label, applicable_profil=False,
            eligibilite_estimee=0, niveau_confiance="faible",
            forces=[], faiblesses=[], justificatifs_manquants=[],
            questions_complementaires=[], probabilite_estimee_obtention="faible",
            signaux_detectes=[], droit_demande="PCH" in droits_set,
        )

    score = 0
    forces, faiblesses, signaux = [], [], []

    # Signaux aide humaine (critère central PCH)
    found, frag = _signal(texte, [r"aide.{0,20}(toilette|douche|lavage|hygi[eè]ne)",
                                    r"ne peut pas se laver", r"besoin d.aide.{0,20}matin",
                                    r"tierce personne", r"aide humaine quotidienne"])
    if found: score += 28; forces.append("Besoin d'aide humaine pour les soins corporels documenté (critère PCH catégorie 1)"); signaux.append(frag)

    found2, frag2 = _signal(texte, [r"fauteuil roulant", r"ne peut (pas|plus) marcher sans",
                                      r"d[eé]placement.{0,20}(impossible|impossible)",
                                      r"marche.{0,20}(limit[eé]e?|impossible|tr[eè]s difficile)",
                                      r"grabataire", r"t[eé]trapl[eé]gie", r"h[eé]mipl[eé]gie"])
    if found2: score += 25; forces.append("Limitation sévère des déplacements compatible avec PCH aide déplacement"); signaux.append(frag2)

    found3, frag3 = _signal(texte, [r"ne peut pas s.habiller", r"aide.{0,20}habillage",
                                      r"besoin aide.{0,20}habiller"])
    if found3: score += 15; forces.append("Besoin d'aide pour l'habillage documenté")

    found4, frag4 = _signal(texte, [r"gastrostomie", r"sonde", r"trachéotomie", r"gastric",
                                      r"alimentation.{0,20}impossible seul", r"d[eé]glutition"])
    if found4: score += 20; forces.append("Besoin d'aide pour l'alimentation/déglutition")

    found5, frag5 = _signal(texte, [r"aide technique", r"fauteuil[^s]", r"ortho[sè]se",
                                      r"proth[eè]se", r"am[eé]nagement logement", r"PMR"])
    if found5: score += 10; forces.append("Aides techniques ou aménagement documentés")

    found6, frag6 = _signal(texte, [r"aidant.{0,15}(fait|s'occupe|g[eè]re|aide)",
                                      r"famille.{0,15}(aide|s'occupe)", r"conjoint.{0,15}aide"])
    if found6: score += 8; forces.append("Aide informelle de l'entourage documentée — à formaliser en PCH")

    # Faiblesses
    if not found and not found2: faiblesses.append("Actes de la vie quotidienne nécessitant aide non documentés précisément")
    if not found5: faiblesses.append("Besoins en aides techniques non documentés")

    # Signaux diagnostics favorables
    found7, _ = _signal(texte, [r"SLA", r"myopathie", r"scl[eé]rose.{0,15}plaques", r"paralysie c[eé]r[eé]brale",
                                  r"polyhandicap"])
    if found7: score += 12; forces.append("Diagnostic compatible avec PCH selon les barèmes d'incapacité")

    score = max(0, min(100, score))
    n_forts = sum([found, found2, found4])

    return AnalyseEligibilite(
        droit="PCH", label=label, applicable_profil=True,
        eligibilite_estimee=score, niveau_confiance=_score_to_confiance(score, n_forts),
        forces=forces, faiblesses=faiblesses,
        justificatifs_manquants=[
            "Grille d'évaluation des besoins d'aide humaine (nombre d'heures/jour)",
            "Devis de prestataire aide à domicile ou aide technique",
            "Certificat médical détaillant les actes impossibles sans aide",
        ],
        questions_complementaires=[
            "Combien de fois par semaine avez-vous besoin d'aide pour la toilette ou la douche ?",
            "Pouvez-vous vous déplacer seul(e) à l'intérieur de votre domicile ? Et à l'extérieur ?",
            "Avez-vous besoin d'aide pour vous habiller le matin ?",
            "Y a-t-il des aides techniques que vous utilisez ou dont vous auriez besoin ?",
        ],
        probabilite_estimee_obtention=_score_to_proba(score),
        signaux_detectes=[s for s in signaux if s],
        droit_demande="PCH" in droits_set,
    )


def _analyser_cmi_stationnement(donnees: dict, texte: str, age: int | None,
                                 profil_mdph: str, droits_set: set) -> AnalyseEligibilite:
    label = "CMI — Mention Stationnement"
    applicable = True  # Applicable à tout profil
    score = 0
    forces, faiblesses, signaux = [], [], []

    found, frag = _signal(texte, [r"marche.{0,20}(difficile|limit[eé]e?|impossible|p[eé]nible)",
                                    r"ne peut (pas|plus) marcher", r"p[eé]rim[eè]tre.{0,15}march",
                                    r"distance.{0,15}march", r"100.{0,10}m[eè]tres?",
                                    r"200.{0,10}m[eè]tres?"])
    if found: score += 30; forces.append("Limitation de la marche documentée (critère principal CMI stationnement)"); signaux.append(frag)

    found2, frag2 = _signal(texte, [r"fauteuil roulant", r"canne", r"b[eé]quille",
                                      r"d[eé]ambulateur", r"aide.{0,15}d[eé]placement"])
    if found2: score += 25; forces.append("Utilisation d'aide à la mobilité — compatible CMI stationnement"); signaux.append(frag2)

    found3, frag3 = _signal(texte, [r"fatigue.{0,20}(marche|d[eé]placement)", r"essoufflement",
                                      r"n.?en peux plus.{0,20}march", r"douleur.{0,20}march"])
    if found3: score += 20; forces.append("Fatigue ou douleur à la marche documentée"); signaux.append(frag3)

    found4, _ = _signal(texte, [r"scl[eé]rose.{0,15}plaques", r"\bSEP\b", r"parkinson",
                                  r"t[eé]trapl[eé]gie", r"h[eé]mipl[eé]gie", r"myopathie"])
    if found4: score += 15; forces.append("Diagnostic neuromoteur compatible avec difficultés de marche durables")

    if not found and not found2: faiblesses.append("Limitation de la marche à documenter précisément (périmètre en mètres)")

    score = max(0, min(100, score))
    return AnalyseEligibilite(
        droit="CMI_STATIONNEMENT", label=label, applicable_profil=applicable,
        eligibilite_estimee=score, niveau_confiance=_score_to_confiance(score, sum([found, found2])),
        forces=forces, faiblesses=faiblesses,
        justificatifs_manquants=["Certificat médical précisant la limitation de la marche et la distance"],
        questions_complementaires=[
            "Quelle est la distance maximale que vous pouvez parcourir sans vous arrêter ?",
            "Avez-vous besoin d'une aide pour vous déplacer (canne, fauteuil, accompagnant) ?",
        ],
        probabilite_estimee_obtention=_score_to_proba(score),
        signaux_detectes=[s for s in signaux if s],
        droit_demande="CMI" in droits_set or "CMI STATIONNEMENT" in droits_set,
    )


def _analyser_cmi_priorite(donnees: dict, texte: str, age: int | None,
                             profil_mdph: str, droits_set: set) -> AnalyseEligibilite:
    label = "CMI — Mention Priorité"
    score = 0
    forces, faiblesses, signaux = [], [], []

    found, frag = _signal(texte, [r"ne peut (pas|plus) rester debout", r"douleur.{0,15}debout",
                                    r"debout.{0,15}(impossible|difficile|douloureux)",
                                    r"fatigabilit[eé].{0,15}debout", r"vertiges.{0,15}station debout"])
    if found: score += 35; forces.append("Impossibilité ou douleur en station debout documentée"); signaux.append(frag)

    found2, frag2 = _signal(texte, [r"file.{0,15}attente", r"transport.{0,15}commun",
                                      r"priorit[eé].{0,10}passage", r"difficultés? transports?"])
    if found2: score += 20; forces.append("Difficultés liées aux files d'attente ou transports évoquées"); signaux.append(frag2)

    found3, _ = _signal(texte, [r"douleurs? chroniques?", r"arthrose", r"fibromyalgie",
                                  r"insuffisance.{0,10}cardiaque", r"BPCO"])
    if found3: score += 15; forces.append("Pathologie chronique pouvant justifier une priorité de passage")

    if not found: faiblesses.append("Impossibilité de rester debout non documentée précisément")

    score = max(0, min(100, score))
    return AnalyseEligibilite(
        droit="CMI_PRIORITE", label=label, applicable_profil=True,
        eligibilite_estimee=score, niveau_confiance=_score_to_confiance(score, sum([found])),
        forces=forces, faiblesses=faiblesses,
        justificatifs_manquants=["Certificat médical précisant l'impossibilité de rester debout en file d'attente"],
        questions_complementaires=[
            "Pouvez-vous rester debout plus de quelques minutes sans douleur ou fatigue importante ?",
        ],
        probabilite_estimee_obtention=_score_to_proba(score),
        signaux_detectes=[s for s in signaux if s],
        droit_demande="CMI" in droits_set or "CMI PRIORITE" in droits_set,
    )


def _analyser_cmi_invalidite(donnees: dict, texte: str, age: int | None,
                               profil_mdph: str, droits_set: set) -> AnalyseEligibilite:
    label = "CMI — Mention Invalidité (taux ≥ 80%)"
    score = 0
    forces, faiblesses, signaux = [], [], []

    found, frag = _signal(texte, [r"taux.{0,10}(80|90|100)\s*%",
                                    r"incapacit[eé].{0,15}(80|90|100)", r"invalide.{0,15}(80|90|100)"])
    if found: score += 50; forces.append("Taux d'incapacité ≥ 80% évoqué — critère CMI invalidité"); signaux.append(frag)

    found2, _ = _signal(texte, [r"AAH", r"allocation.{0,15}adultes.{0,15}handicap"])
    if found2: score += 20; forces.append("Attribution AAH évoquée (suggère taux d'incapacité ≥ 50%)")

    if not found: faiblesses.append("Taux d'incapacité permanente non documenté — requis pour CMI invalidité")

    score = max(0, min(100, score))
    return AnalyseEligibilite(
        droit="CMI_INVALIDITE", label=label, applicable_profil=True,
        eligibilite_estimee=score, niveau_confiance=_score_to_confiance(score, sum([found])),
        forces=forces, faiblesses=faiblesses,
        justificatifs_manquants=["Certificat médical avec taux d'incapacité permanente ≥ 80%"],
        questions_complementaires=[
            "Un médecin a-t-il évalué votre taux d'incapacité permanente ? Quel pourcentage ?",
        ],
        probabilite_estimee_obtention=_score_to_proba(score),
        signaux_detectes=[s for s in signaux if s],
        droit_demande="CMI" in droits_set or "CMI INVALIDITE" in droits_set,
    )


def _analyser_rqth(donnees: dict, texte: str, age: int | None,
                   profil_mdph: str, droits_set: set) -> AnalyseEligibilite:
    label = "Reconnaissance de la Qualité de Travailleur Handicapé (RQTH)"
    applicable = profil_mdph in ("adulte", "protege", "mixte")
    if not applicable or (age is not None and (age < 16 or age > 62)):
        return AnalyseEligibilite(
            droit="RQTH", label=label, applicable_profil=False,
            eligibilite_estimee=0, niveau_confiance="faible",
            forces=[], faiblesses=[], justificatifs_manquants=[],
            questions_complementaires=[], probabilite_estimee_obtention="faible",
            signaux_detectes=[], droit_demande="RQTH" in droits_set,
        )

    score = 20  # Base adulte en âge de travailler
    forces, faiblesses, signaux = [], [], []

    # Tout diagnostic avec impact emploi
    found_diag, frag = _signal(texte, [r"diagnostics?", r"pathologie", r"maladie", r"trouble",
                                        r"handicap", r"s[eé]quelles?"])
    if donnees.get("diagnostics"): score += 15; forces.append("Diagnostic documenté — compatible avec RQTH")

    found2, frag2 = _signal(texte, [r"impact.{0,20}(travail|emploi|professionnel)",
                                      r"difficult[eé]s?.{0,20}(travail|emploi|professionnel)",
                                      r"limitations?.{0,20}(travail|poste|emploi)"])
    if found2: score += 20; forces.append("Impact professionnel des limitations documenté"); signaux.append(frag2)

    found3, _ = _signal(texte, [r"am[eé]nagement.{0,15}poste", r"mi-temps.{0,15}th[eé]rapeutique",
                                  r"restrictions?.{0,15}emploi", r"m[eé]decin.{0,15}travail"])
    if found3: score += 15; forces.append("Aménagement de poste ou restrictions médicales professionnelles évoqués")

    found4, _ = _signal(texte, [r"travaille", r"emploi", r"CDI", r"CDD", r"cherche.{0,15}emploi",
                                  r"demandeur.{0,15}emploi", r"p[oô]le.{0,10}emploi", r"France travail"])
    if found4: score += 10; forces.append("Situation emploi renseignée — RQTH pertinente")

    found5, _ = _signal(texte, [r"retraite", r"plus de 60 ans"])
    if found5: score -= 20; faiblesses.append("Situation de retraite évoquée — vérifier pertinence RQTH")

    if not found2: faiblesses.append("Impact des limitations sur la vie professionnelle à documenter précisément")

    score = max(0, min(100, score))
    return AnalyseEligibilite(
        droit="RQTH", label=label, applicable_profil=True,
        eligibilite_estimee=score, niveau_confiance=_score_to_confiance(score, 2 if found2 else 1),
        forces=forces, faiblesses=faiblesses,
        justificatifs_manquants=[
            "Certificat médical décrivant les limitations au travail",
            "Avis du médecin du travail si en poste (fiche aptitude/inaptitude)",
        ],
        questions_complementaires=[
            "Quelles sont les tâches professionnelles que vous ne pouvez plus ou difficilement effectuer ?",
            "Des aménagements de poste ont-ils été demandés ou mis en place ?",
        ],
        probabilite_estimee_obtention=_score_to_proba(score),
        signaux_detectes=[s for s in signaux if s],
        droit_demande="RQTH" in droits_set,
    )


def _analyser_aeeh(donnees: dict, texte: str, age: int | None,
                   profil_mdph: str, droits_set: set) -> AnalyseEligibilite:
    label = "Allocation d'Éducation de l'Enfant Handicapé (AEEH)"
    applicable = profil_mdph in ("enfant", "mixte") or (age is not None and age < 20)
    if not applicable:
        return AnalyseEligibilite(
            droit="AEEH", label=label, applicable_profil=False,
            eligibilite_estimee=0, niveau_confiance="faible",
            forces=[], faiblesses=[], justificatifs_manquants=[],
            questions_complementaires=[], probabilite_estimee_obtention="faible",
            signaux_detectes=[], droit_demande="AEEH" in droits_set,
        )

    score = 25  # Base enfant
    forces, faiblesses, signaux = [], [], []

    if donnees.get("diagnostics"): score += 20; forces.append("Diagnostic documenté chez l'enfant")

    found, frag = _signal(texte, [r"AESH", r"AVS", r"auxiliaire.{0,15}vie", r"accompagnant",
                                    r"tiers.?temps", r"am[eé]nagement.{0,15}scolaire"])
    if found: score += 20; forces.append("Aménagements scolaires (AESH, tiers-temps) documentés — AEEH fortement compatible"); signaux.append(frag)

    found2, frag2 = _signal(texte, [r"SESSAD", r"IME", r"\bIMPro\b", r"\bCAMSP\b", r"EEAP",
                                      r"prise en charge.{0,15}sp[eé]cialis[eé]e"])
    if found2: score += 15; forces.append("Prise en charge spécialisée documentée — renforce AEEH"); signaux.append(frag2)

    found3, _ = _signal(texte, [r"non scolarisé", r"[eé]cole.{0,15}impossible", r"exclusion.{0,15}scolaire"])
    if found3: score += 10; forces.append("Difficultés de scolarisation documentées")

    # Compléments AEEH
    complement_forces = []
    if _signal(texte, [r"AESH.{0,20}(individuel|dédié|exclusif)"])[0]:
        complement_forces.append("AESH individuelle → AEEH complément catégorie 1 ou 2 possible")
    if _signal(texte, [r"cessation.{0,15}activit[eé]", r"r[eé]duction.{0,15}activit[eé].{0,15}parent",
                        r"mi-temps.{0,15}aidant"])[0]:
        complement_forces.append("Réduction d'activité parentale → AVPF + AEEH complément catégorie 4-5 possible")
    forces.extend(complement_forces)

    if not found and not found2: faiblesses.append("Aménagements et prises en charge de l'enfant à documenter")

    score = max(0, min(100, score))
    return AnalyseEligibilite(
        droit="AEEH", label=label, applicable_profil=True,
        eligibilite_estimee=score, niveau_confiance=_score_to_confiance(score, sum([found, found2])),
        forces=forces, faiblesses=faiblesses,
        justificatifs_manquants=[
            "Certificat médical pédiatrique",
            "Bulletin scolaire et rapport GEVASCO ou ESS",
            "Attestation AESH/AVS si présente",
        ],
        questions_complementaires=[
            "Votre enfant bénéficie-t-il d'une AESH ou d'un tiers-temps à l'école ?",
            "Avez-vous dû réduire votre activité professionnelle pour accompagner votre enfant ?",
            "Votre enfant est-il suivi par un SESSAD ou un autre service spécialisé ?",
        ],
        probabilite_estimee_obtention=_score_to_proba(score),
        signaux_detectes=[s for s in signaux if s],
        droit_demande="AEEH" in droits_set,
    )


def _analyser_avpf(donnees: dict, texte: str, age: int | None,
                   profil_mdph: str, droits_set: set) -> AnalyseEligibilite:
    label = "Affiliation Vieillesse Parent au Foyer (AVPF)"
    applicable = profil_mdph in ("enfant", "mixte") and bool(donnees.get("representant_legal_nom") or donnees.get("aidant_nom"))
    score = 0
    forces, faiblesses, signaux = [], [], []

    found, frag = _signal(texte, [r"r[eé]duction.{0,15}activit[eé]", r"mi-temps.{0,15}(aidant|parent|famille)",
                                    r"cong[eé].{0,15}parental", r"cessation.{0,15}activit[eé]",
                                    r"arr[eê]t.{0,15}aidant", r"pour s.{0,10}occuper"])
    if found: score += 40; forces.append("Réduction ou cessation d'activité parentale documentée — AVPF compatible"); signaux.append(frag)

    found2, _ = _signal(texte, [r"AEEH", r"allocation.{0,15}[eé]ducation"])
    if found2: score += 20; forces.append("AEEH demandée ou présente — AVPF potentiellement cumulable")

    found3, _ = _signal(texte, [r"liste.{0,15}attente", r"pas de place", r"sans.{0,15}SESSAD",
                                  r"aucune prise en charge"])
    if found3: score += 15; forces.append("Absence de prise en charge spécialisée → charge sur le parent encore plus forte")

    if not found: faiblesses.append("Réduction d'activité professionnelle du parent à documenter pour l'AVPF")

    score = max(0, min(100, score))
    return AnalyseEligibilite(
        droit="AVPF", label=label, applicable_profil=applicable,
        eligibilite_estimee=score, niveau_confiance=_score_to_confiance(score, sum([found])),
        forces=forces, faiblesses=faiblesses,
        justificatifs_manquants=["Bulletins de salaire montrant la réduction d'activité", "Attestation employeur"],
        questions_complementaires=[
            "L'un des parents a-t-il réduit ou cessé son activité professionnelle pour s'occuper de l'enfant ?",
        ],
        probabilite_estimee_obtention=_score_to_proba(score),
        signaux_detectes=[s for s in signaux if s],
        droit_demande="AVPF" in droits_set,
    )


def _analyser_savs(donnees: dict, texte: str, age: int | None,
                   profil_mdph: str, droits_set: set) -> AnalyseEligibilite:
    label = "Service d'Accompagnement à la Vie Sociale (SAVS)"
    applicable = profil_mdph in ("adulte", "protege", "mixte")
    if not applicable:
        return AnalyseEligibilite(
            droit="SAVS", label=label, applicable_profil=False,
            eligibilite_estimee=0, niveau_confiance="faible",
            forces=[], faiblesses=[], justificatifs_manquants=[],
            questions_complementaires=[], probabilite_estimee_obtention="faible",
            signaux_detectes=[], droit_demande="SAVS" in droits_set,
        )
    score = 0
    forces, faiblesses, signaux = [], [], []

    found, frag = _signal(texte, [r"psychique", r"bipolaire", r"schizophr", r"trouble.{0,15}psychiatrique",
                                    r"\bTSA\b", r"autisme"])
    if found: score += 25; forces.append("Profil psychique ou TSA adulte compatible avec SAVS"); signaux.append(frag)

    found2, frag2 = _signal(texte, [r"d[eé]ficience.{0,15}intellectuelle", r"DI.{0,5}(l[eé]g[eè]re|mod[eé]r[eé]e)",
                                      r"trisomie"])
    if found2: score += 20; forces.append("Déficience intellectuelle adulte compatible avec SAVS"); signaux.append(frag2)

    found3, frag3 = _signal(texte, [r"autonomie.{0,15}(partielle|r[eé]duite)", r"accompagnement.{0,15}domicile",
                                      r"aide.{0,20}d[eé]marches", r"vivre.{0,15}(seul|domicile)"])
    if found3: score += 20; forces.append("Besoin d'accompagnement pour la vie quotidienne et sociale documenté"); signaux.append(frag3)

    found4, _ = _signal(texte, [r"d[eé]marches administratives.{0,20}(difficile|impossible)",
                                  r"courrier.{0,20}(ne|n.?arrive).{0,15}(pas|plus)",
                                  r"gestion.{0,20}(impossible|difficile)"])
    if found4: score += 15; forces.append("Difficultés de gestion administrative documentées")

    found5, _ = _signal(texte, [r"stabilité", r"logement", r"maintien.{0,15}domicile"])
    if found5: score += 10; forces.append("Besoin de soutien pour la stabilité résidentielle")

    if not found and not found2: faiblesses.append("Profil handicap psychique/TSA/DI adulte non identifié clairement")
    if not found3: faiblesses.append("Besoins d'accompagnement à la vie sociale à préciser")

    score = max(0, min(100, score))
    return AnalyseEligibilite(
        droit="SAVS", label=label, applicable_profil=True,
        eligibilite_estimee=score, niveau_confiance=_score_to_confiance(score, sum([found, found2])),
        forces=forces, faiblesses=faiblesses,
        justificatifs_manquants=["Compte-rendu psychiatrique ou psychologique récent", "Bilan d'autonomie"],
        questions_complementaires=[
            "Pour quelles démarches quotidiennes avez-vous besoin d'un soutien régulier ?",
            "Êtes-vous accompagné(e) par un service ou un professionnel pour votre vie sociale ?",
        ],
        probabilite_estimee_obtention=_score_to_proba(score),
        signaux_detectes=[s for s in signaux if s],
        droit_demande="SAVS" in droits_set,
    )


def _analyser_samsah(donnees: dict, texte: str, age: int | None,
                     profil_mdph: str, droits_set: set) -> AnalyseEligibilite:
    label = "Service d'Accompagnement Médico-Social Adultes Handicapés (SAMSAH)"
    applicable = profil_mdph in ("adulte", "protege", "mixte")
    if not applicable:
        return AnalyseEligibilite(
            droit="SAMSAH", label=label, applicable_profil=False,
            eligibilite_estimee=0, niveau_confiance="faible",
            forces=[], faiblesses=[], justificatifs_manquants=[],
            questions_complementaires=[], probabilite_estimee_obtention="faible",
            signaux_detectes=[], droit_demande="SAMSAH" in droits_set,
        )
    score = 0
    forces, faiblesses, signaux = [], [], []

    # SAMSAH = SAVS + soins médicaux
    found_savs, _ = _signal(texte, [r"psychique", r"bipolaire", r"schizophr", r"\bTSA\b",
                                      r"d[eé]ficience.{0,15}intellectuelle"])
    found_soins, frag = _signal(texte, [r"soins.{0,15}domicile", r"infirmier.{0,15}domicile",
                                          r"injection.{0,15}domicile", r"prise en charge m[eé]dicale.{0,15}r[eé]guli[eè]re",
                                          r"suivi.{0,15}m[eé]dical.{0,15}(lourd|r[eé]gulier|intensif)"])
    if found_savs: score += 20; forces.append("Profil compatible SAVS (base pour SAMSAH)")
    if found_soins: score += 30; forces.append("Soins médicaux réguliers à domicile documentés — SAMSAH compatible"); signaux.append(frag)

    if found_savs and found_soins: score += 15; forces.append("Combinaison accompagnement social + soins médicaux — SAMSAH particulièrement adapté")

    if not found_soins: faiblesses.append("Soins médicaux réguliers à domicile non documentés — SAMSAH vs SAVS à clarifier")

    score = max(0, min(100, score))
    return AnalyseEligibilite(
        droit="SAMSAH", label=label, applicable_profil=True,
        eligibilite_estimee=score, niveau_confiance=_score_to_confiance(score, sum([found_soins])),
        forces=forces, faiblesses=faiblesses,
        justificatifs_manquants=["Prescription médicale des soins à domicile", "Compte-rendu médical récent"],
        questions_complementaires=[
            "Recevez-vous des soins médicaux réguliers à votre domicile (infirmier, injections...) ?",
        ],
        probabilite_estimee_obtention=_score_to_proba(score),
        signaux_detectes=[s for s in signaux if s],
        droit_demande="SAMSAH" in droits_set,
    )


def _analyser_esat(donnees: dict, texte: str, age: int | None,
                   profil_mdph: str, droits_set: set) -> AnalyseEligibilite:
    label = "Établissement et Service d'Aide par le Travail (ESAT)"
    applicable = profil_mdph in ("adulte", "protege", "mixte") and (age is None or 18 <= age <= 60)
    if not applicable:
        return AnalyseEligibilite(
            droit="ESAT", label=label, applicable_profil=False,
            eligibilite_estimee=0, niveau_confiance="faible",
            forces=[], faiblesses=[], justificatifs_manquants=[],
            questions_complementaires=[], probabilite_estimee_obtention="faible",
            signaux_detectes=[], droit_demande="ESAT" in droits_set,
        )
    score = 0
    forces, faiblesses, signaux = [], [], []

    found, frag = _signal(texte, [r"\bESAT\b", r"milieu prot[eé]g[eé]", r"travail.{0,15}adapt[eé]"])
    if found: score += 35; forces.append("ESAT ou milieu protégé déjà identifié"); signaux.append(frag)

    found2, frag2 = _signal(texte, [r"d[eé]ficience.{0,15}intellectuelle", r"trisomie",
                                      r"DI.{0,5}(mod[eé]r[eé]e|l[eé]g[eè]re)"])
    if found2: score += 25; forces.append("Déficience intellectuelle — compatible ESAT (accompagnement travail adapté)"); signaux.append(frag2)

    found3, _ = _signal(texte, [r"ne peut pas.{0,20}milieu ordinaire", r"milieu ordinaire.{0,15}(impossible|difficile)",
                                  r"encadrement.{0,15}n[eé]cessaire", r"besoin.{0,15}structure.{0,15}travail"])
    if found3: score += 20; forces.append("Impossibilité de travailler en milieu ordinaire sans encadrement")

    found4, _ = _signal(texte, [r"capacit[eé]s?.{0,15}travail.{0,15}r[eé]duite", r"schizophr[eé]nie.{0,20}stabilis",
                                  r"psychose.{0,20}stabilis"])
    if found4: score += 15; forces.append("Capacités de travail réduites compatibles avec milieu protégé")

    if not found and not found2: faiblesses.append("Type de capacités de travail à préciser pour orienter ESAT vs milieu ordinaire")

    score = max(0, min(100, score))
    return AnalyseEligibilite(
        droit="ESAT", label=label, applicable_profil=True,
        eligibilite_estimee=score, niveau_confiance=_score_to_confiance(score, sum([found, found2])),
        forces=forces, faiblesses=faiblesses,
        justificatifs_manquants=["Bilan d'orientation professionnel", "Avis médical sur les capacités de travail"],
        questions_complementaires=[
            "Avez-vous déjà travaillé ou visité un ESAT ? Qu'est-ce qui vous convient ou non ?",
            "Qu'est-ce que vous aimeriez faire comme activité de travail ?",
        ],
        probabilite_estimee_obtention=_score_to_proba(score),
        signaux_detectes=[s for s in signaux if s],
        droit_demande="ESAT" in droits_set,
    )


def _analyser_esrp(donnees: dict, texte: str, age: int | None,
                   profil_mdph: str, droits_set: set) -> AnalyseEligibilite:
    label = "Établissement/Service de Rééducation Professionnelle (ESRP)"
    applicable = profil_mdph in ("adulte", "protege", "mixte")
    score = 0
    forces, faiblesses, signaux = [], [], []

    found, frag = _signal(texte, [r"accident.{0,15}travail", r"reconversion.{0,15}(professionnel|obligatoire)",
                                    r"inapte.{0,15}ancien.{0,15}poste", r"ne peut plus.{0,20}m[eé]tier"])
    if found: score += 30; forces.append("Accident du travail ou reconversion obligatoire documenté"); signaux.append(frag)

    found2, _ = _signal(texte, [r"capacit[eé]s?.{0,15}travail.{0,15}pr[eé]serv[eé]es?",
                                  r"peut travailler.{0,15}autre", r"nouveau m[eé]tier",
                                  r"se reconvertir"])
    if found2: score += 20; forces.append("Capacités de travail préservées — reconversion professionnelle possible")

    found3, _ = _signal(texte, [r"\bESRP\b", r"r[eé][eé]ducation.{0,15}professionnel"])
    if found3: score += 30; forces.append("ESRP évoqué dans les données")

    if not found: faiblesses.append("Accident du travail ou séquelles avec reconversion nécessaire à documenter")

    score = max(0, min(100, score))
    return AnalyseEligibilite(
        droit="ESRP", label=label, applicable_profil=applicable,
        eligibilite_estimee=score, niveau_confiance=_score_to_confiance(score, sum([found, found3])),
        forces=forces, faiblesses=faiblesses,
        justificatifs_manquants=["Attestation AT avec taux IPP", "Avis inaptitude médecin du travail"],
        questions_complementaires=[
            "Votre handicap vous oblige-t-il à changer complètement de métier ?",
            "Avez-vous encore des capacités à travailler dans un autre domaine ?",
        ],
        probabilite_estimee_obtention=_score_to_proba(score),
        signaux_detectes=[s for s in signaux if s],
        droit_demande="ESRP" in droits_set,
    )


def _analyser_espo(donnees: dict, texte: str, age: int | None,
                   profil_mdph: str, droits_set: set) -> AnalyseEligibilite:
    label = "Évaluation et Soutien à l'Orientation Professionnelle (ESPO)"
    applicable = profil_mdph in ("adulte", "protege", "mixte") and (age is None or age < 60)
    score = 0
    forces, faiblesses, signaux = [], [], []

    found, frag = _signal(texte, [r"pas de projet", r"ne sait pas.{0,20}(vers quoi|quoi faire)",
                                    r"bilan.{0,15}capacit[eé]s?", r"bilan.{0,15}orientation",
                                    r"\bESPO\b"])
    if found: score += 35; forces.append("Absence de projet professionnel ou demande de bilan documentée"); signaux.append(frag)

    found2, _ = _signal(texte, [r"accident.{0,15}travail", r"handicap.{0,15}acquis",
                                  r"AVC.{0,15}s[eé]quelles?", r"maladie.{0,15}invalidante"])
    if found2: score += 20; forces.append("Handicap acquis récent — besoin d'orientation professionnelle adapté")

    found3, _ = _signal(texte, [r"sans emploi", r"arr[eê]t.{0,15}travail", r"ne travaille.{0,15}plus"])
    if found3: score += 15; forces.append("Situation d'inactivité professionnelle — ESPO peut aider à construire un projet")

    if not found: faiblesses.append("Absence de projet professionnel à documenter explicitement")

    score = max(0, min(100, score))
    return AnalyseEligibilite(
        droit="ESPO", label=label, applicable_profil=applicable,
        eligibilite_estimee=score, niveau_confiance=_score_to_confiance(score, sum([found])),
        forces=forces, faiblesses=faiblesses,
        justificatifs_manquants=["CV", "Bilan de compétences récent si disponible"],
        questions_complementaires=[
            "Avez-vous une idée du type d'activité professionnelle que vous aimeriez faire ?",
            "Avez-vous déjà bénéficié d'un bilan de compétences ou d'une évaluation d'orientation ?",
        ],
        probabilite_estimee_obtention=_score_to_proba(score),
        signaux_detectes=[s for s in signaux if s],
        droit_demande="ESPO" in droits_set,
    )


def _analyser_ueros(donnees: dict, texte: str, age: int | None,
                    profil_mdph: str, droits_set: set) -> AnalyseEligibilite:
    label = "Unité d'Évaluation de Rééducation et d'Orientation Sociale (UEROS)"
    applicable = profil_mdph in ("adulte", "protege", "mixte")
    score = 0
    forces, faiblesses, signaux = [], [], []

    found, frag = _signal(texte, [r"traumatisme.{0,15}cr[aâ]nien", r"AVC", r"l[eé]sion.{0,15}c[eé]r[eé]brale",
                                    r"s[eé]quelles?.{0,15}neurologiques?", r"\bUEROS\b"])
    if found: score += 50; forces.append("Traumatisme crânien ou lésion cérébrale acquise — UEROS spécialisée"); signaux.append(frag)

    found2, _ = _signal(texte, [r"trouble.{0,15}cognitifs?.{0,15}acquis", r"m[eé]moire.{0,15}affect[eé]e",
                                  r"attention.{0,15}s[eé]v[eè]rement.{0,15}diminu[eé]e"])
    if found2: score += 20; forces.append("Troubles cognitifs acquis évoqués")

    if not found: faiblesses.append("Traumatisme crânien ou lésion cérébrale acquise non documenté — critère principal UEROS")

    score = max(0, min(100, score))
    return AnalyseEligibilite(
        droit="UEROS", label=label, applicable_profil=applicable,
        eligibilite_estimee=score, niveau_confiance=_score_to_confiance(score, sum([found])),
        forces=forces, faiblesses=faiblesses,
        justificatifs_manquants=["IRM ou scanner cérébral", "Bilan neuropsychologique"],
        questions_complementaires=[
            "Avez-vous eu un accident avec traumatisme crânien, un AVC ou une lésion cérébrale ?",
        ],
        probabilite_estimee_obtention=_score_to_proba(score),
        signaux_detectes=[s for s in signaux if s],
        droit_demande="UEROS" in droits_set,
    )


def _analyser_ea(donnees: dict, texte: str, age: int | None,
                 profil_mdph: str, droits_set: set) -> AnalyseEligibilite:
    label = "Emploi Accompagné (EA)"
    applicable = profil_mdph in ("adulte", "protege", "mixte") and (age is None or age < 60)
    score = 0
    forces, faiblesses, signaux = [], [], []

    found, frag = _signal(texte, [r"\bTSA\b", r"autisme.{0,15}adulte", r"Asperger"])
    if found: score += 25; forces.append("TSA adulte — profil prioritaire pour l'emploi accompagné"); signaux.append(frag)

    found2, frag2 = _signal(texte, [r"d[eé]ficience.{0,15}intellectuelle.{0,15}l[eé]g[eè]re",
                                      r"DI.{0,5}l[eé]g[eè]re", r"trisomie.{0,15}21.{0,15}léger"])
    if found2: score += 20; forces.append("DI légère — compatible emploi accompagné en milieu ordinaire"); signaux.append(frag2)

    found3, frag3 = _signal(texte, [r"difficult[eé]s?.{0,20}entretien", r"difficult[eé]s?.{0,20}codes? sociaux",
                                      r"open.?space.{0,15}difficile", r"relation.{0,15}coll[eè]gues.{0,15}difficile"])
    if found3: score += 20; forces.append("Difficultés d'adaptation au milieu professionnel documentées"); signaux.append(frag3)

    found4, _ = _signal(texte, [r"(travaille|emploi).{0,15}(actuellement|CDI|CDD|mi.temps)",
                                  r"souhait.{0,20}travailler", r"veut.{0,10}(travailler|emploi)"])
    if found4: score += 15; forces.append("Capacités de travail et souhait d'emploi présents")

    found5, _ = _signal(texte, [r"emploi accompagn[eé]"])
    if found5: score += 25; forces.append("Emploi accompagné déjà identifié")

    if not found and not found2: faiblesses.append("Profil TSA/DI léger à préciser pour cibler l'emploi accompagné")

    score = max(0, min(100, score))
    return AnalyseEligibilite(
        droit="EMPLOI_ACCOMPAGNE", label=label, applicable_profil=applicable,
        eligibilite_estimee=score, niveau_confiance=_score_to_confiance(score, sum([found, found2])),
        forces=forces, faiblesses=faiblesses,
        justificatifs_manquants=["Bilan professionnel", "CV"],
        questions_complementaires=[
            "Avez-vous déjà travaillé en milieu ordinaire ? Comment ça s'est passé ?",
            "Quelles sont vos compétences professionnelles identifiées ?",
        ],
        probabilite_estimee_obtention=_score_to_proba(score),
        signaux_detectes=[s for s in signaux if s],
        droit_demande="EA" in droits_set or "EMPLOI ACCOMPAGNE" in droits_set,
    )


def _analyser_ime(donnees: dict, texte: str, age: int | None,
                  profil_mdph: str, droits_set: set) -> AnalyseEligibilite:
    label = "Institut Médico-Éducatif (IME)"
    applicable = profil_mdph in ("enfant", "mixte") or (age is not None and age < 20)
    if not applicable:
        return AnalyseEligibilite(
            droit="IME", label=label, applicable_profil=False,
            eligibilite_estimee=0, niveau_confiance="faible",
            forces=[], faiblesses=[], justificatifs_manquants=[],
            questions_complementaires=[], probabilite_estimee_obtention="faible",
            signaux_detectes=[], droit_demande="IME" in droits_set,
        )
    score = 0
    forces, faiblesses, signaux = [], [], []

    found, frag = _signal(texte, [r"d[eé]ficience.{0,15}intellectuelle.{0,15}(mod[eé]r[eé]e|s[eé]v[eè]re)",
                                    r"DI.{0,5}(mod[eé]r[eé]e|s[eé]v[eè]re)", r"trisomie"])
    if found: score += 40; forces.append("Déficience intellectuelle modérée/sévère — IME fortement indiqué"); signaux.append(frag)

    found2, frag2 = _signal(texte, [r"milieu ordinaire.{0,15}(impossible|difficile|d[eé]pass[eé])",
                                      r"ne peut pas suivre.{0,15}classe", r"non scolarisabl[e]"])
    if found2: score += 25; forces.append("Impossibilité de suivi en milieu scolaire ordinaire documentée"); signaux.append(frag2)

    found3, _ = _signal(texte, [r"\bIME\b", r"[eé]tablissement.{0,15}m[eé]dico.{0,5}[eé]ducatif"])
    if found3: score += 25; forces.append("IME déjà identifié ou fréquenté")

    if not found: faiblesses.append("Niveau de déficience intellectuelle à préciser (modérée/sévère)")

    score = max(0, min(100, score))
    return AnalyseEligibilite(
        droit="IME", label=label, applicable_profil=True,
        eligibilite_estimee=score, niveau_confiance=_score_to_confiance(score, sum([found, found2])),
        forces=forces, faiblesses=faiblesses,
        justificatifs_manquants=["Bilan neuropsychologique récent", "Rapport pédagogique de l'école actuelle"],
        questions_complementaires=[
            "Votre enfant peut-il suivre les apprentissages en classe ordinaire avec ou sans aménagements ?",
        ],
        probabilite_estimee_obtention=_score_to_proba(score),
        signaux_detectes=[s for s in signaux if s],
        droit_demande="IME" in droits_set,
    )


def _analyser_sessad(donnees: dict, texte: str, age: int | None,
                     profil_mdph: str, droits_set: set) -> AnalyseEligibilite:
    label = "Service d'Éducation Spéciale et de Soins à Domicile (SESSAD)"
    applicable = profil_mdph in ("enfant", "mixte") or (age is not None and age < 20)
    if not applicable:
        return AnalyseEligibilite(
            droit="SESSAD", label=label, applicable_profil=False,
            eligibilite_estimee=0, niveau_confiance="faible",
            forces=[], faiblesses=[], justificatifs_manquants=[],
            questions_complementaires=[], probabilite_estimee_obtention="faible",
            signaux_detectes=[], droit_demande="SESSAD" in droits_set,
        )
    score = 0
    forces, faiblesses, signaux = [], [], []

    found, frag = _signal(texte, [r"\bTSA\b", r"autisme", r"\bTDAH\b", r"DYS", r"\bTND\b",
                                    r"trouble.{0,15}neurod[eé]veloppemental"])
    if found: score += 30; forces.append("TND (TSA/TDAH/DYS) — SESSAD très fréquemment indiqué pour maintien milieu ordinaire"); signaux.append(frag)

    found2, frag2 = _signal(texte, [r"milieu ordinaire", r"[eé]cole ordinaire", r"classe ordinaire"])
    if found2: score += 20; forces.append("Scolarisation en milieu ordinaire — SESSAD adapté pour soutien en contexte"); signaux.append(frag2)

    found3, frag3 = _signal(texte, [r"AESH", r"tiers.?temps", r"am[eé]nagement.{0,15}scolaire"])
    if found3: score += 15; forces.append("Aménagements scolaires existants — SESSAD renforce le dispositif"); signaux.append(frag3)

    found4, _ = _signal(texte, [r"\bSESSAD\b"])
    if found4: score += 30; forces.append("SESSAD déjà identifié ou fréquenté")

    found5, _ = _signal(texte, [r"d[eé]ficience.{0,15}intellectuelle.{0,5}l[eé]g[eè]re"])
    if found5: score += 15; forces.append("DI légère — SESSAD adapté pour enfants en milieu ordinaire")

    if not found: faiblesses.append("Type de trouble ou diagnostic à préciser pour cibler le type de SESSAD")

    score = max(0, min(100, score))
    return AnalyseEligibilite(
        droit="SESSAD", label=label, applicable_profil=True,
        eligibilite_estimee=score, niveau_confiance=_score_to_confiance(score, sum([found, found2])),
        forces=forces, faiblesses=faiblesses,
        justificatifs_manquants=["Bilan orthophonique ou neuropsychologique", "Rapport scolaire + GEVASCO"],
        questions_complementaires=[
            "Votre enfant est-il suivi par un orthophoniste, un ergothérapeute ou un psychomotricien ?",
            "Y a-t-il une liste d'attente pour le SESSAD dans votre secteur ?",
        ],
        probabilite_estimee_obtention=_score_to_proba(score),
        signaux_detectes=[s for s in signaux if s],
        droit_demande="SESSAD" in droits_set,
    )


def _analyser_eeap(donnees: dict, texte: str, age: int | None,
                   profil_mdph: str, droits_set: set) -> AnalyseEligibilite:
    label = "Établissement pour Enfants et Adolescents Polyhandicapés (EEAP)"
    applicable = profil_mdph in ("enfant", "mixte") or (age is not None and age < 20)
    if not applicable:
        return AnalyseEligibilite(
            droit="EEAP", label=label, applicable_profil=False,
            eligibilite_estimee=0, niveau_confiance="faible",
            forces=[], faiblesses=[], justificatifs_manquants=[],
            questions_complementaires=[], probabilite_estimee_obtention="faible",
            signaux_detectes=[], droit_demande="EEAP" in droits_set,
        )
    score = 0
    forces, faiblesses, signaux = [], [], []

    found, frag = _signal(texte, [r"polyhandicap", r"handicap.{0,15}s[eé]v[eè]re.{0,15}(moteur|cognitif)",
                                    r"paralysie.{0,15}c[eé]r[eé]brale.{0,15}s[eé]v[eè]re",
                                    r"[eé]pilepsie.{0,15}s[eé]v[eè]re.{0,15}DI"])
    if found: score += 50; forces.append("Polyhandicap sévère documenté — EEAP spécialisé indiqué"); signaux.append(frag)

    found2, _ = _signal(texte, [r"non scolarisabl[e]", r"[eé]cole.{0,15}impossible",
                                  r"dépendance.{0,15}totale", r"aucune autonom"])
    if found2: score += 25; forces.append("Dépendance totale ou impossibilité de scolarisation documentée")

    found3, _ = _signal(texte, [r"\bEEAP\b"])
    if found3: score += 30; forces.append("EEAP déjà identifié")

    if not found: faiblesses.append("Polyhandicap sévère à documenter clairement pour EEAP")

    score = max(0, min(100, score))
    return AnalyseEligibilite(
        droit="EEAP", label=label, applicable_profil=True,
        eligibilite_estimee=score, niveau_confiance=_score_to_confiance(score, sum([found])),
        forces=forces, faiblesses=faiblesses,
        justificatifs_manquants=["Bilan médical complet (neurologique, moteur)", "Rapport des soins actuels"],
        questions_complementaires=[
            "Votre enfant nécessite-t-il des soins médicaux permanents en plus de l'accompagnement éducatif ?",
        ],
        probabilite_estimee_obtention=_score_to_proba(score),
        signaux_detectes=[s for s in signaux if s],
        droit_demande="EEAP" in droits_set,
    )


def _analyser_mas(donnees: dict, texte: str, age: int | None,
                  profil_mdph: str, droits_set: set) -> AnalyseEligibilite:
    label = "Maison d'Accueil Spécialisée (MAS)"
    applicable = profil_mdph in ("adulte", "protege", "mixte") and (age is None or age >= 18)
    if not applicable:
        return AnalyseEligibilite(
            droit="MAS", label=label, applicable_profil=False,
            eligibilite_estimee=0, niveau_confiance="faible",
            forces=[], faiblesses=[], justificatifs_manquants=[],
            questions_complementaires=[], probabilite_estimee_obtention="faible",
            signaux_detectes=[], droit_demande="MAS" in droits_set,
        )
    score = 0
    forces, faiblesses, signaux = [], [], []

    found, frag = _signal(texte, [r"polyhandicap", r"d[eé]pendance.{0,15}totale", r"grabataire",
                                    r"soins.{0,10}24h", r"vie autonome.{0,15}impossible"])
    if found: score += 50; forces.append("Dépendance totale ou polyhandicap sévère — MAS compatible"); signaux.append(frag)

    found2, _ = _signal(texte, [r"ne peut pas.{0,15}vivre.{0,15}(seul|domicile)", r"maintien domicile.{0,15}impossible"])
    if found2: score += 25; forces.append("Impossibilité de maintien à domicile documentée")

    if not found: faiblesses.append("Niveau de dépendance totale à documenter pour MAS")

    score = max(0, min(100, score))
    return AnalyseEligibilite(
        droit="MAS", label=label, applicable_profil=True,
        eligibilite_estimee=score, niveau_confiance=_score_to_confiance(score, sum([found])),
        forces=forces, faiblesses=faiblesses,
        justificatifs_manquants=["Évaluation pluridisciplinaire du niveau de dépendance", "Bilan médical complet"],
        questions_complementaires=[
            "La personne peut-elle exprimer ses besoins et faire des choix de vie quotidienne ?",
        ],
        probabilite_estimee_obtention=_score_to_proba(score),
        signaux_detectes=[s for s in signaux if s],
        droit_demande="MAS" in droits_set,
    )


def _analyser_fam(donnees: dict, texte: str, age: int | None,
                  profil_mdph: str, droits_set: set) -> AnalyseEligibilite:
    label = "Foyer d'Accueil Médicalisé (FAM)"
    applicable = profil_mdph in ("adulte", "protege", "mixte") and (age is None or age >= 18)
    if not applicable:
        return AnalyseEligibilite(
            droit="FAM", label=label, applicable_profil=False,
            eligibilite_estimee=0, niveau_confiance="faible",
            forces=[], faiblesses=[], justificatifs_manquants=[],
            questions_complementaires=[], probabilite_estimee_obtention="faible",
            signaux_detectes=[], droit_demande="FAM" in droits_set,
        )
    score = 0
    forces, faiblesses, signaux = [], [], []

    found, frag = _signal(texte, [r"soins.{0,15}m[eé]dicaux.{0,15}permanents",
                                    r"m[eé]dicalisation.{0,15}n[eé]cessaire",
                                    r"infirmier.{0,15}permanent", r"FAM\b"])
    if found: score += 40; forces.append("Soins médicaux permanents nécessaires — FAM adapté"); signaux.append(frag)

    found2, _ = _signal(texte, [r"trouble.{0,15}s[eé]v[eè]re", r"handicap.{0,15}mental.{0,15}s[eé]v[eè]re",
                                  r"ne peut pas vivre seul", r"vie autonome impossible"])
    if found2: score += 20; forces.append("Limitations sévères incompatibles avec vie autonome")

    # FAM vs MAS : FAM nécessite aussi des soins + participation aux actes de vie
    found3, _ = _signal(texte, [r"activit[eé]s?.{0,15}possibles?", r"peut participer",
                                  r"capacit[eé]s? r[eé]siduelles?"])
    if found3: score += 10; forces.append("Capacités résiduelles — FAM plus adapté que MAS")

    if not found: faiblesses.append("Besoins médicaux permanents à documenter pour FAM")

    score = max(0, min(100, score))
    return AnalyseEligibilite(
        droit="FAM", label=label, applicable_profil=True,
        eligibilite_estimee=score, niveau_confiance=_score_to_confiance(score, sum([found])),
        forces=forces, faiblesses=faiblesses,
        justificatifs_manquants=["Évaluation des soins médicaux requis", "Bilan médical complet"],
        questions_complementaires=[
            "Des soins médicaux (infirmier, médecin présent) sont-ils nécessaires quotidiennement ?",
        ],
        probabilite_estimee_obtention=_score_to_proba(score),
        signaux_detectes=[s for s in signaux if s],
        droit_demande="FAM" in droits_set,
    )


def _analyser_foyer_vie(donnees: dict, texte: str, age: int | None,
                        profil_mdph: str, droits_set: set) -> AnalyseEligibilite:
    label = "Foyer de Vie"
    applicable = profil_mdph in ("adulte", "protege", "mixte") and (age is None or age >= 18)
    if not applicable:
        return AnalyseEligibilite(
            droit="FOYER_VIE", label=label, applicable_profil=False,
            eligibilite_estimee=0, niveau_confiance="faible",
            forces=[], faiblesses=[], justificatifs_manquants=[],
            questions_complementaires=[], probabilite_estimee_obtention="faible",
            signaux_detectes=[], droit_demande="FOYER VIE" in droits_set or "FOYER DE VIE" in droits_set,
        )
    score = 0
    forces, faiblesses, signaux = [], [], []

    found, frag = _signal(texte, [r"d[eé]ficience.{0,15}intellectuelle", r"DI.{0,5}(mod[eé]r[eé]e|l[eé]g[eè]re)",
                                    r"trisomie"])
    if found: score += 25; forces.append("DI — foyer de vie adapté pour adultes avec autonomie partielle"); signaux.append(frag)

    found2, frag2 = _signal(texte, [r"autonomie.{0,15}partielle", r"peut faire.{0,15}certaines choses",
                                      r"pas.{0,15}ESAT", r"pas de capacit[eé].{0,15}travail"])
    if found2: score += 20; forces.append("Autonomie partielle sans capacité de travail — foyer de vie compatible"); signaux.append(frag2)

    found3, _ = _signal(texte, [r"foyer.{0,15}vie", r"vit.{0,15}foyer", r"h[eé]bergement.{0,15}adapté"])
    if found3: score += 30; forces.append("Foyer de vie déjà identifié")

    if not found: faiblesses.append("Niveau d'autonomie de l'adulte à préciser pour foyer de vie vs ESAT+hébergement")

    score = max(0, min(100, score))
    return AnalyseEligibilite(
        droit="FOYER_VIE", label=label, applicable_profil=True,
        eligibilite_estimee=score, niveau_confiance=_score_to_confiance(score, sum([found, found2])),
        forces=forces, faiblesses=faiblesses,
        justificatifs_manquants=["Bilan d'autonomie", "Évaluation des capacités de la vie quotidienne"],
        questions_complementaires=[
            "La personne peut-elle effectuer certains actes de la vie quotidienne seule ?",
            "A-t-elle des capacités de travail, même partielles ?",
        ],
        probabilite_estimee_obtention=_score_to_proba(score),
        signaux_detectes=[s for s in signaux if s],
        droit_demande="FOYER VIE" in droits_set or "FOYER DE VIE" in droits_set,
    )


def _analyser_foyer_hebergement(donnees: dict, texte: str, age: int | None,
                                 profil_mdph: str, droits_set: set) -> AnalyseEligibilite:
    label = "Foyer d'Hébergement (pour travailleurs ESAT)"
    applicable = profil_mdph in ("adulte", "protege", "mixte") and (age is None or age >= 18)
    if not applicable:
        return AnalyseEligibilite(
            droit="FOYER_HEBERGEMENT", label=label, applicable_profil=False,
            eligibilite_estimee=0, niveau_confiance="faible",
            forces=[], faiblesses=[], justificatifs_manquants=[],
            questions_complementaires=[], probabilite_estimee_obtention="faible",
            signaux_detectes=[], droit_demande="FOYER HEBERGEMENT" in droits_set,
        )
    score = 0
    forces, faiblesses, signaux = [], [], []

    found, frag = _signal(texte, [r"\bESAT\b", r"milieu prot[eé]g[eé]", r"travail.{0,15}adapt[eé]"])
    if found: score += 35; forces.append("Travail en ESAT documenté — foyer d'hébergement naturellement associé"); signaux.append(frag)

    found2, frag2 = _signal(texte, [r"vit seul.{0,15}(difficile|impossible)", r"besoin h[eé]bergement",
                                      r"famille.{0,15}(ne peut pas|plus)"])
    if found2: score += 20; forces.append("Besoin d'hébergement accompagné documenté"); signaux.append(frag2)

    if not found: faiblesses.append("Travail en ESAT à documenter pour le foyer d'hébergement")

    score = max(0, min(100, score))
    return AnalyseEligibilite(
        droit="FOYER_HEBERGEMENT", label=label, applicable_profil=True,
        eligibilite_estimee=score, niveau_confiance=_score_to_confiance(score, sum([found])),
        forces=forces, faiblesses=faiblesses,
        justificatifs_manquants=["Attestation ESAT", "Évaluation besoins d'hébergement"],
        questions_complementaires=[
            "La personne travaille-t-elle ou est-elle orientée vers un ESAT ?",
            "Peut-elle vivre de façon autonome ou a-t-elle besoin d'un hébergement accompagné ?",
        ],
        probabilite_estimee_obtention=_score_to_proba(score),
        signaux_detectes=[s for s in signaux if s],
        droit_demande="FOYER HEBERGEMENT" in droits_set,
    )


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def analyser_eligibilite(
    donnees: dict[str, Any],
    profil_mdph: str = "adulte",
    profil_handicap: str = "",
) -> ResultatEligibiliteComplete:
    """
    Analyse la compatibilité d'un dossier avec les 22 droits MDPH.

    Retourne :
      - analyses: dict {droit: AnalyseEligibilite}
      - droits_demandes: droits déjà cochés
      - droits_omis_probables: droits compatibles non demandés (score ≥ 40)
      - droits_non_applicables: droits non pertinents pour ce profil
      - synthese: résumé lisible
    """
    texte = _construire_texte(donnees)
    age = _age_approx(str(donnees.get("date_naissance", "")))
    droits_set = _droits_demandes_set(donnees)

    analyseurs = [
        _analyser_aah, _analyser_pch,
        _analyser_cmi_stationnement, _analyser_cmi_priorite, _analyser_cmi_invalidite,
        _analyser_rqth, _analyser_aeeh, _analyser_avpf,
        _analyser_savs, _analyser_samsah,
        _analyser_esat, _analyser_esrp, _analyser_espo, _analyser_ueros,
        _analyser_ea, _analyser_ime, _analyser_sessad, _analyser_eeap,
        _analyser_mas, _analyser_fam, _analyser_foyer_vie, _analyser_foyer_hebergement,
    ]

    analyses: dict[str, AnalyseEligibilite] = {}
    for fn in analyseurs:
        try:
            res = fn(donnees, texte, age, profil_mdph, droits_set)
            analyses[res.droit] = res
        except Exception as e:
            logger.warning(f"Erreur analyseur {fn.__name__}: {e}")

    droits_demandes = [d for d, a in analyses.items() if a.droit_demande]
    droits_omis = [
        d for d, a in analyses.items()
        if a.applicable_profil
        and not a.droit_demande
        and a.eligibilite_estimee >= 25       # Seuil bas : signaler dès qu'un signal est présent
        and a.niveau_confiance != "faible"    # Mais avec au moins une confiance moyenne
    ]
    droits_na = [d for d, a in analyses.items() if not a.applicable_profil]

    # Synthèse
    nb_omis = len(droits_omis)
    synthese_parts = []
    if nb_omis > 0:
        labels_omis = [analyses[d].label for d in droits_omis[:3]]
        synthese_parts.append(
            f"Analyse : {nb_omis} droit(s) potentiellement oublié(s) — "
            f"{', '.join(labels_omis)}"
            + (f" et {nb_omis-3} autre(s)" if nb_omis > 3 else "")
        )
    else:
        synthese_parts.append("Les droits demandés semblent cohérents avec les données disponibles.")

    haute_conf = [d for d in droits_omis if analyses[d].niveau_confiance == "haute"]
    if haute_conf:
        synthese_parts.append(
            f"Confiance haute sur : {', '.join(analyses[d].label for d in haute_conf)}"
        )

    return ResultatEligibiliteComplete(
        analyses=analyses,
        droits_demandes=droits_demandes,
        droits_omis_probables=droits_omis,
        droits_non_applicables=droits_na,
        synthese=" | ".join(synthese_parts),
    )
