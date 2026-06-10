"""
app/tests/qa/qa_anti_invention_generalise.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-INV-1→6 — Étape 2 (doctrine) : garde-fou anti-invention GÉNÉRALISÉ.

Le garde-fou page 8 (rejet d'un acte/aide absent de la source) est factorisé dans
app/services/anti_invention.py et appliqué à TOUTE génération de texte narratif
(sections B/C/D/E). Un texte qui introduit un acte/aide non déclaré est écarté ;
jamais d'invention ne part au dossier.

  QA-INV-1 : detecter_inventions repère un acte absent de la source.
  QA-INV-2 : detecter_inventions n'alerte PAS si l'acte est déclaré (source).
  QA-INV-3 : source_depuis_donnees prend les VALEURS, pas les noms de champs.
  QA-INV-4 : garde_anti_invention renvoie le repli sur invention, le texte sinon.
  QA-INV-5 : bout-en-bout — un texte LLM qui invente « aide pour la toilette »
             (non déclaré) est ÉCARTÉ par generer_textes_narratifs.
  QA-INV-6 : bout-en-bout — un texte fidèle aux données déclarées est CONSERVÉ.

Usage : python -m app.tests.qa.qa_anti_invention_generalise
"""

from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.services.anti_invention import (
    conclusions_a_etayer,
    detecter_inventions,
    garde_anti_invention,
    source_depuis_donnees,
)


# ── Faux client LLM (renvoie un texte fixe) ──────────────────────────────────
class _FakeClient:
    def __init__(self, texte: str):
        self._t = texte
        self.chat = self
        self.completions = self

    def create(self, **kw):
        msg = type("M", (), {"content": self._t})()
        choice = type("C", (), {"message": msg})()
        return type("R", (), {"choices": [choice]})()


def run() -> bool:
    res: dict[str, bool] = {}

    # QA-INV-1 : acte inventé (toilette) absent de la source
    res["QA-INV-1 — invention détectée (acte absent)"] = (
        "toilette" in detecter_inventions("aide pour la toilette chaque matin", "grande fatigue déclarée")
    )

    # QA-INV-2 : acte déclaré → pas d'alerte
    res["QA-INV-2 — pas d'alerte si déclaré"] = (
        detecter_inventions("aide pour la toilette", "je n'arrive plus à faire ma toilette seul") == []
    )

    # QA-INV-3 : source = valeurs, pas les clés (la clé avq_toilette ne doit pas leaker)
    src = source_depuis_donnees({"avq_toilette": "", "impact_quotidien": "fatigue intense"})
    res["QA-INV-3 — source = valeurs, pas les clés"] = (
        "toilette" not in src and "fatigue intense" in src
    )

    # QA-INV-4 : garde renvoie repli sur invention, texte sinon
    t1, inv1 = garde_anti_invention("aide pour la toilette", "fatigue", repli="[ÉCARTÉ]")
    t2, inv2 = garde_anti_invention("la personne est très fatiguée", "fatigue", repli="[ÉCARTÉ]")
    res["QA-INV-4 — repli sur invention, texte sinon"] = (
        t1 == "[ÉCARTÉ]" and inv1 and t2 == "la personne est très fatiguée" and inv2 == []
    )

    # QA-INV-5/6 : bout-en-bout via generer_textes_narratifs
    try:
        from app.engines.cerfa_narrative_engine import generer_textes_narratifs
        donnees = {"nom_prenom": "DURAND Marie", "genre": "F",
                   "impact_quotidien": "grande fatigue et douleurs au quotidien"}

        # QA-INV-5 : le LLM invente « aide pour la toilette » (non déclaré) → écarté
        inv_client = _FakeClient("Au quotidien, Marie a besoin d'aide pour la toilette et l'habillage.")
        r5 = generer_textes_narratifs(donnees, "adulte", inv_client, sections_actives={"B"})
        res["QA-INV-5 — bout-en-bout : invention écartée"] = (
            "écartée" in r5.get("texte_b_vie_quotidienne", "")
        )

        # QA-INV-6 : texte fidèle (ne parle que de fatigue, déclarée) → conservé
        ok_client = _FakeClient("Marie décrit une grande fatigue et des douleurs au quotidien.")
        r6 = generer_textes_narratifs(donnees, "adulte", ok_client, sections_actives={"B"})
        res["QA-INV-6 — bout-en-bout : texte fidèle conservé"] = (
            "écartée" not in r6.get("texte_b_vie_quotidienne", "")
            and "fatigue" in r6.get("texte_b_vie_quotidienne", "").lower()
        )
    except Exception as e:  # pragma: no cover
        print(f"     ⚠️  QA-INV-5/6 non exécuté : {e}")
        res["QA-INV-5 — bout-en-bout : invention écartée"] = False
        res["QA-INV-6 — bout-en-bout : texte fidèle conservé"] = False

    # QA-INV-7 : TIERS — une conclusion AMBIGUË (« aide humaine ») n'est PAS rejetée
    # (traduction légitime possible) mais EST signalée au pro pour étayage.
    src_fatigue = "grande fatigue déclarée"
    res["QA-INV-7 — conclusion ambiguë : non rejetée mais signalée"] = (
        detecter_inventions("besoin d'une aide humaine", src_fatigue) == []   # pas de rejet dur
        and "aide humaine" in conclusions_a_etayer("besoin d'une aide humaine", src_fatigue)  # signalée
    )

    print("=" * 64)
    print("  QA-INV-1→7 — Garde-fou anti-invention généralisé (Étape 2)")
    print("=" * 64)
    print()
    ok = True
    for label, passed in res.items():
        print(f"     {'✅' if passed else '❌'} {label}")
        ok = ok and passed
    print()
    print("=" * 64)
    print(f"  DÉCISION QA-INV : {'✅ PASS' if ok else '❌ FAIL'} ({sum(res.values())}/{len(res)})")
    print("=" * 64)
    return ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
