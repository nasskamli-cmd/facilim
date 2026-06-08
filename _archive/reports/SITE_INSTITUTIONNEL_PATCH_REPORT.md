# SITE_INSTITUTIONNEL_PATCH_REPORT.md — Patch NIVEAU 1 de `static/index.html`

**Généré le :** 2026-06-07
**Périmètre :** corrections **NIVEAU 1 uniquement** du rapport AUDIT_SITE_INSTITUTIONNEL_FACILIM.md.
**Mode :** `static/index.html` modifié **localement**. Aucun backend / dashboard / moteur / CERFA touché. **Aucun commit, aucun déploiement.**
**Contrôle final :** 0 mention risquée résiduelle (grep) · 10/10 balises `<section>` équilibrées · mentions obligatoires présentes.

---

## 1. PHRASES SUPPRIMÉES / REMPLACÉES (avant → après)

| # | Avant | Après |
|---|---|---|
| 1 | `<title>` « Des dossiers MDPH complets, enfin simples » | « Préparer des dossiers MDPH, plus simplement » |
| 2 | meta « …Bot WhatsApp, **analyse IA CNSA**, CERFA pré-rempli **automatiquement**. » | « …outil d'appui : les propositions sont **vérifiées et validées par un professionnel**. Facilim **ne décide jamais des droits** et **ne remplace ni la MDPH ni la CDAPH**. » |
| 3 | Badge hero « **Référencé CNSA · Conforme RGPD** · Données hébergées en France » | « **Outil d'appui · Validation humaine obligatoire** · Données hébergées en France » |
| 4 | Hero « Notre IA collecte, analyse et **pré-remplit le CERFA** — pour que vous vous concentriez… » | « …chaque dossier est **relu et validé par un professionnel**. Facilim **ne décide jamais des droits**. » |
| 5 | Stat « **94 % des dossiers acceptés par la MDPH** » | « **100 % des dossiers relus et validés par un professionnel** » |
| 6 | Mockup « **Analyse CNSA** 82/100 » | « **Score de complétude** 82/100 » |
| 7 | Mockup « AEEH — **Probabilité 91 %** » / « Orientation IME — **87 %** » | « AEEH — **piste à explorer avec le professionnel** » / « Orientation IME — **à étayer avec la famille** » |
| 8 | Mockup CERFA « Pré-rempli **automatiquement** » | « Pré-rempli — **à vérifier et valider** » |
| 9 | Titre étape « 3 étapes. Un **dossier complet**. » | « 3 étapes. Un **dossier mieux préparé**. » |
| 10 | Étape 2 « …selon le référentiel **CNSA**, **identifient les droits éligibles**… » + badge « 🤖 **Expert GEVA · Juriste** · Coordinateur local » | « …selon le référentiel **GEVA**, repère des **pistes de droits à explorer**… Facilim **ne décide pas : il prépare**. » + badge « 🤖 **Appui méthodologique aligné GEVA · vérifié par le professionnel** » |
| 11 | Étape 3 « **Dossier complet envoyé** » + « …pré-rempli **automatiquement et envoyé** par email » + badge « CERFA pré-rempli · **Email** · Suivi » | « **Dossier préparé, relu et validé** » + « **relu et validé par le professionnel et par la famille avant toute transmission** » + badge « CERFA pré-rempli · **Validation humaine** · Suivi » |
| 12 | B2B « **Dossiers toujours complets** » / « Plus de dossiers renvoyés… » | « **Dossiers plus complets et mieux structurés** » / « Le professionnel **relit et valide avant transmission**. » |
| 13 | B2B « **Conformité RGPD garantie** » / « **Aucune donnée médicale ne transite par WhatsApp**. » | « **Démarche de conformité RGPD** » / « **Conçu pour respecter les exigences RGPD**. …(HDS en cours). » |
| 14 | Sécurité « **Zéro donnée médicale WhatsApp** » | « **Données de santé sécurisées** » |
| 15 | Footer × 3 `<a href="#">Mentions légales / Politique de confidentialité / RGPD</a>` | spans « **— à compléter avant diffusion publique** » (liens morts retirés) |
| 16 | Formulaire `<a href="#">Politique de confidentialité</a>` | « (Politique de confidentialité **à compléter avant diffusion publique**.) » |

