# FORENSIC_ROOT_CAUSE_M30DPYEX.md — Cause racine unique (dossier témoin réel)

**Généré le :** 2026-06-07
**Mode :** FORENSIC, lecture seule. Aucun code, aucune correction, aucun déploiement.
**Témoin :** `FAC-DOS-M30DPYEX` · « En collecte » · **20/100** (capture dashboard) · CERFA `CF TEST FACILIM 5.pdf` · source bilan PCR CECORA.
**Règle :** aucune conclusion sur hypothèse ; PROUVÉ / DÉCLARÉ / NON VÉRIFIÉ.

---

## ⚠️ Plafond de preuve (honnêteté)
Indisponibles : **texte du chat WhatsApp**, **logs Railway** (non consultés, à votre demande), **`synthese_json` de prod** (`railway ssh` bloqué). Disponibles : **capture dashboard**, **CERFA (texte)**, **bilan PCR**, **code réellement exécuté**. La cause racine ci-dessous est démontrée par **le code + les artefacts** ; le **sous-pas exact défaillant** du pont de collecte nécessite une exécution instrumentée (cf. ÉTAPE 9).

---

## ÉTAPE 1 — CARTOGRAPHIE RÉELLE

| Étape | Existe | Appelée | Visible | Utilisée | Testée |
|---|---|---|---|---|---|
| WhatsApp (webhook) | ✅ | ✅ | — | ✅ | (mock QA) |
| Agent (base.py + collecte_schema) | ✅ | ✅ | — | ✅ | QA-SCHEMA |
| conversation_engine (extraction) | ✅ | ✅ | — | ✅ | QA-V1-REAL (mock) |
| orchestration (merge + persist) | ✅ | ✅ | — | ✅ | partiel |
| **synthese_json** | ✅ | ✅ | dashboard | ✅ **(source unique de vérité)** | — |
| dashboard | ✅ | ✅ | ✅ | ✅ | QA-PROD-2 |
| cockpit / moteurs | ✅ | ✅ | ✅ | ✅ | QA-PROD |
| CERFA (v2_bridge → cerfa_filler) | ✅ | ✅ | PDF | ✅ | QA-FIX-TEST4 |

**Fait structurant prouvé :** tout l'aval (dashboard, cockpit, CERFA) **lit `synthese_json`**. Si `synthese_json` est vide, tout l'aval est vide — indépendamment des correctifs CERFA/AVQ/anti-contamination.

---

## ÉTAPE 2 — TRAÇABILITÉ DES CHAMPS (témoin)

| Champ | Collecté | Demandé | Extrait | Persisté | Vis. dashboard | Vis. cockpit | Vis. CERFA |
|---|---|---|---|---|---|---|---|
| nom / prénom | NON VÉRIFIÉ | OUI (requis) | NON VÉRIFIÉ | mécanisme OUI | **NON** (absent) | NON VÉRIF | **NON** (absent formulaire) |
| date_naissance | NON VÉRIFIÉ | OUI (requis) | NON VÉRIFIÉ | OUI (méca) | **NON** (vide dashboard) | NON VÉRIF | **NON** |
| nir / num_secu | NON | OUI (requis) | NON VÉRIFIÉ | OUI (méca) | **NON** (vide) | NON VÉRIF | **NON** |
| adresse / CP / ville | NON VÉRIFIÉ | OUI (requis) | NON VÉRIFIÉ | OUI (méca) | NON VÉRIF | NON VÉRIF | **NON** |
| organisme_payeur | NON VÉRIFIÉ | partiel (prompt) | possible | OUI (méca) | non pondéré | NON VÉRIF | **NON** (v2_bridge ne mappe pas) |
| numero_allocataire | NON | NON (driver) | possible | OUI (méca) | non pondéré | NON VÉRIF | **NON** |
| pension/categorie/taux_ipp | NON | NON | possible | OUI (méca) | non pondéré | NON VÉRIF | **NON** |
| accident_travail / maladie_pro | NON VÉRIFIÉ | NON (sauf doc) | possible | OUI | non pondéré | NON VÉRIF | partiel |
| avq_* (×5) | NON VÉRIFIÉ | thème prompt | possible | OUI | **non pondéré** | NON VÉRIF | cases NON VÉRIF |
| droits.* | NON VÉRIFIÉ | thème prompt | possible (objet) | OUI | via droits_demandes | NON VÉRIF | cases NON VÉRIF |

