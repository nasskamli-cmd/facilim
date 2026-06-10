# DEPLOY_VALIDATION_PRE_MANUAL_REPORT.md — Validation automatisée pré-test-manuel

**Généré le :** 2026-06-07
**Objet :** déploiement des commits locaux en production + validation automatique **complète** AVANT tout test WhatsApp manuel.
**Verdict global :** ✅ **GO pour test manuel** — toutes les validations automatiques passent ; aucun échec bloquant.

---

## 1. GIT — commits déployés
Branche `master` poussée sur `origin` (`https://github.com/nasskamli-cmd/facilim.git`).
Hash distant = local = **`1dccf6c`**. 5 commits livrés :
```
1dccf6c fix(collecte): persist Vague 1 NIVEAU A fields through extraction
7e04f89 fix(trust): prevent generated narratives from driving decisions
b0ba56b Vague 1 - Collecte NIVEAU A (checklist unique + champs structurés)
af1ecd9 fix(collecte): fin de collecte exige une collecte presque complète
5887b96 fix(cerfa): rétablir le moteur V2 + câblage FACILIM PROD 1→5
```
**Aucun artefact de test commité** : `storage/cerfa/*.pdf` et `app/tests/qa/reports/*.html` sont restés **non suivis / non stagés** (working tree uniquement). Confirmé par `git status`.

## 2. PUSH GitHub
`git push origin master` → `bf6012e..1dccf6c master -> master` (exit 0). Hash distant **`1dccf6c`**.

## 3. DÉPLOIEMENT Railway
`railway up --detach` → **deployment `d3587d13-3e9b-419d-93cf-97f77540bda6`** · statut **● Online** · URL https://www.facilim.fr · region sfo.

## 4. DÉMARRAGE PROD
```
INFO: Waiting for application startup.
INFO: Application startup complete.
INFO: Uvicorn running on http://0.0.0.0:8080
[MIGRATE] SQLite : initialize_schema() OK   |   Appliquées : 0
```
- ✅ `Application startup complete`
- ✅ 0 migration appliquée (aucune nouvelle SQL — conforme)
- ✅ **Aucune** erreur SQL / traceback / migration / `no such column` / exception
- ✅ HTTP **200** sur https://www.facilim.fr

## 5. VALIDATION QA (contre le code déployé `1dccf6c`, identique au local)
```
✅ qa_v1_real_flow        ✅ qa_prod_3
✅ qa_anti_contamination  ✅ qa_prod_4
✅ qa_schema_vague1       ✅ qa_prod_5
✅ qa_prod_1              ✅ qa_fix_test4_cerfa_v2
✅ qa_prod_2              ✅ qa_fix_test4_collecte
→ 10/10 PASS
```
(QA-V1-REAL 5/5, QA-ANTI 5/5, QA-SCHEMA 5/5 inclus.)

## 6. TEST AUTOMATISÉ — FLUX D'EXTRACTION (conversation simulée complète)
Conversation injectée (un seul message) : *« CAF n°123456, pension d'invalidité catégorie 2, aide habillage/repas/déplacements, demande AAH + PCH + RQTH »*.
Passage par le **vrai** `extract_structured_data_from_history` (LLM **mocké**) → fusion (réplique orchestration L493-508) → `normaliser_collecte`.

`synthese_json` obtenu — **tous présents** :
| Champ | Valeur |
|---|---|
| organisme_payeur | CAF ✅ |
| numero_allocataire | 123456 ✅ |
| pension_invalidite | True ✅ |
| categorie_invalidite | 2 ✅ |
| avq_habillage | AIDE_PARTIELLE ✅ |
| avq_repas | AIDE_TOTALE ✅ |
| avq_deplacements | AIDE_PARTIELLE ✅ |
| droits.aah / pch / rqth | True / True / True ✅ |
| droits_demandes (dérivé) | "AAH, PCH, RQTH" ✅ |

**Étape 6 = PASS.**

