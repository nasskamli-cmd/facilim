"""
main.py — Point d'entrée FastAPI de MDPH-Backbone.
Expose deux endpoints principaux :

  POST /api/v1/dossiers/initiate
    Reçoit un dossier brut, le fait passer par toute la pipeline
    (parsing → anonymisation → audit CNSA → FALC → WhatsApp si incomplet).

  POST /api/v1/webhook/whatsapp
    Réceptionne les réponses des usagers via le webhook WhatsApp Business,
    enrichit le dossier et relance le moteur d'analyse.

  GET /api/v1/dossiers/{dossier_id}
    Permet à l'éducateur de consulter l'état d'un dossier depuis son tableau de bord.

NOTE : Le stockage en mémoire (_dossiers_store) est un placeholder de développement.
En production, remplacer par Redis + PostgreSQL.
"""

import asyncio
import logging
import uuid
import importlib
import json
import requests
from datetime import datetime, timezone
from typing import Any
from pathlib import Path

from fastapi import (
    FastAPI, HTTPException, Request, Body, Cookie,
    UploadFile, File, Form, Depends,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel, Field

from config import get_settings
import database
from database import purge_dossier_pii
import auth as _auth_module
from services.email_client import send_verification_code, send_dossier_pdf
from services.pdf_generator import generer_pdf_dossier
from services.cerfa_filler import remplir_cerfa
from services.humanizer import humaniser_texte
from services.ocr_image import ocr_image
from services.conversation_agent import (
    generer_reponse_agent,
    construire_historique_conversation,
    extract_cerfa_field_from_reply,
    get_next_cerfa_field,
    prepopuler_cerfa_depuis_dossier,
    MEDICAL_FIELDS,
    _MEDICAL_REDIRECT_SENT_KEY,
    _MESSAGE_CANAL_SECURISE,
)

settings = get_settings()

# --------------------------------------------------------------------------- #
# Logging                                                                      #
# --------------------------------------------------------------------------- #
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Imports dynamiques des modules numérotés                                     #
# --------------------------------------------------------------------------- #
_parser    = importlib.import_module("1_ingestion.parser")
_anon      = importlib.import_module("1_ingestion.anonymizer")
_validator = importlib.import_module("2_intelligence.cnsa_validator")
_jargon    = importlib.import_module("3_accessibility.jargon_splitter")
_wa        = importlib.import_module("services.whatsapp_client")
_media     = importlib.import_module("services.media_client")
_llm_client = importlib.import_module("4_llm_client.openai_client")

extract_text        = _parser.extract_text
anonymize           = _anon.anonymize
validate_dossier    = _validator.validate_dossier
simplify_questions  = _jargon.simplify_questions
translate_to_language = _jargon.translate_to_language
format_for_whatsapp = _jargon.format_for_whatsapp
send_questions_sequence = _wa.send_questions_sequence
send_text_message   = _wa.send_text_message
download_media      = _media.download_media
transcribe_audio    = _media.transcribe_audio
detect_language     = _media.detect_language

# --------------------------------------------------------------------------- #
# FastAPI application                                                          #
# --------------------------------------------------------------------------- #
app = FastAPI(
    title="MDPH-Backbone API",
    description="Infrastructure automatisée de génération, d'audit et de scoring de dossiers MDPH.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS : allow_origins=["*"] est incompatible avec allow_credentials=True (spec W3C).
# Le dashboard étant servi par FastAPI (même origine), les cookies fonctionnent
# sans CORS credentials. On autorise toutes les origines en lecture seule.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_UPLOAD_SIZE_MB = getattr(settings, "max_upload_size_mb", 20)
_MAX_BODY_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# Middleware ASGI pur — BaseHTTPMiddleware est interdit sur les routes multipart/form-data :
# son call_next() consomme le stream de réception avant que FastAPI puisse lire le fichier,
# ce qui produit une réponse vide ou HTML → response.json() explose côté JS → "Erreur réseau".
class _LimitBodySizeMiddleware:
    def __init__(self, app: Any) -> None:
        self._app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            headers_map = {k.lower(): v for k, v in scope.get("headers", [])}
            cl = headers_map.get(b"content-length")
            if cl and int(cl) > _MAX_BODY_BYTES:
                resp = JSONResponse(
                    status_code=413,
                    content={"detail": (
                        f"Fichier trop volumineux. "
                        f"Limite autorisée : {MAX_UPLOAD_SIZE_MB} Mo."
                    )},
                )
                await resp(scope, receive, send)
                return
        await self._app(scope, receive, send)

app.add_middleware(_LimitBodySizeMiddleware)

app.mount("/static", StaticFiles(directory="static"), name="static")

# Router auth (/auth/login, /auth/verify, /auth/logout)
app.include_router(_auth_module.router)

# ── Agents V2 : router + startup ────────────────────────────────────────────
_agents_import_error = None
try:
    from api_agents import router as _agents_router, startup_agents as _startup_agents
    app.include_router(_agents_router)
    _agents_router_loaded = True
    logger.info("[V2] api_agents router chargé avec succès.")
except Exception as _e:
    _agents_router_loaded = False
    _agents_import_error = str(_e)
    logger.warning(f"api_agents non chargé : {_e}", exc_info=True)

quota_dossiers_actifs = getattr(settings, "quota_dossiers_actifs", 100)

# Déduplication webhook WhatsApp ─────────────────────────────────────────────
# WhatsApp Business Cloud API retente le webhook si elle ne reçoit pas HTTP 200
# dans les 20 secondes. Comme notre traitement (LLM + DB) peut durer 30–60 s,
# chaque message déclenchait 4–8 relances identiques.
# Solution : on mémorise les wamid déjà traités et on retourne 200 immédiatement.
_processed_wamids: set[str] = set()
_MAX_WAMID_CACHE = 5_000   # garde-fou mémoire : purge quand on dépasse cette taille

# --------------------------------------------------------------------------- #
# Modèles Pydantic                                                             #
# --------------------------------------------------------------------------- #
class InitiateDossierRequest(BaseModel):
    """Corps de la requête pour initier l'analyse d'un dossier."""
    texte_brut: str | None = Field(
        default=None,
        description="Texte libre décrivant la situation de la personne (compte-rendu médical, bilan, etc.).",
    )
    telephone_famille: str
    departement_code: str
    educateur_id: str | None = None
    email_famille: str | None = None
    nom_enfant: str | None = Field(default=None, description="Nom de l'enfant.")
    prenom_enfant: str | None = Field(default=None, description="Prénom de l'enfant.")
    ddn_enfant: str | None = Field(default=None, description="Date de naissance (JJ/MM/AAAA).")
    adresse_enfant: str | None = Field(default=None, description="Adresse (numéro et rue).")
    cp_enfant: str | None = Field(default=None, description="Code postal.")
    commune_enfant: str | None = Field(default=None, description="Commune.")


class DossierStatusResponse(BaseModel):
    """Réponse retournée après initiation ou consultation d'un dossier."""
    dossier_id: str
    statut: str
    score_global: int
    droits_identifies: list[str]
    elements_manquants: list[str]
    questions_envoyees: list[str]
    recommandation_finale: str
    whatsapp_envoye: bool
    created_at: str
    updated_at: str


class WhatsAppWebhookPayload(BaseModel):
    """Payload minimal attendu du webhook WhatsApp (simplifié pour la lisibilité)."""
    object: str
    entry: list[Any]


# --------------------------------------------------------------------------- #
# Handler global : garantit que toute exception non gérée retourne du JSON    #
# (uvicorn renverrait sinon du HTML → response.json() explose en JS)          #
# --------------------------------------------------------------------------- #
@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(f"[UNHANDLED] {request.method} {request.url.path} — {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Erreur serveur ({type(exc).__name__}) : {exc}"},
    )


# --------------------------------------------------------------------------- #
# Pages HTML (login / dashboard)                                               #
# --------------------------------------------------------------------------- #
from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="static")


@app.get("/login")
async def page_login(request: Request):
    return FileResponse("static/login.html")


@app.get("/verify")
async def page_verify(request: Request):
    return FileResponse("static/verify.html")


@app.get("/debug")
async def debug_endpoint():
    """Endpoint de diagnostic sans auth."""
    import os, sys
    return {
        "status": "running",
        "version": "V2",
        "static_exists": os.path.isdir("static"),
        "dashboard_exists": os.path.isfile("static/dashboard.html"),
        "login_exists": os.path.isfile("static/login.html"),
        "cwd": os.getcwd(),
        "agents_router_loaded": _agents_router_loaded,
        "agents_import_error": _agents_import_error,
        "python_path": sys.path[:3],
        "agents_dir_exists": os.path.isdir("agents"),
        "api_agents_exists": os.path.isfile("api_agents.py"),
    }

