"""
app/engines/strategie_dossier_engine.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FACILIM 60 — Moteur 4 : Stratégie dossier (orchestrateur)

Avant la génération du CERFA, produit une analyse stratégique complète :

  A. Droits demandés + robustesse
  B. Droits potentiellement oubliés (avec justification)
  C. Orientations potentielles
  D. Urgences détectées
  E. Alertes de cohérence
  F. Forces du dossier
  G. Faiblesses du dossier
  H. Actions recommandées

Intègre les 3 moteurs précédents + stocke dans analyse_situation_json.

Usage :
  from app.engines.strategie_dossier_engine import analyser_strategie
  strategie = analyser_strategie(donnees, profil_mdph="adulte")
  # Résultat intégrable dans synthese_json["analyse_situation_json"]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any

from app.engines.eligibilite_droits_engine import (
    analyser_eligibilite, ResultatEligibiliteComplete, AnalyseEligibilite,
)
from app.engines.dossier_strength_engine import noter_robustesse, RobustesseDossier
from app.engines.questions_levier_engine import identifier_questions_levier, QuestionLevier

logger = logging.getLogger("facilim.engines.strategie_dossier")


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DrOublie:
    droit:              str
    label:              str
    score_compatibilite: int
    niveau_confiance:   str
    justification:      str
    action_suggeree:    str


@dataclass
class Urgence:
    type:               str
    description:        str
    action:             str
    champ_cerfa:        str
    priorite:           str  # "critique" | "haute" | "moyenne"


@dataclass
class AlerteCoherence:
    type:       str
    message:    str
    impact:     str


@dataclass
class StrategieDossier:
    # A — Droits demandés
    droits_demandes:                list[str]
    scores_droits_demandes:         dict[str, int]  # robustesse par droit

    # B — Droits oubliés
    droits_omis:                    list[DrOublie]

    # C — Orientations potentielles
    orientations_suggerees:         list[str]

    # D — Urgences
    urgences:                       list[Urgence]

    # E — Alertes cohérence
    alertes_coherence:              list[AlerteCoherence]

    # F — Forces
    forces:                         list[str]

    # G — Faiblesses
    faiblesses:                     list[str]

    # H — Actions recommandées
    actions:                        list[str]

    # Métadonnées
    score_global_dossier:           int
    niveau_preparation:             str  # "insuffisant" | "moyen" | "bon" | "excellent"
    questions_levier:               list[QuestionLevier]
    synthese_executive:             str  # résumé 2-3 phrases pour le professionnel


# ─────────────────────────────────────────────────────────────────────────────
# DÉTECTION D'URGENCES
# ─────────────────────────────────────────────────────────────────────────────

import re

def _detecter_urgences(donnees: dict) -> list[Urgence]:
    """Détecte les situations d'urgence MDPH (P3 1-6)."""
    urgences = []
    texte = " ".join(str(donnees.get(c, "") or "") for c in [
        "historique_mdph", "droits_demandes", "statut_emploi",
        "impact_quotidien", "notes_pro",
    ]).lower()

    # P3 1 — Fin de droits imminente
    if re.search(r"renouvellement|r[eé][eé]valuation|[eé]ch[eé]ance|expire|arrive.{0,15}(fin|terme)", texte):
        urgences.append(Urgence(
            type="FIN_DROITS",
            description="Un droit (AAH, PCH, AEEH, RQTH) semble en cours de renouvellement. Si l'échéance est dans < 2 mois, traitement prioritaire possible.",
            action="Vérifier la date d'échéance exacte et cocher P3 1 si < 2 mois.",
            champ_cerfa="Case à cocher P3 1",
            priorite="critique",
        ))

    # P3 4 — Sortie hospitalisation
    if re.search(r"sortie.{0,20}(h[oô]pital|hospitalisation|r[eé][eé]ducation)|hospitalis.{0,15}r[eé]cent", texte):
        urgences.append(Urgence(
            type="SORTIE_HOSPITALISATION",
            description="Sortie d'hospitalisation récente identifiée — situation potentiellement urgente.",
            action="Vérifier si retour domicile possible. Cocher P3 4 si urgence avérée.",
            champ_cerfa="Case à cocher P3 4",
            priorite="haute",
        ))

    # P3 6 — Emploi/formation imminent
    if re.search(r"(commence|d[eé]marre|embauche|d[eé]but).{0,20}(bient[oô]t|dans|prochainement)|nouvel.{0,15}(emploi|poste|contrat)", texte):
        urgences.append(Urgence(
            type="EMPLOI_IMMINENT",
            description="Début d'emploi ou de formation imminent identifié — RQTH urgente pour la prise de poste.",
            action="Cocher P3 6. Procédure simplifiée RQTH (P4 2) si applicable.",
            champ_cerfa="Case à cocher P3 6 + P4 2",
            priorite="haute",
        ))

    # Procédure simplifiée renouvellement
    if re.search(r"renouvellement.{0,15}(RQTH|AAH|PCH|AEEH)", texte) and \
       not re.search(r"situation.{0,15}(a chang[eé]|[eé]volu[eé])", texte):
        urgences.append(Urgence(
            type="PROCEDURE_SIMPLIFIEE",
            description="Renouvellement sans évolution de situation — procédure simplifiée disponible pour réduire le délai.",
            action="Cocher P4 0 (procédure simplifiée renouvellement) pour accélérer le traitement.",
            champ_cerfa="Case à cocher P4 0",
            priorite="moyenne",
        ))

    return urgences


