"""
app/audit/consent_history.py — Historique légal des consentements.

Le consentement est le fondement légal de tout traitement de données.
Ce module garantit que chaque état de consentement est :
  - traçable (qui, quand, comment, pour quoi)
  - réversible (retrait possible à tout moment)
  - auditable (preuve juridique conservée)
  - compatible FALC (texte simplifié fourni à l'usager)
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("facilim.audit.consent")

# Texte de consentement affiché à l'usager (version 1.0)
# Compatible FALC — version simplifiée obligatoire
CONSENT_TEXT_V1_FR = """
Facilim va utiliser vos informations pour vous aider à constituer votre dossier MDPH.

Vos données seront utilisées pour :
✓ Préparer votre dossier MDPH
✓ Vous envoyer des rappels et suivre votre dossier
✓ Partager votre dossier avec la MDPH de votre département

Vos droits :
• Vous pouvez demander à voir vos données à tout moment
• Vous pouvez demander à corriger vos données
• Vous pouvez demander à effacer vos données
• Vous pouvez arrêter d'utiliser Facilim à tout moment

Vos données médicales sont protégées et chiffrées.
Elles ne seront jamais vendues.

Pour accepter, répondez OUI.
Pour refuser, répondez NON.
""".strip()

CONSENT_TEXT_V1_HASH = hashlib.sha256(CONSENT_TEXT_V1_FR.encode("utf-8")).hexdigest()

CONSENT_TEXT_V1_FALC = """
Facilim va garder vos informations.
Ces informations servent à faire votre dossier MDPH.

Si vous dites OUI :
• On garde vos informations.
• On vous envoie des messages pour suivre votre dossier.

Si vous dites NON :
• On ne garde rien.
• On ne peut pas vous aider.

Vous pouvez dire NON quand vous voulez.

Tapez OUI pour accepter.
Tapez NON pour refuser.
""".strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_consent_record(
    usager_id: str,
    canal: str,
    finalites: dict[str, bool],
    version_politique: str = "1.0",
    ip_address: str | None = None,
    representant_id: str | None = None,
    db_conn: Any | None = None,
) -> str:
    """
    Enregistre un nouveau consentement.

    Args:
        usager_id: ID de l'usager
        canal: Canal de recueil (whatsapp|sms|portail|papier)
        finalites: Dict des finalités accordées
        version_politique: Version de la politique de confidentialité
        ip_address: IP de recueil (portail web)
        representant_id: ID du représentant légal si applicable
        db_conn: Connexion SQLite

    Returns:
        consent_id
    """
    consent_id = str(uuid.uuid4())
    now = _now_iso()
    donne_par_representant = 1 if representant_id else 0

    record = {
        "id":                           consent_id,
        "usager_id":                    usager_id,
        "version_politique":            version_politique,
        "consent_traitement_dossier":   1 if finalites.get("traitement_dossier", False) else 0,
        "consent_partage_mdph":         1 if finalites.get("partage_mdph", False) else 0,
        "consent_partage_essms":        1 if finalites.get("partage_essms", False) else 0,
        "consent_notifications":        1 if finalites.get("notifications", False) else 0,
        "consent_amelioration_service": 1 if finalites.get("amelioration_service", False) else 0,
        "canal_recueil":                canal,
        "ip_address":                   ip_address,
        "user_agent":                   None,
        "texte_affiche_hash":           CONSENT_TEXT_V1_HASH,
        "accorde_le":                   now,
        "expire_le":                    None,
        "retire_le":                    None,
        "donne_par_representant":       donne_par_representant,
        "representant_id":              representant_id,
        "created_at":                   now,
    }

    logger.info(f"[CONSENT] Consentement enregistré | usager={usager_id[:8]} | canal={canal}")

    if db_conn is not None:
        db_conn.execute(
            """
            INSERT INTO consentements
                (id, usager_id, version_politique,
                 consent_traitement_dossier, consent_partage_mdph, consent_partage_essms,
                 consent_notifications, consent_amelioration_service,
                 canal_recueil, ip_address, user_agent, texte_affiche_hash,
                 accorde_le, expire_le, retire_le,
                 donne_par_representant, representant_id, created_at)
            VALUES
                (:id, :usager_id, :version_politique,
                 :consent_traitement_dossier, :consent_partage_mdph, :consent_partage_essms,
                 :consent_notifications, :consent_amelioration_service,
                 :canal_recueil, :ip_address, :user_agent, :texte_affiche_hash,
                 :accorde_le, :expire_le, :retire_le,
                 :donne_par_representant, :representant_id, :created_at)
            """,
            record,
        )
        # Audit immuable
        db_conn.execute(
            """
            INSERT INTO audit_consentements
                (id, consentement_id, usager_id, action, version_politique,
                 details_json, canal, ip_address, created_at)
            VALUES (?, ?, ?, 'DONNE', ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()), consent_id, usager_id,
                version_politique,
                json.dumps(finalites, ensure_ascii=False),
                canal, ip_address, now,
            ),
        )

    return consent_id


def withdraw_consent(
    usager_id: str,
    consentement_id: str,
    raison: str | None = None,
    db_conn: Any | None = None,
) -> None:
    """Retrait du consentement — conserve la trace, marque retire_le."""
    now = _now_iso()
    logger.info(f"[CONSENT] Retrait consentement | usager={usager_id[:8]}")
    if db_conn is not None:
        db_conn.execute(
            "UPDATE consentements SET retire_le = ? WHERE id = ? AND usager_id = ?",
            (now, consentement_id, usager_id),
        )
        db_conn.execute(
            """
            INSERT INTO audit_consentements
                (id, consentement_id, usager_id, action, version_politique,
                 details_json, canal, ip_address, created_at)
            VALUES (?, ?, ?, 'RETIRE', '1.0', ?, NULL, NULL, ?)
            """,
            (
                str(uuid.uuid4()), consentement_id, usager_id,
                json.dumps({"raison": raison}),
                now,
            ),
        )


def get_active_consent(usager_id: str, db_conn: Any) -> dict[str, Any] | None:
    """Retourne le consentement actif le plus récent pour un usager."""
    row = db_conn.execute(
        """
        SELECT * FROM consentements
        WHERE usager_id = ? AND retire_le IS NULL
        ORDER BY accorde_le DESC LIMIT 1
        """,
        (usager_id,),
    ).fetchone()
    return dict(row) if row else None


def has_valid_consent(usager_id: str, finalite: str, db_conn: Any) -> bool:
    """Vérifie qu'un usager a donné son consentement pour une finalité."""
    consent = get_active_consent(usager_id, db_conn)
    if not consent:
        return False
    column_map = {
        "traitement_dossier":   "consent_traitement_dossier",
        "partage_mdph":         "consent_partage_mdph",
        "partage_essms":        "consent_partage_essms",
        "notifications":        "consent_notifications",
        "amelioration_service": "consent_amelioration_service",
    }
    col = column_map.get(finalite)
    return bool(col and consent.get(col, 0))


def get_consent_message_for_whatsapp() -> str:
    """Message de demande de consentement formaté pour WhatsApp."""
    return (
        "Bonjour et bienvenue sur Facilim 👋\n\n"
        "Avant de commencer, j'ai besoin de votre accord.\n\n"
        + CONSENT_TEXT_V1_FALC
    )
