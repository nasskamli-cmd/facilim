"""
app/agents/anonymizer.py — Agent Fatima : anonymisation des données personnelles.

L'anonymisation est obligatoire avant tout traitement LLM.
Aucune donnée identifiante ne doit atteindre le modèle de langage.

Stratégie :
  1. Remplacement par jetons génériques ([NOM], [PRÉNOM], [DDN], [NSS], [TEL], [ADR])
  2. Hash déterministe des identifiants (pour corrélation sans identification)
  3. Log de chaque opération d'anonymisation
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

logger = logging.getLogger("facilim.agents.fatima")

# ── Patterns d'anonymisation ─────────────────────────────────────────────────

_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Numéro de Sécurité Sociale (15 chiffres)
    (re.compile(r"\b[12]\s*\d{2}\s*\d{2}\s*\d{2,3}\s*\d{3}\s*\d{3}\s*\d{2}\b"), "[NSS]"),
    # Numéros de téléphone français
    (re.compile(r"\b0[1-9][\s.\-]?\d{2}[\s.\-]?\d{2}[\s.\-]?\d{2}[\s.\-]?\d{2}\b"), "[TEL]"),
    (re.compile(r"\+33[\s.\-]?\d[\s.\-]?\d{2}[\s.\-]?\d{2}[\s.\-]?\d{2}[\s.\-]?\d{2}\b"), "[TEL]"),
    # Adresses email
    (re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"), "[EMAIL]"),
    # Dates de naissance (formats courants)
    (re.compile(r"\b\d{2}/\d{2}/\d{4}\b"), "[DDN]"),
    (re.compile(r"\b\d{2}-\d{2}-\d{4}\b"), "[DDN]"),
    # Codes postaux (5 chiffres avec contexte)
    (re.compile(r"\b[0-9]{5}\b"), "[CP]"),
    # IP addresses
    (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "[IP]"),
]

# Noms fréquents à anonymiser (complété par le LLM en production)
_SALUTATIONS = re.compile(
    r"(?:M\.|Mme\.?|Monsieur|Madame|Dr\.?|Docteur)\s+([A-Z][a-zéèêëàâùûü]+(?:\s+[A-Z][a-zéèêëàâùûü]+)*)",
    re.UNICODE,
)


def anonymize_text(
    text: str,
    preserve_structure: bool = True,
) -> tuple[str, dict[str, str]]:
    """
    Anonymise un texte en remplaçant les données identifiantes par des jetons.

    Args:
        text: Texte brut à anonymiser
        preserve_structure: Conserve la ponctuation et la structure

    Returns:
        (texte_anonymisé, mapping_jetons)
        Le mapping permet de reconstruire le texte si nécessaire (usage interne uniquement).
    """
    result = text
    mapping: dict[str, str] = {}

    # Remplacement des salutations avec noms
    for match in _SALUTATIONS.finditer(result):
        original = match.group(0)
        nom = match.group(1)
        jeton = f"[NOM_{hashlib.md5(nom.encode()).hexdigest()[:6].upper()}]"
        mapping[jeton] = original
        result = result.replace(original, jeton)

    # Application des patterns regex
    for pattern, jeton_type in _PATTERNS:
        def replace_with_token(m: re.Match, token: str = jeton_type) -> str:
            original = m.group(0)
            h = hashlib.md5(original.encode()).hexdigest()[:4].upper()
            jeton = f"{token}_{h}"
            mapping[jeton] = original
            return jeton
        result = pattern.sub(replace_with_token, result)

    logger.debug(f"[ANON] Anonymisation : {len(mapping)} éléments remplacés")
    return result, mapping


def anonymize_field(value: str | None, field_type: str = "DONNEE") -> str:
    """Anonymise une valeur individuelle pour les logs."""
    if not value:
        return ""
    h = hashlib.sha256(value.encode()).hexdigest()[:8]
    return f"[{field_type}:{h}]"


def check_anonymization_quality(
    original: str,
    anonymized: str,
    threshold: float = 0.90,
) -> tuple[bool, float]:
    """
    Vérifie que l'anonymisation est suffisante.
    Retourne (ok, score_confiance).
    Score = 1 - (ratio de chiffres/caractères spéciaux non remplacés).
    """
    # Heuristique : un texte bien anonymisé ne doit pas contenir
    # de longues séquences de chiffres (NSS, téléphones) non remplacées
    long_digit_sequences = re.findall(r"\d{8,}", anonymized)
    suspicious_emails = re.findall(r"\S+@\S+\.\S+", anonymized)

    issues = len(long_digit_sequences) + len(suspicious_emails)
    total_words = len(anonymized.split())
    confidence = max(0.0, 1.0 - (issues / max(total_words, 1)) * 10)
    ok = confidence >= threshold

    if not ok:
        logger.warning(
            f"[ANON] Qualité insuffisante | conf={confidence:.2f} | "
            f"séquences_suspectes={issues}"
        )

    return ok, round(confidence, 3)
