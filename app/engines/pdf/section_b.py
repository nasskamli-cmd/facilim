"""
app/engines/pdf/section_b.py — Onglets 4-5-6 : Quotidien, Compensations & Besoins.

Onglet 4 — Quotidien & Ressources (Section B Partie 1) :
  Mode de vie, logement, accidents, allocations et pensions perçues

Onglet 5 — Compensations & Frais (Section B Partie 2) :
  Aides humaines/techniques déjà en place, frais restants à charge

Onglet 6 — Évaluation des Besoins (Section B Partie 3) :
  Boîtes à cocher des besoins ressentis : domicile, déplacements, vie sociale
"""

from __future__ import annotations

import logging
from typing import Any

from app.database.schemas import DossierCERFA

logger = logging.getLogger("facilim.pdf.section_b")


def mapper_section_b(dossier_cerfa: DossierCERFA, cases_cerfa: dict[str, Any]) -> dict[str, Any]:
    """
    Retourne les champs PDF des Onglets 4, 5 et 6 (vie quotidienne → besoins).
    Utilise le texte narratif Phase 3 si disponible (qualité supérieure).
    Fallback sur les données brutes si absent.
    """
    fields: dict[str, Any] = {}
    c = dossier_cerfa.section_c  # section_c = Vie Quotidienne dans le schéma Facilim

    if not c:
        return fields

    # ── Onglet 4 — Logement et ressources ────────────────────────────────────
    # Statut d'occupation — anti-inversion via cases_cerfa pré-calculées
    for key in (
        "OPTION_P5_2_proprietaire",
        "OPTION_P5_2_locataire",
        "OPTION_P5_2_heberge",
    ):
        if key in cases_cerfa:
            fields[key] = cases_cerfa[key]

    # Texte narratif Phase 3 (prioritaire si présent et suffisant)
    _texte_narratif_b = getattr(dossier_cerfa, "texte_b_vie_quotidienne", None) or ""
    if _texte_narratif_b and len(_texte_narratif_b) >= 100:
        _set(fields, "Texte P5 difficultes_quotidiennes", _texte_narratif_b)
        logger.debug("[PDF/section_b] Texte narratif Phase 3 utilisé (%d chars)", len(_texte_narratif_b))
    else:
        _set(fields, "Texte P5 difficultes_quotidiennes", c.difficultes_quotidiennes)

    _set(fields, "Texte P5 type_logement",            c.type_logement)
    _set(fields, "Texte P5 ressources_mensuelles",    c.ressources_mensuelles)
    _set(fields, "Texte P5 allocations_percues",      c.allocations_percues)

    # ── Onglet 5 — Compensations existantes ──────────────────────────────────
    if c.beneficie_aide_humaine:
        fields["case_P6_aide_humaine"] = True
        _set(fields, "Texte P6 aide_humaine_detail", c.detail_aide_humaine)

    if c.beneficie_aide_technique:
        fields["case_P6_aide_technique"] = True
        _set(fields, "Texte P6 aide_technique_detail", c.detail_aide_technique)

    _set(fields, "Texte P6 frais_restant_charge", c.frais_restant_charge)
    _set(fields, "Texte P6 amenagement_logement",  c.amenagement_logement)

    # ── Onglet 6 — Cases besoins ressentis ───────────────────────────────────
    # Mobilité / déplacements
    for key in (
        "case_C1_difficulte_deplacement",
        "case_C1_deplacement_interieur_autonome",
        "case_C1_besoin_aide_toilette",
    ):
        if key in cases_cerfa:
            fields[key] = cases_cerfa[key]

    if c.besoin_aide_repas:
        fields["case_P6_besoin_aide_repas"] = True
    if c.besoin_aide_communication:
        fields["case_P6_besoin_aide_communication"] = True
    if c.besoin_aide_vie_sociale:
        fields["case_P6_besoin_aide_vie_sociale"] = True

    # Opposition IME (enfant/mixte) issue de la règle B
    if getattr(c, "opposition_ime", False):
        fields["case_P7_opposition_ime"]          = True
        fields["case_P7_scolarisation_ordinaire"] = True

    logger.debug(f"[PDF/section_b] {len(fields)} champs mappés")
    return fields


def _set(fields: dict, key: str, value: Any) -> None:
    if value is not None and value != "":
        fields[key] = str(value).strip()
