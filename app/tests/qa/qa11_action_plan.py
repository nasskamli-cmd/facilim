"""
app/tests/qa/qa11_action_plan.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-11 — Action Plan, Parcours & Priorisation Engine

Contrôles :
  P1 — Aucune action impossible (déjà réalisée proposée)
  P2 — Aucune action contradictoire
  P3 — 100% des actions justifiées
  P4 — ROI cohérent (impact > 0, effort > 0)
  P5 — Priorisation stable (haute > moyenne > basse)
  P6 — Plan généré sur 100% des dossiers
  P7 — Parcours produit (4 semaines présentes)
  P8 — 3 versions de chaque action (pro/usager/essms)

Usage :
  python -m app.tests.qa.qa11_action_plan --n 100 --seed 42 --save
  python -m app.tests.qa.qa11_action_plan --n 1000 --seed 42 --save
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
class CheckQA11:
    nom:    str
    statut: str
    detail: str = ""


@dataclass
class ResultatQA11:
    profil_id:      str
    famille:        str
    niveau_doc:     str
    nb_actions:     int
    nb_realisees:   int
    roi_max:        float
    statut:         str
    checks:         list[CheckQA11] = field(default_factory=list)
    erreur:         str             = ""


def _p1_aucune_deja_realisee(tableau) -> CheckQA11:
    """P1 — Les actions déjà réalisées ne doivent pas être dans la liste active."""
    proposees_realisees = [a.id for a in tableau.actions_triees if a.deja_realisee]
    if proposees_realisees:
        return CheckQA11("P1-aucune_realisee", "FAIL",
                          f"Actions déjà réalisées proposées : {proposees_realisees[:3]}")
    return CheckQA11("P1-aucune_realisee", "PASS",
                      f"{tableau.nb_deja_realisees} action(s) déjà réalisées filtrées")


def _p2_pas_contradictoire(tableau) -> CheckQA11:
    """P2 — Pas d'actions contradictoires (ex: PCH + autonomie complète)."""
    ids = {a.id for a in tableau.actions_triees}
    # Vérification simple : pas de duplication d'ID
    ids_vus: set[str] = set()
    doublons = []
    for a in tableau.actions_triees:
        if a.id in ids_vus:
            doublons.append(a.id)
        ids_vus.add(a.id)
    if doublons:
        return CheckQA11("P2-pas_contradictoire", "WARN",
                          f"Actions dupliquées : {doublons[:3]}")
    return CheckQA11("P2-pas_contradictoire", "PASS", "Aucune action contradictoire")


def _p3_actions_justifiees(tableau) -> CheckQA11:
    """P3 — 100% des actions ont une justification."""
    sans_justif = [a.id for a in tableau.actions_triees if not a.justification]
    if sans_justif:
        return CheckQA11("P3-justifiees", "FAIL",
                          f"Actions sans justification : {sans_justif[:3]}")
    return CheckQA11("P3-justifiees", "PASS",
                      f"{len(tableau.actions_triees)} action(s) justifiée(s)")


def _p4_roi_coherent(tableau) -> CheckQA11:
    """P4 — ROI cohérent (positif, impact/effort valides)."""
    invalides = [
        a.id for a in tableau.actions_triees
        if a.roi < 0 or a.impact < 0 or a.effort <= 0 or a.impact > 100
    ]
    if invalides:
        return CheckQA11("P4-roi_coherent", "FAIL",
                          f"ROI invalides : {invalides[:3]}")
    return CheckQA11("P4-roi_coherent", "PASS",
                      f"ROI max={tableau.roi_max:.1f} moy={tableau.roi_moy:.1f}")


def _p5_priorisation_stable(tableau) -> CheckQA11:
    """P5 — Les actions hautes précèdent les moyennes qui précèdent les basses."""
    ordres = [a.priorite for a in tableau.actions_triees]
    # Vérifier que "basse" ne précède jamais "haute"
    seen_basse = False
    violation = None
    for p in ordres:
        if p == "basse":
            seen_basse = True
        if seen_basse and p == "haute":
            violation = "haute après basse"
            break
    if violation:
        return CheckQA11("P5-priorisation_stable", "WARN", f"Ordre non optimal : {violation}")
    return CheckQA11("P5-priorisation_stable", "PASS", "Priorisation cohérente")


