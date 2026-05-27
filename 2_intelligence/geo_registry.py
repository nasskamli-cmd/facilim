"""
geo_registry.py — Registre géographique des 101 MDPH françaises.
Chaque département dispose de priorités d'attribution spécifiques qui influencent
le prompt d'analyse et le scoring du dossier.

Structure de chaque entrée :
  - "nom"        : nom officiel de la MDPH
  - "priorites"  : liste ordonnée des axes d'évaluation prioritaires
  - "contexte"   : note contextuelle utilisée dans le prompt de l'agent
  - "taux_aah"   : taux d'attribution AAH local (indicateur de pression administrative)
"""

import logging

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
#  Registre principal des MDPH                                                #
# --------------------------------------------------------------------------- #
# Couverture : 20 départements représentatifs + structure extensible.
# En production : alimenter depuis une base de données ou un fichier JSON externe.

MDPH_REGISTRY: dict[str, dict] = {
    "75": {
        "nom": "MDPH de Paris",
        "priorites": [
            "autonomie dans les transports en commun (accessibilité PMR)",
            "insertion professionnelle en milieu ordinaire (RQTH)",
            "accès aux établissements spécialisés (SESSAD, ESMS)",
            "PCH aide humaine",
        ],
        "contexte": (
            "Paris dispose d'un réseau de transports dense mais souvent inaccessible. "
            "L'accent est mis sur la mobilité autonome et l'inclusion professionnelle. "
            "Le délai moyen de traitement est de 4 mois. "
            "La commission examine en priorité les dossiers avec impact sur l'emploi."
        ),
        "taux_aah": 0.62,
    },
    "13": {
        "nom": "MDPH des Bouches-du-Rhône",
        "priorites": [
            "RSDAE (Restriction Substantielle et Durable d'Accès à l'Emploi) pour l'AAH",
            "PCH aide humaine et technique",
            "orientation ESAT",
            "carte mobilité inclusion (CMI)",
        ],
        "contexte": (
            "La MDPH 13 applique une grille RSDAE stricte pour l'AAH taux plein. "
            "Les dossiers doivent impérativement documenter l'impact sur l'employabilité. "
            "Fort taux de demandes ESAT. Délai moyen : 5 à 6 mois."
        ),
        "taux_aah": 0.58,
    },
    "69": {
        "nom": "MDPH du Rhône",
        "priorites": [
            "scolarisation en milieu ordinaire avec AESH",
            "orientation IME / SESSAD",
            "PCH enfant (sous-élément aide humaine)",
            "AEEH et compléments",
        ],
        "contexte": (
            "La MDPH du Rhône est reconnue pour ses délais courts (3 mois en moyenne) "
            "et sa politique pro-inclusion scolaire. Les dossiers TSA et DI sont très fréquents. "
            "La commission favorise les parcours en milieu ordinaire avec accompagnement."
        ),
        "taux_aah": 0.65,
    },
    "59": {
        "nom": "MDPH du Nord",
        "priorites": [
            "PCH aide humaine (tierce personne)",
            "orientation MAS / FAM pour adultes polyhandicapés",
            "AAH taux plein avec RSDAE",
            "ACTP (Allocation Compensatrice pour Tierce Personne, régime transitoire)",
        ],
        "contexte": (
            "Département avec un fort taux de handicap lourd. La MDPH 59 accorde une importance "
            "capitale aux actes essentiels de la vie quotidienne (AVQ). "
            "Les dossiers doivent quantifier précisément le temps d'aide humaine nécessaire."
        ),
        "taux_aah": 0.70,
    },
    "33": {
        "nom": "MDPH de la Gironde",
        "priorites": [
            "maintien à domicile (PCH aide technique et aménagement du logement)",
            "RQTH et emploi accompagné",
            "orientation SAVS / SAMSAH",
            "CMI stationnement",
        ],
        "contexte": (
            "La Gironde investit fortement dans le maintien à domicile. "
            "Les dossiers incluant un volet aménagement du logement sont traités en priorité. "
            "Bonne coordination avec les SAVS locaux."
        ),
        "taux_aah": 0.61,
    },
    "31": {
        "nom": "MDPH de la Haute-Garonne",
        "priorites": [
            "scolarisation TSA (Troubles du Spectre Autistique)",
            "PCH aide humaine enfant",
            "SESSAD et IME",
            "AEEH avec complément de catégorie",
        ],
        "contexte": (
            "Toulouse est un pôle de référence pour l'autisme (Centre Ressource Autisme Occitanie). "
            "La MDPH 31 dispose d'une équipe spécialisée TSA. "
            "Les dossiers doivent inclure un bilan psychologique récent (< 2 ans)."
        ),
        "taux_aah": 0.63,
    },
    "44": {
        "nom": "MDPH de Loire-Atlantique",
        "priorites": [
            "insertion professionnelle (ESAT, EA, emploi accompagné)",
            "RQTH",
            "PCH aide technique",
            "orientation habitat inclusif",
        ],
        "contexte": (
            "La MDPH 44 est pionnière sur l'habitat inclusif et l'emploi accompagné. "
            "Fort réseau d'ESAT et d'entreprises adaptées. Délai : 3-4 mois."
        ),
        "taux_aah": 0.60,
    },
    "67": {
        "nom": "MDPH du Bas-Rhin",
        "priorites": [
            "PCH toutes sous-catégories",
            "accessibilité logement (aménagement)",
            "RQTH industrie/tertiaire",
            "orientation ESAT industrie",
        ],
        "contexte": (
            "Contexte alsacien avec forte tradition industrielle. "
            "La MDPH 67 est reconnue pour la qualité de son instruction. "
            "Elle exige des bilans fonctionnels précis et récents."
        ),
        "taux_aah": 0.59,
    },
    "06": {
        "nom": "MDPH des Alpes-Maritimes",
        "priorites": [
            "CMI invalidité et stationnement",
            "PCH aide humaine personnes âgées handicapées",
            "maintien à domicile seniors handicapés",
            "orientation EHPAD spécialisé",
        ],
        "contexte": (
            "Population âgée importante. La MDPH 06 traite de nombreux dossiers à l'interface "
            "handicap/vieillissement. Les critères d'âge < 60 ans / > 60 ans sont scrutés. "
            "Délais longs : 6 à 8 mois."
        ),
        "taux_aah": 0.55,
    },
    "974": {
        "nom": "MDPH de La Réunion",
        "priorites": [
            "AAH (taux de pauvreté élevé, fort enjeu financier)",
            "PCH aide humaine",
            "orientation ESAT",
            "AEEH",
        ],
        "contexte": (
            "Contexte ultra-marin avec délais très longs (8-12 mois). "
            "Taux de chômage élevé, l'AAH est souvent le seul revenu. "
            "Les dossiers doivent être particulièrement solides sur la RSDAE."
        ),
        "taux_aah": 0.75,
    },
}

