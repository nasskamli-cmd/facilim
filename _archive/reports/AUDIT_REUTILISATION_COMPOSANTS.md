# AUDIT_REUTILISATION_COMPOSANTS.md

**Généré le :** 2026-06-07 · lecture seule.
**Règle :** ne jamais recréer ce qui existe. Classement : EXISTE · UTILISÉ · NON UTILISÉ · ORPHELIN · DUPLIQUÉ.

## Modèles / schémas / JSON
| Élément | Classe | Note (réutilisable pour la couche de faits ?) |
|---|---|---|
| `synthese_json` | EXISTE · UTILISÉ | **Réutiliser** comme hôte du registre de faits (additif `faits[]`). |
| `_document_knowledge` (limitations/restrictions/besoins, taggé valeur+extrait) | EXISTE · UTILISÉ | **Réutiliser** : déjà {valeur, extrait_source} → proto-fait documentaire. |
| `evidence_engine.EvidenceItem` (origine: Narratif/Déclaration/Document) | EXISTE · UTILISÉ | **Réutiliser** : déjà une **traçabilité d'origine** → base du champ `source`. |
| `cockpit_pro_json`, `analyse_situation_json` | EXISTE · UTILISÉ | Consommateurs aval (figés) — à alimenter par faits plus tard. |
| `collecte_schema` (checklist unique + AVQ_*/DROITS_KEYS) | EXISTE · UTILISÉ | **Réutiliser** comme référentiel de domaines/champs. |
| `conversation_engine.CHECKLIST_MDPH*` | DUPLIQUÉ / déprécié | Ne pas réutiliser (parallèle de collecte_schema). |

## Moteurs / services
| Élément | Classe | Note |
|---|---|---|
| eligibility, cdaph, evidence, completeness, refusal_risk, strategie_dossier, dossier_strength, human_validation, pre_submission, action_plan, parcours, priorisation, cerfa_gate, audit_trail, professional_cockpit, pro_report, inferencer_mdph, profil_handicap, profil_specifique, questions_levier, justificatifs, cerfa_quality_agent | EXISTE · UTILISÉ (via `facilim_prod`) | **Conserver** — consommateurs ; aucun à recréer. |
| `cerfa_narrative_engine._prompt_section_b/c/d/e` (anti-invention) | EXISTE · UTILISÉ | Conserver (mise en forme de faits). |
| `cerfa_filler` _composer_description_p8 (amplificateur) | EXISTE · UTILISÉ (impression seule) | DUPLIQUÉ (philosophie ≠ narrative_engine) → rationaliser plus tard. |
| `cerfa_filler` V2 + `field_mapper` V3 | DUPLIQUÉ (2 mappers) | Conserver V2 (prod), V3 (fallback) ; ne pas recréer. |
| `human_validation_engine` + `cerfa_gate` | EXISTE · UTILISÉ | **Réutiliser** pour les états de validation des faits. |
| `rules_engine` | ORPHELIN (aucun consommateur trouvé) | À confirmer avant tout usage. |

## Tables
| Élément | Classe | Note |
|---|---|---|
| `dossiers` (colonnes synthese_json, cockpit_pro_json, analyse_situation_json, texte_b/c/d/e, score_completude, cerfa_*) | EXISTE · UTILISÉ | Hôte ; le registre de faits peut vivre dans `synthese_json` (pas de nouvelle table nécessaire au départ). |
| `audit_events`, `cerfa_audit_log` | EXISTE · UTILISÉ | **Réutiliser** pour l'historique/traçabilité des faits. |
| `pieces_justificatives` | EXISTE · UTILISÉ | Lien preuve↔document pour `source`/`citation`. |

## Conclusion de réutilisation
La couche de faits **n'exige aucun nouveau moteur ni nouvelle table** : elle réutilise `synthese_json` (hôte), `_document_knowledge` + `EvidenceItem` (proto-faits + origine), `collecte_schema` (référentiel), `human_validation`/`gate` (validation), `audit_events` (historique). **Le seul élément réellement absent = le format de fait unifié + le routage des extractions vers lui.**

---
*Lecture seule. Classements ORPHELIN/DUPLIQUÉ à confirmer avant toute action ; aucune suppression proposée.*
