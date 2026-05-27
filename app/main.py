"""
app/main.py — Point d'entrée FastAPI Facilim v2.

Architecture event-driven :
  - Webhook WhatsApp → OrchestrationEngine
  - Dashboard ESSMS  → API JSON sécurisée JWT
  - Portail usager   → (à venir) HDS

Tous les événements sont :
  - immédiatement persistés
  - journalisés dans l'audit trail
  - traçables end-to-end

Ce fichier ne contient QUE le câblage HTTP.
La logique métier est dans les engines/.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import (
    Depends, FastAPI, HTTPException, Request, Response,
    UploadFile, File, Form,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config.settings import get_settings
from app.database import connection as db_conn_module
from app.security import encryption, token_manager, access_control
from app.audit import event_logger
from app.services.whatsapp_service import WhatsAppService, parse_webhook_payload
from app.services.notification_service import NotificationService
from app.engines.orchestration_engine import OrchestrationEngine

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("facilim.app")

# ── Initialisation ────────────────────────────────────────────────────────────
encryption.initialize(settings.encryption_key)
db_conn_module.configure(settings.database_url)
db_conn_module.initialize_schema()

# ── Client LLM ───────────────────────────────────────────────────────────────
from openai import OpenAI
_llm_client = OpenAI(api_key=settings.openai_api_key)

# ── Services ─────────────────────────────────────────────────────────────────
_wa_service = WhatsAppService(
    api_token=settings.whatsapp_api_token,
    phone_number_id=settings.whatsapp_phone_number_id,
    api_version=settings.whatsapp_api_version,
)
_notif_service = NotificationService(whatsapp_service=_wa_service)

# ── FastAPI ───────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Facilim API v2",
    description=(
        "Infrastructure nationale de sécurisation et d'orchestration "
        "des parcours MDPH en France."
    ),
    version="2.0.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://facilim.fr"] if settings.is_production else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH"],
    allow_headers=["*"],
)

# Fichiers statiques (dashboard, login)
import os
_static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

_dashboards_dir = os.path.join(os.path.dirname(__file__), "dashboards")
if os.path.isdir(_dashboards_dir):
    app.mount("/dashboards", StaticFiles(directory=_dashboards_dir), name="dashboards")


# ── Dépendances ───────────────────────────────────────────────────────────────

def _get_db():
    """Ouvre une connexion DB par requête (context manager non utilisable en Depends)."""
    conn = db_conn_module._get_raw_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _get_current_user(request: Request) -> dict[str, Any]:
    """Vérifie le JWT du Dashboard. Lève 401 si invalide."""
    token = request.cookies.get("facilim_token") or (
        request.headers.get("Authorization", "").removeprefix("Bearer ").strip() or None
    )
    if not token:
        raise HTTPException(status_code=401, detail="Non authentifié")
    payload = token_manager.verify_dashboard_token(token, settings.jwt_secret_key)
    if not payload:
        raise HTTPException(status_code=401, detail="Token invalide ou expiré")
    return payload


def _get_orchestrator(db=Depends(_get_db)) -> OrchestrationEngine:
    return OrchestrationEngine(
        db_conn=db,
        whatsapp_service=_wa_service,
        notification_service=_notif_service,
        openai_client=_llm_client,
        settings=settings,
    )


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0", "env": settings.app_env}


# ── Webhook WhatsApp ──────────────────────────────────────────────────────────

@app.get("/api/v1/webhook/whatsapp")
async def whatsapp_verify(request: Request):
    """Vérification du webhook WhatsApp (challenge Meta)."""
    params = request.query_params
    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == settings.whatsapp_verify_token
    ):
        return Response(content=params.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(status_code=403, detail="Token de vérification invalide")


@app.post("/api/v1/webhook/whatsapp")
async def whatsapp_webhook(
    request: Request,
    db=Depends(_get_db),
):
    """Réception des messages WhatsApp entrants."""
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"status": "ok"})  # WhatsApp attend 200 même en cas d'erreur

    orchestrator = OrchestrationEngine(
        db_conn=db,
        whatsapp_service=_wa_service,
        notification_service=_notif_service,
        openai_client=_llm_client,
        settings=settings,
    )

    messages = parse_webhook_payload(payload)
    for msg in messages:
        if msg.get("type") in ("text", "image", "document", "audio"):
            _wa_service.mark_as_read(msg["message_id"])
            orchestrator.handle_whatsapp_message(
                from_number=msg["from"],
                message_text=msg.get("text", ""),
                message_id=msg["message_id"],
                media_id=msg.get("media_id"),
                mime_type=msg.get("mime_type"),
            )

    return JSONResponse({"status": "ok"})


# ── Authentification Dashboard ────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/api/v1/auth/login")
def login(body: LoginRequest, response: Response, db=Depends(_get_db)):
    """Authentification Dashboard ESSMS."""
    # Vérification des credentials (hash bcrypt en production)
    valid_pairs = [
        (settings.auth_email, settings.auth_password),
        (settings.auth_email_2, settings.auth_password_2),
    ]
    matched = next(
        ((e, p) for e, p in valid_pairs if e and e == body.email and p == body.password),
        None,
    )
    if not matched:
        raise HTTPException(status_code=401, detail="Identifiants incorrects")

    # Récupération ou création de l'utilisateur
    row = db.execute(
        "SELECT * FROM utilisateurs WHERE email = ? AND actif = 1 LIMIT 1",
        (body.email,),
    ).fetchone()

    if row:
        user = dict(row)
    else:
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            """
            INSERT OR IGNORE INTO utilisateurs
                (id, email, password_hash, role, actif, created_at, updated_at)
            VALUES (?, ?, '[LEGACY]', 'EDUCATEUR', 1, ?, ?)
            """,
            (user_id, body.email, now, now),
        )
        user = {"id": user_id, "email": body.email, "role": "EDUCATEUR", "organisation_id": None}

    # Mise à jour dernière connexion
    db.execute(
        "UPDATE utilisateurs SET derniere_connexion = ? WHERE email = ?",
        (datetime.now(timezone.utc).isoformat(), body.email),
    )

    token, expire_at = token_manager.create_dashboard_token(
        utilisateur_id=user["id"],
        email=user["email"],
        role=user.get("role", "EDUCATEUR"),
        organisation_id=user.get("organisation_id"),
        secret_key=settings.jwt_secret_key,
        expire_minutes=settings.jwt_expire_minutes,
    )

    event_logger.log_event(
        "CONNEXION_DASHBOARD",
        utilisateur_id=user["id"],
        canal="dashboard",
        db_conn=db,
    )

    response.set_cookie(
        key="facilim_token",
        value=token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=settings.jwt_expire_minutes * 60,
    )
    return {"success": True, "role": user.get("role", "EDUCATEUR"), "email": user["email"]}


@app.post("/api/v1/auth/logout")
def logout(response: Response):
    response.delete_cookie("facilim_token")
    return {"success": True}


@app.get("/logout")
def logout_redirect(response: Response):
    response.delete_cookie("facilim_token")
    return RedirectResponse("/login", status_code=302)


# ── Dashboard — Dossiers ──────────────────────────────────────────────────────

@app.get("/api/v1/dashboard/dossiers")
def list_dossiers(
    user=Depends(_get_current_user),
    db=Depends(_get_db),
):
    """Liste des dossiers visibles par l'utilisateur connecté."""
    event_logger.log_event("ACCES_DASHBOARD", utilisateur_id=user.get("sub"), canal="dashboard", db_conn=db)

    if user.get("role") == "SUPER_ADMIN":
        rows = db.execute(
            "SELECT * FROM dossiers WHERE deleted_at IS NULL ORDER BY updated_at DESC LIMIT 200"
        ).fetchall()
    else:
        org_id = user.get("org_id")
        rows = db.execute(
            "SELECT * FROM dossiers WHERE organisation_id = ? AND deleted_at IS NULL "
            "ORDER BY updated_at DESC LIMIT 200",
            (org_id,),
        ).fetchall() if org_id else db.execute(
            "SELECT * FROM dossiers WHERE deleted_at IS NULL ORDER BY updated_at DESC LIMIT 200"
        ).fetchall()

    dossiers = []
    for row in rows:
        d = dict(row)
        d["droits_identifies"] = json.loads(d.get("droits_identifies_json", "[]") or "[]")
        d.pop("droits_identifies_json", None)
        dossiers.append(d)

    return {"dossiers": dossiers, "total": len(dossiers)}


