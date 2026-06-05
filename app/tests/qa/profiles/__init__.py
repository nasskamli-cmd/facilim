"""
Bibliothèque de profils de référence Facilim QA.

Chaque profil définit :
  - Données d'entrée (identité, situation, documents)
  - Outputs attendus (droits, narratifs, cases CERFA, justificatifs)
  - Assertions de validation

Usage :
    from app.tests.qa.profiles import ALL_PROFILES
    from app.tests.qa.profiles.enfants.tsa_leger import PROFIL_TSA_LEGER
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProfilQA:
    """Structure d'un profil de test de référence."""

    # Identifiant
    id:              str
    nom:             str
    categorie:       str   # "enfant" | "adulte" | "insertion_pro" | "protection" | "aidant"
    profil_mdph:     str   # "enfant" | "adulte" | "mixte" | "protege"
    profil_handicap: str   # "tsa" | "moteur" | "psychique" | etc.
    frequence:       str   # "tres_frequent" | "frequent" | "rare"

    # Données d'entrée
    donnees_entree:       dict[str, Any]  = field(default_factory=dict)
    document_texte:       str             = ""   # contenu du bilan/PCR simulé
    document_type:        str             = ""   # "PCR" | "bilan" | "ESRP" | etc.

    # Outputs attendus
    droits_attendus:      list[str]       = field(default_factory=list)   # ["AEEH", "SESSAD"]
    droits_non_attendus:  list[str]       = field(default_factory=list)   # droits qui ne doivent PAS être proposés
    questions_attendues:  list[str]       = field(default_factory=list)   # fragments de questions attendus
    cases_cerfa_attendues:dict[str, str]  = field(default_factory=dict)   # {champ_pdf: valeur_attendue}
    cases_cerfa_absentes: list[str]       = field(default_factory=list)   # cases qui ne doivent PAS être cochées
    sections_narratives:  dict[str, str]  = field(default_factory=dict)   # {"B": "fragment_attendu"}
    justificatifs_attendus:list[str]      = field(default_factory=list)
    incoherences_attendues:list[str]      = field(default_factory=list)   # incohérences à détecter

    # Méta-assertions
    narratif_doit_declencher: bool = True   # le moteur narratif doit s'activer
    boucle_interdite:         bool = True   # pas de boucle WhatsApp
    score_maturite_min:       int  = 50     # score minimum attendu


# Import de tous les profils
def _load_all_profiles() -> list[ProfilQA]:
    from app.tests.qa.profiles.enfants.tsa_leger        import PROFIL_TSA_LEGER
    from app.tests.qa.profiles.enfants.tsa_severe       import PROFIL_TSA_SEVERE
    from app.tests.qa.profiles.enfants.tdah             import PROFIL_TDAH
    from app.tests.qa.profiles.enfants.polyhandicap     import PROFIL_POLYHANDICAP
    from app.tests.qa.profiles.adultes.accident_travail import PROFIL_ACCIDENT_TRAVAIL
    from app.tests.qa.profiles.adultes.moteur_sep       import PROFIL_MOTEUR_SEP
    from app.tests.qa.profiles.adultes.psychique_bipo   import PROFIL_PSYCHIQUE_BIPOLAIRE
    from app.tests.qa.profiles.adultes.schizophrenie    import PROFIL_SCHIZOPHRENIE
    from app.tests.qa.profiles.adultes.maladie_chronique import PROFIL_MALADIE_CHRONIQUE
    from app.tests.qa.profiles.insertion_pro.rqth_espo  import PROFIL_RQTH_ESPO
    from app.tests.qa.profiles.insertion_pro.esat_di    import PROFIL_ESAT_DI
    from app.tests.qa.profiles.protection_juridique.tutelle import PROFIL_TUTELLE
    from app.tests.qa.profiles.protection_juridique.habilitation import PROFIL_HABILITATION
    from app.tests.qa.profiles.aidants.parent_tsa       import PROFIL_PARENT_TSA

    return [
        PROFIL_TSA_LEGER, PROFIL_TSA_SEVERE, PROFIL_TDAH, PROFIL_POLYHANDICAP,
        PROFIL_ACCIDENT_TRAVAIL, PROFIL_MOTEUR_SEP, PROFIL_PSYCHIQUE_BIPOLAIRE,
        PROFIL_SCHIZOPHRENIE, PROFIL_MALADIE_CHRONIQUE,
        PROFIL_RQTH_ESPO, PROFIL_ESAT_DI,
        PROFIL_TUTELLE, PROFIL_HABILITATION,
        PROFIL_PARENT_TSA,
    ]

ALL_PROFILES: list[ProfilQA] = _load_all_profiles()
