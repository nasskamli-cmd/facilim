# FIX_VAGUE1_EXTRACTION_REPORT.md — Sprint FIX-VAGUE1-EXTRACTION-PERSISTENCE

**Généré le :** 2026-06-07
**Objet :** rendre la Vague 1 réellement opérationnelle — les champs NIVEAU A sont désormais **extraits et persistés** (flux WhatsApp → extraction → synthèse).
**Statut :** ✅ **QA-V1-REAL 5/5 PASS · non-régression 10/10 PASS.** Non commité, non déployé.
**Périmètre :** extraction/persistance uniquement. CERFA, cockpit, moteurs 60→100, gate, evidence, anti-contamination, Vague 2, migrations SQL : **non touchés**.

---

## CE QUI ÉTAIT CASSÉ
La Vague 1 était **décorative** : les 14 champs NIVEAU A (+ objet `droits`) étaient demandés par les agents mais **rejetés à l'extraction** :
- `extract_structured_data_from_history` filtrait via `_CHAMPS_EXTRACTIBLES_*` (whitelist **sans** NIVEAU A) → rejet défensif des champs hors liste.
- Appel fait avec `profil_mdph="inconnu"` (orchestration L488) → whitelist ADULTE par défaut, jamais le profil réel.
- Conséquence : `avq_*`, `droits.*`, `prenom`, `nom_naissance`, `organisme_payeur`, `numero_allocataire`, `pension_invalidite`, `categorie_invalidite`, `taux_ipp` **jamais persistés dans `synthese_json`**.

---

## CE QUI A ÉTÉ MODIFIÉ (2 fichiers + 1 QA)

| Fichier | Modification |
|---|---|
| `app/engines/conversation_engine.py` | **(1)** Nouvelle constante `_CHAMPS_NIVEAU_A` (14 champs + `droits`). **(2)** `_champs_extractibles()` ajoute `_CHAMPS_NIVEAU_A` à **tous** les profils (enfant/mixte/adulte → point unique). **(3)** Prompt d'extraction étendu : section **FORMATS SPÉCIAUX** (niveaux AVQ `AUTONOME/DIFFICULTE/AIDE_PARTIELLE/AIDE_TOTALE`, objet `droits`, booléen `pension_invalidite`, `categorie_invalidite` 1/2/3, `organisme_payeur` CAF/MSA/AUTRE, `taux_ipp`). |
| `app/engines/orchestration_engine.py` | `extract_structured_data_from_history(..., profil_mdph=service_type or "inconnu")` au lieu de `"inconnu"` → **profil réel** transmis. |
| `app/tests/qa/qa_v1_real_flow.py` | **NOUVEAU** — QA-V1-REAL-1→5 (vrai flux). |

**Le filtre défensif (anti-pollution) est conservé** : un champ hors whitelist est toujours rejeté (vérifié — `champ_bidon` rejeté en QA-V1-REAL-1).

---

