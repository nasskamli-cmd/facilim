# VALIDATION_1_TEST4_FAILURE_AUDIT.md — Audit du pipeline de données (dossier FAC-DOS-VKSP2HXQ)

**Généré le :** 2026-06-06
**Nature :** Audit forensique du flux de données — diagnostic AVANT toute correction
**Dossier concerné :** FAC-DOS-VKSP2HXQ (« En collecte », 35 %, droits « – », maturité 0/100)
**Méthode :** analyse du code réel + pièces fournies (CERFA généré + bilan). Aucune extrapolation non marquée.

> ⚠️ **Contrainte d'accès** : le dossier `FAC-DOS-VKSP2HXQ` n'existe PAS dans la base **locale** (`mdph_dossiers.db` — 0 dossier). Il vit dans la base de **production** (facilim.fr / Railway), **inaccessible depuis l'environnement d'audit**. Le dump SQL réel de sa ligne est donc classé **NON VÉRIFIÉ**. Le diagnostic est établi par le **code du pipeline** + les **pièces produites** (CERFA `CF TEST 4 FACILIM.pdf`, bilan `Bilan PCR NAIT ALI.docx`).

---

## CE QUI EST PROUVÉ (code + pièces)

### P1 — Création : les données SONT reçues et persistées
Le frontend `createDossier()` appelle **`POST /api/v1/dossiers/initiate`** (et non `/dossiers/create`) avec : `telephone, email, nom_prenom, date_naissance, notes_pro, numero_securite_sociale, type_dossier, numero_dossier_mdph, aidant_familial`.
`initiate_dossier()` (main.py L1491-1576) **persiste** dans `synthese_json` : `email, nom_prenom, date_naissance, notes_pro, num_secu, type_dossier, departement, langue`. (Preuve : code L1552-1576.)
→ **La création n'est PAS le point de perte** de l'email / nom / type.

### P2 — Le CERFA généré contient bien les données de création/identité
Extraction des champs AcroForm de `CF TEST 4 FACILIM.pdf` (**18 / 612 champs remplis**) :
| Champ CERFA | Valeur écrite |
|---|---|
| `Champ de texte P1 1` (département) | `13` |
| `Case à cocher P1 3` (**réévaluation**) | `/Yes` ✅ |
| `Date A 1/2/3` (naissance) | `05` / `12` / `1969` |
| `Champ de texte P2 1` (nom) | `NAIT-ALI` |
| `Champ de texte P2 3` (**prénom**) | `NAIT-ALI` ⚠️ (doublon — « Karim » perdu) |
| `Champ de texte P2 8/17/18/19` (adresse) | `1 rue des Bateliers,` / `13016` / `MARSEILLE` / `France` |
| `Champ de texte 24` (téléphone) | `0642087770` |
| `Champ de texte P8 1` (**Section B**) | `Diagnostics : anxiété, troubles du sommeil, douleurs | Accident de travail : chute` |

→ **La réévaluation (P1 3) ET l'identité SONT dans le CERFA.** Le CERFA n'est donc pas « vide par perte de données de création ».

### P3 — Le narratif n'a pas été produit : Section B = dump de repli
`Champ de texte P8 1` contient le **fallback brut** (`section_b.py` : « Diagnostics : … | Accident de travail : … ») et non un texte narratif. Cela prouve que `texte_b_vie_quotidienne` était **vide** au moment du mapping → **le moteur narratif n'a pas produit de texte exploitable**. Corrobore le dashboard : **maturité 0/100**, **taux d'enrichissement « – »**.

### P4 — RUPTURE : la collecte se termine au PREMIER message (« oui »)
Le déclencheur de fin de collecte (orchestration_engine L825-830) :
```python
_declencher_narratif = (
    (agent.is_complete(donnees) or _dossier_narratif_exploitable(donnees))
    and service_type != "validation_en_attente"
)
if _declencher_narratif:
    self._generer_narratif_et_qualite(...)   # → demande de validation = "message de fin"
```
Et `_dossier_narratif_exploitable()` (L66-107) renvoie **True** dès que :
```python
a_contenu_fonctionnel = any([diagnostics, impact_quotidien, _verbatim_b,
                             notes_pro,            # ← pré-rempli à la création
                             documents_texte, _document_knowledge…])
a_identite_minimale  = any([nom_prenom, date_naissance])   # ← pré-rempli à la création
return a_contenu_fonctionnel and a_identite_minimale and not déjà_généré and not _narratif_echec
```
**Or `notes_pro` ET `nom_prenom`/`date_naissance` sont déjà présents dès la création** (`/initiate`). Le prédicat est donc **vrai avant toute collecte réelle**. Au **premier « oui »** de l'usager, `_declencher_narratif` = True → génération narrative + demande de validation = **« message de fin »**. La collecte MDPH (diagnostics structurés, impact, droits, sections B/C/D/E) **n'a jamais lieu**.

### P5 — Asymétrie prouvée : `notes_pro` termine la collecte mais ne compte pas dans le score
`_calculer_completude_live()` (L110-139) pondère `nom, ddn, nss, adresse, tel, email, diagnostics, impact, droits_demandes, type, dept` — **`notes_pro` n'y figure pas**. Conséquence : `notes_pro` **déclenche la fin** (P4) mais **n'augmente pas la complétude** → le dossier se fige à **~35 %** (admin uniquement) tout en étant « terminé ».

### P6 — La réévaluation est correctement mappée
`field_mapper.py` L93-97 : `type_dossier == "REEVALUATION"` → `Case à cocher P1 3 = /Yes`. Confirmé dans le PDF (P2). → pas de perte ici.

---

## CE QUI EST DÉCLARÉ (hypothèses, séparées des preuves)

- **H1 — Le bilan a été collé dans `notes_pro`.** Le formulaire de création **n'a aucun champ d'upload** (placeholder : « …Certificat médical joint par email »). Le contenu « Diagnostics : anxiété… | Accident de travail : chute » du dump Section B ressemble à un résumé issu de `notes_pro`. Hypothèse : le pro a collé le bilan dans les notes, ce qui (a) a déclenché P4 et (b) a alimenté le dump. *(À confirmer par la ligne prod.)*
- **H2 — Le narratif a échoué ou a été court-circuité.** Soit `_generer_narratif_et_qualite` a produit un texte vide (clé OpenAI prod ?), soit `_narratif_echec` a été posé. Le résultat observable (Section B dump, maturité 0) est cohérent avec les deux. *(À confirmer par les logs prod.)*
- **H3 — Le « message de fin » perçu = la demande de validation usager** (`_demander_validation_usager`) déclenchée juste après le « oui ».

---

## CE QUI EST NON VÉRIFIÉ (sans extrapolation)

- Dump SQL réel de `synthese_json`, `analyse_situation_json`, `cockpit_pro_json` du dossier (base prod inaccessible).
- Présence/activité de la clé OpenAI en production (impacte la qualité narrative).
- Logs conversationnels WhatsApp réels (état session avant/après « oui »).
- Si un fichier bilan a réellement été **uploadé** dans FACILIM (table `pieces_justificatives`) ou seulement collé/emailé.
- Le contenu exact de `notes_pro` persité pour ce dossier.

---

## POINT EXACT DE RUPTURE

> **Orchestration conversationnelle — `_dossier_narratif_exploitable()` (orchestration_engine.py L66).**
> La donnée ne « disparaît » pas en base : elle **n'est jamais collectée**. Comme `notes_pro` + identité sont pré-remplis dès la création, le prédicat « dossier exploitable » est vrai **avant la collecte**, et le **premier message usager (« oui ») termine la collecte**. Tout l'aval (narratif riche, droits demandés, sections B/C/D/E, complétude, maturité) est donc court-circuité.

C'est un problème de **pipeline / état conversationnel**, pas de moteur métier.

---

## TABLEAU DE TRAÇABILITÉ

| Donnée attendue | Source utilisateur | Reçue backend | Persistée (synthèse) | Présente cockpit | Présente CERFA | Statut | Cause probable |
|---|---|---|---|---|---|---|---|
| Email | création | ✅ (`/initiate`) | ✅ `email` | n/a | ❌ (pas un champ CERFA) | OK (non-CERFA) | Email = envoi, pas un champ du formulaire |
| Type = Réévaluation | création | ✅ | ✅ `type_dossier` | — | ✅ `P1 3=/Yes` | **OK** | — |
| Nom | création/bilan | ✅ | ✅ `nom_prenom` | — | ✅ `P2 1` | OK | — |
| Prénom (Karim) | création/bilan | ✅ | ✅ (dans `nom_prenom`) | — | ⚠️ `P2 3=NAIT-ALI` | **MAL MAPPÉ** | split nom/prénom incorrect dans le mapper |
| Date naissance | création/bilan | ✅ | ✅ | — | ✅ `Date A` | OK | — |
| Bilan (contenu riche) | notes/upload | ✅ (notes_pro / enrich) | ✅ `notes_pro` | partiel | ⚠️ dump brut Section B | **NON EXPLOITÉ** | collecte court-circuitée → narratif non enrichi |
| Diagnostics structurés | WhatsApp | ❌ jamais demandés | ❌ | ❌ | ❌ | **PERDU (jamais collecté)** | fin de collecte au 1er « oui » |
| Impact quotidien | WhatsApp | ❌ jamais demandé | ❌ | ❌ | ❌ Section B vide→dump | **PERDU (jamais collecté)** | idem |
| Droits demandés | WhatsApp | ❌ jamais demandés | ❌ | ❌ vide | ❌ P17/P18 vides | **PERDU (jamais collecté)** | idem |
| Narratifs B/C/D/E | moteur narratif | — | ❌ vides | maturité 0 | ❌ dump/vide | **NON PRODUIT** | déclenché sur données trop minces / échec |

---

## DIAGNOSTIC WHATSAPP — pourquoi « oui » termine la collecte

1. À la création, `synthese_json` contient déjà `notes_pro` + `nom_prenom`/`date_naissance`.
2. `_dossier_narratif_exploitable(donnees)` = `True` **immédiatement** (contenu fonctionnel = `notes_pro` ; identité = `nom_prenom`).
3. Au 1ᵉʳ message usager (« oui »), le handler atteint L825 : `_declencher_narratif = True`.
4. `_generer_narratif_et_qualite()` s'exécute, puis `_demander_validation_usager()` envoie la **demande de validation** → perçue comme « message de fin ».
5. La boucle de collecte (questions diagnostics/impact/droits/sections) **n'est jamais parcourue**.

**Cause racine : un dossier pré-rempli (notes_pro + identité) est jugé « exploitable » AVANT toute collecte, donc le premier message la termine.**

---

## DIAGNOSTIC CERFA — pourquoi le CERFA est presque vide