@app.get("/api/v1/dashboard/dossiers/{dossier_id}")
def get_dossier(
    dossier_id: str,
    user=Depends(_get_current_user),
    db=Depends(_get_db),
):
    """Détail d'un dossier avec consentement et scoring."""
    row = db.execute("SELECT * FROM dossiers WHERE id = ?", (dossier_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Dossier non trouvé")

    d = dict(row)
    access_control.require_permission(user.get("role", "LECTEUR"), access_control.Permission.DOSSIER_READ)

    d["droits_identifies"] = json.loads(d.get("droits_identifies_json", "[]") or "[]")
    d["synthese"] = json.loads(d.get("synthese_json", "{}") or "{}")
    d["questions"] = json.loads(d.get("questions_json", "[]") or "[]")
    d["conversation"] = json.loads(d.get("conversation_json", "[]") or "[]")

    # Consentement
    usager_row = db.execute("SELECT id FROM usagers WHERE id = ?", (d.get("usager_id", ""),)).fetchone()
    if usager_row:
        from app.services.consent_service import get_consent_summary
        d["consent"] = get_consent_summary(usager_row["id"], db)

    # Pièces
    pieces = db.execute(
        "SELECT id, type_piece, ocr_effectue, score_confiance_ocr, flag_validation_humaine, "
        "validee_par, created_at FROM pieces_justificatives WHERE dossier_id = ?",
        (dossier_id,),
    ).fetchall()
    d["pieces"] = [dict(p) for p in pieces]

    # Scoring
    scoring = db.execute(
        "SELECT * FROM analyses_scoring WHERE dossier_id = ? ORDER BY created_at DESC LIMIT 1",
        (dossier_id,),
    ).fetchone()
    if scoring:
        d["scoring"] = dict(scoring)

    event_logger.log_event(
        "ACCES_DOSSIER",
        dossier_id=dossier_id,
        utilisateur_id=user.get("sub"),
        canal="dashboard",
        db_conn=db,
    )
    return d


@app.get("/api/v1/dashboard/alertes")
def get_alertes(user=Depends(_get_current_user), db=Depends(_get_db)):
    """Alertes et flags humains pour le Dashboard."""
    flags = db.execute(
        """
        SELECT a.*, d.reference as dossier_reference
        FROM alertes a
        LEFT JOIN dossiers d ON d.id = a.dossier_id
        WHERE a.type_alerte = 'FLAG_HUMAIN' AND a.acquittee = 0
        ORDER BY a.created_at DESC LIMIT 50
        """
    ).fetchall()

    relances = db.execute(
        """
        SELECT * FROM relances
        WHERE statut = 'PLANIFIEE'
        ORDER BY planifiee_le ASC LIMIT 50
        """
    ).fetchall()

    return {
        "flags":    [dict(f) for f in flags],
        "relances": [dict(r) for r in relances],
    }


@app.post("/api/v1/dashboard/dossiers/{dossier_id}/validate-flag")
def validate_flag(
    dossier_id: str,
    request: Request,
    user=Depends(_get_current_user),
    db=Depends(_get_db),
):
    """Validation humaine d'un flag — Human-in-the-loop."""
    access_control.require_permission(user.get("role"), access_control.Permission.HUMAN_VALIDATE)
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """
        UPDATE dossiers SET
            flag_humain_requis = 0,
            raison_flag        = NULL,
            updated_at         = ?
        WHERE id = ?
        """,
        (now, dossier_id),
    )
    db.execute(
        "UPDATE alertes SET acquittee = 1, acquittee_par = ?, acquittee_le = ? WHERE dossier_id = ?",
        (user.get("sub"), now, dossier_id),
    )
    event_logger.log_event(
        "VALIDATION_HUMAINE",
        dossier_id=dossier_id,
        utilisateur_id=user.get("sub"),
        canal="dashboard",
        db_conn=db,
    )
    return {"success": True}


@app.post("/api/v1/dashboard/dossiers/{dossier_id}/relance")
def send_relance(
    dossier_id: str,
    user=Depends(_get_current_user),
    db=Depends(_get_db),
):
    """Envoie une relance manuelle pour un dossier."""
    dossier_row = db.execute("SELECT * FROM dossiers WHERE id = ?", (dossier_id,)).fetchone()
    if not dossier_row:
        raise HTTPException(status_code=404, detail="Dossier non trouvé")

    dossier = dict(dossier_row)
    usager_row = db.execute("SELECT * FROM usagers WHERE id = ?", (dossier.get("usager_id"),)).fetchone()
    if not usager_row:
        raise HTTPException(status_code=400, detail="Usager non trouvé")

    usager = dict(usager_row)
    questions = json.loads(dossier.get("questions_json", "[]") or "[]")

    _notif_service.send_relance_pieces_manquantes(
        usager=usager,
        pieces_manquantes=questions[:5] if questions else ["Informations complémentaires requises"],
        dossier_id=dossier_id,
        db_conn=db,
    )

    relance_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """
        INSERT INTO relances
            (id, dossier_id, usager_id, canal, type_relance, planifiee_le, envoyee_le, statut, created_at)
        VALUES (?, ?, ?, 'whatsapp', 'PIECES_MANQUANTES', ?, ?, 'ENVOYEE', ?)
        """,
        (relance_id, dossier_id, usager["id"], now, now, now),
    )
    event_logger.log_event(
        "RELANCE_ENVOYEE",
        dossier_id=dossier_id,
        utilisateur_id=user.get("sub"),
        canal="dashboard",
        db_conn=db,
    )
    return {"success": True}


