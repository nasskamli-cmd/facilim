"""
app/engines/pre_submission_engine.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FACILIM 90 — Moteur de pré-validation avant dépôt

Avant génération du CERFA final, produit une décision :
  GO           — dossier prêt
  GO_RISQUES   — prêt mais avec points de vigilance
  NO_GO        — dossier incomplet ou incohérent

Synthèse des moteurs completeness + refusal_risk + cdaph_strategy.

Usage :
  from app.engines.pre_submission_engine import pre_valider_dossier
  decision = pre_valider_dossier(donnees, profil_mdph="adulte")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("facilim.engines.pre_submission")

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────────────────────

GO        = "GO"
GO_RISQUES = "GO_AVEC_RISQUES"
NO_GO     = "NO_GO"


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DecisionPreSoumission:
    decision:               str         # GO | GO_AVEC_RISQUES | NO_GO
    score_completude:       int
    score_solidite:         int         # depuis cdaph_strategy
    risque_global:          str
    nb_incoherences:        int
    nb_risques_eleves:      int
    nb_elements_bloquants:  int

    # Explications
    raison_decision:        str
    blocages:               list[str]   # raisons d'un NO_GO
    risques_identifies:     list[str]   # raisons d'un GO_AVEC_RISQUES
    points_forts:           list[str]

    # Actions avant dépôt
    actions_avant_depot:    list[str]
    actions_optionnelles:   list[str]

    # Tableau final
    tableau_completude:     dict        # depuis completeness_engine
    risques_par_droit:      list[dict]  # depuis refusal_risk_engine
    incoherences:           list[dict]

    def emoji(self) -> str:
        return {"GO": "✅", "GO_AVEC_RISQUES": "⚠️", "NO_GO": "❌"}.get(self.decision, "?")

    def to_dict(self) -> dict:
        return {
            "decision":             self.decision,
            "raison":               self.raison_decision,
            "score_completude":     self.score_completude,
            "score_solidite":       self.score_solidite,
            "risque_global":        self.risque_global,
            "blocages":             self.blocages,
            "risques":              self.risques_identifies,
            "points_forts":         self.points_forts,
            "actions_avant_depot":  self.actions_avant_depot,
            "incoherences":         self.incoherences,
        }

    def rapport_text(self) -> str:
        """Génère le tableau de pré-validation formaté."""
        sep = "═" * 56
        sep2 = "─" * 56
        icon = self.emoji()

        lines = [
            sep,
            f"  PRÉ-VALIDATION AVANT DÉPÔT — FACILIM 90",
            sep,
            f"  DÉCISION : {icon} {self.decision.replace('_', ' ')}",
            f"  {self.raison_decision[:65]}",
            sep2,
            "",
            f"  NIVEAU DE COMPLÉTUDE : {self.score_completude}/100",
        ]

        # Scores par dimension
        for nom, dim in self.tableau_completude.get("dimensions", {}).items():
            score = dim.get("score", 0)
            n = int(score / 100 * 8)
            barre = "█" * n + "░" * (8 - n)
            lines.append(f"  {nom.capitalize():<16} : {barre} {score:>3}%")

        lines += [""]

        # Risques par droit
        if self.risques_par_droit:
            lines += [f"  RISQUES DE REFUS PAR DROIT", sep2]
            for r in self.risques_par_droit:
                risque = r.get("risque", "?")
                icon_r = "🟢" if risque == "faible" else ("🟡" if risque == "moyen" else "🔴")
                lines.append(
                    f"  {icon_r} {r.get('droit','?'):<22} [{risque.upper()}]  {r.get('justification','')[:35]}"
                )
            lines.append("")

        # Incohérences
        if self.incoherences:
            lines += [f"  ⚠️  INCOHÉRENCES DÉTECTÉES ({len(self.incoherences)})", sep2]
            for inc in self.incoherences:
                gravite = inc.get("gravite", "?")
                lines += [
                    f"  [{gravite.upper()}] {inc.get('droit','?')} — {inc.get('description','')[:60]}",
                    f"    → {inc.get('resolution','')[:60]}",
                ]
            lines.append("")

        # Blocages (NO_GO)
        if self.blocages:
            lines += [f"  ❌ POINTS BLOQUANTS", sep2]
            for b in self.blocages:
                lines.append(f"  • {b[:70]}")
            lines.append("")

        # Actions avant dépôt
        if self.actions_avant_depot:
            lines += [f"  📋 ACTIONS AVANT DÉPÔT", sep2]
            for i, a in enumerate(self.actions_avant_depot[:5], 1):
                lines.append(f"  {i}. {a[:65]}")
            lines.append("")

        # Points forts
        if self.points_forts:
            lines += [f"  ✅ POINTS FORTS", sep2]
            for p in self.points_forts[:3]:
                lines.append(f"  • {p[:65]}")
            lines.append("")

        lines += [sep, f"  {icon} DÉCISION FINALE : {self.decision.replace('_', ' ')}", sep]
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# LOGIQUE DE DÉCISION
# ─────────────────────────────────────────────────────────────────────────────

def _calculer_decision(
    score_completude: int,
    score_solidite: int,
    risque_global: str,
    nb_incoherences_critiques: int,
    nb_bloquants: int,
    nb_risques_eleves: int,
) -> tuple[str, str]:
    """Retourne (décision, raison)."""

    # NO_GO — situations bloquantes
    if nb_incoherences_critiques > 0:
        return NO_GO, f"Incohérence(s) critique(s) détectée(s) — corriger avant dépôt"

    if nb_bloquants >= 2:
        return NO_GO, f"{nb_bloquants} éléments bloquants — dossier non recevable en l'état"

    if score_completude < 30:
        return NO_GO, f"Complétude critique ({score_completude}%) — dossier trop incomplet"

    if score_completude < 15:
        return NO_GO, "Données insuffisantes — compléter avant tout dépôt"

    # GO — dossier solide
    if (score_completude >= 65 and score_solidite >= 60
            and risque_global == "faible"
            and nb_incoherences_critiques == 0
            and nb_bloquants == 0):
        return GO, f"Dossier complet ({score_completude}%) et solide ({score_solidite}%) — prêt pour dépôt"

    # GO_AVEC_RISQUES — dossier acceptable mais perfectible
    return GO_RISQUES, (
        f"Dossier acceptable ({score_completude}% complétude, "
        f"{score_solidite}% solidité) avec "
        + (f"{nb_risques_eleves} droit(s) à risque élevé" if nb_risques_eleves > 0
           else "des points à renforcer")
    )


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────────────────────

def pre_valider_dossier(
    donnees: dict[str, Any],
    profil_mdph: str = "adulte",
    profil_handicap: str = "",
) -> DecisionPreSoumission:
    """
    Analyse pré-soumission complète. Retourne GO / GO_AVEC_RISQUES / NO_GO.

    Agrège completeness_engine + refusal_risk_engine + cdaph_strategy_engine.

    Returns:
        DecisionPreSoumission avec décision, raisons et actions
    """
    # ── 1. Complétude ──────────────────────────────────────────────────────────
    from app.engines.completeness_engine import evaluer_completude
    rapport_completude = evaluer_completude(donnees, profil_mdph)

    # ── 2. Risques de refus + Incohérences ────────────────────────────────────
    from app.engines.refusal_risk_engine import evaluer_risques_refus
    rapport_risques = evaluer_risques_refus(donnees, profil_mdph)

    # ── 3. Solidité CDAPH ─────────────────────────────────────────────────────
    score_solidite = 0
    points_forts_cdaph: list[str] = []
    try:
        from app.engines.cdaph_strategy_engine import analyser_strategie_cdaph
        rapport_cdaph = analyser_strategie_cdaph(donnees, profil_mdph, profil_handicap)
        score_solidite = rapport_cdaph.score_solidite
        points_forts_cdaph = rapport_cdaph.forces_globales[:3]
    except Exception:
        pass

    # ── 4. Calcul de la décision ──────────────────────────────────────────────
    nb_crit = sum(1 for i in rapport_risques.incoherences if i.gravite == "critique")
    nb_bloquants = len(rapport_completude.elements_bloquants)

    decision, raison = _calculer_decision(
        score_completude=rapport_completude.score_global,
        score_solidite=score_solidite,
        risque_global=rapport_risques.risque_global,
        nb_incoherences_critiques=nb_crit,
        nb_bloquants=nb_bloquants,
        nb_risques_eleves=rapport_risques.nb_risques_eleves,
    )

    # ── 5. Actions avant dépôt ────────────────────────────────────────────────
    actions_obligatoires: list[str] = []
    actions_optionnelles: list[str] = []

    # Incohérences → actions bloquantes
    for inc in rapport_risques.incoherences:
        if inc.gravite == "critique":
            actions_obligatoires.append(f"🔴 CRITIQUE — {inc.resolution[:65]}")
        elif inc.gravite == "importante":
            actions_obligatoires.append(f"🟡 IMPORTANT — {inc.resolution[:65]}")

    # Pièces manquantes des droits à risque élevé
    for r in rapport_risques.risques_par_droit:
        if r.niveau_risque == "élevé" and r.pieces_manquantes:
            actions_obligatoires.append(
                f"Pièce {r.droit} : {r.pieces_manquantes[0]}"
            )

    # Éléments bloquants complétude
    for b in rapport_completude.elements_bloquants:
        if b not in actions_obligatoires:
            actions_obligatoires.append(b)

    # Actions optionnelles : pièces manquantes des risques moyens
    for r in rapport_risques.risques_par_droit:
        if r.niveau_risque == "moyen" and r.pieces_manquantes:
            actions_optionnelles.append(
                f"Renforcer {r.droit} : {r.pieces_manquantes[0]}"
            )

    # Recommandations complétude
    for rec in rapport_completude.recommandations:
        if rec not in actions_obligatoires:
            actions_optionnelles.append(rec)

    # ── 6. Risques identifiés ─────────────────────────────────────────────────
    risques_identifies: list[str] = []
    for r in rapport_risques.risques_par_droit:
        if r.niveau_risque == "élevé":
            risques_identifies.append(f"{r.droit} : {r.justification[:60]}")
        elif r.niveau_risque == "moyen" and len(risques_identifies) < 3:
            risques_identifies.append(f"{r.droit} : {r.justification[:60]}")

    return DecisionPreSoumission(
        decision=decision,
        score_completude=rapport_completude.score_global,
        score_solidite=score_solidite,
        risque_global=rapport_risques.risque_global,
        nb_incoherences=rapport_risques.nb_incoherences,
        nb_risques_eleves=rapport_risques.nb_risques_eleves,
        nb_elements_bloquants=nb_bloquants,
        raison_decision=raison,
        blocages=rapport_completude.elements_bloquants + [
            i.description[:60] for i in rapport_risques.incoherences if i.gravite == "critique"
        ],
        risques_identifies=risques_identifies[:5],
        points_forts=points_forts_cdaph + rapport_completude.dimensions["fonctionnel"].elements_presents[:2],
        actions_avant_depot=actions_obligatoires[:6],
        actions_optionnelles=actions_optionnelles[:4],
        tableau_completude=rapport_completude.to_dict(),
        risques_par_droit=[r.to_dict() for r in rapport_risques.risques_par_droit],
        incoherences=[i.to_dict() for i in rapport_risques.incoherences],
    )
