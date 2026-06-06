"""
app/tests/qa/qa_fix_test4_cerfa_v2.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-FIX-TEST4-CERFA-V2 — Le moteur V2 survit à une erreur d'audit

Vérifie la correction FIX-TEST4 sur `_generer_cerfa_pdf` :
  « Une erreur d'audit ne doit jamais détruire un PDF V2 déjà généré. »

  Cas 1 — colonne `version` absente (SELECT version lève) → PDF V2, AUCUN fallback
  Cas 2 — exception d'audit forcée (_log_cerfa_audit lève) → PDF V2, AUCUN fallback
  Cas 3 — VRAIE erreur de génération V2 → fallback V3 autorisé
  Cas 4 — TEST4 rejoué (réévaluation + bilan, sans droits) → V2 utilisé, AUCUN fallback

Exécution réelle de `app.main._generer_cerfa_pdf`, capture des logs `facilim.app`,
injection de fautes ciblée (proxy DB / mock.patch des dépendances).

Usage : python -m app.tests.qa.qa_fix_test4_cerfa_v2
"""

from __future__ import annotations

import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import json
import logging
import os
import sqlite3
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///./mdph_dossiers.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-key-32-chars-minimum-length-aaaa")
os.environ.setdefault("WHATSAPP_API_TOKEN", "test")
os.environ.setdefault("WHATSAPP_PHONE_NUMBER_ID", "test")
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy-key-for-tests-0000000000")
sys.path.insert(0, ".")

import app.main as m   # déclenche le filet de démarrage (ajoute la colonne version)

DB_PATH = os.path.abspath("mdph_dossiers.db")
DID = "QAFIX_T4"

SYNTHESE = {
    "telephone": "0642087770", "email": "karim@example.fr", "departement": "13",
    "type_dossier": "REEVALUATION", "nom_prenom": "NAIT-ALI", "date_naissance": "05/12/1969",
    "adresse_complete": "1 rue des Bateliers, 13016 MARSEILLE",
    "diagnostics": "anxiété, troubles du sommeil, douleurs", "accident_travail": "chute",
}


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _insert_dossier(c):
    cols = c.execute("PRAGMA table_info(dossiers)").fetchall()
    requis = [r[1] for r in cols if r[3] == 1 and r[4] is None and r[5] == 0]
    c.execute("DELETE FROM dossiers WHERE id = ?", (DID,))
    v = {"id": DID, "reference": DID, "synthese_json": json.dumps(SYNTHESE, ensure_ascii=False),
         "type_dossier": "REEVALUATION"}
    for col in requis:
        v.setdefault(col, "")
    v["reference"] = DID
    c.execute(f"INSERT INTO dossiers ({', '.join(v)}) VALUES ({', '.join('?' for _ in v)})", tuple(v.values()))
    c.commit()


class _DBProxy:
    """Délègue à une vraie connexion, mais simule l'absence de colonne version."""
    def __init__(self, real): self._r = real
    def execute(self, sql, params=()):
        if "SELECT version FROM dossiers" in sql:
            raise sqlite3.OperationalError("no such column: version")
        return self._r.execute(sql, params) if params else self._r.execute(sql)
    def commit(self): return self._r.commit()
    def __getattr__(self, n): return getattr(self._r, n)


class _LogCap(logging.Handler):
    def __init__(self): super().__init__(); self.msgs = []
    def emit(self, r):
        try: self.msgs.append(r.getMessage())
        except Exception: pass


def _run(db):
    cap = _LogCap()
    lg = logging.getLogger("facilim.app"); lg.addHandler(cap); old = lg.level; lg.setLevel(logging.DEBUG)
    pdf = None; err = None
    try:
        _, pdf = m._generer_cerfa_pdf(DID, db)
    except Exception as e:
        err = e
    finally:
        lg.removeHandler(cap); lg.setLevel(old)
    txt = "\n".join(cap.msgs)
    v2 = "[CERFA V2] PDF généré via moteur V2" in txt
    fallback = ("Fallback V3 activé" in txt) or ("Génération V2 échouée" in txt)
    return {"v2": v2, "fallback": fallback, "pdf_len": len(pdf) if pdf else 0, "err": err}


def main():
    sep = "═" * 64
    print(sep); print("  QA-FIX-TEST4-CERFA-V2 — V2 survit à une erreur d'audit"); print(sep)
    base = _conn(); _insert_dossier(base); base.close()

    results = {}

    # Cas 1 — colonne version absente (proxy force l'OperationalError sur SELECT version)
    c1 = _conn()
    r1 = _run(_DBProxy(c1)); c1.close()
    results["Cas 1 — version absente → V2 conservé, pas de fallback"] = (r1["v2"] and not r1["fallback"] and r1["pdf_len"] > 0)

    # Cas 2 — exception d'audit forcée (_log_cerfa_audit lève)
    c2 = _conn()
    with mock.patch.object(m, "_log_cerfa_audit", side_effect=RuntimeError("audit boom")):
        r2 = _run(c2)
    c2.close()
    results["Cas 2 — audit en erreur → V2 conservé, pas de fallback"] = (r2["v2"] and not r2["fallback"] and r2["pdf_len"] > 0)

    # Cas 3 — vraie erreur de génération V2 (la génération elle-même lève)
    c3 = _conn()
    with mock.patch("app.engines.pdf.v2_bridge.generer_cerfa_depuis_synthese", side_effect=RuntimeError("V2 boom")):
        r3 = _run(c3)
    c3.close()
    results["Cas 3 — vraie erreur V2 → fallback V3 autorisé"] = (r3["fallback"] and not r3["v2"] and r3["pdf_len"] > 0)

    # Cas 4 — TEST4 rejoué (aucune injection)
    c4 = _conn()
    r4 = _run(c4); c4.close()
    results["Cas 4 — TEST4 rejoué → V2 utilisé, aucun fallback"] = (r4["v2"] and not r4["fallback"] and r4["pdf_len"] > 0)

    print(f"\n  Cas 1 : v2={r1['v2']} fallback={r1['fallback']} pdf={r1['pdf_len']}o")
    print(f"  Cas 2 : v2={r2['v2']} fallback={r2['fallback']} pdf={r2['pdf_len']}o")
    print(f"  Cas 3 : v2={r3['v2']} fallback={r3['fallback']} pdf={r3['pdf_len']}o  (fallback attendu)")
    print(f"  Cas 4 : v2={r4['v2']} fallback={r4['fallback']} pdf={r4['pdf_len']}o\n")
    for label, ok in results.items():
        print(f"     {'✅' if ok else '❌'} {label}")

    # nettoyage du dossier de test
    cc = _conn(); cc.execute("DELETE FROM dossiers WHERE id = ?", (DID,)); cc.commit(); cc.close()

    ok = all(results.values())
    print(f"\n{sep}")
    print(f"  DÉCISION QA-FIX-TEST4-CERFA-V2 : {'✅ PASS' if ok else '❌ FAIL'} ({sum(results.values())}/{len(results)})")
    print(sep)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
