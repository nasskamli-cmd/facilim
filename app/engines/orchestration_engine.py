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
from app.services.structure_search_service import (
    detecter_mention_etablissement,
    formater_suggestions_whatsapp,
    rechercher_structures,
)
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
    TabNavigationState,
    extract_structured_data_from_history,
    generer_message_validation_onglet,
    onglet_courant_complet,
)
from app.engines.profile_engine import (
    CHAMPS_INTERDITS_ENFANT,
    ProfilUsager,
    appliquer_contraintes_profil,
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


def _calculer_completude_live(donnees: dict) -> int:
    """
    Calcule un score de complétude (0-100) basé sur les champs clés remplis.
    Mis à jour en temps réel à chaque sauvegarde — indépendant de l'analyse IA.
    """
    # Champs clés pondérés (total = 100 pts)
    CHAMPS_PONDERES = {
        "nom_prenom":         15,
        "date_naissance":     15,
        "num_secu":           10,
        "numero_securite_sociale": 10,
        "adresse_complete":   8,
        "telephone":          5,
        "email":              5,
        "diagnostics":        12,
        "impact_quotidien":   10,
        "droits_demandes":    10,
        "type_dossier":       5,
        "departement":        5,
    }
    score = 0
    already_counted_nss = False
    for champ, poids in CHAMPS_PONDERES.items():
        if champ in ("num_secu", "numero_securite_sociale"):
            if not already_counted_nss and donnees.get(champ):
                score += poids
                already_counted_nss = True
        elif donnees.get(champ):
            score += poids
    return min(score, 100)


def _sauvegarder_nav(
    db: Any,
    dossier_id: str,
    nav: "TabNavigationState",
    historique: list[dict],
    donnees: dict,
) -> None:
    """
    Persiste l'état de navigation, la conversation et le verrou de profil.
    Commit immédiat : garantit la visibilité aux connexions concurrentes
    (évite la race condition entre messages successifs rapides).
    """
    score_live = _calculer_completude_live(donnees)
    db.execute(
        """
        UPDATE dossiers SET
            conversation_json        = ?,
            synthese_json            = ?,
            contexte_navigation_json = ?,
            score_completude         = CASE WHEN score_completude < ? THEN ? ELSE score_completude END,
            updated_at               = ?
        WHERE id = ?
        """,
        (
            json.dumps(historique, ensure_ascii=False),
            json.dumps(donnees, ensure_ascii=False),
            json.dumps({
                "onglet_courant":      nav.onglet_courant,
                "validation_demandee": nav.validation_demandee,
                "onglets_valides":     nav.onglets_valides,
                "profil_mdph_lock":    nav.profil_mdph_lock,
            }, ensure_ascii=False),
            score_live, score_live,
            _now_iso(),
            dossier_id,
        ),
    )
    db.commit()  # Commit immédiat — visibilité immédiate pour les requêtes parallèles


def _load_cnsa_validator() -> Any:
    """
    Charge le module CNSA validator de manière défensive.

    En production, le module doit être accessible via PYTHONPATH.
    Si le module est absent (dev, test), retourne un stub qui produit
    un résultat INCOMPLET avec flag humain — jamais un crash silencieux.
    """
    try:
        import importlib
        return importlib.import_module("2_intelligence.cnsa_validator")
    except Exception:
        logger.warning(
            "[ORCH] Module '2_intelligence.cnsa_validator' absent — "
            "stub activé. Configurer PYTHONPATH en production."
        )

        class _StubValidator:
            """
            Validateur CNSA interne — analyse le dossier via LLM quand le module
            externe 2_intelligence.cnsa_validator est absent.
            """
            _llm = None

            @classmethod
            def validate_dossier(cls, texte: str, departement: str = "75") -> dict:
                import json as _json
                try:
                    # Analyse IA du dossier pour proposer les droits et questions manquantes
                    import os
                    api_key = os.environ.get("OPENAI_API_KEY", "")
                    if not api_key:
                        raise ValueError("Pas de clé OpenAI")
                    from openai import OpenAI as _OAI
                    client = _OAI(api_key=api_key)
                    resp = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{
                            "role": "system",
                            "content": (
                                "Tu es un expert MDPH. Analyse ce dossier et retourne un JSON avec :\n"
                                "- droits_proposes: liste des droits MDPH possibles (AAH, PCH, RQTH, AEEH, CMI, orientation ESAT…)\n"
                                "- questions_manquantes: liste des informations encore nécessaires\n"
                                "- score: 0-100 (estimation de complétude)\n"
                                "- statut: COMPLET si score>=70 ET droits_proposes non vide, sinon INCOMPLET\n"
                                "- recommandation: phrase de synthèse courte\n"
                                "Réponds UNIQUEMENT en JSON valide."
                            ),
                        }, {
                            "role": "user",
                            "content": f"Département : {departement}\n\nDonnées dossier :\n{texte[:3000]}",
                        }],
                        max_tokens=500, temperature=0.0,
                        response_format={"type": "json_object"},
                    )
                    result = _json.loads(resp.choices[0].message.content)
                    result["_stub"] = False
                    return result
                except Exception as e:
                    return {
                        "droits_proposes":      [],
                        "questions_manquantes": ["Informations insuffisantes — compléter le dossier"],
                        "score":                0,
                        "statut":               "INCOMPLET",
                        "recommandation":       "Dossier incomplet — poursuite de la collecte nécessaire.",
                        "_stub":                True,
                        "_error":               str(e),
                    }

        return _StubValidator()


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

    @staticmethod
    def _normaliser_telephone_local(numero: str) -> str:
        """
        Convertit vers le format local français (0XXXXXXXXX) pour les recherches en base.
        WhatsApp envoie "33642087770" → "0642087770" pour matcher la saisie du pro.
        """
        n = numero.strip().lstrip("+")
        if n.startswith("33") and len(n) == 11:
            return "0" + n[2:]
        return n

    @staticmethod
    def _normaliser_telephone_wa(numero: str) -> str:
        """
        Convertit vers le format international sans + (33XXXXXXXXX)
        exigé par l'API WhatsApp Cloud pour envoyer des messages.
        """
        n = numero.strip().lstrip("+")
        # Format local français 0XXXXXXXXX → 33XXXXXXXXX
        if n.startswith("0") and len(n) == 10:
            return "33" + n[1:]
        return n

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
        # phone_db  = format local (0XXXXXXXXX) → pour les recherches en base
        # phone_wa  = format international (33XXXXXXXXX) → pour envoyer via l'API WhatsApp
        phone_db = self._normaliser_telephone_local(from_number)
        phone_wa = self._normaliser_telephone_wa(phone_db)
        trace = start_trace()
        log_event(
            "WHATSAPP_RECU",
            canal="whatsapp",
            payload={"from_suffix": from_number[-4:], "has_media": bool(media_id)},
            db_conn=self.db,
        )

        try:
            # ── Verrou anti-doublon en DB : POSÉ avant traitement, LIBÉRÉ après ──
            # Empêche les doublons quand WhatsApp retente le même message_id.
            # Clé = message_id (unique par message WhatsApp).
            import time as _time
            lock_check = self.db.execute(
                "SELECT contexte_json FROM sessions_whatsapp WHERE telephone = ? OR telephone = ? LIMIT 1",
                (phone_db, phone_wa),
            ).fetchone()
            if lock_check:
                import json as _j
                _ctx = _j.loads(lock_check["contexte_json"] or "{}")
                _lock_mid = _ctx.get("processing_message_id")
                _lock_ts  = _ctx.get("processing_since", 0)
                if _lock_mid == message_id:
                    logger.warning("[ORCH] Doublon message_id ignoré : %s", message_id[:12])
                    return {"success": True, "action": "duplicate_ignored"}
                if _lock_mid and (_time.time() - _lock_ts) < 25:
                    logger.warning("[ORCH] Traitement en cours, message ignoré pour %s", phone_db[-4:])
                    return {"success": True, "action": "already_processing"}

            # Poser le verrou (sur les deux formats possibles)
            for _ph in (phone_db, phone_wa):
                self.db.execute(
                    """UPDATE sessions_whatsapp SET contexte_json = json_patch(
                        COALESCE(contexte_json,'{}'),
                        json('{"processing_message_id":"' || ? || '","processing_since":' || ? || '}')
                    ) WHERE telephone = ?""",
                    (message_id, int(_time.time()), _ph),
                )
            self.db.commit()

            # phone_db pour les lookups DB, phone_wa pour les envois WhatsApp
            result = self._process_whatsapp(
                phone_db, phone_wa, message_text, message_id, media_id, mime_type, trace
            )

            # Libérer le verrou
            for _ph in (phone_db, phone_wa):
                self.db.execute(
                    """UPDATE sessions_whatsapp SET contexte_json = json_remove(
                        COALESCE(contexte_json,'{}'), '$.processing_message_id', '$.processing_since'
                    ) WHERE telephone = ?""",
                    (_ph,),
                )
            self.db.commit()
            return result
        except Exception as e:
            logger.error(f"[ORCH] Erreur traitement WhatsApp : {e}", exc_info=True)
            self._send_error_message(phone_wa)
            return {"success": False, "error": str(e)}

    def _process_whatsapp(
        self,
        phone: str,      # format local DB (0XXXXXXXXX) — pour les lookups
        phone_wa: str,   # format international WA (33XXXXXXXXX) — pour les envois
        text: str,
        message_id: str,
        media_id: str | None,
        mime_type: str | None,
        trace: ProcessingTrace,
    ) -> dict[str, Any]:
        """Pipeline de traitement d'un message WhatsApp."""

        # 1. Session d'abord (par texte clair — fiable), puis usager par ID
        # Évite tous les problèmes de format/chiffrement du téléphone.
        session = self._get_or_create_session(phone, None)  # usager_id résolu après
        usager = None

        # Si la session a un usager_id connu → récupérer directement par ID (le plus fiable)
        if session.get("usager_id"):
            _row = self.db.execute(
                "SELECT * FROM usagers WHERE id = ?", (session["usager_id"],)
            ).fetchone()
            if _row:
                usager = dict(_row)

        # Sinon → chercher/créer par téléphone chiffré
        if usager is None:
            usager = self._get_or_create_usager(phone)
            # Mettre à jour la session avec l'usager trouvé/créé
            if session.get("id") and not session.get("usager_id"):
                self.db.execute(
                    "UPDATE sessions_whatsapp SET usager_id = ? WHERE id = ?",
                    (usager["id"], session["id"])
                )

        logger.info("[PIPELINE] phone_db=***%s usager=%s session=%s text=%r",
                    phone[-4:], usager["id"][:8], session.get("id", "?")[:8], text[:20])

        # 2. Vérification du consentement
        consent_ok = not check_consent_required(usager["id"], self.db)
        logger.info("[CONSENT_CHECK] usager=%s consent_ok=%s", usager["id"][:8], consent_ok)

        if not consent_ok:
            with timed_step(trace, "Emma", "REQUEST_CONSENT") as step:
                result = self._handle_consent_flow(usager, text, phone_wa)
                step.metadata["consent_result"] = result
                logger.info("[CONSENT] result=%s", result)
                if result == "accepted_already":
                    pass  # continuer le pipeline
                else:
                    return {"success": True, "action": f"consent_{result}"}

        # 3. Dossier actif déjà résolu via session ci-dessus
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
                return self._handle_document(usager, dossier_id, media_id, mime_type, phone_wa, trace, phone_db=phone)

        # 6. Génération de la réponse conversationnelle
        with timed_step(trace, "Emma", "GENERATE_RESPONSE") as step:
            dossier    = self._get_dossier(dossier_id)
            historique = json.loads(dossier.get("conversation_json", "[]") or "[]")
            donnees    = json.loads(dossier.get("synthese_json", "{}") or "{}")

            # ── Sélection du service (IMMUABLE une fois posé) ─────────────────
            # Le service_type est lu depuis sessions_whatsapp.persona_actif.
            # "intake" / "collecte" / vide → identification d'abord.
            # "enfant" / "mixte" / "adulte" / "protege" → service dédié, définitif.
            from app.services.conversation import get_agent, service_type_from_persona
            service_type = service_type_from_persona(etat)
            agent = get_agent(service_type)

            # ── Extraction LLM ─────────────────────────────────────────────────
            # Whitelist large : l'agent filtre lui-même ses champs via CHECKLIST.
            nouvelles_donnees = extract_structured_data_from_history(
                historique + [{"role": "user", "content": text}],
                self.llm,
                model=self.settings.openai_model_fast,
                profil_mdph="inconnu",
            )
            # Règle de fusion données pro vs données usager :
            # - Champs "projet / orientation / scolarité / emploi" → la parole de l'USAGER prime
            # - Champs administratifs / médicaux → le pro est plus fiable, on ne réécrase pas
            _CHAMPS_USAGER_PRIORITAIRE = {
                "souhait_orientation_usager", "projet_professionnel", "projet_de_vie",
                "situation_scolaire", "etablissement_scolaire", "attentes_usager",
                "qualification_section_c", "qualification_section_d", "formation_actuelle",
                "statut_emploi", "droits_demandes", "impact_quotidien",
            }
            _champs_admin_pro = set(donnees.keys()) - _CHAMPS_USAGER_PRIORITAIRE - {
                "notes_pro", "_derniere_langue_detectee"
            }
            for k, v in nouvelles_donnees.items():
                if not v:
                    continue
                if k in _CHAMPS_USAGER_PRIORITAIRE:
                    donnees[k] = v  # l'usager écrase toujours
                elif k not in _champs_admin_pro:
                    donnees[k] = v  # champ nouveau → ajouter

            # ── Verbatim significatif + chronologie + évaluation relance ─────────
            _relance_a_injecter: str = ""   # instruction de relance pour le contexte, si nécessaire
            if text.strip():
                try:
                    from app.engines.verbatim_engine import (
                        accumuler_verbatim,
                        enregistrer_enrichissement,
                        evaluer_richesse_reponse,
                        extraire_chronologie,
                        section_depuis_onglet,
                        section_eligible_relance,
                    )
                    # Chargement anticipé de l'onglet courant depuis nav_raw
                    _nav_raw_pre = json.loads(dossier.get("contexte_navigation_json", "{}") or "{}")
                    _onglet_pour_verbatim = _nav_raw_pre.get("onglet_courant", 2)

                    donnees = accumuler_verbatim(donnees, text, _onglet_pour_verbatim)
                    _chrono_existante = donnees.get("chronologie") or {}
                    _chrono_maj = extraire_chronologie(text, _chrono_existante)
                    if _chrono_maj:
                        donnees["chronologie"] = _chrono_maj

                    # ── Taux d'enrichissement — mesure post-relance ──────────────
                    # Si une relance était active au tour précédent, ce message est
                    # la réponse post-relance : on calcule et enregistre le taux.
                    _texte_avant_relance = donnees.pop("_texte_avant_relance", None)
                    _section_relance_mesure = donnees.pop("_section_relance_mesure", None)
                    if _texte_avant_relance and _section_relance_mesure:
                        donnees = enregistrer_enrichissement(
                            donnees, _section_relance_mesure, _texte_avant_relance, text
                        )
                        taux = donnees.get("_taux_enrichissement_moyen", 0)
                        logger.info(
                            "[ENRICHISSEMENT] section=%s avant=%d mots après=%d mots taux=%.2f",
                            _section_relance_mesure,
                            len(_texte_avant_relance.split()),
                            len(text.split()),
                            taux,
                        )

                    # ── Logique de relance ────────────────────────────────────────
                    # Règles strictes :
                    #   1. Une seule relance max par section (pas par champ)
                    #   2. Sections B/D/E uniquement (B/C/E si enfant)
                    #   3. Si déjà relancé sur cette section → avancer sans insister
                    _section_courante = section_depuis_onglet(_onglet_pour_verbatim)
                    _profil_pour_relance = service_type if service_type not in ("identification", "") else "adulte"
                    _eligible = section_eligible_relance(_section_courante, _profil_pour_relance)

                    if _eligible:
                        _est_pauvre, _raison_pauvrete = evaluer_richesse_reponse(text)
                        if _est_pauvre:
                            # Vérifier si une relance a déjà eu lieu sur cette section
                            _relances_faites: dict = donnees.get("_relances_faites") or {}
                            _cle_relance = f"relance_{_section_courante}"
                            if not _relances_faites.get(_cle_relance):
                                # Première réponse pauvre → préparer la relance
                                # Mémoriser le texte pauvre pour mesure post-relance
                                donnees["_texte_avant_relance"]   = text
                                donnees["_section_relance_mesure"] = _section_courante
                                _relances_faites[_cle_relance] = True
                                donnees["_relances_faites"] = _relances_faites
                                _relance_a_injecter = (
                                    f"\n⚡ INSTRUCTION RELANCE (priorité absolue) :\n"
                                    f"La réponse précédente est trop courte ou manque de détails "
                                    f"({_raison_pauvrete}).\n"
                                    f"Avant de passer à la question suivante, pose UNE question de "
                                    f"précision sur ce qui vient d'être dit.\n"
                                    f"Exemple : 'Pouvez-vous me dire depuis quand ?' ou "
                                    f"'Qu'est-ce que ça change concrètement dans votre quotidien ?'\n"
                                    f"Ton : chaleureux, jamais insistant. C'est la SEULE relance possible.\n"
                                    f"Après cette relance, quelle que soit la réponse, passer à la suite.\n"
                                )
                                logger.info(
                                    "[RELANCE] Section %s — réponse pauvre détectée, relance injectée",
                                    _section_courante,
                                )
                            else:
                                logger.info(
                                    "[RELANCE] Section %s — relance déjà effectuée, avancer",
                                    _section_courante,
                                )
                except Exception as _vb_err:
                    logger.debug("[VERBATIM] Non bloquant : %s", _vb_err)

            # ── Inférenceur MDPH — relance ciblée si aucune relance Sprint 2 active ──
            # L'inférenceur détecte les hypothèses non confirmées et propose
            # une relance critique ciblée si aucune relance générique n'est déjà en attente.
            # Aucune hypothèse n'est injectée dans le CERFA — uniquement dans les relances.
            if not _relance_a_injecter and text.strip():
                try:
                    from app.engines.inferencer_mdph import (
                        inferer_contexte_mdph,
                        relance_critique_active,
                    )
                    _profil_h_inf = donnees.get("profil_principal", "")
                    _profil_mdph_inf = service_type if service_type not in ("identification", "") else "adulte"
                    _contexte_inf = inferer_contexte_mdph(donnees, _profil_h_inf, _profil_mdph_inf)

                    # Stocker le coverage pour le dashboard
                    donnees["_inference_coverage"] = {
                        "total":       _contexte_inf.coverage.total_detectees,
                        "taux":        _contexte_inf.coverage.taux_couverture,
                        "nc_critiques": _contexte_inf.coverage.non_confirmees_critiques,
                    }

                    # Relance critique — uniquement si pas déjà posée
                    _posees_inf: set = set(donnees.get("_relances_inferees_posees") or [])
                    _relance_inf = relance_critique_active(_contexte_inf, _posees_inf)
                    if _relance_inf:
                        _posees_inf.add(_relance_inf.hypothese_id)
                        donnees["_relances_inferees_posees"] = list(_posees_inf)
                        _relance_a_injecter = (
                            f"\n⚡ RELANCE CIBLÉE (priorité absolue) :\n"
                            f"Une information importante n'a pas encore été abordée.\n"
                            f"Pose cette question avant de continuer : "
                            f"{_relance_inf.question}\n"
                            f"Ton : chaleureux, jamais insistant. C'est la SEULE question à poser maintenant.\n"
                        )
                        logger.info(
                            "[INFERENCER] Relance critique injectée : %s | section=%s",
                            _relance_inf.hypothese_id, _relance_inf.section,
                        )

                    # Stocker les alertes inférées pour le rapport qualité
                    donnees["_alertes_inferees"] = [
                        {"message": a.message, "niveau": a.niveau, "section": a.section}
                        for a in _contexte_inf.alertes_qualite
                    ]
                    # Stocker les informations manquantes pour l'analyse de situation
                    donnees["_infos_manquantes_inferees"] = [
                        {"label": i.label, "section": i.section, "priorite": i.priorite.value}
                        for i in _contexte_inf.informations_manquantes
                    ]
                except Exception as _inf_err:
                    logger.debug("[INFERENCER] Non bloquant : %s", _inf_err)

            # ── Navigation par onglets — chargement anticipé (requis par le bloc langue) ──
            nav_raw = json.loads(dossier.get("contexte_navigation_json", "{}") or "{}")
            nav = TabNavigationState(
                onglet_courant=nav_raw.get("onglet_courant", 2),
                validation_demandee=nav_raw.get("validation_demandee", False),
                onglets_valides=nav_raw.get("onglets_valides", []),
                profil_mdph_lock=service_type,
            )

            # Gestion du choix de langue (réponse 1-6 au menu de bienvenue)
            _choix_langue = {
                "1": "fr", "français": "fr", "francais": "fr",
                "2": "en", "english": "en",
                "3": "es", "español": "es", "espanol": "es",
                "4": "ar", "العربية": "ar",
                "5": "pt", "português": "pt", "portugais": "pt",
            }
            _texte_norm = text.strip().lower()
            if _texte_norm in _choix_langue:
                donnees["_langue_choisie"] = _choix_langue[_texte_norm]
                _noms_langue = {"fr": "français", "en": "anglais", "es": "espagnol",
                                "ar": "arabe", "pt": "portugais"}
                _nom_lng = _noms_langue.get(_choix_langue[_texte_norm], "votre langue")
                self.wa.send_text(
                    phone_wa,
                    f"Parfait, nous allons continuer en {_nom_lng} ! 👍",
                    dossier_id=dossier_id, db_conn=self.db,
                )
                # Enchaîner immédiatement la première vraie question de l'agent
                # (au lieu d'attendre le prochain message de l'usager — évite le silence)
                _premiere_reponse = agent.respond(
                    message="",
                    history=[],
                    donnees=donnees,
                    openai_client=self.llm,
                    model=self.settings.openai_model_fast,
                    onglet_courant=nav.onglet_courant,
                    validation_en_attente=False,
                    history_window=self.settings.memory_window_size,
                )
                self.wa.send_text(phone_wa, _premiere_reponse,
                                  dossier_id=dossier_id, db_conn=self.db)
                historique.append({"role": "assistant", "content": _premiere_reponse})
                _sauvegarder_nav(self.db, dossier_id, nav, historique, donnees)
                return {"success": True, "action": "langue_choisie", "dossier_id": dossier_id}

            # Détection automatique de la langue si non choisie
            if text.strip():
                try:
                    from langdetect import detect as _detect
                    _code_detecte = _detect(text)
                    donnees["_derniere_langue_detectee"] = _code_detecte
                    # Si première détection non-française → mémoriser comme langue choisie
                    if _code_detecte != "fr" and not donnees.get("_langue_choisie"):
                        donnees["_langue_choisie"] = _code_detecte
                except Exception:
                    pass

            # ── Si en identification : vérifier si le profil est déjà connu ──────
            # IMPORTANT : si le pro a déjà transmis la date de naissance via documents,
            # on bascule directement vers l'agent spécialisé sans redemander.
            if service_type == "identification":
                from app.services.conversation.identification import identification_agent as _id_agent
                next_service = _id_agent.determine_next_service(donnees)
                if next_service:
                    # Profil déterminé → verrouiller le service définitivement
                    self._switch_service(session["id"], next_service, usager, donnees)
                    service_type = next_service
                    agent = get_agent(service_type)

                    # L'agent spécialisé se présente directement par son prénom
                    _presentations = {
                        "enfant":  "Bonjour ! Je suis Claire 👋 Je prends le relais pour vous accompagner dans la constitution du dossier MDPH de votre enfant. Je vais vous poser quelques questions simples.",
                        "adulte":  "Bonjour ! Je suis Corrine 👋 Je prends le relais pour vous accompagner dans votre dossier MDPH. Je vais vous poser quelques questions simples.",
                        "mixte":   "Bonjour ! Je suis Corrine 👋 Je prends le relais pour votre dossier MDPH. Quelques questions simples pour continuer.",
                        "protege": "Bonjour ! Je suis Samia 👋 Je prends en charge le dossier MDPH de la personne que vous accompagnez. Je vais vous poser quelques questions.",
                    }
                    _msg_transition = _presentations.get(
                        next_service,
                        "Bonjour ! Je prends le relais pour votre dossier MDPH."
                    )
                    self.wa.send_text(phone_wa, _msg_transition,
                                      dossier_id=dossier_id, db_conn=self.db)
                    logger.info(
                        "[ORCH] Service verrouillé : %s | usager=%s",
                        service_type, usager["id"][:8],
                    )

            # ── Profilage multi-handicap (recalcul si diagnostics mis à jour) ──
            # Uniquement si diagnostics ou traitements viennent d'être enrichis
            if nouvelles_donnees.get("diagnostics") or nouvelles_donnees.get("traitements"):
                try:
                    from app.engines.profil_handicap_engine import (
                        detecter_profil_handicap,
                        persister_profil_handicap,
                    )
                    profil_h = detecter_profil_handicap(donnees)
                    if profil_h.profil_principal:
                        donnees["profil_principal"]  = profil_h.profil_principal
                        donnees["profil_secondaire"] = profil_h.profil_secondaire
                        donnees["tags_detectes"]     = profil_h.tags_detectes
                        persister_profil_handicap(self.db, dossier_id, profil_h)
                        logger.info(
                            "[PROFIL_H] dossier=%s principal=%s secondaire=%s",
                            dossier_id[:8], profil_h.profil_principal, profil_h.profil_secondaire,
                        )
                except Exception as _ph_err:
                    logger.warning("[PROFIL_H] Détection échouée (non bloquant) : %s", _ph_err)

            # ── Nettoyage des champs interdits selon le service ───────────────
            if service_type == "enfant":
                donnees = appliquer_contraintes_profil(
                    donnees,
                    ProfilUsager(
                        age_annees=0, profil_mdph="enfant", est_mineur=True,
                        date_naissance="", champs_bloques=dict(CHAMPS_INTERDITS_ENFANT),
                    ),
                )

            # Mettre à jour nav.profil_mdph_lock si le service a changé
            nav.profil_mdph_lock = service_type

            texte_up = text.strip().upper()
            if nav.validation_demandee and texte_up in ("OUI", "YES", "OK", "CORRECT", "VALIDER"):
                nav.onglets_valides.append(nav.onglet_courant)
                nav.onglet_courant = min(nav.onglet_courant + 1, 10)
                nav.validation_demandee = False

            # ── Validation d'onglet : seulement si l'onglet a des champs réels ──
            # Les onglets avec champs=[] (onglets 3, 5, 6) sont avancés silencieusement
            # sans envoyer de message de validation — évite les relances parasites.
            from app.engines.conversation_engine import ONGLETS_MDPH as _ONGLETS
            _onglet_courant_def = next(
                (o for o in _ONGLETS if o["num"] == nav.onglet_courant), None
            )
            _onglet_a_des_champs = bool(_onglet_courant_def and _onglet_courant_def.get("champs"))

            if (
                not nav.validation_demandee
                and onglet_courant_complet(donnees, nav.onglet_courant, service_type)
                and nav.onglet_courant not in nav.onglets_valides
            ):
                if _onglet_a_des_champs:
                    # Onglet avec champs → demander confirmation à l'usager
                    nav.validation_demandee = True
                    msg_validation = generer_message_validation_onglet(nav.onglet_courant)
                    self.wa.send_text(phone_wa, msg_validation, dossier_id=dossier_id, db_conn=self.db)
                    _sauvegarder_nav(self.db, dossier_id, nav, historique, donnees)
                    return {"success": True, "action": "validation_demandee", "dossier_id": dossier_id}
                else:
                    # Onglet vide → avancer silencieusement sans message
                    nav.onglets_valides.append(nav.onglet_courant)
                    nav.onglet_courant = min(nav.onglet_courant + 1, 10)
                    logger.info("[NAV] Onglet %d vide → avance silencieuse vers %d",
                                nav.onglet_courant - 1, nav.onglet_courant)

            # ── Réponse via le service dédié ──────────────────────────────────
            # Injection relance dans les données si nécessaire
            if _relance_a_injecter:
                donnees["_instruction_relance_active"] = _relance_a_injecter
            elif donnees.get("_instruction_relance_active"):
                # Nettoyer l'instruction après utilisation (évite persistance indéfinie)
                del donnees["_instruction_relance_active"]

            reponse = agent.respond(
                message=text,
                history=historique,
                donnees=donnees,
                openai_client=self.llm,
                model=self.settings.openai_model_fast,
                onglet_courant=nav.onglet_courant,
                validation_en_attente=nav.validation_demandee,
                history_window=self.settings.memory_window_size,
            )

            # Sauvegarde
            historique.append({"role": "user",      "content": text})
            historique.append({"role": "assistant",  "content": reponse})
            historique = self._appliquer_fenetre_memoire(historique)
            _sauvegarder_nav(self.db, dossier_id, nav, historique, donnees)

            # ── Point 2 : collecte complète → narratif + qualité + validation ──
            if agent.is_complete(donnees) and service_type != "validation_en_attente":
                self._generer_narratif_et_qualite(dossier_id, donnees, service_type)
                self._demander_validation_usager(
                    dossier_id, usager, donnees, phone_wa, session["id"]
                )
                _sauvegarder_nav(self.db, dossier_id, nav, historique, donnees)
                return {"success": True, "action": "validation_demandee", "dossier_id": dossier_id}

            # ── Point 2 : traitement réponse validation usager ───────────────────
            if service_type == "validation_en_attente":
                return self._traiter_reponse_validation_usager(
                    text, dossier_id, usager, donnees, phone_wa, session["id"]
                )

            self.wa.send_text(phone_wa, reponse, dossier_id=dossier_id, db_conn=self.db)
            self._handle_structure_search(text, donnees, phone_wa, dossier_id)

            step.metadata["service_type"] = service_type
            step.metadata["manquants"]    = len(agent.missing_fields(donnees))

        return {"success": True, "action": "response_sent", "dossier_id": dossier_id}

    # ── Génération narrative + rapport qualité ───────────────────────────────

    def _generer_narratif_et_qualite(
        self,
        dossier_id: str,
        donnees: dict[str, Any],
        profil_mdph: str,
    ) -> None:
        """
        Déclenché quand la collecte est complète.
        1. Génère les textes narratifs CERFA (sections B/C/D/E)
        2. Calcule le rapport qualité + score de maturité
        3. Persiste le tout en base
        Non bloquant : les erreurs sont loggées sans interrompre le pipeline.
        """
        try:
            from app.engines.cerfa_narrative_engine import generer_textes_narratifs
            from app.engines.cerfa_quality_agent import verifier_qualite_cerfa

            profil_h = donnees.get("profil_principal", "")
            textes = generer_textes_narratifs(
                donnees=donnees,
                profil_mdph=profil_mdph,
                openai_client=self.llm,
                profil_handicap=profil_h,
                model="gpt-4o",
            )

            # Récupérer les alertes inférées stockées en cours de conversation
            _alertes_inf_raw = donnees.get("_alertes_inferees") or []

            rapport = verifier_qualite_cerfa(
                donnees=donnees,
                textes_narratifs=textes,
                profil_mdph=profil_mdph,
                alertes_inferees=_alertes_inf_raw,
            )

            # Fusionner les textes narratifs dans donnees pour la persistance
            donnees.update(textes)

            alertes = rapport.alertes_rouges + rapport.alertes_oranges
            self.db.execute(
                """
                UPDATE dossiers SET
                    texte_b_vie_quotidienne = ?,
                    texte_c_scolarite       = ?,
                    texte_d_situation_pro   = ?,
                    texte_e_projet_vie      = ?,
                    score_maturite_cerfa    = ?,
                    niveau_maturite         = ?,
                    alertes_qualite_json    = ?,
                    rapport_qualite_json    = ?
                WHERE id = ?
                """,
                (
                    textes.get("texte_b_vie_quotidienne", ""),
                    textes.get("texte_c_scolarite", ""),
                    textes.get("texte_d_situation_pro", ""),
                    textes.get("texte_e_projet_vie", ""),
                    rapport.score_maturite,
                    rapport.niveau_maturite,
                    json.dumps(alertes, ensure_ascii=False),
                    json.dumps({
                        "alertes_rouges":        rapport.alertes_rouges,
                        "alertes_oranges":       rapport.alertes_oranges,
                        "zones_pauvres":         rapport.zones_pauvres,
                        "contradictions":        rapport.contradictions,
                        "dimensions_manquantes": rapport.dimensions_manquantes_E,
                        "score_maturite":        rapport.score_maturite,
                        "niveau_maturite":       rapport.niveau_maturite,
                        "retentissement_absent": rapport.retentissement_absent,
                        "projet_vie_incomplet":  rapport.projet_vie_incomplet,
                    }, ensure_ascii=False),
                    dossier_id,
                ),
            )
            self.db.commit()

            logger.info(
                "[NARRATIF] dossier=%s score_maturite=%d niveau=%s alertes_rouges=%d",
                dossier_id[:8], rapport.score_maturite, rapport.niveau_maturite,
                len(rapport.alertes_rouges),
            )

            # ── Analyse de situation (Sprint 5) ──────────────────────────────
            try:
                from app.engines.analyse_situation_engine import analyser_situation
                rapport_dict = {
                    "alertes_rouges":        rapport.alertes_rouges,
                    "retentissement_absent": rapport.retentissement_absent,
                    "projet_vie_incomplet":  rapport.projet_vie_incomplet,
                    "zones_pauvres":         rapport.zones_pauvres,
                    "contradictions":        rapport.contradictions,
                    "score_maturite":        rapport.score_maturite,
                }
                _infos_man_raw = donnees.get("_infos_manquantes_inferees") or []
                analyse = analyser_situation(
                    donnees=donnees,
                    textes_narratifs=textes,
                    rapport_qualite=rapport_dict,
                    profil_mdph=profil_mdph,
                    openai_client=self.llm,
                    infos_manquantes_inferees=_infos_man_raw,
                )
                analyse_dict = analyse.to_dict()
                self.db.execute(
                    """
                    UPDATE dossiers SET
                        analyse_situation_json   = ?,
                        synthese_situation       = ?,
                        niveau_confiance_analyse = ?
                    WHERE id = ?
                    """,
                    (
                        json.dumps(analyse_dict, ensure_ascii=False),
                        analyse.synthese_situation,
                        analyse.niveau_confiance,
                        dossier_id,
                    ),
                )
                self.db.commit()
                logger.info(
                    "[ANALYSE] dossier=%s confiance=%s acteurs=%d preconisations=%d",
                    dossier_id[:8], analyse.niveau_confiance,
                    len(analyse.acteurs_mobilisables),
                    len(analyse.preconisations),
                )
            except Exception as _ae:
                logger.warning("[ANALYSE] Non bloquant : %s", _ae)

            # Notification dashboard si alertes rouges
            if rapport.alertes_rouges:
                try:
                    self.notif.send_quality_alert(
                        dossier_id=dossier_id,
                        alertes=rapport.alertes_rouges,
                        score_maturite=rapport.score_maturite,
                    )
                except Exception:
                    pass  # notification non bloquante

        except Exception as e:
            logger.error("[NARRATIF] Échec génération narratif (non bloquant) : %s", e, exc_info=True)

    # ── Gestion du consentement ──────────────────────────────────────────────

    def _handle_consent_flow(
        self, usager: dict, text: str, phone_wa: str
    ) -> str:
        """Gère le flux de consentement conversationnel. phone_wa = format international pour l'API WhatsApp."""
        from app.audit.consent_history import get_consent_message_for_whatsapp

        # Double-check : si le consentement a été enregistré entre-temps par une
        # tâche parallèle (race condition), ne pas re-traiter ni renvoyer le menu.
        if not check_consent_required(usager["id"], self.db):
            logger.info("[CONSENT] Consentement déjà présent (race condition évitée)")
            return "accepted_already"

        # Si c'est une réponse à la demande de consentement
        result = record_whatsapp_consent(usager["id"], text, self.db)

        if result == "accepted":
            # Commit immédiat : le consentement doit être visible dès le prochain message
            try:
                self.db.commit()
            except Exception:
                pass

            # Récupérer les données déjà connues pour personnaliser le message
            _dossier_row = None
            try:
                _session = self.db.execute(
                    "SELECT dossier_id FROM sessions_whatsapp WHERE telephone = ? OR telephone = ? LIMIT 1",
                    (phone_wa, self._normaliser_telephone_local(phone_wa))
                ).fetchone()
                if _session and _session["dossier_id"]:
                    _dossier_row = self.db.execute(
                        "SELECT synthese_json FROM dossiers WHERE id = ?",
                        (_session["dossier_id"],)
                    ).fetchone()
            except Exception:
                pass

            _donnees_connues = {}
            if _dossier_row:
                import json as _j
                _donnees_connues = _j.loads(_dossier_row["synthese_json"] or "{}")

            _champs_deja_remplis = [
                k for k, v in _donnees_connues.items()
                if v and not k.startswith("_") and k not in ("notes_pro", "email", "urgence")
            ]
            _nb = len(_champs_deja_remplis)

            # Déterminer le nom de l'agent selon le profil déjà connu
            _agent_nom = "l'équipe Facilim"
            try:
                from app.services.conversation.identification import identification_agent as identification_agent_ref
                _next = identification_agent_ref.determine_next_service(_donnees_connues)
                _agent_nom = {"enfant": "Claire", "adulte": "Corrine",
                              "mixte": "Corrine", "protege": "Samia"}.get(_next, "l'équipe Facilim")
            except Exception:
                pass

            _intro_pro = (
                f"Votre accompagnant(e) m'a déjà transmis {_nb} information(s) — "
                f"je ne vous poserai pas les questions correspondantes.\n\n"
            ) if _nb > 0 else ""

            # ── Message d'information post-consentement (Point 1) ─────────────
            # Envoyé UNE SEULE FOIS, uniquement quand result == "accepted".
            # Protection naturelle : ce bloc n'est jamais atteint si :
            #   - consentement déjà présent → retour "accepted_already" ligne 614
            #   - reprise de conversation → _handle_consent_flow non appelée
            #   - relance dashboard → _handle_consent_flow non appelée
            _MSG_INFO_FACILIM = (
                "ℹ️ Facilim prépare votre dossier MDPH à partir des informations "
                "que vous nous communiquez et des documents transmis.\n\n"
                "Avant toute signature ou transmission à la MDPH, il est important "
                "de relire l'ensemble du dossier et de vérifier l'exactitude des informations.\n\n"
                "Vous restez libre de modifier, compléter ou corriger tout élément "
                "avant validation finale."
            )
            self.wa.send_text(phone_wa, _MSG_INFO_FACILIM)
            logger.info("[CONSENT] Message information post-consentement envoyé | usager=%s",
                        usager["id"][:8])

            # Vérifier si la langue est déjà choisie (ne pas renvoyer le menu en boucle)
            _langue_deja_choisie = _donnees_connues.get("_langue_choisie")
            if not _langue_deja_choisie:
                _msg_consent_ok = (
                    f"Merci ! 🙏 Je suis {_agent_nom}.\n\n"
                    f"{_intro_pro}"
                    f"Dans quelle langue souhaitez-vous qu'on échange ?\n\n"
                    f"1️⃣ Français\n"
                    f"2️⃣ English\n"
                    f"3️⃣ Español\n"
                    f"4️⃣ العربية\n"
                    f"5️⃣ Português\n"
                    f"6️⃣ Autre — écrivez directement dans votre langue\n\n"
                    f"📝 Vous pouvez aussi envoyer des *messages vocaux* 🎤\n"
                    f"📎 Ou des *photos de documents*"
                )
                self.wa.send_text(phone_wa, _msg_consent_ok)
        elif result == "refused":
            self.wa.send_text(
                phone_wa,
                "Je comprends votre décision. Vos informations ne seront pas conservées.\n"
                "Si vous changez d'avis, contactez-nous de nouveau. — L'équipe Facilim",
            )
        else:
            # Réponse non reconnue → renvoyer la demande
            self.wa.send_text(phone_wa, get_consent_message_for_whatsapp())
            result = "unclear"

        return result

    # ── Gestion des documents ────────────────────────────────────────────────

    def _handle_document(
        self,
        usager: dict,
        dossier_id: str,
        media_id: str,
        mime_type: str | None,
        phone_wa: str,   # format international pour l'API WhatsApp
        trace: ProcessingTrace,
        phone_db: str = "",  # format local pour lookups DB (dérivé si absent)
    ) -> dict[str, Any]:
        """
        Traite tout média reçu via WhatsApp :
        - Audio/vocal → transcription Whisper → traité comme message texte
        - PDF/Word/Excel → extraction texte + enrichissement LLM du dossier
        - Image → sauvegarde + flag humain
        """
        mime  = (mime_type or "").lower()
        now   = _now_iso()

        # ── Étape 1 : télécharger le média depuis Meta ──────────────────────
        media_result = self.wa.download_media(media_id)

        # ── Cas 1 : MESSAGE VOCAL → Whisper ──────────────────────────────────
        if any(t in mime for t in ("audio", "ogg", "opus", "mpeg", "mp4", "aac", "amr")):
            if media_result:
                content_bytes, _ = media_result
                try:
                    import io as _io
                    transcription = self.llm.audio.transcriptions.create(
                        model="whisper-1",
                        file=("audio.ogg", _io.BytesIO(content_bytes), "audio/ogg"),
                        language="fr",
                        response_format="text",
                    )
                    texte_transcrit = str(transcription).strip()
                    if texte_transcrit:
                        logger.info("[ORCH/AUDIO] Transcription Whisper OK : %d chars", len(texte_transcrit))
                        # Traiter la transcription comme un message texte normal
                        _pdb = phone_db or self._normaliser_telephone_local(phone_wa)
                        return self._process_whatsapp(
                            _pdb, phone_wa, texte_transcrit, media_id + "_transcrit",
                            None, None, trace,
                        )
                except Exception as e:
                    logger.error("[ORCH/AUDIO] Transcription Whisper échouée : %s", e)
                    self.wa.send_text(
                        phone_wa,
                        "Je n'ai pas pu transcrire votre message vocal. Pourriez-vous réécrire "
                        "votre message en texte ? Merci 🙏",
                        dossier_id=dossier_id, db_conn=self.db,
                    )
                    return {"success": True, "action": "audio_transcription_failed"}
            else:
                self.wa.send_text(
                    phone_wa,
                    "Votre message vocal a bien été reçu mais je n'ai pas pu le télécharger. "
                    "Pouvez-vous l'envoyer à nouveau ou l'écrire en texte ?",
                    dossier_id=dossier_id, db_conn=self.db,
                )
                return {"success": True, "action": "audio_download_failed"}

        # ── Cas 2 : PDF, Word, Excel → extraction texte + enrichissement ─────
        elif any(t in mime for t in ("pdf", "word", "excel", "spreadsheet",
                                      "msword", "opendocument", "text")):
            piece_id = str(uuid.uuid4())
            self.db.execute(
                """INSERT INTO pieces_justificatives
                   (id, dossier_id, type_piece, mime_type, uploaded_par,
                    ocr_effectue, flag_validation_humaine, created_at, updated_at)
                   VALUES (?, ?, 'DOCUMENT_RECU', ?, 'whatsapp', 0, 0, ?, ?)""",
                (piece_id, dossier_id, mime, now, now),
            )
            reponse = "Document reçu ✅ Je l'analyse pour préremplir votre dossier..."
            self.wa.send_text(phone_wa, reponse, dossier_id=dossier_id, db_conn=self.db)

            if media_result:
                content_bytes, detected_mime = media_result
                # Importer la fonction d'extraction depuis main.py via import dynamique
                try:
                    from app.main import _extraire_texte_fichier, _llm_client
                    ext = ".pdf" if "pdf" in detected_mime else ".docx" if "word" in detected_mime else ".bin"
                    texte = _extraire_texte_fichier(content_bytes, f"document{ext}", detected_mime)
                    if len(texte) > 50 and not texte.startswith("["):
                        # Enrichissement LLM
                        import json as _json
                        prompt = f"""Extrais les informations MDPH depuis ce document.
Retourne UNIQUEMENT un JSON avec les champs trouvés parmi :
nom_prenom, date_naissance, adresse_complete, departement, num_secu,
diagnostics, traitements, medecin_traitant, impact_quotidien, statut_emploi,
historique_mdph, accident_travail, restrictions_emploi

Document :
{texte[:3000]}"""
                        resp = self.llm.chat.completions.create(
                            model=self.settings.openai_model_fast,
                            messages=[{"role": "user", "content": prompt}],
                            max_tokens=400, temperature=0.0,
                            response_format={"type": "json_object"},
                        )
                        extraits = _json.loads(resp.choices[0].message.content)
                        if extraits:
                            dossier_row = self.db.execute(
                                "SELECT synthese_json FROM dossiers WHERE id = ?", (dossier_id,)
                            ).fetchone()
                            synthese = _json.loads(dossier_row["synthese_json"] or "{}")
                            for k, v in extraits.items():
                                if v and k not in synthese:
                                    synthese[k] = v
                            self.db.execute(
                                "UPDATE dossiers SET synthese_json = ?, updated_at = ? WHERE id = ?",
                                (_json.dumps(synthese, ensure_ascii=False), now, dossier_id),
                            )
                            nb = len(extraits)
                            self.wa.send_text(
                                phone_wa,
                                f"✅ J'ai analysé votre document et prérempli {nb} information(s) "
                                f"dans votre dossier. Continuons !",
                                dossier_id=dossier_id, db_conn=self.db,
                            )
                        else:
                            self.wa.send_text(
                                phone_wa,
                                "Document reçu et enregistré. Continuons la collecte d'informations.",
                                dossier_id=dossier_id, db_conn=self.db,
                            )
                except Exception as e:
                    logger.error("[ORCH/DOC] Extraction échouée : %s", e)
                    self.wa.send_text(
                        phone_wa,
                        "Document reçu ✅ Il sera examiné par l'équipe.",
                        dossier_id=dossier_id, db_conn=self.db,
                    )

            log_event("DOCUMENT_RECU", dossier_id=dossier_id, usager_id=usager["id"],
                      canal="whatsapp", payload={"mime_type": mime}, db_conn=self.db)
            return {"success": True, "action": "document_extracted", "piece_id": piece_id}

        # ── Cas 3 : Image → analyse GPT-4o Vision + extraction infos ────────
        else:
            piece_id = str(uuid.uuid4())
            self.db.execute(
                """INSERT INTO pieces_justificatives
                   (id, dossier_id, type_piece, mime_type, uploaded_par,
                    ocr_effectue, flag_validation_humaine, created_at, updated_at)
                   VALUES (?, ?, 'IMAGE_RECU', ?, 'whatsapp', 0, 0, ?, ?)""",
                (piece_id, dossier_id, mime, now, now),
            )
            self.wa.send_text(
                phone_wa, "Photo reçue 📷 Je l'analyse...",
                dossier_id=dossier_id, db_conn=self.db,
            )

            if media_result:
                content_bytes, _ = media_result
                try:
                    import base64 as _b64, json as _json
                    img_b64 = _b64.b64encode(content_bytes).decode()
                    vision_resp = self.llm.chat.completions.create(
                        model="gpt-4o",
                        messages=[{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": (
                                    "Analyse cette image dans le contexte d'un dossier MDPH. "
                                    "Extrais toutes les informations utiles (nom, prénom, date naissance, "
                                    "diagnostics, ordonnances, certificats, adresse, NIR, etc.). "
                                    "Retourne un JSON avec les champs trouvés parmi : "
                                    "nom_prenom, date_naissance, adresse_complete, num_secu, "
                                    "diagnostics, traitements, medecin_traitant, type_document. "
                                    "Si l'image n'est pas un document médical/administratif, "
                                    "retourne {\"type_document\": \"autre\"}."
                                )},
                                {"type": "image_url", "image_url": {
                                    "url": f"data:{mime};base64,{img_b64}",
                                    "detail": "high",
                                }},
                            ],
                        }],
                        max_tokens=400,
                        response_format={"type": "json_object"},
                    )
                    extraits = _json.loads(vision_resp.choices[0].message.content)
                    extraits.pop("type_document", None)
                    if extraits:
                        dossier_row = self.db.execute(
                            "SELECT synthese_json FROM dossiers WHERE id = ?", (dossier_id,)
                        ).fetchone()
                        synthese = _json.loads(dossier_row["synthese_json"] or "{}")
                        for k, v in extraits.items():
                            if v and k not in synthese:
                                synthese[k] = v
                        self.db.execute(
                            "UPDATE dossiers SET synthese_json = ?, updated_at = ? WHERE id = ?",
                            (_json.dumps(synthese, ensure_ascii=False), now, dossier_id),
                        )
                        self.wa.send_text(
                            phone_wa,
                            f"✅ Photo analysée — {len(extraits)} information(s) extraite(s) pour votre dossier.",
                            dossier_id=dossier_id, db_conn=self.db,
                        )
                    else:
                        self.wa.send_text(
                            phone_wa, "Photo enregistrée ✅ Continuons.",
                            dossier_id=dossier_id, db_conn=self.db,
                        )
                except Exception as e:
                    logger.warning("[ORCH/VISION] GPT-4o Vision échoué : %s", e)
                    self.wa.send_text(
                        phone_wa, "Photo reçue et enregistrée ✅",
                        dossier_id=dossier_id, db_conn=self.db,
                    )

            log_event("IMAGE_RECUE", dossier_id=dossier_id, usager_id=usager["id"],
                      canal="whatsapp", payload={"mime_type": mime}, db_conn=self.db)
            return {"success": True, "action": "image_analyzed", "piece_id": piece_id}

    # ── Déclenchement de l'analyse ───────────────────────────────────────────

    # ── Point 2 : Validation finale usager ──────────────────────────────────

    _TEXTE_VALIDATION_USAGER = (
        "📋 Votre dossier MDPH est prêt.\n\n"
        "Avant de finaliser :\n\n"
        "✅ Je confirme avoir pris connaissance du contenu du dossier "
        "préparé en mon nom et l'avoir relu attentivement.\n\n"
        "✅ Je confirme avoir eu la possibilité de corriger les informations "
        "si nécessaire.\n\n"
        "✅ Je comprends que Facilim est un outil d'aide à la préparation "
        "du dossier.\n\n"
        "✅ Je comprends que la validation finale des informations et la "
        "signature du dossier relèvent de ma responsabilité ou de celle "
        "de mon représentant légal.\n\n"
        "Répondez OUI pour confirmer\n"
        "ou NON pour revenir à votre dossier."
    )

    def _demander_validation_usager(
        self,
        dossier_id: str,
        usager: dict,
        donnees: dict,
        phone_wa: str,
        session_id: str,
    ) -> None:
        """
        Bascule l'état en 'validation_en_attente' et envoie le texte de validation.
        Appelé quand is_complete() est True.
        """
        # Basculer l'état de session
        self.db.execute(
            "UPDATE sessions_whatsapp SET persona_actif = 'validation_en_attente' WHERE id = ?",
            (session_id,)
        )
        self.db.commit()
        # Envoyer le texte de validation
        self.wa.send_text(phone_wa, self._TEXTE_VALIDATION_USAGER,
                          dossier_id=dossier_id, db_conn=self.db)
        logger.info("[VALIDATION] Texte validation envoyé | dossier=%s | usager=%s",
                    dossier_id[:8], usager["id"][:8])

    def _traiter_reponse_validation_usager(
        self,
        text: str,
        dossier_id: str,
        usager: dict,
        donnees: dict,
        phone_wa: str,
        session_id: str,
    ) -> dict:
        """
        Traite la réponse OUI/NON de l'usager à la validation finale.
        OUI → INSERT cerfa_validations + _trigger_analysis
        NON → INSERT cerfa_validations (refus tracé) + retour collecte
        Autre → renvoi du texte de validation
        """
        import hashlib as _hl, json as _j, uuid as _uuid
        from datetime import datetime, timezone

        texte_norm = text.strip().lower()
        _MOTS_OUI = {"oui", "yes", "ok", "d'accord", "dacord", "j'accepte", "accepte"}
        _MOTS_NON = {"non", "no", "refus", "refuse", "annuler", "retour"}

        if texte_norm not in _MOTS_OUI and texte_norm not in _MOTS_NON:
            # Réponse non reconnue → rappel du texte
            self.wa.send_text(phone_wa, self._TEXTE_VALIDATION_USAGER,
                              dossier_id=dossier_id, db_conn=self.db)
            return {"success": True, "action": "validation_rappel", "dossier_id": dossier_id}

        reponse = "OUI" if texte_norm in _MOTS_OUI else "NON"
        now = datetime.now(timezone.utc).isoformat()

        # Hash du contenu au moment de la validation
        synthese_hash = _hl.sha256(
            _j.dumps(donnees, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

        # Récupérer le hash du dernier PDF généré depuis cerfa_audit_log
        _audit_row = self.db.execute(
            """SELECT details_json FROM cerfa_audit_log
               WHERE dossier_id = ? AND event_type = 'generation_cerfa'
               ORDER BY event_at DESC LIMIT 1""",
            (dossier_id,)
        ).fetchone()
        cerfa_pdf_hash = None
        if _audit_row:
            try:
                _d = _j.loads(_audit_row["details_json"] or "{}")
                cerfa_pdf_hash = _d.get("pdf_hash")
            except Exception:
                pass

        # Récupérer la version du dossier
        _dossier_row = self.db.execute(
            "SELECT version FROM dossiers WHERE id = ?", (dossier_id,)
        ).fetchone()
        version = (_dossier_row["version"] if _dossier_row and _dossier_row["version"] else 1)

        # INSERT cerfa_validations
        self.db.execute(
            """INSERT INTO cerfa_validations
               (id, dossier_id, validated_by, canal, type_validation, validated_at,
                synthese_hash, cerfa_pdf_hash, dossier_version, confirmation_texte,
                reponse_usager, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                str(_uuid.uuid4()), dossier_id, usager["id"], "whatsapp", "usager",
                now, synthese_hash, cerfa_pdf_hash, version,
                self._TEXTE_VALIDATION_USAGER, reponse, now
            )
        )

        # INSERT cerfa_audit_log
        from app.main import _log_cerfa_audit
        _log_cerfa_audit(
            db=self.db, dossier_id=dossier_id,
            event_type="validation_usager", canal="whatsapp",
            acteur_id=usager["id"], acteur_type="usager",
            details={"reponse": reponse, "synthese_hash": synthese_hash,
                     "pdf_hash": cerfa_pdf_hash, "version": version},
        )
        self.db.commit()

        if reponse == "OUI":
            self.wa.send_text(
                phone_wa,
                "✅ Merci ! Votre confirmation a bien été enregistrée.\n\n"
                "Votre professionnel accompagnant va finaliser l'envoi de votre dossier.\n"
                "Vous recevrez le formulaire par email pour vérification avant signature.",
                dossier_id=dossier_id, db_conn=self.db,
            )
            logger.info("[VALIDATION] OUI enregistré | dossier=%s", dossier_id[:8])
            self._trigger_analysis(dossier_id, usager, donnees)
            return {"success": True, "action": "validation_acceptee", "dossier_id": dossier_id}
        else:
            # Remettre l'état en collecte
            self.db.execute(
                "UPDATE sessions_whatsapp SET persona_actif = 'adulte' WHERE id = ?",
                (session_id,)
            )
            self.db.commit()
            self.wa.send_text(
                phone_wa,
                "Votre dossier est conservé. Vous pouvez le compléter ou le corriger.\n"
                "Contactez votre professionnel accompagnant si vous avez des questions.",
                dossier_id=dossier_id, db_conn=self.db,
            )
            logger.info("[VALIDATION] NON enregistré | dossier=%s", dossier_id[:8])
            return {"success": True, "action": "validation_refusee", "dossier_id": dossier_id}

    def _trigger_analysis(
        self,
        dossier_id: str,
        usager: dict,
        donnees: dict,
    ) -> None:
        """
        Déclenche le pipeline d'analyse CNSA + Jade quand la collecte est complète.

        Protections :
        - Timeout 30 s sur l'ensemble du pipeline (circuit breaker)
        - Maximum 3 cycles INCOMPLET → flag humain obligatoire au-delà
        - Import défensif du validator (stub si module absent)
        """
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

        _ANALYSE_TIMEOUT_SEC = 30
        _MAX_CYCLES_INCOMPLET = 3

        try:
            dossier = self._get_dossier(dossier_id)

            # ── Protection boucle INCOMPLET infinie ───────────────────────────
            nb_analyses = self.db.execute(
                "SELECT COUNT(*) FROM analyses_scoring WHERE dossier_id = ?",
                (dossier_id,),
            ).fetchone()[0]

            if nb_analyses >= _MAX_CYCLES_INCOMPLET:
                create_flag_humain(
                    dossier_id=dossier_id,
                    raison=(
                        f"Dossier bloqué en cycle INCOMPLET depuis {nb_analyses} analyses. "
                        "Intervention humaine requise avant toute nouvelle tentative."
                    ),
                    educateur_id=None,
                    severite="HAUTE",
                    db_conn=self.db,
                )
                logger.warning(
                    "[ORCH] Analyse bloquée — %d cycles dépassent le max (%d) | dossier=%s",
                    nb_analyses, _MAX_CYCLES_INCOMPLET, dossier_id[:8],
                )
                return

            # ── Transition EN_COLLECTE → EN_ANALYSE ──────────────────────────
            if dossier and dossier.get("statut") == DossierStatut.EN_COLLECTE:
                transition_dossier(
                    dossier_id,
                    DossierStatut.EN_COLLECTE,
                    DossierStatut.EN_ANALYSE,
                    raison="Collecte complète — déclenchement analyse",
                    canal="system",
                    db_conn=self.db,
                )

            texte_synthese = json.dumps(donnees, ensure_ascii=False)
            dept = dossier.get("departement_code", "75") if dossier else "75"

            # ── Import défensif du validator CNSA ─────────────────────────────
            validator = _load_cnsa_validator()

            # ── Pipeline d'analyse avec timeout global ────────────────────────
            def _run_analysis():
                analyse = validator.validate_dossier(texte_synthese, dept)
                scoring = score_dossier(
                    dossier_id=dossier_id,
                    texte_anonymise=texte_synthese,
                    analyse_llm=analyse,
                    confidence_threshold=self.settings.scoring_confidence_threshold,
                    db_conn=self.db,
                )
                return analyse, scoring

            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_run_analysis)
                try:
                    analyse, scoring = future.result(timeout=_ANALYSE_TIMEOUT_SEC)
                except FuturesTimeout:
                    raise TimeoutError(
                        f"Pipeline d'analyse dépassé ({_ANALYSE_TIMEOUT_SEC}s)"
                    )

            # ── Mise à jour scoring ───────────────────────────────────────────
            update_scoring(
                dossier_id=dossier_id,
                score=scoring.get("score_global", 0),
                confiance=scoring.get("confiance", 0.0),
                droits_identifies=scoring.get("droits_identifies", []),
                flag_humain=scoring.get("_flag_humain", False),
                raison_flag=scoring.get("raison_flag"),
                db_conn=self.db,
            )

            # ── Transition selon résultat ─────────────────────────────────────
            if scoring.get("statut_analyse") == "COMPLET" and not scoring.get("_flag_humain"):
                transition_dossier(
                    dossier_id,
                    DossierStatut.EN_ANALYSE,
                    DossierStatut.COMPLET,
                    raison=(
                        f"Score={scoring.get('score_global')}/100 — "
                        f"confiance={scoring.get('confiance', 0):.0%}"
                    ),
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
            logger.error("[ORCH] Erreur analyse : %s", e, exc_info=True)
            create_flag_humain(
                dossier_id=dossier_id,
                raison=f"Erreur moteur d'analyse : {e}",
                educateur_id=None,
                severite="HAUTE",
                db_conn=self.db,
            )

    # ── Helpers base de données ───────────────────────────────────────────────

    def _get_or_create_usager(self, phone: str) -> dict[str, Any]:
        """phone doit être en format local canonique (0XXXXXXXXX) — normalisé en amont."""
        from app.security.encryption import encrypt, decrypt, generate_reference

        phone_enc = encrypt(phone)
        row = self.db.execute(
            "SELECT * FROM usagers WHERE telephone_enc = ? LIMIT 1",
            (phone_enc,),
        ).fetchone()

        if row:
            return dict(row)

        # Fallback : si le pro a saisi le format international, chercher par déchiffrement
        # (coûteux mais correct — seulement si la recherche directe échoue)
        try:
            all_rows = self.db.execute(
                "SELECT id, telephone_enc, reference_interne, canal_prefere, est_mineur, "
                "langue_preferee, actif, created_at, updated_at FROM usagers "
                "WHERE telephone_enc IS NOT NULL LIMIT 200"
            ).fetchall()
            for r in all_rows:
                try:
                    decrypted = decrypt(r["telephone_enc"] or "")
                    if decrypted:
                        _d = decrypted.strip().lstrip("+")
                        _norm = ("0" + _d[2:]) if (_d.startswith("33") and len(_d) == 11) else _d
                        if _norm == phone:
                            logger.info("[ORCH] Usager retrouvé via déchiffrement fallback | phone=***%s", phone[-4:])
                            return dict(r)
                except Exception:
                    continue
        except Exception as e:
            logger.warning("[ORCH] Fallback déchiffrement échoué : %s", e)

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

    def _get_or_create_session(self, phone: str, usager_id: str | None) -> dict[str, Any]:
        # Chercher par téléphone (texte clair) — cherche les deux formats
        phone_intl = "33" + phone[1:] if phone.startswith("0") else phone
        row = self.db.execute(
            "SELECT * FROM sessions_whatsapp WHERE telephone = ? OR telephone = ? LIMIT 1",
            (phone, phone_intl),
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

    # ── Changement de service (identification → spécialisé) ─────────────────

    def _switch_service(
        self,
        session_id: str,
        service_type: str,
        usager: dict,
        donnees: dict,
    ) -> None:
        """
        Bascule définitivement vers le service spécialisé.
        Persiste persona_actif dans sessions_whatsapp ET est_mineur dans usagers.
        Commit immédiat pour que les requêtes concurrentes voient le changement.
        """
        now = _now_iso()
        self.db.execute(
            "UPDATE sessions_whatsapp SET persona_actif = ?, derniere_activite = ? WHERE id = ?",
            (service_type, now, session_id),
        )
        # Persister est_mineur selon le service
        est_mineur = 1 if service_type in ("enfant",) else 0
        self.db.execute(
            "UPDATE usagers SET est_mineur = ?, updated_at = ? WHERE id = ?",
            (est_mineur, now, usager["id"]),
        )
        usager["est_mineur"] = est_mineur
        self.db.commit()   # commit immédiat — visible aux requêtes concurrentes
        logger.info(
            "[SWITCH] %s → %s | usager=%s",
            "identification", service_type, usager["id"][:8],
        )

    # ── Règle Q60 — Recherche de structures géolocalisées ───────────────────

    def _handle_structure_search(
        self,
        texte: str,
        donnees: dict,
        phone_wa: str,   # format international (33XXXXXXXXX) pour l'API WhatsApp
        dossier_id: str,
    ) -> None:
        """
        Règle Agent Métier — Question 60 :
        Si l'usager mentionne un type d'établissement (IME, ESAT, ESRP…),
        recherche les structures à proximité et envoie les suggestions en
        second message WhatsApp, séparé de la réponse conversationnelle.
        """
        types_etab = detecter_mention_etablissement(texte)
        if not types_etab:
            return

        logger.info(f"[Q60] Établissements détectés : {types_etab} | dossier={dossier_id[:8]}")

        adresse   = donnees.get("adresse_complete")
        dept_code = donnees.get("departement")
        prenom    = (donnees.get("nom_prenom") or "").split()[0] if donnees.get("nom_prenom") else None

        google_key = getattr(self.settings, "google_places_api_key", None) or None

        try:
            resultat = rechercher_structures(
                types_etablissement=types_etab,
                adresse_usager=adresse,
                departement_code=dept_code,
                rayon_km=30,
                max_resultats=3,
                google_api_key=google_key,
            )
            message_structs = formater_suggestions_whatsapp(
                resultat=resultat,
                types_etablissement=types_etab,
                prenom_usager=prenom,
            )
            self.wa.send_text(phone_wa, message_structs, dossier_id=dossier_id, db_conn=self.db)
            log_event(
                "STRUCTURES_SUGGEREES",
                dossier_id=dossier_id,
                canal="whatsapp",
                payload={"types": types_etab, "nb_resultats": len(resultat.structures)},
                db_conn=self.db,
            )
        except Exception as e:
            logger.warning(f"[Q60] Recherche structures échouée (non-bloquant) : {e}")

    # ── Fenêtre de contexte avec résumé glissant ────────────────────────────

    def _appliquer_fenetre_memoire(self, historique: list[dict]) -> list[dict]:
        """
        Gère la fenêtre de contexte conversationnelle pour limiter le coût en tokens.

        Si l'historique dépasse memory_summary_threshold messages :
          - Les messages plus anciens que les memory_window_size derniers sont résumés
            en un message système compact via l'API LLM
          - Les memory_window_size messages récents sont conservés mot-à-mot
          - Le résumé est injecté en tête comme message système

        Si le seuil n'est pas atteint, seule la troncature max_conversation_history
        s'applique (comportement antérieur, sans appel LLM supplémentaire).
        """
        threshold   = self.settings.memory_summary_threshold
        window_size = self.settings.memory_window_size

        if len(historique) <= threshold:
            return historique[-self.settings.max_conversation_history:]

        messages_anciens = historique[:-window_size]
        messages_recents = historique[-window_size:]

        resume = self._resumer_historique(messages_anciens)

        contexte_compresse = [{"role": "system", "content": resume}] + messages_recents
        logger.info(
            f"[ORCH/MEMORY] Résumé glissant : {len(messages_anciens)} messages → 1 résumé | "
            f"{len(messages_recents)} messages récents conservés"
        )
        return contexte_compresse

    def _resumer_historique(self, messages: list[dict]) -> str:
        """
        Génère un résumé compact de l'historique ancien via GPT-4o-mini.
        Le résumé est formulé pour servir de contexte système dans la suite de la conversation.
        """
        if not messages:
            return ""

        dialogue = "\n".join(
            f"{m['role'].capitalize()} : {m['content']}"
            for m in messages
            if m.get("content")
        )

        try:
            response = self.llm.chat.completions.create(
                model=self.settings.openai_model_fast,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Tu es un assistant MDPH. Résume de manière concise et factuelle "
                            "l'échange précédent entre l'usager et l'assistant. "
                            "Conserve uniquement les informations structurelles importantes : "
                            "nom, situation familiale, type de handicap mentionné, droits évoqués, "
                            "documents transmis, et accords/refus exprimés. "
                            "Formule en français, 5 lignes maximum."
                        ),
                    },
                    {"role": "user", "content": dialogue},
                ],
                max_tokens=300,
                temperature=0.0,
            )
            return f"[Résumé de l'échange précédent] {response.choices[0].message.content.strip()}"
        except Exception as e:
            logger.warning(f"[ORCH/MEMORY] Erreur résumé LLM : {e} — troncature simple appliquée")
            # Fallback : résumé textuel non-LLM basé sur les derniers messages
            extrait = dialogue[-800:]
            return f"[Contexte antérieur (résumé automatique indisponible)] {extrait}"

    def _send_error_message(self, phone: str) -> None:
        try:
            self.wa.send_text(
                phone,
                "Une erreur est survenue. Nos équipes ont été alertées. "
                "Veuillez réessayer dans quelques minutes. — L'équipe Facilim",
            )
        except Exception:
            pass