@app.get("/dashboard")
async def page_dashboard(request: Request, session_token: str | None = Cookie(default=None)):
    """
    Page principale du tableau de bord.
    Redirige vers /login si l'utilisateur n'est pas authentifié.
    """
    try:
        if not session_token or not _auth_module.is_valid_session(session_token):
            return RedirectResponse(url="/login", status_code=302)
        return FileResponse("static/dashboard.html")
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Erreur dashboard: {e}", exc_info=True)
        return RedirectResponse(url="/login", status_code=302)


@app.get("/")
async def page_root(request: Request):
    return FileResponse("static/login.html")


# --------------------------------------------------------------------------- #
# Auth API                                                                     #
# --------------------------------------------------------------------------- #
@app.post("/api/v1/auth/send-code")
async def auth_send_code(body: dict = Body(embed=False)):
    email = body.get("email", "").strip().lower()
    if not email:
        raise HTTPException(status_code=422, detail="Email requis.")
    code = _auth_module.generate_code(email)
    send_verification_code(email, code)
    return {"status": "sent"}


@app.post("/api/v1/auth/verify-code")
async def auth_verify_code(body: dict = Body(embed=False)):
    email = body.get("email", "").strip().lower()
    code  = body.get("code", "").strip()
    if not email or not code:
        raise HTTPException(status_code=422, detail="Email et code requis.")
    token = _auth_module.verify_code(email, code)
    if not token:
        raise HTTPException(status_code=401, detail="Code invalide ou expiré.")
    response = JSONResponse({"status": "ok"})
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=28800,
    )
    return response


@app.post("/api/v1/auth/logout")
async def auth_logout(session_token: str | None = Cookie(default=None)):
    if session_token:
        _auth_module.invalidate_session(session_token)
    response = JSONResponse({"status": "logged_out"})
    response.delete_cookie("session_token")
    return response


# --------------------------------------------------------------------------- #
# ENDPOINT 1 — POST /api/v1/dossiers/initiate                                 #
# --------------------------------------------------------------------------- #
@app.post(
    "/api/v1/dossiers/initiate",
    summary="Initier l'analyse d'un dossier MDPH",
    tags=["Dossiers"],
)
async def initiate_dossier(request: InitiateDossierRequest):
    """
    Pipeline complète d'analyse d'un dossier MDPH :

    1. Extraction et nettoyage du texte brut
    2. Anonymisation RGPD par LLM (remplacement des DCP par tokens)
    3. Audit multi-agents CNSA (Expert GEVA, Juriste, Coordinateur local)
    4. Si INCOMPLET :
       a. Génération de questions ciblées
       b. Traduction FALC (questions simples pour l'usager)
       c. Envoi WhatsApp à la famille
    5. Retour de l'état au tableau de bord de l'éducateur
    """
    quota = quota_dossiers_actifs
    nb_actifs = database.count_dossiers_actifs()
    if nb_actifs >= quota:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "QUOTA_ATTEINT",
                "message": f"Vous avez atteint la limite de {quota} dossier(s) actif(s). Clôturez ou archivez des dossiers existants avant d'en créer un nouveau.",
            },
        )

    dossier_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    dossier: dict[str, Any] = {
        "dossier_id":           dossier_id,
        "telephone_famille":    request.telephone_famille,
        "departement_code":     request.departement_code,
        "educateur_id":         request.educateur_id,
        "email_famille":        request.email_famille,
        "nom_enfant":           request.nom_enfant,
        "prenom_enfant":        request.prenom_enfant,
        "ddn_enfant":           request.ddn_enfant,
        "adresse_enfant":       request.adresse_enfant,
        "cp_enfant":            request.cp_enfant,
        "commune_enfant":       request.commune_enfant,
        "statut":               "EN_COURS",
        "created_at":           now,
        "updated_at":           now,
        "historique_reponses":  [],
        "analyse":              {},
    }

    logger.info(f"Nouveau dossier | id={dossier_id} | dept={request.departement_code}")

    try:
        # ── Étape 1 : Extraction et nettoyage du texte ────────────────────────
        texte_extrait = extract_text(
            raw_input=request.texte_brut,
            source_type="text",
        )
        dossier = _extraire_donnees_depuis_texte(dossier, texte_extrait)

        # ── Étape 2 : Anonymisation RGPD ──────────────────────────────────────
        anon_result = anonymize(texte_extrait)
        texte_anon  = anon_result.get("anonymized_text", texte_extrait)
        logger.info(
            f"Dossier {dossier_id} | anonymisation OK | DCP={anon_result.get('token_count', 0)}"
        )

        # ── Étape 3 : Audit CNSA ──────────────────────────────────────────────
        analyse = validate_dossier(texte_anon, request.departement_code)

        if analyse.get("recommandation_finale"):
            analyse["recommandation_finale"] = humaniser_texte(analyse["recommandation_finale"])

        dossier["analyse"] = analyse
        dossier["statut"]  = analyse.get("statut", "INCOMPLET")
        database.save_dossier(dossier)

        questions_falc_envoyees: list[str] = []
        whatsapp_envoye = False
        _is_enfant_intro = True  # valeur par defaut
        _is_enfant_intro = True  # valeur par defaut

        # ── Étape 4 : Gestion du cas INCOMPLET ─────────────────────────────
        if dossier["statut"] == "INCOMPLET":
            questions_expertes = analyse.get("questions_manquantes", [])

            if questions_expertes:
                # Déterminer adulte ou enfant AVANT la simplification FALC
                _ds_intro = analyse.get("donnees_structurees") or {}
                _is_enfant_intro = _ds_intro.get("is_enfant", True)
                _ddn_str = dossier.get("ddn_enfant") or _ds_intro.get("date_naissance") or ""
                if _ddn_str and _is_enfant_intro:
                    try:
                        _parts = _ddn_str.replace("/", "-").split("-")
                        if len(_parts) == 3:
                            _annee = int(_parts[-1]) if len(_parts[-1]) == 4 else int(_parts[0])
                            if datetime.now().year - _annee >= 18:
                                _is_enfant_intro = False
                    except Exception:
                        pass

                # Simplification FALC avec le bon registre (adulte ou enfant)
                questions_falc = simplify_questions(questions_expertes[:1], is_enfant=_is_enfant_intro)

                # Traduction dans la langue de la famille si elle n'est pas francophone
                langue_famille = dossier.get("langue_famille", "fr")
                questions_falc = translate_to_language(questions_falc, langue_famille)

                # Formatage pour WhatsApp (boutons ou texte libre)
                questions_wa = format_for_whatsapp(questions_falc)

                if _is_enfant_intro:
                    intro = (
                        "Bonjour !\n\n"
                        "Nous préparons le dossier MDPH de votre enfant.\n"
                        "Pour qu'il soit complet, nous avons besoin "
                        "de quelques informations supplémentaires.\n\n"
                        "Répondez à votre rythme — vous pouvez écrire librement, "
                        "envoyer un message vocal ou une photo."
                    )
                else:
                    intro = (
                        "Bonjour !\n\n"
                        "Nous préparons votre dossier MDPH.\n"
                        "Pour qu'il soit complet, nous avons besoin "
                        "de quelques informations supplémentaires.\n\n"
                        "Répondez à votre rythme — vous pouvez écrire librement, "
                        "envoyer un message vocal ou une photo."
                    )

                wa_results = send_questions_sequence(
                    phone_number=request.telephone_famille,
                    formatted_questions=questions_wa,
                    intro_message=intro,
                )

                questions_falc_envoyees = questions_falc
                whatsapp_envoye = any("error" not in r for r in wa_results)
                dossier["questions_en_attente"] = len(questions_falc)

                logger.info(
                    f"Dossier {dossier_id} | INCOMPLET | "
                    f"{len(questions_falc)} questions FALC envoyées | "
                    f"WhatsApp={'OK' if whatsapp_envoye else 'ÉCHEC'}"
                )

        # ── Vérification données personnelles avant de valider COMPLET ──────────
        if dossier["statut"] == "COMPLET":
            champs_manquants = _verifier_donnees_personnelles(dossier)
            if champs_manquants:
                dossier["statut"] = "INCOMPLET"
                if not analyse.get("questions_manquantes"):
                    analyse["questions_manquantes"] = []
                analyse["questions_manquantes"] = champs_manquants + analyse.get("questions_manquantes", [])
                dossier["analyse"] = analyse
                logger.info(
                    f"Dossier {dossier_id} : passage COMPLET → INCOMPLET "
                    f"(données personnelles manquantes : {champs_manquants})"
                )

        # ── Envoi WhatsApp si données personnelles manquantes (2ème chance) ────
        if dossier["statut"] == "INCOMPLET" and not whatsapp_envoye:
            questions_restantes = analyse.get("questions_manquantes", [])
            if questions_restantes:
                questions_falc = simplify_questions(questions_restantes[:4], is_enfant=_is_enfant_intro)
                langue_famille = dossier.get("langue_famille", "fr")
                questions_falc = translate_to_language(questions_falc, langue_famille)
                questions_wa   = format_for_whatsapp(questions_falc)
                intro = (
                    "Bonjour 👋\n\n"
                    "Pour compléter le dossier MDPH, nous avons besoin "
                    "de quelques informations supplémentaires.\n\n"
                    "Merci de répondre à ces questions."
                )
                wa_results = send_questions_sequence(
                    phone_number=request.telephone_famille,
                    formatted_questions=questions_wa,
                    intro_message=intro,
                )
                questions_falc_envoyees = questions_falc
                whatsapp_envoye = any("error" not in r for r in wa_results)
                dossier["questions_en_attente"] = len(questions_falc)
                logger.info(
                    f"Dossier {dossier_id} | INCOMPLET (données perso) | "
                    f"{len(questions_falc)} questions FALC envoyées | "
                    f"WhatsApp={'OK' if whatsapp_envoye else 'ÉCHEC'}"
                )

        # ── Vérification finale avant envoi PDF+CERFA ────────────────────────
        if dossier["statut"] == "COMPLET":
            pret, champs_pdf_manquants = _dossier_pret_a_envoyer(dossier)
            if not pret:
                dossier["statut"] = "INCOMPLET"
                questions_blocage = [
                    f"Pouvez-vous nous donner le/la {c} de la personne ?"
                    for c in champs_pdf_manquants
                ]
                analyse["questions_manquantes"] = (
                    questions_blocage + analyse.get("questions_manquantes", [])
                )
                dossier["analyse"] = analyse
                logger.warning(
                    f"Dossier {dossier_id} | PDF BLOQUÉ — champs manquants : {champs_pdf_manquants}"
                )
                if not whatsapp_envoye:
                    questions_falc_bloquage = simplify_questions(questions_blocage[:4], is_enfant=_is_enfant_intro)
                    langue_famille = dossier.get("langue_famille", "fr")
                    questions_falc_bloquage = translate_to_language(questions_falc_bloquage, langue_famille)
                    wa_bloquage = format_for_whatsapp(questions_falc_bloquage)
                    wa_res = send_questions_sequence(
                        phone_number=request.telephone_famille,
                        formatted_questions=wa_bloquage,
                        intro_message=(
                            "Bonjour 👋\n\nIl nous manque encore quelques informations "
                            "indispensables pour finaliser le dossier MDPH.\n\n"
                            "Merci de répondre à ces dernières questions."
                        ),
                    )
                    questions_falc_envoyees = questions_falc_bloquage
                    whatsapp_envoye = any("error" not in r for r in wa_res)
                    dossier["questions_en_attente"] = len(questions_falc_bloquage)

            else:
                email_famille = dossier.get("email_famille")
                if email_famille:
                    try:
                        pdf_bytes   = generer_pdf_dossier(dossier)
                        cerfa_bytes = None
                        try:
                            cerfa_bytes = remplir_cerfa(dossier)
                        except Exception as cerfa_err:
                            logger.warning(
                                f"CERFA non généré (initiation) : {cerfa_err}",
                                exc_info=True,  # log complet → Railway logs
                            )
                        envoye = send_dossier_pdf(
                            email_famille, pdf_bytes, dossier["dossier_id"],
                            cerfa_bytes=cerfa_bytes,
                        )
                        logger.info(
                            f"PDF + CERFA {'envoyés' if envoye else 'ÉCHEC envoi'} "
                            f"| email={email_famille} | dossier={dossier_id}"
                        )
                        if envoye:
                            try:
                                phone = dossier.get("telephone_famille")
                                if phone:
                                    msg_complet = _construire_message_complet(dossier)
                                    send_text_message(phone, msg_complet)
                            except Exception as wa_err:
                                logger.warning(f"Message scoring WhatsApp non envoyé (initiation) : {wa_err}")
                        if envoye:
                            try:
                                purge_dossier_pii(dossier_id)
                            except Exception as rgpd_err:
                                logger.error(f"Purge RGPD échouée (initiation) : {rgpd_err}")
                    except Exception as pdf_err:
                        logger.error(f"Erreur génération/envoi PDF (initiation) : {pdf_err}")
                else:
                    logger.warning(
                        f"Dossier COMPLET sans email famille — PDF NON ENVOYÉ | "
                        f"id={dossier_id} | email_famille={dossier.get('email_famille')!r}"
                    )

        dossier["questions_falc_envoyees"] = questions_falc_envoyees
        dossier["whatsapp_envoye"]         = whatsapp_envoye
        dossier["updated_at"] = datetime.now(timezone.utc).isoformat()
        database.save_dossier(dossier)

        return DossierStatusResponse(
            dossier_id=dossier_id,
            statut=dossier["statut"],
            score_global=analyse.get("score_global", 0),
            droits_identifies=analyse.get("droits_identifies", []),
            elements_manquants=analyse.get("elements_manquants", []),
            questions_envoyees=questions_falc_envoyees,
            recommandation_finale=analyse.get("recommandation_finale", ""),
            whatsapp_envoye=whatsapp_envoye,
            created_at=dossier["created_at"],
            updated_at=dossier["updated_at"],
        )

    except ValueError as e:
        logger.warning(f"Dossier {dossier_id} | Erreur de validation : {e}")
        raise HTTPException(status_code=422, detail=str(e))
    except NotImplementedError as e:
        logger.warning(f"Dossier {dossier_id} | Fonctionnalité non disponible : {e}")
        raise HTTPException(status_code=501, detail=str(e))
    except RuntimeError as e:
        logger.error(f"Dossier {dossier_id} | Erreur service externe : {e}")
        dossier["statut"] = "ERREUR"
        database.save_dossier(dossier)
        raise HTTPException(status_code=503, detail=f"Erreur du service d'analyse : {e}")
    except Exception as e:
        logger.exception(f"Dossier {dossier_id} | Erreur inattendue : {e}")
        dossier["statut"] = "ERREUR"
        database.save_dossier(dossier)
        raise HTTPException(status_code=500, detail="Erreur interne du serveur.")


