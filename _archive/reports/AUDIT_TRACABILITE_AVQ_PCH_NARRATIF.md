# AUDIT_TRACABILITE_AVQ_PCH_NARRATIF.md — D'où viennent les limitations fonctionnelles du CERFA ?

**Généré le :** 2026-06-07
**Dossier :** CECORA Marie-Christine (PCR — France Travail / RICHEBOIS) · CERFA `CF TEST FACILIM 4.4.pdf`
**Mode :** AUDIT LECTURE SEULE. Aucune correction, aucune modification, aucun déploiement.
**Sources analysées :** bilan PCR (docx, intégral) ; CERFA PDF (21 pages) ; code de la chaîne (`services/cerfa_filler.py` V2 = chemin prod, `cerfa_narrative_engine.py`, `inferencer_mdph.py`, `section_b.py`). **Données de production (synthese_json / analyse_situation_json / cockpit_pro_json / conversation) NON accessibles** : le dossier a été produit en prod (volume Railway) ; `railway ssh` est bloqué par garde-fou et **n'a pas été contourné**. La base locale contient 0 dossier.

---

## 0. RÉPONSE COURTE (les 7 questions du critère de réussite)

1. **Pourquoi les cases AVQ sont cochées ?** Par **détection de mots-clés** (`services/cerfa_filler.py` L1804-1821) appliquée à un texte qui inclut le **narratif P8 généré par LLM** (réinjecté en L1791).
2. **Pourquoi certaines limitations apparaissent ?** Parce que le **prompt du narratif P8** (`_composer_description_p8`, L116-141) demande « **fort impact** », cadre tout en « **ce qu'elle ne peut pas faire seule** », et **donne en exemple** « *a besoin d'aide pour préparer ses repas* » — **sans aucune règle anti-invention**.
3. **Prouvées / inférées / inventées ?** Ménage, fatigabilité, station debout, répit = **PROUVÉ** (bilan). Aide toilette / habillage / repas = **INVENTÉ** (absent du bilan). « Ne peut se lever seule » = **AMPLIFIÉ** (source réelle « difficulté station debout prolongée », transformée en dépendance).
4. **Où la transformation se produit ?** Premier point : le **prompt P8** (génération) ; second point : le **détecteur de cases par mots-clés** + sa **boucle de réinjection** (L1791).
5. **Première cause racine ?** `_composer_description_p8` : prompt amplificateur **sans garde-fou**, alors qu'un prompt anti-invention existe ailleurs (`cerfa_narrative_engine._prompt_section_b`).
6. **Dossier fidèle ou amplifié ?** **Amplifié** sur l'axe AVQ/aide humaine.
7. **Risque MDPH ?** **ÉLEVÉ** (affirmations fonctionnelles non démontrées dans un document certifié sur l'honneur).

---

## ÉTAPE 1 — INVENTAIRE CERFA (affirmations fonctionnelles observées)

> ⚠️ Le CERFA est un PDF **aplati** : pypdf ne lit que les libellés du template, pas les cases cochées (dessinées en surcouche). L'inventaire ci-dessous reprend les affirmations **rapportées par l'utilisateur** + les libellés CERFA correspondants.

| Élément CERFA | Libellé / texte exact |
|---|---|
| P6 B1 / P7 hygiène | « Pour l'hygiène corporelle (se laver, aller aux toilettes) » → *besoin d'aide pour la toilette* |
| P6 B2 / P7 habillage | « Pour s'habiller (mettre et ôter les vêtements…) » → *besoin d'aide pour l'habillage* |
| P6 B3 / P7 repas | « Pour préparer les repas » → *besoin d'aide pour préparer les repas* |
| P6 B4 / mobilité | mobilité intérieure → *« ne peut pas se lever seule »* |
| P6 7 / P7 2 | aide humaine / mobilité → présence d'aide humaine |

---

## ÉTAPE 2 — RECHERCHE DE LA SOURCE (par élément)

### Bilan PCR — ce qui EST écrit (extraits exacts)
- « Fatigabilité physique et émotionnelle impactant le quotidien et le rythme de vie. »
- « l'évolution récente de sa situation a **renforcé ses limitations dans certains actes de la vie quotidienne (en particulier le ménage)** et accentué sa fatigue physique et émotionnelle. »
- « Elle rencontre également des **difficultés à maintenir une position assise ou debout prolongée** au regard de ses problématiques santé. »
- « besoin important de **répit**, de soutien et de recentrage sur elle-même. »
- « les **difficultés de santé et l'épuisement** actuellement observés… »

### Bilan PCR — ce qui N'EST PAS écrit (recherche exhaustive, 0 occurrence)
`toilette` ❌ · `hygiène` ❌ · `se laver` ❌ · `habillage`/`s'habiller`/`vêtement` ❌ · `repas`/`préparer les repas`/`alimentation`/`cuisine` ❌ · `se lever` ❌ · `aide humaine`/`auxiliaire`/`aide à domicile` ❌ · `ne peut pas seule` ❌.

| Élément CERFA | Bilan PCR | WhatsApp | Synthèse | Analyse situation | Cockpit | Narratif |
|---|---|---|---|---|---|---|
| Aide toilette | **introuvable** | NON VÉRIFIÉ (prod) | NON VÉRIFIÉ (prod) | NON VÉRIFIÉ | NON VÉRIFIÉ | issu du LLM P8 |
| Aide habillage | **introuvable** | NON VÉRIFIÉ | NON VÉRIFIÉ | NON VÉRIFIÉ | NON VÉRIFIÉ | issu du LLM P8 |
| Aide repas | **introuvable** | NON VÉRIFIÉ | NON VÉRIFIÉ | NON VÉRIFIÉ | NON VÉRIFIÉ | **exemple du prompt P8** |
| Ne peut se lever seule | « difficulté station debout prolongée » (≠) | NON VÉRIFIÉ | NON VÉRIFIÉ | NON VÉRIFIÉ | NON VÉRIFIÉ | amplifié par P8 |
| Difficulté ménage | **« en particulier le ménage »** | — | — | — | — | fidèle |
| Fatigabilité | **explicite** | — | — | — | — | fidèle |
| Station debout | **explicite** | — | — | — | — | fidèle |

---

## ÉTAPE 3 — CLASSIFICATION

### PROUVÉ (présent explicitement dans le bilan)
- **Difficulté pour le ménage** — « renforcé ses limitations dans certains actes de la vie quotidienne (en particulier le ménage) ».
- **Fatigabilité physique et émotionnelle** — explicite, répété.
- **Difficulté à maintenir station assise/debout prolongée** — explicite.
- **Besoin de répit / épuisement** — explicite.

### INFÉRÉ / AMPLIFIÉ (source réelle mais affaiblie ou durcie)
- **« Ne peut pas se lever seule »** — la source est « difficulté à maintenir une position **debout prolongée** ». Le CERFA transforme une **gêne d'endurance posturale** en **incapacité à se lever** (dépendance). Inférence **non justifiable en l'état** → glissement léger→fort.

### INVENTÉ (introuvable, aucune déduction justifiable)
- **Besoin d'aide pour la toilette / l'hygiène** — aucune trace, aucun lien logique avec « fatigue + ménage ».
- **Besoin d'aide pour l'habillage** — idem.
- **Besoin d'aide pour préparer les repas** — idem, **et c'est précisément l'exemple écrit dans le prompt P8** (risque d'« amorçage » : le LLM recopie l'exemple).

---

## ÉTAPE 4 — MATRICE DE TRAÇABILITÉ

| Élément CERFA | Source exacte | Niveau |
|---|---|---|
| Difficulté ménage | bilan PCR (« en particulier le ménage ») | **PROUVÉ** |
| Fatigabilité | bilan PCR (« fatigabilité physique et émotionnelle ») | **PROUVÉ** |
| Difficulté station debout | bilan PCR (« position assise ou debout prolongée ») | **PROUVÉ** |
| Besoin de répit | bilan PCR (« besoin important de répit ») | **PROUVÉ** |
| Aide toilette | aucune | **INVENTÉ** |
| Aide habillage | aucune | **INVENTÉ** |
| Aide repas | aucune (exemple du prompt) | **INVENTÉ** |
| Ne peut se lever seule | bilan affaibli (« debout prolongée ») | **AMPLIFIÉ** |

---

## ÉTAPE 5 — PREMIER POINT DE TRANSFORMATION

```
bilan : fatigabilité, difficulté ménage, station debout difficile
   │
   ▼  (synthèse LLM → difficultes_quotidiennes / besoins_aide / impact_quotidien)   [NON VÉRIFIÉ : prod]
   │
   ▼  services/cerfa_filler.py  L1155  description_situation = _composer_description_p8(...)
   │     ↳ PROMPT L116-141 : « fort impact », « ce qu'elle NE PEUT PAS FAIRE SEULE »,
   │       exemple injecté « a besoin d'aide pour préparer ses repas », AUCUN « n'invente rien »
   │     → le LLM produit un narratif de DÉPENDANCE (toilette/habillage/repas/lever)
   │
   ▼  services/cerfa_filler.py  L1789-1794  _detection_b2b3 inclut (description_situation)  ← BOUCLE
   │
   ▼  services/cerfa_filler.py  L1804-1821  mots-clés → cases P6 B1/B2/B3/B4 + L1771 P6 7
   │
   ▼  PDF : cases AVQ cochées + narratif P8 amplifié
```

**Localisation précise :**
- **Fichier :** `services/cerfa_filler.py`
- **Fonction :** `_composer_description_p8` (génération) + corps de `remplir_cerfa…` (détection cases)
- **Lignes :** **L123-124** (cadrage dépendance + « fort impact »), **L136-138** (exemples injectés dont « préparer ses repas »), **L1791** (réinjection du texte LLM dans la détection), **L1804-1821** (mots-clés → cases), **L1811** (« préparer », « repas »), **L1814** (« se lever », « déplacer »).
- **Règle :** « si un mot-clé apparaît dans le texte (y compris narratif généré) → cocher la case ».
- **Prompt :** `_composer_description_p8` (L116-141).
- **Moteur :** générateur CERFA V2 (`services/cerfa_filler.py`).

**Preuve par reproduction** (logique L1804-1821 ré-exécutée à l'identique) :
- **Bilan PCR brut → 0 case AVQ.**
- **Narratif P8 amplifié → coche repas (B3) + mobilité (B4) + aide humaine (P6 7).**
→ L'amplification naît **entre le bilan et le PDF**, dans la génération/détection, pas dans la source.

---

## ÉTAPE 6 — NARRATIF (audit des deux moteurs)

FACILIM possède **deux** générateurs de narratif, **contradictoires** :

| Moteur | Rôle | Garde-fou | Verdict |
|---|---|---|---|
| `cerfa_narrative_engine._prompt_section_b` (texte_b_vie_quotidienne) | « Narratif B » | **« N'invente rien. N'infère rien. Ne suppose rien. [INFO MANQUANTE] si absent »** (L210-212) | ✅ fidèle |
| `services/cerfa_filler._composer_description_p8` (P8 du PDF, **chemin prod**) | description situation | **AUCUN** ; au contraire « fort impact » + « ne peut pas faire seule » + exemples injectés | ❌ amplifie |

- **Phrases fidèles** (P8 conforme au bilan) : fatigabilité, difficulté ménage, station debout, besoin de répit.
- **Phrases amplifiées** : « ne peut pas se lever seule » (← station debout difficile).
- **Phrases non démontrées** : aide toilette, aide habillage, aide repas.

> Le narratif **conservateur** (`_prompt_section_b`) n'est **pas** celui qui remplit le P8 du PDF en V2. Le PDF utilise le narratif **amplificateur** `_composer_description_p8`.

---

## ÉTAPE 7 — P6 / P7 / PCH (origine de chaque case)

| Case | Règle de mapping | Champ source | Justification présente ? |
|---|---|---|---|
| P6 B1 (hygiène/toilette) | mots-clés `hygiène/toilette/se laver` (L1805) | `_detection_b2b3` (inclut narratif P8) | ❌ absente du bilan |
| P6 B2 (habillage) | mots-clés `habillage/s'habill/vêtement` (L1808) | idem | ❌ absente |
| P6 B3 (repas) | mots-clés `repas/préparer/cuisine/manger` (L1811) | idem | ❌ absente (et « préparer » trop large) |
| P6 B4 (mobilité int.) | mots-clés `déplacer/marche/se lever` (L1814) | idem | ⚠️ source affaiblie (station debout) |
| P6 7 (aide humaine) | mots-clés `besoin d'aide/aide pour/ne peut pas seule` (L1758-1769) | narratif + difficultes | ❌ aide humaine jamais déclarée |
| P7 2 (mobilité logement) | `besoins_aide_humaine` (L1830) | booléen synthèse | NON VÉRIFIÉ (prod) |

**Remarque AVQ structuré (Vague 1) :** les champs `avq_*` introduits en Vague 1 alimentent **field_mapper (V3)**, **PAS** `cerfa_filler` (V2). En prod V2, les cases P6/P7 restent **pilotées par mots-clés**, pas par les `avq_*` explicites. La Vague 1 n'a donc **pas** réduit ce risque sur le chemin V2.

---

## ÉTAPE 8 — RISQUE MDPH

- **Risque faible** (champ imprécis) : libellés de mobilité génériques.
- **Risque moyen** (interprétation discutable) : « ne peut pas se lever seule » (amplification d'une gêne réelle).
- **Risque ÉLEVÉ** (affirmation fonctionnelle **non démontrée**) : **aide toilette + aide habillage + aide repas + aide humaine**. Présentées dans un formulaire signé « je certifie sur l'honneur l'exactitude des informations » (CERFA p.5). Conséquences : requalification d'une limitation légère/modérée en dépendance forte, perte de crédibilité du dossier, voire exposition de la personne (art. L114-19 CSS / 441-1 code pénal cités sur le CERFA).

---

## MODE AUDIT FACILIM

### CE QUI EST PROUVÉ
- Le **bilan PCR ne contient aucune** mention de toilette/hygiène/habillage/repas/aide humaine/« se lever » (recherche exhaustive, 0 occurrence).
- La **logique de cochage AVQ** est un **keyword-matching** (L1804-1821) appliqué à un texte **incluant le narratif P8 généré** (réinjection L1791).
- Le **prompt P8** (`_composer_description_p8`, L116-141) est **amplificateur** : « fort impact », cadrage « ne peut pas faire seule », **exemple injecté « besoin d'aide pour préparer ses repas »**, **sans règle anti-invention**.
- Un **prompt anti-invention existe** (`_prompt_section_b`, L210-212) mais **n'est pas** le générateur du P8 en V2.
- **Reproduction** : bilan brut → 0 case ; narratif amplifié → cases repas/mobilité/aide humaine.

### CE QUI EST INFÉRÉ
- « Ne peut pas se lever seule » dérive de « difficulté à maintenir une station debout prolongée » → **inférence durcie, non justifiable**.
- Les valeurs AVQ observées proviennent de la **synthèse/narratif LLM** (forte présomption, le bilan n'en contenant aucune).

### CE QUI EST INVENTÉ
- **Aide toilette, aide habillage, aide repas** : aucune source, aucune déduction valable.

### CE QUI EST NON VÉRIFIÉ
- `synthese_json`, `analyse_situation_json`, `cockpit_pro_json`, `conversation_json` **réels** de CECORA (production inaccessible ; `railway ssh` bloqué, non contourné).
- Si toilette/habillage proviennent du **phrasé clinique de la synthèse** (« hygiène ») ou du **narratif P8** précisément (les deux mènent au même cochage).
- L'état **exact** des cases du PDF (aplati, surcouche non lisible par pypdf).

### RISQUE PRINCIPAL
Transformer une **limitation légère/modérée** (fatigabilité, ménage, posture) en **dépendance fonctionnelle forte** (aide pour toilette/habillage/repas/lever) dans un document certifié sur l'honneur. **`champ vide < information fausse`** — exactement le risque redouté.

### GOULOT D'ÉTRANGLEMENT
Le **narratif P8 généré par LLM est réinjecté dans le détecteur de cases** (L1791) : un texte « rédigé pour avoir du fort impact » devient automatiquement des **cases cochées**. Texte amplifié → cases amplifiées.

### PREMIÈRE LIGNE DE CODE RESPONSABLE
`services/cerfa_filler.py` **L137** (exemple injecté « a besoin d'aide pour préparer ses repas ») et **L123-124** (« ce qu'elle ne peut pas faire seule » + « fort impact »), aggravées par **L1791** (réinjection) et **L1811/1814** (mots-clés trop larges « préparer », « déplacer », « se lever »).

### PREMIER CHAMP RESPONSABLE
`description_situation` (narratif P8) — généré par prompt amplificateur **puis réutilisé** comme source de détection des cases. En amont : `difficultes_quotidiennes` / `besoins_aide` (synthèse, non vérifiés).

### PREMIER PROMPT RESPONSABLE
`_composer_description_p8` (`services/cerfa_filler.py`, L116-141).

### CORRECTION MINIMALE ENVISAGEABLE *(description uniquement — aucune modification réalisée)*
1. **Aligner le prompt P8 sur la règle anti-invention** déjà présente dans `cerfa_narrative_engine._prompt_section_b` : ajouter « N'invente rien. N'infère rien. [INFO MANQUANTE] si absent », **supprimer** « fort impact » et le cadrage « ne peut pas faire seule », **retirer les exemples concrets** (surtout « préparer ses repas »).
2. **Ne plus réinjecter** la sortie LLM (`description_situation`) dans `_detection_b2b3` (L1791) : ne cocher les cases AVQ que sur des **champs structurés explicites** (les `avq_*` de Vague 1 / besoins déclarés), jamais sur du texte narratif généré.
3. **Restreindre les mots-clés** trop larges (retirer « préparer », « déplacer » seuls ; exiger un motif « aide pour … » couplé).
4. **Cible** : faire de V2 (`cerfa_filler`) un consommateur des `avq_*` structurés (comme field_mapper V3) → une case n'est cochée que si un niveau AVQ ≥ DIFFICULTÉ est **explicitement collecté**.

---

## PREUVES — extraits exacts

- **Bilan (PROUVÉ)** : « renforcé ses limitations dans certains actes de la vie quotidienne (en particulier **le ménage**) » ; « difficultés à maintenir une **position assise ou debout prolongée** » ; « **fatigabilité** physique et émotionnelle ».
- **Bilan (ABSENCE)** : 0 occurrence de toilette / hygiène / habillage / repas / se lever / aide humaine.
- **Code prompt P8 (cause)** : L123 « ce qu'elle ne peut pas faire seule » ; L137 « a besoin d'aide pour préparer ses repas » ; (pas de « n'invente rien »).
- **Code détection (mécanisme)** : L1791 réinjection ; L1811 `["repas","préparer",…]` ; L1814 `["déplacer","se lever",…]`.
- **Code narratif conservateur (contraste)** : L210-212 « N'invente rien. N'infère rien. Ne suppose rien. ».
- **CERFA p.5 (enjeu)** : « En cochant cette case, je certifie sur l'honneur l'exactitude des informations déclarées. » + art. L114-19 / 441-1.

---

*Audit lecture seule. Aucun moteur, prompt, CERFA, gate, audit, scoring modifié. Conclusions limitées par l'inaccessibilité des données de production (railway ssh bloqué, non contourné).*
