# AUDIT_IMPACT_CONTAMINATION.md — Combien de décisions changeraient sans les narratifs générés ?

**Généré le :** 2026-06-07
**Mode :** AUDIT D'IMPACT — LECTURE SEULE. Aucune correction, modification, réécriture ou déploiement.
**Question centrale :** si l'on retirait **totalement** les narratifs générés (`texte_b/c/d/e = ""`) des moteurs décisionnels, combien de décisions FACILIM changeraient ?
**Réponse courte :** beaucoup. **~35 % à ~45 %** du score de solidité, l'essentiel du score CDAPH/cockpit, une partie des signaux d'éligibilité, et la décision d'export du gate dépendent du généré. **Mais** la simulation `texte_*=""` **ne neutralise PAS** la contamination AVQ→CERFA (qui passe par un autre champ généré, `description_situation`).

---

## ⚠️ AVERTISSEMENT MÉTHODOLOGIQUE (à lire en premier)

Il existe **deux familles** de texte généré, pas une :
- **Famille 1 — `texte_b/c/d/e`** (produits par `cerfa_narrative_engine`) → consommés par eligibility, CDAPH, dossier_strength, evidence, gate, analyse_situation. **C'est ce que la simulation `texte_*=""` mesure.**
- **Famille 2 — `description_situation`** (produit par `cerfa_filler._composer_description_p8`, P8) → réinjecté dans le détecteur AVQ (cerfa_filler L1791). **Champ DIFFÉRENT : vider `texte_b/c/d/e` ne le supprime pas.**

➡️ **Conséquence :** la simulation proposée sous-estime le problème. Elle nettoie la contamination « Phase 2 » mais **laisse intacte la contamination AVQ→CERFA** (la plus grave côté document officiel). Tout plan de correction doit traiter **les deux familles**.

---

## ÉTAPE 1 — CARTOGRAPHIE DES ENTRÉES (par moteur)

**Légende :** 🟩 PREUVE (déclaré/structuré/document) · 🟥 NARRATIF (généré FACILIM)

| Moteur | Entrées 🟩 PREUVE | Entrées 🟥 NARRATIF |
|---|---|---|
| **eligibility** (`_construire_texte` L79-104) | diagnostics, impact_quotidien, restrictions_emploi, statut_emploi, droits_demandes, `_document_knowledge`, `_verbatim_*` | **texte_b, texte_c, texte_d, texte_e** (L82-83) |
| **droits_oubliés** | (= sortie eligibility) | (hérite de eligibility) |
| **cdaph_strategy** (`_texte_complet` L86-91) | diagnostics, impact, notes_pro, `_document_knowledge`, expression_directe, dates | **texte_b/c/d/e** ; `_evaluer_preuves` `len(texte_b)` L148 |
| **dossier_strength** (POIDS L59-67) | impact_quotidien, restrictions, notes_pro, diagnostics, `_verbatim_*` | **texte_b (20%)**, **texte_dc (15%)**, texte_b dans retentissement (L91-98), texte_e (projet) |
| **cockpit** (`generer_cockpit` L405-427) | — (aucune lecture directe de texte_*) | **indirect** : `score = rapport_cdaph.score_solidite` (L427) + droits CDAPH + graphe evidence |
| **gate export** (`verifier_gate_cerfa` L279-323) | identité, validation humaine, complétude, pièces | **texte_b/d** présence (`_verif_narratifs` L314) |
| **evidence_engine** (L292-333) | diagnostics, impact, restrictions, `_document_knowledge` (taggés Déclaration/Document) | **texte_b/c/d/e** (taggés « Narratif », L292) |
| **analyse_situation** (L263-510) | données structurées | **textes_narratifs** réinjectés dans un prompt LLM (L485-510) |
| **cerfa_filler P8/AVQ** (Famille 2) | difficultes_quotidiennes, besoins_aide (🟩) | **description_situation** réinjecté (L1791) → cases AVQ |

---

## ÉTAPE 2 — POIDS DES NARRATIFS (quantifié sur le code)

