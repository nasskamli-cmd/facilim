# AUDIT_CONTAMINATION_NARRATIFS.md — Le texte généré par LLM est-il réutilisé comme preuve décisionnelle ?

**Généré le :** 2026-06-07
**Mode :** AUDIT LECTURE SEULE. Aucune correction, aucun refactoring, aucun déploiement, aucun test de modification.
**Question centrale :** un texte produit par un LLM est-il réutilisé comme **donnée d'entrée décisionnelle** dans d'autres moteurs FACILIM (au-delà du P8 déjà documenté) ?
**Réponse en une ligne :** **OUI — contamination SYSTÉMIQUE.** Au moins **7 moteurs** consomment des narratifs générés par FACILIM comme entrée de scoring, d'éligibilité aux droits, de « preuve », de stratégie, d'analyse, ou de gate CERFA.

---

## 0. DÉFINITION (pour éviter les faux positifs)

On distingue **trois natures de champ** :
- 🟩 **Déclaré** (preuve) : saisi par l'usager / extrait d'un document — ex. `diagnostics`, `impact_quotidien`, `restrictions_emploi`, `_document_knowledge`. **Légitime** comme entrée décisionnelle.
- 🟥 **Généré** (prose FACILIM) : produit par un LLM **interne** — `texte_b_vie_quotidienne`, `texte_c_scolarite`, `texte_d_situation_pro`, `texte_e_projet_vie` (`cerfa_narrative_engine`), `description_situation` (P8, `cerfa_filler`), `synthese_situation` (`analyse_situation`). **Réutiliser ceci comme entrée décisionnelle = CONTAMINATION.**
- 🟦 **Structuré** : booléens / niveaux / listes — ex. `droits.*`, `avq_*` (Vague 1), `score_*`.

⚠️ **Le motif systémique** : presque tous les moteurs construisent un **blob de texte mixte** (`_construire_texte` / `_texte_complet` / `all_text`) qui **fusionne déclaré + généré** puis fait du keyword-matching/scoring dessus. **Aucun moteur ne sépare la preuve déclarée de la prose générée.**

---

## ÉTAPE 1 — INVENTAIRE DES PRODUCTEURS DE TEXTE GÉNÉRÉ

| Module | Fonction | Produit (🟥 généré) |
|---|---|---|
| `app/engines/cerfa_narrative_engine.py` | `generer_textes_narratifs` / `_prompt_section_b/c/d/e` | `texte_b/c/d/e_*` |
| `services/cerfa_filler.py` | `_composer_description_p8` | `description_situation` (P8) |
| `app/engines/analyse_situation_engine.py` | `analyser_situation` (LLM) | `analyse_situation_json`, `synthese_situation` |
| `services/cerfa_expert.py` | (LLM) | textes CERFA experts |
| `services/humanizer.py` | (LLM) | reformulations |
| `app/engines/document_functional_extractor.py` | (LLM) | `_document_knowledge` (extrait de doc → 🟩 mais via LLM) |
| `services/conversation_agent.py` / `app/services/conversation/base.py` | (LLM) | tours de conversation, synthèse |
| `app/engines/cerfa_quality_agent.py` | (LLM) | évaluation qualité |

> Producteurs LLM confirmés (call sites `chat.completions`) : 12 fichiers `app/` + 8 `services/`.

---

## ÉTAPE 2 / 3 — MATRICE PRODUCTEUR → CONSOMMATEUR (réinjections décisionnelles)

