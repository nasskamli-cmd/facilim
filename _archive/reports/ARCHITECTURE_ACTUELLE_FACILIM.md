# ARCHITECTURE_ACTUELLE_FACILIM.md — État réel après commits b0ba56b / 7e04f89 / 1dccf6c

**Généré le :** 2026-06-07
**Mode :** lecture seule. Description de l'architecture **telle que déployée** (deployment `d3587d13`, Online).

---

## 1. FLUX PRINCIPAL (réel)

```
WhatsApp (webhook) / création dossier
        ↓
conversation_engine        ← agents (collecte_schema = checklist unique)
        ↓
orchestration_engine       ← pilote le tour de conversation
        ↓
extract_structured_data_from_history   ← EXTRACTION (whitelist + NIVEAU A depuis 1dccf6c)
        ↓
synthese_json              ← STOCKAGE (fusion : usager prioritaire / admin non réécrasé)
        ↓
   ┌── generer_textes_narratifs (texte_b/c/d/e)  → AFFICHAGE/IMPRESSION uniquement
   ↓
facilim_prod (run)         ← orchestre la chaîne FACILIM 60→100
        ↓
professional_cockpit_engine ← score = CDAPH ; droits = eligibility/cdaph
        ↓
cerfa_gate_engine          ← PASS / WARNING / BLOCK export
        ↓
CERFA V2 (cerfa_filler via v2_bridge)   ← fallback V3 (field_mapper) si V2 échoue
        ↓
audit_trail_engine / historique (cockpit_pro_json, analyse_situation_json)
```

> **Note clé (post-sprints) :** les cases AVQ du CERFA V2 sont désormais pilotées par les **champs structurés `avq_*`** (anti-contamination 7e04f89), et ces champs sont enfin **extraits/persistés** (1dccf6c) — **mais** leur **collecte conversationnelle** dépend encore de questions `requis=False` (voir §5 / ROADMAP).

---

## 2. MODULES ACTIFS

| Module | Rôle | Entrée | Sortie | Statut | Risque |
|---|---|---|---|---|---|
| `collecte_schema` | Source unique de la checklist + `normaliser_collecte` | profil | checklist, droits.*→droits_demandes | ✅ Actif | NIVEAU A `requis=False` |
| `conversation_engine` | Prompt agents + extraction structurée (whitelist) | historique WhatsApp | champs extraits | ✅ Actif (corrigé 1dccf6c) | dépend qualité LLM |
| `orchestration_engine` | Pilote conversation + persistance synthese | message, dossier | synthese_json | ✅ Actif | fusion multi-tours `droits` |
| `facilim_prod` | Orchestrateur chaîne 60→100 | synthese_json | cockpit_pro | ✅ Actif | hérite contamination résiduelle V3 |
| `eligibilite_droits_engine` | Score par droit (22 droits) | preuves déclarées (texte_b/c/d/e retirés) | analyses droits | ✅ Actif (assaini 7e04f89) | keyword sur texte déclaré |
| `cdaph_strategy_engine` | Score de solidité / stratégie | preuves déclarées | score_solidite | ✅ Actif (assaini 7e04f89) | — |
| `evidence_engine` | Graphe de preuves (origine taguée) | déclaré + narratif (tagué) | items preuve | ⚠️ Actif | narratifs encore inclus (tagués) |
| `cerfa_gate_engine` | Décision export | synthese + validations | PASS/WARN/BLOCK | ✅ Actif | blocage sur présence narratif |
| `cerfa_filler` (V2) | Génération PDF CERFA | dossier V2 | PDF | ✅ Actif (prod) | mapping NIVEAU A incomplet |
| `v2_bridge` | synthese_json → dossier V2 | synthese_json | dossier V2 | ✅ Actif | n'écrit pas organisme/allocataire |
| `field_mapper` (V3) | Génération CERFA (fallback) | synthese_json | champs | ⚠️ Fallback | AVQ par mots-clés (non assaini) |
| `professional_cockpit_engine` | Tableau de pilotage pro | synthese_json | cockpit_pro_json | ✅ Actif | score = CDAPH (héritage) |
| `audit_trail_engine` / historique | Traçabilité | événements | audit/historique | ✅ Actif | — |
| `dossier_strength_engine` | Score de solidité (indicateur) | preuves + narratif | score | ⚠️ Actif | ~45 % narratif (refonte différée) |

---

