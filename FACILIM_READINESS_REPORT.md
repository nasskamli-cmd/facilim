# FACILIM — RAPPORT DE PRÉPARATION TERRAIN (READINESS REPORT)

**Généré le :** 2026-06-06
**Version :** FACILIM PROD (développements gelés)
**Nature :** Audit final avant pilote terrain — **factuel uniquement**

> Ce rapport ne contient aucune estimation optimiste. Chaque affirmation est fondée sur l'un de ces éléments observables :
> **(C)** le code source, **(QA)** un test QA exécuté, **(M)** une métrique mesurée, **(R)** un rapport généré dans `app/tests/qa/reports/`.
> Date d'exécution des QA citées : **2026-06-06 09:44 UTC**, seed 42, sans clé OpenAI.

---

## PARTIE 1 — INVENTAIRE COMPLET DES MOTEURS

Le dépôt contient **37 modules moteurs** dans `app/engines/` + 1 package `pdf/`. (C)
On distingue **deux chaînes distinctes** :

- **Chaîne A — Workflow réel déployé** : WhatsApp → `main.py` → `orchestration_engine.py`. C'est ce qui tourne aujourd'hui en production.
- **Chaîne B — FACILIM PROD analytique** (FACILIM 60→100) : orchestrée par `facilim_prod.py`. **Fait vérifié : `facilim_prod` / `verifier_gate_cerfa` / `creer_journal_audit` / `analyser_dossier_complet` ne sont importés par aucun fichier hors de leurs propres modules** (C, grep). La chaîne B n'est donc **pas câblée** dans le workflow réel.

### Chaîne A — Moteurs du workflow réel (câblés dans `orchestration_engine.py`)

```
MOTEUR profile_engine
Objectif : Calcule le profil (âge, mineur, tutelle) — source de vérité du routage
Entrées  : date_naissance, signaux tutelle
Sorties  : ProfilUsager
Utilisé  : OUI (orchestration_engine ligne 47)
Critique : OUI — détermine l'agent et les sections autorisées

MOTEUR conversation_engine
Objectif : Checklists par profil, assemblage prompt, extraction structurée
Entrées  : historique conversation, profil
Sorties  : réponse agent, données structurées
Utilisé  : OUI (orchestration_engine ligne 40)
Critique : OUI — collecte des données

MOTEUR case_state_engine
Objectif : État d'avancement du dossier
Entrées  : dossier
Sorties  : état / progression
Utilisé  : OUI (orchestration_engine ligne 33)
Critique : OUI

MOTEUR scoring_engine
Objectif : Score dossier (score_dossier)
Entrées  : dossier
Sorties  : score
Utilisé  : OUI (orchestration_engine ligne 52)
Critique : MOYEN

MOTEUR verbatim_engine
Objectif : Verbatim cumulatif, taux d'enrichissement, relance intelligente
Entrées  : réponses usager
Sorties  : verbatim catégorisé, taux
Utilisé  : OUI (import dynamique ligne 488)
Critique : MOYEN

MOTEUR inferencer_mdph
Objectif : Moteur d'inférence (référentiel 78 règles) — détecte droits
Entrées  : données collectées
Sorties  : hypothèses (DIRECTE/INDIRECTE/ABSENTE)
Utilisé  : OUI (import dynamique ligne 575)
Critique : OUI

MOTEUR profil_handicap_engine
Objectif : Profilage multi-handicap
Entrées  : signaux conversation
Sorties  : profil_principal/secondaire, tags
Utilisé  : OUI (import dynamique ligne 732)
Critique : OUI

MOTEUR cerfa_narrative_engine
Objectif : Génère les narratifs B/C/D/E (LLM)
Entrées  : diagnostics, impact, verbatim
Sorties  : texte_b/c/d/e
Utilisé  : OUI (ligne 888) — DÉPEND DE LA CLÉ OpenAI
Critique : OUI

MOTEUR cerfa_quality_agent
Objectif : Contrôle qualité narratifs + score maturité
Entrées  : narratifs
Sorties  : score maturité, alertes
Utilisé  : OUI (ligne 889)
Critique : MOYEN

MOTEUR analyse_situation_engine
Objectif : Analyse de situation (2 couches : déterministe + GPT-4o)
Entrées  : dossier complet
Sorties  : 10 clés JSON (synthèse, risques, besoins, acteurs…)
Utilisé  : OUI (ligne 959)
Critique : MOYEN

MOTEUR document_functional_extractor
Objectif : Extraction fonctionnelle depuis documents
Entrées  : texte OCR
Sorties  : éléments fonctionnels
Utilisé  : OUI (ligne 1256)
Critique : MOYEN

MOTEUR document_engine
Objectif : process_document — traitement documentaire
Utilisé  : OUI (app/services/document_service.py ligne 21)
Critique : MOYEN

MOTEUR comite_agents
Objectif : executer_comite_agents — délibération multi-agents
Utilisé  : OUI (main.py ligne 1960)
Critique : À VÉRIFIER (un seul point d'appel)

MOTEUR pdf/ (cerfa_filler + field_mapper)
Objectif : Remplissage CERFA (build_field_map)
Sorties  : field_map (clés AcroForm → valeurs)
Utilisé  : OUI (workflow réel + facilim_prod)
Critique : OUI
```

