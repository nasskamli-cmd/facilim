# AUDIT_VAGUE1_EXTRACTION_PERSISTENCE.md — Vague 1 fonctionne-t-elle, ou est-elle décorative ?

**Généré le :** 2026-06-07
**Mode :** AUDIT LECTURE SEULE. Aucune correction, modification, commit, déploiement.
**Hypothèse testée :** les champs NIVEAU A (Vague 1) sont dans la checklist mais **absents des listes d'extraction / de la persistance** → jamais capturés.
**Verdict :** **HYPOTHÈSE CONFIRMÉE.** La Vague 1 est **essentiellement décorative** en flux réel : ses champs structurés sont **demandés mais jamais extraits ni persistés**.

---

## ÉTAPE 1 — Champs NIVEAU A ajoutés par Vague 1 (source : `collecte_schema.py`)

| # | Champ | Groupe | Déf. (ligne) |
|---|---|---|---|
| 1 | `prenom` | identité fine | L63 |
| 2 | `nom_naissance` | identité fine | L64 |
| 3 | `organisme_payeur` | administratif | L67 |
| 4 | `numero_allocataire` | administratif | L68 |
| 5 | `pension_invalidite` | invalidité | L71 |
| 6 | `categorie_invalidite` | invalidité | L72 |
| 7 | `accident_travail` | invalidité | L73 |
| 8 | `maladie_professionnelle` | invalidité | L74 |
| 9 | `taux_ipp` | invalidité | L75 |
| 10 | `avq_toilette` | AVQ | L37-40 |
| 11 | `avq_habillage` | AVQ | L37-40 |
| 12 | `avq_repas` | AVQ | L37-40 |
| 13 | `avq_deplacements` | AVQ | L37-40 |
| 14 | `avq_gestion_quotidienne` | AVQ | L37-40 |
| 15 | objet `droits.*` (clés : `aah, pch, rqth, cmi_invalidite, cmi_priorite, cmi_stationnement` [+`aeeh`]) | droits | L42-45 |

