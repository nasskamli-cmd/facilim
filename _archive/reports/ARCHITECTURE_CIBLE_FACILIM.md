# ARCHITECTURE_CIBLE_FACILIM.md — Comité exécutif : représentation fidèle de la situation de vie

**Généré le :** 2026-06-07
**Base de preuve :** dossiers réels `FAC-DOS-M30DPYEX` (20/100, identité absente du CERFA) et `FAC-DOS--SW-VJVD` (bilan BFP riche + conversation → CERFA vide) ; code réellement exécuté.
**Mode :** conceptuel. Aucun code, aucun framework, aucune implémentation. Partir du **flux réel d'information**.

---

## PARCOURS DE 4 INFORMATIONS RÉELLES (preuve de la rupture)

| Information (source réelle) | SOURCE | COMPRÉHENSION | STRUCTURATION | FUSION | SYNTHÈSE | UTILISATION | CERFA |
|---|---|---|---|---|---|---|---|
| « suivie par un psychiatre » (bilan) | ✅ présent | ✅ lue (texte) | ❌ **aucun champ « suivi psychiatrique »** → reste dans `_document_knowledge` (texte) | ~ (texte) | partielle (texte) | moteurs : texte | ❌ absent CERFA |
| « souhaite intégrer un ESAT » (WhatsApp) | ✅ | ✅ | ❌ pas de **champ orientation/droit structuré** « ESAT » | — | texte (projet) | partiel | ❌/❓ case non vérifiable |
| « fatigabilité importante » (WA + bilan) | ✅ | ✅ | ❌ pas d'**AVQ structuré** (reste `impact_quotidien`/texte) | — | texte | texte | ❌ |
| « besoin d'aide tâches ménagères » | ⚠️ peu/non demandé | ⚠️ | ❌ `avq_gestion_quotidienne` quasi jamais alimenté | — | — | — | ❌ |

**Constat transversal prouvé : la rupture est quasi toujours à la STRUCTURATION.** L'information est **captée et comprise** (surtout via le bilan, qui est riche) mais **jamais convertie en champ structuré exploitable** : elle reste en **texte libre** (`impact_quotidien`, `_document_knowledge`, narratifs), invisible pour le dashboard (qui ne compte que des champs structurés) et le CERFA (qui mappe des champs structurés).

---

## ÉTAPE 1 — CARTOGRAPHIE ACTUELLE

### EXISTE
Collecte (agents + `collecte_schema`), extraction WhatsApp (whitelist), extraction document (liste admin limitée), `_document_knowledge`, `synthese_json` (source de vérité), moteurs 60→100 (eligibility, cdaph, evidence, strength, gate…), cockpit, CERFA V2, audit/historique, instrumentation `[TRACE_*]`.

### CÂBLÉ
`synthese_json` alimente tout l'aval (dashboard, cockpit, moteurs, CERFA via v2_bridge). Deux sources écrivent dedans (WhatsApp via extraction LLM ; document via extraction admin + `_document_knowledge`).

### VISIBLE
Dashboard : **12 champs de base pondérés** (complétude). Cockpit : score CDAPH + droits. CERFA : champs structurés mappés.

### UTILISÉ
Champs **structurés** : identité de base, `droits_demandes` (texte), `avq_*` (si présents, V2), diagnostics, impact_quotidien (texte). `_document_knowledge` (texte) lu par certains moteurs.

### NON UTILISÉ (prouvé)
- **Tout le contenu riche resté en texte** : suivi psychiatrique, absences, comportement, projet (ESAT/mécanique) → présents dans le bilan, **absents du CERFA**.
- **Champs NIVEAU A non comptés** dans la complétude (barème = 12 champs base uniquement).
- **organisme_payeur / numero_allocataire / invalidité** : non mappés au CERFA (v2_bridge).
- La **2ᵉ source** quand la 1ʳᵉ a déjà écrit la clé (fusion « premier écrivain gagne », clé vide bloquante).

---

## ÉTAPE 2 — MODÈLE CONCEPTUEL CIBLE (représentation minimale)

**Une seule représentation structurée de la « situation de vie »**, alimentée par **toutes les sources**, suffisante pour produire synthèse + cockpit + CERFA + stratégie **sans re-questionner** :

- Chaque **fait** = {valeur structurée, **source**, **citation**, **niveau de confiance**, **statut de validation**}.
- Les sources (WhatsApp, document, saisie pro) **convergent** vers ce modèle unique (pas de silos texte parallèles).
- Le **texte libre** (narratif, _document_knowledge) devient une **preuve attachée** à un fait structuré, **jamais** la donnée elle-même.
- Un fait n'est « connu » qu'**une fois** : toute source ultérieure **enrichit ou corrige** (avec traçabilité), au lieu d'être ignorée.

---

## ÉTAPE 3 — CARTE DE CONNAISSANCES FACILIM