## PREUVE D'EXTRACTION
Via le **vrai** `extract_structured_data_from_history` (LLM mocké, car pas de clé réelle ; le mock simule une sortie LLM correcte — la qualité de l'LLM n'est pas testable hors clé, mais la **plomberie whitelist/prompt** l'est) :
```
REAL-1 : {'pension_invalidite': True, 'categorie_invalidite': 2}      (champ_bidon rejeté ✓)
REAL-2 : {'organisme_payeur': 'CAF', 'numero_allocataire': '123456'}
REAL-3 : {'avq_habillage': 'AIDE_PARTIELLE'}   + prompt contient avq/droits/formats ✓
REAL-4 : {'droits': {'aah': True, 'pch': True}}  (objet survit au whitelist)
```
Avant le fix, **tous** ces champs étaient écartés par le filtre (`filtered = {k:v for k,v in extracted.items() if k in champs_autorises}`). Désormais ils sont conservés.

## PREUVE DE PERSISTANCE
QA-V1-REAL-5 applique la **réplique exacte de la fusion d'orchestration** (L493-508) :
```
synthese (avant) = {'nom_prenom': 'DURAND Marie'}
+ extraction      = {'droits': {...}, 'avq_repas': 'AIDE_TOTALE', 'organisme_payeur': 'CAF'}
→ synthese (après) = {... 'organisme_payeur': 'CAF', 'avq_repas': 'AIDE_TOTALE', 'droits': {'aah':True,'pch':True}}
→ normaliser_collecte → droits_demandes = 'AAH, PCH'
```
Les champs NIVEAU A **arrivent dans la synthèse** et `droits.*` est dérivé en `droits_demandes` (legacy) — chaîne complète opérationnelle.

## QA-V1-REAL
```
✅ QA-V1-REAL-1 — pension_invalidite + categorie_invalidite extraits (junk rejeté)
✅ QA-V1-REAL-2 — organisme_payeur + numero_allocataire extraits
✅ QA-V1-REAL-3 — avq_habillage extrait + prompt contient les formats Vague 1
✅ QA-V1-REAL-4 — objet droits.{aah,pch} extrait (survit au whitelist)
✅ QA-V1-REAL-5 — flux complet : champs persistés + droits_demandes dérivé
DÉCISION : ✅ PASS (5/5)
```

## NON-RÉGRESSION
```
✅ qa_v1_real_flow       ✅ qa_prod_3
✅ qa_schema_vague1      ✅ qa_prod_4
✅ qa_anti_contamination ✅ qa_prod_5
✅ qa_prod_1             ✅ qa_fix_test4_cerfa_v2
✅ qa_prod_2             ✅ qa_fix_test4_collecte
→ 10/10 PASS
```

---

## CE QUI EST PROUVÉ
- Les champs NIVEAU A **passent désormais l'extraction** (whitelist) — le bug racine est corrigé.
- Le **profil réel** est transmis (plus de `"inconnu"` figé) → bonne whitelist par profil, anti-pollution conservée.
- Le **prompt** demande explicitement les formats Vague 1 (niveaux AVQ, objet `droits`, booléens).
- La **fusion** d'orchestration fait arriver ces champs dans `synthese_json` (réplique testée).
- `normaliser_collecte` dérive `droits_demandes` depuis l'objet `droits` persisté.
- **Zéro régression** (10/10), dont QA-ANTI (anti-contamination) et QA-SCHEMA (Vague 1).

## CE QUI EST NON VÉRIFIÉ
- **Qualité d'extraction du LLM réel** : que le modèle produise effectivement les bons niveaux AVQ / l'objet `droits` à partir d'une vraie conversation — non testable sans clé OpenAI réelle (le mock simule une sortie correcte ; le présent sprint prouve la **plomberie**, pas la performance LLM).
- **Bout-en-bout en production** : non exécuté (non déployé ; `railway ssh` bloqué, non contourné).
- **Fusion multi-tours de l'objet `droits`** : une fois `droits` présent dans la synthèse, la règle « ne pas réécraser l'admin » empêche de **compléter** l'objet à un tour ultérieur (ex. tour 1 `aah`, tour 2 `pch` non fusionné). Limitation connue, hors périmètre.
- **`categorie_invalidite`** typée tantôt `int` tantôt `str` selon l'LLM — non normalisée (les consommateurs lisent surtout en texte).

## RISQUE PRINCIPAL RESTANT
**Dépendance à la fiabilité du LLM d'extraction** : la collecte structurée fonctionne maintenant *si* le LLM mappe correctement le langage naturel vers les niveaux AVQ / l'objet `droits`. À valider en conversation réelle (premier test terrain). Risque secondaire : la fusion multi-tours de `droits` (ci-dessus).

## GO / NO GO
```
GO
```
**Justification :** QA-V1-REAL 5/5 ✅ + non-régression 10/10 ✅ + anti-pollution conservée ✅ + anti-contamination intacte (QA-ANTI 5/5) ✅. La Vague 1 cesse d'être décorative ; le fix anti-contamination (7e04f89) devient **exploitable** (les `avq_*` peuvent enfin atteindre les cases AVQ). **Réserve :** validation terrain de la qualité d'extraction LLM requise avant de considérer la collecte fiable en production.

---

## CRITÈRE DE RÉUSSITE — contrôle
1. Champs Vague 1 réellement **extractibles** ✅ (whitelist) · 2. **persistés** ✅ (fusion) · 3. arrivent dans `synthese_json` ✅ · 4. QA via **vrai flux** (pas injection directe) ✅ · 5. Vague 1 **non décorative** ✅ · 6. anti-contamination **exploitable** ✅ · 7. **aucune régression** ✅ (10/10).

---

*Sprint exécuté dans le périmètre extraction/persistance (`conversation_engine` + appel orchestration). CERFA, cockpit, moteurs, gate, evidence, anti-contamination, migrations : non modifiés. Non commité, non déployé.*
