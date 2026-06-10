"""
email_client.py — Envoi d'emails transactionnels via Brevo (ex-Sendinblue).

Utilisé pour :
  - Envoyer le code de vérification à 6 chiffres lors de la connexion
  - Envoyer le dossier PDF complété à la MDPH (Phase suivante)

Documentation Brevo API : https://developers.brevo.com/reference/sendtransacemail
"""

import logging
import random
import base64
import requests
from config import get_settings

logger   = logging.getLogger(__name__)
settings = get_settings()

# Endpoint API Brevo (HTTP — pas de SMTP, pas de port bloqué)
_BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def generate_code() -> str:
    """
    Génère un code de vérification à 6 chiffres.
    Retourne une chaîne comme "482917".
    """
    return str(random.randint(100000, 999999))


def send_verification_code(recipient_email: str, code: str) -> bool:
    """
    Envoie un email contenant le code de vérification à 6 chiffres.

    Args:
        recipient_email : Adresse email de l'éducateur.
        code            : Code à 6 chiffres généré par generate_code().

    Returns:
        True si l'email a été envoyé, False en cas d'échec.
    """
    subject = f"Votre code de connexion Facilim : {code}"

    html_body = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head><meta charset="UTF-8"></head>
    <body style="margin:0;padding:0;background:#F0F4F8;font-family:Inter,Arial,sans-serif;">
      <div style="max-width:480px;margin:40px auto;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 16px rgba(0,0,0,0.08);">

        <div style="background:#1B3A6B;padding:24px 32px;display:flex;align-items:center;gap:12px;">
          <div style="width:36px;height:36px;background:#2ECC9A;border-radius:8px;display:inline-flex;align-items:center;justify-content:center;font-weight:700;font-size:16px;color:#0F3D2E;">F</div>
          <span style="color:#ffffff;font-size:20px;font-weight:600;margin-left:10px;">Facilim</span>
        </div>

        <div style="padding:32px;">
          <p style="color:#1A202C;font-size:16px;font-weight:600;margin:0 0 8px;">Votre code de connexion</p>
          <p style="color:#718096;font-size:14px;margin:0 0 28px;line-height:1.6;">
            Utilisez ce code pour finaliser votre connexion à votre espace Facilim.
            Il est valable pendant <strong>10 minutes</strong>.
          </p>

          <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;padding:24px;text-align:center;margin-bottom:28px;">
            <span style="font-size:36px;font-weight:700;color:#1B3A6B;letter-spacing:10px;">{code}</span>
          </div>

          <p style="color:#A0AEC0;font-size:12px;margin:0;line-height:1.6;">
            Si vous n'avez pas demandé ce code, ignorez cet email.
            Votre compte reste sécurisé.
          </p>
        </div>

        <div style="background:#F8FAFC;padding:16px 32px;border-top:1px solid #F0F4F8;">
          <p style="color:#A0AEC0;font-size:11px;margin:0;text-align:center;">
            Facilim · Données hébergées en France · Conforme RGPD
          </p>
        </div>

      </div>
    </body>
    </html>
    """

    payload = {
        "sender":      {"name": settings.brevo_sender_name, "email": settings.brevo_sender_email},
        "to":          [{"email": recipient_email}],
        "subject":     subject,
        "htmlContent": html_body,
        "textContent": f"Votre code de connexion Facilim : {code}\n\nValable 10 minutes.",
    }
    headers = {
        "api-key":      settings.brevo_api_key,
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(_BREVO_API_URL, json=payload, headers=headers, timeout=10)
        if resp.status_code in (200, 201):
            logger.info(f"Code de vérification envoyé à {recipient_email}")
            return True
        else:
            logger.error(f"Échec envoi email à {recipient_email} : {resp.status_code} {resp.text}")
            return False

    except Exception as e:
        logger.error(f"Échec envoi email à {recipient_email} : {e}")
        return False


def send_dossier_pdf(
    recipient_email: str,
    pdf_bytes: bytes,
    dossier_id: str,
    cerfa_bytes: bytes | None = None,
    pch_bytes: bytes | None = None,
    rapo_bytes: bytes | None = None,
) -> bool:
    """
    Envoie le dossier MDPH complété en pièce jointe PDF à la famille.

    Args:
        recipient_email : Adresse email de la famille.
        pdf_bytes       : Contenu binaire du fichier PDF.
        dossier_id      : Identifiant du dossier (pour le nom du fichier).

    Returns:
        True si l'email a été envoyé, False en cas d'échec.
    """
    short_id = dossier_id[:8]
    subject  = f"Votre dossier MDPH est prêt — Facilim (réf. {short_id})"

    html_body = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head><meta charset="UTF-8"></head>
    <body style="margin:0;padding:0;background:#F0F4F8;font-family:Inter,Arial,sans-serif;">
      <div style="max-width:520px;margin:40px auto;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 16px rgba(0,0,0,0.08);">

        <div style="background:#1B3A6B;padding:24px 32px;display:flex;align-items:center;gap:12px;">
          <div style="width:36px;height:36px;background:#2ECC9A;border-radius:8px;display:inline-flex;align-items:center;justify-content:center;font-weight:700;font-size:16px;color:#0F3D2E;">F</div>
          <span style="color:#ffffff;font-size:20px;font-weight:600;margin-left:10px;">Facilim</span>
        </div>

        <div style="padding:32px;">
          <p style="color:#1A202C;font-size:16px;font-weight:600;margin:0 0 12px;">
            Votre dossier MDPH est complété
          </p>
          <p style="color:#718096;font-size:14px;margin:0 0 20px;line-height:1.7;">
            Bonjour,<br/><br/>
            Votre dossier MDPH a été complété grâce aux informations que vous avez transmises.
            Vous trouverez en pièce jointe le document PDF récapitulatif.<br/><br/>
            Conservez ce document précieusement — il contient l'ensemble des éléments
            de votre dossier.
          </p>

          <div style="background:#F0FFF4;border:1px solid #2ECC9A;border-radius:10px;padding:16px 20px;margin-bottom:24px;">
            <p style="margin:0;color:#276749;font-size:13px;font-weight:600;">
              Référence dossier : {short_id}
            </p>
          </div>

          <p style="color:#A0AEC0;font-size:12px;margin:0;line-height:1.6;">
            Ce message a été généré automatiquement par Facilim.<br/>
            Pour toute question, contactez la personne qui vous accompagne.
          </p>
        </div>

        <div style="background:#F8FAFC;padding:16px 32px;border-top:1px solid #F0F4F8;">
          <p style="color:#A0AEC0;font-size:11px;margin:0;text-align:center;">
            Facilim · Données hébergées en France · Conforme RGPD
          </p>
        </div>

      </div>
    </body>
    </html>
    """

    attachments = [
        {
            "content": base64.b64encode(pdf_bytes).decode(),
            "name":    f"recapitulatif_facilim_{short_id}.pdf",
        }
    ]
    if cerfa_bytes:
        attachments.append({
            "content": base64.b64encode(cerfa_bytes).decode(),
            "name":    f"cerfa_15692_prefilled_{short_id}.pdf",
        })
    if pch_bytes:
        attachments.append({
            "content": base64.b64encode(pch_bytes).decode(),
            "name":    f"pch_parentalite_{short_id}.pdf",
        })
    if rapo_bytes:
        attachments.append({
            "content": base64.b64encode(rapo_bytes).decode(),
            "name":    f"lettre_rapo_{short_id}.pdf",
        })

    payload = {
        "sender":      {"name": settings.brevo_sender_name, "email": settings.brevo_sender_email},
        "to":          [{"email": recipient_email}],
        "subject":     subject,
        "htmlContent": html_body,
        "textContent": "Votre dossier MDPH est complété. Veuillez consulter la pièce jointe PDF.",
        "attachment":  attachments,
    }
    headers = {
        "api-key":      settings.brevo_api_key,
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(_BREVO_API_URL, json=payload, headers=headers, timeout=30)
        if resp.status_code in (200, 201):
            logger.info(f"Dossier PDF envoyé à {recipient_email} | dossier={dossier_id}")
            return True
        else:
            logger.error(f"Échec envoi PDF à {recipient_email} : {resp.status_code} {resp.text}")
            return False

    except Exception as e:
        logger.error(f"Échec envoi PDF à {recipient_email} : {e}")
        return False


def send_contact_notification(
    prenom: str,
    nom: str,
    email: str,
    structure: str,
    type_structure: str,
    message: str,
    notify_to: str = "nasskamli@gmail.com",
) -> bool:
    """
    Envoie une notification interne quand quelqu'un remplit le formulaire
    de contact de la homepage Facilim.

    Returns:
        True si l'email a été envoyé, False en cas d'échec.
    """
    subject = f"[Facilim] Contact : {prenom} {nom} — {structure}"

    html_body = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head><meta charset="UTF-8"></head>
    <body style="margin:0;padding:0;background:#F0F4F8;font-family:Inter,Arial,sans-serif;">
      <div style="max-width:520px;margin:40px auto;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 16px rgba(0,0,0,0.08);">

        <div style="background:#1B3A6B;padding:24px 32px;">
          <div style="display:inline-flex;align-items:center;gap:10px;">
            <div style="width:36px;height:36px;background:#2ECC9A;border-radius:8px;display:inline-flex;align-items:center;justify-content:center;font-weight:700;font-size:16px;color:#0F3D2E;">F</div>
            <span style="color:#ffffff;font-size:20px;font-weight:600;margin-left:10px;">Facilim — Nouveau contact</span>
          </div>
        </div>

        <div style="padding:32px;">
          <table style="width:100%;border-collapse:collapse;font-size:14px;color:#1A202C;">
            <tr><td style="padding:6px 0;color:#718096;width:120px;">Prénom</td><td style="padding:6px 0;font-weight:500;">{prenom}</td></tr>
            <tr><td style="padding:6px 0;color:#718096;">Nom</td><td style="padding:6px 0;font-weight:500;">{nom}</td></tr>
            <tr><td style="padding:6px 0;color:#718096;">Email</td><td style="padding:6px 0;"><a href="mailto:{email}" style="color:#1B3A6B;">{email}</a></td></tr>
            <tr><td style="padding:6px 0;color:#718096;">Structure</td><td style="padding:6px 0;">{structure}</td></tr>
            <tr><td style="padding:6px 0;color:#718096;">Type</td><td style="padding:6px 0;">{type_structure}</td></tr>
          </table>

          <div style="margin-top:24px;background:#F8FAFC;border-left:3px solid #2ECC9A;padding:16px 20px;border-radius:0 8px 8px 0;">
            <p style="margin:0 0 6px;font-size:12px;font-weight:600;color:#718096;text-transform:uppercase;letter-spacing:.5px;">Message</p>
            <p style="margin:0;font-size:14px;color:#1A202C;line-height:1.7;white-space:pre-wrap;">{message}</p>
          </div>
        </div>

        <div style="background:#F8FAFC;padding:16px 32px;border-top:1px solid #F0F4F8;">
          <p style="color:#A0AEC0;font-size:11px;margin:0;text-align:center;">
            Facilim · Données hébergées en France · Conforme RGPD
          </p>
        </div>

      </div>
    </body>
    </html>
    """

    text_body = (
        f"Nouveau contact via facilim.fr\n\n"
        f"Prénom    : {prenom}\n"
        f"Nom       : {nom}\n"
        f"Email     : {email}\n"
        f"Structure : {structure}\n"
        f"Type      : {type_structure}\n\n"
        f"Message :\n{message}"
    )

    payload = {
        "sender":      {"name": settings.brevo_sender_name, "email": settings.brevo_sender_email},
        "to":          [{"email": notify_to}],
        "replyTo":     {"email": email, "name": f"{prenom} {nom}"},
        "subject":     subject,
        "htmlContent": html_body,
        "textContent": text_body,
    }
    headers = {
        "api-key":      settings.brevo_api_key,
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(_BREVO_API_URL, json=payload, headers=headers, timeout=10)
        if resp.status_code in (200, 201):
            logger.info(f"[CONTACT] Notification envoyée à {notify_to} pour {email}")
            return True
        else:
            logger.error(f"[CONTACT] Échec notification : {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        logger.error(f"[CONTACT] Échec notification : {e}")
        return False
