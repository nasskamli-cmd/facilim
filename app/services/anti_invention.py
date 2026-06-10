"""
app/services/anti_invention.py — Garde-fou anti-invention déterministe (partagé).

Doctrine du renforcement légitime : un texte produit par Facilim ne doit JAMAIS
introduire un acte ou une aide que la personne n'a pas déclaré. Une consigne au
modèle ne suffit pas (il déduit parfois une dépendance d'une simple fatigue). On
vérifie donc APRÈS génération : si un marqueur d'acte/aide apparaît dans le texte
mais dans AUCUNE source réellement déclarée, c'est une invention → on l'écarte.

Ce module factorise le garde-fou historique de `_composer_description_p8` (page 8)
pour le généraliser à toute génération de texte (sections narratives B/C/D/E…).
"""

from __future__ import annotations

from typing import Any

# Actes / équipements / personnes CONCRETS que le modèle invente parfois à partir
# d'une simple fatigue ou douleur. On NE liste PAS les tournures génériques de
# TRADUCTION (« aide pour », « besoin d'aide »…) : la doctrine AUTORISE la
# traduction (« je n'arrive plus à faire ma toilette seul » → « aide à la toilette »).
# Ne flaguer que ce qui, s'il apparaît, DEVAIT avoir été déclaré : un acte précis,
# un équipement nommé, un aidant. Sinon on blanchirait des rédactions légitimes.
ACTES_AIDES_MARQUEURS: tuple[str, ...] = (
    "toilette", "se laver", "se doucher", "douche",
    "s'habiller", "habiller", "habillage",
    "fauteuil roulant", "aidant",
)


def _collecter_valeurs(obj: Any) -> list[str]:
    """Collecte récursivement les VALEURS chaîne (jamais les clés) d'une structure."""
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        out: list[str] = []
        for v in obj.values():
            out += _collecter_valeurs(v)
        return out
    if isinstance(obj, (list, tuple)):
        out = []
        for v in obj:
            out += _collecter_valeurs(v)
        return out
    return []


def source_depuis_donnees(donnees: dict[str, Any]) -> str:
    """
    Construit la « source de vérité » à partir des VALEURS déclarées (sans les
    noms de champs, qui contamineraient le test : la clé `avq_toilette` contient
    « toilette »). Sert de référence au garde-fou.
    """
    return " ".join(_collecter_valeurs(donnees or {})).lower()


# 2e tier — CONCLUSIONS d'aide AMBIGUËS. Elles peuvent être une traduction légitime
# (« je n'arrive plus seul » → « aide humaine ») OU une sur-interprétation. On ne les
# REJETTE donc PAS (cela blanchirait des rédactions correctes) : on les SIGNALE au
# professionnel pour qu'il vérifie qu'elles sont bien étayées. (Avocat du diable doux.)
CONCLUSIONS_AIDE_AMBIGUES: tuple[str, ...] = (
    "aide humaine", "besoin d'aide", "dépendant", "incapable de", "ne peut pas se",
)


def detecter_inventions(texte: str, source: str,
                        marqueurs: tuple[str, ...] = ACTES_AIDES_MARQUEURS) -> list[str]:
    """Marqueurs d'acte/aide CONCRETS présents dans le texte mais ABSENTS de la source.
    Tier « rejet dur » : un acte concret absent de la source EST une invention."""
    t = (texte or "").lower()
    s = (source or "").lower()
    return [m for m in marqueurs if m in t and m not in s]


def conclusions_a_etayer(texte: str, source: str) -> list[str]:
    """Conclusions d'aide ambiguës présentes dans le texte mais absentes de la source.
    Tier « signalement doux » : ne pas rejeter, alerter le pro pour étayage."""
    t = (texte or "").lower()
    s = (source or "").lower()
    return [m for m in CONCLUSIONS_AIDE_AMBIGUES if m in t and m not in s]


def garde_anti_invention(texte: str, source: str, repli: str,
                         marqueurs: tuple[str, ...] = ACTES_AIDES_MARQUEURS) -> tuple[str, list[str]]:
    """
    Retourne (texte_validé, inventions). Si le texte introduit un acte/aide absent
    de la source, on renvoie `repli` (rendu sûr) au lieu du texte inventé — jamais
    on ne laisse partir une invention.
    """
    inventions = detecter_inventions(texte, source, marqueurs)
    if inventions:
        return repli, inventions
    return texte, []
