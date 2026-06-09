"""
app/tests/qa/qa_medical_hors_cerfa.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-MED-1→5 — Le médical ne figure pas sur le CERFA (cartographie).

Spec : CARTOGRAPHIE_CERFA_15692.md — « Le médical n'est pas ici. Médecin traitant,
diagnostics, traitements ne figurent pas sur ce CERFA : ils sont sur le certificat
médical (15695). On ne les demande pas, on ne les écrit pas. On enregistre SA date
(jamais celle du CERFA), et l'instructeur alerte s'il manque ou s'il a plus d'un an. »

  QA-MED-1 : diagnostics / traitements / medecin_traitant ne sont PLUS demandés
             (absents de la checklist de tous les profils).
  QA-MED-2 : diagnostics n'est PLUS bloquant (criticite = 'signale').
  QA-MED-3 : le certificat médical (existence + date) reste demandé (conservé).
  QA-MED-4 : diagnostics n'apparaît plus dans missing_field_ids (jamais redemandé).
  QA-MED-5 : le moteur narratif n'injecte plus le diagnostic dans ses prompts.

Usage : python -m app.tests.qa.qa_medical_hors_cerfa
"""

from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.services.collecte_schema import checklist_for, criticite_champ

_MEDICAL = {"diagnostics", "traitements", "medecin_traitant"}


def run() -> bool:
    res: dict[str, bool] = {}

    # QA-MED-1 : médical absent des checklists de tous les profils
    absent_partout = True
    for profil in ("adulte", "enfant", "protege", "mixte"):
        ids = {it.get("id") for it in checklist_for(profil)}
        if _MEDICAL & ids:
            absent_partout = False
    res["QA-MED-1 — médical non demandé (tous profils)"] = absent_partout

    # QA-MED-2 : diagnostics non bloquant
    res["QA-MED-2 — diagnostics non bloquant"] = criticite_champ("diagnostics") == "signale"

    # QA-MED-3 : certificat médical (date) conservé
    ids_adulte = {it.get("id") for it in checklist_for("adulte")}
    res["QA-MED-3 — certificat médical conservé"] = "certificat_medical_date" in ids_adulte

    # QA-MED-4 : diagnostics jamais dans missing_field_ids
    from app.services.conversation.router import get_agent
    ag = get_agent("adulte")
    miss = ag.missing_field_ids({})  # dossier vide → plein de manquants, mais PAS diagnostics
    res["QA-MED-4 — diagnostics hors missing_field_ids"] = "diagnostics" not in miss

    # QA-MED-5 : prompt narratif sans injection de diagnostic
    from pathlib import Path
    src = (Path(__file__).resolve().parents[2] / "engines" / "cerfa_narrative_engine.py").read_text(encoding="utf-8")
    res["QA-MED-5 — narratif sans injection diagnostic"] = "INFO MANQUANTE : diagnostics" not in src

    print("=" * 64)
    print("  QA-MED-1→5 — Médical hors CERFA")
    print("=" * 64)
    print()
    ok = True
    for label, passed in res.items():
        print(f"     {'✅' if passed else '❌'} {label}")
        ok = ok and passed
    print()
    print("=" * 64)
    print(f"  DÉCISION QA-MED : {'✅ PASS' if ok else '❌ FAIL'} ({sum(res.values())}/{len(res)})")
    print("=" * 64)
    return ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
