"""
app/services/structure_search_service.py — Recherche de structures médico-sociales.

Règle « Question 60 » (Agent Métier) :
  Lorsqu'un type d'établissement (IME, ESAT, ESRP, UEROS, SESSAD, ITEP, CRP…)
  est évoqué dans la conversation, l'IA effectue une recherche des structures
  adaptées aux alentours de l'adresse de l'usager et envoie les suggestions
  directement par WhatsApp.

Backends supportés (priorité décroissante) :
  1. Google Places API (si GOOGLE_PLACES_API_KEY configurée)
  2. API Annuaire Santé FINESS (https://api.lannuaire.service-public.fr) — gratuit
  3. Dataset FINESS local (./storage/finess_medico_social.json) — embarqué
  4. Réponse de substitution explicite (toujours non-vide)
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("facilim.services.structure_search")

# ── Mots-clés déclencheurs → types de structure FINESS ───────────────────────
_TRIGGER_MAP: dict[str, list[str]] = {
    "IME":    ["Institut Médico-Éducatif"],
    "ESAT":   ["Établissement et Service d'Aide par le Travail"],
    "ESRP":   ["Établissement de Réadaptation Professionnelle"],
    "SESSAD": ["Service d'Éducation Spéciale et de Soins À Domicile"],
    "ITEP":   ["Institut Thérapeutique Éducatif et Pédagogique"],
    "UEROS":  ["Unité d'Évaluation de Réentraînement et d'Orientation Sociale"],
    "CRP":    ["Centre de Rééducation Professionnelle"],
    "ULIS":   ["Unité Localisée pour l'Inclusion Scolaire"],
    "SAVS":   ["Service d'Accompagnement à la Vie Sociale"],
    "SAMSAH": ["Service d'Accompagnement Médico-Social pour Adultes Handicapés"],
    "MAS":    ["Maison d'Accueil Spécialisée"],
    "FAM":    ["Foyer d'Accueil Médicalisé"],
    "FOYER":  ["Foyer de vie", "Foyer occupationnel"],
    "CAMSP":  ["Centre d'Action Médico-Sociale Précoce"],
    "CMPP":   ["Centre Médico-Psycho-Pédagogique"],
}

# Regex compilée : détecte tous les mots-clés (insensible à la casse)
_TRIGGER_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _TRIGGER_MAP) + r")\b",
    re.IGNORECASE,
)


@dataclass
class StructureTrouvee:
    nom:         str
    type_etab:   str
    adresse:     str
    telephone:   str = ""
    distance_km: float | None = None
    url:         str = ""


@dataclass
class ResultatRecherche:
    structures:     list[StructureTrouvee] = field(default_factory=list)
    type_recherche: str = ""
    adresse_ref:    str = ""
    source:         str = "substitution"


# ── Détection de déclencheur ──────────────────────────────────────────────────

def detecter_mention_etablissement(texte: str) -> list[str]:
    """
    Retourne la liste des types d'établissements mentionnés dans le texte.
    Exemples : "je voudrais un ESAT" → ["ESAT"]
               "entre IME et SESSAD"  → ["IME", "SESSAD"]
    """
    matches = _TRIGGER_PATTERN.findall(texte)
    return list({m.upper() for m in matches})


# ── Point d'entrée principal ──────────────────────────────────────────────────

def rechercher_structures(
    types_etablissement: list[str],
    adresse_usager: str | None,
    departement_code: str | None = None,
    rayon_km: int = 30,
    max_resultats: int = 3,
    google_api_key: str | None = None,
) -> ResultatRecherche:
    """
    Recherche les structures médico-sociales adaptées à proximité de l'adresse.

    Cascade de backends :
      Google Places → FINESS API → dataset local → substitution
    """
    adresse_ref = adresse_usager or (f"département {departement_code}" if departement_code else "France")
    type_principal = types_etablissement[0] if types_etablissement else "structure médico-sociale"

    # Backend 1 : Google Places
    if google_api_key:
        try:
            result = _recherche_google_places(
                types_etablissement, adresse_ref, rayon_km, max_resultats, google_api_key
            )
            if result.structures:
                return result
        except Exception as e:
            logger.warning(f"[STRUCT] Google Places échoué : {e}")

    # Backend 2 : FINESS API publique
    try:
        result = _recherche_finess_api(types_etablissement, departement_code, max_resultats)
        if result.structures:
            return result
    except Exception as e:
        logger.warning(f"[STRUCT] FINESS API échoué : {e}")

    # Backend 3 : Dataset FINESS local
    try:
        result = _recherche_dataset_local(types_etablissement, departement_code, max_resultats)
        if result.structures:
            return result
    except Exception as e:
        logger.warning(f"[STRUCT] Dataset local échoué : {e}")

    # Backend 4 : Substitution explicite (toujours non-vide)
    return _substitution(type_principal, adresse_ref, departement_code)


# ── Formateur WhatsApp ─────────────────────────────────────────────────────────

def formater_suggestions_whatsapp(
    resultat: ResultatRecherche,
    types_etablissement: list[str],
    prenom_usager: str | None = None,
) -> str:
    """
    Formate le résultat de recherche en message WhatsApp lisible (FALC).
    """
    type_label = " / ".join(
        _TRIGGER_MAP.get(t, [t])[0] for t in types_etablissement[:2]
    )
    intro_prenom = f"Pour vous, " if not prenom_usager else f"Pour {prenom_usager}, "

    if not resultat.structures:
        return (
            f"Je n'ai pas trouvé de {type_label} à proximité dans notre base.\n"
            "Je vous conseille de contacter directement votre MDPH pour obtenir la liste "
            "des établissements de votre secteur. — L'équipe Facilim"
        )

    lignes = [
        f"📍 {intro_prenom}voici des {type_label} proches de chez vous :\n"
    ]
    for i, s in enumerate(resultat.structures, 1):
        dist = f" (~{s.distance_km:.0f} km)" if s.distance_km else ""
        tel  = f"\n   📞 {s.telephone}" if s.telephone else ""
        lignes.append(f"{i}. *{s.nom}*{dist}\n   {s.adresse}{tel}")

    lignes.append(
        "\nCes informations proviennent du répertoire national FINESS. "
        "Voulez-vous que je prépare une demande d'orientation vers l'un de ces établissements ?"
    )

    return "\n".join(lignes)


# ── Backend 1 : Google Places ─────────────────────────────────────────────────

def _recherche_google_places(
    types_etab: list[str],
    adresse: str,
    rayon_km: int,
    max_resultats: int,
    api_key: str,
) -> ResultatRecherche:
    """Recherche via Google Places API (Nearby Search)."""
    try:
        import httpx
    except ImportError:
        raise RuntimeError("httpx non installé")

    query = " ".join(_TRIGGER_MAP.get(t, [t])[0] for t in types_etab[:2])
    geocode_url = (
        f"https://maps.googleapis.com/maps/api/geocode/json"
        f"?address={adresse}&key={api_key}"
    )
    geo_resp = httpx.get(geocode_url, timeout=5.0).json()
    results  = geo_resp.get("results", [])
    if not results:
        return ResultatRecherche()

    loc      = results[0]["geometry"]["location"]
    lat, lng = loc["lat"], loc["lng"]

    nearby_url = (
        f"https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        f"?location={lat},{lng}&radius={rayon_km * 1000}"
        f"&keyword={query}&language=fr&key={api_key}"
    )
    nearby_resp = httpx.get(nearby_url, timeout=5.0).json()
    places      = nearby_resp.get("results", [])[:max_resultats]

    structures = [
        StructureTrouvee(
            nom=p.get("name", "Établissement"),
            type_etab=query,
            adresse=p.get("vicinity", ""),
            source="google_places",
        )
        for p in places
    ]
    return ResultatRecherche(
        structures=structures,
        type_recherche=query,
        adresse_ref=adresse,
        source="google_places",
    )


# ── Backend 2 : API FINESS publique ──────────────────────────────────────────

def _recherche_finess_api(
    types_etab: list[str],
    departement_code: str | None,
    max_resultats: int,
) -> ResultatRecherche:
    """
    Recherche via l'API Annuaire FINESS (https://api.finess.esante.gouv.fr).
    Endpoint : GET /etablissement/getAll?numDep={dept}&categorie={cat}
    """
    try:
        import httpx
    except ImportError:
        raise RuntimeError("httpx non installé")

    if not departement_code:
        return ResultatRecherche()

    # Codes catégories FINESS pour les principaux types
    _FINESS_CATEGORIE: dict[str, str] = {
        "IME": "182", "ESAT": "249", "ESRP": "246", "SESSAD": "378",
        "ITEP": "183", "MAS": "255", "FAM": "256", "SAVS": "445",
        "SAMSAH": "446", "CAMSP": "186", "CMPP": "189",
    }

    structures = []
    for type_etab in types_etab[:2]:
        cat_code = _FINESS_CATEGORIE.get(type_etab)
        if not cat_code:
            continue

        url = (
            f"https://api.finess.esante.gouv.fr/api/establishment/getAll"
            f"?numDep={departement_code}&categorie={cat_code}&limit={max_resultats}"
        )
        try:
            resp = httpx.get(url, timeout=8.0, headers={"Accept": "application/json"})
            if resp.status_code != 200:
                continue
            data = resp.json()
            etabs = data if isinstance(data, list) else data.get("etablissements", [])
            for e in etabs[:max_resultats]:
                structures.append(StructureTrouvee(
                    nom=e.get("raisonSocialeLongue") or e.get("raisonSociale", "Établissement"),
                    type_etab=type_etab,
                    adresse=f"{e.get('adresseAcheminement', '')} {e.get('libCommune', '')}".strip(),
                    telephone=e.get("telephone", ""),
                ))
        except Exception as e:
            logger.debug(f"[STRUCT/FINESS] {type_etab} : {e}")

    if not structures:
        return ResultatRecherche()

    return ResultatRecherche(
        structures=structures[:max_resultats],
        type_recherche=" / ".join(types_etab),
        adresse_ref=f"département {departement_code}",
        source="finess_api",
    )


# ── Backend 3 : Dataset FINESS local ─────────────────────────────────────────

def _recherche_dataset_local(
    types_etab: list[str],
    departement_code: str | None,
    max_resultats: int,
) -> ResultatRecherche:
    """
    Recherche dans un fichier JSON local (pré-extrait du dataset FINESS public).
    Format attendu : liste de {"nom", "type", "adresse", "telephone", "departement"}
    """
    dataset_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "storage", "finess_medico_social.json"
    )
    if not os.path.isfile(dataset_path):
        return ResultatRecherche()

    with open(dataset_path, encoding="utf-8") as f:
        dataset: list[dict] = json.load(f)

    type_upper = {t.upper() for t in types_etab}
    structures = [
        StructureTrouvee(
            nom=e["nom"],
            type_etab=e.get("type", ""),
            adresse=e.get("adresse", ""),
            telephone=e.get("telephone", ""),
        )
        for e in dataset
        if e.get("type", "").upper() in type_upper
        and (not departement_code or e.get("departement") == departement_code)
    ][:max_resultats]

    if not structures:
        return ResultatRecherche()

    return ResultatRecherche(
        structures=structures,
        type_recherche=" / ".join(types_etab),
        adresse_ref=f"département {departement_code}",
        source="dataset_local",
    )


# ── Backend 4 : Substitution ──────────────────────────────────────────────────

def _substitution(
    type_principal: str,
    adresse_ref: str,
    departement_code: str | None,
) -> ResultatRecherche:
    """
    Réponse de substitution quand aucune API n'est disponible.
    Oriente l'usager vers les ressources MDPH officielles.
    """
    label = _TRIGGER_MAP.get(type_principal.upper(), [type_principal])[0]
    dept  = f" (département {departement_code})" if departement_code else ""

    structures = [
        StructureTrouvee(
            nom=f"Votre MDPH locale{dept}",
            type_etab="MDPH",
            adresse="À retrouver sur https://www.mdph.fr",
            telephone="",
            url="https://www.mdph.fr",
        ),
        StructureTrouvee(
            nom=f"Annuaire FINESS — {label}",
            type_etab=type_principal,
            adresse="https://finess.sante.gouv.fr",
            telephone="",
            url="https://finess.sante.gouv.fr",
        ),
    ]
    return ResultatRecherche(
        structures=structures,
        type_recherche=label,
        adresse_ref=adresse_ref,
        source="substitution",
    )
