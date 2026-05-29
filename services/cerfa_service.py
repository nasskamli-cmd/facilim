"""
services/cerfa_service.py — Orchestration : validation → relance WhatsApp ou génération PDF.

Pipeline :
  1. CERFAValidator vérifie que les données collectées sont complètes et cohérentes.
  2a. Si invalide → relance_questions génère UNE question WhatsApp (principe FALC).
  2b. Si valide   → cerfa_filler génère le PDF du CERFA 15692 et le retourne.

Retour de traiter_dossier_cerfa() :
    Cas invalide (validation) :
        {
            "valide":              False,
            "type":                "validation",
            "erreurs":             list[str],
            "warnings":            list[str],
            "donnees":             dict,
            "message_a_envoyer":   str,   # UNE question WhatsApp — envoyer tel quel
            "questions_restantes": list[str],  # questions suivantes (tours suivants)
        }

    Cas valide (succès) :
        {
            "valide":     True,
            "type":       "succes",
            "pdf_bytes":  bytes,   # PDF généré, prêt à envoyer par email
            "warnings":   list[str],
            "donnees":    dict,
        }

    Cas erreur technique (bug inattendu) :
        {
            "valide":  False,
            "type":    "technique",
            "erreur":  str,   # message générique (pas de stack trace exposé)
            "donnees": dict,
        }
"""

from __future__ import annotations

import logging
from typing import Any

from validators.cerfa_validator import CERFAValidator
from services.relance_questions import obtenir_questions_depuis_erreurs
from services.cerfa_filler import remplir_cerfa

logger = logging.getLogger(__name__)


def traiter_dossier_cerfa(donnees_collectees: dict[str, Any]) -> dict[str, Any]:
    """
    Valide les données collectées et génère le PDF CERFA ou une question de relance.

    Args:
        donnees_collectees: dictionnaire des données collectées via WhatsApp
                            ou saisies par l'éducateur. Structure attendue :
                            les champs de CERFA_FIELD_ORDER de conversation_agent.py.

    Returns:
        Dictionnaire avec au minimum les clés "valide" et "type".
        Voir le docstring du module pour la structure complète selon les cas.

    Raises:
        Aucune exception levée — les erreurs techniques sont capturées et retournées
        dans le dict avec "type": "technique".
    """
    donnees_collectees = donnees_collectees or {}

    # ── Étape 1 : validation ─────────────────────────────────────────────────
    try:
        validation = CERFAValidator(donnees_collectees).valider()
    except Exception as exc:
        logger.exception("[CERFA_SERVICE] Erreur inattendue dans CERFAValidator")
        return {
            "valide":  False,
            "type":    "technique",
            "erreur":  "Erreur interne lors de la validation du dossier.",
            "donnees": donnees_collectees,
        }

    # ── Étape 2a : dossier invalide → relance ────────────────────────────────
    if not validation["valide"]:
        logger.info(
            f"[CERFA_SERVICE] Dossier invalide : {len(validation['erreurs'])} erreur(s) — "
            f"relance en cours"
        )

        questions = obtenir_questions_depuis_erreurs(validation["erreurs"])

        # Une seule question envoyée (principe FALC — jamais de liste sur WhatsApp)
        message_a_envoyer = questions[0] if questions else (
            "Des informations importantes manquent dans votre dossier. "
            "Pouvez-vous nous décrire les principales difficultés rencontrées "
            "au quotidien par la personne ?"
        )

        return {
            "valide":              False,
            "type":                "validation",
            "erreurs":             validation["erreurs"],
            "warnings":            validation.get("warnings", []),
            "donnees":             donnees_collectees,
            "message_a_envoyer":   message_a_envoyer,
            "questions_restantes": questions[1:],   # pour les tours suivants
        }

    # ── Étape 2b : dossier valide → génération PDF ───────────────────────────
    logger.info("[CERFA_SERVICE] Dossier valide — génération du PDF CERFA.")

    try:
        pdf_bytes = remplir_cerfa(donnees_collectees)
    except Exception as exc:
        logger.exception("[CERFA_SERVICE] Erreur lors de la génération du PDF CERFA")
        return {
            "valide":  False,
            "type":    "technique",
            "erreur":  "Le dossier est complet mais une erreur est survenue lors de la génération du formulaire. Merci de réessayer.",
            "donnees": donnees_collectees,
        }

    return {
        "valide":    True,
        "type":      "succes",
        "pdf_bytes": pdf_bytes,
        "warnings":  validation.get("warnings", []),
        "donnees":   donnees_collectees,
    }


