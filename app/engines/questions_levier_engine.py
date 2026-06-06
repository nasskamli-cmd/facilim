"""
app/engines/questions_levier_engine.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FACILIM 60 — Moteur 3 : Questions à fort levier

Identifie les 3 à 5 questions qui augmenteraient le plus fortement
les chances d'obtenir les droits — sans surcharger l'usager.

Critère de sélection :
  ROI = (impact sur le droit × spécificité de la question) / effort demandé

Ne jamais poser une question vague.
Poser uniquement des questions dont la réponse peut directement
alimenter le CERFA ou renforcer le narratif.

Usage :
  from app.engines.questions_levier_engine import identifier_questions_levier
  questions = identifier_questions_levier(donnees, profil_mdph="adulte",
                                           droits_cibles=["AAH", "PCH"])
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("facilim.engines.questions_levier")


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURE
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class QuestionLevier:
    question:           str     # La question à poser à l'usager
    droit_concerne:     str     # Droit(s) bénéficiaires
    champ_cerfa:        str     # Champ CERFA que la réponse peut alimenter
    impact_estime:      int     # 0-100 : impact sur le score du droit
    effort_usager:      int     # 1=très facile, 2=moyen, 3=difficile
    roi:                float   # impact / effort
    contexte_interne:   str     # Pourquoi cette question est posée (pour le professionnel)
    categorie:          str     # "aide_humaine" | "limitations" | "emploi" | etc.


# ─────────────────────────────────────────────────────────────────────────────
# BIBLIOTHÈQUE DE QUESTIONS
# Chaque question est définie avec ses conditions de déclenchement
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _QuestionTemplate:
    question:           str
    droit_concerne:     str
    champ_cerfa:        str
    impact_estime:      int
    effort_usager:      int
    categorie:          str
    contexte_interne:   str
    condition_absente:  list[str]   # patterns dont l'absence déclenche la question
    condition_presente: list[str]   # patterns dont la présence est nécessaire


_QUESTIONS_TEMPLATES: list[_QuestionTemplate] = [

    # ── AIDE HUMAINE ──────────────────────────────────────────────────────────
    _QuestionTemplate(
        question="Combien de fois par semaine avez-vous besoin d'aide pour la toilette ou la douche ? Quelqu'un vous aide-t-il pour cela ?",
        droit_concerne="PCH",
        champ_cerfa="Champ de texte P8 1 + Case à cocher P6 4",
        impact_estime=35, effort_usager=1,
        categorie="aide_humaine",
        contexte_interne="Critère central PCH catégorie 1 (hygiène). Si aide ≥ 1/semaine, PCH probable.",
        condition_absente=[r"toilette|douche|lavage|aide.{0,15}(matin|hygi[eè]ne)"],
        condition_presente=[r"PCH|aide humaine|tierce personne|marche.{0,15}difficile|scl[eé]rose|paralys"],
    ),
    _QuestionTemplate(
        question="Pouvez-vous vous déplacer seul(e) à l'extérieur de votre domicile ? Si non, quelle est la distance maximale sans aide ?",
        droit_concerne="PCH / CMI Stationnement",
        champ_cerfa="Case à cocher P6 B6/B7 + P7 2/3",
        impact_estime=30, effort_usager=1,
        categorie="mobilite",
        contexte_interne="Déplacement extérieur impossible → PCH volet déplacement. Distance < 200m → CMI stationnement.",
        condition_absente=[r"p[eé]rim[eè]tre|distance.{0,10}march|extérieur.{0,15}impossible|seul.{0,15}impossible"],
        condition_presente=[r"marche.{0,15}difficile|fauteuil|canne|scl[eé]rose|moteur"],
    ),
    _QuestionTemplate(
        question="Pouvez-vous vous habiller seul(e) ? Y a-t-il des vêtements ou des gestes que vous ne pouvez plus faire ?",
        droit_concerne="PCH",
        champ_cerfa="Champ de texte P8 1",
        impact_estime=20, effort_usager=1,
        categorie="aide_humaine",
        contexte_interne="Habillage = critère PCH catégorie 1. Souvent oublié dans les données.",
        condition_absente=[r"habill|vêtement|s'habiller"],
        condition_presente=[r"PCH|aide humaine|moteur|tétraplégie|hémiplégie|polyhandicap"],
    ),
    _QuestionTemplate(
        question="Cuisinez-vous seul(e) ? Y a-t-il des jours où il vous est impossible de préparer un repas ?",
        droit_concerne="PCH / AAH",
        champ_cerfa="Case à cocher P6 B4",
        impact_estime=18, effort_usager=1,
        categorie="aide_humaine",
        contexte_interne="Préparation repas = critère PCH. Impossible certains jours → variabilité à documenter.",
        condition_absente=[r"repas|cuisine|manger|préparer.{0,10}repas"],
        condition_presente=[r"PCH|aide|fatigue|douleur|bipolaire|SEP|fibro"],
    ),

    # ── LIMITATIONS EMPLOI ────────────────────────────────────────────────────
    _QuestionTemplate(
        question="Depuis combien de temps exactement êtes-vous en arrêt de travail ou sans emploi ? Avez-vous une pension d'invalidité ?",
        droit_concerne="AAH",
        champ_cerfa="Case à cocher P14 2/3 + P5 16",
        impact_estime=35, effort_usager=1,
        categorie="emploi",
        contexte_interne="Durée arrêt > 1 an + pension invalidité → AAH différentielle très probable.",
        condition_absente=[r"pension.{0,15}invalidit[eé]|\d+.{0,10}(ans?|mois).{0,15}arr[eê]t|depuis.{0,10}\d"],
        condition_presente=[r"arr[eê]t|sans emploi|inaptitude|AAH|maladie chronique"],
    ),
    _QuestionTemplate(
        question="Un médecin a-t-il évalué votre taux d'incapacité permanente ? Si oui, quel est ce taux ?",
        droit_concerne="AAH / CMI Invalidité",
        champ_cerfa="Champ de texte P5 Taux d'IPP",
        impact_estime=30, effort_usager=2,
        categorie="emploi",
        contexte_interne="Taux IPP documenté → AAH 1 si ≥ 80%. Indispensable pour CMI invalidité.",
        condition_absente=[r"taux.{0,10}(incapacit[eé]|IPP|80|90)", r"incapacit[eé] permanente"],
        condition_presente=[r"accident du travail|invalidit[eé]|AAH|rente AT"],
    ),
    _QuestionTemplate(
        question="Quelles tâches professionnelles ne pouvez-vous plus effectuer à cause de votre handicap ? Des aménagements de poste ont-ils été demandés ?",
        droit_concerne="RQTH",
        champ_cerfa="Champ de texte P13 7/8 + Case P 13 1/2",
        impact_estime=25, effort_usager=1,
        categorie="emploi",
        contexte_interne="Impact emploi concret → renforce RQTH et section D du CERFA.",
        condition_absente=[r"am[eé]nagement.{0,10}poste|tâche.{0,15}impossible|ne peut plus.{0,15}(travail|poste)"],
        condition_presente=[r"RQTH|travaille|emploi|professionnel"],
    ),

    # ── SCOLARITÉ ENFANT ──────────────────────────────────────────────────────
    _QuestionTemplate(
        question="Votre enfant a-t-il une AESH ? Est-ce une AESH individuelle ou mutualisée ? Combien d'heures par semaine ?",
        droit_concerne="AEEH",
        champ_cerfa="Case à cocher P10 1 + Champ P10 TABLEAU A",
        impact_estime=30, effort_usager=1,
        categorie="scolarite",
        contexte_interne="AESH individuelle → AEEH complément cat. 1 ou 2. Heures → quantifier le besoin.",
        condition_absente=[r"AESH.{0,15}(individuelle|mutualisée|\d+.h)", r"\d+.{0,5}heures?.{0,10}AESH"],
        condition_presente=[r"AESH|AVS|accompagnant"],
    ),
    _QuestionTemplate(
        question="L'un de vos parents a-t-il réduit ou arrêté son activité professionnelle pour s'occuper de votre enfant ? Si oui, depuis quand et de combien ?",
        droit_concerne="AVPF",
        champ_cerfa="Case à cocher P17 4 + Case à cocher P4 1",
        impact_estime=30, effort_usager=1,
        categorie="scolarite",
        contexte_interne="Réduction activité + AEEH → AVPF. Trimestres retraite perdus sinon.",
        condition_absente=[r"r[eé]duction.{0,10}activit[eé]|mi-temps.{0,10}parent|arr[eê]t.{0,10}(pour|aidant)"],
        condition_presente=[r"enfant|AEEH|parent.{0,10}(travail|emploi)"],
    ),

    # ── URGENCES ──────────────────────────────────────────────────────────────
    _QuestionTemplate(
        question="Un de vos droits (AAH, PCH, AEEH, RQTH) arrive-t-il à échéance dans les 2 prochains mois ?",
        droit_concerne="Urgence P3 1",
        champ_cerfa="Case à cocher P3 1",
        impact_estime=40, effort_usager=1,
        categorie="urgence",
        contexte_interne="Fin de droits < 2 mois = urgence MDPH → traitement en 6 semaines au lieu de 4 mois.",
        condition_absente=[r"[eé]ch[eé]ance|expire|renouvellement.{0,15}urgent|dans.{0,5}(2|deux).{0,5}mois"],
        condition_presente=[r"renouvellement|AAH|PCH|AEEH|RQTH"],
    ),
    _QuestionTemplate(
        question="Avez-vous trouvé un emploi ou commencez-vous une formation bientôt, et attendez-vous la RQTH pour démarrer ?",
        droit_concerne="Urgence P3 6",
        champ_cerfa="Case à cocher P3 6",
        impact_estime=35, effort_usager=1,
        categorie="urgence",
        contexte_interne="Nouvel emploi qui attend RQTH → urgence P3 6 → traitement accéléré.",
        condition_absente=[r"commence.{0,15}(bientôt|dans|prochainement)|nouvel.{0,15}(emploi|poste)|attend.{0,10}RQTH"],
        condition_presente=[r"RQTH|emploi|travail|formation"],
    ),

    # ── PROJET DE VIE ─────────────────────────────────────────────────────────
    _QuestionTemplate(
        question="Quel type d'accompagnement ou de service vous aiderait le plus pour améliorer votre quotidien ou votre situation professionnelle ?",
        droit_concerne="Projet de vie (E)",
        champ_cerfa="Champ de texte P16 1 + P16 2",
        impact_estime=20, effort_usager=2,
        categorie="projet",
        contexte_interne="Réponse → texte E. Orientation concrète → P16 1/2.",
        condition_absente=[r"souhait|voudrait?|aimerait?|projet.{0,20}vie|objectif"],
        condition_presente=[],  # Toujours pertinent si texte E absent
    ),
    _QuestionTemplate(
        question="Souhaitez-vous travailler en milieu ordinaire (avec adaptations), en ESAT, ou avez-vous besoin d'un bilan d'orientation professionnelle ?",
        droit_concerne="RQTH / ESAT / ESPO",
        champ_cerfa="Case à cocher P16 1/2 + P18 3/4",
        impact_estime=25, effort_usager=1,
        categorie="projet",
        contexte_interne="Choix orientation → P16 1 ou 2. Pas de projet → ESPO P18 3.",
        condition_absente=[r"milieu ordinaire|ESAT|ESPO|bilan.{0,15}orientation|pas de projet"],
        condition_presente=[r"RQTH|adulte|emploi|travail"],
    ),

    # ── AIDE FINANCIÈRE ───────────────────────────────────────────────────────
    _QuestionTemplate(
        question="Percevez-vous le RSA, une allocation chômage (ARE) ou une autre aide financière actuellement ?",
        droit_concerne="AAH (calcul ressources)",
        champ_cerfa="Case à cocher P5 10 / P5 20",
        impact_estime=15, effort_usager=1,
        categorie="ressources",
        contexte_interne="RSA + ARE → ressources qui réduisent AAH différentielle. À déclarer pour calcul exact.",
        condition_absente=[r"\bRSA\b|\bARE\b|ch[oô]mage.{0,10}alloc"],
        condition_presente=[r"AAH|sans emploi"],
    ),

    # ── PROTECTION JURIDIQUE ──────────────────────────────────────────────────
    _QuestionTemplate(
        question="Avez-vous un tuteur, un curateur ou une habilitation familiale ? Si oui, depuis quelle date et quel tribunal a prononcé cette mesure ?",
        droit_concerne="Protection juridique (P3 A4)",
        champ_cerfa="REPRESENTANT LEGAL 1-6 + Date P3 1",
        impact_estime=25, effort_usager=1,
        categorie="protection",
        contexte_interne="Mesure de protection → REPRESENTANT LEGAL obligatoire. Date → vérification validité.",
        condition_absente=[r"tribunal|jugement|date.{0,10}(mesure|protection|tutelle)", r"depuis.{0,10}(tutelle|curatelle)"],
        condition_presente=[r"tutelle|curatelle|habilitation|protég[eé]|protect"],
    ),

    # ── CONSENTEMENT ─────────────────────────────────────────────────────────
    _QuestionTemplate(
        question="Acceptez-vous que la MDPH contacte vos médecins, votre école ou votre employeur pour compléter l'évaluation de votre dossier ?",
        droit_concerne="Consentement échanges (P4 4)",
        champ_cerfa="Case à cocher P4 4",
        impact_estime=20, effort_usager=1,
        categorie="consentement",
        contexte_interne="Sans ce consentement, la MDPH évalue uniquement sur les pièces fournies → risque de sous-évaluation.",
        condition_absente=[r"consent|accepte.{0,20}([eé]changes?|contacts?)|autorise.{0,20}MDPH"],
        condition_presente=[],  # Toujours poser si consentement absent
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────────────────────

def identifier_questions_levier(
    donnees: dict[str, Any],
    profil_mdph: str = "adulte",
    droits_cibles: list[str] | None = None,
    n_max: int = 5,
) -> list[QuestionLevier]:
    """
    Identifie les N questions à plus fort levier pour ce dossier.

    Args:
        donnees:       synthese_json du dossier
        profil_mdph:   "adulte" | "enfant" | "protege" | "mixte"
        droits_cibles: droits pour lesquels prioriser les questions
        n_max:         nombre maximum de questions à retourner (défaut 5)

    Returns:
        Liste de QuestionLevier triée par ROI décroissant
    """
    # Construire texte complet pour détection
    champs = [
        "diagnostics", "impact_quotidien", "restrictions_emploi", "statut_emploi",
        "notes_pro", "texte_b_vie_quotidienne", "texte_c_scolarite",
        "texte_d_situation_pro", "texte_e_projet_vie", "aidant_besoins",
        "droits_demandes", "historique_mdph", "expression_directe",
    ]
    texte = " ".join(str(donnees.get(c, "") or "") for c in champs).lower()

    # Verbatims
    for c in ["_verbatim_b", "_verbatim_c", "_verbatim_d", "_verbatim_e"]:
        lst = donnees.get(c) or []
        if isinstance(lst, list):
            texte += " " + " ".join(str(x) for x in lst)

    candidates: list[QuestionLevier] = []

    for tmpl in _QUESTIONS_TEMPLATES:

        # Filtrer par profil
        if profil_mdph == "enfant" and tmpl.categorie in ("emploi",):
            continue
        if profil_mdph == "adulte" and tmpl.categorie in ("scolarite",):
            # Sauf si enfant dans le dossier
            if not donnees.get("representant_legal_nom") and "enfant" not in texte[:50]:
                continue

        # Filtrer par droits cibles
        if droits_cibles:
            droit_match = any(d in tmpl.droit_concerne for d in droits_cibles)
            if not droit_match and tmpl.categorie not in ("urgence", "consentement"):
                continue

        # Vérifier condition présente (signal nécessaire pour déclencher la question)
        if tmpl.condition_presente:
            signal_ok = any(
                re.search(p, texte, re.IGNORECASE)
                for p in tmpl.condition_presente
            )
            if not signal_ok:
                continue

        # Vérifier condition absente (signal manquant → question pertinente)
        if tmpl.condition_absente:
            signal_manquant = all(
                not re.search(p, texte, re.IGNORECASE)
                for p in tmpl.condition_absente
            )
            if not signal_manquant:
                continue  # Signal déjà présent → question inutile

        roi = tmpl.impact_estime / tmpl.effort_usager

        candidates.append(QuestionLevier(
            question=tmpl.question,
            droit_concerne=tmpl.droit_concerne,
            champ_cerfa=tmpl.champ_cerfa,
            impact_estime=tmpl.impact_estime,
            effort_usager=tmpl.effort_usager,
            roi=roi,
            contexte_interne=tmpl.contexte_interne,
            categorie=tmpl.categorie,
        ))

    # Trier par ROI décroissant
    candidates.sort(key=lambda q: (-q.roi, -q.impact_estime))

    # Dédupliquer par catégorie (max 2 questions par catégorie)
    seen_categories: dict[str, int] = {}
    filtered: list[QuestionLevier] = []
    for q in candidates:
        cat_count = seen_categories.get(q.categorie, 0)
        if cat_count < 2:
            filtered.append(q)
            seen_categories[q.categorie] = cat_count + 1
        if len(filtered) >= n_max:
            break

    return filtered[:n_max]
