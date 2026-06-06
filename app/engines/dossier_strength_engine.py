"""
app/engines/dossier_strength_engine.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FACILIM 60 — Moteur 2 : Robustesse du dossier

Note la solidité du dossier droit par droit selon 7 critères pondérés :

  30 %  Retentissement fonctionnel
  20 %  Narratif B (texte vie quotidienne)
  15 %  Narratif D ou C (emploi / scolarité)
  10 %  Projet de vie (texte E)
  10 %  Documents (notes_pro, _document_knowledge)
  10 %  Cohérence globale
   5 %  Verbatim direct

Usage :
  from app.engines.dossier_strength_engine import noter_robustesse
  resultat = noter_robustesse(donnees, profil_mdph="adulte")
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("facilim.engines.dossier_strength")

# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DetailScores:
    retentissement:     int   # /100 — limitations fonctionnelles concrètes
    narratif_b:         int   # /100 — qualité texte vie quotidienne
    narratif_dc:        int   # /100 — qualité texte emploi ou scolarité
    projet_vie:         int   # /100 — qualité section E
    documents:          int   # /100 — richesse documentaire
    coherence:          int   # /100 — cohérence inter-sections
    verbatim:           int   # /100 — présence expressions directes


@dataclass
class RobustesseDossier:
    score_global:       int
    scores_par_droit:   dict[str, int]
    points_forts:       list[str]
    points_faibles:     list[str]
    axes_amelioration:  list[str]
    detail_scores:      DetailScores


# ─────────────────────────────────────────────────────────────────────────────
# CRITÈRES PONDÉRÉS
# ─────────────────────────────────────────────────────────────────────────────

POIDS = {
    "retentissement": 0.30,
    "narratif_b":     0.20,
    "narratif_dc":    0.15,
    "projet_vie":     0.10,
    "documents":      0.10,
    "coherence":      0.10,
    "verbatim":       0.05,
}


def _score_global(detail: DetailScores) -> int:
    return round(
        detail.retentissement * POIDS["retentissement"]
        + detail.narratif_b   * POIDS["narratif_b"]
        + detail.narratif_dc  * POIDS["narratif_dc"]
        + detail.projet_vie   * POIDS["projet_vie"]
        + detail.documents    * POIDS["documents"]
        + detail.coherence    * POIDS["coherence"]
        + detail.verbatim     * POIDS["verbatim"]
    )


# ─────────────────────────────────────────────────────────────────────────────
# ÉVALUATION DES CRITÈRES
# ─────────────────────────────────────────────────────────────────────────────

def _evaluer_retentissement(donnees: dict) -> int:
    """30% — Limitations fonctionnelles concrètes documentées."""
    score = 0
    impact = str(donnees.get("impact_quotidien", "") or "").lower()
    restrictions = str(donnees.get("restrictions_emploi", "") or "").lower()
    texte_b = str(donnees.get("texte_b_vie_quotidienne", "") or "").lower()
    all_text = f"{impact} {restrictions} {texte_b}"

    # ── Longueur (jusqu'à 25 pts) — inclut texte_b généré ────────────────────
    chars_base = len(impact) + len(restrictions)
    chars_b    = len(texte_b)
    score += min(12, chars_base // 15)         # impact_quotidien + restrictions
    score += min(13, chars_b // 200)           # texte_b narratif LLM

    # ── Patterns limitations physiques ────────────────────────────────────────
    patterns_physiques = [
        (r"ne peut (pas|plus)\b|impossible", 7, "impossibilité concrète"),
        (r"\d+\s*(fois|heures?|minutes?|m[eè]tres?|nuits?|semaines?)", 6, "mesure quantifiée"),
        (r"le matin|le soir|chaque jour|tous les jours|chaque semaine", 5, "temporalité"),
        (r"aide.{0,20}(toilette|manger|marcher|habiller|cuisiner|douche)", 7, "aide humaine"),
        (r"fauteuil|canne|d[eé]ambulateur|orth[eè]se|proth[eè]se", 5, "aide technique"),
        (r"(avant|depuis).{0,20}(l.accident|la maladie|le diagnostic)", 5, "rupture temporelle"),
        (r"fatigue|[eé]puis|douleur.{0,10}(quand|si|pour|d[eè]s)", 4, "variabilité"),
    ]

    # ── Patterns limitations fonctionnelles cognitives / comportementales ─────
    # (TSA, psychique, DI, TDAH, enfant)
    patterns_cognitifs = [
        (r"crise|effondrement|melt.?down", 7, "crise documentée"),
        (r"routine.{0,20}(indispensable|perturbée|changement)", 5, "rigidité routines"),
        (r"s.isole|isolement|retrait|ne sort plus", 5, "isolement social"),
        (r"impossible.{0,20}(classe|école|travail|concentration)", 6, "impact scolaire/pro"),
        (r"(bons?|mauvais?).{0,10}jours?|[eé]pisode.{0,20}(dépressif|maniaque)", 6, "variabilité épisodes"),
        (r"hypersensib|saturation sensorielle|bruit.{0,15}(insupportable|difficile)", 5, "sensoriel"),
        (r"gestion administrative.{0,20}impossible|courrier.{0,20}(n.?ouvre|impossible)", 5, "admin impossible"),
        (r"hospitalisation|hospitalis[eé].{0,10}\d+", 6, "hospitalisations documentées"),
    ]

    for pattern, pts, _ in patterns_physiques + patterns_cognitifs:
        if re.search(pattern, all_text, re.IGNORECASE):
            score += pts

    return min(100, score)


def _evaluer_narratif_b(donnees: dict) -> int:
    """20% — Qualité du texte libre vie quotidienne (P8)."""
    texte = str(donnees.get("texte_b_vie_quotidienne", "") or "").lower()
    if not texte: return 0
    score = 0

    # Longueur
    if len(texte) > 1000: score += 30
    elif len(texte) > 500: score += 20
    elif len(texte) > 200: score += 10
    else: score += 5

    # Richesse sémantique
    richesse = [
        (r"quotidien|journée|jour", 8),
        (r"limitation|impossible|ne peut pas|difficile", 10),
        (r"aide|aidant|accompagnement|soutien", 8),
        (r"\d.{0,5}(ans?|mois|semaines?)", 6),   # durée
        (r"diagnostic|pathologie|traitement|m[eé]dicament", 5),
        (r"(matin|soir|nuit|heure).{0,30}(difficile|impossible|aide)", 8),
        (r"vie sociale|famille|entourage|isolement", 6),
        (r"exempt|concret|par exemple|comme", 5),  # exemples
    ]
    for pattern, pts in richesse:
        if re.search(pattern, texte, re.IGNORECASE):
            score += pts

    # Marqueurs de qualité rédactionnelle
    if "il est possible que" not in texte and "probablement" not in texte:
        score += 5  # pas de marqueurs de supposition

    return min(100, score)


def _evaluer_narratif_dc(donnees: dict, profil_mdph: str) -> int:
    """15% — Qualité du texte emploi (D) ou scolarité (C)."""
    if profil_mdph == "enfant":
        texte = str(donnees.get("texte_c_scolarite", "") or "").lower()
        champ = "scolarité"
    else:
        texte = str(donnees.get("texte_d_situation_pro", "") or "").lower()
        champ = "emploi"

    if not texte: return 0
    score = 0

    if len(texte) > 500: score += 30
    elif len(texte) > 200: score += 20
    elif len(texte) > 50: score += 10

    if champ == "emploi":
        richesse = [
            (r"travail|emploi|poste|m[eé]tier", 10),
            (r"arr[eê]t|inaptitude|licenci|sans emploi", 10),
            (r"am[eé]nagement|adaptation|restriction", 8),
            (r"avant.{0,20}(travaillais|avais un emploi|CDI|CDD)", 8),
            (r"ne peut plus.{0,20}(travailler|exercer|reprendre)", 8),
        ]
    else:  # scolarité
        richesse = [
            (r"[eé]cole|classe|scolarit[eé]", 10),
            (r"AESH|tiers.temps|am[eé]nagement|adapt[eé]", 10),
            (r"difficult[eé]s?|retard|r[eé]ussite|[eé]chec", 8),
            (r"apprentissage|lecture|[eé]criture|calcul|math", 6),
        ]

    for pattern, pts in richesse:
        if re.search(pattern, texte, re.IGNORECASE):
            score += pts

    return min(100, score)


def _evaluer_projet_vie(donnees: dict) -> int:
    """10% — Qualité du texte projet de vie (section E)."""
    texte = str(donnees.get("texte_e_projet_vie", "") or "").lower()
    if not texte: return 0
    score = 0

    if len(texte) > 500: score += 30
    elif len(texte) > 200: score += 20
    elif len(texte) > 50: score += 10

    richesse = [
        (r"souhait|voudrait?|aimerait?|objectif|projet", 15),
        (r"(SESSAD|SAVS|ESAT|emploi accompagn[eé]|PCH|RQTH)", 15),
        (r"vie.{0,15}(quotidienne|sociale|familiale|professionnelle)", 10),
        (r"am[eé]liorer|maintenir|conserver|progresser", 10),
        (r"stabilit[eé]|ind[eé]pendance|autonomie", 10),
    ]
    for pattern, pts in richesse:
        if re.search(pattern, texte, re.IGNORECASE):
            score += pts

    return min(100, score)


def _evaluer_documents(donnees: dict) -> int:
    """10% — Richesse documentaire (notes_pro, _document_knowledge)."""
    score = 0
    notes = str(donnees.get("notes_pro", "") or "")
    dk = donnees.get("_document_knowledge") or {}

    if notes and len(notes) > 100: score += 30
    elif notes and len(notes) > 30: score += 15

    if isinstance(dk, dict):
        cats = ["limitations", "restrictions", "besoins", "verbatim", "chronologie", "projets"]
        for cat in cats:
            items = dk.get(cat, [])
            if isinstance(items, list) and items:
                score += 10

    # Documents joints
    if donnees.get("documents_texte"):
        score += 20

    return min(100, score)


def _evaluer_coherence(donnees: dict, profil_mdph: str) -> int:
    """10% — Cohérence inter-sections."""
    score = 50  # baseline
    droits = str(donnees.get("droits_demandes", "") or "").upper()
    impact = str(donnees.get("impact_quotidien", "") or "").lower()
    statut = str(donnees.get("statut_emploi", "") or "").lower()
    texte_b = str(donnees.get("texte_b_vie_quotidienne", "") or "").lower()

    # Cohérence droits ↔ profil
    if profil_mdph == "enfant" and "AEEH" not in droits:
        score -= 15  # Enfant sans AEEH = incohérent
    if profil_mdph == "adulte" and "AEEH" in droits:
        score -= 20  # Adulte avec AEEH = incohérent
    if profil_mdph in ("adulte",) and "RQTH" not in droits and "AAH" not in droits and droits:
        score -= 10  # Adulte sans aucun droit emploi/vie

    # Cohérence impact ↔ droits
    if "PCH" in droits and impact and "aide" not in impact and texte_b and "aide" not in texte_b:
        score -= 10  # PCH demandée sans mention d'aide

    # Cohérence positive
    if texte_b and len(texte_b) > 200 and droits:
        score += 15  # Texte B + droits = cohérence bonne
    if donnees.get("diagnostics") and impact:
        score += 10  # Diagnostics + impact = chaîne causale

    return max(0, min(100, score))


def _evaluer_verbatim(donnees: dict) -> int:
    """5% — Présence de l'expression directe de la personne."""
    score = 0

    # Verbatim WhatsApp
    for c in ["_verbatim_b", "_verbatim_c", "_verbatim_d", "_verbatim_e"]:
        lst = donnees.get(c) or []
        if isinstance(lst, list) and lst:
            score += 20

    # Expression directe
    expr = str(donnees.get("expression_directe", "") or "")
    if expr and len(expr) > 30: score += 30

    # Guillemets dans les textes narratifs (citations)
    for c in ["texte_b_vie_quotidienne", "texte_e_projet_vie"]:
        texte = str(donnees.get(c, "") or "")
        if "«" in texte or '"' in texte or "'" in texte:
            score += 15
            break

    # Document knowledge verbatim
    dk = donnees.get("_document_knowledge") or {}
    if isinstance(dk, dict) and dk.get("verbatim"):
        score += 20

    return min(100, score)


