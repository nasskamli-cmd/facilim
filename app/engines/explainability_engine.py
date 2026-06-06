"""
app/engines/explainability_engine.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FACILIM 80 — Moteur d'explicabilité (Explainability Engine)

Explique toutes les décisions prises par Facilim :
  - Pourquoi un droit est proposé ou écarté
  - Pourquoi un score est tel qu'il est
  - Quelles preuves soutiennent chaque décision
  - Quelles actions renforceraient le dossier

Couche d'audit et de transparence sur les moteurs existants.
Ne modifie aucune logique métier.

Usage :
  from app.engines.explainability_engine import expliquer_dossier
  rapport = expliquer_dossier(donnees, profil_mdph="adulte")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("facilim.engines.explainability")


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURES DE DONNÉES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ExplicationDroit:
    droit:                  str
    label:                  str
    score:                  int             # 0-100
    confiance:              str             # "forte" | "moyenne" | "faible"
    est_solide:             bool            # score ≥ 70
    preuves:                list[str]       # descriptions des preuves
    sources:                list[str]       # types de sources ("WhatsApp", "Document"...)
    citations:              list[str]       # extraits textuels exacts
    faiblesses:             list[str]       # lacunes identifiées
    pieces_renforcantes:    list[str]       # pièces qui renforceraient
    actions_recommandees:   list[str]
    raisonnement_cdaph:     str             # "La CDAPH valide X si..."


@dataclass
class ExplicationScore:
    score_cdaph:    int
    detail: dict[str, int]    # {critere: score}
    explication_par_critere: dict[str, str]   # {critere: explication}

    def to_dict(self) -> dict:
        return {
            "score_cdaph":  self.score_cdaph,
            "detail":       self.detail,
            "explications": self.explication_par_critere,
        }


@dataclass
class ExplicationOrientation:
    orientation:            str
    label:                  str
    justifications:         list[str]
    sources:                list[str]
    pieces_renforcantes:    list[str]
    confiance:              str


@dataclass
class ExplicationQuestion:
    question:           str
    impact_estime:      int
    droits_concernes:   list[str]
    raison:             str
    champ_cerfa:        str


@dataclass
class RapportExplicabilite:
    """Rapport complet d'explicabilité pour un dossier."""

    # Contexte
    profil_mdph:            str
    nb_sources_actives:     int
    sources_presentes:      list[str]
    sources_manquantes:     list[str]

    # Preuves
    nb_preuves:             int
    preuves_par_droit:      dict[str, int]

    # Scores
    explication_score:      ExplicationScore

    # Droits
    explications_solides:   list[ExplicationDroit]
    explications_fragiles:  list[ExplicationDroit]

    # Orientations
    explications_orientations: list[ExplicationOrientation]

    # Questions levier
    explications_questions: list[ExplicationQuestion]

    # Rapport professionnel (texte formaté)
    rapport_professionnel:  str

    def to_dict(self) -> dict:
        return {
            "contexte": {
                "profil_mdph":          self.profil_mdph,
                "nb_sources_actives":   self.nb_sources_actives,
                "sources_presentes":    self.sources_presentes,
                "sources_manquantes":   self.sources_manquantes,
                "nb_preuves":           self.nb_preuves,
            },
            "score": self.explication_score.to_dict(),
            "droits_solides": [
                {
                    "droit":            d.droit,
                    "label":            d.label,
                    "score":            d.score,
                    "confiance":        d.confiance,
                    "preuves":          d.preuves,
                    "sources":          d.sources,
                    "citations":        d.citations[:3],
                    "raisonnement":     d.raisonnement_cdaph,
                }
                for d in self.explications_solides
            ],
            "droits_fragiles": [
                {
                    "droit":                d.droit,
                    "label":               d.label,
                    "score":               d.score,
                    "faiblesses":          d.faiblesses,
                    "actions":             d.actions_recommandees,
                    "pieces_renforcantes": d.pieces_renforcantes,
                }
                for d in self.explications_fragiles
            ],
            "orientations": [
                {
                    "orientation":   o.orientation,
                    "justifications": o.justifications,
                    "sources":        o.sources,
                    "pieces":         o.pieces_renforcantes,
                }
                for o in self.explications_orientations
            ],
            "questions_levier": [
                {
                    "question":         q.question,
                    "impact":           q.impact_estime,
                    "droits":           q.droits_concernes,
                    "raison":           q.raison,
                    "champ_cerfa":      q.champ_cerfa,
                }
                for q in self.explications_questions
            ],
        }


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _confiance_label(score: int) -> str:
    if score >= 70: return "forte"
    if score >= 40: return "moyenne"
    return "faible"


