"""
app/tests/qa/qa_coherence_case_recit.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-COH-1→5 — Étape 4 (doctrine) : cohérence BIDIRECTIONNELLE case ↔ récit.

« Chaque case cochée doit se retrouver dans le récit, et chaque difficulté racontée
doit avoir sa case. La moindre contradiction installe le doute, et le doute se paie
en refus. » On signale au pro, on ne fabrique JAMAIS ni case ni texte.

  QA-COH-1 : besoin AVQ coché MAIS absent du récit → alerte (case → récit).
  QA-COH-2 : besoin AVQ coché ET présent dans le récit → pas d'alerte.
  QA-COH-3 : difficulté évoquée (verbatim) MAIS aucune case AVQ → alerte (récit → case).
  QA-COH-4 : domaine évalué AUTONOME + évoqué → pas d'alerte (déjà qualifié).
  QA-COH-5 : non-régression — dossier sans AVQ ni récit → aucune alerte de cohérence.

Usage : python -m app.tests.qa.qa_coherence_case_recit
"""

from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.engines.revue_instructeur import coherence_cases_recit, controles_coherence

_RECIT_REPAS = ("Au quotidien, la personne décrit surtout des difficultés pour préparer "
                "ses repas et faire la cuisine ; elle se fatigue vite.")
_RECIT_TOILETTE = ("Au quotidien, la personne a besoin d'aide pour la toilette et se laver ; "
                   "elle ne peut pas le faire seule sans assistance.")


def _labels(donnees: dict) -> str:
    return " || ".join(a["label"] for a in coherence_cases_recit(donnees))


def run() -> bool:
    res: dict[str, bool] = {}

    # QA-COH-1 : toilette cochée besoin, récit ne parle QUE de repas → alerte case→récit
    al1 = _labels({"avq_toilette": "AIDE_TOTALE", "texte_b_vie_quotidienne": _RECIT_REPAS})
    res["QA-COH-1 — case cochée absente du récit → alerte"] = (
        "case/récit" in al1 and "Toilette" in al1
    )

    # QA-COH-2 : toilette cochée besoin, récit la mentionne → pas d'alerte case→récit
    al2 = _labels({"avq_toilette": "AIDE_TOTALE", "texte_b_vie_quotidienne": _RECIT_TOILETTE})
    res["QA-COH-2 — case cochée présente dans le récit → pas d'alerte"] = (
        "case/récit" not in al2
    )

    # QA-COH-3 : verbatim évoque la toilette mais aucune case AVQ → alerte récit→case
    al3 = _labels({"impact_quotidien": "je n'arrive plus à faire ma toilette seule"})
    res["QA-COH-3 — difficulté évoquée sans case → alerte"] = (
        "récit/case" in al3 and "Toilette" in al3
    )

    # QA-COH-4 : domaine évalué AUTONOME + évoqué → pas d'alerte récit→case
    al4 = _labels({"avq_toilette": "AUTONOME", "impact_quotidien": "je gère ma toilette sans souci"})
    res["QA-COH-4 — domaine évalué (AUTONOME) → pas d'alerte récit/case"] = (
        "récit/case" not in al4
    )

    # QA-COH-5 : dossier vide → aucune alerte de cohérence case/récit
    res["QA-COH-5 — non-régression : dossier sans AVQ ni récit"] = (
        coherence_cases_recit({}) == []
    )

    # QA-COH-6 : CONTRADICTION (avocat du diable doux) — évalué AUTONOME mais difficulté
    # évoquée dans l'impact quotidien → flag « À vérifier » (l'exemple-type de la doctrine).
    al6 = _labels({"avq_habillage": "AUTONOME",
                   "impact_quotidien": "je mets 40 minutes à m'habiller le matin"})
    res["QA-COH-6 — contradiction AUTONOME/difficulté → à vérifier"] = (
        "À vérifier" in al6 and "Habillage" in al6
    )

    # QA-COH-7 : conclusion d'aide AMBIGUË dans le récit, non déclarée → la revue
    # demande de l'étayer (sans rejet, sans invention).
    alertes7 = controles_coherence(
        {"droits_demandes": "AAH", "impact_quotidien": "grande fatigue",
         "texte_b_vie_quotidienne": "La personne a besoin d'une aide humaine au quotidien."},
        "adulte",
    )
    labels7 = " || ".join(a["label"] for a in alertes7)
    res["QA-COH-7 — conclusion ambiguë non déclarée → à étayer"] = (
        "aide humaine" in labels7 and "étayer" in labels7
    )

    print("=" * 64)
    print("  QA-COH-1→5 — Cohérence bidirectionnelle case ↔ récit (Étape 4)")
    print("=" * 64)
    print()
    ok = True
    for label, passed in res.items():
        print(f"     {'✅' if passed else '❌'} {label}")
        ok = ok and passed
    print()
    print("=" * 64)
    print(f"  DÉCISION QA-COH : {'✅ PASS' if ok else '❌ FAIL'} ({sum(res.values())}/{len(res)})")
    print("=" * 64)
    return ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
