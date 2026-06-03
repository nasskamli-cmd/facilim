"""
app/services/whatsapp_service.py — Service WhatsApp Business Cloud API.

Encapsule tous les appels à l'API WhatsApp Cloud.
Le canal WhatsApp est le canal PRINCIPAL d'interaction usager.
C'est un levier d'accessibilité sociale, pas un simple canal technique.

Contraintes :
  - Aucune donnée médicale brute dans les messages WhatsApp
  - Messages courts, clairs, sans jargon
  - Compatible FALC
  - Rate limiting intégré
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from app.audit.event_logger import log_event

logger = logging.getLogger("facilim.services.whatsapp")

_MIN_DELAY_BETWEEN_MESSAGES = 0.5  # secondes
_last_send_time: float = 0.0


def _throttle() -> None:
    global _last_send_time
    elapsed = time.monotonic() - _last_send_time
    if elapsed < _MIN_DELAY_BETWEEN_MESSAGES:
        time.sleep(_MIN_DELAY_BETWEEN_MESSAGES - elapsed)
    _last_send_time = time.monotonic()


class WhatsAppService:
    """Service d'envoi et réception de messages WhatsApp Business."""

    def __init__(self, api_token: str, phone_number_id: str, api_version: str = "v20.0"):
        self.api_token       = api_token
        self.phone_number_id = phone_number_id
        self.api_url = (
            f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
        )
        self._headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type":  "application/json",
        }

    def send_text(
        self,
        to: str,
        text: str,
        *,
        dossier_id: str | None = None,
        db_conn: Any | None = None,
    ) -> bool:
        """Envoie un message texte simple."""
        _throttle()
        # Troncature de sécurité : WhatsApp limite à 4096 chars
        if len(text) > 4000:
            text = text[:3980] + "\n\n[...message tronqué]"

        payload = {
            "messaging_product": "whatsapp",
            "to":                to,
            "type":              "text",
            "text":              {"preview_url": False, "body": text},
        }
        try:
            resp = requests.post(self.api_url, headers=self._headers, json=payload, timeout=10)
            success = resp.status_code == 200
            if success:
                logger.info(f"[WA] Message envoyé | to={to[-4:]} | len={len(text)}")
            else:
                logger.error(f"[WA] Erreur API | status={resp.status_code} | body={resp.text[:200]}")
            if db_conn:
                log_event(
                    "WHATSAPP_ENVOYE",
                    dossier_id=dossier_id,
                    canal="whatsapp",
                    payload={"to_suffix": to[-4:], "length": len(text), "success": success},
                    db_conn=db_conn,
                )
            return success
        except requests.RequestException as e:
            logger.error(f"[WA] Exception réseau : {e}")
            return False

    def send_sequence(
        self,
        to: str,
        messages: list[str],
        delay_between: float = 1.0,
        dossier_id: str | None = None,
        db_conn: Any | None = None,
    ) -> int:
        """Envoie une séquence de messages avec délai. Retourne le nombre envoyés."""
        sent = 0
        for i, msg in enumerate(messages):
            if i > 0:
                time.sleep(delay_between)
            if self.send_text(to, msg, dossier_id=dossier_id, db_conn=db_conn):
                sent += 1
        return sent

    def send_document(
        self,
        to: str,
        document_url: str,
        filename: str,
        caption: str | None = None,
        dossier_id: str | None = None,
        db_conn: Any | None = None,
    ) -> bool:
        """Envoie un document PDF (ex : résumé de dossier, CERFA)."""
        _throttle()
        payload = {
            "messaging_product": "whatsapp",
            "to":                to,
            "type":              "document",
            "document": {
                "link":     document_url,
                "filename": filename,
                **({"caption": caption} if caption else {}),
            },
        }
        try:
            resp = requests.post(self.api_url, headers=self._headers, json=payload, timeout=15)
            success = resp.status_code == 200
            if db_conn:
                log_event(
                    "WHATSAPP_DOCUMENT_ENVOYE",
                    dossier_id=dossier_id,
                    canal="whatsapp",
                    payload={"filename": filename, "success": success},
                    db_conn=db_conn,
                )
            return success
        except requests.RequestException as e:
            logger.error(f"[WA] Exception envoi document : {e}")
            return False

    def download_media(self, media_id: str) -> tuple[bytes, str] | None:
        """
        Télécharge un média WhatsApp (audio, image, document, vidéo) depuis Meta API.

        Étape 1 : GET /v20.0/{media_id} → récupère l'URL de téléchargement
        Étape 2 : GET {url} → télécharge le contenu binaire

        Returns:
            (contenu_bytes, mime_type) ou None si échec
        """
        try:
            # Étape 1 : URL du média
            meta_resp = requests.get(
                f"https://graph.facebook.com/v20.0/{media_id}",
                headers={"Authorization": f"Bearer {self.api_token}"},
                timeout=10,
            )
            if meta_resp.status_code != 200:
                logger.error("[WA] download_media step1 error %d : %s",
                             meta_resp.status_code, meta_resp.text[:200])
                return None

            meta   = meta_resp.json()
            url    = meta.get("url")
            mime   = meta.get("mime_type", "application/octet-stream")

            if not url:
                logger.error("[WA] Pas d'URL dans la réponse media : %s", meta)
                return None

            # Étape 2 : téléchargement du binaire
            dl_resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {self.api_token}"},
                timeout=30,
                stream=True,
            )
            if dl_resp.status_code != 200:
                logger.error("[WA] Téléchargement échoué %d", dl_resp.status_code)
                return None

            content = dl_resp.content
            logger.info("[WA] Média téléchargé | id=%s | mime=%s | size=%d",
                        media_id[:8], mime, len(content))
            return content, mime

        except Exception as e:
            logger.error("[WA] Erreur download_media : %s", e)
            return None

    def mark_as_read(self, message_id: str) -> None:
        """Marque un message comme lu (indicateur 'lu' dans WhatsApp)."""
        payload = {
            "messaging_product": "whatsapp",
            "status":            "read",
            "message_id":        message_id,
        }
        try:
            requests.post(self.api_url, headers=self._headers, json=payload, timeout=5)
        except requests.RequestException:
            pass


def parse_webhook_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extrait les messages entrants du payload webhook WhatsApp.

    Returns:
        Liste de dicts normalisés : {from, message_id, type, text, media_id, timestamp}
    """
    messages = []
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    normalized = {
                        "from":       msg.get("from", ""),
                        "message_id": msg.get("id", ""),
                        "timestamp":  msg.get("timestamp", ""),
                        "type":       msg.get("type", "text"),
                        "text":       msg.get("text", {}).get("body", ""),
                        "media_id":   None,
                        "filename":   None,
                        "mime_type":  None,
                    }
                    # Documents / images
                    for media_type in ("image", "document", "audio", "video"):
                        if media_type in msg:
                            normalized["media_id"]  = msg[media_type].get("id")
                            normalized["filename"]  = msg[media_type].get("filename")
                            normalized["mime_type"] = msg[media_type].get("mime_type")
                            break
                    messages.append(normalized)
    except Exception as e:
        logger.error(f"[WA] Erreur parsing webhook : {e}")
    return messages