# ─────────────────────────────────────────────────────────────────────────────
# EXPLICATION DES SCORES
# ─────────────────────────────────────────────────────────────────────────────

_EXPLICATIONS_CRITERES = {
    "preuves": {
        0:  "Aucune preuve documentaire — dossier entièrement déclaratif",
        30: "Preuves partielles — quelques éléments mais insuffisants pour la CDAPH",
        50: "Preuves satisfaisantes — base documentaire présente",
        70: "Bonnes preuves — bilans et texte B solides",
        90: "Très bonnes preuves — dossier bien étayé avec documents et verbatim",
    },
    "coherence": {
        0:  "Incohérences majeures détectées — risque de refus",
        30: "Cohérence partielle — quelques contradictions à clarifier",
        50: "Cohérence satisfaisante — triangle diagnostics/limitations/droits établi",
        70: "Bonne cohérence — chaîne causale claire",
        90: "Excellente cohérence — toutes les sections convergent",
    },
    "retentissement": {
        0:  "Retentissement non documenté — la CDAPH ne peut pas évaluer les besoins",
        30: "Retentissement vague — manque d'exemples concrets et de mesures",
        50: "Retentissement décrit — limitations présentes mais peu objectivées",
        70: "Bon retentissement — exemples concrets, fréquences, impossibilités nommées",
        90: "Excellent retentissement — quantifié, temporalisé, illustré par verbatim",
    },
    "projet": {
        0:  "Aucun projet de vie documenté — section E absente",
        30: "Projet vague — orientation non précisée",
        50: "Projet présent — objectifs identifiés",
        70: "Bon projet — cohérent avec les limitations, orientation réaliste",
        90: "Excellent projet — structure identifiée, plan précis, cohérence totale",
    },
    "justificatifs": {
        0:  "Aucun justificatif identifié",
        30: "Justificatifs partiels — pièces obligatoires manquantes",
        50: "Justificatifs corrects — pièces principales identifiées",
        70: "Bons justificatifs — liste complète produite",
        90: "Excellents justificatifs — toutes les pièces critiques présentes",
    },
}


def _expliquer_score_critere(critere: str, score: int) -> str:
    """Retourne l'explication textuelle d'un score sur un critère."""
    seuils = _EXPLICATIONS_CRITERES.get(critere, {})
    seuil_applicable = 0
    for s in sorted(seuils.keys()):
        if score >= s:
            seuil_applicable = s
    return seuils.get(seuil_applicable, f"Score {score}/100")


def _construire_explication_score(rapport_cdaph) -> ExplicationScore:
    """Construit l'explication détaillée des scores."""
    detail = {
        "preuves":         rapport_cdaph.score_preuves,
        "coherence":       rapport_cdaph.score_coherence,
        "retentissement":  rapport_cdaph.score_retentissement,
        "projet":          rapport_cdaph.score_projet,
        "justificatifs":   rapport_cdaph.score_justificatifs,
    }

    explications = {
        critere: _expliquer_score_critere(critere, score)
        for critere, score in detail.items()
    }

    return ExplicationScore(
        score_cdaph=rapport_cdaph.score_solidite,
        detail=detail,
        explication_par_critere=explications,
    )


