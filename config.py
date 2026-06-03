"""
config.py — Centralisation de toutes les variables d'environnement.
Utilise pydantic-settings pour valider et typer la configuration au démarrage.
Les valeurs sont lues depuis un fichier .env ou les variables d'environnement système.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """
    Classe principale de configuration.
    Chaque attribut correspond à une variable d'environnement (insensible à la casse).
    Les champs sans valeur par défaut sont OBLIGATOIRES au démarrage.
    """

    # --- Clés API LLM ---
    openai_api_key: str
    openai_model: str = "gpt-4o"
    openai_anonymizer_model: str = "gpt-4o-mini"

    # --- WhatsApp Business Cloud API ---
    whatsapp_api_token: str
    whatsapp_phone_number_id: str
    whatsapp_verify_token: str = "mdph_verify"

    # --- Application ---
    app_env: str = "development"
    app_secret_key: str = "changeme-in-prod"
    log_level: str = "INFO"
    base_url: str = "https://facilim.fr"  # URL publique de l'app (domaine custom ou Railway)

    # --- Base de données ---
    database_url: str = "sqlite:///./mdph_dossiers.db"

    # --- Brevo (envoi d'emails transactionnels) ---
    brevo_api_key: str = ""
    brevo_smtp_key: str = ""
    brevo_smtp_login: str = ""
    brevo_sender_email: str = "noreply@facilim.fr"
    brevo_sender_name: str = "Facilim"

    # --- Interface personne qui accompagne — identifiants de connexion ---
    auth_email:    str = "admin@facilim.fr"
    auth_password: str = "changeme"

    # --- Compte secondaire optionnel (ex : conjoint, collègue) ---
    auth_email_2:    str = ""
    auth_password_2: str = ""

    # --- Quota dossiers actifs par compte ---
    # Nombre maximum de dossiers EN_COURS + INCOMPLET simultanément autorisés.
    # Passez cette valeur à 0 pour désactiver le quota.
    quota_dossiers_actifs: int = 10

    # --- Taille maximale des fichiers uploadés (photos + PDFs), en mégaoctets ---
    # S'applique à chaque requête entrante. Couvre les envois combinés.
    max_upload_size_mb: int = 50

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",   # ignore les nouvelles variables Railway (jwt_secret_key, auth_password_hash...)
    )


@lru_cache()
def get_settings() -> Settings:
    """
    Retourne une instance singleton de Settings.
    Le décorateur @lru_cache garantit que le fichier .env n'est lu qu'une seule fois.
    """
    return Settings()
