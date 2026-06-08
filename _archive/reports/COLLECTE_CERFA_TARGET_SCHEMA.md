# COLLECTE_CERFA_TARGET_SCHEMA.md — Schéma cible unique de collecte FACILIM

**Version :** cible v1 (conception) · **Généré le :** 2026-06-07
**Statut :** document de référence — **source de vérité unique** pour toute collecte future.
**Nature :** conception seule. Aucun code, aucun moteur, aucun déploiement.
**Méthode :** part du **CERFA 15692\*01**, remonte CERFA ← cockpit ← moteurs ← synthèse ← collecte.

> Convention : chaque champ a un **id canonique** (snake_case), un **type**, un **niveau** (Obligatoire / Recommandé / Facultatif), et des **consommateurs** (CERFA, cockpit, droits, CDAPH, audit). **Un champ = un id = une vérité**, utilisé identiquement par la collecte, la synthèse, le cockpit, les moteurs et le CERFA.

---

## SECTION 1 — PRINCIPES D'ARCHITECTURE

1. **Une seule checklist** (`COLLECTE_SCHEMA`) pilote la collecte conversationnelle, ET sert de schéma de `synthese_json`, ET de contrat d'entrée des moteurs/cockpit/CERFA. Fin des deux modèles parallèles (`conversation_engine.CHECKLIST_MDPH` vs agents).
2. **Une seule structure de données** : `synthese_json` suit exactement les ids du schéma (pas de clés ad hoc, pas d'alias).
3. **Source de vérité unique** : tout consommateur (CERFA mapper, cockpit, eligibilite/cdaph) lit les **mêmes ids**. Aucun consommateur ne lit un champ qui n'existe pas dans le schéma.
4. **Interdits structurels** :
   - ❌ modèles parallèles / checklists divergentes ;
   - ❌ champs dupliqués (`num_secu` vs `numero_securite_sociale`, `departement` vs `departement_code`…) → **un seul id canonique** + alias dépréciés en migration ;
   - ❌ texte libre là où un champ structuré est nécessaire (AVQ, droits, invalidité, protection) ;
   - ❌ champ consommé par le CERFA sans champ de collecte correspondant.
5. **Champs structurés typés** : enum fermées quand le CERFA a des cases (sexe, type de demande, AVQ, droits, catégorie invalidité, protection). Le texte libre est réservé aux **narratifs** (projet de vie, expression directe) — qui restent des champs distincts, jamais le réceptacle de données structurables.
6. **Profil + conditions** : sections activées par `profil` (adulte/enfant/protégé/mixte) et par qualifications (`section_d_active`, `section_f_active`…). Un champ non applicable = `non_concerne`, jamais vide ambigu.

### Types de champ normalisés
`text` · `text_long` (narratif) · `date` · `bool` · `enum(...)` · `list[enum]` · `int` · `avq_level` = enum(`autonome` | `difficulte` | `aide_partielle` | `aide_totale` | `non_concerne`).

---

## SECTION 2 — MATRICE CERFA → COLLECTE (champs structurants)

| Section CERFA | Champ CERFA | id collecte | Type | Niveau | Consommateurs |
|---|---|---|---|---|---|
| A1 | Type de demande | `type_demande` | enum(premiere, reevaluation, renouvellement, situation_changee) | Obligatoire | CERFA, audit |
| A1 | Dossier MDPH existant | `numero_dossier_mdph` | text | Reco. | CERFA |
| A1 | Département MDPH | `departement` | text | Obligatoire | CERFA, cockpit |
| A1 | Urgence | `urgence` | bool + `urgence_motif` text | Reco. | CERFA(P3), cdaph |
| A2 | Nom de naissance | `nom_naissance` | text | Obligatoire | CERFA |
| A2 | Nom d'usage | `nom_usage` | text | Facultatif | CERFA |
| A2 | Prénom(s) | `prenom` | text | Obligatoire | CERFA, cockpit |
| A2 | Sexe | `sexe` | enum(homme, femme) | Obligatoire | CERFA |
| A2 | Date de naissance | `date_naissance` | date | Obligatoire | CERFA, profil, cockpit |
| A2 | Commune/pays naissance | `commune_naissance`, `pays_naissance` | text | Reco. | CERFA |
| A2 | Nationalité | `nationalite` | enum(francaise, eee_suisse, autre) | Obligatoire | CERFA |
| A2 | Adresse complète | `adresse_complete`, `code_postal`, `commune`, `pays` | text | Obligatoire | CERFA, cockpit |
| A2 | Téléphone / email | `telephone`, `email` | text | Obligatoire | CERFA, envoi |
| A2 | Mode de contact souhaité | `mode_contact` | enum(email, telephone, sms, courrier) | Reco. | CERFA |
| A | NIR | `nir` | text(15) | Obligatoire | CERFA, droits |
| A | Organisme assurance maladie | `organisme_assurance_maladie` | enum(cpam, msa, autre) | Reco. | CERFA |
| A | Organisme payeur prestations | `organisme_payeur` | enum(caf, msa, aucun) | Reco. | CERFA, droits |
| A | Numéro allocataire | `numero_allocataire` | text | Reco. | CERFA |
| A | Personne à contacter | `personne_contact_nom`, `_lien`, `_tel` | text | Facultatif | CERFA |
| A | Aidé dans les démarches | `aide_demarches` | bool | Facultatif | CERFA |
| A4 | Protection juridique | `protection_type` | enum(aucune, tutelle, curatelle_simple, curatelle_renforcee, habilitation_familiale, sauvegarde) | Obligatoire(si protégé) | CERFA, cockpit, cdaph |
| A4 | Représentant légal | `representant_*` (cf. §4) | text | Obligatoire(si protégé) | CERFA |
| B | Situation logement | `logement_statut` | enum(proprietaire, locataire, heberge, etablissement) | Obligatoire | CERFA(P5) |
| B | Vit seul/couple/famille | `composition_foyer` | enum(seul, couple, famille, etablissement) | Reco. | CERFA, cdaph |
| B | Ressources / RSA / AAH perçue / pension | `ressources_*` (cf. §8) | structuré | Reco. | CERFA, droits |
| B | AVQ | `avq_*` (cf. §6) | avq_level | Obligatoire(adulte) | CERFA(P6/P7), cockpit, droits(PCH), cdaph |
| B | Aides techniques / aménagements | `pch_*` (cf. §7) | structuré | Reco. | CERFA, droits(PCH) |
| B (texte) | Difficultés vie quotidienne | `texte_b_vie_quotidienne` | text_long (narratif) | Auto (généré) | CERFA(P8) |
| C | Scolarité enfant | `scolarite_*` (cf. §9) | structuré | Obligatoire(enfant) | CERFA(P9-12), droits(AEEH/PPS) |
| D | Emploi / invalidité / AT-MP | `emploi_*`, `invalidite_*`, `at_mp_*` (cf. §8) | structuré | Reco.(adulte) | CERFA(P13-18), droits(RQTH/AAH) |
| E | Droits demandés | `droits.*` (cf. §11) | bool par droit | Obligatoire | CERFA(P17/P18), droits, cockpit, cdaph |
| E | Projet de vie | `projet_*` (cf. §12) | text_long + enums | Reco. | CERFA(P16), cdaph |
| F | Aidant | `aidant_*` (cf. §10) | structuré | Conditionnel | CERFA(P19-20), droits(AVPF), cdaph |

---

## SECTION 3 — IDENTITÉ

| id | Type | Niveau |
|---|---|---|
| `nom_naissance` | text | **Obligatoire** |
| `nom_usage` | text | Facultatif |
| `prenom` | text | **Obligatoire** |
| `sexe` | enum(homme, femme) | **Obligatoire** |
| `date_naissance` | date | **Obligatoire** |
| `commune_naissance`, `pays_naissance` | text | Recommandé |
| `nationalite` | enum(francaise, eee_suisse, autre) | **Obligatoire** |
| `adresse_complete`, `code_postal`, `commune`, `pays` | text | **Obligatoire** |
| `telephone` | text | **Obligatoire** |
| `email` | text | **Obligatoire** (envoi) |
| `mode_contact` | enum(email, telephone, sms, courrier) | Recommandé |
| `nir` | text(15) | **Obligatoire** |
| `organisme_assurance_maladie` | enum(cpam, msa, autre) | Recommandé |
| `organisme_payeur` | enum(caf, msa, aucun) | Recommandé |
| `numero_allocataire` | text | Recommandé |
| `departement` | text | **Obligatoire** |

> **Règle prénom/nom** : collecte **séparée** `nom_naissance` + `prenom` (ne plus dériver d'un champ unique `nom_prenom`). Supprime la perte « Karim ».

---

## SECTION 4 — PROTECTION JURIDIQUE (activée si majeur protégé)

| id | Type | Niveau |
|---|---|---|
| `protection_type` | enum(aucune, tutelle, curatelle_simple, curatelle_renforcee, habilitation_familiale, sauvegarde_justice) | **Obligatoire** (si protégé) |
| `representant_nom`, `representant_prenom` | text | **Obligatoire** (si protégé) |
| `representant_qualite` | enum(tuteur, curateur, mandataire, parent) | **Obligatoire** (si protégé) |
| `representant_adresse`, `representant_tel`, `representant_email` | text | Recommandé |
| `jugement_tribunal`, `jugement_date` | text/date | **Obligatoire** (si protégé) |
| `jugement_a_joindre` | bool | Recommandé |

---

## SECTION 5 — SANTÉ

| id | Type | Niveau |
|---|---|---|
| `diagnostics` | list[text] | **Obligatoire** |
| `traitements` | list[text] | **Obligatoire** |
| `medecin_traitant_nom`, `_ville` | text | Recommandé |
| `specialistes` | list[text] | Facultatif |
| `hospitalisations` | text_long | Facultatif |
| `douleurs` | bool + `douleurs_detail` text | Recommandé |
| `fatigabilite` | enum(non, legere, importante, invalidante) | Recommandé |
| `troubles_cognitifs` | bool + detail | Recommandé |
| `troubles_psychiques` | bool + detail | Recommandé |
| `date_debut_limitations` | date/text | Recommandé |

---

## SECTION 6 — ACTIVITÉS DE VIE QUOTIDIENNE (AVQ) — **structuré, jamais texte libre**

Chaque AVQ = un champ `avq_level` ∈ {autonome, difficulte, aide_partielle, aide_totale, non_concerne} (+ `*_detail` text optionnel).

| id | Niveau |
|---|---|
| `avq_toilette` | **Obligatoire** (adulte) |
| `avq_habillage` | **Obligatoire** |
| `avq_repas` (préparation + prise) | **Obligatoire** |
| `avq_mobilite` (marche/intérieur) | **Obligatoire** |
| `avq_transferts` | Recommandé |
| `avq_deplacements_exterieur` | **Obligatoire** |
| `avq_courses` | Recommandé |
| `avq_menage` | Recommandé |
| `avq_gestion_budget` | Recommandé |
| `avq_gestion_administrative` | Recommandé |
| `avq_communication` | Recommandé |
| `avq_orientation` (spatio-temporelle) | Recommandé |
| `avq_securite` | Recommandé |

> Le narratif B (`texte_b_vie_quotidienne`) est **généré à partir** de ces champs structurés, et non l'inverse.

---

## SECTION 7 — PCH (données structurées)

| id | Type | Niveau |
|---|---|---|
| `pch_aide_humaine` | bool + `pch_aide_humaine_heures` int + detail | Reco.(si PCH) |
| `pch_aide_technique` | bool + `pch_aide_technique_detail` text | Reco. |
| `pch_amenagement_logement` | bool + detail | Reco. |
| `pch_amenagement_vehicule` | bool + detail | Reco. |
| `pch_transport` | bool + detail | Reco. |
| `pch_charges_specifiques` | bool + detail | Facultatif |
| `pch_charges_exceptionnelles` | bool + detail | Facultatif |

---

## SECTION 8 — EMPLOI / ORIENTATION / INVALIDITÉ / AT-MP

| id | Type | Niveau |
|---|---|---|
| `emploi_statut` | enum(emploi, chomage, inactif, esat, retraite, etudiant) | Reco.(adulte) |
| `emploi_employeur`, `emploi_contrat` | text/enum | Facultatif |
| `emploi_temps` | enum(plein, partiel) | Facultatif |
| `arret_travail` | bool + `arret_motif` | Reco. |
| `at_mp` | enum(non, accident_travail, maladie_pro) | **Obligatoire si concerné** |
| `at_mp_rente` | bool + `at_mp_taux_ipp` int | Reco.(si AT/MP) |
| `pension_invalidite` | bool | Reco. |
| `pension_categorie` | enum(1, 2, 3) | **Obligatoire si pension** |
| `medecin_travail` | text | Reco.(si emploi) |
| `cap_emploi`, `france_travail`, `mission_locale` | bool | Facultatif |
| `orientation_pro_souhaitee` | enum(milieu_ordinaire, esat, crp_cpo_ueros, formation, aucune) | Reco. |
| `formation_actuelle`, `reconversion` | text | Facultatif |
| `niveau_scolaire`, `diplomes` | text | Facultatif |
| `limitations_professionnelles` | text_long | Reco.(si RQTH) |
| `besoin_amenagement_poste`, `maintien_emploi` | bool + detail | Reco. |

---

## SECTION 9 — ENFANT / SCOLARITÉ (activée si profil enfant)

| id | Type | Niveau |
|---|---|---|
| `scolarite_etablissement`, `scolarite_classe` | text | **Obligatoire** (enfant) |
| `scolarite_type` | enum(ordinaire, ulis, ime, itep, autre) | **Obligatoire** |
| `aesh` | enum(aucune, mutualisee, individuelle) + heures int | Reco. |
| `pps` | bool | Reco. |
| `gevasco` | bool (à joindre) | Reco. |
| `materiel_adapte` | bool + detail | Facultatif |
| `transport_scolaire` | bool | Facultatif |
| `orientation_scolaire_souhaitee` | enum(ordinaire, ulis, esms, autre) | Reco. |
| `esms_enfant` | bool + detail | Reco. |
| `besoins_enfant` (apprentissages, communication, hygiène, repas, déplacement) | avq_level (par item) | Reco. |

---

## SECTION 10 — AIDANTS (activée si `aidant_present`)

| id | Type | Niveau |
|---|---|---|
| `aidant_present` | bool | **Obligatoire** (qualification) |
| `aidant_nom`, `aidant_lien` | text/enum | Cond. |
| `aidant_cohabitation` | bool | Cond. |
| `aidant_aide_nature` | list[enum](hygiene, repas, deplacements, administrative, financiere, surveillance, coordination) | Cond. |
| `aidant_frequence` | enum(quotidienne, hebdo, ponctuelle) | Cond. |
| `aidant_impact_pro` | enum(aucun, reduction, arret) | Reco. |
| `aidant_epuisement` | bool | Reco. |
| `aidant_besoin_repit` | bool | Reco. |
| `aidant_soutien_psy` | bool | Facultatif |
| `aidant_avpf` | bool | Reco. |

---

## SECTION 11 — DROITS DEMANDÉS — **structure explicite, fin du champ texte unique**

Objet `droits` = un **booléen par droit** (+ sous-champ détail si pertinent) :

| id | Type | Profils |
|---|---|---|
| `droits.aah` | bool | adulte |
| `droits.aah_complement` | bool | adulte |
| `droits.pch` | bool | adulte/enfant |
| `droits.cmi_invalidite` | bool | tous |
| `droits.cmi_priorite` | bool | tous |
| `droits.cmi_stationnement` | bool | tous |
| `droits.rqth` | bool | adulte |
| `droits.orientation_pro` | bool | adulte |
| `droits.esat` | bool | adulte |
| `droits.crp_cpo_ueros` | bool | adulte |
| `droits.orientation_esms_adulte` | bool | adulte |
| `droits.aeeh` | bool | enfant |
| `droits.aeeh_complement` | bool | enfant |
| `droits.pps` | bool | enfant |
| `droits.avpf` | bool | aidant |
| `droits.actp_acfp_renouvellement` | bool | renouvellement |
| `droits.autres` | text | tous |

> Remplace `droits_demandes` (texte parsé au mot-clé) → **collecte explicite case par case**, directement mappable P17/P18 et lisible par les moteurs droits/CDAPH.

---

## SECTION 12 — PROJET DE VIE

| id | Type | Niveau |
|---|---|---|
| `projet_objectif_principal` | text_long | Recommandé |
| `projet_souhaits` | text_long | Recommandé |
| `projet_contraintes` | text_long | Facultatif |
| `projet_professionnel` | text_long | Reco.(adulte) |
| `projet_scolaire` | text_long | Reco.(enfant) |
| `projet_autonomie` | text_long | Recommandé |
| `projet_besoins_accompagnement` | list[enum] + detail | Recommandé |
| `texte_e_projet_vie` | text_long (généré) | Auto |

---

## SECTION 13 — MATRICE PROFILS (champs spécifiques cibles)

| Profil | Champs spécifiques (en plus du tronc identité+santé+AVQ+droits) |
|---|---|
| Adulte | composition_foyer, emploi_*, ressources_*, projet_professionnel |
| Enfant | representant_*, scolarite_*, aesh, pps, gevasco, besoins_enfant, droits.aeeh* |
| Aidant | aidant_present + Section 10 complète, droits.avpf |
| Curatelle / tutelle | protection_type (simple/renforcée), representant_*, jugement_* |
| Habilitation familiale | protection_type=habilitation_familiale, representant_*, jugement_* |
| Invalidité cat. 2 | pension_invalidite, pension_categorie=2, ressources_* |
| Accident du travail | at_mp=accident_travail, at_mp_rente, at_mp_taux_ipp, medecin_travail |
| Maladie professionnelle | at_mp=maladie_pro, at_mp_taux_ipp |
| PCH | AVQ complets + pch_* (aide humaine/technique/aménagements/transport) |
| RQTH | emploi_*, limitations_professionnelles, medecin_travail, droits.rqth |
| ESMS | orientation_esms_adulte / esms_enfant, droits.orientation_esms_* |

---

## SECTION 14 — PRIORISATION PILOTE ESSMS

### NIVEAU 1 — BLOQUANT PILOTE (dossier insuffisant sans)
Identité complète (`nom_naissance`, `prenom`, `sexe`, `date_naissance`, `nir`, `adresse_complete`, `departement`), `type_demande`, **AVQ structurés** (`avq_toilette/habillage/repas/mobilite/deplacements_exterieur`), **`droits.*`** (au moins un droit explicite), `diagnostics`, `impact`/narratif B, `protection_type` (si protégé), `scolarite_*` (si enfant).

### NIVEAU 2 — IMPORTANT (améliore fortement)
`pension_invalidite`+`pension_categorie`, `at_mp`+`taux_ipp`, `pch_*`, `ressources_*`, `aesh`/`pps`/`gevasco` (enfant), `limitations_professionnelles`, `projet_*`, `organisme_payeur`/`numero_allocataire`, Section 10 aidant.

### NIVEAU 3 — CONFORT (non bloquant)
`specialistes`, `hospitalisations`, `nom_usage`, `mode_contact`, `personne_contact_*`, `pch_charges_exceptionnelles`, diplômes/niveau scolaire.

---

## SECTION 15 — PLAN DE MIGRATION (description, sans coder)

```
Modèle actuel (2 checklists divergentes, champs texte libre)
        ↓
Modèle cible (1 schéma structuré aligné CERFA)
```

- **Champs à AJOUTER** : `nom_naissance`, `prenom` (séparé), `sexe` (saisie), `commune_naissance`, `nationalite`, `mode_contact`, `organisme_assurance_maladie`, `organisme_payeur`, `numero_allocataire` (collecte agent), tous les `avq_*`, tous les `pch_*`, `pension_invalidite`/`pension_categorie`, `at_mp*`/`taux_ipp`, `protection_type` fin, Section 9 enfant détaillée, Section 10 aidant, objet `droits.*` explicite, `projet_*`.
- **Champs à RESTRUCTURER** : `impact_quotidien` (texte) → dérivé/éclaté en `avq_*` (le texte devient narratif généré) ; `droits_demandes` (texte) → `droits.*` (booléens) ; `nom_prenom` → `nom_naissance` + `prenom` ; `type_dossier` → `type_demande`.
- **Champs à FUSIONNER (dédup)** : `num_secu`/`numero_securite_sociale` → `nir` ; `departement`/`departement_code` → `departement` ; les deux checklists (`conversation_engine.CHECKLIST_MDPH` + agents) → **une seule**.
- **Champs à SUPPRIMER / déprécier** : la `CHECKLIST_MDPH` de `conversation_engine` (inutilisée) ; les alias dupliqués après migration.
- **Branchement** : le schéma unique alimente `synthese_json` ; CERFA mapper, cockpit, eligibilite/cdaph lisent les **mêmes ids** → plus de « attendu CERFA non collecté » ni « collecté non structuré ».

---

## MODE AUDIT FACILIM

### CE QUI EXISTE DÉJÀ
Identité de base (`nom_prenom`, `date_naissance`, `telephone`, `email`, `departement`), `num_secu` (souvent vide), `diagnostics`, `traitements`, `impact_quotidien` (texte), `historique_mdph`, `type_dossier`, `droits_demandes` (texte), enfant (`situation_scolaire`, `etablissement_scolaire`, `representant_*`), protégé (`type_protection`, `jugement_tribunal`), narratifs B/C/D/E générés.

### CE QUI MANQUE
Identité fine (nom de naissance, sexe-saisie, commune/nationalité, mode contact, organismes/allocataire), **AVQ structurés**, **PCH structuré**, **invalidité/AT-MP/IPP**, **droits explicites par droit**, scolarité fine (AESH/PPS/GEVASCO/AEEH), **Section F aidant**, projet de vie structuré.

### CE QUI EST REDONDANT
Deux checklists (`conversation_engine` vs agents) ; doublons d'ids (`num_secu`/`numero_securite_sociale`, `departement`/`departement_code`) ; champs définis-non-utilisés (`numero_allocataire`, `organisme_payeur`, `projet_orientation`, `statut_occupation`).

### RISQUE PRINCIPAL
Continuer à corriger **champ par champ** sans schéma unique → dette permanente, CERFA toujours incomplet par profil, impossibilité de garantir un dossier MDPH complet en pilote.

### GOULOT D'ÉTRANGLEMENT
**Le schéma de collecte** : tant qu'il n'est pas unifié et structuré (AVQ/droits/invalidité), aucun consommateur aval (cockpit, moteurs, CERFA) ne peut produire un dossier complet.

### SPRINT UNIQUE RECOMMANDÉ
**« Schéma de collecte unique aligné CERFA 15692 »** : implémenter `COLLECTE_SCHEMA` (ce document) comme **unique** checklist + structure `synthese_json`, brancher collecte → cockpit → moteurs → CERFA sur les mêmes ids, structurer AVQ + droits + invalidité, supprimer la checklist parallèle. Un seul chantier structurant — pas de correctifs ponctuels.

### PREUVES ATTENDUES (à la livraison du sprint)
- Une seule checklist référencée par les agents (plus de modèle parallèle).
- `synthese_json` d'un dossier test contenant `avq_*`, `droits.*`, `pension_*`/`at_mp_*` structurés.
- CERFA régénéré : page E cochée depuis `droits.*`, cases P6/P7 depuis `avq_*`.
- Matrice CERFA→collecte sans case « attendu non collecté » sur les champs NIVEAU 1.
- Couverture pilote : profils PCH, invalidité cat. 2, ESMS, aidant passent de ❌ à ✅.

---

*Conception uniquement. Aucun fichier de code modifié, aucun moteur, aucun prompt, aucun CERFA, aucun déploiement. Ce document est la référence cible des futurs développements de collecte.*
