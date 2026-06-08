"""
app/services/faits.py — Couche de FAITS CANONIQUES (FACILIM V2, ADDITIVE).

Objectif : porter, à l'intérieur de synthese_json, une représentation de faits
tracés (valeur + source + extrait + statut) SANS supprimer les clés plates.

PRINCIPES NON NÉGOCIABLES :
  - ADDITIF      : n'efface JAMAIS une clé plate. N'écrit que synthese["faits"].
  - DÉTERMINISTE : aucune IA, aucun appel réseau. Pure projection/normalisation
                   des clés déjà produites par l'extraction EXISTANTE.
  - IDEMPOTENT   : upsert par identité stable (domaine.champ) — jamais de doublon.
  - SANS STORE   : opère sur le dict synthese_json déjà persisté ailleurs.

La source fiable, pour les domaines migrés, devient synthese["faits"].
Les consommateurs lisent les faits S'ILS EXISTENT, sinon fallback dict plat
(aucune régression sur les dossiers anciens).

Format d'un fait :
  {
    "id": "domaine.champ", "domaine": "...", "champ": "...", "valeur": "...",
    "source": "document|whatsapp|professionnel", "extrait": "...",
    "statut": "PROUVE|DECLARE|INFERE",
    "created_at": "...", "updated_at": "..."
  }
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SOURCES_VALIDES = {"document", "whatsapp", "professionnel"}
STATUTS_VALIDES = {"PROUVE", "DECLARE", "INFERE"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fait_id(domaine: str, champ: str) -> str:
    """Identité STABLE d'un fait = domaine.champ → garantit l'idempotence."""
    return f"{domaine}.{champ}"


def make_fait(
    domaine: str,
    champ: str,
    valeur: Any,
    source: str,
    extrait: str = "",
    statut: str = "DECLARE",
    *,
    now: str | None = None,
) -> dict:
    """Construit un fait canonique normalisé (valeurs invalides ramenées à un défaut sûr)."""
    horodatage = now or _now_iso()
    return {
        "id":         fait_id(domaine, champ),
        "domaine":    domaine,
        "champ":      champ,
        "valeur":     valeur,
        "source":     source if source in SOURCES_VALIDES else "professionnel",
        "extrait":    extrait or "",
        "statut":     statut if statut in STATUTS_VALIDES else "DECLARE",
        "created_at": horodatage,
        "updated_at": horodatage,
    }


def get_faits(synthese: dict) -> list[dict]:
    """Liste des faits (toujours une liste, jamais None)."""
    f = synthese.get("faits") if isinstance(synthese, dict) else None
    return f if isinstance(f, list) else []


def faits_domaine(synthese: dict, domaine: str) -> list[dict]:
    """Faits d'un domaine donné."""
    return [
        f for f in get_faits(synthese)
        if isinstance(f, dict) and f.get("domaine") == domaine
    ]


def upsert_fait(synthese: dict, fait: dict) -> dict:
    """
    Ajoute un fait nouveau, ou met à jour le fait existant de même id (domaine.champ).

    - ADDITIF    : ne touche à AUCUNE clé plate. Crée synthese["faits"] si absent.
    - IDEMPOTENT : pas de doublon (clé d'unicité = id).
    - Conserve created_at d'origine ; met à jour updated_at, valeur, source, extrait, statut.
    Retourne le dict synthese muté (et renvoyé pour chaînage).
    """
    if not isinstance(synthese, dict) or not isinstance(fait, dict):
        return synthese

    if not fait.get("id"):
        fait["id"] = fait_id(fait.get("domaine", ""), fait.get("champ", ""))

    faits = synthese.get("faits")
    if not isinstance(faits, list):
        faits = []
        synthese["faits"] = faits

    for i, existant in enumerate(faits):
        if isinstance(existant, dict) and existant.get("id") == fait["id"]:
            fusion = dict(existant)
            fusion["valeur"]     = fait.get("valeur", existant.get("valeur"))
            fusion["source"]     = fait.get("source", existant.get("source"))
            fusion["extrait"]    = fait.get("extrait") or existant.get("extrait", "")
            fusion["statut"]     = fait.get("statut", existant.get("statut"))
            fusion["created_at"] = existant.get("created_at", fait.get("created_at"))
            fusion["updated_at"] = fait.get("updated_at") or _now_iso()
            faits[i] = fusion
            return synthese

    faits.append(fait)
    return synthese


# ─────────────────────────────────────────────────────────────────────────────
# DOMAINE PILOTE — projet_professionnel
# Projection DÉTERMINISTE des clés plates EXISTANTES (produites par l'extraction
# LLM déjà en place) vers des faits canoniques. AUCUNE nouvelle extraction/IA.
# ─────────────────────────────────────────────────────────────────────────────

DOMAINE_PROJET_PRO = "projet_professionnel"

# (clé plate source produite par l'extraction → champ canonique du fait)
_MAP_PROJET_PRO: list[tuple[str, str]] = [
    ("projet_professionnel",    "projet_professionnel"),
    ("formation_actuelle",      "formation_cible"),
    ("etablissement_formation", "etablissement_cible"),
    ("projet_orientation",      "orientation_souhaitee"),
]


def derive_faits_projet_professionnel(
    synthese: dict,
    *,
    source: str = "whatsapp",
    extrait: str = "",
    now: str | None = None,
) -> dict:
    """
    Projette les clés plates du domaine projet_professionnel en faits canoniques.

    - Ne lit que des clés DÉJÀ présentes (produites par l'extraction existante).
    - N'efface aucune clé plate.
    - Idempotent (upsert par domaine.champ).
    Un projet est par nature déclaratif → statut DECLARE.
    """
    if not isinstance(synthese, dict):
        return synthese

    for cle_plate, champ in _MAP_PROJET_PRO:
        val = synthese.get(cle_plate)
        if isinstance(val, str):
            val = val.strip()
        if not val:
            continue
        upsert_fait(
            synthese,
            make_fait(
                domaine=DOMAINE_PROJET_PRO,
                champ=champ,
                valeur=val,
                source=source,
                extrait=extrait,
                statut="DECLARE",
                now=now,
            ),
        )
    return synthese
