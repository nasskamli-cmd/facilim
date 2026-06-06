"""
app/tests/qa/qa_prod_5.py
━━━━━━━━━━━━━━━━━━━━━━━━━
QA-PROD-5 — Visibilité de l'historique dans le dashboard

Vérifie, SANS recalcul ni nouvelle logique, que la timeline du dossier est
visible dans le dashboard, alimentée par GET /dossiers/{id}/historique.

  A. Câblage statique (dashboard.html)
     - panneau #panel-historique + fonctions loadHistorique / renderHistorique
     - loadHistorique appelle /historique ; renderHistorique appelé dans openDossier
     - rendu GÉNÉRIQUE (aucun type d'événement codé en dur dans renderHistorique)
     - aucun fetch / appel API dans renderHistorique (le fetch est dans loadHistorique)
     - liste vide gérée

  B. Données réelles (FastAPI TestClient)
     - GET /historique renvoie une timeline réelle (date/type/source/details)
     - ordre chronologique ; gate BLOCK porte une 'raison' ; COCKPIT_CALCULE présent
     - dossier sans événement → evenements = []

  C. Artefacts visuels
     - reports/historique_render_events.html + historique_render_empty.html
       (renderHistorique + markup EXTRAITS de dashboard.html, alimentés par le JSON réel)

PASS = A + B.

Usage : python -m app.tests.qa.qa_prod_5
"""

from __future__ import annotations

import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import json
import os
import re
import sqlite3
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///./mdph_dossiers.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-key-32-chars-minimum-length-aaaa")
os.environ.setdefault("WHATSAPP_API_TOKEN", "test")
os.environ.setdefault("WHATSAPP_PHONE_NUMBER_ID", "test")
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy-key-for-tests-0000000000")
sys.path.insert(0, ".")

from app.tests.qa.qa_prod_2 import HARNESS_CSS   # réutilise le CSS hors-ligne (pas de duplication)

DASHBOARD = Path("app/dashboards/dashboard.html")
REPORTS = Path("app/tests/qa/reports")
DB_PATH = os.path.abspath("mdph_dossiers.db")


def checks_statiques(txt: str) -> list[tuple[str, bool]]:
    m = re.search(r"function renderHistorique\(data\) \{(.*?)\n\}\n", txt, re.S)
    body = m.group(1) if m else ""
    ml = re.search(r"async function loadHistorique\([^)]*\) \{(.*?)\n\}", txt, re.S)
    load_body = ml.group(1) if ml else ""
    # Rendu générique : aucun nom de type d'événement codé en dur dans le rendu
    types_en_dur = any(t in body for t in ["COCKPIT_CALCULE", "gate_export_check", "DROITS_VALIDES"])
    return [
        ("panneau #panel-historique présent",          'id="panel-historique"' in txt),
        ("timeline #historique-timeline présente",      'id="historique-timeline"' in txt),
        ("fonction renderHistorique présente",          "function renderHistorique(data)" in txt),
        ("fonction loadHistorique présente",            "async function loadHistorique(" in txt),
        ("loadHistorique appelle /historique",          "/historique" in load_body),
        ("loadHistorique appelée dans openDossier",     "loadHistorique(id)" in txt),
        ("renderHistorique sans fetch (no recalc)",     "fetch(" not in body),
        ("rendu générique (aucun type codé en dur)",    not types_en_dur),
        ("liste vide gérée",                            "Aucun événement enregistré" in txt),
    ]


def extraire(txt: str) -> tuple[str, str]:
    m = re.search(r"(function renderHistorique\(data\) \{.*?\n\})\n", txt, re.S)
    render_fn = m.group(1) if m else ""
    ps = txt.index('<div id="panel-historique"')
    pe = txt.index("<!-- Zone pro", ps)
    chunk = txt[ps:pe].rstrip()
    chunk = chunk[:chunk.rfind("</div>")].rstrip()
    return render_fn, chunk


def generer_harness(render_fn, panel_html, data, nom, slug):
    payload = json.dumps(data, ensure_ascii=False)
    page = f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<title>Historique — {nom}</title><style>{HARNESS_CSS}</style></head><body class="p-6">
