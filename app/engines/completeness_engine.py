"""
app/engines/completeness_engine.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FACILIM 90 — Moteur de complétude

Calcule le niveau de complétude d'un dossier MDPH sur 5 dimensions :
  1. Administratif  (20%)
  2. Médical        (25%)
  3. Fonctionnel    (30%)
  4. Projet de vie  (15%)
  5. Justificatifs  (10%)

Usage :
  from app.engines.completeness_engine import evaluer_completude
  rapport = evaluer_completude(donnees, profil_mdph="adulte")
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("facilim.engines.completeness")


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DimensionCompletude:
    nom:            str
    score:          int         # 0-100
    poids:          float       # poids dans le score global
    elements_presents:  list[str]
    elements_manquants: list[str]
    barre:          str


@dataclass
class RapportCompletude:
    score_global:       int
    niveau:             str     # "excellent" | "bon" | "moyen" | "insuffisant" | "critique"
    dimensions:         dict[str, DimensionCompletude]
    elements_bloquants: list[str]   # manques critiques pour recevabilité
    recommandations:    list[str]

    def barre_globale(self) -> str:
        n = int(self.score_global / 100 * 12)
        return "█" * n + "░" * (12 - n)

    def to_dict(self) -> dict:
        return {
            "score_global": self.score_global,
            "niveau":       self.niveau,
            "dimensions":   {
                k: {
                    "score":    d.score,
                    "poids":    d.poids,
                    "presents": d.elements_presents,
                    "manquants":d.elements_manquants,
                }
                for k, d in self.dimensions.items()
            },
            "bloquants":     self.elements_bloquants,
            "recommandations": self.recommandations,
        }


# ─────────────────────────────────────────────────────────────────────────────
# ÉVALUATION DES 5 DIMENSIONS
# ─────────────────────────────────────────────────────────────────────────────

def _barre(score: int, largeur: int = 10) -> str:
    n = int(score / 100 * largeur)
    return "█" * n + "░" * (largeur - n)


def _dim_administratif(donnees: dict) -> DimensionCompletude:
    presents, manquants = [], []
    score = 0

    def _chk(champ: str, label: str, pts: int, alt: str = ""):
        v = donnees.get(champ) or donnees.get(alt, "")
        if v and str(v).strip():
            presents.append(label)
            return pts
        manquants.append(label)
        return 0

    score += _chk("nom_prenom", "Nom et prénom", 20)
    score += _chk("date_naissance", "Date de naissance", 20)
    score += _chk("adresse_complete", "Adresse complète", 15)
    score += _chk("num_secu", "Numéro de sécurité sociale", 20)
    score += _chk("departement", "Département MDPH", 10)
    score += _chk("telephone", "Téléphone", 8)
    score += _chk("genre", "Genre", 4)
    score += _chk("nationalite", "Nationalité", 3)

    return DimensionCompletude(
        nom="Administratif", score=min(100, score), poids=0.20,
        elements_presents=presents, elements_manquants=manquants,
        barre=_barre(min(100, score)),
    )


def _dim_medical(donnees: dict) -> DimensionCompletude:
    presents, manquants = [], []
    score = 0
    texte = " ".join(str(donnees.get(c, "") or "") for c in [
        "diagnostics", "traitements", "notes_pro", "impact_quotidien",
        "texte_b_vie_quotidienne",
    ]).lower()

    # Diagnostics
    diag = str(donnees.get("diagnostics", "") or "")
    if diag and len(diag) > 5:
        presents.append("Diagnostics documentés")
        score += 25
        if len(diag) > 30:
            score += 5  # diagnostic détaillé
    else:
        manquants.append("Diagnostics (indispensable)")

    # Traitements
    trt = str(donnees.get("traitements", "") or "")
    if trt and len(trt) > 5:
        presents.append("Traitements documentés")
        score += 15
    else:
        manquants.append("Traitements en cours")

    # Documents médicaux (notes pro / bilans)
    notes = str(donnees.get("notes_pro", "") or "")
    dk = donnees.get("_document_knowledge") or {}
    if len(notes) > 50:
        presents.append("Documents médicaux présents (bilans/PCR)")
        score += 25
    elif isinstance(dk, dict) and any(dk.values()):
        presents.append("Données documentaires extraites")
        score += 15
    else:
        manquants.append("Certificat médical ou bilan spécialisé")

    # Taux / invalidité / certificat
    has_cert = re.search(r"certificat|bilan|compte.?rendu|attestation", texte)
    has_taux = re.search(r"taux|incapacit[eé]|\d+\s*%", texte)
    if has_cert:
        presents.append("Référence à un certificat médical")
        score += 15
    else:
        manquants.append("Certificat médical récent (< 3 mois)")
    if has_taux:
        presents.append("Taux d'incapacité référencé")
        score += 15
    else:
        manquants.append("Taux d'incapacité permanente")

    return DimensionCompletude(
        nom="Médical", score=min(100, score), poids=0.25,
        elements_presents=presents, elements_manquants=manquants,
        barre=_barre(min(100, score)),
    )


def _dim_fonctionnel(donnees: dict) -> DimensionCompletude:
    presents, manquants = [], []
    score = 0

    impact = str(donnees.get("impact_quotidien", "") or "")
    texte_b = str(donnees.get("texte_b_vie_quotidienne", "") or "")
    restrictions = str(donnees.get("restrictions_emploi", "") or "")
    statut = str(donnees.get("statut_emploi", "") or "")
    all_text = f"{impact} {texte_b} {restrictions}".lower()

    # Impact quotidien
    if len(impact) > 20:
        presents.append("Impact quotidien documenté")
        score += 20
        if len(impact) > 80:
            score += 5
    else:
        manquants.append("Impact quotidien sur la vie (indispensable pour section B)")

    # Texte B narratif
    if len(texte_b) > 300:
        presents.append("Texte B détaillé (narratif vie quotidienne)")
        score += 30
    elif len(texte_b) > 100:
        presents.append("Texte B présent (à enrichir)")
        score += 15
    else:
        manquants.append("Section B (texte vie quotidienne) — priorité absolue")

    # Retentissement professionnel
    if len(statut) > 10 or len(restrictions) > 10:
        presents.append("Situation professionnelle documentée")
        score += 15
    else:
        manquants.append("Retentissement professionnel (statut emploi)")

    # Limitations concrètes (exemples, chiffres)
    has_concrete = re.search(
        r"ne (peut|peux|peut plus|peux plus)\b|\d+.{0,10}(m[eè]tres?|fois|heures?)",
        all_text, re.I
    )
    if has_concrete:
        presents.append("Limitations fonctionnelles objectivées (mesures/impossibilités)")
        score += 20
    else:
        manquants.append("Limitations concrètes (exemples chiffrés, impossibilités nommées)")

    # AVQ
    has_avq = re.search(r"toilette|habillage|alimentation|déplacement|cuisine|courses", all_text)
    if has_avq:
        presents.append("Activités de la vie quotidienne (AVQ) citées")
        score += 10
    else:
        manquants.append("AVQ (toilette, habillage, alimentation, déplacements...)")

    return DimensionCompletude(
        nom="Fonctionnel", score=min(100, score), poids=0.30,
        elements_presents=presents, elements_manquants=manquants,
        barre=_barre(min(100, score)),
    )


def _dim_projet_vie(donnees: dict, profil_mdph: str) -> DimensionCompletude:
    presents, manquants = [], []
    score = 0

    texte_e = str(donnees.get("texte_e_projet_vie", "") or "")
    droits   = str(donnees.get("droits_demandes", "") or "")
    proj     = str(donnees.get("projet_orientation", "") or "")
    texte_c  = str(donnees.get("texte_c_scolarite", "") or "")
    texte_d  = str(donnees.get("texte_d_situation_pro", "") or "")

    # ── FACILIM V2 (ADDITIF) — lire les FAITS du domaine projet si présents ──
    # Source fiable si disponible ; sinon fallback intégral sur le dict plat ci-dessus.
    _faits_projet_champs: set = set()
    try:
        from app.services.faits import faits_domaine
        _faits_projet_champs = {
            f.get("champ") for f in faits_domaine(donnees, "projet_professionnel")
            if f.get("valeur")
        }
    except Exception:
        _faits_projet_champs = set()

    # Texte E / projet de vie
    if len(texte_e) > 200:
        presents.append("Section E (projet de vie) documentée")
        score += 35
    elif len(texte_e) > 50:
        presents.append("Section E présente (à enrichir)")
        score += 15
    else:
        manquants.append("Section E (projet de vie) absente — attendue par la CDAPH")

    # Droits demandés
    if droits.strip():
        presents.append(f"Droits demandés identifiés ({droits[:40]}...)" if len(droits) > 40 else f"Droits : {droits}")
        score += 25
    else:
        manquants.append("Droits demandés non identifiés")

    # Orientation précisée — clé plate OU fait canonique projet (V2, additif)
    _orientation_via_fait = bool(_faits_projet_champs & {
        "orientation_souhaitee", "projet_professionnel",
        "formation_cible", "etablissement_cible",
    })
    if proj.strip() or _orientation_via_fait or re.search(
        r"(ESAT|ESPO|SESSAD|milieu ordinaire|foyer|SAVS)", droits + texte_e
    ):
        presents.append("Orientation ou structure souhaitée précisée")
        score += 20
    else:
        manquants.append("Orientation souhaitée non précisée")

    # Section C ou D selon profil
    if profil_mdph in ("enfant", "mixte") and len(texte_c) > 100:
        presents.append("Section C (scolarité) documentée")
        score += 20
    elif profil_mdph in ("adulte", "protege") and len(texte_d) > 100:
        presents.append("Section D (emploi) documentée")
        score += 20
    else:
        if profil_mdph in ("enfant", "mixte"):
            manquants.append("Section C (scolarité) absente")
        else:
            manquants.append("Section D (situation professionnelle) absente")

    return DimensionCompletude(
        nom="Projet de vie", score=min(100, score), poids=0.15,
        elements_presents=presents, elements_manquants=manquants,
        barre=_barre(min(100, score)),
    )


def _dim_justificatifs(donnees: dict, profil_mdph: str) -> DimensionCompletude:
    presents, manquants = [], []
    score = 0

    try:
        from app.engines.justificatifs_engine import justificatifs_requis
        justifs = justificatifs_requis(donnees, profil_mdph)
        nb_oblig = len([j for j in justifs if j.obligatoire])
        nb_total = len(justifs)

        if nb_oblig > 0:
            presents.append(f"{nb_oblig} pièce(s) obligatoire(s) identifiée(s)")
            score += 30
        if nb_total > nb_oblig:
            presents.append(f"{nb_total - nb_oblig} pièce(s) recommandée(s)")
            score += 10
    except Exception:
        manquants.append("Liste de justificatifs non générée")

    # Vérifier la présence réelle de pièces
    notes = str(donnees.get("notes_pro", "") or "")
    dk = donnees.get("_document_knowledge") or {}

    if len(notes) > 30:
        presents.append("Notes professionnelles / PCR présent")
        score += 25
    else:
        manquants.append("Aucun document professionnel joint")

    if isinstance(dk, dict) and any(isinstance(v, list) and v for v in dk.values()):
        presents.append("Données documentaires extraites (bilans, restrictions)")
        score += 20
    else:
        manquants.append("Bilans spécialisés ou comptes-rendus")

    # GEVASCO pour enfants
    if profil_mdph in ("enfant", "mixte"):
        texte_all = f"{notes} {str(dk)}".lower()
        if re.search(r"gevasco|ess|évaluation scolaire", texte_all):
            presents.append("GEVASCO ou ESS référencé")
            score += 15
        else:
            manquants.append("GEVASCO (guide évaluation scolaire) — indispensable enfant")

    return DimensionCompletude(
        nom="Justificatifs", score=min(100, score), poids=0.10,
        elements_presents=presents, elements_manquants=manquants,
        barre=_barre(min(100, score)),
    )


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────────────────────

def evaluer_completude(
    donnees: dict[str, Any],
    profil_mdph: str = "adulte",
) -> RapportCompletude:
    """
    Évalue le niveau de complétude d'un dossier MDPH sur 5 dimensions.

    Returns:
        RapportCompletude avec scores détaillés et recommandations
    """
    dims = {
        "administratif": _dim_administratif(donnees),
        "medical":       _dim_medical(donnees),
        "fonctionnel":   _dim_fonctionnel(donnees),
        "projet_vie":    _dim_projet_vie(donnees, profil_mdph),
        "justificatifs": _dim_justificatifs(donnees, profil_mdph),
    }

    # Score global pondéré
    score_global = round(sum(d.score * d.poids for d in dims.values()))
    niveau = (
        "excellent"    if score_global >= 85 else
        "bon"          if score_global >= 70 else
        "moyen"        if score_global >= 50 else
        "insuffisant"  if score_global >= 30 else
        "critique"
    )

    # Éléments bloquants (manquants dans les sections critiques)
    bloquants = []
    if dims["administratif"].score < 40:
        bloquants.append("Données administratives incomplètes — recevabilité compromise")
    if "Diagnostics (indispensable)" in dims["medical"].elements_manquants:
        bloquants.append("Diagnostic médical absent — dossier non recevable")
    if any("Section B" in m for m in dims["fonctionnel"].elements_manquants):
        bloquants.append("Section B absente — évaluation impossible sans description vie quotidienne")
    if any("Droits" in m for m in dims["projet_vie"].elements_manquants):
        bloquants.append("Aucun droit demandé — CERFA incomplet")

    # Recommandations prioritaires
    recommandations = []
    dims_triees = sorted(dims.items(), key=lambda x: x[1].score)
    for _, dim in dims_triees[:3]:
        if dim.elements_manquants:
            recommandations.append(
                f"{dim.nom} ({dim.score}%) — Manque : {dim.elements_manquants[0]}"
            )

    return RapportCompletude(
        score_global=score_global,
        niveau=niveau,
        dimensions=dims,
        elements_bloquants=bloquants,
        recommandations=recommandations,
    )
