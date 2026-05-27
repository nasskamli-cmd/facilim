"""
media_client.py — Téléchargement des médias WhatsApp depuis l'API Graph de Meta.

Lorsqu'un usager envoie un message vocal (type "audio") via WhatsApp Business,
le payload webhook ne contient pas le fichier audio lui-même, mais un identifiant
de média (media_id). Ce module effectue les deux étapes nécessaires pour récupérer
le fichier :

  1. Interroger l'API Graph pour obtenir l'URL de téléchargement du média.
  2. Télécharger les octets du fichier audio depuis cette URL.

Documentation Meta :
  https://developers.facebook.com/docs/whatsapp/cloud-api/reference/media
"""

import logging
import requests
from config import get_settings

logger   = logging.getLogger(__name__)
settings = get_settings()

_WA_API_BASE    = "https://graph.facebook.com/v19.0"
_MEDIA_TIMEOUT  = 30  # secondes — les fichiers audio peuvent être plus lourds qu'un texte


def _get_headers() -> dict:
    """Headers d'authentification pour l'API Graph de Meta."""
    return {"Authorization": f"Bearer {settings.whatsapp_api_token}"}


def download_media(media_id: str) -> tuple[bytes, str]:
    """
    Télécharge un média WhatsApp à partir de son identifiant.

    Étape 1 : appel à GET /v19.0/{media_id} → renvoie l'URL de téléchargement et le MIME type.
    Étape 2 : téléchargement des octets depuis cette URL (toujours avec le Bearer token).

    Args:
        media_id : Identifiant du média extrait du payload webhook WhatsApp.
                   Présent dans msg["audio"]["id"] pour les messages vocaux.

    Returns:
        Tuple (audio_bytes, mime_type).
        - audio_bytes : contenu binaire du fichier audio, prêt à être envoyé à Whisper.
        - mime_type   : type MIME déclaré par Meta (ex: "audio/ogg; codecs=opus").

    Raises:
        RuntimeError : En cas d'échec de l'une ou l'autre des deux étapes réseau.
    """

    # ── Étape 1 : résolution de l'URL de téléchargement ───────────────────────
    logger.info(f"Récupération URL média | media_id={media_id}")
    try:
        meta_response = requests.get(
            f"{_WA_API_BASE}/{media_id}",
            headers=_get_headers(),
            timeout=_MEDIA_TIMEOUT,
        )
        meta_response.raise_for_status()
        media_info = meta_response.json()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(
            f"Impossible de récupérer les métadonnées du média {media_id} : {e}"
        ) from e

    download_url = media_info.get("url")
    mime_type    = media_info.get("mime_type", "audio/ogg")

    if not download_url:
        raise RuntimeError(
            f"URL de téléchargement absente dans la réponse Meta pour le média {media_id}."
        )

    logger.info(f"URL média obtenue | mime_type={mime_type}")

    # ── Étape 2 : téléchargement des octets audio ──────────────────────────────
    try:
        audio_response = requests.get(
            download_url,
            headers=_get_headers(),
            timeout=_MEDIA_TIMEOUT,
        )
        audio_response.raise_for_status()
        audio_bytes = audio_response.content
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Impossible de télécharger le fichier audio : {e}") from e

    logger.info(f"Audio téléchargé | taille={len(audio_bytes)} octets")
    return audio_bytes, mime_type


def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    """
    Transcrit un fichier audio en texte via l'API Whisper d'OpenAI.

    Args:
        audio_bytes : Contenu binaire du fichier audio (téléchargé via download_media).
        mime_type   : Type MIME du fichier (ex: "audio/ogg; codecs=opus").

    Returns:
        Transcription textuelle du message vocal.
        Retourne une chaîne vide en cas d'échec (fallback gracieux).
    """
    import openai
    import io

    # Déterminer l'extension depuis le MIME type
    ext = "ogg"
    if "mp4" in mime_type or "m4a" in mime_type:
        ext = "mp4"
    elif "mpeg" in mime_type or "mp3" in mime_type:
        ext = "mp3"
    elif "webm" in mime_type:
        ext = "webm"
    elif "wav" in mime_type:
        ext = "wav"

    try:
        client = openai.OpenAI(api_key=settings.openai_api_key)
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = f"audio.{ext}"

        logger.info(f"Transcription Whisper | ext={ext} | taille={len(audio_bytes)} octets")
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="fr",
        )
        texte = transcript.text.strip()
        logger.info(f"Transcription OK | {len(texte)} caractères")
        return texte

    except Exception as e:
        logger.error(f"Erreur transcription Whisper : {e}")
        return ""


def detect_language(text: str) -> str:
    """
    Détecte la langue d'un texte court via l'API OpenAI.
    Utilisé pour adapter les questions FALC à la langue de la famille.

    Args:
        text : Texte à analyser (réponse de l'usager via WhatsApp).

    Returns:
        Code ISO 639-1 de la langue détectée (ex: "fr", "ar", "tr", "en").
        Retourne "fr" par défaut en cas d'échec ou de texte trop court.
    """
    import openai

    if not text or len(text.strip()) < 5:
        return "fr"

    try:
        client = openai.OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Tu es un détecteur de langue. "
                        "Réponds UNIQUEMENT avec le code ISO 639-1 de la langue du texte "
                        "(ex: fr, ar, tr, en, es, pt, ro, wo). "
                        "Aucun autre texte, juste le code à 2 lettres."
                    ),
                },
                {"role": "user", "content": text[:200]},
            ],
            max_tokens=5,
            temperature=0,
        )
        code = response.choices[0].message.content.strip().lower()[:2]
        logger.info(f"Langue détectée : '{code}'")
        return code if len(code) == 2 else "fr"

    except Exception as e:
        logger.error(f"Erreur détection langue : {e}")
        return "fr"
