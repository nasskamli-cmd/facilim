# TERRAIN_TEST6_PREUVE_AUDIT.md — Cartographie des pertes sources → CERFA (TEST 6)

**Généré le :** 2026-06-07
**Dossier :** `FAC-DOS--SW-VJVD` · « En collecte » · **complétude 20/100** (capture dashboard).
**Sources (pièces jointes) :** conversation WhatsApp (`ECHANGE WAAT APPS TEST 6.docx`) · bilan `BFP AIT ABBAS Abdelkarim.docx` · CERFA `CF TEST 6 FACILIM.pdf`.
**Mode :** rapport de preuve, lecture seule. Aucun correctif, aucune supposition.

## ⚠️ Limites de preuve
- **CERFA aplati** : pypdf lit le gabarit + le **texte dessiné par FACILIM** (prouvé : l'en-tête « AIT ABBAS Abdelkarim » est extrait). Les **cases à cocher** (AVQ, droits, orientation ESAT) sont **graphiques → NON LISIBLES** en texte → leur état = **NON VÉRIFIÉ**.
- **Upload du bilan sur ce dossier = NON VÉRIFIÉ** : la conversation n'évoque aucun envoi de document ; impossible de confirmer que le bilan a été ingéré dans `FAC-DOS--SW-VJVD`.
- **`synthese_json` interne = NON VÉRIFIÉ** (volume prod inaccessible ; aucune trace lisible).

---

## CE QUI EST PROUVÉ
- Le CERFA ne contient, en **texte**, **aucune** valeur déclarée des sources, hormis l'en-tête « AIT ABBAS Abdelkarim » (p.1).
- Le bilan et la conversation contiennent des informations **riches** (identité complète, NIR, suivi psychiatrique, projet pro).
- Le dashboard affiche **20/100**.
→ **L'information disparaît entre les sources et le CERFA.**

## CE QUI EST DÉCLARÉ
- Que ce dossier est issu d'un test réel (WhatsApp + bilan AIT ABBAS).

## CE QUI EST NON VÉRIFIÉ
- L'état des **cases à cocher** du CERFA (AVQ / droits / orientation ESAT).
- Si le **bilan a été uploadé** sur ce dossier.
- Le contenu réel de `synthese_json` et le **sous-pas exact** de la perte (faute de traces `[TRACE_*]` lisibles).

---

## MATRICE 1 — INVENTAIRE DES SOURCES

| Information | Source | Citation exacte |
|---|---|---|
| Nom-prénom | Bilan | « NOM – PRÉNOM AIT ABBAS Abdelkarim » |
| Date naissance | Bilan | « Date de naissance 09/05/1988 » |
| Adresse | Bilan | « 123 boulevard Romain Rolland, Résidence les Marronniers, Bt 49, 13010 MARSEILLE » |
| NIR | Bilan | « N°SS 1 88 05 99 353 028 81 » |
| NIR | WhatsApp | « 188059935302881 » |
| N° dossier | Bilan | « Dossier n°169962 » |
| Difficultés psy/phys | WhatsApp | « J'ai des problème psychique et physique » / « Depuis des années » |
| Maintien projet / absences | WhatsApp | « J'arrive pas a garder un projet je suis souvent malade est absent » / « J'ai du mal a m'investir » |
| Projet ESAT | WhatsApp | « J'aimerais travailler en esat » / « Millieu protégé » / « Avoir une orientation ESAT … l'esat la Farigoule … il peuvent me prendre » |
| Formation | WhatsApp | (Q formation) → « Non » |
| Suivi psychiatrique | Bilan | « accompagnement par … Mme COLLOMBARD la psychiatre » / « distanciel préconisé par son psychiatre » |
| Suivi psychologue / AS | Bilan | « Mme FONTAINE la psychologue », « Mme CALI l'assistante sociale » |
| Suivi médical | Bilan | « suivi … par son généraliste, son psychiatre et ses spécialistes (cardiologue etc.) » |
| Absences santé | Bilan | « il a également eu des absences » / « absent une partie de son stage pour raison médicale » |
| Comportement social | Bilan | « propos inadaptés qui peuvent engendrer des tensions » / « du mal à s'intégrer au groupe » |
| Fatigabilité | Bilan | « il fatigue vite » |
| Projet mécanique | Bilan | « valider son projet de devenir mécanicien automobile » |
| Formation ESRP | Bilan | « une formation à l'EPNAL ESRP à Lyon » |
| France Travail | Bilan | « doit … s'inscrire à France Travail » |
| Expression usager | Bilan | « Je veux vivre comme les gens normaux. Il me faut quelque chose d'adapté. » |

> Divergence notable : **projet ESAT/La Farigoule = WhatsApp** ; **projet mécanique/ESRP = bilan** → projets différents selon la source.

---

## MATRICE 2 — CERFA (informations réellement remplies, en texte)

| Information CERFA | Page | Valeur |
|---|---|---|
| En-tête « Dossier préparé pour » | 1 | « AIT ABBAS Abdelkarim » |
| Identité (nom/prénom/date/adresse/NIR) | 2-3 | **vide** (aucune valeur extraite) |
| Organisme payeur / n° allocataire | 3 | **vide** |
| Pension / catégorie / taux invalidité | 6 | **vide** |
| Vie quotidienne (P8 narratif) | 9 | **vide** (aucun texte extrait) |
| Projet de vie / professionnel (P16) | 16 | **vide** |
| Orientation ESAT / RQTH / AAH / PCH / CMI | 17-19 | **NON VÉRIFIÉ** (cases graphiques) |
| AVQ (P6/P7) | 6-7 | **NON VÉRIFIÉ** (cases graphiques) |

> Seule donnée FACILIM confirmée : le **nom en en-tête**. Tout le reste du texte = gabarit non rempli.

---

## MATRICE 3 — TRAÇABILITÉ (élément CERFA → source)

| Information CERFA | Source retrouvée ? | Origine |
|---|---|---|
| « AIT ABBAS Abdelkarim » (en-tête) | Oui | Bilan / dossier pré-rempli |
| Tout autre champ texte | — | **rien rempli** → rien à tracer |
| Cases (AVQ/droits/ESAT) | NON VÉRIFIÉ | (graphique illisible) |

→ **Un seul** élément texte tracé (le nom). Aucune autre information source confirmée dans le CERFA.

---

## MATRICE 4 — PERTES (présent dans les sources, absent du CERFA texte)

| Information | Source | Importance |
|---|---|---|
| Prénom / Nom (champs formulaire P2) | Bilan + WhatsApp | forte |
| Date de naissance 09/05/1988 | Bilan | forte |
| Adresse (Romain Rolland, 13010 Marseille) | Bilan | forte |
| NIR 1 88 05 99 353 028 81 | Bilan **+** WhatsApp | forte |
| N° dossier MDPH 169962 | Bilan | moyenne |
| Suivi psychiatrique (Dr COLLOMBARD) | Bilan | forte |
| Suivi psychologue / AS | Bilan | moyenne |
| Suivi médical (généraliste, cardiologue) | Bilan | forte |
| Absences pour raison de santé | Bilan + WhatsApp | forte |
| Fatigabilité (« fatigue vite ») | Bilan | forte |
| Comportement / propos inadaptés / collectif | Bilan | forte |
| Projet ESAT / La Farigoule / milieu protégé | WhatsApp | forte |
| Projet mécanique / ESRP Lyon / France Travail | Bilan | forte |
| Expression directe de l'usager | Bilan | moyenne |
| Difficultés psychiques et physiques | WhatsApp | forte |

→ **Pertes massives** : la quasi-totalité des informations sources est absente du CERFA (texte).

---

## MATRICE 5 — INVENTIONS (phrase CERFA non retrouvée dans les sources)

| Phrase CERFA | Source retrouvée |
|---|---|
| *(aucune phrase de contenu trouvée en texte hors gabarit)* | — |

→ **Aucune invention textuelle prouvée.** Le CERFA n'invente pas : il est **vide**. (État des cases = NON VÉRIFIÉ → invention par case non contrôlable.)

---

## ANALYSE SPÉCIALE

**Identité** : nom/prénom/date/adresse/NIR tous présents dans le bilan (NIR aussi en WhatsApp) → **CERFA : tous absents** (sauf nom en en-tête). PERDUS.
**Vie quotidienne** : toilette/habillage/repas/courses/déplacements → **jamais déclarés précisément** (WhatsApp vague « psychique et physique ») = NON CONCERNÉ structuré ; fatigue (bilan « fatigue vite ») → PERDUE.
**Santé psychique** : psychiatre/psychologue/absences/troubles → **RICHES dans le bilan**, **0 dans le CERFA** → PERDUES (perte critique).
**Projet professionnel** : ESAT/La Farigoule/milieu protégé (WhatsApp) + mécanique/ESRP/France Travail (bilan) → **CERFA texte vide** ; orientation ESAT (case) = NON VÉRIFIÉ.
**Droits** : AAH/PCH/RQTH/CMI → **jamais demandés par l'usager** (WhatsApp ne mentionne que l'orientation ESAT) ni dans le bilan → NON CONCERNÉ ; présence éventuelle en cases = NON VÉRIFIÉ (serait à surveiller).

