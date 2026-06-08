# ANTI_CONTAMINATION_REPORT.md — Sprint ANTI-CONTAMINATION NIVEAU CRITIQUE

**Généré le :** 2026-06-07
**Périmètre :** droits (eligibility) + cockpit (CDAPH) + CERFA (AVQ). Aucune extension hors contamination.
**Statut :** ✅ **QA-ANTI 5/5 PASS · non-régression 14/14 PASS.** Non déployé.
**Règle appliquée :** un narratif généré peut être **affiché / imprimé**, mais **ne peut plus** servir de **preuve / score / détection de droit / cochage de case**.

---

## CE QUI A ÉTÉ MODIFIÉ

| # | Fichier | Fonction | Changement |
|---|---|---|---|
| 1 | `app/engines/eligibilite_droits_engine.py` | `_construire_texte` | **Retrait** de `texte_b/c/d/e` du blob décisionnel des 22 analyseurs de droits |
| 2 | `app/engines/cdaph_strategy_engine.py` | `_texte_complet` | **Retrait** de `texte_b/c/d/e` du blob de scoring |
| 2 | `app/engines/cdaph_strategy_engine.py` | `_evaluer_preuves` | Bonus de **longueur `texte_b` supprimé** → re-basé sur l'**impact_quotidien déclaré** |
| 2 | `app/engines/cdaph_strategy_engine.py` | `_evaluer_projet` | Bonus de **longueur `texte_e` supprimé** → re-basé sur le **projet déclaré** |
| 3 | `services/cerfa_filler.py` | bloc détection AVQ (`_detection_b2b3`) | **Retrait** de `description_situation` (narratif P8) **et** de `difficultes_quotidiennes` (aliasé sur `texte_b`) ; **ajout** lecture des `avq_*` structurés comme source officielle des cases P6 B1-B4 |
| 3 | `services/cerfa_filler.py` | bloc aide humaine (`_texte_aide_humaine`) | **Retrait** de `description_situation` et `difficultes_quotidiennes` de la détection P6 7 |
| 3+ | `app/engines/pdf/v2_bridge.py` | `synthese_to_v2_dossier` | **Ajout** : propagation des `avq_*` dans `donnees_structurees` (nécessaire pour que le filler V2 lise la preuve structurée — voir « Découverte ») |
| QA | `app/tests/qa/qa_anti_contamination.py` | **NOUVEAU** | QA-ANTI-1→5 |

### ⚠️ Découverte pendant l'implémentation (justifie 2 ajustements hors plan strict)
1. **`difficultes_quotidiennes` EST le narratif généré.** `v2_bridge` L234 : `cerfa_reponses["difficultes_quotidiennes"] = texte_b si présent`. Le champ que le plan croyait « déclaré » est en réalité `texte_b`. → il a fallu le **retirer aussi** de la détection AVQ (sinon `texte_b` y rentrait, en violation de la règle « ne plus lire texte_b »). Le narratif reste utilisé pour **imprimer** la page 8 (autorisé).
2. **`donnees_structurees` ne contenait pas les `avq_*`.** Sans propagation dans `v2_bridge`, la lecture `ds.get("avq_toilette")` aurait été **inerte** → fix factice. La propagation `avq_*` dans `v2_bridge` était **indispensable** pour que MOD 3 Part B fonctionne réellement. `v2_bridge` n'est pas un moteur 60→100 ni un fichier interdit ; c'est le pont de données alimentant `cerfa_filler`.

---

## CE QUI N'A PAS ÉTÉ MODIFIÉ
Conformément aux interdictions : **moteurs 60→100, cockpit (`professional_cockpit_engine`), gate (`cerfa_gate_engine`), evidence_engine, dossier_strength_engine, prompts, collecte, Vague 1 (`collecte_schema`, agents), migrations SQL** — aucun changement. Le **cockpit** est assaini **par héritage** (son score = score CDAPH désormais propre), sans modification de son code. Le narratif P8 (`_composer_description_p8`) reste **généré et imprimé** (seul son usage décisionnel a disparu).

---

## PREUVES AVANT / APRÈS

| Aspect | AVANT (contaminé) | APRÈS (corrigé) | Preuve |
|---|---|---|---|
| **Score CDAPH vs narratif** | `len(texte_b)` ajoutait jusqu'à +30 ; un narratif massif gonflait le score | **score identique avec/sans narratif massif** (22 = 22) | QA-ANTI-1 |
| **Cases AVQ depuis narratif** | « ne peut se lever seule / aide toilette » (généré) → cases P6 cochées (cf. AUDIT_TRACABILITE) | **0 case** AVQ depuis le narratif | QA-ANTI-3, QA-ANTI-5 |
| **Cases AVQ depuis structuré** | dépendaient du keyword sur texte généré | `avq_toilette=AIDE_TOTALE` → **B1 cochée** ; `avq_repas=DIFFICULTE` → **B3 cochée** ; B2/B4 **non** cochées (pas de faux positif) | QA-ANTI-4 |
| **Droits sans narratif** | dépendance partielle au narratif | **AAH eligibilite=52** à partir des seules preuves déclarées | QA-ANTI-2 |
| **Cas réel CECORA** | aide toilette/habillage/repas inventées | **aucune limitation AVQ inventée** (faits déclarés fatigue/ménage/station debout préservés en P8) | QA-ANTI-5 |

---

## QA-ANTI

