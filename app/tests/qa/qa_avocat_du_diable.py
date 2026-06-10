"""
app/tests/qa/qa_avocat_du_diable.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-AVOCAT-1→6 — Étape 7 (doctrine) : la revue, avocat du diable (refusal_risk).

Décision médico-sociale : la MDPH évalue le RETENTISSEMENT FONCTIONNEL, pas le
diagnostic (qui vit sur le certificat 15695). Le moteur de risque ne pénalise donc
plus l'absence de diagnostic/taux DANS le dossier ; il objective le retentissement
réellement collecté et, pour le médical, rappelle le certificat.

  QA-AVOCAT-1 : AAH avec retentissement fonctionnel → risque faible.
  QA-AVOCAT-2 : AAH creux → risque élevé + motif « retentissement trop mince ».
  QA-AVOCAT-3 : plus de pénalité « diagnostic absent » (médical hors CERFA).
  QA-AVOCAT-4 : RQTH sans certificat → réclame le CERTIFICAT (pas le diagnostic).
  QA-AVOCAT-5 : AEEH pour un adulte → incohérence majeure (non-régression).
  QA-AVOCAT-6 : dossier_strength.noter_robustesse fonctionne (score + axes).

Usage : python -m app.tests.qa.qa_avocat_du_diable
"""

from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.engines.refusal_risk_engine import evaluer_risques_refus


def _risque(donnees, profil, droit):
    rapport = evaluer_risques_refus(donnees, profil)
    for r in rapport.risques_par_droit:
        if r.droit == droit:
            return r
    return None


def run() -> bool:
    res: dict[str, bool] = {}

    aah_solide = {
        "droits_demandes": "AAH",
        "impact_quotidien": "je ne peux plus rester debout longtemps, douleurs, besoin d'aide pour les courses",
        "aides_en_place": "aide d'un proche pour le ménage et les courses",
        "certificat_medical_date": "12/03/2026",
        "restrictions_emploi": "inaptitude au poste prononcée",
    }
    aah_creux = {"droits_demandes": "AAH"}

    r1 = _risque(aah_solide, "adulte", "AAH")
    res["QA-AVOCAT-1 — AAH avec retentissement → faible"] = r1 is not None and r1.niveau_risque == "faible"

    r2 = _risque(aah_creux, "adulte", "AAH")
    res["QA-AVOCAT-2 — AAH creux → élevé + « trop mince »"] = (
        r2 is not None and r2.niveau_risque == "élevé" and "trop mince" in r2.justification.lower()
    )

    # QA-AVOCAT-3 : un dossier sans diagnostics ne doit PLUS être pénalisé « diagnostic absent »
    tous_textes = " ".join(
        " ".join(r.points_faibles) + " " + " ".join(r.pieces_manquantes)
        for r in evaluer_risques_refus(aah_solide, "adulte").risques_par_droit
    ).lower()
    res["QA-AVOCAT-3 — plus de pénalité « diagnostic absent »"] = "diagnostic absent" not in tous_textes

    # QA-AVOCAT-4 : RQTH sans certificat → réclame le certificat, pas le diagnostic
    r4 = _risque({"droits_demandes": "RQTH", "statut_emploi": "sans emploi"}, "adulte", "RQTH")
    pieces4 = " ".join(r4.pieces_manquantes).lower() if r4 else ""
    res["QA-AVOCAT-4 — RQTH réclame le certificat (pas le diagnostic)"] = (
        "certificat" in pieces4 and "diagnostic" not in pieces4
    )

    # QA-AVOCAT-5 : AEEH pour adulte → incohérence CRITIQUE (le bon mécanisme)
    r5 = evaluer_risques_refus({"droits_demandes": "AEEH"}, "adulte")
    incoh5 = [i.to_dict() for i in r5.incoherences]
    res["QA-AVOCAT-5 — AEEH adulte → incohérence critique détectée"] = any(
        i.get("droit") == "AEEH" and i.get("gravite") == "critique" for i in incoh5
    )

    # QA-AVOCAT-6 : dossier_strength fonctionne
    try:
        from app.engines.dossier_strength_engine import noter_robustesse
        rob = noter_robustesse(aah_solide, "adulte")
        res["QA-AVOCAT-6 — robustesse calculée (score 0-100)"] = (
            hasattr(rob, "score_global") and 0 <= rob.score_global <= 100
        )
    except Exception as e:  # pragma: no cover
        print(f"     ⚠️  QA-AVOCAT-6 : {e}")
        res["QA-AVOCAT-6 — robustesse calculée (score 0-100)"] = False

    print("=" * 64)
    print("  QA-AVOCAT-1→6 — Revue avocat du diable (Étape 7)")
    print("=" * 64)
    print()
    ok = True
    for label, passed in res.items():
        print(f"     {'✅' if passed else '❌'} {label}")
        ok = ok and passed
    print()
    print("=" * 64)
    print(f"  DÉCISION QA-AVOCAT : {'✅ PASS' if ok else '❌ FAIL'} ({sum(res.values())}/{len(res)})")
    print("=" * 64)
    return ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