---

## QUESTIONS FINALES

**Q1 — Le CERFA est-il fidèle aux sources ?**
**NON (prouvé).** Hors le nom en en-tête, **aucune** information source n'apparaît en texte dans le CERFA. Fidélité ≈ nulle sur le contenu.

**Q2 — Informations critiques disparues ?**
Identité (date/adresse), NIR (pourtant déclaré 2×), suivi psychiatrique, absences santé, fatigabilité, comportement, projet (ESAT + mécanique). Cf. MATRICE 4.

**Q3 — Informations inventées ?**
**Aucune prouvée** en texte (le CERFA est vide, pas faux). Cases NON VÉRIFIÉES.

**Q4 — Bilan PCR correctement exploité ?**
**Exploité (visible CERFA) ≈ 0 %** · **ignoré ≈ 100 %**. Justification : ~9 300 caractères de contenu riche (identité, NIR, suivi psy, projet, comportement) → **0 occurrence** dans le CERFA texte ; dashboard 20/100. *(Réserve : une partie pourrait résider dans `_document_knowledge`/synthese non visibles, et l'upload du bilan sur ce dossier n'est pas confirmé — NON VÉRIFIÉ.)*

**Q5 — Conversation WhatsApp correctement exploitée ?**
**Exploitée (visible CERFA) ≈ 0 %** · **ignorée ≈ 100 %**. Justification : faits déclarés (NIR, difficultés psy/phys, projet ESAT/La Farigoule, pas de formation) → **0 occurrence** dans le CERFA texte ; le NIR (188059935302881) n'apparaît pas sur le formulaire. *(La conversation elle-même a peu collecté : le bot n'a demandé ni nom/prénom/date/adresse, ni AVQ, ni droits ; l'usager a donné des réponses vagues.)*