> « Persisté = mécanisme OUI » : `_sauvegarder_nav` (orchestration L168-193) écrit `json.dumps(donnees)` → synthese_json (appels L691/814/846/880/886). **La persistance existe** ; ce n'est pas le maillon cassé.

---

## ÉTAPE 3 — QUESTIONS RÉPÉTÉES (preuve de code)
- `_build_context` (base.py L193-196) liste les requis manquants : `manquants_ids = [id for item in CHECKLIST if requis=True and not donnees.get(id)]`.
- Le bloc « INFORMATIONS DÉJÀ CONNUES — NE PAS REDEMANDER » (L228-240) ne masque que les champs **présents dans `donnees`**.
- **Donc** : un champ est reposé **si et seulement si** il n'est pas dans `donnees`. Des **questions d'identité répétées** ⟹ l'identité **n'est pas dans `donnees`/synthese_json** ⟹ l'extraction ne l'a pas captée/accumulée.
- **Où la mémoire est « perdue » :** pas dans la persistance (elle existe) ni dans le recalcul (correct) — mais **en amont**, parce que `donnees` ne reçoit pas l'information depuis l'extraction. `missing_fields` est recalculé à chaque tour sur `donnees` rechargé depuis `synthese_json` (orchestration L472) → si la synthèse reste vide, les mêmes questions reviennent.

**Conclusion ÉTAPE 3 (PROUVÉE) :** les questions répétées sont le **symptôme observable** d'un `synthese_json` qui n'accumule pas les réponses → pointe vers le pont **extraction → synthèse**.

---

## ÉTAPE 4 — VIE QUOTIDIENNE
| Affirmation | Statut |
|---|---|
| Fatigabilité, difficulté ménage, station debout (bilan) | **PROUVÉE** dans la source ; présence CERFA NON VÉRIFIÉE (overlay non lisible) |
| Aide toilette/habillage/repas, « ne peut se lever seule » | **NON trouvées** en texte dans le CERFA (0 occurrence) → pas d'invention textuelle prouvée |
| AVQ structurés | **NON VÉRIFIÉ** (cases graphiques) |
| Incohérence « vie quotidienne » | **SUPPOSÉE** liée à une synthèse pauvre → narratif générique, pas à une amplification (anti-contamination déployée) |

→ Aucune **invention textuelle** prouvée ; l'« incohérence » vient probablement de la **pauvreté des données**, pas d'une transformation.

---

## ÉTAPE 5 — POURQUOI 20 % (preuve mathématique)
`_calculer_completude_live` (orchestration L142-165), barème (total 100) :
```
nom_prenom 15 · date_naissance 15 · num_secu/nss 10 · adresse_complete 8 ·
telephone 5 · email 5 · diagnostics 12 · impact_quotidien 10 ·
droits_demandes 10 · type_dossier 5 · departement 5
```
- **Aucun champ NIVEAU A n'est pondéré** → la Vague 1 ne peut PAS faire bouger ce score.
- Dashboard : **date_naissance vide (−15)** + **NIR vide (−10)** (prouvé capture). À eux seuls, nom+date+NSS = **40 pts** d'identité ; leur absence plafonne le score bas.
- **20/100** ⟹ seuls ~20 pts présents. Combinaisons compatibles (ex.) : `diagnostics 12 + departement 5 + type_dossier 5 = 22`, ou `impact_quotidien 10 + droits_demandes 10`, etc. → **quelques champs de base seulement**, **identité lourde absente**.
- **Preuve** : le 20 % est gouverné par l'**identité de base absente**, pas par le NIVEAU A (hors barème).

---