| Producteur (🟥) | Consommateur | Lieu exact | Utilisation | Niveau |
|---|---|---|---|---|
| `description_situation` (P8) | détecteur AVQ (cerfa_filler) | `services/cerfa_filler.py` L1791 → L1804-1821 | **décisionnel** (coche cases P6/P7) | **4** |
| `texte_b/c/d/e` | **eligibilite_droits_engine** | `eligibilite_droits_engine.py` L77-83 `_construire_texte` → `_signal()` L109 → `_analyser_aah/pch/cmi/rqth…` | **influence l'éligibilité aux droits** | **3** |
| `texte_b/e` | **cdaph_strategy_engine** | `cdaph_strategy_engine.py` L86-91 `_texte_complet`, L148-155 (score selon `len(texte_b)`), L294-300 | **score de stratégie** → `analyse_situation_json` | **2-3** |
| `texte_b` + `texte_dc` | **dossier_strength_engine** | `dossier_strength_engine.py` POIDS L61-62 (`narratif_b=0.20`,`narratif_dc=0.15`), `_evaluer_retentissement` L86-98, `_evaluer_narratif_b` L131-162 | **35 % du score global**, score selon longueur | **2** |
| `texte_b/c/d/e` | **evidence_engine** | `evidence_engine.py` L292-320 `_extraire_narratifs` (« Extrait les **preuves** des narratifs générés »), L423 | **narratif traité comme PREUVE** | **3** |
| `texte_b/d/e` | **analyse_situation_engine** | `analyse_situation_engine.py` L263/279-281, L447 (`for texte in textes_narratifs.values()`), L485-510 (réinjecté dans un **prompt LLM**) | **analyse + re-LLM** → `analyse_situation_json` | **5** |
| `texte_b/d` | **cerfa_gate_engine** | `cerfa_gate_engine.py` L249-263 `_verif_narratifs` (blocage si `len(texte_b) < 50`) | **gate d'export CERFA** | **4** |
| `analyse_situation_json` (🟥 dérivé) | cockpit / FACILIM 60→100 | `orchestration_engine.py` L1051-1066 | alimente cockpit | **5 (indirect)** |

---

## ÉTAPE 4 — CLASSIFICATION PAR NIVEAU

- **NIVEAU 0 (affichage)** : rendu dashboard des `texte_*` (lecture). *(non décisionnel)*
- **NIVEAU 1 (explication)** : narratifs imprimés dans le CERFA en tant que texte. *(légitime)*
- **NIVEAU 2 (influence un score)** : `dossier_strength_engine` (35 % du score), `cdaph_strategy_engine` (score selon longueur narratif).
- **NIVEAU 3 (influence un droit)** : `eligibilite_droits_engine` (signaux keyword sur narratif → score par droit AAH/PCH/CMI/RQTH), `evidence_engine` (narratif = preuve).
- **NIVEAU 4 (influence un CERFA)** : `cerfa_filler` P8 → cases AVQ ; `cerfa_gate_engine` (blocage export selon présence narratif).
- **NIVEAU 5 (plusieurs moteurs)** : `analyse_situation_engine` (consomme narratifs + re-LLM + agrège, alimente cockpit et `analyse_situation_json`).

---

## ÉTAPE 5 — AUDIT DES MOTEURS MAJEURS

### Analyse de situation — **CONTAMINÉ (niveau 5)**
Reçoit `textes_narratifs` (orchestration L1005), itère dessus (L447) et les **réinjecte dans un prompt LLM** (L485-510). Le texte généré devient entrée d'une nouvelle analyse LLM → boucle généré→généré. Sortie : `analyse_situation_json` (consommée par le cockpit).

### Cockpit professionnel — **STRUCTURÉ en surface, contaminé en amont**
`professional_cockpit_engine.generer_cockpit` ne lit **pas** directement `texte_*` (aucune occurrence de narratif/impact dans le moteur). ✅ Bonne nouvelle. **MAIS** il est alimenté par `analyse_situation_json` / la chaîne FACILIM prod, déjà contaminés. → **contamination héritée**, pas native.

### Eligibility Engine — **CONTAMINÉ (niveau 3, le plus grave par impact)**
`_construire_texte` (L77-83) agrège `texte_b/c/d/e` (🟥) avec les champs déclarés dans **un seul blob** `texte`, passé à **tous** les `_analyser_*` (AAH, PCH, CMI×3, RQTH, AEEH, ESAT, SAMSAH…). `_signal(texte, patterns)` (L109) fait du keyword-matching → **chaque droit voit sa probabilité influencée par de la prose générée.**

### Droits oubliés — **CONTAMINÉ (via eligibility)**
Les « droits oubliés » sont produits par la même chaîne d'éligibilité (cockpit `droits_oublies`, orchestration L1095) → héritent de la contamination de l'eligibility engine.