| Domaine | Champs nécessaires (min.) | Origine possible | Confiance | Usages aval |
|---|---|---|---|---|
| Identité | nom, prénom, naissance, sexe, NIR | doc, WhatsApp, pro | doc/pro = forte | CERFA P2, dashboard |
| Administration | organisme payeur, n° allocataire, dossier MDPH | WhatsApp, pro | déclarée | CERFA P2 |
| Handicap | nature (psy/physique/cognitif), ancienneté | doc, WhatsApp | doc = forte | CERFA, scoring |
| Santé | diagnostics, suivi (psychiatre/psy/AS/médecin), absences | **doc** | doc = forte | CERFA P8, éligibilité |
| Professionnels | intervenants (psychiatre nommé, AS, tuteurs) | doc | forte | aidants/partage |
| AVQ | toilette, habillage, repas, déplacements, ménage (niveaux) | WhatsApp, doc | déclarée | CERFA P6/P7, PCH |
| Déplacements | mobilité int./ext., transports | WhatsApp, doc | déclarée | CERFA P7 |
| Projet de vie | aspirations, maintien domicile | WhatsApp, doc | déclarée | CERFA P16 |
| Projet professionnel | ESAT/milieu protégé, métier visé, formation/ESRP | **WhatsApp + doc** | déclarée | CERFA D/E, orientation |
| Droits | AAH, PCH, RQTH, CMI, orientation ESMS | WhatsApp, pro | déclarée | CERFA P17, cockpit |
| Aidants | aidant principal, besoins, répit | WhatsApp, doc | déclarée | CERFA F |
| Habitat | type logement, hébergement | WhatsApp | déclarée | CERFA P5 |
| Ressources | pension invalidité, RSA, revenus | WhatsApp, doc | déclarée | CERFA B1 |
| Historique | parcours MDPH, parcours pro | doc | forte | contexte |

> Aujourd'hui, **seuls quelques champs de « Identité/Administration/Droits-texte »** transitent réellement ; les domaines **Santé, Professionnels, AVQ, Projet** restent en **texte non structuré** → perdus pour le CERFA.

---

## ÉTAPE 4 — OÙ L'INFORMATION DISPARAÎT

| Catégorie | S'applique ? | Preuve |
|---|---|---|
| A = non collecté | partiel (WhatsApp) | identité/AVQ/droits jamais demandés en conversation (bot vague) |
| B = collecté mais non compris | non | le LLM « comprend » (résume) |
| **C = compris mais non structuré** | **OUI — dominant** | bilan riche (psychiatre, absences, projet, fatigue) → `_document_knowledge`/texte, **jamais** en champs structurés → absent CERFA (SW-VJVD) |
| D = structuré mais non fusionné | oui (secondaire) | fusion « premier écrivain gagne » / clé vide bloquante (QA prouvée) |
| E = fusionné mais non utilisé | oui (secondaire) | organisme/allocataire/invalidité persistables mais non mappés CERFA |
| F = utilisé mais non visible | marginal | complétude ne compte pas le NIVEAU A |
| G = visible mais non exploité | non observé | — |

**La catégorie C (compris mais non structuré) est le point de perte qui explique « sources riches → CERFA pauvre »**, car elle se vérifie même quand la collecte a réussi (cas du bilan).

---

## ÉTAPE 5 — GOULOT UNIQUE

### GOULOT UNIQUE
**L'absence de STRUCTURATION : l'information comprise reste en texte libre et n'est jamais convertie en champs structurés d'un modèle « situation de vie » partagé.** Il n'existe pas de représentation structurée commune que les deux sources alimentent ; chaque source dépose une tranche partielle (extraction WhatsApp whitelistée / extraction document admin-limitée + `_document_knowledge` texte), et le riche reste du texte inexploité.

### PREUVES
- `FAC-DOS--SW-VJVD` : bilan BFP **présent et riche** (psychiatre Dr COLLOMBARD, absences, projet mécanique/ESRP, fatigue) → **0 occurrence** dans le CERFA ; dashboard 20/100.
- Chemin document : extrait une **liste admin limitée** + `_document_knowledge` (texte) ; **jamais** d'`avq_*`/droits/organisme structurés (prouvé code).
- `FAC-DOS-M30DPYEX` : même les champs de base (identité) absents → 20/100.
- Complétude = 12 champs structurés uniquement ; le texte riche ne la fait pas monter.

### IMPACT
Dossiers réels plafonnés à ~20/100, CERFA non exploitable, effort de collecte et bilans professionnels perdus.

### RISQUE
Tant que le riche reste du texte, **aucun correctif aval (CERFA, moteurs) ne peut produire un dossier fidèle** : on mappe du vide.

---

## ÉTAPE 6 — ARCHITECTURE CIBLE (conceptuelle)

### FLUX D'INFORMATION CIBLE
`Sources (WhatsApp + Documents + Saisie pro) → COMPRÉHENSION → STRUCTURATION en faits {valeur, source, citation, confiance} → FUSION dans le modèle unique « situation de vie » → SYNTHÈSE/COCKPIT/CERFA/STRATÉGIE`.

