"""
app/engines/orchestration_engine.py — Orchestrateur central Facilim.

Point d'entrée unique pour tout événement entrant.
Chaque événement déclenche immédiatement :
  1. Mise à jour de l'état en base (PostgreSQL / SQLite)
  2. Journalisation dans audit_events
  3. Transition d'état si applicable
  4. Réponse appropriée selon le canal

Principes :
  - Déterministe : même entrée → même traitement
  - Idempotent : replay sans double effet
  - Traçable : chaque décision est journalisée
  - Human-in-the-loop : aucune décision sensible automatisée
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.audit.event_logger import log_event
from app.audit.trace_manager import ProcessingTrace, start_trace, timed_step
from app.engines.case_state_engine import (
    DossierStatut,
    create_dossier,
    create_flag_humain,
    transition_dossier,
    update_scoring,
)
from app.engines.conversation_engine import (
    ConversationState,
    detect_missing_fields,
    extract_structured_data_from_history,
    generate_response,
)
from app.engines.scoring_engine import score_dossier
from app.services.consent_service import (
    check_consent_required,
    record_whatsapp_consent,
    require_consent_for_processing,
)

logger = logging.getLogger("facilim.engines.orchestration")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class OrchestrationEngine:
    """Orchestrateur central — traite chaque événement entrant."""

    def __init__(
        self,
        db_conn: Any,
        whatsapp_service: Any,
        notification_service: Any,
        openai_client: Any,
        settings: Any,
    ):
        self.db             = db_conn
        self.wa             = whatsapp_service
        self.notif          = notification_service
        self.llm            = openai_client
        self.settings       = settings

    # ── Point d'entrée principal ─────────────────────────────────────────────

    def handle_whatsapp_message(
        self,
        from_number: str,
        message_text: str,
        message_id: str,
        media_id: str | None = None,
        mime_type: str | None = None,
    ) -> dict[str, Any]:
        """
        Traite un message WhatsApp entrant.
        Retourne un dict de résultat pour logging / réponse API.
        """
        trace = start_trace()
        log_event(
            "WHATSAPP_RECU",
            canal="whatsapp",
            payload={"from_suffix": from_number[-4:], "has_media": bool(media_id)},
            db_conn=self.db,
        )

        try:
            result = self._process_whatsapp(
                from_number, message_text, message_id, media_id, mime_type, trace
            )
            self.db.commit()
            return result
        except Exception as e:
            logger.error(f"[ORCH] Erreur traitement WhatsApp : {e}", exc_info=True)
            self._send_error_message(from_number)
            return {"success": False, "error": str(e)}

    def _process_whatsapp(
        self,
        phone: str,
        text: str,
        message_id: str,
        media_id: str | None,
        mime_type: str | None,
        trace: ProcessingTrace,
    ) -> dict[str, Any]:
        """Pipeline de traitement d'un message WhatsApp."""

        # 1. Récupération ou création de l'usager
        with timed_step(trace, "Emma", "IDENTIFY_USER") as step:
            usager = self._get_or_create_usager(phone)
            step.metadata["usager_id"] = usager["id"]

        # 2. Vérification du consentement
        consent_ok = not check_consent_required(usager["id"], self.db)

        if not consent_ok:
            with timed_step(trace, "Emma", "REQUEST_CONSENT") as step:
                result = self._handle_consent_flow(usager, text, phone)
                step.metadata["consent_result"] = result
                if result != "accepted":
                    return {"success": True, "action": "consent_requested"}

        # 3. Vérification du consentement pour le traitement
        if not require_consent_for_processing(usager["id"], "traitement_dossier", self.db):
            self.wa.send_text(
                phone,
                "Pour vous aider, j'ai besoin de votre accord. "
                "Répondez OUI pour accepter ou NON pour refuser.",
            )
            return {"success": True, "action": "consent_required"}

        # 4. Récupération du dossier actif
        session = self._get_or_create_session(phone, usager["id"])
        dossier_id = session.get("dossier_id")
        etat = session.get("persona_actif", ConversationState.COLLECTE)

        if not dossier_id:
            with timed_step(trace, "Emma", "CREATE_DOSSIER") as step:
                dossier_id = self._create_new_dossier(usager)
                self._update_session_dossier(session["id"], dossier_id)
                step.metadata["dossier_id"] = dossier_id

        # 5. Traitement selon l'état conversationnel
        if media_id:
            with timed_step(trace, "Léa", "PROCESS_DOCUMENT") as step:
                return self._handle_document(usager, dossier_id, media_id, mime_type, phone, trace)

        # 6. Génération de la réponse conversationnelle
        with timed_step(trace, "Emma", "GENERATE_RESPONSE") as step:
            dossier = self._get_dossier(dossier_id)
            historique = json.loads(dossier.get("conversation_json", "[]") or "[]")
            donnees = json.loads(dossier.get("synthese_json", "{}") or "{}")

            # Mise à jour des données avec extraction LLM
            nouvelles_donnees = extract_structured_data_from_history(
                historique + [{"role": "user", "content": text}],
                self.llm,
                model=self.settings.openai_model_fast,
            )
            donnees.update({k: v for k, v in nouvelles_donnees.items() if v})

            elements_manquants = detect_missing_fields(donnees)

            # Génération de la réponse
            reponse = generate_response(
                message_entrant=text,
                historique=historique,
                etat=etat,
                donnees_collectees=donnees,
                elements_manquants=elements_manquants,
                openai_client=self.llm,
                is_mineur=bool(usager.get("est_mineur")),
                model=self.settings.openai_model_fast,
            )

            # Sauvegarde du nouvel échange
            historique.append({"role": "user",      "content": text})
            historique.append({"role": "assistant",  "content": reponse})
            historique = historique[-self.settings.max_conversation_history:]

            now = _now_iso()
            self.db.execute(
                """
                UPDATE dossiers SET
                    conversation_json = ?,
                    synthese_json     = ?,
                    updated_at        = ?
                WHERE id = ?
                """,
                (
                    json.dumps(historique, ensure_ascii=False),
                    json.dumps(donnees, ensure_ascii=False),
                    now,
                    dossier_id,
                ),
            )

            # 7. Déclenchement de l'analyse si toutes les infos sont collectées
            if not elements_manquants:
                self._trigger_analysis(dossier_id, usager, donnees)

            # 8. Envoi de la réponse
            self.wa.send_text(phone, reponse, dossier_id=dossier_id, db_conn=self.db)

            step.metadata["elements_manquants"] = len(elements_manquants)

        return {"success": True, "action": "response_sent", "dossier_id": dossier_id}

    # ── Gestion du consentement ──────────────────────────────────────────────

    def _handle_consent_flow(
        self, usager: dict, text: str, phone: str
    ) -> str:
        """Gère le flux de consentement conversationnel."""
        from app.audit.consent_history import get_consent_message_for_whatsapp

        # Si c'est une réponse à la demande de consentement
        result = record_whatsapp_consent(usager["id"], text, self.db)

        if result == "accepted":
            self.wa.send_text(
                phone,
                "Merci pour votre confiance ! Je vais maintenant vous aider "
                "à constituer votre dossier MDPH étape par étape.\n\n"
                "Commençons : quel est le nom et prénom de la personne concernée par le dossier ?",
            )
        elif result == "refused":
            self.wa.send_text(
                phone,
                "Je comprends votre décision. Vos informations ne seront pas conservées.\n"
                "Si vous changez d'avis, contactez-nous de nouveau. — L'équipe Facilim",
            )
        else:
            # Réponse non reconnue → renvoyer la demande
            self.wa.send_text(phone, get_consent_message_for_whatsapp())
            result = "unclear"

        return result

    # ── Gestion des documents ────────────────────────────────────────────────

    def _handle_document(
        self,
        usager: dict,
        dossier_id: str,
        media_id: str,
        mime_type: str | None,
        phone: str,
        trace: ProcessingTrace,
    ) -> dict[str, Any]:
        """Traite un document reçu via WhatsApp (photo, PDF)."""
        piece_id = str(uuid.uuid4())
        now = _now_iso()

        self.db.execute(
            """
            INSERT INTO pieces_justificatives
                (id, dossier_id, type_piece, mime_type, uploaded_par,
                 ocr_effectue, flag_validation_humaine, created_at, updated_at)
            VALUES (?, ?, 'DOCUMENT_RECU', ?, 'whatsapp', 0, 1, ?, ?)
            """,
            (piece_id, dossier_id, mime_type, now, now),
        )

        log_event(
            "DOCUMENT_RECU",
            dossier_id=dossier_id,
            usager_id=usager["id"],
            canal="whatsapp",
            payload={"piece_id": piece_id, "mime_type": mime_type},
            db_conn=self.db,
        )

        # Flag human-in-the-loop pour validation du document
        create_flag_humain(
            dossier_id=dossier_id,
            raison="Document reçu via WhatsApp — validation humaine requise avant intégration.",
            educateur_id=None,
            severite="NORMALE",
            db_conn=self.db,
        )

        self.wa.send_text(
            phone,
            "Votre document a bien été reçu. Il sera examiné par notre équipe "
            "dans les plus brefs délais.\n"
            "Avez-vous d'autres documents à nous transmettre ?",
            dossier_id=dossier_id,
            db_conn=self.db,
        )

        return {"success": True, "action": "document_received", "piece_id": piece_id}

    # ── Déclenchement de l'analyse ───────────────────────────────────────────

    def _trigger_analysis(
        self,
        dossier_id: str,
        usager: dict,
        donnees: dict,
    ) -> None:
        """Déclenche le pipeline d'analyse CNSA + Jade quand la collecte est complète."""
        try:
            # Transition vers EN_ANALYSE
            dossier = self._get_dossier(dossier_id)
            if dossier and dossier.get("statut") == DossierStatut.EN_COLLECTE:
                transition_dossier(
                    dossier_id,
                    DossierStatut.EN_COLLECTE,
                    DossierStatut.EN_ANALYSE,
                    raison="Collecte complète — déclenchement analyse",
                    canal="system",
                    db_conn=self.db,
                )

            # Appel CNSA validator existant
            import importlib
            _validator = importlib.import_module("2_intelligence.cnsa_validator")
            texte_synthese = json.dumps(donnees, ensure_ascii=False)
            analyse = _validator.validate_dossier(
                texte_synthese,
                dossier.get("departement_code", "75") if dossier else "75",
            )

            # Scoring Jade
            scoring = score_dossier(
                dossier_id=dossier_id,
                texte_anonymise=texte_synthese,
                analyse_llm=analyse,
                confidence_threshold=self.settings.scoring_confidence_threshold,
                db_conn=self.db,
            )

            # Mise à jour du dossier
            droits = scoring.get("droits_identifies", [])
            update_scoring(
                dossier_id=dossier_id,
                score=scoring.get("score_global", 0),
                confiance=scoring.get("confiance", 0.0),
                droits_identifies=droits,
                flag_humain=scoring.get("_flag_humain", False),
                raison_flag=scoring.get("raison_flag"),
                db_conn=self.db,
            )

            # Transition selon le résultat
            statut_analyse = scoring.get("statut_analyse", "INCOMPLET")
            if statut_analyse == "COMPLET" and not scoring.get("_flag_humain"):
                transition_dossier(
                    dossier_id,
                    DossierStatut.EN_ANALYSE,
                    DossierStatut.COMPLET,
                    raison=f"Score={scoring.get('score_global')}/100 — confiance={scoring.get('confiance'):.0%}",
                    canal="system",
                    db_conn=self.db,
                )
            else:
                questions = analyse.get("questions_manquantes", [])
                self.db.execute(
                    "UPDATE dossiers SET questions_json = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(questions, ensure_ascii=False), _now_iso(), dossier_id),
                )
                transition_dossier(
                    dossier_id,
                    DossierStatut.EN_ANALYSE,
                    DossierStatut.INCOMPLET,
                    raison="Analyse incomplète ou confiance insuffisante",
                    canal="system",
                    db_conn=self.db,
                )

        except Exception as e:
            logger.error(f"[ORCH] Erreur analyse : {e}", exc_info=True)
            create_flag_humain(
                dossier_id=dossier_id,
                raison=f"Erreur moteur d'analyse : {e}",
                educateur_id=None,
                severite="HAUTE",
                db_conn=self.db,
            )

    # ── Helpers base de données ───────────────────────────────────────────────

    def _get_or_create_usager(self, phone: str) -> dict[str, Any]:
        from app.security.encryption import encrypt, generate_reference

        phone_enc = encrypt(phone)
        row = self.db.execute(
            "SELECT * FROM usagers WHERE telephone_enc = ? LIMIT 1",
            (phone_enc,),
        ).fetchone()

        if row:
            return dict(row)

        usager_id = str(uuid.uuid4())
        ref = generate_reference("FAC")
        now = _now_iso()
        self.db.execute(
            """
            INSERT INTO usagers
                (id, telephone_enc, reference_interne, canal_prefere, created_at, updated_at)
            VALUES (?, ?, ?, 'whatsapp', ?, ?)
            """,
            (usager_id, phone_enc, ref, now, now),
        )
        log_event("USAGER_CREE", usager_id=usager_id, canal="whatsapp", db_conn=self.db)
        return {
            "id": usager_id,
            "telephone_enc": phone_enc,
            "reference_interne": ref,
            "canal_prefere": "whatsapp",
            "est_mineur": 0,
        }

    def _get_or_create_session(self, phone: str, usager_id: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT * FROM sessions_whatsapp WHERE telephone = ? LIMIT 1",
            (phone,),
        ).fetchone()

        if row:
            self.db.execute(
                "UPDATE sessions_whatsapp SET derniere_activite = ? WHERE id = ?",
                (_now_iso(), row["id"]),
            )
            return dict(row)

        session_id = str(uuid.uuid4())
        now = _now_iso()
        self.db.execute(
            """
            INSERT INTO sessions_whatsapp
                (id, usager_id, telephone, persona_actif, derniere_activite, created_at)
            VALUES (?, ?, ?, 'intake', ?, ?)
            """,
            (session_id, usager_id, phone, now, now),
        )
        return {
            "id": session_id,
            "usager_id": usager_id,
            "telephone": phone,
            "persona_actif": "intake",
            "dossier_id": None,
        }

    def _create_new_dossier(self, usager: dict) -> str:
        dossier_id = create_dossier(
            usager_id=usager["id"],
            departement_code=usager.get("departement_code", "75"),
            db_conn=self.db,
        )
        transition_dossier(
            dossier_id,
            DossierStatut.BROUILLON,
            DossierStatut.EN_COLLECTE,
            raison="Démarrage collecte WhatsApp",
            canal="whatsapp",
            db_conn=self.db,
        )
        return dossier_id

    def _update_session_dossier(self, session_id: str, dossier_id: str) -> None:
        self.db.execute(
            "UPDATE sessions_whatsapp SET dossier_id = ?, persona_actif = 'collecte' WHERE id = ?",
            (dossier_id, session_id),
        )

    def _get_dossier(self, dossier_id: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT * FROM dossiers WHERE id = ?", (dossier_id,)
        ).fetchone()
        return dict(row) if row else None

    def _send_error_message(self, phone: str) -> None:
        try:
            self.wa.send_text(
                phone,
                "Une erreur est survenue. Nos équipes ont été alertées. "
                "Veuillez réessayer dans quelques minutes. — L'équipe Facilim",
            )
        except Exception:
            pass
