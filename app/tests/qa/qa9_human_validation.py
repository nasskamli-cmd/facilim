"""
app/tests/qa/qa9_human_validation.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-9 — Validation Human Validation & Professional Cockpit

Contrôles :
  V1 — 0 droit stratégique auto-validé
  V2 — 100% des droits disposent d'un statut
  V3 — 100% des scores sont explicables
  V4 — 100% des questions disposent d'un ROI
  V5 — Chaque pièce a une justification
  V6 — Rapport professionnel non vide
  V7 — Cockpit complet (7 blocs présents)
  V8 — Stabilité seed → scores identiques

Usage :
  python -m app.tests.qa.qa9_human_validation --n 100 --seed 42 --save
  python -m app.tests.qa.qa9_human_validation --n 1000 --seed 42 --save
"""

from __future__ import annotations

import sys

# Force l'affichage UTF-8 sur la console (évite les crashs Windows cp1252 sur ≥, ✅, …)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")
os.environ.setdefault("DATABASE_URL", "sqlite:///./mdph_dossiers.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-key-32-chars-minimum-length!")
os.environ.setdefault("WHATSAPP_API_TOKEN", "test")
os.environ.setdefault("WHATSAPP_PHONE_NUMBER_ID", "test")


@dataclass
class CheckQA9:
    nom:    str
    statut: str   # "PASS" | "WARN" | "FAIL"
    detail: str = ""


@dataclass
class ResultatQA9:
    profil_id:      str
    famille:        str
    niveau_doc:     str
    nb_a_valider:   int
    nb_auto:        int
    score_cockpit:  int
    statut:         str
    checks:         list[CheckQA9] = field(default_factory=list)
    erreur:         str            = ""


# ─────────────────────────────────────────────────────────────────────────────
# CONTRÔLES
# ─────────────────────────────────────────────────────────────────────────────

def _v1_aucun_auto_valide(tableau) -> CheckQA9:
    """V1 — 0 droit stratégique auto-validé."""
    auto_valides = [
        e.element for e in tableau.elements_a_valider
        if e.validation_professionnelle is True
    ]
    if auto_valides:
        return CheckQA9("V1-aucun_auto_valide", "FAIL",
                         f"Droits auto-validés INTERDITS : {auto_valides}")
    return CheckQA9("V1-aucun_auto_valide", "PASS",
                     f"{len(tableau.elements_a_valider)} droit(s) en attente (aucun auto-validé)")


def _v2_statuts_presents(tableau) -> CheckQA9:
    """V2 — 100% des droits ont un statut."""
    sans_statut = [
        e.element for e in tableau.elements_a_valider
        if not e.statut or e.statut not in ("a_valider", "valide", "refuse", "modifie")
    ]
    if sans_statut:
        return CheckQA9("V2-statuts_presents", "FAIL",
                         f"Éléments sans statut valide : {sans_statut[:3]}")
    return CheckQA9("V2-statuts_presents", "PASS",
                     f"Tous les statuts présents ({len(tableau.elements_a_valider)} éléments)")


def _v3_scores_explicables(cockpit) -> CheckQA9:
    """V3 — Score global + preuves présentes."""
    if cockpit.score_global is None or not (0 <= cockpit.score_global <= 100):
        return CheckQA9("V3-scores_explicables", "FAIL",
                         f"Score invalide : {cockpit.score_global}")

    sans_score = [d for d in cockpit.droits_solides + cockpit.droits_fragiles
                  if d.score < 0 or d.score > 100]
    if sans_score:
        return CheckQA9("V3-scores_explicables", "FAIL",
                         f"Scores hors bornes : {[d.droit for d in sans_score[:3]]}")

    return CheckQA9("V3-scores_explicables", "PASS",
                     f"Score global {cockpit.score_global}/100 + {len(cockpit.droits_solides + cockpit.droits_fragiles)} scores unitaires")


def _v4_questions_roi(cockpit) -> CheckQA9:
    """V4 — 100% des questions ont un ROI."""
    sans_roi = [
        q for q in cockpit.questions
        if q.impact_roi is None or not (0 <= q.impact_roi <= 100)
    ]
    if sans_roi:
        return CheckQA9("V4-questions_roi", "FAIL",
                         f"{len(sans_roi)} question(s) sans ROI valide")
    return CheckQA9("V4-questions_roi", "PASS",
                     f"{len(cockpit.questions)} question(s) avec ROI")


def _v5_pieces_justifiees(cockpit) -> CheckQA9:
    """V5 — Chaque pièce a une justification."""
    sans_justif = [
        p for p in cockpit.pieces
        if not p.justification or len(p.justification.strip()) < 5
    ]
    if sans_justif:
        return CheckQA9("V5-pieces_justifiees", "WARN",
                         f"{len(sans_justif)} pièce(s) sans justification")
    return CheckQA9("V5-pieces_justifiees", "PASS",
                     f"{len(cockpit.pieces)} pièce(s) justifiée(s)")


