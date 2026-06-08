# MDPH_DATA_TRACEABILITY_MATRIX.md — Cartographie du cycle de vie des données FACILIM

**Généré le :** 2026-06-07
**Mode :** AUDIT LECTURE SEULE. Aucune correction, modification, commit ou déploiement.
**Objet :** pour chaque champ MDPH critique, tracer `SOURCE → COLLECTE → STOCKAGE → SYNTHÈSE → COCKPIT/MOTEURS → CERFA` et localiser le **premier point de rupture**.

---

## 0. DÉCOUVERTE MAJEURE (keystone — vérifiée directement)

**Le `synthese_json` est alimenté UNIQUEMENT par `extract_structured_data_from_history`** (orchestration_engine L484-508), qui **filtre via une whitelist** (`conversation_engine._CHAMPS_EXTRACTIBLES_*`, L436-477) et **rejette tout champ hors liste** (L530-537). Appel fait avec `profil_mdph="inconnu"` → whitelist **ADULTE** par défaut (L488).

➡️ **Conséquence prouvée :** **AUCUN champ NIVEAU A / Vague 1 n'est dans la whitelist** → ils sont **demandés en conversation mais jamais persistés** :
`prenom`, `nom_naissance`, `organisme_payeur`, `numero_allocataire`, `pension_invalidite`, `categorie_invalidite`, `maladie_professionnelle`, `taux_ipp`, **tous les `avq_*`**, et l'**objet `droits.*`**.

➡️ **Impact direct sur les sprints précédents :**
- **Vague 1 (collecte structurée) est INERTE en flux réel** : les champs structurés n'atteignent jamais `synthese_json`.
- **Le fix anti-contamination `avq_*`→CERFA (commit 7e04f89) est INERTE en flux réel** : `avq_*` n'étant jamais persisté, les cases AVQ ne se cochent plus depuis le structuré… et la source narrative ayant été (justement) retirée, **les cases AVQ risquent de ne plus se cocher du tout en conversation réelle**. C'est cohérent avec « case cochée uniquement si preuve structurée » — mais la preuve structurée **n'arrive jamais**.

**Le vrai goulot n'est ni le CERFA ni les moteurs : c'est l'EXTRACTION.**

---

## 1. MÉTHODE & ÉTAGES

| Étage | Mécanisme | Fichier(s) |
|---|---|---|
| COLLECTE (questions) | `checklist_for(profil)` (3 agents) | `collecte_schema.py`, `conversation/*_agent.py` |
| EXTRACTION (capture) | `extract_structured_data_from_history` + **whitelist** | `conversation_engine.py` L436-542 |
| STOCKAGE | `synthese_json` (+ colonnes dédiées `texte_b/c/d/e`, `analyse_situation_json`, `cockpit_pro_json`) | `orchestration_engine.py` L484-508 |
| SYNTHÈSE/NARRATIF | `texte_b/c/d/e` (LLM), `description_situation` (P8) | `cerfa_narrative_engine.py`, `cerfa_filler.py` |
| MOTEURS | eligibility / cdaph / cockpit / strength / evidence | `app/engines/*` |
| CERFA | V2 `cerfa_filler` (+ `v2_bridge`), V3 `field_mapper` | `services/cerfa_filler.py`, `app/engines/pdf/*` |

**Statuts :** OK · PARTIEL · NON UTILISÉ · PERDU (collecté/demandé mais non persisté) · INEXISTANT (ni champ ni source).

---

## 2. MATRICE PAR CHAMP

> Légende colonnes : **Coll.** (demandé par un agent) · **Stock.** (persisté dans synthese_json) · **Synth.** (narratif) · **Cockpit/Moteurs** · **CERFA**.

