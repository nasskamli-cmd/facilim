# PROTOCOLE_TEST_TERRAIN_DEFINITIF.md — Rejeu instrumenté unique

**Généré le :** 2026-06-07
**Cible :** prod instrumentée `c3081775` (commit `3404fce`) · traces `[TRACE_COLLECTE]` (WhatsApp) + `[TRACE_SOURCE_SYNTHESE]` (document).
**But :** **un seul test réel** qui localise définitivement la rupture DOCUMENT + WHATSAPP → EXTRACTION → FUSION → `synthese_json`.
**Principe :** séparer les deux sources dans le temps (document d'abord, WhatsApp ensuite) pour attribuer chaque trace sans ambiguïté ; couvrir des champs **communs** (pour tester la fusion) **et disjoints** (pour tester la captation).

---

## SCÉNARIO TERRAIN

**Profil :** adulte, cohérent avec le bilan PCR joint (CECORA). Valeurs administratives = **fictives de test** (ne pas utiliser de vraies données).

| Champ | Valeur de test | Source prévue |
|---|---|---|
| Nom / Prénom | CECORA / Marie-Christine | WhatsApp + bilan |
| Date de naissance | 19/01/1966 | WhatsApp + bilan |
| Sexe | Femme | WhatsApp |
| Adresse | 159 Bd Henri Barnier, 13015 Marseille | WhatsApp + bilan |
| Département | 13 | WhatsApp |
| NIR (fictif) | 2 66 01 13 055 042 12 | **WhatsApp uniquement** |
| Organisme payeur | CAF | **WhatsApp uniquement** |
| N° allocataire | 1234567 | **WhatsApp uniquement** |
| Pension invalidité | Oui | WhatsApp |
| Catégorie invalidité | 2 | WhatsApp |
| AVQ toilette | autonome | WhatsApp |
| AVQ habillage | besoin d'aide (→ AIDE_PARTIELLE) | WhatsApp |
| AVQ repas | autonome | WhatsApp |
| AVQ déplacements | besoin d'aide à l'extérieur (→ AIDE_PARTIELLE) | WhatsApp |
| AVQ gestion quotidienne / ménage | besoin d'aide (→ AIDE_PARTIELLE) | WhatsApp + bilan |
| Droits demandés | AAH, PCH, RQTH, CMI invalidité | WhatsApp |
| Projet de vie | préserver sa santé, retrouver un équilibre, à terme métiers du lien | WhatsApp + bilan |
| Santé / fatigue / station debout | fatigabilité, station debout limitée | **bilan (document)** |
| Document joint | **bilan PCR CECORA** (PDF/DOCX) | upload |

> **Champs « disjoints » volontaires** : NIR / organisme / allocataire **uniquement par WhatsApp** (absents du bilan) → testent la captation WhatsApp pure. Santé/fatigue **par le bilan** → teste la captation document pure. Identité + projet + ménage **par les deux** → testent la **fusion** (qui gagne ? doublon ignoré ?).

---

## CONVERSATION WHATSAPP (message par message)

> Envoyer **un message à la fois**, attendre la réponse de l'agent. (L'extraction tourne à chaque tour.)

1. `Bonjour, je veux préparer un dossier MDPH pour moi.`
2. `Je m'appelle Marie-Christine CECORA, je suis une femme, née le 19/01/1966.`
3. `J'habite 159 Bd Henri Barnier, 13015 Marseille (département 13).`
4. `Mon numéro de sécurité sociale est 2 66 01 13 055 042 12.`
5. `Je suis à la CAF, mon numéro d'allocataire est 1234567.`
6. `Je touche une pension d'invalidité de catégorie 2.`
7. `Au quotidien : pour la toilette je suis autonome, mais pour m'habiller j'ai besoin d'aide.`
8. `Pour les repas je me débrouille seule ; par contre pour me déplacer à l'extérieur j'ai besoin d'aide, et pour le ménage aussi.`
9. `Je ressens beaucoup de fatigue et je ne peux pas rester debout longtemps.`
10. `Je voudrais demander l'AAH, la PCH, la RQTH et la carte mobilité inclusion mention invalidité.`
11. `Mon projet : d'abord préserver ma santé et retrouver un équilibre ; plus tard, retravailler dans les métiers du lien.`
12. *(joindre le document)* `Je vous envoie aussi mon bilan PCR.` **+ pièce jointe : bilan PCR CECORA.**

