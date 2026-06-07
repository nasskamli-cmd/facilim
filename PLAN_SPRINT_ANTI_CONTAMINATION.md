# PLAN_SPRINT_ANTI_CONTAMINATION.md — Sprint « ANTI-CONTAMINATION NIVEAU CRITIQUE »

**Généré le :** 2026-06-07
**Nature :** PLANIFICATION UNIQUEMENT. Aucune ligne de code, aucune modification, aucun commit, aucun déploiement.
**But :** supprimer la contamination par narratifs générés sur les **3 sorties critiques** (droits, cockpit, CERFA) **sans casser** V2, Vague 1, moteurs 60→100, cockpit, gate, ni les QA existantes.
**Principe directeur :** les moteurs **décident** sur 🟩 preuve + 🟦 structuré ; ils n'**affichent/impriment** que le 🟥 généré. On ne supprime pas les narratifs — on les **retire des entrées décisionnelles**.

---

## ÉTAPE 1 — INVENTAIRE EXACT DES POINTS À MODIFIER

### 1.A — eligibility_engine  *(CRITIQUE — droits)*
- **Fichier :** `app/engines/eligibilite_droits_engine.py`
- **Fonction pivot :** `_construire_texte(donnees)` — **L77-106**
- **Lignes fautives :** **L82-83** (`"texte_b_vie_quotidienne", "texte_c_scolarite", "texte_d_situation_pro", "texte_e_projet_vie"` dans la liste `champs`).
- **Dépendances :** `texte` est construit **une seule fois** dans `analyser_eligibilite` (**L1176**) puis passé aux **22 analyseurs** (`_analyser_aah`…`_analyser_foyer_hebergement`, **L1191-1194**) via `_signal(texte, …)` (**L109-117**).
- **Portée du correctif :** retirer 4 entrées de la liste L82-83 → assainit **les 22 droits + droits_omis_probables** en un point.
- **À conserver :** `diagnostics, impact_quotidien, restrictions_emploi, statut_emploi, droits_demandes, historique_mdph, aidant_besoins, notes_pro, _verbatim_*, _document_knowledge` (🟩).

### 1.B — cdaph_strategy  *(CRITIQUE — cockpit)*
- **Fichier :** `app/engines/cdaph_strategy_engine.py`
- **Fonction pivot :** `_texte_complet(donnees)` — **L86-91** (inclut `texte_b/c/d/e`).
- **Lignes fautives secondaires :** `_evaluer_preuves` **L148-157** (`len(texte_b)` → +30) ; `_evaluer_projet` **L297-301** (`len(texte_e)>200` → +30).
- **Dépendances :** `texte` construit dans `analyser_strategie_cdaph` (**L768**) → passé à `_evaluer_preuves/coherence/retentissement/projet` (**L771-774**) ; agrégation **L778-783** ; sérialisé `analyse_situation_json` **L876-878**.
- **Consommateur aval :** `professional_cockpit_engine.generer_cockpit` **L411** (`analyser_strategie_cdaph`) → **L427** `score = rapport_cdaph.score_solidite`.
- **Portée :** retirer `texte_b/c/d/e` de `_texte_complet` **et** neutraliser les bonus de longueur L148-157 / L297-301 → assainit CDAPH **et** le cockpit (par héritage, sans toucher au cockpit).

### 1.C — cerfa_filler  *(CRITIQUE — CERFA / AVQ)*
- **Fichier :** `services/cerfa_filler.py`
- **Fonction pivot :** corps de remplissage, bloc **L1789-1821** (`_detection_b2b3_brut` → cases P6 B1-B6).
- **Ligne fautive :** **L1791** (`(description_situation or "").lower()` injecté dans le blob de détection AVQ). Origine du 🟥 : `description_situation` généré en **L1155** via `_composer_description_p8` (**L53-156**).
- **Dépendance bloquante :** `cerfa_filler` **n'importe pas** `collecte_schema` et **n'utilise pas** `avq_*` (vérifié : 0 occurrence). → retirer simplement L1791 ferait **disparaître les cases AVQ légitimes** sur le chemin V2 (régression).
- **Correctif en 2 volets obligatoires :**
  1. **Retirer** `description_situation` du blob `_detection_b2b3_brut` (L1789-1794).
  2. **Ajouter** la lecture des `avq_*` structurés (🟦, Vague 1) comme **source autoritaire** des cases P6 B1-B4 (aligner V2 sur `field_mapper` V3 : `avq_toilette/habillage/repas/...` niveau ≥ DIFFICULTÉ → case cochée).
