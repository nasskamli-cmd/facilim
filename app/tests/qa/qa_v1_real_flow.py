"""
app/tests/qa/qa_v1_real_flow.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-V1-REAL-1→5 — FIX-VAGUE1-EXTRACTION-PERSISTENCE.

Teste le VRAI flux d'extraction (conversation → extract_structured_data_from_history
→ fusion synthèse), PAS l'injection directe. Le client LLM est mocké (pas de clé réelle) :
le mock simule la sortie d'un LLM correct ; les tests prouvent que :
  - le whitelist n'écarte PLUS les champs NIVEAU A (le bug corrigé) ;
  - le prompt d'extraction contient bien les formats Vague 1 (avq/droits) ;
  - la logique de fusion (orchestration) fait arriver les champs dans la synthèse ;
  - normaliser_collecte dérive droits_demandes depuis l'objet droits.

  QA-V1-REAL-1 : "pension d'invalidité catégorie 2" → pension_invalidite + categorie_invalidite
  QA-V1-REAL-2 : "CAF numéro 123456"               → organisme_payeur + numero_allocataire
  QA-V1-REAL-3 : "besoin d'aide pour m'habiller"   → avq_habillage
  QA-V1-REAL-4 : "je demande AAH et PCH"           → droits {aah, pch}
  QA-V1-REAL-5 : flux complet + normaliser_collecte → champs persistés + droits_demandes dérivé

Usage : python -m app.tests.qa.qa_v1_real_flow
"""

from __future__ import annotations
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import json
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./mdph_dossiers.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-key-32-chars-minimum-length-aaaa")
os.environ.setdefault("WHATSAPP_API_TOKEN", "test")
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy-key-for-tests-0000000000")
sys.path.insert(0, ".")

from app.engines.conversation_engine import extract_structured_data_from_history
from app.services.collecte_schema import normaliser_collecte


# ── Mock OpenAI : capture le prompt, renvoie une sortie LLM simulée ───────────
class _Msg:
    def __init__(self, content): self.content = content
class _Choice:
    def __init__(self, content): self.message = _Msg(content)
class _Resp:
    def __init__(self, content): self.choices = [_Choice(content)]
class _Completions:
    def __init__(self, payload, capture): self._payload = payload; self._capture = capture
    def create(self, model, messages, **kw):
        self._capture["prompt"] = messages[0]["content"]
        return _Resp(json.dumps(self._payload, ensure_ascii=False))
class _Chat:
    def __init__(self, payload, capture): self.completions = _Completions(payload, capture)
class _FakeClient:
    def __init__(self, payload, capture): self.chat = _Chat(payload, capture)


def _extract(payload, conversation, profil="adulte"):
    """Appelle la VRAIE fonction d'extraction avec un LLM mocké."""
    cap = {}
    client = _FakeClient(payload, cap)
    histo = [{"role": "user", "content": conversation}]
    out = extract_structured_data_from_history(histo, client, profil_mdph=profil)
    return out, cap.get("prompt", "")


# ── Fusion synthèse : RÉPLIQUE EXACTE d'orchestration_engine L493-508 ─────────
_CHAMPS_USAGER_PRIORITAIRE = {
    "souhait_orientation_usager", "projet_professionnel", "projet_de_vie",
    "situation_scolaire", "etablissement_scolaire", "attentes_usager",
    "qualification_section_c", "qualification_section_d", "formation_actuelle",
    "statut_emploi", "droits_demandes", "impact_quotidien",
}
def _fusionner(donnees: dict, nouvelles: dict) -> dict:
    d = dict(donnees)
    admin_pro = set(d.keys()) - _CHAMPS_USAGER_PRIORITAIRE - {"notes_pro", "_derniere_langue_detectee"}
    for k, v in nouvelles.items():
        if not v:
            continue
        if k in _CHAMPS_USAGER_PRIORITAIRE:
            d[k] = v
        elif k not in admin_pro:
            d[k] = v
    return d