# ─────────────────────────────────────────────────────────────────────────────
# ALERTES DE COHÉRENCE
# ─────────────────────────────────────────────────────────────────────────────

def _detecter_alertes_coherence(donnees: dict, profil_mdph: str,
                                  eligibilite: ResultatEligibiliteComplete) -> list[AlerteCoherence]:
    """Détecte les incohérences potentielles dans le dossier."""
    alertes = []
    droits = str(donnees.get("droits_demandes", "") or "").upper()

    # Enfant sans AEEH
    if profil_mdph == "enfant" and "AEEH" not in droits:
        alertes.append(AlerteCoherence(
            type="DROIT_MANQUANT_ENFANT",
            message="Dossier enfant sans AEEH déclarée.",
            impact="L'AEEH est la prestation de base pour tout enfant handicapé. Son absence peut signifier un oubli.",
        ))

    # PCH demandé sans aide humaine documentée
    if "PCH" in droits:
        texte_b = str(donnees.get("texte_b_vie_quotidienne", "") or "").lower()
        impact = str(donnees.get("impact_quotidien", "") or "").lower()
        if not re.search(r"aide|tierce personne|aidant|toilette|habill|manger|d[eé]placement", texte_b + impact):
            alertes.append(AlerteCoherence(
                type="PCH_SANS_AIDE",
                message="PCH demandée sans mention d'aide humaine dans les textes.",
                impact="L'évaluateur MDPH cherchera des preuves des actes nécessitant aide. Sans documentation, la PCH peut être refusée.",
            ))

    # ESAT adulte sans DI/psychique
    if "ESAT" in droits and profil_mdph == "adulte":
        diag = str(donnees.get("diagnostics", "") or "").lower()
        if not re.search(r"d[eé]ficience|DI|trisomie|psychique|schizophr|bipolaire", diag):
            alertes.append(AlerteCoherence(
                type="ESAT_PROFIL_INATTENDU",
                message="ESAT demandé mais diagnostic habituel (DI, psychique) non identifié.",
                impact="À vérifier : l'ESAT est indiqué principalement pour DI et handicap psychique.",
            ))

    # Adulte sans aucun droit emploi ni vie quotidienne
    if profil_mdph == "adulte" and droits and \
       not any(d in droits for d in ["AAH", "RQTH", "PCH", "CMI", "SAVS", "ESAT"]):
        alertes.append(AlerteCoherence(
            type="PROFIL_INCOMPLET",
            message="Aucun droit vie quotidienne ni emploi identifié pour un adulte.",
            impact="Vérifier que les droits principaux ont bien été envisagés.",
        ))

    return alertes


