"""
auth.py — Système d'authentification pour l'interface Facilim.

Flux en deux étapes :
  1. POST /auth/login  → vérifie email + mot de passe,
                         génère un code à 6 chiffres et l'envoie par email.
  2. POST /auth/verify → vérifie le code, crée une session (cookie sécurisé),
                         l'interface redirige ensuite vers /dashboard.
  3. POST /auth/logout → invalide la session côté serveur.

Sessions et codes stockés en mémoire (simple dict Python).
Suffisant en développement avec un seul éducateur.
En production : migrer vers Redis avec TTL automatique.
"""

import logging
import secrets
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Cookie, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import get_settings
from services.email_client import generate_code, send_verification_code

logger   = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/auth", tags=["Auth"])

# ─── Durées de vie ───────────────────────────────────────────────────────────
_CODE_DURATION    = timedelta(minutes=10)   # Le code expire après 10 minutes
_SESSION_DURATION = timedelta(hours=8)      # La session dure 8 heures

# ─── Stockages en mémoire ────────────────────────────────────────────────────
# Codes en attente de validation
#   { email: { "code": str, "expires_at": datetime } }
_pending_codes: dict[str, dict] = {}

# Sessions actives
#   { token: { "email": str, "created_at": datetime } }
_active_sessions: dict[str, dict] = {}


# ─── Modèles de requête ──────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email:    str
    password: str

class VerifyRequest(BaseModel):
    email: str
    code:  str


# ─── Utilitaires ─────────────────────────────────────────────────────────────

def is_valid_session(token: str | None) -> bool:
    """
    Vérifie si un token de session est valide et non expiré.
    Nettoie automatiquement les sessions périmées.
    """
    if not token or token not in _active_sessions:
        return False

    session = _active_sessions[token]
    expiry  = session["created_at"] + _SESSION_DURATION

    if datetime.now(timezone.utc) > expiry:
        del _active_sessions[token]
        logger.debug(f"Session expirée supprimée | email={session['email']}")
        return False

    return True


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post(
    "/login",
    summary="Étape 1 — Vérification email + mot de passe",
)
async def login(body: LoginRequest):
    """
    Vérifie les identifiants configurés dans .env.
    En cas de succès : génère un code à 6 chiffres et l'envoie par email Brevo.
    Retourne 401 si les identifiants sont incorrects.
    Retourne 503 si l'email ne peut pas être envoyé.
    """
    # Liste des comptes autorisés (compte principal + compte secondaire optionnel)
    comptes_autorises = [
        (settings.auth_email.lower(), settings.auth_password),
    ]
    if settings.auth_email_2 and settings.auth_password_2:
        comptes_autorises.append((settings.auth_email_2.lower(), settings.auth_password_2))

    if (body.email.lower(), body.password) not in comptes_autorises:
        logger.warning(f"Échec de connexion | email_saisi={body.email}")
        raise HTTPException(
            status_code=401,
            detail="Email ou mot de passe incorrect.",
        )

    # Génération du code et mémorisation avec horodatage d'expiration
    code = generate_code()
    _pending_codes[body.email.lower()] = {
        "code":       code,
        "expires_at": datetime.now(timezone.utc) + _CODE_DURATION,
    }

    # Envoi de l'email de vérification via Brevo
    sent = send_verification_code(recipient_email=body.email, code=code)
    if not sent:
        # On supprime le code en mémoire si l'email n'est pas parti
        del _pending_codes[body.email.lower()]
        logger.error(f"Impossible d'envoyer le code à {body.email}")
        raise HTTPException(
            status_code=503,
            detail="Impossible d'envoyer l'email de vérification. Réessayez dans quelques instants.",
        )

    logger.info(f"Code de vérification envoyé | email={body.email}")
    return {
        "status":  "code_sent",
        "message": "Un code de vérification a été envoyé à votre adresse email.",
    }


@router.post(
    "/verify",
    summary="Étape 2 — Vérification du code à 6 chiffres",
)
async def verify(body: VerifyRequest):
    """
    Vérifie le code reçu par email.
    En cas de succès : crée une session et retourne un cookie httpOnly sécurisé.
    Le cookie (session_token) est lu automatiquement par le navigateur à chaque requête.
    """
    email  = body.email.lower()
    pending = _pending_codes.get(email)

    if not pending:
        raise HTTPException(
            status_code=400,
            detail="Aucun code en attente pour cet email. Veuillez vous reconnecter.",
        )

    if datetime.now(timezone.utc) > pending["expires_at"]:
        del _pending_codes[email]
        raise HTTPException(
            status_code=400,
            detail="Le code a expiré (validité : 10 minutes). Veuillez vous reconnecter.",
        )

    if pending["code"] != body.code.strip():
        logger.warning(f"Code incorrect | email={email}")
        raise HTTPException(
            status_code=401,
            detail="Code incorrect. Vérifiez votre boîte email.",
        )

    # ── Code valide ──────────────────────────────────────────────────────────
    del _pending_codes[email]  # Code à usage unique — on le supprime immédiatement

    # Génération d'un token de session aléatoire (256 bits d'entropie)
    session_token = secrets.token_urlsafe(32)
    _active_sessions[session_token] = {
        "email":      email,
        "created_at": datetime.now(timezone.utc),
    }

    logger.info(f"Connexion réussie | email={email}")

    # Cookie httpOnly : inaccessible en JavaScript (protection XSS)
    # SameSite=lax : protection CSRF basique
    response = JSONResponse(content={"status": "authenticated"})
    response.set_cookie(
        key      = "session_token",
        value    = session_token,
        httponly = True,
        samesite = "lax",
        max_age  = int(_SESSION_DURATION.total_seconds()),
    )
    return response


@router.post(
    "/logout",
    summary="Déconnexion",
)
async def logout(session_token: str | None = Cookie(default=None)):
    """
    Invalide la session côté serveur et supprime le cookie côté navigateur.
    """
    if session_token and session_token in _active_sessions:
        email = _active_sessions[session_token]["email"]
        del _active_sessions[session_token]
        logger.info(f"Déconnexion | email={email}")

    response = JSONResponse(content={"status": "logged_out"})
    response.delete_cookie("session_token")
    return response
