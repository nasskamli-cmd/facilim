"""
app/tests/qa/qa_validation_1_test4.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-VALIDATION-1-TEST4 — Reproduction de la rupture du dossier FAC-DOS-VKSP2HXQ

Rupture prouvée (cf. VALIDATION_1_TEST4_FAILURE_AUDIT.md) :
  Un dossier seulement PRÉ-REMPLI à la création (notes_pro + identité, AUCUN
  contenu réellement collecté) est jugé « narratif exploitable » dès la création,
  ce qui termine la collecte au 1ᵉʳ message WhatsApp (« oui »).

Ce test cible le prédicat exact `_dossier_narratif_exploitable`.

  Cas A (rupture) : pré-rempli /initiate (notes_pro + nom + ddn, sans collecte)
                    → ATTENDU APRÈS CORRECTIF : NON exploitable (collecte continue)
  Cas B (non-rég) : contenu réellement collecté (impact_quotidien/diagnostics)
                    → exploitable = True (le flux normal de fin fonctionne)
  Cas C (asymétrie) : notes_pro ne contribue pas au score de complétude

Usage : python -m app.tests.qa.qa_validation_1_test4
"""

from __future__ import annotations

import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./mdph_dossiers.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-key-32-chars-minimum-length-aaaa")
os.environ.setdefault("WHATSAPP_API_TOKEN", "test")
os.environ.setdefault("WHATSAPP_PHONE_NUMBER_ID", "test")
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy-key-for-tests-0000000000")
sys.path.insert(0, ".")

from app.engines.orchestration_engine import _dossier_narratif_exploitable, _calculer_completude_live


def main():
    sep = "═" * 64
    print(sep); print("  QA-VALIDATION-1-TEST4 — Rupture FAC-DOS-VKSP2HXQ"); print(sep)

    # Cas A — dossier pré-rempli comme /initiate (réévaluation + notes collées),
    # AUCUN contenu réellement collecté en conversation.
    dossier_initie = {
        "telephone": "0642087770",
        "email": "karim@example.fr",
        "departement": "13",
        "type_dossier": "REEVALUATION",
        "nom_prenom": "NAIT ALI Karim",
        "date_naissance": "1969-12-05",
        "notes_pro": "Bilan PCR : anxiété, troubles du sommeil, douleurs. Accident de travail : chute.",
    }
    exploitable_A = _dossier_narratif_exploitable(dossier_initie)

    # Cas B — contenu RÉELLEMENT collecté (doit rester exploitable)
    dossier_collecte = dict(dossier_initie)
    dossier_collecte["impact_quotidien"] = "Ne peut rester debout plus de 15 min, aide pour s'habiller."
    dossier_collecte["diagnostics"] = "Lombalgie chronique post-AT, troubles anxieux."
    exploitable_B = _dossier_narratif_exploitable(dossier_collecte)

    # Cas C — asymétrie : notes_pro ne compte pas dans le score
    score_sans_notes = _calculer_completude_live({k: v for k, v in dossier_initie.items() if k != "notes_pro"})
    score_avec_notes = _calculer_completude_live(dossier_initie)

    checks = {
        "Cas A — pré-rempli seul → NON exploitable (collecte continue)": (exploitable_A is False),
        "Cas B — contenu collecté → exploitable (fin normale OK)":        (exploitable_B is True),
        "Cas C — notes_pro n'augmente pas la complétude":                (score_sans_notes == score_avec_notes),
    }

    print(f"\n  exploitable(pré-rempli seul) = {exploitable_A}   (attendu False après correctif)")
    print(f"  exploitable(contenu collecté) = {exploitable_B}   (attendu True)")
    print(f"  score sans notes_pro = {score_sans_notes} | avec notes_pro = {score_avec_notes}\n")
    for label, ok in checks.items():
        print(f"     {'✅' if ok else '❌'} {label}")

    ok = all(checks.values())
    print(f"\n{sep}")
    print(f"  DÉCISION QA-VALIDATION-1-TEST4 : {'✅ PASS' if ok else '❌ FAIL (rupture présente)'}")
    print(sep)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
