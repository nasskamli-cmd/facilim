"""
app/tests/qa/qa_anti_contamination.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-ANTI-1→5 — Sprint ANTI-CONTAMINATION NIVEAU CRITIQUE.

Vérifie que les narratifs générés (texte_b/c/d/e, description_situation) ne sont
PLUS utilisés comme source décisionnelle (droits, score, cases CERFA), tout en
restant imprimables.

  QA-ANTI-1 : CDAPH — invariance au narratif (un texte_b/e massif ne change pas le score).
  QA-ANTI-2 : eligibility — droits conservés à partir des preuves DÉCLARÉES (sans narratif).
  QA-ANTI-3 : CERFA — narratif "ne peut se lever seule / aide toilette…" SANS preuve → 0 case AVQ.
  QA-ANTI-4 : CERFA — avq_* structurés présents (sans narratif) → cases AVQ cochées.
  QA-ANTI-5 : CERFA — cas réel CECORA (faits déclarés + narratif inventé) → aucune AVQ inventée.

Usage : python -m app.tests.qa.qa_anti_contamination
"""

from __future__ import annotations
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import io
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./mdph_dossiers.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-key-32-chars-minimum-length-aaaa")
os.environ.setdefault("WHATSAPP_API_TOKEN", "test")
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy-key-for-tests-0000000000")
sys.path.insert(0, ".")

from app.engines.cdaph_strategy_engine import analyser_strategie_cdaph
from app.engines.eligibilite_droits_engine import analyser_eligibilite
from app.engines.pdf.v2_bridge import synthese_to_v2_dossier
from services.cerfa_filler import remplir_cerfa
from pypdf import PdfReader

AVQ_FIELDS = {
    "B1 toilette":   "Case à cocher P6 B1",
    "B2 habillage":  "Case à cocher P6 B2",
    "B3 repas":      "Case à cocher P6 B3",
    "B4 mobilité":   "Case à cocher P6 B4",
}


def _checked(fields, name) -> bool:
    if not fields or name not in fields:
        return False
    v = fields[name].get("/V")
    return v is not None and str(v) not in ("/Off", "", "None")


def _avq_coches(synthese: dict, service_type="adulte") -> dict:
    """Génère le CERFA V2 réel et relit l'état des cases AVQ P6 B1-B4."""
    dossier = synthese_to_v2_dossier(synthese, service_type)
    pdf = remplir_cerfa(dossier)
    fields = PdfReader(io.BytesIO(pdf)).get_fields()
    return {k: _checked(fields, fid) for k, fid in AVQ_FIELDS.items()}