- **Zone grise (à conserver pour l'instant) :** `difficultes_quotidiennes`, `besoins_aide_str`, `aides_actuelles` (extraits de synthèse, proches du déclaré) — **garder** mais signaler comme suivi. Le 🟥 pur est `description_situation`.
- **Ne PAS toucher :** `_composer_description_p8` reste utilisé pour **imprimer** le texte P8 (affichage), mais sa sortie ne doit plus **alimenter la détection**.

### 1.D — gate  *(CRITIQUE — export, mais correctif DIFFÉRÉ)*
- **Fichier :** `app/engines/cerfa_gate_engine.py`
- **Fonction :** `_verif_narratifs(donnees, profil_mdph)` — **L249-268** ; appelée dans `verifier_gate_cerfa` **L314** ; décision `autorise_export = len(bloquants)==0` **L323**.
- **Dépendance :** blocage si `len(texte_b) < 50` (L252-253) / `len(texte_d) < 30` (L262-263).
- **Décision de sprint :** **NE PAS modifier dans ce sprint.** Raison : retirer ce contrôle laisserait passer des dossiers vides ; le re-baser sur le déclaré demande une réflexion séparée. **Maintenir tel quel** (le gate reste un garde-fou de présence). À traiter dans un sprint ultérieur.

### 1.E — evidence_engine  *(IMPORTANT — correctif DIFFÉRÉ)*
- **Fichier :** `app/engines/evidence_engine.py`
- **Fonction :** `_extraire_narratifs(donnees)` — **L292-311** ; appelée dans `construire_graphe_preuves` **L423**.
- **Atténuation existante :** chaque item est tagué `origine="Narratif"` (vs `Déclaration`/`Document`).
- **Décision de sprint :** **DIFFÉRÉ.** Le correctif propre = faire respecter le tag d'origine en aval (pondérer/exclure les items « Narratif » des calculs). Hors périmètre critique de ce sprint (evidence n'est pas une sortie droit/CERFA directe).

> **Périmètre RÉEL du sprint = 1.A + 1.B + 1.C uniquement** (droits, cockpit, CERFA). 1.D et 1.E sont documentés mais **différés**.

---

## ÉTAPE 2 — RÈGLE DE CONFIANCE (à graver comme invariant)

### ✅ AUTORISÉ comme source DÉCISIONNELLE (score / droit / case CERFA / gate)
- Données structurées (`avq_*`, `droits.*`, `date_naissance`, `statut_emploi`, `profil_mdph`…)
- Réponses WhatsApp / champs collectés (`impact_quotidien`, `diagnostics`, `restrictions_emploi`, `besoins_aide`…)
- Documents source extraits (`_document_knowledge`, `notes_pro`)
- Verbatims directs de la personne (`_verbatim_*`, `expression_directe`)

### ⛔ INTERDIT comme source DÉCISIONNELLE (mais autorisé en AFFICHAGE / IMPRESSION)
- `texte_b_vie_quotidienne`, `texte_c_scolarite`, `texte_d_situation_pro`, `texte_e_projet_vie`
- `description_situation` (P8)
- `synthese_situation` / tout résumé généré
- `analyse_situation_json` (analyse générée) en réinjection décisionnelle

**Formulation opérationnelle :** un champ 🟥 ne doit jamais apparaître dans un `_signal(...)`, un `re.search(...)` décisionnel, un `len(...)` qui score, ou un blob de détection. Il ne sort que vers un champ texte du PDF ou l'UI.

---

## ÉTAPE 3 — MATRICE AVANT / APRÈS

| Moteur | Avant | Après |
|---|---|---|
| **eligibility** | preuve 🟩 + narratif 🟥 (`texte_b/c/d/e`) dans `_construire_texte` | **preuve 🟩 uniquement** |
| **cdaph_strategy** | blob 🟩+🟥 + bonus `len(texte_b/e)` | **preuve 🟩** ; bonus de longueur narratif **supprimés** |
| **cockpit** | score = CDAPH contaminé | score = CDAPH assaini (**par héritage, aucune modif cockpit**) |
| **cerfa_filler / AVQ** | cases ← `description_situation` 🟥 (réinjection L1791) | cases ← **`avq_*` 🟦 structuré** (+ déclaré 🟩) |
| **droits_oubliés** | dérivé eligibility contaminé | dérivé eligibility assaini (**héritage**) |
| **gate** | présence narratif (inchangé) | **inchangé (différé)** |
| **evidence** | narratif = item de preuve (tagué) | **inchangé (différé)** |
| **dossier_strength** | ~45 % narratif | **inchangé (refonte ultérieure)** |
| **P8 (texte imprimé)** | généré, imprimé | **généré, imprimé (inchangé)** — seul son usage décisionnel disparaît |

