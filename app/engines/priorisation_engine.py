"""
app/engines/priorisation_engine.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FACILIM 100 — Moteur de priorisation des actions

Classe toutes les actions par ROI = impact / effort.
Garantit que les actions les plus rentables (impact élevé / effort faible)
sont présentées en premier.

Usage :
  from app.engines.priorisation_engine import prioriser_actions
  actions_triees = prioriser_actions(actions_brutes)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("facilim.engines.priorisation")


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Action:
    """Une action concrète avec impact, effort et ROI."""
    id:                 str
    titre:              str         # Titre court (< 60 chars)
    description:        str         # Détaillée pour professionnel
    description_usager: str         # Version FALC
    description_essms:  str         # Version structure médico-sociale
    droit_concerne:     str
    dimension_cerfa:    str         # "B" | "C" | "D" | "E" | "Administratif" | "Médical"
    impact:             int         # 0-100 (gain estimé sur solidité du dossier)
    effort:             int         # 1=très facile / 2=moyen / 3=difficile
    roi:                float       # impact / effort — calculé automatiquement
    delai_jours:        int         # délai estimé pour compléter l'action
    priorite:           str         # "haute" | "moyenne" | "basse"
    categorie:          str         # "document" | "narratif" | "rendez-vous" | "administratif"
    deja_realisee:      bool        # True si la donnée est déjà présente
    source_constat:     str         # Moteur source du constat
    justification:      str         # Pourquoi cette action améliore le dossier

    def to_dict(self) -> dict:
        return {
            "id":                 self.id,
            "titre":              self.titre,
            "description":        self.description,
            "description_usager": self.description_usager,
            "droit_concerne":     self.droit_concerne,
            "dimension":          self.dimension_cerfa,
            "impact":             self.impact,
            "effort":             self.effort,
            "roi":                round(self.roi, 1),
            "delai_jours":        self.delai_jours,
            "priorite":           self.priorite,
            "categorie":          self.categorie,
            "deja_realisee":      self.deja_realisee,
            "justification":      self.justification,
        }


@dataclass
class TableauPriorisation:
    """Tableau de priorisation des actions classées par ROI."""
    actions_triees:     list[Action]    # triées par ROI décroissant
    actions_urgentes:   list[Action]    # ROI > 20 et délai ≤ 7 jours
    actions_hautes:     list[Action]    # ROI > 15
    actions_moyennes:   list[Action]    # ROI 8-15
    actions_basses:     list[Action]    # ROI < 8
    nb_deja_realisees:  int
    roi_max:            float
    roi_moy:            float

    def to_dict(self) -> dict:
        return {
            "total":        len(self.actions_triees),
            "urgentes":     [a.to_dict() for a in self.actions_urgentes],
            "hautes":       [a.to_dict() for a in self.actions_hautes],
            "moyennes":     [a.to_dict() for a in self.actions_moyennes],
            "basses":       [a.to_dict() for a in self.actions_basses],
            "deja_realisees": self.nb_deja_realisees,
            "roi_max":      round(self.roi_max, 1),
            "roi_moy":      round(self.roi_moy, 1),
        }

    def top_n(self, n: int = 5) -> list[Action]:
        return self.actions_triees[:n]


# ─────────────────────────────────────────────────────────────────────────────
# CALCUL DU ROI ET CLASSIFICATION
# ─────────────────────────────────────────────────────────────────────────────

def _calculer_roi(action: Action) -> float:
    """ROI = impact / effort. Effort 0 → ROI = impact (par convention)."""
    if action.effort <= 0:
        return float(action.impact)
    return action.impact / action.effort


def _determiner_priorite(roi: float, impact: int) -> str:
    if roi >= 20 or impact >= 35:
        return "haute"
    if roi >= 10 or impact >= 20:
        return "moyenne"
    return "basse"


def prioriser_actions(actions: list[Action]) -> TableauPriorisation:
    """
    Trie et classe toutes les actions par ROI.

    Filtre les actions déjà réalisées de la liste principale.
    Les conserve dans nb_deja_realisees pour traçabilité.

    Returns:
        TableauPriorisation avec actions classées
    """
    # Calculer ROI pour toutes les actions
    for action in actions:
        action.roi = _calculer_roi(action)
        action.priorite = _determiner_priorite(action.roi, action.impact)

    # Séparer réalisées / non réalisées
    nb_deja = sum(1 for a in actions if a.deja_realisee)
    actives = [a for a in actions if not a.deja_realisee]

    # Trier par ROI décroissant, puis impact décroissant
    actives.sort(key=lambda a: (-a.roi, -a.impact))

    # Classifier
    urgentes = [a for a in actives if a.roi > 20 and a.delai_jours <= 7]
    hautes   = [a for a in actives if a.priorite == "haute" and a not in urgentes]
    moyennes = [a for a in actives if a.priorite == "moyenne"]
    basses   = [a for a in actives if a.priorite == "basse"]

    rois = [a.roi for a in actives] or [0]

    return TableauPriorisation(
        actions_triees=actives,
        actions_urgentes=urgentes,
        actions_hautes=hautes,
        actions_moyennes=moyennes,
        actions_basses=basses,
        nb_deja_realisees=nb_deja,
        roi_max=max(rois),
        roi_moy=round(sum(rois) / len(rois), 1),
    )
