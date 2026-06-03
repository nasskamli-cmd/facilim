"""
app/services/consent_service.py — Orchestration complète du cycle de vie du consentement.

Gère :
  - Demande de consentement (envoi message WhatsApp/SMS/Email)
  - Recueil de la réponse utilisateur
  - Enregistrement juridiquement tracé
  - Vérification avant chaque traitement
  - Retrait et anonymisation consécutive
"""

from __future__ import annotations

import logging
from typing import Any

from app.audit.consent_history import (
    create_consent_record,
    get_active_consent,
    get_consent_message_for_whatsapp,
    has_valid_consent,
    withdraw_consent,
)
from app.audit.event_logger import log_event

logger = logging.getLogger("facilim.services.consent")

# Mots-clés d'acceptation / refus (multi-langues basique)
_ACCEPTANCE_KEYWORDS = {"oui", "yes", "ok", "d'accord", "dacord", "j'accepte", "accepte"}
_REFUSAL_KEYWORDS    = {"non", "no", "refus", "refuse", "je refuse", "pas d'accord"}


def parse_consent_response(message: str) -> str | None:
    """
    Analyse la réponse de l'usager à la demande de consentement.

    Returns:
        'accepted' | 'refused' | None (réponse non reconnue)
    """
    normalized = message.strip().lower()
    if normalized in _ACCEPTANCE_KEYWORDS:
        return "accepted"
    if normalized in _REFUSAL_KEYWORDS:
        return "refused"
    return None


def check_consent_required(usager_id: str, db_conn: Any) -> bool:
    """Retourne True si l'usager n'a pas encore donné son consentement."""
    consent = get_active_consent(usager_id, db_conn)
    return consent is None


def request_consent_via_whatsapp(
    usager_id: str,
    telephone: str,
    whatsapp_send_fn: Any,
) -> None:
    """Envoie la demande de consentement via WhatsApp."""
    message = get_consent_message_for_whatsapp()
    try:
        whatsapp_send_fn(telephone, message)
        logger.info(f"[CONSENT] Demande envoyée via WhatsApp | usager={usager_id[:8]}")
    except Exception as e:
        logger.error(f"[CONSENT] Échec envoi WhatsApp : {e}")


def record_whatsapp_consent(
    usager_id: str,
    response_text: str,
    db_conn: Any,
) -> str:
    """
    Enregistre la réponse de consentement reçue via WhatsApp.

    Returns:
        'accepted' | 'refused' | 'unclear'
    """
    decision = parse_consent_response(response_text)

    if decision == "accepted":
        finalites = {
            "traitement_dossier":   True,
            "partage_mdph":         True,
            "partage_essms":        True,
            "notifications":        True,
            "amelioration_service": False,  # opt-in séparé
        }
        create_consent_record(
            usager_id=usager_id,
            canal="whatsapp",
            finalites=finalites,
            db_conn=db_conn,
        )
        log_event(
            "CONSENTEMENT_DONNE",
            usager_id=usager_id,
            canal="whatsapp",
            payload={"finalites": finalites},
            db_conn=db_conn,
        )
        logger.info(f"[CONSENT] Accepté | usager={usager_id[:8]}")
        return "accepted"

    elif decision == "refused":
        log_event(
            "CONSENTEMENT_REFUSE",
            usager_id=usager_id,
            canal="whatsapp",
            payload={"message": response_text},
            db_conn=db_conn,
        )
        logger.info(f"[CONSENT] Refusé | usager={usager_id[:8]}")
        return "refused"

    return "unclear"


def require_consent_for_processing(
    usager_id: str,
    finalite: str,
    db_conn: Any,
) -> bool:
    """
    Vérifie que l'usager a consenti à la finalité avant de lancer un traitement.
    Doit être appelé avant tout traitement de données personnelles.

    Returns:
        True si le traitement est autorisé
    """
    authorized = has_valid_consent(usager_id, finalite, db_conn)
    if not authorized:
        logger.warning(
            f"[CONSENT] Traitement bloqué — consentement manquant "
            f"| usager={usager_id[:8]} | finalite={finalite}"
        )
    return authorized


def get_consent_summary(usager_id: str, db_conn: Any) -> dict[str, Any]:
    """Résumé du consentement pour le Dashboard ESSMS."""
    consent = get_active_consent(usager_id, db_conn)
    if not consent:
        return {"statut": "AUCUN", "finalites": {}}
    return {
        "statut":      "ACTIF" if not consent.get("retire_le") else "RETIRÉ",
        "accorde_le":  consent.get("accorde_le"),
        "retire_le":   consent.get("retire_le"),
        "canal":       consent.get("canal_recueil"),
        "version":     consent.get("version_politique"),
        "finalites": {
            "traitement_dossier":   bool(consent.get("consent_traitement_dossier")),
            "partage_mdph":         bool(consent.get("consent_partage_mdph")),
            "partage_essms":        bool(consent.get("consent_partage_essms")),
            "notifications":        bool(consent.get("consent_notifications")),
            "amelioration_service": bool(consent.get("consent_amelioration_service")),
        },
    }