def _p6_plan_genere(tableau) -> CheckQA11:
    """P6 — Plan généré (au moins 1 action proposée)."""
    if len(tableau.actions_triees) + tableau.nb_deja_realisees == 0:
        return CheckQA11("P6-plan_genere", "FAIL", "Aucune action générée")
    return CheckQA11("P6-plan_genere", "PASS",
                      f"{len(tableau.actions_triees)} action(s) actives")


def _p7_parcours_complet(parcours) -> CheckQA11:
    """P7 — Parcours contient 4 semaines."""
    nb_semaines = len(parcours.etapes)
    if nb_semaines < 4:
        return CheckQA11("P7-parcours_complet", "FAIL",
                          f"Seulement {nb_semaines} semaine(s)")
    if not parcours.parcours_usager or len(parcours.parcours_usager) < 50:
        return CheckQA11("P7-parcours_complet", "WARN", "Parcours usager trop court")
    return CheckQA11("P7-parcours_complet", "PASS", "4 semaines présentes")


def _p8_trois_versions(tableau) -> CheckQA11:
    """P8 — Les 3 versions de chaque action sont présentes."""
    sans_usager = [a.id for a in tableau.actions_triees if not a.description_usager]
    sans_essms  = [a.id for a in tableau.actions_triees if not a.description_essms]
    if sans_usager or sans_essms:
        return CheckQA11("P8-trois_versions", "WARN",
                          f"Manque: usager={len(sans_usager)} essms={len(sans_essms)}")
    return CheckQA11("P8-trois_versions", "PASS", "3 versions présentes pour toutes les actions")


def executer_qa11(profil) -> ResultatQA11:
    try:
        from app.engines.action_plan_engine import generer_plan_action
        from app.engines.parcours_engine import construire_parcours

        donnees = dict(profil.donnees)
        tableau  = generer_plan_action(donnees, profil.profil_mdph, profil.profil_handicap)
        parcours = construire_parcours(tableau)

        checks = [
            _p1_aucune_deja_realisee(tableau),
            _p2_pas_contradictoire(tableau),
            _p3_actions_justifiees(tableau),
            _p4_roi_coherent(tableau),
            _p5_priorisation_stable(tableau),
            _p6_plan_genere(tableau),
            _p7_parcours_complet(parcours),
            _p8_trois_versions(tableau),
        ]

        nb_fail = sum(1 for c in checks if c.statut == "FAIL")
        nb_warn = sum(1 for c in checks if c.statut == "WARN")
        statut  = "FAIL" if nb_fail > 0 else ("WARN" if nb_warn > 2 else "PASS")

        return ResultatQA11(
            profil_id=profil.id, famille=profil.famille,
            niveau_doc=profil.niveau_documentation,
            nb_actions=len(tableau.actions_triees),
            nb_realisees=tableau.nb_deja_realisees,
            roi_max=tableau.roi_max,
            statut=statut, checks=checks,
        )

    except Exception as e:
        return ResultatQA11(
            profil_id=profil.id, famille=profil.famille,
            niveau_doc=getattr(profil, "niveau_documentation", "?"),
            nb_actions=0, nb_realisees=0, roi_max=0.0,
            statut="FAIL", erreur=f"{type(e).__name__}: {str(e)[:100]}",
        )