### CDAPH Strategy — **CONTAMINÉ (niveau 2-3)**
`_texte_complet` (L86-91) inclut `texte_b/c/d/e` ; score **selon la longueur** du narratif (L148-155 : >800 / >300 / >100 chars). Sérialisé dans `analyse_situation_json` (L876).

### Evidence Engine — **CONTAMINÉ (niveau 3, le plus grave conceptuellement)**
`_extraire_narratifs` (L292) : commentaire littéral *« Extrait les preuves des narratifs générés (B/C/D/E) »*. Le moteur censé identifier les **preuves** traite la **prose auto-générée** comme preuve. C'est la contamination à l'état pur.

### Gate CERFA — **CONTAMINÉ (niveau 4)**
`_verif_narratifs` (L249-263) : blocage si `len(texte_b) < 50` ou `len(texte_d) < 30`. La décision d'autoriser l'export dépend de la **présence/longueur** d'un texte généré (récompense la verbosité, pas la véracité).

---

## ÉTAPE 6 — CHAÎNES À RISQUE

**Chaîne 1 — AVQ / CERFA (déjà documentée)**
`bilan → _composer_description_p8 (cerfa_filler L116-141) → description_situation → réinjection L1791 → détecteur AVQ L1804-1821 → cases P6/P7`. Impact : **affirmations fonctionnelles inventées dans le CERFA.**

**Chaîne 2 — Droits**
`narratif LLM (texte_b/c/d/e) → eligibilite_droits L77-83 (_construire_texte) → _signal keyword L109 → score par droit → droits_identifies → cockpit / CERFA P17`. Impact : **un droit peut être renforcé par une phrase que FACILIM a lui-même écrite.**

**Chaîne 3 — Score de solidité**
`texte_b/dc → dossier_strength POIDS 0.35 + scoring par longueur L96-98/L138-141 → score_global`. Impact : **un dossier paraît plus solide parce que le LLM a écrit plus de texte.**

**Chaîne 4 — Analyse / cockpit**
`textes_narratifs → analyse_situation_engine L485-510 (re-LLM) → analyse_situation_json → cockpit`. Impact : **boucle généré→analysé→affiché comme synthèse professionnelle.**

**Chaîne 5 — Gate**
`texte_b length → cerfa_gate_engine L249-263 → décision PASS/BLOCK export`. Impact : **export gouverné par la longueur du narratif.**

---

## ÉTAPE 7 — RÉPONSE À LA QUESTION PRINCIPALE

**FACILIM est aujourd'hui en configuration B :**
```
Preuves
   ↓
Narratifs  (générés tôt — orchestration_engine L922-939, AVANT analyse/décision)
   ↓
Moteurs    (eligibility, strength, evidence, cdaph, analyse, gate, cerfa)
```
Les narratifs sont produits **en premier** (orchestration step 1) puis **consommés** par les moteurs décisionnels (steps 3-4). FACILIM **raisonne en partie sur sa propre prose**, pas uniquement sur les preuves déclarées.

