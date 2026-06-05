"""Profil QA — Enfant TSA niveau 1 (Lucas Durand)"""
from app.tests.qa.profiles import ProfilQA

PROFIL_TSA_LEGER = ProfilQA(
    id="ENFANT_TSA_LEGER",
    nom="Lucas Durand — TSA niveau 1, 9 ans",
    categorie="enfant",
    profil_mdph="enfant",
    profil_handicap="tsa",
    frequence="tres_frequent",

    donnees_entree={
        "nom_prenom":             "DURAND Lucas",
        "date_naissance":         "20/09/2015",
        "genre":                  "garçon",
        "representant_legal_nom": "DURAND Marie",
        "representant_legal_lien":"mère",
        "diagnostics":            "TSA niveau 1, dyspraxie associée",
        "traitements":            "suivi orthophonie 2x/semaine, psychomotricité",
        "impact_quotidien":       "difficultés importantes à l'école et à la maison",
        "situation_scolaire":     "CM2, classe ordinaire avec AESH 12h",
        "etablissement_scolaire": "École Jules Ferry Marseille",
        "droits_demandes":        "AEEH SESSAD",
    },

    document_texte="""BILAN NEUROPSYCHOLOGIQUE — DURAND Lucas — Né le 20/09/2015
DIAGNOSTIC : Trouble du spectre autistique niveau 1 + dyspraxie développementale.
VIE SCOLAIRE : CM2, AESH 12h. Isolement récréations, jeux collectifs impossibles.
Il s'isole, refuse les changements de routine, écriture laborieuse, surcharges sensorielles.
EXPRESSION PARENT : « À la maison c'est l'explosion après l'école. »
FREINS : Hypersensibilité sensorielle (bruit, cantine). Rigidité aux transitions.
RESSOURCES : Bonne mémoire visuelle. Motivation si consignes claires.
PROJET : SESSAD TSA recommandé. Maintien milieu ordinaire avec AESH renforcée.
CHRONOLOGIE : Signalements dès 4 ans. Diagnostic posé en 2021.""",
    document_type="bilan",

    droits_attendus=["AEEH", "SESSAD", "AESH"],
    droits_non_attendus=["AAH", "RQTH", "ESAT", "PCH"],

    questions_attendues=[
        "difficultés",
        "l'école",
        "depuis quand",
    ],

    cases_cerfa_attendues={
        "Case à cocher P17 1": "/Yes",   # AEEH
        "Case à cocher P 9 1": "/Yes",   # scolarisation ordinaire
        "Champ de texte P9 1": "Jules Ferry",
    },
    cases_cerfa_absentes=["Case à cocher P17 5", "Case à cocher P18 1"],  # AAH, RQTH

    sections_narratives={
        "B": "s'isole",      # texte B doit mentionner isolement
        "C": "AESH",         # texte C doit mentionner AESH
        "E": "SESSAD",       # texte E doit mentionner SESSAD
    },

    justificatifs_attendus=["GEVASCO", "Bilan neuropsychologique récent"],

    narratif_doit_declencher=True,
    boucle_interdite=True,
    score_maturite_min=60,
)
