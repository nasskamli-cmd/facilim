"""
app/agents/registry.py — Registre des agents internes Facilim.

Les agents sont des états logiques INTERNES, invisibles à l'usager.
L'usager voit toujours "l'Assistant Facilim" (façade unique).

Agents définis :
  Emma    (N1) — Accueil, identification, consentement
  Lucas   (N2) — Collecte structurée et vérification checklist
  Noah    (N2) — Analyse juridique / Jade (RAG réglementaire)
  Léa     (N3) — Traitement documentaire et OCR
  Paul    (N1) — Notifications et relances
  Fatima  (N2) — Conformité RGPD et anonymisation
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentDefinition:
    nom:        str
    niveau:     str
    role:       str
    canal:      str       # whatsapp|dashboard|system|all
    description: str


REGISTRY: dict[str, AgentDefinition] = {
    "emma": AgentDefinition(
        nom         = "Emma",
        niveau      = "N1",
        role        = "Accueil et identification",
        canal       = "whatsapp",
        description = (
            "Gère le premier contact, la demande de consentement, l'identification "
            "de l'usager et l'orientation vers le bon parcours (adulte/enfant/renouvellement)."
        ),
    ),
    "lucas": AgentDefinition(
        nom         = "Lucas",
        niveau      = "N2",
        role        = "Collecte structurée MDPH",
        canal       = "whatsapp",
        description = (
            "Orchestre la collecte conversationnelle des 16 champs obligatoires MDPH. "
            "Pose une question à la fois, valide les réponses, détecte les incohérences."
        ),
    ),
    "noah": AgentDefinition(
        nom         = "Noah",
        niveau      = "N2",
        role        = "Analyse juridique (Jade)",
        canal       = "system",
        description = (
            "Moteur de scoring réglementaire basé sur le RAG juridique. "
            "Cite toujours ses sources (CASF, Loi 2005-102, GEVA). "
            "Ne peut pas halluciner — confiance insuffisante = NON_CALCULÉ + flag humain."
        ),
    ),
    "lea": AgentDefinition(
        nom         = "Léa",
        niveau      = "N3",
        role        = "Traitement documentaire",
        canal       = "system",
        description = (
            "Reçoit et traite les pièces justificatives (OCR, extraction, validation). "
            "Génère les CERFA pré-remplis. "
            "Score OCR < 90% → flag humain systématique."
        ),
    ),
    "paul": AgentDefinition(
        nom         = "Paul",
        niveau      = "N1",
        role        = "Notifications et relances",
        canal       = "all",
        description = (
            "Gère les relances planifiées (pièces manquantes, renouvellements, expirations). "
            "Sélectionne le canal optimal selon les préférences de l'usager."
        ),
    ),
    "fatima": AgentDefinition(
        nom         = "Fatima",
        niveau      = "N2",
        role        = "Conformité RGPD",
        canal       = "system",
        description = (
            "Anonymisation des données, purge automatique après conservation, "
            "export RGPD, traitement des demandes de retrait de consentement."
        ),
    ),
}


def get_agent(nom: str) -> AgentDefinition | None:
    """Retourne la définition d'un agent par son nom (case-insensitive)."""
    return REGISTRY.get(nom.lower())


def list_agents() -> list[dict[str, str]]:
    """Retourne la liste des agents pour le Dashboard ESSMS."""
    return [
        {
            "nom":         a.nom,
            "niveau":      a.niveau,
            "role":        a.role,
            "description": a.description,
        }
        for a in REGISTRY.values()
    ]
