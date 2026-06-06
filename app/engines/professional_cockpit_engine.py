"""
app/engines/professional_cockpit_engine.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FACILIM 85 — Tableau de pilotage professionnel

Orchestrateur unique qui agrège tous les moteurs Facilim
et produit le tableau de bord du professionnel accompagnant.

7 blocs :
  1. Forces du dossier
  2. Faiblesses
  3. Droits solides (avec scores)
  4. Droits fragiles (avec explications)
  5. Questions prioritaires (classées par ROI)
  6. Pièces prioritaires
  7. Tableau de validation professionnelle

Usage :
  from app.engines.professional_cockpit_engine import generer_cockpit
  cockpit = generer_cockpit(donnees, profil_mdph="adulte")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("facilim.engines.professional_cockpit")


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LigneDroit:
    droit:              str
    label:              str
    score:              int
    barre_score:        str     # visualisation textuelle
    decision:           str
    explication:        str
    preuves:            list[str]
    risque:             str     # "FAIBLE" | "MOYEN" | "ÉLEVÉ"


@dataclass
class LigneQuestion:
    numero:             int
    question:           str
    impact_roi:         int     # 0-100
    droit_concerne:     str
    raison:             str


@dataclass
class LignePiece:
    numero:             int
    piece:              str
    droit_concerne:     str
    obligatoire:        bool
    justification:      str


@dataclass
class LigneValidation:
    element:            str
    label:              str
    confiance:          int
    statut:             str     # "a_valider" | "valide" | "refuse"
    decision_previsible: str
    checkbox:           str     # "☐" | "✅" | "❌"


@dataclass
class CockpitProfessionnel:
    """Tableau de bord complet pour le professionnel accompagnant."""

    profil_mdph:            str
    score_global:           int
    niveau:                 str     # "excellent" | "bon" | "moyen" | "fragile"

    # Blocs 1-2
    forces:                 list[str]
    faiblesses:             list[str]

    # Bloc 3 — Droits solides
    droits_solides:         list[LigneDroit]

    # Bloc 4 — Droits fragiles
    droits_fragiles:        list[LigneDroit]

    # Bloc 5 — Questions
    questions:              list[LigneQuestion]

    # Bloc 6 — Pièces
    pieces:                 list[LignePiece]

    # Bloc 7 — Validation
    lignes_validation:      list[LigneValidation]

    # Résumé exécutif
    resume:                 str

    # Statut de préparation
    pret_pour_cerfa:        bool
    nb_en_attente_validation: int

    # Sources
    sources_actives:        list[str]
    nb_preuves:             int

    def dashboard_text(self) -> str:
        """Génère le tableau de bord en texte formaté."""
        return _formater_cockpit(self)

    def to_dict(self) -> dict:
        return {
            "profil_mdph":   self.profil_mdph,
            "score_global":  self.score_global,
            "niveau":        self.niveau,
            "pret_cerfa":    self.pret_pour_cerfa,
            "nb_attente":    self.nb_en_attente_validation,
            "forces":        self.forces,
            "faiblesses":    self.faiblesses,
            "droits_solides": [
                {"droit": d.droit, "score": d.score, "decision": d.decision}
                for d in self.droits_solides
            ],
            "droits_fragiles": [
                {"droit": d.droit, "score": d.score, "risque": d.risque,
                 "explication": d.explication[:80]}
                for d in self.droits_fragiles
            ],
            "questions": [
                {"q": q.question[:80], "roi": q.impact_roi, "droit": q.droit_concerne}
                for q in self.questions
            ],
            "pieces": [
                {"piece": p.piece, "droit": p.droit_concerne, "obligatoire": p.obligatoire}
                for p in self.pieces
            ],
            "validation": [
                {"element": v.element, "confiance": v.confiance, "statut": v.statut}
                for v in self.lignes_validation
            ],
            "resume": self.resume,
        }


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _barre(score: int, largeur: int = 12) -> str:
    n = int(score / 100 * largeur)
    return "█" * n + "·" * (largeur - n)


def _score_barre_label(score: int, largeur: int = 10) -> str:
    n = int(score / 100 * largeur)
    points = "·" * (largeur - n - 3) if largeur - n >= 3 else ""
    return f"{_barre(score, n)} {points} {score:>3} %"


def _risque_label(score: int) -> str:
    if score >= 70: return "FAIBLE"
    if score >= 40: return "MOYEN"
    return "ÉLEVÉ"


# ─────────────────────────────────────────────────────────────────────────────
# CONSTRUCTION DES BLOCS
# ─────────────────────────────────────────────────────────────────────────────

def _construire_lignes_droits(analyses) -> tuple[list[LigneDroit], list[LigneDroit]]:
    """Construit les lignes de droits solides et fragiles."""
    solides, fragiles = [], []

    for d in analyses:
        risque = _risque_label(d.robustesse_pct)
        barre  = _barre(d.robustesse_pct, 10)
        preuves = d.forces[:3] if hasattr(d, "forces") else []

        explication = ""
        if hasattr(d, "faiblesses") and d.faiblesses:
            explication = d.faiblesses[0][:80]

        ligne = LigneDroit(
            droit=d.droit,
            label=d.label,
            score=d.robustesse_pct,
            barre_score=f"{barre} {d.robustesse_pct:>3}%",
            decision=d.decision_previsible,
            explication=explication or d.raisonnement_cdaph[:70],
            preuves=preuves,
            risque=risque,
        )

        if d.robustesse_pct >= 70:
            solides.append(ligne)
        else:
            fragiles.append(ligne)

    solides.sort(key=lambda l: -l.score)
    fragiles.sort(key=lambda l: l.score)
    return solides, fragiles


def _construire_lignes_questions(questions_levier) -> list[LigneQuestion]:
    """Construit les lignes de questions avec ROI."""
    lignes = []
    for i, q in enumerate(questions_levier[:5], 1):
        if isinstance(q, str):
            lignes.append(LigneQuestion(
                numero=i, question=q, impact_roi=25,
                droit_concerne="", raison="Amélioration robustesse",
            ))
        elif hasattr(q, "question"):
            droit = getattr(q, "droit_concerne", "")
            roi   = getattr(q, "impact_estime", 25)
            raison = getattr(q, "contexte_interne", "Amélioration robustesse du dossier")
            lignes.append(LigneQuestion(
                numero=i, question=q.question, impact_roi=roi,
                droit_concerne=droit, raison=raison[:80],
            ))
    return lignes


def _construire_lignes_pieces(donnees: dict, profil_mdph: str) -> list[LignePiece]:
    """Construit la liste des pièces prioritaires avec justification."""
    try:
        from app.engines.justificatifs_engine import justificatifs_requis
        justifs = justificatifs_requis(donnees, profil_mdph)
        lignes = []
        obligatoires = [j for j in justifs if j.obligatoire]
        facultatifs  = [j for j in justifs if not j.obligatoire]
        all_pieces = obligatoires + facultatifs[:4]

        for i, j in enumerate(all_pieces[:8], 1):
            lignes.append(LignePiece(
                numero=i,
                piece=j.nom,
                droit_concerne=j.categorie,
                obligatoire=j.obligatoire,
                justification=j.raison[:80],
            ))
        return lignes
    except Exception:
        return []


def _construire_lignes_validation(tableau_validation) -> list[LigneValidation]:
    """Construit les lignes du tableau de validation."""
    lignes = []
    for e in tableau_validation.elements_a_valider:
        checkbox = "✅" if e.est_valide else ("❌" if e.statut == "refuse" else "☐")
        lignes.append(LigneValidation(
            element=e.element,
            label=e.label,
            confiance=e.confiance,
            statut=e.statut,
            decision_previsible=e.decision_previsible,
            checkbox=checkbox,
        ))
    return lignes


# ─────────────────────────────────────────────────────────────────────────────
# FORMATEUR TEXTE
# ─────────────────────────────────────────────────────────────────────────────

def _formater_cockpit(c: CockpitProfessionnel) -> str:
    SEP  = "═" * 58
    SEP2 = "─" * 58

    lines = [
        SEP,
        f"  COCKPIT PROFESSIONNEL — FACILIM 85",
        f"  Profil : {c.profil_mdph.upper()}  |  Score : {c.score_global}/100 — {c.niveau.upper()}",
        f"  Sources actives : {' · '.join(c.sources_actives) or '(aucune)'}",
        f"  Preuves extraites : {c.nb_preuves}",
        SEP,
        "",
    ]

    # Bloc 1 — Forces
    lines += [f"  {'■ FORCES DU DOSSIER':<40}", SEP2]
    if c.forces:
        for f in c.forces[:5]:
            lines.append(f"  ✓ {f[:60]}")
    else:
        lines.append("  (Aucune force identifiée — enrichir les données)")
    lines.append("")

    # Bloc 2 — Faiblesses
    lines += [f"  {'■ FAIBLESSES':<40}", SEP2]
    if c.faiblesses:
        for f in c.faiblesses[:5]:
            lines.append(f"  ⚠ {f[:60]}")
    else:
        lines.append("  (Aucune faiblesse majeure)")
    lines.append("")

    # Bloc 3 — Droits solides
    lines += [f"  {'■ DROITS SOLIDES':<40}", SEP2]
    if c.droits_solides:
        for d in c.droits_solides:
            lines.append(f"  {d.label[:35]:<35} {d.barre_score}")
            if d.preuves:
                lines.append(f"    ↳ {d.preuves[0][:65]}")
    else:
        lines.append("  (Aucun droit à profil solide actuellement)")
    lines.append("")

    # Bloc 4 — Droits fragiles
    lines += [f"  {'■ DROITS FRAGILES':<40}", SEP2]
    if c.droits_fragiles:
        for d in c.droits_fragiles:
            lines.append(f"  {d.label[:35]:<35} {d.barre_score}  [{d.risque}]")
            if d.explication:
                lines.append(f"    ↳ {d.explication[:65]}")
    else:
        lines.append("  (Tous les droits analysés semblent solides)")
    lines.append("")

    # Bloc 5 — Questions
    lines += [f"  {'■ QUESTIONS À FORT LEVIER':<40}", SEP2]
    if c.questions:
        for q in c.questions:
            roi_barre = "▶" * min(5, q.impact_roi // 10)
            lines += [
                f"  {q.numero}. {q.question[:65]}",
                f"     ROI estimé : +{q.impact_roi}  {roi_barre}"
                + (f"  [{q.droit_concerne}]" if q.droit_concerne else ""),
            ]
            lines.append("")
    else:
        lines.append("  (Informations critiques toutes présentes)")
    lines.append("")

    # Bloc 6 — Pièces
    lines += [f"  {'■ PIÈCES PRIORITAIRES':<40}", SEP2]
    if c.pieces:
        for p in c.pieces:
            tag = "OBLIGATOIRE" if p.obligatoire else "recommandée"
            lines += [
                f"  {p.numero}. {p.piece[:55]}",
                f"     [{tag}] {p.justification[:55]}",
            ]
    else:
        lines.append("  (Liste de justificatifs non générée)")
    lines.append("")

    # Bloc 7 — Validation
    lines += [
        f"  {'■ TABLEAU DE VALIDATION PROFESSIONNELLE':<40}",
        SEP2,
        f"  {'Élément':<28} {'Conf.':>5}  {'Décision':<12} {'Validation'}",
        f"  {'-'*28} {'-----':>5}  {'-'*12} {'-'*10}",
    ]
    for v in c.lignes_validation:
        lines.append(
            f"  {v.label[:28]:<28} {v.confiance:>4}%  "
            f"{v.decision_previsible[:12]:<12} {v.checkbox}"
        )

    if c.pret_pour_cerfa:
        lines += ["", f"  ✅ PRÊT — Tous les éléments stratégiques ont été traités", ""]
    else:
        lines += [
            "",
            f"  ⚠️  EN ATTENTE — {c.nb_en_attente_validation} élément(s) à valider",
            f"     Valider chaque droit avant génération du CERFA final.",
            "",
        ]

    lines.append(SEP)
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────────────────────

def generer_cockpit(
    donnees: dict[str, Any],
    profil_mdph: str = "adulte",
    profil_handicap: str = "",
) -> CockpitProfessionnel:
    """
    Génère le tableau de pilotage professionnel complet.

    Orchestre tous les moteurs Facilim sans en modifier aucun.

    Args:
        donnees:        synthese_json du dossier
        profil_mdph:    "adulte" | "enfant" | "protege" | "mixte"
        profil_handicap: optionnel

    Returns:
        CockpitProfessionnel avec les 7 blocs et le tableau de validation
    """
    # ── 1. Moteurs existants ──────────────────────────────────────────────────
    from app.engines.cdaph_strategy_engine import analyser_strategie_cdaph
    from app.engines.evidence_engine import construire_graphe_preuves
    from app.engines.questions_levier_engine import identifier_questions_levier
    from app.engines.human_validation_engine import creer_tableau_validation

    rapport_cdaph   = analyser_strategie_cdaph(donnees, profil_mdph, profil_handicap)
    graphe          = construire_graphe_preuves(donnees, profil_mdph)
    tableau_valid   = creer_tableau_validation(donnees, profil_mdph, profil_handicap)

    droits_cibles = [d.droit for d in rapport_cdaph.droits_solides + rapport_cdaph.droits_fragiles]
    questions     = identifier_questions_levier(donnees, profil_mdph, droits_cibles)

    # ── 2. Construction des blocs ─────────────────────────────────────────────
    all_analyses = rapport_cdaph.droits_solides + rapport_cdaph.droits_fragiles
    droits_solides_l, droits_fragiles_l = _construire_lignes_droits(all_analyses)

    lignes_questions  = _construire_lignes_questions(questions)
    lignes_pieces     = _construire_lignes_pieces(donnees, profil_mdph)
    lignes_validation = _construire_lignes_validation(tableau_valid)

    # ── 3. Score et niveau ────────────────────────────────────────────────────
    score  = rapport_cdaph.score_solidite
    niveau = (
        "excellent" if score >= 80 else
        "bon"       if score >= 65 else
        "moyen"     if score >= 45 else
        "fragile"
    )

    # ── 4. Résumé ─────────────────────────────────────────────────────────────
    nb_solides  = len(droits_solides_l)
    nb_fragiles = len(droits_fragiles_l)
    nb_attente  = tableau_valid.nb_en_attente

    resume = (
        f"Score {score}/100 ({niveau}). "
        f"{nb_solides} droit(s) solide(s)"
        + (f", {nb_fragiles} droit(s) fragile(s)" if nb_fragiles else "")
        + f". {nb_attente} élément(s) en attente de validation."
    )

    return CockpitProfessionnel(
        profil_mdph=profil_mdph,
        score_global=score,
        niveau=niveau,
        forces=rapport_cdaph.forces_globales[:6],
        faiblesses=rapport_cdaph.faiblesses_globales[:5],
        droits_solides=droits_solides_l,
        droits_fragiles=droits_fragiles_l,
        questions=lignes_questions,
        pieces=lignes_pieces,
        lignes_validation=lignes_validation,
        resume=resume,
        pret_pour_cerfa=tableau_valid.pret_pour_cerfa,
        nb_en_attente_validation=nb_attente,
        sources_actives=graphe.sources_presentes,
        nb_preuves=graphe.nb_preuves_total,
    )