def main():
    sep = "═" * 64
    print(sep); print("  QA-ANTI-1→5 — Sprint ANTI-CONTAMINATION"); print(sep)
    res = {}

    # ── QA-ANTI-1 : CDAPH invariant au narratif ──────────────────────────────
    d_pauvre = {"date_naissance": "01/01/1980", "departement": "75", "droits_demandes": "AAH"}
    d_narratif = {
        **d_pauvre,
        "texte_b_vie_quotidienne": "Je ne peux absolument rien faire seule, aide totale pour tout, "
                                   "ne peut pas se lever, besoin d'aide pour la toilette. " * 60,
        "texte_e_projet_vie": "projet de vie très détaillé et ambitieux. " * 60,
        "texte_d_situation_pro": "situation professionnelle complexe. " * 40,
    }
    s_pauvre = analyser_strategie_cdaph(d_pauvre, "adulte").score_solidite
    s_narratif = analyser_strategie_cdaph(d_narratif, "adulte").score_solidite
    a1 = (s_pauvre == s_narratif)
    res["QA-ANTI-1 — CDAPH invariant au narratif (score inchangé)"] = a1
    print(f"\n  QA-ANTI-1 : score sans narratif={s_pauvre} | avec narratif massif={s_narratif} "
          f"→ {'identique' if a1 else 'DIFFÉRENT (contamination !)'}")

    # ── QA-ANTI-2 : eligibility sur preuves déclarées (sans narratif) ─────────
    d_preuve = {
        "date_naissance": "01/01/1980", "departement": "75", "droits_demandes": "AAH",
        "diagnostics": "sclérose en plaques sévère, évolutive",
        "impact_quotidien": "inaptitude au travail, arrêt longue durée, "
                            "pension d'invalidité 2ème catégorie reconnue",
        # AUCUN texte_b/c/d/e
    }
    r2 = analyser_eligibilite(d_preuve, "adulte")
    aah = r2.analyses.get("AAH")
    a2 = bool(aah and aah.eligibilite_estimee > 0)
    res["QA-ANTI-2 — droits conservés depuis preuves déclarées (AAH>0)"] = a2
    print(f"  QA-ANTI-2 : AAH eligibilite_estimee={aah.eligibilite_estimee if aah else 'N/A'} "
          f"(narratif vide) → {'conservé' if a2 else 'PERDU'}")

    # ── QA-ANTI-3 : narratif inventé sans preuve → 0 case AVQ ─────────────────
    s3 = {
        "nom_prenom": "DUPONT Marie", "date_naissance": "01/01/1980", "departement": "75",
        "texte_b_vie_quotidienne": "Elle ne peut pas se lever seule, a besoin d'aide pour la "
                                   "toilette, l'habillage et pour préparer les repas.",
        # AUCUN avq_*, AUCUNE aide_humaine déclarée, AUCUN impact
    }
    c3 = _avq_coches(s3)
    a3 = not any(c3.values())
    res["QA-ANTI-3 — narratif inventé sans preuve → 0 case AVQ"] = a3
    print(f"  QA-ANTI-3 : cases AVQ = {c3} → {'aucune (OK)' if a3 else 'INVENTÉES (FAIL)'}")

    # ── QA-ANTI-4 : avq_* structurés (sans narratif) → cases cochées ──────────
    s4 = {
        "nom_prenom": "DUPONT Marie", "date_naissance": "01/01/1980", "departement": "75",
        "avq_toilette": "AIDE_TOTALE", "avq_repas": "DIFFICULTE",
        # PAS de narratif, avq_habillage/deplacements absents (doivent rester décochés)
    }
    c4 = _avq_coches(s4)
    a4 = (c4["B1 toilette"] and c4["B3 repas"] and not c4["B2 habillage"] and not c4["B4 mobilité"])
    res["QA-ANTI-4 — avq_* structurés → cases cochées (B1,B3) sans faux positif"] = a4
    print(f"  QA-ANTI-4 : cases AVQ = {c4} → {'structuré OK' if a4 else 'FAIL'}")

    # ── QA-ANTI-5 : cas réel CECORA — faits déclarés + narratif inventé ───────
    s5 = {
        "nom_prenom": "CECORA Marie-Christine", "date_naissance": "19/01/1966", "departement": "13",
        "impact_quotidien": "fatigabilité physique et émotionnelle, difficulté pour le ménage, "
                            "difficulté à maintenir une position debout prolongée, besoin de répit",
        "texte_b_vie_quotidienne": "Elle ne peut pas se lever seule, besoin d'aide pour la toilette, "
                                   "l'habillage et pour préparer les repas.",
        # AUCUN avq_* → aucune limitation AVQ ne doit être cochée
    }
    c5 = _avq_coches(s5)
    a5 = not any(c5.values())
    res["QA-ANTI-5 — CECORA : faits déclarés + narratif inventé → 0 AVQ inventée"] = a5
    print(f"  QA-ANTI-5 : cases AVQ = {c5} → {'aucune invention (OK)' if a5 else 'INVENTÉES (FAIL)'}")

    print()
    for k, v in res.items():
        print(f"     {'✅' if v else '❌'} {k}")

    ok = all(res.values())
    print(f"\n{sep}")
    print(f"  DÉCISION QA-ANTI (1→5) : {'✅ PASS' if ok else '❌ FAIL'} ({sum(res.values())}/{len(res)})")
    print(sep)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
