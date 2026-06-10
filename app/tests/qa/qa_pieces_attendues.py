"""
app/tests/qa/qa_pieces_attendues.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-PIECES-1→5 — Étape 3 (doctrine) : complétude des pièces.

« Un dossier complet ne se fait pas refuser sur la forme. » La revue remonte au
professionnel toute pièce OBLIGATOIRE manquante (GEVASco scolaire, identité,
domicile, pièces par droit), tant qu'elle est corrigeable. Le certificat médical
(< 1 an) est déjà contrôlé par ailleurs.

  QA-PIECES-1 : enfant → la revue réclame le GEVASco (niveau ROUGE).
  QA-PIECES-2 : adulte → la revue réclame identité + justificatif de domicile.
  QA-PIECES-3 : le certificat n'est PAS dupliqué dans la liste « pièce à joindre ».
  QA-PIECES-4 : justificatifs_engine — certificat libellé « moins d'un an » (doctrine).
  QA-PIECES-5 : non-régression — les pièces réclamées sont bien OBLIGATOIRES.

Usage : python -m app.tests.qa.qa_pieces_attendues
"""

from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.engines.justificatifs_engine import justificatifs_requis
from app.engines.revue_instructeur import controles_coherence


def _labels(donnees: dict, profil: str) -> str:
    return " || ".join(a.get("label", "") for a in controles_coherence(donnees, profil))


def run() -> bool:
    res: dict[str, bool] = {}

    enfant = {"nom_prenom": "PETIT Léo", "date_naissance": "01/01/2015",
              "droits_demandes": "AEEH", "situation_scolaire": "ULIS"}
    adulte = {"nom_prenom": "DURAND Marie", "date_naissance": "01/01/1985",
              "droits_demandes": "AAH"}

    al_enf = _labels(enfant, "enfant")
    al_ad = _labels(adulte, "adulte")

    res["QA-PIECES-1 — GEVASco réclamé (enfant)"] = (
        "GEVASCO" in al_enf.upper() and "Pièce obligatoire à joindre" in al_enf
    )
    res["QA-PIECES-2 — identité + domicile réclamés (adulte)"] = (
        "identité" in al_ad.lower() and "domicile" in al_ad.lower()
    )
    # Le certificat est traité par le contrôle de fraîcheur, pas par la liste « à joindre »
    res["QA-PIECES-3 — certificat non dupliqué dans 'pièce à joindre'"] = (
        "Pièce obligatoire à joindre : Certificat" not in al_ad
    )

    # Vérif limitée au CERTIFICAT (le domicile reste légitimement « < 3 mois »).
    certs = [j.nom for j in justificatifs_requis(adulte, "adulte") if "certificat" in j.nom.lower()]
    res["QA-PIECES-4 — certificat libellé « moins d'un an »"] = (
        bool(certs)
        and all("moins d'un an" in c.lower() for c in certs)
        and not any("3 mois" in c.lower() for c in certs)
    )

    res["QA-PIECES-5 — pièces réclamées = obligatoires"] = all(
        j.obligatoire for j in justificatifs_requis(enfant, "enfant")
        if j.nom in ("Certificat médical de moins d'un an",
                     "GEVASCO (Groupe d'Évaluation des Volets Administratifs Scolaires)")
    )

    print("=" * 64)
    print("  QA-PIECES-1→5 — Complétude des pièces (Étape 3)")
    print("=" * 64)
    print()
    ok = True
    for label, passed in res.items():
        print(f"     {'✅' if passed else '❌'} {label}")
        ok = ok and passed
    print()
    print("=" * 64)
    print(f"  DÉCISION QA-PIECES : {'✅ PASS' if ok else '❌ FAIL'} ({sum(res.values())}/{len(res)})")
    print("=" * 64)
    return ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
