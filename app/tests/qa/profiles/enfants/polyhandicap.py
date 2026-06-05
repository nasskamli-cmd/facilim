"""Profil QA — Enfant polyhandicap, 5 ans"""
from app.tests.qa.profiles import ProfilQA

PROFIL_POLYHANDICAP = ProfilQA(
    id="ENFANT_POLYHANDICAP",
    nom="Hugo Martin — Polyhandicap, 5 ans",
    categorie="enfant",
    profil_mdph="enfant",
    profil_handicap="di",
    frequence="rare",

    donnees_entree={
        "nom_prenom":             "MARTIN Hugo",
        "date_naissance":         "22/01/2019",
        "genre":                  "garçon",
        "representant_legal_nom": "MARTIN Christine",
        "representant_legal_lien":"mère",
        "diagnostics":            "polyhandicap, paralysie cérébrale sévère, épilepsie réfractaire",
        "traitements":            "antiépileptiques, kinésithérapie, gastrostomie",
        "impact_quotidien":       "dépendance totale 24h/24, alimentation par sonde, mobilité nulle",
        "situation_scolaire":     "non scolarisé — liste attente EEAP",
        "droits_demandes":        "AEEH PCH",
    },

    document_texte="""BILAN MÉDICAL — MARTIN Hugo
Polyhandicap sévère. Pas de communication verbale. Mobilité absente.
Alimentation par gastrostomie. Epilepsie réfractaire (3-4 crises/jour).
Surveillance permanente indispensable — risque vital.
Parents n'ont pas dormi plus de 3h consécutives depuis 2 ans.
Liste attente EEAP : 18 mois minimum.""",
    document_type="bilan",

    droits_attendus=["AEEH", "AEEH_COMPLEMENT", "PCH", "PCPE"],
    droits_non_attendus=["RQTH", "AAH", "ESAT"],

    cases_cerfa_attendues={
        "Case à cocher P17 1": "/Yes",
        "Case à cocher P17 2": "/Yes",  # PCH
    },

    sections_narratives={
        "B": "dépendance",
        "E": "EEAP",
    },

    justificatifs_attendus=["Certificat médical spécialisé", "Attestation soins infirmiers"],

    narratif_doit_declencher=True,
    boucle_interdite=True,
    score_maturite_min=50,
)