| Moteur | Dépendance narratif (🟥) | Base (lignes) |
|---|---|---|
| **dossier_strength** | **~35 % PROUVÉ** (narratif_b 0.20 + narratif_dc 0.15) **+ ~10-15 %** partiel (retentissement L91-98, projet_vie) → **~45-50 %** | POIDS L59-67, L98, L134, L174 |
| **cdaph_strategy** | **élevée** : blob `texte` alimente 4 sous-scores sur 5 (**95 % du poids** : preuves 0.35 + cohérence 0.25 + retentissement 0.20 + projet 0.15) ; seul justificatifs (0.05) est 🟩 pur. Part **purement** narrative ≈ 15-30 % (ex. `len(texte_b)` = 30/100 de la sous-note preuves = ~10 % global) | L778-783, L148-157 |
| **cockpit** | = celle de CDAPH (score identique) **+ evidence** | L427, L411-412 |
| **eligibility** | **faible-moyenne en poids, ÉLEVÉE en danger** : les `_signal` matchent surtout des termes cliniques/admin qui existent **aussi** dans les champs 🟩 ; le narratif n'ajoute que les signaux **uniquement** présents dans la prose (vecteur de faux positif décisif) | L82-83, L109, L161-166 |
| **gate** | **binaire** : la présence/longueur de `texte_b` peut faire basculer AUTORISE↔BLOQUE | L252-253, L314, L323 |
| **evidence** | **élevée** mais **origine taguée** (garde-fou partiel) | L292-309 |
| **cerfa_filler P8/AVQ** | **totale** sur les cases AVQ (mais via `description_situation`, pas `texte_*`) | L1791, L1804-1821 |

---

## ÉTAPE 3 — SIMULATION THÉORIQUE (`texte_b/c/d/e = ""`)