<h1 class="text-sm text-gray-400 mb-3">Harness historique — {nom} (données réelles GET /historique, aucun recalcul)</h1>
<div class="max-w-2xl">
{panel_html}
</div>
<script>
{render_fn}
const data = {payload};
renderHistorique(data);
</script></body></html>"""
    REPORTS.mkdir(parents=True, exist_ok=True)
    p = REPORTS / f"historique_render_{slug}.html"
    p.write_text(page, encoding="utf-8")
    return p


def _insert(con, did, decision):
    cols = con.execute("PRAGMA table_info(dossiers)").fetchall()
    requis = [c[1] for c in cols if c[3] == 1 and c[4] is None and c[5] == 0]
    con.execute("DELETE FROM dossiers WHERE id = ?", (did,))
    v = {"id": did, "cockpit_pro_json": json.dumps({"gate_export": {"decision": decision, "message": "Pièces justificatives manquantes"}}, ensure_ascii=False),
         "synthese_json": "{}", "reference": did}
    for c in requis:
        v.setdefault(c, "")
    v["reference"] = did
    con.execute(f"INSERT INTO dossiers ({', '.join(v)}) VALUES ({', '.join('?' for _ in v)})", tuple(v.values()))


def main():
    txt = DASHBOARD.read_text(encoding="utf-8")
    sep = "═" * 64
    print(sep); print("  QA-PROD-5 — Visibilité de l'historique (dashboard)"); print(sep)

    print("\n  ── A. Câblage statique ──")
    stat = checks_statiques(txt)
    for label, ok in stat:
        print(f"     {'✅' if ok else '❌'} {label}")
    a_ok = all(ok for _, ok in stat)

    # B — données réelles via TestClient
    print("\n  ── B. Données réelles (GET /historique) ──")
    from fastapi.testclient import TestClient
    from app.main import app
    import app.main as m
    from app.audit.event_logger import log_event

    app.dependency_overrides[m._get_current_user] = lambda: {"sub": "qa_prod_5", "role": "SUPER_ADMIN"}
    client = TestClient(app)
    con = sqlite3.connect(DB_PATH)
    _insert(con, "QAP5_BLOCK", "BLOQUE_EXPORT")
    _insert(con, "QAP5_VIDE", "AUTORISE")
    con.commit()

    b_ok = False
    data_events, data_empty = {"evenements": []}, {"evenements": []}
    try:
        log_event("COCKPIT_CALCULE", dossier_id="QAP5_BLOCK", canal="pipeline",
                  payload={"score_completude": 54, "score_solidite": 55, "decision": "GO_AVEC_RISQUES"}, db_conn=con)
        con.commit()
        client.post("/api/v1/dossiers/QAP5_BLOCK/envoyer-cerfa")   # → gate BLOCK journalisé
        data_events = client.get("/api/v1/dossiers/QAP5_BLOCK/historique").json()
        data_empty = client.get("/api/v1/dossiers/QAP5_VIDE/historique").json()

        evs = data_events.get("evenements", [])
        champs_ok = all(all(k in e for k in ("date", "type", "source", "details")) for e in evs)
        dates = [e["date"] for e in evs if e.get("date")]
        chrono = dates == sorted(dates)
        a_cockpit = any(e["type"] == "COCKPIT_CALCULE" for e in evs)
        a_block = any(e["type"] == "gate_export_check" and e["details"].get("raison") for e in evs)
        vide_ok = data_empty.get("evenements", None) == []

        for label, ok in [
            (f"{len(evs)} événements renvoyés", len(evs) >= 2),
            ("champs date/type/source/details présents", champs_ok),
            ("ordre chronologique", chrono),
            ("COCKPIT_CALCULE présent", a_cockpit),
            ("gate BLOCK avec raison", a_block),
            ("dossier sans événement → liste vide", vide_ok),
        ]:
            print(f"     {'✅' if ok else '❌'} {label}")
        b_ok = all([len(evs) >= 2, champs_ok, chrono, a_cockpit, a_block, vide_ok])
    finally:
        app.dependency_overrides.clear()
        con.execute("DELETE FROM dossiers WHERE id IN ('QAP5_BLOCK','QAP5_VIDE')")
        con.commit(); con.close()

    # C — artefacts visuels
    render_fn, panel = extraire(txt)
    p1 = generer_harness(render_fn, panel, data_events, "timeline (BLOCK + cockpit)", "events")
    p2 = generer_harness(render_fn, panel, data_empty, "historique vide", "empty")
    print(f"\n  ── C. Artefacts visuels ──\n     → {p1.name}\n     → {p2.name}")

    print(f"\n{sep}")
    ok = a_ok and b_ok
    print(f"  DÉCISION QA-PROD-5 : {'✅ PASS' if ok else '❌ FAIL'} (A={a_ok}, B={b_ok})")
    print(sep)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
