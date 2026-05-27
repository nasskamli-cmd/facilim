"""
api_agents.py — Router FastAPI pour les nouveaux endpoints agents Facilim V2.

À inclure dans main.py avec :
    from api_agents import router as agents_router, startup_agents
    app.include_router(agents_router)
    app.add_event_handler("startup", startup_agents)

Nouveaux endpoints :
  GET  /api/v1/agents/status                → statut de tous les agents
  POST /api/v1/dossiers/{id}/force-relance  → Mathilde relance immédiate
  GET  /api/v1/dossiers/{id}/relances       → historique des relances
  GET  /api/v1/dossiers/{id}/score          → score Maya + suggestions RAG
  POST /api/v1/dossiers/{id}/score/recalcul → recalcul du score
  PATCH /api/v1/dossiers/{id}/urgence       → mettre à jour urgence/langue
  GET  /api/v1/agents/logs                  → logs récents des agents
"""

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Cookie, HTTPException, Body
from fastapi.responses import JSONResponse

import database
import database_extensions as db_ext
from config import get_settings

logger   = logging.getLogger("facilim.api_agents")
settings = get_settings()

router = APIRouter(prefix="/api/v1", tags=["Agents V2"])


# ── Auth helper ───────────────────────────────────────────────────────────────

def _require_auth(session_token: str | None):
    """Lève 401 si la session est invalide."""
    import auth as _auth_module
    if not session_token or not _auth_module.is_valid_session(session_token):
        raise HTTPException(status_code=401, detail="Non authentifié.")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect("mdph_dossiers.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# ── Startup ────────────────────────────────────────────────────────────────────

async def startup_agents():
    """
    Initialise les extensions DB et lance le scheduler de relances.
    Appeler via app.add_event_handler("startup", startup_agents).
    """
    db_ext.init_extensions()
    logger.info("[API_AGENTS] Extensions DB initialisées.")

    # Scheduler de relances en background
    try:
        from relance_scheduler import start_scheduler
        start_scheduler()
    except Exception as e:
        logger.error(f"[API_AGENTS] Impossible de démarrer le scheduler : {e}")


# ── GET /api/v1/agents/status ─────────────────────────────────────────────────

@router.get("/agents/status", summary="Statut de tous les agents Facilim")
async def agents_status(session_token: str | None = Cookie(default=None)):
    _require_auth(session_token)
    return {
        "agents": [
            {"nom": "Léa",      "niveau": "N-1", "role": "Validation entrée dossier",       "actif": True},
            {"nom": "Thomas",   "niveau": "N-1", "role": "Dispatch & priorisation",          "actif": True},
            {"nom": "Emma",     "niveau": "N0",  "role": "Collecte Enfance",                 "actif": True},
            {"nom": "Mathilde", "niveau": "N0",  "role": "Relances automatiques famille",    "actif": True},
            {"nom": "Ibrahim",  "niveau": "N0",  "role": "Traduction & détection de langue", "actif": True},
            {"nom": "Camille",  "niveau": "N1",  "role": "Instruction, OCR & normalisation", "actif": True},
            {"nom": "Lucas",    "niveau": "N1",  "role": "Correction documents illisibles",  "actif": True},
            {"nom": "Inès",     "niveau": "N2",  "role": "Anonymisation & chiffrement AES",  "actif": True},
            {"nom": "Maya",     "niveau": "N2",  "role": "Scoring prédictif RAG",            "actif": True},
            {"nom": "Hugo",     "niveau": "N3",  "role": "Directeur — supervision",          "actif": True},
            {"nom": "Elsa",     "niveau": "N4",  "role": "Juriste conformité MDPH",          "actif": True},
            {"nom": "Raphaël",  "niveau": "N4",  "role": "Stratégique & tendances",          "actif": True},
            {"nom": "Mehdi",    "niveau": "N4",  "role": "Cybersécurité & logs SIEM",        "actif": True},
        ],
        "scheduler_relances": "actif",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── POST /api/v1/dossiers/{id}/force-relance ──────────────────────────────────

@router.post(
    "/dossiers/{dossier_id}/force-relance",
    summary="Forcer une relance immédiate par Mathilde",
)
async def force_relance(
    dossier_id: str,
    session_token: str | None = Cookie(default=None),
):
    _require_auth(session_token)
    dossier = database.get_dossier_by_id(dossier_id)
    if not dossier:
        raise HTTPException(status_code=404, detail="Dossier introuvable.")
    if dossier.get("statut") in ("COMPLET", "ARCHIVE"):
        raise HTTPException(status_code=400, detail="Ce dossier est terminé, pas de relance nécessaire.")

    from agents.mathilde_agent import MathildeAgent
    conn  = _get_conn()
    agent = MathildeAgent(db_conn=conn)
    dossier = agent.run(dossier, force=True, db_conn=conn)
    conn.close()

    # Sauvegarder le statut mis à jour
    database.save_dossier(dossier)

    return {
        "status":        "ok",
        "nb_relances":   dossier.get("nb_relances", 0),
        "statut_relance": dossier.get("statut_relance", ""),
        "message":       f"Relance #{dossier.get('nb_relances')} envoyée par Mathilde.",
    }


# ── GET /api/v1/dossiers/{id}/relances ────────────────────────────────────────

@router.get(
    "/dossiers/{dossier_id}/relances",
    summary="Historique des relances d'un dossier",
)
async def get_relances(
    dossier_id: str,
    session_token: str | None = Cookie(default=None),
):
    _require_auth(session_token)
    if not database.get_dossier_by_id(dossier_id):
        raise HTTPException(status_code=404, detail="Dossier introuvable.")

    relances = db_ext.get_relances_par_dossier(dossier_id)
    return {"dossier_id": dossier_id, "relances": relances, "total": len(relances)}


# ── GET /api/v1/dossiers/{id}/score ───────────────────────────────────────────

@router.get(
    "/dossiers/{dossier_id}/score",
    summary="Score Maya actuel + suggestions RAG",
)
async def get_score(
    dossier_id: str,
    session_token: str | None = Cookie(default=None),
):
    _require_auth(session_token)
    dossier = database.get_dossier_by_id(dossier_id)
    if not dossier:
        raise HTTPException(status_code=404, detail="Dossier introuvable.")

    analyse = dossier.get("analyse", {})
    return {
        "dossier_id":        dossier_id,
        "score_actuel":      dossier.get("score_actuel") or analyse.get("score_global", 0),
        "score_potentiel":   dossier.get("score_potentiel"),
        "suggestion":        dossier.get("score_suggestion", ""),
        "justification":     dossier.get("score_justification", ""),
        "taux_incapacite":   dossier.get("taux_incapacite", ""),
        "taux_justification":dossier.get("taux_justification", ""),
        "rag_sources":       dossier.get("rag_sources", []),
        "droits_identifies": analyse.get("droits_identifies", []),
    }


# ── POST /api/v1/dossiers/{id}/score/recalcul ────────────────────────────────

@router.post(
    "/dossiers/{dossier_id}/score/recalcul",
    summary="Recalcul du score par Maya",
)
async def recalcul_score(
    dossier_id: str,
    session_token: str | None = Cookie(default=None),
):
    _require_auth(session_token)
    dossier = database.get_dossier_by_id(dossier_id)
    if not dossier:
        raise HTTPException(status_code=404, detail="Dossier introuvable.")

    from agents.maya_agent import MayaAgent
    agent   = MayaAgent()
    dossier = agent.run(dossier)

    # Sauvegarder
    database.save_dossier(dossier)
    db_ext.save_score(
        dossier_id,
        dossier.get("score_actuel", 0),
        dossier.get("score_potentiel", 0),
        dossier.get("score_suggestion", ""),
        dossier.get("score_justification", ""),
        dossier.get("rag_sources", []),
    )

    return {
        "status":          "recalcule",
        "score_actuel":    dossier.get("score_actuel"),
        "score_potentiel": dossier.get("score_potentiel"),
        "suggestion":      dossier.get("score_suggestion"),
        "taux_incapacite": dossier.get("taux_incapacite"),
    }


# ── PATCH /api/v1/dossiers/{id}/urgence ──────────────────────────────────────

@router.patch(
    "/dossiers/{dossier_id}/meta",
    summary="Mettre à jour urgence, langue préférée, agent actuel",
)
async def patch_dossier_meta(
    dossier_id: str,
    body: dict = Body(embed=False),
    session_token: str | None = Cookie(default=None),
):
    _require_auth(session_token)
    dossier = database.get_dossier_by_id(dossier_id)
    if not dossier:
        raise HTTPException(status_code=404, detail="Dossier introuvable.")

    allowed_fields = {"urgence", "langue_preferee", "agent_actuel"}
    updates = {k: v for k, v in body.items() if k in allowed_fields}

    if "urgence" in updates and updates["urgence"] not in ("normal", "urgent", "critique"):
        raise HTTPException(status_code=422, detail="urgence doit être 'normal', 'urgent' ou 'critique'.")

    db_ext.save_dossier_agent_fields(dossier_id, updates)
    dossier.update(updates)
    database.save_dossier(dossier)

    return {"status": "ok", "mis_a_jour": updates}


# ── GET /api/v1/agents/logs ───────────────────────────────────────────────────

@router.get(
    "/agents/logs",
    summary="Derniers logs des agents (Mehdi SIEM)",
)
async def get_agents_logs(
    agent: str | None = None,
    niveau: str | None = None,
    limit: int = 50,
    session_token: str | None = Cookie(default=None),
):
    _require_auth(session_token)
    conn = _get_conn()
    try:
        query  = "SELECT * FROM logs_agents WHERE 1=1"
        params: list[Any] = []
        if agent:
            query += " AND agent_nom=?"
            params.append(agent)
        if niveau:
            query += " AND niveau=?"
            params.append(niveau.upper())
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return {"logs": [dict(r) for r in rows], "total": len(rows)}
    except Exception:
        return {"logs": [], "total": 0}
    finally:
        conn.close()


# ── GET /api/v1/dossiers (extension) ─────────────────────────────────────────
# Override du endpoint existant pour inclure les champs agents V2

@router.get(
    "/dossiers",
    summary="Liste des dossiers (enrichie agents V2)",
)
async def list_dossiers_v2(session_token: str | None = Cookie(default=None)):
    _require_auth(session_token)
    dossiers_raw = database.list_dossiers()

    enrichis = []
    for d in dossiers_raw:
        analyse = d.get("analyse", {})
        enrichis.append({
            **d,
            "score_actuel":      d.get("score_actuel") or analyse.get("score_global", 0),
            "score_potentiel":   d.get("score_potentiel"),
            "score_suggestion":  d.get("score_suggestion", ""),
            "taux_incapacite":   d.get("taux_incapacite", ""),
            "nb_relances":       d.get("nb_relances", 0),
            "statut_relance":    d.get("statut_relance", ""),
            "derniere_relance_at": d.get("derniere_relance_at"),
            "urgence":           d.get("urgence", "normal"),
            "langue_preferee":   d.get("langue_preferee", "fr"),
            "agent_actuel":      d.get("agent_actuel", ""),
            "type_dossier":      d.get("type_dossier", ""),
            "cellule_assignee":  d.get("cellule_assignee", ""),
        })

    total = len(enrichis)
    urgents  = sum(1 for d in enrichis if d.get("urgence") in ("urgent", "critique"))
    actifs   = sum(1 for d in enrichis if d.get("statut") in ("EN_COURS", "INCOMPLET"))
    bloques  = sum(1 for d in enrichis if d.get("statut") == "BLOQUE")

    return {
        "dossiers":     enrichis,
        "total":        total,
        "stats": {
            "actifs":   actifs,
            "urgents":  urgents,
            "bloques":  bloques,
            "complets": sum(1 for d in enrichis if d.get("statut") == "COMPLET"),
        },
    }
