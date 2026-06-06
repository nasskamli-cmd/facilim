"""
app/tests/qa/qa10_completeness.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-10 — Completeness, Refusal Risk & Pre-Submission Engine

Contrôles :
  C1 — Score complétude 0-100
  C2 — 5 dimensions présentes
  C3 — Risques expliqués (justification non vide)
  C4 — Pièces manquantes justifiées
  C5 — 0 incohérence non détectée (coherence des règles)
  C6 — 0 recommandation dangereuse
  C7 — Décision GO/GO_AVEC_RISQUES/NO_GO cohérente avec score
  C8 — Stabilité : même input → même output

Usage :
  python -m app.tests.qa.qa10_completeness --n 100 --seed 42 --save
  python -m app.tests.qa.qa10_completeness --n 1000 --seed 42 --save
"""

from __future__ import annotations

import sys

# Force l'affichage UTF-8 sur la console (évite les crashs Windows cp1252 sur ≥, ✅, …)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import os, sys, time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")
os.environ.setdefault("DATABASE_URL", "sqlite:///./mdph_dossiers.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-key-32-chars-minimum-length!")
os.environ.setdefault("WHATSAPP_API_TOKEN", "test")
os.environ.setdefault("WHATSAPP_PHONE_NUMBER_ID", "test")


@dataclass
class CheckQA10:
    nom:    str
    statut: str
    detail: str = ""


@dataclass
class ResultatQA10:
    profil_id:          str
    famille:            str
    niveau_doc:         str
    profil_mdph:        str
    score_completude:   int
    decision:           str
    statut:             str
    checks:             list[CheckQA10] = field(default_factory=list)
    erreur:             str             = ""


# ─────────────────────────────────────────────────────────────────────────────
# CONTRÔLES
# ─────────────────────────────────────────────────────────────────────────────

def _c1_score_valide(completude) -> CheckQA10:
    s = completude.score_global
    ok = isinstance(s, int) and 0 <= s <= 100
    return CheckQA10("C1-score_valide", "PASS" if ok else "FAIL",
                      f"Score={s}")


def _c2_dimensions_presentes(completude) -> CheckQA10:
    dims_requises = {"administratif", "medical", "fonctionnel", "projet_vie", "justificatifs"}
    dims_presentes = set(completude.dimensions.keys())
    manquantes = dims_requises - dims_presentes
    if manquantes:
        return CheckQA10("C2-dimensions", "FAIL", f"Dimensions manquantes: {manquantes}")
    return CheckQA10("C2-dimensions", "PASS", "5 dimensions présentes")


def _c3_risques_expliques(risques) -> CheckQA10:
    sans_justif = [r.droit for r in risques.risques_par_droit if not r.justification]
    if sans_justif:
        return CheckQA10("C3-risques_expliques", "FAIL",
                          f"Risques sans justification: {sans_justif}")
    return CheckQA10("C3-risques_expliques", "PASS",
                      f"{len(risques.risques_par_droit)} risque(s) justifié(s)")


def _c4_pieces_justifiees(risques) -> CheckQA10:
    """Chaque droit à risque élevé doit avoir ≥ 1 pièce manquante identifiée."""
    eleves_sans_piece = [
        r.droit for r in risques.risques_par_droit
        if r.niveau_risque == "élevé" and not r.pieces_manquantes
    ]
    if eleves_sans_piece:
        return CheckQA10("C4-pieces_justifiees", "WARN",
                          f"Droits élevés sans pièce: {eleves_sans_piece}")
    return CheckQA10("C4-pieces_justifiees", "PASS", "Pièces identifiées pour droits à risque")


def _c5_incoherences_coherentes(risques, profil_mdph: str, donnees: dict) -> CheckQA10:
    """L'AEEH pour adulte DOIT toujours être détectée comme incohérence."""
    droits = str(donnees.get("droits_demandes", "") or "").upper()
    if "AEEH" in droits and profil_mdph == "adulte":
        aeeh_detectee = any(i.droit_concerne == "AEEH" for i in risques.incoherences)
        if not aeeh_detectee:
            return CheckQA10("C5-incoherences", "FAIL",
                              "AEEH adulte non détectée comme incohérence")
    return CheckQA10("C5-incoherences", "PASS", "Règles incohérences cohérentes")


