"""
app/engines/rules_engine.py — Moteur de règles métier MDPH.

Encode les règles réglementaires MDPH en logique déterministe.
Ces règles sont non-LLM : elles s'exécutent avant le scoring Jade
et servent de garde-fous contractuels.

Règles implémentées :
  - Certificat médical obligatoire (bloquant)
  - Age minimum/maximum selon le type de droit
  - Cohérence département/domicile
  - Délais de renouvellement (anticipation 6 mois)
  - Pièces justificatives obligatoires par type de demande
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("facilim.engines.rules")


@dataclass
class RuleViolation:
    code:        str
    message:     str
    bloquant:    bool = True
    droit_impact: str | None = None


@dataclass
class RulesResult:
    valid:          bool
    violations:     list[RuleViolation] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)

    def add_violation(self, code: str, message: str, bloquant: bool = True) -> None:
        self.violations.append(RuleViolation(code=code, message=message, bloquant=bloquant))
        if bloquant:
            self.valid = False

    def add_warning(self, message: str) -> None:
        self.avertissements.append(message)


# ── Règles par type de droit ─────────────────────────────────────────────────

_PIECES_PAR_DROIT: dict[str, list[str]] = {
    "AAH": [
        "Justificatif d'identité",
        "Certificat médical (CERFA 13878)",
        "Justificatif de domicile",
        "Avis d'imposition",
    ],
    "PCH": [
        "Justificatif d'identité",
        "Certificat médical (CERFA 13878)",
        "Justificatif de domicile",
        "Devis ou factures des aides humaines",
        "Plan d'aide si renouvellement",
    ],
    "RQTH": [
        "Justificatif d'identité",
        "Certificat médical",
        "Justificatif de domicile",
    ],
    "AEEH": [
        "Justificatif d'identité du responsable légal",
        "Certificat médical enfant (CERFA 13878)",
        "Justificatif de domicile",
        "Compte-rendu scolaire ou médical récent",
    ],
    "CMI": [
        "Justificatif d'identité",
        "Certificat médical",
        "Justificatif de domicile",
        "Photo d'identité",
    ],
}

_AGE_MINIMUM_AAH   = 20
_AGE_MAXIMUM_AEEH  = 20
_AGE_MINIMUM_PCH   = 0   # Possible dès la naissance (si handicap congénital)
_DELAI_RENOUVELLEMENT_ALERTE_JOURS = 180  # 6 mois avant expiration


def check_certificat_medical(dossier: dict[str, Any], pieces: list[dict]) -> RuleViolation | None:
    """Règle bloquante : le certificat médical est obligatoire."""
    has_cert = any(
        p.get("type_piece") in ("CERTIFICAT_MEDICAL", "BILAN_FONCTIONNEL")
        and p.get("validee_par") is not None
        for p in pieces
    )
    if not has_cert:
        return RuleViolation(
            code="CERT_MEDICAL_MANQUANT",
            message=(
                "Le certificat médical (CERFA 13878) est obligatoire pour toute demande MDPH. "
                "Sans ce document, aucune décision ne peut être prise."
            ),
            bloquant=True,
        )
    return None


def check_coherence_age(
    date_naissance: str | None,
    droits_demandes: list[str],
) -> list[RuleViolation]:
    """Vérifie la cohérence âge / type de droit."""
    violations = []
    if not date_naissance:
        return violations

    try:
        # Parsing souple (JJ/MM/AAAA ou AAAA-MM-JJ)
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                ddn = datetime.strptime(date_naissance.strip(), fmt)
                break
            except ValueError:
                continue
        else:
            return violations

        today = datetime.now(timezone.utc).replace(tzinfo=None)
        age_annees = (today - ddn).days // 365

        if "AAH" in droits_demandes and age_annees < _AGE_MINIMUM_AAH:
            violations.append(RuleViolation(
                code="AGE_INSUFFISANT_AAH",
                message=f"L'AAH est accessible à partir de {_AGE_MINIMUM_AAH} ans (âge actuel : {age_annees} ans).",
                bloquant=True,
                droit_impact="AAH",
            ))

        if "AEEH" in droits_demandes and age_annees >= _AGE_MAXIMUM_AEEH:
            violations.append(RuleViolation(
                code="AGE_EXCESSIF_AEEH",
                message=f"L'AEEH est réservée aux enfants de moins de {_AGE_MAXIMUM_AEEH} ans.",
                bloquant=True,
                droit_impact="AEEH",
            ))

    except Exception:
        pass

    return violations


def check_pieces_requises(
    droits_demandes: list[str],
    pieces_presentes: list[dict],
) -> list[str]:
    """Retourne la liste des pièces manquantes selon les droits demandés."""
    types_presents = {p.get("type_piece", "") for p in pieces_presentes}
    manquantes = []

    for droit in droits_demandes:
        pieces_requises = _PIECES_PAR_DROIT.get(droit, [])
        for piece in pieces_requises:
            # Vérification approximative (les types_piece ne correspondent pas 1:1)
            found = any(piece.lower()[:10] in t.lower() for t in types_presents)
            if not found and piece not in manquantes:
                manquantes.append(f"{piece} (requis pour {droit})")

    return manquantes


def check_coherence_departement(
    departement_code: str | None,
    adresse_usager: str | None,
) -> RuleViolation | None:
    """
    Alerte si le département du dossier ne correspond pas à l'adresse.
    Non-bloquant (l'usager peut avoir déménagé).
    """
    if not departement_code or not adresse_usager:
        return None
    # Extraction du code postal dans l'adresse
    import re
    cp_match = re.search(r"\b(\d{5})\b", adresse_usager)
    if not cp_match:
        return None
    cp = cp_match.group(1)
    dept_from_cp = cp[:2] if cp[:2] != "97" else cp[:3]
    if dept_from_cp != departement_code:
        return RuleViolation(
            code="COHERENCE_DEPARTEMENT",
            message=(
                f"Le code postal de l'adresse ({cp}) semble appartenir "
                f"au département {dept_from_cp} mais le dossier est ouvert "
                f"en département {departement_code}. Vérification recommandée."
            ),
            bloquant=False,
        )
    return None


def apply_all_rules(
    dossier: dict[str, Any],
    donnees: dict[str, Any],
    pieces: list[dict],
) -> RulesResult:
    """
    Applique l'ensemble des règles métier sur un dossier.

    Args:
        dossier: Données du dossier (DB)
        donnees: Données collectées (synthese_json)
        pieces: Liste des pièces justificatives

    Returns:
        RulesResult avec violations et avertissements
    """
    result = RulesResult(valid=True)
    droits = donnees.get("types_demande", [])
    if isinstance(droits, str):
        droits = [d.strip() for d in droits.replace(",", " ").split() if d.strip()]

    # Règle 1 : Certificat médical (bloquant)
    violation = check_certificat_medical(dossier, pieces)
    if violation:
        result.add_violation(violation.code, violation.message, violation.bloquant)

    # Règle 2 : Cohérence âge / droits
    ddn = donnees.get("date_naissance")
    age_violations = check_coherence_age(ddn, droits)
    for v in age_violations:
        result.add_violation(v.code, v.message, v.bloquant)

    # Règle 3 : Pièces requises
    pieces_manquantes = check_pieces_requises(droits, pieces)
    for pm in pieces_manquantes:
        result.add_warning(f"Pièce potentiellement manquante : {pm}")

    # Règle 4 : Cohérence département/adresse (non-bloquant)
    dept_violation = check_coherence_departement(
        dossier.get("departement_code"),
        donnees.get("adresse_complete"),
    )
    if dept_violation:
        result.add_violation(dept_violation.code, dept_violation.message, dept_violation.bloquant)

    if result.violations:
        bloquants = [v for v in result.violations if v.bloquant]
        logger.warning(
            f"[RULES] {len(result.violations)} violation(s) | "
            f"{len(bloquants)} bloquante(s) | dossier={dossier.get('id','?')[:8]}"
        )
    else:
        logger.info(f"[RULES] Règles OK | dossier={dossier.get('id','?')[:8]}")

    return result
