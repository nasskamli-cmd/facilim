"""Profil QA — Adulte trouble bipolaire"""
from app.tests.qa.profiles import ProfilQA

PROFIL_PSYCHIQUE_BIPOLAIRE = ProfilQA(
    id="ADULTE_PSYCHIQUE_BIPOLAIRE",
    nom="Sophie Bernard — Trouble bipolaire type 1, 38 ans",
    categorie="adulte",
    profil_mdph="adulte",
    profil_handicap="psychique",
    frequence="frequent",

    donnees_entree={
        "nom_prenom":      "BERNARD Sophie",
        "date_naissance":  "22/07/1986",
        "genre":           "femme",
        "diagnostics":     "trouble bipolaire type 1, épisodes maniaques et dépressifs",
        "traitements":     "Lithium + antipsychotique, suivi psychiatrique mensuel",
        "impact_quotidien":"alternance jours stables et mauvaises périodes, emploi précaire",
        "statut_emploi":   "CDD courts, nombreux arrêts, licenciée pour inaptitude il y a 6 mois",
        "droits_demandes": "RQTH AAH",
    },

    document_texte="",
    document_type="",

    droits_attendus=["RQTH", "AAH", "SAVS"],
    droits_non_attendus=["AEEH", "ESAT", "MAS", "IME"],

    cases_cerfa_attendues={
        "Case à cocher P17 5": "/Yes",   # AAH
        "Case à cocher P17 6": "/Yes",   # RQTH
        "Case à cocher P18 1": "/Yes",   # RQTH emploi
    },

    sections_narratives={
        "B": "jours",         # B doit mentionner variabilité
        "D": "emploi",
        "E": "stabilité",
    },

    justificatifs_attendus=["Certificat psychiatrique", "Lettre licenciement inaptitude"],

    narratif_doit_declencher=True,
    boucle_interdite=True,
    score_maturite_min=60,
)
