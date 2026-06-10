# TRACE_SOURCE_SYNTHESE_INSTRUMENTATION_REPORT.md — Instrumentation source → synthese_json

**Généré le :** 2026-06-07
**Périmètre :** **logs uniquement**. Aucun changement de comportement, aucun moteur/CERFA/prompt métier modifié, aucune correction de merge/extraction. Non commité, non déployé.
**Statut :** ✅ QA-TRACE-SOURCE-SYNTHESE 5/5 PASS · non-régression 10/10 PASS · compile OK.

---

## CE QUI A ÉTÉ INSTRUMENTÉ

**2 fichiers modifiés (logs only) + 1 QA :**

| Fichier | Ajouts |
|---|---|
| `app/engines/orchestration_engine.py` | Helpers de masquage (`_trace_mask_phone`, `_trace_mask_value`, `_trace_resume`, `_trace_extrait`) ; traces **`[TRACE_COLLECTE]`** (chemin WhatsApp) et **`[TRACE_SOURCE_SYNTHESE]`** (chemin document) |
| `app/engines/conversation_engine.py` | `[TRACE_COLLECTE] 6-REJETES` (champs hors whitelist) |
| `app/tests/qa/qa_trace_source_synthese.py` | **NOUVEAU** — QA-TRACE-SOURCE-SYNTHESE 1→5 |

**Points couverts (1→14) :**
1 message reçu · 2 longueur message · 3 document reçu (mime+taille) · 4 texte extrait (longueur) · 5 champs extraits document · 6 champs extraits WhatsApp + rejetés · 7 champs rejetés · 8 synthèse avant fusion (clés) · 9 synthèse après / sauvegarde · 10 champs ajoutés · 11 champs ignorés (déjà présents) · 12 écrasé/non écrasé (déduit des avant/après) · 13 sauvegarde OK/échec · 14 complétude avant/après.

---

## SOURCE WHATSAPP — TRACE ATTENDUE (tag `[TRACE_COLLECTE]`)
```
[TRACE_COLLECTE] 1-MSG dossier=FAC-DOS-... tel=****5678 profil=adulte msg_len=42
[TRACE_COLLECTE] 3-SYNTHESE_AVANT nb_champs=3 completude=15 champs=[...]
[TRACE_COLLECTE] 4-EXTRACT call profil=adulte history_msgs=7
[TRACE_COLLECTE] 5-EXTRAIT {organisme_payeur=CAF, numero_allocataire=123456, droits={aah,pch}}
[TRACE_COLLECTE] 6-REJETES profil=adulte rejetes=['champ_hors_liste']
[TRACE_COLLECTE] 7-SYNTHESE_APRES nb_champs=6 completude=35 champs=[...] (completude_avant=15)
[TRACE_COLLECTE] 8-SAVE start dossier=... nb_champs=6 completude=35 champs=[...]
[TRACE_COLLECTE] 9-SAVE ok dossier=... completude=35
```

## SOURCE DOCUMENT — TRACE ATTENDUE (tag `[TRACE_SOURCE_SYNTHESE]`)
```
[TRACE_SOURCE_SYNTHESE] 3-DOC recu dossier=... mime=application/pdf taille=964000o
[TRACE_SOURCE_SYNTHESE] 4-DOC texte_extrait len=8123 exploitable=True
[TRACE_SOURCE_SYNTHESE] 5-DOC champs_extraits {nom_prenom=CECORA Marie-Christine, impact_quotidien=<390c>, statut_emploi=...}
[TRACE_SOURCE_SYNTHESE] 8-SYNTHESE_AVANT(doc) nb_champs=2 completude=10 champs=[...]
[TRACE_SOURCE_SYNTHESE] 10/11-DOC ajoutes=['nom_prenom','impact_quotidien'] ignores_deja_presents=['departement']
[TRACE_SOURCE_SYNTHESE] 6-DOC_KNOWLEDGE type=PCR items=12 categories=['limitations_fonctionnelles',...] | NB: alimente _document_knowledge (texte), PAS les champs structures avq_*/droits/organisme
[TRACE_SOURCE_SYNTHESE] 9-SAVE(doc) start nb_champs=8 completude=37 champs=[...]
[TRACE_SOURCE_SYNTHESE] 13-SAVE(doc) ok dossier=... completude=37
```

## FUSION — TRACE ATTENDUE
- WhatsApp : `5-EXTRAIT` (entrant) → `7-SYNTHESE_APRES` (résultat) → écart de clés = ajouts.
- Document : `5-DOC champs_extraits` → `10/11-DOC ajoutes/ignores_deja_presents` (règle `k not in synthese`).
- Le `6-DOC_KNOWLEDGE` montre explicitement que le bilan alimente `_document_knowledge` (texte) **et non** les champs structurés.

---

## EXEMPLES DE LOGS MASQUÉS (réels, QA TEST 5)
```
phone  = ****5678              (derniers 4 chiffres)
nir    = ***                   (jamais affiché)
diag   = <400c>                (longueur uniquement)
adresse_complete = <38c>       (longueur uniquement)
resume = nb_champs=8 completude=37 champs=[...]   (NOMS de champs, jamais les valeurs)
extrait= {organisme_payeur=CAF, droits={aah,pch}, impact_quotidien=<390c>}
```
**Aucune** valeur sensible complète (NIR `280017512300120`, tel `0612345678`, adresse complète, texte médical long) n'apparaît — vérifié par QA TEST 5.

---