### IDENTITÉ
| Champ | Coll. | Stock. | Moteurs | CERFA | Statut | 1er point de rupture |
|---|---|---|---|---|---|---|
| nom | ✅ (`nom_prenom`) | ✅ | non | P2 1 | **OK** | — |
| prénom | ✅ (`prenom` NIVEAU A) | ❌ | non | P2 3 (fallback split `nom_prenom`) | **PERDU** (structuré) / PARTIEL (via split) | **extraction** (hors whitelist) |
| nom_naissance | ✅ (NIVEAU A) | ❌ | non | P2 1 (fallback split) | **PERDU** / PARTIEL | **extraction** |
| sexe / genre | ✅ (`genre` requis) | ✅ | **aucun moteur** | P2 radio | **OK** (CERFA) / NON UTILISÉ (moteurs) | — |
| date_naissance | ✅ | ✅ | ✅ (âge) | Date A | **OK** | — |
| lieu/commune naissance | ❌ | ❌ | non | P2 4/5 (vide) | **INEXISTANT** | **jamais collecté** |
| nationalité | ❌ | ❌ | non | P2 radio (vide) | **INEXISTANT** | **jamais collecté** |
| adresse | ✅ (`adresse_complete`) | ✅ | non | P2 8/9 | **OK** | — |
| email | ⚠️ (whitelist oui, checklist non) | ✅ si mentionné | non | P2 11 | **PARTIEL** | collecte non explicite |
| téléphone | ✅ | ✅ | non | 24 | **OK** | — |
| NIR / num_secu | ✅ | ✅ | non | Numero SS | **OK** | — |

### ADMINISTRATIF
| Champ | Coll. | Stock. | Moteurs | CERFA | Statut | 1er point de rupture |
|---|---|---|---|---|---|---|
| CAF/MSA (`organisme_payeur`) | ✅ (NIVEAU A) | ❌ | aucun | P2 radio | **PERDU** | **extraction** |
| numéro allocataire | ✅ (NIVEAU A) | ❌ | aucun | P2 13 (attendu, vide) | **PERDU** | **extraction** |
| assurance maladie (CPAM) | ❌ | ❌ | non | P2 radio (vide) | **INEXISTANT** | jamais collecté |
| mutuelle | ❌ | ❌ | non | ABSENT | **INEXISTANT** | n/a |
| pension_invalidite | ✅ (NIVEAU A) | ❌ | eligibility (via texte `statut_emploi`) | via mot-clé | **PERDU** (structuré) / PARTIEL (texte) | **extraction** |
| catégorie invalidité | ✅ (NIVEAU A) | ❌ | eligibility (mot-clé) | ABSENT | **PERDU** + CERFA INEXISTANT | **extraction** |
| taux IPP | ✅ (NIVEAU A) | ❌ | strength/cdaph (mot-clé) | non écrit | **PERDU** | **extraction** |
| AT / MP (`accident_travail`) | ⚠️ | ⚠️ (hors whitelist — voir NON VÉRIFIÉ) | eligibility/cdaph/evidence | P5 15/20 | **PARTIEL / NON VÉRIFIÉ** | extraction probable |
| RSA | ❌ | ❌ | non explicite | via impact (texte) | **INEXISTANT** (structuré) | jamais collecté |
| AAH existante | ✅ (via `droits_demandes`) | ✅ | ✅ | P17 | **PARTIEL** (demandée vs existante non distinguées) | conception |

### DROITS
| Champ | Coll. | Stock. | Moteurs | CERFA | Statut | 1er point de rupture |
|---|---|---|---|---|---|---|
| `droits_demandes` (texte) | ✅ | ✅ | ✅ (elig/cdaph) | P17 | **OK** | — |
| objet `droits.*` (structuré) | ✅ (NIVEAU A) | ❌ | aucun (lisent le texte) | via `normaliser` → texte | **PERDU** (objet) | **extraction** |
| AAH | ✅ (texte) | ✅ | ✅ | P17 6 | **OK** (texte) | — |
| PCH | ✅ (texte) | ✅ | ✅ | P17 2/12 | **OK** (texte) | — |
| RQTH | ✅ (texte) | ✅ | ✅ | P17 6 / P18 | **OK** (texte) | — |
| CMI invalidité | ✅ (texte) | ✅ | ✅ | P17 3/13 | **OK** (texte) | — |
| CMI priorité | ✅ (texte) | ✅ | partiel | P17 13 | **PARTIEL** (souvent confondu avec invalidité) | conception |
| CMI stationnement | ✅ (texte) | ✅ | ✅ | P17 4/14 | **OK** (texte) | — |
| orientation ESMS | ✅ (texte) | ✅ | ✅ | P17 8 | **OK** (texte) | — |
| AEEH | ✅ (texte) | ✅ | ✅ | P17 1 | **OK** (texte) | — |