def main():
    sep = "═" * 64
    print(sep); print("  QA-V1-REAL-1→5 — Vrai flux extraction/persistance Vague 1"); print(sep)
    res = {}

    # ── QA-V1-REAL-1 ──
    out, prompt = _extract(
        {"pension_invalidite": True, "categorie_invalidite": 2, "champ_bidon": "x"},
        "Je touche une pension d'invalidité catégorie 2",
    )
    r1 = (out.get("pension_invalidite") is True and out.get("categorie_invalidite") == 2
          and "champ_bidon" not in out)  # le filtre défensif rejette toujours l'inconnu
    res["QA-V1-REAL-1 — pension_invalidite + categorie_invalidite extraits (junk rejeté)"] = r1
    print(f"\n  REAL-1 : {out}")

    # ── QA-V1-REAL-2 ──
    out2, _ = _extract(
        {"organisme_payeur": "CAF", "numero_allocataire": "123456"},
        "Je suis à la CAF, numéro 123456",
    )
    r2 = (out2.get("organisme_payeur") == "CAF" and out2.get("numero_allocataire") == "123456")
    res["QA-V1-REAL-2 — organisme_payeur + numero_allocataire extraits"] = r2
    print(f"  REAL-2 : {out2}")

    # ── QA-V1-REAL-3 (+ vérif prompt contient les formats AVQ) ──
    out3, prompt3 = _extract(
        {"avq_habillage": "AIDE_PARTIELLE"},
        "J'ai besoin d'aide pour m'habiller",
    )
    prompt_ok = all(s in prompt3 for s in ["avq_habillage", "AIDE_PARTIELLE", "droits", "pension_invalidite"])
    r3 = (out3.get("avq_habillage") == "AIDE_PARTIELLE" and prompt_ok)
    res["QA-V1-REAL-3 — avq_habillage extrait + prompt contient les formats Vague 1"] = r3
    print(f"  REAL-3 : {out3} | prompt_formats={prompt_ok}")

    # ── QA-V1-REAL-4 (objet droits) ──
    out4, _ = _extract(
        {"droits": {"aah": True, "pch": True}},
        "Je demande l'AAH et la PCH",
    )
    r4 = (isinstance(out4.get("droits"), dict)
          and out4["droits"].get("aah") is True and out4["droits"].get("pch") is True)
    res["QA-V1-REAL-4 — objet droits.{aah,pch} extrait (survit au whitelist)"] = r4
    print(f"  REAL-4 : {out4}")

    # ── QA-V1-REAL-5 : flux complet → fusion synthèse → normaliser_collecte ──
    out5, _ = _extract(
        {"droits": {"aah": True, "pch": True}, "avq_repas": "AIDE_TOTALE",
         "organisme_payeur": "CAF"},
        "Je demande AAH et PCH, j'ai besoin d'aide totale pour les repas, je suis à la CAF",
    )
    synthese = {"nom_prenom": "DURAND Marie"}                 # synthèse existante
    synthese = _fusionner(synthese, out5)                     # fusion réelle (orchestration)
    persiste = (synthese.get("organisme_payeur") == "CAF"
                and synthese.get("avq_repas") == "AIDE_TOTALE"
                and isinstance(synthese.get("droits"), dict))
    norm = normaliser_collecte(synthese)                      # dérivation legacy
    dd = norm.get("droits_demandes", "").upper()
    r5 = (persiste and "AAH" in dd and "PCH" in dd)
    res["QA-V1-REAL-5 — flux complet : champs persistés + droits_demandes dérivé"] = r5
    print(f"  REAL-5 : synthese={ {k: synthese[k] for k in ('organisme_payeur','avq_repas','droits') if k in synthese} } | droits_demandes={norm.get('droits_demandes')!r}")

    print()
    for k, v in res.items():
        print(f"     {'✅' if v else '❌'} {k}")

    ok = all(res.values())
    print(f"\n{sep}")
    print(f"  DÉCISION QA-V1-REAL (1→5) : {'✅ PASS' if ok else '❌ FAIL'} ({sum(res.values())}/{len(res)})")
    print(sep)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
