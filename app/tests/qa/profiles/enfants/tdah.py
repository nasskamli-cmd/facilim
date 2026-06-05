"""Profil QA — Enfant TDAH + DYS, 11 ans"""
from app.tests.qa.profiles import ProfilQA

PROFIL_TDAH = ProfilQA(
    id="ENFANT_TDAH_DYS",
    nom="Camille Petit — TDAH + DYS, 11 ans",
    categorie="enfant",
    profil_mdph="enfant",
    profil_handicap="di",  # TND classé ici
    frequence="tres_frequent",

    donnees_entree={
        "nom_prenom":             "PETIT Camille",
        "date_naissance":         "14/05/2013",
        "genre":                  "fille",
        "representant_legal_nom": "PETIT François",
        "representant_legal_lien":"père",
        "diagnostics":            "TDAH combiné sévère, dyslexie sévère, dysorthographie",
        "traitements":            "Ritaline, orthophonie 2x/semaine",
        "impact_quotidien":       "difficultés importantes en classe, devoirs problématiques",
        "situation_scolaire":     "6ème, tiers-temps accordé",
        "droits_demandes":        "AEEH aménagements",
    },

    document_texte="""BILAN ORTHOPHONIQUE — PETIT Camille
TDAH + dyslexie sévère + dysorthographie. Lecture très lente, erreurs massives.
Tiers-temps accordé. AESH non encore mise en place.
Écriture difficile — tablette recommandée.
L'enfant pleure chaque soir sur ses devoirs. Confiance en soi effondrée.
PROJET : AESH individuelle + matériel adapté. Tiers-temps confirmé.
GEVASCO à renouveler.""",
    document_type="bilan",

    droits_attendus=["AEEH", "AESH"],
    droits_non_attendus=["AAH", "ESAT", "SESSAD", "IME"],

    cases_cerfa_attendues={
        "Case à cocher P17 1": "/Yes",
        "Case à cocher P 10 2": "/Yes",  # aménagements temps
        "Case à cocher P 10 3": "/Yes",  # matériel adapté
    },

    sections_narratives={
        "B": "difficultés",
        "C": "tiers-temps",
    },

    justificatifs_attendus=["GEVASCO", "Bilan orthophonique", "Bilan psychologique"],

    narratif_doit_declencher=True,
    boucle_interdite=True,
    score_maturite_min=55,
)
