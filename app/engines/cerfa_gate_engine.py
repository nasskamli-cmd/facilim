"""
app/engines/cerfa_gate_engine.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FACILIM PROD — Verrou de sécurité avant génération CERFA

Bloque la génération du CERFA final si :
  1. Validation humaine incomplète (éléments ≥ 60% non traités)
  2. Incohérence critique non résolue
  3. Score de complétude < seuil (défaut : 35%)
  4. Pièces obligatoires manquantes
  5. Identité incomplète (recevabilité compromise)

Affiche "Pourquoi le dépôt est bloqué" avec message lisible.

Usage :
  from app.engines.cerfa_gate_engine import verifier_gate_cerfa
  gate = verifier_gate_cerfa(donnees, tableau_validation, decision_presoumission)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("facilim.engines.cerfa_gate")

# ─────────────────────────────────────────────────────────────────────────────
# SEUILS
# ─────────────────────────────────────────────────────────────────────────────

SEUIL_COMPLETUDE_MINIMUM    = 30    # % — en dessous : NO_GO absolu
SEUIL_COMPLETUDE_RECOMMANDE = 50    # % — en dessous : WARN
SEUIL_VALIDATION_CONFIANCE  = 60    # % — éléments ≥ ce seuil doivent être validés


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BlocageGate:
    code:           str     # identifiant unique du blocage
    categorie:      str     # "CRITIQUE" | "IMPORTANT" | "AVERTISSEMENT"
    message:        str     # message lisible pour le professionnel
    resolution:     str     # comment lever ce blocage
    bloquant:       bool    # True → génération impossible


@dataclass
class ResultatGate:
    # ── DISTINCTION CRITIQUE ──────────────────────────────────────────────────
    # La PRÉVISUALISATION est TOUJOURS disponible — pour consultation, lecture.
    # Seul l'EXPORT FINAL (PDF définitif, transmission) peut être bloqué.
    autorise_previsualisation: bool = True    # TOUJOURS True
    autorise_export:    bool        = False   # Conditionnel — blocage export uniquement

    # Rétrocompatibilité
    @property
    def autorisation(self) -> bool:
        """Alias : autorisation = autorise_export (pour rétrocompatibilité)."""
        return self.autorise_export

    code_decision:      str         = ""      # "AUTORISE" | "BLOQUE_EXPORT" | "AUTORISE_AVEC_AVERTISSEMENTS"
    blocages:           list[BlocageGate] = None
    avertissements:     list[BlocageGate] = None
    message_global:     str         = ""
    nb_blocages_critriques: int     = 0
    nb_avertissements:  int         = 0

    def __post_init__(self):
        if self.blocages is None:
            self.blocages = []
        if self.avertissements is None:
            self.avertissements = []

    def to_dict(self) -> dict:
        return {
            "autorise_previsualisation": True,   # Toujours
            "autorise_export":   self.autorise_export,
            "decision":          self.code_decision,
            "blocages":      [{"code": b.code, "message": b.message, "resolution": b.resolution}
                              for b in self.blocages],
            "avertissements":[{"code": b.code, "message": b.message}
                              for b in self.avertissements],
            "message":       self.message_global,
        }

    def rapport_gate(self) -> str:
        sep = "═" * 58
        icon = "✅" if self.autorise_export else "❌"
        lines = [
            sep,
            f"  VÉRIFICATION EXPORT CERFA — FACILIM PROD",
            f"  Prévisualisation : ✅ TOUJOURS DISPONIBLE",
            f"  Export final     : {icon} {self.code_decision.replace('_', ' ')}",
            sep,
            "",
        ]
        if self.blocages:
            lines += [f"  ❌ BLOCAGES ({len(self.blocages)})", "─" * 58]
            for b in self.blocages:
                lines += [
                    f"  [{b.code}] {b.message}",
                    f"    → Résolution : {b.resolution}",
                    "",
                ]
        if self.avertissements:
            lines += [f"  ⚠️  AVERTISSEMENTS ({len(self.avertissements)})", "─" * 58]
            for a in self.avertissements:
                lines += [f"  [{a.code}] {a.message}", ""]

        lines += [
            "─" * 58,
            f"  {self.message_global}",
            sep,
        ]
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# VÉRIFICATIONS
# ─────────────────────────────────────────────────────────────────────────────

def _verif_validation_humaine(tableau_validation) -> list[BlocageGate]:
    """Vérifie que les éléments stratégiques ≥ 60% sont tous traités."""
    blocages = []
    if tableau_validation is None:
        return blocages

    en_attente_hauts = [
        e for e in tableau_validation.elements_a_valider
        if e.statut == "a_valider" and e.confiance >= SEUIL_VALIDATION_CONFIANCE
    ]

    if en_attente_hauts:
        noms = ", ".join(e.element for e in en_attente_hauts[:3])
        blocages.append(BlocageGate(
            code="VALIDATION_INCOMPLETE",
            categorie="CRITIQUE",
            message=f"{len(en_attente_hauts)} droit(s) stratégique(s) non validé(s) : {noms}",
            resolution="Dans le cockpit, valider ou refuser chaque droit avant génération.",
            bloquant=True,
        ))

    return blocages


def _verif_incoherences(decision_presoumission) -> list[BlocageGate]:
    """Vérifie l'absence d'incohérences critiques."""
    blocages = []
    if decision_presoumission is None:
        return blocages

    critiques = [
        i for i in decision_presoumission.incoherences
        if i.get("gravite") == "critique"
    ]
    if critiques:
        for inc in critiques[:3]:
            blocages.append(BlocageGate(
                code=f"INCOHERENCE_{inc.get('droit', 'INCONNU')}",
                categorie="CRITIQUE",
                message=f"Incohérence critique [{inc.get('droit')}] : {inc.get('description', '')[:80]}",
                resolution=inc.get("resolution", "Corriger l'incohérence avant dépôt.")[:80],
                bloquant=True,
            ))

    return blocages


def _verif_completude(decision_presoumission) -> list[BlocageGate]:
    """Vérifie le score de complétude."""
    blocages = []
    if decision_presoumission is None:
        return blocages

    score = decision_presoumission.score_completude
    if score < SEUIL_COMPLETUDE_MINIMUM:
        blocages.append(BlocageGate(
            code="COMPLETUDE_CRITIQUE",
            categorie="CRITIQUE",
            message=f"Score de complétude {score}% < seuil minimum {SEUIL_COMPLETUDE_MINIMUM}% — dossier trop incomplet",
            resolution="Compléter les sections administratives, médicales et fonctionnelles avant dépôt.",
            bloquant=True,
        ))
    elif score < SEUIL_COMPLETUDE_RECOMMANDE:
        blocages.append(BlocageGate(
            code="COMPLETUDE_INSUFFISANTE",
            categorie="AVERTISSEMENT",
            message=f"Score de complétude {score}% — en dessous du niveau recommandé ({SEUIL_COMPLETUDE_RECOMMANDE}%)",
            resolution="Enrichir le dossier pour maximiser les chances d'attribution.",
            bloquant=False,
        ))

    return blocages


def _verif_identite(donnees: dict) -> list[BlocageGate]:
    """Vérifie la complétude administrative minimale."""
    blocages = []
    manquants = []

    if not donnees.get("nom_prenom"):
        manquants.append("Nom et prénom")
    if not donnees.get("date_naissance"):
        manquants.append("Date de naissance")
    if not donnees.get("departement"):
        manquants.append("Département MDPH")
    if not donnees.get("droits_demandes"):
        manquants.append("Droits demandés (page E)")

    if manquants:
        blocages.append(BlocageGate(
            code="IDENTITE_INCOMPLETE",
            categorie="CRITIQUE",
            message=f"Données obligatoires manquantes : {', '.join(manquants)}",
            resolution="Compléter les informations d'identité et les droits demandés.",
            bloquant=True,
        ))

    return blocages


def _verif_pieces_obligatoires(decision_presoumission) -> list[BlocageGate]:
    """Vérifie les pièces obligatoires critiques."""
    blocages = []
    if decision_presoumission is None:
        return blocages

    # Regarder les actions avant dépôt qui sont critiques
    actions_critiques = [
        a for a in decision_presoumission.actions_avant_depot
        if "🔴 CRITIQUE" in a
    ]
    if actions_critiques:
        for action in actions_critiques[:2]:
            blocages.append(BlocageGate(
                code="PIECE_CRITIQUE_MANQUANTE",
                categorie="IMPORTANT",
                message=action[:100],
                resolution="Obtenir et joindre la pièce avant génération du CERFA.",
                bloquant=False,  # WARN seulement, pas bloquant
            ))

    return blocages


def _verif_narratifs(donnees: dict, profil_mdph: str) -> list[BlocageGate]:
    """Vérifie la présence des narratifs essentiels."""
    blocages = []
    texte_b = str(donnees.get("texte_b_vie_quotidienne", "") or "")
    if len(texte_b) < 50:
        blocages.append(BlocageGate(
            code="TEXTE_B_ABSENT",
            categorie="IMPORTANT",
            message="Section B (vie quotidienne) absente ou vide — champ décisif pour la CDAPH",
            resolution="Générer le narratif B via le moteur de narration (nécessite clé OpenAI) ou saisir manuellement.",
            bloquant=False,
        ))
    if profil_mdph in ("adulte", "mixte"):
        texte_d = str(donnees.get("texte_d_situation_pro", "") or "")
        if len(texte_d) < 30:
            blocages.append(BlocageGate(
                code="TEXTE_D_ABSENT",
                categorie="AVERTISSEMENT",
                message="Section D (situation professionnelle) vide — important pour RQTH/AAH",
                resolution="Compléter la section D ou générer le narratif.",
                bloquant=False,
            ))

    return blocages


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────────────────────

def verifier_gate_cerfa(
    donnees: dict[str, Any],
    tableau_validation=None,
    decision_presoumission=None,
    profil_mdph: str = "adulte",
) -> ResultatGate:
    """
    Vérifie si le CERFA peut être généré.

    Retourne autorisation=True uniquement si aucun blocage critique.

    Args:
        donnees:               synthese_json du dossier
        tableau_validation:    depuis human_validation_engine
        decision_presoumission: depuis pre_submission_engine
        profil_mdph:           "adulte" | "enfant" | "protege" | "mixte"

    Returns:
        ResultatGate avec décision, blocages et avertissements
    """
    tous_blocages: list[BlocageGate] = []

    # 1. Identité minimale
    tous_blocages.extend(_verif_identite(donnees))

    # 2. Validation humaine
    tous_blocages.extend(_verif_validation_humaine(tableau_validation))

    # 3. Incohérences critiques
    tous_blocages.extend(_verif_incoherences(decision_presoumission))

    # 4. Complétude
    tous_blocages.extend(_verif_completude(decision_presoumission))

    # 5. Narratifs
    tous_blocages.extend(_verif_narratifs(donnees, profil_mdph))

    # 6. Pièces critiques
    tous_blocages.extend(_verif_pieces_obligatoires(decision_presoumission))

    # Séparer bloquants vs avertissements
    bloquants    = [b for b in tous_blocages if b.bloquant]
    avertissements = [b for b in tous_blocages if not b.bloquant]

    autorise_export = len(bloquants) == 0

    # La PRÉVISUALISATION est toujours disponible — seul l'export est conditionnel
    if autorise_export and not avertissements:
        code = "AUTORISE"
        message = "✅ Export autorisé — dossier complet et validé."
    elif autorise_export:
        code = "AUTORISE_AVEC_AVERTISSEMENTS"
        message = (f"⚠️ Export autorisé avec {len(avertissements)} avertissement(s). "
                   "La prévisualisation reste disponible à tout moment.")
    else:
        raisons = " | ".join(b.code for b in bloquants[:2])
        code = "BLOQUE_EXPORT"
        message = (f"❌ Export bloqué — {len(bloquants)} point(s) critique(s) : {raisons}. "
                   "La prévisualisation reste disponible. Corriger avant export définitif.")

    return ResultatGate(
        autorise_previsualisation=True,   # TOUJOURS
        autorise_export=autorise_export,
        code_decision=code,
        blocages=bloquants,
        avertissements=avertissements,
        message_global=message,
        nb_blocages_critriques=len(bloquants),
        nb_avertissements=len(avertissements),
    )
