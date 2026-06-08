# VAGUE1_PROD_VALIDATION_REPORT.md — Déploiement + validation terrain (Vague 1 NIVEAU A)

**Généré le :** 2026-06-07
**Périmètre :** Validation uniquement. Aucune nouvelle fonctionnalité, aucun nouveau champ, aucune Vague 1.x/2.
**Statut global :** 🟡 **DÉPLOYÉ + STABLE — en attente du rejeu réel** (ÉTAPES 1-4 prouvées ; ÉTAPES 5-9 à compléter après la conversation WhatsApp réelle).

---

## Tableau de bord de la preuve

| Critère | État | Preuve |
|---|---|---|
| Calculé | ✅ | QA-SCHEMA 5/5 |
| Câblé | ✅ | synthèse→cockpit→CERFA |
| Visible | ✅ | dashboard PROD-2/5 |
| QA locale | ✅ | 14/14 |
| **Déployé** | ✅ | commit `b0ba56b` / deployment `c074e8f9` Online |
| **Démarrage stable** | ✅ | `Application startup complete`, HTTP 200, 0 erreur |
| **Test réel — collecte** | ❌ | en attente rejeu utilisateur |
| **Synthèse enrichie réelle** | ❌ | en attente rejeu |
| **Dashboard enrichi réel** | ❌ | en attente rejeu |
| **CERFA enrichi réel** | ❌ | en attente rejeu |

---

## ÉTAPE 1 — DIAGNOSTIC AVANT DÉPLOIEMENT

### CE QUI EST MODIFIÉ
7 fichiers code : `app/engines/conversation_engine.py`, `app/engines/facilim_prod.py`, `app/engines/pdf/field_mapper.py`, `app/engines/pdf/v2_bridge.py`, `app/services/conversation/adult_agent.py`, `child_agent.py`, `protected_agent.py`.

### CE QUI SERA DÉPLOYÉ
- **Nouveaux** : `app/services/collecte_schema.py` (source unique : `checklist_for`, `normaliser_collecte`, `AVQ_*`, `DROITS_KEYS`), `app/tests/qa/qa_schema_vague1.py` (non chargé au runtime).
- **Modifiés** : 3 agents → `CHECKLIST = checklist_for(profil)` (mêmes champs requis) ; field_mapper/v2_bridge/facilim_prod → `normaliser_collecte` en entrée + lecture identité fine/AVQ ; conversation_engine → commentaire de dépréciation (no-op).
- **Impacts** : aucun changement de schéma ; aval (cockpit/CERFA/gate/audit) inchangé grâce à la normalisation rétro-compatible.

### RISQUE DE DÉPLOIEMENT
- **Migrations** : ✅ aucune nouvelle migration SQL (confirmé `git status`) → zéro risque schéma, pas de récidive du bug splitter.
- **Compatibilité** : NIVEAU A en `requis=False` → `is_complete` inchangé → fin de collecte identique ; `normaliser_collecte` idempotente.
- **Régression** : 14/14 QA locales PASS ; `collecte_schema` n'a aucun import lourd → pas de risque de chargement.

---

## ÉTAPE 2 — COMMIT
```
commit  b0ba56b553df8352c5be4432142e4646ed1e8a55
message Vague 1 - Collecte NIVEAU A : checklist unique + champs structures (identite/AVQ/droits/invalidite)
        14 files changed, 1342 insertions(+), 90 deletions(-)
```

---

## ÉTAPE 3 — DÉPLOIEMENT
```
deployment id  c074e8f9-d85a-4e6b-a703-09880dc0270c
statut         ● Online
URL            https://www.facilim.fr
build          OK (railway up --detach, build c074e8f9)
region         sfo
```

---

## ÉTAPE 4 — VÉRIFICATION DÉMARRAGE
Logs production :
```
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080
[MIGRATE] ... (deja appliquee)  ×11
Facilim -- Bilan des migrations  Appliquees : 0
[MIGRATE] SQLite : initialize_schema() OK
```
Contrôles : erreurs SQL ❌ aucune · erreurs migration ❌ aucune · traceback ❌ aucun · exceptions ❌ aucune. Santé HTTP : **200**.

### CE QUI EST PROUVÉ
Déploiement réussi du commit `b0ba56b` ; démarrage applicatif complet ; 0 migration appliquée (aucun changement de schéma) ; 0 erreur ; site répond HTTP 200.

### CE QUI EST DÉCLARÉ
Le code Vague 1 (checklist unique + champs structurés + normalisation) est désormais le code exécuté en production.

