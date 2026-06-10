"""
app/tests/qa/qa_cloisonnement_prescripteur.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-PRESC-1→5 — Cloisonnement du prescripteur (RGPD) à l'extraction documentaire.

Spec : CARTOGRAPHIE_CERFA_15692.md — « Cloisonnement du prescripteur. Le conseiller
(France Travail, etc.) figurant dans un bilan n'est jamais l'usager : ni dans
l'identité, ni dans un récit, ni nulle part. »

  QA-PRESC-1 : un item dont la VALEUR est un email est écarté (None).
  QA-PRESC-2 : un item dont la VALEUR est un téléphone FR est écarté (None).
  QA-PRESC-3 : un email/téléphone résiduel dans l'extrait_source est nettoyé,
               l'item fonctionnel légitime est conservé.
  QA-PRESC-4 : _construire_knowledge filtre les items « contact tiers » et garde
               les faits usager (bilan ESRP avec bloc conseiller France Travail).
  QA-PRESC-5 : aucune coordonnée (email/téléphone) ne subsiste dans le knowledge.

Usage : python -m app.tests.qa.qa_cloisonnement_prescripteur
"""

from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.engines.document_functional_extractor import (
    _RE_EMAIL,
    _RE_TEL,
    _construire_knowledge,
    _scrub_pii,
    cloisonner_prescripteur_item,
)


def run() -> bool:
    res: dict[str, bool] = {}

    # ── QA-PRESC-1 : valeur = email → écarté ──
    res["QA-PRESC-1 — valeur email écartée"] = (
        cloisonner_prescripteur_item("sophie.martin@francetravail.fr", "Conseiller référent") is None
    )

    # ── QA-PRESC-2 : valeur = téléphone → écarté ──
    out2 = cloisonner_prescripteur_item("06 12 34 56 78", "Tel conseiller")
    res["QA-PRESC-2 — valeur téléphone écartée"] = out2 is None

    # ── QA-PRESC-3 : email résiduel dans l'extrait nettoyé, item gardé ──
    out3 = cloisonner_prescripteur_item(
        "formation CADGA recommandée",
        "Projet validé par le conseiller jean.dupont@pole-emploi.fr en 2024",
    )
    res["QA-PRESC-3 — extrait nettoyé, fait gardé"] = (
        out3 is not None
        and out3[0] == "formation CADGA recommandée"
        and "@" not in out3[1]
        and "jean.dupont" not in out3[1]
    )

    # ── QA-PRESC-4 + 5 : extraction complète d'un bilan ESRP avec bloc prescripteur ──
    raw = {
        "date_document": "12/03/2024",
        "limitations_fonctionnelles": [
            {"valeur": "station debout prolongée difficile", "extrait_source": "ne peut rester debout longtemps"},
        ],
        "projets": [
            {"valeur": "orientation ESRP recommandée", "extrait_source": "orientation vers un ESRP préconisée"},
        ],
        # Fuites prescripteur que le garde-fou doit écarter / nettoyer :
        "verbatim": [
            {"valeur": "sophie.martin@francetravail.fr", "extrait_source": "Conseillère référente"},
            {"valeur": "Conseillère : S. Martin", "extrait_source": "contact : 01 23 45 67 89"},
        ],
        "ressources": [
            {"valeur": "motivation pour le projet", "extrait_source": "très motivée, suivie par jean@ft.fr"},
        ],
    }
    k = _construire_knowledge(raw, "Bilan ESRP La Rose.docx", "ESRP")

    # QA-PRESC-4 : faits usager conservés, items contact-tiers écartés
    verbatim_vals = [i.valeur for i in k.verbatim]
    res["QA-PRESC-4 — faits usager gardés, contacts écartés"] = (
        len(k.limitations_fonctionnelles) == 1
        and len(k.projets) == 1
        and "sophie.martin@francetravail.fr" not in verbatim_vals   # email écarté
        and "Conseillère : S. Martin" not in verbatim_vals          # tel dans extrait → écarté
        and len(k.ressources) == 1                                  # fait gardé...
    )

    # QA-PRESC-5 : zéro coordonnée résiduelle dans tout le knowledge
    blob = " ".join(
        f"{i.valeur} {i.extrait_source}"
        for champ in (
            "limitations_fonctionnelles", "restrictions_medicales", "besoins",
            "freins", "ressources", "projets", "verbatim", "chronologie",
        )
        for i in getattr(k, champ)
    )
    res["QA-PRESC-5 — zéro email/téléphone résiduel"] = (
        not _RE_EMAIL.search(blob) and not _RE_TEL.search(blob)
    )

    # ── Rapport ──
    print("=" * 64)
    print("  QA-PRESC-1→5 — Cloisonnement du prescripteur (RGPD)")
    print("=" * 64)
    print()
    ok = True
    for label, passed in res.items():
        print(f"     {'✅' if passed else '❌'} {label}")
        ok = ok and passed
    print()
    print("=" * 64)
    print(f"  DÉCISION QA-PRESC : {'✅ PASS' if ok else '❌ FAIL'} ({sum(res.values())}/{len(res)})")
    print("=" * 64)
    return ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