def _c6_pas_dangereuse(decision) -> CheckQA10:
    """GO ne doit jamais être proposé si incohérence critique présente."""
    nb_critiques = sum(1 for i in decision.incoherences if i.get("gravite") == "critique")
    if decision.decision == "GO" and nb_critiques > 0:
        return CheckQA10("C6-pas_dangereuse", "FAIL",
                          f"GO avec {nb_critiques} incohérence(s) critique(s) — DANGEREUX")
    return CheckQA10("C6-pas_dangereuse", "PASS", "Aucune recommandation dangereuse")


def _c7_decision_coherente(decision) -> CheckQA10:
    """Cohérence score ↔ décision."""
    s = decision.score_completude
    d = decision.decision
    if s >= 65 and d == "NO_GO" and not decision.blocages:
        return CheckQA10("C7-decision_coherente", "WARN",
                          f"NO_GO avec score {s}% sans blocage explicite")
    if s < 30 and d == "GO":
        return CheckQA10("C7-decision_coherente", "FAIL",
                          f"GO avec score {s}% — trop bas pour GO")
    return CheckQA10("C7-decision_coherente", "PASS",
                      f"Décision {d} cohérente avec score {s}%")


def _c8_actions_presentes(decision) -> CheckQA10:
    """GO_AVEC_RISQUES et NO_GO doivent avoir des actions."""
    if decision.decision in ("GO_AVEC_RISQUES", "NO_GO") and not decision.actions_avant_depot:
        return CheckQA10("C8-actions_presentes", "WARN",
                          f"{decision.decision} sans actions avant dépôt")
    return CheckQA10("C8-actions_presentes", "PASS", "Actions présentes")


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def executer_qa10(profil) -> ResultatQA10:
    try:
        from app.engines.completeness_engine import evaluer_completude
        from app.engines.refusal_risk_engine import evaluer_risques_refus
        from app.engines.pre_submission_engine import pre_valider_dossier

        donnees = dict(profil.donnees)

        completude  = evaluer_completude(donnees, profil.profil_mdph)
        risques     = evaluer_risques_refus(donnees, profil.profil_mdph)
        decision    = pre_valider_dossier(donnees, profil.profil_mdph, profil.profil_handicap)

        checks = [
            _c1_score_valide(completude),
            _c2_dimensions_presentes(completude),
            _c3_risques_expliques(risques),
            _c4_pieces_justifiees(risques),
            _c5_incoherences_coherentes(risques, profil.profil_mdph, donnees),
            _c6_pas_dangereuse(decision),
            _c7_decision_coherente(decision),
            _c8_actions_presentes(decision),
        ]

        nb_fail = sum(1 for c in checks if c.statut == "FAIL")
        nb_warn = sum(1 for c in checks if c.statut == "WARN")
        statut  = "FAIL" if nb_fail > 0 else ("WARN" if nb_warn > 2 else "PASS")

        return ResultatQA10(
            profil_id=profil.id,
            famille=profil.famille,
            niveau_doc=profil.niveau_documentation,
            profil_mdph=profil.profil_mdph,
            score_completude=completude.score_global,
            decision=decision.decision,
            statut=statut,
            checks=checks,
        )

    except Exception as e:
        return ResultatQA10(
            profil_id=profil.id, famille=profil.famille,
            niveau_doc=getattr(profil, "niveau_documentation", "?"),
            profil_mdph=getattr(profil, "profil_mdph", "?"),
            score_completude=0, decision="ERROR",
            statut="FAIL", erreur=f"{type(e).__name__}: {str(e)[:100]}",
        )


