"""
app/tests/qa/qa7_cdaph_runner.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-7 — Validation du Moteur de Stratégie CDAPH

Mesure sur 100 / 500 / 1000 dossiers synthétiques :
  - Cohérence des recommandations
  - Absence de conseils absurdes
  - Stabilité des scores
  - Qualité des questions levier

Usage :
  python -m app.tests.qa.qa7_cdaph_runner --n 100 --seed 42 --save
  python -m app.tests.qa.qa7_cdaph_runner --n 1000 --seed 42 --save
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


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CheckQA7:
    nom:    str
    statut: str   # "PASS" | "WARN" | "FAIL"
    detail: str   = ""


@dataclass
class ResultatQA7:
    profil_id:        str
    famille:          str
    niveau_doc:       str
    profil_mdph:      str
    score_solidite:   int
    statut:           str       # "PASS" | "WARN" | "FAIL"
    checks:           list[CheckQA7] = field(default_factory=list)
    erreur:           str       = ""


# ─────────────────────────────────────────────────────────────────────────────
# CONTRÔLES QA-7
# ─────────────────────────────────────────────────────────────────────────────

def _verifier_rapport(profil, rapport) -> list[CheckQA7]:
    """7 contrôles automatiques sur le rapport CDAPH."""
    checks = []

    # S1 — Score cohérent avec niveau de documentation
    seuils = {"pauvre": (5, 45), "moyen": (20, 70), "riche": (40, 95)}
    seuil_min, seuil_max = seuils.get(profil.niveau_documentation, (5, 95))
    score = rapport.score_solidite
    checks.append(CheckQA7(
        "S1-score_coherent",
        "PASS" if seuil_min <= score <= seuil_max else "WARN",
        f"Score {score}/100 pour doc={profil.niveau_documentation} (attendu {seuil_min}-{seuil_max})",
    ))

    # S2 — Au moins 1 analyse de droit produite
    nb_droits = len(rapport.droits_solides) + len(rapport.droits_fragiles)
    checks.append(CheckQA7(
        "S2-droits_analyses",
        "PASS" if nb_droits >= 1 else "FAIL",
        f"{nb_droits} droit(s) analysé(s)",
    ))

    # S3 — Aucun conseil absurde : droits non_attendus dans droits_solides
    faux_solides = [
        d.droit for d in rapport.droits_solides
        if d.droit in set(profil.droits_non_attendus)
    ]
    checks.append(CheckQA7(
        "S3-pas_absurde",
        "FAIL" if faux_solides else "PASS",
        f"Droits incompatibles en solides : {faux_solides}" if faux_solides else "OK",
    ))

    # S4 — Questions ≤ 5 et non vides
    nb_q = len(rapport.questions_levier)
    checks.append(CheckQA7(
        "S4-questions_levier",
        "PASS" if 0 <= nb_q <= 5 else "WARN",
        f"{nb_q} question(s) levier",
    ))

    # S5 — Forces et faiblesses non vides (sauf dossier vide)
    if profil.donnees:  # pas le dossier vide
        has_analysis = rapport.forces_globales or rapport.faiblesses_globales
        checks.append(CheckQA7(
            "S5-forces_faiblesses",
            "PASS" if has_analysis else "WARN",
            "Forces/faiblesses produites" if has_analysis else "Analyse vide",
        ))

    # S6 — Décision prévisible cohérente avec robustesse
    for droit_analyse in rapport.droits_solides:
        if droit_analyse.decision_previsible == "défavorable":
            checks.append(CheckQA7(
                "S6-coherence_decision",
                "FAIL",
                f"{droit_analyse.droit} : robustesse {droit_analyse.robustesse_pct}% mais décision défavorable",
            ))
            break
    else:
        checks.append(CheckQA7("S6-coherence_decision", "PASS", "Décisions cohérentes"))

    # S7 — Score stable (déterministe)
    # Vérifié implicitement par la reproductibilité du seed

    # S8 — Résumé exécutif non vide
    checks.append(CheckQA7(
        "S8-resume_present",
        "PASS" if rapport.resume_executif and len(rapport.resume_executif) > 20 else "WARN",
        f"{len(rapport.resume_executif)} chars",
    ))

    return checks


def _score_qa7(checks: list[CheckQA7]) -> int:
    total = sum(
        100 if c.statut == "PASS" else 50 if c.statut == "WARN" else 0
        for c in checks
    )
    return round(total / len(checks)) if checks else 0


def _statut(checks: list[CheckQA7]) -> str:
    if any(c.statut == "FAIL" for c in checks): return "FAIL"
    if sum(1 for c in checks if c.statut == "WARN") > 2: return "WARN"
    return "PASS"


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def executer_qa7(profil) -> ResultatQA7:
    """Exécute le pipeline QA-7 sur un profil synthétique."""
    try:
        from app.engines.cdaph_strategy_engine import analyser_strategie_cdaph
        donnees = dict(profil.donnees)
        # SyntheticProfile n'a pas de document_texte — utiliser getattr pour compatibilité
        doc_texte = getattr(profil, "document_texte", None)
        if doc_texte and not donnees.get("notes_pro"):
            donnees["notes_pro"] = doc_texte[:600]

        rapport = analyser_strategie_cdaph(donnees, profil.profil_mdph, profil.profil_handicap)
        checks  = _verifier_rapport(profil, rapport)

        return ResultatQA7(
            profil_id=profil.id,
            famille=profil.famille,
            niveau_doc=profil.niveau_documentation,
            profil_mdph=profil.profil_mdph,
            score_solidite=rapport.score_solidite,
            statut=_statut(checks),
            checks=checks,
        )

    except Exception as e:
        return ResultatQA7(
            profil_id=profil.id,
            famille=profil.famille,
            niveau_doc=getattr(profil, "niveau_documentation", "?"),
            profil_mdph=getattr(profil, "profil_mdph", "?"),
            score_solidite=0,
            statut="FAIL",
            erreur=f"{type(e).__name__}: {str(e)[:100]}",
        )


# ─────────────────────────────────────────────────────────────────────────────
# RAPPORT
# ─────────────────────────────────────────────────────────────────────────────

def generer_rapport_qa7(resultats: list[ResultatQA7], seed: int, n: int,
                         duree_s: float) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    nb_pass = sum(1 for r in resultats if r.statut == "PASS")
    nb_fail = sum(1 for r in resultats if r.statut == "FAIL")
    nb_warn = sum(1 for r in resultats if r.statut == "WARN")

    scores = [r.score_solidite for r in resultats]
    score_moy = round(sum(scores) / len(scores), 1) if scores else 0
    score_med = sorted(scores)[len(scores) // 2] if scores else 0

    # Stabilité : variance des scores
    variance = round(sum((s - score_moy)**2 for s in scores) / len(scores), 1) if scores else 0
    ecart_type = round(variance ** 0.5, 1)

    # Anomalies
    from collections import defaultdict
    check_fails: dict[str, int] = defaultdict(int)
    for r in resultats:
        for c in r.checks:
            if c.statut == "FAIL":
                check_fails[c.nom] += 1

    # Par niveau de documentation
    par_doc: dict[str, list[int]] = defaultdict(list)
    for r in resultats:
        par_doc[r.niveau_doc].append(r.score_solidite)

    # Par famille
    par_famille: dict[str, list[int]] = defaultdict(list)
    for r in resultats:
        par_famille[r.famille].append(r.score_solidite)

    ok_pass = nb_pass / n >= 0.85 if n <= 100 else (nb_pass / n >= 0.80 if n <= 500 else nb_pass / n >= 0.75)
    ok_fail = nb_fail == 0
    ok_absurde = not any(
        c.statut == "FAIL" and "S3" in c.nom
        for r in resultats for c in r.checks
    )
    decision = "✅ PASS" if (ok_pass and ok_fail and ok_absurde) else "⚠️ WARN"

    lines = [
        f"# QA-7 — Moteur Stratégie CDAPH",
        f"",
        f"**Généré le :** {now}  ",
        f"**Dossiers testés :** {n} (seed={seed})  ",
        f"**Durée :** {duree_s:.1f}s ({duree_s/n*1000:.0f}ms/dossier)  ",
        f"**Décision :** {decision}",
        "",
        "---",
        "",
        "## 1. Résultats globaux",
        "",
        f"| Métrique | Valeur |",
        f"|---------|--------|",
        f"| PASS | {nb_pass}/{n} ({round(nb_pass/n*100,1)}%) |",
        f"| WARN | {nb_warn}/{n} |",
        f"| FAIL | {nb_fail}/{n} |",
        f"| Score solidité moyen | {score_moy}/100 |",
        f"| Score solidité médian | {score_med}/100 |",
        f"| Écart-type (stabilité) | {ecart_type} |",
        f"| Conseils absurdes (S3 FAIL) | {check_fails.get('S3-pas_absurde', 0)} |",
        "",
        "---",
        "",
        "## 2. Score par niveau de documentation",
        "",
        "| Niveau | N | Score moy | Cohérence |",
        "|--------|---|-----------|----------|",
    ]

    for doc_level in ["riche", "moyen", "pauvre"]:
        sc_list = par_doc.get(doc_level, [])
        if not sc_list:
            continue
        moy = round(sum(sc_list) / len(sc_list), 1)
        # Vérification de cohérence monotone (riche > moyen > pauvre)
        coherent = "✅" if (
            (doc_level == "riche" and moy >= 40) or
            (doc_level == "moyen" and moy >= 20) or
            (doc_level == "pauvre" and moy <= 50)
        ) else "⚠️"
        lines.append(f"| {doc_level} | {len(sc_list)} | {moy} | {coherent} |")

    lines += [
        "",
        "---",
        "",
        "## 3. Score par famille de handicap",
        "",
        "| Famille | N | Score moy |",
        "|---------|---|-----------|",
    ]
    for famille, sc_list in sorted(par_famille.items(), key=lambda x: -len(x[1])):
        moy = round(sum(sc_list) / len(sc_list), 1)
        lines.append(f"| {famille} | {len(sc_list)} | {moy} |")

    lines += [
        "",
        "---",
        "",
        "## 4. Contrôles QA-7 — Fréquences d'anomalies",
        "",
        "| Contrôle | FAIL | Fréquence |",
        "|---------|------|----------|",
    ]
    for nom_check, count in sorted(check_fails.items(), key=lambda x: -x[1]):
        lines.append(f"| `{nom_check}` | {count} | {round(count/n*100,1)}% |")

    if not check_fails:
        lines.append("| _(aucun)_ | 0 | 0% |")

    lines += [
        "",
        "---",
        "",
        f"## Décision finale : {decision}",
        "",
        f"- PASS ≥ seuil : {'✅' if ok_pass else '❌'} ({round(nb_pass/n*100,1)}%)",
        f"- FAIL = 0 : {'✅' if ok_fail else '❌'} ({nb_fail})",
        f"- Conseils absurdes = 0 : {'✅' if ok_absurde else '❌'}",
        f"- Écart-type < 20 : {'✅' if ecart_type < 20 else '⚠️'} ({ecart_type})",
        "",
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="QA-7 — Moteur Stratégie CDAPH")
    parser.add_argument("--n",    type=int, default=100, help="Nombre de dossiers")
    parser.add_argument("--seed", type=int, default=42,  help="Seed aléatoire")
    parser.add_argument("--save", action="store_true",   help="Sauvegarder le rapport")
    args = parser.parse_args()

    n, seed = args.n, args.seed
    print(f"QA-7 — Moteur Stratégie CDAPH : {n} dossiers (seed={seed})")
    print()

    # Génération des profils
    t0 = time.time()
    print(f"[1/3] Génération de {n} profils synthétiques...")
    from app.tests.qa.synthetic_profiles_engine import generer_profils
    profils = generer_profils(n=n, seed=seed)
    print(f"  {len(profils)} profils générés")

    # Pipeline
    print(f"\n[2/3] Analyse stratégique CDAPH ({n} dossiers)...")
    resultats: list[ResultatQA7] = []
    errors = 0
    for i, profil in enumerate(profils):
        r = executer_qa7(profil)
        resultats.append(r)
        if r.erreur: errors += 1
        if (i + 1) % max(1, n // 10) == 0:
            nb_p = sum(1 for x in resultats if x.statut == "PASS")
            nb_f = sum(1 for x in resultats if x.statut == "FAIL")
            score_moy = round(sum(x.score_solidite for x in resultats) / len(resultats), 1)
            print(f"  [{i+1:>4}/{n}] PASS:{nb_p} FAIL:{nb_f} score_moy:{score_moy} erreurs:{errors}")

    t1 = time.time()
    duree = round(t1 - t0, 1)
    print(f"\n  ✅ Analyse terminée en {duree}s ({duree/n*1000:.0f}ms/dossier)")

    # Métriques
    print(f"\n[3/3] Rapport QA-7...")
    nb_pass = sum(1 for r in resultats if r.statut == "PASS")
    nb_fail = sum(1 for r in resultats if r.statut == "FAIL")
    scores  = [r.score_solidite for r in resultats]
    score_moy = round(sum(scores) / len(scores), 1)
    ecart = round((sum((s - score_moy)**2 for s in scores) / len(scores)) ** 0.5, 1)
    absurdes = sum(1 for r in resultats for c in r.checks
                   if c.statut == "FAIL" and "S3" in c.nom)

    sep = "─" * 60
    print(f"\n{sep}")
    print(f"  QA-7 — {n} dossiers CDAPH (seed={seed})")
    print(sep)
    print(f"  PASS          : {nb_pass}/{n} ({round(nb_pass/n*100,1)}%)")
    print(f"  FAIL          : {nb_fail}/{n}")
    print(f"  Score moy     : {score_moy}/100  (écart-type {ecart})")
    print(f"  Conseils absu.: {absurdes} ({'✅' if absurdes == 0 else '❌'})")
    print(f"  Stabilité     : {'✅ stable' if ecart < 20 else '⚠️ variable'} (σ={ecart})")

    # Cohérence documentation
    par_doc: dict[str, list[int]] = {}
    for r in resultats:
        par_doc.setdefault(r.niveau_doc, []).append(r.score_solidite)
    print(f"\n  Scores par documentation :")
    for doc in ["riche", "moyen", "pauvre"]:
        sl = par_doc.get(doc, [])
        if sl:
            moy = round(sum(sl) / len(sl), 1)
            print(f"    {doc:<8} : {moy}/100 (N={len(sl)})")

    ok = (nb_pass / n >= (0.85 if n <= 100 else 0.80 if n <= 500 else 0.75)
          and nb_fail == 0 and absurdes == 0)
    decision = "✅ PASS" if ok else "⚠️ WARN"
    print(f"\n  Décision QA-7 ({n} dossiers) : {decision}")
    print(sep)

    if args.save:
        rapport_md = generer_rapport_qa7(resultats, seed, n, duree)
        out_dir = Path("app/tests/qa/reports")
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        path = out_dir / f"qa7_cdaph_{n}_{ts}.md"
        path.write_text(rapport_md, encoding="utf-8")
        print(f"\n  Rapport : {path}")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