Le CERFA **n'est pas vide par perte de données** : identité, département, réévaluation, téléphone, adresse y sont. Il est **mince** parce que les champs qui dépendent de la **collecte conversationnelle** n'ont jamais été remplis :
- **Section B (P8 1)** : `texte_b_vie_quotidienne` vide → `section_b.py` retombe sur le **dump brut**.
- **Droits demandés (P17/P18)** : aucun droit collecté → cases vides.
- **Sections C/D/E** : non collectées.
- **Prénom (P2 3)** : bug de split nom/prénom (secondaire).

Tout cela est **en aval** de la rupture P4 (collecte court-circuitée).

---

## CORRECTION MINIMALE PROPOSÉE (périmètre : orchestration / état conversationnel)

**Objectif** : empêcher qu'un dossier **pré-rempli à la création** (notes_pro + identité, sans contenu réellement collecté) soit jugé « exploitable » et termine la collecte au premier message — **sans** toucher aux moteurs, règles MDPH, scoring ou cockpit.

**Changement minimal (orchestration_engine.py, `_dossier_narratif_exploitable`)** : retirer `notes_pro` de la liste `a_contenu_fonctionnel`. `notes_pro` est **pré-rempli à la création** (avant toute collecte) et est le seul signal « fonctionnel » garanti présent d'emblée ; il ne doit pas, à lui seul, déclarer le dossier prêt à clôturer. Les signaux réellement **collectés** (`diagnostics`, `impact_quotidien`, `_verbatim_b`, `documents_texte`, `_document_knowledge`) restent déclencheurs légitimes.

> Effet : un dossier seulement pré-rempli (cas du test 4) **poursuit la collecte** au lieu de se terminer au « oui ». `notes_pro` reste disponible pour le narratif (aucune donnée supprimée) — il ne sert simplement plus de **déclencheur de fin**.

**Hors périmètre de ce correctif (à traiter séparément, documenté) :** le bug de split nom/prénom (P2 3), et la robustesse du moteur narratif en mode dégradé sans LLM.

### Correctif appliqué + preuve (red → green)
Le correctif ci-dessus **a été appliqué** (`orchestration_engine.py`, `_dossier_narratif_exploitable` — `notes_pro` retiré du déclencheur). Preuve par QA-VALIDATION-1-TEST4 :
- **Avant** : `exploitable(pré-rempli seul) = True` → ❌ FAIL (rupture reproduite).
- **Après** : `exploitable(pré-rempli seul) = False`, `exploitable(contenu collecté) = True` → ✅ PASS.
- **Non-régression** : QA-PROD-1→5 + QA-5/7/9/10/11 → tous PASS.

**⚠️ NON VÉRIFIÉ** : la correction est prouvée au niveau du prédicat (unitaire) ; la validation **bout-en-bout WhatsApp réelle** (créer → « oui » → la collecte continue → CERFA enrichi) reste à exécuter en environnement réel (pipeline WhatsApp + clé OpenAI prod non accessibles ici).

---

## TEST REPRODUCTIBLE — QA-VALIDATION-1-TEST4

Voir `app/tests/qa/qa_validation_1_test4.py`. Il rejoue le scénario au niveau du prédicat de rupture :
- **Cas A (bug)** : dossier pré-rempli comme `/initiate` (`notes_pro` + `nom_prenom` + `date_naissance`, sans contenu collecté) → **AVANT** correctif, `_dossier_narratif_exploitable` = True (la collecte se terminerait au 1ᵉʳ message) ; **APRÈS** correctif = False (la collecte continue).
- **Cas B (non-régression)** : dossier avec contenu réellement collecté (`impact_quotidien`/`diagnostics`) → reste exploitable (True) dans les deux cas.
- **Cas C** : `notes_pro` ne contribue pas au score (asymétrie documentée).

---

## RÉSULTAT — origine de l'échec

| Étape | Verdict |
|---|---|
| 1. Création dossier | ✅ OK (données reçues et persistées via `/initiate`) |
| 2. Upload / extraction bilan | 🟦 Probablement collé dans `notes_pro` (H1) — pas d'upload à la création |
| 3. Persistance | ✅ OK (synthese_json pré-rempli) |
| 4. **Orchestration / état conversationnel** | ❌ **RUPTURE** (`_dossier_narratif_exploitable` vrai avant collecte → fin au 1ᵉʳ « oui ») |
| 5. Mapping CERFA | 🟡 Correct pour l'identité/réévaluation ; mince car collecte court-circuitée ; bug prénom (secondaire) |
| 6. Export PDF | ✅ OK (génère ce qui existe) |

**L'échec provient de l'étape 4 (orchestration / état conversationnel).** Les étapes 1, 3, 6 sont saines ; 5 est correct mais affamé par 4.

---
---

# COMPLÉMENT — AUDIT APPROFONDI PAR LECTURE DE CODE (2026-06-06, tour 2)

> Ce complément approfondit et **corrige** certaines hypothèses du rapport initial, à partir de la lecture du code. Aucune nouvelle correction n'a été codée dans ce tour (lecture seule).

## Fichiers lus
- `app/main.py` : `initiate_dossier` (L1491-1600), `upload_document_dossier` (L1810-1899), `_extraire_texte_fichier` (L1747+), `_generer_cerfa_pdf` (L2202+), `telecharger/previsualiser/envoyer_cerfa`.
- `app/engines/orchestration_engine.py` : `_dossier_narratif_exploitable` (L66-107), `_calculer_completude_live` (L110-139), déclencheur narratif (L825-846).
- `app/engines/cerfa_narrative_engine.py` : `generer_textes_narratifs` (L401-472), `_determiner_sections_actives` (L475-490).
- `app/engines/pdf/field_mapper.py` : `_nom`/`_prenom` (L44-59), page 1 type de demande (L79-103), P8 1 (L336-357), P17 droits (L606-620).
- `app/engines/pdf/section_b.py` (chaîne V3 — non active ici), `app/engines/pdf/v2_bridge.py` (L372-382).

## Fonctions analysées (verdict)
| Fonction | Rôle | Verdict |
|---|---|---|
| `initiate_dossier` | création + pré-remplissage synthese_json | ✅ persiste email/nom/ddn/notes/type |
| `upload_document_dossier` | upload + extraction LLM → synthese_json | ⚠️ tronque + n'écrase pas l'existant |
| `_extraire_texte_fichier` | extraction texte (pdf/**docx**/xlsx/txt) | ✅ docx supporté (python-docx) |
| `_dossier_narratif_exploitable` | déclencheur de fin de collecte | ❌ **rupture** (vrai avant collecte) |
| `generer_textes_narratifs` | narratif B/C/D/E via LLM | sur échec → `[ERREUR GÉNÉRATION]` (≠ dump) |
| `field_mapper._prenom` | extraction prénom | ❌ renvoie le **nom** si pas de prénom |
| `field_mapper` P8 1 | texte B | dump niveau 3 ⇒ texte_b ET notes_pro vides |
| `field_mapper` P17 | droits demandés | lit **uniquement** `droits_demandes` |

## Flux réel observé (reconstruit)
1. **Création** `/initiate` → `synthese_json` = {email, departement, type_dossier=REEVALUATION, nom_prenom, date_naissance, …}. `notes_pro` **non saisi** (vide).
2. **Upload bilan** (.docx, 29 000 car.) → `_extraire_texte_fichier` OK → LLM sur **les 4 000 premiers caractères seulement** → extrait `diagnostics="anxiété, troubles du sommeil, douleurs"`, `accident_travail="chute"` → fusionnés dans `synthese_json` (les clés absentes uniquement). `documents_texte` = **2 000 car. max**.
3. **WhatsApp** : 1ᵉʳ « oui ». `_dossier_narratif_exploitable` déjà **True** (car `diagnostics` présent + `nom_prenom`) → la collecte se termine / ou le « oui » est consommé par le consentement. Dans les deux cas la **collecte MDPH n'a pas lieu**.
4. **Narratif** : `texte_b_vie_quotidienne` **jamais persisté** (le CERFA montre le dump niveau 3, pas `[ERREUR GÉNÉRATION]`, pas de narratif).
5. **CERFA** (`field_mapper`) : identité + réévaluation OK ; P8 1 = dump `diagnostics | accident` ; P17/P18 vides ; prénom = nom.

## PREMIER POINT DE RUPTURE PROUVÉ (révisé)
> **`_dossier_narratif_exploitable()` se déclenche sur du contenu PRÉ-COLLECTE.**
> Le rapport initial pointait `notes_pro`. La lecture du dump P8 1 (**niveau 3**, field_mapper L345-357) **prouve que `notes_pro` était VIDE**. C'est donc **`diagnostics`** — extrait du **bilan uploadé** — qui rend le dossier « exploitable » avant toute collecte. ⇒ **Le retrait de `notes_pro` (tour 1) est nécessaire mais INSUFFISANT.** La rupture réelle : le déclencheur confond « contient du contenu fonctionnel » avec « collecte terminée », alors que ce contenu peut venir de la **création** ou d'un **bilan uploadé** — donc être présent **avant le moindre échange WhatsApp**.

## Tableau (révisé) — donnée → reçue → persistée → synthèse → cockpit → CERFA
| Donnée | Source | Reçue | Persistée | Synthèse | Cockpit | CERFA | Statut | Cause prouvée |
|---|---|---|---|---|---|---|---|---|
| Email | création | ✅ | ✅ `email` | ✅ | n/a | ❌ | OK (non-CERFA) | email = envoi |
| Type Réévaluation | création | ✅ | ✅ | ✅ | — | ✅ `P1 3` | OK | field_mapper L93 |
| Nom | création | ✅ | ✅ `nom_prenom="NAIT-ALI"` | ✅ | — | `P2 1=NAIT-ALI` | OK | — |
| **Prénom Karim** | bilan | ✅ (extrait) | ❌ non fusionné | ❌ | — | `P2 3=NAIT-ALI` | **PERDU** | merge L1881 `k not in synthese` + `_prenom` L53-59 |
| Diagnostics | bilan | ✅ (4000 car.) | ✅ `diagnostics` | ✅ | partiel | ⚠️ dump P8 1 | DÉGRADÉ | tronqué + narratif absent |
| Bilan complet (29k) | bilan | ⚠️ 4000/29000 | ⚠️ 2000 car. | partiel | ❌ | ❌ | **TRONQUÉ** | upload L1865/L1887 |
| Impact quotidien | WhatsApp | ❌ jamais demandé | ❌ | ❌ | ❌ | ❌ | PERDU | collecte court-circuitée |
| **Droits demandés** | WhatsApp | ❌ jamais collectés | ❌ | ❌ | ❌ vide | ❌ P17/P18 vides | **PERDU** | `droits_demandes` jamais peuplé |
| Narratif B | moteur | — | ❌ vide | maturité 0 | ❌ | dump | **NON PRODUIT** | déclencheur tiré avant collecte / narratif non persisté |