# ─────────────────────────────────────────────────────────────────────────────
# SCORES PAR DROIT
# Les droits ont des critères plus ou moins importants selon leur nature
# ─────────────────────────────────────────────────────────────────────────────

# Poids spécifiques par droit (remplace les poids globaux pour certains critères)
_POIDS_DROITS: dict[str, dict[str, float]] = {
    "AAH":     {"retentissement": 0.30, "narratif_b": 0.20, "narratif_dc": 0.20, "projet_vie": 0.05, "documents": 0.10, "coherence": 0.10, "verbatim": 0.05},
    "PCH":     {"retentissement": 0.40, "narratif_b": 0.25, "narratif_dc": 0.05, "projet_vie": 0.05, "documents": 0.10, "coherence": 0.10, "verbatim": 0.05},
    "RQTH":    {"retentissement": 0.20, "narratif_b": 0.15, "narratif_dc": 0.30, "projet_vie": 0.10, "documents": 0.10, "coherence": 0.10, "verbatim": 0.05},
    "AEEH":    {"retentissement": 0.25, "narratif_b": 0.20, "narratif_dc": 0.25, "projet_vie": 0.05, "documents": 0.10, "coherence": 0.10, "verbatim": 0.05},
    "CMI":     {"retentissement": 0.40, "narratif_b": 0.25, "narratif_dc": 0.10, "projet_vie": 0.05, "documents": 0.10, "coherence": 0.05, "verbatim": 0.05},
    "SESSAD":  {"retentissement": 0.20, "narratif_b": 0.15, "narratif_dc": 0.30, "projet_vie": 0.15, "documents": 0.10, "coherence": 0.05, "verbatim": 0.05},
    "ESAT":    {"retentissement": 0.20, "narratif_b": 0.15, "narratif_dc": 0.30, "projet_vie": 0.20, "documents": 0.05, "coherence": 0.05, "verbatim": 0.05},
    "DEFAULT": POIDS,
}


