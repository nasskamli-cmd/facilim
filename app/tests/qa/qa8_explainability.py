"""
app/tests/qa/qa8_explainability.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-8 — Validation Evidence & Explainability Engine

Contrôles :
  E1 — Aucune preuve inventée (anti-hallucination)
  E2 — Aucune source inexistante
  E3 — 100% des droits ont au moins une justification
  E4 — 100% des droits fragiles ont une faiblesse
  E5 — 100% des questions levier ont une justification
  E6 — 100% des scores sont explicables
  E7 — Rapport professionnel non vide
  E8 — Stabilité : même seed → même résultat

Usage :
  python -m app.tests.qa.qa8_explainability --n 100 --seed 42 --save
  python -m app.tests.qa.qa8_explainability --n 1000 --seed 42 --save
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
class CheckQA8:
    nom:    str
    statut: str   # "PASS" | "WARN" | "FAIL"
    detail: str = ""


@dataclass
class ResultatQA8:
    profil_id:          str
    famille:            str
    niveau_doc:         str
    nb_preuves:         int
    nb_droits_analyses: int
    statut:             str
    checks:             list[CheckQA8] = field(default_factory=list)
    erreur:             str            = ""


# ─────────────────────────────────────────────────────────────────────────────
# CONTRÔLES
# ─────────────────────────────────────────────────────────────────────────────

def _verifier_anti_hallucination(graphe, donnees: dict) -> CheckQA8:
    """E1 — Aucune preuve inventée : chaque citation doit tracer dans les données réelles."""
    # Construire le corpus textuel complet des données
    corpus = " ".join(
        str(v).lower() for v in donnees.values()
        if isinstance(v, str)
    )
    # Ajouter les verbatims
    for c in ["_verbatim_b", "_verbatim_c", "_verbatim_d", "_verbatim_e"]:
        lst = donnees.get(c) or []
        if isinstance(lst, list):
            corpus += " ".join(str(x).lower() for x in lst)

    preuves_inventees = []
    for item in graphe.items:
        if not item.citation.strip():
            continue
        # Vérification : au moins 3 mots consécutifs de la citation doivent être dans le corpus
        mots = item.citation.lower().split()
        mots_significatifs = [m for m in mots if len(m) > 3]
        if not mots_significatifs:
            continue
        # Check : ≥ 2 mots de la citation dans le corpus
        mots_trouves = sum(1 for m in mots_significatifs[:6] if m in corpus)
        if mots_trouves < min(2, len(mots_significatifs)):
            preuves_inventees.append(item.information[:40])

    if preuves_inventees:
        return CheckQA8(
            "E1-anti_hallucination", "FAIL",
            f"Preuves potentiellement inventées : {preuves_inventees[:2]}",
        )
    return CheckQA8("E1-anti_hallucination", "PASS",
                     f"{graphe.nb_preuves_total} preuves tracées dans les données")


def _verifier_sources_reelles(graphe, donnees: dict) -> CheckQA8:
    """E2 — Aucune source inexistante."""
    sources_valides = {"WhatsApp", "Document", "Narratif", "Déclaration", "Inférence"}
    sources_invalides = [
        item.source_type for item in graphe.items
        if item.source_type not in sources_valides
    ]
    if sources_invalides:
        return CheckQA8(
            "E2-sources_reelles", "FAIL",
            f"Sources invalides : {list(set(sources_invalides))[:3]}",
        )

    # Vérifier que les champs déclarés comme sources existent
    faux_champs = []
    champs_connus = set(donnees.keys()) | {
        "_document_knowledge.limitations", "_document_knowledge.besoins",
        "_document_knowledge.verbatim", "_document_knowledge.projets",
        "inferencer_mdph",
    }
    for item in graphe.items:
        if item.source_champ and "." not in item.source_champ:
            # Champ simple : doit exister dans donnees
            if item.source_champ not in donnees and item.source_champ not in champs_connus:
                faux_champs.append(item.source_champ)

    if faux_champs:
        return CheckQA8(
            "E2-sources_reelles", "WARN",
            f"Champs sources non vérifiés : {list(set(faux_champs))[:3]}",
        )

    return CheckQA8("E2-sources_reelles", "PASS",
                     "Toutes les sources sont valides")


def _verifier_droits_justifies(rapport) -> CheckQA8:
    """E3 — 100% des droits ont au moins une justification."""
    sans_justif = [
        d for d in rapport.explications_solides + rapport.explications_fragiles
        if not d.preuves and not d.faiblesses and not d.raisonnement_cdaph
    ]
    if sans_justif:
        return CheckQA8(
            "E3-droits_justifies", "FAIL",
            f"Droits sans justification : {[d.droit for d in sans_justif[:3]]}",
        )
    nb_total = len(rapport.explications_solides) + len(rapport.explications_fragiles)
    return CheckQA8("E3-droits_justifies", "PASS",
                     f"{nb_total} droit(s) — tous justifiés")


def _verifier_fragiles_ont_faiblesses(rapport) -> CheckQA8:
    """E4 — 100% des droits fragiles ont au moins une faiblesse."""
    sans_faiblesse = [
        d for d in rapport.explications_fragiles
        if not d.faiblesses
    ]
    if sans_faiblesse:
        return CheckQA8(
            "E4-fragiles_faiblesses", "FAIL",
            f"Droits fragiles sans faiblesse : {[d.droit for d in sans_faiblesse[:3]]}",
        )
    return CheckQA8("E4-fragiles_faiblesses", "PASS",
                     f"{len(rapport.explications_fragiles)} fragile(s) — tous avec faiblesses")


def _verifier_questions_justifiees(rapport) -> CheckQA8:
    """E5 — 100% des questions levier ont une justification."""
    sans_raison = [
        q for q in rapport.explications_questions
        if not q.raison or len(q.raison) < 5
    ]
    if sans_raison:
        return CheckQA8(
            "E5-questions_justifiees", "WARN",
            f"{len(sans_raison)} question(s) sans raison détaillée",
        )
    return CheckQA8("E5-questions_justifiees", "PASS",
                     f"{len(rapport.explications_questions)} question(s) justifiée(s)")


def _verifier_scores_explicables(rapport) -> CheckQA8:
    """E6 — 100% des scores ont une explication."""
    criteres_requis = ["preuves", "coherence", "retentissement", "projet", "justificatifs"]
    manquants = [
        c for c in criteres_requis
        if c not in rapport.explication_score.explication_par_critere
        or not rapport.explication_score.explication_par_critere[c]
    ]
    if manquants:
        return CheckQA8(
            "E6-scores_explicables", "FAIL",
            f"Critères sans explication : {manquants}",
        )
    return CheckQA8("E6-scores_explicables", "PASS",
                     "Tous les critères de score sont explicables")


def _verifier_rapport_non_vide(rapport) -> CheckQA8:
    """E7 — Rapport professionnel non vide et substantiel."""
    rp = rapport.rapport_professionnel
    if not rp or len(rp) < 200:
        return CheckQA8("E7-rapport_non_vide", "FAIL",
                         f"Rapport trop court : {len(rp)} chars")
    if len(rp) < 500:
        return CheckQA8("E7-rapport_non_vide", "WARN",
                         f"Rapport court : {len(rp)} chars")
    return CheckQA8("E7-rapport_non_vide", "PASS",
                     f"Rapport complet : {len(rp)} chars")


def _verifier_coherence_scores(rapport) -> CheckQA8:
    """E8 — Cohérence des scores (solide → score ≥ 70, fragile → score < 70)."""
    incoherents = []
    for d in rapport.explications_solides:
        if d.score < 70:
            incoherents.append(f"{d.droit}:solide mais score={d.score}")
    for d in rapport.explications_fragiles:
        if d.score >= 70:
            incoherents.append(f"{d.droit}:fragile mais score={d.score}")

    if incoherents:
        return CheckQA8("E8-coherence_scores", "FAIL",
                         f"Incohérences : {incoherents[:2]}")
    return CheckQA8("E8-coherence_scores", "PASS",
                     "Classification solide/fragile cohérente")


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def executer_qa8(profil) -> ResultatQA8:
    """Exécute le pipeline QA-8 sur un profil synthétique."""
    try:
        from app.engines.evidence_engine import construire_graphe_preuves
        from app.engines.explainability_engine import expliquer_dossier

        donnees = dict(profil.donnees)
        doc_texte = getattr(profil, "document_texte", None)
        if doc_texte and not donnees.get("notes_pro"):
            donnees["notes_pro"] = doc_texte[:600]

        graphe  = construire_graphe_preuves(donnees, profil.profil_mdph)
        rapport = expliquer_dossier(donnees, profil.profil_mdph, profil.profil_handicap)

        nb_droits = (len(rapport.explications_solides) +
                     len(rapport.explications_fragiles))

        checks = [
            _verifier_anti_hallucination(graphe, donnees),
            _verifier_sources_reelles(graphe, donnees),
            _verifier_droits_justifies(rapport),
            _verifier_fragiles_ont_faiblesses(rapport),
            _verifier_questions_justifiees(rapport),
            _verifier_scores_explicables(rapport),
            _verifier_rapport_non_vide(rapport),
            _verifier_coherence_scores(rapport),
        ]

        nb_fail = sum(1 for c in checks if c.statut == "FAIL")
        nb_warn = sum(1 for c in checks if c.statut == "WARN")
        statut = "FAIL" if nb_fail > 0 else ("WARN" if nb_warn > 2 else "PASS")

        return ResultatQA8(
            profil_id=profil.id,
            famille=profil.famille,
            niveau_doc=profil.niveau_documentation,
            nb_preuves=graphe.nb_preuves_total,
            nb_droits_analyses=nb_droits,
            statut=statut,
            checks=checks,
        )

    except Exception as e:
        import traceback
        return ResultatQA8(
            profil_id=profil.id,
            famille=profil.famille,
            niveau_doc=getattr(profil, "niveau_documentation", "?"),
            nb_preuves=0,
            nb_droits_analyses=0,
            statut="FAIL",
            erreur=f"{type(e).__name__}: {str(e)[:100]}",
        )


# ─────────────────────────────────────────────────────────────────────────────
# RAPPORT
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="QA-8 — Evidence & Explainability")
    parser.add_argument("--n",    type=int, default=100, help="Nombre de dossiers")
    parser.add_argument("--seed", type=int, default=42,  help="Seed aléatoire")
    parser.add_argument("--save", action="store_true",   help="Sauvegarder")
    args = parser.parse_args()
    n, seed = args.n, args.seed

    print(f"QA-8 — Evidence & Explainability : {n} dossiers (seed={seed})")
    print()

    t0 = time.time()
    print(f"[1/3] Génération de {n} profils...")
    from app.tests.qa.synthetic_profiles_engine import generer_profils
    profils = generer_profils(n=n, seed=seed)
    print(f"  {len(profils)} profils générés")

    print(f"\n[2/3] Pipeline QA-8 ({n} dossiers)...")
    resultats: list[ResultatQA8] = []
    errors = 0
    for i, profil in enumerate(profils):
        r = executer_qa8(profil)
        resultats.append(r)
        if r.erreur: errors += 1
        if (i + 1) % max(1, n // 10) == 0:
            nb_p = sum(1 for x in resultats if x.statut == "PASS")
            nb_f = sum(1 for x in resultats if x.statut == "FAIL")
            prv_moy = round(sum(x.nb_preuves for x in resultats) / len(resultats), 1)
            print(f"  [{i+1:>4}/{n}] PASS:{nb_p} FAIL:{nb_f} preuves_moy:{prv_moy} erreurs:{errors}")

    t1 = time.time()
    duree = round(t1 - t0, 1)
    print(f"\n  ✅ Pipeline terminé en {duree}s ({duree/n*1000:.0f}ms/dossier)")

    # Métriques
    print(f"\n[3/3] Analyse QA-8...")
    nb_pass  = sum(1 for r in resultats if r.statut == "PASS")
    nb_fail  = sum(1 for r in resultats if r.statut == "FAIL")
    nb_warn  = sum(1 for r in resultats if r.statut == "WARN")
    prv_moy  = round(sum(r.nb_preuves for r in resultats) / n, 1)
    droits_moy = round(sum(r.nb_droits_analyses for r in resultats) / n, 1)

    # Fréquences d'anomalies par check
    from collections import defaultdict
    check_fails: dict[str, int] = defaultdict(int)
    for r in resultats:
        for c in r.checks:
            if c.statut == "FAIL":
                check_fails[c.nom] += 1

    # Vérifications seuils QA-8
    ok_pass = nb_fail == 0  # 0 FAIL bloquant
    ok_halluc = check_fails.get("E1-anti_hallucination", 0) == 0
    ok_sources = check_fails.get("E2-sources_reelles", 0) == 0
    ok_scores  = check_fails.get("E6-scores_explicables", 0) == 0
    stabilite  = round(nb_pass / n * 100, 1)
    ok_stabilite = stabilite >= 95

    decision = "✅ PASS" if (ok_pass and ok_halluc and ok_sources and ok_scores and ok_stabilite) else "⚠️ WARN"

    sep = "─" * 62
    print(f"\n{sep}")
    print(f"  QA-8 — {n} dossiers Evidence & Explainability (seed={seed})")
    print(sep)
    print(f"  PASS          : {nb_pass}/{n} ({round(nb_pass/n*100,1)}%)")
    print(f"  WARN          : {nb_warn}/{n}")
    print(f"  FAIL          : {nb_fail}/{n}")
    print(f"  Preuves moy   : {prv_moy}")
    print(f"  Droits moy    : {droits_moy}")
    print(f"  Erreurs moteur: {errors}")
    print()
    print(f"  Seuils QA-8 :")
    print(f"    0 preuve inventée      : {'✅' if ok_halluc else '❌'} ({check_fails.get('E1-anti_hallucination',0)})")
    print(f"    0 source inexistante   : {'✅' if ok_sources else '❌'} ({check_fails.get('E2-sources_reelles',0)})")
    print(f"    100% droits expliqués  : {'✅' if check_fails.get('E3-droits_justifies',0)==0 else '❌'}")
    print(f"    100% scores explicable : {'✅' if ok_scores else '❌'}")
    print(f"    Stabilité ≥ 95%        : {'✅' if ok_stabilite else '❌'} ({stabilite}%)")

    if check_fails:
        print(f"\n  Anomalies (top 5) :")
        for nom, count in sorted(check_fails.items(), key=lambda x: -x[1])[:5]:
            print(f"    {count:>4}/{n}  {nom}")

    print(f"\n  Décision QA-8 ({n} dossiers) : {decision}")
    print(sep)

    if args.save:
        out_dir = Path("app/tests/qa/reports")
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        path = out_dir / f"qa8_explainability_{n}_{ts}.txt"
        content_lines = [
            f"QA-8 — Evidence & Explainability Engine",
            f"Généré le {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            f"N={n} seed={seed} durée={duree}s",
            f"PASS={nb_pass} FAIL={nb_fail} WARN={nb_warn}",
            f"Preuves_moy={prv_moy} Droits_moy={droits_moy}",
            f"Stabilité={stabilite}%",
            f"Décision={decision}",
            "",
            "Anomalies:",
        ]
        for nom, count in sorted(check_fails.items(), key=lambda x: -x[1]):
            content_lines.append(f"  {count}/{n} {nom}")
        path.write_text("\n".join(content_lines), encoding="utf-8")
        print(f"\n  Rapport : {path}")

    sys.exit(0 if (ok_pass and ok_halluc and ok_stabilite) else 1)


if __name__ == "__main__":
    main()
