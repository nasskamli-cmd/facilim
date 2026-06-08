# ARCHITECTURE_STRUCTURATION_FACILIM.md — Source de vérité « situation de vie »

**Généré le :** 2026-06-07
**Mode :** conception conceptuelle (comité exécutif). Aucun code, aucun moteur, aucune Vague 2.
**Base de preuve :** dossiers réels `FAC-DOS-M30DPYEX`, `FAC-DOS--SW-VJVD` (bilan BFP AIT ABBAS + WhatsApp TEST 6) + faits code déjà prouvés.

---

## CE QUI EST PROUVÉ
- `synthese_json` = source de vérité unique ; tout l'aval (dashboard/cockpit/CERFA/moteurs) la lit.
- Sources **riches** (bilan BFP : identité, NIR, suivi psychiatrique, absences, projet) mais **CERFA vide** + **20/100** → perte **avant** `synthese_json`.
- Chemin document : extrait une **liste admin limitée** + `_document_knowledge` (**texte**) ; **jamais** d'`avq_*`/droits/suivi-santé **structurés**.
- Chemin WhatsApp : extraction whitelistée (NIVEAU A inclus depuis 1dccf6c) **mais** dépend de questions posées + format enum.
- Fusion : « premier écrivain gagne » ; clé présente même vide **bloque** la 2ᵉ source.
- Complétude = **12 champs de base** uniquement (NIVEAU A non compté).

## CE QUI EST DÉCLARÉ
- Anti-contamination (narratif ≠ preuve) et CERFA V2 fonctionnent.
- Les prompts couvrent des **thèmes** (autonomie/droits/projet).

## CE QUI EST NON VÉRIFIÉ
- État des **cases** CERFA (graphique) ; **upload réel** du bilan sur les dossiers témoins ; `synthese_json` interne en prod ; **sous-pas technique exact** de la perte (traces `[TRACE_*]` non disponibles pour ces dossiers).

---

## CARTE DE CONNAISSANCES (MISSION 1)

| Domaine | Champs (min.) | Origine possible | Preuve attendue | Usages aval |
|---|---|---|---|---|
| IDENTITÉ | nom, prénom, naissance, sexe, NIR | doc, WhatsApp, pro | pièce identité / bilan | CERFA P2, dashboard |
| ADMINISTRATIF | organisme payeur, n° allocataire, dossier MDPH | WhatsApp, pro | attestation CAF/MSA | CERFA P2 |
| HANDICAP | nature (psy/physique/cognitif), ancienneté | doc, WhatsApp | certificat / bilan | CERFA, scoring |
| SANTÉ | diagnostics, suivi (psychiatre/psy/médecin), traitements | **doc** | bilan, certificat médical | CERFA P8, éligibilité |
| PROFESSIONNELS | intervenants nommés (psychiatre, AS, tuteurs) | doc | bilan | aidants/partage |
| AVQ | toilette, habillage, repas, ménage (niveaux) | WhatsApp, doc | déclaration / bilan | CERFA P6, PCH |
| MOBILITÉ | déplacements int./ext., transports | WhatsApp, doc | déclaration | CERFA P7 |
| FATIGABILITÉ | présence, intensité, déclencheurs | WhatsApp, **doc** | « il fatigue vite » (bilan) | CERFA P7, PCH |
| ENVIRONNEMENT | logement, hébergement | WhatsApp | déclaration | CERFA P5 |
| AIDANTS | aidant principal, besoins, répit | WhatsApp, doc | déclaration | CERFA F |
| EMPLOI | statut, parcours, absences | doc, WhatsApp | bilan | CERFA D |
| FORMATION | en cours/visée (ESRP…) | doc, WhatsApp | bilan | CERFA D |
| PROJET PROFESSIONNEL | métier visé, ESAT/milieu protégé | **WhatsApp + doc** | « ESAT La Farigoule » / « mécanicien » | CERFA D/E |
| PROJET DE VIE | aspirations, maintien domicile | WhatsApp, doc | expression usager | CERFA P16 |
| DROITS | AAH, PCH, RQTH, CMI | WhatsApp, pro | demande explicite | CERFA P17, cockpit |
| ORIENTATION | ESMS (ESAT…), structure cible | WhatsApp, doc | « ils peuvent me prendre » | CERFA E3 |

---

## AUDIT DES SOURCES (MISSION 2 — TEST 6 réel)