### AVQ (autonomie)
| Champ | Coll. | Stock. | Moteurs | CERFA | Statut | 1er point de rupture |
|---|---|---|---|---|---|---|
| toilette (`avq_toilette`) | ✅ (NIVEAU A) | ❌ | (lisaient texte) | P6 B1 (post-fix : structuré) | **PERDU** | **extraction** |
| habillage (`avq_habillage`) | ✅ | ❌ | — | P6 B2 | **PERDU** | **extraction** |
| repas (`avq_repas`) | ✅ | ❌ | — | P6 B3 | **PERDU** | **extraction** |
| déplacements (`avq_deplacements`) | ✅ | ❌ | — | P6 B4 / P7 | **PERDU** | **extraction** |
| gestion administrative (`avq_gestion_quotidienne`) | ✅ | ❌ | — | P6/field_mapper | **PERDU** | **extraction** |
| courses | ❌ (pas de champ) | ❌ | non | P6 B5 (mot-clé impact) | **PARTIEL** (texte) | pas de champ structuré |
| ménage | ❌ | ❌ | non | ABSENT | **INEXISTANT** | n/a |
| communication | ❌ (pas de champ avq) | ❌ | non | P6 B6 (mot-clé) | **PARTIEL** (texte) | pas de champ structuré |

> ⚠️ Post-commit 7e04f89, les cases AVQ se cochent **uniquement** sur `avq_*` (structuré). Comme `avq_*` n'est jamais persisté (extraction), **les AVQ ne sont plus alimentées en flux réel**. La preuve du fix (QA-ANTI-4) passe car le test injecte directement `avq_*` dans la synthèse, court-circuitant l'extraction.

### ENFANT
| Champ | Coll. | Stock. | Moteurs | CERFA | Statut | 1er point de rupture |
|---|---|---|---|---|---|---|
| AESH | ❌ (déduit de `situation_scolaire`) | via texte | ✅ (mot-clé) | P10 1 (mot-clé) | **PARTIEL** | pas de champ dédié |
| PPS | ❌ | ❌ | non | ABSENT | **INEXISTANT** | n/a |
| GEVASCO | ❌ (mot-clé) | via texte | ✅ (mot-clé) | ABSENT | **PARTIEL** (moteurs) / CERFA INEXISTANT | pas de champ dédié |
| établissement (`etablissement_scolaire`) | ✅ | ✅ | non | P9 1 | **OK** | — |
| scolarité (`situation_scolaire`) | ✅ | ✅ | ✅ | P9 cases | **OK** | — |

### PROTECTION
| Champ | Coll. | Stock. | Moteurs | CERFA | Statut | 1er point de rupture |
|---|---|---|---|---|---|---|
| `type_protection` | ✅ (agent protege) | ⚠️ whitelist a `protection_juridique`/`sous_tutelle`, **pas** `type_protection` | eligibility (texte) | P3 cases | **PARTIEL / NON VÉRIFIÉ** (mismatch de nommage) | **extraction** (nom non whitelisté) |
| curatelle simple | déduit `type_protection` | — | non | P3 5 | **PARTIEL** (simple/renforcée même case) | extraction + conception |
| curatelle renforcée | déduit | — | non | P3 5 (même case) | **PARTIEL** | conception |
| tutelle | déduit | — | non | P3 4 | **PARTIEL** | extraction |
| habilitation familiale | déduit | — | non | P3 6 | **PARTIEL** | extraction |

### AIDANT
| Champ | Coll. | Stock. | Moteurs | CERFA | Statut | 1er point de rupture |
|---|---|---|---|---|---|---|
| aidant principal (`aidant_nom`) | ✅ (whitelist) | ✅ | ✅ | P20 1/2 | **OK** | — |
| lien aidant | ✅ (déduit) | partiel | non | P20 3 | **PARTIEL** | — |
| épuisement aidant (`aidant_besoins`) | ✅ (whitelist) | ✅ | ✅ | texte | **OK/PARTIEL** | — |
| répit | ❌ | ❌ | non | F2 (cases, vide) | **INEXISTANT** | jamais collecté |
| aidants secondaires | ❌ | ❌ | non | ABSENT | **INEXISTANT** | n/a |

### PROJET
| Champ | Coll. | Stock. | Moteurs | CERFA | Statut | 1er point de rupture |
|---|---|---|---|---|---|---|
| projet professionnel (`projet_professionnel`) | ✅ (whitelist) | ✅ | ✅ | P16 | **OK** | — |
| souhait orientation (`projet_orientation`) | ✅ (whitelist) | ✅ | ✅ | P16 | **OK** | — |
| projet de vie | ❌ champ dédié (→ `texte_e` généré) | colonne dédiée | strength/evidence | P16 | **PARTIEL** (généré, pas collecté) | génération vs collecte |
| maintien domicile | ❌ (déduit `mode_vie`) | partiel | elig/cdaph (texte) | P5 6 (déduit) | **PARTIEL** | pas de champ dédié |