# ── Pages HTML ────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return RedirectResponse("/dashboard")


@app.get("/dashboard")
def dashboard_page():
    dashboard_path = os.path.join(os.path.dirname(__file__), "dashboards", "dashboard.html")
    if os.path.isfile(dashboard_path):
        return FileResponse(dashboard_path)
    return HTMLResponse("<h1>Facilim v2 — Dashboard en cours de chargement</h1>")


@app.get("/login")
def login_page():
    static_login = os.path.join(os.path.dirname(__file__), "..", "static", "login.html")
    if os.path.isfile(static_login):
        return FileResponse(static_login)
    return HTMLResponse("""
    <!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8">
    <title>Facilim — Connexion</title>
    <script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-gray-50 flex items-center justify-center min-h-screen">
    <div class="bg-white p-8 rounded-xl shadow w-full max-w-sm">
      <h1 class="text-xl font-bold text-gray-900 mb-6">Facilim — Connexion</h1>
      <form id="f" class="space-y-4">
        <input id="email" type="email" placeholder="Email" required
          class="w-full border rounded-lg px-3 py-2 text-sm">
        <input id="pass" type="password" placeholder="Mot de passe" required
          class="w-full border rounded-lg px-3 py-2 text-sm">
        <button type="submit" class="w-full bg-blue-700 text-white py-2 rounded-lg text-sm font-medium">
          Se connecter
        </button>
        <p id="err" class="text-red-600 text-xs hidden">Identifiants incorrects</p>
      </form>
      <script>
        document.getElementById('f').addEventListener('submit', async e => {
          e.preventDefault();
          const res = await fetch('/api/v1/auth/login', {
            method:'POST', credentials:'include',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({email: document.getElementById('email').value,
                                  password: document.getElementById('pass').value})
          });
          if (res.ok) window.location='/dashboard';
          else document.getElementById('err').classList.remove('hidden');
        });
      </script>
    </div></body></html>
    """)


