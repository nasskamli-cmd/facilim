"""
app/tests/qa/qa_droits_page17.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-P17-1→8 — Page 17 (E1) : demandes de droits selon l'âge + cohérence.

Spec : CARTOGRAPHIE_CERFA_15692.md, page 17 — « Selon l'âge calculé. Moins de
20 ans : AEEH… Plus de 20 ans : AAH (→ compléter D)… une demande sans case, ou
une case sans demande, sont des fautes. »

Point clé : la frontière des allocations est 20 ans, distincte de `is_enfant`
(18 ans, pour l'autorité parentale / la scolarité). Un jeune de 18-19 ans relève
encore de l'AEEH alors qu'il est juridiquement adulte.

  QA-P17-1 : 19 ans (is_enfant=False) + AEEH → P17 1 coché, pas P17 6.
  QA-P17-2 : 19 ans + AAH → P17 6 NON coché (AAH ≥ 20 ans).
  QA-P17-3 : 25 ans + AAH → P17 6 ; rétro-compat moins_de_20=None = is_enfant.
  QA-P17-4 : cohérence — AAH pour 15 ans → alerte ROUGE.
  QA-P17-5 : cohérence — AEEH pour 30 ans → alerte ROUGE.
  QA-P17-6 : cohérence — AAH sans volet pro (D) → alerte ORANGE.
  QA-P17-7 : cohérence — CMI sans type → alerte ORANGE.
  QA-P17-8 : pas de fausse alerte pour un adulte AAH + RQTH + projet pro.

Usage : python -m app.tests.qa.qa_droits_page17
"""

from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.engines.revue_instructeur import controles_coherence
from services.cerfa_filler import _mapper_droits


def _labels(donnees: dict) -> str:
    return " || ".join(a.get("label", "") for a in controles_coherence(donnees, "adulte"))


def run() -> bool:
    res: dict[str, bool] = {}

    # ── Part A — routage moins_de_20 ──
    c19_aeeh = _mapper_droits(["AEEH"], is_enfant=False, besoins_aide_humaine=False, moins_de_20=True)
    res["QA-P17-1 — 19 ans AEEH → P17 1, pas P17 6"] = (
        "Case à cocher P17 1" in c19_aeeh and "Case à cocher P17 6" not in c19_aeeh
    )

    c19_aah = _mapper_droits(["AAH"], is_enfant=False, besoins_aide_humaine=False, moins_de_20=True)
    res["QA-P17-2 — 19 ans AAH → P17 6 non coché"] = "Case à cocher P17 6" not in c19_aah

    c25_aah = _mapper_droits(["AAH"], is_enfant=False, besoins_aide_humaine=False, moins_de_20=False)
    compat_ad = _mapper_droits(["AAH"], is_enfant=False, besoins_aide_humaine=False)  # None → is_enfant
    compat_enf = _mapper_droits(["AEEH"], is_enfant=True, besoins_aide_humaine=False)
    res["QA-P17-3 — 25 ans AAH → P17 6 ; rétro-compat None"] = (
        "Case à cocher P17 6" in c25_aah
        and "Case à cocher P17 6" in compat_ad
        and "Case à cocher P17 1" in compat_enf
    )

    # ── Part B — cohérence (controles_coherence) ──
    al4 = _labels({"date_naissance": "01/01/2011", "droits_demandes": "AAH"})  # ~15 ans
    res["QA-P17-4 — AAH pour 15 ans → ROUGE"] = "AAH demandée" in al4 and "moins de 20" in al4

    al5 = _labels({"date_naissance": "01/01/1996", "droits_demandes": "AEEH"})  # ~30 ans
    res["QA-P17-5 — AEEH pour 30 ans → ROUGE"] = "AEEH demandée" in al5 and "20 ou plus" in al5

    al6 = _labels({"date_naissance": "01/01/1990", "droits_demandes": "AAH"})  # adulte, sans volet pro
    res["QA-P17-6 — AAH sans volet pro → ORANGE"] = "volet professionnel" in al6

    al7 = _labels({"date_naissance": "01/01/1990", "droits_demandes": "RQTH, CMI"})  # CMI sans type
    res["QA-P17-7 — CMI sans type → ORANGE"] = "CMI est demandée sans préciser le type" in al7

    al8 = _labels({
        "date_naissance": "01/01/1990",
        "droits_demandes": "AAH, RQTH",
        "projet_professionnel": "reconversion en cours",
    })
    res["QA-P17-8 — adulte AAH+RQTH+projet → pas d'alerte âge/pro"] = (
        "AAH demandée" not in al8
        and "volet professionnel" not in al8
    )

    # ── Rapport ──
    print("=" * 64)
    print("  QA-P17-1→8 — Page 17 (E1) demandes de droits selon l'âge")
    print("=" * 64)
    print()
    ok = True
    for label, passed in res.items():
        print(f"     {'✅' if passed else '❌'} {label}")
        ok = ok and passed
    print()
    print("=" * 64)
    print(f"  DÉCISION QA-P17 : {'✅ PASS' if ok else '❌ FAIL'} ({sum(res.values())}/{len(res)})")
    print("=" * 64)
    return ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
