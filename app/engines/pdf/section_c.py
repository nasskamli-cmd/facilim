"""
app/engines/pdf/section_c.py — Onglet 7 : Scolarité & Études (Section C CERFA).

Couvre les pages 9-12 du CERFA pour les profils enfant/mixte :
  - Situation scolaire actuelle
  - Aménagements et emploi du temps
  - Besoins de compensation en milieu éducatif
  - Projet d'orientation scolaire
"""

from __future__ import annotations

import logging
from typing import Any

from app.database.schemas import DossierCERFA

logger = logging.getLogger("facilim.pdf.section_c")


def mapper_section_c(dossier_cerfa: DossierCERFA, _cases_cerfa: dict[str, Any]) -> dict[str, Any]:
    """
    Retourne les champs PDF de la Section C (Scolarité / Onglet 7).

    Actif uniquement pour les profils enfant et mixte.
    Pour les adultes, retourne un dict vide (pages non remplies).
    """
    fields: dict[str, Any] = {}

    if dossier_cerfa.profil not in ("enfant", "mixte"):
        logger.debug("[PDF/section_c] Profil adulte — section C ignorée")
        return fields

    b = dossier_cerfa.section_b  # section_b = Vie Scolaire dans le schéma Facilim
    if not b:
        return fields

    # ── Situation scolaire ────────────────────────────────────────────────────
    _set(fields, "Texte P9 etablissement_scolaire",  b.etablissement_scolaire)
    _set(fields, "Texte P9 classe_niveau",           b.classe_niveau)
    _set(fields, "Texte P9 commune_etablissement",   b.commune_etablissement)

    # Type d'établissement
    type_etab = (b.type_etablissement or "").upper()
    for t in ("ORDINAIRE", "ULIS", "IME", "ITEP", "SEGPA", "AUTRE"):
        fields[f"case_P9_etab_{t.lower()}"] = t in type_etab

    # ── Aménagements déjà en place ────────────────────────────────────────────
    if b.beneficie_avs:
        fields["case_P10_avs"] = True
        _set(fields, "Texte P10 avs_detail", b.detail_avs)

    if b.beneficie_amenagement_temps:
        fields["case_P10_amenagement_temps"] = True

    if b.beneficie_materiel_adapte:
        fields["case_P10_materiel_adapte"] = True
        _set(fields, "Texte P10 materiel_adapte_detail", b.detail_materiel_adapte)

    # ── Projet d'orientation scolaire ─────────────────────────────────────────
    _set(fields, "Texte P11 projet_orientation_scolaire", b.projet_orientation_scolaire)
    _set(fields, "Texte P11 attentes_famille",            b.attentes_famille_scolarite)

    logger.debug(f"[PDF/section_c] {len(fields)} champs mappés")
    return fields


def _set(fields: dict, key: str, value: Any) -> None:
    if value is not None and value != "":
        fields[key] = str(value).strip()
