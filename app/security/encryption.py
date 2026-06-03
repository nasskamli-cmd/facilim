"""
app/security/encryption.py — Chiffrement des données sensibles au repos.

Utilise Fernet (AES-128-CBC + HMAC-SHA256) de la bibliothèque cryptography.
Les données médicales et PII sont préfixées ENC:: pour distinguer
les valeurs chiffrées des valeurs en clair (migrations progressives).

En production : stocker la clé dans un KMS (AWS KMS, GCP KMS, HashiCorp Vault).
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from typing import Any

logger = logging.getLogger("facilim.security.encryption")

_ENCRYPTED_PREFIX = "ENC::"
_fernet: Any = None  # Instance Fernet lazy-initialized


def initialize(encryption_key: str) -> None:
    """Configure le moteur de chiffrement. Appeler au démarrage."""
    global _fernet
    if not encryption_key:
        logger.warning(
            "[ENCRYPTION] Aucune clé de chiffrement configurée — "
            "les données sensibles ne seront PAS chiffrées. INTERDIT EN PRODUCTION."
        )
        return
    try:
        from cryptography.fernet import Fernet

        # Normalisation : re-ajouter le padding base64 si Railway l'a tronqué
        key_stripped = encryption_key.strip().rstrip("=")
        padding     = (4 - len(key_stripped) % 4) % 4
        key_padded  = (key_stripped + "=" * padding).encode()

        decoded = base64.urlsafe_b64decode(key_padded)
        if len(decoded) != 32:
            raise ValueError(
                f"Clé Fernet invalide : {len(decoded)} bytes (32 attendus)."
            )
        # Reconstruire la clé correctement paddée pour Fernet
        proper_key = base64.urlsafe_b64encode(decoded)
        _fernet = Fernet(proper_key)
        logger.info("[ENCRYPTION] Moteur Fernet initialisé.")
    except ImportError:
        logger.error(
            "[ENCRYPTION] cryptography non installée — pip install cryptography"
        )


def encrypt(value: str | None) -> str | None:
    """Chiffre une chaîne. Retourne None si value est None."""
    if value is None:
        return None
    if _fernet is None:
        return value  # mode dégradé : pas de chiffrement
    encrypted = _fernet.encrypt(value.encode("utf-8"))
    return _ENCRYPTED_PREFIX + encrypted.decode("ascii")


def decrypt(value: str | None) -> str | None:
    """Déchiffre une chaîne. Retourne None si value est None."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.startswith(_ENCRYPTED_PREFIX):
        return value  # pas chiffré ou mode dégradé
    if _fernet is None:
        logger.error("[ENCRYPTION] Tentative de déchiffrement sans clé configurée.")
        return "[DONNÉES CHIFFRÉES — CLÉ MANQUANTE]"
    try:
        payload = value[len(_ENCRYPTED_PREFIX):]
        return _fernet.decrypt(payload.encode("ascii")).decode("utf-8")
    except Exception as e:
        logger.error(f"[ENCRYPTION] Échec déchiffrement : {e}")
        return "[DONNÉES CORROMPUES]"


def hash_sha256(value: str) -> str:
    """Hash SHA256 déterministe pour indexation et preuves d'intégrité."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_phone(phone: str) -> str:
    """Hash déterministe du numéro de téléphone pour l'indexation sans PII."""
    normalized = phone.strip().replace(" ", "").replace("-", "")
    return hash_sha256(f"facilim:phone:{normalized}")


def is_encrypted(value: str | None) -> bool:
    return isinstance(value, str) and value.startswith(_ENCRYPTED_PREFIX)


def generate_reference(prefix: str = "FAC") -> str:
    """Génère une référence unique non-devinable."""
    random_part = base64.urlsafe_b64encode(os.urandom(6)).decode("ascii").upper()
    return f"{prefix}-{random_part}"
