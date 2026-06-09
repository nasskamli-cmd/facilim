"""
app/tests/qa/qa_orientation_crp.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-CRP-1→6 — Orientation professionnelle ESRP/CRP (priorité 1 de la cartographie).

Spec : CARTOGRAPHIE_CERFA_15692.md, page 18 (E3) — « un ESRP est un centre de
rééducation professionnelle → cocher "orientation professionnelle" ET "CRP", plus
la RQTH. Jamais en scolarité. C'est l'erreur exacte du test (ESRP en scolarité,
aucune case d'orientation cochée). »

Bug reproduit : un ESRP nommé seulement dans le projet libre (« formation CADGA à
l'ESRP La Rose ») n'atteignait pas _mapper_droits → P18 5 (marché du travail)
coché à tort, P18 3 (CRP) jamais coché.

  QA-CRP-1 : _detecter_orientation_crp depuis le projet libre.
  QA-CRP-2 : _detecter_orientation_crp = False pour un projet « milieu ordinaire ».
  QA-CRP-3 : _mapper_droits(orientation_crp=True) → P18 2 + P18 3, pas P18 5.
  QA-CRP-4 : _mapper_droits ORP ordinaire (sans CRP) → P18 5, pas P18 3.
  QA-CRP-5 : exclusivité ESAT préservée → P18 4, jamais P18 3.
  QA-CRP-6 : bout-en-bout (remplir_cerfa) ESRP → P18 3 coché, P18 5 absent, pas de scolarité.

Usage : python -m app.tests.qa.qa_orientation_crp
"""

from __future__ import annotations

import io
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from services.cerfa_filler import _detecter_orientation_crp, _mapper_droits


def run() -> bool:
    res: dict[str, bool] = {}

    # ── QA-CRP-1 : détection depuis le projet libre ──
    res["QA-CRP-1 — détecte ESRP dans le projet libre"] = (
        _detecter_orientation_crp(False, "reconversion via une formation CADGA à l'ESRP La Rose") is True
        and _detecter_orientation_crp(False, "", "Centre de réadaptation professionnelle de Lyon") is True
        and _detecter_orientation_crp(True) is True  # champ structuré a_cible_esrp
    )

    # ── QA-CRP-2 : pas de faux positif sur un projet ordinaire ──
    res["QA-CRP-2 — pas de CRP pour un projet ordinaire"] = (
        _detecter_orientation_crp(False, "retour à l'emploi en milieu ordinaire, poste administratif") is False
    )

    # ── QA-CRP-3 : mapping avec orientation_crp=True → P18 2 + P18 3, pas P18 5 ──
    cases3 = _mapper_droits(
        ["RQTH", "orientation professionnelle"], is_enfant=False,
        besoins_aide_humaine=False, orientation_crp=True,
    )
    res["QA-CRP-3 — orientation_crp → P18 2+P18 3, pas P18 5"] = (
        "Case à cocher P18 1" in cases3       # RQTH
        and "Case à cocher P18 2" in cases3   # orientation pro (parente)
        and "Case à cocher P18 3" in cases3   # CRP
        and "Case à cocher P18 5" not in cases3  # PAS marché du travail
    )

    # ── QA-CRP-4 : ORP ordinaire (sans CRP) → P18 5, pas P18 3 ──
    cases4 = _mapper_droits(
        ["RQTH", "orientation professionnelle"], is_enfant=False,
        besoins_aide_humaine=False, orientation_crp=False,
    )
    res["QA-CRP-4 — ORP ordinaire → P18 5, pas P18 3"] = (
        "Case à cocher P18 5" in cases4
        and "Case à cocher P18 3" not in cases4
    )

    # ── QA-CRP-5 : ESAT exclusif → P18 4, jamais P18 3 ──
    cases5 = _mapper_droits(
        ["RQTH", "orientation professionnelle", "ESAT"], is_enfant=False,
        besoins_aide_humaine=False, orientation_crp=False,
    )
    res["QA-CRP-5 — ESAT → P18 4, jamais P18 3"] = (
        "Case à cocher P18 4" in cases5
        and "Case à cocher P18 3" not in cases5
    )

    # ── QA-CRP-6 : bout-en-bout via remplir_cerfa ──
    try:
        from app.engines.pdf.v2_bridge import synthese_to_v2_dossier
        from pypdf import PdfReader
        from services.cerfa_filler import remplir_cerfa

        synthese = {
            "nom_prenom": "NAIT ALI Karim", "date_naissance": "10/05/1994", "genre": "homme",
            "adresse_complete": "5 rue de la Paix 69003 Lyon", "departement": "69",
            "droits_demandes": "RQTH, orientation professionnelle",
            "projet_professionnel": "reconversion via une formation CADGA a l ESRP La Rose",
            "statut_emploi": "sans emploi depuis 12 mois",
        }
        dossier = synthese_to_v2_dossier(synthese, "adulte", "")
        pdf = remplir_cerfa(dossier)
        fields = PdfReader(io.BytesIO(pdf)).get_fields() or {}

        def coche(nom: str) -> bool:
            v = fields.get(nom, {}).get("/V")
            return bool(v) and str(v) not in ("/Off", "Off", "")

        scolarite = any(
            coche(n) for n in fields
            if any(p in n for p in ("P9 ", "P10", "P11", "P12"))
        )
        res["QA-CRP-6 — bout-en-bout ESRP (P18 3 ✓, P18 5 ✗, pas scolarité)"] = (
            coche("Case à cocher P18 3")
            and not coche("Case à cocher P18 5")
            and not scolarite
        )
    except Exception as e:  # pragma: no cover
        print(f"     ⚠️  QA-CRP-6 non exécuté (PDF) : {e}")
        res["QA-CRP-6 — bout-en-bout ESRP (P18 3 ✓, P18 5 ✗, pas scolarité)"] = False

    # ── Rapport ──
    print("=" * 64)
    print("  QA-CRP-1→6 — Orientation professionnelle ESRP/CRP")
    print("=" * 64)
    print()
    ok = True
    for label, passed in res.items():
        print(f"     {'✅' if passed else '❌'} {label}")
        ok = ok and passed
    print()
    print("=" * 64)
    print(f"  DÉCISION QA-CRP : {'✅ PASS' if ok else '❌ FAIL'} ({sum(res.values())}/{len(res)})")
    print("=" * 64)
    return ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
