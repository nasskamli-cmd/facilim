# COLLECTE_SCHEMA_IMPLEMENTATION_PLAN.md — Feuille de route d'implémentation

**Version :** plan v1 · **Généré le :** 2026-06-07
**Source cible :** `COLLECTE_CERFA_TARGET_SCHEMA.md` · **État du code :** audité (AUDIT_MODELE_COLLECTE_MDPH.md)
**Nature :** plan produit — **aucun code, aucune implémentation**.
**Boussole :** *Pilote ESSMS d'abord, production ensuite.* Respect de la pyramide FACILIM (N1 workflow/collecte/synthèse/visibilité/validation/CERFA → N2 cockpit/audit/reporting → N3 optimisation).

> **Insight structurant (réutilisation)** : le **CERFA V2 (`cerfa_filler`) et `field_mapper` consomment DÉJÀ** la plupart des champs cibles (cases AVQ P6/P7, `organisme_payeur`, `nationalite`, parsing droits, pension, AT/MP…). **Le chantier est donc surtout côté COLLECTE** (les rendre saisis/structurés), pas côté CERFA. Cela évite une réécriture massive.

---

## SECTION 1 — INVENTAIRE GLOBAL

| Domaine | Nombre de champs (cible) | Déjà collectés (agents actifs) |
|---|---|---|
| Identité | 16 | 5 (nom_prenom, date_naissance, adresse, tel, email) |
| Administratif (NIR, organismes, allocataire, dept, type demande, urgence, dossier existant, personne contact) | 9 | 3 (num_secu*, departement, type_dossier) |
| Protection juridique | 7 | 2 (type_protection, jugement — profil protégé) |
| Santé | 10 | 4 (diagnostics, traitements, medecin_traitant, date_debut) |
| AVQ | 13 | 0 (texte libre `impact_quotidien`) |
| PCH | 7 | 0 |
| Emploi / invalidité / AT-MP | 18 | 2 (statut_emploi, qualification_d) |
| Enfant / scolarité | 10 | 2 (situation_scolaire, etablissement) |
| Aidant | 10 | 1 (aidant_familial booléen, création) |
| Droits | 16 | 1 (droits_demandes texte unique) |
| Projet de vie | 8 | 1 (expression_directe texte) |
| **Total** | **~124** | **~21 réellement structurés** |

> ~17 % du schéma cible est aujourd'hui réellement collecté de façon structurée.

---

## SECTION 2 — PRIORISATION PILOTE

### NIVEAU A — BLOQUANT PILOTE (sans → dossier insuffisant / CERFA incomplet / risque MDPH)
- **Identité** : `nom_naissance`, `prenom` (séparés), `sexe`, `date_naissance`, `nir`, `adresse_complete`, `departement`.
- **Demande** : `type_demande`.
- **Santé** : `diagnostics`, `traitements` (+ narratif B existant).
- **AVQ structurés (cœur PCH/évaluation)** : `avq_toilette`, `avq_habillage`, `avq_repas`, `avq_mobilite`, `avq_deplacements_exterieur`.
- **Droits explicites** : objet `droits.*` (au moins AAH, PCH, RQTH, CMI, AEEH selon profil).
- **Protection** (si profil protégé) : `protection_type`, `representant_*`, `jugement_*`.
- **Enfant** (si profil enfant) : `representant_*`, `scolarite_*`, `aesh`, `pps`.
- **Invalidité / AT-MP** (si concerné) : `pension_invalidite`+`pension_categorie`, `at_mp`+`at_mp_taux_ipp`.

### NIVEAU B — IMPORTANT (forte valeur, pilote possible sans)
`pch_*` (aide humaine/technique/aménagements/transport), Section 10 **aidant** complète, `ressources_*`, emploi détaillé (`medecin_travail`, `limitations_professionnelles`, `orientation_pro_souhaitee`), scolarité fine (`gevasco`, `materiel_adapte`, `besoins_enfant`), `nationalite`, `organisme_payeur`/`numero_allocataire`, `projet_*` structuré, `composition_foyer`, `logement_statut`.

