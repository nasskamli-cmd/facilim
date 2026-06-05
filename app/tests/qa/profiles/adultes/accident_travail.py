"""Profil QA — Adulte accident du travail (Karim NAIT ALI — dossier réel)"""
from app.tests.qa.profiles import ProfilQA

PROFIL_ACCIDENT_TRAVAIL = ProfilQA(
    id="ADULTE_ACCIDENT_TRAVAIL",
    nom="Karim NAIT ALI — AT 2019, séquelles physiques et psychologiques",
    categorie="adulte",
    profil_mdph="adulte",
    profil_handicap="moteur",
    frequence="tres_frequent",

    donnees_entree={
        "nom_prenom":      "NAIT ALI Karim",
        "date_naissance":  "05/12/1969",
        "genre":           "homme",
        "adresse_complete":"1 rue des Bateliers 13016 Marseille",
        "num_secu":        "169122613484366",
        "telephone":       "0642087770",
        "departement":     "13",
        "diagnostics":     "anxiété, troubles du sommeil, douleurs chroniques",
        "traitements":     "médicaments pour l'anxiété, le sommeil et les douleurs",
        "impact_quotidien":"accident de travail 2019, ne peut plus rester debout, marche limitée",
        "statut_emploi":   "sans emploi depuis 2019, ancien CDI Port Autonome",
        "droits_demandes": "RQTH AAH ESPO",
    },

    document_texte="""BILAN PRESTATION CONSEIL ET REPERAGE — NAIT ALI Karim
Accident du travail 2019 (chute). 6 ans de séquelles.
EXPRESSION : « Avant j'avais un CDI. Depuis l'accident je suis bloqué, j'ai peur
de retourner travailler. Je ne dors pas la nuit. »
SANTÉ : Fatigabilité importante. Reviviscences traumatiques.
RESTRICTIONS : pas port charges, pas flexion tronc, pas accroupi, pas milieu bruyant.
NIVEAU FRANÇAIS : A1.1 (lecteur non scripteur).
PROJET : pas de projet défini. Orientation ESPO recommandée.
RESSOURCES : motivation, sérieux, ponctualité observées.""",
    document_type="PCR",

    droits_attendus=["RQTH", "AAH", "ESPO"],
    droits_non_attendus=["AEEH", "SESSAD", "IME", "MAS"],

    questions_attendues=["depuis quand", "travail", "limitations"],

    cases_cerfa_attendues={
        "Case à cocher P17 5": "/Yes",   # AAH
        "Case à cocher P17 6": "/Yes",   # RQTH
        "Case à cocher P18 1": "/Yes",   # RQTH emploi
        "Case à cocher P18 3": "/Yes",   # ESPO/CRP/UEROS
        "Champ de texte P8 1": "accident",  # section B doit mentionner AT
    },
    cases_cerfa_absentes=["Case à cocher P17 1"],  # AEEH ne doit pas être coché

    sections_narratives={
        "B": "accident",
        "D": "ESPO",
        "E": "retourner travailler",
    },

    justificatifs_attendus=[
        "Fiche aptitude/inaptitude médecin du travail",
        "Attestation AT (déclaration accident)",
        "Certificat médical récent",
    ],

    incoherences_attendues=[],

    narratif_doit_declencher=True,
    boucle_interdite=True,
    score_maturite_min=65,
)