> Ordre recommandé : **messages 1→11 d'abord**, puis **document en dernier (msg 12)** — pour voir si le document **complète** ou est **bloqué** par des clés déjà présentes (test fusion). *(Variante possible : document AVANT la conversation — voir Protocole §B.)*

---

## DONNÉES ATTENDUES (par source)

| Champ | Attendu WhatsApp (`5-EXTRAIT`) | Attendu Document (`5-DOC`) |
|---|---|---|
| nom_prenom | ✅ | ✅ |
| date_naissance | ✅ | ✅ |
| adresse_complete | ✅ | ✅ |
| num_secu | ✅ (masqué `***`) | possible |
| organisme_payeur | ✅ | ❌ (hors liste extraction doc) |
| numero_allocataire | ✅ | ❌ |
| pension_invalidite | ✅ | ❌ |
| categorie_invalidite | ✅ (=2) | ❌ |
| avq_toilette/habillage/repas/deplacements/gestion | ✅ (niveaux) | ❌ (jamais en avq_*) |
| droits (objet) | ✅ {aah,pch,rqth,cmi_invalidite} | ❌ |
| impact_quotidien | possible | ✅ (santé/ménage) |
| diagnostics / restrictions | possible | ✅ |
| _document_knowledge | — | ✅ (limitations_fonctionnelles…) |

---

## LOGS ATTENDUS (grille trace par trace)

### Source DOCUMENT — `[TRACE_SOURCE_SYNTHESE]`
| Trace | Attendu (réussite) | Échec = |
|---|---|---|
| `3-DOC recu … mime=… taille=…o` | présent, taille > 0 | **absent** → doc jamais reçu (**A**) |
| `4-DOC texte_extrait len=… exploitable=True` | len > 1000, exploitable=True | `exploitable=False` / len faible → extraction texte KO (**B**) |
| `5-DOC champs_extraits {…}` | nom_prenom, impact_quotidien, … présents | `∅` → extraction structurée doc vide (**B**) |
| `8-SYNTHESE_AVANT(doc) …` | état avant fusion | — (référence) |
| `10/11-DOC ajoutes=[…] ignores_deja_presents=[…]` | `ajoutes` non vide | tout en `ignores` alors que valeurs réelles → fusion bloquée (**C**) |
| `6-DOC_KNOWLEDGE type=… items=…` | items > 0 | items=0 → bilan non reconnu |
| `9-SAVE(doc) start` puis `13-SAVE(doc) ok completude=…` | les deux présents | `13` absent ou `FAIL` → persistance doc (**D**) |

### Source WHATSAPP — `[TRACE_COLLECTE]`
| Trace | Attendu (réussite) | Échec = |
|---|---|---|
| `1-MSG … tel=****… profil=… msg_len=…` | un par message | absent → message non traité |
| `3-SYNTHESE_AVANT …` | état avant | — (référence) |
| `4-EXTRACT call profil=… history_msgs=…` | présent | absent → extraction non appelée |
| `5-EXTRAIT {…}` | champs du message présents | `∅ (aucun champ extrait)` répété → extraction WhatsApp vide (**B**) |
| `6-REJETES rejetes=[…]` | vide ou champs hors-profil | champs attendus rejetés → whitelist trop stricte (**C**) |
| `7-SYNTHESE_APRES … (completude_avant=…)` | nb_champs ↑, completude ↑ | identique à avant alors que `5-EXTRAIT` plein → fusion bloquée (**C**) |
| `8/9-SAVE start/ok completude=…` | les deux, completude croissante | `9` absent/`FAIL` → persistance (**D**) |

---

## TABLEAU DE CONTRÔLE (à cocher pendant/après le test)