### SOURCE DE VÉRITÉ UNIQUE
Un **modèle « situation de vie » structuré** (la carte de connaissances). `synthese_json` en est la matérialisation ; **toutes** les sources y convergent ; le dashboard, le CERFA et les moteurs n'en lisent **que** les champs structurés.

### RÈGLES DE FUSION
- Un fait peut être **enrichi/corrigé** par une nouvelle source (jamais « premier écrivain gagne » silencieux).
- Conflit → **conserver les deux** avec source + confiance, et signaler pour validation (ne pas écraser sans trace, ne pas ignorer sur « clé déjà présente même vide »).
- Priorité : preuve documentaire/pro > déclaratif vague, mais la **parole de l'usager** prime sur le projet de vie.

### RÈGLES DE TRAÇABILITÉ
Chaque fait porte **sa source et sa citation**. Aucun fait sans origine. Le CERFA n'affiche que des faits **tracés**.

### RÈGLES DE VALIDATION HUMAINE
Le professionnel **valide/corrige** les faits structurés ; la personne (ou représentant) valide le dossier. Rien n'est transmis sans relecture humaine.

### RÈGLES D'UTILISATION DES NARRATIFS
Le narratif généré est une **mise en forme** d'un fait structuré tracé — **jamais** une source décisionnelle (déjà acté : anti-contamination). Le texte de bilan = **preuve attachée**, pas la donnée.

---

## ÉTAPE 7 — PLAN DE TRANSFORMATION

### CE QUI EST DÉJÀ BON
`synthese_json` comme point de convergence ; moteurs 60→100 fonctionnels sur données présentes ; anti-contamination (narratif ≠ preuve) ; instrumentation `[TRACE_*]` ; collecte unique `collecte_schema` ; validation humaine (gate).

### CE QUI DOIT ÊTRE CONSERVÉ
Tout l'aval (CERFA V2, cockpit, moteurs, gate, audit) — il est sain ; il manque seulement des **faits structurés** à consommer.

### CE QUI DOIT ÊTRE RE-CÂBLÉ (conceptuel, non codé)
La **STRUCTURATION** : convertir le contenu compris (WhatsApp + document) en **champs structurés** du modèle « situation de vie » (notamment Santé, Professionnels, AVQ, Projet), au lieu de le laisser en texte.

### CE QUI DOIT ÊTRE SUPPRIMÉ
Rien d'urgent. À terme : les **silos texte parallèles** (information qui n'existe qu'en `_document_knowledge`/narratif sans fait structuré correspondant). Pas de suppression de moteur.

### CE QUI NE DOIT SURTOUT PAS ÊTRE DÉVELOPPÉ
Nouveau moteur, Vague 2, refonte scoring, nouveau mapping CERFA **avant** que la structuration produise des faits, UX/multi-tenant/quotas/rôles, quick fixes symptomatiques.

### SPRINT UNIQUE PRIORITAIRE
**« STRUCTURATION DE LA SITUATION DE VIE »** : faire en sorte que les informations **comprises** des deux sources deviennent des **faits structurés tracés** dans `synthese_json` (Santé/Professionnels/AVQ/Projet en priorité), **avant** tout travail aval. (Périmètre, fichiers et code = hors de ce document.)

### PREUVES ATTENDUES
Sur un dossier réel instrumenté (`c3081775`) : les traces `[TRACE_*]` montrent que le contenu du bilan/conversation **arrive en champs structurés** dans `synthese_json` → complétude > 20 → CERFA reflétant identité + santé + AVQ + projet, **chaque champ tracé à sa source**.

---

## LIVRABLE FINAL — réponse à la question

**« Quel est aujourd'hui le principal blocage empêchant FACILIM de produire automatiquement une représentation fidèle de la situation de vie à partir des sources réelles ? »**

> **La STRUCTURATION.** Les sources sont riches et **comprises**, mais l'information n'est **jamais convertie en données structurées** d'un modèle « situation de vie » unique : elle reste en **texte libre** (`_document_knowledge`, `impact_quotidien`, narratifs) que ni le dashboard ni le CERFA n'exploitent. **Preuve décisive** : un bilan professionnel complet (`FAC-DOS--SW-VJVD`) produit un CERFA **vide** et une complétude de **20/100** — la collecte et la compréhension ont réussi, mais la structuration n'a pas eu lieu.

*(Catégorie C dominante, avec D/E en aggravation. Le sous-pas technique exact reste à confirmer par les traces de production — la conclusion architecturale, elle, est démontrée par les dossiers réels.)*

---

*Synthèse comité exécutif, conceptuelle. Aucun code, aucune implémentation, aucune hypothèse non étayée. Toutes les affirmations sont adossées aux dossiers réels et aux faits déjà prouvés cette session.*
