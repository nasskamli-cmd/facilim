"""Profil QA — Parent aidant enfant TSA (AVPF)"""
from app.tests.qa.profiles import ProfilQA

PROFIL_PARENT_TSA = ProfilQA(
    id="AIDANT_PARENT_TSA",
    nom="Marie DURAND — Mère aidante Lucas TSA, AVPF",
    categorie="aidant",
    profil_mdph="enfant",  # dossier enfant avec aidant
    profil_handicap="tsa",
    frequence="frequent",

    donnees_entree={
        # Enfant
        "nom_prenom":             "DURAND Lucas",
        "date_naissance":         "20/09/2015",
        "genre":                  "garçon",
        "representant_legal_nom": "DURAND Marie",
        "representant_legal_lien":"mère",
        "diagnostics":            "TSA niveau 1, dyspraxie",
        "situation_scolaire":     "CM2 AESH 12h",
        "droits_demandes":        "AEEH SESSAD",
        # Aidant
        "aidant_nom":             "DURAND Marie",
        "aidant_besoins":         "réduction activité professionnelle, épuisement, liste attente SESSAD",
    },

    document_texte="",
    document_type="",

    # Pour ce profil : test de la détection AVPF aidant
    droits_attendus=["AEEH", "SESSAD", "AVPF"],
    droits_non_attendus=["AAH", "RQTH"],

    cases_cerfa_attendues={
        "Case à cocher P17 1": "/Yes",   # AEEH
        "Case à cocher P17 4": "/Yes",   # AVPF
    },

    sections_narratives={
        "E": "SESSAD",
    },

    justificatifs_attendus=["GEVASCO", "Bulletin paie parent (réduction activité)"],

    narratif_doit_declencher=True,
    boucle_interdite=True,
    score_maturite_min=55,
)
