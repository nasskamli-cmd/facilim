"""
app/engines/pdf/section_a.py — Onglets 2-3 : Identité & Représentation.

Onglet 2 — Identité & Logistique (Section A Partie 1) :
  Nom, prénom, date de naissance, NIR, adresse, coordonnées

Onglet 3 — Représentation & Urgences (Section A Partie 2) :
  Autorité parentale, tuteurs, situations critiques
"""

from __future__ import annotations

import logging
from typing import Any

from app.database.schemas import DossierCERFA

logger = logging.getLogger("facilim.pdf.section_a")


def mapper_section_a(dossier_cerfa: DossierCERFA, _cases_cerfa: dict[str, Any]) -> dict[str, Any]:
    """
    Retourne les champs PDF de la Section A (Onglets 2 et 3).

    Toutes les valeurs textuelles viennent de section_a du DossierCERFA.
    Les données chiffrées sont passées déjà déchiffrées dans les champs Pydantic.
    """
    fields: dict[str, Any] = {}
    a = dossier_cerfa.section_a

    # ── Onglet 2 — Identité ───────────────────────────────────────────────────
    _set(fields, "Texte P2 nom_naissance",     a.nom_naissance)
    _set(fields, "Texte P2 nom_usage",         a.nom_usage)
    _set(fields, "Texte P2 prenom",            a.prenom)
    _set(fields, "Texte P2 date_naissance",    a.date_naissance)
    _set(fields, "Texte P2 lieu_naissance",    a.lieu_naissance)
    _set(fields, "Texte P2 nir",               a.nir)
    _set(fields, "Texte P2 adresse",           a.adresse_complete)
    _set(fields, "Texte P2 code_postal",       a.code_postal)
    _set(fields, "Texte P2 commune",           a.commune)
    _set(fields, "Texte P2 telephone",         a.telephone)
    _set(fields, "Texte P2 email",             a.email)
    _set(fields, "Texte P2 nationalite",       a.nationalite)

    # Sexe
    if a.sexe == "M":
        fields["case_P2_sexe_M"] = True
        fields["case_P2_sexe_F"] = False
    elif a.sexe == "F":
        fields["case_P2_sexe_M"] = False
        fields["case_P2_sexe_F"] = True

    # ── Onglet 3 — Représentation légale ─────────────────────────────────────
    situation_jur = dossier_cerfa.situation_juridique
    if situation_jur:
        _set(fields, "Texte P3 representant_nom",    situation_jur.representant_nom)
        _set(fields, "Texte P3 representant_prenom", situation_jur.representant_prenom)
        _set(fields, "Texte P3 representant_lien",   situation_jur.lien_parente)
        _set(fields, "Texte P3 representant_tel",    situation_jur.telephone_representant)

        # Type de protection juridique
        protection = (situation_jur.type_protection or "").upper()
        for mesure in ("TUTELLE", "CURATELLE", "SAUVEGARDE", "HABILITATION_FAMILIALE"):
            fields[f"case_P3_{mesure.lower()}"] = mesure in protection

    logger.debug(f"[PDF/section_a] {len(fields)} champs mappés")
    return fields


def _set(fields: dict, key: str, value: Any) -> None:
    if value is not None and value != "":
        fields[key] = str(value).strip()
