"""
app/engines/pdf/section_d.py — Onglets 8-9 : Situation & Projet Professionnel.

Onglet 8 — Situation Professionnelle (Section D Partie 1) :
  Emploi actuel, arrêts de travail, parcours, diplômes et compétences

Onglet 9 — Projet Professionnel (Section D Partie 2) :
  Attentes, souhaits de formation, structures d'accompagnement identifiées
  Inclut les cases d'orientation issues de la Règle A (autodétermination)
"""

from __future__ import annotations

import logging
from typing import Any

from app.database.schemas import DossierCERFA

logger = logging.getLogger("facilim.pdf.section_d")


def mapper_section_d(dossier_cerfa: DossierCERFA, cases_cerfa: dict[str, Any]) -> dict[str, Any]:
    """
    Retourne les champs PDF des Sections D et E (Onglets 8 et 9).

    Actif pour les profils adulte et mixte.
    """
    fields: dict[str, Any] = {}

    if dossier_cerfa.profil not in ("adulte", "mixte"):
        logger.debug("[PDF/section_d] Profil enfant — sections D/E ignorées")
        return fields

    d = dossier_cerfa.section_d
    e = dossier_cerfa.section_e

    # ── Onglet 8 — Situation professionnelle actuelle ─────────────────────────
    if d:
        statut = (d.statut_emploi or "").upper()
        for s in ("EMPLOI", "CHOMAGE", "INACTIF", "RETRAITE", "INVALIDITE"):
            fields[f"case_P13_statut_{s.lower()}"] = s in statut

        _set(fields, "Texte P13 employeur",           d.nom_employeur)
        _set(fields, "Texte P13 poste_occupe",        d.poste_occupe)
        _set(fields, "Texte P13 secteur_activite",    d.secteur_activite)
        _set(fields, "Texte P13 date_arret_travail",  d.date_arret_travail)
        _set(fields, "Texte P14 diplome_niveau",      d.diplome_plus_eleve)
        _set(fields, "Texte P14 formations_suivies",  d.formations_suivies)
        _set(fields, "Texte P14 competences_cles",    d.competences_cles)

    # ── Texte narratif Phase 3 (situation pro) ───────────────────────────────
    _texte_narratif_d = getattr(dossier_cerfa, "texte_d_situation_pro", None) or ""
    if _texte_narratif_d and len(_texte_narratif_d) >= 80 and d:
        _set(fields, "Texte P13 consequences_pro", _texte_narratif_d)
        logger.debug("[PDF/section_d] Texte narratif Phase 3 utilisé (%d chars)", len(_texte_narratif_d))

    # ── Texte narratif Phase 3 (projet de vie / section E) ────────────────────
    _texte_narratif_e = getattr(dossier_cerfa, "texte_e_projet_vie", None) or ""
    if _texte_narratif_e and len(_texte_narratif_e) >= 80 and e:
        _set(fields, "Texte P18 projet_vie_narratif", _texte_narratif_e)
        logger.debug("[PDF/section_d] Texte narratif Projet de vie utilisé (%d chars)", len(_texte_narratif_e))

    # ── Onglet 9 — Projet professionnel ──────────────────────────────────────
    if e:
        # Cases d'orientation (déjà calculées par le moteur de règles)
        for key in (
            "Case à cocher P18 1",  # RQTH
            "Case à cocher P18 2",  # ESPO
            "Case à cocher P18 3",  # ESRP
            "Case à cocher P18 4",  # ESAT
            "Case à cocher P18 EA", # Entreprise adaptée
            "Case à cocher P18 6",  # Emploi accompagné
            "Case à cocher CMI priorité",
            "Case à cocher CMI stationnement",
        ):
            if key in cases_cerfa:
                fields[key] = cases_cerfa[key]

        _set(fields, "Texte P18 projet_professionnel",    e.projet_professionnel)
        _set(fields, "Texte P18 structures_identifiees",  e.structures_identifiees)
        _set(fields, "Texte P18 souhait_formation",       e.souhait_formation)

    logger.debug(f"[PDF/section_d] {len(fields)} champs mappés")
    return fields


def _set(fields: dict, key: str, value: Any) -> None:
    if value is not None and value != "":
        fields[key] = str(value).strip()
