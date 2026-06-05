"""Profil QA — Adulte maladie chronique (fibromyalgie + fatigue chronique)"""
from app.tests.qa.profiles import ProfilQA

PROFIL_MALADIE_CHRONIQUE = ProfilQA(
    id="ADULTE_MALADIE_CHRONIQUE",
    nom="Isabelle Moreau — Fibromyalgie + SFC, 47 ans",
    categorie="adulte",
    profil_mdph="adulte",
    profil_handicap="maladie_chronique",
    frequence="frequent",

    donnees_entree={
        "nom_prenom":      "MOREAU Isabelle",
        "date_naissance":  "30/04/1977",
        "genre":           "femme",
        "diagnostics":     "fibromyalgie sévère, syndrome de fatigue chronique",
        "traitements":     "antalgiques, duloxétine, kinésithérapie mensuelle",
        "impact_quotidien":"fatigue intense variable, mauvaises journées fréquentes, travail impossible",
        "statut_emploi":   "arrêt longue durée 2 ans, assistante de direction",
        "droits_demandes": "RQTH",
    },

    document_texte="",
    document_type="",

    droits_attendus=["RQTH", "AAH", "CMI"],
    droits_non_attendus=["ESAT", "IME", "MAS"],

    cases_cerfa_attendues={
        "Case à cocher P17 6": "/Yes",   # RQTH
        "Case à cocher P17 5": "/Yes",   # AAH
    },

    sections_narratives={
        "B": "fatigue",
        "D": "arrêt",
    },

    justificatifs_attendus=["Certificat rhumatologue", "Attestation arrêt travail prolongé"],

    narratif_doit_declencher=True,
    boucle_interdite=True,
    score_maturite_min=60,
)