### NIVEAU C — CONFORT (post-pilote)
`nom_usage`, `mode_contact`, `commune_naissance`, `personne_contact_*`, `specialistes`, `hospitalisations`, `pch_charges_exceptionnelles`, `diplomes`/`niveau_scolaire`, `reconversion`, `aidant_soutien_psy`.

---

## SECTION 3 — DÉPENDANCES (par domaine)
Chaîne : **Collecte → Extraction → Synthèse → Cockpit → CERFA**.

| Domaine | Point d'ajout collecte | Extraction | Synthèse (`synthese_json`) | Cockpit / moteurs | CERFA |
|---|---|---|---|---|---|
| Identité fine | CHECKLIST agent + form création | prompt upload | nouveaux ids | faible | **déjà lu** (field_mapper P2) |
| AVQ | CHECKLIST agent (`avq_*`) | prompt upload (à étendre) | `avq_*` | cdaph/eligibilite (PCH) | **cases P6/P7 déjà mappées** |
| Droits `droits.*` | CHECKLIST Section E (cases) | — | objet `droits` | droits/cdaph (gros gain) | **P17/P18 déjà mappées** (via parsing → à brancher sur booléens) |
| Invalidité/AT-MP | CHECKLIST Section D | prompt upload | `pension_*`, `at_mp_*` | droits/cdaph | **déjà attendu** par cerfa_filler |
| Aidant | nouvelle Section F agent | — | `aidant_*` | cdaph | P19-20 |
| Protection | protected_agent (affiner) | — | `protection_type` fin | cockpit | A4 |

> **Conclusion dépendances** : le plus gros effort est **collecte + synthèse** ; l'aval (CERFA/cockpit) est **déjà prêt** pour la majorité des champs.

---

## SECTION 4 — LOTS D'IMPLÉMENTATION (vagues)

### VAGUE 1 — Pilote ESSMS viable (NIVEAU A)
**Objectif** : un dossier adulte/enfant complet sur les champs bloquants.
- **Champs** : identité fine (nom_naissance/prenom/sexe/nir), `type_demande`, **AVQ cœur** (5 champs `avq_level`), **`droits.*`** explicites, protection (si protégé), scolarité+aesh+pps (si enfant), invalidité/AT-MP de base.
- **Structures** : une **checklist unique** (fusion des 2 modèles) ; ajout des ids dans `synthese_json` ; objet `droits` ; enum `avq_level`.
- **Impacts** : agents (CHECKLIST), `synthese_json`, branchement `droits.*` → P17/P18, `avq_*` → P6/P7 (mapping déjà présent → adaptation lecture booléens/levels).
- **Hors périmètre V1** : PCH avancée, aidant complet, emploi détaillé, projet structuré.

### VAGUE 2 — Dossier MDPH robuste (NIVEAU B)
**Objectif** : qualité MDPH professionnelle.
- PCH avancée (`pch_*`), **aidants** (Section F complète + AVPF), invalidité/AT-MP détaillée (rente, IPP, catégorie), emploi détaillé (médecin du travail, limitations pro, orientation), ressources, scolarité fine (GEVASCO, matériel), `nationalite`/organismes/allocataire, projet de vie structuré.

### VAGUE 3 — Production complète (NIVEAU C)
**Objectif** : confort, enrichissement, automatisation.
- Champs confort (§14 N3), enrichissement extraction (multi-doc, GEVASCO parsé), automatisations (pré-cochage droits depuis éligibilité avec validation humaine), optimisation narratifs.

---

## SECTION 5 — MATRICE IMPACT

| Domaine | Collecte | Synthèse | Cockpit | CERFA | QA |
|---|---|---|---|---|---|
| Identité fine | moyen | faible | faible | **faible (déjà lu)** | faible |
| AVQ structurés | **fort** | moyen | moyen | faible (P6/P7 prêtes) | **fort** |
| Droits `droits.*` | **fort** | moyen | **fort** | moyen (P17/P18 prêtes) | **fort** |
| Invalidité/AT-MP | moyen | faible | moyen | faible (attendu) | moyen |
| Aidant | **fort** | moyen | moyen | moyen | moyen |
| PCH avancée | moyen | moyen | moyen | moyen | moyen |
| Emploi détaillé | moyen | faible | faible | faible | faible |
| Protection fine | faible | faible | faible | faible | faible |

