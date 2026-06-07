"""
app/tests/qa/qa_schema_vague1.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-SCHEMA-1→5 — Vague 1 (NIVEAU A) : checklist unique + champs structurés bout-en-bout.

  QA-SCHEMA-1 : structure — checklist unique (agents = checklist_for), NIVEAU A présent, pas de doublon, modèle parallèle déprécié.
  QA-SCHEMA-2 : collecte — les nouveaux ids existent ; is_complete INCHANGÉ (NIVEAU A non requis).
  QA-SCHEMA-3 : synthèse — normaliser_collecte : droits.* → droits_demandes ; champs structurés préservés ; idempotent.
  QA-SCHEMA-4 : cockpit — facilim_prod consomme un dossier structuré (cockpit généré).
  QA-SCHEMA-5 : CERFA — build_field_map mappe avq_* → P6/P7, droits.* → P17, prenom/nom_naissance → P2.

Usage : python -m app.tests.qa.qa_schema_vague1
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

from app.services.collecte_schema import checklist_for, normaliser_collecte, AVQ_CHAMPS
from app.services.conversation.adult_agent import adult_agent as AG
from app.services.conversation.child_agent import child_agent as CG
from app.services.conversation.protected_agent import protected_agent as PG
from app.engines.pdf.field_mapper import build_field_map

NIVEAU_A_IDS = ["prenom", "nom_naissance", "organisme_payeur", "numero_allocataire",
                "pension_invalidite", "categorie_invalidite", "accident_travail",
                "maladie_professionnelle", "taux_ipp"] + AVQ_CHAMPS


def ids(cl):
    return [c["id"] for c in cl]


def main():
    sep = "═" * 64
    print(sep); print("  QA-SCHEMA-1→5 — Vague 1 (NIVEAU A)"); print(sep)
    res = {}

    # ── QA-SCHEMA-1 : structure ──
    a_ids, c_ids, p_ids = ids(AG.CHECKLIST), ids(CG.CHECKLIST), ids(PG.CHECKLIST)
    s1 = (
        a_ids == ids(checklist_for("adulte"))
        and c_ids == ids(checklist_for("enfant"))
        and p_ids == ids(checklist_for("protege"))
        and all(x in a_ids for x in NIVEAU_A_IDS)
        and len(a_ids) == len(set(a_ids))   # pas de doublon
    )
    # modèle parallèle déprécié
    src_ce = open("app/engines/conversation_engine.py", encoding="utf-8").read()
    s1 = s1 and ("DÉPRÉCIÉ (Vague 1)" in src_ce)
    res["QA-SCHEMA-1 — checklist unique + NIVEAU A + parallèle déprécié"] = s1

    # ── QA-SCHEMA-2 : nouveaux champs + is_complete inchangé ──
    new_present = all(x in a_ids for x in NIVEAU_A_IDS)
    # dossier complet sur les ANCIENS requis (sans NIVEAU A) → is_complete True (NIVEAU A non requis)
    d_old_complet = {
        "nom_prenom": "DURAND Marie", "date_naissance": "01/01/1980", "genre": "F",
        "adresse_complete": "1 rue X 75000 Paris", "num_secu": "280017512300120",
        "telephone": "0600000000", "departement": "75", "situation_familiale": "celibataire",
        "enfants_a_charge": "0", "diagnostics": "X", "traitements": "Y",
        "medecin_traitant": "Dr Z", "impact_quotidien": "limitations", "historique_mdph": "1ere",
        "qualification_section_c": "non", "qualification_section_d": "non",
    }
    s2 = new_present and (AG.is_complete(d_old_complet) is True)
    res["QA-SCHEMA-2 — nouveaux champs présents + is_complete inchangé"] = s2

    # ── QA-SCHEMA-3 : normalisation ──
    n = normaliser_collecte({"droits": {"aah": True, "rqth": True, "cmi_invalidite": True},
                             "avq_toilette": "AIDE_TOTALE", "prenom": "Marie"})
    dd = n.get("droits_demandes", "").upper()
    s3 = ("AAH" in dd and "RQTH" in dd and "CMI" in dd
          and n.get("avq_toilette") == "AIDE_TOTALE" and n.get("prenom") == "Marie"
          and normaliser_collecte(n).get("droits_demandes", "").upper().count("AAH") == 1)  # idempotent
    res["QA-SCHEMA-3 — droits.* → droits_demandes + structurés préservés (idempotent)"] = s3

    # ── QA-SCHEMA-4 : cockpit ──
    try:
        from app.engines import facilim_prod
        d_cockpit = {"nom_prenom": "DURAND Marie", "date_naissance": "01/01/1980",
                     "departement": "75", "diagnostics": "lombalgie chronique",
                     "impact_quotidien": "ne peut rester debout",
                     "droits": {"aah": True, "rqth": True}}
        r = facilim_prod.run(d_cockpit, profil_mdph="adulte", generer_cerfa=False)
        ck = r.cockpit_professionnel()
        s4 = isinstance(ck, dict) and "droits_detectes" in ck and "decision" in ck
    except Exception as e:
        print("   QA-SCHEMA-4 exception:", e); s4 = False
    res["QA-SCHEMA-4 — dossier structuré → cockpit généré"] = s4

    # ── QA-SCHEMA-5 : CERFA ──
    fm = build_field_map({
        "nom_naissance": "DURAND", "prenom": "Marie", "departement": "75",
        "avq_toilette": "AIDE_TOTALE", "avq_repas": "DIFFICULTE", "avq_deplacements": "AIDE_PARTIELLE",
        "droits": {"aah": True, "pch": True, "rqth": True, "cmi_invalidite": True},
    }, service_type="adulte")
    s5 = (
        fm.get("Champ de texte P2 1") == "DURAND"
        and fm.get("Champ de texte P2 3") == "Marie"
        and fm.get("Case à cocher P6 B2") == "/Yes"   # toilette
        and fm.get("Case à cocher P6 B4") == "/Yes"   # repas
        and fm.get("Case à cocher P7 2") == "/Yes"    # déplacements
        and fm.get("Case à cocher P17 5") == "/Yes"   # AAH
        and fm.get("Case à cocher P17 6") == "/Yes"   # RQTH
        and fm.get("Case à cocher P17 2") == "/Yes"   # PCH
        and fm.get("Case à cocher P17 3") == "/Yes"   # CMI
    )
    res["QA-SCHEMA-5 — avq_*→P6/P7, droits.*→P17, prenom/nom→P2"] = s5

    print()
    for k, v in res.items():
        print(f"     {'✅' if v else '❌'} {k}")
    print(f"\n  Détails CERFA : P2 1={fm.get('Champ de texte P2 1')!r} P2 3={fm.get('Champ de texte P2 3')!r} "
          f"P6B2={fm.get('Case à cocher P6 B2')} P17 5={fm.get('Case à cocher P17 5')}")

    ok = all(res.values())
    print(f"\n{sep}")
    print(f"  DÉCISION QA-SCHEMA (1→5) : {'✅ PASS' if ok else '❌ FAIL'} ({sum(res.values())}/{len(res)})")
    print(sep)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