| Fait | Source | Domaine |
|---|---|---|
| AIT ABBAS Abdelkarim | Bilan | Identité |
| Né le 09/05/1988 | Bilan | Identité |
| 123 bd Romain Rolland, 13010 Marseille | Bilan | Identité/Environnement |
| NIR 1 88 05 99 353 028 81 | Bilan **+** WhatsApp | Identité/Administratif |
| Dossier MDPH n°169962 | Bilan | Administratif |
| Suivi psychiatre (Dr COLLOMBARD) | Bilan | Santé/Professionnels |
| Suivi psychologue / AS | Bilan | Santé/Professionnels |
| Généraliste, cardiologue | Bilan | Santé |
| Absences répétées pour raison de santé | Bilan + WhatsApp | Santé/Emploi |
| « il fatigue vite » | Bilan | Fatigabilité |
| Propos inadaptés / difficulté en collectif | Bilan | Handicap (psychique) |
| « problème psychique et physique », « depuis des années » | WhatsApp | Handicap |
| Projet ESAT / milieu protégé / La Farigoule | WhatsApp | Projet pro/Orientation |
| Projet mécanicien automobile | Bilan | Projet pro |
| Formation ESRP EPNAL Lyon | Bilan | Formation |
| France Travail à faire | Bilan | Emploi |
| Pas de formation en cours | WhatsApp | Formation |

---

## AUDIT DE STRUCTURATION (MISSION 3)