> ⚠️ **Note :** `avq_courses` (cité dans l'hypothèse) **n'existe pas** dans Vague 1. Le champ réel est `avq_gestion_quotidienne`. `AVQ_CHAMPS` contient exactement 5 champs (L37-40).

**Total : 14 champs scalaires + 1 objet `droits.*`.**

---

## ÉTAPE 2 / 3 — Tableau de traçabilité (vérifié directement)

Légende : **CL** = checklist (`checklist_for`) · **PE** = prompt extraction conversation · **WL** = whitelist `_CHAMPS_EXTRACTIBLES_*` · **PD** = chemin document · **SJ** = persisté dans synthese_json · **CERFA** = destination existante.

| Champ | CL | PE/WL (conversation) | PD (document) | SJ | CERFA | Verdict |
|---|---|---|---|---|---|---|
| `prenom` | ✅ | ❌ | ❌ | ❌ | P2 3 (fallback split) | **DÉFINI MAIS NON EXTRAIT** |
| `nom_naissance` | ✅ | ❌ | ❌ | ❌ | P2 1 (fallback split) | **DÉFINI MAIS NON EXTRAIT** |
| `organisme_payeur` | ✅ | ❌ | ❌ | ❌ | P2 radio | **DÉFINI MAIS NON EXTRAIT** |
| `numero_allocataire` | ✅ | ❌ | ❌ | ❌ | P2 13 | **DÉFINI MAIS NON EXTRAIT** |
| `pension_invalidite` | ✅ | ❌ | ❌ | ❌ | (mot-clé statut) | **DÉFINI MAIS NON EXTRAIT** |
| `categorie_invalidite` | ✅ | ❌ | ❌ | ❌ | ABSENT | **DÉFINI MAIS NON EXTRAIT** |
| `accident_travail` | ✅ | ❌ | ✅ (L1320) | ⚠️ **uniquement si document** | P5 15/20 | **EXTRAIT (document seulement)** |
| `maladie_professionnelle` | ✅ | ❌ | ❌ | ❌ | (partiel AT/MP) | **DÉFINI MAIS NON EXTRAIT** |
| `taux_ipp` | ✅ | ❌ | ❌ | ❌ | non écrit | **DÉFINI MAIS NON EXTRAIT** |
| `avq_toilette` | ✅ | ❌ | ❌ | ❌ | P6 B1 (post-fix) | **DÉFINI MAIS NON EXTRAIT** |
| `avq_habillage` | ✅ | ❌ | ❌ | ❌ | P6 B2 | **DÉFINI MAIS NON EXTRAIT** |
| `avq_repas` | ✅ | ❌ | ❌ | ❌ | P6 B3 | **DÉFINI MAIS NON EXTRAIT** |
| `avq_deplacements` | ✅ | ❌ | ❌ | ❌ | P6 B4 | **DÉFINI MAIS NON EXTRAIT** |
| `avq_gestion_quotidienne` | ✅ | ❌ | ❌ | ❌ | P6 (field_mapper) | **DÉFINI MAIS NON EXTRAIT** |
| objet `droits.*` | ✅ | ❌ (extrait `droits_demandes` texte) | ❌ | ❌ (objet) | via `normaliser` → texte | **DÉFINI MAIS NON EXTRAIT** (objet) |

**Aucun champ NIVEAU A n'est en statut OK.** 14/15 = « DÉFINI MAIS NON EXTRAIT ». 1/15 (`accident_travail`) = extrait **uniquement** par upload de document, jamais par la conversation.

### Preuves directes (numéros de ligne vérifiés)
- **Whitelists conversation** : `_CHAMPS_EXTRACTIBLES_ENFANT` (L436-448), `_CHAMPS_EXTRACTIBLES_ADULTE` (L450-465), `_MIXTE` (L467-469) — **aucune** ne contient un champ NIVEAU A.
- **Extraction conversation** : `extract_structured_data_from_history` filtre sur la whitelist (L499) + **rejet défensif** des champs hors liste (L530-537), avec prompt « n'inclus AUCUN champ hors de cette liste » (L512).
- **Appel** : orchestration L484-488 avec `profil_mdph="inconnu"` → whitelist ADULTE.
- **Fusion/persistance conversation** : orchestration L502-508 → seul `nouvelles_donnees` (whitelisté) entre dans `donnees` → `synthese_json`.
- **Chemin document** : prompt L1316-1320 (liste **sans** NIVEAU A) ; `fusionner_dans_donnees` (document_functional_extractor L493-521) écrit **uniquement** `donnees["_document_knowledge"]`, jamais `avq_*`/`droits.*`/identité fine.
- **Normalisation** : `normaliser_collecte` (collecte_schema L158-183) dérive `droits_demandes` depuis `droits.*` — mais appelée au **moment du CERFA** (field_mapper/v2_bridge/facilim_prod), sur `donnees` = synthese_json qui **ne contient pas `droits.*`** → **sans effet en flux réel**.

---

## ÉTAPE 4 — Comptage réel

| Mesure | Conversation (WhatsApp) | Avec document uploadé |
|---|---|---|
| Champs NIVEAU A **demandés** (checklist) | 15 (mais `requis=False` → non priorisés) | 15 |
| Champs NIVEAU A **réellement extractibles** | **0** | **1** (`accident_travail`) |
| Champs NIVEAU A **réellement persistables** | **0** | **1** |
| Champs NIVEAU A **arrivant réellement au CERFA (structuré)** | **0** | **1** (AT/MP) |

➡️ **0 / 14 champs structurés** Vague 1 atteignent le CERFA en conversation pure. **1 / 14** (accident_travail) si et seulement si un document est uploadé.

---

## ÉTAPE 5 — Premier point de rupture unique

**OUI, un seul endroit neutralise la quasi-totalité de la Vague 1 :**

```
conversation_engine._CHAMPS_EXTRACTIBLES_ADULTE / _ENFANT / _MIXTE   (L436-469)
        ↓ utilisé par
extract_structured_data_from_history(...)   (L499, rejet L530-537)
        ↓ appelé par
orchestration_engine  (L484, profil_mdph="inconnu")
        ↓
synthese_json  ← ne reçoit JAMAIS le NIVEAU A
```

Un unique verrou (la whitelist d'extraction) bloque 14 des 15 champs. Tout le reste de la Vague 1 (normalisation, lecture CERFA `avq_*`, branchement anti-contamination 7e04f89) est **construit correctement en aval** mais **affamé** faute de données en entrée.

---

## MODE AUDIT FACILIM

### CE QUI EST PROUVÉ
- Les 15 champs NIVEAU A sont dans la **checklist** (`collecte_schema`) mais **aucun** dans les **whitelists d'extraction** (conversation) ni dans la **liste d'extraction document**.
- `synthese_json` n'est alimenté que par ces deux chemins → **le NIVEAU A structuré n'est jamais persisté** (sauf `accident_travail` via document).
- `normaliser_collecte` (droits.* → droits_demandes) est **sans effet** car `droits.*` n'est jamais en synthèse.
- **Vague 1 est inerte en flux réel** ; le fix anti-contamination `avq_*` (7e04f89) l'est aussi (données absentes).

### CE QUI EST NON VÉRIFIÉ
- Existence éventuelle d'un **autre point d'écriture** de synthese_json (d'autres `UPDATE dossiers SET synthese_json` existent, ex. L1396/L1489 ; les chemins lus écrivent du whitelisté/dérivé/`_document_knowledge`, mais je n'ai pas lu **chaque** site ligne à ligne).
- Comportement **réel en production** (données prod inaccessibles ; `railway ssh` bloqué, non contourné).
- Si une **édition pro via dashboard** permet de saisir/persister des NIVEAU A hors conversation (non tracé).

### RISQUE PRINCIPAL
Les sprints Vague 1 et anti-contamination **paraissent livrés et testés** (QA vertes) alors qu'ils sont **inopérants en production** : les QA injectent les `avq_*`/`droits.*` directement dans la synthèse, court-circuitant l'extraction réelle. Illusion de couverture.

### GOULOT D'ÉTRANGLEMENT
`_CHAMPS_EXTRACTIBLES_*` + `extract_structured_data_from_history` (whitelist d'extraction).

### PREMIER POINT DE RUPTURE
**L'extraction** (whitelist), entre COLLECTE et STOCKAGE. Les champs sont demandés, l'usager peut répondre, mais la capture les jette avant la persistance.

### IMPACT SUR TEST4 (Karim / CECORA)
Cohérent avec l'audit AVQ : les `avq_*` structurés n'ayant **jamais** été collectés/persistés, le CERFA ne pouvait s'appuyer que sur le **narratif** → d'où les limitations AVQ inventées. Le fix anti-contamination a coupé le narratif **sans** que le structuré n'arrive → en l'état, AVQ **vides** en flux réel (sous-remplissage), pas surremplissage.

### IMPACT SUR LE DASHBOARD ~35 %
Le faible taux de remplissage observé est **expliqué** : tout le NIVEAU A (identité fine, administratif, invalidité, AVQ, droits structurés) **n'entre jamais** dans `synthese_json`. Ajouter Vague 1 n'a pas pu faire monter le remplissage, puisque les champs sont jetés à l'extraction. (Et `requis=False` ⇒ ils ne comptent pas non plus dans une complétude basée sur les requis.)

### IMPACT SUR LE CERFA
Cases/champs NIVEAU A du CERFA **vides** en flux réel : organisme payeur, n° allocataire, cases AVQ P6, taux IPP, catégorie invalidité. Identité fine (prénom/nom_naissance) **rattrapée** par découpage heuristique de `nom_prenom`. Les droits restent remplis via `droits_demandes` (texte, whitelisté).

### CORRECTION THÉORIQUE MINIMALE (ne pas coder)
1. **Ajouter** les 14 champs NIVEAU A (+ clés `droits.*`) aux trois `_CHAMPS_EXTRACTIBLES_*`.
2. **Passer le vrai `profil_mdph`** à `extract_structured_data_from_history` (au lieu de `"inconnu"`).
3. **Étendre le prompt d'extraction** pour produire les **niveaux AVQ** (AUTONOME/DIFFICULTE/AIDE_PARTIELLE/AIDE_TOTALE) et l'**objet `droits.*`** (booléens), pas seulement du texte.
4. *(Optionnel)* **Étendre la liste d'extraction document** (L1316-1320) aux mêmes champs pour bénéficier des bilans uploadés.
5. **QA d'activation** : un dossier conversationnel réel doit faire apparaître `avq_*`, `droits.*`, `organisme_payeur`, `numero_allocataire` dans `synthese_json`, puis dans le CERFA.

> Cette correction, **localisée à un seul fichier** (`conversation_engine.py`) pour l'essentiel, **active rétroactivement** Vague 1 ET rend opérant le fix anti-contamination 7e04f89.

---

## CRITÈRE DE RÉUSSITE — réponse
**Vague 1 NE fonctionne PAS réellement : elle est décorative.** Les champs structurés sont définis et demandés, mais **jetés à l'extraction** (whitelist), donc **jamais persistés ni acheminés au CERFA** (sauf `accident_travail` via document). Le branchement aval (normalisation, lecture `avq_*`, anti-contamination) est correct mais **affamé**. Un **seul** correctif (whitelist d'extraction + prompt) activerait l'ensemble.

---

*Audit lecture seule. Keystone (whitelists + chemins de persistance conversation & document) vérifié directement, lignes citées. Aucune correction effectuée. Production non observée.*