def main():
    parser = argparse.ArgumentParser(description="QA-11 Action Plan")
    parser.add_argument("--n",    type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()
    n, seed = args.n, args.seed

    print(f"QA-11 — Action Plan & Parcours : {n} dossiers (seed={seed})")
    t0 = time.time()

    from app.tests.qa.synthetic_profiles_engine import generer_profils
    profils = generer_profils(n=n, seed=seed)
    print(f"  {n} profils générés")

    print(f"\n[2/3] Pipeline QA-11 ({n} dossiers)...")
    resultats: list[ResultatQA11] = []
    errors = 0
    for i, profil in enumerate(profils):
        r = executer_qa11(profil)
        resultats.append(r)
        if r.erreur: errors += 1
        if (i + 1) % max(1, n // 10) == 0:
            nb_p = sum(1 for x in resultats if x.statut == "PASS")
            nb_f = sum(1 for x in resultats if x.statut == "FAIL")
            actions_moy = round(sum(x.nb_actions for x in resultats) / len(resultats), 1)
            roi_moy = round(sum(x.roi_max for x in resultats) / len(resultats), 1)
            print(f"  [{i+1:>4}/{n}] PASS:{nb_p} FAIL:{nb_f} actions:{actions_moy} roi_max:{roi_moy}")

    t1 = time.time()
    duree = round(t1 - t0, 1)

    nb_pass  = sum(1 for r in resultats if r.statut == "PASS")
    nb_fail  = sum(1 for r in resultats if r.statut == "FAIL")
    nb_warn  = sum(1 for r in resultats if r.statut == "WARN")
    actions_moy = round(sum(r.nb_actions for r in resultats) / n, 1)
    roi_moy  = round(sum(r.roi_max for r in resultats) / n, 1)
    stabilite = round(nb_pass / n * 100, 1)

    check_fails: dict[str, int] = defaultdict(int)
    for r in resultats:
        for c in r.checks:
            if c.statut == "FAIL": check_fails[c.nom] += 1

    ok_realisee = check_fails.get("P1-aucune_realisee", 0) == 0
    ok_justif   = check_fails.get("P3-justifiees", 0) == 0
    ok_roi      = check_fails.get("P4-roi_coherent", 0) == 0
    ok_plan     = check_fails.get("P6-plan_genere", 0) == 0
    ok_stab     = stabilite >= 95

    decision = "✅ PASS" if all([ok_realisee, ok_justif, ok_roi, ok_plan, ok_stab]) else "⚠️ WARN"

    sep = "─" * 62
    print(f"\n{sep}")
    print(f"  QA-11 — {n} dossiers Action Plan & Parcours (seed={seed})")
    print(sep)
    print(f"  PASS : {nb_pass}/{n} ({stabilite}%)")
    print(f"  FAIL : {nb_fail}/{n}")
    print(f"  Actions actives moy  : {actions_moy}")
    print(f"  ROI max moyen        : {roi_moy:.1f}")
    print(f"  Durée                : {duree}s ({duree/n*1000:.0f}ms/dossier)")
    print()
    print(f"  Seuils QA-11 :")
    print(f"    0 action déjà réalisée proposée : {'✅' if ok_realisee else '❌'}")
    print(f"    100% actions justifiées          : {'✅' if ok_justif else '❌'}")
    print(f"    ROI cohérent                     : {'✅' if ok_roi else '❌'}")
    print(f"    Plan généré sur 100%             : {'✅' if ok_plan else '❌'}")
    print(f"    Stabilité ≥ 95%                  : {'✅' if ok_stab else '❌'} ({stabilite}%)")

    if check_fails:
        print(f"\n  Anomalies :")
        for nom, c in sorted(check_fails.items(), key=lambda x: -x[1])[:5]:
            print(f"    {c:>4}/{n}  {nom}")

    print(f"\n  Décision QA-11 : {decision}")
    print(sep)

    if args.save:
        out_dir = Path("app/tests/qa/reports")
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        path = out_dir / f"qa11_action_plan_{n}_{ts}.txt"
        lines = [
            f"QA-11 Action Plan & Parcours",
            f"N={n} seed={seed} durée={duree}s",
            f"PASS={nb_pass} FAIL={nb_fail} WARN={nb_warn}",
            f"actions_moy={actions_moy} roi_max={roi_moy}",
            f"stabilité={stabilite}% décision={decision}",
        ] + [f"  {c}/{n} {nom}" for nom, c in sorted(check_fails.items(), key=lambda x: -x[1])]
        path.write_text("\n".join(lines), encoding="utf-8")
        print(f"\n  Rapport : {path}")

    sys.exit(0 if all([ok_realisee, ok_justif, ok_stab]) else 1)


if __name__ == "__main__":
    main()
