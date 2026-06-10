# MESURE_STRUCTURATION_FACILIM.md — Système de mesure de la structuration

**Généré le :** 2026-06-07
**Mode :** conception d'un **système de mesure** uniquement. Aucun correctif, aucune implémentation produit, aucun moteur métier.
**Données réelles :** bilan BFP AIT ABBAS + WhatsApp TEST 6 (`FAC-DOS--SW-VJVD`), bilan PCR CECORA (`FAC-DOS-M30DPYEX`).
**But :** mesurer **où chaque fait disparaît** dans `SOURCE → STRUCTURATION → SYNTHÈSE → DASHBOARD → CERFA`.

---

## CE QUI EST PROUVÉ
- **Source ✅** : les faits existent dans les pièces (bilans/WhatsApp lus).
- **CERFA ❌ (contenu)** : extraction texte → seul l'en-tête nom apparaît ; 0 occurrence des valeurs sources sur 21 pages (AIT ABBAS & CECORA).
- **Structuration ❌ pour les faits documentaires** : le chemin document produit du **texte** (`_document_knowledge`) + une liste admin limitée ; **jamais** d'`avq_*`/santé-suivi/projet **structurés** (code prouvé).
- **Dashboard ❌** : 20/100 ; barème = 12 champs base, **n'inclut pas** les domaines riches (santé/professionnels/projet/AVQ).

## CE QUI EST NON VÉRIFIÉ
- **Étape STRUCTURATION / SYNTHÈSE par fait** en runtime : nécessite l'**export de `synthese_json`** par dossier (prod inaccessible) + les traces `[TRACE_*]` d'un rejeu.
- État des **cases** CERFA (graphiques).

---

## MATRICE DE TRAÇABILITÉ (MISSION 1 — faits réels)

| Domaine | Champ | Valeur | Dossier |
|---|---|---|---|
| Identité | nom_prénom | AIT ABBAS Abdelkarim | SW-VJVD |
| Identité | date_naissance | 09/05/1988 | SW-VJVD |
| Identité | NIR | 1 88 05 99 353 028 81 | SW-VJVD (bilan+WA) |
| Administratif | dossier_mdph | 169962 | SW-VJVD |
| Santé | suivi_psychiatre | Dr COLLOMBARD | SW-VJVD |
| Santé | suivi_psychologue | Mme FONTAINE | SW-VJVD |
| Santé | suivi_medical | généraliste, cardiologue | SW-VJVD |
| Professionnels | assistante_sociale | Mme CALI | SW-VJVD |
| Handicap | nature | psychique + physique | SW-VJVD (WA+bilan) |
| Fatigabilité | présence | Oui (« il fatigue vite ») | SW-VJVD |
| Emploi | absences_santé | Oui (répétées) | SW-VJVD |
| Projet pro | orientation | ESAT / milieu protégé | SW-VJVD (WA) |
| Orientation | structure cible | ESAT La Farigoule | SW-VJVD (WA) |
| Projet pro | métier visé | mécanicien automobile | SW-VJVD (bilan) |
| Formation | visée | ESRP EPNAL Lyon | SW-VJVD (bilan) |
| Santé | fatigabilité/ménage | difficulté ménage, station debout | M30DPYEX (CECORA) |
| Aidants | rôle | aidante (mère + petit-fils) | M30DPYEX |

## MATRICE — PARCOURS OBSERVÉ (MISSION 2)

| Fait | Source | Structuré | Synthèse | Dashboard | CERFA |
|---|---|---|---|---|---|
| Identité (nom/date) | ✅ | NON VÉRIFIÉ | NON VÉRIFIÉ | ❌ | ❌ |
| NIR | ✅ | NON VÉRIFIÉ | NON VÉRIFIÉ | ❌ | ❌ |
| Suivi psychiatre | ✅ | ❌ (→ texte) | NON VÉRIFIÉ (texte) | ❌ | ❌ |
| Fatigabilité | ✅ | ❌ | NON VÉRIFIÉ (texte) | ❌ | ❌ |
| Absences santé | ✅ | ❌ | NON VÉRIFIÉ (texte) | ❌ | ❌ |
| Orientation ESAT / La Farigoule | ✅ | ❌ | NON VÉRIFIÉ (texte) | ❌ | ❌/❓ (case) |
| Projet mécanique / ESRP | ✅ | ❌ | NON VÉRIFIÉ (texte) | ❌ | ❌ |

