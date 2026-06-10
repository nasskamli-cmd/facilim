"""
app/tests/qa/qa_elicitation_retentissement.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-ELIC-1→5 — Étape 1 (DOCTRINE_RENFORCEMENT_LEGITIME) : élicitation du retentissement.

La doctrine : on ne gagne pas le taux d'incapacité en gonflant un fait, mais en POSANT MIEUX
les questions, pour faire sortir un retentissement réel mais tu. Ancrage « journée ordinaire »,
réponse possible à la VOIX, capture de la NATURE de l'aide (physique/verbale/matérielle), sans
jamais durcir ni inventer.

  QA-ELIC-1 : la règle ancre les questions dans une journée ordinaire (moments concrets).
  QA-ELIC-2 : la règle propose la réponse par message vocal (en plus du FALC).
  QA-ELIC-3 : la règle capte la NATURE de l'aide : physique, verbale, matérielle.
  QA-ELIC-4 : l'anti-invention est PRÉSERVÉE (ne pas supposer, laisser vide en cas de doute).
  QA-ELIC-5 : la règle est bien INJECTÉE dans les 3 agents (adulte / enfant / protégé).

Usage : python -m app.tests.qa.qa_elicitation_retentissement
"""

from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.services.conversation._shared import REGLES_COMMUNICATION_COMMUNES as R
from app.services.conversation.router import get_agent

_low = R.lower()


def run() -> bool:
    res: dict[str, bool] = {}

    # QA-ELIC-1 : ancrage journée ordinaire (moments concrets)
    res["QA-ELIC-1 — ancrage journée ordinaire"] = (
        "journée ordinaire" in _low
        and "journée type" in _low
        and all(m in _low for m in ("lever", "toilette", "repas", "courses", "déplacements", "démarches"))
    )

    # QA-ELIC-2 : proposition de réponse vocale + FALC
    res["QA-ELIC-2 — réponse vocale proposée"] = (
        "vocal" in _low and "falc" in _low
    )

    # QA-ELIC-3 : nature de l'aide (physique / verbale / matérielle)
    res["QA-ELIC-3 — nature de l'aide (physique/verbale/matérielle)"] = all(
        m in _low for m in ("physique", "verbale", "matérielle", "stimulation", "guidance")
    )

    # QA-ELIC-4 : anti-invention préservée
    res["QA-ELIC-4 — anti-invention préservée"] = (
        "ne suppose jamais" in _low
        and "anti-invention" in _low
        and "laisse vide et demande" in _low
        and "exactement ma situation" in _low
    )

    # QA-ELIC-5 : règle injectée dans les 3 agents
    injecte_partout = True
    for profil in ("adulte", "enfant", "protege"):
        prompt = getattr(get_agent(profil), "SYSTEM_PROMPT", "")
        if "ÉLICITATION DU RETENTISSEMENT" not in prompt or "journée type" not in prompt.lower():
            injecte_partout = False
    res["QA-ELIC-5 — injectée dans les 3 agents"] = injecte_partout

    print("=" * 64)
    print("  QA-ELIC-1→5 — Élicitation du retentissement (Étape 1)")
    print("=" * 64)
    print()
    ok = True
    for label, passed in res.items():
        print(f"     {'✅' if passed else '❌'} {label}")
        ok = ok and passed
    print()
    print("=" * 64)
    print(f"  DÉCISION QA-ELIC : {'✅ PASS' if ok else '❌ FAIL'} ({sum(res.values())}/{len(res)})")
    print("=" * 64)
    return ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