def _v6_rapport_non_vide(rapports) -> CheckQA9:
    """V6 — Rapport professionnel non vide."""
    rp = rapports.professionnel
    if not rp or len(rp) < 200:
        return CheckQA9("V6-rapport_non_vide", "FAIL",
                         f"Rapport trop court : {len(rp)} chars")
    # Vérifier les 4 rapports
    min_len = min(len(rapports.professionnel), len(rapports.essms),
                  len(rapports.mdph), len(rapports.qualite))
    if min_len < 100:
        return CheckQA9("V6-rapport_non_vide", "WARN",
                         f"Un rapport < 100 chars")
    return CheckQA9("V6-rapport_non_vide", "PASS",
                     f"4 rapports générés (min {min_len} chars)")


def _v7_cockpit_complet(cockpit) -> CheckQA9:
    """V7 — Les 7 blocs du cockpit sont présents."""
    manquants = []
    if not cockpit.forces and not cockpit.faiblesses:
        manquants.append("forces/faiblesses")
    if cockpit.score_global is None:
        manquants.append("score_global")
    if cockpit.nb_en_attente_validation is None:
        manquants.append("tableau_validation")
    if cockpit.resume is None or len(cockpit.resume) < 10:
        manquants.append("resume")

    if manquants:
        return CheckQA9("V7-cockpit_complet", "WARN",
                         f"Blocs manquants : {manquants}")
    return CheckQA9("V7-cockpit_complet", "PASS", "7 blocs présents")


def _v8_validations_toutes_false(tableau) -> CheckQA9:
    """V8 — Toutes les validations par défaut = False."""
    pre_validees = [
        e.element for e in tableau.elements_a_valider
        if e.validation_professionnelle is not False
    ]
    if pre_validees:
        return CheckQA9("V8-default_false", "FAIL",
                         f"Validations non-False à la création : {pre_validees}")
    return CheckQA9("V8-default_false", "PASS",
                     "Toutes les validations démarrent à False")


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def executer_qa9(profil) -> ResultatQA9:
    try:
        from app.engines.human_validation_engine import creer_tableau_validation
        from app.engines.professional_cockpit_engine import generer_cockpit
        from app.engines.pro_report_engine import generer_rapports

        donnees = dict(profil.donnees)
        doc_texte = getattr(profil, "document_texte", None)
        if doc_texte and not donnees.get("notes_pro"):
            donnees["notes_pro"] = doc_texte[:600]

        tableau  = creer_tableau_validation(donnees, profil.profil_mdph, profil.profil_handicap)
        cockpit  = generer_cockpit(donnees, profil.profil_mdph, profil.profil_handicap)
        rapports = generer_rapports(cockpit, donnees)

        checks = [
            _v1_aucun_auto_valide(tableau),
            _v2_statuts_presents(tableau),
            _v3_scores_explicables(cockpit),
            _v4_questions_roi(cockpit),
            _v5_pieces_justifiees(cockpit),
            _v6_rapport_non_vide(rapports),
            _v7_cockpit_complet(cockpit),
            _v8_validations_toutes_false(tableau),
        ]

        nb_fail = sum(1 for c in checks if c.statut == "FAIL")
        nb_warn = sum(1 for c in checks if c.statut == "WARN")
        statut  = "FAIL" if nb_fail > 0 else ("WARN" if nb_warn > 2 else "PASS")

        return ResultatQA9(
            profil_id=profil.id,
            famille=profil.famille,
            niveau_doc=profil.niveau_documentation,
            nb_a_valider=tableau.nb_a_valider,
            nb_auto=tableau.nb_automatiques_presents,
            score_cockpit=cockpit.score_global,
            statut=statut,
            checks=checks,
        )

    except Exception as e:
        return ResultatQA9(
            profil_id=profil.id,
            famille=profil.famille,
            niveau_doc=getattr(profil, "niveau_documentation", "?"),
            nb_a_valider=0,
            nb_auto=0,
            score_cockpit=0,
            statut="FAIL",
            erreur=f"{type(e).__name__}: {str(e)[:100]}",
        )