### CE QUI EST NON VÉRIFIÉ
Le comportement de collecte conversationnelle réel (le LLM pose-t-il les nouvelles questions ?) — exige une vraie conversation WhatsApp.

---

## ÉTAPE 5 — REJEU RÉEL TEST4  *(EN ATTENTE UTILISATEUR)*
Aucune simulation. Le rejeu doit être effectué par l'utilisateur sur WhatsApp.
- Dossier : `FAC-DOS-VKSP2HXQ` (ou nouveau dossier réel).
- À faire par l'utilisateur : dérouler une collecte complète puis générer le CERFA.

> **Note honnête :** les NIVEAU A sont en `requis=False`. Le LLM peut donc poser les questions AVQ/droits/invalidité **sans y être contraint** par `is_complete`. Si le rejeu montre que ces questions ne sont pas posées spontanément, la conclusion sera : structure en prod ✅ mais **collecte réelle à forcer** (promotion `requis` = réglage Vague 1.x, hors périmètre de cette mission).

---

## ÉTAPE 6 — ANALYSE LOGS  *(à compléter après rejeu)*
| Catégorie | Question | Observé |
|---|---|---|
| Collecte | Questions AVQ posées ? | _en attente_ |
| Collecte | Questions droits posées ? | _en attente_ |
| Collecte | Questions invalidité posées ? | _en attente_ |
| Collecte | Organisme payeur / allocataire demandés ? | _en attente_ |
| Progression | Atteint identité / santé / AVQ / droits ? | _en attente_ |
| Validation | Collecte se termine normalement ? | _en attente_ |

---

## ÉTAPE 7 — ANALYSE SYNTHÈSE  *(à compléter après rejeu)*
| Champ | Présent | Valeur |
|---|---|---|
| prenom | _?_ | |
| nom_naissance | _?_ | |
| sexe | _?_ | |
| nir | _?_ | |
| organisme_payeur | _?_ | |
| numero_allocataire | _?_ | |
| pension_invalidite | _?_ | |
| categorie_invalidite | _?_ | |
| avq_toilette | _?_ | |
| avq_habillage | _?_ | |
| avq_repas | _?_ | |
| avq_deplacements | _?_ | |
| avq_gestion_quotidienne | _?_ | |
| droits.* | _?_ | |

---

## ÉTAPE 8 — ANALYSE DASHBOARD  *(à compléter après rejeu)*
- Avant : ≈ 35 %
- Après : _en attente_
- Champs désormais visibles / sections enrichies / champs encore absents : _en attente_

---

## ÉTAPE 9 — ANALYSE CERFA  *(à compléter après rejeu)*
- Identité (prénom / nom / sexe / NIR) : _en attente_
- AVQ (issus `avq_*`) : _en attente_
- Droits (AAH / PCH / RQTH / CMI) : _en attente_
- Invalidité (pension / catégorie / AT-MP) : _en attente_

---

## ÉTAPE 10 — VERDICT (provisoire)

### CE QUI EST PROUVÉ
Vague 1 **déployée et stable** en production (commit `b0ba56b`, deployment `c074e8f9`, startup OK, HTTP 200, 0 erreur, 0 migration). Logique validée en local (QA-SCHEMA 5/5, non-régression 14/14).

### CE QUI EST DÉCLARÉ
Le code de collecte structurée (checklist unique + champs NIVEAU A + normalisation) est le code actif en prod.

### CE QUI EST NON VÉRIFIÉ
La **preuve terrain** : collecte réelle, synthèse enrichie réelle, dashboard réel, CERFA réel — tous en attente du rejeu WhatsApp utilisateur.

### RISQUE PRINCIPAL
Que le LLM ne pose pas spontanément les nouvelles questions (NIVEAU A `requis=False`) → champs structurés vides en pratique malgré le branchement correct. Si observé, correctif = promotion `requis` (Vague 1.x, hors périmètre).

### GOULOT D'ÉTRANGLEMENT
Le rejeu réel utilisateur : seule étape que l'agent ne peut exécuter.

### VAGUE 1 TERMINÉE ?
```
NON
```
**Justification :** selon les règles FACILIM, la Vague 1 n'est terminée que si déployée **ET** validée en terrain réel (collecte + synthèse + dashboard + CERFA observés sans régression). Déploiement + stabilité = ✅ prouvés ; preuve terrain = ❌ pas encore obtenue. Ce rapport sera complété (ÉTAPES 5-9 + verdict final) dès le rejeu réel.

---

*Validation uniquement. Aucun moteur FACILIM 60→100, gate, audit, historique, scoring, prompt modifié. Aucun champ ajouté.*
