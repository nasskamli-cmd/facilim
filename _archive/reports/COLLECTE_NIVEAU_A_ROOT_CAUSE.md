# COLLECTE_NIVEAU_A_ROOT_CAUSE.md — Pourquoi le NIVEAU A n'arrive pas naturellement au dossier

**Généré le :** 2026-06-07
**Mode :** lecture seule. Aucune modification, aucun commit, aucun déploiement.
**Question centrale :** *FACILIM peut-il aujourd'hui terminer une collecte complète sans jamais demander les champs NIVEAU A ?*
**Réponse (PROUVÉE) : OUI.** La fin de collecte ne dépend que des champs `requis=True` ; tous les champs NIVEAU A sont `requis=False`. La collecte peut donc se terminer (et déclencher narratif + CERFA) avec **zéro** champ NIVEAU A renseigné.

---

## Parcours réel reconstitué (preuves de code)
```
WhatsApp → orchestration_engine.respond
  → agent.respond  (SYSTEM_PROMPT + _build_context)         [base.py]
       • _build_context (L193-196) : liste « Informations à collecter MAINTENANT »
         = UNIQUEMENT les champs requis=True non remplis
       • SYSTEM_PROMPT : aborde aussi des THÈMES (autonomie, droits, projet) hors checklist
  → réponse utilisateur (texte libre)
  → extract_structured_data_from_history  [conversation_engine.py]
       • whitelist _CHAMPS_EXTRACTIBLES_* + _CHAMPS_NIVEAU_A (depuis 1dccf6c)  → NIVEAU A extractible
       • profil réel transmis (depuis 1dccf6c)
  → fusion → synthese_json  [orchestration L499-508]
  → fin de collecte = is_complete (missing_fields==0 = requis=True seulement)  [base.py L101-102]
  → narratif + facilim_prod + cockpit + CERFA
```

**Trois verrous prouvés dans `base.py` :**
- `missing_fields` **ignore** les champs non requis : `if not item.get("requis", True): continue` (**L90**).
- `is_complete = len(missing_fields)==0` (**L101-102**) → ne dépend QUE des `requis=True`.
- `_build_context` ne propose à l'agent que les `requis=True` : `... if item.get("requis", True) and not donnees.get(...)` (**L193-196**) ; sinon « Toutes les informations sont collectées » (**L225-226**).

**Dans `collecte_schema.py` : TOUS les NIVEAU A sont `requis=False`** (L63-81). → Ils ne sont jamais comptés par `missing_fields`, jamais listés par le pilote de questions, jamais bloquants pour la fin.

---

## CE QUI EST PROUVÉ
1. **La collecte se termine sans aucun NIVEAU A** (requis=False + is_complete sur requis seulement). C'est le **goulot unique**.
2. **Le pilote déterministe de questions (`_build_context`) ne propose jamais le NIVEAU A** (requis=True only).
3. **`numero_allocataire`, `categorie_invalidite`, `taux_ipp`, `pension_invalidite`, `accident_travail`, `maladie_professionnelle` ne figurent dans AUCUN prompt agent** (0 occurrence dans `app/services/conversation/`) → ni driver, ni prompt = **réellement jamais demandés**.
4. **`projet_vie` / `projet_orientation` / `projet_professionnel` ne sont PAS des champs de `collecte_schema`** (0 occurrence) → pas de question de collecte dédiée ; le « projet de vie » passe par le narratif généré `texte_e` et/ou l'extraction libre `projet_orientation`.
5. **Post-1dccf6c, le NIVEAU A est extractible/persistable** (whitelist `_CHAMPS_NIVEAU_A`) **si** mentionné.

## CE QUI EST DÉCLARÉ (par le code/prompt, pas observé en réel)
- Le `SYSTEM_PROMPT` d'**adult_agent** aborde les **thèmes** : autonomie/hygiène/alimentation/déplacements/ménage (L33), **droits** AAH/PCH/RQTH/CMI (L64), **projet de vie** (L39/48), **organisme payeur** (L69). → l'agent **peut** poser ces sujets en texte libre.
- Le prompt d'extraction (1dccf6c) demande les formats AVQ (enum) et l'objet `droits`.

## CE QUI EST SUPPOSÉ
- Que, faute d'être bloquants, les thèmes NIVEAU A sont **survolés** puis la collecte est déclarée terminée → dossier « pauvre ». (Cohérent avec les symptômes terrain, mais non mesuré en conversation réelle.)