# ── RGPD ─────────────────────────────────────────────────────────────────────

@app.get("/api/v1/rgpd/export/{usager_id}")
def export_rgpd(
    usager_id: str,
    user=Depends(_get_current_user),
    db=Depends(_get_db),
):
    """Export des données d'un usager (Article 15 RGPD)."""
    access_control.require_permission(user.get("role"), access_control.Permission.RGPD_MANAGE)
    from app.services.compliance_service import ComplianceService
    svc = ComplianceService(retention_days=settings.rgpd_retention_days)
    data = svc.export_usager_data(
        usager_id=usager_id,
        db_conn=db,
        requesting_utilisateur_id=user.get("sub"),
    )
    return JSONResponse(data)


@app.delete("/api/v1/rgpd/erase/{usager_id}")
def erase_rgpd(
    usager_id: str,
    user=Depends(_get_current_user),
    db=Depends(_get_db),
):
    """Effacement des données d'un usager (Article 17 RGPD)."""
    access_control.require_permission(user.get("role"), access_control.Permission.RGPD_MANAGE)
    from app.services.compliance_service import ComplianceService
    svc = ComplianceService(retention_days=settings.rgpd_retention_days)
    ok = svc.erase_usager_data(
        usager_id=usager_id,
        db_conn=db,
        requesting_utilisateur_id=user.get("sub"),
    )
    return {"success": ok}


# ── Audit ─────────────────────────────────────────────────────────────────────

@app.get("/api/v1/audit/events")
def get_audit_events(
    dossier_id: str | None = None,
    limit: int = 100,
    user=Depends(_get_current_user),
    db=Depends(_get_db),
):
    """Lecture du journal d'audit (SUPER_ADMIN / ADMIN_ESSMS uniquement)."""
    access_control.require_permission(user.get("role"), access_control.Permission.AUDIT_READ)
    if dossier_id:
        rows = db.execute(
            "SELECT * FROM audit_events WHERE dossier_id = ? ORDER BY created_at DESC LIMIT ?",
            (dossier_id, limit),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM audit_events ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return {"events": [dict(r) for r in rows]}


# ── Compatibilité avec l'ancien main.py (route legacy) ───────────────────────
# Conservée pour ne pas casser les intégrations existantes

@app.get("/api/v1/dossiers")
def legacy_list_dossiers(user=Depends(_get_current_user), db=Depends(_get_db)):
    """Route legacy — redirection vers /api/v1/dashboard/dossiers."""
    rows = db.execute(
        "SELECT * FROM dossiers WHERE deleted_at IS NULL ORDER BY updated_at DESC LIMIT 100"
    ).fetchall()
    return {"dossiers": [dict(r) for r in rows]}
