# AUDIT_SITE_INSTITUTIONNEL_FACILIM.md — Positionnement public

**Généré le :** 2026-06-07
**Mode :** lecture seule. Aucun fichier modifié, aucun texte changé, aucun commit, aucun déploiement. Diagnostic + propositions uniquement.

---

## 1. PAGES ANALYSÉES
- **`static/index.html`** — landing page publique unique (servie sur `/` → `www.facilim.fr`). Mono-fichier (HTML + Tailwind CDN + JS inline).
- `/login` — page de connexion (non marketing).
- `/dashboards/*` — tableau de bord pro (authentifié, non public).
- **FAQ** : absente. **Mentions légales / Politique de confidentialité / RGPD** : liens présents mais pointant vers `#` (placeholders **morts**).

> Une seule surface marketing publique : `index.html`. Tout l'audit porte dessus.

---

## 2. SYNTHÈSE EXÉCUTIVE

**Verdict : C — RISQUÉ INSTITUTIONNELLEMENT** (et **non diffusable vers ARS / MDPH / CNSA** en l'état).

Le site est commercialement soigné mais comporte plusieurs affirmations qui, devant une autorité publique, posent un risque réel :
- Revendication **« Référencé CNSA »** (non vérifiée) + **« Analyse CNSA »** → laisse croire à un **label/endossement public**.
- **« 94 % des dossiers acceptés par la MDPH »** → laisse croire que FACILIM **influence la décision MDPH/CDAPH**.
- **« AEEH — Probabilité 91 % »**, **« Orientation IME — 87 % »** → laisse croire que FACILIM **prédit/obtient des droits**.
- **« CERFA pré-rempli automatiquement et envoyé »**, **« Dossiers toujours complets »** → promesse d'**automatisation et de complétude garantie**, **sans validation humaine** mentionnée.
- **Absence totale** des mentions clés : *FACILIM ne décide pas*, *ne remplace ni la MDPH ni la CDAPH*, *validation humaine obligatoire*, *autodétermination*.
- **Contradiction** : « Conformité RGPD garantie » vs footer « HDS en cours ».
- **Liens légaux morts** (mentions légales / confidentialité = `#`).

➡️ Acceptable pour une cible **B2C/B2B commerciale**, **inacceptable** pour un dossier **ESSMS/ARS/MDPH/CNSA** sans corrections NIVEAU 1.

---

## 3. TABLEAU PHRASE PAR PHRASE

| Section | Phrase actuelle | Classe | Risque | Proposition |
|---|---|---|---|---|
| `<title>` | « Des dossiers MDPH complets, enfin simples » | 🟡 | « complets » = promesse de complétude | « Des dossiers MDPH mieux structurés, plus simples à préparer » |
| meta desc | « CERFA pré-rempli automatiquement » | 🟡 | automatisation perçue | « aide à la préparation du CERFA, sous validation humaine » |
| meta desc | « analyse IA CNSA » | 🔴 | endossement CNSA implicite | « analyse alignée sur le référentiel GEVA/CNSA » (référentiel ≠ label) |
| Badge hero | **« Référencé CNSA »** | 🔴 | **fausse impression de label public** (si non vérifié) | Supprimer, ou remplacer par « S'appuie sur le référentiel CNSA (GEVA) » **si exact** |
| Badge hero | « Conforme RGPD » | 🟡 | OK si vrai ; cohérence avec « HDS en cours » | « Conforme RGPD · Hébergement de santé (HDS) en cours » |
| Hero H1 | « Le dossier MDPH. Enfin simple. Enfin humain. » | 🟢 | bon (humain) | conserver |
| Hero sous-titre | « Notre IA collecte, analyse et pré-remplit le CERFA » | 🟡 | IA fait tout, pas d'humain | « FACILIM aide à collecter, structurer et préparer le CERFA — chaque dossier est relu et validé par un professionnel » |
| Stats | **« 94 % des dossiers acceptés par la MDPH »** | 🔴 | **influence sur la décision MDPH/CDAPH** + non vérifiable | Supprimer. Remplacer par un indicateur **process** : « dossiers plus complets dès le 1er envoi » (sans taux d'acceptation) |
| Stats | « −75 % de temps administratif » | 🟡 | gain de temps (OK si interne/mesuré) | « jusqu'à X h gagnées par dossier (retour structures pilotes) » |
| Stats | « 2 500 familles accompagnées » | 🟡 | chiffre non vérifiable | conserver **si** justifiable, sinon retirer/atténuer |
| Mockup | **« Analyse CNSA 82/100 »** | 🔴 | score « CNSA » = endossement | « Score de complétude FACILIM 82/100 » |
| Mockup | **« AEEH — Probabilité 91 % »**, **« Orientation IME — 87 % »** | 🔴 | **prédiction/garantie de droits** | « AEEH — piste à explorer / à étayer » (pas de %), ou « éléments en faveur d'une demande AEEH » |
| Mockup CERFA | « Pré-rempli automatiquement » | 🟡 | automatisation | « pré-rempli à partir des informations collectées, à vérifier » |
| Étape 2 | « identifient les droits éligibles (AAH, PCH, AEEH, RQTH…) » | 🟡 | détection de droits | « repèrent les **pistes de droits à explorer** avec le professionnel » |
| Étape 2 | **« 🤖 Expert GEVA · Juriste · Coordinateur local »** | 🔴 | **IA présentée comme juriste/expert** remplaçant le pro | « Appui méthodologique aligné GEVA » (retirer « Juriste/Expert ») |
| Étape 3 | **« Dossier complet envoyé »** + « CERFA pré-rempli automatiquement et envoyé par email » | 🔴 | envoi **sans validation humaine** + complétude garantie | « Dossier préparé, **relu et validé** par le professionnel et la famille avant tout envoi » |
| Témoignage 3 | « amélioré notre taux d'acceptation MDPH » / « fin des dossiers renvoyés » | 🟡 | influence décision MDPH | reformuler en process (« moins de retours pour pièces manquantes ») ou retirer la mention « acceptation » |
| B2B | **« Dossiers toujours complets »** / « Plus de dossiers renvoyés » | 🔴 | **garantie de complétude** | « Dossiers plus complets et mieux structurés » |
| B2B | **« Conformité RGPD garantie »** | 🔴 | « garantie » + contradiction HDS | « Démarche de conformité RGPD ; hébergement HDS en cours » |
| B2B | « Aucune donnée médicale ne transite par WhatsApp » | 🟡 | à vérifier (le bot collecte l'impact/quotidien) | aligner avec la réalité produit (NON VÉRIFIÉ) |
| Footer | « Conforme RGPD » + « HDS en cours » | 🟡 | cohérence | harmoniser le discours conformité |
| Footer | Mentions légales / Politique confidentialité = `#` | 🔴 | **obligation légale non satisfaite** | créer et lier les pages réelles |
| Sécurité (section) | TLS · France · RGPD art.9 · canal dédié santé | 🟢 | bon | conserver |

---

## 4. CE QUI EST BIEN POSITIONNÉ (à conserver)
- 🟢 H1 « **Enfin humain** » — l'humain est valorisé.
- 🟢 Étape 1 : la **famille** répond + **l'accompagnateur** saisit/importe → rôle humain visible.
- 🟢 Section **Sécurité** (TLS, hébergement France, RGPD art. 9, canal santé dédié).
- 🟢 Ton « avec et pour les travailleurs sociaux » (B2B intro) — appui, pas remplacement.
- 🟢 Cible claire ESSMS (IME/SESSAD/ESAT/SAVS/SAMSAH…).

## 5. CE QUI EST AMBIGU (à reformuler)
- 🟡 « pré-remplit le CERFA » / « automatiquement » → ajouter systématiquement « **sous validation humaine** ».
- 🟡 « identifient les droits éligibles » → « **repèrent des pistes de droits à explorer** ».
- 🟡 « −75 % de temps », « 2 500 familles » → étayer ou atténuer (chiffres process, pas d'outcome).
- 🟡 « Aucune donnée médicale via WhatsApp » → vérifier la réalité produit.

## 6. CE QUI EST RISQUÉ (à supprimer / remplacer)
- 🔴 **« Référencé CNSA »** + **« Analyse CNSA »** + **« Score CNSA »** → label public implicite.
- 🔴 **« 94 % des dossiers acceptés par la MDPH »** → influence décision MDPH/CDAPH.
- 🔴 **« Probabilité 91 % » / « 87 % »** de droits → prédiction/garantie de droits.
- 🔴 **« Expert GEVA · Juriste »** (personas IA) → IA remplaçant le professionnel.
- 🔴 **« Dossier complet envoyé »** sans validation humaine + **« Dossiers toujours complets »** / **« RGPD garantie »**.
- 🔴 **Liens légaux morts**.

---

## 7. MESSAGE CIBLE ESSMS (proposé)
> « FACILIM est le **cockpit professionnel** qui aide vos équipes à préparer des dossiers MDPH **plus complets et mieux structurés**, plus vite. La famille s'exprime simplement (WhatsApp ou saisie pro), FACILIM **structure** l'information et **prépare** le CERFA ; **votre professionnel relit, complète et valide**. Vous suivez tous vos dossiers depuis un tableau de bord, avec relances et alertes. FACILIM **ne remplace pas** votre expertise — il la **libère du temps administratif** pour l'accompagnement humain. »

## 8. MESSAGE CIBLE ARS / MDPH / CNSA (proposé)
> « FACILIM est un **outil d'appui à l'expression des besoins** et à la **qualité documentaire** des dossiers MDPH. Il **structure** la parole de la personne et de ses aidants selon le **référentiel GEVA**, **sans jamais décider** des droits. **FACILIM ne se substitue ni à la MDPH ni à la CDAPH** : l'évaluation et la décision restent **entièrement** de leur compétence. Chaque dossier est **relu et validé par un professionnel et par la personne (ou son représentant)** avant toute transmission. L'outil est **traçable** (origine de chaque information), respecte le **RGPD** (données de santé, art. 9) et place l'**autodétermination** de la personne au centre. »

---

## 9. NOUVELLE STRUCTURE RECOMMANDÉE DE LA PAGE
1. **Titre principal** : « Le dossier MDPH, mieux préparé. Toujours validé par l'humain. »
2. **Sous-titre** : « FACILIM aide les structures médico-sociales et les familles à structurer et préparer le dossier MDPH. FACILIM ne décide jamais : le professionnel et la personne valident. »
3. **Section 1 — Le problème** (complexité, temps, dossiers renvoyés pour incomplétude).
4. **Section 2 — La solution / Comment ça marche** (3 étapes : la personne s'exprime → FACILIM structure et prépare → le pro relit/valide → la personne valide).
5. **Section 3 — Pour les ESSMS** (gain de temps, complétude, suivi, coordination — formulé « plus complet », pas « garanti »).
6. **Section 4 — Autodétermination & personnes accompagnées** (expression des besoins, projet de vie, pouvoir d'agir, validation par la personne/représentant).
7. **Section 5 — Cadre & confiance institutionnelle** (ne décide pas / ne remplace pas MDPH-CDAPH / validation humaine / traçabilité / RGPD-HDS / référentiel GEVA-CNSA).
8. **CTA** : « Demander une démonstration » (pas « Commencer un dossier » en hero).
9. **Bandeau de sécurité permanent** : « FACILIM ne décide pas des droits · Validation humaine obligatoire · Données de santé protégées (RGPD) ».
10. **Footer** : mentions légales / confidentialité / RGPD **réels**.

---

## 10. VERSION RECOMMANDÉE DES TEXTES

### Hero
**« Le dossier MDPH, mieux préparé — toujours validé par l'humain. »**
Sous-titre : « FACILIM aide les familles et les structures médico-sociales à exprimer les besoins et à préparer un dossier MDPH complet et structuré. Les propositions sont **relues et validées par un professionnel** ; **FACILIM ne décide jamais des droits**. »

### Problème
« Les dossiers MDPH sont longs, complexes et souvent renvoyés pour pièces manquantes. Les équipes y passent des heures, au détriment de l'accompagnement. »

### Solution
« FACILIM **structure** la parole de la personne (via WhatsApp ou saisie pro), **prépare** le CERFA selon le référentiel GEVA, et **signale** les pistes de droits à explorer. Le professionnel **relit, complète, valide**. Rien n'est transmis sans validation humaine. »

### Pour les ESSMS
« Moins de temps administratif, des dossiers **plus complets et mieux structurés**, un **suivi centralisé** (relances, alertes, coordination d'équipe). FACILIM **libère du temps** pour l'accompagnement — sans remplacer votre expertise. »

### Pour les personnes accompagnées
« Vous (ou votre représentant) **vous exprimez simplement**, à votre rythme. Votre **projet de vie** et vos **besoins** sont au centre. Vous **relisez et validez** votre dossier. Vous restez **décisionnaire** de votre démarche. »

### Pour les autorités
« FACILIM est un outil d'**appui** à la qualité documentaire et à l'expression des besoins. Il **ne décide pas**, **ne se substitue ni à la MDPH ni à la CDAPH**. Chaque information est **traçable** ; la **décision reste à la CDAPH**. »

### Sécurité / validation humaine
« Validation humaine **obligatoire** avant tout envoi · FACILIM **ne décide pas des droits** · Données de santé protégées (RGPD art. 9, hébergement France, HDS en cours) · Traçabilité de l'origine de chaque information. »

### CTA
« **Demander une démonstration** » (B2B) — et en secondaire « Découvrir comment FACILIM appuie vos équipes ».

---

## 11. MENTIONS À AJOUTER (bandeau + section confiance)
- **FACILIM ne décide jamais des droits.**
- **FACILIM ne se substitue ni à la MDPH ni à la CDAPH.**
- **Les propositions sont vérifiées et validées par un professionnel.**
- **La personne (ou son représentant) reste au centre de la démarche et valide son dossier.**
- **Aucun dossier n'est transmis sans relecture humaine.**
- **FACILIM s'appuie sur le référentiel GEVA/CNSA — sans label ni endossement officiel** (sauf preuve formelle).

---

## 12. RISQUES RESTANTS (si publié tel quel)
- **Institutionnel** : « Référencé CNSA » / « Analyse CNSA » / « 94 % acceptés MDPH » → rejet ou défiance ARS/MDPH/CNSA ; soupçon de se substituer à l'évaluation publique.
- **Juridique/réglementaire** : « RGPD garantie » + « HDS en cours » (contradiction) ; **mentions légales/confidentialité absentes** (obligation) ; affichage de **probabilités de droits** (risque de pratique commerciale trompeuse).
- **Produit↔discours** : « Aucune donnée médicale via WhatsApp » vs collecte de l'impact/quotidien (NON VÉRIFIÉ — à aligner).
- **Réputationnel** : promesses « dossier complet » / « toujours complets » non tenables → déception, surtout au regard du **blocage #1** (collecte NIVEAU A non sollicitée) qui limite aujourd'hui la complétude réelle.

## 13. PRIORITÉ DE CORRECTION

### NIVEAU 1 — À corriger AVANT tout contact ESSMS / institution
1. Retirer/qualifier **« Référencé CNSA »**, **« Analyse CNSA »**, **« Score CNSA »**.
2. Supprimer **« 94 % des dossiers acceptés par la MDPH »** et toute mention d'**influence sur la décision**.
3. Supprimer les **probabilités de droits** (« 91 % », « 87 % ») et **« Expert GEVA · Juriste »**.
4. Ajouter partout : **validation humaine obligatoire** + **FACILIM ne décide pas / ne remplace pas MDPH-CDAPH**.
5. Corriger **« RGPD garantie »** (cohérence HDS) et **créer les mentions légales / confidentialité** (liens réels).

### NIVEAU 2 — À corriger avant pilote
6. Reformuler **« Dossier complet envoyé »** → « préparé, relu et validé avant envoi ».
7. Reformuler **« Dossiers toujours complets »** → « plus complets et mieux structurés ».
8. Étayer ou atténuer les **chiffres** (2 500 familles, −75 %, témoignages « acceptation »).
9. Ajouter une **section Autodétermination** explicite.
10. Vérifier/aligner **« zéro donnée médicale WhatsApp »** avec la réalité produit.

### NIVEAU 3 — Amélioration future
11. FAQ institutionnelle (rôle MDPH, validation, données, autodétermination).
12. Page « Cadre & conformité » dédiée (GEVA, RGPD, HDS, traçabilité).
13. Étude de cas ESSMS (process, pas outcome).

---

## CRITÈRE DE RÉUSSITE — réponses
- **Le site est-il institutionnellement sûr ?** Non — **C (risqué)**, non diffusable vers ARS/MDPH/CNSA sans NIVEAU 1.
- **Phrases qui posent problème :** §3/§6 (CNSA, 94 % MDPH, probabilités de droits, Expert/Juriste, dossier complet/garanti, RGPD garantie, liens légaux morts).
- **Comment reformuler FACILIM :** cockpit d'**appui** + **structuration** + **validation humaine** + **ne décide pas**.
- **Gain de temps sans inquiéter :** parler **temps administratif** et **qualité documentaire** (process), jamais **taux d'acceptation** ni **probabilité de droits**.
- **Autodétermination :** section dédiée (expression, projet de vie, validation par la personne).
- **Acceptable ESSMS/ARS/MDPH/CNSA :** oui **après** NIVEAU 1 + NIVEAU 2, avec les mentions du §11.

---

*Audit institutionnel, lecture seule. Aucune modification du site, aucun commit, aucun déploiement. Les chiffres et la mention « Référencé CNSA » sont **NON VÉRIFIÉS** — leur véracité conditionne le passage de 🔴 à 🟡.*