# --------------------------------------------------------------------------- #
# ENDPOINT 2 — POST /api/v1/webhook/whatsapp                                  #
# --------------------------------------------------------------------------- #

async def _process_whatsapp_async(
    phone_number: str,
    user_reply: str,
    message_type: str,
    detected_language: str | None,
) -> None:
    """
    Traitement asynchrone complet d'un message WhatsApp.

    Appelé via asyncio.create_task() APRÈS que le webhook a déjà retourné 200.
    WhatsApp ne retente donc plus le webhook pendant ce traitement.
    Les appels LLM bloquants (validate_dossier, generer_reponse_agent) sont
    exécutés dans un thread via asyncio.to_thread() pour ne pas bloquer
    la boucle d'événements.
    """
    try:
        dossier = database.get_active_dossier_by_phone(phone_number)
        if not dossier:
            logger.warning(f"Aucun dossier actif pour le numéro {phone_number}")
            return

        # ── Mémorisation de la langue ─────────────────────────────────────────
        if detected_language and not dossier.get("langue_famille"):
            dossier["langue_famille"] = detected_language
            logger.info(f"Langue famille mémorisée : {detected_language} | dossier={dossier['dossier_id']}")

        # ── Enregistrement de la réponse ──────────────────────────────────────
        label_type = "photo (OCR)" if message_type == "image" else message_type
        dossier["historique_reponses"].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reponse":   user_reply,
            "type":      label_type,
            "langue":    detected_language,
        })
        dossier["updated_at"] = datetime.now(timezone.utc).isoformat()
        dossier["questions_en_attente"] = 0

        # ── Relance de l'analyse (LLM → thread) ──────────────────────────────
        texte_enrichi = _compose_enriched_text(dossier)
        dossier = _extraire_donnees_depuis_texte(dossier, texte_enrichi)
        database.save_dossier(dossier)

        nouvelle_analyse = await asyncio.to_thread(
            validate_dossier, texte_enrichi, dossier["departement_code"]
        )

        if nouvelle_analyse.get("recommandation_finale"):
            nouvelle_analyse["recommandation_finale"] = await asyncio.to_thread(
                humaniser_texte, nouvelle_analyse["recommandation_finale"]
            )

        dossier["analyse"] = nouvelle_analyse
        nouveau_statut = nouvelle_analyse.get("statut", "INCOMPLET")

        if nouveau_statut == "COMPLET":
            champs_manquants = _verifier_donnees_personnelles(dossier)
            if champs_manquants:
                nouveau_statut = "INCOMPLET"
                nouvelle_analyse["questions_manquantes"] = (
                    champs_manquants + nouvelle_analyse.get("questions_manquantes", [])
                )
                dossier["analyse"] = nouvelle_analyse
                logger.info(
                    f"Dossier {dossier['dossier_id']} : passage COMPLET → INCOMPLET "
                    f"(données personnelles manquantes)"
                )

        dossier["statut"] = nouveau_statut
        database.save_dossier(dossier)

        logger.info(
            f"Dossier {dossier['dossier_id']} | Relance analyse | statut={nouveau_statut}"
        )

        if nouveau_statut == "COMPLET":
            pret, champs_pdf_manquants = _dossier_pret_a_envoyer(dossier)
            if not pret:
                nouveau_statut    = "INCOMPLET"
                dossier["statut"] = "INCOMPLET"
                questions_blocage = [
                    f"Pouvez-vous nous donner le/la {c} de la personne ?" for c in champs_pdf_manquants
                ]
                nouvelle_analyse["questions_manquantes"] = (
                    questions_blocage + nouvelle_analyse.get("questions_manquantes", [])
                )
                dossier["analyse"] = nouvelle_analyse
                database.save_dossier(dossier)
                logger.warning(
                    f"Dossier {dossier['dossier_id']} | PDF BLOQUÉ (webhook) "
                    f"— champs manquants : {champs_pdf_manquants}"
                )
                _ds_wh = nouvelle_analyse.get("donnees_structurees") or {}
                _is_enf_wh = _ds_wh.get("is_enfant", True)
                questions_falc_bl = simplify_questions(questions_blocage[:4], is_enfant=_is_enf_wh)
                langue_famille = dossier.get("langue_famille", "fr")
                questions_falc_bl = translate_to_language(questions_falc_bl, langue_famille)
                wa_bl = format_for_whatsapp(questions_falc_bl)
                await asyncio.to_thread(
                    send_questions_sequence,
                    phone_number,
                    wa_bl,
                    "Nous avons presque toutes les informations nécessaires. "
                    "Il nous manque encore quelques détails pour finaliser le dossier.",
                )
                dossier["questions_en_attente"] = len(questions_falc_bl)
                database.save_dossier(dossier)

            else:
                email_famille = dossier.get("email_famille")
                if email_famille:
                    try:
                        pdf_bytes   = await asyncio.to_thread(generer_pdf_dossier, dossier)
                        cerca_bytes = None
                        try:
                            cerca_bytes = await asyncio.to_thread(remplir_cerfa, dossier)
                        except Exception as cerfa_err:
                            logger.warning(
                                f"CERFA non généré (webhook) : {cerfa_err}",
                                exc_info=True,  # log complet → Railway logs
                            )
                        envoye = await asyncio.to_thread(
                            send_dossier_pdf,
                            email_famille, pdf_bytes, dossier["dossier_id"],
                            cerca_bytes,
                        )
                        logger.info(
                            f"PDF + CERFA {'envoyés' if envoye else 'ÉCHEC'} "
                            f"| email={email_famille} | dossier={dossier['dossier_id']}"
                        )
                        if envoye:
                            try:
                                phone = dossier.get("telephone_famille")
                                if phone:
                                    msg_complet = _construire_message_complet(dossier)
                                    await asyncio.to_thread(send_text_message, phone, msg_complet)
                            except Exception as wa_err:
                                logger.warning(f"Message scoring WhatsApp non envoyé (webhook) : {wa_err}")
                        if envoye:
                            try:
                                purge_dossier_pii(dossier["dossier_id"])
                            except Exception as rgpd_err:
                                logger.error(f"Purge RGPD échouée (webhook) : {rgpd_err}")
                    except Exception as pdf_err:
                        logger.error(f"Erreur génération/envoi PDF : {pdf_err}")
                else:
                    logger.warning(
                        f"Dossier COMPLET sans email famille — PDF NON ENVOYÉ (webhook) | "
                        f"id={dossier['dossier_id']} | email_famille={dossier.get('email_famille')!r}"
                    )

        # ── Réponse intelligente via agent conversationnel ────────────────────
        if nouveau_statut == "INCOMPLET":
            elements_manquants = nouvelle_analyse.get("questions_manquantes", [])
            historique_conv = construire_historique_conversation(
                dossier.get("historique_reponses", [])
            )
            donnees_collectees = {
                "nom":          dossier.get("nom_enfant"),
                "prenom":       dossier.get("prenom_enfant"),
                "date_naissance": dossier.get("ddn_enfant"),
                "adresse":      dossier.get("adresse_enfant"),
                "code_postal":  dossier.get("cp_enfant"),
                "commune":      dossier.get("commune_enfant"),
                "telephone":    dossier.get("telephone_famille"),
                "departement":  dossier.get("departement_code"),
                "email":        dossier.get("email_famille"),
            }
            ds = nouvelle_analyse.get("donnees_structurees") or {}
            is_enfant_agent = ds.get("is_enfant", True)
            _ddn_agent = dossier.get("ddn_enfant") or ds.get("date_naissance") or ""
            if _ddn_agent and is_enfant_agent:
                try:
                    _parts = _ddn_agent.replace("/", "-").split("-")
                    if len(_parts) == 3:
                        _annee = int(_parts[-1]) if len(_parts[-1]) == 4 else int(_parts[0])
                        if datetime.now().year - _annee >= 18:
                            is_enfant_agent = False
                except Exception:
                    pass
            donnees_collectees.update({
                "genre":           ds.get("genre"),
                "situation_fam":   ds.get("situation_familiale"),
                "diagnostic":      ds.get("diagnostic_principal"),
                "droits_demandes": ", ".join(nouvelle_analyse.get("droits_identifies") or []),
                "adulte_ou_enfant": "adulte" if not is_enfant_agent else "enfant",
            })
            donnees_collectees = {k: v for k, v in donnees_collectees.items() if v}

            try:
                _oai_client = _llm_client._client
            except Exception:
                import openai as _openai
                _oai_client = _openai.OpenAI(api_key=settings.openai_api_key)

            # ── Machine à états CERFA ─────────────────────────────────────────
            cerfa_reponses = dossier.get("cerfa_reponses") or {}

            # Pré-remplissage automatique depuis les données déjà connues du dossier
            # (évite de reposer des questions sur le nom, l'adresse, le genre, etc.)
            prepopuler_cerfa_depuis_dossier(cerfa_reponses, dossier)
            dossier["cerfa_reponses"] = cerfa_reponses

            current_field = get_next_cerfa_field(cerfa_reponses)

            # Cas 1 : le prochain champ est le sentinel de redirection médicale
            force_medical_redirect = (current_field == _MEDICAL_REDIRECT_SENT_KEY)
            if force_medical_redirect:
                # Marquer le message comme envoyé AVANT l'appel à generer_reponse_agent
                # pour qu'il ne soit pas renvoyé au prochain message.
                cerfa_reponses[_MEDICAL_REDIRECT_SENT_KEY] = "sent"
                dossier["cerfa_reponses"] = cerfa_reponses
                logger.info("[CERFA] Redirection canal sécurisé à envoyer.")

            # Cas 2 : champ non-médical — tenter d'extraire la valeur depuis la réponse
            elif current_field and current_field not in MEDICAL_FIELDS:
                try:
                    valeur = await asyncio.to_thread(
                        extract_cerfa_field_from_reply, user_reply, current_field, _oai_client
                    )
                    if valeur:
                        cerfa_reponses[current_field] = valeur
                        dossier["cerfa_reponses"] = cerfa_reponses
                        logger.info(f"[CERFA] Champ '{current_field}' extrait : {valeur[:40]}")
                except Exception as ex_err:
                    logger.warning(f"[CERFA] Extraction échouée pour '{current_field}': {ex_err}")

            reponse_envoyee = False
            try:
                reponse_agent = await asyncio.to_thread(
                    generer_reponse_agent,
                    user_reply,             # message_entrant
                    historique_conv,        # historique
                    donnees_collectees,     # donnees_collectees
                    elements_manquants,     # elements_manquants
                    _oai_client,            # openai_client
                    is_enfant_agent,        # is_enfant
                    cerfa_reponses,         # cerfa_reponses
                    force_medical_redirect, # force_medical_redirect
                )
                await asyncio.to_thread(send_text_message, phone_number, reponse_agent)
                reponse_envoyee = True
                dossier["historique_reponses"].append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "role":      "assistant",
                    "content":   reponse_agent,
                    "type":      "agent",
                })
                dossier["questions_en_attente"] = 1
                database.save_dossier(dossier)
                logger.info(f"Dossier {dossier['dossier_id']} | Agent → réponse envoyée")
            except Exception as agent_err:
                logger.error(f"Agent conversationnel erreur : {agent_err}", exc_info=True)

            if not reponse_envoyee:
                if elements_manquants:
                    msg_fallback = f"Merci pour votre réponse. Pouvez-vous me préciser : {elements_manquants[0]} ?"
                else:
                    msg_fallback = "Merci pour votre réponse. Nous analysons votre dossier."
                try:
                    await asyncio.to_thread(send_text_message, phone_number, msg_fallback)
                except Exception as fb_err:
                    logger.error(f"Fallback WhatsApp aussi échoué : {fb_err}")
                database.save_dossier(dossier)

    except Exception as e:
        logger.exception(f"[_process_whatsapp_async] Erreur non gérée : {e}")


