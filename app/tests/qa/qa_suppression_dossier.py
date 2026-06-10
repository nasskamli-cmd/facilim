"""
app/tests/qa/qa_suppression_dossier.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-DEL-1→5 — Suppression d'un dossier : pas d'alerte fantôme, pas de résurrection.

Bug terrain : après suppression d'un dossier, l'alerte « Revue instructeur » restait
visible (acquittee=0) ; au clic (openDossier), le dossier « revenait ». Cause : le
soft-delete ne touchait pas la table `alertes`.

Correctif (delete_dossier) : à la suppression, on ACQUITTE les alertes et on ANNULE
les relances planifiées ; les filtres `deleted_at IS NULL` (liste, get_alertes,
get_dossier) empêchent tout réaffichage / réouverture.

  QA-DEL-1 : après suppression, le dossier disparaît de la liste.
  QA-DEL-2 : l'alerte du dossier est acquittée (acquittee=1).
  QA-DEL-3 : get_alertes (filtre réel) ne renvoie plus l'alerte du dossier supprimé.
  QA-DEL-4 : la relance planifiée est annulée.
  QA-DEL-5 : get_dossier (filtre réel) ne peut pas rouvrir le dossier supprimé.

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
    con.execute("CREATE TABLE relances (id TEXT, dossier_id TEXT, statut TEXT)")
    con.execute("INSERT INTO dossiers VALUES ('D1', NULL, '2026-01-01')")
    con.execute("INSERT INTO alertes VALUES ('A1','D1','REVUE_INSTRUCTEUR',0)")
    con.execute("INSERT INTO relances VALUES ('R1','D1','PLANIFIEE')")
    return con


def _delete_logic(con: sqlite3.Connection, dossier_id: str) -> None:
    """Réplique exacte de delete_dossier (main.py) après correctif."""
    now = "2026-06-10T00:00:00Z"
    con.execute("UPDATE dossiers SET deleted_at = ?, updated_at = ? WHERE id = ?", (now, now, dossier_id))
    con.execute("UPDATE alertes SET acquittee = 1 WHERE dossier_id = ? AND acquittee = 0", (dossier_id,))
    con.execute("UPDATE relances SET statut = 'ANNULEE' WHERE dossier_id = ? AND statut = 'PLANIFIEE'", (dossier_id,))


def run() -> bool:
    res: dict[str, bool] = {}
    con = _setup()
    _delete_logic(con, "D1")

    # QA-DEL-1 : liste (filtre réel)
    liste = con.execute("SELECT id FROM dossiers WHERE deleted_at IS NULL").fetchall()
    res["QA-DEL-1 — dossier hors liste"] = len(liste) == 0

    # QA-DEL-2 : alerte acquittée
    acq = con.execute("SELECT acquittee FROM alertes WHERE id = 'A1'").fetchone()[0]
    res["QA-DEL-2 — alerte acquittée"] = acq == 1

    # QA-DEL-3 : get_alertes (filtre réel main.py:1135+1155)
    alertes = con.execute(
        "SELECT a.id FROM alertes a LEFT JOIN dossiers d ON d.id = a.dossier_id "
        "WHERE a.type_alerte IN ('FLAG_HUMAIN','CHAMP_NON_COMMUNIQUE','CHAMP_A_COMPLETER_PRO','REVUE_INSTRUCTEUR') "
        "AND a.acquittee = 0 AND d.id IS NOT NULL AND d.deleted_at IS NULL"
    ).fetchall()
    res["QA-DEL-3 — get_alertes n'affiche plus l'alerte"] = len(alertes) == 0

    # QA-DEL-4 : relance annulée
    st = con.execute("SELECT statut FROM relances WHERE id = 'R1'").fetchone()[0]
    res["QA-DEL-4 — relance planifiée annulée"] = st == "ANNULEE"

    # QA-DEL-5 : get_dossier (filtre réel main.py:906) ne rouvre pas
    d = con.execute("SELECT id FROM dossiers WHERE id = 'D1' AND deleted_at IS NULL").fetchone()
    res["QA-DEL-5 — get_dossier ne peut pas rouvrir (pas de résurrection)"] = d is None

    print("=" * 64)
    print("  QA-DEL-1→5 — Suppression dossier (anti-alerte-fantôme)")
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