### Chaîne B — Moteurs FACILIM PROD (appelés UNIQUEMENT par `facilim_prod.py`, non câblé)

```
MOTEUR evidence_engine            → graphe preuves (preuves × sources × confiance)   | Utilisé : chaîne B seulement | Critique : OUI
MOTEUR completeness_engine        → score complétude 5 dimensions                    | Utilisé : chaîne B seulement | Critique : OUI
MOTEUR refusal_risk_engine        → risques de refus + incohérences                  | Utilisé : chaîne B seulement | Critique : OUI
MOTEUR cdaph_strategy_engine      → score solidité + forces/faiblesses               | Utilisé : chaîne B seulement | Critique : OUI
MOTEUR eligibilite_droits_engine  → analyse 22 droits                                | Utilisé : chaîne B seulement | Critique : OUI
MOTEUR strategie_dossier_engine   → droits oubliés + urgences                        | Utilisé : chaîne B seulement | Critique : OUI
MOTEUR human_validation_engine    → tableau de validation humaine                    | Utilisé : chaîne B seulement | Critique : OUI
MOTEUR pre_submission_engine      → décision GO / GO_AVEC_RISQUES / NO_GO            | Utilisé : chaîne B seulement | Critique : OUI
MOTEUR action_plan_engine         → plan d'action (catalogue 18 actions)             | Utilisé : chaîne B seulement | Critique : MOYEN
MOTEUR parcours_engine            → feuille de route                                 | Utilisé : chaîne B seulement | Critique : MOYEN
MOTEUR priorisation_engine        → prioriser_actions (utilisé par action_plan)      | Utilisé : indirect (chaîne B) | Critique : MOYEN
MOTEUR cerfa_gate_engine          → verrou export (préview jamais bloquée)           | Utilisé : chaîne B seulement | Critique : OUI
MOTEUR audit_trail_engine         → journal d'audit traçable                         | Utilisé : chaîne B seulement | Critique : MOYEN
MOTEUR professional_cockpit_engine→ cockpit unique                                   | Utilisé : chaîne B seulement | Critique : OUI
MOTEUR pro_report_engine          → 4 rapports                                       | Utilisé : chaîne B seulement | Critique : MOYEN
MOTEUR dossier_strength_engine    → robustesse par droit (noter_robustesse)          | Utilisé : par strategie_dossier + QA | Critique : MOYEN (doublon cdaph)
MOTEUR questions_levier_engine    → identifier_questions_levier                      | Utilisé : explainability + cockpit + strategie | Critique : MOYEN
MOTEUR justificatifs_engine       → justificatifs_requis                             | Utilisé : cdaph + completeness + cockpit | Critique : MOYEN
```

### Moteur orphelin (testé mais jamais appelé en production ni dans la chaîne B)

```
MOTEUR explainability_engine (expliquer_dossier)
Fait vérifié : importé UNIQUEMENT par app/tests/qa/qa8_explainability.py (C, grep).
Le cockpit professionnel appelle directement questions_levier_engine et justificatifs_engine,
PAS explainability_engine.
Statut : ORPHELIN PRODUIT — couvert par QA-8 mais hors de tout chemin produit.
```

---

## PARTIE 2 — CARTOGRAPHIE FONCTIONNELLE

Flux cible vs flux réellement câblé (C) :

