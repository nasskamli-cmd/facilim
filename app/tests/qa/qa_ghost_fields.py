"""
app/tests/qa/qa_ghost_fields.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-GHOST — Audit anti-champ-fantôme du moteur de remplissage.

Spec : CARTOGRAPHIE_CERFA_15692.md — « Vérifie que chaque champ PDF ciblé existe
réellement (612 champs) — pas de champ fantôme. »

Un champ fantôme = un nom de champ que le filler tente de remplir mais qui
n'existe PAS dans le PDF officiel. L'écriture échoue silencieusement → la donnée
collectée est perdue sans alerte.

Ce test :
  - extrait les noms de champs littéraux cités par services/cerfa_filler.py
    (hors f-strings dynamiques, résolus à l'exécution vers de vrais champs) ;
  - les confronte aux 612 champs réels du template ;
  - ÉCHOUE si un champ fantôme NOUVEAU apparaît (au-delà des fantômes connus,
    documentés ci-dessous et à résoudre avec la cartographie visuelle du PDF).

  QA-GHOST-1 : le template expose bien 612 champs.
  QA-GHOST-2 : aucun champ fantôme NOUVEAU (⊆ liste connue documentée).

Usage : python -m app.tests.qa.qa_ghost_fields
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from pypdf import PdfReader

_TEMPLATE = Path(__file__).resolve().parents[3] / "static" / "forms" / "cerfa_15692.pdf"
_FILLER = Path(__file__).resolve().parents[3] / "services" / "cerfa_filler.py"

# Fantômes CONNUS et DOCUMENTÉS : cités par le filler mais absents du PDF. Ils
# correspondent à des données réellement collectées (préférence de contact,
# urgence, NIR du parent, frais, ressources, nb d'enfants) dont le bon nom de
# champ réel reste à identifier sur la cartographie visuelle du PDF — les assigner
# au hasard écrirait dans la MAUVAISE case (interdit par la règle anti-invention).
# À RÉSOUDRE par un humain avec le plan des 612 champs. Ne pas en ajouter.
_FANTOMES_CONNUS = {
    "Case à cocher P1 urgence",
    "Case à cocher P2 contact courrier",
    "Case à cocher P2 contact email",
    "Case à cocher P2 contact tel",
    "Champ de texte P3 NSS Parent",
    "Champ de texte P4 enfants",
    "Champ de texte P5 frais",
    "Champ de texte P5 ressources",
}

_RE_CHAMP = re.compile(
    r'"(Case à cocher [^"{}]+|Champ de texte [^"{}]+|Date P[^"{}]+'
    r'|N° SS [^"{}]+|REPRESENTANT [^"{}]+)"'
)


def run() -> bool:
    res: dict[str, bool] = {}

    real = set((PdfReader(str(_TEMPLATE)).get_fields() or {}).keys())
    real_rstrip = {r.rstrip() for r in real}
    res["QA-GHOST-1 — template = 612 champs"] = len(real) == 612

    src = _FILLER.read_text(encoding="utf-8")
    cites = sorted({m for m in _RE_CHAMP.findall(src) if "{" not in m})
    ghosts = {c for c in cites if c not in real and c.rstrip() not in real_rstrip}

    nouveaux = ghosts - _FANTOMES_CONNUS
    res["QA-GHOST-2 — aucun champ fantôme nouveau"] = not nouveaux

    print("=" * 64)
    print("  QA-GHOST — Audit anti-champ-fantôme")
    print("=" * 64)
    print()
    print(f"  Champs réels (PDF)      : {len(real)}")
    print(f"  Champs cités (filler)   : {len(cites)}")
    print(f"  Fantômes connus         : {len(_FANTOMES_CONNUS)}")
    print(f"  Fantômes actuels        : {len(ghosts)}")
    if nouveaux:
        print(f"  ⚠️  NOUVEAUX fantômes    : {sorted(nouveaux)}")
    print()
    ok = True
    for label, passed in res.items():
        print(f"     {'✅' if passed else '❌'} {label}")
        ok = ok and passed
    print()
    print("=" * 64)
    print(f"  DÉCISION QA-GHOST : {'✅ PASS' if ok else '❌ FAIL'} ({sum(res.values())}/{len(res)})")
    print("=" * 64)
    return ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
