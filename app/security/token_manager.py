"""
app/security/token_manager.py — Gestion des tokens JWT et sessions.

Deux types de tokens :
  1. JWT Dashboard ESSMS : stateful + JWT, révocable via DB
  2. Token WhatsApp : mapping stateless (phone_hash, dossier_id) via Redis/SQLite
  3. Token portail sécurisé : JWT à usage unique (one-time-token)
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("facilim.security.token")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(dt: datetime) -> str:
    return dt.isoformat()


# ── JWT Dashboard ───────────────────────────────────────────────────────────

def create_dashboard_token(
    utilisateur_id: str,
    email: str,
    role: str,
    organisation_id: str | None,
    secret_key: str,
    algorithm: str = "HS256",
    expire_minutes: int = 480,
) -> tuple[str, datetime]:
    """Crée un JWT signé pour le Dashboard ESSMS. Retourne (token, expire_at)."""
    try:
        import jwt as pyjwt
    except ImportError:
        raise RuntimeError("PyJWT non installé — pip install PyJWT")

    expire_at = _now() + timedelta(minutes=expire_minutes)
    payload = {
        "sub": utilisateur_id,
        "email": email,
        "role": role,
        "org_id": organisation_id,
        "iat": int(_now().timestamp()),
        "exp": int(expire_at.timestamp()),
        "jti": str(uuid.uuid4()),  # JWT ID unique pour révocation
    }
    token = pyjwt.encode(payload, secret_key, algorithm=algorithm)
    return token, expire_at


def verify_dashboard_token(
    token: str,
    secret_key: str,
    algorithm: str = "HS256",
) -> dict[str, Any] | None:
    """Vérifie et décode un JWT Dashboard. Retourne le payload ou None."""
    try:
        import jwt as pyjwt
        payload = pyjwt.decode(token, secret_key, algorithms=[algorithm])
        return payload
    except Exception as e:
        logger.warning(f"[TOKEN] JWT invalide : {e}")
        return None


def hash_token(token: str) -> str:
    """Hash SHA256 d'un token pour stockage en base (ne jamais stocker le token brut)."""
    return hashlib.sha256(token.encode()).hexdigest()


# ── Token portail sécurisé (one-time) ──────────────────────────────────────

def generate_secure_token(byte_length: int = 32) -> str:
    """Token cryptographiquement sûr pour portail HDS."""
    return secrets.token_urlsafe(byte_length)


# ── Mapping WhatsApp ────────────────────────────────────────────────────────

def build_whatsapp_session_key(phone_number: str) -> str:
    """Clé Redis/SQLite pour l'état conversationnel WhatsApp."""
    normalized = phone_number.strip().replace(" ", "").replace("+", "")
    return f"wa:session:{normalized}"


def build_whatsapp_dossier_key(phone_number: str) -> str:
    """Clé Redis/SQLite pour le dossier actif lié à ce numéro."""
    normalized = phone_number.strip().replace(" ", "").replace("+", "")
    return f"wa:dossier:{normalized}"


# ── Validation d'un token de vérification email ────────────────────────────

def generate_email_verification_token() -> str:
    return secrets.token_urlsafe(24)