---

## ÉTAPE 4 — IMPACT QA (tests existants)

| Suite QA | Risque | Action |
|---|---|---|
| **QA-SCHEMA-1→5** (Vague 1) | **Faible** — testent `avq_*`/`droits.*` structurés ; le correctif 1.C **renforce** ce chemin. QA-SCHEMA-5 (avq_*→P6/P7) doit **rester PASS** (devient même la voie principale). | **Doit rester identique / PASS** |
| **QA-FIX-TEST4-CERFA-V2** | Moyen — touche `cerfa_filler` ; vérifier que la suppression L1791 ne casse pas la génération V2. | **Vérifier, adapter si assertions sur cases issues du narratif** |
| **QA-FIX-TEST4-COLLECTE** | Faible — collecte, pas mapping. | Identique |
| **QA-VALIDATION-1-TEST4** | Moyen — si elle asserte des cases AVQ issues du narratif. | **Revue ciblée** |
| **QA-PROD-1→5** | Moyen — PROD-2 (cockpit visible), PROD-3 (gate). Le score cockpit **baissera** sur dossiers pauvres → si une assertion fige un seuil de score, elle cassera. | **Adapter les seuils de score**, garder les assertions de présence/structure |
| **QA-5 / 7 / 9 / 10 / 11** (massive_qa, facilim60…) | **Moyen-élevé** — profils synthétiques peuvent reposer sur des narratifs riches → scores/droits baisseront pour les profils « pauvres en preuve structurée ». | **Recalibrer les attendus** des profils dont la solidité venait du narratif |