def _score_pour_droit(droit: str, detail: DetailScores) -> int:
    poids = _POIDS_DROITS.get(droit, _POIDS_DROITS["DEFAULT"])
    return round(
        detail.retentissement * poids.get("retentissement", 0.30)
        + detail.narratif_b   * poids.get("narratif_b", 0.20)
        + detail.narratif_dc  * poids.get("narratif_dc", 0.15)
        + detail.projet_vie   * poids.get("projet_vie", 0.10)
        + detail.documents    * poids.get("documents", 0.10)
        + detail.coherence    * poids.get("coherence", 0.10)
        + detail.verbatim     * poids.get("verbatim", 0.05)
    )


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────────────────────

def noter_robustesse(
    donnees: dict[str, Any],
    profil_mdph: str = "adulte",
    droits_a_noter: list[str] | None = None,
) -> RobustesseDossier:
    """
    Note la robustesse du dossier sur 100, global et par droit.

    Args:
        donnees: synthese_json du dossier
        profil_mdph: "adulte" | "enfant" | "protege" | "mixte"
        droits_a_noter: liste de droits à noter (défaut = droits demandés + principaux)

    Returns:
        RobustesseDossier avec scores et axes d'amélioration
    """
    # 1. Évaluation des 7 critères
    detail = DetailScores(
        retentissement = _evaluer_retentissement(donnees),
        narratif_b     = _evaluer_narratif_b(donnees),
        narratif_dc    = _evaluer_narratif_dc(donnees, profil_mdph),
        projet_vie     = _evaluer_projet_vie(donnees),
        documents      = _evaluer_documents(donnees),
        coherence      = _evaluer_coherence(donnees, profil_mdph),
        verbatim       = _evaluer_verbatim(donnees),
    )

    score_global = _score_global(detail)

    # 2. Droits à noter
    droits_demandes_raw = str(donnees.get("droits_demandes", "") or "").upper()
    droits_candidats = droits_a_noter or []
    if not droits_candidats:
        # Droits les plus fréquents selon profil
        if profil_mdph == "enfant":
            droits_candidats = ["AEEH", "SESSAD", "IME", "EEAP", "PCH", "CMI"]
        else:
            droits_candidats = ["AAH", "PCH", "RQTH", "CMI", "SAVS", "ESAT", "ESPO"]
        # Ajouter les droits demandés
        for tok in ["AAH", "PCH", "RQTH", "CMI", "AEEH", "SESSAD", "ESAT", "ESPO", "EA"]:
            if tok in droits_demandes_raw and tok not in droits_candidats:
                droits_candidats.append(tok)

    scores_par_droit = {d: _score_pour_droit(d, detail) for d in droits_candidats}

    # 3. Points forts
    points_forts = []
    if detail.narratif_b >= 70:
        points_forts.append(f"Texte B (vie quotidienne) bien documenté ({detail.narratif_b}/100) — impact positif sur l'évaluation")
    if detail.retentissement >= 70:
        points_forts.append(f"Retentissement fonctionnel bien décrit ({detail.retentissement}/100) — limitations concrètes")
    if detail.documents >= 70:
        points_forts.append(f"Richesse documentaire satisfaisante ({detail.documents}/100)")
    if detail.verbatim >= 60:
        points_forts.append("Expressions directes de la personne présentes — rend le dossier plus personnel et convaincant")
    if detail.coherence >= 70:
        points_forts.append("Cohérence entre les sections du dossier")
    if not points_forts:
        points_forts.append("Dossier existant — base disponible pour amélioration")

    # 4. Points faibles
    points_faibles = []
    if detail.narratif_b < 40:
        points_faibles.append(f"Texte B insuffisant ({detail.narratif_b}/100) — l'évaluateur MDPH ne peut pas objectiver les besoins")
    if detail.retentissement < 40:
        points_faibles.append(f"Limitations fonctionnelles peu documentées ({detail.retentissement}/100) — risque de sous-évaluation des droits")
    if detail.narratif_dc < 30:
        label_dc = "scolarité (C)" if profil_mdph == "enfant" else "situation emploi (D)"
        points_faibles.append(f"Texte {label_dc} insuffisant ({detail.narratif_dc}/100)")
    if detail.projet_vie < 30:
        points_faibles.append(f"Projet de vie non documenté ({detail.projet_vie}/100) — section E manquante")
    if detail.documents < 30:
        points_faibles.append(f"Pas de documentation externe ({detail.documents}/100) — dossier repose uniquement sur les déclarations")
    if detail.coherence < 40:
        points_faibles.append(f"Incohérences potentielles entre sections ({detail.coherence}/100)")

    # 5. Axes d'amélioration
    axes = []
    if detail.retentissement < 60:
        axes.append(
            "PRIORITÉ 1 — Enrichir la description des limitations : nommer les actes impossibles, "
            "quantifier (nombre de fois/semaine, durée, distance), donner des exemples du quotidien"
        )
    if detail.narratif_b < 60:
        axes.append(
            "PRIORITÉ 2 — Compléter le texte B : décrire une journée type avec les moments difficiles, "
            "nommer qui aide et pour quoi, inclure des citations directes"
        )
    if detail.documents < 40:
        axes.append(
            "Documents — Joindre : certificat médical récent, bilans spécialisés, "
            "comptes-rendus de soins, GEVASCO pour enfant, fiche médecin du travail"
        )
    if detail.narratif_dc < 40:
        label = "Texte C (scolarité)" if profil_mdph == "enfant" else "Texte D (emploi)"
        axes.append(f"{label} — Compléter avec parcours détaillé et impact du handicap")
    if detail.projet_vie < 40:
        axes.append("Texte E (projet de vie) — Exprimer les attentes concrètes : droits souhaités, services adaptés, objectifs à 1-3 ans")
    if detail.verbatim < 30:
        axes.append("Verbatim — Inclure des citations directes de la personne accompagnée")

    if not axes:
        axes.append("Dossier solide — vérifier que tous les droits applicables sont cochés en page E")

    return RobustesseDossier(
        score_global=score_global,
        scores_par_droit=scores_par_droit,
        points_forts=points_forts,
        points_faibles=points_faibles,
        axes_amelioration=axes,
        detail_scores=detail,
    )