## QA PASS / FAIL
```
✅ TEST 1 — Document : clés tracées, médical masqué
✅ TEST 2 — WhatsApp : admin/invalidité/droits tracés
✅ TEST 3 — Fusion : les deux sources présentes
✅ TEST 4 — Champ vide existant → valeur document IGNORÉE (observé)
✅ TEST 5 — Aucune fuite (NIR/tel/adresse/médical) + masquage OK
DÉCISION : ✅ PASS (5/5)
```

## NON-RÉGRESSION
```
✅ qa_trace_source_synthese   ✅ qa_prod_3
✅ qa_v1_real_flow            ✅ qa_prod_4
✅ qa_anti_contamination      ✅ qa_prod_5
✅ qa_prod_1                  ✅ qa_fix_test4_collecte
✅ qa_prod_2                  ✅ qa_fix_test4_cerfa_v2
→ 10/10 PASS
```

---

## RÉPONSES (ÉTAPE 4) — déjà déductibles du code lu (à confirmer en runtime par les traces)

1. **Le bilan est-il lu ?** Seulement s'il est **uploadé via WhatsApp** (chemin `_handle_document`). Sur le témoin : à confirmer par `3-DOC recu` (présent ou absent dans les logs).
2. **Texte extrait ?** Oui via `_extraire_texte_fichier` → `4-DOC texte_extrait len=…`.
3. **Envoyé à une extraction structurée ?** **Oui** — prompt LLM dédié, mais **liste de champs limitée** (`nom_prenom, date_naissance, adresse_complete, departement, num_secu, diagnostics, traitements, medecin_traitant, impact_quotidien, statut_emploi, historique_mdph, accident_travail, restrictions_emploi`) — **aucun champ NIVEAU A**.
4. **Bilan → `_document_knowledge` seulement ?** **NON** (PROUVÉ code) : il alimente **(a)** un set **administratif limité** dans `synthese` (via l'extraction LLM) **et (b)** `_document_knowledge` (via `fusionner_dans_donnees`).
5. **`_document_knowledge` fusionné dans synthese ?** **Oui** (`fusionner_dans_donnees` écrit `synthese["_document_knowledge"]`) → trace `6-DOC_KNOWLEDGE`.
6. **Champs du bilan ignorés si synthese a déjà une valeur vide ?** **OUI (PROUVÉ — QA TEST 4)** : le merge document est `if v and k not in synthese` → une **clé présente même vide** bloque la valeur réelle du document.
7. **Le merge écrase ou refuse ?** **REFUSE d'écraser** (document : `k not in synthese` ; WhatsApp : admin non-prioritaire seulement si nouveau) → **premier écrivain gagne**.
8. **Vie quotidienne du bilan → où ?** Vers **`impact_quotidien`** (si le LLM la mappe) **et** `_document_knowledge.limitations_fonctionnelles` — **jamais** `texte_b` (généré plus tard) ni `notes_pro`.
9. **Limitations structurées en `avq_*` ?** **NON (PROUVÉ)** : ni l'extraction document (liste sans avq_*) ni `fusionner_dans_donnees` (écrit `_document_knowledge`) ne produisent d'`avq_*`. Le bilan ne devient **jamais** de l'AVQ structuré.
10. **WhatsApp et document se complètent ?** **Partiellement** : même `synthese_json`, deux chemins, **les deux refusent d'écraser** → complémentaires **uniquement sur des clés disjointes** ; si les deux visent `impact_quotidien`, le **second est ignoré**.

---

## CE QUI RESTE NON VÉRIFIÉ
- **Le déroulé réel sur `FAC-DOS-M30DPYEX`** : sans rejeu instrumenté en prod, on ne sait pas encore si `3-DOC recu` apparaît (bilan réellement uploadé ?), ni si `5-EXTRAIT`/`5-DOC` capturent l'identité. **Les traces sont prêtes ; il faut UN rejeu instrumenté.**
- La **qualité de l'extraction LLM** (capte-t-elle vraiment l'identité du bilan / de WhatsApp ?).
- L'état réel de `synthese_json` en prod (volume inaccessible).

---

## GO / NO GO POUR DÉPLOIEMENT INSTRUMENTATION
```
GO (sous votre feu vert explicite)
```
- ✅ Logs uniquement, **zéro changement de comportement** (vérifié : non-régression 10/10, dont QA-ANTI / QA-V1-REAL / QA-FIX-TEST4).
- ✅ **Aucune fuite** de donnée sensible (QA TEST 5).
- ✅ Couvre **les deux sources** (WhatsApp + document) jusqu'à `synthese_json`.
- ⚠️ Ne rien **corriger** tant que le rejeu instrumenté n'a pas isolé le sous-pas exact.
- 🔴 **Non commité / non déployé** : j'attends votre feu vert pour `git commit` puis `railway up`. Après déploiement, **un rejeu réel de `FAC-DOS-M30DPYEX`** (upload bilan + conversation) fera apparaître les traces `[TRACE_*]` qui trancheront définitivement WhatsApp vs document vs extraction vs fusion vs persistance.

---

## Découverte déjà acquise (sans même déployer)
**PROUVÉ par lecture + QA :** le bilan, même bien lu, **ne produit jamais de champs `avq_*`/`droits`/`organisme_payeur` structurés** (extraction document limitée + `_document_knowledge` = texte), et **toute valeur réelle est ignorée si la clé existe déjà (même vide)** dans `synthese_json`. Ces deux mécanismes (à NE PAS corriger maintenant) sont des **causes directes** d'un dossier pauvre quand la source est documentaire.

---

*Instrumentation source→synthese, logs uniquement. Aucune correction (merge/extraction/CERFA/prompts intacts). Non commité, non déployé. Le sous-pas exact sur le témoin sera isolé au rejeu instrumenté.*
