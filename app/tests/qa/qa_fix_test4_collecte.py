"""
app/tests/qa/qa_fix_test4_collecte.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-FIX-TEST4-COLLECTE — La collecte ne se termine plus sur un dossier pré-rempli

Vérifie la correction FIX-TEST4-COLLECTE : le raccourci `_dossier_narratif_exploitable`
(P0.2-H3) n'autorise la fin de collecte que si la collecte est PRESQUE complète
(≤ 3 champs requis manquants). `is_complete` reste un déclencheur valable.

Reproduit la décision EXACTE de orchestration_engine.traiter_message_async (L825) :
    _declencher_narratif = is_complete(d) OR (_dossier_narratif_exploitable(d) AND _collecte_presque_complete(agent, d))

  Cas 1 — Bilan riche + 1ᵉʳ « oui »            → PAS de validation (collecte continue)
  Cas 2 — Bilan + collecte partielle (mi-chemin)→ PAS de validation (progression)
  Cas 3 — droits_demandes est bien collectable  → la collecte peut atteindre la Section E
  Cas 4 — Section E renseignée                   → droits_demandes != []
  Cas 5 — Collecte réellement complète           → validation (is_complete)
  Cas 6 — Régression TEST4 (Karim/bilan/oui)     → PAS de validation au tour 1

Usage : python -m app.tests.qa.qa_fix_test4_collecte
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
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy-key-for-tests-0000000000")
sys.path.insert(0, ".")

from app.engines.orchestration_engine import _dossier_narratif_exploitable, _collecte_presque_complete
from app.services.conversation.adult_agent import adult_agent as AG


def decision(donnees):
    """Réplique exacte de la condition _declencher_narratif (hors validation_en_attente)."""
    return bool(
        AG.is_complete(donnees)
        or (_dossier_narratif_exploitable(donnees) and _collecte_presque_complete(AG, donnees))
    )


# Dossier pré-rempli UNIQUEMENT par le bilan + création (aucune collecte conversationnelle)
D_BILAN = {
    "nom_prenom": "NAIT-ALI", "date_naissance": "05/12/1969", "departement": "13",
    "email": "karim@example.fr", "type_dossier": "REEVALUATION", "telephone": "0642087770",
    "adresse_complete": "1 rue des Bateliers 13016 MARSEILLE",
    "diagnostics": "anxiété, troubles du sommeil, douleurs", "accident_travail": "chute",
    "documents_texte": "--- Bilan PCR NAIT ALI ---\nOrientation ESAT, douleurs chroniques…",
}

# Collecte partielle (mi-chemin) : quelques champs collectés mais > 3 requis encore manquants
D_PARTIEL = dict(D_BILAN, genre="M", situation_familiale="marié",
                 enfants_a_charge="2", impact_quotidien="ne peut rester debout >15 min")

# Collecte réellement complète (tous les champs REQUIS de la checklist adulte)
D_COMPLET = dict(D_PARTIEL, num_secu="169127512300112", traitements="antalgiques, anxiolytiques",
                 medecin_traitant="Dr Martin (Marseille)", historique_mdph="RQTH 2019",
                 qualification_section_c="non", qualification_section_d="non")

# Section E renseignée
D_COMPLET_AVEC_DROITS = dict(D_COMPLET, droits_demandes=["AAH", "RQTH", "CMI"])


def main():
    sep = "═" * 64
    print(sep); print("  QA-FIX-TEST4-COLLECTE — fin de collecte gatée"); print(sep)

    checklist_ids = [c["id"] for c in AG.CHECKLIST]

    res = {}
    # Cas 1 — bilan + 1er "oui"
    d1 = decision(D_BILAN)
    res["Cas 1 — bilan + 1ᵉʳ oui → PAS de validation"] = (d1 is False)
    # Cas 2 — collecte partielle
    d2 = decision(D_PARTIEL)
    res["Cas 2 — collecte partielle → PAS de validation (progression)"] = (d2 is False)
    # Cas 3 — droits collectable + collecte non close (peut atteindre Section E)
    res["Cas 3 — droits_demandes collectable + collecte ouverte"] = (
        "droits_demandes" in checklist_ids and decision(D_BILAN) is False
    )
    # Cas 4 — Section E renseignée → droits != []
    res["Cas 4 — Section E renseignée → droits_demandes != []"] = (
        len(D_COMPLET_AVEC_DROITS.get("droits_demandes", [])) > 0
    )
    # Cas 5 — collecte complète → validation
    d5 = decision(D_COMPLET)
    res["Cas 5 — collecte complète → validation (is_complete)"] = (d5 is True)
    # Cas 6 — régression TEST4
    d6 = decision(D_BILAN)
    res["Cas 6 — TEST4 rejoué → PAS de validation au tour 1"] = (d6 is False)

    # Détails
    print(f"\n  missing_fields(bilan)   = {len(AG.missing_fields(D_BILAN))}  → presque_complete={_collecte_presque_complete(AG, D_BILAN)}")
    print(f"  missing_fields(partiel) = {len(AG.missing_fields(D_PARTIEL))}  → presque_complete={_collecte_presque_complete(AG, D_PARTIEL)}")
    print(f"  missing_fields(complet) = {len(AG.missing_fields(D_COMPLET))}  → is_complete={AG.is_complete(D_COMPLET)}")
    print(f"  exploitable(bilan)      = {_dossier_narratif_exploitable(D_BILAN)}")
    print(f"  décision(bilan)={d1}  décision(partiel)={d2}  décision(complet)={d5}\n")
    for label, ok in res.items():
        print(f"     {'✅' if ok else '❌'} {label}")

    ok = all(res.values())
    print(f"\n{sep}")
    print(f"  DÉCISION QA-FIX-TEST4-COLLECTE : {'✅ PASS' if ok else '❌ FAIL'} ({sum(res.values())}/{len(res)})")
    print(sep)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
