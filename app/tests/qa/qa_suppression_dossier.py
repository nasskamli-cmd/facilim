"""
app/tests/qa/qa_suppression_dossier.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-DEL-1→10 — Fermeture complète : suppression de dossier, alertes & relances orphelines.

Règle de fermeture : un dossier supprimé (deleted_at) est INVISIBLE, NON OUVRABLE,
NON RELANÇABLE, NON ALERTABLE sur toute l'application.

Le test reproduit FIDÈLEMENT les requêtes réelles de app/main.py :
  - suppression : delete_dossier (deleted_at + acquittement alertes + annulation relances)
  - liste        : SELECT * FROM dossiers WHERE deleted_at IS NULL
  - alertes      : get_alertes (JOIN dossiers, acquittee=0, deleted_at IS NULL)
  - relances     : get_alertes relances (JOIN dossiers, statut='PLANIFIEE', deleted_at IS NULL)
  - ouverture    : get_dossier (WHERE id=? AND deleted_at IS NULL)

Usage : python -m app.tests.qa.qa_suppression_dossier
"""

from __future__ import annotations

import sqlite3
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _setup() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE dossiers (id TEXT, deleted_at TEXT, updated_at TEXT)")
    con.execute("CREATE TABLE alertes (id TEXT, dossier_id TEXT, type_alerte TEXT, acquittee INT)")
    con.execute("CREATE TABLE relances (id TEXT, dossier_id TEXT, statut TEXT, planifiee_le TEXT)")
    return con


# ── Requêtes RÉELLES répliquées depuis app/main.py ───────────────────────────
def _delete_dossier(con, did):           # delete_dossier (main.py:3128)
    now = "2026-06-10T00:00:00Z"
    con.execute("UPDATE dossiers SET deleted_at=?, updated_at=? WHERE id=?", (now, now, did))
    con.execute("UPDATE alertes SET acquittee=1 WHERE dossier_id=? AND acquittee=0", (did,))
    con.execute("UPDATE relances SET statut='ANNULEE' WHERE dossier_id=? AND statut='PLANIFIEE'", (did,))

def _liste(con):                          # liste dossiers (main.py:874)
    return [r[0] for r in con.execute("SELECT id FROM dossiers WHERE deleted_at IS NULL").fetchall()]

def _get_alertes(con):                    # get_alertes alertes (main.py:1147)
    return con.execute(
        "SELECT a.id FROM alertes a LEFT JOIN dossiers d ON d.id=a.dossier_id "
        "WHERE a.type_alerte IN ('FLAG_HUMAIN','CHAMP_NON_COMMUNIQUE','CHAMP_A_COMPLETER_PRO','REVUE_INSTRUCTEUR') "
        "AND a.acquittee=0 AND d.id IS NOT NULL AND d.deleted_at IS NULL").fetchall()

def _get_relances(con):                   # get_alertes relances (main.py:1160, corrigé)
    return con.execute(
        "SELECT r.id FROM relances r LEFT JOIN dossiers d ON d.id=r.dossier_id "
        "WHERE r.statut='PLANIFIEE' AND d.id IS NOT NULL AND d.deleted_at IS NULL").fetchall()

def _get_dossier(con, did):               # get_dossier ouverture (main.py:906)
    return con.execute("SELECT id FROM dossiers WHERE id=? AND deleted_at IS NULL", (did,)).fetchone()


def run() -> bool:
    res: dict[str, bool] = {}
    con = _setup()

    # QA-DEL-1/2/3 : créer dossier + alerte + relance
    con.execute("INSERT INTO dossiers VALUES ('D1', NULL, '2026-01-01')")
    con.execute("INSERT INTO alertes VALUES ('A1','D1','REVUE_INSTRUCTEUR',0)")
    con.execute("INSERT INTO relances VALUES ('R1','D1','PLANIFIEE','2026-01-02')")
    # dossier témoin (non-régression)
    con.execute("INSERT INTO dossiers VALUES ('D2', NULL, '2026-01-01')")
    con.execute("INSERT INTO alertes VALUES ('A2','D2','REVUE_INSTRUCTEUR',0)")
    con.execute("INSERT INTO relances VALUES ('R2','D2','PLANIFIEE','2026-01-02')")
    res["QA-DEL-1/2/3 — dossier + alerte + relance créés"] = (
        _get_dossier(con, "D1") is not None and len(_get_alertes(con)) == 2 and len(_get_relances(con)) == 2
    )

    # QA-DEL-4 : supprimer D1
    _delete_dossier(con, "D1")
    res["QA-DEL-4 — suppression appliquée"] = con.execute(
        "SELECT deleted_at FROM dossiers WHERE id='D1'").fetchone()[0] is not None

    # QA-DEL-5 : liste → D1 absent
    res["QA-DEL-5 — D1 absent de la liste"] = "D1" not in _liste(con)

    # QA-DEL-6 : alertes → aucune alerte de D1
    ids_al = {r[0] for r in _get_alertes(con)}
    res["QA-DEL-6 — aucune alerte liée à D1"] = "A1" not in ids_al

    # QA-DEL-7 : relances → aucune relance active de D1
    ids_rl = {r[0] for r in _get_relances(con)}
    res["QA-DEL-7 — aucune relance active de D1"] = "R1" not in ids_rl

    # QA-DEL-8 : ouverture via URL (get_dossier) → refus
    res["QA-DEL-8 — ouverture via URL refusée"] = _get_dossier(con, "D1") is None

    # QA-DEL-9 : ouverture via alerte (même get_dossier, depuis f.dossier_id) → refus
    #   on simule le clic : l'alerte A1 pointe dossier_id='D1' → get_dossier('D1')
    res["QA-DEL-9 — ouverture via alerte refusée + non restauré"] = (
        _get_dossier(con, "D1") is None and "D1" not in _liste(con)
    )

    # QA-DEL-10 : non-régression → D2 totalement intact
    res["QA-DEL-10 — D2 intact (liste/alerte/relance)"] = (
        "D2" in _liste(con)
        and "A2" in {r[0] for r in _get_alertes(con)}
        and "R2" in {r[0] for r in _get_relances(con)}
    )

    print("=" * 64)
    print("  QA-DEL-1→10 — Fermeture suppression / alertes / relances")
    print("=" * 64)
    print()
    ok = True
    for label, passed in res.items():
        print(f"     {'✅' if passed else '❌'} {label}")
        ok = ok and passed
    print()
    print("=" * 64)
    print(f"  DÉCISION QA-DEL : {'✅ PASS' if ok else '❌ FAIL'} ({sum(res.values())}/{len(res)})")
    print("=" * 64)
    return ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
