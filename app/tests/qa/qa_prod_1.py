"""
app/tests/qa/qa_prod_1.py
━━━━━━━━━━━━━━━━━━━━━━━━━
QA-PROD-1 — Test de câblage FACILIM PROD-1

Vérifie, sur des dossiers de test représentatifs, que la chaîne FACILIM 60→100
participe RÉELLEMENT au parcours :

  1. facilim_prod.run() est réellement exécuté          (résultat non nul)
  2. le cockpit professionnel est généré                (objet consolidé non vide)
  3. aucun moteur CRITIQUE n'est ignoré                 (aucun None parmi les critiques)
  4. aucun résultat n'est perdu                         (10 champs cockpit présents)

Sert aussi de mesure (Phase 5) : temps d'exécution, moteurs exécutés/ignorés.

Usage :
  python -m app.tests.qa.qa_prod_1
  python -m app.tests.qa.qa_prod_1 --save
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
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, ".")
os.environ.setdefault("DATABASE_URL", "sqlite:///./mdph_dossiers.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-key-32-chars-minimum-length!")
os.environ.setdefault("WHATSAPP_API_TOKEN", "test")

from app.engines import facilim_prod


# ─────────────────────────────────────────────────────────────────────────────
# PROFILS DE TEST (représentatifs — données figées, pas de hasard)
# ─────────────────────────────────────────────────────────────────────────────

PROFILS = [
    {
        "nom_test": "Karim — Accident du travail",
        "profil_mdph": "adulte",
        "profil_handicap": "moteur",
        "donnees": {
            "nom_prenom": "Karim NAIT ALI",
            "date_naissance": "1985-03-12",
            "departement": "93",
            "droits_demandes": ["RQTH", "AAH"],
            "impact_quotidien": "Douleurs chroniques lombaires depuis un accident du travail en 2019, "
                                "limitation de la marche et impossibilité de porter des charges.",
            "texte_b_vie_quotidienne": "M. NAIT ALI ne peut plus rester debout plus de 15 minutes. "
                                       "Il a besoin d'aide pour s'habiller le bas du corps les mauvais jours. "
                                       "Les déplacements extérieurs sont limités à de courtes distances.",
            "texte_d_situation_pro": "Sans emploi depuis 2020 après inaptitude. Souhaite une reconnaissance RQTH "
                                     "et envisage un bilan de compétences ESPO.",
            "notes_pro": "Bilan ESPO envisagé. Orientation reclassement à étudier.",
        },
    },
    {
        "nom_test": "Lucas — TSA enfant léger",
        "profil_mdph": "enfant",
        "profil_handicap": "tsa",
        "donnees": {
            "nom_prenom": "Lucas DURAND",
            "date_naissance": "2016-05-04",
            "departement": "75",
            "droits_demandes": ["AEEH"],
            "situation_scolaire": "Scolarisé en CE2 avec AESH 15h/semaine et tiers-temps aux évaluations.",
            "impact_quotidien": "Troubles de la communication sociale, besoin de routines, "
                                "difficultés de concentration en classe.",
            "texte_b_vie_quotidienne": "Lucas a besoin d'un cadre très structuré. Les transitions sont difficiles. "
                                       "Un accompagnement éducatif est en place.",
            "texte_c_scolarite": "AESH 15h, tiers-temps, suivi par le RASED. GEVASCO à compléter.",
            "notes_pro": "Orientation SESSAD à envisager. Parent ayant réduit son activité.",
        },
    },
    {
        "nom_test": "Profil SEP — Sclérose en plaques",
        "profil_mdph": "adulte",
        "profil_handicap": "maladie_chronique",
        "donnees": {
            "nom_prenom": "Sophie MARTIN",
            "date_naissance": "1980-09-21",
            "departement": "69",
            "droits_demandes": ["AAH", "CMI", "RQTH"],
            "impact_quotidien": "Sclérose en plaques évoluant par poussées. Fatigue invalidante, "
                                "troubles de l'équilibre, périodes de bons et de mauvais jours.",
            "texte_b_vie_quotidienne": "Les bons jours, Mme MARTIN est autonome. Les mauvais jours, elle ne peut "
                                       "pas se déplacer sans aide et reste alitée. La fatigue est imprévisible.",
            "texte_d_situation_pro": "En poste aménagé, difficultés croissantes. RQTH demandée pour maintien dans l'emploi.",
            "notes_pro": "Variabilité à documenter. CMI stationnement et priorité à étudier.",
        },
    },
    {
        "nom_test": "Profil aidant familial",
        "profil_mdph": "adulte",
        "profil_handicap": "",
        "donnees": {
            "nom_prenom": "Nadia BENALI",
            "date_naissance": "1975-11-02",
            "departement": "13",
            "droits_demandes": ["AAH"],
            "impact_quotidien": "Aidante de son fils en situation de handicap, a réduit son activité professionnelle "
                                "pour assurer l'accompagnement quotidien.",
            "texte_b_vie_quotidienne": "Mme BENALI consacre plusieurs heures par jour à l'accompagnement de son fils. "
                                       "Elle l'aide pour les actes essentiels et les rendez-vous médicaux.",
            "aidant_familial": "Oui — réduction d'activité professionnelle pour le rôle d'aidant.",
            "notes_pro": "Droit aidant (AVPF / AJPP) à signaler. Section F à renseigner.",
        },
    },
]

# Moteurs CRITIQUES : leur absence (None) = câblage défaillant
ATTRS_CRITIQUES = [
    ("evidence_engine",        "graphe_preuves"),
    ("completeness_engine",    "completude"),
    ("refusal_risk_engine",    "risques"),
    ("cdaph_strategy_engine",  "rapport_cdaph"),
    ("eligibilite_droits",     "eligibilite"),
    ("strategie_dossier",      "strategie"),
    ("human_validation",       "tableau_validation"),
    ("pre_submission",         "decision_presoumission"),
    ("action_plan",            "plan_action"),
    ("cerfa_gate",             "gate_cerfa"),
    ("professional_cockpit",   "cockpit"),
]

# Champs cockpit attendus (aucun ne doit manquer)
CHAMPS_COCKPIT = [
    "score_completude", "score_solidite", "decision", "risques_refus",
    "droits_detectes", "droits_oublies", "questions_roi",
    "pieces_prioritaires", "plan_action", "validation_humaine",
]


def tester_profil(p: dict) -> dict:
    t0 = time.time()
    resultat = facilim_prod.run(
        p["donnees"],
        profil_mdph=p["profil_mdph"],
        profil_handicap=p["profil_handicap"],
        generer_cerfa=False,
    )
    duree = round((time.time() - t0) * 1000)

    # 1. facilim_prod exécuté
    prod_execute = resultat is not None

    # 3. moteurs critiques
    moteurs_executes, moteurs_ignores = [], []
    for nom, attr in ATTRS_CRITIQUES:
        if getattr(resultat, attr, None) is not None:
            moteurs_executes.append(nom)
        else:
            moteurs_ignores.append(nom)

    # 2. cockpit généré + 4. aucun résultat perdu
    cockpit = resultat.cockpit_professionnel()
    cockpit_genere = bool(cockpit) and cockpit.get("cockpit_texte", "") != ""
    champs_manquants = [c for c in CHAMPS_COCKPIT if c not in cockpit]

    checks = {
        "prod_execute":        prod_execute,
        "cockpit_genere":      cockpit_genere,
        "aucun_critique_ignore": len(moteurs_ignores) == 0,
        "aucun_resultat_perdu": len(champs_manquants) == 0,
    }
    ok = all(checks.values())

    return {
        "nom": p["nom_test"],
        "ok": ok,
        "checks": checks,
        "duree_ms": duree,
        "moteurs_executes": moteurs_executes,
        "moteurs_ignores": moteurs_ignores,
        "champs_manquants": champs_manquants,
        "decision": cockpit.get("decision", "?"),
        "score_completude": cockpit.get("score_completude", 0),
        "score_solidite": cockpit.get("score_solidite", 0),
        "nb_droits_detectes": len(cockpit.get("droits_detectes", [])),
        "nb_droits_oublies": len(cockpit.get("droits_oublies", [])),
        "nb_actions": len(cockpit.get("plan_action", [])),
        "nb_questions": len(cockpit.get("questions_roi", [])),
        "nb_pieces": len(cockpit.get("pieces_prioritaires", [])),
        "gate_export": cockpit.get("gate_export", {}).get("autorise_export", None),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()

    sep = "═" * 64
    print(sep)
    print("  QA-PROD-1 — Test de câblage FACILIM PROD-1")
    print(sep)

    resultats = [tester_profil(p) for p in PROFILS]
    nb_ok = sum(1 for r in resultats if r["ok"])

    lignes_rapport = [
        "# QA-PROD-1 — Rapport de câblage FACILIM PROD-1",
        "",
        f"**Profils testés :** {len(resultats)}",
        f"**Résultat :** {nb_ok}/{len(resultats)} PASS",
        "",
        "| Profil | Câblage | Temps | Décision | Complét. | Solid. | Droits | Oubliés | Actions | Critiques ignorés |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]

    for r in resultats:
        statut = "✅ PASS" if r["ok"] else "❌ FAIL"
        print(f"\n  ── {r['nom']} ── {statut}")
        for nom_check, val in r["checks"].items():
            print(f"     {'✅' if val else '❌'} {nom_check}")
        print(f"     ⏱  {r['duree_ms']} ms | décision={r['decision']} | "
              f"complétude={r['score_completude']} | solidité={r['score_solidite']}")
        print(f"     moteurs exécutés : {len(r['moteurs_executes'])}/{len(ATTRS_CRITIQUES)} "
              f"| ignorés : {r['moteurs_ignores'] or 'aucun'}")
        print(f"     droits détectés={r['nb_droits_detectes']} oubliés={r['nb_droits_oublies']} "
              f"actions={r['nb_actions']} questions={r['nb_questions']} pièces={r['nb_pieces']} "
              f"gate_export={r['gate_export']}")

        lignes_rapport.append(
            f"| {r['nom']} | {'✅' if r['ok'] else '❌'} | {r['duree_ms']} ms | {r['decision']} | "
            f"{r['score_completude']} | {r['score_solidite']} | {r['nb_droits_detectes']} | "
            f"{r['nb_droits_oublies']} | {r['nb_actions']} | {r['moteurs_ignores'] or '—'} |"
        )

    print(f"\n{sep}")
    decision = "✅ PASS" if nb_ok == len(resultats) else "❌ FAIL"
    print(f"  DÉCISION QA-PROD-1 : {decision} ({nb_ok}/{len(resultats)})")
    print(sep)

    lignes_rapport += [
        "",
        f"## Décision : {decision}",
        "",
        "Contrôles par profil : (1) facilim_prod exécuté, (2) cockpit généré, "
        "(3) aucun moteur critique ignoré, (4) aucun résultat perdu (10 champs cockpit).",
        "",
        f"*Généré le {datetime.now().strftime('%Y-%m-%d %H:%M')} — sans LLM.*",
    ]

    if args.save:
        out_dir = Path("app/tests/qa/reports")
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        path = out_dir / f"qa_prod_1_{ts}.md"
        path.write_text("\n".join(lignes_rapport), encoding="utf-8")
        print(f"\n  Rapport : {path}")

    sys.exit(0 if nb_ok == len(resultats) else 1)


if __name__ == "__main__":
    main()