> Les efforts **forts** sont concentrés sur **collecte AVQ + droits + aidant** (et leur QA). L'aval CERFA est majoritairement **faible** (déjà câblé).

---

## SECTION 6 — RISQUES

### Risques techniques
- **Régression collecte** : modifier la CHECKLIST des agents peut perturber le flux conversationnel (ordre des questions, is_complete). → couvrir par QA collecte + non-régression QA-PROD/QA-historiques.
- **Divergence d'ids** : tant que les 2 checklists coexistent, risque d'incohérence. → fusion en V1.
- **Mapping booléens droits / levels AVQ** : le mapper lit aujourd'hui du texte parsé ; brancher sur `droits.*`/`avq_*` demande une adaptation lecture (pas une réécriture).

### Risques métier
- **AVQ mal formulées** → mauvaise objectivation PCH. Exige une formulation FALC validée.
- **Pré-cochage droits** = risque d'orientation automatique (contraire à la philosophie « FACILIM éclaire »). → garder la **validation humaine** (jamais auto-cocher sans confirmation).

### Risques pilote
- Périmètre trop large en V1 → pilote retardé. → s'en tenir au NIVEAU A.
- Champs NIVEAU A manquants → dossiers insuffisants en pilote.

### Risques régression
- Toute modif des agents/synthese doit passer la non-régression existante (QA-PROD-1→5, QA-5/7/9/10/11, QA-FIX-TEST4-*).

---

## SECTION 7 — STRATÉGIE DE TEST (profils minimaux)

| Profil | Données minimales | Résultat attendu |
|---|---|---|
| Adulte réévaluation | identité fine + AVQ cœur + `droits.{aah,rqth}` | CERFA E coché, P6/P7 cohérents, complétude ↑ |
| Première demande adulte | idem + `type_demande=premiere` | P1 1 coché, dossier complet N1 |
| Enfant scolarisé | representant + scolarite + aesh/pps + `droits.{aeeh,pps}` | sections C remplies, AEEH coché |
| Invalidité catégorie 2 | `pension_invalidite=true`, `pension_categorie=2` | champ invalidité présent CERFA/cockpit |
| Accident du travail | `at_mp=accident_travail`, `at_mp_taux_ipp` | AT/MP structuré, cohérence D |
| PCH | AVQ complets + `pch_aide_humaine` | besoins PCH objectivés, P6/P7 |
| Aidant | Section F (`aidant_present`, aide, impact_pro) + `droits.avpf` | P19-20 remplies |
| Protection juridique | `protection_type` + representant + jugement | A4 rempli, cockpit cohérent |

---

## SECTION 8 — PLAN QA

- **QA-SCHEMA-1 (Structure)** : une seule checklist active ; `synthese_json` conforme aux ids du schéma ; aucun id dupliqué ; énums valides.
- **QA-SCHEMA-2 (Collecte)** : par profil minimal, les champs NIVEAU A sont demandés et capturés (collecte ne se clôt pas avant) ; AVQ/droits structurés présents en synthèse.
- **QA-SCHEMA-3 (Synthèse)** : chaque champ collecté apparaît dans `synthese_json` au bon id/type ; pas de perte (cf. audit traçabilité).
- **QA-SCHEMA-4 (Cockpit/moteurs)** : `droits.*`/`avq_*` consommés par eligibilite/cdaph (droits détectés non vides quand justifiés).
- **QA-SCHEMA-5 (CERFA)** : `droits.*` → P17/P18 ; `avq_*` → P6/P7 ; identité fine → P2 ; couverture N1 ↑ ; **non-régression** QA-6 (ghost fields=0, incompatibles=0).
- **Non-régression obligatoire** : QA-PROD-1→5, QA-5/7/9/10/11, QA-FIX-TEST4-COLLECTE/CERFA-V2.

---

## SECTION 9 — ESTIMATION

