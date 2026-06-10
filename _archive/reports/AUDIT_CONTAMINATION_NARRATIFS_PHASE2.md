# AUDIT_CONTAMINATION_NARRATIFS_PHASE2.md — Audit exhaustif final (local ou systémique ?)

**Généré le :** 2026-06-07
**Mode :** AUDIT LECTURE SEULE. Aucune correction, aucun refactoring, aucune implémentation, aucun déploiement.
**Objet :** terminer l'audit en lisant le **code décisionnel réel** de chaque moteur restant (eligibility, droits_oubliés, CDAPH, cockpit, gate, orchestration) et trancher : **LOCAL ou SYSTÉMIQUE**.
**Verdict :** **SYSTÉMIQUE.** La contamination atteint l'ensemble de la chaîne décisionnelle, **jusqu'au cockpit lu par le professionnel ESSMS**.

---

## 0. Rappel des 3 contaminations déjà prouvées (Phase 1)
1. **CERFA P8 → détecteur AVQ** (cases inventées). 2. **dossier_strength** (≈35 % du score = narratif). 3. **evidence_engine** (narratif = preuve).
Cette Phase 2 confirme par lecture **eligibility, droits_oubliés, CDAPH, cockpit, gate, orchestration** + **corrige** une conclusion Phase 1 sur le cockpit.

---

## ÉTAPE 1 — MATRICE PRODUCTEUR → CONSOMMATEUR (complétée, lignes vérifiées)

| Producteur (🟥 généré) | Consommateur | Lieu exact (vérifié) | Impact |
|---|---|---|---|
| `description_situation` (P8) | détecteur AVQ | `services/cerfa_filler.py` L1791 → L1804-1821 | **ÉLEVÉ** |
| `texte_b` | dossier_strength | `dossier_strength_engine.py` POIDS L61-62, `_evaluer_narratif_b` L131-162 | **ÉLEVÉ** |
| `texte_b/c/d/e` | evidence_engine | `evidence_engine.py` L292-311 `_extraire_narratifs` | **ÉLEVÉ** |
| `texte_b/c/d/e` | **eligibility** | `eligibilite_droits_engine.py` L82-83 `_construire_texte` → `_signal()` L109-117 → `_analyser_aah` L161-166 (`score += 22`) etc. | **ÉLEVÉ (droits)** |
| eligibility (droits non demandés) | **droits oubliés** | sortie cockpit `droits_oublies` (`facilim_prod.py`, `orchestration_engine.py` L1095) | **ÉLEVÉ (droits)** |
| `texte_b` (longueur) | **CDAPH** | `cdaph_strategy_engine.py` `_evaluer_preuves` L148-157 (`len>800 → +30`), `_texte_complet` L86-91 | **ÉLEVÉ (score+stratégie)** |
| CDAPH + evidence | **cockpit** | `professional_cockpit_engine.py` L411-412 (appelle CDAPH + evidence), **L427 `score = rapport_cdaph.score_solidite`** | **ÉLEVÉ (score affiché)** |
| `texte_b/d` (présence) | **gate export** | `cerfa_gate_engine.py` L314 `_verif_narratifs` → L319-323 `autorise_export` | **ÉLEVÉ (export)** |
| narratifs | **orchestration → analyse** | `orchestration_engine.py` L922-939 (génère) → L1005 (`analyser_situation(textes_narratifs=…)`) → `analyse_situation_engine.py` L447, L485-510 (re-LLM) | **ÉLEVÉ (boucle)** |

---

## ÉTAPE 2 — NIVEAU DE RISQUE PAR MOTEUR (lecture confirmée)