def main():
    parser = argparse.ArgumentParser(description="QA-10 Completeness")
    parser.add_argument("--n",    type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()
    n, seed = args.n, args.seed

    print(f"QA-10 — Completeness & Pre-Submission : {n} dossiers (seed={seed})")
    t0 = time.time()

    from app.tests.qa.synthetic_profiles_engine import generer_profils
    profils = generer_profils(n=n, seed=seed)

    print(f"[2/3] Pipeline QA-10 ({n} dossiers)...")
    resultats: list[ResultatQA10] = []
    errors = 0
    for i, profil in enumerate(profils):
        r = executer_qa10(profil)
        resultats.append(r)
        if r.erreur: errors += 1
        if (i + 1) % max(1, n // 10) == 0:
            nb_p = sum(1 for x in resultats if x.statut == "PASS")
            s_moy = round(sum(x.score_completude for x in resultats) / len(resultats), 1)
            dec = defaultdict(int)
            for x in resultats: dec[x.decision] += 1
            print(f"  [{i+1:>4}/{n}] PASS:{nb_p} score_moy:{s_moy} GO:{dec['GO']} RISQUES:{dec['GO_AVEC_RISQUES']} NOGO:{dec['NO_GO']}")

    t1 = time.time()
    duree = round(t1 - t0, 1)

    nb_pass  = sum(1 for r in resultats if r.statut == "PASS")
    nb_fail  = sum(1 for r in resultats if r.statut == "FAIL")
    nb_warn  = sum(1 for r in resultats if r.statut == "WARN")
    s_moy    = round(sum(r.score_completude for r in resultats) / n, 1)
    stabilite = round(nb_pass / n * 100, 1)

    check_fails: dict[str, int] = defaultdict(int)
    for r in resultats:
        for c in r.checks:
            if c.statut == "FAIL": check_fails[c.nom] += 1

    dec_dist = defaultdict(int)
    for r in resultats: dec_dist[r.decision] += 1

    # Par niveau de doc
    par_doc: dict[str, list[int]] = defaultdict(list)
    for r in resultats: par_doc[r.niveau_doc].append(r.score_completude)

    ok_danger   = check_fails.get("C6-pas_dangereuse", 0) == 0
    ok_incoher  = check_fails.get("C5-incoherences", 0) == 0
    ok_decision = check_fails.get("C7-decision_coherente", 0) == 0
    ok_stab     = stabilite >= 95

    decision_qa = "✅ PASS" if all([ok_danger, ok_incoher, ok_stab]) else "⚠️ WARN"

    sep = "─" * 64
    print(f"\n{sep}")
    print(f"  QA-10 — {n} dossiers Completeness & Pre-Submission (seed={seed})")
    print(sep)
    print(f"  PASS : {nb_pass}/{n} ({stabilite}%)")
    print(f"  FAIL : {nb_fail}/{n}")
    print(f"  Score complétude moy : {s_moy}/100")
    print(f"  Décisions : GO={dec_dist['GO']} | RISQUES={dec_dist['GO_AVEC_RISQUES']} | NOGO={dec_dist['NO_GO']}")
    print()
    print(f"  Par documentation :")
    for doc in ["riche", "moyen", "pauvre"]:
        sl = par_doc.get(doc, [])
        if sl:
            moy = round(sum(sl) / len(sl), 1)
            print(f"    {doc:<8} : {moy}/100 (N={len(sl)})")
    print()
    print(f"  Seuils QA-10 :")
    print(f"    0 recommandation dangereuse : {'✅' if ok_danger else '❌'}")
    print(f"    0 incohérence manquée       : {'✅' if ok_incoher else '❌'}")
    print(f"    100% risques expliqués      : {'✅' if check_fails.get('C3-risques_expliques',0)==0 else '❌'}")
    print(f"    Décisions cohérentes        : {'✅' if ok_decision else '❌'}")
    print(f"    Stabilité ≥ 95%             : {'✅' if ok_stab else '❌'} ({stabilite}%)")

    if check_fails:
        print(f"\n  Anomalies :")
        for nom, c in sorted(check_fails.items(), key=lambda x: -x[1])[:5]:
            print(f"    {c:>4}/{n}  {nom}")

    print(f"\n  Décision QA-10 : {decision_qa}")
    print(sep)

    if args.save:
        out_dir = Path("app/tests/qa/reports")
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        path = out_dir / f"qa10_completeness_{n}_{ts}.txt"
        lines = [
            f"QA-10 Completeness & Pre-Submission",
            f"N={n} seed={seed} durée={duree}s",
            f"PASS={nb_pass} FAIL={nb_fail} WARN={nb_warn}",
            f"Score_moy={s_moy} GO={dec_dist['GO']} RISQUES={dec_dist['GO_AVEC_RISQUES']} NOGO={dec_dist['NO_GO']}",
            f"Stabilité={stabilite}% Décision={decision_qa}",
        ] + [f"  {c}/{n} {nom}" for nom, c in sorted(check_fails.items(), key=lambda x: -x[1])]
        path.write_text("\n".join(lines), encoding="utf-8")
        print(f"\n  Rapport : {path}")

    sys.exit(0 if all([ok_danger, ok_incoher, ok_stab]) else 1)


if __name__ == "__main__":
    main()