# ─────────────────────────────────────────────────────────────────────────────
# ORIENTATIONS SUGGÉRÉES
# ─────────────────────────────────────────────────────────────────────────────

def _identifier_orientations(donnees: dict, profil_mdph: str,
                               eligibilite: ResultatEligibiliteComplete) -> list[str]:
    """Identifie les orientations potentielles selon le profil."""
    orientations = []
    texte = " ".join(str(donnees.get(c, "") or "") for c in [
        "diagnostics", "impact_quotidien", "statut_emploi", "projet_orientation",
        "droits_demandes", "situation_scolaire",
    ]).lower()

    # Enfant
    if profil_mdph in ("enfant", "mixte"):
        if re.search(r"TSA|autisme|TDAH|DYS|TND", texte, re.I):
            orientations.append("SESSAD spécialisé TND — maintien en milieu scolaire ordinaire avec soutien")
        if re.search(r"d[eé]ficience.{0,15}intellectuelle.{0,15}mod[eé]r[eé]e|DI.{0,5}mod[eé]r[eé]e", texte):
            orientations.append("IME — accompagnement éducatif et soins en établissement")
        if re.search(r"polyhandicap|grabataire|d[eé]pendance totale", texte):
            orientations.append("EEAP — établissement pour enfants polyhandicapés")
        if re.search(r"ULIS", texte, re.I):
            orientations.append("Maintien en ULIS avec SESSAD complémentaire")

    # Adulte emploi
    if profil_mdph in ("adulte", "protege", "mixte"):
        if re.search(r"sans emploi|arr[eê]t|inactif", texte) and \
           not re.search(r"projet.{0,20}(clair|d[eé]fini|trouv[eé])", texte):
            orientations.append("ESPO — bilan et orientation professionnelle adaptée")
        if re.search(r"accident du travail|inapte.{0,15}(ancien|poste).{0,15}reconversion", texte):
            orientations.append("ESRP — rééducation et reconversion professionnelle")
        if re.search(r"TSA.{0,15}adulte|DI.{0,5}l[eé]g[eè]re.{0,15}(emploi|travail)", texte):
            orientations.append("Emploi accompagné (EA) — soutien pour intégration en milieu ordinaire")
        if re.search(r"d[eé]ficience.{0,15}intellectuelle.{0,15}(mod[eé]r[eé]e|l[eé]g[eè]re).{0,30}travail", texte) or \
           re.search(r"ESAT", texte, re.I):
            orientations.append("ESAT — travail en milieu protégé avec accompagnement adapté")

    # Adulte vie quotidienne / hébergement
    if profil_mdph in ("adulte", "protege", "mixte"):
        if re.search(r"psychique|bipolaire|schizophr|TSA.{0,15}adulte", texte, re.I) and \
           re.search(r"domicile|autonomie.{0,15}partielle", texte):
            orientations.append("SAVS — accompagnement à la vie sociale pour maintien à domicile")
        if re.search(r"d[eé]ficience.{0,15}intellectuelle.{0,15}adulte", texte) and \
           not re.search(r"ESAT", texte, re.I):
            orientations.append("Foyer de vie — hébergement accompagné pour adultes DI")
        if re.search(r"ESAT.{0,30}(logement|h[eé]bergement)", texte) or \
           (re.search(r"ESAT", texte, re.I) and re.search(r"ne peut pas vivre seul", texte)):
            orientations.append("Foyer d'hébergement — hébergement pour travailleurs ESAT")
        if re.search(r"polyhandicap.{0,15}adulte|d[eé]pendance totale.{0,15}adulte", texte):
            orientations.append("MAS ou FAM — hébergement médicalisé pour polyhandicap adulte sévère")

    return orientations


