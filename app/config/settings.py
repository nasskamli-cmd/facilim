"""
app/config/settings.py — Configuration centralisée Facilim v2.

Toutes les variables d'environnement sont validées et typées au démarrage.
Compatible HDS : séparation des clés sensibles, logging de la config active.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("facilim.config")


class Settings(BaseSettings):

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Identité applicative ────────────────────────────────────────────────
    app_name: str = "Facilim"
    app_env: Literal["development", "staging", "production"] = "development"
    app_version: str = "2.0.0"
    app_secret_key: str = Field(default="changeme-in-prod-min-32-chars!!")
    base_url: str = "https://facilim.fr"
    log_level: str = "INFO"

    # ── LLM ────────────────────────────────────────────────────────────────
    openai_api_key: str
    openai_model: str = "gpt-4o"
    openai_model_fast: str = "gpt-4o-mini"
    openai_model_anonymizer: str = "gpt-4o-mini"

    # ── Base de données principale ──────────────────────────────────────────
    # SQLite pour dev, PostgreSQL en prod (changer uniquement cette URL)
    database_url: str = "sqlite:///./mdph_dossiers.db"
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # ── Redis (cache + sessions WhatsApp) ──────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    redis_ttl_session: int = 3600        # secondes
    redis_ttl_whatsapp_state: int = 7200  # session WhatsApp active

    # ── Chiffrement des données sensibles ──────────────────────────────────
    # Clé Fernet 32 bytes base64 — générer avec : Fernet.generate_key()
    # Fallback automatique sur AES_SECRET_KEY si ENCRYPTION_KEY absent (legacy Railway)
    encryption_key: str = ""

    # ── WhatsApp Business Cloud API ────────────────────────────────────────
    whatsapp_api_token: str
    whatsapp_phone_number_id: str
    whatsapp_verify_token: str = "facilim_webhook_v2"
    whatsapp_api_version: str = "v20.0"

    # ── SMS (ex : OVH Telecom ou Twilio) ───────────────────────────────────
    sms_provider: Literal["twilio", "ovh", "disabled"] = "disabled"
    sms_api_key: str = ""
    sms_api_secret: str = ""
    sms_sender: str = "Facilim"

    # ── Email (Brevo / SendGrid) ───────────────────────────────────────────
    brevo_api_key: str = ""
    brevo_smtp_key: str = ""
    brevo_smtp_login: str = ""
    brevo_sender_email: str = "noreply@facilim.fr"
    brevo_sender_name: str = "Facilim"
    # Boîte qui reçoit les demandes de renseignement du formulaire de contact.
    contact_email: str = "contactfacilim@gmail.com"
    # Jeton partagé protégeant le webhook d'email entrant (inbound parsing).
    inbound_email_secret: str = ""

    # ── Observabilité (Sentry) — suivi des erreurs en production ────────────
    # Vide = désactivé. On ne transmet jamais de donnée de santé brute (scrubbing).
    sentry_dsn: str = ""
    sentry_environment: str = "production"

    # ── Stockage documents ─────────────────────────────────────────────────
    storage_backend: Literal["local", "s3", "gcs"] = "local"
    storage_local_path: str = "./storage"
    s3_bucket: str = ""
    s3_region: str = "eu-west-3"
    s3_access_key: str = ""
    s3_secret_key: str = ""

    # ── Authentification Dashboard ESSMS ───────────────────────────────────
    # Les mots de passe sont stockés en hash bcrypt (rounds=12).
    # Générer : python -c "import bcrypt; print(bcrypt.hashpw(b'MOT_DE_PASSE', bcrypt.gensalt(12)).decode())"
    auth_email:          str = "admin@facilim.fr"
    auth_password_hash:  str = ""   # hash bcrypt — vide = compte désactivé
    auth_email_2:        str = ""
    auth_password_hash_2: str = ""  # hash bcrypt — vide = compte désactivé
    jwt_secret_key: str = Field(default="jwt-changeme-in-prod!!")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480  # 8 heures

    # ── Quotas et limites ──────────────────────────────────────────────────
    quota_dossiers_actifs: int = 10
    max_upload_size_mb: int = 25
    max_conversation_history: int = 50
    memory_summary_threshold: int = 20  # résumé déclenché quand l'historique dépasse ce seuil
    memory_window_size: int = 10        # messages récents conservés mot-à-mot après résumé

    # ── Recherche de structures géolocalisées (Règle Q60) ─────────────────
    google_places_api_key: str = ""     # laisser vide → fallback FINESS API

    # ── Human-in-the-loop ──────────────────────────────────────────────────
    ocr_confidence_threshold: float = 0.90  # < 90% → flag humain
    scoring_confidence_threshold: float = 0.75
    legal_confidence_threshold: float = 0.80

    # ── RGPD ───────────────────────────────────────────────────────────────
    rgpd_retention_days: int = 1825        # 5 ans (MDPH)
    rgpd_pii_purge_after_completion: bool = True
    consent_cookie_duration_days: int = 365

    # ── Notifications planifiées ───────────────────────────────────────────
    relance_delai_initial_jours: int = 7
    relance_delai_critique_jours: int = 30
    expiration_alerte_jours: int = 60

    @field_validator("app_secret_key", "jwt_secret_key")
    @classmethod
    def validate_secret_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("Les clés secrètes doivent faire au minimum 32 caractères.")
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def whatsapp_api_url(self) -> str:
        return (
            f"https://graph.facebook.com/{self.whatsapp_api_version}"
            f"/{self.whatsapp_phone_number_id}/messages"
        )


@lru_cache()
def get_settings() -> Settings:
    """Instance singleton des settings — lu une seule fois au démarrage."""
    s = Settings()
    logger.info(
        f"[CONFIG] env={s.app_env} | model={s.openai_model} | db={s.database_url[:30]}..."
    )
    return s