@app.post(
    "/api/v1/webhook/whatsapp",
    summary="Webhook de réception des réponses WhatsApp",
    tags=["Webhook"],
)
async def whatsapp_webhook(request: Request):
    """
    Endpoint de webhook WhatsApp Business Cloud API.

    Retourne HTTP 200 IMMÉDIATEMENT après déduplication.
    WhatsApp arrête alors de retenter — le traitement LLM s'exécute en arrière-plan.

    Deux cas d'usage :
      1. GET de vérification (lors de la configuration Meta Developer) →
         géré par l'endpoint GET ci-dessous.
      2. POST de notification (réponse de l'usager) →
         extraction du wamid pour déduplication, retour 200, traitement async.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Corps de la requête JSON invalide.")

    phone_number, user_reply, message_type, detected_language = _extract_whatsapp_reply(body)

    if not phone_number or not user_reply:
        logger.debug("Webhook WhatsApp : notification de statut ou payload vide, ignoré.")
        return {"status": "ignored"}

    # ── Déduplication par wamid ───────────────────────────────────────────────
    # WhatsApp retente jusqu'à 5 × si elle ne reçoit pas HTTP 200 dans les 20 s.
    # On mémorise chaque wamid traité pour éviter de répondre plusieurs fois
    # au même message.
    wamid = _extract_wamid(body)
    if wamid:
        if wamid in _processed_wamids:
            logger.info(f"[DEDUP] Message déjà traité, ignoré : wamid={wamid}")
            return {"status": "duplicate_ignored"}
        _processed_wamids.add(wamid)
        if len(_processed_wamids) > _MAX_WAMID_CACHE:
            _processed_wamids.clear()   # purge simple — les wamid anciens n'ont plus d'intérêt

    logger.info(
        f"Réponse WhatsApp reçue | from={phone_number} | type={message_type} "
        f"| wamid={wamid} | aperçu='{user_reply[:60]}'"
    )

    # ── Lancement du traitement en arrière-plan ───────────────────────────────
    # On retourne 200 AVANT de lancer le LLM.
    asyncio.create_task(
        _process_whatsapp_async(phone_number, user_reply, message_type, detected_language)
    )
    return {"status": "received"}


@app.get(
    "/api/v1/webhook/whatsapp",
    summary="Vérification du webhook WhatsApp (Meta Developer Console)",
    tags=["Webhook"],
)
async def whatsapp_webhook_verify(request: Request):
    """
    Endpoint de vérification du webhook requis par Meta lors de la configuration.
    Meta envoie un GET avec hub.mode, hub.challenge et hub.verify_token.
    """
    params    = dict(request.query_params)
    mode      = params.get("hub.mode")
    token     = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.whatsapp_verify_token:
        logger.info("Vérification webhook WhatsApp réussie.")
        from fastapi.responses import FileResponse, PlainTextResponse
        return PlainTextResponse(challenge)

    logger.warning(f"Tentative de vérification webhook échouée | token_reçu={token}")
    raise HTTPException(status_code=403, detail="Token de vérification invalide.")


# --------------------------------------------------------------------------- #
# ENDPOINT 3 — GET /api/v1/dossiers                                            #
# --------------------------------------------------------------------------- #
@app.get(
    "/api/v1/dossiers",
    summary="Lister tous les dossiers",
    tags=["Dossiers"],
)
async def list_dossiers():
    """Retourne la liste de tous les dossiers pour le tableau de bord."""
    dossiers = database.list_dossiers()
    return {"dossiers": dossiers}


# --------------------------------------------------------------------------- #
# ENDPOINT 4 — GET /api/v1/dossiers/{dossier_id}                              #
# --------------------------------------------------------------------------- #
@app.get(
    "/api/v1/dossiers/{dossier_id}",
    response_model=DossierStatusResponse,
    summary="Consulter l'état d'un dossier",
    tags=["Dossiers"],
)
async def get_dossier(dossier_id: str):
    """Retourne l'état actuel d'un dossier pour le tableau de bord de l'éducateur."""
    dossier = database.get_dossier_by_id(dossier_id)
    if not dossier:
        raise HTTPException(status_code=404, detail=f"Dossier '{dossier_id}' introuvable.")

    analyse = dossier.get("analyse") or {}

    return DossierStatusResponse(
        dossier_id=dossier_id,
        statut=dossier.get("statut", "INCONNU"),
        score_global=analyse.get("score_global", 0),
        droits_identifies=analyse.get("droits_identifies", []),
        elements_manquants=analyse.get("elements_manquants", []),
        questions_envoyees=dossier.get("questions_falc_envoyees", []),
        recommandation_finale=analyse.get("recommandation_finale", ""),
        whatsapp_envoye=dossier.get("whatsapp_envoye", False),
        created_at=dossier.get("created_at", ""),
        updated_at=dossier.get("updated_at", ""),
    )


