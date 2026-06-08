# ARCHITECTURE_REELLE_FACILIM.md — Cartographie réelle (preuves de câblage)

**Généré le :** 2026-06-07
**Mode :** lecture seule. Câblage établi par les `import`/appels réels (numéros de ligne cités).

---

## COLLECTE
- **Agents** (`app/services/conversation/{adult,child,protected}_agent.py`) : un singleton par profil ; `CHECKLIST = checklist_for(profil)`. Question-driver dans `base.py._build_context` (L193-196) — **ne liste que les champs `requis=True`**.
- **conversation_engine** : `SYSTEM_PROMPT`/`REMINDER` + `extract_structured_data_from_history` (extraction) + whitelists + `_CHAMPS_NIVEAU_A` (1dccf6c). `CHECKLIST_MDPH*` = **parallèle déprécié** (refs internes uniquement).
- **collecte_schema** : source unique (`checklist_for`, `AVQ_CHAMPS`, `DROITS_KEYS`, `normaliser_collecte`).
- **orchestration_engine** : pilote le tour (`respond`), appelle l'extraction (L484, profil réel depuis 1dccf6c), fusionne dans `synthese_json` (L499-508).

## EXTRACTION
- **Whitelists** : `_CHAMPS_EXTRACTIBLES_ENFANT/ADULTE/MIXTE` + `_CHAMPS_NIVEAU_A` injecté à tous les profils via `_champs_extractibles` (L472-478).
- **Extraction LLM** : `extract_structured_data_from_history` (prompt strict + formats Vague 1 ; filtre défensif L530-537).
- **Normalisation** : `normaliser_collecte` (droits.* → droits_demandes) appelée au **moment du CERFA/cockpit** (v2_bridge, facilim_prod, field_mapper).

## SYNTHÈSE
- **synthese_json** : état consolidé (réponses extraites + fusion). Source de TOUT l'aval.
- **Enrichissements** : `_document_knowledge` (document_functional_extractor, upload), `_verbatim_*`, `texte_b/c/d/e` (cerfa_narrative_engine — colonnes dédiées), `analyse_situation_json`, `cockpit_pro_json`.
- **Dérivations** : `droits_demandes` (depuis droits.*), `description_situation` P8 (depuis difficultes/besoins).

## MOTEURS

| MOTEUR | EXISTE | APPELÉ | VISIBLE | UTILISÉ | Preuve d'appel |
|---|---|---|---|---|---|
| conversation_engine | ✅ | ✅ | — | ✅ | orchestration |
| orchestration_engine | ✅ | ✅ | — | ✅ | main (webhook) |
| collecte_schema | ✅ | ✅ | — | ✅ | agents |
| facilim_prod | ✅ | ✅ | — | ✅ | orchestration L1063 |
| eligibilite_droits | ✅ | ✅ | cockpit (droits) | ✅ | facilim_prod L249 |
| cdaph_strategy | ✅ | ✅ | cockpit (score) | ✅ | facilim_prod L242 + cockpit L411 |
| evidence_engine | ✅ | ✅ | cockpit (preuves) | ✅ | facilim_prod L221 + cockpit L412 |
| dossier_strength | ✅ | ✅ | score robustesse | ✅ | via strategie_dossier L34 |
| strategie_dossier | ✅ | ✅ | — | ✅ | facilim_prod L256 |
| completeness_engine | ✅ | ✅ | — | ✅ | facilim_prod L228 |
| refusal_risk | ✅ | ✅ | — | ✅ | facilim_prod L235 |
| human_validation | ✅ | ✅ | cockpit (validation) | ✅ | facilim_prod L263 + cockpit L409 |
| pre_submission | ✅ | ✅ | gate | ✅ | facilim_prod L270 |
| action_plan | ✅ | ✅ | cockpit (plan) | ✅ | facilim_prod L277 |
| priorisation | ✅ | ✅ | — | ✅ | action_plan L25 / parcours L28 |
| parcours_engine | ✅ | 🟡 conditionnel | — | 🟡 | facilim_prod L285 |
| cerfa_gate | ✅ | ✅ | dashboard (gate) | ✅ | facilim_prod L292 |
| cerfa_filler (V2) | ✅ | ✅ | CERFA PDF | ✅ | v2_bridge L396 |
| v2_bridge | ✅ | ✅ | CERFA | ✅ | main `_generer_cerfa_pdf` |
| field_mapper (V3) | ✅ | 🟡 fallback | CERFA (fallback) | 🟡 | facilim_prod L302 / fallback |
| professional_cockpit | ✅ | ✅ | dashboard | ✅ | facilim_prod L320 |
| audit_trail | ✅ | ✅ | historique | ✅ | facilim_prod L310 |
| pro_report | ✅ | 🟡 conditionnel | — | 🟡 | facilim_prod L328 |
| inferencer_mdph | ✅ | ✅ | alertes | ✅ | evidence L341 + orch L602 |
| profil_handicap | ✅ | ✅ | contexte questions | ✅ | orch L759 |
| profil_specifique | ✅ | ✅ | questions ciblées | ✅ | base.py L155 |
| questions_levier | ✅ | ✅ | cockpit (questions) | ✅ | cockpit L416 |
| justificatifs | ✅ | ✅ | — | ✅ | cdaph L328 |
| cerfa_quality_agent | ✅ | ✅ | qualité | ✅ | orch L924 |
| cerfa_narrative_engine | ✅ | ✅ | texte_b/c/d/e | ✅ | orch L923 |
| comite_agents | ✅ | 🟡 route main L2041 | NON VÉRIFIÉ | NON VÉRIFIÉ | route dédiée — usage flux non tracé |
| rules_engine | ✅ | ❓ aucun consommateur trouvé | — | NON VÉRIFIÉ | POSSIBLE orphelin |
| conversation_engine.`CHECKLIST_MDPH*` | ✅ | refs internes seules | — | POSSIBLE non utilisé | déprécié (collecte_schema actif) |

## CERFA — chemin réel
```
collecte (synthese_json)
  → v2_bridge.synthese_to_v2_dossier  (normaliser_collecte ; identité fine ; avq_* propagés [1dccf6c])
  → cerfa_filler.remplir_cerfa (V2)   (cases AVQ depuis avq_* ; droits depuis droits_demandes ; P8 = description_situation imprimé)
  → PDF
  [fallback V3 field_mapper si V2 lève — AVQ par mots-clés, NON assaini]
```

## COCKPIT
- **Score affiché** = `rapport_cdaph.score_solidite` (`professional_cockpit_engine.generer_cockpit` L427).
- **Provenance** : CDAPH (cdaph_strategy) + evidence + questions_levier + human_validation.
- **Dépendances** : cdaph_strategy, evidence_engine, questions_levier_engine, human_validation_engine ; alimenté par `synthese_json` (donc par l'extraction).

---

*Câblage établi par imports/appels réels. Statuts 🟡/NON VÉRIFIÉ explicités. Aucune modification.*