# ─────────────────────────────────────────────────────────────────────────────
# EXPLICATION DES DROITS
# ─────────────────────────────────────────────────────────────────────────────

def _construire_explication_droit(
    droit_analyse,
    graphe_preuves,
) -> ExplicationDroit:
    """Construit l'explication complète d'un droit avec ses preuves traçables."""
    from app.engines.evidence_engine import EvidenceItem

    # Récupérer les preuves spécifiques à ce droit depuis le graphe
    preuves_droit = graphe_preuves.preuves_pour_droit(droit_analyse.droit)

    # Construire descriptions, sources, citations
    descriptions   = [p.information for p in preuves_droit]
    sources        = sorted(set(p.source_type for p in preuves_droit))
    citations      = [p.citation for p in preuves_droit if p.citation]

    # Enrichir avec les forces issues de l'analyse CDAPH
    for force in droit_analyse.forces:
        if len(force) > 10 and force not in descriptions:
            descriptions.append(force)

    # Pièces renforcantes (depuis pieces_manquantes de l'analyse)
    pieces = droit_analyse.pieces_manquantes[:3]

    # Actions recommandées (depuis l'analyse)
    actions = [f.replace("Pièce prioritaire absente : ", "Joindre : ").strip()
               for f in droit_analyse.faiblesses
               if "manquante" in f.lower() or "absente" in f.lower()]
    if not actions and droit_analyse.faiblesses:
        actions = [droit_analyse.faiblesses[0]]

    return ExplicationDroit(
        droit=droit_analyse.droit,
        label=droit_analyse.label,
        score=droit_analyse.robustesse_pct,
        confiance=_confiance_label(droit_analyse.robustesse_pct),
        est_solide=droit_analyse.robustesse_pct >= 70,
        preuves=descriptions[:5],
        sources=sources,
        citations=citations[:3],
        faiblesses=droit_analyse.faiblesses[:4],
        pieces_renforcantes=pieces,
        actions_recommandees=actions[:3],
        raisonnement_cdaph=droit_analyse.raisonnement_cdaph,
    )


# ─────────────────────────────────────────────────────────────────────────────
# EXPLICATION DES ORIENTATIONS
# ─────────────────────────────────────────────────────────────────────────────

_ORIENTATIONS_META = {
    "ESPO": {
        "label": "Évaluation et Soutien à l'Orientation Professionnelle",
        "pieces": ["CV ou historique professionnel", "Bilan de compétences si disponible"],
    },
    "SESSAD": {
        "label": "Service d'Éducation Spéciale et de Soins à Domicile",
        "pieces": ["GEVASCO", "Bilan orthophonique ou neuropsychologique", "Rapport scolaire"],
    },
    "ESAT": {
        "label": "Établissement et Service d'Aide par le Travail",
        "pieces": ["Bilan d'orientation professionnel", "Attestation capacités de travail"],
    },
    "SAVS": {
        "label": "Service d'Accompagnement à la Vie Sociale",
        "pieces": ["Compte-rendu psychiatrique récent", "Bilan d'autonomie"],
    },
    "IME": {
        "label": "Institut Médico-Éducatif",
        "pieces": ["Bilan neuropsychologique récent", "Rapport pédagogique école"],
    },
}


