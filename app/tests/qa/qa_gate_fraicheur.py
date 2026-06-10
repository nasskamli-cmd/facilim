"""
app/tests/qa/qa_gate_fraicheur.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-FRAICHEUR-1→4 — Anti-gate-obsolète au verrou d'export.

Risque audité : le gate persisté (cockpit_pro_json) peut être périmé (une édition
dashboard modifie synthese_json SANS recalculer le gate). Sans garde, un dossier
au cœur devenu incomplet, mais portant un gate « PASS » obsolète, serait exporté.

Correctif : export_gate.coeur_incomplet revérifie la solidité du cœur sur la
synthèse FRAÎCHE, et le verrou bloque l'export indépendamment du gate persisté.

  QA-FRAICHEUR-1 : coeur_incomplet bloque un dossier creux (cœur vide).
  QA-FRAICHEUR-2 : coeur_incomplet bloque un cœur partiel.
  QA-FRAICHEUR-3 : coeur_incomplet NE bloque PAS un cœur solide.
  QA-FRAICHEUR-4 : SCÉNARIO DE RUPTURE — gate persisté « PASS » + synthèse fraîche
                   incomplète ⇒ décision finale = BLOQUÉ (le verrou refuse).

Usage : python -m app.tests.qa.qa_gate_fraicheur
"""

from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.services.export_gate import coeur_incomplet, lire_gate_export

_COEUR = {
    "impact_quotidien": "douleurs et fatigue au quotidien",
    "aides_en_place": "aide d'un proche pour les courses",
    "attentes_usager": "obtenir des aides adaptées",
    "projet_de_vie": "rester autonome à domicile",
}


def run() -> bool:
    res: dict[str, bool] = {}

    b1, r1 = coeur_incomplet({"droits_demandes": "AAH"})
    res["QA-FRAICHEUR-1 — dossier creux bloqué"] = b1 is True and r1.startswith("cœur")

    b2, _ = coeur_incomplet({"droits_demandes": "AAH", "impact_quotidien": "fatigue"})
    res["QA-FRAICHEUR-2 — cœur partiel bloqué"] = b2 is True

    b3, r3 = coeur_incomplet({"droits_demandes": "AAH", **_COEUR})
    res["QA-FRAICHEUR-3 — cœur solide autorisé"] = b3 is False and r3 == ""

    # ── SCÉNARIO DE RUPTURE (Cas A/C de l'audit) ──
    # Gate persisté « PASS » (calculé quand le cœur était complet)…
    gate_persiste_pass = {"gate_export": {"decision": "AUTORISE", "message": "ok"}}
    g = lire_gate_export(gate_persiste_pass)
    # …mais la synthèse FRAÎCHE a un cœur vidé (édition dashboard) :
    synthese_fraiche = {"droits_demandes": "AAH"}   # cœur vide
    coeur_bloque, _ = coeur_incomplet(synthese_fraiche)
    # Décision finale du verrou = autorisé seulement si gate PASS ET cœur frais OK.
    export_autorise_final = g["autorise_export"] and not coeur_bloque
    res["QA-FRAICHEUR-4 — gate PASS obsolète + cœur vide ⇒ export BLOQUÉ"] = (
        g["autorise_export"] is True          # le gate persisté dit (à tort) « OK »
        and coeur_bloque is True              # mais la fraîcheur détecte le cœur vide
        and export_autorise_final is False    # ⇒ verrou refuse
    )

    print("=" * 64)
    print("  QA-FRAICHEUR-1→4 — Anti-gate-obsolète (verrou export)")
    print("=" * 64)
    print()
    ok = True
    for label, passed in res.items():
        print(f"     {'✅' if passed else '❌'} {label}")
        ok = ok and passed
    print()
    print("=" * 64)
    print(f"  DÉCISION QA-FRAICHEUR : {'✅ PASS' if ok else '❌ FAIL'} ({sum(res.values())}/{len(res)})")
    print("=" * 64)
    return ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