# ---------------------------------------------------------------------------
# Bloc de test rapide
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys, os
    # Ajoute la racine du projet au path pour les imports relatifs au projet
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import json

    print("=" * 60)
    print("TEST 1 — Dossier incomplet (champs manquants)")
    print("=" * 60)

    dossier_incomplet = {
        "nom_prenom":    "Karim NAIT ALI",
        "date_naissance": "05/12/1969",
        # Manquent : type_demande, genre, adresse_complete,
        #            situation_familiale, type_droits, difficultes_quotidiennes
    }

    resultat = traiter_dossier_cerfa(dossier_incomplet)
    print(f"valide  : {resultat['valide']}")
    print(f"type    : {resultat['type']}")
    print(f"erreurs : {resultat.get('erreurs', [])}")
    print(f"\nmessage_a_envoyer :\n  {resultat.get('message_a_envoyer', '')}")
    print(f"\nquestions_restantes ({len(resultat.get('questions_restantes', []))}) :")
    for i, q in enumerate(resultat.get("questions_restantes", [])[:3], 1):
        print(f"  {i}. {q[:80]}…")

    print()
    print("=" * 60)
    print("TEST 2 — Dossier complet (tous les champs obligatoires)")
    print("=" * 60)

    dossier_complet = {
        "dossier_id":             "TEST-SVC-001",
        "nom_enfant":             "NAIT ALI",
        "prenom_enfant":          "Karim",
        "ddn_enfant":             "05/12/1969",
        "adresse_enfant":         "1 rue des Bateliers",
        "cp_enfant":              "13016",
        "commune_enfant":         "MARSEILLE",
        "telephone_famille":      "0642087770",
        "email_famille":          "test@test.com",
        "departement_code":       "13",
        # Données collectées via WhatsApp
        "type_demande":           "renouvellement",
        "nom_prenom":             "Karim NAIT ALI",
        "date_naissance":         "05/12/1969",
        "genre":                  "homme",
        "adresse_complete":       "1 rue des Bateliers, 13016 Marseille",
        "situation_familiale":    "marié",
        "type_droits":            "RQTH, AAH",
        "difficultes_quotidiennes": (
            "Douleurs chroniques suite à un accident du travail en 2019. "
            "Difficultés à rester debout plus de 20 minutes, station debout douloureuse. "
            "Fatigabilité importante, nécessite des pauses fréquentes."
        ),
        "besoins_aide":           "Aménagement du poste de travail, aide aux déplacements",
        "organisme_payeur":       "CAF",
        "protection_juridique":   "aucune",
        # Analyse LLM (structure attendue par cerfa_filler)
        "cerfa_reponses":         {},
        "analyse": {
            "droits_identifies":  ["RQTH", "AAH"],
            "elements_probants":  ["AT 2019"],
            "synthese_agents":    {
                "geva_pro":   "Accident du travail 2019, limitations fonctionnelles avérées",
                "juriste":    "RQTH et AAH justifiés",
            },
            "donnees_structurees": {
                "is_enfant":           False,
                "genre":               "homme",
                "situation_familiale": "marié",
                "a_enfants_charge":    True,
                "type_logement":       "appartement",
                "statut_occupation":   "locataire",
                "type_demande":        "renouvellement",
                "deja_connu_mdph":     True,
                "accident_travail":    True,
                "consentement_informations": True,
            },
        },
    }

    resultat2 = traiter_dossier_cerfa(dossier_complet)
    print(f"valide   : {resultat2['valide']}")
    print(f"type     : {resultat2['type']}")
    print(f"warnings : {resultat2.get('warnings', [])}")
    if resultat2["valide"]:
        taille = len(resultat2.get("pdf_bytes", b""))
        print(f"pdf_bytes: {taille} octets generés [OK]")
    else:
        print(f"erreur   : {resultat2.get('erreur', '')}")
        print(f"erreurs  : {resultat2.get('erreurs', [])}")

    print()
    print("=" * 60)
    print("TEST 3 — NIR invalide (regex corrigée)")
    print("=" * 60)

    dossier_nir_invalide = {**dossier_complet, "numero_securite_sociale": "123456"}
    resultat3 = traiter_dossier_cerfa(dossier_nir_invalide)
    print(f"valide  : {resultat3['valide']}")
    nir_erreur = [e for e in resultat3.get("erreurs", []) if "securite" in e.lower()]
    print(f"erreur NIR détectée : {bool(nir_erreur)}")
    if nir_erreur:
        print(f"  -> {nir_erreur[0]}")