### eligibility_engine — **CONTAMINÉ (le plus grave par impact)**
- **Entrées :** `_construire_texte` (L77-106) agrège **`texte_b/c/d/e`** (🟥) + déclaré + `_document_knowledge` dans **un seul blob `texte`**.
- **Calcul :** chaque `_analyser_*` (AAH L144, PCH L217, CMI×3, RQTH L403, AEEH, ESAT…) appelle `_signal(texte, [patterns])` (L109) → `score += 15..25` (ex. L163 `+22`, L166).
- **Critères :** `_score_to_proba` (L120), `_score_to_confiance` (L127) dérivent du score contaminé.
- **Verdict :** un droit voit sa probabilité monter si le **narratif généré** contient « invalidité 2ᵉ catégorie », « inaptitude », etc. — **trust du CONTENU généré**, le cas le plus dangereux.

### droits_oubliés — **CONTAMINÉ (hérité d'eligibility)**
Pas un moteur isolé : ce sont les droits **bien notés mais non demandés** issus de la même chaîne d'éligibilité (champ `droit_demande` L154 + `droits_set`). Donc même contamination que l'eligibility.

### cdaph_strategy — **CONTAMINÉ**
- `_texte_complet` (L86-91) inclut `texte_b/c/d/e`.
- `_evaluer_preuves` (L142-192) — sous-note **« 35 % preuves objectives »** — **commence par** `len(texte_b) > 800 → +30` (L148-157). Une note nommée « preuves objectives » est partiellement pilotée par la **longueur d'un texte généré**.
- L174 : `re.search("diagnos|bilan|certificat…", texte)` sur le blob incluant le narratif → +20.
- *Atténuation :* lit aussi `notes_pro`, `_document_knowledge`, `expression_directe`, dates (déclaré) → mélange, pas 100 % généré.

### cockpit_professionnel — **CONTAMINÉ PAR COMPOSITION** ⚠️ *(correction de la Phase 1)*
La Phase 1 le disait « structuré / contamination héritée ». **Lecture L405-427 :** `generer_cockpit` **appelle** `analyser_strategie_cdaph` (L411) et `construire_graphe_preuves` (evidence, L412), puis **`score = rapport_cdaph.score_solidite` (L427)**. Le **score affiché au professionnel ESSMS est le score CDAPH contaminé** ; `droits_solides/fragiles` viennent de CDAPH. Le cockpit ne lit pas les `texte_*` lui-même, mais **il EST l'agrégateur des moteurs contaminés**. → contaminé, activement.

### gate_export — **CONTAMINÉ (présence, pas véracité)**
`verifier_gate_cerfa` (L279-323) agrège `_verif_narratifs` (L314) ; si `len(texte_b) < 50` (L252-253) → blocage ; `autorise_export = len(bloquants)==0` (L323). La décision **AUTORISE / RÉSERVE / BLOQUE** dépend donc de la **présence/longueur** d'un narratif généré. *Nuance :* contrôle d'**existence**, pas de confiance dans le contenu — contamination réelle mais moins perverse qu'eligibility.

### orchestration_engine — **VECTEUR DE CONTAMINATION**
Génère les narratifs **en premier** (L922-939) puis les **réinjecte** dans `analyser_situation(textes_narratifs=…)` (L1005). Ne décide pas lui-même mais **organise** la boucle preuve→narratif→moteur.

### evidence_engine — **CONTAMINÉ (garde-fou partiel)**
`_extraire_narratifs` (L292) ajoute `texte_b/c/d/e` comme `EvidenceItem` d'origine **« Narratif »** ; `_extraire_declarations` (L314) tague « Déclaration » ; documents « Document ». → **le moteur connaît l'origine** (métadonnée `EvidenceItem.origine`) — garde-fou partiel — **mais** les narratifs entrent quand même dans le graphe de preuves.

---

## ÉTAPE 3 — CHAÎNES DE CONTAMINATION COMPLÈTES

**Chaîne A — la plus critique (droits + décision pro + CERFA) :**
```
bilan/preuve
  ↓ generer_textes_narratifs (texte_b)              [généré]
  ↓ eligibilite_droits _construire_texte L82 → _signal L109 → score droit
  ↓ CDAPH _evaluer_preuves L148 (len texte_b) → score_solidite
  ↓ cockpit L427 score = score CDAPH + droits_solides/fragiles
  ↓ AFFICHÉ AU PROFESSIONNEL ESSMS (go/no-go) + droits_oublies + CERFA P17
```

