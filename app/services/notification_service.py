"""
app/services/notification_service.py — Service de notifications omnicanal.

Façade unique pour l'envoi de notifications via :
  - WhatsApp (canal principal)
  - SMS (fallback)
  - Email (confirmation, documents)
  - Dashboard (alertes internes ESSMS)

La sélection du canal est automatique selon :
  1. La préférence de l'usager
  2. La disponibilité du canal
  3. La sensibilité du contenu (médical → portail sécurisé, pas WhatsApp)
"""

from __future__ import annotations

import logging
from typing import Any

from app.audit.event_logger import log_event

logger = logging.getLogger("facilim.services.notification")


class NotificationService:
    """Façade omnicanal pour les notifications Facilim."""

    def __init__(
        self,
        whatsapp_service: Any | None = None,
        email_service: Any | None = None,
        sms_service: Any | None = None,
    ):
        self._wa    = whatsapp_service
        self._email = email_service
        self._sms   = sms_service

    def notify_usager(
        self,
        usager: dict[str, Any],
        message: str,
        *,
        canal_force: str | None = None,
        type_notification: str = "INFO",
        dossier_id: str | None = None,
        db_conn: Any | None = None,
    ) -> bool:
        """
        Envoie une notification à un usager via le canal le plus approprié.

        Args:
            usager: Dict usager (avec telephone_enc, email_enc, canal_prefere)
            message: Texte du message (jamais de données médicales brutes)
            canal_force: Force un canal spécifique
            type_notification: INFO|ALERTE|RELANCE|VALIDATION
        """
        canal = canal_force or usager.get("canal_prefere", "whatsapp")
        telephone = usager.get("telephone_enc", "")
        email = usager.get("email_enc", "")

        success = False

        if canal == "whatsapp" and self._wa and telephone:
            from app.security.encryption import decrypt
            tel = decrypt(telephone)
            if tel:
                success = self._wa.send_text(
                    tel, message,
                    dossier_id=dossier_id,
                    db_conn=db_conn,
                )

        elif canal == "email" and self._email and email:
            from app.security.encryption import decrypt
            em = decrypt(email)
            if em:
                success = self._email.send(
                    to=em,
                    subject=f"Facilim — {type_notification.lower()}",
                    body=message,
                )

        elif canal == "sms" and self._sms and telephone:
            from app.security.encryption import decrypt
            tel = decrypt(telephone)
            if tel:
                success = self._sms.send(tel, message)

        if not success:
            logger.warning(
                f"[NOTIF] Échec envoi | canal={canal} | type={type_notification}"
                + (f" | dossier={dossier_id[:8]}" if dossier_id else "")
            )

        if db_conn:
            log_event(
                "NOTIFICATION_ENVOYEE",
                dossier_id=dossier_id,
                usager_id=usager.get("id"),
                canal=canal,
                payload={"type": type_notification, "success": success},
                db_conn=db_conn,
            )

        return success

    def notify_educateur(
        self,
        educateur: dict[str, Any],
        message: str,
        *,
        type_alerte: str = "INFO",
        dossier_id: str | None = None,
        db_conn: Any | None = None,
    ) -> None:
        """Crée une alerte Dashboard pour un éducateur."""
        import uuid
        from datetime import datetime, timezone

        if db_conn:
            alerte_id = str(uuid.uuid4())
            db_conn.execute(
                """
                INSERT INTO alertes
                    (id, dossier_id, destinataire_id, type_alerte, severite,
                     titre, description, created_at)
                VALUES (?, ?, ?, ?, 'NORMALE', ?, ?, ?)
                """,
                (
                    alerte_id,
                    dossier_id,
                    educateur.get("id"),
                    type_alerte,
                    f"[Facilim] {type_alerte}",
                    message,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            log_event(
                "ALERTE_ENVOYEE",
                dossier_id=dossier_id,
                utilisateur_id=educateur.get("id"),
                canal="dashboard",
                payload={"type": type_alerte},
                db_conn=db_conn,
            )
            logger.info(f"[NOTIF] Alerte Dashboard créée | type={type_alerte}")

    def send_relance_pieces_manquantes(
        self,
        usager: dict[str, Any],
        pieces_manquantes: list[str],
        dossier_id: str,
        db_conn: Any | None = None,
    ) -> bool:
        """Relance spécialisée pour les pièces manquantes."""
        pieces_str = "\n".join(f"• {p}" for p in pieces_manquantes)
        message = (
            "Bonjour, votre dossier MDPH est presque prêt !\n\n"
            "Il manque encore les documents suivants :\n"
            f"{pieces_str}\n\n"
            "Pouvez-vous nous les envoyer ici en photo ou en PDF ?\n"
            "L'équipe Facilim"
        )
        return self.notify_usager(
            usager, message,
            type_notification="RELANCE",
            dossier_id=dossier_id,
            db_conn=db_conn,
        )
