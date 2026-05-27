"""
app/services/sms_service.py — Service SMS (canal de fallback).

Le SMS est utilisé quand :
  - L'usager n'a pas WhatsApp
  - WhatsApp est indisponible
  - Canal explicitement préféré par l'usager

Les SMS sont courts (160 caractères max par segment).
Aucune donnée médicale ne transite par SMS.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("facilim.services.sms")

_MAX_SMS_LENGTH = 160


class SMSService:
    """Service SMS générique avec support Twilio et désactivation."""

    def __init__(
        self,
        provider: str = "disabled",
        api_key: str = "",
        api_secret: str = "",
        sender: str = "Facilim",
    ):
        self.provider   = provider
        self.api_key    = api_key
        self.api_secret = api_secret
        self.sender     = sender

    def send(self, to: str, message: str) -> bool:
        """Envoie un SMS. Retourne True si succès."""
        if self.provider == "disabled":
            logger.info(f"[SMS] Désactivé — message non envoyé | to={to[-4:]}")
            return False

        # Troncature sécuritaire
        if len(message) > _MAX_SMS_LENGTH * 3:
            message = message[:_MAX_SMS_LENGTH * 3 - 3] + "..."

        if self.provider == "twilio":
            return self._send_twilio(to, message)

        logger.warning(f"[SMS] Provider '{self.provider}' non supporté")
        return False

    def _send_twilio(self, to: str, message: str) -> bool:
        try:
            from twilio.rest import Client
            client = Client(self.api_key, self.api_secret)
            client.messages.create(body=message, from_=self.sender, to=to)
            logger.info(f"[SMS] Envoyé via Twilio | to={to[-4:]}")
            return True
        except Exception as e:
            logger.error(f"[SMS] Erreur Twilio : {e}")
            return False