```
✅ QA-ANTI-1 — CDAPH invariant au narratif (22 sans narratif == 22 avec narratif massif)
✅ QA-ANTI-2 — droits conservés depuis preuves déclarées (AAH eligibilite=52, narratif vide)
✅ QA-ANTI-3 — narratif "ne peut se lever seule/aide toilette" sans preuve → 0 case AVQ
✅ QA-ANTI-4 — avq_* structurés (sans narratif) → B1+B3 cochées, B2+B4 non (pas de faux positif)
✅ QA-ANTI-5 — CECORA : faits déclarés + narratif inventé → 0 AVQ inventée
DÉCISION : ✅ PASS (5/5)
```
QA-ANTI-3/4/5 génèrent le **vrai PDF V2** (`synthese_to_v2_dossier` → `remplir_cerfa`) et relisent l'état réel des cases P6 via pypdf (`/V`).

---

## NON-RÉGRESSION

```
✅ qa_anti_contamination     ✅ qa_prod_1
✅ qa_schema_vague1          ✅ qa_prod_2
✅ qa_fix_test4_cerfa_v2     ✅ qa_prod_3
✅ qa_fix_test4_collecte     ✅ qa_prod_4
✅ qa_validation_1_test4     ✅ qa_prod_5
✅ qa7_cdaph_runner          ✅ qa9_human_validation
✅ qa10_completeness         ✅ qa11_action_plan
→ 14/14 PASS
```
- **qa7_cdaph_runner PASS** (moteur CDAPH modifié) · **qa_fix_test4_cerfa_v2 PASS** (chemin cerfa_filler modifié, via stack complet) · **qa_schema_vague1 PASS** (Vague 1 intacte, chemin `avq_*` renforcé).
- **qa4_facilim60** : **non runnable** — exige une **clé OpenAI réelle** (« exécution impossible en mode réel »). Échec **pré-existant** confirmé par baseline (échoue à l'identique sans mes modifications), **indépendant** du sprint.
- **Méthode de preuve de non-régression :** `git stash` de mes 4 fichiers → les seuls échecs initiaux (qa_fix_test4_cerfa_v2, qa_prod_3/4/5, qa4_facilim60) échouaient **déjà à l'identique** sans mes changements → cause = **dépendances manquantes du venv** (`fastapi`, `pydantic-settings`, `requests`), pas ma logique. Après installation des dépendances du `requirements.txt`, 4 de ces 5 passent ; le 5ᵉ (qa4) reste bloqué par l'absence de clé OpenAI réelle.

---

## CE QUI EST PROUVÉ
- Aucun moteur critique ne raisonne plus sur `texte_b/c/d/e` (eligibility, CDAPH) : retrait vérifié + invariance de score (QA-ANTI-1).
- Les droits restent détectables à partir des preuves déclarées (QA-ANTI-2).
- Les cases AVQ proviennent des `avq_*` structurés (QA-ANTI-4), bout-en-bout via le vrai chemin V2 (v2_bridge → cerfa_filler).
- Le CERFA n'invente plus de limitations à partir d'un narratif (QA-ANTI-3, QA-ANTI-5).
- Le cockpit repose sur un score CDAPH assaini (héritage), sans modification du cockpit.
- Zéro régression (14/14 ; baseline prouve la neutralité du diff).

## CE QUI EST NON VÉRIFIÉ
- **En production** : non déployé (la prod conserve le comportement actuel jusqu'à `railway up`).
- **qa4_facilim60 / chaîne 60→100 en mode LLM réel** : non exécutable ici (clé OpenAI réelle absente).
- **Sur dossiers réels variés** : l'ampleur exacte de la baisse de score sur dossiers « pauvres en preuve » n'est pas instrumentée (attendu et voulu, mais non chiffré en prod).
- **Zone résiduelle** : `besoins_aide_str`/`aides_str` conservés dans la détection AVQ comme **déclaré** ; si une source amont y injectait un jour du généré, il faudrait re-auditer (non observé aujourd'hui).

## RISQUE PRINCIPAL RESTANT
**Sous-détection AVQ sur le chemin V2 pour les dossiers SANS `avq_*` structurés** (ex. anciens dossiers pré-Vague-1) : les cases ne se cochent plus sur narratif → elles ne se cocheront que si la collecte `avq_*` a eu lieu. C'est le comportement **voulu** (« case cochée uniquement si preuve structurée »), mais il **suppose que la collecte Vague 1 alimente bien `avq_*`** en conversation réelle — point déjà signalé comme NON VÉRIFIÉ (collecte WhatsApp live). Mitigation en place : détection structurée + aides déclarées (OR), QA-ANTI-4 garde-fou.

## GO / NO GO
```
GO
```
**Justification :** QA-ANTI 5/5 ✅ + non-régression 14/14 ✅ + aucune case AVQ légitime perdue (QA-ANTI-4) + QA-SCHEMA Vague 1 inchangée ✅ + génération V2 sans exception ✅. Les critères NO GO (perte d'une case AVQ structurée légitime ; régression sur dossier documenté ; QA-SCHEMA cassée) ne sont **pas** déclenchés.

**Réserve de déploiement :** déploiement à décider séparément (ce sprint = correction + preuve locale). À surveiller en prod : baisse attendue des scores cockpit/CDAPH sur dossiers pauvres en preuve, et bonne alimentation de `avq_*` par la collecte réelle.

---

## Note environnement (transparence)
Pour exécuter la non-régression complète, les dépendances projet manquantes du venv ont été installées (`fastapi`, `pydantic-settings`, `requests` + `requirements.txt`). **Aucun code FACILIM modifié** par cette installation. Python 3.14 (venv fraîchement (ré)installé) expliquait les `ModuleNotFoundError` initiaux.

---

*Sprint exécuté dans le périmètre droits/cockpit/CERFA. Moteurs 60→100, gate, evidence, dossier_strength, prompts, collecte, Vague 1, migrations : non modifiés. Non déployé.*