> Nuance honnête : les moteurs lisent AUSSI les champs déclarés (`impact_quotidien`, `diagnostics`, `_document_knowledge`). Ce n'est donc pas « 100 % narratif » — c'est un **mélange non séparé** où le généré pèse significativement (jusqu'à 35 % du score de solidité, et un signal direct sur chaque droit).

---

## MODE AUDIT FACILIM

### CE QUI EST PROUVÉ
- **7 moteurs** lisent des narratifs générés par FACILIM comme entrée non-affichage : `cerfa_filler` (P8/AVQ), `eligibilite_droits`, `cdaph_strategy`, `dossier_strength`, `evidence`, `analyse_situation`, `cerfa_gate` (références lignes ci-dessus).
- `dossier_strength` attribue **35 %** du score global à la qualité/longueur du narratif (POIDS L61-62).
- `evidence_engine` **nomme explicitement** les narratifs générés comme « preuves » (L292).
- `eligibilite_droits` fusionne `texte_b/c/d/e` dans le blob keyword-matché par **tous** les analyseurs de droits (L77-83).
- Les narratifs sont générés **avant** l'analyse (orchestration L922 → L1005) → réinjection effective.
- Motif systémique `_construire_texte`/`_texte_complet`/`all_text` mélangeant déclaré + généré, présent dans ≥3 moteurs.

### CE QUI EST DÉCLARÉ
- Le cockpit (`professional_cockpit_engine`) ne lit pas directement les narratifs (entrée structurée) — contamination **héritée** seulement.
- `field_mapper` V3 + Vague 1 utilisent les `avq_*` structurés (mais conservent un fallback keyword).

### CE QUI EST NON VÉRIFIÉ
- L'**ampleur quantitative** du basculement d'un droit dû au seul narratif (les `_signal` ajoutent des points ; je n'ai pas isolé, droit par droit, le delta exact attribuable au généré vs au déclaré).
- Le comportement **en production sur CECORA** (données prod inaccessibles — `railway ssh` bloqué, non contourné).
- Si `analyse_situation_json` réinjecté influence un **2ᵉ tour** de génération (boucle multi-passes) au-delà de ce qui est lu ici.

### RISQUE PRINCIPAL
FACILIM peut **se citer lui-même comme preuve** : une phrase écrite par son LLM (potentiellement inventée, cf. audit P8) augmente un score, valide un droit, et débloque l'export — sans nouvelle preuve réelle. Auto-renforcement circulaire de l'erreur.

### GOULOT D'ÉTRANGLEMENT
Le **blob de texte mixte** (`_construire_texte`/`_texte_complet`) qui **ne sépare pas** preuve déclarée et prose générée. Tant que ce mélange existe, chaque moteur keyword/score est contaminable.

### MOTEUR LE PLUS À RISQUE
- **Par impact :** `eligibilite_droits_engine` (niveau 3 — détermine les droits, le résultat final pour l'usager).
- **Par principe :** `evidence_engine` (traite le généré comme preuve — l'erreur conceptuelle fondatrice).

### PREMIÈRE LIGNE DE CODE À RISQUE
`app/engines/eligibilite_droits_engine.py` **L82-83** (inclusion de `texte_b_vie_quotidienne`/`texte_c/d/e` dans le texte décisionnel des droits), au même rang que `services/cerfa_filler.py` **L1791** (réinjection P8 → AVQ).

### NIVEAU DE CONTAMINATION
```
SYSTÉMIQUE
```
Justification : ≥7 moteurs, couvrant **scoring, droits, preuve, stratégie, analyse, gate et CERFA** — soit l'ensemble de la chaîne décisionnelle, via un motif de conception répété.

---

## CRITÈRE DE RÉUSSITE — réponses

1. **Le problème P8 est-il isolé ?** ❌ Non.
2. **Existe-t-il ailleurs ?** ✅ Oui, dans ≥6 autres moteurs.
3. **Moteurs contaminés :** cerfa_filler (P8/AVQ), eligibilite_droits, cdaph_strategy, dossier_strength, evidence_engine, analyse_situation, cerfa_gate.
4. **Moteurs sûrs :** professional_cockpit_engine (entrée structurée, contamination héritée seulement), collecte_schema / agents (structuré), field_mapper V3 sur le chemin `avq_*` (Vague 1).
5. **Preuves ou narratifs ?** FACILIM raisonne **en partie sur ses propres narratifs** (configuration B).
6. **Local ou systémique ?** **SYSTÉMIQUE**.
7. **Prochain chantier prioritaire :** **séparer preuve déclarée et prose générée** dans toute la chaîne décisionnelle — c.-à-d. interdire aux moteurs de score/droit/evidence/gate/AVQ de lire les champs 🟥 générés, et les faire décider **uniquement** sur le déclaré 🟩 + le structuré 🟦. (Conception uniquement — aucune modification dans cet audit.)

---

*Audit lecture seule. Aucun moteur, prompt, CERFA, gate, scoring modifié. Limites : données de production inaccessibles ; delta quantitatif par droit non isolé.*
