# TERRAIN_TEST_CERFA_20_AUDIT.md — Audit terrain CERFA 20 % (WhatsApp/bilan → CERFA)

**Généré le :** 2026-06-07
**Mode :** lecture seule. Aucune correction, aucun code, aucun commit, aucun déploiement.
**Dossier :** `FAC-DOS-M30DPYEX` · statut « En collecte » · **complétude 20/100** (capture dashboard).
**Sources analysées :** CERFA `CF TEST FACILIM 5.pdf` (extraction pypdf) · capture dashboard · bilan PCR `CECORA Marie-Christine.docx`.

## ⚠️ Limites de preuve (à lire en premier)
- **Le texte du chat WhatsApp n'a PAS été fourni** (seule la capture dashboard est disponible). La comparaison porte donc sur **bilan PCR (source connue) ↔ CERFA**. Ce qui a réellement été tapé dans WhatsApp = **NON VÉRIFIÉ**.
- **CERFA aplati** : pypdf lit le gabarit + le **texte dessiné par FACILIM** (prouvé : l'en-tête « CECORA Marie-Christine » est extrait). Les **cases à cocher** (AVQ, droits) sont des marques graphiques **non lisibles** en texte → leur état = **NON VÉRIFIÉ**.
- Logs Railway **non consultés** (non souhaité).

---

## ÉTAPE 1 — INVENTAIRE CERFA (CF TEST 5)
**Méthode :** recherche, sur les 21 pages, des valeurs réellement remplies (texte FACILIM).

| Section CERFA | Champ | Rempli ? | Valeur | Observations |
|---|---|---|---|---|
| En-tête FACILIM (p.1) | Nom usager | ✅ | « CECORA Marie-Christine » | Seul texte FACILIM trouvé |
| P2 Identité | Prénom | ❌ | — | Aucun « Marie » sur le formulaire |
| P2 Identité | Nom / Nom naissance | ❌ | — | Absent du formulaire |
| P2 Identité | Sexe | ❓ (case) | — | Non lisible (case) |
| P2 Identité | Date de naissance | ❌ | — | « 1966 / 19/01 » : 0 occurrence |
| P2 Identité | Adresse / CP / Commune | ❌ | — | « MARSEILLE / 13015 / Barnier » : 0 occurrence |
| P2 | NIR (n° SS) | ❌ | — | Vide (confirmé dashboard) |
| P2 | Organisme payeur (CAF/MSA) | ❌ | — | Libellé gabarit seulement |
| P2 | N° allocataire | ❌ | — | Libellé gabarit seulement |
| P6 Invalidité | Pension / catégorie / taux IPP | ❌/❓ | — | Libellés gabarit ; valeurs absentes |
| P6/P7 AVQ | toilette/habillage/repas/déplacements | ❓ (cases) | — | État cases non lisible |
| P8 Vie quotidienne | Narratif | ❓ | — | Texte overlay non confirmé |
| P16 Projet | Projet de vie | ❓ | — | Non confirmé |
| P17/P18 Droits | AAH/PCH/RQTH/CMI | ❓ (cases) | — | État cases non lisible |
| P19/P20 Aidant | Aidant familial | ❓ | — | Non confirmé |

**Constat clé prouvé :** aucune **valeur texte déclarée** (identité, date, adresse, NIR, organisme, allocataire) n'apparaît sur le formulaire, alors que le texte FACILIM est extractible. → **identité/administratif non reportés**.

---

## ÉTAPE 2 — INVENTAIRE « DÉCLARÉ » (bilan PCR CECORA — source disponible)

| Information | Catégorie | Phrase source (bilan) |
|---|---|---|
| CECORA Marie-Christine | Identité | « NOM – PRÉNOM CECORA Marie-Christine » |
| Née le 19/01/1966 | Identité | « Date de naissance 19/01/1966 » |
| Bât. C2 La Bricarde, 159 Bd Henri Barnier, 13015 Marseille | Identité | « Adresse … 13015 MARSEILLE » |
| Fatigabilité physique et émotionnelle | Santé | « fatigabilité physique et émotionnelle impactant le quotidien » |
| Difficulté station assise/debout prolongée | Santé/AVQ | « difficultés à maintenir une position assise ou debout prolongée » |
| Difficulté pour le ménage | AVQ | « limitations dans certains actes … (en particulier le ménage) » |
| Besoin de répit / épuisement | Aidant/Santé | « besoin important de répit … épuisement … observés » |
| Aidante (mère âgée + petit-fils) | Aidant | « J'accompagne ma mère âgée … mon petit-fils » |
| Parcours pro (restauration, aide à domicile) | Emploi | « j'ai travaillé … dans l'aide à domicile » |
| Suivi équipe emploi France Travail | Emploi | « suivie dans le cadre d'équipe emploi » |
| Priorité santé / pas de reprise immédiate | Projet | « ma priorité est de retrouver un équilibre … préserver ma santé » |

**Absents du bilan (jamais déclarés dans la source) :** NIR · organisme payeur/CAF-MSA · n° allocataire · pension/catégorie/taux d'invalidité · AVQ toilette/habillage/repas (niveaux) · droits explicitement demandés (AAH/PCH/RQTH/CMI).

---

## ÉTAPE 3 — COMPARAISON SOURCE → CERFA

| Information | Déclarée (bilan) | Présente CERFA | Où ? | Verdict |
|---|---|---|---|---|
| Identité (nom/prénom) | ✅ | ❌ (hors en-tête) | — | **PERDUE** |
| Date de naissance | ✅ | ❌ | — | **PERDUE** |
| Adresse / commune | ✅ | ❌ | — | **PERDUE** |
| Fatigabilité / santé | ✅ | ❓ (P8 non lisible) | ? | **NON VÉRIFIÉ** |
| Difficulté ménage | ✅ | ❓ | ? | **NON VÉRIFIÉ** |
| Aidant (mère/petit-fils) | ✅ | ❓ | ? | **NON VÉRIFIÉ** |
| Projet (santé/répit) | ✅ | ❓ | ? | **NON VÉRIFIÉ** |
| Emploi / France Travail | ✅ | ❓ | ? | **NON VÉRIFIÉ** |
| NIR | ❌ | ❌ | — | **NON CONCERNÉE** (jamais déclaré) |
| Organisme payeur / allocataire | ❌ | ❌ | — | **NON CONCERNÉE** |
| Pension/catégorie/taux invalidité | ❌ | ❌ | — | **NON CONCERNÉE** |
| AVQ toilette/habillage/repas (niveaux) | ❌ | ❓ (cases) | — | **NON CONCERNÉE** (non déclaré) |
| Droits AAH/PCH/RQTH/CMI | ❌ | ❓ (cases) | — | **NON CONCERNÉE** |

---

## ÉTAPE 4 — TRAÇABILITÉ TECHNIQUE (pertes / partiels)

| Information | Premier point de rupture | Preuve |
|---|---|---|
| Identité / date / adresse | **Collecte/ingestion** : ces valeurs n'ont pas atteint `synthese_json` (sinon mappées P2) | dashboard NIR/date **vides** ; CERFA sans identité ; v2_bridge mappe nom/prénom/adresse **si présents** dans synthese |
| NIR | **Collecte** : non saisi (champ pro vide) | capture dashboard (champ NIR vide) |
| Organisme / allocataire | **Collecte + mapping** : non déclaré (bilan) ET non mappé V2 même si présent | root cause prouvé (v2_bridge ne propage pas organisme/allocataire) |
| Invalidité (pension/cat./taux) | **Collecte** : non déclaré (bilan) ; non sollicité (absent prompts) | COLLECTE_NIVEAU_A_ROOT_CAUSE.md |
| AVQ structurés / droits | **Collecte** : non déclaré sous forme structurée ; requis=False non exigé | base.py L90/L193-196 |

---

## ÉTAPE 5 — COLLECTE NIVEAU A (réellement demandés ?)
*(Le chat WhatsApp n'étant pas fourni, « Question posée ? » est évalué par le code : driver déterministe + prompts.)*

| Champ NIVEAU A | Question posée ? | Réponse donnée ? | Extrait ? | CERFA ? |
|---|---|---|---|---|
| organisme_payeur | 🟡 thème prompt adulte (L69), pas driver | NON VÉRIFIÉ | possible | ❌ (non mappé V2) |
| numero_allocataire | ❌ (aucun prompt, pas driver) | NON VÉRIFIÉ | possible | ❌ |
| pension_invalidite | ❌ | NON VÉRIFIÉ | possible | ❌ |
| categorie_invalidite | ❌ | NON VÉRIFIÉ | possible | ❌ |
| taux_ipp | ❌ | NON VÉRIFIÉ | possible | ❌ |
| avq_toilette/habillage/repas/déplacements/gestion | 🟡 thèmes prompt (L33), pas driver | NON VÉRIFIÉ | possible | ❓ (cases) |
| droits.aah/pch/rqth/cmi_* | 🟡 thème prompt (L64), pas driver | NON VÉRIFIÉ | possible | ❓ (cases) |

→ Aucun NIVEAU A n'est **exigé** (requis=False) ni **listé par le driver** ; certains sont seulement des **thèmes** de prompt. Cohérent avec un dossier à 20 %.

---

## ÉTAPE 6 — CONTRÔLE ANTI-INVENTION
- **Aucune** affirmation fonctionnelle inventée trouvée en **texte** dans le CERFA (« ne peut se lever seule », « aide toilette/habillage/repas » → 0 occurrence hors libellés gabarit). ✅ cohérent avec l'anti-contamination déployée.
- **État des cases AVQ/droits : NON VÉRIFIÉ** (graphique non lisible). L'anti-invention ne peut être confirmée à 100 % sur les cases sans rendu visuel.
- Classement : aucune invention **prouvée** ; **NON VÉRIFIÉ** sur les cases.

---

## ÉTAPE 7 — DIAGNOSTIC 20 %

| Cause | S'applique ? | Détail |
|---|---|---|
| **Collecte (question jamais posée)** | ✅ **principale** | NIVEAU A non exigé (requis=False) + admin/invalidité hors prompts. Même les requis de base (NIR, date) sont vides → collecte très partielle. |
| **Extraction (déclaré non extrait)** | 🟡 possible | NON VÉRIFIÉ sans le chat ; si l'usager a parlé santé/ménage, ça atterrit en texte libre, pas en structuré. |
| **Persistance (extrait non enregistré)** | 🟡 NON VÉRIFIÉ | non observable sans synthese_json prod. |
| **Mapping (présent synthèse, absent CERFA)** | ✅ confirmé pour | organisme_payeur / numero_allocataire / invalidité (v2_bridge ne les écrit pas). |
| **Produit (hors périmètre)** | ✅ | NIR/organisme/allocataire/invalidité **absents du bilan** → jamais déclarés (cause A). |

**Synthèse du 20 % :** le dossier est pauvre d'abord parce que **peu d'informations sont entrées dans `synthese_json`** (collecte partielle, identité de base non capturée), aggravé par le fait que les champs administratifs/invalidité **n'étaient pas dans la source** et **ne sont pas sollicités**. Le CERFA ne peut pas être riche si la synthèse est vide.

---

## ÉTAPE 8 — VERDICT PRODUIT
**B — brouillon à compléter manuellement** (proche de A en l'état).
Justification : complétude 20/100, identité de base (nom/prénom/date/adresse/NIR) **absente du CERFA**, administratif/invalidité vides. Un professionnel devrait re-saisir l'essentiel → le dossier n'est pas exploitable tel quel pour un dépôt MDPH.

---

## FORMAT FINAL

### CE QUI EST PROUVÉ
- Dossier **20/100**, NIR + date de naissance **vides** (dashboard).
- **Aucune valeur texte déclarée** (identité, date, adresse, NIR, organisme, allocataire) sur le formulaire CERFA (extraction pypdf ; texte FACILIM extractible mais absent).
- **Aucune invention textuelle** d'AVQ/limitations dans le CERFA.
- Cause racine systémique déjà établie : NIVEAU A `requis=False` non exigé + admin/invalidité hors prompts + non mappés V2.

### CE QUI EST DÉCLARÉ
- Le bilan PCR contient identité, santé (fatigue/ménage/station debout), aidant, projet, emploi.
- Les prompts adultes couvrent les **thèmes** AVQ/droits/projet/organisme.

### CE QUI EST NON VÉRIFIÉ
- **Le contenu réel du chat WhatsApp** (non fourni) → impossible de trancher définitivement A vs B vs C.
- L'**état des cases** AVQ/droits du CERFA (graphique).
- Le **synthese_json** réel (prod inaccessible).
- Si le **bilan a été ingéré** (uploadé) et ce qu'il a produit.

### CHAMPS BIEN TRANSFÉRÉS
- Aucun champ **texte déclaré** confirmé sur le formulaire (hors en-tête nom). (Cases NON VÉRIFIÉES.)

### CHAMPS PERDUS
- Identité (nom/prénom), date de naissance, adresse — déclarés (bilan) mais absents du CERFA.

### CHAMPS PARTIELS
- Santé / ménage / projet / aidant / emploi : possiblement en texte libre (P8) — **NON VÉRIFIÉ**.

### CHAMPS INVENTÉS OU AMPLIFIÉS
- Aucun **prouvé** en texte. Cases **NON VÉRIFIÉES**.

### PREMIER POINT DE RUPTURE PRINCIPAL
**La collecte / l'entrée des données dans `synthese_json`** : même l'identité de base n'y est pas arrivée → le CERFA et le dashboard sont vides en amont du mapping.

### EXPLICATION DU 20 %
Synthèse quasi vide → dashboard 20 % → CERFA pauvre. Causes cumulées : (1) collecte partielle (identité de base non capturée) ; (2) NIVEAU A non exigé/non sollicité ; (3) champs admin/invalidité **absents de la source** ; (4) mapping V2 manquant pour organisme/allocataire/invalidité.

### GOULOT D'ÉTRANGLEMENT
**L'alimentation de `synthese_json`** : tant que la collecte (questions + extraction + ingestion document) ne remplit pas la synthèse — à commencer par l'**identité de base** — tout l'aval (cockpit, CERFA) reste vide.

### CORRECTION MINIMALE THÉORIQUE (ne pas coder)
1. **Garantir la capture de l'identité de base** (nom/prénom/date/adresse/NIR) — vérifier pourquoi elle n'arrive pas (chat trop court ? bilan non ingéré ? extraction échouée ?) via un test instrumenté avec logs.
2. **Solliciter le NIVEAU A** (promotion ciblée `requis=True` ou extension `_build_context`) + compléter les prompts (allocataire/invalidité).
3. **Mapper au CERFA** organisme/allocataire/invalidité (sprint MAPPING-NIVEAU-A-CERFA).
4. **Instrumenter** : fournir le chat WhatsApp + logs extraction pour trancher A/B/C définitivement.

### GO / NO GO PILOTE ESSMS
**NO GO.** À 20/100 avec identité de base absente du CERFA, le dossier n'est pas exploitable pour un dépôt. Le socle technique est en place, mais la **collecte réelle n'alimente pas la synthèse** — c'est le verrou à lever avant tout pilote.

---

## Réponse à la question A–E
- **A (non déclaré)** : ✅ pour NIR/organisme/allocataire/invalidité/AVQ-structuré/droits (absents du bilan).
- **B (déclaré non extrait)** : 🟡 **NON VÉRIFIÉ** (chat WhatsApp non fourni) — probable pour identité/santé si elles ont été dites.
- **C (extrait non persisté)** : 🟡 NON VÉRIFIÉ.
- **D (persisté non mappé)** : ✅ confirmé pour organisme/allocataire/invalidité.
- **E (inventé/transformé)** : ❌ non prouvé (aucune invention texte ; cases non vérifiées).
**Dominante : A + collecte insuffisante**, avec une part **D** confirmée sur l'administratif.

---

*Audit terrain, lecture seule. Comparaison bilan↔CERFA (chat WhatsApp non fourni). Cases CERFA et synthese_json prod = NON VÉRIFIÉ. Aucune modification.*
