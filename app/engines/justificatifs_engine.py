"""
app/engines/justificatifs_engine.py — Moteur de signalement des justificatifs MDPH

Règles métier : selon le profil et les droits demandés,
détermine quels justificatifs sont nécessaires à joindre au dossier.

Sprint QA-1 Fix 7 — Signalement critique des pièces justificatives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Justificatif:
    nom: str
    obligatoire: bool
    raison: str
    categorie: str  # "identite" | "medical" | "social" | "emploi" | "juridique" | "scolaire"


def justificatifs_requis(donnees: dict[str, Any], profil_mdph: str = "adulte") -> list[Justificatif]:
    """
    Retourne la liste des justificatifs nécessaires selon le profil.
    Utilisé par le QA engine et par les agents conversationnels.
    """
    result: list[Justificatif] = []

    diagnostics_low = str(donnees.get("diagnostics", "") or "").lower()
    droits_up = str(donnees.get("droits_demandes", "") or "").upper()
    statut_emploi_low = str(donnees.get("statut_emploi", "") or "").lower()
    impact_low = str(donnees.get("impact_quotidien", "") or "").lower()
    type_protection = str(donnees.get("type_protection", "") or "").lower()
    situation_scolaire = str(donnees.get("situation_scolaire", "") or "").lower()

    # ── PIÈCES SYSTÉMATIQUES ─────────────────────────────────────────────────

    result.append(Justificatif(
        nom="Certificat médical de moins de 3 mois",
        obligatoire=True,
        raison="Obligatoire pour tout dossier MDPH",
        categorie="medical",
    ))

    if profil_mdph == "enfant":
        result.append(Justificatif(
            nom="GEVASCO (Groupe d'Évaluation des Volets Administratifs Scolaires)",
            obligatoire=True,
            raison="Document scolaire obligatoire pour les dossiers enfants",
            categorie="scolaire",
        ))
    else:
        result.append(Justificatif(
            nom="Justificatif d'identité (CNI ou passeport)",
            obligatoire=True,
            raison="Pièce d'identité obligatoire",
            categorie="identite",
        ))
        result.append(Justificatif(
            nom="Justificatif de domicile de moins de 3 mois",
            obligatoire=True,
            raison="Justificatif domicile obligatoire",
            categorie="identite",
        ))

    # ── MÉDICAL — SELON DIAGNOSTIC ───────────────────────────────────────────

    _keywords_bilan_neuro = ["autisme", "tsa", "troubles neurodéveloppementaux", "tdah", "dys"]
    if any(k in diagnostics_low for k in _keywords_bilan_neuro):
        result.append(Justificatif(
            nom="Bilan neuropsychologique",
            obligatoire=False,
            raison="Fortement recommandé pour TSA/TDAH/DYS pour étayer les demandes",
            categorie="medical",
        ))

    _keywords_psy = ["schizophrénie", "bipolaire", "psychose", "psychiatr"]
    if any(k in diagnostics_low for k in _keywords_psy):
        result.append(Justificatif(
            nom="Compte-rendu psychiatrique récent",
            obligatoire=False,
            raison="Étayer le retentissement des troubles psychiques",
            categorie="medical",
        ))

    _keywords_moteur = ["sclérose en plaques", "sep", "myopathie", "moteur", "paralysie"]
    if any(k in diagnostics_low for k in _keywords_moteur):
        result.append(Justificatif(
            nom="Bilan de kinésithérapie ou ergothérapie",
            obligatoire=False,
            raison="Évaluation fonctionnelle pour les troubles moteurs",
            categorie="medical",
        ))

    # ── DROITS DEMANDÉS ──────────────────────────────────────────────────────

    if "PCH" in droits_up:
        result.append(Justificatif(
            nom="Devis de prestataire PCH (aide humaine ou technique)",
            obligatoire=False,
            raison="Utile pour étayer la demande PCH",
            categorie="social",
        ))
        result.append(Justificatif(
            nom="Grille d'évaluation des besoins (si déjà réalisée)",
            obligatoire=False,
            raison="Évaluation des besoins PCH",
            categorie="social",
        ))

    if "AEEH" in droits_up:
        result.append(Justificatif(
            nom="Bulletins de salaire ou justificatif ressources du ou des parents",
            obligatoire=False,
            raison="Calcul de l'AEEH complémentaire selon les ressources",
            categorie="social",
        ))

    if "AAH" in droits_up:
        result.append(Justificatif(
            nom="Avis d'imposition ou de non-imposition",
            obligatoire=True,
            raison="Ressources obligatoires pour le calcul de l'AAH",
            categorie="social",
        ))

    if "RQTH" in droits_up:
        result.append(Justificatif(
            nom="Curriculum Vitae et dernier contrat de travail",
            obligatoire=False,
            raison="Pour la demande de RQTH et le plan de compensation emploi",
            categorie="emploi",
        ))

    if "ESAT" in droits_up or "esat" in statut_emploi_low:
        result.append(Justificatif(
            nom="Attestation ou compte-rendu de l'ESAT d'accueil",
            obligatoire=False,
            raison="Confirmation de l'orientation ESAT",
            categorie="emploi",
        ))

    # ── SCOLARITÉ ────────────────────────────────────────────────────────────

    if profil_mdph == "enfant" and situation_scolaire:
        result.append(Justificatif(
            nom="Dernier bulletin scolaire et rapport de l'enseignant référent",
            obligatoire=False,
            raison="Description de la situation scolaire et des aménagements en place",
            categorie="scolaire",
        ))
        if any(k in situation_scolaire for k in ["aesh", "avs", "ulis", "sessad"]):
            result.append(Justificatif(
                nom="Compte-rendu d'ESS (Équipe de Suivi de Scolarisation)",
                obligatoire=False,
                raison="Bilan des aménagements scolaires déjà en place",
                categorie="scolaire",
            ))

    # ── EMPLOI / MÉDECINE DU TRAVAIL ─────────────────────────────────────────

    _arr_travail = ["accident du travail", "arrêt longue durée", "arrêt de travail", "mi-temps thérapeutique"]
    if any(k in statut_emploi_low or k in impact_low for k in _arr_travail):
        result.append(Justificatif(
            nom="Fiche de liaison médecin du travail",
            obligatoire=False,
            raison="Contexte emploi et restrictions médicales au travail",
            categorie="emploi",
        ))
        result.append(Justificatif(
            nom="Attestation de l'employeur ou relevé CPAM",
            obligatoire=False,
            raison="Justifier la rupture ou l'adaptation du parcours professionnel",
            categorie="emploi",
        ))

    # ── PROTECTION JURIDIQUE ─────────────────────────────────────────────────

    if type_protection or profil_mdph == "protege":
        label = "Jugement de tutelle en cours de validité"
        if "habilitation" in type_protection:
            label = "Jugement d'habilitation familiale en cours de validité"
        elif "curatelle" in type_protection:
            label = "Jugement de curatelle en cours de validité"
        result.append(Justificatif(
            nom=label,
            obligatoire=True,
            raison="Obligatoire pour dossier de majeur protégé",
            categorie="juridique",
        ))

    return result


def noms_justificatifs_requis(donnees: dict[str, Any], profil_mdph: str = "adulte") -> list[str]:
    """Retourne uniquement les noms des justificatifs requis."""
    return [j.nom for j in justificatifs_requis(donnees, profil_mdph)]