## MATRICE DE PERTE (MISSION 3)

| Fait | Dernière étape où il EXISTE (prouvé) |
|---|---|
| Identité (nom/date/adresse) | **Source** (présent en en-tête CERFA, absent du formulaire) |
| NIR | **Source** |
| Suivi psychiatre / psychologue / AS | **Source** (puis au mieux `_document_knowledge` texte = NON VÉRIFIÉ) |
| Fatigabilité | **Source** |
| Absences santé | **Source** |
| Orientation ESAT / La Farigoule | **Source** |
| Projet mécanique / ESRP | **Source** |

➡️ **Point de disparition prouvé = à la STRUCTURATION** (le fait existe en source, n'est pas un champ structuré, et n'atteint ni dashboard ni CERFA). L'étape intermédiaire exacte (texte `_document_knowledge` vs rien) = **NON VÉRIFIÉ** sans export `synthese_json`.

---

## DOMAINES DE CONNAISSANCE (MISSION 4)

| Domaine | Faits observables | Source possible | Utilisation aval |
|---|---|---|---|
| IDENTITÉ | nom, prénom, naissance, sexe, NIR | doc/WA/pro | CERFA P2, dashboard |
| ADMINISTRATIF | organisme payeur, n° allocataire, dossier MDPH | WA/pro/doc | CERFA P2 |
| HANDICAP | nature, ancienneté | doc/WA | scoring, CERFA |
| SANTÉ | diagnostics, suivi (psychiatre/psy/médecin), traitements | **doc** | CERFA P8, éligibilité |
| PROFESSIONNELS | intervenants nommés | doc | aidants/partage |
| AVQ | toilette, habillage, repas, ménage (niveaux) | WA/doc | CERFA P6, PCH |
| MOBILITÉ | déplacements, transports | WA/doc | CERFA P7 |
| FATIGABILITÉ | présence, intensité, déclencheurs | WA/**doc** | CERFA P7, PCH |
| AIDANTS | aidant, besoins, répit | WA/doc | CERFA F |
| EMPLOI | statut, parcours, absences | doc/WA | CERFA D |
| FORMATION | en cours/visée | doc/WA | CERFA D |
| PROJET PROFESSIONNEL | métier, ESAT/milieu protégé | WA+doc | CERFA D/E |
| PROJET DE VIE | aspirations, maintien domicile | WA/doc | CERFA P16 |
| ORIENTATION | ESMS cible (ESAT…) | WA/doc | CERFA E3 |
| DROITS | AAH, PCH, RQTH, CMI | WA/pro | CERFA P17, cockpit |

---

## POINTS D'INSTRUMENTATION (MISSION 5)

### À MESURER DANS WHATSAPP
nb messages ; par message : faits candidats (domaine/champ) déclarés ; longueur (masquée). *(déjà : `[TRACE_COLLECTE] 1/4/5`)*

### À MESURER DANS LES DOCUMENTS
document reçu (taille/mime) ; texte extrait (longueur) ; faits candidats par domaine. *(déjà : `[TRACE_SOURCE_SYNTHESE] 3/4/5/6`)*

### À MESURER DANS LA STRUCTURATION *(manque actuel)*
pour chaque fait candidat : **devient-il un champ structuré** ? domaine/champ cible, **source, citation, confiance**. → mesure **fact-level** (aujourd'hui on ne mesure que field-level).

### À MESURER DANS synthese_json
liste des **clés structurées** présentes (déjà via `_trace_resume`) **+ par fait** : présent/absent + origine. → nécessite **export** de `synthese_json` par dossier.

### À MESURER DANS LE DASHBOARD
complétude (12 champs) + **présence des domaines riches** (santé/projet/AVQ) → aujourd'hui non comptés.

### À MESURER DANS LE CERFA
par champ/case : rempli/vide + **traçable à une source**. *(cases = à lire via un rendu, pas le texte)*

---

## CRITÈRE DE SUCCÈS (MISSION 6 — matrice de validation)

| Condition | Mesure |
|---|---|
| C1 | **faits observés (source) = faits structurés** (taux ≥ cible) |
| C2 | **faits structurés = faits persistés** dans synthese_json |
| C3 | **faits persistés = faits localisables** (dashboard et/ou CERFA) |
| C4 | **chaque fait** porte : **source + citation + confiance + validation_humaine** |

Structuration « réussie » = C1 ∧ C2 ∧ C3 ∧ C4 vrais sur un panel de dossiers réels.

---

## SPRINT UNIQUE RECOMMANDÉ (MISSION 7)

### Le plus petit sprint **de mesure** (sans toucher au produit)
**« HARNAIS DE TRAÇABILITÉ DE FAITS »** — un outil de **mesure hors-produit** qui :
1. prend en entrée, pour chaque dossier (CECORA, AIT ABBAS, +1 réel) : **le référentiel de faits attendus** (liste « or » extraite des sources), **l'export `synthese_json`**, et **le CERFA** ;
2. calcule, **par fait**, la **dernière étape où il existe** (source / structuré / synthèse / dashboard / CERFA) ;
3. produit les **3 matrices** (traçabilité, parcours, perte) + le **score C1-C4**.

C'est **uniquement de la mesure** : aucun moteur, aucun prompt, aucun CERFA, aucun dashboard modifié. Il consomme des **exports en lecture** + les pièces sources.

### Pré-requis (lecture seule, à fournir)
- Référentiel de faits « or » par dossier (peut être bâti à partir des pièces).
- **Export `synthese_json`** des 3 dossiers (read-only) — aujourd'hui le seul élément manquant (prod inaccessible).
- Les CERFA générés + (idéalement) les traces `[TRACE_*]` d'un rejeu instrumenté.

### PREUVES ATTENDUES
Pour chaque dossier : un tableau **fait → dernière étape** ; un **taux de structuration** (faits source → structurés) ; la liste des faits **perdus à la structuration** ; le respect **C4** (source/citation/confiance/validation) par fait. Sur CECORA & AIT ABBAS, attendu observé : **structuration ≈ 0 %** des faits riches (à confirmer par l'export).

---

## CE QU'IL NE FAUT PAS DÉVELOPPER
Aucun **moteur métier**, aucune **Vague 2**, aucune modification **CERFA / prompts / scoring / dashboards / quotas**, aucun **correctif** de structuration — **tant que la mesure n'a pas chiffré** la perte par fait. Le harnais est **observation seule**.

---

## QUESTION FINALE — réponse
**Comment démontrer, dossier réel à l'appui, que FACILIM transforme correctement une situation de vie en faits structurés exploitables ?**

> En **mesurant fait par fait** : (1) bâtir le **référentiel de faits** depuis les sources ; (2) **exporter `synthese_json`** et lire le **CERFA** ; (3) via le **harnais de traçabilité**, situer chaque fait sur `source → structuré → synthèse → dashboard → CERFA` et calculer **C1-C4**. La démonstration est faite **uniquement** si **chaque fait observé devient un champ structuré, persisté, localisable, portant source + citation + confiance + validation** — sans dépendre d'un narratif libre. Aujourd'hui (prouvé sur AIT ABBAS / CECORA), les faits riches **n'existent plus après la source** côté CERFA/dashboard ; le harnais chiffrera précisément l'étape de disparition une fois `synthese_json` exporté.

---

*Conception d'un système de mesure, lecture seule. Aucun correctif, aucune implémentation produit. Le seul élément manquant pour chiffrer la structuration = l'export `synthese_json` par dossier ; tout le reste est déjà disponible (sources, CERFA, instrumentation `[TRACE_*]`).*