# --------------------------------------------------------------------------- #
# ENDPOINT 5 — DELETE /api/v1/dossiers/{dossier_id}                           #
# --------------------------------------------------------------------------- #
@app.delete(
    "/api/v1/dossiers/{dossier_id}",
    summary="Supprimer un dossier",
    tags=["Dossiers"],
)
async def delete_dossier(dossier_id: str, session_token: str | None = Cookie(default=None)):
    """Suppression logique d'un dossier (soft delete, RGPD-safe)."""
    if not session_token or not _auth_module.is_valid_session(session_token):
        raise HTTPException(status_code=401, detail="Session expirée. Veuillez vous reconnecter.")
    dossier = database.get_dossier_by_id(dossier_id)
    if not dossier:
        raise HTTPException(status_code=404, detail="Dossier introuvable.")
    session_info = _auth_module.get_session_info(session_token) if hasattr(_auth_module, "get_session_info") else {}
    deleted_by   = session_info.get("email") if session_info else None
    ok = database.soft_delete_dossier(dossier_id, deleted_by=deleted_by)
    if not ok:
        raise HTTPException(status_code=404, detail="Dossier introuvable ou déjà supprimé.")
    logger.info(f"[DELETE] Dossier {dossier_id} supprimé (soft) par {deleted_by}.")
    return {"status": "deleted", "dossier_id": dossier_id}


# --------------------------------------------------------------------------- #
# ENDPOINT 6 — DELETE /api/v1/admin/reset-dossier/{telephone}                 #
# --------------------------------------------------------------------------- #
@app.delete(
    "/api/v1/admin/reset-dossier/{telephone}",
    tags=["Admin"],
)
async def admin_reset_dossier(telephone: str):
    """
    Supprime tous les dossiers associés à un numéro de téléphone.
    Permet de relancer un test complet depuis zéro.
    Accès sans auth — à utiliser uniquement en dev/test.
    """
    telephone_clean = telephone.lstrip("+").replace(" ", "")
    with database._get_connection() as conn:
        cur  = conn.cursor()
        rows = cur.execute(
            "SELECT dossier_id FROM dossiers WHERE telephone_famille = ?",
            (telephone_clean,)
        ).fetchall()
        if not rows:
            return {"deleted": 0, "message": "Aucun dossier trouvé pour ce numéro"}
        ids = [r[0] for r in rows]
        cur.execute("DELETE FROM dossiers WHERE telephone_famille = ?", (telephone_clean,))
        conn.commit()
    logger.info(f"[RESET] {len(ids)} dossier(s) supprimé(s) pour {telephone_clean}")
    return {
        "deleted": len(ids),
        "ids": ids,
        "message": "Dossiers supprimés — prêt pour un nouveau test",
    }


