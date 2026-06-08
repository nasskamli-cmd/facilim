# INVENTAIRE_CONNAISSANCES_FACILIM.md

**Généré le :** 2026-06-07 · lecture/analyse seule.
Carte de connaissances : par domaine → champs **existants** / **manquants** / **origine** / **usages actuels**.
(« existant » = champ réellement présent dans le flux ; « peu persisté » = défini mais inconstant — cf. audits NIVEAU A.)

| Domaine | Champs existants | Champs manquants (structurés) | Origine | Usages actuels |
|---|---|---|---|---|
| Identité | nom_prenom, date_naissance, genre | prenom/nom_naissance séparés (peu persistés), sexe fiable | doc, WA, pro | CERFA P2, dashboard |
| Administratif | numero_dossier_mdph | organisme_payeur, numero_allocataire (peu persistés) | WA, doc, pro | CERFA P2 (partiel) |
| Santé | diagnostics, traitements (texte) | suivi structuré (psychiatre/psy/médecin), absences | doc | CERFA P8, éligibilité |
| Professionnels | — | intervenant{role,nom} (liste) | doc | aucun (perdu en texte) |
| Limitations | impact_quotidien (texte) | limitation{type,intensite}, fatigabilité | WA, doc | CERFA P8 (texte), moteurs |
| AVQ | avq_* (définis, peu persistés) | fiabilisation enum + persistance | WA, doc | CERFA P6 (si présents) |
| Mobilité | — (déduit texte) | mobilite_int/ext, transports | WA, doc | CERFA P7 (mots-clés) |
| Cognition | — | mémoire, apprentissage, organisation | doc (bilan) | aucun (texte) |
| Comportement | — | trait + impact (propos inadaptés, collectif) | doc | aucun (texte) |
| Communication | — | oral/écrit | doc | aucun (texte) |
| Aidants | aidant_nom, aidant_besoins | aidant{role,besoins,répit} structuré, aidants secondaires | WA, doc | CERFA F (partiel) |
| Environnement | mode_vie (texte) | type_logement, aides techniques, aménagements | WA | CERFA P5 (déduit) |
| Emploi | statut_emploi | absences_sante (bool/contexte), parcours | doc, WA | CERFA D |
| Formation | formation_actuelle, projet (texte) | formation{intitule,organisme} (ESRP…) | doc, WA | CERFA D |
| Ressources | (pension via statut texte) | pension_invalidite, categorie, taux_ipp (peu persistés), RSA | WA, doc | CERFA B1 (partiel) |
| Droits | droits_demandes (texte), droits.* (peu persistés) | objet droits fiable | WA, pro | CERFA P17, cockpit |
| Projet de vie | projet_professionnel/orientation (texte), texte_e (généré) | projet_vie{libelle} structuré | WA, doc | CERFA P16 |
| Orientation | (via droits_demandes texte) | orientation{type,structure} (ESAT/La Farigoule) | WA, doc | CERFA E3 (case) |

## Synthèse de l'inventaire
- **Bien structurés** : identité base, departement, droits_demandes (texte), scolaire, representant/protection.
- **Définis mais peu persistés** : NIVEAU A (avq_*, droits.*, organisme/allocataire, invalidité).
- **Quasi inexistants en structuré (restent en texte)** : Professionnels, Cognition, Comportement, Communication, Mobilité fine, Fatigabilité, Absences santé, Orientation structurée — **ce sont précisément les domaines riches des bilans**.

---
*Lecture seule. Aucune création de champ ; inventaire de l'existant et des manques.*
