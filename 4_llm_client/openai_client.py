"""
openai_client.py — Gestionnaire centralisé des appels LLM.
Abstrait la communication avec l'API OpenAI (compatible Mistral via base_url).
Toutes les couches du projet passent par ce module pour garantir :
  - Une gestion des erreurs uniforme
  - Un point unique de changement de modèle ou de fournisseur
  - Une traçabilité des appels (logs, coûts)
"""

import logging
from typing import Optional
from openai import OpenAI, APIError, APIConnectionError, RateLimitError
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Initialisation du client OpenAI (singleton au niveau module)
# Pour Mistral : passer base_url="https://api.mistral.ai/v1" et la clé Mistral
_client = OpenAI(api_key=settings.openai_api_key)


def call_llm(
    system_prompt: str,
    user_message: str,
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> str:
    """
    Effectue un appel LLM synchrone et retourne le texte généré.

    Args:
        system_prompt: Instructions de rôle données au modèle (persona de l'agent).
        user_message:  Le contenu à traiter (texte du dossier, questions, etc.).
        model:         Modèle à utiliser (par défaut : settings.openai_model).
        temperature:   Créativité du modèle (0.0 = déterministe, 1.0 = créatif).
        max_tokens:    Limite de la réponse générée.

    Returns:
        Le texte brut de la réponse du LLM.

    Raises:
        RuntimeError: En cas d'erreur API non récupérable.
    """
    target_model = model or settings.openai_model
    # Sécurité : gpt-4o supporte au maximum 16 384 tokens en sortie.
    # On plafonne à 4 096 pour laisser de la marge au prompt et éviter l'erreur.
    max_tokens = min(max_tokens, 4096)

    try:
        logger.info(f"Appel LLM | modèle={target_model} | tokens_max={max_tokens}")

        response = _client.chat.completions.create(
            model=target_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )

        result = response.choices[0].message.content.strip()
        logger.info(f"Réponse LLM reçue | tokens_utilisés={response.usage.total_tokens}")
        return result

    except RateLimitError as e:
        logger.error(f"Limite de débit API atteinte : {e}")
        raise RuntimeError("Service IA temporairement surchargé. Veuillez réessayer dans quelques instants.") from e

    except APIConnectionError as e:
        logger.error(f"Impossible de joindre l'API OpenAI : {e}")
        raise RuntimeError("Connexion à l'API IA impossible. Vérifiez votre réseau.") from e

    except APIError as e:
        logger.error(f"Erreur API OpenAI (statut {e.status_code}) : {e.message}")
        raise RuntimeError(f"Erreur du service IA : {e.message}") from e


def transcribe_audio(
    audio_bytes: bytes,
    mime_type: str = "audio/ogg",
) -> dict:
    """
    Transcrit un message vocal en texte via l'API Whisper d'OpenAI.
    Détecte automatiquement la langue parlée — aucune configuration requise.

    Args:
        audio_bytes : Contenu binaire du fichier audio téléchargé depuis Meta.
        mime_type   : Type MIME déclaré par Meta (ex: "audio/ogg; codecs=opus").
                      Utilisé pour déterminer l'extension du fichier envoyé à Whisper.

    Returns:
        Dictionnaire {"text": str, "language": str}.
        - text     : transcription en clair du message vocal.
        - language : code ISO 639-1 de la langue détectée (ex: "fr", "ar", "tr", "wo").

    Raises:
        RuntimeError : En cas d'erreur API non récupérable.
    """
    import io

    # Correspondance MIME → extension de fichier reconnue par Whisper
    # Whisper accepte : flac, mp3, mp4, mpeg, mpga, m4a, ogg, wav, webm
    _mime_to_ext = {
        "audio/ogg":  "ogg",
        "audio/mpeg": "mp3",
        "audio/mp4":  "mp4",
        "audio/m4a":  "m4a",
        "audio/wav":  "wav",
        "audio/webm": "webm",
        "audio/flac": "flac",
    }
    # Le MIME type peut contenir des paramètres supplémentaires (ex: "audio/ogg; codecs=opus")
    base_mime = mime_type.split(";")[0].strip().lower()
    extension = _mime_to_ext.get(base_mime, "ogg")

    # Whisper attend un objet fichier — on enveloppe les octets dans un BytesIO en mémoire
    audio_file      = io.BytesIO(audio_bytes)
    audio_file.name = f"vocal.{extension}"  # Le nom du fichier indique le format à Whisper

    logger.info(f"Transcription Whisper | format={extension} | taille={len(audio_bytes)} octets")

    try:
        response = _client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json",  # verbose_json inclut le champ "language"
        )

        text     = response.text.strip()
        language = getattr(response, "language", "fr") or "fr"

        logger.info(f"Transcription réussie | langue_détectée={language} | aperçu='{text[:80]}'")
        return {"text": text, "language": language}

    except APIError as e:
        logger.error(f"Erreur Whisper API (statut {e.status_code}) : {e.message}")
        raise RuntimeError(f"Erreur de transcription audio : {e.message}") from e

    except APIConnectionError as e:
        logger.error(f"Connexion Whisper impossible : {e}")
        raise RuntimeError("Connexion à l'API de transcription audio impossible. Vérifiez votre réseau.") from e


def detect_language(text: str) -> str:
    """
    Détecte la langue d'un message texte via GPT-4o.
    Utilisé quand une famille écrit directement dans sa langue sans passer par un vocal.

    Args:
        text : Le texte dont on veut identifier la langue.

    Returns:
        Code ISO 639-1 de la langue détectée (ex: "fr", "ar", "tr", "en", "wo").
        Retourne "fr" par défaut en cas d'échec.
    """
    if not text or not text.strip():
        return "fr"

    try:
        response = _client.chat.completions.create(
            model="gpt-4o-mini",  # Modèle léger suffisant pour cette tâche simple
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Tu es un détecteur de langue. "
                        "Réponds UNIQUEMENT avec le code ISO 639-1 de la langue du texte reçu. "
                        "Exemples de réponses valides : fr, en, ar, tr, wo, es, pt, de, it. "
                        "Un seul mot, rien d'autre."
                    ),
                },
                {"role": "user", "content": text},
            ],
            temperature=0.0,
            max_tokens=5,
        )
        code = response.choices[0].message.content.strip().lower()
        # Sécurité : si la réponse est bizarre, on revient à "fr"
        if len(code) > 5 or not code.isalpha():
            return "fr"
        logger.info(f"Langue texte détectée : {code}")
        return code

    except Exception as e:
        logger.warning(f"Détection de langue échouée : {e}. Langue par défaut : fr")
        return "fr"