# --------------------------------------------------------------------------- #
# ENDPOINT 7 — GET /api/v1/debug/whatsapp-test                                #
# --------------------------------------------------------------------------- #
@app.get("/api/v1/debug/whatsapp-test", tags=["Debug"])
async def debug_whatsapp_test(to: str = "33642087770"):
    """
    Diagnostic rapide : tente d'envoyer un message WhatsApp et retourne
    la réponse brute de l'API Meta (succès ou message d'erreur complet).
    Accessible sans authentification pour faciliter le debug en prod.
    """
    url = f"https://graph.facebook.com/v19.0/{settings.whatsapp_phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_api_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": "Test Facilim — système opérationnel."},
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        return {"status_code": resp.status_code, "response": resp.json()}
    except Exception as exc:
        return {"error": str(exc)}


# --------------------------------------------------------------------------- #
# ENDPOINT 8 — POST /api/v1/extract-text                                      #
# --------------------------------------------------------------------------- #
@app.post(
    "/api/v1/extract-text",
    summary="Extraire le texte d'un fichier PDF ou Word",
    tags=["Fichiers"],
)
async def extract_text_from_file(
    file: UploadFile = File(...),
    session_token: str | None = Cookie(default=None),
):
    """
    Reçoit un fichier PDF ou Word, extrait son texte brut et le retourne.
    Le dashboard utilise ce texte pour alimenter la pipeline d'analyse CNSA.

    Formats acceptés : .pdf, .docx
    Taille maximale  : MAX_UPLOAD_SIZE_MB Mo (configuré dans .env)
    """
    if not session_token or not _auth_module.is_valid_session(session_token):
        raise HTTPException(status_code=401, detail="Session expirée. Veuillez vous reconnecter.")

    import services.file_extractor as _fe
    from pathlib import Path as _Path

    ext = _Path(file.filename).suffix.lower()
    if ext not in _fe.EXTENSIONS_AUTORISES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Format non supporté : '{ext}'. "
                "Formats acceptés : PDF (.pdf), Word (.docx), image (.jpg, .jpeg, .png)."
            ),
        )

    try:
        contenu = await file.read()
        if not contenu:
            raise ValueError("Le fichier reçu est vide.")
        size_mb = len(contenu) / (1024 * 1024)
        if size_mb > MAX_UPLOAD_SIZE_MB:
            raise ValueError(f"Fichier trop volumineux ({size_mb:.1f} Mo). Limite : {MAX_UPLOAD_SIZE_MB} Mo.")
        resultat = _fe.extraire_texte(file.filename, contenu)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Erreur extraction fichier '{file.filename}' : {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Impossible d'extraire le texte du fichier : {e}",
        )

    texte = resultat.get("texte", "")
    logger.info(f"Texte extrait | fichier={file.filename} | {len(texte)} caractères")
    return {
        "texte":         texte,
        "filename":      file.filename,
        "avertissement": resultat.get("avertissement"),
    }


# --------------------------------------------------------------------------- #
# ENDPOINT 9 — POST /api/v1/dossiers/{dossier_id}/enrich                      #
# --------------------------------------------------------------------------- #
@app.post(
    "/api/v1/dossiers/{dossier_id}/enrich",
    summary="Enrichir un dossier avec un fichier ou du texte supplémentaire",
    tags=["Dossiers"],
)
async def enrich_dossier(
    dossier_id: str,
    file: UploadFile | None = File(default=None),
    texte_libre: str | None = Form(default=None),
    session_token: str | None = Cookie(default=None),
):
    """
    Enrichit un dossier (texte libre ou fichier PDF/Word/image) et relance l'analyse.
    Retourne TOUJOURS du JSON — même en cas d'erreur serveur.
    """
    # ── Guard : toute exception non HTTPException devient une 500 JSON ─────────
    try:
        return await _enrich_dossier_impl(
            dossier_id=dossier_id,
            file=file,
            texte_libre=texte_libre,
            session_token=session_token,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"[ENRICH] Erreur inattendue sur dossier {dossier_id} : {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur serveur inattendue ({type(exc).__name__}) : {exc}",
        )


async def _enrich_dossier_impl(
    dossier_id: str,
    file: UploadFile | None,
    texte_libre: str | None,
    session_token: str | None,
) -> dict:
    """Implémentation réelle de l'enrichissement — appelée depuis le wrapper."""

    # ── Auth ──────────────────────────────────────────────────────────────────
    if not session_token or not _auth_module.is_valid_session(session_token):
        raise HTTPException(
            status_code=401,
            detail="Session expirée. Veuillez vous reconnecter.",
        )

    # ── Dossier ───────────────────────────────────────────────────────────────
    dossier = database.get_dossier_by_id(dossier_id)
    if not dossier:
        raise HTTPException(status_code=404, detail=f"Dossier '{dossier_id}' introuvable.")
    if dossier.get("statut") == "ERREUR":
        raise HTTPException(
            status_code=422,
            detail="Ce dossier est en erreur — supprimez-le et créez-en un nouveau.",
        )

    # ── Extraction du texte ───────────────────────────────────────────────────
    texte_ajoute   = ""
    fichier_source = "texte_libre"

    if file and file.filename:
        import services.file_extractor as _fe
        from pathlib import Path as _Path

        ext = _Path(file.filename).suffix.lower()
        if ext not in _fe.EXTENSIONS_AUTORISES:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Format non supporté : '{ext}'. "
                    "Formats acceptés : PDF (.pdf), Word (.doc/.docx), "
                    "image (.jpg, .jpeg, .png)."
                ),
            )

        contenu = await file.read()

        if len(contenu) == 0:
            raise HTTPException(status_code=422, detail="Le fichier reçu est vide.")

        if len(contenu) > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Fichier trop volumineux "
                    f"({len(contenu) // (1024*1024)} Mo). "
                    f"Limite : {MAX_UPLOAD_SIZE_MB} Mo."
                ),
            )

        try:
            resultat     = _fe.extraire_texte(file.filename, contenu)
            texte_ajoute = resultat.get("texte", "")
        except ValueError as ve:
            raise HTTPException(status_code=422, detail=str(ve))
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Impossible d'extraire le texte du fichier : {exc}",
            )

        fichier_source = file.filename

        if not texte_ajoute:
            avert = (
                "Le fichier ne contient pas de texte exploitable "
                "(PDF scanné ou image sans OCR). "
                "Saisissez les informations dans l'onglet Texte libre."
            )
            raise HTTPException(status_code=422, detail=avert)

    if texte_libre and texte_libre.strip():
        texte_ajoute = (texte_ajoute + "\n\n" + texte_libre.strip()).strip()

    if not texte_ajoute:
        raise HTTPException(
            status_code=422,
            detail="Aucun contenu fourni. Saisissez du texte ou importez un fichier.",
        )

    # ── Mise à jour du dossier ────────────────────────────────────────────────
    if not isinstance(dossier.get("historique_reponses"), list):
        dossier["historique_reponses"] = []

    dossier["historique_reponses"].append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reponse":   texte_ajoute[:500],
        "type":      "enrichissement",
        "source":    fichier_source,
    })
    dossier["updated_at"] = datetime.now(timezone.utc).isoformat()

    # ── Re-analyse (sauvegarde intermédiaire avant l'appel LLM) ──────────────
    # On sauvegarde d'abord l'historique pour ne pas le perdre si le LLM échoue.
    database.save_dossier(dossier)

    texte_enrichi = _compose_enriched_text(dossier)
    dossier       = _extraire_donnees_depuis_texte(dossier, texte_enrichi)

    try:
        nouvelle_analyse = validate_dossier(texte_enrichi, dossier["departement_code"])
    except Exception as exc:
        logger.exception(f"[ENRICH] validate_dossier échoué : {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de l'analyse du dossier : {exc}",
        )

    if nouvelle_analyse.get("recommandation_finale"):
        try:
            nouvelle_analyse["recommandation_finale"] = humaniser_texte(
                nouvelle_analyse["recommandation_finale"]
            )
        except Exception:
            pass  # humanisation non bloquante

    dossier["analyse"] = nouvelle_analyse
    dossier["statut"]  = nouvelle_analyse.get("statut", "INCOMPLET")
    database.save_dossier(dossier)
    logger.info(f"[ENRICH] Dossier {dossier_id} enrichi | statut={dossier['statut']}")

    # ── Envoi PDF si dossier complet ──────────────────────────────────────────
    if dossier["statut"] == "COMPLET":
        email_famille = dossier.get("email_famille")
        if email_famille:
            try:
                pdf_bytes   = generer_pdf_dossier(dossier)
                cerfa_bytes = None
                try:
                    cerfa_bytes = remplir_cerfa(dossier)
                except Exception as cerfa_err:
                    logger.warning(
                        f"[ENRICH] CERFA non généré : {cerfa_err}",
                        exc_info=True,
                    )
                if send_dossier_pdf(email_famille, pdf_bytes, dossier_id, cerfa_bytes=cerfa_bytes):
                    purge_dossier_pii(dossier_id)
            except Exception as pdf_err:
                logger.error(f"[ENRICH] Erreur envoi PDF : {pdf_err}")

    return {
        "dossier_id":  dossier_id,
        "statut":      dossier["statut"],
        "score_global": dossier["analyse"].get("score_global", 0),
        "message":     "Dossier enrichi et re-analysé avec succès.",
    }


