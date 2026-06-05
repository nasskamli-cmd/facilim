"""Profil QA — Insertion pro RQTH + ESPO"""
from app.tests.qa.profiles import ProfilQA

PROFIL_RQTH_ESPO = ProfilQA(
    id="INSERTION_RQTH_ESPO",
    nom="Thomas Duval — RQTH + ESPO, TSA adulte 27 ans",
    categorie="adulte",
    profil_mdph="adulte",
    profil_handicap="tsa",
    frequence="frequent",

    donnees_entree={
        "nom_prenom":      "DUVAL Thomas",
        "date_naissance":  "18/09/1997",
        "genre":           "homme",
        "diagnostics":     "TSA niveau 1, diagnostiqué à 24 ans",
        "traitements":     "suivi psychiatrique mensuel",
        "impact_quotidien":"difficultés entretiens emploi, surcharge open space, pas de projet clair",
        "statut_emploi":   "sans emploi depuis 18 mois, licence mathématiques",
        "droits_demandes": "RQTH",
    },

    document_texte="""BILAN PCR — DUVAL Thomas
TSA niveau 1 diagnostiqué tardivement. Licence mathématiques (mention bien).
Échecs répétés entretiens : communication non-verbale différente, stress intense.
Essai cabinet comptable 2 semaines : open space insupportable.
Compétences réelles : analyse, concentration, rigueur.
Pas d'idée de secteur adapté. Bilan capacités nécessaire.
PROJET : ESPO recommandé pour définir projet adapté au profil.""",
    document_type="PCR",

    droits_attendus=["RQTH", "ESPO"],
    droits_non_attendus=["AAH", "ESAT", "MAS"],  # TSA 1 avec compétences ≠ ESAT

    cases_cerfa_attendues={
        "Case à cocher P17 6": "/Yes",   # RQTH
        "Case à cocher P18 1": "/Yes",   # RQTH emploi
        "Case à cocher P18 3": "/Yes",   # ESPO/CRP/UEROS
        "Case à cocher P16 5": "/Yes",   # bilan capacités
    },
    cases_cerfa_absentes=["Case à cocher P18 4"],  # ESAT ne doit PAS être coché

    sections_narratives={
        "D": "ESPO",
        "E": "mathématiques",
    },

    justificatifs_attendus=["Certificat médical psychiatrique"],

    incoherences_attendues=[],  # ESPO + "pas de projet" = cohérent

    narratif_doit_declencher=True,
    boucle_interdite=True,
    score_maturite_min=65,
)