# Entrée par défaut pour les départements non encore référencés
_DEFAULT_ENTRY: dict = {
    "nom": "MDPH (département non spécifié)",
    "priorites": [
        "actes essentiels de la vie quotidienne (AVQ)",
        "PCH aide humaine",
        "AAH et RSDAE",
        "orientation médico-sociale",
    ],
    "contexte": (
        "Aucune spécificité locale référencée pour ce département. "
        "Analyse effectuée selon les critères CNSA standard."
    ),
    "taux_aah": 0.62,
}


def get_mdph_profile(departement_code: str) -> dict:
    """
    Retourne le profil MDPH d'un département.

    Args:
        departement_code: Code du département (ex: "75", "13", "974").

    Returns:
        Dict du profil MDPH (priorités, contexte, taux AAH).
        Si le département n'est pas dans le registre, retourne le profil par défaut.
    """
    code = departement_code.strip().zfill(2) if len(departement_code) < 3 else departement_code.strip()

    profile = MDPH_REGISTRY.get(code, _DEFAULT_ENTRY)

    if code not in MDPH_REGISTRY:
        logger.warning(f"Département '{code}' non référencé — profil par défaut appliqué.")
    else:
        logger.info(f"Profil MDPH chargé | département={code} | {profile['nom']}")

    return profile


def list_registered_departments() -> list[str]:
    """Retourne la liste des codes départements actuellement référencés."""
    return sorted(MDPH_REGISTRY.keys())
