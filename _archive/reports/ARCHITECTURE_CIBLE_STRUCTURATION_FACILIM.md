# ARCHITECTURE CIBLE DE STRUCTURATION FACILIM

**Généré le :** 2026-06-07
**Nature :** architecture de référence (conception). **Aucun code, aucune modification produit, aucun patch, aucun nouveau moteur.**
**But :** transformer toute information **comprise** (WhatsApp, documents, bilans, évaluations) en **faits structurés traçables, validables, réutilisables** — sans dépendre du texte libre.

**Exemples cibles** (question centrale) :
« Suivi par le Dr COLLOMBARD » · « Fatigabilité importante » · « Projet ESAT » · « Besoin d'aide pour le ménage » · « Absent régulièrement pour raison de santé » → 5 **faits structurés** (voir §MODÈLE).

---

## DOMAINES (21) — faits observables / champs structurés / origine / preuve

| Domaine | Faits observables (ex.) | Champs structurés (ex.) | Origine possible | Preuve attendue |
|---|---|---|---|---|
| Identité | nom, prénom, naissance, sexe | `nom`, `prenom`, `date_naissance`, `sexe` | pièce identité, bilan, WA, pro | citation document/usager |
| Coordonnées | adresse, tel, email | `adresse`, `cp`, `commune`, `telephone`, `email` | WA, doc, pro | déclaration/document |
| Administratif | NIR, organisme payeur, n° allocataire, dossier MDPH | `nir`, `organisme_payeur`, `numero_allocataire`, `numero_dossier_mdph` | attestation, WA, doc | pièce justificative |
| Situation familiale | situation, enfants à charge | `situation_familiale`, `enfants_a_charge` | WA, doc | déclaration |
| Logement | type, hébergement | `type_logement`, `hebergement` | WA | déclaration |
| Professionnels de santé | psychiatre, psychologue, médecin, AS | `intervenant{role,nom}` (liste) | bilan, certificat | nom cité dans document |
| Diagnostics | pathologies | `diagnostic{libelle}` (liste) | certificat médical, bilan | mention médicale |
| Traitements | médicaments, soins | `traitement{libelle}` | certificat, WA | mention |
| Limitations | restrictions fonctionnelles | `limitation{type,intensite}` | bilan, WA | citation |
| AVQ | toilette/habillage/repas/ménage | `avq_{acte}` = niveau (AUTONOME…AIDE_TOTALE) | WA, bilan | déclaration/observation |
| Mobilité | déplacements int./ext., transports | `mobilite_{int,ext}`, `transports` | WA, bilan | déclaration |
| Communication | expression, compréhension | `communication_{oral,ecrit}` | bilan | observation |
| Cognition | mémoire, apprentissage, organisation | `cognition_{memoire,apprentissage}` | bilan | observation |
| Comportement | propos inadaptés, collectif, règles | `comportement{trait,impact}` | bilan | citation |
| Emploi | statut, parcours, absences | `statut_emploi`, `absences_sante`(bool/contexte) | bilan, WA | citation |
| Formation | en cours/visée | `formation{intitule,organisme}` | bilan, WA | mention |
| Ressources | pension invalidité, RSA, revenus | `pension_invalidite`, `categorie_invalidite`, `ressource{type}` | WA, doc | attestation |
| Droits | AAH, PCH, RQTH, CMI | `droit{code,demande:bool}` | WA, pro | demande explicite |
| Aidants | aidant principal, besoins, répit | `aidant{role,nom,besoins}` | WA, doc | déclaration |
| Projet de vie | aspirations, maintien domicile | `projet_vie{libelle}` | WA, bilan | expression usager |
| Orientation | ESAT/ESMS cible, structure | `orientation{type,structure}` | WA, doc | « ils peuvent me prendre » |
| Environnement | aides techniques, aménagements | `aide_technique{type}` | WA, doc | déclaration |

---

## MODÈLE DE FAIT UNIQUE FACILIM

```json
{
  "domaine": "Professionnels de santé",
  "champ": "intervenant.psychiatre",
  "valeur": "Dr COLLOMBARD",
  "source": "bilan BFP AIT ABBAS",
  "citation": "accompagnement par Mme COLLOMBARD la psychiatre",
  "confiance": "forte",
  "validation_professionnel": false,
  "validation_personne": false
}
```

Les 5 exemples cibles, structurés :
| Fait brut | domaine | champ | valeur |
|---|---|---|---|
| Suivi Dr COLLOMBARD | Professionnels de santé | `intervenant.psychiatre` | "Dr COLLOMBARD" |
| Fatigabilité importante | Limitations | `fatigabilite.intensite` | "importante" |
| Projet ESAT | Orientation | `orientation.type` | "ESAT" |
| Besoin d'aide ménage | AVQ | `avq_gestion_quotidienne` | "AIDE_PARTIELLE" |
| Absent pour raison de santé | Emploi | `absences_sante` | true (+ contexte) |

> Chaque fait porte **source + citation + confiance + double validation**. Le **texte libre** (bilan, narratif) devient **preuve attachée**, jamais la donnée elle-même.

---

## RÈGLES DE FUSION

