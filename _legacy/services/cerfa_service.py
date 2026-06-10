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
from services.cerfa_expert import analyser_profil_mdph

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

    # ── Étape 0 : analyse experte du profil MDPH ─────────────────────────────
    # Détermine profil, cohérences, enrichit ds, génère narration P8.
    try:
        expertise = analyser_profil_mdph(donnees_collectees)
        donnees_collectees = expertise["cerfa"]   # dossier enrichi
        _alertes_expert    = expertise["alertes"]
        if _alertes_expert:
            logger.info(f"[CERFA_SERVICE] Alertes expert : {_alertes_expert}")
    except Exception as exc:
        logger.warning(f"[CERFA_SERVICE] Analyse experte échouée (non bloquant) : {exc}")
        expertise = {}

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
        "valide":         True,
        "type":           "succes",
        "pdf_bytes":      pdf_bytes,
        "warnings":       validation.get("warnings", []),
        "donnees":        donnees_collectees,
        "profil_mdph":    expertise.get("profil"),
        "alertes_expert": expertise.get("alertes", []),
        "justifications": expertise.get("justifications", []),
        "narration_p8":   expertise.get("narration_p8", ""),
        "coherence":      expertise.get("coherence", {}),
    }



# ---------------------------------------------------------------------------
# Bloc de test rapide (si __name__ == "__main__")
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

    _d = {
        "dossier_id": "TEST-SVC-001",
        "nom_enfant": "NAIT ALI", "prenom_enfant": "Karim",
        "ddn_enfant": "05/12/1969", "departement_code": "13",
        "cerfa_reponses": {},
        "type_demande": "renouvellement", "nom_prenom": "Karim NAIT ALI",
        "date_naissance": "05/12/1969", "genre": "homme",
        "adresse_complete": "1 rue des Bateliers, 13016 Marseille",
        "situation_familiale": "marie", "type_droits": "RQTH, AAH",
        "difficultes_quotidiennes": "Douleurs chroniques AT 2019.",
        "besoins_aide": "Amenagement poste de travail",
        "organisme_payeur": "CAF", "protection_juridique": "aucune",
        "analyse": {
            "droits_identifies": ["RQTH", "AAH"],
            "elements_probants": ["AT 2019"],
            "synthese_agents": {"geva_pro": "AT 2019", "juriste": "RQTH AAH"},
            "donnees_structurees": {
                "is_enfant": False, "genre": "homme",
                "situation_familiale": "marie",
                "type_demande": "renouvellement", "deja_connu_mdph": True,
                "accident_travail": True, "consentement_informations": True,
            },
        },
    }
    _r = traiter_dossier_cerfa(_d)
    print("valide   :", _r["valide"])
    print("type     :", _r["type"])
    print("profil   :", _r.get("profil_mdph"))
    if _r["valide"]:
        print("pdf_bytes:", len(_r.get("pdf_bytes", b"")), "octets")
