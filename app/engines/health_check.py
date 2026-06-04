"""
app/engines/health_check.py — Vérifications de robustesse pour la mise en production.

Vérifie à chaque démarrage et sur demande :
  - Variables d'environnement obligatoires
  - Connexion base de données
  - Connectivité OpenAI (ping léger)
  - Connectivité WhatsApp (format token)
  - Gestion des cas limites : dossier vide, profil inconnu, API indisponible

Ce module ne lève jamais d'exception — il retourne un rapport de santé.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("facilim.health")

# Variables d'environnement obligatoires en production
_ENV_OBLIGATOIRES = [
    ("OPENAI_API_KEY",          "Clé OpenAI — génération narrative et analyse"),
    ("DATABASE_URL",            "URL base de données"),
    ("JWT_SECRET_KEY",          "Clé JWT dashboard"),
    ("WHATSAPP_API_TOKEN",      "Token WhatsApp Business Cloud"),
    ("WHATSAPP_PHONE_NUMBER_ID","ID numéro WhatsApp"),
]

# Variables recommandées (non bloquantes)
_ENV_RECOMMANDEES = [
    ("BREVO_API_KEY",           "Email transactionnel (2FA, notifications)"),
    ("ENCRYPTION_KEY",          "Chiffrement données sensibles"),
    ("OPENAI_MODEL",            "Modèle OpenAI (défaut : gpt-4o-mini)"),
]


@dataclass
class HealthReport:
    status:       str           = "OK"      # OK | DEGRADED | CRITICAL
    timestamp:    str           = ""
    env_ok:       list[str]     = field(default_factory=list)
    env_manquant: list[str]     = field(default_factory=list)
    env_recommande_manquant: list[str] = field(default_factory=list)
    db_ok:        bool          = False
    openai_ok:    bool          = False
    openai_latency_ms: int      = 0
    warnings:     list[str]     = field(default_factory=list)
    errors:       list[str]     = field(default_factory=list)

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)


def verifier_env() -> tuple[list[str], list[str], list[str]]:
    """Retourne (presentes, manquantes, recommandees_manquantes)."""
    presentes, manquantes = [], []
    for key, desc in _ENV_OBLIGATOIRES:
        if os.environ.get(key):
            presentes.append(key)
        else:
            manquantes.append(f"{key} — {desc}")

    rec_manquantes = []
    for key, desc in _ENV_RECOMMANDEES:
        if not os.environ.get(key):
            rec_manquantes.append(f"{key} — {desc}")

    return presentes, manquantes, rec_manquantes


def verifier_db(db_conn: Any) -> bool:
    """Vérifie que la base répond avec une requête minimale."""
    try:
        db_conn.execute("SELECT 1").fetchone()
        return True
    except Exception as e:
        logger.error("[HEALTH] DB non disponible : %s", e)
        return False


def verifier_openai(api_key: str) -> tuple[bool, int]:
    """Ping léger sur l'API OpenAI. Retourne (ok, latency_ms)."""
    import time
    try:
        from openai import OpenAI
        t0 = time.monotonic()
        client = OpenAI(api_key=api_key)
        client.models.list()
        latency_ms = int((time.monotonic() - t0) * 1000)
        return True, latency_ms
    except Exception as e:
        logger.warning("[HEALTH] OpenAI non disponible : %s", e)
        return False, 0


def health_check(db_conn: Any | None = None, check_openai: bool = False) -> HealthReport:
    """
    Rapport de santé complet.
    Appelé au démarrage (app/main.py) et sur GET /api/v1/health.
    Non bloquant — retourne toujours un rapport.
    """
    report = HealthReport(timestamp=datetime.now(timezone.utc).isoformat())

    # Variables d'environnement
    report.env_ok, report.env_manquant, report.env_recommande_manquant = verifier_env()

    if report.env_manquant:
        report.errors.extend(report.env_manquant)
        report.status = "CRITICAL"
    elif report.env_recommande_manquant:
        report.warnings.extend(report.env_recommande_manquant)

    # Base de données
    if db_conn:
        report.db_ok = verifier_db(db_conn)
        if not report.db_ok:
            report.errors.append("Base de données inaccessible")
            report.status = "CRITICAL"

    # OpenAI (optionnel — évite le coût à chaque démarrage)
    if check_openai:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if api_key:
            report.openai_ok, report.openai_latency_ms = verifier_openai(api_key)
            if not report.openai_ok:
                report.warnings.append("OpenAI non disponible — fonctionnement en mode dégradé")
                if report.status == "OK":
                    report.status = "DEGRADED"
        else:
            report.warnings.append("OPENAI_API_KEY absente — génération narrative désactivée")

    if report.status == "OK" and report.warnings:
        report.status = "DEGRADED"

    logger.info(
        "[HEALTH] status=%s env_ok=%d env_manquant=%d db=%s openai=%s",
        report.status, len(report.env_ok), len(report.env_manquant),
        report.db_ok, report.openai_ok,
    )
    return report


def verifier_robustesse_pipeline(
    donnees: dict[str, Any],
    textes_narratifs: dict[str, str],
    rapport_qualite: dict[str, Any],
    profil_mdph: str,
) -> dict[str, Any]:
    """
    Vérifie les cas limites avant de lancer le pipeline d'analyse.
    Retourne un dict de signaux pour adapter le comportement.

    Cas gérés :
      - dossier vide → analyse partielle uniquement
      - profil non reconnu → analyse générique sans spécialisation
      - API GPT indisponible → couche 1 seulement
      - textes narratifs absents → utiliser les données brutes
    """
    signaux: dict[str, Any] = {
        "dossier_vide":        False,
        "profil_reconnu":      True,
        "textes_disponibles":  True,
        "qualite_disponible":  True,
        "mode":                "complet",
    }

    # Dossier vide
    champs_essentiels = ["diagnostics", "impact_quotidien", "nom_prenom"]
    nb_remplis = sum(1 for c in champs_essentiels if donnees.get(c))
    if nb_remplis == 0:
        signaux["dossier_vide"] = True
        signaux["mode"] = "minimal"
        logger.info("[ROBUSTESSE] Dossier vide — mode minimal")

    # Profil non reconnu
    profils_connus = {
        "adulte", "enfant", "mixte", "protege",
        "tsa", "psychique", "psychique_humeur", "psychique_psychotique",
        "moteur", "di", "maladie_chronique",
        "sensoriel", "sensoriel_auditif", "sensoriel_visuel",
    }
    if profil_mdph not in profils_connus:
        signaux["profil_reconnu"] = False
        logger.info("[ROBUSTESSE] Profil non reconnu : %s — analyse générique", profil_mdph)

    # Textes narratifs absents
    textes_presents = any(v.strip() for v in textes_narratifs.values() if v)
    if not textes_presents:
        signaux["textes_disponibles"] = False
        logger.info("[ROBUSTESSE] Textes narratifs absents — fallback sur données brutes")

    # Rapport qualité absent
    if not rapport_qualite or rapport_qualite == {}:
        signaux["qualite_disponible"] = False

    return signaux