| Champ | Déclaré | Extrait (5-DOC/5-EXTRAIT) | Persisté (9/13-SAVE) | Visible dashboard | Visible CERFA |
|---|---|---|---|---|---|
| nom_prenom | ☐ | ☐ | ☐ | ☐ | ☐ |
| date_naissance | ☐ | ☐ | ☐ | ☐ | ☐ |
| adresse_complete | ☐ | ☐ | ☐ | ☐ | ☐ |
| num_secu (NIR) | ☐ | ☐ | ☐ | ☐ | ☐ |
| organisme_payeur | ☐ | ☐ | ☐ | ☐ | ☐ |
| numero_allocataire | ☐ | ☐ | ☐ | ☐ | ☐ |
| pension_invalidite | ☐ | ☐ | ☐ | ☐ | ☐ |
| categorie_invalidite | ☐ | ☐ | ☐ | ☐ | ☐ |
| avq_toilette | ☐ | ☐ | ☐ | ☐ | ☐ |
| avq_habillage | ☐ | ☐ | ☐ | ☐ | ☐ |
| avq_repas | ☐ | ☐ | ☐ | ☐ | ☐ |
| avq_deplacements | ☐ | ☐ | ☐ | ☐ | ☐ |
| avq_gestion_quotidienne | ☐ | ☐ | ☐ | ☐ | ☐ |
| droits.aah / pch / rqth / cmi_invalidite | ☐ | ☐ | ☐ | ☐ | ☐ |
| projet_de_vie | ☐ | ☐ | ☐ | ☐ | ☐ |
| impact / santé (bilan) | ☐ | ☐ | ☐ | ☐ | ☐ |

---

## MATRICE DE DÉCISION (catégorie unique)

| # | Observation déterminante dans les traces | Catégorie |
|---|---|---|
| 1 | Pas de `3-DOC recu` (et/ou aucun `1-MSG`) | **A** — source non reçue |
| 2 | `3-DOC recu` OK mais `4-DOC exploitable=False` ou `5-DOC ∅` (et/ou `5-EXTRAIT ∅` répété malgré messages riches) | **B** — extraction vide |
| 3 | `5-DOC`/`5-EXTRAIT` pleins, mais `7-SYNTHESE_APRES`/`10-11` ne montrent **pas** les nouveaux champs (`ignores_deja_presents` non vide, ou nb_champs stable) | **C** — fusion défaillante |
| 4 | Champs bien fusionnés (`7-SYNTHESE_APRES` ↑) mais `9/13-SAVE` absent ou `FAIL` | **D** — persistance défaillante |
| 5 | `9/13-SAVE ok` avec les champs ET completude ↑, mais **dashboard/CERFA vides** | **E** — lecture aval |
| 6 | Plusieurs des ci-dessus simultanément | **F** — multi-causes (quantifier lesquelles + sur quels champs) |

> Règle d'attribution : remonter de A vers E ; la **première** étape où l'information attendue disparaît = la catégorie. Si la disparition diffère selon les champs (ex. AVQ en B mais identité en C), c'est **F** avec ventilation par champ.

---

## VERDICT POSSIBLE A/B/C/D/E/F
À remplir **uniquement** après lecture des traces réelles. La catégorie sera **démontrée par les lignes exactes** `[TRACE_COLLECTE]` / `[TRACE_SOURCE_SYNTHESE]`. Aucune conclusion avant.

---

## PROTOCOLE EXACT (jour du test)

**Pré-requis :** prod sur `c3081775` (vérifié Online). Avoir le bilan PCR sous la main.

**A. Déroulé recommandé (sources séparées)**
1. Noter l'**heure de début** (à la minute) et créer/ouvrir le dossier → noter la **référence `FAC-DOS-XXXX`**.
2. Envoyer les **messages 1→11** WhatsApp, un par un, en attendant chaque réponse.
3. Envoyer le **message 12 + pièce jointe (bilan)** en dernier.
4. Ouvrir le **dashboard** → noter la **complétude** affichée + cocher le tableau de contrôle (visible dashboard).
5. **Prévisualiser le CERFA** → cocher (visible CERFA).
6. **Me prévenir immédiatement** (≤ 20 min) avec : référence dossier + heure de début + heure de fin.

**B. Variante (si on veut isoler le document)** : faire l'**upload du bilan AVANT** tout message, observer les `[TRACE_SOURCE_SYNTHESE]`, puis la conversation. (Utile si on soupçonne le chemin document.)

**C. Côté analyse (moi)** : dès ton signal, je lis **exclusivement** les traces `[TRACE_COLLECTE]` / `[TRACE_SOURCE_SYNTHESE]` dans la fenêtre, je remplis le tableau de contrôle + la matrice, et je rends **une seule catégorie A/B/C/D/E/F** avec les lignes de preuve.

> ⏱️ **Critique** : la fenêtre de logs Railway est courte. Le test et la lecture doivent être **rapprochés** (≤ ~20 min). Ne pas attendre.

---

*Préparation du test terrain définitif uniquement. Aucun audit, aucun bug recherché, aucune correction. Données administratives du scénario = fictives de test.*
