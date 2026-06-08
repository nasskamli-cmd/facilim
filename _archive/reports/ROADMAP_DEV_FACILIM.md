# ROADMAP_DEV_FACILIM.md — Conduite de développement

**Généré le :** 2026-06-07
**Mode :** lecture seule / planification. Aucune modification, aucun déploiement.

---

## CE QUI EST PROUVÉ
- **Déploiement prod stable** (`d3587d13`, Online, HTTP 200, démarrage propre, 0 erreur SQL/migration).
- **CERFA V2** opérationnel en prod ; fallback V3 en place.
- **Anti-contamination (V2)** : narratifs retirés des décisions droits/score/AVQ (QA-ANTI 5/5).
- **Extraction/persistance NIVEAU A** : la plomberie fonctionne (whitelist + profil réel + prompt + fusion + normalisation) — QA-V1-REAL 5/5.
- **Collecte** : checklist unique (QA-SCHEMA 5/5).
- **Cockpit / gate / audit / historique** : QA-PROD 1→5 PASS.
- **Non-régression globale** : 10/10 sur la dernière passe.

## CE QUI EST NON VÉRIFIÉ
- **Qualité d'extraction du LLM réel** (mapping langage naturel → niveaux AVQ / objet `droits`) — testé en LLM **mocké** uniquement.
- **La collecte conversationnelle pose-t-elle les questions NIVEAU A ?** (champs `requis=False` → non listés par le pilote de questions `base.py`). **Risque #1 du CERFA à 35 %.**
- **Mapping CERFA** de `organisme_payeur`/`numero_allocataire`/`pension_invalidite`/`categorie_invalidite`/`taux_ipp` (V2 ne les écrit pas — prouvé : P2 13 vide).
- **Comportement bout-en-bout en production** (volume DB prod inaccessible ; `railway ssh` bloqué).
- **AVQ sur fallback V3** (mots-clés non assainis).
- **Fusion multi-tours de l'objet `droits`**.

## CE QU'IL NE FAUT PLUS DÉVELOPPER POUR L'INSTANT
- ❌ **Aucun nouveau moteur** tant que la Vague 1 n'est pas validée en terrain réel.
- ❌ **Vague 2** (sous aucun prétexte).
- ❌ Refonte `dossier_strength` (différée — c'est un indicateur, pas une décision droit/CERFA).
- ❌ Nouveau mapping CERFA spéculatif **avant** de savoir ce que le test terrain révèle.
- ❌ Toute « amélioration » d'un prompt métier sans point de rupture prouvé.

## PROCHAINES ÉTAPES APRÈS TEST TERRAIN
*(voir « PLAN APRÈS TEST TERRAIN » ci-dessous selon le résultat)*
1. Lire les logs prod du dossier réel (`[CONV]`, extraction, `[CERFA V2]`).
2. Croiser **déclaré vs synthese_json vs CERFA** (audit terrain).
3. Décider du sprint suivant **uniquement** sur preuve de rupture observée.

---

## RÈGLES DE DÉVELOPPEMENT À RESPECTER
1. **Jamais corriger un symptôme sans point de rupture** identifié (fichier/fonction/ligne).
2. **Jamais utiliser un narratif généré comme preuve** (score/droit/case/gate). Narratif = affichage/impression.
3. **Toute nouvelle donnée doit franchir 6 étapes** : collectée → extraite → persistée → visible → utilisée → testée. *(Leçon Vague 1 : une donnée définie mais non extraite est décorative.)*
4. **Aucun moteur nouveau** tant que Vague 1 terrain n'est pas validée.
5. **Aucun déploiement sans QA verte + rapport**.
6. **Aucun test manuel sans scénario + preuves attendues** définis à l'avance.
7. **Tout correctif a son QA dédié** (ex. `qa_v1_real_flow` pour 1dccf6c).
8. *(corollaire)* **Ne jamais conclure sur une hypothèse** : classer PROUVÉ / DÉCLARÉ / NON VÉRIFIÉ.

---

## PLAN APRÈS TEST TERRAIN

### ✅ Si test terrain PASS (extraction + CERFA corrects)
1. **Valider Vague 1** officiellement (terrain).
2. **Sprint MAPPING-NIVEAU-A-CERFA** : propager `organisme_payeur`/`numero_allocataire`/`pension_invalidite`/`categorie_invalidite`/`taux_ipp` dans `v2_bridge` → cases CERFA (gap #2/#3 connu).
3. **5 dossiers réels internes** (scénarios variés : adulte/enfant/protégé) avec preuves attendues.
4. **Préparation pilote ESSMS** (doc d'accompagnement, critères de succès).

### ❌ Si test terrain FAIL extraction (champs absents du synthese_json)
1. **Audit logs extraction LLM** : `[CONV] Champs rejetés`, `Extraction données échouée`, JSON produit.
2. **Vérifier la collecte** : l'agent pose-t-il les questions NIVEAU A ? (si `requis=False` bloque → sprint « promotion requis / SYSTEM_PROMPT »).
3. **Ajustement prompt extraction** (formats AVQ/droits) + **QA réelle ciblée** par champ défaillant.

### ❌ Si test terrain FAIL CERFA (synthese OK mais CERFA vide)
1. **Audit mapping V2** (`cerfa_filler` + `v2_bridge`) champ par champ.
2. **Sprint MAPPING-NIVEAU-A-CERFA** (organisme/allocataire/invalidité) + vérif chemin V2 vs fallback V3.
3. QA CERFA dédiée (lecture des champs PDF via pypdf, comme `qa_anti_contamination`).

### ❌ Si test terrain FAIL dashboard (synthese OK mais non affiché)
1. **Audit `synthese_json` → cockpit** (`professional_cockpit_engine` / route dashboard).
2. **Correction visibilité** (rendu des champs structurés dans le cockpit) + QA d'affichage.

---

## Priorité unique recommandée
**Faire le test terrain d'abord.** Tous les chantiers ci-dessus sont **conditionnés** au résultat. Le point de rupture #1 le plus probable (collecte NIVEAU A `requis=False` non sollicitée) se confirmera ou s'infirmera par l'observation des questions réellement posées en conversation.

---

*Roadmap conditionnelle au test terrain. Aucune action de développement engagée. Règles de confiance et de preuve gravées.*