## ÉTAPE 6 — VAGUE 1 (NIVEAU A)
| Champ | Défini | Sollicité | Extractible | Persistable | Visible | Utilisé | Rupture |
|---|---|---|---|---|---|---|---|
| identité fine, organisme, allocataire, invalidité, avq_*, droits.* | ✅ (collecte_schema) | ❌ (requis=False, hors driver ; certains hors prompts) | ✅ (whitelist 1dccf6c) | ✅ (méca) | ❌ (non pondéré dashboard) | partiel (CERFA cases) | **Sollicitation (requis=False) + non pondéré + mapping V2 partiel** |

Rupture NIVEAU A : réelle mais **secondaire** ici — car même les champs **requis=True** (identité) manquent. Le NIVEAU A est un problème **en plus**, pas LE problème du 20 %.

---

## ÉTAPE 7 — MOTEURS
| Moteur | Consomme synthese_json | Consomme narratif | Consomme structuré | Utilisé prod |
|---|---|---|---|---|
| eligibility | ✅ | ❌ (retiré 7e04f89) | ✅ (texte déclaré) | ✅ |
| droits_oublies | ✅ (via eligibility) | ❌ | ✅ | ✅ |
| cdaph | ✅ | ❌ (retiré) | ✅ | ✅ |
| cockpit | ✅ (score=CDAPH) | ❌ | ✅ | ✅ |
| gate | ✅ | présence narratif | ✅ | ✅ |
| evidence | ✅ | tagué (origine) | ✅ | ✅ |
| strength | ✅ | partiel | ✅ | ✅ |
| cerfa (v2) | ✅ | imprime P8 | ✅ | ✅ |

**Tous consomment `synthese_json`.** Si elle est vide, **aucun moteur ne peut produire de valeur** — quelle que soit leur qualité. Les moteurs ne sont **pas** la cause.

---

## ÉTAPE 8 — CAUSE RACINE UNIQUE

> **Le pont de collecte « conversation WhatsApp → extraction LLM → `synthese_json` » ne remplit pas réellement `synthese_json`.**