---

## 3. MATRICE DE MATURITÉ (synthèse)

| Couche | Champs sains (OK) | Champs cassés |
|---|---|---|
| **existe (défini)** | tous les NIVEAU A existent dans `collecte_schema` | lieu naissance, nationalité, CPAM, mutuelle, RSA, ménage, PPS, répit, aidants secondaires = **inexistants** |
| **collecté (demandé)** | base requise + NIVEAU A (requis=False) | requis=False ⇒ NIVEAU A peut ne pas être priorisé à la question |
| **persisté** | base requise, `droits_demandes`, scolaire, aidant_nom, projet_* | **TOUT le NIVEAU A non persisté** (whitelist) |
| **utilisé moteurs** | diagnostics, impact, droits_demandes, statut_emploi, scolaire, projet | genre, organisme_payeur, RSA, `droits.*`, `avq_*` (jamais lus en structuré) |
| **CERFA** | identité base, droits (texte), scolaire, aidant, projet | AVQ structuré (inerte), allocataire, organisme (vides), catégorie invalidité/taux IPP/mutuelle/ménage (absents) |

---

## 4. MODE AUDIT FACILIM

### CE QUI EST PROUVÉ
- **L'extraction est whitelistée et exclut tout le NIVEAU A** (`conversation_engine` L436-477, filtrage L530-537) — vérifié directement.
- **synthese_json = sortie de l'extraction whitelistée** (orchestration L484-508) — vérifié.
- Donc **Vague 1 et le fix anti-contamination `avq_*` sont inertes en flux réel** (données structurées jamais persistées).
- Les droits passent par le **texte** (`droits_demandes`, whitelisté) → CERFA + moteurs fonctionnent (OK).
- Les moteurs ne lisent **jamais** `genre`, `organisme_payeur`, `droits.*` (objet), ni les `avq_*` en structuré (exploration vérifiée sur échantillon).

### CE QUI EST DÉCLARÉ
- Les mappings CERFA détaillés (numéros de cases/lignes) proviennent d'une **exploration de code** (cerfa_filler/v2_bridge/field_mapper) ; le cœur (AVQ, identité P2, droits P17, v2_bridge) a été vérifié en main propre lors des sprints précédents, le reste est rapporté.
- `requis=False` sur le NIVEAU A : ces champs **peuvent ne pas être demandés en priorité** (selon `missing_fields`) — à confirmer en conversation réelle.

### CE QUI EST NON VÉRIFIÉ
- **`accident_travail`** : déclaré persisté par une exploration, mais **absent de la whitelist** que j'ai lue → chemin de persistance incertain (document extractor ? clé dérivée ?). À tracer.
- **`type_protection`** vs `protection_juridique` : mismatch de nommage collecte↔whitelist → persistance du type exact non garantie.
- Comportement **réel** (production) : non observé (données prod inaccessibles ; `railway ssh` bloqué, non contourné).
- Le **chemin document uploadé** (`document_functional_extractor` / `_document_knowledge`) pourrait alimenter certains champs hors whitelist — non tracé exhaustivement.

### TOP 20 CHAMPS LES PLUS CRITIQUES (impact MDPH/CERFA)
1. AVQ toilette 2. AVQ habillage 3. AVQ repas 4. AVQ déplacements 5. AVQ gestion administrative 6. pension_invalidite 7. catégorie invalidité 8. taux IPP 9. organisme_payeur (CAF/MSA) 10. numéro allocataire 11. droits.* (structuré) 12. prénom/nom_naissance 13. AAH 14. PCH 15. RQTH 16. CMI (×3) 17. orientation ESMS 18. type_protection 19. AESH/scolarité 20. projet de vie.

### TOP 20 CHAMPS PERDUS (collectés/demandés mais NON persistés — rupture = extraction)
1. `avq_toilette` 2. `avq_habillage` 3. `avq_repas` 4. `avq_deplacements` 5. `avq_gestion_quotidienne` 6. `prenom` 7. `nom_naissance` 8. `organisme_payeur` 9. `numero_allocataire` 10. `pension_invalidite` 11. `categorie_invalidite` 12. `maladie_professionnelle` 13. `taux_ipp` 14. objet `droits.*` 15. (`type_protection` — mismatch) … 16-20 : tous dérivés des 14 ci-dessus (cases AVQ CERFA, score PCH structuré, etc.).

