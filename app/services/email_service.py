"""
app/services/email_service.py — Service d'envoi d'emails transactionnels.

Utilise Brevo (ex-Sendinblue) comme provider principal.
Fallback SMTP disponible pour les environnements sans accès API.

Contenus envoyés :
  - Codes de vérification
  - Résumés de dossier
  - CERFA pré-rempli
  - Notifications de statut
  - Confirmations de consentement

Les données médicales ne sont JAMAIS envoyées par email en clair.
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

logger = logging.getLogger("facilim.services.email")


class EmailService:
    """Service d'email transactionnel via Brevo API ou SMTP."""

    def __init__(
        self,
        brevo_api_key: str = "",
        smtp_host: str = "smtp-relay.brevo.com",
        smtp_port: int = 587,
        smtp_login: str = "",
        smtp_key: str = "",
        sender_email: str = "noreply@facilim.fr",
        sender_name: str = "Facilim",
    ):
        self.brevo_api_key  = brevo_api_key
        self.smtp_host      = smtp_host
        self.smtp_port      = smtp_port
        self.smtp_login     = smtp_login
        self.smtp_key       = smtp_key
        self.sender_email   = sender_email
        self.sender_name    = sender_name

    def send(
        self,
        to: str,
        subject: str,
        body: str,
        html: str | None = None,
        attachments: list[tuple[str, bytes]] | None = None,
    ) -> bool:
        """
        Envoie un email. Tente Brevo API puis SMTP en fallback.

        Args:
            to: Adresse destinataire
            subject: Sujet de l'email
            body: Corps texte brut
            html: Corps HTML (optionnel)
            attachments: Liste de (nom_fichier, contenu_bytes)

        Returns:
            True si envoyé avec succès
        """
        if self.brevo_api_key:
            return self._send_via_brevo_api(to, subject, body, html, attachments)
        return self._send_via_smtp(to, subject, body, html, attachments)

    def _send_via_brevo_api(
        self,
        to: str,
        subject: str,
        body: str,
        html: str | None,
        attachments: list[tuple[str, bytes]] | None,
    ) -> bool:
        try:
            import sib_api_v3_sdk
            from sib_api_v3_sdk.rest import ApiException

            config = sib_api_v3_sdk.Configuration()
            config.api_key["api-key"] = self.brevo_api_key

            api = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(config))

            email = sib_api_v3_sdk.SendSmtpEmail(
                sender={"name": self.sender_name, "email": self.sender_email},
                to=[{"email": to}],
                subject=subject,
                text_content=body,
                html_content=html or self._text_to_html(body),
            )

            api.send_transac_email(email)
            logger.info(f"[EMAIL] Envoyé via Brevo API | to={to[-10:]}")
            return True

        except Exception as e:
            logger.error(f"[EMAIL] Erreur Brevo API : {e}")
            return self._send_via_smtp(to, subject, body, html, attachments)

    def _send_via_smtp(
        self,
        to: str,
        subject: str,
        body: str,
        html: str | None,
        attachments: list[tuple[str, bytes]] | None,
    ) -> bool:
        if not self.smtp_login or not self.smtp_key:
            logger.warning("[EMAIL] SMTP non configuré — email non envoyé")
            return False
        try:
            msg = MIMEMultipart("alternative")
            msg["From"]    = f"{self.sender_name} <{self.sender_email}>"
            msg["To"]      = to
            msg["Subject"] = subject

            msg.attach(MIMEText(body, "plain", "utf-8"))
            if html:
                msg.attach(MIMEText(html, "html", "utf-8"))

            for fname, fdata in (attachments or []):
                part = MIMEApplication(fdata, Name=fname)
                part["Content-Disposition"] = f'attachment; filename="{fname}"'
                msg.attach(part)

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as s:
                s.starttls()
                s.login(self.smtp_login, self.smtp_key)
                s.send_message(msg)

            logger.info(f"[EMAIL] Envoyé via SMTP | to={to[-10:]}")
            return True

        except Exception as e:
            logger.error(f"[EMAIL] Erreur SMTP : {e}")
            return False

    def send_verification_code(self, to: str, code: str, prenom: str = "") -> bool:
        body = (
            f"Bonjour{' ' + prenom if prenom else ''},\n\n"
            f"Votre code de vérification Facilim est : {code}\n\n"
            "Ce code est valable 15 minutes.\n\n"
            "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.\n\n"
            "— L'équipe Facilim"
        )
        return self.send(to, "Votre code de vérification Facilim", body)

    def send_dossier_summary(
        self,
        to: str,
        reference: str,
        droits_identifies: list[str],
        score: int,
        cerfa_pdf: bytes | None = None,
    ) -> bool:
        droits_str = ", ".join(droits_identifies) if droits_identifies else "En cours d'analyse"
        body = (
            f"Bonjour,\n\n"
            f"Votre dossier MDPH (référence : {reference}) est maintenant complet.\n\n"
            f"Droits identifiés : {droits_str}\n"
            f"Niveau de complétude : {score}/100\n\n"
            "Le dossier CERFA pré-rempli est joint à cet email si disponible.\n\n"
            "Prochaines étapes :\n"
            "  1. Vérifiez les informations dans le CERFA ci-joint\n"
            "  2. Signez le document\n"
            "  3. Envoyez-le à votre MDPH avec les pièces justificatives\n\n"
            "En cas de question, répondez à ce message ou contactez votre éducateur.\n\n"
            "— L'équipe Facilim"
        )
        attachments = []
        if cerfa_pdf:
            attachments.append((f"CERFA_MDPH_{reference}.pdf", cerfa_pdf))
        return self.send(
            to,
            f"[Facilim] Votre dossier MDPH est complet — {reference}",
            body,
            attachments=attachments if attachments else None,
        )

    @staticmethod
    def _text_to_html(text: str) -> str:
        escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f"<html><body><pre style='font-family:sans-serif'>{escaped}</pre></body></html>"
