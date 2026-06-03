"""
app/engines/pdf/section_f.py — Onglet 10 : Aidant Familial (Section F CERFA).

Couvre les pages 19-20 du CERFA :
  - Identité de l'aidant
  - Nature et volume de l'aide apportée
  - Besoins de répit et attentes de l'aidant

Les pages 19-20 sont laissées vides si _aidant_present == False dans cases_cerfa.
"""

from __future__ import annotations

import logging
from typing import Any

from app.database.schemas import DossierCERFA

logger = logging.getLogger("facilim.pdf.section_f")


def mapper_section_f(dossier_cerfa: DossierCERFA, cases_cerfa: dict[str, Any]) -> dict[str, Any]:
    """
    Retourne les champs PDF de la Section F (Aidant familial / Onglet 10).

    Si _aidant_present est False dans cases_cerfa, les pages 19-20 restent vierges.
    """
    fields: dict[str, Any] = {}

    # Signal provenant du moteur de règles
    if not cases_cerfa.get("_aidant_present", False):
        logger.debug("[PDF/section_f] Pas d'aidant déclaré — pages 19-20 ignorées")
        return fields

    aidant = dossier_cerfa.section_f.aidant if dossier_cerfa.section_f else None
    if not aidant:
        return fields

    # ── Identité de l'aidant ──────────────────────────────────────────────────
    _set(fields, "Texte P19 aidant_nom",     aidant.nom)
    _set(fields, "Texte P19 aidant_prenom",  aidant.prenom)
    _set(fields, "Texte P19 aidant_lien",    aidant.lien_avec_usager)
    _set(fields, "Texte P19 aidant_tel",     aidant.telephone)

    if aidant.lien_avec_usager:
        lien = aidant.lien_avec_usager.upper()
        for rel in ("CONJOINT", "PARENT", "ENFANT", "FRATRIE", "AUTRE"):
            fields[f"case_P19_lien_{rel.lower()}"] = rel in lien

    # ── Nature de l'aide ──────────────────────────────────────────────────────
    _set(fields, "Texte P19 aide_nature",       aidant.nature_aide)
    _set(fields, "Texte P19 aide_heures_semaine", aidant.heures_aide_hebdomadaire)

    if aidant.aide_toilette:
        fields["case_P19_aide_toilette"] = True
    if aidant.aide_repas:
        fields["case_P19_aide_repas"] = True
    if aidant.aide_deplacements:
        fields["case_P19_aide_deplacements"] = True
    if aidant.aide_communication:
        fields["case_P19_aide_communication"] = True
    if aidant.aide_administrative:
        fields["case_P19_aide_administrative"] = True

    # ── Besoins de répit et attentes (page 20) ────────────────────────────────
    _set(fields, "Texte P20 besoins_repit",   aidant.besoins_repit)
    _set(fields, "Texte P20 attentes_aidant", aidant.attentes)

    if aidant.souhaite_formation:
        fields["case_P20_souhaite_formation"] = True

    logger.debug(f"[PDF/section_f] {len(fields)} champs mappés")
    return fields


def _set(fields: dict, key: str, value: Any) -> None:
    if value is not None and value != "":
        fields[key] = str(value).strip()