## CE QUI EST NON VÉRIFIÉ
- **Comportement du LLM réel** : pose-t-il effectivement les questions AVQ/droits/projet, et **mappe-t-il** le texte libre vers les champs **structurés** (avq_* enum, objet droits, organisme_payeur) ?
- Couverture des prompts **enfant_agent / protege_agent** sur AVQ/droits (vérifié sur adulte uniquement ; admin/invalidité absents partout).
- **Visibilité cockpit/dashboard** des champs NIVEAU A bruts.

---

## MATRICE CHAMP PAR CHAMP

Colonnes : **Exist.**(checklist) · **Req.**(requis) · **miss_f**(missing_fields) · **Driver?**(_build_context peut le proposer) · **Prompt?**(cité dans un SYSTEM_PROMPT) · **Extr.**(extractible) · **Persist.** · **CERFA** · **Fin sans lui ?**

| Champ | Exist. | Req. | miss_f | Driver? | Prompt? | Extr. | Persist. | CERFA | Fin sans lui |
|---|---|---|---|---|---|---|---|---|---|
| prenom | ✅ NIVEAU_A | ❌ | ❌ | ❌ | ~ (identité) | ✅ | ✅ | ✅ P2 3 (fallback split) | **OUI** |
| nom_naissance | ✅ | ❌ | ❌ | ❌ | ~ | ✅ | ✅ | ✅ P2 1 (fallback split) | **OUI** |
| organisme_payeur | ✅ | ❌ | ❌ | ❌ | ✅ adulte L69 | ✅ | ✅ | ❌ (v2_bridge gap) | **OUI** |
| numero_allocataire | ✅ | ❌ | ❌ | ❌ | ❌ **aucun** | ✅ | ✅ | ❌ (P2 13 vide, prouvé) | **OUI** |
| pension_invalidite | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ | **OUI** |
| categorie_invalidite | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ (absent CERFA) | **OUI** |
| taux_ipp | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ | **OUI** |
| accident_travail | ✅ | ❌ | ❌ | ❌ | ❌ (sauf doc) | ✅ | ✅ | ✅ P5 15/20 | **OUI** |
| maladie_professionnelle | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ~ (AT/MP partiel) | **OUI** |
| avq_toilette | ✅ | ❌ | ❌ | ❌ | ✅ thème (L33) | ✅ | ✅ | ✅ P6 B1 (V2, si enum) | **OUI** |
| avq_habillage | ✅ | ❌ | ❌ | ❌ | ✅ thème | ✅ | ✅ | ✅ P6 B2 (si enum) | **OUI** |
| avq_repas | ✅ | ❌ | ❌ | ❌ | ✅ thème | ✅ | ✅ | ✅ P6 B3 (si enum) | **OUI** |
| avq_deplacements | ✅ | ❌ | ❌ | ❌ | ✅ thème | ✅ | ✅ | ✅ P6 B4/P7 (si enum) | **OUI** |
| avq_gestion_quotidienne | ✅ | ❌ | ❌ | ❌ | ~ (ménage) | ✅ | ✅ | ~ (field_mapper) | **OUI** |
| droits.aah | objet `droits` (whitelist) | ❌ | ❌ | ❌ | ✅ L64 | ✅ | ✅ | ✅ P17 (via droits_demandes) | **OUI** |
| droits.pch | ″ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ P17 | **OUI** |
| droits.rqth | ″ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ P17/P18 | **OUI** |
| droits.cmi_invalidite | ″ | ❌ | ❌ | ❌ | ✅ (CMI) | ✅ | ✅ | ✅ P17 | **OUI** |
| droits.cmi_priorite | ″ | ❌ | ❌ | ❌ | ~ (CMI) | ✅ | ✅ | ~ (souvent confondu) | **OUI** |
| droits.cmi_stationnement | ″ | ❌ | ❌ | ❌ | ~ (CMI) | ✅ | ✅ | ✅ P17 | **OUI** |
| projet_vie | ❌ **n'existe pas** | — | ❌ | ❌ | ✅ thème (L39/48) | ~ (projet_orientation) | ~ | ✅ P16 (via texte_e) | **OUI** |

> Questions 6 (agent porteur) : les **3 agents** portent NIVEAU_A_COMMUN (via `checklist_for`). Question 7 (moment) : aucun moment **imposé** (jamais dans le driver). Questions 12-13 (cockpit/dashboard) : **NON VÉRIFIÉ**. Question 15 (réellement demandé) : **thèmes AVQ/droits/projet/organisme = possible via prompt adulte** ; **allocataire/invalidité = non** (absents des prompts).

