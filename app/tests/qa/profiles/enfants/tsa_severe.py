"""Profil QA — Enfant TSA niveau 3 avec DI, 7 ans"""
from app.tests.qa.profiles import ProfilQA

PROFIL_TSA_SEVERE = ProfilQA(
    id="ENFANT_TSA_SEVERE",
    nom="Emma Rossi — TSA niveau 3 + DI modérée, 7 ans",
    categorie="enfant",
    profil_mdph="enfant",
    profil_handicap="tsa",
    frequence="frequent",

    donnees_entree={
        "nom_prenom":             "ROSSI Emma",
        "date_naissance":         "15/03/2017",
        "genre":                  "fille",
        "representant_legal_nom": "ROSSI Paolo",
        "representant_legal_lien":"père",
        "diagnostics":            "TSA niveau 3, déficience intellectuelle modérée, épilepsie traitée",
        "traitements":            "Valproate, suivi neuropédiatrique, psychomotricité",
        "impact_quotidien":       "dépendance totale pour hygiène, alimentation, communication non verbale",
        "situation_scolaire":     "IME depuis 2024",
        "droits_demandes":        "AEEH IME",
    },

    document_texte="""COMPTE RENDU MÉDICAL — ROSSI Emma
TSA niveau 3 avec DI modérée. Communication : quelques mots + pictogrammes.
Dépendance totale pour les actes essentiels. Épilepsie contrôlée (Valproate).
Scolarisée en IME depuis septembre 2024.
Autonomie très limitée. Comportements d'automutilation lors des transitions.
PROJET : Maintien IME. PCH aide humaine indispensable à domicile (8h/jour minimum).
Parents épuisés — mère a arrêté de travailler.""",
    document_type="bilan",

    droits_attendus=["AEEH", "AEEH_COMPLEMENT", "IME", "PCH"],
    droits_non_attendus=["RQTH", "AAH", "ESPO"],

    cases_cerfa_attendues={
        "Case à cocher P17 1": "/Yes",   # AEEH
        "Case à cocher P 9 3": "/Yes",   # IME
    },
    cases_cerfa_absentes=["Case à cocher P17 5", "Case à cocher P17 6"],

    sections_narratives={
        "B": "dépendance",
        "C": "IME",
        "E": "maintien",
    },

    justificatifs_attendus=["Certificat médical", "Compte rendu neurologique", "Bilan psychomoteur"],

    narratif_doit_declencher=True,
    boucle_interdite=True,
    score_maturite_min=55,
)