def _construire_explications_orientations(
    strategie,
    graphe_preuves,
) -> list[ExplicationOrientation]:
    """Construit les explications des orientations suggérées."""
    explications: list[ExplicationOrientation] = []

    for orientation_txt in strategie.orientations_suggerees[:5]:
        # Identifier la clé d'orientation
        cle = next(
            (k for k in _ORIENTATIONS_META if k in orientation_txt.upper()),
            None
        )
        meta = _ORIENTATIONS_META.get(cle or "", {
            "label": orientation_txt,
            "pieces": [],
        })

        # Preuves pour cette orientation (via les droits associés)
        preuves_assoc = graphe_preuves.preuves_pour_droit(cle or "")
        sources = sorted(set(p.source_type for p in preuves_assoc))
        justifications = [p.information for p in preuves_assoc[:3]]

        # Si pas de preuves directes, utiliser la description de l'orientation
        if not justifications:
            justifications = [orientation_txt[:80]]

        confiance = (
            "forte" if len(preuves_assoc) >= 3 else
            "moyenne" if len(preuves_assoc) >= 1 else "faible"
        )

        explications.append(ExplicationOrientation(
            orientation=cle or orientation_txt[:20],
            label=meta.get("label", orientation_txt),
            justifications=justifications,
            sources=sources or ["Inférence"],
            pieces_renforcantes=meta.get("pieces", []),
            confiance=confiance,
        ))

    return explications


# ─────────────────────────────────────────────────────────────────────────────
# EXPLICATION DES QUESTIONS LEVIER
# ─────────────────────────────────────────────────────────────────────────────

def _construire_explications_questions(questions_levier) -> list[ExplicationQuestion]:
    """Construit les explications des questions à fort levier."""
    from app.engines.questions_levier_engine import QuestionLevier

    explications: list[ExplicationQuestion] = []
    for q in questions_levier:
        if isinstance(q, str):
            # Format simple (texte seul)
            explications.append(ExplicationQuestion(
                question=q,
                impact_estime=25,
                droits_concernes=[],
                raison="Amélioration de la robustesse du dossier",
                champ_cerfa="P8 1 (Texte B)",
            ))
        elif hasattr(q, "question"):
            # Format QuestionLevier structuré
            explications.append(ExplicationQuestion(
                question=q.question,
                impact_estime=q.impact_estime,
                droits_concernes=[q.droit_concerne] if hasattr(q, "droit_concerne") else [],
                raison=getattr(q, "contexte_interne", "Amélioration de la robustesse"),
                champ_cerfa=getattr(q, "champ_cerfa", ""),
            ))

    return explications


# ─────────────────────────────────────────────────────────────────────────────
# RAPPORT PROFESSIONNEL FORMATÉ
# ─────────────────────────────────────────────────────────────────────────────