```
WhatsApp            ✅ câblé (main.py webhook async + orchestration_engine)
   ↓
Documents           ✅ câblé (document_service + extraction OCR)
   ↓
Extraction          ✅ câblé (document_functional_extractor)
   ↓
Inférences          ✅ câblé (inferencer_mdph + profil_handicap_engine)
   ↓
Narratifs           ✅ câblé (cerfa_narrative_engine) — ⚠️ DÉPEND DE LA CLÉ OpenAI
   ↓
Droits              ⚠️ PARTIEL — inferencer_mdph détecte ; eligibilite_droits_engine
                       (22 droits, chaîne B) N'EST PAS appelé depuis le workflow réel
   ↓
Stratégie           ❌ NON CÂBLÉ — cdaph_strategy / strategie_dossier (chaîne B uniquement)
   ↓
Validation humaine  ❌ NON CÂBLÉ — human_validation_engine existe, jamais appelé en prod
   ↓
CERFA               ✅ câblé (pdf/cerfa_filler) — mais SANS passage par cerfa_gate_engine
   ↓
Rapports            ❌ NON CÂBLÉ — pro_report_engine / cockpit (chaîne B uniquement)
   ↓
Export final        ⚠️ câblé SANS verrou — verifier_gate_cerfa() jamais invoqué avant export
```

**Étapes utilisées (réellement en prod) :** WhatsApp, Documents, Extraction, Inférences, Narratifs, CERFA, Export.
**Étapes inutilisées en prod (existent mais non câblées) :** Stratégie complète, Validation humaine, Cockpit, Rapports, Gate d'export, Journal d'audit.
**Doublons :** (1) `dossier_strength_engine` vs `cdaph_strategy_engine` (deux scores de robustesse, méthodes différentes — C) ; (2) détection des droits oubliés présente à la fois dans `strategie_dossier_engine` et `eligibilite_droits_engine`.
**Zones mortes :** `explainability_engine.expliquer_dossier` (orphelin) ; toute la chaîne B est une zone morte vis-à-vis du workflow réel tant que `facilim_prod` n'est pas appelé.

---

## PARTIE 3 — COUVERTURE RÉELLE

### Couverture CERFA 15692*01 (R : QA-6, 1000 dossiers synthétiques)

| Indicateur | Mesure (1000) | Seuil QA-6 | Statut |
|---|---|---|---|
| Couverture critique **N1** | **76.0 %** | ≥ 35 % | ✅ |
| Couverture applicable moyenne | 16.9 % | — | — |
| Couverture globale (/612 champs) | 11.4 % (≈ 69.8 champs) | — | — |
| Couverture droits P17/P18 | 50.0 % (P17=94.1 %, P18=100 %) | — | — |
| Champs fantômes critiques | **0** | 0 | ✅ |
| Droits incompatibles cochés | **0** | 0 | ✅ |

**Couverture par section (R, QA-6) :** Texte libre B (P8) 100 % · Droits E3 (P18) 100 % · Droits E1/E2 (P17) 94.1 % · Consentement (P4) 60 % · Projet de vie E (P16) 48.8 % · Identité A1/A2 35.7 % · Page de garde 25 % · Emploi D 6.2 % · Aidant F 4.6 % · Scolarité C 1.6 % · **Vie quotidienne B1/AVQ (P5/P6/P7) 0.8 %**.

> **Nuance factuelle :** les profils synthétiques contiennent déjà des textes narratifs pré-remplis. Le N1=76 % est donc obtenu **avec** les champs texte libres remplis. Les sections à cases détaillées (AVQ P5-P7, scolarité C, aidant F) restent < 7 % : ce sont des champs **non mappés**, pas un effet LLM.

### Couverture par profil MDPH (R, QA-6)

| Profil | N | Cov N1 moyenne |
|---|---|---|
| adulte | 640 | 78.3 % |
| enfant | 291 | 76.4 % |
| **protege** | 69 | **52.7 %** (point bas) |

### Couverture droits (R : QA-5 droits oubliés les plus ratés, sur 1000)

`SAVS` non détecté 121 fois · `PCH` 112 · `CMI_PRIORITE` 86 · `AAH` 81 · `CMI_STATIONNEMENT` 80 · `ESPO` 26 · `FOYER_VIE` 25 · `AVPF` 14 · `RQTH` 10.
Droits détectés par le moteur mais **non cochés dans le PDF** (R, QA-6) : `RQTH` 19.5 % · `SESSAD` 13.0 % · `FOYER_HEBERGEMENT` 12.3 % — **gap field_mapper ↔ moteur stratégie**.

