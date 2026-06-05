"""Profil QA — Majeur protégé sous tutelle"""
from app.tests.qa.profiles import ProfilQA

PROFIL_TUTELLE = ProfilQA(
    id="PROTECTION_TUTELLE",
    nom="Patrick Bernard — Tutelle, DI légère, 31 ans",
    categorie="adulte",
    profil_mdph="protege",
    profil_handicap="di",
    frequence="frequent",

    donnees_entree={
        "nom_prenom":             "BERNARD Patrick",
        "date_naissance":         "08/06/1993",
        "genre":                  "homme",
        "representant_legal_nom": "GIRARD Isabelle",
        "type_protection":        "tutelle",
        "jugement_tribunal":      "Tribunal Judiciaire Marseille, jugement 2020",
        "diagnostics":            "déficience intellectuelle légère, épilepsie contrôlée",
        "traitements":            "antiépileptiques, suivi psychiatrique",
        "impact_quotidien":       "autonomie réduite, gestion argent impossible, ESAT 5 ans",
        "statut_emploi":          "ESAT Provence depuis 2019",
        "droits_demandes":        "AAH renouvellement PCH",
    },

    document_texte="",
    document_type="",

    droits_attendus=["AAH", "ESAT"],
    droits_non_attendus=["RQTH", "AEEH", "ESPO"],

    cases_cerfa_attendues={
        "Case à cocher P17 5": "/Yes",
        "REPRESENTANT LEGAL 1": "tutelle",
        "REPRESENTANT LEGAL 3": "GIRARD",
    },
    cases_cerfa_absentes=["Case à cocher P17 6"],  # RQTH pas adapté tutelle ESAT

    sections_narratives={
        "B": "autonomie",
        "D": "ESAT",
        "E": "maintien",
    },

    justificatifs_attendus=["Jugement tutelle en cours de validité", "Attestation ESAT"],

    narratif_doit_declencher=True,
    boucle_interdite=True,
    score_maturite_min=65,
)
