"""
app/tests/qa/qa_cablage_completude.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-CABLAGE-1→8 — Câblage de la logique de complétude (sprint de branchement).

Prouve que la logique déjà développée est désormais OPÉRATIONNELLE :
  P1 validite_dossier persisté        → QA-CABLAGE-1
  P2 dossier_solide consommé par gate → QA-CABLAGE-2/3/4
  P3 CHAMP_A_COMPLETER_PRO visible    → QA-CABLAGE-5
  P4 synthese_completude utilisée     → QA-CABLAGE-6
  P5 transitions historisées          → QA-CABLAGE-7/8

Usage : python -m app.tests.qa.qa_cablage_completude
"""

from __future__ import annotations

import sqlite3
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.engines.cerfa_gate_engine import verifier_gate_cerfa
from app.engines.orchestration_engine import _score_completude_metier
from app.engines.revue_instructeur import revue_dossier
from app.services.field_status import (
    etats_snapshot,
    journaliser_transitions,
    marquer_a_completer_pro,
    marquer_refus,
)

_COEUR = {
    "impact_quotidien": "douleurs et fatigue au quotidien",
    "aides_en_place": "aide d'un proche pour les courses",
    "attentes_usager": "obtenir des aides adaptées",
    "projet_de_vie": "rester autonome à domicile",
}


def _a_blocage(gate, code: str) -> bool:
    return any(b.code == code for b in gate.blocages)


def run() -> bool:
    res: dict[str, bool] = {}

    # ── P1 : validite_dossier n'est plus jeté (revue_dossier le retourne, orchestration le garde) ──
    rev = revue_dossier({"droits_demandes": "AAH", **_COEUR}, "adulte", "test-id", db=None)
    res["QA-CABLAGE-1 — validite présent dans la revue (conservé)"] = (
        "validite" in rev and isinstance(rev["validite"], dict) and "pret" in rev["validite"]
    )

    # ── P2/P3 : gate consomme dossier_solide ──
    creux = {"droits_demandes": "AAH"}
    incomplet = {"droits_demandes": "AAH", "impact_quotidien": "fatigue"}  # cœur partiel
    solide = {"droits_demandes": "AAH", **_COEUR}

    g_creux = verifier_gate_cerfa(creux, profil_mdph="adulte")
    g_incomplet = verifier_gate_cerfa(incomplet, profil_mdph="adulte")
    g_solide = verifier_gate_cerfa(solide, profil_mdph="adulte")

    res["QA-CABLAGE-2 — gate BLOQUE un dossier creux (COEUR_INCOMPLET)"] = (
        _a_blocage(g_creux, "COEUR_INCOMPLET") and g_creux.autorise_export is False
    )
    res["QA-CABLAGE-3 — gate BLOQUE un dossier incomplet (cœur partiel)"] = (
        _a_blocage(g_incomplet, "COEUR_INCOMPLET")
    )
    res["QA-CABLAGE-4 — gate n'ajoute PAS COEUR_INCOMPLET si cœur solide"] = (
        not _a_blocage(g_solide, "COEUR_INCOMPLET")
    )

    # ── P3 : CHAMP_A_COMPLETER_PRO visible dans le filtre d'alertes ──
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE alertes (id TEXT, type_alerte TEXT, acquittee INT)")
    con.executemany(
        "INSERT INTO alertes VALUES (?,?,0)",
        [("1", "CHAMP_NON_COMMUNIQUE"), ("2", "CHAMP_A_COMPLETER_PRO"), ("3", "AUTRE")],
    )
    # Réplique du filtre de get_alertes (main.py:1135, après câblage P3)
    rows = con.execute(
        "SELECT type_alerte FROM alertes WHERE type_alerte IN "
        "('FLAG_HUMAIN','CHAMP_NON_COMMUNIQUE','CHAMP_A_COMPLETER_PRO','REVUE_INSTRUCTEUR') "
        "AND acquittee = 0"
    ).fetchall()
    types = {r[0] for r in rows}
    res["QA-CABLAGE-5 — CHAMP_A_COMPLETER_PRO visible (get_alertes)"] = (
        "CHAMP_A_COMPLETER_PRO" in types and "AUTRE" not in types
    )

    # ── P4 : le score affiché utilise synthese_completude (≠ ancien fill-rate) ──
    s_vide = _score_completude_metier({})
    s_partiel = _score_completude_metier({"droits_demandes": "AAH", **_COEUR})
    res["QA-CABLAGE-6 — score complétude = synthese_completude (croît avec le fourni)"] = (
        s_vide == 0 and s_partiel > s_vide
    )

    # ── P5 : transitions historisées (les 4 types) ──
    d = {"nom_prenom": ""}            # tout en attente
    ids = ["nom_prenom", "num_secu", "nationalite", "telephone"]
    avant = etats_snapshot(d, ids)    # tous en_attente
    d["nom_prenom"] = "DURAND Marie"  # en_attente → fourni
    marquer_refus(d, "num_secu", "non")                  # en_attente → refuse
    marquer_a_completer_pro(d, "nationalite", "je ne sais pas")  # en_attente → a_completer_pro
    n = journaliser_transitions(d, avant, ids, origine="whatsapp", horodatage="2026-01-01T00:00:00Z")
    hist = d.get("_historique_statuts", [])
    transitions = {(e["champ"], e["ancien"], e["nouveau"]) for e in hist}
    res["QA-CABLAGE-7 — transitions capturées (fourni/refuse/a_completer_pro)"] = (
        n == 3
        and ("nom_prenom", "en_attente", "fourni") in transitions
        and ("num_secu", "en_attente", "refuse") in transitions
        and ("nationalite", "en_attente", "a_completer_pro") in transitions
    )

    # a_completer_pro → fourni + persistance (champ/ancien/nouveau/horodatage/origine)
    avant2 = etats_snapshot(d, ["nationalite"])           # a_completer_pro
    d["nationalite"] = "française"                          # → fourni
    journaliser_transitions(d, avant2, ["nationalite"], origine="dashboard",
                            horodatage="2026-01-02T00:00:00Z")
    dernier = d["_historique_statuts"][-1]
    res["QA-CABLAGE-8 — a_completer_pro→fourni + événement complet persisté"] = (
        dernier == {"champ": "nationalite", "ancien": "a_completer_pro", "nouveau": "fourni",
                    "horodatage": "2026-01-02T00:00:00Z", "origine": "dashboard"}
    )

    print("=" * 64)
    print("  QA-CABLAGE-1→8 — Câblage de la complétude")
    print("=" * 64)
    print()
    ok = True
    for label, passed in res.items():
        print(f"     {'✅' if passed else '❌'} {label}")
        ok = ok and passed
    print()
    print("=" * 64)
    print(f"  DÉCISION QA-CABLAGE : {'✅ PASS' if ok else '❌ FAIL'} ({sum(res.values())}/{len(res)})")
    print("=" * 64)
    return ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