- **Adulte :** RQTH/AAH/CMI fiables ; PCH/SAVS faibles.
- **Enfant :** AEEH/SESSAD bons ; `AEEH` non coché 2.2 % (R, QA-6).
- **Insertion (ESPO/ESAT/RQTH) :** détection OK, mais RQTH mal reportée au PDF (19.5 %).
- **Protection juridique :** couverture CERFA la plus basse (52.7 % N1).
- **Aidants :** section F couverte à 4.6 % (champs non mappés).

### Couverture documentaire (C)

| Type | Statut |
|---|---|
| PDF (OCR + extraction) | ✅ câblé (`document_engine`, `document_functional_extractor`) |
| Bilans / certificats / comptes rendus | ⚠️ traités comme texte générique — pas d'extracteur typé par document |
| GEVASCO | ❌ aucun parseur dédié identifié dans le code |

---

## PARTIE 4 — QA GLOBAL (consolidation factuelle)

Toutes les batteries ré-exécutées le **2026-06-06 09:44**, seed 42, sans LLM. Décision = code de sortie 0.

| Batterie | 100 | 500 | 1000 | FAIL | WARN | Régression |
|---|---|---|---|---|---|---|
| QA-5 massif | PASS (100 % PASS) | PASS (99.4 %) | PASS (99.5 %, 5 WARN) | 0 | 5/1000 | Aucune |
| QA-6 PDF CERFA | PASS (N1 75.8 %) | PASS (N1 76.1 %) | PASS (N1 76.0 %) | 0 | 0 | Aucune |
| QA-7 CDAPH | PASS (100 %) | PASS (100 %) | PASS (100 %) | 0 | 0 | Aucune |
| QA-8 Explainability | PASS (100 %) | PASS (100 %) | PASS (100 %) | 0 | 0 | Aucune |
| QA-9 Validation humaine | PASS (100 %) | PASS (100 %) | PASS (100 %) | 0 | 0 | Aucune |
| QA-10 Complétude/Pré-soumission | PASS (100 %) | PASS (100 %) | PASS (100 %) | 0 | 0 | Aucune |
| QA-11 Plan d'action/Parcours | PASS (100 %) | PASS (100 %) | PASS (100 %) | 0 | 0 | Aucune |

**Résultat global : 21/21 exécutions PASS. 0 FAIL. 0 régression.**

**Stabilité (R) :** QA-7 écart-type 5.7 ; QA-8 / QA-9 / QA-10 / QA-11 stabilité **100 %** (même seed → mêmes résultats). 0 faux positif dangereux sur QA-5.

**Vitesse (M) :** QA-5 1 ms/dossier · QA-6 2 ms/dossier · QA-7 0 ms · QA-8 2.4 ms · pipeline complet `facilim_prod` mesuré **426 ms** sur 1 dossier réel (smoke test, sans LLM).

**Chiffres bruts à connaître (R) — ils ne sont pas optimistes :**
- **QA-7 :** score solidité **moyen 31.9/100** (médiane 31). Les profils synthétiques sont peu narratifs → solidité basse.
- **QA-10 :** sur 1000, **GO = 0**, GO_AVEC_RISQUES = 974, **NO_GO = 26**. Score complétude moyen **45.5/100**. → **Aucun dossier synthétique n'atteint le niveau « GO ».**
- **QA-9 :** score moyen 31.9, 0 droit stratégique auto-validé (contrôle de sécurité OK).
- **QA-11 :** 7.2 actions/dossier, ROI max 34.6.

---

## PARTIE 5 — DETTES TECHNIQUES

### Dette forte
| Dette | Impact | Probabilité | Effort |
|---|---|---|---|
| Chaîne B (FACILIM 60-100) non câblée dans le workflow réel | Cockpit/stratégie/validation/gate/rapports invisibles pour le pro en prod | Certaine (C) | ~2-3 j de câblage |
| Export CERFA sans passage par `cerfa_gate_engine` | Un CERFA peut être exporté sans validation humaine ni contrôle de cohérence | Certaine (C) | ~0.5 j |
| Dépendance OpenAI pour les narratifs | Sans clé : sections B/C/D/E non narratives, qualité chute | Certaine | ~1 j (mode dégradé explicite) |

