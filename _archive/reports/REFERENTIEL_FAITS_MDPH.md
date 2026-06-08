# REFERENTIEL_FAITS_MDPH.md — Référentiel de faits attendus (gold)

**Généré le :** 2026-06-08 · spécification de mesure (lecture seule). Aucun code, aucune modif produit.
**Usage :** liste « or » des faits qu'un dossier MDPH devrait contenir ; dénominateur du taux de structuration.
**Exemples + citations réels** issus des pièces déjà lues (bilan BFP **AIT ABBAS Abdelkarim**, bilan PCR **CECORA Marie-Christine**, WhatsApp TEST6).

> Colonnes : **Faits observables** · **Champs structurables** · **Exemple réel + citation** · **Preuve attendue** · **Source possible** · **Usages FACILIM**.

| Domaine | Faits observables | Champs structurables | Exemple réel + citation | Preuve attendue | Source | Usages FACILIM |
|---|---|---|---|---|---|---|
| Identité | nom, prénom, naissance, sexe | `nom`,`prenom`,`date_naissance`,`sexe` | « AIT ABBAS Abdelkarim » / « Date de naissance 09/05/1988 » (bilan) | citation doc/usager | doc, WA, pro | CERFA P2, dashboard, dérivation âge |
| Coordonnées | adresse, tel, email | `adresse`,`cp`,`commune`,`telephone`,`email` | « 123 boulevard Romain Rolland … Bt 49, 13010 MARSEILLE » (bilan) | document | WA, doc | CERFA P2, contact |
| Administratif | NIR, organisme payeur, n° alloc., n° dossier | `nir`,`organisme_payeur`,`numero_allocataire`,`numero_dossier_mdph` | « N°SS 1 88 05 99 353 028 81 », « Dossier n°169962 » (bilan) | pièce justificative | doc, WA, pro | CERFA P2 |
| Situation familiale | situation, enfants | `situation_familiale`,`enfants_a_charge` | CECORA : « j'accompagne ma mère … petit-fils » | déclaration | WA, doc | CERFA, contexte |
| Logement | type, hébergement | `type_logement`,`hebergement` | (bilan : adresse résidence) | déclaration | WA | CERFA P5 |
| Santé | état psy/physique | `etat_sante`,`suivi` | « stabiliser son état de santé psychique et physique » (bilan) | mention médicale | doc | CERFA P8, éligibilité |
| Professionnels de santé | psychiatre, psy, AS, médecin | `intervenant{role,nom}` | « Mme COLLOMBARD la psychiatre », « Mme FONTAINE la psychologue », « Mme CALI l'AS » (bilan) | nom cité | doc | aidants/partage, CERFA |
| Diagnostics | pathologies | `diagnostic{libelle}` | (certificat requis) | certificat | doc | CERFA, éligibilité |
| Traitements | médicaments/soins | `traitement{libelle}` | « suivi … cardiologue » (bilan) | mention | doc | CERFA |
| Limitations | restrictions, fatigabilité | `limitation{type,intensite}`,`fatigabilite` | « il fatigue vite » (bilan) ; « station debout limitée » (CECORA) | citation | doc, WA | CERFA P7/P8, PCH |
| AVQ | toilette/habillage/repas/ménage | `avq_{acte}`=niveau | « besoin d'aide pour le ménage » (CECORA) | déclaration/observation | WA, doc | CERFA P6, PCH |
| Mobilité | déplacements, transports | `mobilite_{int,ext}`,`transports` | (à préciser) | déclaration | WA, doc | CERFA P7 |
| Communication | oral/écrit | `communication_{oral,ecrit}` | « petit niveau à l'écrit » (bilan) | observation | doc | CERFA, GEVA |
| Cognition | mémoire, apprentissage, organisation | `cognition_{memoire,apprentissage,organisation}` | « du mal à organiser son travail », « peu investi dans les apprentissages » (bilan) | observation | doc | CERFA, scoring |
| Comportement | propos, collectif, règles | `comportement{trait,impact}` | « propos inadaptés qui peuvent engendrer des tensions » (bilan) | citation | doc | CERFA P8, orientation |
| Emploi | statut, parcours, absences santé | `statut_emploi`,`absences_sante` | « absent une partie de son stage pour raison médicale » (bilan) | citation | doc, WA | CERFA D |
| Formation | en cours/visée | `formation{intitule,organisme}` | « formation à l'EPNAL ESRP à Lyon » (bilan) | mention | doc, WA | CERFA D |
| Ressources | pension invalidité, RSA, revenus | `pension_invalidite`,`categorie_invalidite`,`taux_ipp`,`ressource{type}` | « pension d'invalidité catégorie 2 » (WA TEST6) | attestation | WA, doc | CERFA B1 |
| Droits | AAH, PCH, RQTH, CMI | `droit{code,demande}` | TEST6 : aucun demandé par l'usager (orientation ESAT seule) | demande explicite | WA, pro | CERFA P17, cockpit |
| Aidants | aidant principal, besoins, répit | `aidant{role,nom,besoins}` | CECORA : « apporte un soutien important à ma fille … petit-fils » | déclaration | WA, doc | CERFA F |
| Projet de vie | aspirations, maintien domicile | `projet_vie{libelle}` | « Je veux vivre comme les gens normaux. Il me faut quelque chose d'adapté » (bilan) | expression usager | WA, doc | CERFA P16 |
| Orientation | ESAT/ESMS cible, structure | `orientation{type,structure}` | « ESAT La Farigoule … ils peuvent me prendre » (WA) | « ils peuvent me prendre » | WA, doc | CERFA E3, droits |
| Environnement | aides techniques, aménagements | `aide_technique{type}`,`amenagement` | (à préciser) | document/devis | WA, doc | CERFA B, PCH |

**Règle de comptage** : le référentiel « or » d'**un** dossier = les faits réellement présents dans **ses** pièces (avec citation). Ce tableau fixe la **structure** des faits par domaine + les **usages aval** (où chaque fait devrait servir).

---
*Spécification de mesure. Citations issues des pièces réelles. Aucune modification produit.*