# --------------------------------------------------------------------------- #
# FONCTIONS UTILITAIRES INTERNES                                               #
# --------------------------------------------------------------------------- #

def _extract_wamid(webhook_body: dict) -> str | None:
    """Extrait le message ID WhatsApp (wamid) depuis le payload webhook pour déduplication."""
    try:
        msg = webhook_body["entry"][0]["changes"][0]["value"]["messages"][0]
        return msg.get("id")
    except (IndexError, KeyError, TypeError):
        return None


def _extract_whatsapp_reply(
    webhook_body: dict,
) -> tuple[str | None, str | None, str, str | None]:
    """
    Extrait le numéro d'expéditeur, le texte de réponse et la langue depuis le payload webhook.
    Gère les messages texte, les boutons interactifs, les messages vocaux et les photos.

    Returns:
        Tuple (phone_number, reply_text, message_type, detected_language).
        detected_language : code ISO 639-1 ou None si non détectable.
    """
    try:
        entry   = webhook_body.get("entry", [])
        changes = entry[0].get("changes", [])
        value   = changes[0].get("value", {})
        messages = value.get("messages", [])
        if not messages:
            return None, None, "unknown", None
        msg      = messages[0]
        phone    = msg.get("from")
        msg_type = msg.get("type", "unknown")
        language = None
        reply    = None

        if msg_type == "text":
            reply = msg.get("text", {}).get("body", "")
            try:
                language = detect_language(reply)
            except Exception:
                pass

        elif msg_type == "interactive":
            interactive = msg.get("interactive", {})
            i_type = interactive.get("type")
            if i_type == "button_reply":
                reply = interactive.get("button_reply", {}).get("title", "")
            elif i_type == "list_reply":
                reply = interactive.get("list_reply", {}).get("title", "")

        elif msg_type == "audio":
            audio_id = msg.get("audio", {}).get("id")
            try:
                audio_bytes, mime_type = download_media(audio_id)
                transcription = transcribe_audio(audio_bytes, mime_type)
                reply = transcription
                try:
                    language = detect_language(reply)
                except Exception:
                    pass
                logger.info(f"Audio transcrit | from={phone} | {len(reply)} chars")
            except RuntimeError as e:
                logger.error(f"Échec transcription audio : {e}")

        elif msg_type == "image":
            image_id = msg.get("image", {}).get("id")
            try:
                image_bytes, mime_actual = download_media(image_id)
                reply = ocr_image(image_bytes, mime_actual)
                logger.info(f"Photo OCR | from={phone} | {len(reply)} chars")
            except Exception as e:
                logger.error(f"Échec OCR photo : {e}")

        else:
            logger.debug(f"Type de message non géré : {msg_type}")

        return phone, reply, msg_type, language

    except (IndexError, KeyError, TypeError):
        return None, None, "unknown", None


def _compose_enriched_text(dossier: dict) -> str:
    """
    Construit un texte consolidé combinant :
    - Le texte initial du dossier (analyse existante)
    - Toutes les réponses WhatsApp reçues de la famille
    Ce texte est ensuite passé à validate_dossier pour re-analyser.
    """
    parties = []
    analyse = dossier.get("analyse") or {}
    syntheses = analyse.get("synthese_agents") or {}
    for cle in ("situation_globale", "besoins", "geva_pro", "recommandation"):
        val = syntheses.get(cle) or ""
        if val.strip():
            parties.append(val.strip())
    ds = analyse.get("donnees_structurees") or {}
    if ds:
        lignes_ds = [
            f"{k}: {v}" for k, v in ds.items()
            if v and str(v).strip() not in ("null", "None", "", "false", "true")
        ]
        if lignes_ds:
            parties.append("Données structurées extraites :\n" + "\n".join(lignes_ds))
    champs_perso = [
        ("Nom",              dossier.get("nom_enfant")),
        ("Prénom",           dossier.get("prenom_enfant")),
        ("Date de naissance", dossier.get("ddn_enfant")),
        ("Adresse",          dossier.get("adresse_enfant")),
        ("Code postal",      dossier.get("cp_enfant")),
        ("Commune",          dossier.get("commune_enfant")),
        ("Email",            dossier.get("email_famille")),
    ]
    lignes_perso = [f"{k}: {v}" for k, v in champs_perso if v and str(v).strip()]
    if lignes_perso:
        parties.append("Informations personnelles :\n" + "\n".join(lignes_perso))
    historique = dossier.get("historique_reponses") or []
    reponses_famille = [
        r.get("reponse") or r.get("content") or ""
        for r in historique
        if isinstance(r, dict)
        and r.get("role", "user") != "assistant"
        and r.get("type") != "agent"
    ]
    reponses_valides = [r.strip() for r in reponses_famille if r.strip()]
    if reponses_valides:
        parties.append("Réponses de la famille :\n" + "\n".join(reponses_valides))
    return "\n\n---\n\n".join(parties) if parties else "Aucune information disponible."


def _extraire_donnees_depuis_texte(dossier: dict, texte_brut: str) -> dict:
    """
    Tente d'extraire automatiquement les données personnelles manquantes
    (nom, prénom, date de naissance, adresse, CP, commune) directement
    depuis le texte du document importé, via le LLM.

    N'écrase jamais un champ déjà renseigné par l'éducateur dans le formulaire.
    En cas d'échec (LLM indisponible, parsing raté), retourne le dossier inchangé.
    """
    champs_manquants = [
        c for c in ("nom_enfant", "prenom_enfant", "ddn_enfant",
                    "adresse_enfant", "cp_enfant", "commune_enfant")
        if not str(dossier.get(c) or "").strip()
    ]
    if not champs_manquants:
        return dossier

    logger.info(
        f"Dossier {dossier['dossier_id']} | extraction auto données perso "
        f"| champs manquants : {champs_manquants}"
    )

    system_prompt = (
        "\nTu es un extracteur de données structurées.\n"
        "À partir d'un document médico-social, extrais les informations personnelles du bénéficiaire principal.\n"
        "Réponds UNIQUEMENT en JSON valide avec cette structure exacte :\n"
        "{\n"
        '  "nom": "<nom de famille ou chaîne vide>",\n'
        '  "prenom": "<prénom ou chaîne vide>",\n'
        '  "date_naissance": "<JJ/MM/AAAA ou chaîne vide>",\n'
        '  "adresse": "<numéro et rue ou chaîne vide>",\n'
        '  "code_postal": "<5 chiffres ou chaîne vide>",\n'
        '  "commune": "<ville ou chaîne vide>"\n'
        "}\n"
        "Si une information n'est pas dans le document, laisse la valeur en chaîne vide.\n"
        "Ne devine jamais — extrais uniquement ce qui est explicitement écrit.\n"
    )
    user_message = f"Extrais les données personnelles du bénéficiaire depuis ce document :\n\n{texte_brut[:3000]}"

    try:
        _llm_mod = importlib.import_module("4_llm_client.openai_client")
        raw = _llm_mod.call_llm(
            system_prompt=system_prompt,
            user_message=user_message,
            temperature=0.0,
            max_tokens=256,
        )
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            parts = cleaned.split("```")
            cleaned = parts[1] if len(parts) > 1 else cleaned
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()
        extracted = json.loads(cleaned)
        mapping = {
            "nom_enfant":     extracted.get("nom", "").strip(),
            "prenom_enfant":  extracted.get("prenom", "").strip(),
            "ddn_enfant":     extracted.get("date_naissance", "").strip(),
            "adresse_enfant": extracted.get("adresse", "").strip(),
            "cp_enfant":      extracted.get("code_postal", "").strip(),
            "commune_enfant": extracted.get("commune", "").strip(),
        }
        for champ, valeur in mapping.items():
            if valeur and not str(dossier.get(champ) or "").strip():
                dossier[champ] = valeur
    except Exception as exc:
        logger.warning(f"_extraire_donnees_depuis_texte : échec LLM ({exc}) — dossier inchangé")

    return dossier


