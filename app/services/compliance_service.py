"""
app/services/compliance_service.py — Service de conformité RGPD.

Implémente les droits des personnes :
  - Droit d'accès (Article 15 RGPD)
  - Droit de rectification (Article 16)
  - Droit à l'effacement (Article 17)
  - Droit à la portabilité (Article 20)
  - Droit d'opposition (Article 21)

Gère également :
  - Purge automatique après délai de conservation
  - Export des données en format lisible
  - Journalisation des demandes RGPD
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.audit.event_logger import log_event
from app.security.encryption import decrypt

logger = logging.getLogger("facilim.services.compliance")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ComplianceService:

    def __init__(self, retention_days: int = 1825):
        self.retention_days = retention_days  # 5 ans par défaut (MDPH)

    def export_usager_data(
        self,
        usager_id: str,
        db_conn: Any,
        include_medical: bool = False,
        requesting_utilisateur_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Export complet des données d'un usager (Article 15 & 20 RGPD).
        Les données médicales nécessitent une justification séparée.
        """
        log_event(
            "DONNEE_EXPORTEE",
            usager_id=usager_id,
            utilisateur_id=requesting_utilisateur_id,
            payload={"include_medical": include_medical},
            db_conn=db_conn,
        )

        # Données usager
        row = db_conn.execute(
            "SELECT * FROM usagers WHERE id = ?", (usager_id,)
        ).fetchone()
        if not row:
            return {"error": "Usager non trouvé"}

        usager_data = dict(row)
        # Déchiffrement des PII pour l'export
        for field in ("nom_enc", "prenom_enc", "telephone_enc", "email_enc",
                      "date_naissance_enc", "adresse_enc"):
            if field in usager_data:
                usager_data[field] = decrypt(usager_data[field])

        # Consentements
        consents = db_conn.execute(
            "SELECT * FROM consentements WHERE usager_id = ? ORDER BY accorde_le DESC",
            (usager_id,),
        ).fetchall()

        # Dossiers (sans données médicales)
        dossiers = db_conn.execute(
            "SELECT id, reference, statut, score_completude, created_at, updated_at "
            "FROM dossiers WHERE usager_id = ?",
            (usager_id,),
        ).fetchall()

        export = {
            "generated_at":   _now().isoformat(),
            "rgpd_base":      "Article 15 & 20 RGPD",
            "usager":         usager_data,
            "consentements":  [dict(c) for c in consents],
            "dossiers":       [dict(d) for d in dossiers],
        }

        if include_medical:
            medical_rows = db_conn.execute(
                """
                SELECT dm.* FROM donnees_medicales dm
                JOIN dossiers d ON d.id = dm.dossier_id
                WHERE d.usager_id = ?
                """,
                (usager_id,),
            ).fetchall()
            medical_data = []
            for row in medical_rows:
                r = dict(row)
                for field in ("diagnostics_enc", "traitements_enc", "medecin_enc",
                              "actes_vie_quotidienne_enc", "texte_brut_enc"):
                    if field in r:
                        r[field] = decrypt(r[field])
                medical_data.append(r)
            export["donnees_medicales"] = medical_data

        return export

    def erase_usager_data(
        self,
        usager_id: str,
        db_conn: Any,
        raison: str = "Demande d'effacement Art.17 RGPD",
        requesting_utilisateur_id: str | None = None,
    ) -> bool:
        """
        Effacement des données personnelles (Article 17 RGPD).
        Conserve les données nécessaires aux obligations légales (MDPH = 5 ans).
        """
        log_event(
            "DONNEE_SUPPRIMEE",
            usager_id=usager_id,
            utilisateur_id=requesting_utilisateur_id,
            payload={"raison": raison},
            db_conn=db_conn,
        )

        now = _now().isoformat()
        try:
            # Anonymisation (pas suppression physique — obligations légales)
            db_conn.execute(
                """
                UPDATE usagers SET
                    telephone_enc      = '[SUPPRIMÉ]',
                    email_enc          = NULL,
                    nom_enc            = '[SUPPRIMÉ]',
                    prenom_enc         = '[SUPPRIMÉ]',
                    date_naissance_enc = NULL,
                    adresse_enc        = NULL,
                    code_postal        = NULL,
                    commune            = NULL,
                    deleted_at         = ?,
                    updated_at         = ?
                WHERE id = ?
                """,
                (now, now, usager_id),
            )
            # Effacement données médicales
            db_conn.execute(
                """
                UPDATE donnees_medicales SET
                    diagnostics_enc              = NULL,
                    traitements_enc              = NULL,
                    medecin_enc                  = NULL,
                    actes_vie_quotidienne_enc    = NULL,
                    historique_mdph_enc          = NULL,
                    texte_brut_enc               = NULL,
                    texte_anon_enc               = NULL,
                    updated_at                   = ?
                WHERE dossier_id IN (
                    SELECT id FROM dossiers WHERE usager_id = ?
                )
                """,
                (now, usager_id),
            )
            logger.info(f"[RGPD] Données effacées | usager={usager_id[:8]}")
            return True
        except Exception as e:
            logger.error(f"[RGPD] Erreur effacement : {e}")
            return False

    def purge_expired_dossiers(self, db_conn: Any) -> int:
        """
        Purge automatique des dossiers dont la durée de conservation est dépassée.
        À appeler périodiquement (ex : tâche cron quotidienne).
        """
        cutoff = (_now() - timedelta(days=self.retention_days)).isoformat()
        rows = db_conn.execute(
            """
            SELECT d.usager_id FROM dossiers d
            WHERE d.clos_le < ? AND d.deleted_at IS NULL
            """,
            (cutoff,),
        ).fetchall()

        purged = 0
        for row in rows:
            self.erase_usager_data(
                row["usager_id"],
                db_conn,
                raison=f"Purge automatique après {self.retention_days} jours",
            )
            purged += 1

        if purged:
            logger.info(f"[RGPD] Purge automatique : {purged} usager(s) anonymisé(s)")
        return purged