def _generer_rapport_professionnel(
    rapport_cdaph,
    strategie,
    explication_score: ExplicationScore,
    explications_solides: list[ExplicationDroit],
    explications_fragiles: list[ExplicationDroit],
    explications_orientations: list[ExplicationOrientation],
    explications_questions: list[ExplicationQuestion],
    graphe_preuves,
) -> str:
    """Génère le rapport professionnel formaté pour lecture directe."""
    sep = "═" * 54
    sep2 = "─" * 54

    def barre(score: int, largeur: int = 10) -> str:
        n = int(score / 100 * largeur)
        return "█" * n + "░" * (largeur - n)

    lines = [
        sep,
        f"  FACILIM — ANALYSE STRATÉGIQUE DOSSIER",
        sep,
        "",
    ]

    # Score global
    score = explication_score.score_cdaph
    niveau = (
        "TRÈS SOLIDE" if score >= 80 else
        "SOLIDE"      if score >= 65 else
        "MOYEN"       if score >= 45 else
        "FRAGILE"
    )
    lines += [
        f"  SCORE DE SOLIDITÉ : {score}/100 — {niveau}",
        f"  {barre(score, 20)}",
        "",
    ]

    # Sources actives
    if graphe_preuves.sources_presentes:
        lines += [
            f"  Sources actives : {' · '.join(graphe_preuves.sources_presentes)}",
            f"  Preuves extraites : {graphe_preuves.nb_preuves_total}",
        ]
    if graphe_preuves.sources_absentes:
        lines.append(f"  Sources manquantes : {', '.join(graphe_preuves.sources_absentes[:2])}")
    lines.append("")

    # Forces
    lines += [
        sep,
        "  FORCES DU DOSSIER",
        sep2,
    ]
    if rapport_cdaph.forces_globales:
        for f in rapport_cdaph.forces_globales[:5]:
            lines.append(f"  ✅ {f}")
    else:
        lines.append("  (Aucune force identifiée — enrichir le dossier)")
    lines.append("")

    # Faiblesses
    lines += [
        sep,
        "  FAIBLESSES DU DOSSIER",
        sep2,
    ]
    if rapport_cdaph.faiblesses_globales:
        for f in rapport_cdaph.faiblesses_globales[:5]:
            lines.append(f"  ⚠️  {f}")
    else:
        lines.append("  (Aucune faiblesse majeure identifiée)")
    lines.append("")

    # Droits solides
    lines += [
        sep,
        "  DROITS — PROFIL FAVORABLE",
        sep2,
    ]
    if explications_solides:
        for d in explications_solides:
            lines += [
                f"  ✅ {d.label}",
                f"     Robustesse : {d.score}%  {barre(d.score, 8)}  | Risque : FAIBLE",
                f"     Raisonnement : {d.raisonnement_cdaph[:80]}",
            ]
            if d.preuves:
                lines.append(f"     Preuves : {d.preuves[0][:70]}")
            if d.citations:
                lines.append(f"     Citation : « {d.citations[0][:70]} »")
            lines.append("")
    else:
        lines.append("  (Aucun droit à profil solide actuellement)")
    lines.append("")

    # Droits fragiles
    lines += [
        sep,
        "  DROITS FRAGILES — À RENFORCER",
        sep2,
    ]
    if explications_fragiles:
        for d in explications_fragiles:
            risque = "ÉLEVÉ" if d.score < 40 else "MOYEN"
            lines += [
                f"  ⚠️  {d.label}",
                f"     Robustesse : {d.score}%  {barre(d.score, 8)}  | Risque : {risque}",
                f"     Raisonnement : {d.raisonnement_cdaph[:80]}",
            ]
            if d.faiblesses:
                lines.append(f"     Faiblesse : {d.faiblesses[0][:70]}")
            if d.pieces_renforcantes:
                lines.append(f"     Pièce prioritaire : {d.pieces_renforcantes[0][:60]}")
            lines.append("")
    else:
        lines.append("  (Tous les droits analysés semblent solides)")
    lines.append("")

    # Questions levier
    lines += [
        sep,
        "  QUESTIONS À FORT LEVIER",
        sep2,
    ]
    if explications_questions:
        for i, q in enumerate(explications_questions[:5], 1):
            lines += [
                f"  {i}. {q.question}",
                f"     Impact estimé : {q.impact_estime}/100"
                + (f" | Droit : {q.droits_concernes[0]}" if q.droits_concernes else ""),
            ]
            if q.raison and len(q.raison) > 20:
                lines.append(f"     Pourquoi : {q.raison[:80]}")
            lines.append("")
    else:
        lines.append("  (Toutes les informations critiques semblent présentes)")
    lines.append("")

    # Pièces prioritaires
    toutes_pieces = []
    for d in explications_fragiles:
        for p in d.pieces_renforcantes:
            if p not in toutes_pieces:
                toutes_pieces.append(p)

    if toutes_pieces:
        lines += [
            sep,
            "  PIÈCES PRIORITAIRES À JOINDRE",
            sep2,
        ]
        for i, p in enumerate(toutes_pieces[:5], 1):
            lines.append(f"  {i}. {p}")
        lines.append("")

    # Orientations
    if explications_orientations:
        lines += [
            sep,
            "  ORIENTATIONS POTENTIELLES",
            sep2,
        ]
        for o in explications_orientations[:4]:
            lines += [
                f"  → {o.label} ({o.confiance})",
            ]
            if o.justifications:
                lines.append(f"    Justification : {o.justifications[0][:70]}")
        lines.append("")

    # Explication des scores
    lines += [
        sep,
        "  EXPLICATION DES SCORES",
        sep2,
        f"  Score global   : {explication_score.score_cdaph}/100",
    ]
    for critere, score_c in explication_score.detail.items():
        expl = explication_score.explication_par_critere.get(critere, "")
        poids = {"preuves": 35, "coherence": 25, "retentissement": 20, "projet": 15, "justificatifs": 5}
        p = poids.get(critere, 0)
        lines += [
            f"  {critere.capitalize():<16} : {score_c:>3}/100  {barre(score_c, 6)}  ({p}%)",
            f"    {expl[:80]}",
        ]
    lines += ["", sep]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def expliquer_dossier(
    donnees: dict[str, Any],
    profil_mdph: str = "adulte",
    profil_handicap: str = "",
) -> RapportExplicabilite:
    """
    Génère l'explication complète de toutes les décisions Facilim.

    Orchestre :
      1. Evidence engine (preuves traçables)
      2. CDAPH strategy engine (analyse stratégique)
      3. Stratégie dossier (droits oubliés, orientations)
      4. Questions levier engine

    Args:
        donnees:        synthese_json du dossier
        profil_mdph:    "adulte" | "enfant" | "protege" | "mixte"
        profil_handicap: optionnel

    Returns:
        RapportExplicabilite complet et auditable
    """
    # ── 1. Construire le graphe de preuves ────────────────────────────────────
    from app.engines.evidence_engine import construire_graphe_preuves
    graphe = construire_graphe_preuves(donnees, profil_mdph)

    # ── 2. Analyse stratégique CDAPH ─────────────────────────────────────────
    from app.engines.cdaph_strategy_engine import analyser_strategie_cdaph
    rapport_cdaph = analyser_strategie_cdaph(donnees, profil_mdph, profil_handicap)

    # ── 3. Stratégie dossier (orientations, questions) ────────────────────────
    from app.engines.strategie_dossier_engine import analyser_strategie
    strategie = analyser_strategie(donnees, profil_mdph, profil_handicap)

    # ── 4. Questions levier ───────────────────────────────────────────────────
    from app.engines.questions_levier_engine import identifier_questions_levier
    droits_cibles = strategie.droits_demandes + [d.droit for d in strategie.droits_omis[:3]]
    questions_levier = identifier_questions_levier(donnees, profil_mdph, droits_cibles)

    # ── 5. Construire les explications ────────────────────────────────────────
    explication_score = _construire_explication_score(rapport_cdaph)

    explications_solides = [
        _construire_explication_droit(d, graphe)
        for d in rapport_cdaph.droits_solides
    ]
    explications_fragiles = [
        _construire_explication_droit(d, graphe)
        for d in rapport_cdaph.droits_fragiles
    ]
    explications_orientations = _construire_explications_orientations(strategie, graphe)
    explications_questions = _construire_explications_questions(questions_levier)

    # ── 6. Rapport professionnel ──────────────────────────────────────────────
    rapport_pro = _generer_rapport_professionnel(
        rapport_cdaph=rapport_cdaph,
        strategie=strategie,
        explication_score=explication_score,
        explications_solides=explications_solides,
        explications_fragiles=explications_fragiles,
        explications_orientations=explications_orientations,
        explications_questions=explications_questions,
        graphe_preuves=graphe,
    )

    return RapportExplicabilite(
        profil_mdph=profil_mdph,
        nb_sources_actives=len(graphe.sources_presentes),
        sources_presentes=graphe.sources_presentes,
        sources_manquantes=graphe.sources_absentes,
        nb_preuves=graphe.nb_preuves_total,
        preuves_par_droit=graphe.nb_preuves_par_droit,
        explication_score=explication_score,
        explications_solides=explications_solides,
        explications_fragiles=explications_fragiles,
        explications_orientations=explications_orientations,
        explications_questions=explications_questions,
        rapport_professionnel=rapport_pro,
    )