| Fait | Compris | Structuré | Persisté | Visible | Utilisé | Catégorie |
|---|---|---|---|---|---|---|
| Identité (nom/date/adresse) | ✅ | ❌ | ❓ | ❌ | ❌ | **C** (et absent CERFA) |
| NIR | ✅ | partiel | ❓ | ❌ | ❌ | **C/E** |
| Suivi psychiatre | ✅ | ❌ (→ _document_knowledge texte) | texte | ❌ | texte | **C** |
| Absences santé | ✅ | ❌ | texte | ❌ | texte | **C** |
| Fatigabilité | ✅ | ❌ (pas d'AVQ/champ) | texte | ❌ | texte | **C** |
| Comportement psychique | ✅ | ❌ | texte | ❌ | texte | **C** |
| Projet ESAT / La Farigoule | ✅ | ❌ (pas de champ orientation) | texte | ❌ | partiel | **C** |
| Projet mécanique / ESRP | ✅ | ❌ | texte | ❌ | texte | **C** |
| AVQ (toilette/habillage/…) | — | ❌ | — | ❌ | ❌ | **A** (non collecté précis) |
| Droits (AAH/PCH/RQTH/CMI) | — | ❌ | — | ❌ | ❌ | **A** (jamais demandés) |
| organisme/allocataire | — (absent sources) | — | — | — | — | A (hors sources) |

**Catégorie dominante : C (compris mais non structuré).** Vérifiée même quand la collecte/compréhension réussit (bilan riche). **D/E** en aggravation (fusion + mapping). **A** pour ce qui n'est pas demandé (AVQ/droits).

---

## SOURCE DE VÉRITÉ CIBLE (MISSION 4)

**Modèle de fait unifié** — chaque information de la carte devient :
```
Fait = { domaine, champ, valeur (structurée), source, citation, confiance, validation_humaine }
```
Exemple réel :
```
{ domaine: "Fatigabilité", champ: "présence", valeur: true,
  source: "bilan BFP AIT ABBAS", citation: "il fatigue vite",
  confiance: "forte (document)", validation_humaine: "non relue" }
```
Toutes les sources convergent vers **ce** modèle (matérialisé dans `synthese_json`). Le **texte** (bilan/narratif) devient une **preuve attachée**, jamais la donnée.

### RÈGLES DE FUSION
Une nouvelle source **enrichit ou corrige** un fait existant (jamais ignorée parce que « clé déjà présente »). Un champ vide n'est pas « présent » : il doit pouvoir être rempli par une source ultérieure.

### RÈGLES DE PRIORITÉ
Preuve **documentaire/pro** > déclaratif vague pour Santé/Identité/Historique. **Parole de l'usager** prioritaire pour Projet de vie / attentes / orientation souhaitée.

### RÈGLES DE CONFLIT
Deux valeurs divergentes → **conserver les deux** (valeur + source + confiance), **signaler** pour validation humaine, **ne jamais** écraser silencieusement ni dropper.

### RÈGLES DE TRAÇABILITÉ
Aucun fait sans **source + citation**. Le CERFA et le cockpit n'affichent **que** des faits tracés. Un fait sans preuve = non transmis.

### RÈGLES DE VALIDATION HUMAINE
Statut par fait : `non relu → validé pro → validé usager`. Aucune transmission CERFA sans relecture humaine (gate existant).

---

## GOULOT UNIQUE (MISSION 6)

### GOULOT UNIQUE
**La STRUCTURATION** : l'information comprise des deux sources **n'est pas convertie en faits structurés** d'un modèle « situation de vie » ; elle reste en **texte libre** (`_document_knowledge`, `impact_quotidien`, narratifs) inexploitable par le dashboard et le CERFA.

### PREUVES
`FAC-DOS--SW-VJVD` : bilan BFP riche → **0 occurrence** dans le CERFA, **20/100**. Chemin document prouvé : produit du **texte** (`_document_knowledge`), pas des champs structurés. Complétude = 12 champs base.

### IMPACT
Dossiers réels plafonnés à ~20 %, CERFA non exploitable, bilans professionnels perdus.

### RISQUE SI IGNORÉ
Aucun travail aval (CERFA, moteurs, mapping) ne peut produire un dossier fidèle → pilote ESSMS **NO GO** durable.

---

## PLAN DE TRANSFORMATION (MISSION 5)

### CE QUI EXISTE DÉJÀ / FONCTIONNE / CÂBLÉ / VISIBLE / UTILISÉ
- **Existe & fonctionne** : `synthese_json` (convergence), moteurs 60→100, anti-contamination, CERFA V2, dashboard, gate, instrumentation `[TRACE_*]`, collecte unique.
- **Câblé** : 2 sources → `synthese_json` → aval.
- **Visible/Utilisé** : 12 champs base + droits texte + avq_* (si présents).

### CE QUI EST INUTILISÉ
Tout le **contenu riche resté en texte** (santé, professionnels, projet, fatigue) ; champs NIVEAU A non comptés ; 2ᵉ source bloquée par la fusion.

### COMPOSANTS À CRÉER
**Une couche de STRUCTURATION** (conceptuelle, pas un « moteur » métier) : convertit le contenu compris (WhatsApp + document) en **faits structurés tracés** alimentant `synthese_json`. *(Conception ici ; périmètre/code = sprint dédié ultérieur.)*

### COMPOSANTS À RECÂBLER
L'**extraction** (WhatsApp + document) pour qu'elle **émette des faits structurés** (domaines Santé/Professionnels/AVQ/Projet) au lieu de texte ; la **fusion** pour enrichir au lieu d'ignorer.

### COMPOSANTS À SUPPRIMER
Rien d'urgent. À terme : les **silos texte parallèles** sans fait structuré correspondant.

### COMPOSANTS À CONSERVER
Tout l'aval (CERFA V2, cockpit, moteurs, gate, audit) — sain ; il manque seulement des **faits structurés** à consommer.

---

## SPRINT UNIQUE PRIORITAIRE
**« STRUCTURATION DE LA SITUATION DE VIE »** — faire en sorte que les informations **comprises** des deux sources deviennent des **faits structurés tracés** (`{valeur, source, citation, confiance, validation}`) dans `synthese_json`, en priorité **Santé / Professionnels / AVQ / Fatigabilité / Projet**, **avant** tout travail aval.

### PREUVES DE VALIDATION ATTENDUES
Sur un dossier réel instrumenté (`c3081775`) avec bilan BFP + conversation riches :
- les traces `[TRACE_*]` montrent le contenu **arrivant en champs structurés** (pas seulement `_document_knowledge`) ;
- **complétude > 20** ;
- **CERFA fidèle** : identité + santé (suivi psychiatre) + fatigabilité + projet (ESAT/mécanique) présents, **chaque champ tracé à sa source** ;
- **sans dépendre d'un narratif libre**.

---

## CE QU'IL NE FAUT PAS DÉVELOPPER
Nouveau **moteur métier**, **Vague 2**, refonte **scoring**, modification **CERFA/prompts/dashboards/quotas**, **UX**, nouveau **mapping CERFA** — **avant** que la couche de structuration produise des faits. Aucun quick fix symptomatique.

---

## CRITÈRE DE SUCCÈS — réponse
Un bilan BFP riche + une conversation riche **doivent** produire une **situation de vie structurée** (faits tracés) → synthèse riche → dashboard riche → CERFA fidèle, **sans narratif libre décisionnel**. Le **seul** verrou pour y arriver = **la structuration** (conversion texte compris → faits structurés). C'est le **sprint unique** à mener ; tout le reste est déjà en place ou doit être gelé.

---

*Conception conceptuelle. Aucun code, aucun moteur créé, aucune hypothèse non étayée. Sous-pas technique exact de la perte = à confirmer par traces `[TRACE_*]` d'un rejeu instrumenté ; la conclusion (goulot = structuration) est démontrée par les dossiers réels.*
