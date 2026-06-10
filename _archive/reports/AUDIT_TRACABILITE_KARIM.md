# AUDIT_TRACABILITE_KARIM.md — Cartographie de perte de données (dossier FAC-DOS-VKSP2HXQ)

**Généré le :** 2026-06-07
**Nature :** Audit de traçabilité — **lecture seule, aucune correction**.
**Méthode :** croisement (C) code déterministe · (L) logs prod Railway · (P) pièces (CERFA 4.x, bilan PCR).
**Limite d'accès :** la `synthese_json` / `cockpit_pro_json` **réelles de production ne sont pas lisibles** (base prod, accès SSH refusé). Les colonnes « Synthèse/Cockpit » sont donc **inférées** du code + logs, sinon marquées NON VÉRIFIÉ.

> ⚠️ Contexte temporel : le dossier reflète une collecte **court-circuitée** (bug « oui → fin », corrigé tout récemment mais **pas encore rejoué en réel**). Beaucoup de « ❌ collecté » viennent de là.

---

## TABLEAU DE TRAÇABILITÉ

| Champ | Collecté | Extrait | Synthèse | Dashboard | CERFA | Premier point de rupture |
|---|---|---|---|---|---|---|
| nom | ✅ création | ✅ bilan | ✅ `nom_prenom` | ✅ | ✅ « NAIT-ALI » | — |
| **prénom** | ⚠️ bilan (« Karim ») | ✅ bilan | ❌ (écrasé non) | ❌ | ❌ vide | **Création** : `nom_prenom="NAIT-ALI"` sans prénom + merge upload `k not in synthese` (n'écrase pas) |
| sexe/genre | ❌ jamais demandé | ❌ (hors prompt) | ❌ | ❌ | ❌ « genre= » (L) | **Modèle/collecte** : pas de champ création, hors prompt extraction, collecte court-circuitée |
| date naissance | ✅ création/bilan | ✅ | ✅ | ✅ | ✅ | — |
| téléphone | ✅ création | — | ✅ | ✅ | ✅ | — |
| email | ✅ création | ✅ | ✅ | ✅ | ⛔ non-champ CERFA | (email = envoi, pas un champ du formulaire) |
| adresse | ⚠️ bilan | ✅ `adresse_complete` | ⚠️ | ⚠️ | ✅ si extraite | Extraction bilan (tronquée) |
| **NIR / num_secu** | ❌ non fourni | ✅ extractible | ❌ | ❌ | ❌ « NIR non renseigné » (L) | **Collecte** : requis mais jamais fourni/atteint (collecte court-circuitée) |
| **CAF / MSA** (`organisme_payeur`) | ❌ jamais demandé | ❌ hors prompt | ❌ | ❌ | ❌ | **Modèle** : absent de `adult_agent.CHECKLIST` + hors prompt extraction |
| **numéro allocataire** | ❌ jamais demandé (agent) | ❌ hors prompt | ❌ | ❌ | ❌ (mapper lit `P2 10` mais vide) | **Modèle** : absent de `adult_agent.CHECKLIST` |
| médecin traitant | ⚠️ si bilan le cite | ✅ extractible | ⚠️ | — | ⚠️ | Collecte court-circuitée / dépend du bilan |
| mutuelle | ❌ | ❌ | ❌ | — | ❌ | **Modèle** : champ inexistant |
| accident travail | ✅ bilan | ✅ `accident_travail` | ✅ | — | ✅ (dump/narratif) | — |
| douleurs / anxiété | ✅ bilan | ✅ `diagnostics` | ✅ | — | ✅ (narratif P8) | — |
| traitements | ⚠️ requis | ✅ extractible | ⚠️ | ⚠️ | ⚠️ | Collecte court-circuitée |
| fatigabilité | ⚠️ free-text | ⚠️ (dans impact) | ⚠️ | — | ⚠️ narratif | **Modèle** : pas de champ structuré (vit dans `impact_quotidien`) |
| **limitations AVQ** (toilette, habillage, repas, déplacements, ménage, courses, autonomie) | ⚠️ free-text seulement | ⚠️ (dans `impact_quotidien`) | ⚠️ | ❌ | ❌ cases P6/P7 ~0,8 % (QA-6) | **Modèle** : pas de champs AVQ structurés + non déduits auto (cerfa_filler L396) |
| **projet de vie** (projet pro, souhaits, objectifs, besoins accompagnement) | ❌ Section E non atteinte | ⚠️ | ⚠️ `texte_e` (sur données minces) | ⚠️ | ⚠️ P16 partiel | **Collecte** : Section E jamais atteinte (collecte court-circuitée) |
| emploi / RQTH / reconversion / formation | ❌ Section D/E non atteintes | ⚠️ `statut_emploi` extractible | ⚠️ | ⚠️ | ⚠️ | **Collecte** : Sections D/E non atteintes |
| **droits** (AAH/PCH/CMI/RQTH) | ❌ Section E non atteinte | ❌ (hors prompt) | ❌ `droits_demandes` vide | ❌ | ❌ « droits=[] » (L) | **Collecte** : `droits_demandes` jamais collecté (Section E non atteinte) |

Légende : ✅ présent · ❌ absent · ⚠️ partiel · (L)=prouvé par log prod · (P)=pièce.

---

## CE QUI EST PROUVÉ
- **Prénom** : `_split_nom_prenom("NAIT ALI Karim") → ("NAIT ALI","Karim")` (v2_bridge L272-287) est **correct**. La perte vient de l'entrée `nom_prenom="NAIT-ALI"` (sans prénom) + le merge upload `if v and k not in synthese` (main.py L1881) **n'écrase pas** `nom_prenom` déjà posé → « Karim » du bilan ignoré.
- **CAF/MSA/numéro allocataire** : présents dans le schéma + la checklist générique `conversation_engine` (L64, optionnels) + **lus** par `field_mapper` (P2 10 / Case 4), mais **absents de `adult_agent.CHECKLIST`** (collecte adulte active) et **hors du prompt d'extraction upload** (main.py L1842-1861) → jamais collectés.
- **Genre, NIR** : requis dans `adult_agent.CHECKLIST` mais logs prod = « genre= » et « NIR non renseigné ». Pas de champ genre à la création ; NIR non fourni ; collecte court-circuitée → jamais collectés.
- **Droits** : `droits_demandes` est un champ de **Section E** (collecte) ; jamais peuplé → log prod « droits=[] ».
- **Limitations AVQ** : pas de champs structurés dans `adult_agent.CHECKLIST` ; les cases P6/P7 ne sont pas déduites automatiquement (cerfa_filler L396) → QA-6 : couverture AVQ ~0,8 %.
- **Identité de base** (nom, ddn, tél, dept, email) : collectée à la création (`/initiate`), présente.
- **Santé** (accident travail, douleurs, anxiété) : extraite du bilan (`diagnostics`, `accident_travail`), présente (narratif P8 V2 généré — logs prod 1670/2171 chars).

## CE QUI EST DÉCLARÉ (hypothèses)
- `nom_prenom = "NAIT-ALI"` (sans prénom) est **déduit** du fait que le CERFA montre nom = prénom = « NAIT-ALI » et que le split V2 est correct (la seule entrée produisant ce résultat est un token unique majuscule).
- La « case école cochée » : sans accès aux champs du PDF aplati 4.3, l'hypothèse est un **mot-clé** (formation/ESAT/orientation présent dans le bilan) déclenchant une case formation/scolarité (P16 5 / P17 16 / P18 3). **Champ exact NON identifié.**
- Le dashboard ~35 % : reflète les champs pondérés présents (`nom`, `ddn`, `email`, `type`, `dept`, `diagnostics`…) ; les champs lourds collecte-dépendants (`num_secu`, `impact_quotidien`, `droits_demandes`) manquants tirent le score vers le bas.

## CE QUI EST NON VÉRIFIÉ
- Contenu exact de `synthese_json` / `analyse_situation_json` / `cockpit_pro_json` **en production** (base inaccessible) → colonnes « Synthèse/Cockpit » inférées.
- Le calcul arithmétique exact du « 35 % » (nécessite la `synthese_json` prod).
- La **case « école »** exacte (PDF 4.3 aplati, champs AcroForm illisibles : 0/612).
- Le comportement **après le fix collecte** (le dossier audité reflète la collecte court-circuitée d'avant ; pas de rejeu réel post-fix).

---

## RÉPONSES AUX 7 QUESTIONS

1. **Prénom Karim disparaît** : `nom_prenom` posé à la création = « NAIT-ALI » (sans prénom). Le bilan contient « Karim » mais le merge upload (`k not in synthese`) **n'écrase pas** un champ existant. Le split V2 est correct mais reçoit une entrée sans prénom → prénom vide. *(Création + merge upload.)*
2. **NIR** : **demandé en théorie** (requis dans `adult_agent.CHECKLIST`, accepté à la création, extractible du bilan) **mais jamais obtenu** : non saisi à la création, absent/illisible dans le bilan, et collecte court-circuitée avant de le redemander. → **jamais collecté** (pas « stocké puis perdu »).
3. **CAF / MSA** : **jamais demandés** par l'agent adulte (absents de `adult_agent.CHECKLIST`) et **absents du prompt d'extraction**. Le mapper les lit (`organisme_payeur`/`numero_allocataire`) mais ils ne sont jamais alimentés. → **absents du modèle de collecte actif.**
4. **Dashboard 35 %** : champs pondérés (`_calculer_completude_live`, orchestration L110-139) **manquants** = principalement `num_secu` (10), `impact_quotidien` (10), `droits_demandes` (10), + genre/situation_familiale/traitements (requis pour `is_complete`, non pondérés). Tous **collecte-dépendants** → non remplis car collecte court-circuitée. *(Détail arithmétique exact = NON VÉRIFIÉ sans synthese prod.)*
5. **Limitations PCH (AVQ)** : **collectées uniquement en free-text** (`impact_quotidien`), **pas en champs structurés** ; **non extraites** vers des items AVQ ; **non utilisées** comme cases P6/P7 (non déduites auto). → présentes dans le narratif, absentes des cases.
6. **Projet de vie** : **collecte de la Section E court-circuitée** → projet sous-collecté ; `texte_e_projet_vie` généré par le narratif mais sur données minces ; injecté partiellement en P16. → **collecté insuffisamment, injection partielle.**
7. **Case « école » cochée** : **NON VÉRIFIÉ** (champ exact illisible dans le PDF aplati). Hypothèse : mot-clé formation/ESAT/orientation du bilan déclenchant une case formation/scolarité (cerfa_filler P16 5 / P17 16 / P18 3). À confirmer en identifiant la case exacte.

---

## MODE AUDIT FACILIM

### RISQUE PRINCIPAL
Même **après** le correctif collecte, plusieurs champs resteront vides car ils sont **absents du modèle de collecte de l'agent adulte** (genre est requis mais sans source de saisie ; **CAF/MSA, numéro allocataire, limitations AVQ structurées** ne sont jamais demandés ni extraits). Le fix collecte ne ramène QUE les champs que l'agent sait demander.

### GOULOT D'ÉTRANGLEMENT
**La collecte** — sur deux plans : (a) elle était **court-circuitée** (corrigé, à re-valider) ; (b) son **modèle (CHECKLIST agent + prompt extraction)** est **incomplet** (genre sans saisie, pas de CAF/MSA/allocataire/AVQ structurés). Tout l'aval (synthèse, dashboard, CERFA) ne peut afficher que ce que la collecte produit.

### PROCHAIN SPRINT UNIQUE
**Rejeu réel TEST4 post-fix collecte** pour établir la **nouvelle baseline** : mesurer précisément quels champs la collecte corrigée remplit désormais (jusqu'à la Section E / droits). Ce n'est qu'après cette mesure qu'on saura quels « ❌ » étaient dus au court-circuit (résolus) vs aux **vrais gaps structurels** du modèle (CAF/MSA, allocataire, genre, AVQ) — qui feront l'objet du sprint suivant. *(Ne pas corriger le modèle avant d'avoir mesuré l'effet du fix.)*

### PREUVES ATTENDUES (prochain sprint)
- Logs prod du rejeu : questions envoyées par section, `onglet_courant` qui progresse, Section E atteinte.
- `synthese_json` après rejeu : `num_secu`, `impact_quotidien`, `droits_demandes`, `genre` remplis ou toujours vides.
- CERFA régénéré : page E (P17/P18) cochée si droits collectés ; dashboard recalculé.
- Liste finale des champs qui restent vides **malgré** une collecte complète → cible du sprint « modèle de collecte ».

---

*Audit uniquement. Aucun fichier de code modifié, aucun moteur créé, aucun déploiement.*