**Interdits** : « premier écrivain gagne », écrasement silencieux, suppression de valeur.
**Mécanismes** :
- **Enrichissement** : une nouvelle source ajoute un fait absent (ex. WhatsApp complète l'administratif d'un bilan).
- **Correction** : une source plus fiable/récente **propose** une nouvelle valeur → l'ancienne est **conservée en historique** (jamais supprimée).
- **Conflit** : deux valeurs divergentes → **les deux coexistent** (chacune avec source/confiance) + **signalement** pour validation humaine.
- **Historique** : chaque fait garde ses versions (valeur, source, date, statut).
- **Priorité (suggestion, non écrasement)** : preuve documentaire/pro > déclaratif vague pour Santé/Identité ; parole de l'usager prioritaire pour Projet de vie / orientation souhaitée.

---

## TRAÇABILITÉ
```
SOURCE (citation) → FAIT STRUCTURÉ {source, citation, confiance}
   → SYNTHÈSE (agrégation de faits validés)
   → COCKPIT (affiche faits + statut + origine)
   → CERFA (chaque champ/case = un fait tracé)
```
Règle : **aucun fait sans source + citation** ; **aucun champ CERFA sans fait tracé**. Toute information répond à : d'où vient-elle ? qui l'a dite ? quel document ? validée ? où utilisée ?

---

## VALIDATION HUMAINE (états)
`extrait` → `proposé` → `validé_professionnel` → `validé_personne` → (`rejeté`).
- Le CERFA n'utilise que des faits **≥ validé_professionnel** (idéalement `validé_personne`).
- Aucune transmission sans relecture humaine (gate existant conservé).

---

## IMPACT SUR synthese_json
`synthese_json` devient (ou héberge) un **registre de faits** (`faits[]`) en plus des champs legacy. Transition **non cassante** : les champs legacy restent dérivables des faits validés. La source de vérité = **les faits**, plus le texte libre.

## IMPACT SUR LE COCKPIT
Le cockpit affiche **par domaine** les faits + leur **statut de validation** + leur **origine** ; les scores se calculent sur des **faits**, pas du texte. Complétude = couverture des domaines par des faits validés (remplace le barème de 12 champs).

## IMPACT SUR LE CERFA
Chaque champ/case CERFA est alimenté par un **fait validé tracé** (identité, AVQ, droits, orientation…). Plus de dépendance au narratif ; le narratif devient une **mise en forme** de faits (déjà acté : narratif ≠ preuve).

---

## CE QUI EXISTE / CÂBLÉ / UTILISÉ / MANQUE

| | État |
|---|---|
| **Existe & câblé** | `synthese_json` (point de convergence) ; extraction WhatsApp (whitelist) ; extraction document (admin limitée) + `_document_knowledge` (texte) ; `evidence_engine` (origine taguée Narratif/Déclaration/Document) ; gate de validation humaine ; instrumentation `[TRACE_*]`. |
| **Utilisé** | champs structurés base (identité, droits texte, avq_* si présents) + texte (impact, _document_knowledge). |
| **MANQUE (le cœur)** | (1) un **modèle de fait unique** {source, citation, confiance, validation} ; (2) une **structuration** convertissant le texte compris (santé/professionnels/AVQ/projet) en faits ; (3) des **règles de fusion** sans écrasement ; (4) la **traçabilité par fait** de bout en bout ; (5) les **états de validation** par fait. |

---

## PLAN DE MIGRATION (conceptuel, non-cassant)
1. **Introduire le modèle de fait** à côté de `synthese_json` (additif, zéro régression).
2. **Brancher les extractions** (WhatsApp + document) pour qu'elles **émettent des faits** (en priorité Santé/Professionnels/AVQ/Limitations/Orientation), tout en gardant les champs legacy.
3. **Cockpit & CERFA lisent les faits validés** avec **repli** sur le legacy tant que la couverture monte.
4. **Validation humaine** : exposer les faits `proposé` au professionnel ; CERFA consomme les `validé`.
5. **Déprécier** progressivement les silos texte (`_document_knowledge` brut) une fois la couverture suffisante.
Chaque étape **mesurable** (harnais de traçabilité de faits : taux source→fait→validé→CERFA).

---

## RISQUES
- **Double source de vérité** pendant la transition (faits vs legacy) → discipline de dérivation.
- **Fiabilité de l'extraction LLM** en faits structurés (à mesurer, pas supposer).
- **Sur-structuration** (créer des champs jamais utilisés) → se limiter aux faits exploités aval.
- **Charge de validation humaine** → prioriser les faits décisionnels (droits, AVQ, orientation).
- **Conflits non résolus** s'ils s'accumulent sans validation → file de validation visible.

---

## CE QU'IL NE FAUT PAS DÉVELOPPER (tant que la couche de faits n'est pas posée)
Nouveau **moteur métier**, **Vague 2**, refonte **scoring**, modif **CERFA/prompts/dashboards/quotas**, **UX**, **multi-tenant**, **rôles managers**, nouveau **mapping** spéculatif. Aucun patch symptomatique.

---

## CRITÈRE DE RÉUSSITE
À partir d'un **bilan BFP** + une **conversation WhatsApp** réels, FACILIM produit des **faits structurés** (modèle ci-dessus) **traçables, validables, réutilisables**, **sans narratif libre**. Chaque information répond à : **d'où vient-elle / qui l'a dite / quel document / validée / où utilisée**. Démonstration = les 5 faits exemples (COLLOMBARD, fatigabilité, ESAT, ménage, absences) deviennent des faits sourcés, validables, et alimentent cockpit + CERFA.

---

*Architecture cible de structuration. Conception de référence uniquement — aucun code, aucun moteur, aucun patch, aucune modification produit. Base pour une refonte propre ultérieure.*
