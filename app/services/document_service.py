"""
app/services/document_service.py — Service de gestion des pièces justificatives.

Orchestration complète du cycle de vie d'un document :
  1. Réception (WhatsApp, upload portail)
  2. Stockage sécurisé
  3. OCR et extraction de texte
  4. Validation par le moteur documentaire (Léa)
  5. Mise à jour du dossier
  6. Notification si validation humaine requise
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.audit.event_logger import log_event
from app.engines.document_engine import process_document
from app.engines.case_state_engine import create_flag_humain

logger = logging.getLogger("facilim.services.document")


def receive_document_from_whatsapp(
    dossier_id: str,
    usager_id: str,
    media_content: bytes,
    mime_type: str,
    storage_service: Any,
    db_conn: Any,
    educateur_id: str | None = None,
) -> dict[str, Any]:
    """
    Traite un document reçu via WhatsApp :
      - stockage chiffré
      - OCR (si image/PDF)
      - analyse documentaire (Léa)
      - flag humain si nécessaire

    Returns:
        Dict avec piece_id, type_detecte, flag_humain
    """
    piece_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Extension selon MIME
    ext_map = {
        "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
        "application/pdf": "pdf", "image/gif": "gif",
    }
    ext = ext_map.get(mime_type, "bin")

    # Stockage
    chemin = storage_service.store(media_content, category="documents", extension=ext)

    # Enregistrement de la pièce
    db_conn.execute(
        """
        INSERT INTO pieces_justificatives
            (id, dossier_id, type_piece, chemin_stockage, mime_type, taille_octets,
             uploaded_par, ocr_effectue, flag_validation_humaine, created_at, updated_at)
        VALUES (?, ?, 'DOCUMENT_RECU', ?, ?, ?, 'whatsapp', 0, 1, ?, ?)
        """,
        (piece_id, dossier_id, chemin, mime_type, len(media_content), now, now),
    )

    log_event(
        "DOCUMENT_RECU",
        dossier_id=dossier_id,
        usager_id=usager_id,
        canal="whatsapp",
        payload={"piece_id": piece_id, "mime_type": mime_type, "taille": len(media_content)},
        db_conn=db_conn,
    )

    # OCR si image (appel au module existant si disponible)
    texte_extrait = ""
    if mime_type.startswith("image/"):
        try:
            import importlib
            _ocr = importlib.import_module("services.ocr_image")
            texte_extrait = _ocr.ocr_image(media_content) or ""
        except Exception as e:
            logger.warning(f"[DOC] OCR non disponible : {e}")

    # Analyse documentaire (Léa)
    if texte_extrait:
        result = process_document(
            dossier_id=dossier_id,
            piece_id=piece_id,
            text_extrait=texte_extrait,
            mime_type=mime_type,
            db_conn=db_conn,
        )
    else:
        # Pas de texte extractible → flag humain systématique
        result = {
            "piece_id":       piece_id,
            "type_detecte":   "INCONNU",
            "ocr_confidence": 0.0,
            "contenu_valide": False,
            "flag_humain":    True,
            "raison_flag":    "Contenu non extractible — validation manuelle requise.",
        }
        create_flag_humain(
            dossier_id=dossier_id,
            raison=result["raison_flag"],
            educateur_id=educateur_id,
            severite="NORMALE",
            db_conn=db_conn,
        )

    return result


def get_pieces_dossier(dossier_id: str, db_conn: Any) -> list[dict[str, Any]]:
    """Retourne la liste des pièces d'un dossier."""
    rows = db_conn.execute(
        """
        SELECT id, type_piece, ocr_effectue, score_confiance_ocr,
               flag_validation_humaine, validee_par, validee_le,
               mime_type, taille_octets, created_at
        FROM pieces_justificatives
        WHERE dossier_id = ? AND deleted_at IS NULL
        ORDER BY created_at DESC
        """,
        (dossier_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def validate_piece(
    piece_id: str,
    validateur_id: str,
    type_confirme: str,
    db_conn: Any,
) -> bool:
    """Validation manuelle d'une pièce par un éducateur."""
    now = datetime.now(timezone.utc).isoformat()
    db_conn.execute(
        """
        UPDATE pieces_justificatives SET
            flag_validation_humaine = 0,
            validee_par             = ?,
            validee_le              = ?,
            type_piece              = ?,
            updated_at              = ?
        WHERE id = ?
        """,
        (validateur_id, now, type_confirme, now, piece_id),
    )
    logger.info(f"[DOC] Pièce validée | piece={piece_id[:8]} | type={type_confirme}")
    return True
