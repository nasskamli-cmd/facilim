"""Profil QA — Adulte SEP progressive (Marie Leclerc)"""
from app.tests.qa.profiles import ProfilQA

PROFIL_MOTEUR_SEP = ProfilQA(
    id="ADULTE_MOTEUR_SEP",
    nom="Marie Leclerc — SEP progressive, 44 ans",
    categorie="adulte",
    profil_mdph="adulte",
    profil_handicap="moteur",
    frequence="tres_frequent",

    donnees_entree={
        "nom_prenom":      "LECLERC Marie",
        "date_naissance":  "15/03/1980",
        "genre":           "femme",
        "diagnostics":     "sclérose en plaques progressive secondaire, diagnostiquée 2017",
        "traitements":     "Ocrevus perfusion 6 mois, kinésithérapie 3x/sem",
        "impact_quotidien":"ne peut plus marcher longtemps, aide humaine quotidienne, mari à mi-temps",
        "statut_emploi":   "arrêt longue durée 18 mois, ancienne infirmière",
        "droits_demandes": "PCH CMI RQTH",
        "notes_pro": """Marie Leclerc, 44 ans, SEP progressive secondaire.
Depuis 2021 : ne peut plus marcher plus de 100m, aide pour toilette et habillage matin.
Son mari a réduit son travail à mi-temps. Conduite arrêtée (troubles équilibre).
Ne peut pas reprendre son métier d'infirmière. Projet de reconversion non défini.""",
    },

    document_texte="",  # Test sans document — données via interface
    document_type="",

    droits_attendus=["PCH", "CMI", "RQTH"],
    droits_non_attendus=["AEEH", "IME", "ESAT"],

    cases_cerfa_attendues={
        "Case à cocher P17 7": "/Yes",   # PCH adulte
        "Case à cocher P17 6": "/Yes",   # RQTH
        "Case à cocher P17 3": "/Yes",   # CMI
        "Case à cocher P17 13": "/Yes",  # CMI stationnement
    },

    sections_narratives={
        "B": "marcher",
        "D": "infirmière",
        "E": "reconversion",
    },

    justificatifs_attendus=[
        "Bilan ergothérapie",
        "Attestation neurologue",
        "Fiche inaptitude médecin travail",
    ],

    narratif_doit_declencher=True,
    boucle_interdite=True,
    score_maturite_min=70,
)
