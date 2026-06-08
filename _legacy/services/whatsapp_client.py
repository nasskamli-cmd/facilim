"""
whatsapp_client.py — Client WhatsApp Business Cloud API (Meta).
Gère l'envoi de messages interactifs (boutons) et de messages texte ouverts
vers les numéros de téléphone des familles.

Documentation API : https://developers.facebook.com/docs/whatsapp/cloud-api
Version API utilisée : v19.0

Limites importantes de l'API WhatsApp :
  - Maximum 3 boutons par message interactif
  - Titre de bouton : 20 caractères max
  - Corps du message : 1024 caractères max
  - En-tête : 60 caractères max
"""

import logging
import requests
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# URL de base de l'API WhatsApp Cloud
_WA_API_BASE = "https://graph.facebook.com/v19.0"
_WA_TIMEOUT  = 15  # secondes


def _get_headers() -> dict:
    """Construit les headers d'authentification pour chaque requête."""
    return {
        "Authorization": f"Bearer {settings.whatsapp_api_token}",
        "Content-Type": "application/json",
    }


def send_text_message(phone_number: str, message: str) -> dict:
    """
    Envoie un message texte simple.

    Args:
        phone_number: Numéro au format international sans '+' (ex: "33612345678").
        message:      Texte du message (max 4096 caractères).

    Returns:
        Réponse JSON de l'API WhatsApp.

    Raises:
        RuntimeError: En cas d'échec de l'envoi.
    """
    url = f"{_WA_API_BASE}/{settings.whatsapp_phone_number_id}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_number,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": message,
        },
    }

    return _post_to_api(url, payload, f"message texte → {phone_number}")


def send_button_message(
    phone_number: str,
    question: str,
    options: list[str],
    header_text: str = "Dossier MDPH",
    footer_text: str = "Répondez en appuyant sur un bouton",
) -> dict:
    """
    Envoie un message interactif avec boutons de réponse.
    L'API WhatsApp limite à 3 boutons par message.

    Args:
        phone_number: Numéro au format international sans '+'.
        question:     Corps du message / question posée (max 1024 caractères).
        options:      Liste de libellés de boutons (max 3, chacun max 20 caractères).
        header_text:  Titre en en-tête du message (max 60 caractères).
        footer_text:  Note de bas de message (max 60 caractères).

    Returns:
        Réponse JSON de l'API WhatsApp.

    Raises:
        ValueError:   Si plus de 3 options sont fournies.
        RuntimeError: En cas d'échec de l'envoi.
    """
    if len(options) > 3:
        raise ValueError(
            f"WhatsApp n'autorise que 3 boutons maximum par message. "
            f"{len(options)} options fournies."
        )

    url = f"{_WA_API_BASE}/{settings.whatsapp_phone_number_id}/messages"

    # Construction des boutons selon la spec API WhatsApp
    buttons = [
        {
            "type": "reply",
            "reply": {
                "id": f"btn_{i}_{opt.lower().replace(' ', '_')[:20]}",
                "title": opt[:20],  # Troncature au seuil API
            },
        }
        for i, opt in enumerate(options)
    ]

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "header": {
                "type": "text",
                "text": header_text[:60],  # Troncature au seuil API
            },
            "body": {
                "text": question[:1024],   # Troncature au seuil API
            },
            "footer": {
                "text": footer_text[:60],
            },
            "action": {
                "buttons": buttons,
            },
        },
    }

    return _post_to_api(url, payload, f"message boutons → {phone_number}")


def send_questions_sequence(
    phone_number: str,
    formatted_questions: list[dict],
    intro_message: str | None = None,
) -> list[dict]:
    """
    Envoie une séquence de questions à la famille via WhatsApp.
    Chaque question est envoyée dans un message distinct pour plus de clarté.

    Args:
        phone_number:        Numéro au format international sans '+'.
        formatted_questions: Liste issue de jargon_splitter.format_for_whatsapp().
        intro_message:       Message d'introduction optionnel envoyé en premier.

    Returns:
        Liste des réponses API pour chaque message envoyé.
    """
    results = []

    # Message d'introduction pour contextualiser la démarche
    if intro_message:
        try:
            result = send_text_message(phone_number, intro_message)
            results.append({"type": "intro", "response": result})
        except RuntimeError as e:
            logger.error(f"Échec envoi intro WhatsApp : {e}")

    # Envoi de chaque question
    for i, q_data in enumerate(formatted_questions, start=1):
        question = q_data.get("question", "")
        q_type   = q_data.get("type", "text")
        options  = q_data.get("options", [])

        logger.info(f"Envoi question {i}/{len(formatted_questions)} | type={q_type}")

        try:
            if q_type == "button" and options:
                result = send_button_message(
                    phone_number=phone_number,
                    question=question,
                    options=options[:3],  # Sécurité : on ne prend que les 3 premiers
                    header_text=f"Question {i}/{len(formatted_questions)}",
                )
            else:
                result = send_text_message(phone_number, question)

            results.append({"type": q_type, "question": question, "response": result})

        except (RuntimeError, ValueError) as e:
            logger.error(f"Échec envoi question {i} : {e}")
            results.append({"type": q_type, "question": question, "error": str(e)})

    logger.info(f"Séquence WhatsApp terminée | {len(results)} message(s) traités")
    return results


def _post_to_api(url: str, payload: dict, context: str) -> dict:
    """
    Effectue la requête POST vers l'API WhatsApp avec gestion des erreurs.

    Args:
        url:     URL de l'endpoint.
        payload: Corps JSON de la requête.
        context: Description courte pour les logs.

    Returns:
        Réponse JSON de l'API.

    Raises:
        RuntimeError: Pour toute erreur réseau ou erreur API (statut != 200).
    """
    try:
        logger.info(f"Appel API WhatsApp | {context}")
        response = requests.post(
            url,
            headers=_get_headers(),
            json=payload,
            timeout=_WA_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        logger.info(f"Message envoyé avec succès | message_id={data.get('messages', [{}])[0].get('id', 'N/A')}")
        return data

    except requests.exceptions.Timeout:
        raise RuntimeError(f"Timeout WhatsApp API après {_WA_TIMEOUT}s pour : {context}")

    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(f"Connexion WhatsApp API impossible : {e}") from e

    except requests.exceptions.HTTPError as e:
        error_body = {}
        try:
            error_body = e.response.json()
        except Exception:
            pass
        raise RuntimeError(
            f"Erreur HTTP WhatsApp API {e.response.status_code} : "
            f"{error_body.get('error', {}).get('message', str(e))}"
        ) from e