**Q6 — Goulot principal :**
**F = combinaison (prouvée par les artefacts) :**
- **Collecte** : la conversation WhatsApp n'a quasiment rien collecté de structuré (identité, AVQ, droits jamais demandés/donnés).
- **Exploitation document** : le bilan, très riche, n'apparaît nulle part dans le CERFA (ni identité, ni suivi psy, ni projet).
- **CERFA / aval** : même le nom (présent en en-tête) n'est pas reporté sur le formulaire P2.
→ La perte se produit à **plusieurs points** entre sources et CERFA. **Le sous-pas exact (extraction vs fusion vs persistance vs mapping) n'est PAS observable à partir des seuls artefacts** : il nécessite les traces `[TRACE_COLLECTE]`/`[TRACE_SOURCE_SYNTHESE]` (non présentes pour ce dossier).

---

## RISQUE PRINCIPAL
Un dossier dont **les sources sont riches** (bilan complet + conversation) produit un **CERFA quasi vide** (20/100) : l'effort de collecte et le document professionnel **ne se traduisent pas** dans le dossier MDPH. Dossier **non exploitable** en l'état.

## GOULOT D'ÉTRANGLEMENT
La chaîne **sources → `synthese_json`** : l'information n'atteint pas la synthèse (donc ni dashboard ni CERFA). Localisation du sous-pas = à confirmer par traces.

## VERDICT A/B/C/D/E/F
**F — combinaison** (collecte WhatsApp pauvre + exploitation bilan ≈ nulle + identité non reportée au CERFA), **prouvé par les artefacts** ; isolation d'une cause unique = requiert les traces de production.

## PREUVES CITÉES
- CERFA : seul « Dossier préparé pour : AIT ABBAS Abdelkarim » (p.1) ; `1988/09/05/Romain Rolland/Marronniers/13010/169962/188059935302881/Farigoule/mécani/psychiatre/ESRP/France Travail/fatigue/absent` → **0 occurrence** sur les 21 pages.
- Bilan : NIR « 1 88 05 99 353 028 81 », naissance « 09/05/1988 », « Mme COLLOMBARD la psychiatre », « il fatigue vite », « mécanicien automobile », « EPNAL ESRP à Lyon ».
- WhatsApp : « 188059935302881 », « problème psychique et physique », « l'esat la Farigoule … il peuvent me prendre », formation « Non ».
- Dashboard : « NIVEAU DE COMPLÉTUDE 20/100 », « En collecte », `FAC-DOS--SW-VJVD`.

---

*Rapport de preuve, lecture seule. Aucune supposition au-delà des citations. Cases CERFA, upload bilan et synthese_json = NON VÉRIFIÉ. Aucun correctif proposé.*
