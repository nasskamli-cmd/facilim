"""
app/engines/pdf/accueil.py — Onglet 1 : Accueil & Identification.

Couvre la page de garde du CERFA 15692*01 :
  - Type de demande (première demande / renouvellement / recours)
  - Urgence
  - Département et organisme destinataire
"""

from __future__ import annotations

import logging
from typing import Any

from app.database.schemas import DossierCERFA

logger = logging.getLogger("facilim.pdf.accueil")


def mapper_accueil(dossier_cerfa: DossierCERFA, cases_cerfa: dict[str, Any]) -> dict[str, Any]:
    """
    Retourne les champs PDF correspondant à la page de garde (Onglet 1).

    Args:
        dossier_cerfa: Modèle Pydantic complet du dossier
        cases_cerfa: Cases pré-calculées par le moteur de règles

    Returns:
        Dict {nom_champ_pdf: valeur} prêt à être injecté dans le PDF
    """
    fields: dict[str, Any] = {}

    # ── Type de demande ───────────────────────────────────────────────────────
    type_demande = (dossier_cerfa.section_a.type_demande or "").lower()
    if "renouvellement" in type_demande or "renouvellement" in type_demande:
        fields["case_P1_renouvellement"]   = True
        fields["case_P1_premiere_demande"] = False
        fields["case_P1_recours"]          = False
        fields["case_P1_reevaluation"]     = False
    elif "recours" in type_demande:
        fields["case_P1_recours"]          = True
        fields["case_P1_premiere_demande"] = False
        fields["case_P1_renouvellement"]   = False
        fields["case_P1_reevaluation"]     = False
    elif any(k in type_demande for k in ("reevaluation", "réévaluation", "revision", "révision")):
        fields["case_P1_reevaluation"]     = True
        fields["case_P1_premiere_demande"] = False
        fields["case_P1_renouvellement"]   = False
        fields["case_P1_recours"]          = False
    else:
        # Par défaut : première demande
        fields["case_P1_premiere_demande"] = True
        fields["case_P1_renouvellement"]   = False
        fields["case_P1_recours"]          = False
        fields["case_P1_reevaluation"]     = False

    # ── Urgence ───────────────────────────────────────────────────────────────
    if dossier_cerfa.section_urgence.est_urgent:
        fields["Case à cocher P1 urgence"] = True
        if dossier_cerfa.section_urgence.raison_urgence:
            fields["Texte P1 raison_urgence"] = dossier_cerfa.section_urgence.raison_urgence

    # ── Cases héritées du moteur de règles ────────────────────────────────────
    for key in ("case_P1_renouvellement", "case_P1_premiere_demande", "Case à cocher P1 urgence"):
        if key in cases_cerfa:
            fields[key] = cases_cerfa[key]

    logger.debug(f"[PDF/accueil] {len(fields)} champs mappés")
    return fields
