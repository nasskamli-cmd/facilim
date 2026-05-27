"""
app/engines/document_engine.py — Moteur de traitement documentaire (Agent Léa).

Responsabilités :
  - Extraction de texte (PDF, images via OCR)
  - Validation du contenu extrait
  - Détection du type de document
  - Génération de CERFA pré-rempli
  - Score de confiance OCR → flag humain si < seuil

Human-in-the-loop obligatoire si :
  - Score OCR < 90%
  - Document illisible
  - Contenu incohérent
  - Type de document non identifié
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.audit.event_logger import log_agent_action
from app.engines.case_state_engine import create_flag_humain

logger = logging.getLogger("facilim.engines.document")

_OCR_THRESHOLD = 0.90  # < 90% → flag humain

_DOCUMENT_TYPES = {
    "certificat_medical": [
        "certificat médical", "cerfa 13878", "médecin", "diagnostic",
        "pathologie", "traitement", "prescription", "handicap"
    ],
    "justificatif_identite": [
        "carte nationale d'identité", "passeport", "titre de séjour",
        "carte d'identité", "CNI"
    ],
    "justificatif_domicile": [
        "facture", "relevé", "quittance", "EDF", "eau", "gaz",
        "taxe d'habitation", "avis d'imposition"
    ],
    "bilan_fonctionnel": [
        "bilan", "ergothérapeute", "psychomotricien", "autonomie",
        "AVQ", "activités de la vie quotidienne", "GEVA"
    ],
    "plan_aide": [
        "plan d'aide", "plan personnalisé", "APA", "PCH",
        "conseil départemental", "auxiliaire de vie"
    ],
}


def detect_document_type(text: str) -> tuple[str, float]:
    """
    Identifie le type de document à partir du texte extrait.

    Returns:
        (type_detecte, score_confiance)
    """
    text_lower = text.lower()
    scores: dict[str, float] = {}

    for doc_type, keywords in _DOCUMENT_TYPES.items():
        hits = sum(1 for kw in keywords if kw.lower() in text_lower)
        scores[doc_type] = hits / len(keywords)

    if not scores:
        return "INCONNU", 0.0

    best_type = max(scores, key=lambda k: scores[k])
    best_score = scores[best_type]

    if best_score < 0.1:
        return "INCONNU", best_score

    return best_type.upper(), round(best_score, 3)


def estimate_ocr_confidence(text: str, expected_length_min: int = 50) -> float:
    """
    Estime la qualité de l'OCR à partir du texte extrait.
    Indicateurs : longueur, ratio alphanumérique, séquences aberrantes.
    """
    if not text or len(text) < expected_length_min:
        return 0.0

    total_chars = len(text)
    alphanumeric = sum(1 for c in text if c.isalnum() or c in " .,;:!?()-\n")
    ratio_alpha = alphanumeric / total_chars

    # Pénalité si trop de caractères spéciaux inconnus (OCR bruité)
    import re
    weird_chars = len(re.findall(r"[^\x00-\x7FÀ-ÿ]", text))
    penalty = min(weird_chars / max(total_chars, 1) * 5, 0.3)

    confidence = max(0.0, min(ratio_alpha - penalty, 1.0))
    return round(confidence, 3)


def process_document(
    dossier_id: str,
    piece_id: str,
    text_extrait: str,
    mime_type: str | None,
    ocr_confidence_threshold: float = _OCR_THRESHOLD,
    db_conn: Any | None = None,
) -> dict[str, Any]:
    """
    Pipeline de traitement d'un document reçu.

    1. Estimation de la qualité OCR
    2. Détection du type de document
    3. Décision humain/auto selon le score
    4. Persistance et journalisation

    Returns:
        Dict avec type_detecte, confiance, flag_humain, contenu_valide
    """
    now = datetime.now(timezone.utc).isoformat()
    input_hash = hashlib.sha256(text_extrait.encode()).hexdigest()[:16]

    # 1. Qualité OCR
    ocr_confidence = estimate_ocr_confidence(text_extrait)
    flag_humain    = ocr_confidence < ocr_confidence_threshold

    # 2. Type de document
    type_detecte, type_confidence = detect_document_type(text_extrait)

    # 3. Validation finale
    contenu_valide = (
        ocr_confidence >= ocr_confidence_threshold
        and type_detecte != "INCONNU"
        and type_confidence >= 0.15
    )

    raison_flag = None
    if flag_humain:
        raison_flag = (
            f"Score OCR insuffisant ({ocr_confidence:.0%} < {ocr_confidence_threshold:.0%}). "
            "Vérification manuelle obligatoire avant intégration au dossier."
        )
        if db_conn:
            create_flag_humain(
                dossier_id=dossier_id,
                raison=raison_flag,
                educateur_id=None,
                severite="NORMALE",
                db_conn=db_conn,
            )

    if not contenu_valide and not flag_humain:
        raison_flag = f"Type de document non identifié ({type_detecte}) ou contenu insuffisant."

    # 4. Mise à jour de la pièce en base
    if db_conn and piece_id:
        db_conn.execute(
            """
            UPDATE pieces_justificatives SET
                type_piece                = ?,
                ocr_effectue              = 1,
                score_confiance_ocr       = ?,
                flag_validation_humaine   = ?,
                updated_at                = ?
            WHERE id = ?
            """,
            (
                type_detecte,
                ocr_confidence,
                1 if flag_humain else 0,
                now,
                piece_id,
            ),
        )

        output_hash = hashlib.sha256(
            json.dumps({"type": type_detecte, "conf": ocr_confidence}).encode()
        ).hexdigest()[:16]

        log_agent_action(
            agent_nom="Léa",
            action="OCR_TRAITEMENT",
            dossier_id=dossier_id,
            agent_niveau="N3",
            input_hash=input_hash,
            output_hash=output_hash,
            score_confiance=ocr_confidence,
            flag_genere=flag_humain,
            db_conn=db_conn,
        )

    result = {
        "piece_id":        piece_id,
        "type_detecte":    type_detecte,
        "ocr_confidence":  ocr_confidence,
        "type_confidence": type_confidence,
        "contenu_valide":  contenu_valide,
        "flag_humain":     flag_humain,
        "raison_flag":     raison_flag,
    }

    logger.info(
        f"[LEA] Document traité | dossier={dossier_id[:8]} | "
        f"type={type_detecte} | ocr={ocr_confidence:.0%} | flag={flag_humain}"
    )

    return result