**Principe QA :** les tests qui assertaient un **score chiffré** ou un **droit détecté** *grâce au narratif* doivent être **recalibrés** (c'est le comportement voulu). Les tests de **structure / présence / non-régression fonctionnelle** doivent **rester identiques**.

---

## ÉTAPE 5 — NOUVEAUX TESTS OBLIGATOIRES (à créer : `qa_anti_contamination.py`)

| Test | Entrée | Résultat attendu | Vérifie |
|---|---|---|---|
| **QA-ANTI-1** | Dossier **riche en narratif** (`texte_b` long, dramatique) mais **pauvre en preuve** (impact/diagnostics vides, `avq_*` absents) | **score CDAPH/strength CHUTE** ; peu/pas de droits « solides » | eligibility + cdaph ne se nourrissent plus du narratif |
| **QA-ANTI-2** | Dossier **riche en preuve structurée** (diagnostics, impact, `avq_*`, `droits.*`) **sans narratif** (`texte_*=""`) | **droits conservés** ; score correct | la décision tient sans narratif |
| **QA-ANTI-3** | `texte_b` contient « ne peut pas se lever seule », « aide toilette » **sans `avq_*` ni déclaré correspondant** | **aucune case AVQ cochée** (P6 B1-B4) | réinjection P8→AVQ coupée |
| **QA-ANTI-4** | `avq_toilette=AIDE_TOTALE`, `avq_repas=DIFFICULTE` **sans aucun narratif** | **cases P6 cochées** (toilette, repas) | les `avq_*` structurés pilotent bien les cases (pas de régression) |
| **QA-ANTI-5** *(ajout recommandé)* | Dossier CECORA réel (bilan : fatigue/ménage/station debout, **pas** d'AVQ) | **0 case AVQ inventée** ; ménage/fatigue préservés | reproduction du cas réel ayant déclenché l'audit |

---

## ÉTAPE 6 — RISQUE DE RÉGRESSION

### CE QUI VA / PEUT BAISSER (comportement **attendu**, pas un bug)
- Scores **cockpit** et **CDAPH** sur dossiers **pauvres en preuve structurée** (~30 % de baisse possible, cf. AUDIT_IMPACT).
- **Droits « probables »** qui ne tenaient que sur des signaux présents uniquement dans le narratif.
- Niveau cockpit (« bon » → « moyen ») sur ces mêmes dossiers.

### CE QUI NE DOIT PAS BAISSER (sinon = régression réelle → NO GO)
- Dossiers **réellement documentés** (diagnostics + impact + documents) : scores/droits stables.
- Dossiers avec **preuves structurées** (`avq_*`, `droits.*`) : cases CERFA et droits **conservés**.
- **Vague 1** : QA-SCHEMA-1→5 **PASS** à l'identique ; le chemin `avq_*`→CERFA **renforcé**.
- Génération **V2** fonctionnelle (PDF produit, pas d'exception).
- **Gate** : comportement inchangé (hors périmètre).

---

## MODE AUDIT FACILIM

### CE QUI EST PROUVÉ
- **3 points d'injection** localisés et vérifiés : `_construire_texte` L82-83 (eligibility), `_texte_complet` L86-91 + L148-157/L297-301 (cdaph), réinjection L1791 (cerfa_filler).
- eligibility : `texte` construit 1× (L1176) → 22 analyseurs (L1191-1194) → **un seul correctif** suffit.
- cockpit : `score = rapport_cdaph.score_solidite` (L427) → assaini **par héritage**, aucune modif cockpit.
- `cerfa_filler` n'utilise **pas** `avq_*` → l'étape 1.C **doit ajouter** cette lecture (sinon régression).

### CE QUI EST NON VÉRIFIÉ
- L'**ampleur réelle** de la baisse de score/droits (non instrumentée — production inaccessible, `railway ssh` bloqué non contourné).
- Si `difficultes_quotidiennes`/`besoins_aide` (zone grise) sont eux-mêmes partiellement générés (extraction LLM) → à clarifier avant de les conserver comme 🟩.
- Quels profils QA synthétiques reposent **précisément** sur le narratif (à mesurer au moment du recalibrage).

### RISQUE PRINCIPAL
**Sur-correction** : retirer le narratif de `cerfa_filler` **sans** brancher `avq_*` ferait disparaître des cases AVQ légitimes → régression silencieuse sur les vrais dossiers. **Mitigation : 1.C en 2 volets + QA-ANTI-4.**

### GOULOT D'ÉTRANGLEMENT
Le **blob mixte** dupliqué (`_construire_texte` / `_texte_complet`). Le neutraliser aux 2 endroits + couper L1791 couvre les 3 sorties critiques.

### FICHIER À MODIFIER EN PREMIER
`app/engines/eligibilite_droits_engine.py` (`_construire_texte`, L82-83) — plus haut enjeu (droits irréversibles), correctif le plus simple et le plus sûr (retrait de 4 entrées de liste).

### ORDRE DES MODIFICATIONS
1. **eligibility** `_construire_texte` (droits) — *retrait 4 champs* → QA-ANTI-1/2.
2. **cdaph** `_texte_complet` + bonus longueur (cockpit par héritage) → QA-ANTI-1.
3. **cerfa_filler** : (a) couper L1791, (b) brancher `avq_*` → QA-ANTI-3/4/5.
4. **Recalibrer** QA-PROD / massive_qa / facilim60 (seuils de score).
5. *(différé : gate, evidence, refonte dossier_strength.)*

### TESTS BLOQUANTS (GO/NO GO)
- QA-ANTI-1→5 **tous PASS**.
- QA-SCHEMA-1→5 **PASS à l'identique**.
- Génération V2 sans exception (smoke test PDF).
- Non-régression : un dossier « bien documenté » de référence conserve droits + score (± tolérance).

### CRITÈRES GO / NO GO
- **GO** si : QA-ANTI 5/5 ✅ + QA-SCHEMA 5/5 ✅ + dossier documenté de référence stable ✅ + aucune exception V2 ✅.
- **NO GO** si : une case AVQ légitime disparaît (QA-ANTI-4 ❌), OU un dossier documenté perd des droits/score (régression réelle), OU QA-SCHEMA casse.

---

## CRITÈRE DE RÉUSSITE — checklist livrée

1. **Fichiers exacts :** `eligibilite_droits_engine.py`, `cdaph_strategy_engine.py`, `services/cerfa_filler.py` (+ différés : `cerfa_gate_engine.py`, `evidence_engine.py`).
2. **Fonctions exactes :** `_construire_texte` (L77-106), `_texte_complet` (L86-91) + `_evaluer_preuves`/`_evaluer_projet`, bloc `_detection_b2b3` (L1789-1821) + `_composer_description_p8`.
3. **Règles de confiance :** AUTORISÉ 🟩🟦 / INTERDIT 🟥 (ÉTAPE 2).
4. **QA nécessaires :** QA-ANTI-1→5 (nouveaux) + recalibrage QA-PROD/massive/facilim60.
5. **Ordre de correction :** eligibility → cdaph → cerfa_filler → recalibrage QA.
6. **Risques :** sur-correction AVQ (mitigée), baisse attendue des scores sur dossiers pauvres.
7. **Plan exécutable :** oui — chaque étape a fichier/fonction/lignes/test associé.

---

*Plan de sprint, lecture seule. Aucune ligne de code écrite, aucune modification, aucun commit, aucun déploiement. Périmètre exécutif limité à eligibility + cdaph + cerfa_filler (droits, cockpit, CERFA) ; gate, evidence et dossier_strength explicitement différés.*
