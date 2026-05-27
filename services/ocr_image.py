"""
ocr_image.py — Extraction de texte depuis une image via GPT-4o Vision.

Utilisé quand une famille envoie une photo (ordonnance, compte-rendu médical,
justificatif) via WhatsApp. L'image est envoyée à GPT-4o qui en extrait le texte
visible et décrit les éléments pertinents pour le dossier MDPH.
"""

import base64
import logging
from openai import OpenAI
from config import get_settings

logger   = logging.getLogger(__name__)
settings = get_settings()

_SYSTEM_PROMPT = """\
Tu es un assistant spécialisé dans l'analyse de documents médicaux et administratifs \
pour les dossiers MDPH (Maison Départementale des Personnes Handicapées).

On te fournit une image envoyée par une famille. Extrais et retranscris fidèlement :
- Tout le texte visible (ordonnances, comptes-rendus, courriers, justificatifs)
- Les informations clés : diagnostics, médicaments, dates, signatures médicales
- Les noms de professionnels de santé et établissements s'ils sont présents

Si l'image ne contient pas de texte (photo de famille, etc.), décris brièvement \
ce que tu vois en une phrase.

Réponds UNIQUEMENT avec le contenu extrait / la description, sans commentaire ni \
reformulation de ta mission.
"""


def ocr_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """
    Extrait le texte d'une image via GPT-4o Vision.

    Args:
        image_bytes : Contenu binaire de l'image.
        mime_type   : Type MIME (image/jpeg, image/png, image/webp, image/gif).

    Returns:
        Texte extrait, ou message d'erreur générique en cas d'échec.
    """
    if not image_bytes:
        return "[Image vide ou illisible]"

    # Normalisation du mime type pour l'API OpenAI
    # (image/ogg n'est pas supporté — fallback jpeg)
    supported_mimes = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    if mime_type not in supported_mimes:
        mime_type = "image/jpeg"

    try:
        b64 = base64.standard_b64encode(image_bytes).decode("ascii")
        client = OpenAI(api_key=settings.openai_api_key)

        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{b64}",
                                "detail": "high",
                            },
                        }
                    ],
                },
            ],
            max_tokens=1000,
        )

        result = response.choices[0].message.content.strip()
        logger.info(f"OCR image OK | {len(image_bytes)} octets → {len(result)} caractères")
        return result

    except Exception as exc:
        logger.error(f"OCR image échoué : {exc}")
        return "[Lecture de l'image impossible]"
