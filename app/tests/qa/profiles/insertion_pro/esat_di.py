"""Profil QA — Insertion pro ESAT + DI adulte"""
from app.tests.qa.profiles import ProfilQA

PROFIL_ESAT_DI = ProfilQA(
    id="INSERTION_ESAT_DI",
    nom="Lucas Bernard — DI modérée, ESAT, 31 ans",
    categorie="adulte",
    profil_mdph="adulte",
    profil_handicap="di",
    frequence="frequent",

    donnees_entree={
        "nom_prenom":      "BERNARD Lucas",
        "date_naissance":  "03/03/1993",
        "genre":           "homme",
        "diagnostics":     "déficience intellectuelle modérée, trisomie 21",
        "traitements":     "suivi médical annuel",
        "impact_quotidien":"autonomie partielle, ESAT depuis 5 ans, tutelle",
        "statut_emploi":   "ESAT depuis 5 ans",
        "droits_demandes": "AAH renouvellement ESAT",
        "type_protection": "tutelle",
        "jugement_tribunal":"Tribunal Marseille 2020",
    },

    document_texte="",
    document_type="",

    droits_attendus=["AAH", "ESAT"],
    droits_non_attendus=["ESPO", "RQTH", "AEEH"],  # DI modérée adulte ≠ ces droits

    cases_cerfa_attendues={
        "Case à cocher P17 5": "/Yes",   # AAH
        "Case à cocher P17 11": "/Yes",  # ESMS
        "Case à cocher P18 4": "/Yes",   # ESAT
        "REPRESENTANT LEGAL 1": "tutelle",
    },

    sections_narratives={
        "B": "autonomie",
        "D": "ESAT",
    },

    justificatifs_attendus=["Attestation ESAT", "Jugement tutelle"],

    # Test cohérence : ESAT + projet sortie milieu ordinaire → emploi accompagné possible
    incoherences_attendues=[],

    narratif_doit_declencher=True,
    boucle_interdite=True,
    score_maturite_min=60,
)