## 3. SOURCES DE VÉRITÉ

| Source | Nature | Rôle décisionnel autorisé ? |
|---|---|---|
| **Données collectées** (réponses WhatsApp) | 🟩 Preuve déclarée | ✅ OUI |
| **Documents source** (`_document_knowledge`, notes_pro) | 🟩 Preuve documentaire | ✅ OUI |
| **`synthese_json`** | 🟦 État structuré consolidé | ✅ OUI (source de tout l'aval) |
| **Champs structurés** (`avq_*`, `droits.*`, `pension_invalidite`…) | 🟦 Structuré | ✅ OUI (source officielle des cases) |
| **`analyse_situation_json`** | 🟥 Dérivé (analyse générée) | ⚠️ Affichage / synthèse (pas re-décision) |
| **`cockpit_pro_json`** | Dérivé structuré | ✅ Affichage pilotage |
| **Narratifs** (`texte_b/c/d/e`, `description_situation` P8) | 🟥 Généré LLM | ⛔ **Affichage / impression UNIQUEMENT** |
| **CERFA** | Document final | Sortie (relu/validé humain) |

> **Règle gravée (7e04f89) :** les narratifs générés sont **affichables et imprimables** mais **ne doivent plus servir de preuve décisionnelle** (score, droit, case CERFA, gate).

---

## 4. ARCHITECTURE DE CONFIANCE

```
🟩 PREUVES DÉCLARÉES  +  🟦 DONNÉES STRUCTURÉES
        ↓
   MOTEURS (eligibility, cdaph, cerfa_filler AVQ, gate)
        ↓
   DÉCISIONS (droits, score, cases CERFA, export)

🟥 NARRATIFS GÉNÉRÉS (texte_b/c/d/e, P8)
        ↓
   AFFICHAGE / IMPRESSION uniquement   (jamais en entrée décisionnelle)
```

**Statut d'application :**
- ✅ eligibility, cdaph, cerfa_filler (V2 AVQ) : narratifs retirés des décisions (7e04f89).
- ⚠️ **field_mapper (V3)** : AVQ encore par mots-clés sur `impact` — **non assaini** (risque sur fallback).
- ⚠️ **evidence_engine** : inclut encore les narratifs comme items (origine taguée, non exclue).
- ⚠️ **dossier_strength** : ~45 % du score = narratif (refonte différée).

---

## 5. ÉTAT DES PRINCIPAUX VERROUS

| Verrou | Statut | Preuve |
|---|---|---|
| CERFA V2 | ✅ Rétabli & utilisé en prod | QA-FIX-TEST4-CERFA-V2 PASS ; logs `[CERFA V2] PDF généré` |
| Collecte (checklist unique) | ✅ Active | QA-SCHEMA 5/5 ; `collecte_schema.checklist_for` |
| Vague 1 (champs structurés) | 🟡 Définie + extraite + persistée, **collecte conversationnelle à valider** | QA-V1-REAL 5/5 (LLM mocké) ; champs `requis=False` non sollicités (base.py) |
| Extraction (whitelist + profil réel) | ✅ Corrigée (1dccf6c) | QA-V1-REAL ; whitelist inclut NIVEAU A |
| Anti-contamination | ✅ Active (V2) | QA-ANTI 5/5 ; ⚠️ V3 non couvert |
| Cockpit | ✅ Actif | QA-PROD-2 PASS ; assaini par héritage CDAPH |
| Gate | ✅ Actif | QA-PROD-3 PASS |
| Audit trail | ✅ Actif | QA-PROD-4 PASS |
| Historique | ✅ Actif | QA-PROD-5 PASS |
| Tests terrain | ❌ **NON RÉALISÉS** | aucune trace conversation dans logs prod |

---

## Synthèse de maturité
- **Déployé & stable :** CERFA V2, collecte, extraction, anti-contamination (V2), cockpit, gate, audit, historique.
- **À valider en terrain réel :** la **collecte conversationnelle** des champs NIVEAU A (le LLM pose-t-il les questions ? extrait-il correctement ?).
- **Gaps résiduels connus :** mapping CERFA de `organisme_payeur`/`numero_allocataire`/invalidité (V2) ; AVQ V3 non assaini ; fusion multi-tours `droits` ; evidence/dossier_strength encore exposés au narratif.

---

*Architecture décrite telle que déployée. Aucune modification de code. Statuts adossés aux QA et aux audits de session.*