## 7. TEST AUTOMATISÉ — CERFA depuis synthèse structurée
CERFA V2 généré (`synthese_to_v2_dossier` → `remplir_cerfa`), relecture des champs via pypdf :
| Contrôle | Résultat |
|---|---|
| Prénom (P2 3) = "Marie" | ✅ |
| AVQ B2 habillage cochée (depuis `avq_habillage`) | ✅ |
| AVQ B3 repas cochée (depuis `avq_repas`) | ✅ |
| AVQ B4 déplacements cochée (depuis `avq_deplacements`) | ✅ |
| AVQ B1 toilette **NON** cochée (pas d'`avq_toilette`) | ✅ |
| Droits ≥ 3 cases P17/P18 (AAH/PCH/RQTH) | ✅ (P17×2 + P18×1) |

**Étape 7 = PASS.** Les cases AVQ proviennent **uniquement** des `avq_*` structurés.

## 8. TEST ANTI-INVENTION
Dossier avec narratif *« ne peut pas se lever seule, besoin d'aide toilette/habillage/repas »* **sans** `avq_*` :
- Cases AVQ P6 B1-B4 = **toutes décochées** ✅

**Étape 8 = PASS.** Aucune limitation AVQ inventée depuis le narratif.

---

## CE QUI EST PROUVÉ
- Déploiement réussi (`1dccf6c`, deployment `d3587d13`, Online, HTTP 200, démarrage propre, 0 erreur).
- 10/10 QA vertes contre le code déployé.
- **Flux extraction → synthèse opérationnel** : les champs NIVEAU A (organisme, allocataire, pension, catégorie, `avq_*`, objet `droits`) arrivent réellement dans `synthese_json` ; `droits_demandes` dérivé.
- **CERFA** : prénom correct ; cases AVQ pilotées **exclusivement** par `avq_*` ; droits AAH/PCH/RQTH cochés.
- **Anti-invention** confirmée : narratif seul → 0 case AVQ.

## CE QUI EST NON VÉRIFIÉ
- **Qualité d'extraction du LLM RÉEL** : les tests utilisent un LLM **mocké** (pas de clé OpenAI réelle en local). La **plomberie** (whitelist, prompt, fusion, persistance, mapping) est prouvée ; la capacité du modèle à mapper le langage naturel → niveaux AVQ / objet `droits` à partir d'une vraie conversation **n'est pas** prouvée. **C'est précisément l'objet du test manuel.**
- **Comportement en production réelle** (clé OpenAI prod active) : non observé end-to-end (volume prod inaccessible ; `railway ssh` bloqué, non contourné).
- **Fusion multi-tours de l'objet `droits`** (compléter sur plusieurs messages) : non couverte (limitation connue).

## ERREURS / GAPS TROUVÉS (non bloquants)
1. **`numero_allocataire` et `organisme_payeur` non mappés au CERFA par V2.** Ils sont désormais **persistés** dans `synthese_json` (sprint réussi), mais `v2_bridge.synthese_to_v2_dossier` **ne les propage pas** vers le dossier V2 → P2 13 reste vide, radio organisme non cochée. **Ce n'est pas une régression** (ils n'arrivaient jamais au CERFA auparavant). C'est un **gap de mapping résiduel**, hors périmètre de ce sprint (toucher `v2_bridge`/CERFA était exclu).
2. `pension_invalidite` / `categorie_invalidite` / `taux_ipp` persistés mais non écrits dans des cases CERFA dédiées (mapping V2 absent — même nature que #1).

## CORRECTIONS NÉCESSAIRES ÉVENTUELLES
- Aucune **corrective bloquante**. Les gaps #1/#2 sont des **extensions de mapping** (sprint futur « MAPPING-NIVEAU-A-CERFA », hors périmètre actuel) : propager `organisme_payeur`/`numero_allocataire`/`pension_invalidite`/`categorie_invalidite`/`taux_ipp` dans `v2_bridge` vers les champs/cases CERFA correspondants. À planifier séparément, **pas** maintenant.

## GO / NO GO pour test WhatsApp manuel
```
GO
```
**Justification :** déploiement stable, 10/10 QA, et les 3 tests d'intégration (extraction, CERFA, anti-invention) passent. Aucun test automatique n'a échoué → la règle « si un test échoue, pas de test manuel » n'est pas déclenchée. Le test manuel a désormais un **objectif précis et unique** : valider la **qualité d'extraction du LLM réel** en conversation WhatsApp (seul point NON VÉRIFIÉ critique). Surveiller en parallèle les gaps de mapping #1/#2 (allocataire/organisme/invalidité encore absents du CERFA).

---

*Validation pré-manuel. Déploiement réalisé (autorisé). Aucun nouveau développement hors périmètre ; gaps de mapping documentés mais non corrigés (hors scope). Vague 2 non lancée.*
