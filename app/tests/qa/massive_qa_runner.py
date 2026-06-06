"""
app/tests/qa/massive_qa_runner.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-5 — Simulateur massif de dossiers MDPH

Pipeline automatique sans LLM : rapide, reproductible, scalable.

100 dossiers  : ~5 secondes
500 dossiers  : ~25 secondes
1000 dossiers : ~50 secondes

Usage :
  python -m app.tests.qa.massive_qa_runner --n 100 --seed 42
  python -m app.tests.qa.massive_qa_runner --n 500 --seed 42
  python -m app.tests.qa.massive_qa_runner --n 1000 --seed 42
  python -m app.tests.qa.massive_qa_runner --n 100 --seed 42 --save
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
from typing import Any

sys.path.insert(0, ".")
os.environ.setdefault("DATABASE_URL", "sqlite:///./mdph_dossiers.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-key-32-chars-minimum-length!")
os.environ.setdefault("WHATSAPP_API_TOKEN", "test")
os.environ.setdefault("WHATSAPP_PHONE_NUMBER_ID", "test")

from app.tests.qa.synthetic_profiles_engine import SyntheticProfile, generer_profils, distribution_familles


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURES DE RÉSULTATS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    nom:    str
    statut: str   # "PASS" | "WARN" | "FAIL" | "SKIP"
    detail: str   = ""


@dataclass
class DossierResult:
    profil_id:          str
    famille:            str
    profil_mdph:        str
    niveau_doc:         str
    type_demande:       str
    statut:             str   # "PASS" | "WARN" | "FAIL"
    score:              int   # 0-100
    checks:             list[CheckResult] = field(default_factory=list)
    droits_oublies_detectes: list[str] = field(default_factory=list)
    droits_faux_positifs: list[str]   = field(default_factory=list)
    erreur:             str           = ""

    @property
    def nb_fail(self) -> int:
        return sum(1 for c in self.checks if c.statut == "FAIL")

    @property
    def nb_warn(self) -> int:
        return sum(1 for c in self.checks if c.statut == "WARN")


# ─────────────────────────────────────────────────────────────────────────────
# CONTRÔLES AUTOMATIQUES
# ─────────────────────────────────────────────────────────────────────────────

def _check_droits(profil: SyntheticProfile, strat) -> list[CheckResult]:
    checks = []

    # A1 — Droits attendus cohérents avec le dossier
    droits_detectes = set(strat.droits_demandes)
    droits_proposes = {d.droit for d in strat.droits_omis}

    nb_attendus_couverts = sum(
        1 for d in profil.droits_attendus
        if d in droits_detectes or d in droits_proposes
    )
    pct = nb_attendus_couverts / len(profil.droits_attendus) if profil.droits_attendus else 1.0
    checks.append(CheckResult(
        "A1-droits_coherents",
        "PASS" if pct >= 0.5 else "WARN",
        f"{nb_attendus_couverts}/{len(profil.droits_attendus)} droits attendus couverts",
    ))

    # A2 — Droits oubliés détectés
    nb_oublies_detectes = sum(
        1 for d in profil.droits_oublies
        if d in droits_proposes or any(d in p for p in droits_proposes)
    )
    if profil.droits_oublies:
        pct_oublies = nb_oublies_detectes / len(profil.droits_oublies)
        checks.append(CheckResult(
            "A2-droits_oublies",
            "PASS" if pct_oublies >= 0.5 else "WARN",
            f"{nb_oublies_detectes}/{len(profil.droits_oublies)} droits oubliés détectés",
        ))

    # A3 — Pas de droits absurdes (non attendus avec score élevé)
    faux_pos = [
        d.droit for d in strat.droits_omis
        if d.droit in profil.droits_non_attendus and d.score_compatibilite >= 70
    ]
    checks.append(CheckResult(
        "A3-pas_absurde",
        "FAIL" if faux_pos else "PASS",
        f"Faux positifs dangereux : {faux_pos}" if faux_pos else "OK",
    ))

    return checks, list(droits_proposes & set(profil.droits_oublies)), faux_pos


def _check_cerfa(profil: SyntheticProfile, field_map: dict) -> list[CheckResult]:
    checks = []

    # B1 — Champs critiques présents
    for champ, valeur_attendue in profil.cases_cerfa_attendues.items():
        valeur = field_map.get(champ, "[ABSENT]")
        if valeur_attendue == "/Yes":
            ok = valeur == "/Yes"
        else:
            ok = valeur_attendue.lower() in str(valeur).lower()
        checks.append(CheckResult(
            f"B1-{champ[:30]}",
            "PASS" if ok else "WARN",
            f"Attendu '{valeur_attendue}', obtenu '{valeur}'",
        ))

    # B2 — Pas de champs fantômes (clés inconnues)
    # Contrôle léger : vérifier que le type_dossier est bien mappé
    has_p1 = any("P1" in k for k in field_map)
    checks.append(CheckResult(
        "B2-type_dossier_presente",
        "PASS" if has_p1 else "WARN",
        "Case type dossier présente" if has_p1 else "Aucune case P1 mappée",
    ))

    return checks


def _check_robustesse(profil: SyntheticProfile, rob) -> list[CheckResult]:
    checks = []

    # E1 — Score cohérent avec niveau documentation
    seuils = {"pauvre": 5, "moyen": 15, "riche": 25}
    seuil = seuils.get(profil.niveau_documentation, 5)

    checks.append(CheckResult(
        "E1-robustesse_coherente",
        "PASS" if rob.score_global >= seuil else "WARN",
        f"Robustesse {rob.score_global}/100 (seuil {seuil} pour docs {profil.niveau_documentation})",
    ))

    # E2 — Questions levier présentes si documentation pauvre
    return checks


def _calculer_score(checks: list[CheckResult]) -> int:
    """Score 0-100 basé sur les checks."""
    if not checks:
        return 50
    total = sum(
        100 if c.statut == "PASS" else
        50  if c.statut == "WARN" else
        0   if c.statut == "FAIL" else
        50  # SKIP
        for c in checks
    )
    return round(total / len(checks))


def _statut_global(checks: list[CheckResult]) -> str:
    nb_fail = sum(1 for c in checks if c.statut == "FAIL")
    nb_warn = sum(1 for c in checks if c.statut == "WARN")
    if nb_fail > 0: return "FAIL"
    if nb_warn > 2: return "WARN"
    return "PASS"


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE PAR DOSSIER
# ─────────────────────────────────────────────────────────────────────────────

def executer_pipeline(profil: SyntheticProfile) -> DossierResult:
    """Exécute le pipeline complet sur un profil synthétique (sans LLM)."""
    try:
        from app.engines.strategie_dossier_engine import analyser_strategie
        from app.engines.dossier_strength_engine import noter_robustesse
        from app.engines.pdf.field_mapper import build_field_map

        donnees = dict(profil.donnees)

        # Moteurs FACILIM 60
        strat = analyser_strategie(donnees, profil.profil_mdph, profil.profil_handicap)
        rob   = noter_robustesse(donnees, profil.profil_mdph)
        field_map = build_field_map(donnees, profil.profil_mdph)

        # Contrôles A — Droits
        checks_a, oublies_detectes, faux_pos = _check_droits(profil, strat)

        # Contrôles B — CERFA
        checks_b = _check_cerfa(profil, field_map)

        # Contrôles E — Robustesse
        checks_e = _check_robustesse(profil, rob)

        all_checks = checks_a + checks_b + checks_e
        score = _calculer_score(all_checks)
        statut = _statut_global(all_checks)

        return DossierResult(
            profil_id=profil.id,
            famille=profil.famille,
            profil_mdph=profil.profil_mdph,
            niveau_doc=profil.niveau_documentation,
            type_demande=profil.type_demande,
            statut=statut,
            score=score,
            checks=all_checks,
            droits_oublies_detectes=oublies_detectes,
            droits_faux_positifs=faux_pos,
        )

    except Exception as e:
        import traceback
        return DossierResult(
            profil_id=profil.id,
            famille=profil.famille,
            profil_mdph=profil.profil_mdph,
            niveau_doc=profil.niveau_documentation,
            type_demande=profil.type_demande,
            statut="FAIL",
            score=0,
            erreur=f"{type(e).__name__}: {str(e)[:100]}",
        )


# ─────────────────────────────────────────────────────────────────────────────
# ANALYSE DES RÉSULTATS
# ─────────────────────────────────────────────────────────────────────────────

def analyser_resultats(resultats: list[DossierResult]) -> dict:
    """Calcule toutes les métriques du rapport."""
    n = len(resultats)
    if n == 0:
        return {}

    nb_pass = sum(1 for r in resultats if r.statut == "PASS")
    nb_warn = sum(1 for r in resultats if r.statut == "WARN")
    nb_fail = sum(1 for r in resultats if r.statut == "FAIL")
    scores  = [r.score for r in resultats]

    # Par famille
    par_famille: dict[str, dict] = {}
    for r in resultats:
        if r.famille not in par_famille:
            par_famille[r.famille] = {"pass": 0, "warn": 0, "fail": 0, "scores": []}
        par_famille[r.famille][r.statut.lower()] += 1
        par_famille[r.famille]["scores"].append(r.score)

    # Par niveau documentation
    par_doc: dict[str, dict] = {}
    for r in resultats:
        if r.niveau_doc not in par_doc:
            par_doc[r.niveau_doc] = {"pass": 0, "warn": 0, "fail": 0, "scores": []}
        par_doc[r.niveau_doc][r.statut.lower()] += 1
        par_doc[r.niveau_doc]["scores"].append(r.score)

    # Top anomalies
    anomalies: dict[str, int] = {}
    for r in resultats:
        for c in r.checks:
            if c.statut == "FAIL":
                anomalies[c.nom] = anomalies.get(c.nom, 0) + 1

    # Droits oubliés non détectés
    oublies_non_detectes: dict[str, int] = {}
    for profil_gen in _profils_cache:
        if profil_gen.id in {r.profil_id for r in resultats}:
            result = next((r for r in resultats if r.profil_id == profil_gen.id), None)
            if result:
                for d in profil_gen.droits_oublies:
                    if d not in result.droits_oublies_detectes:
                        oublies_non_detectes[d] = oublies_non_detectes.get(d, 0) + 1

    # Faux positifs dangereux
    nb_faux_pos = sum(1 for r in resultats if r.droits_faux_positifs)

    sorted_scores = sorted(scores)

    return {
        "n": n,
        "nb_pass": nb_pass,
        "nb_warn": nb_warn,
        "nb_fail": nb_fail,
        "taux_pass": round(nb_pass / n * 100, 1),
        "taux_warn": round(nb_warn / n * 100, 1),
        "taux_fail": round(nb_fail / n * 100, 1),
        "score_moy": round(sum(scores) / n, 1),
        "score_median": sorted_scores[n // 2],
        "score_min": min(scores),
        "score_max": max(scores),
        "nb_faux_positifs": nb_faux_pos,
        "taux_faux_positifs": round(nb_faux_pos / n * 100, 2),
        "par_famille": par_famille,
        "par_doc": par_doc,
        "top_anomalies": sorted(anomalies.items(), key=lambda x: -x[1])[:20],
        "top_oublies_non_detectes": sorted(oublies_non_detectes.items(), key=lambda x: -x[1])[:20],
        "top_fragiles": sorted(resultats, key=lambda r: r.score)[:20],
    }


_profils_cache: list[SyntheticProfile] = []


# ─────────────────────────────────────────────────────────────────────────────
# SEUILS DE VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

_SEUILS = {
    100:  {"taux_pass": 85, "taux_fail": 5},
    500:  {"taux_pass": 80, "taux_fail": 8},
    1000: {"taux_pass": 75, "taux_fail": 10},
}


def _seuils_pour_n(n: int) -> dict:
    """Retourne les seuils appropriés pour N dossiers."""
    if n <= 100: return _SEUILS[100]
    if n <= 500: return _SEUILS[500]
    return _SEUILS[1000]


# ─────────────────────────────────────────────────────────────────────────────
# GÉNÉRATION RAPPORT MARKDOWN
# ─────────────────────────────────────────────────────────────────────────────

def generer_rapport_md(
    metriques: dict,
    seed: int,
    n: int,
    duree_s: float,
    seuils: dict,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    nb_pass = metriques["nb_pass"]
    nb_fail = metriques["nb_fail"]
    taux_pass = metriques["taux_pass"]
    taux_fail = metriques["taux_fail"]
    score_moy = metriques["score_moy"]
    score_med = metriques["score_median"]
    score_min = metriques["score_min"]
    faux_pos  = metriques["nb_faux_positifs"]

    # Décision globale
    ok_pass = taux_pass >= seuils["taux_pass"]
    ok_fail = taux_fail <= seuils["taux_fail"]
    ok_danger = faux_pos == 0
    decision = "✅ PASS" if (ok_pass and ok_fail and ok_danger) else (
        "⚠️ WARN" if (ok_fail and ok_danger) else "❌ FAIL"
    )

    lines = [
        f"# QA-5 — Simulateur Massif MDPH — Rapport",
        f"",
        f"**Généré le :** {now}  ",
        f"**Dossiers testés :** {n}  ",
        f"**Seed :** {seed}  ",
        f"**Durée :** {duree_s:.1f}s ({duree_s/n*1000:.0f}ms/dossier)  ",
        f"**Décision :** {decision}",
        "",
        "---",
        "",
        "## 1. Synthèse exécutive",
        "",
        f"Sur **{n} dossiers synthétiques** testés avec le pipeline Facilim complet (sans LLM) :",
        f"",
        f"- **{nb_pass} PASS** ({taux_pass:.1f}%) — seuil requis : ≥ {seuils['taux_pass']}%  ",
        f"- **{metriques['nb_warn']} WARN** ({metriques['taux_warn']:.1f}%)  ",
        f"- **{nb_fail} FAIL** ({taux_fail:.1f}%) — seuil max : ≤ {seuils['taux_fail']}%  ",
        f"- **Score moyen :** {score_moy}/100 · **Médiane :** {score_med}/100 · **Min :** {score_min}/100  ",
        f"- **Faux positifs dangereux :** {faux_pos} ({metriques['taux_faux_positifs']:.2f}%)  ",
        "",
        "---",
        "",
        "## 2. Scores globaux",
        "",
        f"| Métrique | Valeur | Seuil | Statut |",
        f"|---------|--------|-------|--------|",
        f"| Taux PASS | {taux_pass:.1f}% | ≥ {seuils['taux_pass']}% | {'✅' if ok_pass else '❌'} |",
        f"| Taux FAIL | {taux_fail:.1f}% | ≤ {seuils['taux_fail']}% | {'✅' if ok_fail else '❌'} |",
        f"| Faux positifs dangereux | {faux_pos} | 0 | {'✅' if ok_danger else '❌'} |",
        f"| Score moyen | {score_moy}/100 | — | — |",
        f"| Score médian | {score_med}/100 | — | — |",
        f"| Score minimum | {score_min}/100 | — | — |",
        "",
        "---",
        "",
        "## 3. Scores par famille de handicap",
        "",
        "| Famille | N | PASS | WARN | FAIL | Score moy |",
        "|---------|---|------|------|------|-----------|",
    ]

    for famille, stats in sorted(metriques["par_famille"].items(), key=lambda x: -len(x[1]["scores"])):
        n_f = len(stats["scores"])
        sc = round(sum(stats["scores"]) / n_f, 1) if stats["scores"] else 0
        lines.append(f"| {famille} | {n_f} | {stats['pass']} | {stats['warn']} | {stats['fail']} | {sc} |")

    lines += [
        "",
        "---",
        "",
        "## 4. Scores par niveau de documentation",
        "",
        "| Niveau | N | PASS | WARN | FAIL | Score moy |",
        "|--------|---|------|------|------|-----------|",
    ]

    for doc_level in ["riche", "moyen", "pauvre"]:
        stats = metriques["par_doc"].get(doc_level, {"pass": 0, "warn": 0, "fail": 0, "scores": []})
        n_d = len(stats["scores"])
        if n_d == 0: continue
        sc = round(sum(stats["scores"]) / n_d, 1)
        lines.append(f"| {doc_level} | {n_d} | {stats['pass']} | {stats['warn']} | {stats['fail']} | {sc} |")

    # Top anomalies
    lines += [
        "",
        "---",
        "",
        "## 5. Top anomalies (checks en FAIL les plus fréquents)",
        "",
        "| # | Check | Occurrences |",
        "|---|-------|------------|",
    ]
    for i, (nom, count) in enumerate(metriques["top_anomalies"][:20], 1):
        lines.append(f"| {i} | `{nom}` | {count}/{n} ({round(count/n*100,1)}%) |")

    # Droits oubliés non détectés
    lines += [
        "",
        "---",
        "",
        "## 6. Droits oubliés les plus souvent non détectés",
        "",
        "| # | Droit oublié | Non détecté N fois |",
        "|---|-------------|-------------------|",
    ]
    for i, (droit, count) in enumerate(metriques["top_oublies_non_detectes"][:20], 1):
        lines.append(f"| {i} | `{droit}` | {count} fois |")

    # Top profils fragiles
    lines += [
        "",
        "---",
        "",
        "## 7. Top 20 profils fragiles (score le plus bas)",
        "",
        "| ID | Famille | Doc | Score | Statut | Erreur |",
        "|----|---------|-----|-------|--------|--------|",
    ]
    for r in metriques["top_fragiles"][:20]:
        err = r.erreur[:40] if r.erreur else ""
        lines.append(f"| {r.profil_id} | {r.famille} | {r.niveau_doc} | {r.score} | {r.statut} | {err} |")

    # Recommandations
    lines += [
        "",
        "---",
        "",
        "## 8. Recommandations",
        "",
    ]

    if not ok_pass:
        lines.append(f"- **Taux PASS insuffisant** ({taux_pass:.1f}% < {seuils['taux_pass']}%) — vérifier les contrôles A1/A2 (détection droits).")
    if not ok_fail:
        lines.append(f"- **Trop de FAIL** ({taux_fail:.1f}% > {seuils['taux_fail']}%) — analyser les anomalies ci-dessus.")
    if not ok_danger:
        lines.append(f"- **{faux_pos} faux positif(s) dangereux** — droits incompatibles suggérés à score élevé. À corriger en priorité.")

    top_anom = metriques["top_anomalies"][:3]
    if top_anom:
        lines.append(f"- Anomalie la plus fréquente : `{top_anom[0][0]}` ({top_anom[0][1]} fois) — à investiguer.")

    top_oublies = metriques["top_oublies_non_detectes"][:3]
    if top_oublies:
        lines.append(f"- Droits oubliés les plus souvent ratés : {', '.join(f'`{d}`' for d, _ in top_oublies)} — améliorer la détection.")

    if not (ok_pass or ok_fail or ok_danger):
        lines.append("- **Décision : NE PAS DÉPLOYER** — corriger les anomalies critiques avant production.")
    elif ok_pass and ok_fail and ok_danger:
        lines.append("- **Décision : VALIDÉ** — Facilim passe les tests massifs aux seuils requis.")

    # Décision finale
    lines += [
        "",
        "---",
        "",
        f"## Décision finale : {decision}",
        "",
        f"| Critère | Résultat | Seuil | OK |",
        f"|---------|---------|-------|-----|",
        f"| PASS ≥ {seuils['taux_pass']}% | {taux_pass:.1f}% | {seuils['taux_pass']}% | {'✅' if ok_pass else '❌'} |",
        f"| FAIL ≤ {seuils['taux_fail']}% | {taux_fail:.1f}% | {seuils['taux_fail']}% | {'✅' if ok_fail else '❌'} |",
        f"| 0 proposition dangereuse | {faux_pos} | 0 | {'✅' if ok_danger else '❌'} |",
        "",
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────────────────────

def main():
    global _profils_cache

    parser = argparse.ArgumentParser(description="QA-5 — Simulateur massif MDPH")
    parser.add_argument("--n",    type=int, default=100,  help="Nombre de dossiers (défaut 100)")
    parser.add_argument("--seed", type=int, default=42,   help="Seed aléatoire (défaut 42)")
    parser.add_argument("--save", action="store_true",    help="Sauvegarder le rapport")
    parser.add_argument("--verbose", action="store_true", help="Afficher le détail des FAIL")
    args = parser.parse_args()

    n, seed = args.n, args.seed
    seuils = _seuils_pour_n(n)

    print(f"QA-5 — Simulateur massif : {n} dossiers (seed={seed})")
    print(f"Seuils : PASS ≥ {seuils['taux_pass']}% · FAIL ≤ {seuils['taux_fail']}%")
    print()

    # Génération
    t0 = time.time()
    print(f"[1/3] Génération des profils synthétiques...")
    profils = generer_profils(n=n, seed=seed)
    _profils_cache = profils
    dist = distribution_familles(profils)
    print(f"  {len(profils)} profils générés — top familles : " +
          ", ".join(f"{f}={c}" for f, c in list(dist.items())[:5]))

    # Pipeline
    print(f"\n[2/3] Exécution du pipeline ({n} dossiers)...")
    resultats: list[DossierResult] = []
    errors = 0
    for i, profil in enumerate(profils):
        r = executer_pipeline(profil)
        resultats.append(r)
        if r.erreur:
            errors += 1
        if (i + 1) % max(1, n // 10) == 0:
            nb_p = sum(1 for x in resultats if x.statut == "PASS")
            nb_f = sum(1 for x in resultats if x.statut == "FAIL")
            print(f"  [{i+1:>4}/{n}] PASS:{nb_p} FAIL:{nb_f} erreurs:{errors}")

    t1 = time.time()
    duree = round(t1 - t0, 1)
    print(f"\n  ✅ Pipeline terminé en {duree}s ({duree/n*1000:.0f}ms/dossier)")

    # Analyse
    print(f"\n[3/3] Analyse des résultats...")
    metriques = analyser_resultats(resultats)

    # Affichage console
    sep = "─" * 60
    print(f"\n{sep}")
    print(f"  RÉSULTATS QA-5 — {n} dossiers (seed={seed})")
    print(sep)
    print(f"  PASS : {metriques['nb_pass']:>4} ({metriques['taux_pass']:5.1f}%) | seuil ≥ {seuils['taux_pass']}%  {'✅' if metriques['taux_pass'] >= seuils['taux_pass'] else '❌'}")
    print(f"  WARN : {metriques['nb_warn']:>4} ({metriques['taux_warn']:5.1f}%)")
    print(f"  FAIL : {metriques['nb_fail']:>4} ({metriques['taux_fail']:5.1f}%) | seuil ≤ {seuils['taux_fail']}%  {'✅' if metriques['taux_fail'] <= seuils['taux_fail'] else '❌'}")
    print(f"  Score moyen : {metriques['score_moy']}/100 · Médiane : {metriques['score_median']}/100 · Min : {metriques['score_min']}/100")
    print(f"  Faux positifs dangereux : {metriques['nb_faux_positifs']} {'✅' if metriques['nb_faux_positifs'] == 0 else '❌'}")
    print()

    # Top anomalies
    if metriques["top_anomalies"]:
        print("  Top 5 anomalies :")
        for nom, count in metriques["top_anomalies"][:5]:
            print(f"    {count:>4}x  {nom}")

    # Top droits oubliés non détectés
    if metriques["top_oublies_non_detectes"]:
        print("  Top 5 droits oubliés non détectés :")
        for droit, count in metriques["top_oublies_non_detectes"][:5]:
            print(f"    {count:>4}x  {droit}")

    # Verbose : détail des FAIL
    if args.verbose:
        fails = [r for r in resultats if r.statut == "FAIL"][:10]
        if fails:
            print(f"\n  Détail des {len(fails)} premiers FAIL :")
            for r in fails:
                print(f"    {r.profil_id} [{r.famille}] score={r.score}")
                if r.erreur:
                    print(f"      Erreur : {r.erreur}")
                for c in r.checks:
                    if c.statut == "FAIL":
                        print(f"      FAIL {c.nom}: {c.detail[:60]}")

    # Décision
    ok = (metriques["taux_pass"] >= seuils["taux_pass"] and
          metriques["taux_fail"] <= seuils["taux_fail"] and
          metriques["nb_faux_positifs"] == 0)
    decision = "✅ PASS" if ok else ("⚠️ WARN" if metriques["taux_fail"] <= seuils["taux_fail"] else "❌ FAIL")
    print(f"\n  Décision QA-5 ({n} dossiers) : {decision}")
    print(sep)

    # Sauvegarde rapport
    if args.save:
        rapport_md = generer_rapport_md(metriques, seed, n, duree, seuils)
        out_dir = Path("app/tests/qa/reports")
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        path = out_dir / f"massive_qa_{n}_{ts}.md"
        path.write_text(rapport_md, encoding="utf-8")
        print(f"\n  Rapport : {path}")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
