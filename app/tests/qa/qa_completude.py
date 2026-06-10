"""
app/tests/qa/qa_completude.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-COMPL-1→8 — Complétude différenciée (sans vider les exigences).

Décision métier : améliorer la COMPLÉTUDE, pas accélérer artificiellement
is_complete. On distingue 5 états par champ — complet / en_attente / à compléter
par pro / refusé / non applicable — et un dossier creux ne passe JAMAIS « prêt ».

  QA-COMPL-1 : les 5 états sont distingués (etat_par_champ).
  QA-COMPL-2 : un champ « à compléter par pro » n'est plus reposé à l'usager
               (hors missing_fields) MAIS reste exigé/visible.
  QA-COMPL-3 : champs refusés ET délégués restent VISIBLES dans points_d_attention.
  QA-COMPL-4 : dossier_solide = False si le cœur est vide/délégué, True si fourni.
  QA-COMPL-5 : un dossier creux (une demande, rien d'autre) n'est PAS « prêt ».
  QA-COMPL-6 : « je ne sais pas » détecté et distinct d'un refus / d'une vraie réponse.
  QA-COMPL-7 : les exigences ne sont PAS vidées (champs admin toujours requis).
  QA-COMPL-8 : une valeur fournie reprend le dessus sur un marquage « à compléter pro ».

Usage : python -m app.tests.qa.qa_completude
"""

from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.engines.revue_instructeur import points_d_attention, validite_dossier
from app.services.conversation.router import get_agent
from app.services.field_status import (
    marquer_a_completer_pro,
    marquer_refus,
    phrase_de_refus,
    phrase_ne_sait_pas,
)

_COEUR = {
    "impact_quotidien": "douleurs et fatigue au quotidien",
    "aides_en_place": "aide d'un proche pour les courses",
    "attentes_usager": "obtenir des aides adaptées",
    "projet_de_vie": "rester autonome à domicile",
}


def run() -> bool:
    res: dict[str, bool] = {}
    ag = get_agent("adulte")

    # QA-COMPL-1 : 5 états distingués
    d = {"nom_prenom": "DURAND Marie"}          # fourni : nom_prenom
    marquer_refus(d, "num_secu", "non")          # refus
    marquer_a_completer_pro(d, "nationalite", "je ne sais pas")  # délégué
    etats = {e["id"]: e["etat"] for e in ag.etat_par_champ(d)}
    res["QA-COMPL-1 — 5 états distingués"] = (
        etats.get("nom_prenom") == "fourni"
        and etats.get("num_secu") == "refuse"
        and etats.get("nationalite") == "a_completer_pro"
        and etats.get("date_naissance") == "en_attente"
    )

    # QA-COMPL-2 : délégué pro hors missing_fields, mais toujours exigé
    miss_ids = ag.missing_field_ids(d)
    res["QA-COMPL-2 — délégué pro non reposé mais exigé"] = (
        "nationalite" not in miss_ids       # plus reposé à l'usager
        and "num_secu" not in miss_ids      # refusé non reposé
        and "date_naissance" in miss_ids    # en attente toujours posé
    )

    # QA-COMPL-3 : refusé + délégué restent VISIBLES (points_d_attention)
    pts = {p["id"]: p["etat"] for p in points_d_attention(d, "adulte")}
    res["QA-COMPL-3 — refusé/délégué restent visibles"] = (
        pts.get("num_secu") == "refuse" and pts.get("nationalite") == "a_completer_pro"
    )

    # QA-COMPL-4 : dossier_solide
    creux = {"droits_demandes": "AAH"}
    solide = {"droits_demandes": "AAH", **_COEUR}
    delegue_coeur = {"droits_demandes": "AAH", **_COEUR}
    marquer_a_completer_pro(delegue_coeur, "projet_de_vie", "je ne sais pas")
    delegue_coeur["projet_de_vie"] = ""  # délégué, vide
    res["QA-COMPL-4 — dossier_solide vide/délégué=False, fourni=True"] = (
        ag.dossier_solide(creux) is False
        and ag.dossier_solide(solide) is True
        and ag.dossier_solide(delegue_coeur) is False
    )

    # QA-COMPL-5 : dossier creux PAS prêt (critère de validation)
    res["QA-COMPL-5 — dossier creux pas prêt"] = validite_dossier(creux, "adulte")["pret"] is False

    # QA-COMPL-6 : détection « je ne sais pas » distincte
    res["QA-COMPL-6 — « je ne sais pas » détecté et distinct"] = (
        phrase_ne_sait_pas("je ne sais pas trop, désolé") is True
        and phrase_ne_sait_pas("oui, c'est l'AAH") is False
        and phrase_de_refus("je ne sais pas") is False   # pas un refus
    )

    # QA-COMPL-7 : exigences non vidées — champs admin toujours requis
    ids_requis = {it["id"] for it in ag.CHECKLIST if it.get("requis")}
    res["QA-COMPL-7 — exigences non vidées"] = {
        "nationalite", "organisme_payeur", "preference_contact",
        "commune_naissance", "frais_handicap",
    }.issubset(ids_requis)

    # QA-COMPL-8 : une valeur fournie reprend le dessus sur « à compléter pro »
    d8 = {}
    marquer_a_completer_pro(d8, "nationalite", "je ne sais pas")
    d8["nationalite"] = "française"
    etats8 = {e["id"]: e["etat"] for e in ag.etat_par_champ(d8)}
    res["QA-COMPL-8 — valeur fournie prime sur délégation"] = etats8.get("nationalite") == "fourni"

    # QA-COMPL-9 : conditionnels — posés seulement si pertinent.
    sans_emploi = ag.missing_field_ids({"situation_professionnelle": "sans_activite"})
    en_emploi = ag.missing_field_ids({"situation_professionnelle": "emploi"})
    sans_projet = ag.missing_field_ids({})
    avec_projet = ag.missing_field_ids({"projet_professionnel": "reconversion"})
    res["QA-COMPL-9 — conditionnels posés seulement si pertinent"] = (
        "consequences_professionnelles" not in sans_emploi          # pas d'emploi → non posé
        and "consequences_professionnelles" in en_emploi            # en emploi → posé
        and "emploi_accompagne" not in sans_projet                  # pas de projet → non posé
        and "emploi_accompagne" in avec_projet                      # projet → posé
    )

    print("=" * 64)
    print("  QA-COMPL-1→8 — Complétude différenciée")
    print("=" * 64)
    print()
    ok = True
    for label, passed in res.items():
        print(f"     {'✅' if passed else '❌'} {label}")
        ok = ok and passed
    print()
    print("=" * 64)
    print(f"  DÉCISION QA-COMPL : {'✅ PASS' if ok else '❌ FAIL'} ({sum(res.values())}/{len(res)})")
    print("=" * 64)
    return ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
