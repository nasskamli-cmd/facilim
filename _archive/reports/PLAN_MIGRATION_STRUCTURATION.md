# PLAN_MIGRATION_STRUCTURATION.md

**Généré le :** 2026-06-07 · planification seule (aucun code, aucun commit).
Migration **non-cassante**, additive, mesurable. Réutilise l'existant (cf. AUDIT_REUTILISATION).

## PHASE 1 — MESURE
- **Quoi** : harnais de traçabilité **hors-produit** ; export `synthese_json` réel (endpoint existant `GET /api/v1/dashboard/dossiers`) ; référentiel de faits « or » par dossier (CECORA, AIT ABBAS, +1).
- **Effort** : faible. **Risque** : nul (observation). **Dépendances** : accès lecture endpoint.
- **Preuves attendues** : taux source→fait actuel chiffré ; liste des faits perdus en texte par dossier.

## PHASE 2 — STRUCTURATION
- **Quoi** : format **FAIT FACILIM** (`synthese_json.faits[]`) ; router les **extractions existantes** (WA + document) pour émettre des faits {valeur, source, citation, confiance} — priorité Santé/Professionnels/Limitations/AVQ/Orientation. Champs legacy conservés (dérivés).
- **Effort** : moyen. **Risque** : moyen (qualité extraction LLM). **Dépendances** : Phase 1 (mesure de référence), `collecte_schema`, `_document_knowledge`, `EvidenceItem`.
- **Preuves attendues** : sur dossier réel, les faits riches apparaissent dans `faits[]` avec source+citation ; taux de structuration ↑ vs Phase 1.

## PHASE 3 — FUSION
- **Quoi** : règles enrichissement/correction/conflit/historique (sans écrasement) entre sources (WA + doc).
- **Effort** : moyen. **Risque** : moyen (conflits non résolus). **Dépendances** : Phase 2.
- **Preuves attendues** : deux sources sur un même champ → coexistence + historique, **aucune perte** ; cas « clé vide » ne bloque plus l'enrichissement.

## PHASE 4 — VALIDATION HUMAINE
- **Quoi** : états `extrait→proposé→validé_pro→validé_personne→rejeté` ; réutiliser `human_validation`/`gate` ; exposer les faits `proposé` au professionnel.
- **Effort** : moyen. **Risque** : charge de validation. **Dépendances** : Phase 3.
- **Preuves attendues** : un fait ne devient `validé` que par action humaine ; audit (qui/quand/source) par fait.

## PHASE 5 — CONSOMMATION PAR LE CERFA
- **Quoi** : cockpit, moteurs et CERFA lisent les **faits validés** (repli legacy pendant la transition) ; chaque champ/case = un fait tracé.
- **Effort** : moyen. **Risque** : régression CERFA si bascule trop tôt (→ repli legacy obligatoire). **Dépendances** : Phases 2-4.
- **Preuves attendues** : CERFA fidèle généré **depuis des faits validés**, complétude reflétant la couverture réelle, **sans narratif libre** ; chaque valeur traçable à sa source.

## Ordonnancement & garde-fous
- Strictement **séquentiel** ; chaque phase **mesurée** avant la suivante.
- **Non-cassant** : legacy maintenu jusqu'à Phase 5 validée.
- **Réutilisation** maximale (aucun nouveau moteur/table au départ).

---
*Plan de migration. Aucune implémentation engagée.*