## 2. NOUVELLES MENTIONS / SECTIONS AJOUTÉES
- **Section « Autodétermination »** (`#autodetermination`) : Expression des besoins · Projet de vie · Participation · Pouvoir d'agir (la personne/représentant valide).
- **Section « Cadre & confiance institutionnelle »** (`#cadre`) avec les 5 mentions obligatoires :
  - **Facilim ne décide jamais des droits.**
  - **Facilim ne se substitue ni à la MDPH ni à la CDAPH.**
  - Les propositions sont **vérifiées et validées par un professionnel**.
  - La **personne ou son représentant valide** le dossier.
  - **Aucun dossier n'est transmis sans relecture humaine.** + « s'appuie sur le référentiel GEVA/CNSA, **sans label ni endossement officiel** ».
- Mentions « validation humaine » réinjectées dans : meta, badge hero, hero, stats, étapes 2-3, B2B.

## 3. CE QUI N'A PAS ÉTÉ TOUCHÉ (hors NIVEAU 1)
- Chiffres NIVEAU 2 conservés : « **2 500 familles** », « **−75 % de temps administratif** » (à étayer/atténuer en NIVEAU 2).
- Témoignages (mention « taux d'acceptation MDPH » de Pierre L. **conservée** — NIVEAU 2).
- CTA commerciaux (« Commencer un dossier », « Essayer Facilim gratuitement ») — NIVEAU 2.
- Section Sécurité (déjà 🟢), structure visuelle, JS, backend, dashboard, moteurs, CERFA.

## 4. RISQUES RESTANTS (après patch NIVEAU 1)
- **NIVEAU 2 non traité** : chiffres non vérifiés (2 500, −75 %), témoignage « taux d'acceptation », CTA « gratuitement ».
- **Pages légales réelles** : remplacées par « à compléter » → **doivent être créées** avant diffusion publique réelle (obligation légale).
- **Cohérence produit↔discours** : « Données de santé sécurisées / canal dédié » reste à **vérifier** côté produit (NON VÉRIFIÉ).
- **Référentiel GEVA/CNSA** : la formulation « s'appuie sur le référentiel GEVA/CNSA sans label » est prudente ; à valider que l'alignement GEVA est réel.
- **Blocage produit #1** (collecte NIVEAU A non sollicitée) : le discours « dossier mieux préparé » reste en avance sur la complétude réelle tant que ce blocage n'est pas levé en terrain.

## 5. GO / NO GO DIFFUSION INSTITUTIONNELLE
```
GO conditionnel
```
- ✅ **GO pour présenter/échanger** avec ESSMS / ARS / MDPH / CNSA : le positionnement risqué NIVEAU 1 est corrigé (plus de label CNSA, plus de taux d'acceptation MDPH, plus de probabilités de droits, plus de « juriste IA », validation humaine et non-décision affichées partout, autodétermination valorisée).
- ⚠️ **NO GO pour mise en ligne publique large** tant que : (a) les **pages légales réelles** ne sont pas créées, (b) les **chiffres NIVEAU 2** ne sont pas étayés ou retirés, (c) la cohérence « données de santé » n'est pas confirmée.
- 🔴 **Rappel** : non déployé. La version corrigée est **locale** ; la prod sert encore l'ancienne page jusqu'à un `railway up` (sur votre décision).

---

## CRITÈRE DE RÉUSSITE — contrôle
FACILIM est désormais présenté comme un **outil d'appui, de structuration, d'autodétermination et de validation humaine** — **jamais** comme un outil de décision ou de garantie de droits. ✅ (mentions obligatoires présentes, 0 phrase 🔴 NIVEAU 1 résiduelle.)

---

*Patch NIVEAU 1, édition locale de `static/index.html`. Aucun backend/dashboard/moteur/CERFA modifié. Aucun commit, aucun déploiement.*
