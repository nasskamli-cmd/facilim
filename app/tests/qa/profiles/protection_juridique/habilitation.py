"""Profil QA — Habilitation familiale (alternative tutelle)"""
from app.tests.qa.profiles import ProfilQA

PROFIL_HABILITATION = ProfilQA(
    id="PROTECTION_HABILITATION",
    nom="Marc Rousseau — Habilitation familiale, DI légère, 28 ans",
    categorie="adulte",
    profil_mdph="protege",
    profil_handicap="di",
    frequence="rare",

    donnees_entree={
        "nom_prenom":             "ROUSSEAU Marc",
        "date_naissance":         "15/11/1996",
        "genre":                  "homme",
        "representant_legal_nom": "ROUSSEAU Anne",
        "type_protection":        "habilitation familiale",
        "jugement_tribunal":      "TJ Lyon 2023 — habilitation familiale étendue",
        "diagnostics":            "déficience intellectuelle légère",
        "impact_quotidien":       "vie en logement accompagné, SAVS, activités ESAT",
        "statut_emploi":          "ESAT",
        "droits_demandes":        "AAH",
    },

    document_texte="",
    document_type="",

    droits_attendus=["AAH", "ESAT", "SAVS"],
    droits_non_attendus=["RQTH", "ESPO"],

    cases_cerfa_attendues={
        "Case à cocher P17 5": "/Yes",
    },

    sections_narratives={
        "B": "autonomie",
        "E": "accompagnement",
    },

    justificatifs_attendus=["Jugement habilitation familiale"],

    # Test : habilitation familiale doit être proposée avant tutelle
    incoherences_attendues=[],

    narratif_doit_declencher=True,
    boucle_interdite=True,
    score_maturite_min=60,
)