| Moteur | Effet | Justification |
|---|---|---|
| **dossier_strength** | **IMPACT FORT** | narratif_b → 0 (L134), narratif_dc → 0 (L174), retentissement perd jusqu'à 13 pts (L98) → score chute d'environ **45 %** → indicateur **non fiable** |
| **cdaph_strategy** | **IMPACT MOYEN-FORT** | preuves perd le bonus `len(texte_b)` (-30 sur la sous-note), projet/cohérence/retentissement dégradés ; reste le déclaré (notes_pro, dk, dates) → score baisse nettement, le **niveau** (excellent/bon/moyen) peut flipper |
| **cockpit** | **IMPACT MOYEN-FORT** | son score EST le score CDAPH (L427) → baisse + reclassement du niveau affiché au pro |
| **eligibility** | **IMPACT FAIBLE-MOYEN (sur l'ampleur), ÉLEVÉ (sur la justesse)** | les signaux présents dans les champs 🟩 subsistent ; **disparaissent les signaux inventés par le LLM** → moins de droits faussement « probables » |
| **droits_oubliés** | **IMPACT FAIBLE-MOYEN** | suit eligibility |
| **gate export** | **IMPACT FORT (comportement)** | `_verif_narratifs` déclenche un blocage si `texte_b` vide → le gate **bloquerait** (ou avertirait) systématiquement → révèle que le gate **dépend** du narratif |
| **evidence** | **IMPACT MOYEN** | les items « Narratif » disparaissent ; restent Déclaration + Document |
| **analyse_situation** | **IMPACT MOYEN** | le prompt de re-analyse reçoit des sections vides → analyse plus pauvre |
| **cerfa_filler P8/AVQ** | **AUCUN IMPACT** ⚠️ | `description_situation` n'est PAS `texte_b` → **la contamination AVQ persiste** malgré la simulation |

**Lecture d'ensemble :** retirer `texte_*` **dégrade fortement les scores** (strength, CDAPH, cockpit) et **fait blocer le gate**, **assainit** eligibility/evidence, **mais ne corrige pas l'AVQ/CERFA**. Plusieurs moteurs deviennent **non fiables non parce qu'ils perdent de l'information, mais parce qu'ils étaient construits pour noter du texte généré**.

---

## ÉTAPE 4 — GRAPHE DE PROPAGATION

```
                         bilan / WhatsApp / documents (🟩 PREUVE)
                                        │
                 ┌──────────────────────┴───────────────────────┐
                 ▼                                               ▼
   cerfa_narrative_engine                          cerfa_filler._composer_description_p8
   → texte_b/c/d/e (🟥 Famille 1)                  → description_situation (🟥 Famille 2)
        │                                                        │
        ├──► eligibility _construire_texte ──► droits ──► droits_oubliés        │ réinjection L1791
        │                                                        │              ▼
        ├──► CDAPH _texte_complet ──► score_solidite ──┐         │      détecteur AVQ L1804
        │                                              ▼         │              ▼
        ├──► evidence (graphe de preuves) ──────► COCKPIT ◄──────┘        cases CERFA P6/P7
        │                                          │ (score + droits affichés au PRO ESSMS)
        ├──► dossier_strength (score 45% narratif) ─┘
        │
        ├──► gate _verif_narratifs ──► autorise_export (PASS/WARNING/BLOCK)
        │
        └──► analyse_situation (re-LLM) ──► analyse_situation_json ──► cockpit
```

Deux convergences : **le cockpit** (point de convergence des décisions vues par le professionnel) et **le CERFA** (document officiel, alimenté par P8/AVQ + droits).

---

## ÉTAPE 5 — POINT DE RUPTURE UNIQUE

**Le motif `_construire_texte` (eligibility) / `_texte_complet` (CDAPH)** — la fusion 🟩+🟥 dans un seul blob.

- **Preuve :** ce motif unique alimente eligibility (→ droits, droits_oubliés) **et** CDAPH (→ cockpit score + droits affichés). Filtrer `texte_b/c/d/e` hors de ce blob neutraliserait la contamination décisionnelle de **4 moteurs** (eligibility, droits_oubliés, CDAPH, cockpit) en un geste localisé (un filtre d'entrée, pas une refonte logique).
- **Limite honnête :** ce point **ne couvre pas** : (a) le P8→AVQ (`description_situation` + réinjection L1791), (b) dossier_strength (qui est *conçu* pour noter le narratif → nécessite une refonte, pas un filtre), (c) le gate (présence narrative).

➡️ **Il n'existe donc pas UN composant qui répare tout.** Le plus fort levier décisionnel = le **blob mixte** ; le plus fort risque *document* = le **P8→AVQ**. Deux chantiers distincts.

---

## ÉTAPE 6 — MATRICE DE PRIORITÉ

### 🔴 CRITIQUE (droits / CERFA / décision ESSMS)
- **eligibility `_construire_texte`** → droits (résultat usager).
- **cerfa_filler P8 → AVQ** → contenu du CERFA officiel.
- **CDAPH → cockpit** → score & droits affichés = go/no-go du professionnel.
- **gate `_verif_narratifs`** → autorisation d'export/dépôt.

### 🟠 IMPORTANT (score / recommandation)
- **dossier_strength** (~45 % narratif) — indicateur de solidité.
- **evidence_engine** — graphe de preuves (origine taguée = atténuation).
- **analyse_situation** — synthèse re-LLM.

### 🟢 CONFORT (affichage)
- Rendu des narratifs dans le dashboard (lecture seule).

---

## MODE AUDIT FACILIM

### CE QUI EST PROUVÉ
- **dossier_strength** : 35 % du score = narratif pur (POIDS L61-62) ; → 0 si `texte_*=""` (L134/L174).
- **CDAPH** : 4 sous-scores sur 5 (95 % du poids) reçoivent le blob incluant le narratif ; `_evaluer_preuves` démarre par `len(texte_b)>800→+30` (L148-157) ; agrégation L778-783.
- **cockpit** : `score = rapport_cdaph.score_solidite` (L427) → impact CDAPH = impact cockpit.
- **gate** : `autorise_export` dépend de `_verif_narratifs` (présence `texte_b`, L314/323).
- **eligibility** : `texte_b/c/d/e` dans le texte décisionnel (L82-83) consommé par tous les `_analyser_*`.
- **P8/AVQ** est un champ **distinct** (`description_situation`) non couvert par `texte_*=""`.

### CE QUI EST DÉCLARÉ
- eligibility/CDAPH lisent **aussi** du 🟩 → la suppression du narratif **dégrade** sans « casser » l'information sous-jacente (si le déclaré la porte).
- evidence **tague l'origine** → garde-fou partiel réutilisable.

### CE QUI EST NON VÉRIFIÉ
- Le **nombre exact** de décisions qui basculeraient (droits gagnés/perdus, niveaux flippés) — nécessiterait un rejeu instrumenté sur dossiers réels (production inaccessible ; `railway ssh` bloqué, non contourné).
- La part **précise** narrative de `_evaluer_projet_vie` / `_evaluer_coherence` (mixtes — estimation, non isolée).
- Si les consommateurs du graphe evidence **respectent** le tag d'origine.

### RISQUE PRINCIPAL
Des **droits**, un **score de solidité**, un **CERFA** et une **autorisation d'export** partiellement fondés sur la prose de FACILIM — pas sur des preuves vérifiées. Pour un pilote ESSMS : un professionnel valide/dépose un dossier dont des éléments fonctionnels sont fabriqués → requalification MDPH, perte de crédibilité, exposition (faux).

### GOULOT D'ÉTRANGLEMENT
Le **blob mixte** `_construire_texte` / `_texte_complet` (fusion déclaré+généré, sans séparation), dupliqué dans eligibility et CDAPH.

### COMPOSANT À TRAITER EN PREMIER
**`eligibilite_droits_engine._construire_texte`** (exclure `texte_b/c/d/e` du blob décisionnel des droits) — **en parallèle conceptuel** du **P8→AVQ** (`cerfa_filler` L1791).

### POURQUOI
- `_construire_texte` gouverne les **droits** (sortie irréversible pour l'usager) **et** droits_oubliés ; le même filtre appliqué à `_texte_complet` assainit CDAPH→cockpit. Levier maximal, risque minimal (filtre d'entrée).
- Le **P8→AVQ** est le seul à fabriquer du **contenu faux dans le document officiel** (le plus dommageable juridiquement) et n'est PAS couvert par le filtre du blob → doit être traité **conjointement**.

### CE QU'IL NE FAUT PAS CORRIGER ENCORE
- **dossier_strength** : ~45 % de son score étant *par conception* du narratif, le « corriger » = le **repenser**, pas le filtrer → risque élevé, et ce n'est qu'un **indicateur** (IMPORTANT, pas CRITIQUE). À différer.
- **gate `_verif_narratifs`** : le retirer naïvement laisserait passer des dossiers vides ; à retravailler avec soin, pas en premier.
- **Prompts, moteurs FACILIM 60→100, scoring, mapping** : ne rien toucher tant que le plan global n'est pas validé.
- **Ne pas** faire un refactor global du blob en un seul sweep.

### IMPACT SI RIEN N'EST FAIT
FACILIM continue de **se citer lui-même comme preuve** jusqu'au cockpit et au CERFA. Le pilote ESSMS produit des dossiers où limitations, droits, scores et export reposent partiellement sur des narratifs auto-générés (possiblement inventés). Premier dossier requalifié par une MDPH = **perte de confiance** sur l'outil entier.

---

## CRITÈRE DE RÉUSSITE — réponses

1. **Part réelle des décisions dépendant du narratif :** dossier_strength ~45 % (prouvé) ; CDAPH/cockpit élevée (95 % du poids exposé au blob, part purement narrative ~15-30 %) ; gate = bascule binaire ; eligibility faible en poids mais critique en justesse ; AVQ/CERFA = total (via champ distinct).
2. **Moteurs qui cesseraient d'être fiables sans narratif :** dossier_strength (s'effondre), CDAPH & cockpit (scores chutent, niveaux flippent), gate (bloque tout). eligibility/evidence : **s'améliorent** (moins de faux signaux).
3. **Composant unique maximisant le gain :** le blob mixte `_construire_texte` / `_texte_complet` (4 moteurs assainis) — sans toutefois couvrir AVQ/CERFA.
4. **Réparable localement ou refonte ?** **Mixte** : eligibility, CDAPH, cockpit, gate, evidence, P8/AVQ = **corrections locales** (filtres d'entrée / séparation, ~6 sites énumérés) ; **dossier_strength = refonte** (sa raison d'être est de noter le narratif).
5. **Prochaine correction réellement prioritaire :** séparer 🟩 preuve / 🟥 narratif dans `_construire_texte` (droits) **et** rompre la réinjection P8→AVQ (cerfa_filler L1791). *(Constat de priorité — aucune implémentation dans cet audit.)*

---

---

# COMPLÉMENT — Quantification finale (CDAPH, cockpit, gate) + sprint

## C1. CDAPH — quantification détaillée par sous-score

Agrégation (vérifiée L778-783) :
`score_solidite = preuves×0.35 + coherence×0.25 + retentissement×0.20 + projet×0.15 + justificatifs×0.05`

Chaque sous-score reçoit le **blob `texte`** (qui contient `texte_b/c/d/e`) **sauf** justificatifs (structuré). Détail des points 🟥 narratif vs 🟩 preuve :

| Sous-score (poids) | Points 🟥 narratif | Points 🟩 preuve/structuré | Part narrative | Lignes |
|---|---|---|---|---|
| **preuves (0.35)** | `len(texte_b)` → **+30** (pur) ; regex `diagnos\|bilan…` (+20) et dates (+15) **matchables dans le narratif** | notes_pro/dk +20 ; expression/verbatim +15 | **~30-50 %** | L148-190 |
| **cohérence (0.25)** | `_signal(texte, aide toilette/tierce pers.)` +15 ; regex « travaille actuellement » -10 | diagnostics+impact ±15 ; profil/droits ±25 (structuré) | **~15 %** | L200-240 |
| **retentissement (0.20)** | **100 % des checks tournent sur le blob** ; narratif = source la plus riche (« ne peut » +20, quantifié +20, AVQ toilette/habillage +10…) | impact_quotidien (🟩) peut matcher les mêmes motifs | **~50-70 %** | L251-284 |
| **projet (0.15)** | `len(texte_e) > 200` → **+30** (pur) ; regex ESAT/RQTH sur blob | projet_orientation, droits (structuré) | **~40 %** | L294-317 |
| **justificatifs (0.05)** | — | 100 % structuré (`justificatifs_engine`) | **0 %** | L322+ |

**Calcul de la part narrative globale CDAPH :**
```
preuves        0.35 × ~0.35 = 0.123
cohérence      0.25 × ~0.15 = 0.037
retentissement 0.20 × ~0.55 = 0.110
projet         0.15 × ~0.40 = 0.060
justificatifs  0.05 × 0      = 0.000
                       TOTAL ≈ 0.33
```
➡️ **CDAPH ≈ 30 % narratif (fourchette 25-40 %).**

⚠️ **Effet pervers prouvé :** la part narrative est **maximale précisément quand la preuve déclarée est faible** (cas CECORA : bilan pauvre en AVQ, narratif LLM riche). Le score est donc le **plus gonflé** là où il est le **moins fondé**. La contamination est pire quand elle est plus dangereuse.

## C2. Cockpit — impact chiffré

`generer_cockpit` L427 : **`score = rapport_cdaph.score_solidite`** (identité stricte). Donc :
- **Score cockpit = ~30 % narratif** (hérite intégralement de CDAPH).
- `droits_solides` / `droits_fragiles` viennent de CDAPH (L419-420) → tri des droits **partiellement narratif**.
- `niveau` (excellent ≥80 / bon ≥65 / moyen ≥45 / fragile, L428-433) : un score gonflé de ~20-30 pts peut **franchir un palier** → le professionnel voit « bon » au lieu de « moyen ».
- **Impact = MOYEN-FORT** : c'est le **chiffre de pilotage affiché au pro ESSMS**.

## C3. Gate — impact chiffré

`_verif_narratifs` (L249-263) : `len(texte_b) < 50` → blocage ; `len(texte_d) < 30` → blocage (adulte). `autorise_export = len(bloquants)==0` (L323).
- **Nature : binaire de présence**, pas de confiance dans le contenu.
- Sans narratif → le gate **bloque** (faux négatif « sécuritaire »). Avec narratif (même inventé) → le gate **autorise** (faux positif dangereux).
- **Impact = FORT sur le comportement**, mais correction **délicate** (le retirer laisse passer des dossiers vides).

## C4. Graphe de propagation complet (récapitulatif chiffré)

```
PREUVE (bilan/WhatsApp/doc)
   │
   ├─► texte_b/c/d/e (Famille 1) ─┬─► eligibility (faible poids / danger ÉLEVÉ) ─► droits ─► droits_oubliés
   │                              ├─► CDAPH (~30%) ──► COCKPIT score (~30%) ──► niveau/droits affichés au PRO
   │                              ├─► dossier_strength (~45%) ─► indicateur solidité
   │                              ├─► evidence (origine taguée) ─► graphe de preuves ─► cockpit
   │                              ├─► gate (présence) ─► PASS/WARNING/BLOCK export
   │                              └─► analyse_situation (re-LLM) ─► analyse_situation_json ─► cockpit
   │
   └─► description_situation (Famille 2, P8) ─► réinjection L1791 ─► détecteur AVQ ─► cases CERFA P6/P7
```
Convergences : **COCKPIT** (décision humaine) et **CERFA** (document officiel).

## C5. Composant unique à traiter en premier — décision

| Candidat | Moteurs assainis | Couvre AVQ/CERFA ? | Risque correction | Verdict |
|---|---|---|---|---|
| `_construire_texte` (eligibility) | eligibility + droits_oubliés | ❌ | faible (filtre) | **prioritaire #1** |
| `_texte_complet` (CDAPH) | CDAPH + cockpit | ❌ | faible (filtre) | **prioritaire #2** |
| réinjection P8 L1791 (cerfa_filler) | AVQ/CERFA | ✅ (le seul) | faible (couper une source) | **prioritaire #1 bis** |
| dossier_strength | indicateur | ❌ | **élevé (refonte)** | différé |
| evidence `_extraire_narratifs` | graphe | ❌ | moyen | différé |

➡️ **Il n'existe pas UN composant unique.** Le maximum de contamination éliminé au **moindre risque** = **filtrer `texte_b/c/d/e` hors des deux blobs décisionnels** (`_construire_texte` + `_texte_complet`) **ET couper la réinjection P8→AVQ (L1791)**. Trois points, tous des **filtres d'entrée** (pas de réécriture de logique), couvrant **droits + cockpit + CERFA** = les 3 sorties CRITIQUES.

## C6. VERDICT — correction locale ou refonte de confiance ?

**LES DEUX, par couches :**
- 🟢 **Correction LOCALE possible (sprint court, faible risque)** pour les sorties CRITIQUES : eligibility, CDAPH→cockpit, P8→AVQ, gate, evidence. Ce sont **~5-6 points d'injection énumérés**, corrigeables par séparation 🟩/🟥 sans toucher la logique métier ni les moteurs FACILIM 60→100.
- 🔴 **REFONTE nécessaire** pour **dossier_strength uniquement** : ~45 % de son score *est par conception* la qualité du narratif → on ne le filtre pas, on le repense (mais c'est un **indicateur**, pas une décision droit/CERFA → différable).

**Conclusion : FACILIM est réparable sans réécriture globale.** La contamination, bien que SYSTÉMIQUE en portée, passe par un **motif unique et localisé** (le blob mixte) + **une réinjection unique** (P8). Neutraliser ces deux mécanismes assainit l'essentiel sans refonte.

## C7. PROCHAIN SPRINT RECOMMANDÉ (constat — non implémenté ici)

**Sprint « ANTI-CONTAMINATION NIVEAU CRITIQUE » (périmètre minimal, fort gain) :**
1. **Séparer 🟩/🟥** dans `eligibilite_droits_engine._construire_texte` (L79-104) → les `_signal` des droits ne lisent plus `texte_b/c/d/e`. *(droits + droits_oubliés)*
2. **Séparer 🟩/🟥** dans `cdaph_strategy_engine._texte_complet` (L86-91) → score CDAPH/cockpit fondé sur preuve. *(score affiché au pro)*
3. **Couper la réinjection P8→AVQ** : `cerfa_filler` ne doit plus dériver les cases AVQ de `description_situation` (L1791) — les cases AVQ ne se cochent que sur les `avq_*` structurés (Vague 1). *(CERFA officiel)*
4. **QA de non-régression** : vérifier que sur un dossier riche en preuve déclarée, les scores/droits/cases **restent**, et que sur un dossier pauvre en preuve (type CECORA) ils **chutent** (= comportement souhaité).

**Hors sprint (différé) :** refonte dossier_strength ; revue gate `_verif_narratifs` ; exploitation du tag d'origine d'evidence.

**Ce que ce sprint NE touche pas :** prompts, moteurs FACILIM 60→100, mapping CERFA structuré, cockpit (corrigé indirectement via CDAPH), Vague 1.

---

## SYNTHÈSE FINALE — impact par moteur

| Moteur | Niveau d'impact narratif | Catégorie | Action |
|---|---|---|---|
| dossier_strength | **~45 %** | IMPORTANT | refonte (différé) |
| CDAPH | **~30 %** (25-40 %) | CRITIQUE (via cockpit) | filtre local |
| cockpit | **~30 %** (= CDAPH) | CRITIQUE | corrigé via CDAPH |
| eligibility | poids faible / **danger ÉLEVÉ** | CRITIQUE | filtre local #1 |
| droits_oubliés | hérité eligibility | CRITIQUE | corrigé via eligibility |
| gate | binaire (présence) | CRITIQUE | revue (différé) |
| evidence | élevé (origine taguée) | IMPORTANT | différé |
| analyse_situation | moyen | IMPORTANT | différé |
| **cerfa_filler P8→AVQ** | **total** (champ distinct) | **CRITIQUE** | **couper réinjection #1 bis** |

---

*Audit d'impact, lecture seule. Aucun moteur, prompt, score, CERFA, mapping modifié. Limites : ampleur chiffrée non instrumentée sur dossiers réels (production inaccessible, `railway ssh` bloqué non contourné) ; parts narratives des sous-scores mixtes (preuves, retentissement, projet, cohérence) **estimées par lecture du code**, non mesurées par exécution.*