**Chaîne B — AVQ / CERFA (Phase 1) :**
```
preuve → _composer_description_p8 → description_situation → réinjection L1791 → cases AVQ P6/P7
```

**Chaîne C — Gate :**
```
texte_b (longueur) → _verif_narratifs L314 → blocages → autorise_export L323 → PASS/WARNING/BLOCK
```

**Chaîne D — Boucle d'analyse :**
```
textes_narratifs → analyse_situation L485-510 (re-LLM) → analyse_situation_json → cockpit
```

---

## ÉTAPE 4 — CARTOGRAPHIE DE CONFIANCE

### 🟩 MOTEURS DE CONFIANCE (décident sur structuré / déclaré uniquement)
- **`collecte_schema` + agents de conversation** : champs structurés (Vague 1), aucune décision sur prose générée.
- **`field_mapper` (V3) — chemin `avq_*` / `droits.*`** : cases pilotées par champs **structurés** Vague 1 *(réserve : conserve un fallback keyword sur `impact`)*.
- **`human_validation_engine`** : validation humaine (l'humain tranche) — par construction non auto-contaminé.
- **`export_gate.py` (`lire_gate_export`)** : se contente de **relire** la décision `gate_export` du cockpit (ne calcule rien sur du narratif) — *mais relaie une décision elle-même contaminée en amont*.

### 🟥 MOTEURS CONTAMINÉS (décident en partie sur du texte généré)
`cerfa_filler` (P8→AVQ) · `eligibilite_droits` · `droits_oublies` (hérité) · `cdaph_strategy` · `dossier_strength` · `evidence_engine` · `professional_cockpit` (composition) · `cerfa_gate` · `analyse_situation` (+ vecteur `orchestration`).

> **Constat :** aucun moteur **décisionnel** n'est totalement sûr ; les seuls sûrs sont les couches de **collecte/structuration** et la **validation humaine**.

---

## ÉTAPE 5 — IMPACT PILOTE ESSMS

| Contamination | Type d'effet | Impact ESSMS |
|---|---|---|
| eligibility → droits | décision de droit | **ÉLEVÉ** |
| droits_oublies | suggestion de droit | **ÉLEVÉ** |
| CDAPH → cockpit score | go/no-go affiché au pro | **ÉLEVÉ** |
| P8 → AVQ CERFA | document officiel | **ÉLEVÉ** |
| gate export | autorise/bloque le dépôt | **ÉLEVÉ** (présence) |
| evidence (preuve) | graphe de preuves | **ÉLEVÉ** |
| dossier_strength | score/indicateur | **MOYEN** |
| affichage narratifs dashboard | lecture seule | **FAIBLE** |

Pour un **pilote ESSMS**, le risque dominant : un professionnel voit un **score « solide »**, des **droits « probables »** et un **CERFA « complet »** qui reposent partiellement sur de la **prose générée par FACILIM**, pas sur des preuves vérifiées.

---

## MODE AUDIT FACILIM

### CE QUI EST PROUVÉ
- **eligibility** intègre `texte_b/c/d/e` dans le texte décisionnel des droits (L82-83) et score par `_signal` (L109/161-166).
- **CDAPH** score la sous-note « preuves objectives » selon `len(texte_b)` (L148-157).
- **cockpit** expose `score = rapport_cdaph.score_solidite` (L427) et appelle CDAPH + evidence (L411-412) → contaminé par composition.
- **gate** fait dépendre `autorise_export` de la présence narrative (L314/323).
- **orchestration** génère les narratifs avant l'analyse et les y réinjecte (L922→L1005).
- **evidence** range les narratifs comme `EvidenceItem` (L292) tout en taguant l'origine.

### CE QUI EST DÉCLARÉ
- `evidence_engine` **tague l'origine** (Narratif/Déclaration/Document) → garde-fou partiel exploitable pour un futur correctif.
- CDAPH/eligibility lisent **aussi** du déclaré (`_document_knowledge`, `notes_pro`, `expression_directe`) → contamination **partielle**, pas exclusive.
- Le cockpit ne lit pas `texte_*` directement (contamination uniquement via CDAPH/evidence).

### CE QUI EST NON VÉRIFIÉ
- Le **delta quantitatif** exact (combien de points / quels droits basculent) attribuable au seul généré vs déclaré — mécanisme prouvé, ampleur non chiffrée.
- Si les consommateurs du graphe de preuves **respectent** le tag `origine` (sinon le garde-fou est inopérant) — non tracé jusqu'au bout.
- Comportement **en production** (données CECORA inaccessibles ; `railway ssh` bloqué, non contourné).

### RISQUE PRINCIPAL
**Auto-référence circulaire jusqu'au professionnel** : FACILIM écrit un narratif → ce narratif augmente un score, valide un droit, et débloque l'export → le professionnel ESSMS lit un dossier « solide » fondé en partie sur la prose de l'outil, pas sur des preuves.

### GOULOT D'ÉTRANGLEMENT
Le **blob de texte mixte** (`_construire_texte` / `_texte_complet`) qui **fusionne déclaré + généré** sans séparation, présent à l'identique dans eligibility et CDAPH (et la réinjection P8). Un seul motif de conception alimente toute la contamination.

### MOTEUR LE PLUS CONTAMINÉ
**`eligibilite_droits_engine`** — il fait **confiance au contenu** du narratif généré pour décider des **droits** (le résultat final pour l'usager), et propage vers droits_oublies + cockpit + CERFA P17.

### MOTEUR LE PLUS FIABLE
La couche **collecte structurée** (`collecte_schema` + agents Vague 1) et **`human_validation_engine`** (l'humain tranche) — seuls éléments non auto-contaminés.

### CHAÎNE DE CONTAMINATION LA PLUS CRITIQUE
**Chaîne A** : `narratif → eligibility/CDAPH → cockpit (score + droits affichés au pro ESSMS) → CERFA/gate`. C'est celle qui atteint **à la fois** la décision humaine et le document officiel.

### NIVEAU GLOBAL
```
SYSTÉMIQUE
```
**Justification :** la contamination touche **tous** les étages décisionnels — AVQ/CERFA, score de solidité, éligibilité aux droits, droits oubliés, stratégie CDAPH, cockpit professionnel, gate d'export, boucle d'analyse — via **un motif de conception unique et répété** (blob mixte déclaré+généré). Ce n'est pas un défaut local de P8 : c'est une propriété de l'architecture actuelle.

---

## CRITÈRE DE RÉUSSITE — réponses

1. **Moteurs qui utilisent des narratifs :** cerfa_filler(P8), eligibility, droits_oublies, cdaph, dossier_strength, evidence, cockpit(composition), gate, analyse_situation.
2. **Moteurs totalement sûrs :** collecte_schema + agents, human_validation_engine ; (field_mapper sur chemin `avq_*` sous réserve du fallback keyword).
3. **Moteurs décidant à partir de textes générés :** eligibility (droits), cdaph+cockpit (score/go-no-go), cerfa_filler (cases CERFA), gate (export).
4. **Local ou systémique :** **SYSTÉMIQUE**.
5. **Moteur à traiter en premier :** **`eligibilite_droits_engine`** (impact droits, trust du contenu) — en attaquant le motif `_construire_texte` (séparer déclaré/généré). *(Constat de priorité, pas d'implémentation.)*
6. **FACILIM raisonne sur les preuves ou sur ses productions :** **en partie sur ses propres productions** (configuration B), désormais confirmé **jusqu'au cockpit professionnel**.

---

*Audit lecture seule. Aucun moteur, prompt, score, CERFA, mapping modifié. Limites : delta quantitatif non isolé ; respect du tag d'origine evidence non tracé ; production inaccessible.*
