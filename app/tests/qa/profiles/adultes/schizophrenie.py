"""Profil QA — Adulte schizophrénie stabilisée, ESAT"""
from app.tests.qa.profiles import ProfilQA

PROFIL_SCHIZOPHRENIE = ProfilQA(
    id="ADULTE_SCHIZOPHRENIE_ESAT",
    nom="Patrick Bernard — Schizophrénie, ESAT, 44 ans",
    categorie="adulte",
    profil_mdph="adulte",
    profil_handicap="psychique",
    frequence="frequent",

    donnees_entree={
        "nom_prenom":      "BERNARD Patrick",
        "date_naissance":  "08/06/1980",
        "genre":           "homme",
        "diagnostics":     "schizophrénie paranoïde stabilisée sous traitement",
        "traitements":     "Rispéridone, Clozapine, suivi CMP bimensuel",
        "impact_quotidien":"vie en appartement partagé, gestion argent impossible, ESAT 5 ans",
        "statut_emploi":   "ESAT depuis 5 ans, mi-temps",
        "droits_demandes": "AAH renouvellement",
    },

    document_texte="""RAPPORT ACCOMPAGNEMENT SOCIAL — BERNARD Patrick
Schizophrénie stabilisée. ESAT depuis 5 ans, apprécié de l'équipe.
Ne peut pas gérer argent seul — a donné somme importante à inconnu.
Dernier renouvellement AAH il y a 3 ans. Curatelle renforcée 2019.
PROJET : maintien ESAT. Pas de projet milieu ordinaire actuellement.""",
    document_type="bilan",

    droits_attendus=["AAH", "ESAT"],
    droits_non_attendus=["RQTH", "AEEH", "ESPO"],  # RQTH inadapté ESAT, ESPO pas pertinent

    cases_cerfa_attendues={
        "Case à cocher P17 5": "/Yes",   # AAH
        "Case à cocher P17 11": "/Yes",  # ESAT/ESMS
        "Case à cocher P18 4": "/Yes",   # ESAT
    },

    sections_narratives={
        "B": "argent",
        "D": "ESAT",
        "E": "maintien",
    },

    justificatifs_attendus=["Attestation ESAT", "Certificat psychiatrique", "Jugement curatelle"],

    incoherences_attendues=[],

    narratif_doit_declencher=True,
    boucle_interdite=True,
    score_maturite_min=60,
)
