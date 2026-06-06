"""
app/engines/parcours_engine.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FACILIM 100 — Moteur de parcours (feuille de route)

Construit une feuille de route temporelle depuis le plan d'action.
Organise les actions en semaines selon :
  - Urgence (délai immédiat)
  - Impact (priorité métier)
  - Effort (faisabilité)

Produit 3 versions :
  - Professionnel (technique)
  - Usager (FALC)
  - ESSMS (structure)

Usage :
  from app.engines.parcours_engine import construire_parcours
  parcours = construire_parcours(tableau_priorisation)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.engines.priorisation_engine import Action, TableauPriorisation

logger = logging.getLogger("facilim.engines.parcours")


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EtapeParcours:
    semaine:        int         # 1, 2, 3, 4
    label_semaine:  str         # "Semaine 1 — Documents urgents"
    actions:        list[Action]
    objectif:       str         # objectif de la semaine
    nb_jours_max:   int         # délai maximum de la semaine


@dataclass
class PlanParcours:
    """Feuille de route temporelle complète."""
    etapes:             list[EtapeParcours]
    duree_totale_jours: int
    nb_actions_total:   int
    date_depot_estimee: str     # "Semaine 4" ou durée estimée

    # Versions textuelles
    parcours_professionnel: str
    parcours_usager:        str     # FALC
    parcours_essms:         str

    def to_dict(self) -> dict:
        return {
            "etapes": [
                {
                    "semaine":      e.semaine,
                    "label":        e.label_semaine,
                    "objectif":     e.objectif,
                    "nb_actions":   len(e.actions),
                    "actions":      [a.titre for a in e.actions],
                }
                for e in self.etapes
            ],
            "duree_jours":  self.duree_totale_jours,
            "nb_actions":   self.nb_actions_total,
            "depot_estime": self.date_depot_estimee,
        }


# ─────────────────────────────────────────────────────────────────────────────
# ORGANISATION DES SEMAINES
# ─────────────────────────────────────────────────────────────────────────────

_SEMAINES_CONFIG = [
    {
        "semaine": 1,
        "label":   "Semaine 1 — Documents prioritaires",
        "objectif":"Réunir toutes les pièces disponibles immédiatement",
        "critere": lambda a: a.delai_jours <= 7 and a.categorie in ("document", "administratif"),
        "jours":   7,
    },
    {
        "semaine": 2,
        "label":   "Semaine 2 — Enrichissement du contenu",
        "objectif":"Compléter les descriptions fonctionnelles et recueillir les informations manquantes",
        "critere": lambda a: a.categorie in ("narratif",) or (a.categorie == "rendez-vous" and a.delai_jours <= 14),
        "jours":   7,
    },
    {
        "semaine": 3,
        "label":   "Semaine 3 — Rendez-vous et compléments",
        "objectif":"Obtenir les pièces nécessitant un rendez-vous ou un délai",
        "critere": lambda a: a.categorie == "rendez-vous" and a.delai_jours > 7,
        "jours":   14,
    },
    {
        "semaine": 4,
        "label":   "Semaine 4 — Validation et dépôt",
        "objectif":"Valider le dossier avec le professionnel et déposer à la MDPH",
        "critere": lambda a: False,  # Semaine de clôture — toujours présente
        "jours":   7,
    },
]


def _repartir_actions(actions_triees: list[Action]) -> dict[int, list[Action]]:
    """Répartit les actions sur les semaines selon leur catégorie et délai."""
    semaines: dict[int, list[Action]] = {1: [], 2: [], 3: [], 4: []}
    attribuees: set[str] = set()

    for config in _SEMAINES_CONFIG[:3]:  # S1, S2, S3
        for action in actions_triees:
            if action.id in attribuees:
                continue
            if config["critere"](action):
                semaines[config["semaine"]].append(action)
                attribuees.add(action.id)

    # Actions non encore attribuées → S2 par défaut
    for action in actions_triees:
        if action.id not in attribuees:
            semaines[2].append(action)
            attribuees.add(action.id)

    return semaines


# ─────────────────────────────────────────────────────────────────────────────
# FORMATEURS TEXTE
# ─────────────────────────────────────────────────────────────────────────────

def _formater_professionnel(etapes: list[EtapeParcours], nb_total: int, depot: str) -> str:
    lines = [
        "═" * 54,
        "  FEUILLE DE ROUTE — PRÉPARATION DOSSIER MDPH",
        f"  {nb_total} action(s) — Dépôt estimé : {depot}",
        "═" * 54,
        "",
    ]
    for etape in etapes:
        lines += [
            f"  {etape.label_semaine.upper()}",
            f"  Objectif : {etape.objectif}",
            "  " + "─" * 50,
        ]
        if etape.actions:
            for i, a in enumerate(etape.actions, 1):
                impact_tag = "★" * min(3, a.impact // 15)
                lines += [
                    f"  {i}. {a.titre}",
                    f"     Impact : {a.impact}/100 {impact_tag}  | Effort : {'●' * a.effort}{'○' * (3 - a.effort)}  | ROI : {a.roi:.0f}",
                    f"     {a.justification[:75]}",
                ]
        else:
            if etape.semaine == 4:
                lines += ["  → Validation finale et dépôt MDPH"]
        lines.append("")
    lines += ["═" * 54, f"  Dépôt estimé : {depot}", "═" * 54]
    return "\n".join(lines)


def _formater_usager(etapes: list[EtapeParcours], nb_total: int) -> str:
    """Version FALC — phrases courtes, simples, numérotées."""
    lines = [
        "VOTRE PLAN D'ACTION",
        "=" * 40,
        "",
        "Voici ce que vous devez faire pour préparer votre dossier.",
        "Prenez une étape à la fois.",
        "",
    ]
    num = 1
    for etape in etapes:
        if not etape.actions and etape.semaine == 4:
            lines += [
                f"Étape {num} — {etape.label_semaine}",
                "",
                f"  {num}. Montrez votre dossier à votre accompagnant(e).",
                f"  {num+1}. Déposez votre dossier à la MDPH.",
                "",
            ]
            num += 2
            continue
        if etape.actions:
            lines += [f"Étape — {etape.label_semaine}", ""]
            for action in etape.actions:
                lines.append(f"  {num}. {action.description_usager}")
                num += 1
            lines.append("")
    lines += [
        "=" * 40,
        "Votre accompagnant(e) peut vous aider à chaque étape.",
    ]
    return "\n".join(lines)


def _formater_essms(etapes: list[EtapeParcours], nb_total: int) -> str:
    lines = [
        "PROTOCOLE PRÉPARATION DOSSIER MDPH — ESSMS",
        "=" * 50,
        "",
    ]
    for etape in etapes:
        lines += [f"[{etape.label_semaine}]", f"Objectif : {etape.objectif}", ""]
        if etape.actions:
            for a in etape.actions:
                lines.append(f"  ▸ {a.description_essms}")
        elif etape.semaine == 4:
            lines += [
                "  ▸ Présenter le dossier complet à la personne accompagnée",
                "  ▸ Vérifier la liste des pièces jointes",
                "  ▸ Effectuer le dépôt MDPH (physique, postal ou plateforme)",
            ]
        lines.append("")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────────────────────

def construire_parcours(tableau: TableauPriorisation) -> PlanParcours:
    """
    Construit la feuille de route temporelle depuis le plan d'action priorisé.

    Args:
        tableau: TableauPriorisation depuis action_plan_engine

    Returns:
        PlanParcours avec les 3 versions (professionnel, usager, ESSMS)
    """
    semaines_actions = _repartir_actions(tableau.actions_triees)

    etapes: list[EtapeParcours] = []
    for config in _SEMAINES_CONFIG:
        s = config["semaine"]
        etapes.append(EtapeParcours(
            semaine=s,
            label_semaine=config["label"],
            actions=semaines_actions.get(s, []),
            objectif=config["objectif"],
            nb_jours_max=config["jours"],
        ))

    nb_total = sum(len(e.actions) for e in etapes)
    duree_totale = sum(e.nb_jours_max for e in etapes if e.actions or e.semaine == 4)

    # Durée estimée
    if nb_total <= 3:
        depot = "2 à 3 semaines"
    elif nb_total <= 6:
        depot = "3 à 4 semaines"
    else:
        depot = "4 à 6 semaines"

    return PlanParcours(
        etapes=etapes,
        duree_totale_jours=duree_totale,
        nb_actions_total=nb_total,
        date_depot_estimee=depot,
        parcours_professionnel=_formater_professionnel(etapes, nb_total, depot),
        parcours_usager=_formater_usager(etapes, nb_total),
        parcours_essms=_formater_essms(etapes, nb_total),
    )
