# VITRINE_PATCH_REPORT.md — Amélioration de la vitrine publique `static/index.html`

**Généré le :** 2026-06-07
**Périmètre :** amélioration éditoriale/visuelle de la landing (sur la base déjà corrigée NIVEAU 1). `static/index.html` modifié **localement**.
**Mode :** aucun backend / dashboard / moteur / CERFA / prompt touché. **Aucun commit, aucun déploiement.**
**Contrôle :** 0 mention interdite (CNSA label, taux MDPH, probabilité de droits, IA juriste, dossier garanti) · 11/11 `<section>` équilibrées · 5/5 `<details>` FAQ équilibrés · 68,1 KB.

---

## 1. CE QUI A ÉTÉ AMÉLIORÉ
- **Réassurance immédiate dès le hero** : ajout d'un bandeau « Facilim ne décide pas · La MDPH/CDAPH décide · Le professionnel vérifie · La personne valide ».
- **Crédibilité institutionnelle plutôt que vanité** : la bande de chiffres marketing (non vérifiables) est remplacée par une bande **« Nos engagements »** (validation humaine, aucune décision automatique, traçabilité).
- **6 axes mis en avant** côté ESSMS : autodétermination (section dédiée existante), gain de temps **implicite**, qualité documentaire, **traçabilité (ajoutée)**, validation humaine, appui ESSMS.
- **FAQ institutionnelle** ajoutée (accordéon natif, sans JS) répondant aux objections ARS/MDPH/CNSA.
- **Navigation** enrichie d'un lien « Le cadre » (#cadre) pour rendre la section de confiance visible.
- **Ton** : suppression des promesses chiffrées non prouvées → discours sobre, factuel, institutionnel.

## 2. PHRASES MODIFIÉES (avant → après)
| Zone | Avant | Après |
|---|---|---|
| Hero — social proof | « **+2 500 familles accompagnées en 2024** » | « **Conçu avec et pour** les structures médico-sociales » |
| Bande chiffres | « **2 500+** familles » / « **−75 %** de temps administratif » | **Supprimés.** Remplacés par « **0** décision automatique — la MDPH/CDAPH décide » et « **100 %** traçabilité de l'origine de chaque information » (la carte « 100 % relus et validés par un professionnel » est conservée) |
| Bande chiffres — titre | (aucun) | Ajout « **Nos engagements — Un cadre clair, au service de la décision publique** » |
| B2B — gain de temps | « Gain de temps immédiat / **De 3h à 20 minutes par dossier** » | « **Du temps rendu à l'accompagnement** / Moins de temps sur l'administratif, plus de temps pour la relation humaine » |
| B2B — déploiement | « **Déploiement en 24h** / opérationnel dès le lendemain » | « **Déploiement simple** / prise en main rapide » (claim 24h retiré) |

## 3. SECTIONS / ÉLÉMENTS AJOUTÉS
- **Bandeau de réassurance** (hero) — 4 garanties non-décisionnelles.
- **Bande « Nos engagements »** — 3 piliers de confiance (validation humaine / 0 décision auto / traçabilité).
- **Feature « Traçabilité des informations »** (section B2B) — « origine de chaque information conservée, dossier vérifiable et lisible par l'équipe MDPH ».
- **Section FAQ institutionnelle** (`#faq`) — 5 questions/réponses :
  1. Facilim remplace-t-il la MDPH ? → Non, ne se substitue pas.
  2. Qui décide des droits ? → La CDAPH ; Facilim ne décide jamais.
  3. Comment éviter les erreurs de l'outil ? → Validation humaine obligatoire + traçabilité.
  4. Que deviennent les données de santé ? → France, démarche RGPD art. 9, HDS en cours.
  5. La personne reste-t-elle actrice ? → Oui, autodétermination + validation.
- **Lien nav « Le cadre »**.

## 4. CE QUI N'A PAS ÉTÉ TOUCHÉ
Backend, dashboard, moteurs, CERFA, prompts métier. Sections existantes conservées : Hero (H1 « Enfin humain »), Comment ça marche, Témoignages, Pour les structures, Autodétermination, Cadre institutionnel, Sécurité, Contact, Footer. Mentions légales = toujours « à compléter avant diffusion publique » (NIVEAU 1, inchangé). JS inline inchangé (la FAQ utilise `<details>` natif).

## 5. RISQUES RESTANTS
- **Témoignages** : la citation de Pierre L. mentionne encore « taux d'acceptation MDPH » (texte attribué, NIVEAU 2) — à reformuler ou retirer avant diffusion publique large.
- **Pages légales réelles** absentes (placeholder) — **obligation** avant mise en ligne publique.
- **Cohérence produit↔discours** : « validation humaine obligatoire » et « traçabilité » doivent correspondre à la réalité produit (gate + audit_trail existent ; à confirmer en conditions réelles).
- **« Déploiement simple »**, ton « rapide » : rester mesuré, ne pas promettre de délai chiffré.
- **Blocage produit #1** (collecte NIVEAU A non sollicitée) : le discours « dossier mieux préparé » reste en avance sur la complétude réelle tant que ce point n'est pas levé en terrain.

## 6. GO / NO GO DIFFUSION
```
GO conditionnel
```
- ✅ **GO pour présentation/démo** à ESSMS / ARS / MDPH / CNSA : page sobre, rassurante, sans promesse risquée ; positionnement « appui + validation humaine + autodétermination + ne décide pas » affiché de bout en bout ; FAQ qui désamorce les objections institutionnelles.
- ⚠️ **NO GO mise en ligne publique large** tant que : (a) **pages légales** créées, (b) **témoignage « taux d'acceptation »** reformulé/retiré, (c) cohérence produit (validation humaine, traçabilité, données de santé) confirmée.
- 🔴 **Non déployé** : la prod sert encore la version précédente jusqu'à un `git push` + `railway up` (sur votre décision).

---

## CRITÈRE DE RÉUSSITE — contrôle
La page **donne envie à un ESSMS de demander une démo** (bénéfices concrets : temps rendu à l'accompagnement, dossiers mieux structurés, suivi, traçabilité) **tout en rassurant ARS/MDPH/CNSA** (ne décide pas, ne remplace pas, validation humaine, autodétermination, données protégées, FAQ dédiée). ✅ Aucune promesse non prouvée ajoutée ; mentions interdites absentes.

---

*Amélioration vitrine, édition locale de `static/index.html` + ce rapport. Aucun commit, aucun déploiement.*