| Vague | Complexité | Risque | Valeur |
|---|---|---|---|
| Vague 1 (pilote viable, N-A) | Moyenne | Moyen (modif agents + synthèse) | **Très forte** (débloque le pilote) |
| Vague 2 (dossier robuste, N-B) | Moyenne-haute | Moyen | Forte |
| Vague 3 (production, N-C) | Variable | Faible | Moyenne |

---

## MODE AUDIT FACILIM

### CE QUI EXISTE DÉJÀ
Collecte core (identité base, diagnostics/traitements, impact texte, type_dossier, droits_demandes texte, scolarité minimale, protection minimale) ; narratifs B/C/D/E générés ; cockpit/gate/audit/historique (PROD-1→5) ; **CERFA V2 + field_mapper qui consomment déjà** AVQ/droits/organismes/nationalité/pension ; fix collecte déployé.

### CE QUI PEUT ÊTRE RÉUTILISÉ
- Le **mécanisme CHECKLIST** des agents (ajouter des ids).
- Le **prompt d'extraction** (étendre la whitelist).
- `synthese_json` (ajouter des clés).
- **L'aval CERFA/cockpit** : déjà prêt pour la majorité des champs cibles → **pas de réécriture CERFA**.
- Le filet `_COLONNES_PHASE3` (pattern pour garantir des colonnes).

### CE QUI DOIT ÊTRE AJOUTÉ
Une **checklist unique** ; les champs **AVQ structurés**, **`droits.*` explicites**, **invalidité/AT-MP**, **aidant (Section F)**, **identité fine** ; le branchement `droits.*`→P17/P18 et `avq_*`→P6/P7 (adaptation lecture).

### CE QUI NE DOIT PAS ÊTRE DÉVELOPPÉ
- Ne pas réécrire CERFA/cockpit/gate/audit/historique (faits).
- Ne pas conserver/étendre la **checklist parallèle** `conversation_engine` (à déprécier).
- Ne pas viser les 612 champs en V1 (seulement NIVEAU A).
- Ne pas auto-cocher les droits sans validation humaine.

### RISQUE PRINCIPAL
Élargir le périmètre V1 au-delà du NIVEAU A → pilote retardé et risque de régression sur le flux conversationnel.

### GOULOT D'ÉTRANGLEMENT
**La collecte structurée (AVQ + droits + aidant)** : tout le reste (aval) est prêt ; c'est la saisie/structuration qui manque.

### SPRINT UNIQUE RECOMMANDÉ
**VAGUE 1 — « Collecte NIVEAU A unifiée »** : une checklist unique + `avq_*` + `droits.*` + identité fine + invalidité de base, branchés bout-en-bout, avec QA-SCHEMA-1→5 sur les profils minimaux. Périmètre strictement NIVEAU A → pilote ESSMS viable sans réécriture.

### PREUVES ATTENDUES (fin Vague 1)
- Une seule checklist active (plus de modèle parallèle).
- `synthese_json` d'un dossier test : `avq_*` + `droits.*` + identité fine structurés.
- CERFA régénéré : P17/P18 depuis `droits.*`, P6/P7 depuis `avq_*`, P2 identité fine.
- QA-SCHEMA-1→5 PASS + non-régression PASS.
- Profils minimaux (adulte/enfant/invalidité/PCH/protection) produisant un dossier N1 complet.

---

## Réponse au critère de réussite
1. **Dans le pilote (Vague 1)** : NIVEAU A — identité fine, type demande, AVQ cœur, droits explicites, protection/scolarité/invalidité conditionnelles.
2. **Reporté** : PCH avancée, aidant complet, emploi détaillé, projet structuré (V2) ; confort (V3).
3. **Ordre** : Vague 1 (N-A) → Vague 2 (N-B) → Vague 3 (N-C).
4. **Impacts** : surtout collecte + synthèse ; aval CERFA/cockpit majoritairement faible (déjà câblé) — cf. §5.
5. **Tests** : QA-SCHEMA-1→5 par profil minimal + non-régression (§7-§8).
6. **Éviter la réécriture massive** : réutiliser l'aval existant, étendre la checklist plutôt que refondre, livrer par vagues NIVEAU A→B→C.

*Plan uniquement. Aucun fichier de code modifié, aucun agent/prompt/CERFA/moteur touché, aucun déploiement.*
