"""
test_smtp.py — Diagnostic de la connexion SMTP Brevo.
Exécuter avec : python test_smtp.py
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import get_settings

settings = get_settings()

print("=" * 55)
print("  Diagnostic SMTP Brevo")
print("=" * 55)
smtp_login = settings.brevo_smtp_login or settings.brevo_sender_email

print(f"  Host       : smtp-relay.brevo.com")
print(f"  Port       : 587")
print(f"  Login SMTP : {smtp_login}")
print(f"  Expéditeur : {settings.brevo_sender_email}")
print(f"  Clé SMTP   : {settings.brevo_smtp_key[:12]}...")
print("=" * 55)

try:
    print("\n[1/4] Connexion au serveur SMTP...")
    server = smtplib.SMTP("smtp-relay.brevo.com", 587, timeout=10)
    print("      OK — Connecté")

    print("[2/4] Envoi EHLO...")
    server.ehlo()
    print("      OK")

    print("[3/4] Activation STARTTLS (chiffrement)...")
    server.starttls()
    print("      OK")

    print("[4/4] Authentification...")
    server.login(smtp_login, settings.brevo_smtp_key)
    print("      OK — Authentifié avec succès !")

    # Envoi d'un email de test
    print("\n  Envoi d'un email de test à nasskamli@gmail.com...")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Test SMTP Facilim — connexion OK"
    msg["From"]    = f"{settings.brevo_sender_name} <{settings.brevo_sender_email}>"
    msg["To"]      = settings.brevo_sender_email
    msg.attach(MIMEText("Bravo ! La connexion SMTP Brevo fonctionne.", "plain", "utf-8"))

    server.sendmail(settings.brevo_sender_email, settings.brevo_sender_email, msg.as_string())
    server.quit()

    print("\n  SUCCÈS — Email envoyé ! Vérifie ta boîte mail.")

except smtplib.SMTPAuthenticationError as e:
    print(f"\n  ERREUR D'AUTHENTIFICATION : {e}")
    print("  → La clé SMTP est incorrecte ou expirée.")
    print("  → Va dans Brevo > SMTP et API > Générer une nouvelle clé.")

except smtplib.SMTPConnectError as e:
    print(f"\n  ERREUR DE CONNEXION : {e}")
    print("  → Le port 587 est peut-être bloqué par ton réseau ou antivirus.")

except TimeoutError:
    print("\n  TIMEOUT — Impossible de joindre smtp-relay.brevo.com:587")
    print("  → Port 587 bloqué par le firewall ou le réseau.")

except Exception as e:
    print(f"\n  ERREUR INATTENDUE : {type(e).__name__}: {e}")
