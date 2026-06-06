"""
app/tests/qa/qa_prod_3.py
━━━━━━━━━━━━━━━━━━━━━━━━━
QA-PROD-3 — Application réelle du gate CERFA avant export

Vérifie que le gate DÉJÀ calculé (lu depuis cockpit_pro_json, AUCUN recalcul)
est réellement appliqué au point d'export :

  Partie A — Fonction pure `lire_gate_export` (lecture du gate persisté)
    PASS / WARNING / BLOCK / absent → décision attendue

  Partie B — Exécution réelle de la route (FastAPI TestClient)
    Scénario 1 (PASS)    : POST /envoyer-cerfa  → NON bloqué par le gate (≠ 403)
    Scénario 2 (WARNING) : POST /envoyer-cerfa  → NON bloqué (≠ 403)
    Scénario 3 (BLOCK)   : POST /envoyer-cerfa  → REFUSÉ (403, aucun PDF/email)
                           GET  /cerfa.pdf?export=true → REFUSÉ (403)
                           GET  /cerfa.pdf (prévisualisation) → NON bloqué (≠ 403)
    Scénario 4 (absent)  : POST /envoyer-cerfa  → NON bloqué (fail-open documenté)

  Partie C — Trace d'audit : des lignes `gate_export_check` sont écrites.

PASS = A (4/4) + B (BLOCK refusé, autres autorisés) + C (audit présent).

Usage :
  python -m app.tests.qa.qa_prod_3
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

os.environ.setdefault("DATABASE_URL", "sqlite:///./mdph_dossiers.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-key-32-chars-minimum-length-aaaa")
os.environ.setdefault("WHATSAPP_API_TOKEN", "test")
os.environ.setdefault("WHATSAPP_PHONE_NUMBER_ID", "test")
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy-key-for-tests-0000000000")
sys.path.insert(0, ".")

from app.services.export_gate import lire_gate_export

DB_PATH = os.path.abspath("mdph_dossiers.db")

def _cockpit(decision):
    if decision is None:
        return "{}"
    return json.dumps({"gate_export": {"decision": decision, "message": f"[test] {decision}"}}, ensure_ascii=False)

CAS = [
    ("PASS",    "AUTORISE",                     True),
    ("WARNING", "AUTORISE_AVEC_AVERTISSEMENTS", True),
    ("BLOCK",   "BLOQUE_EXPORT",                False),
    ("ABSENT",  None,                           True),   # fail-open documenté
]


def partie_a() -> bool:
    print("\n  ── A. Fonction pure lire_gate_export (gate persisté) ──")
    ok = True
    for nom, decision, autorise_attendu in CAS:
        g = lire_gate_export(_cockpit(decision))
        passed = (g["autorise_export"] == autorise_attendu)
        ok = ok and passed
        print(f"     {'✅' if passed else '❌'} {nom:8} → statut={g['statut']:8} autorise_export={g['autorise_export']} (attendu {autorise_attendu})")
    return ok


def _insert_dossiers():
    con = sqlite3.connect(DB_PATH)
    cols = con.execute("PRAGMA table_info(dossiers)").fetchall()  # cid,name,type,notnull,dflt,pk
    requis = [c[1] for c in cols if c[3] == 1 and c[4] is None and c[5] == 0]
    ids = {}
    for nom, decision, _ in CAS:
        did = f"QAP3_{nom}"
        ids[nom] = did
        con.execute("DELETE FROM dossiers WHERE id = ?", (did,))
        valeurs = {"id": did, "cockpit_pro_json": _cockpit(decision), "synthese_json": "{}"}
        for col in requis:
            valeurs.setdefault(col, "")
        # Colonnes UNIQUE → valeur distincte par dossier de test
        if "reference" in valeurs or "reference" in [c for c in requis]:
            valeurs["reference"] = did
        champs = ", ".join(valeurs.keys())
        placeholders = ", ".join("?" for _ in valeurs)
        con.execute(f"INSERT INTO dossiers ({champs}) VALUES ({placeholders})", tuple(valeurs.values()))
    con.commit()
    con.close()
    return ids


def _cleanup(ids):
    con = sqlite3.connect(DB_PATH)
    for did in ids.values():
        con.execute("DELETE FROM dossiers WHERE id = ?", (did,))
    con.commit()
    con.close()


def partie_b_c() -> tuple[bool, bool]:
    from fastapi.testclient import TestClient
    from app.main import app
    import app.main as m

    # Auth simulée — n'altère aucune logique métier
    app.dependency_overrides[m._get_current_user] = lambda: {"sub": "qa_prod_3"}
    client = TestClient(app)
    ids = _insert_dossiers()

    print("\n  ── B. Exécution réelle de la route (TestClient) ──")
    okb = True
    resultats = {}
    try:
        for nom, decision, autorise in CAS:
            did = ids[nom]
            r = client.post(f"/api/v1/dossiers/{did}/envoyer-cerfa")
            bloque = (r.status_code == 403)
            attendu_bloque = (nom == "BLOCK")
            passed = (bloque == attendu_bloque)
            okb = okb and passed
            resultats[nom] = r.status_code
            etat = "REFUSÉ (403)" if bloque else f"non bloqué ({r.status_code})"
            print(f"     {'✅' if passed else '❌'} {nom:8} POST /envoyer-cerfa → {etat}")

        # Export définitif via GET ?export=true sur BLOCK → 403
        rb = client.get(f"/api/v1/dossiers/{ids['BLOCK']}/cerfa.pdf?export=true")
        p1 = (rb.status_code == 403)
        okb = okb and p1
        print(f"     {'✅' if p1 else '❌'} BLOCK    GET /cerfa.pdf?export=true → {'REFUSÉ (403)' if p1 else rb.status_code}")

        # Prévisualisation (sans export) sur BLOCK → JAMAIS bloquée (≠ 403)
        rp = client.get(f"/api/v1/dossiers/{ids['BLOCK']}/cerfa.pdf")
        p2 = (rp.status_code != 403)
        okb = okb and p2
        print(f"     {'✅' if p2 else '❌'} BLOCK    GET /cerfa.pdf (prévisualisation) → {'non bloquée' if p2 else 'BLOQUÉE (403) ✗'} ({rp.status_code})")

        # Partie C — audit
        print("\n  ── C. Trace d'audit (cerfa_audit_log) ──")
        con = sqlite3.connect(DB_PATH)
        n_audit = con.execute(
            "SELECT COUNT(*) FROM cerfa_audit_log WHERE event_type='gate_export_check' AND dossier_id LIKE 'QAP3_%'"
        ).fetchone()[0]
        con.close()
        okc = n_audit >= len(CAS)
        print(f"     {'✅' if okc else '❌'} {n_audit} entrées 'gate_export_check' journalisées")
    finally:
        app.dependency_overrides.clear()
        _cleanup(ids)

    return okb, okc


def main():
    sep = "═" * 64
    print(sep); print("  QA-PROD-3 — Application réelle du gate CERFA"); print(sep)
    a = partie_a()
    try:
        b, c = partie_b_c()
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"\n  ⚠️ Partie B/C non exécutée : {e}")
        b, c = False, False

    print(f"\n{sep}")
    ok = a and b and c
    print(f"  DÉCISION QA-PROD-3 : {'✅ PASS' if ok else '❌ FAIL'}  (A={a}, B={b}, C={c})")
    print(sep)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
