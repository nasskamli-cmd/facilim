"""
app/tests/qa/qa_trace_source_synthese.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA des traces [TRACE_SOURCE_SYNTHESE] / [TRACE_COLLECTE] — instrumentation source→synthese.

Vérifie l'OBSERVABILITÉ et le MASQUAGE (logs uniquement, aucun comportement).

  TEST 1 — Document seul : les clés extraites apparaissent dans la trace (valeurs médicales masquées).
  TEST 2 — WhatsApp seul : les clés admin/invalidité/droits apparaissent dans la trace.
  TEST 3 — Document + WhatsApp : la fusion contient les deux sources.
  TEST 4 — Champ vide existant : DÉMONTRE la sémantique réelle du merge document (`k not in synthese`).
  TEST 5 — Pas de fuite : aucune valeur sensible complète (NIR/tel/adresse/médical) dans les traces.

Usage : python -m app.tests.qa.qa_trace_source_synthese
"""

from __future__ import annotations
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./mdph_dossiers.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-key-32-chars-minimum-length-aaaa")
os.environ.setdefault("WHATSAPP_API_TOKEN", "test")
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy-key-for-tests-0000000000")
sys.path.insert(0, ".")

from app.engines.orchestration_engine import (
    _trace_mask_phone, _trace_mask_value, _trace_resume, _trace_extrait,
)


# Réplique EXACTE de la règle de merge document (orchestration : `if v and k not in synthese`)
def _merge_document(synthese: dict, extraits: dict) -> dict:
    s = dict(synthese)
    for k, v in extraits.items():
        if v and k not in s:
            s[k] = v
    return s


def main():
    sep = "═" * 64
    print(sep); print("  QA-TRACE-SOURCE-SYNTHESE — instrumentation source→synthese"); print(sep)
    res = {}

    # ── TEST 1 — Document seul ──
    extraits_doc = {
        "nom_prenom": "CECORA Marie-Christine",
        "impact_quotidien": "difficultés pour le ménage, fatigabilité, station debout limitée " * 6,
        "statut_emploi": "suivi équipe emploi France Travail",
        "diagnostics": "fatigue chronique " * 30,
    }
    line1 = _trace_extrait(extraits_doc)
    t1 = (all(k in line1 for k in extraits_doc)                       # clés présentes
          and "<" in line1 and "c>" in line1                          # médical masqué en longueur
          and "fatigue chronique fatigue chronique" not in line1)     # valeur médicale absente
    res["TEST 1 — Document : clés tracées, médical masqué"] = t1
    print(f"\n  TEST1 trace = {line1[:160]}")

    # ── TEST 2 — WhatsApp seul ──
    extraits_wa = {
        "organisme_payeur": "CAF",
        "numero_allocataire": "123456",
        "categorie_invalidite": 2,
        "droits": {"aah": True, "pch": True},
    }
    line2 = _trace_extrait(extraits_wa)
    t2 = ("organisme_payeur=CAF" in line2 and "numero_allocataire=123456" in line2
          and "categorie_invalidite=2" in line2 and "droits={aah,pch}" in line2)
    res["TEST 2 — WhatsApp : admin/invalidité/droits tracés"] = t2
    print(f"  TEST2 trace = {line2}")

    # ── TEST 3 — Document + WhatsApp (fusion) ──
    synthese = {}
    synthese = _merge_document(synthese, extraits_doc)   # source document
    synthese = _merge_document(synthese, extraits_wa)    # source whatsapp (complète)
    resume3 = _trace_resume(synthese)
    t3 = all(k in resume3 for k in ("nom_prenom", "organisme_payeur", "numero_allocataire", "droits"))
    res["TEST 3 — Fusion : les deux sources présentes"] = t3
    print(f"  TEST3 resume = {resume3}")

    # ── TEST 4 — Champ vide existant (sémantique merge document) ──
    synthese_vide = {"impact_quotidien": ""}                          # clé présente mais vide
    doc_reel = {"impact_quotidien": "difficultés ménage, fatigue importante"}
    apres = _merge_document(synthese_vide, doc_reel)
    valeur_ignoree = (apres.get("impact_quotidien") == "")            # restée vide → ignorée
    t4 = valeur_ignoree
    res["TEST 4 — Champ vide existant → valeur document IGNORÉE (observé)"] = t4
    print(f"  TEST4 : impact_quotidien après merge = {apres.get('impact_quotidien')!r} "
          f"→ {'IGNORÉ (clé présente même vide)' if valeur_ignoree else 'fusionné'}")

    # ── TEST 5 — Pas de fuite sensible ──
    sensibles = {
        "num_secu": "280017512300120",
        "telephone": "0612345678",
        "adresse_complete": "159 Bd Henri Barnier, 13015 Marseille",
        "diagnostics": "X" * 400,
        "organisme_payeur": "CAF",
    }
    blob = " | ".join([
        _trace_resume(sensibles),
        _trace_extrait(sensibles),
        _trace_mask_phone("0612345678"),
        _trace_mask_value("num_secu", "280017512300120"),
        _trace_mask_value("adresse_complete", sensibles["adresse_complete"]),
        _trace_mask_value("diagnostics", sensibles["diagnostics"]),
    ])
    fuites = [
        ("NIR complet", "280017512300120"),
        ("téléphone complet", "0612345678"),
        ("adresse complète", "159 Bd Henri Barnier"),
        ("médical long", "X" * 50),
    ]
    aucune_fuite = all(motif not in blob for _, motif in fuites)
    masque_ok = ("***" in blob and "****5678" in blob and "<400c>" in blob)
    t5 = aucune_fuite and masque_ok
    res["TEST 5 — Aucune fuite (NIR/tel/adresse/médical) + masquage OK"] = t5
    print(f"  TEST5 masquage : phone={_trace_mask_phone('0612345678')} nir={_trace_mask_value('num_secu','280017512300120')} "
          f"diag={_trace_mask_value('diagnostics','X'*400)}")
    if not aucune_fuite:
        for nom, motif in fuites:
            if motif in blob:
                print(f"     ⚠️ FUITE détectée : {nom}")

    print()
    for k, v in res.items():
        print(f"     {'✅' if v else '❌'} {k}")

    ok = all(res.values())
    print(f"\n{sep}")
    print(f"  DÉCISION QA-TRACE-SOURCE-SYNTHESE : {'✅ PASS' if ok else '❌ FAIL'} ({sum(res.values())}/{len(res)})")
    print(sep)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