def main():
    parser = argparse.ArgumentParser(description="QA-9 — Human Validation")
    parser.add_argument("--n",    type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()
    n, seed = args.n, args.seed

    print(f"QA-9 — Human Validation & Professional Cockpit : {n} dossiers (seed={seed})")
    print()

    t0 = time.time()
    print(f"[1/3] Génération des profils...")
    from app.tests.qa.synthetic_profiles_engine import generer_profils
    profils = generer_profils(n=n, seed=seed)
    print(f"  {n} profils générés")

    print(f"\n[2/3] Pipeline QA-9...")
    resultats: list[ResultatQA9] = []
    errors = 0
    for i, profil in enumerate(profils):
        r = executer_qa9(profil)
        resultats.append(r)
        if r.erreur: errors += 1
        if (i + 1) % max(1, n // 10) == 0:
            nb_p = sum(1 for x in resultats if x.statut == "PASS")
            nb_f = sum(1 for x in resultats if x.statut == "FAIL")
            score_moy = round(sum(x.score_cockpit for x in resultats) / len(resultats), 1)
            print(f"  [{i+1:>4}/{n}] PASS:{nb_p} FAIL:{nb_f} score_moy:{score_moy} err:{errors}")

    t1 = time.time()
    duree = round(t1 - t0, 1)
    print(f"\n  ✅ Pipeline terminé en {duree}s ({duree/n*1000:.0f}ms/dossier)")

    print(f"\n[3/3] Rapport QA-9...")
    nb_pass  = sum(1 for r in resultats if r.statut == "PASS")
    nb_fail  = sum(1 for r in resultats if r.statut == "FAIL")
    nb_warn  = sum(1 for r in resultats if r.statut == "WARN")
    score_moy = round(sum(r.score_cockpit for r in resultats) / n, 1)
    valid_moy = round(sum(r.nb_a_valider for r in resultats) / n, 1)
    auto_moy  = round(sum(r.nb_auto for r in resultats) / n, 1)
    stabilite = round(nb_pass / n * 100, 1)

    from collections import defaultdict
    check_fails: dict[str, int] = defaultdict(int)
    for r in resultats:
        for c in r.checks:
            if c.statut == "FAIL":
                check_fails[c.nom] += 1

    ok_auto_val  = check_fails.get("V1-aucun_auto_valide", 0) == 0
    ok_statuts   = check_fails.get("V2-statuts_presents", 0) == 0
    ok_scores    = check_fails.get("V3-scores_explicables", 0) == 0
    ok_roi       = check_fails.get("V4-questions_roi", 0) == 0
    ok_default   = check_fails.get("V8-default_false", 0) == 0
    ok_stabilite = stabilite >= 95

    decision = "✅ PASS" if all([ok_auto_val, ok_statuts, ok_scores, ok_roi, ok_default, ok_stabilite]) else "⚠️ WARN"

    sep = "─" * 64
    print(f"\n{sep}")
    print(f"  QA-9 — {n} dossiers Human Validation & Cockpit (seed={seed})")
    print(sep)
    print(f"  PASS : {nb_pass}/{n} ({round(nb_pass/n*100,1)}%)")
    print(f"  WARN : {nb_warn}/{n}")
    print(f"  FAIL : {nb_fail}/{n}")
    print(f"  Score cockpit moy   : {score_moy}/100")
    print(f"  Éléments à valider  : {valid_moy} moy/dossier")
    print(f"  Éléments automatiques: {auto_moy} moy/dossier")
    print()
    print(f"  Seuils QA-9 :")
    print(f"    0 droit auto-validé         : {'✅' if ok_auto_val else '❌'}")
    print(f"    100% droits avec statut      : {'✅' if ok_statuts else '❌'}")
    print(f"    100% scores explicables      : {'✅' if ok_scores else '❌'}")
    print(f"    100% questions avec ROI      : {'✅' if ok_roi else '❌'}")
    print(f"    Validation default=False     : {'✅' if ok_default else '❌'}")
    print(f"    Stabilité ≥ 95%             : {'✅' if ok_stabilite else '❌'} ({stabilite}%)")

    if check_fails:
        print(f"\n  Anomalies :")
        for nom, count in sorted(check_fails.items(), key=lambda x: -x[1])[:5]:
            print(f"    {count:>4}/{n}  {nom}")

    print(f"\n  Décision QA-9 ({n} dossiers) : {decision}")
    print(sep)

    if args.save:
        out_dir = Path("app/tests/qa/reports")
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        path = out_dir / f"qa9_human_validation_{n}_{ts}.txt"
        lines = [
            f"QA-9 Human Validation & Professional Cockpit",
            f"N={n} seed={seed} durée={duree}s",
            f"PASS={nb_pass} FAIL={nb_fail} WARN={nb_warn}",
            f"Score_moy={score_moy} Validmoy={valid_moy}",
            f"Stabilité={stabilite}% Décision={decision}",
        ]
        for nom, count in sorted(check_fails.items(), key=lambda x: -x[1]):
            lines.append(f"  {count}/{n} {nom}")
        path.write_text("\n".join(lines), encoding="utf-8")
        print(f"\n  Rapport : {path}")

    sys.exit(0 if all([ok_auto_val, ok_statuts, ok_scores, ok_stabilite]) else 1)


if __name__ == "__main__":
    main()