# ─────────────────────────────────────────────────────────────────────────────
# NIVEAU DE PRÉPARATION
# ─────────────────────────────────────────────────────────────────────────────

def _niveau_preparation(score: int) -> str:
    if score >= 80: return "excellent"
    if score >= 60: return "bon"
    if score >= 40: return "moyen"
    return "insuffisant"


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def analyser_strategie(
    donnees: dict[str, Any],
    profil_mdph: str = "adulte",
    profil_handicap: str = "",
) -> StrategieDossier:
    """
    Analyse stratégique complète avant génération CERFA.

    Ne modifie pas le dossier — analyse uniquement.
    Résultat à stocker dans synthese_json["analyse_situation_json"].

    Args:
        donnees:       synthese_json complet du dossier
        profil_mdph:   "adulte" | "enfant" | "protege" | "mixte"
        profil_handicap: optionnel — "tsa" | "psychique" | "moteur" | etc.

    Returns:
        StrategieDossier complet
    """
    logger.info(f"Stratégie dossier — profil: {profil_mdph}")

    # ── 1. Éligibilité ────────────────────────────────────────────────────────
    eligibilite: ResultatEligibiliteComplete = analyser_eligibilite(
        donnees, profil_mdph, profil_handicap
    )

    # ── 2. Robustesse ─────────────────────────────────────────────────────────
    droits_a_noter = list(eligibilite.droits_demandes) + eligibilite.droits_omis_probables[:5]
    robustesse: RobustesseDossier = noter_robustesse(
        donnees, profil_mdph, droits_a_noter or None
    )

    # ── 3. Questions levier ───────────────────────────────────────────────────
    droits_cibles = eligibilite.droits_demandes + eligibilite.droits_omis_probables[:3]
    questions = identifier_questions_levier(
        donnees, profil_mdph, droits_cibles, n_max=5
    )

    # ── 4. Urgences ───────────────────────────────────────────────────────────
    urgences = _detecter_urgences(donnees)

    # ── 5. Alertes cohérence ──────────────────────────────────────────────────
    alertes = _detecter_alertes_coherence(donnees, profil_mdph, eligibilite)

    # ── 6. Droits omis (enrichis) ─────────────────────────────────────────────
    droits_omis: list[DrOublie] = []
    for droit_id in eligibilite.droits_omis_probables:
        analyse: AnalyseEligibilite = eligibilite.analyses[droit_id]
        # Construire justification lisible
        if analyse.forces:
            justif = f"Éléments compatibles détectés : {analyse.forces[0]}"
            if len(analyse.forces) > 1:
                justif += f" + {analyse.forces[1]}"
        else:
            justif = f"Profil potentiellement compatible avec {analyse.label}"

        action = (
            f"Vérifier avec la personne : {analyse.questions_complementaires[0]}"
            if analyse.questions_complementaires
            else f"Vérifier l'éligibilité à {analyse.label}"
        )

        droits_omis.append(DrOublie(
            droit=droit_id,
            label=analyse.label,
            score_compatibilite=analyse.eligibilite_estimee,
            niveau_confiance=analyse.niveau_confiance,
            justification=justif,
            action_suggeree=action,
        ))

    # Trier par score décroissant
    droits_omis.sort(key=lambda d: -d.score_compatibilite)

    # ── 7. Orientations ───────────────────────────────────────────────────────
    orientations = _identifier_orientations(donnees, profil_mdph, eligibilite)

    # ── 8. Scores droits demandés ─────────────────────────────────────────────
    scores_demandes = {
        d: robustesse.scores_par_droit.get(d, robustesse.score_global)
        for d in eligibilite.droits_demandes
    }

    # ── 9. Actions recommandées ───────────────────────────────────────────────
    actions: list[str] = []

    if urgences:
        for u in urgences:
            if u.priorite == "critique":
                actions.append(f"⚠️ URGENT — {u.action}")

    if droits_omis:
        top_omis = droits_omis[:2]
        for d in top_omis:
            actions.append(
                f"Droit potentiellement oublié ({d.niveau_confiance}) — "
                f"{d.label} : {d.action_suggeree}"
            )

    if robustesse.axes_amelioration:
        actions.append(robustesse.axes_amelioration[0])

    if alertes:
        for a in alertes[:2]:
            actions.append(f"Vérifier cohérence : {a.message}")

    if not donnees.get("texte_b_vie_quotidienne"):
        actions.append("PRIORITÉ — Générer le narratif B avant production CERFA")

    # ── 10. Synthèse exécutive ────────────────────────────────────────────────
    parties_synthese = []

    nb_demandes = len(eligibilite.droits_demandes)
    nb_omis = len(droits_omis)
    score = robustesse.score_global
    niveau = _niveau_preparation(score)

    parties_synthese.append(
        f"Dossier {niveau} (robustesse {score}/100) — "
        f"{nb_demandes} droit(s) demandé(s)."
    )

    if nb_omis > 0:
        top_labels = ", ".join(d.label.split("(")[0].strip() for d in droits_omis[:2])
        parties_synthese.append(
            f"{nb_omis} droit(s) potentiellement omis : {top_labels}"
            + (f" (et {nb_omis-2} autre(s))" if nb_omis > 2 else "")
        )

    if urgences:
        parties_synthese.append(f"{len(urgences)} situation(s) d'urgence détectée(s).")

    if robustesse.points_faibles:
        parties_synthese.append(f"Axe prioritaire : {robustesse.points_faibles[0]}")

    return StrategieDossier(
        droits_demandes=eligibilite.droits_demandes,
        scores_droits_demandes=scores_demandes,
        droits_omis=droits_omis,
        orientations_suggerees=orientations,
        urgences=urgences,
        alertes_coherence=alertes,
        forces=robustesse.points_forts,
        faiblesses=robustesse.points_faibles,
        actions=actions[:8],  # Maximum 8 actions
        score_global_dossier=score,
        niveau_preparation=niveau,
        questions_levier=questions,
        synthese_executive=" | ".join(parties_synthese),
    )


