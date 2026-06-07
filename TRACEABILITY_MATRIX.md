# TRACEABILITY_MATRIX.md — Cycle de vie des champs NIVEAU A (post b0ba56b / 7e04f89 / 1dccf6c)

**Généré le :** 2026-06-07
**Mode :** lecture seule. État **après** les 3 commits déployés.
**Légende :** ✅ OK · 🟡 conditionnel/partiel · ❌ rompu · ❓ NON VÉRIFIÉ.
**Stages :** COLLECTÉ (l'agent le demande) → EXTRAIT (whitelist+LLM) → PERSISTÉ (synthese_json) → VISIBLE dashboard → UTILISÉ moteurs → MAPPÉ CERFA.

---

## Matrice

| CHAMP | COLLECTÉ | EXTRAIT | PERSISTÉ | VISIBLE | UTILISÉ | CERFA | 1er point de rupture |
|---|---|---|---|---|---|---|---|
| `prenom` | 🟡 requis=False | ✅ (1dccf6c) | ✅ | ❓ | — | ✅ P2 3 | **COLLECTE** (non sollicité) |
| `nom_naissance` | 🟡 requis=False | ✅ | ✅ | ❓ | — | ✅ P2 1 | **COLLECTE** |
| `organisme_payeur` | 🟡 requis=False | ✅ | ✅ | ❓ | ❌ | ❌ (v2_bridge gap) | **COLLECTE** + **MAPPING CERFA** |
| `numero_allocataire` | 🟡 requis=False | ✅ | ✅ | ❓ | ❌ | ❌ (P2 13 vide, **prouvé**) | **COLLECTE** + **MAPPING CERFA** |
| `pension_invalidite` | 🟡 requis=False | ✅ | ✅ | ❓ | 🟡 (via texte statut, pas le booléen) | ❌ (pas de case structurée) | **COLLECTE** + **MAPPING CERFA** |
| `categorie_invalidite` | 🟡 requis=False | ✅ | ✅ | ❓ | ❌ | ❌ (ABSENT du CERFA) | **COLLECTE** + **CERFA absent** |
| `taux_ipp` | 🟡 requis=False | ✅ | ✅ | ❓ | 🟡 (mot-clé) | ❌ (non écrit) | **COLLECTE** + **CERFA absent** |
| `accident_travail` | 🟡 (+ document) | ✅ | ✅ | ❓ | ✅ (elig/cdaph) | ✅ P5 15/20 | **COLLECTE** (le mieux loti) |
| `maladie_professionnelle` | 🟡 requis=False | ✅ | ✅ | ❓ | 🟡 | 🟡 (AT/MP partiel) | **COLLECTE** + mapping partiel |
| `avq_toilette` | 🟡 requis=False | ✅ | ✅ | ❓ | ✅ (cerfa_filler V2) | ✅ P6 B1 | **COLLECTE** + risque enum |
| `avq_habillage` | 🟡 requis=False | ✅ | ✅ | ❓ | ✅ | ✅ P6 B2 | **COLLECTE** + risque enum |
| `avq_repas` | 🟡 requis=False | ✅ | ✅ | ❓ | ✅ | ✅ P6 B3 | **COLLECTE** + risque enum |
| `avq_deplacements` | 🟡 requis=False | ✅ | ✅ | ❓ | ✅ | ✅ P6 B4/P7 | **COLLECTE** + risque enum |
| `avq_gestion_quotidienne` | 🟡 requis=False | ✅ | ✅ | ❓ | 🟡 | 🟡 (field_mapper) | **COLLECTE** |
| objet `droits.*` | 🟡 requis=False | ✅ | ✅ | ❓ | ✅ (via droits_demandes) | ✅ P17 | **COLLECTE** + fusion multi-tours |

---

## Lecture des ruptures

### Rupture #1 (commune à TOUS) — COLLECTE
`base.py._build_context` (L193-196) et `missing_fields` (L90) **n'injectent que les champs `requis=True`**. Tout le NIVEAU A est `requis=False` → **non listé dans les questions** → non demandé spontanément → rien à extraire.
**C'est la rupture amont qui neutralise toute la chaîne**, malgré extraction/persistance réparées.

### Rupture #2 — MAPPING CERFA (sous-ensemble admin/invalidité)
`organisme_payeur`, `numero_allocataire`, `pension_invalidite`, `categorie_invalidite`, `taux_ipp` : **persistés mais non écrits au CERFA** par V2 (`v2_bridge` ne les propage pas ; cases absentes). **Prouvé** : P2 13 = vide au test de déploiement.

### Risque #3 — enum AVQ
`avq_*` mappés au CERFA **si** la valeur ∈ {AUTONOME, DIFFICULTE, AIDE_PARTIELLE, AIDE_TOTALE} (égalité stricte `_avq_besoin`). Une valeur libre du LLM → case non cochée (perte silencieuse).

### Colonne VISIBLE = ❓ partout
La présence des champs NIVEAU A dans le **rendu dashboard** n'a **pas** été vérifiée (le cockpit lit le score CDAPH + droits ; l'affichage des `avq_*`/`organisme_payeur` bruts n'est pas confirmé). **NON VÉRIFIÉ**.

---

## Ce qui FONCTIONNE de bout en bout (post-commits)
- **`droits.*` / droits_demandes** → CERFA P17 + moteurs : chaîne complète **si** déclaré (prouvé QA-V1-REAL + validation déploiement).
- **`avq_*`** → cases P6 : chaîne complète **si** déclaré ET valeur conforme à l'enum (prouvé via injection directe ; **collecte réelle NON VÉRIFIÉE**).
- **identité fine** (`prenom`/`nom_naissance`) → P2 (avec fallback split `nom_prenom`).
- **`accident_travail`** → P5 : le seul champ « invalidité » réellement bout-en-bout.

---

*Matrice établie à partir du code déployé + audits de session. La colonne COLLECTÉ=🟡 et VISIBLE=❓ sont les zones NON VÉRIFIÉES clés, à lever en test terrain.*
