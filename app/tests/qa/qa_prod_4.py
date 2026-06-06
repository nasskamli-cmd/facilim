"""
app/tests/qa/qa_prod_4.py
━━━━━━━━━━━━━━━━━━━━━━━━━
QA-PROD-4 — Audit trail persistant et consultable

Vérifie que les événements critiques sont PERSISTÉS (tables existantes
audit_events / cerfa_audit_log) et RELISIBLES via GET /dossiers/{id}/historique.
Aucun moteur appelé, aucun recalcul.

  Cas 1 — Calcul cockpit   : événement écrit + relu
  Cas 2 — Gate PASS        : événement écrit (export autorisé)
  Cas 3 — Gate BLOCK       : événement écrit + raison enregistrée
  Cas 4 — Export autorisé  : événement écrit
  Cas 5 — Export refusé    : événement écrit
  Cas 6 — Lecture historique : ordre chronologique + cohérence

PASS = 6/6 cas vérifiés par écriture réelle + relecture réelle.

Usage :
  python -m app.tests.qa.qa_prod_4
"""

from __future__ import annotations

import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import json
import os
import sqlite3
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///./mdph_dossiers.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-key-32-chars-minimum-length-aaaa")
os.environ.setdefault("WHATSAPP_API_TOKEN", "test")
os.environ.setdefault("WHATSAPP_PHONE_NUMBER_ID", "test")
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy-key-for-tests-0000000000")
sys.path.insert(0, ".")

DB_PATH = os.path.abspath("mdph_dossiers.db")


def _cockpit(decision: str) -> str:
    return json.dumps({"gate_export": {"decision": decision, "message": f"[test] {decision}"}}, ensure_ascii=False)


def _insert_dossier(con, did, decision):
    cols = con.execute("PRAGMA table_info(dossiers)").fetchall()
    requis = [c[1] for c in cols if c[3] == 1 and c[4] is None and c[5] == 0]
    con.execute("DELETE FROM dossiers WHERE id = ?", (did,))
    valeurs = {"id": did, "cockpit_pro_json": _cockpit(decision), "synthese_json": "{}", "reference": did}
    for col in requis:
        valeurs.setdefault(col, "")
    valeurs["reference"] = did
    champs = ", ".join(valeurs.keys())
    ph = ", ".join("?" for _ in valeurs)
    con.execute(f"INSERT INTO dossiers ({champs}) VALUES ({ph})", tuple(valeurs.values()))


def main():
    from fastapi.testclient import TestClient
    from app.main import app
    import app.main as m
    from app.audit.event_logger import log_event

    sep = "═" * 64
    print(sep); print("  QA-PROD-4 — Audit trail persistant et consultable"); print(sep)

    app.dependency_overrides[m._get_current_user] = lambda: {"sub": "qa_prod_4", "role": "SUPER_ADMIN"}
    client = TestClient(app)

    id_pass, id_block = "QAP4_PASS", "QAP4_BLOCK"
    con = sqlite3.connect(DB_PATH)
    _insert_dossier(con, id_pass, "AUTORISE")
    _insert_dossier(con, id_block, "BLOQUE_EXPORT")
    con.commit()

    resultats = {}
    try:
        # Cas 1 — Calcul cockpit : écrit via le MÊME mécanisme que orchestration_engine (event_logger → audit_events)
        log_event("COCKPIT_CALCULE", dossier_id=id_pass, canal="pipeline",
                  payload={"score_completude": 54, "score_solidite": 55, "decision": "GO_AVEC_RISQUES", "gate": "AUTORISE"},
                  db_conn=con)
        con.commit()

        # Cas 2 + 4 — Gate PASS / export autorisé : POST réel (gate laisse passer → 400 email manquant)
        r_pass = client.post(f"/api/v1/dossiers/{id_pass}/envoyer-cerfa")
        # Cas 3 + 5 — Gate BLOCK / export refusé : POST réel → 403 + raison journalisée
        r_block = client.post(f"/api/v1/dossiers/{id_block}/envoyer-cerfa")

        # Lecture réelle de l'historique
        h_pass = client.get(f"/api/v1/dossiers/{id_pass}/historique").json()
        h_block = client.get(f"/api/v1/dossiers/{id_block}/historique").json()
        ev_pass = h_pass.get("evenements", [])
        ev_block = h_block.get("evenements", [])

        def _find(evs, typ, pred=lambda d: True):
            return [e for e in evs if e["type"] == typ and pred(e.get("details", {}))]

        # Vérifications
        c1 = bool(_find(ev_pass, "COCKPIT_CALCULE"))
        c2 = bool(_find(ev_pass, "gate_export_check", lambda d: d.get("export_autorise") is True))
        c3 = bool(_find(ev_block, "gate_export_check", lambda d: d.get("export_autorise") is False and d.get("raison")))
        c4 = (r_pass.status_code != 403) and c2
        c5 = (r_block.status_code == 403) and c3
        dates = [e["date"] for e in ev_pass if e.get("date")]
        c6 = (len(ev_pass) >= 2) and (dates == sorted(dates))

        resultats = {
            "Cas 1 — Calcul cockpit (écrit + relu)":      c1,
            "Cas 2 — Gate PASS (événement écrit)":        c2,
            "Cas 3 — Gate BLOCK (écrit + raison)":        c3,
            "Cas 4 — Export autorisé (événement écrit)":  c4,
            "Cas 5 — Export refusé (événement écrit)":    c5,
            "Cas 6 — Historique chronologique cohérent":  c6,
        }

        print(f"\n  POST PASS → {r_pass.status_code} | POST BLOCK → {r_block.status_code}")
        print(f"  Historique PASS : {len(ev_pass)} évén. | Historique BLOCK : {len(ev_block)} évén.\n")
        for label, ok in resultats.items():
            print(f"     {'✅' if ok else '❌'} {label}")

        # Exemple d'événements relus (preuve de lecture)
        print("\n  ── Exemple — historique du dossier PASS (chronologique) ──")
        for e in ev_pass:
            print(f"     [{e['date'][:19]}] {e['type']:22} src={e['source']:16} details={json.dumps(e['details'], ensure_ascii=False)[:70]}")

        # Vérif statique : orchestration_engine journalise bien le cockpit
        src = Path("app/engines/orchestration_engine.py").read_text(encoding="utf-8")
        c_static = 'COCKPIT_CALCULE' in src and 'log_event' in src
        print(f"\n     {'✅' if c_static else '❌'} orchestration_engine journalise COCKPIT_CALCULE (vérif statique)")
        resultats["Vérif statique orchestration"] = c_static

    finally:
        app.dependency_overrides.clear()
        con.execute("DELETE FROM dossiers WHERE id IN (?, ?)", (id_pass, id_block))
        con.commit()
        con.close()

    ok = all(resultats.values())
    print(f"\n{sep}")
    print(f"  DÉCISION QA-PROD-4 : {'✅ PASS' if ok else '❌ FAIL'} ({sum(resultats.values())}/{len(resultats)})")
    print(sep)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