`synthese_json` est l'**unique source de vérité** de tout l'aval (ÉTAPE 1 + ÉTAPE 7). Sur le témoin, il est **quasi vide** : preuve mathématique du 20 % = **identité de base absente** (date/NIR vides, nom non reporté ; ÉTAPE 5), et symptôme des **questions répétées** = champs jamais accumulés dans `donnees` (ÉTAPE 3). La persistance (write-back) **existe** (ÉTAPE 2) ; le mapping CERFA et les moteurs **fonctionnent sur les données présentes** (ÉTAPES 1/7). Donc le maillon défaillant est **en amont** : la **captation des informations dites en conversation vers `synthese_json`** (étape `extract_structured_data_from_history` + intégration au flux d'intake).

**Une seule priorité.** Pas le CERFA. Pas les moteurs. Pas le NIVEAU A (secondaire). Pas l'UX. **Le pont de collecte → synthèse.**

---

## GOULOT D'ÉTRANGLEMENT
`extract_structured_data_from_history` (conversation_engine) **+** son intégration dans le flux d'intake/orchestration : c'est **l'unique convertisseur** conversation → `synthese_json`. Tant qu'il ne capte pas l'identité de base réellement déclarée, tout l'aval reste vide.

---

## FORMAT DE SORTIE

### CE QUI EST PROUVÉ
- Tout l'aval lit `synthese_json` (cartographie + moteurs).
- Le 20 % est gouverné par l'**identité de base absente** (barème L142-165 ; date/NIR vides).
- Questions répétées ⟺ champs absents de `donnees` (base.py L193-240).
- La persistance write-back **existe** (`_sauvegarder_nav` L168-193).
- NIVEAU A **non pondéré** dans le score → la Vague 1 ne pouvait pas remonter le 20 %.
- Aucune invention textuelle dans le CERFA (anti-contamination tient).

### CE QUI EST DÉCLARÉ
- Le bilan contient identité + santé + projet + aidant + emploi.
- Les prompts adultes couvrent les thèmes AVQ/droits/projet/organisme.

### CE QUI EST NON VÉRIFIÉ
- Le **sous-pas exact** qui casse le pont (conversation non lancée ? extraction LLM vide ? dossier doc-only ? intake qui ne persiste pas ?) — faute de chat/logs/synthese prod.
- État des cases CERFA ; visibilité cockpit des champs bruts.

### CHAMPS PERDUS
- Identité (nom/prénom), date_naissance, NIR, adresse — absents du dashboard/CERFA malgré requis=True.

### QUESTIONS RÉPÉTÉES
- Cause : champs non présents dans `donnees` (synthese non accumulée) → `_build_context` les re-liste. Mémoire « perdue » en amont (captation), pas en persistance.

### ORIGINE DES ÉCARTS VIE QUOTIDIENNE
- Pauvreté de la synthèse → narratif générique. Pas d'amplification/invention prouvée (anti-contamination active).

### POURQUOI LE DOSSIER EST À 20 %
- Barème 100 % sur 12 champs de base ; identité lourde (nom 15 + date 15 + NIR 10 = 40) absente → plafond bas ; ~20 pts = quelques champs (type_dossier/departement/diagnostics/impact). NIVEAU A hors barème.

### CAUSE RACINE UNIQUE
- **Le pont collecte → extraction → `synthese_json` ne remplit pas la synthèse** (identité de base comprise). Tout l'aval reflète fidèlement une synthèse vide.

### GOULOT D'ÉTRANGLEMENT
- `extract_structured_data_from_history` + son intégration au flux d'intake (unique convertisseur conversation→synthèse).

### CORRECTION MINIMALE
*(Avant tout correctif de comportement — règle « pas de fix symptomatique sans preuve » : il manque UNE preuve, le sous-pas défaillant.)*
1. **Instrumenter le pont** (observabilité, sans changer le comportement) : journaliser, par tour, `[TRACE] message reçu`, `nouvelles_donnees extraites` (clés), `taille synthese_json après save`.
2. **Un rejeu réel instrumenté** sur `FAC-DOS-M30DPYEX` → localiser le sous-pas exact (conversation lancée ? extraction vide ? doc-only ?).
3. **Puis** correctif ciblé selon la preuve (probablement : intégration extraction durant l'intake, ou fiabilité d'extraction de l'identité).
- **Nombre exact de fichiers (étape 1) :** **1** (`orchestration_engine.py`, logs uniquement).
- **Risque :** très faible (aucune modif de logique).
- **QA nécessaires :** 1 rejeu réel instrumenté + lecture logs ; comparaison message↔synthese_json.
- **Preuves attendues :** trace montrant si l'identité est (a) jamais dite, (b) dite mais non extraite, (c) extraite mais non persistée.

### QA À EXÉCUTER
- Rejeu réel `FAC-DOS-M30DPYEX` avec logs `[TRACE]` actifs ; vérifier l'apparition de nom/date/NIR dans `synthese_json` tour par tour.

### CE QU'IL NE FAUT PAS DÉVELOPPER (gelé tant que la cause racine n'est pas réparée)
- ❌ Nouveau moteur, refonte scoring, Vague 2.
- ❌ Re-câblage CERFA / mapping NIVEAU A (on mapperait du vide).
- ❌ UX, multi-tenant, quotas, rôles, facturation.
- ❌ Ajustement de prompts métier « au feeling ».
- ❌ Tout correctif symptomatique avant le rejeu instrumenté.

### GO / NO GO PILOTE
- **NO GO.** À 20/100 avec identité de base absente, le dossier est un **brouillon non exploitable**. Le socle aval est sain ; le verrou est le **pont de collecte**, à instrumenter puis réparer avant tout pilote.

---

*Forensic, lecture seule. Cause racine démontrée au niveau « pont collecte→synthèse » (code + math du 20 % + symptôme questions répétées). Sous-pas exact = à isoler par 1 rejeu instrumenté (chat/logs absents ici). Aucune modification effectuée.*