def _construire_message_complet(dossier: dict) -> str:
    """
    Construit le message WhatsApp envoyé quand le dossier est COMPLET.
    Inclut le scoring prédictif par droit — honnête, avec probabilité et recommandation.
    """
    analyse = dossier.get("analyse") or {}
    scoring = analyse.get("scoring_predictif") or {}
    droits  = analyse.get("droits_identifies") or []
    score   = analyse.get("score_global", 0)
    reco    = analyse.get("recommandation_finale") or ""
    nom     = dossier.get("prenom_enfant") or dossier.get("nom_enfant") or "votre proche"

    lignes = [
        f"Votre dossier MDPH pour {nom} est finalisé.",
        f"Score de complétude : {score}/100",
        "",
        "Droits analysés :",
    ]

    for droit in droits:
        droit_key = droit.upper().replace(" ", "_").replace("-", "_")
        info = (
            scoring.get(droit)
            or scoring.get(droit.upper())
            or scoring.get(droit_key)
        )
        if info and isinstance(info, dict):
            prob  = info.get("probabilite", "?")
            r_msg = info.get("recommandation", "")
            if isinstance(prob, int):
                if prob >= 75:
                    emoji = "🟢"
                elif prob >= 40:
                    emoji = "🟡"
                else:
                    emoji = "🔴"
            else:
                emoji = "⚪"
            ligne = f"{emoji} {droit} : {prob}% de chances d'aboutir"
            if r_msg:
                ligne += f"\n   → {r_msg}"
            lignes.append(ligne)
        else:
            lignes.append(f"• {droit}")

    if reco:
        lignes += ["", f"Action prioritaire : {reco}"]

    lignes += [
        "",
        "Le dossier complet et le CERFA pré-rempli ont été envoyés à votre adresse email.",
        "Déposez-les à votre MDPH ou envoyez-les par recommandé.",
    ]

    return "\n".join(lignes)


def _dossier_pret_a_envoyer(dossier: dict) -> tuple[bool, list[str]]:
    """Vérification finale avant envoi PDF+CERFA. Couvre 100% des champs CERFA 15692."""
    manquants: list[str] = []
    analyse  = dossier.get("analyse") or {}
    ds       = analyse.get("donnees_structurees") or {}
    is_enfant = ds.get("is_enfant", True)
    sujet    = "de l'enfant" if is_enfant else "de la personne"

    champs_db = [
        ("nom_enfant",        "nom de famille " + sujet),
        ("prenom_enfant",     "prénom " + sujet),
        ("ddn_enfant",        "date de naissance " + sujet + " (JJ/MM/AAAA)"),
        ("adresse_enfant",    "adresse du domicile (numéro et rue)"),
        ("cp_enfant",         "code postal du domicile"),
        ("commune_enfant",    "commune / ville du domicile"),
        ("telephone_famille", "numéro de téléphone"),
        ("departement_code",  "code du département MDPH (ex : 75, 69, 13…)"),
    ]
    for champ, label in champs_db:
        if not str(dossier.get(champ) or "").strip():
            manquants.append(label)

    genre = str(ds.get("genre") or "").lower().strip()
    if genre not in ("homme", "masculin", "m", "male", "femme", "féminin", "f", "female"):
        manquants.append("genre " + sujet + " (homme ou femme)")

    if not str(ds.get("situation_familiale") or "").strip():
        manquants.append("situation familiale (célibataire, marié(e), pacsé(e), etc.)")

    droits = analyse.get("droits_identifies") or []
    if not droits:
        manquants.append("type(s) de demande(s) MDPH (ex : AAH, PCH, RQTH, AEEH, orientation…)")

    syntheses = analyse.get("synthese_agents") or {}
    geva_pro  = str(syntheses.get("geva_pro") or "").strip()
    elements  = analyse.get("elements_probants") or []
    if not geva_pro and not elements:
        manquants.append("description des difficultés et de la situation (page 8 du CERFA)")

    return len(manquants) == 0, manquants


def _verifier_donnees_personnelles(dossier: dict) -> list[str]:
    """WhatsApp questions for missing mandatory fields."""
    analyse  = dossier.get("analyse") or {}
    ds       = analyse.get("donnees_structurees") or {}
    is_enfant = ds.get("is_enfant", True)
    sujet    = "de l'enfant" if is_enfant else "de la personne"

    questions = []

    if not str(dossier.get("nom_enfant") or "").strip():
        questions.append(f"Quel est le nom de famille {sujet} ?")
    if not str(dossier.get("prenom_enfant") or "").strip():
        questions.append(f"Quel est le prénom {sujet} ?")
    if not str(dossier.get("ddn_enfant") or "").strip():
        questions.append(f"Quelle est la date de naissance {sujet} ? (JJ/MM/AAAA)")
    if not str(dossier.get("adresse_enfant") or "").strip():
        questions.append("Quelle est l'adresse du domicile ? (numéro et rue)")
    if not str(dossier.get("cp_enfant") or "").strip():
        questions.append("Quel est le code postal du domicile ?")
    if not str(dossier.get("commune_enfant") or "").strip():
        questions.append("Dans quelle commune / ville la personne habite-t-elle ?")
    if not str(dossier.get("telephone_famille") or "").strip():
        questions.append("Quel est le numéro de téléphone de contact ?")
    if not str(dossier.get("departement_code") or "").strip():
        questions.append(
            "Dans quel département déposez-vous le dossier MDPH ? "
            "(indiquez le numéro, ex : 75 pour Paris, 69 pour le Rhône)"
        )

    genre = str(ds.get("genre") or "").lower().strip()
    if genre not in ("homme", "masculin", "m", "male", "femme", "féminin", "f", "female"):
        questions.append(
            f"Quel est le genre {sujet} ? (répondez simplement : homme ou femme)"
        )

    if not str(ds.get("situation_familiale") or "").strip():
        questions.append(
            "Quelle est la situation familiale de la personne ? "
            "(célibataire, marié(e), pacsé(e), en concubinage, divorcé(e), veuf/veuve)"
        )

    droits = analyse.get("droits_identifies") or []
    if not droits:
        questions.append(
            "Quelles aides ou reconnaissances souhaitez-vous demander à la MDPH ? "
            "(ex : AAH, PCH, RQTH, AEEH, carte mobilité inclusion, orientation IME/ESAT…)"
        )

    return questions


# --------------------------------------------------------------------------- #
# Initialisation de la base de données au démarrage                           #
# --------------------------------------------------------------------------- #
@app.on_event("startup")
async def startup_event():
    database.init_db()
    # Initialisation des extensions agents V2 (relances, scores, logs)
    try:
        from database_extensions import init_extensions
        init_extensions()
    except Exception as _e:
        logger.warning(f"database_extensions non initialisé : {_e}")

    # ── Protection anti-spam au démarrage ─────────────────────────────────────
    # Les dossiers dont derniere_relance_at est NULL sont éligibles au 1er cycle
    # du scheduler dès le démarrage. Si l'app a redémarré souvent (crash-loop,
    # redéploiement), cela peut envoyer des dizaines de messages en quelques minutes.
    # On initialise derniere_relance_at à "maintenant" pour les dossiers qui n'en
    # ont pas encore, afin que le prochain cycle (dans 1h) ré-évalue correctement.
    try:
        import sqlite3 as _sqlite3
        _conn = _sqlite3.connect("mdph_dossiers.db", check_same_thread=False)
        _now  = datetime.now(timezone.utc).isoformat()
        _conn.execute("""
            UPDATE dossiers
            SET derniere_relance_at = ?
            WHERE derniere_relance_at IS NULL
              AND statut IN ('INCOMPLET', 'EN_COURS')
              AND (nb_relances IS NULL OR nb_relances = 0)
        """, (_now,))
        _conn.commit()
        _conn.close()
        logger.info("[STARTUP] derniere_relance_at initialisé pour les dossiers sans relance précédente.")
    except Exception as _e:
        logger.warning(f"[STARTUP] Initialisation derniere_relance_at échouée : {_e}")

    # Démarrage scheduler relances (Mathilde)
    if _agents_router_loaded:
        try:
            await _startup_agents()
        except Exception as _e:
            logger.warning(f"startup_agents échoué : {_e}")
    logger.info("MDPH-Backbone V2 démarré (agents multi-niveaux actifs).")