---

## PREMIER POINT DE RUPTURE
**La logique de complétude** : `missing_fields`/`is_complete`/`_build_context` (base.py L90, L101-102, L193-196) ne prennent en compte que `requis=True`. Comme **tout le NIVEAU A est `requis=False`** (collecte_schema), il n'est **ni exigé, ni priorisé, ni bloquant**. La rupture est **entre la définition du champ et le pilotage de la collecte**, en amont de l'extraction (qui, elle, est déjà réparée).

## GOULOT D'ÉTRANGLEMENT UNIQUE
`requis=False` sur l'ensemble du NIVEAU A **+** une fin de collecte calculée sur les seuls `requis=True`. Un seul mécanisme (`missing_fields` filtrant `requis`) neutralise la collecte structurée. Secondairement : **certains champs (allocataire, invalidité) ne sont dans aucun prompt** → invisibles même en texte libre.

## IMPACT SUR DASHBOARD
Le dashboard reflète `synthese_json` : si la collecte se termine sur les requis de base sans NIVEAU A, le `synthese_json` reste « maigre » → **dashboard peu rempli** (cohérent avec le terrain). Visibilité des champs NIVEAU A bruts dans le cockpit = **NON VÉRIFIÉ**.

## IMPACT SUR CERFA
- AVQ/droits/identité : présents au CERFA **uniquement si** collectés ET extraits (structuré) — non garanti.
- **organisme_payeur / numero_allocataire / pension / categorie / taux** : même collectés, **non mappés** au CERFA V2 (gap prouvé P2 13 vide) → vides.
- Résultat : **CERFA incomplet** sur l'administratif et l'invalidité, AVQ aléatoires → ressenti « dossier pauvre ».

## IMPACT SUR PILOTE ESSMS
Tant que le NIVEAU A n'est ni exigé ni systématiquement demandé, le dossier produit reste **niveau B (brouillon à compléter)**. Le professionnel doit re-saisir manuellement l'administratif/invalidité → la promesse « dossier mieux préparé » n'est pas tenue de bout en bout. **NO GO pilote** sur ce point.

## CORRECTION MINIMALE THÉORIQUE (ne pas coder)
1. **Rendre une partie ciblée du NIVEAU A « collectable de façon priorisée »** : soit promouvoir un sous-ensemble en `requis=True` (ex. organisme_payeur, numero_allocataire, AVQ cœur, droits) ; soit **étendre `_build_context`** pour lister aussi les NIVEAU A pertinents (sans forcément bloquer `is_complete`).
2. **Combler les prompts manquants** : ajouter explicitement `numero_allocataire`, `pension/categorie/taux d'invalidité`, `accident/maladie pro` aux SYSTEM_PROMPT (et vérifier enfant/protégé).
3. **Garantir le format structuré** à l'extraction (enum AVQ, objet droits) — déjà amorcé (1dccf6c), à valider en réel.
4. *(séparé)* **Mapper au CERFA** organisme/allocataire/invalidité (sprint MAPPING-NIVEAU-A-CERFA).
Tout cela **sans** créer de nouveau moteur.

## CE QU'IL NE FAUT PAS DÉVELOPPER
- ❌ Nouveau moteur, Vague 2, refonte scoring.
- ❌ Re-cabler le CERFA avant d'avoir corrigé la **collecte** (sinon on mappe du vide).
- ❌ Promesses produit avant validation terrain.
- ❌ Toucher anti-contamination / extraction (déjà réparés).

## VERDICT
**Le problème n'est plus le CERFA : il est dans le PILOTAGE de la collecte.** Cause racine **prouvée** : tout le NIVEAU A est `requis=False`, et la fin de collecte ne dépend que des `requis=True` → FACILIM **peut terminer une collecte « complète » sans jamais exiger le NIVEAU A**. Aggravé par l'absence de certains champs (allocataire, invalidité) dans les prompts, et par le gap de mapping CERFA pour l'administratif. Les correctifs précédents (anti-contamination, extraction, persistance) sont **nécessaires mais insuffisants** tant que la collecte ne **sollicite** pas réellement le NIVEAU A.

---

*Diagnostic racine, lecture seule. Preuves : base.py L90/L101-102/L193-196 ; collecte_schema L63-81 (requis=False) ; absence des champs admin/invalidité dans app/services/conversation/ ; absence de projet_vie dans collecte_schema. NON VÉRIFIÉ : comportement LLM réel, prompts enfant/protégé, visibilité cockpit/dashboard.*