def strategie_to_dict(strategie: StrategieDossier) -> dict:
    """Sérialise la stratégie pour stockage dans analyse_situation_json."""
    return {
        "droits_demandes":          strategie.droits_demandes,
        "scores_droits_demandes":   strategie.scores_droits_demandes,
        "droits_omis": [
            {
                "droit":              d.droit,
                "label":              d.label,
                "score":              d.score_compatibilite,
                "confiance":          d.niveau_confiance,
                "justification":      d.justification,
                "action":             d.action_suggeree,
            }
            for d in strategie.droits_omis
        ],
        "orientations":             strategie.orientations_suggerees,
        "urgences": [
            {
                "type":         u.type,
                "description":  u.description,
                "action":       u.action,
                "priorite":     u.priorite,
                "champ_cerfa":  u.champ_cerfa,
            }
            for u in strategie.urgences
        ],
        "alertes_coherence": [
            {
                "type":     a.type,
                "message":  a.message,
                "impact":   a.impact,
            }
            for a in strategie.alertes_coherence
        ],
        "forces":                   strategie.forces,
        "faiblesses":               strategie.faiblesses,
        "actions":                  strategie.actions,
        "score_global":             strategie.score_global_dossier,
        "niveau_preparation":       strategie.niveau_preparation,
        "questions_levier": [
            {
                "question":       q.question,
                "droit":          q.droit_concerne,
                "roi":            round(q.roi, 1),
                "champ_cerfa":    q.champ_cerfa,
            }
            for q in strategie.questions_levier
        ],
        "synthese":                 strategie.synthese_executive,
    }