## Diagnostic WhatsApp (confirmé)
La collecte se termine au 1ᵉʳ message parce que `_dossier_narratif_exploitable` est **vrai dès l'upload du bilan** (`diagnostics` extrait) — pas besoin d'attendre la conversation. Le « oui » atteint soit le déclencheur narratif (L829), soit le flux de consentement (L410-425) ; dans les deux cas la boucle de questions (diagnostics structurés, impact, **droits**, sections) **n'est jamais parcourue**.

## Diagnostic CERFA (complété)
- **P8 1 = dump niveau 3** (field_mapper L345-357) ⇒ `texte_b_vie_quotidienne` **vide** ET `notes_pro` **vide** ; seuls `diagnostics`+`accident_travail` restaient → dump.
- **P17/P18 vides** : `field_mapper` (L606-620) lit **uniquement** `donnees["droits_demandes"]`, jamais peuplé (ni création, ni extraction bilan — le prompt upload n'extrait pas `droits_demandes` —, ni collecte).
- **Prénom perdu** : `_prenom("NAIT-ALI")` → fallback `parts[0]` = `"NAIT-ALI"` (L59) car aucun token minuscule ; et le « Karim » du bilan n'a pas écrasé `nom_prenom` (merge L1881).
- **Deux générateurs CERFA** : le dump existe **uniquement** dans `field_mapper.py`. La chaîne `_generer_cerfa_pdf → v2_bridge → services.cerfa_filler` ne contient pas cette chaîne → le PDF de test 4 a été produit par la voie **field_mapper** (build_field_map). *Quel générateur sert le bouton réel = NON VÉRIFIÉ (à confirmer).*

## Pourquoi un bilan riche finit en CERFA 18/612 (réponse au critère de réussite)
**Chaîne causale prouvée :**
1. Le bilan (29k car.) est **tronqué à 4 000 car.** pour l'extraction LLM → seuls quelques champs superficiels (`diagnostics`, `accident_travail`) sont extraits ; les détails fonctionnels riches sont **perdus dès l'upload** (main.py L1865).
2. Ces champs extraits rendent `_dossier_narratif_exploitable` **True avant toute collecte** → la collecte conversationnelle (impact, **droits**, sections B/C/D/E) **n'a jamais lieu** (orchestration L825-829).
3. Le **narratif** n'est pas produit/persisté → `texte_b` vide → field_mapper retombe sur le **dump** P8 1.
4. `droits_demandes` n'étant jamais peuplé, **toute la page E (P17/P18) reste vide**.
5. Le mapping prénom et la troncature aggravent, mais le facteur dominant est **(2)** : la collecte est court-circuitée, donc 90 % des champs CERFA (qui dépendent de la collecte) restent vides ⇒ **18/612**.

## Correction minimale PROPOSÉE (NON codée — validation requise)
Le périmètre reste **orchestration / état conversationnel** (aucun moteur 60→100, aucune règle MDPH).

1. **Corriger le déclencheur (cause racine)** : `_dossier_narratif_exploitable` ne doit pas clôturer la collecte tant qu'**aucun échange de collecte réel** n'a eu lieu. Proposition : exiger un signal de **progression conversationnelle** (ex. ≥ 1 réponse usager de collecte, ou un onglet réellement validé) en plus du contenu — afin que du contenu **pré-collecte** (notes de création OU bilan uploadé) ne termine pas la collecte au 1ᵉʳ « oui ». *(Le retrait de `notes_pro` du tour 1 traite un sous-cas ; il faut aussi neutraliser le cas `diagnostics`/bilan.)*
2. **Ne pas tronquer le bilan à l'aveugle** (main.py L1865/L1887) : traiter le document par segments ou relever les seuils, pour ne pas perdre 25 000/29 000 caractères dès l'upload.
3. **Prénom** : si `nom_prenom` ne contient qu'un token (pas de prénom), ne pas recopier le nom dans le champ prénom ; et permettre au bilan d'enrichir le prénom manquant (revoir le merge `k not in synthese` pour les champs partiels).
4. **Droits E** : prévoir le peuplement de `droits_demandes` (collecte ou dérivation depuis le bilan) — **hors périmètre strict** (touche la logique droits) → à cadrer séparément.

> Aucune de ces corrections n'est appliquée dans ce tour. Le fallback **n'est pas masqué** : il est exposé comme symptôme de `texte_b` vide.

## NON VÉRIFIÉ (ce tour)
- Quel générateur CERFA (field_mapper vs cerfa_filler) a produit `CF TEST 4 FACILIM.pdf`.
- Si le « oui » a été consommé par le consentement ou par le déclencheur narratif (logs prod requis).
- Valeur exacte de `nom_prenom` persistée (« NAIT-ALI » est **déduit** de `P2 1=P2 3` + logique `_nom`/`_prenom` — déduction forte mais non lue en base prod).
- Contenu exact de `synthese_json`/`cockpit_pro_json` prod (base inaccessible).

---
---

# COMPLÉMENT 2 — CHAÎNE DE GÉNÉRATION CERFA RÉELLE (2026-06-06, tour 3)

> Lecture seule. Aucune correction codée. Élucide **quel générateur** a rempli le CERFA et **la condition exacte** du dump P8 1.

## Fichiers lus
- `app/main.py` : `_generer_cerfa_pdf` (L2320-2485) — **génération réelle** appelée par `telecharger/previsualiser/envoyer`.
- `app/engines/pdf/v2_bridge.py` : `generer_cerfa_depuis_synthese` (L372-393).
- `services/cerfa_filler.py` (V2) : identité P2 (L1246/L1257/L1297), `_mapper_droits` (L342+), section B (L77-155, L903).
- `app/engines/pdf/cerfa_filler.py` (V3) : `CerfaFiller.generer` → `build_field_map` (L117-118, L241-242).
- `app/engines/pdf/field_mapper.py` : P8 1 (L336-357), P2 (L191-193), `_nom`/`_prenom` (L44-59), P17 (L606-620).

## DEUX générateurs CERFA + bascule prouvée
`_generer_cerfa_pdf` (L2414-2485) :
```
try:   moteur V2  (v2_bridge → services/cerfa_filler.remplir_cerfa)        # PRIORITÉ
except Exception as e_v2:
       logger.warning("[CERFA V2] Moteur V2 indisponible (%s) — fallback V3")
       fallback V3 (app/engines/pdf/CerfaFiller → field_mapper.build_field_map)  # DÉGRADÉ
```
**Preuve d'attribution** : le dump exact `Diagnostics : … | Accident de travail : …` n'existe **que** dans `field_mapper.py` (L349/L355). La V2 (`services/cerfa_filler.py`) formule différemment (L903 : « Accident de travail survenu en {année} »). ⇒ Le CERFA de test 4 **a été produit par le fallback V3/field_mapper** ⇒ **le moteur V2 a levé une exception** (silencieuse, niveau `warning`).

> **Nouveau point de rupture (génération)** : l'échec du moteur V2 **n'est pas visible** (avalé en `warning`), et le fallback V3 produit un CERFA **dégradé**. La cause de l'échec V2 (template PDF absent sur Railway ? `synthese_to_v2_dossier` ? `cerfa_expert` ?) est **NON VÉRIFIÉE** (logs prod requis).

## 3. Ordre réel des sources pour P8 1 (chaîne V3/field_mapper, celle qui a tourné)
field_mapper L336-357 :
1. `donnees["texte_b_vie_quotidienne"]` si non vide → **narratif** (priorité 1).
2. sinon `donnees["notes_pro"]` si non vide → **texte collé** (priorité 2).
3. sinon → **dump** `Diagnostics | Traitements | Restrictions | Accident` (priorité 3).

## 4. Condition exacte du fallback dump
`texte_b_vie_quotidienne` **vide** ET `notes_pro` **vide**, avec au moins un de `diagnostics/traitements/restrictions_emploi/accident_travail` présent. ⇒ Observé : `texte_b` vide (narratif non produit) + `notes_pro` vide → dump basé sur `diagnostics`+`accident_travail` (extraits du bilan).

## 5-6. Identité P2 — pourquoi P2 1 = P2 3 = « NAIT-ALI »
field_mapper L191-193 : `P2 1 = _nom(nom_prenom)`, `P2 3 = _prenom(nom_prenom)`.
- `_prenom(full)` (L53-59) : renvoie le **premier token minuscule** ; si aucun → **`return parts[0]`** (= le nom).
- Avec `nom_prenom = "NAIT-ALI"` (un seul token majuscule, pas de prénom) : `_nom` → « NAIT-ALI », `_prenom` → fallback `parts[0]` = « NAIT-ALI ». ⇒ **les deux champs valent NAIT-ALI**.
- Le « Karim » extrait du bilan n'a pas corrigé : merge upload `if v and k not in synthese` (main.py L1881) **n'écrase pas** `nom_prenom` déjà posé.
> (En chaîne V2, l'identité serait mappée par `services/cerfa_filler.py` L1246/L1257 — mais V2 a échoué, donc non exécutée.)

## 7-8. Droits P17/P18 — pourquoi aucune demande E cochée
field_mapper L606-620 : `droits = str(donnees.get("droits_demandes","")).upper()` puis `P17 1=AEEH∈droits`, `P17 2=PCH`, etc. ⇒ **lit UNIQUEMENT `donnees["droits_demandes"]`**. Ce champ n'est peuplé **nulle part** dans le parcours : ni `/initiate`, ni l'extraction bilan (le prompt upload n'extrait pas `droits_demandes`), ni la collecte (court-circuitée). ⇒ `droits_demandes` vide ⇒ **toutes les cases P17/P18 décochées**.
> (En chaîne V2, `_mapper_droits` lit une **liste** `droits` — mais elle serait également vide faute de collecte.)

## 9. Sources attendues vs sources réellement lues par le mapping CERFA
| Source | Attendue | Réellement lue par le mapping ? |
|---|---|---|
| `synthese_json` (→ `donnees`) | ✅ | ✅ **seule source** lue par `build_field_map` / V2 |
| données création | ✅ | ✅ (via synthese_json) |
| `texte_b_vie_quotidienne` | ✅ (clé de synthese) | ✅ lue (mais vide) |
| `droits_demandes` | ✅ (clé de synthese) | ✅ lue (mais vide) |
| `analyse_situation_json` | ❓ | ❌ **JAMAIS lu** par le mapping CERFA |
| `cockpit_pro_json` | ❓ | ❌ **JAMAIS lu** par le mapping CERFA |

→ **Gap structurel** : les droits/besoins éventuellement détectés dans `analyse_situation_json` ou `cockpit_pro_json` ne sont **pas** réinjectés dans le CERFA. Le mapping ne lit que `synthese_json`.

## 10. Premier champ vide responsable
- Pour P8 1 (Section B) : **`texte_b_vie_quotidienne`** vide (puis `notes_pro` vide) → dump.
- Pour la page E : **`droits_demandes`** vide → 0 case cochée.
Ces deux champs sont vides parce que (a) la collecte a été court-circuitée (tour 2) et (b) le narratif n'a pas été persisté ; le tout aggravé par (c) l'échec du moteur V2 → fallback V3 dégradé.

## Diagnostic CERFA — synthèse (tours 1→3)
1. Collecte court-circuitée (rupture orchestration, tour 2) ⇒ `texte_b` et `droits_demandes` jamais remplis.
2. Moteur V2 en échec (tour 3) ⇒ fallback V3/field_mapper, donc dump P8 1 + `_prenom` bug + lecture `droits_demandes`-only.
3. Le mapping ne lit que `synthese_json` (ni analyse, ni cockpit) ⇒ aucun rattrapage possible depuis les couches enrichies.

## Correction minimale PROPOSÉE (NON codée — diagnostic seulement)
Périmètre : génération / mapping (pas de moteur métier, pas de règle MDPH).
1. **Rendre visible l'échec V2** : remonter l'exception `e_v2` (logger.error + flag dossier) au lieu d'un simple `warning`, afin de savoir *pourquoi* la V2 tombe (cause racine du dump à confirmer).
2. **Prénom** : si `nom_prenom` n'a pas de prénom détectable, **ne pas recopier le nom** dans `P2 3` (laisser vide ou marquer `[À COMPLÉTER]`) ; et autoriser le bilan à compléter le prénom manquant (assouplir le merge L1881 pour champs partiels).
3. **Droits E** : prévoir une source de `droits_demandes` (collecte, ou dérivation contrôlée) — **touche la logique droits → à cadrer hors de ce périmètre**.
4. **(Lien tour 2)** corriger le déclencheur de fin de collecte pour que la collecte ait réellement lieu — sans quoi `texte_b`/`droits_demandes` resteront vides quel que soit le générateur.

> Aucune correction appliquée ce tour. Le fallback **n'est pas masqué** : il est exposé comme conséquence de l'échec V2 + des champs vides.

---
---

# DIAGNOSTIC V2 CERFA (2026-06-06, tour 4) — pourquoi V2 échoue avant le fallback

> Lecture seule + **un diagnostic d'exécution non destructif** (rejeu de la chaîne V2 réelle en local, aucune écriture de source). Aucune correction codée.

## Flux V2 attendu
```
_generer_cerfa_pdf (main.py L2414)
  └─ try: v2_bridge.generer_cerfa_depuis_synthese(donnees, service_type, num_mdph)   # L2416
        ├─ synthese_to_v2_dossier(synthese)        # v2_bridge L36 — conversion → clés V2 (nom_enfant, email_famille, departement_code…)
        ├─ analyser_profil_mdph(dossier)           # services/cerfa_expert — enrichissement (try/except interne)
        └─ remplir_cerfa(dossier)                  # services/cerfa_filler L500
              ├─ if not _CERFA_PATH.exists(): raise FileNotFoundError   # L513
              ├─ reader = PdfReader(_CERFA_PATH)                        # L515
              ├─ ~2000 lignes de mapping champs/cases
              └─ writer.write(buffer)  (sur erreur → raise)            # L2544
     except Exception as e_v2:                                          # L2469
        logger.warning("[CERFA V2] Moteur V2 indisponible (%s) — fallback V3", e_v2)
        → fallback V3 (field_mapper)                                    # L2473-2485
```

## Fichiers lus
- `app/main.py` `_generer_cerfa_pdf` (L2320-2485).
- `app/engines/pdf/v2_bridge.py` `generer_cerfa_depuis_synthese` (L372-393), `synthese_to_v2_dossier` (L36+).
- `services/cerfa_filler.py` : `_CERFA_PATH` (L158), `remplir_cerfa` (L500-2545), garde template (L513), `writer.write` (L2541-2545), cochage tolérant (L1466, L2516-2523).

## Dépendances nécessaires
1. **Template PDF** : `services/cerfa_filler.py` → `_CERFA_PATH = <repo>/static/forms/cerfa_15692.pdf`.
   - **Local : présent** (737 343 octets) ✅. (NB : un second template `storage/templates/cerfa_15692_01.pdf` existe mais **n'est PAS** celui utilisé par V2.)
2. **pypdf** (`PdfReader`/`PdfWriter`) — présent en local.
3. **Clé OpenAI** — *non bloquante* : l'expert P8 et la rédaction P8 tombent en repli texte brut sur erreur LLM (401 observé), V2 produit quand même le PDF.

## Conditions d'échec possibles (énumérées) et verdict local
| # | Cause possible | Verdict (prouvé en local) |
|---|---|---|
| 1 | Données d'entrée incomplètes | ❌ **exclue** — V2 réussit sur données TEST4 incomplètes |
| 2 | Conversion `synthese_to_v2_dossier` | ❌ **exclue** — OK (`email_famille='karim@…'`, `prenom_enfant=''`) |
| 3 | **Template PDF introuvable** (`FileNotFoundError` L513) | ⚠️ **candidat n°1 en prod** (présent en local, à vérifier sur Railway) |
| 4 | Champ PDF manquant | ❌ — toléré silencieusement (L1466) |
| 5 | Exception pypdf/pdfrw (`writer.write` L2544) | 🟦 possible si version pypdf différente sur Railway |
| 6 | Bug interne `services/cerfa_filler` | ❌ **exclue** — fonctionne en local sur ces données |
| 7 | **Environnement Railway** | ⚠️ **cause d'ensemble** (englobe 3 et 5) |

## Preuve d'exécution (rejeu chaîne V2 réelle, local)
```
generer_cerfa_depuis_synthese(synthese_TEST4, "adulte", "")  → ✅ 991 543 octets (aucun fallback)
synthese_to_v2_dossier(...)  → nom_enfant='NAIT-ALI'  prenom_enfant=''  email_famille='karim@example.fr'  dept='13'
_CERFA_PATH = .../static/forms/cerfa_15692.pdf  exists=True
```
→ **À données identiques, V2 réussit en local.** L'échec de TEST4 n'est donc **pas** un bug de données/conversion/interne. La variable différenciante est l'**environnement de production**.

## Exception probablement avalée
**`FileNotFoundError: Formulaire CERFA introuvable : .../static/forms/cerfa_15692.pdf`** (L513), levée en prod si `static/forms/` n'est pas déployé sur Railway ou si le CWD/chemin diffère. Candidat secondaire : exception **pypdf** à `writer.write` (L2544) selon la version Railway. Dans les deux cas, capture silencieuse à L2469 (`warning`) → fallback V3 → CERFA dégradé.

## Les logs actuels permettent-ils de connaître la cause ?
**Partiellement.** L2469 journalise `logger.warning("[CERFA V2] Moteur V2 indisponible (%s) — fallback V3", e_v2)` : le message **contient le texte de l'exception** `e_v2`. Donc la cause **figure dans les logs Railway** au niveau `WARNING`, mais :
- **sans traceback** (`exc_info` absent) → pas de pile d'appel ;
- au niveau `warning` (peut être filtré) ;
- **non persistée** (ni `cerfa_audit_log`, ni flag dossier) → invisible côté pro/dashboard, introuvable par dossier.

## Preuve disponible / preuve manquante
- **Disponible** : le code (try/except L2415-2485), le template local présent, V2 fonctionnel en local sur données TEST4.
- **Manquante** : la **ligne de log Railway** `[CERFA V2] Moteur V2 indisponible (…)` du dossier FAC-DOS-VKSP2HXQ (confirmerait l'exception exacte) ; l'état réel du système de fichiers Railway (`static/forms/`).

## Correction minimale PROPOSÉE (NON codée) — rendre l'échec V2 visible
Périmètre : observabilité de la génération (aucun moteur métier, aucune règle, **ne pas améliorer le fallback V3**).
1. **Élever le log** L2469 : `logger.error("[CERFA V2] Échec — fallback V3", exc_info=True)` (traceback complet) au lieu de `warning` sans pile.
2. **Persister la cause** : `_log_cerfa_audit(event_type="cerfa_v2_fallback", details={"exception": str(e_v2), "classe": type(e_v2).__name__})` → traçable par dossier (réutilise l'audit existant).
3. **Vérification de démarrage du template** : au boot, logger/flag si `_CERFA_PATH` (V2) est absent — pour détecter immédiatement un déploiement Railway sans `static/forms/`.

> Aucune de ces actions n'est appliquée ici. Elles servent uniquement à **révéler** la cause racine (probable `FileNotFoundError` template) avant toute correction.

## Réponse au critère de réussite (cause de l'échec V2)
| Cause candidate | Statut |
|---|---|
| 1. Données incomplètes | ❌ exclue (preuve locale) |
| 2. Conversion `synthese_to_v2_dossier` | ❌ exclue (preuve locale) |
| 3. **Template PDF introuvable** | ⚠️ **cause probable n°1** (à confirmer via log Railway) |
| 4. Champ PDF manquant | ❌ toléré silencieusement |
| 5. Exception pypdf/pdfrw | 🟦 possible (version Railway) |
| 6. Bug interne `cerfa_filler` | ❌ exclue (preuve locale) |
| 7. **Environnement Railway** | ⚠️ **cause d'ensemble** (3 et/ou 5) |

**Conclusion : l'échec V2 est environnemental (prod), pas un bug de données/code — très probablement le template `static/forms/cerfa_15692.pdf` absent sur Railway (FileNotFoundError L513), capture silencieuse L2469.** La confirmation définitive exige la ligne de log Railway, que la correction minimale n°1+2 rendrait immédiatement visible.

> **⚠️ CETTE CONCLUSION (template/environnement) EST RÉFUTÉE PAR LE TOUR 5 PLUS BAS.** Les logs Railway réels montrent une cause différente : `no such column: version`. Voir « DIAGNOSTIC RAILWAY CERFA V2 ».

---
---

# DIAGNOSTIC RAILWAY CERFA V2 (2026-06-06, tour 5) — cause racine confirmée par les logs prod

> Accès Railway **authentifié** (`nasskamli@gmail.com`, projet `facilim`/production, service en ligne, https://www.facilim.fr). Lecture seule : `railway logs` + requête SQLite locale. **Aucune modification de code, de Railway, de dépendances, ni du fallback.**

## EXCEPTION EXACTE (copie verbatim des logs Railway)
```
2026-06-05 21:00:21,759 | WARNING  | facilim.app | [CERFA V2] Moteur V2 indisponible (no such column: version) — fallback V3
2026-06-06 19:22:03,386 | WARNING  | facilim.app | [CERFA V2] Moteur V2 indisponible (no such column: version) — fallback V3
```
Commande : `railway logs -d -n 500 --filter "CERFA V2"` (service `facilim`, env `production`).
Le 2ᵉ enregistrement — **2026-06-06 19:22:03 UTC = 21:22 heure locale** — coïncide avec la « dernière activité 06/06/26 21:22 » du dossier **FAC-DOS-VKSP2HXQ** ⇒ c'est la génération CERFA de TEST4.

## CE QUI EST PROUVÉ
1. **L'exception réelle en prod n'est PAS un problème de template ni de pypdf** : c'est `no such column: version` (erreur SQLite `OperationalError`). → **Causes 3 (template) et 5 (pypdf) RÉFUTÉES.**
2. **La colonne `version` n'existe pas dans `dossiers`** — ni en prod, ni **en local** : `PRAGMA table_info(dossiers)` → `'version' in cols = False` (47 colonnes). `models.py` ne définit que `version_politique`, `cerfa_version` (et `dossier_version` dans `cerfa_validations`), **jamais** `dossiers.version`.
3. **Pourquoi la colonne manque** : migration `008_cerfa_validations.sql` **L70** = `ALTER TABLE dossiers ADD COLUMN version INTEGER DEFAULT 1;`, **précédée de 5 lignes de commentaires `--` (L65-69) sans `;` intercalé**. Le découpeur de migrations (`migrations/__init__.py`) filtre tout segment `startswith("--")` → **l'`ALTER` est avalé dans le segment commentaire et n'est jamais exécuté**. (Même classe de bug que celle corrigée en PROD-1 pour `cockpit_pro_json`, et signalée historiquement pour `analyse_situation_json`.) Migration 008 est marquée « appliquée » mais la colonne n'a jamais été créée.
4. **Le déclencheur exact** : `main.py` `_generer_cerfa_pdf` **L2444** exécute `SELECT version FROM dossiers WHERE id = ?` — **à l'intérieur du bloc `try` V2, APRÈS** une génération PDF V2 réussie (pour journaliser la version dans l'audit). Cette requête lève `no such column: version` → capturée L2469 → **le bon PDF V2 est jeté** → fallback V3 (dump).
5. **Reproduction LOCALE identique** : `SELECT version FROM dossiers` en local → `OperationalError: no such column: version` — **exactement le message des logs prod**. ⇒ **le bug se reproduit en local** : il n'est **pas** environnemental.

## Pourquoi le comportement « diffère » entre local et Railway (critère 4)
**Il ne diffère PAS.** Le moteur V2 tombe en fallback V3 **aussi bien en local qu'en prod**, pour la même raison (`no such column: version`). Le faux signal « V2 réussit en local » du tour 4 venait de ce que j'appelais `generer_cerfa_depuis_synthese()` **directement**, **en contournant** le `SELECT version` de `_generer_cerfa_pdf`. Le **moteur de remplissage V2 fonctionne** ; c'est `_generer_cerfa_pdf` qui le fait échouer via une requête sur une colonne inexistante.

## CE QUI EST DÉCLARÉ (hypothèses)
- La génération PDF V2 réussit bel et bien avant le `SELECT version` (le code calcule les hashes et la page de couverture avant L2444) ; l'exception survient donc **après** un PDF V2 valide qui est **gaspillé**. *(Cohérent avec le code ; non capturé en bytes car l'exception jette le résultat.)*

## CE QUI EST NON VÉRIFIÉ
- Le **traceback complet** prod (le log est au niveau `WARNING` sans `exc_info`) — non nécessaire, la cause est déjà identifiée et reproduite.
- Confirmation que `dossiers.version` est aussi absente dans la base **PostgreSQL** prod (le log `no such column` est un message de type **SQLite** → la prod tourne probablement encore en **SQLite sur le volume `/data`**, pas PostgreSQL — à confirmer, mais non bloquant pour la cause).

## DÉPENDANCES PDF (étape 4) — désormais hors-cause
Non déterminantes : l'exception n'est pas liée à pypdf/pdfrw. Le moteur V2 ouvre et remplit le template sans erreur (prouvé en local, 991 543 octets). Comparatif de versions non nécessaire pour cette cause racine.

## CAUSE RACINE (une seule réponse)
> **AUTRE — bug de code/migration (non environnemental).**
> La colonne `dossiers.version` n'a jamais été créée (ALTER de la migration 008 avalé par le découpeur de migrations à cause des commentaires en tête de segment). `_generer_cerfa_pdf` (L2444) interroge `SELECT version FROM dossiers` **dans le bloc try V2**, ce qui lève `no such column: version` **après** une génération V2 réussie, déclenchant le fallback V3 dégradé — **sur tous les environnements**, prod comme local.

## Réponse au critère de réussite
1. **Exception exacte en prod** : `no such column: version` (logs verbatim ci-dessus, 2026-06-06 19:22:03 UTC).
2. **Cause racine** : colonne `dossiers.version` manquante (migration 008 non appliquée à cause du découpeur) + `SELECT version` dans le try V2 (main.py L2444).
3. **Pourquoi V3 activé** : l'`OperationalError` est capturée à L2469 (`except`) → le PDF V2 déjà généré est abandonné → fallback V3 (dump P8 1, droits vides, bug prénom).
4. **Local vs Railway** : aucune différence — bug reproduit à l'identique en local.

## Correction minimale PROPOSÉE (NON codée — diagnostic uniquement)
Deux options, à valider avant tout codage (périmètre infra/migration, pas de moteur métier) :
- **(a) Créer la colonne manquante** : corriger la migration 008 pour que l'`ALTER ... ADD COLUMN version` ne soit plus avalé (placer l'`ALTER` en tête de segment, comme le correctif PROD-1), **et/ou** ajouter `version` au filet `_COLONNES_PHASE3` de `main.py` (déjà utilisé pour garantir des colonnes au démarrage). → la cause racine disparaît partout.
- **(b) Rendre `_generer_cerfa_pdf` tolérant** : sortir le `SELECT version` (audit de version) du bloc `try` V2, ou l'entourer d'un `try/except` local, pour qu'une erreur d'audit **ne fasse plus échouer une génération V2 réussie**.
- **(transverse)** Corriger le **découpeur de migrations** lui-même (cause systémique : 008 `version`, historiquement 010, évité de justesse en PROD-1) — mais cela dépasse le périmètre « minimal ».

> Aucune de ces corrections n'est appliquée. Le fallback V3 n'est pas masqué. La preuve (log prod + repro local) est suffisante pour décider de la correction.

---
---

# CAUSE RACINE CERFA V2 (2026-06-06, tour 6) — confirmation ligne par ligne

> Lecture seule. Aucune correction, aucune migration, aucun changement Railway/fallback/moteur.

## ÉTAPE 1 — Localisation du code (preuve)
| Élément | Valeur |
|---|---|
| Fichier | `app/main.py` |
| Fonction | `_generer_cerfa_pdf(dossier_id, db)` |
| Ligne | **L2444-2446** |
| Requête exacte | `SELECT version FROM dossiers WHERE id = ?` |
C'est la **seule** lecture de `dossiers.version` du flux ; elle alimente `_version_val` (L2447) puis le champ `version` de `_log_cerfa_audit` (L2458). → **usage purement audit/traçabilité**, pas génération PDF.

## ÉTAPE 2 — Périmètre du try V2 (cartographie réelle, L2415-2485)
```
try (L2415):
  L2417  pdf_bytes = generer_cerfa_depuis_synthese(...)   ← GÉNÉRATION PDF V2  (métier V2)
  L2421  _synthese_hash = sha256(donnees)                 ← AUDIT
  L2424  _cerfa_pdf_hash = sha256(pdf_bytes)              ← AUDIT  (preuve que pdf_bytes est valide ici)
  L2436  pdf_bytes = _ajouter_page_couverture(pdf_bytes)  ← MISE EN FORME (try/except local propre)
  L2444  SELECT version FROM dossiers                     ← AUDIT  ←★ EXCEPTION "no such column: version"
  L2448  _log_cerfa_audit(... version=_version_val ...)   ← AUDIT  (jamais atteint)
  L2463  open(output_path,"wb").write(pdf_bytes)          ← PERSISTANCE  (jamais atteint)
  L2467  return output_path, pdf_bytes                    ← (jamais atteint)
except e_v2 (L2469): warning → FALLBACK V3 (L2472-2485)
```
**Découpage par responsabilité :**
- **V2 (génération)** : L2417 (+ L2436 mise en forme). ✅ réussit.
- **Audit** : L2421-2424, L2444-2461. ❌ `SELECT version` (L2444) échoue.
- **Persistance** : L2463-2464. ⛔ jamais atteinte.
Le `try` **englobe à tort l'audit ET la persistance** dans le même bloc que la génération V2 ⇒ une erreur **d'audit** fait échouer toute la branche V2.

## ÉTAPE 3 — Schéma local (preuve)
`PRAGMA table_info(dossiers)` → **47 colonnes**, et **`'version' in colonnes = False`**.
Colonnes proches présentes : `version_politique`, `cerfa_version` (et `dossier_version` dans la table `cerfa_validations`). **Colonne `version` : ABSENTE.**
→ **Réponse : NON, la colonne `version` n'existe pas** (en local).

## ÉTAPE 4 — Migrations (preuve)
- Migration censée créer la colonne : **`008_cerfa_validations.sql`**, **ligne 70** : `ALTER TABLE dossiers ADD COLUMN version INTEGER DEFAULT 1;`
- **Existe ?** OUI (le fichier et l'instruction existent).
- **Appliquée localement ?** Migration 008 marquée appliquée, **mais l'ALTER n'a PAS été exécuté** : l'instruction (L70) est précédée de **5 lignes de commentaires `--` (L65-69) sans `;`**. Le runner (`migrations/__init__.py`) filtre `if not s.strip().startswith("--")` → le segment entier (commentaires **+** ALTER) est **rejeté**.
- **Appliquée en production ?** Même fichier de migration, **même rejet** → colonne absente en prod (cohérent avec le log `no such column: version`).

## ÉTAPE 5 — Comparaison local / prod
| Élément | Local | Prod |
|---|---|---|
| Colonne `version` | **NON** (PRAGMA) | **NON** (log `no such column: version`) |
| Migration 008 (ALTER version) | présente mais **ALTER avalé** | présente mais **ALTER avalé** |
| Lecture SQL `SELECT version` OK | **NON** (`OperationalError` reproduit) | **NON** (exception loggée) |
> **Correction de la prémisse** : la colonne **n'existe PAS non plus en local**. Le bug se reproduit **à l'identique** local = prod. Il n'y a **aucune divergence** local/prod.

## ÉTAPE 6 — Moment exact de l'exception → **CAS A**
```
L2417  PDF V2 généré (pdf_bytes)        ✅ existe en mémoire
L2424  hash(pdf_bytes) calculé          ✅ preuve que le PDF est valide à ce point
L2436  page de couverture fusionnée     ✅ pdf_bytes enrichi
L2444  SELECT version                   ❌ EXCEPTION "no such column: version"
L2463  écriture disque du PDF V2         ⛔ JAMAIS atteinte
L2469  except → fallback V3
```
**Preuve que le PDF V2 est déjà généré** : le hash `_cerfa_pdf_hash = sha256(pdf_bytes)` est calculé **avec succès** à L2424, donc `pdf_bytes` est un PDF V2 valide **avant** l'exception. Variables disponibles au moment du crash : `pdf_bytes` (PDF V2 + couverture), `_synthese_hash`, `_cerfa_pdf_hash`, `_nb_pages`.
**Nuance** : le PDF V2 existe **en mémoire** mais **n'est jamais écrit sur disque** (L2463 non atteinte) ⇒ il est purement et simplement **abandonné**, puis V3 régénère et sauvegarde son propre PDF dégradé.

## ÉTAPE 7 — Impact → **C. Combinaison des deux**
- **Migration manquante** = le *déclencheur* (colonne `version` absente → `SELECT version` lève).
- **Mauvais périmètre try/except** = l'*amplificateur* (une erreur d'**audit** située dans le `try` de **génération** détruit un PDF V2 réussi).
Sans la colonne manquante : pas d'exception. Sans le mauvais périmètre : l'erreur d'audit n'aurait pas dû faire échouer la génération. **Les deux sont nécessaires** pour produire le symptôme TEST4.

## CE QUI EST PROUVÉ
- Lecture `dossiers.version` : `main.py` `_generer_cerfa_pdf` **L2444** (`SELECT version FROM dossiers`).
- Colonne `version` **absente** en local (PRAGMA) et en prod (log) ; exception **reproduite en local** (`OperationalError: no such column: version`).
- ALTER de la colonne dans **008 L70**, **avalé** par le découpeur (commentaires en tête de segment).
- **PDF V2 déjà généré** (hash calculé L2424) **avant** l'exception ; **non persisté** (L2463 non atteinte).
- Le `try` V2 englobe génération + audit + persistance ⇒ une erreur d'audit déclenche le fallback.

## CE QUI EST DÉCLARÉ
- En prod, `dossiers` n'a jamais eu la colonne (même fichier de migration, même découpeur) — très fortement étayé par le message `no such column` mais non lu directement dans la base prod.

## CE QUI EST NON VÉRIFIÉ
- Lecture directe du schéma de la base **prod** (nécessiterait `railway ssh` dans le conteneur — non fait).
- Moteur de base en prod : le message `no such column` est de **forme SQLite** → la prod tourne probablement en **SQLite sur le volume `/data`** (et non PostgreSQL) — à confirmer, sans impact sur la cause.

## CAUSE RACINE (réponse unique)
> **Combinaison de plusieurs causes** : (1) **migration manquante** — colonne `dossiers.version` jamais créée (ALTER de 008 avalé par le découpeur) ; (2) **mauvais try/except** — le `SELECT version` d'audit est dans le bloc `try` de génération V2 (L2444), si bien qu'une erreur d'audit **jette un PDF V2 déjà généré** et bascule en fallback V3.

## CORRECTION MINIMALE PROPOSÉE (description seule, non codée)
- **Minimale immédiate (périmètre try)** : déplacer/encapsuler le `SELECT version` + `_log_cerfa_audit` (L2444-2461) **hors** du `try` de génération, ou dans un `try/except` **local**, afin qu'une erreur d'audit **n'invalide plus** une génération V2 réussie. ⇒ rétablit V2 **sans toucher aux moteurs**, même si la colonne reste absente (la version retombe alors sur le défaut `1`).
- **Complémentaire (cause racine schéma)** : garantir la colonne `version` — soit corriger l'ALTER de la migration 008 (mettre l'`ALTER` en tête de segment, comme le correctif PROD-1), soit l'ajouter au filet `_COLONNES_PHASE3` de `main.py`.
- **Transverse (systémique)** : corriger le découpeur de migrations qui rejette les segments précédés de commentaires (cause récurrente : 008 `version`, historiquement 010, évité en PROD-1).
> Recommandation : appliquer **le correctif de périmètre try (B) en priorité** (rétablit V2 immédiatement), puis la garantie de colonne (A). Aucune correction n'est codée dans ce tour.

## Réponse au critère de réussite
1. **Pourquoi `version` manque en prod** : l'ALTER de la migration 008 est avalé par le découpeur (commentaires en tête) → colonne jamais créée (local + prod).
2. **Où l'exception est déclenchée** : `main.py` `_generer_cerfa_pdf` L2444 (`SELECT version FROM dossiers`).
3. **PDF V2 déjà généré ?** OUI (Cas A) — généré en mémoire (hash L2424) avant l'exception, jamais écrit sur disque.
4. **Pourquoi un problème d'audit provoque un fallback CERFA** : le `SELECT version` (audit) est dans le **même bloc `try`** que la génération V2 ; son exception est capturée par l'`except` de génération (L2469) → fallback V3.
5. **Correction minimale pour rétablir V2 sans toucher aux moteurs** : sortir le `SELECT version`/audit du `try` de génération (ou try/except local), + garantir la colonne `version`.

---
---

# CAUSE RACINE COLLECTE (2026-06-06, tour 7) — pourquoi le dossier reste faible

> Lecture seule. Aucune correction. Le CERFA V2 est désormais clos (cf. DEPLOY_VERIFY) ; le goulot restant est la **collecte**. Diagnostic par tracé de code + logs prod.

## Fichiers / fonctions analysés
- `app/main.py` : `initiate_dossier` (L1491), `upload_document_dossier` (L1810), `_calculer_completude_live` (orchestration L110).
- `app/engines/orchestration_engine.py` : `traiter_message_async` (dispatch L405-870), `_handle_consent_flow`, `_dossier_narratif_exploitable` (L66-108), déclencheur narratif (L825-846).
- `app/engines/eligibilite_droits_engine.py` (L1198) + `strategie_dossier_engine.py` (L418) : seuls sites touchant `droits_demandes` (en **lecture**).

## 1. Pourquoi « oui » termine la conversation
- **Route** : `POST /webhook/whatsapp` → `main.py` (BackgroundTasks) → `OrchestrationService.traiter_message_async`.
- **Déclencheur de fin** (orchestration L825-830) :
  ```python
  _declencher_narratif = (agent.is_complete(donnees) or _dossier_narratif_exploitable(donnees)) and service_type != "validation_en_attente"
  if _declencher_narratif: self._generer_narratif_et_qualite(...) ; self._demander_validation_usager(...)  # = "message de fin"
  ```
- **Condition réelle** : `_dossier_narratif_exploitable(donnees)` (L84-91, état **actuel** après correctif) renvoie `True` dès qu'un de `diagnostics / impact_quotidien / _verbatim_b / documents_texte / _document_knowledge` est présent **+** une identité. **L'upload du bilan remplit `diagnostics` ET `documents_texte`** → `exploitable = True` **avant toute collecte**.
- **Conséquence** : au 1ᵉʳ message usager qualifiant (« oui »), `_declencher_narratif` est vrai → génération narratif + `_demander_validation_usager` → **demande de validation perçue comme « message de fin »**. La boucle de questions n'est jamais entrée.
- État conversationnel : avant = persona `identification` / collecte en cours ; après = `validation_en_attente`. **Note** : le retrait de `notes_pro` (tour 2) ne suffit pas — `diagnostics`/`documents_texte` issus du bilan déclenchent toujours.

## 2. Où devait aller la collecte
Workflow normal attendu : `START → consentement → identification profil → questions par onglet (ONGLETS_MDPH : vie quotidienne, retentissement, scolarité/emploi, **droits souhaités**, projet de vie) jusqu'à is_complete → narratif → validation`.
Workflow réellement observé : `START → (consentement) → 1ᵉʳ « oui » → exploitable=True → narratif + validation`. **Les onglets de questions (impact structuré, droits, NIR, genre) sont sautés.**

## 3. Le bilan est-il injecté ?
| Étape | Présent ? | Preuve |
|---|---|---|
| Upload | **Oui** | route `upload_document_dossier` (main.py L1810) |
| Stockage | **Oui** | `synthese_json` enrichi |
| Extraction | **Oui (tronquée)** | LLM sur `texte_extrait[:4000]` (L1865) ; `documents_texte[:2000]` (L1887) |
| Injection dans `donnees` | **Oui (partielle)** | `diagnostics`, `accident_travail` ajoutés (merge `k not in synthese`) ; CERFA P8 LLM 2171 chars en prod |
→ Le bilan **est** injecté, mais **tronqué** (≈ 4 000 / 29 000 car. analysés, 2 000 persistés) et il **déclenche** la fin prématurée (cause §1).

## 4. Pourquoi `droits=[]`
- Le remplissage CERFA lit `donnees["droits_demandes"]` (V3 field_mapper L606) / la liste `droits` (V2). Log prod : `droits=[]`.
- **Aucun site n'écrit `donnees["droits_demandes"]`** dans le chemin de collecte/synthèse : les seules occurrences (`eligibilite_droits_engine` L1198, `strategie_dossier_engine` L418) **lisent** ce champ pour produire leurs propres sorties d'analyse — elles ne le réinjectent pas dans la synthèse.
- `/initiate` ne le pose pas ; le prompt d'extraction du bilan (main.py L1842-1861) n'extrait **pas** `droits_demandes` ; la collecte (qui poserait la question « quels droits ? ») est court-circuitée (§1).
- ⇒ `droits_demandes` reste **vide partout** → 0 case E/P17/P18 cochée.

## 5. Pourquoi la complétude reste ~35 %
`_calculer_completude_live` (orchestration L110-139) pondère : nom 15, ddn 15, NSS 10, adresse 8, tel 5, email 5, **diagnostics 12, impact_quotidien 10, droits_demandes 10**, type 5, dept 5.
- Présents (création + bilan) : nom, ddn, email, type, dept, (diagnostics, adresse selon extraction).
- **Manquants** car jamais collectés : `impact_quotidien` (10), `droits_demandes` (10), `num_secu`/NIR (10), genre. Logs prod confirment : `NIR non renseigné`, `genre=`, `droits=[]`.
- ⇒ le score plafonne bas (~35 %) : les champs « lourds » dépendant de la collecte ne sont jamais remplis.

## TABLEAU DE DIAGNOSTIC
| Étape | Exécutée | Preuve |
|---|---|---|
| Création dossier | ✅ | `/initiate` persiste email/nom/ddn/type (main.py L1552-1576) |
| Upload bilan | ✅ | `upload_document_dossier` (L1810) ; P8 LLM 2171 chars en prod |
| Extraction bilan | ✅ tronquée | LLM sur 4000/29000 car. (L1865) ; documents_texte 2000 (L1887) |
| Réponse WhatsApp « oui » | ✅ | déclenche narratif+validation (exploitable=True, L825-830) |
| **Suite collecte (questions)** | ❌ | court-circuitée — jamais entrée |
| **Droits demandés** | ❌ | aucun site d'écriture de `droits_demandes` → `droits=[]` (log prod) |
| Narratif B | ✅ (V2) | `[EXPERT-P8] 1670 chars` / `[CERFA P8] 2171 chars` (prod) |
| Cockpit | ⚠️ | calculé sur données minces ; `appui-evaluation → 500` en prod (à part) |
| CERFA | ✅ V2 | 984 750 o, mais mince (E vide) |

## CAUSE RACINE COLLECTE
### CE QUI EST PROUVÉ
- `_dossier_narratif_exploitable` (L84-91) renvoie `True` sur `diagnostics`/`documents_texte` (remplis par l'upload du bilan) + identité → la collecte se termine au 1ᵉʳ message (L825-830).
- `donnees["droits_demandes"]` n'a **aucun site d'écriture** dans le chemin collecte/synthèse (grep) → `droits=[]` (log prod).
- Le bilan est injecté mais **tronqué** (4000/29000, 2000 persistés).
- Complétude basse = champs collecte-dépendants (`impact_quotidien`, `droits_demandes`, `num_secu`, genre) jamais remplis (logs prod : NIR/genre absents, droits=[]).

### CE QUI EST DÉCLARÉ
- Le « message de fin » perçu = `_demander_validation_usager` déclenché juste après le « oui » (cohérent avec L842).
- L'ordre exact consentement vs déclencheur narratif sur le « oui » dépend de l'état consentement au moment du message.

### CE QUI EST NON VÉRIFIÉ
- Les **logs conversationnels prod** du dossier (hors fenêtre de rétention / indexés par usager, non par dossier) — l'enchaînement exact des messages WhatsApp n'a pas été relu en prod.
- Si un onglet quelconque a été partiellement parcouru avant le déclenchement.

### PREMIER POINT DE RUPTURE
> **État conversationnel** — `_dossier_narratif_exploitable()` (orchestration_engine L66) est vrai **avant toute collecte** parce que l'upload du bilan a rempli `diagnostics`/`documents_texte`. La collecte WhatsApp est donc clôturée au 1ᵉʳ message. (Cause secondaire structurelle : `droits_demandes` n'a aucun site d'alimentation.)

### CHAÎNE CAUSALE COMPLÈTE
```
Upload bilan → diagnostics + documents_texte écrits dans synthese
   ↓
_dossier_narratif_exploitable = True AVANT toute collecte
   ↓
1ᵉʳ « oui » → _declencher_narratif True → narratif + demande de validation (= "message de fin")
   ↓
boucle de questions (impact structuré, DROITS, NIR, genre) jamais parcourue
   ↓
droits_demandes vide (aucun site d'écriture) + impact/num_secu/genre vides
   ↓
complétude ~35 %, page E vide, droits=[]
   ↓
CERFA V2 généré mais MINCE (narratif B OK depuis le bilan, mais 0 droit, identité incomplète)
```

### CORRECTION MINIMALE PROPOSÉE (description seule, non codée — périmètre COLLECTE)
1. **Ne pas clôturer la collecte sur du contenu PRÉ-COLLECTE.** `_dossier_narratif_exploitable` doit exiger un **signal de collecte réelle** (≥ 1 réponse usager de collecte, ou ≥ 1 onglet parcouru) et **non** la simple présence de `diagnostics`/`documents_texte` issus d'un upload/création. (Le retrait de `notes_pro` du tour 2 est insuffisant : il faut aussi neutraliser `diagnostics`/`documents_texte` pré-collecte comme déclencheurs de fin.)
2. **Prévoir un site d'alimentation de `droits_demandes`** : soit une question de collecte explicite (« quels droits souhaitez-vous ? »), soit une dérivation contrôlée depuis l'éligibilité/bilan **écrite dans la synthèse** — ⚠️ touche la logique droits → à cadrer hors « collecte pure ».
3. **(observé, à part)** `GET /appui-evaluation → 500` en prod : à investiguer séparément (panneau analyse).
> Aucune correction appliquée ce tour.

## Réponses au critère de réussite
1. **WhatsApp s'arrête après « oui »** : `_dossier_narratif_exploitable` vrai avant collecte (bilan → diagnostics/documents_texte) → déclencheur narratif+validation (L825-830).
2. **La collecte n'alimente pas le dossier** : la boucle de questions est court-circuitée → impact/droits/NIR/genre jamais collectés.
3. **`droits=[]`** : `droits_demandes` n'a aucun site d'écriture dans le chemin synthèse + collecte sautée.
4. **Complétude ~35 %** : champs lourds collecte-dépendants jamais remplis (pondération L110-139).
5. **Premier point de rupture** : **état conversationnel** (`_dossier_narratif_exploitable` vrai avant collecte).

---

## COMPLÉMENT (tour 8) — tracé déterministe des 5 points

### Fichiers / fonctions lus
- `app/engines/orchestration_engine.py` : `traiter_message_async` (dispatch L405-870), `_handle_consent_flow` (L1078), `_dossier_narratif_exploitable` (L66-108), déclencheur narratif (L825-830), `_demander_validation_usager` (L1504-1526), `_traiter_reponse_validation_usager` (L1528).
- `app/engines/conversation_engine.py` : checklist Section E `droits_demandes` (L121-126), onglet « Droits & Prestations » (L273-276), `extract_structured_data_from_history` (L477).
- `app/main.py` : `get_appui_evaluation` (L901-962), usages `notes_pro` (L1562, 1702, 1891…).
- Multi-moteurs lisant `notes_pro` : cdaph (L90/162/558), completeness (L113/136/304), evidence (L272), eligibilite (L82), dossier_strength (L231), action_plan (L395/404).

### 1. Condition exacte du « oui → fin »
- **Handler** : `traiter_message_async`. Si `check_consent_required` est vrai → `_handle_consent_flow` (qui interprète le texte via `record_whatsapp_consent`) **consomme** le « oui » comme acceptation de consentement et retourne (L414-425). Si le consentement est **déjà** donné (cas probable après lancement), le « oui » **n'est PAS spécialement interprété** : il passe directement au dispatch de collecte.
- **Branche de fin** : à L825-830, `_declencher_narratif = (is_complete OR _dossier_narratif_exploitable) and service_type != "validation_en_attente"`. `_dossier_narratif_exploitable` étant **déjà vrai** (bilan → `diagnostics`/`documents_texte`), le 1ᵉʳ message qualifiant déclenche `_generer_narratif_et_qualite` puis `_demander_validation_usager` (L1504) → bascule `persona_actif='validation_en_attente'` + envoi de `_TEXTE_VALIDATION_USAGER` = **le « message final »**.
- **État avant** : `identification`/collecte. **État après** : `validation_en_attente`.
- **Conclusion** : « oui » n'a pas de pouvoir spécial ; c'est **le premier message** qui déclenche une fin déjà « armée » par le contenu pré-collecte.

### 2-4. Source attendue de `droits_demandes` & raison exacte de `droits=[]`
- **Source attendue** : champ de **collecte Section E** défini dans `conversation_engine` (L121-126, « EN FIN de collecte »), récupéré par `extract_structured_data_from_history`. ⇒ `droits_demandes` doit être **renseigné par la conversation WhatsApp** (question « quels droits souhaités ? »).
- **Raison exacte du vide** : la collecte est clôturée **avant** d'atteindre la Section E (cause §1) → la question des droits **n'est jamais posée** → `droits_demandes` jamais extrait. Aucun autre site n'écrit ce champ dans la synthèse (cf. tour 7).
- **REEVALUATION ne le peuple pas** : `type_dossier=REEVALUATION` ne mappe que la **case CERFA P1 3** (réévaluation) via `field_mapper` L94 / `accueil.py` L45-46 — c'est la *procédure*, pas la *liste de droits*. Donc la création « réévaluation des droits » **ne doit pas** alimenter `droits_demandes` ; les droits restent à collecter.

### 3. Effet du retrait de `notes_pro` (vérifié)
- Le retrait porte **uniquement** sur la liste `a_contenu_fonctionnel` de `_dossier_narratif_exploitable` (déclencheur de fin).
- `notes_pro` **reste lu** comme **source de données** par : `cerfa_narrative_engine`/CERFA P8 (fallback L341), cdaph, completeness, evidence, eligibilite, dossier_strength, action_plan.
- ⇒ **Aucune source utile supprimée.** `notes_pro` servait à la fois au fallback CERFA **et** à l'analyse/narratif (qui le lisent toujours) ; il ne sert simplement plus de **déclencheur de fin de collecte**. Retrait **sans effet de bord négatif** (mais insuffisant seul : `diagnostics`/`documents_texte` déclenchent encore).

### 4 (bis). Statut du bilan joint : **injecté**, pas seulement affiché
- `upload_document_dossier` (main.py L1810) : extraction LLM → fusion dans `synthese_json` (`diagnostics`, `accident_travail`, `documents_texte` tronqué 2000). Preuve d'injection réelle dans l'orchestration : en prod, `[EXPERT-P8] 1670 chars` puis `[CERFA P8] 2171 chars` — le narratif V2 **utilise le contenu du bilan**.
- ⇒ Le bilan est **réellement injecté** dans les données d'orchestration/narratif (pas un simple affichage). Limite : **tronqué** (≈4000/29000 analysés) et il **déclenche** la fin prématurée.

### 5. Diagnostic du 500 `GET /appui-evaluation` (lecture seule, NON corrigé)
- Route `get_appui_evaluation` (main.py L901). Ligne **L959-961** :
  ```python
  "inference_coverage": json.loads(
      (db.execute("SELECT synthese_json FROM dossiers WHERE id=?", (dossier_id,)).fetchone() or {}).get("synthese_json") or "{}"
  ).get("_inference_coverage") or {},
  ```
- `fetchone()` renvoie un **`sqlite3.Row`** (row_factory=Row, confirmé par les accès `row["..."]` plus haut). **`sqlite3.Row` n'a pas de méthode `.get()`** → `AttributeError: 'sqlite3.Row' object has no attribute 'get'` → **HTTP 500**.
- **Indépendant de TEST4** : ce bug frappe **tout dossier** ouvert dans le panneau « Appui à l'évaluation ». Le frontend l'avale (`if (!res.ok) return;`) → le panneau ne s'affiche pas. **Sans rapport avec le CERFA ni la collecte.**

### Réponse au critère de réussite (cause principale du TEST4 restant)
| Hypothèse | Verdict |
|---|---|
| A. État conversationnel WhatsApp | ✅ **CAUSE PRINCIPALE** — `_dossier_narratif_exploitable` vrai avant collecte → collecte clôturée au 1ᵉʳ message |
| B. Absence d'injection du bilan | ❌ FAUX — le bilan **est** injecté (narratif V2 l'utilise) |
| C. `droits_demandes` jamais peuplé | ⚠️ **CONSÉQUENCE de A** (Section E jamais atteinte) + lacune structurelle (aucun autre site d'écriture) |
| D. 500 appui-évaluation | ❌ INDÉPENDANT — n'affecte que le panneau analyse, ni CERFA ni collecte |
| **Réponse** | **A (principale), dont C découle. B faux. D indépendant.** ⇒ proche de **E (A+C)**, mais le déclencheur unique est **A**. |

### Correction minimale PROPOSÉE (description, NON codée — périmètre COLLECTE)
1. **A (cause racine)** : `_dossier_narratif_exploitable` ne doit clôturer la collecte que sur un **signal de collecte réelle** (≥1 réponse usager de collecte ou ≥1 onglet parcouru), et **non** sur du contenu pré-collecte (`diagnostics`/`documents_texte` venant de l'upload, ou notes de création). C'est la correction unique qui rétablit la collecte.
2. **C (complément)** : une fois la collecte rétablie, la Section E posera la question des droits → `droits_demandes` se remplira naturellement. (Aucune dérivation automatique nécessaire ; éviter de toucher la logique droits.)
3. **D (à part, hors collecte)** : `get_appui_evaluation` L960 — remplacer l'accès `.get()` sur Row par un accès `["synthese_json"]` (diagnostic seulement, non corrigé ici).
> Aucune correction appliquée. Priorité : **A** (sans quoi C reste vide quel que soit le reste).

---
---

# CAUSE RACINE FIN PRÉMATURÉE DE COLLECTE (2026-06-07, tour 9) — trace conversationnelle complète

> Lecture seule. Fichiers lus : `app/engines/orchestration_engine.py` (`traiter_message_async` L447-870, `_dossier_narratif_exploitable` L66-108, `_demander_validation_usager` L1504), `app/engines/conversation_engine.py` (Section E `droits_demandes`, onglets, `extract_structured_data_from_history`), `app/services/conversation` (agents). Aucune correction.

## Déroulé EXACT d'un message dans `traiter_message_async` (ordre des lignes)
```
L411  consent_ok = not check_consent_required(...)
L414  if not consent_ok: _handle_consent_flow(...) ; return        ← "oui" consommé comme CONSENTEMENT si requis
L458  service_type = service_type_from_persona(etat)               (persona session)
L463  nouvelles_donnees = extract_structured_data_from_history(...) (extraction)
L687  if service_type == "identification": determine_next_service → _switch_service → envoi présentation ("Corrine…")
L767  if nav.validation_demandee and text∈(OUI,…): onglet_courant += 1
L777  if onglet_courant_complet(...) : (envoi message de validation d'onglet) OU avance silencieuse
L804  reponse = agent.respond(...)                                 ← QUESTION SUIVANTE calculée
L816  historique += [user, assistant] ; _sauvegarder_nav(...)
L825  _declencher_narratif = (agent.is_complete OR _dossier_narratif_exploitable) and service_type != "validation_en_attente"
L829  if _declencher_narratif:
L830      _generer_narratif_et_qualite(...)
L841      if _narratif_ok:
L842          _demander_validation_usager(...)                      ← MESSAGE FINAL envoyé (persona → validation_en_attente)
L846          return                                                ← ★ RETURN : on saute l'envoi de la question
L864  self.wa.send_text(phone_wa, reponse)                          ← envoi de la QUESTION — JAMAIS ATTEINT si L846 a return
```

## 1. Où passe exactement le « oui »
- **Fonction/handler** : `OrchestrationService.traiter_message_async`. Si le consentement est requis → `_handle_consent_flow`/`record_whatsapp_consent` (le « oui » = consentement, return). Sinon, le « oui » poursuit le flux de collecte.
- **État avant** : session `persona_actif = 'identification'` (posé par `/initiate`). **Après** : `_switch_service` → `'adulte'` (profil déterminé via date_naissance), puis `_demander_validation_usager` (L1518) → `'validation_en_attente'`.
- Le « oui » n'a **aucune sémantique de collecte** ici : c'est simplement le 1ᵉʳ message qui fait tourner le pipeline jusqu'au déclencheur.

## 2. Événement qui déclenche la fin (condition / branche / ligne)
- **Condition** : `_declencher_narratif` (**L825**) = `(agent.is_complete(donnees) OR _dossier_narratif_exploitable(donnees)) and service_type != "validation_en_attente"`. Ici `is_complete=False` mais **`_dossier_narratif_exploitable=True`** (bilan → `diagnostics`/`documents_texte`).
- **Branche** : **L829→L830→L842→L846**. `_demander_validation_usager` (L1504) bascule la session en `validation_en_attente` et envoie `_TEXTE_VALIDATION_USAGER` = **le message final**, puis **`return` L846**.
- **Effet décisif** : la question suivante, pourtant **déjà calculée** par `agent.respond` (L804), **n'est jamais envoyée** car le `return` L846 court-circuite `self.wa.send_text(phone_wa, reponse)` (**L864**).
- ⇒ L'usager reçoit : présentation « Corrine… je vais vous poser quelques questions » (L726) **immédiatement suivie** du message de validation — sans aucune question. **C'est exactement le symptôme « oui → fin ».**

## 3. Où la collecte devrait continuer
| État actuel | État suivant attendu (normal) | État réel observé |
|---|---|---|
| 1ᵉʳ message, onglet A | envoi question onglet courant (L864) → réponse → `onglet_courant += 1` | **return L846** → aucune question |
| onglet B/C/D… | progression onglet par onglet jusqu'à `is_complete` | jamais atteint |
| **onglet E (droits)** | question « droits souhaités » → `extract_structured_data` remplit `droits_demandes` | **jamais atteint** |
| is_complete | narratif + validation | narratif + validation déclenchés **dès le tour 1** |

## 4. État manquant
- Aucun **flag de progression de collecte** : pas de `collecte_demarree`, pas de compteur de tours usager, pas de vérification « ≥1 onglet réellement parcouru » avant d'autoriser la clôture.
- `_dossier_narratif_exploitable` **ne distingue pas** le contenu **pré-collecte** (bilan uploadé, notes de création) du contenu **réellement collecté en conversation**.
- ⇒ Le système n'a aucun moyen de savoir que « la collecte n'a pas encore commencé » → il clôture sur la seule présence de contenu.

## 5. Le narratif est-il déclenché trop tôt ?
> **OUI.** La **condition de génération narrative** (L825, contenu présent) est satisfaite **avant** la **condition de clôture normale** (`is_complete` / tous onglets validés). Le narratif/validation démarre **au tour 1**, avant que les onglets n'atteignent la Section E.

## 6. Pourquoi la Section E n'est jamais atteinte (chaîne)
La Section E (droits) est le **dernier onglet**, atteint seulement après progression onglet-par-onglet (un onglet par tour validé, L767-794 + envoi question L864). Or le déclencheur narratif (L829-846) **termine tout au tour 1** et **empêche l'envoi de la moindre question** → `onglet_courant` ne progresse jamais → Section E jamais affichée → `droits_demandes` jamais collecté.

## PREMIER POINT DE RUPTURE
```
Fichier   : app/engines/orchestration_engine.py
Fonction  : traiter_message_async — déclencheur narratif (L825-846)
            appuyé sur _dossier_narratif_exploitable (L66-108)
Condition : _dossier_narratif_exploitable(donnees) == True dès le 1ᵉʳ message
            (bilan uploadé → diagnostics / documents_texte présents) + identité
Conséquence : _demander_validation_usager (L842) + return (L846)
            → la question de collecte (L864) n'est jamais envoyée
```

## CHAÎNE CAUSALE COMPLÈTE
```
Upload bilan → diagnostics + documents_texte écrits dans synthese_json
   ↓
_dossier_narratif_exploitable = True AVANT toute collecte (L84-91)
   ↓ (transition incorrecte)
1ᵉʳ message → _declencher_narratif True (L825) → _demander_validation_usager (L842) → return (L846)
   ↓
collecte interrompue : la question (L804) n'est jamais envoyée (L864 sauté), onglet_courant figé
   ↓
Section E (droits, dernier onglet) jamais atteinte
   ↓
droits_demandes vide (extract_structured_data jamais appelé sur la Section E)
   ↓
CERFA incomplet (page E vide, droits=[], + NIR/genre non collectés) — complétude ~35 %
```

## CE QUI EST PROUVÉ
- Ordre d'exécution L804 (question calculée) → L825 (déclencheur) → L842/L846 (return) **avant** L864 (envoi question). Le `return` L846 saute l'envoi.
- `_dossier_narratif_exploitable` vrai sur `diagnostics`/`documents_texte` (remplis par l'upload bilan) — L84-91.
- Section E = champ de collecte `droits_demandes` (conversation_engine L121-126), atteint en fin de progression onglets.
- Aucun flag de progression de collecte ne conditionne la clôture.

## CE QUI EST DÉCLARÉ
- Le « message final » perçu = `_TEXTE_VALIDATION_USAGER` envoyé par `_demander_validation_usager`.
- Si le consentement n'était pas encore donné, le 1ᵉʳ « oui » est d'abord consommé par le consentement, et c'est le **message suivant** qui déclenche la fin (même mécanisme, décalé d'un tour).

## CE QUI EST NON VÉRIFIÉ
- Logs conversationnels prod du dossier (hors fenêtre) — l'enchaînement réel des messages WhatsApp n'a pas été relu en prod.
- Le nombre exact d'onglets parcourus avant le déclenchement (probablement 0).

## CORRECTION MINIMALE PROPOSÉE (description seule, non codée — périmètre COLLECTE)
- **Conditionner la clôture à une progression réelle de collecte.** Le déclencheur `_declencher_narratif` (ou `_dossier_narratif_exploitable`) ne doit autoriser la fin que si la collecte a **réellement avancé** : p.ex. exiger `is_complete` **ou** (contenu fonctionnel **réellement collecté en conversation** ET ≥1 onglet parcouru / ≥1 réponse usager de collecte). Le contenu **pré-collecte** (bilan uploadé, notes de création) ne doit **pas**, à lui seul, déclencher la fin.
- Effet attendu : la collecte enverra ses questions onglet par onglet jusqu'à la Section E → `droits_demandes` se remplira → CERFA complet. **Aucun moteur, droit, narratif ou CERFA modifié** — uniquement la **condition de fin de collecte**.
> Aucune correction appliquée ce tour.

## Critère de réussite — réponses
1. **« oui » ne mène pas à la question suivante** : la question est calculée (L804) mais le `return` du déclencheur narratif (L846) est atteint avant son envoi (L864).
2. **La collecte se termine** : `_dossier_narratif_exploitable=True` au tour 1 → `_demander_validation_usager`.
3. **Section E jamais atteinte** : la progression onglet-par-onglet (qui mène à E en dernier) est court-circuitée dès le tour 1.
4. **`droits_demandes` vide** : la question Section E n'est jamais posée → jamais extraite.
5. **Premier point de rupture** : `orchestration_engine.traiter_message_async` / déclencheur narratif L825-846 sur `_dossier_narratif_exploitable` vrai pré-collecte.