### Dette moyenne
| Dette | Impact | Probabilité | Effort |
|---|---|---|---|
| Gap field_mapper ↔ moteur stratégie (RQTH non coché 19.5 %) | Droit détecté non reporté dans le PDF | Mesurée (R) | ~1 j |
| Journal d'audit non persisté (en mémoire seulement) | Pas de traçabilité après la session | Certaine (C) | ~1 j (colonne/table DB) |
| Doublon `dossier_strength` vs `cdaph_strategy` | Deux scores de robustesse divergents | Certaine (C) | ~1 j (harmonisation) |
| `facilim_prod` non couvert par un test automatisé | Régression possible non détectée | Certaine | ~0.5 j (test d'intégration) |

### Dette faible
| Dette | Impact | Probabilité | Effort |
|---|---|---|---|
| `explainability_engine` orphelin | Code maintenu pour rien (sauf QA-8) | Certaine (C) | Décision : brancher ou retirer |
| `import sys` dupliqué dans qa10/qa11 | Cosmétique, sans effet | Certaine (C) | < 5 min |
| Sections CERFA non mappées (AVQ, scolarité C, aidant F < 7 %) | Champs à cocher non remplis | Mesurée (R) | Variable |

---

## PARTIE 6 — RISQUES RÉSIDUELS (jamais validés en réel)

Tous les tests sont **synthétiques** (générateur `synthetic_profiles_engine.py`). N'ont **jamais** été validés sur du réel :

1. **Comportements utilisateurs réels** sur WhatsApp (réponses ambiguës, hors-sujet, multi-tours désordonnés).
2. **Documents atypiques** : certificats manuscrits, scans de mauvaise qualité, formats non standard — aucun extracteur typé (C).
3. **GEVASCO** : aucun parseur dédié (C).
4. **Dossiers incomplets réels** : QA-10 montre que même synthétiques, beaucoup sont NO_GO/RISQUES ; comportement sur vrai dossier partiel non observé.
5. **Erreurs de saisie / fautes / abréviations / dialectes** : non modélisées par le générateur.
6. **Multi-pathologies complexes réelles** : seuls des couples profil_principal/secondaire synthétiques testés.
7. **Situations rares** : polyhandicap (17 cas synthétiques), habilitation familiale, refus de soin, situations familiales conflictuelles.
8. **Qualité narrative LLM sur cas réels** : le 87 % de qualité narrative cité historiquement n'a pas été re-mesuré ici et dépend de la clé OpenAI.
9. **Bout-en-bout WhatsApp → CERFA réel** : jamais exécuté de façon tracée dans cette session.
10. **Pertinence métier validée par un professionnel MDPH** : zéro validation humaine experte à ce jour.

---

## PARTIE 7 — FONCTIONS NON UTILISÉES / CODE MORT / DUPLICATIONS

| Élément | Constat (C) | Recommandation |
|---|---|---|
| `explainability_engine.expliquer_dossier` | Importé seulement par QA-8 | **Brancher dans le cockpit OU retirer** |
| Toute la chaîne B (`facilim_prod` + 14 moteurs) | Aucun appel depuis `main.py`/`orchestration_engine` | **Câbler** (c'est le sens du pilote) — ne pas supprimer |
| `dossier_strength_engine` | Doublon partiel de `cdaph_strategy_engine` | Harmoniser ou déprécier après décision |
| Détection droits oubliés en double (`strategie_dossier` + `eligibilite_droits`) | Deux logiques | Unifier en v2 |
| `EvidenceGraph.items[].section_cerfa` | Tag non exploité côté affichage | Supprimable si confirmé inutile |
| `PlanParcours.parcours_essms` | Généré, non exposé | Exposer ou retirer |
| `import sys` redondant qa10/qa11 | Sans effet | Nettoyage cosmétique |

> **Aucune suppression n'est recommandée avant le pilote** : la majorité du « non utilisé » est en réalité du « non encore câblé ». Supprimer maintenant détruirait la chaîne B qui est le cœur du produit cible.

---

## PARTIE 8 — 10 SCÉNARIOS TERRAIN POUR LE PILOTE ESSMS

| # | Profil | Objectif | Risque principal | Critères de réussite |
|---|---|---|---|---|
| 1 | **TSA enfant léger** (AESH, tiers-temps) | AEEH + SESSAD détectés, sections C/E générées | AVPF parent oublié | AEEH coché, GEVASCO demandé, texte E exploitable |
| 2 | **TSA sévère / polyhandicap** | Orientation IME/MAS, PCH | Sous-estimation des besoins | IME/MAS proposé, PCH signalé, 0 proposition dangereuse |
| 3 | **Polyhandicap** | Couverture besoins lourds | Cov N1 protégé basse (52.7 %) | Droits lourds détectés, alerte si champs AVQ vides |
| 4 | **SEP adulte** | RQTH/AAH/CMI, variabilité documentée | Variabilité « bons/mauvais jours » non captée | Texte B reflète la variabilité, CMI proposé |
| 5 | **Accident du travail** (réf. Karim) | RQTH+AAH+ESPO, PCH oublié, CMI | PCH/CMI ratés (cf. QA-5) | PCH détecté comme oublié, ESPO cochée |
| 6 | **Bipolaire** | RQTH/AAH, SAVS | SAVS raté (121× en QA-5) | SAVS proposé, variabilité documentée |
| 7 | **Schizophrénie** | AAH, accompagnement, protection | Déni/refus de soin | Besoins d'accompagnement identifiés sans surinterprétation |
| 8 | **Aidant familial** | AVPF/AJPP, section F | Section F mappée à 4.6 % | Aidant documenté, droit aidant signalé |
| 9 | **Tutelle / protection juridique** | Représentant légal, Option B | Cov CERFA la plus basse | Qualité juridique renseignée, recevabilité OK |
| 10 | **ESRP / ESPO (insertion)** | Orientation reclassement | RQTH non cochée au PDF (19.5 %) | RQTH **réellement cochée** dans le field_map |

---

## PARTIE 9 — CHECKLIST DE VALIDATION TERRAIN (exploitable)

À remplir par le professionnel pour **chaque dossier** du pilote :

```
□ Temps de préparation mesuré (objectif : < X min vs méthode actuelle)
□ Nombre de corrections humaines nécessaires sur le CERFA produit
□ Au moins un droit oublié pertinent détecté et confirmé par le pro
□ Narratif B/C/D/E jugé utilisable tel quel (oui / à retoucher / inutilisable)
□ CERFA exploitable / déposable en l'état (oui / non)
□ Rapport professionnel jugé pertinent par le pro
□ Tableau de validation humaine compris et utilisé
□ Gate d'export : blocage compris quand il survient
□ Aucun droit incompatible coché (vérif. visuelle)
□ Aucune donnée personnelle visible dans les logs
□ Export final conforme (champs, identité, droits demandés)
□ Verdict pro : gain de temps réel ? (oui / non / neutre)
```

Prérequis techniques avant pilote :
```
□ Clé OpenAI active (sinon narratifs dégradés)
□ PDF storage/templates/cerfa_15692_01.pdf présent
□ facilim_prod câblé dans le workflow OU procédure d'appel manuel documentée
□ verifier_gate_cerfa() invoqué avant tout export définitif
```

---

## PARTIE 10 — MATURITÉ (note /10, justifiée par les faits)

| Dimension | Note | Justification factuelle |
|---|---|---|
| **Architecture** | 8/10 | Séparation claire, 2 chaînes identifiables, modularité réelle (C). −2 : chaîne B non intégrée. |
| **Moteurs métier** | 8/10 | 37 moteurs, QA 21/21 PASS, 0 conseil absurde (R). −2 : doublons + scores synthétiques bas. |
| **CERFA** | 6/10 | N1 76 %, 0 ghost, 0 incompatible (R). −4 : sections AVQ/C/F < 7 %, RQTH non cochée 19.5 %. |
| **Droits** | 6/10 | Détection fiable RQTH/AAH/AEEH. −4 : SAVS/PCH/CMI souvent ratés (R, QA-5). |
| **Narratifs** | 5/10 | Pipeline présent et câblé. −5 : dépendance dure à OpenAI, non re-mesuré ici sur réel. |
| **Validation humaine** | 6/10 | Moteur robuste, 0 auto-validation (R, QA-9). −4 : non câblé au workflow réel. |
| **Explicabilité** | 7/10 | QA-8 100 % PASS, 0 hallucination. −3 : `explainability_engine` orphelin du produit. |
| **QA** | 9/10 | 21/21 PASS, stabilité 100 %, 7000+ exécutions cumulées. −1 : `facilim_prod` non testé automatiquement + 100 % synthétique. |
| **Robustesse** | 6/10 | Crash console UTF-8 corrigé (7 runners) ; 0 FAIL. −4 : 0 test sur documents/saisies réels. |
| **Production** | 4/10 | Webhook async déployé. −6 : chaîne B non câblée, gate non invoqué, audit non persisté, 0 test terrain. |

**Moyenne factuelle : ≈ 6,5/10.**

---

## CONCLUSION OBLIGATOIRE

### 1. FACILIM est-il prêt pour…

| Étape | Réponse | Justification factuelle |
|---|---|---|
| **Tests internes** | **OUI** | 21/21 QA PASS, orchestrateur `facilim_prod` tourne de bout en bout (426 ms, 0 moteur en échec), 0 proposition dangereuse. Suffisant pour tester en interne sur données contrôlées. |
| **Pilote ESSMS** | **NON (pas en l'état)** | La chaîne B (stratégie, validation humaine, cockpit, rapports, gate) **n'est pas câblée** dans le workflow réel (C). Un pilote suppose que le professionnel voie ces sorties — ce qui exige le câblage préalable + clé OpenAI. **Conditionnel : OUI après câblage + clé.** |
| **Utilisation réelle (terrain)** | **NON** | Zéro test sur dossier réel, zéro validation par un professionnel MDPH, export possible sans gate, audit non persisté. |

### 2. Les 10 risques les plus importants avant déploiement réel

1. **Chaîne B non câblée** dans le workflow réel (`facilim_prod` jamais appelé) — bloquant pilote.
2. **Export CERFA sans verrou** : `verifier_gate_cerfa()` jamais invoqué avant export (C).
3. **Dépendance OpenAI** non sécurisée par un mode dégradé explicite.
4. **0 validation par un professionnel MDPH** : pertinence métier non confirmée.
5. **Droits stratégiques souvent ratés** : SAVS, PCH, CMI (R, QA-5).
6. **RQTH/SESSAD/FOYER détectés mais non cochés** dans le PDF (R, QA-6).
7. **Journal d'audit volatil** (non persisté) — pas de traçabilité post-session.
8. **Sections CERFA à cases peu couvertes** (AVQ, scolarité C, aidant F < 7 %).
9. **0 test sur documents/saisies réels** (GEVASCO, scans, fautes) — extracteurs typés absents.
10. **`facilim_prod` non couvert par un test automatisé** : risque de régression silencieuse.

### 3. Question finale

> **« Qu'est-ce qui empêche encore FACILIM d'être utilisé demain matin par un professionnel pour préparer un dossier MDPH de bout en bout ? »**

**Réponse honnête, fondée uniquement sur l'observable :**

Trois obstacles, et un seul est de la « logique métier » :

1. **Le câblage manque (obstacle n°1).** Les moteurs FACILIM 60→100 fonctionnent et passent les QA, mais `facilim_prod.py` n'est appelé par **aucun** point du workflow réel (fait vérifié par recherche dans tout `app/`). Concrètement : aujourd'hui, le professionnel n'a **aucun chemin produit** qui lui montre la stratégie, le tableau de validation, le cockpit, les rapports ou le verrou d'export. Tout cela existe mais reste « débranché ».

2. **Le filet de sécurité n'est pas posé (obstacle n°2).** Un CERFA peut être exporté sans que `verifier_gate_cerfa()` ni la validation humaine n'aient été exécutés. Pour un usage réel, c'est rédhibitoire : le verrou existe dans le code mais n'est pas dans le chemin d'export.

3. **Rien n'a été vu en vrai (obstacle n°3).** 100 % des 7000+ tests sont synthétiques. Aucun dossier MDPH réel, aucun document réel (certificat, GEVASCO), aucune validation par un professionnel. Les chiffres bruts invitent à la prudence : score solidité moyen 31.9/100 et **GO=0** sur 1000 dossiers (QA-10) — sur données synthétiques peu narratives, mais ce signal doit être confronté au réel avant toute conclusion.

**En une phrase :** *FACILIM n'est pas bloqué par sa logique métier — qui est testée et stable — mais par le fait que sa partie « décision/validation/restitution » n'est pas encore branchée sur le chemin que suit réellement un dossier, et qu'aucun dossier réel n'y est encore passé.* Le déblocage est principalement un travail de **câblage (≈ 2-3 jours)** et de **validation terrain encadrée**, pas de développement de nouveaux moteurs.

---

*Rapport factuel — sources : code source `app/engines/`, rapports `app/tests/qa/reports/*_20260606_1144`, exécution QA du 2026-06-06 09:44 UTC.*
*Aucune nouvelle logique métier introduite. Développements gelés.*