### TOP 20 CHAMPS COLLECTÉS MAIS NON UTILISÉS
- `genre` (CERFA oui, **aucun moteur**), `enfants_a_charge` (peu exploité), `medecin_traitant` (preuve, peu décisionnel), `historique_mdph` (texte analyse seulement), `traitements` (preuve), `date_debut_limitations` (chrono), et — en l'état — **tous les NIVEAU A persistés seraient inutilisés par les moteurs** (qui lisent le texte, pas le structuré) tant que les moteurs ne sont pas branchés sur le structuré.

### TOP 20 CHAMPS ATTENDUS PAR LE CERFA MAIS ABSENTS (cases/champs jamais alimentés)
1. commune/lieu de naissance (P2) 2. nationalité (P2) 3. organisme d'assurance maladie/CPAM (P2) 4. numéro allocataire (P2 13, perdu) 5. organisme payeur (P2, perdu) 6. taux IPP (P6) 7. catégorie invalidité 8. ménage (B1 entretien) 9. répit aidant (F2) 10. aidants secondaires 11. PPS 12. GEVASCO 13. mutuelle/frais restant à charge (B1) 14-20 : cases AVQ P6 (vides en flux réel faute de `avq_*` persistés).

### RISQUE PILOTE ESSMS
Un professionnel collecte consciencieusement (l'agent **pose** les questions NIVEAU A) mais **les réponses disparaissent** : le CERFA ressort avec AVQ vides, allocataire/organisme vides, et des droits reposant sur le seul texte. **L'effort de collecte ne se traduit pas dans le dossier.** Pire ressenti possible que « champ vide » : « j'ai répondu et ça ne sert à rien ».

### GOULOT D'ÉTRANGLEMENT
**`conversation_engine._CHAMPS_EXTRACTIBLES_*` + l'appel `extract_structured_data_from_history(..., profil_mdph="inconnu")`.** Un seul verrou bloque la persistance de tout le NIVEAU A et neutralise Vague 1 + l'anti-contamination structurée.

### PROCHAIN SPRINT UNIQUE RECOMMANDÉ
**« ACTIVATION DE LA COLLECTE STRUCTURÉE » (1 fichier, fort levier) :**
1. Ajouter les champs NIVEAU A (`prenom`, `nom_naissance`, `organisme_payeur`, `numero_allocataire`, `pension_invalidite`, `categorie_invalidite`, `maladie_professionnelle`, `taux_ipp`, les 5 `avq_*`, et l'objet/clés `droits.*`) aux whitelists `_CHAMPS_EXTRACTIBLES_*`.
2. Passer le **vrai `profil_mdph`** à `extract_structured_data_from_history` (au lieu de `"inconnu"`).
3. Adapter le **prompt d'extraction** pour produire les niveaux AVQ (AUTONOME/DIFFICULTE/…) et l'objet `droits.*`.
4. QA : un dossier conversationnel réel doit faire apparaître `avq_*`/`droits.*`/`organisme_payeur` dans `synthese_json`, puis dans le CERFA.

> Ce sprint **active** rétroactivement Vague 1 **et** rend opérant le fix anti-contamination 7e04f89 (les `avq_*` arriveront enfin jusqu'aux cases). Sans lui, les deux sprints précédents restent inertes en production. *(Constat — aucune implémentation ici.)*

---

## 5. RÉPONSE AU CRITÈRE DE RÉUSSITE
- **Quelles données entrent ?** Base requise (identité, diagnostics, impact, droits texte, scolaire, aidant_nom, projet) + NIVEAU A **demandé**.
- **Quelles données disparaissent ?** Tout le NIVEAU A structuré (avq_*, droits.*, identité fine, administratif, invalidité) — à l'**extraction**.
- **Quelles données ne servent à rien ?** `genre` (aucun moteur) ; et tout NIVEAU A même si persisté (moteurs lisent le texte, pas le structuré).
- **Quelles données sont attendues par le CERFA mais absentes ?** AVQ (flux réel), allocataire/organisme, lieu naissance, nationalité, CPAM, taux IPP, catégorie invalidité, mutuelle, ménage, répit.
- **Quelles données bloquent réellement le pilote ESSMS ?** La rupture d'extraction : la collecte structurée ne se rend pas au dossier.

---

*Audit lecture seule. Aucune correction. Keystone (whitelist d'extraction) vérifié directement ; mappings CERFA et consommation moteurs issus d'exploration (cœur vérifié en propre). Production non observée.*
