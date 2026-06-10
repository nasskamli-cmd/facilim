"""
app/tests/qa/qa_validite_dossier.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-VAL-1→5 — Validité métier (« ouvre des droits »), pas taux de remplissage.

Spec : CARTOGRAPHIE_CERFA_15692.md — « Validité, pas remplissage. Un dossier est
"prêt" seulement si au moins une demande de droit est exprimée, toute orientation
est justifiée, le récit est fidèle, et il n'y a ni donnée du prescripteur ni
invention. Le score doit dire "ouvre des droits", pas "rempli à X %". »

  QA-VAL-1 : dossier sans demande → PAS prêt.
  QA-VAL-2 : une demande, sans orientation pro → prêt.
  QA-VAL-3 : orientation pro (RQTH) demandée SANS projet → PAS prêt (non justifiée).
  QA-VAL-4 : orientation pro (RQTH) + projet renseigné → prêt.
  QA-VAL-5 : un champ critique refusé → PAS prêt (finalisation bloquée).

Usage : python -m app.tests.qa.qa_validite_dossier
"""

from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.engines.revue_instructeur import validite_dossier
from app.services.field_status import marquer_refus

# Cœur substantiel d'un dossier solide (sinon « pas prêt », même avec une demande).
_COEUR = {
    "impact_quotidien": "fatigue importante, douleurs au quotidien",
    "aides_en_place": "aide de ma compagne pour les courses",
    "attentes_usager": "besoin d'une reconnaissance et d'aides",
    "projet_de_vie": "rester autonome à domicile",
}


def run() -> bool:
    res: dict[str, bool] = {}

    v1 = validite_dossier({}, "adulte")
    res["QA-VAL-1 — sans demande → pas prêt"] = (v1["pret"] is False) and not v1["criteres"]["au_moins_une_demande"]

    # Demande + cœur solide, sans orientation pro → prêt.
    v2 = validite_dossier({"droits_demandes": "AAH", **_COEUR}, "adulte")
    res["QA-VAL-2 — demande + cœur solide → prêt"] = v2["pret"] is True

    v3 = validite_dossier({"droits_demandes": "RQTH, orientation professionnelle", **_COEUR}, "adulte")
    res["QA-VAL-3 — orientation sans projet → pas prêt"] = (
        v3["pret"] is False and not v3["criteres"]["orientation_justifiee"]
    )

    v4 = validite_dossier(
        {"droits_demandes": "RQTH, orientation professionnelle",
         "projet_professionnel": "reconversion via ESRP", **_COEUR}, "adulte",
    )
    res["QA-VAL-4 — orientation + projet + cœur → prêt"] = v4["pret"] is True

    d5 = {"droits_demandes": "AAH", **_COEUR}
    marquer_refus(d5, "num_secu", "je ne veux pas donner mon numéro")
    v5 = validite_dossier(d5, "adulte")
    res["QA-VAL-5 — champ critique refusé → pas prêt"] = (
        v5["pret"] is False and not v5["criteres"]["pas_de_blocage"]
    )

    # Dossier creux (une demande, cœur vide) → PAS prêt (critère validation clé).
    v6 = validite_dossier({"droits_demandes": "AAH"}, "adulte")
    res["QA-VAL-6 — dossier creux → pas prêt"] = (
        v6["pret"] is False and not v6["criteres"]["dossier_solide"]
    )

    print("=" * 64)
    print("  QA-VAL-1→5 — Validité métier (ouvre des droits)")
    print("=" * 64)
    print()
    ok = True
    for label, passed in res.items():
        print(f"     {'✅' if passed else '❌'} {label}")
        ok = ok and passed
    print()
    print("=" * 64)
    print(f"  DÉCISION QA-VAL : {'✅ PASS' if ok else '❌ FAIL'} ({sum(res.values())}/{len(res)})")
    print("=" * 64)
    return ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
