# PROTOCOLE_TEST_TERRAIN_ABC.md — Preuve définitive par isolation des chaînes

**Généré le :** 2026-06-07
**Cible :** prod instrumentée `c3081775` / `3404fce` · traces `[TRACE_COLLECTE]` (WhatsApp) + `[TRACE_SOURCE_SYNTHESE]` (document).
**But :** isoler **séparément** WhatsApp / Document / Fusion pour prouver où l'information disparaît.
**Méthode :** 3 tests, **dossiers distincts**, chaque test une seule source (sauf C). Données admin = **fictives de test**.

> ⏱️ Règle de fenêtre : test + signal ≤ ~20 min (logs Railway courts). Noter **référence + heure** de chaque dossier.

---

# TEST A — DOCUMENT SEUL  (dossier `FAC-DOS-A`)

**Protocole :**
1. Créer un dossier neuf. Noter réf + heure. **N'envoyer AUCUN message.**
2. Uploader **uniquement** le bilan PCR (PDF/DOCX).
3. Attendre la réponse « Document analysé… ».
4. Dashboard → noter complétude. Prévisualiser CERFA.
5. Me signaler (réf + heure).

**Traces attendues :** `[TRACE_SOURCE_SYNTHESE]` 3-DOC recu → 4-DOC texte_extrait → 5-DOC champs_extraits → 8-SYNTHESE_AVANT(doc) → 10/11-DOC ajoutes/ignores → 6-DOC_KNOWLEDGE → 13-SAVE(doc) ok.
**Aucune** trace `[TRACE_COLLECTE]`.

**Mesure (à remplir) :**
| Champ | Extrait `5-DOC` | Persisté `13-SAVE` | Dashboard | CERFA | Attendu (théorie code, à confirmer) |
|---|---|---|---|---|---|
| nom_prenom | ☐ | ☐ | ☐ | ☐ | possible (liste extraction doc) |
| date_naissance | ☐ | ☐ | ☐ | ☐ | possible |
| adresse_complete | ☐ | ☐ | ☐ | ☐ | possible |
| diagnostics / impact_quotidien | ☐ | ☐ | ☐ | ☐ | possible (santé/ménage) |
| organisme_payeur / numero_allocataire | ☐ | ☐ | ☐ | ☐ | **attendu ABSENT** (hors liste doc) |
| pension/categorie/taux invalidité | ☐ | ☐ | ☐ | ☐ | **attendu ABSENT** |
| avq_* (toilette/habillage/repas/déplacements/gestion) | ☐ | ☐ | ☐ | ☐ | **attendu ABSENT** (jamais en avq_*) |
| droits.* | ☐ | ☐ | ☐ | ☐ | **attendu ABSENT** |
| _document_knowledge (limitations…) | ☐ | ☐ | n/a | n/a | **attendu PRÉSENT** (texte) |

**Objectif A :** prouver ce qu'un document apporte **seul** → en particulier confirmer/infirmer que **les limitations du bilan ne deviennent pas de l'AVQ structuré** ni de l'administratif (organisme/allocataire/invalidité).

---

# TEST B — WHATSAPP SEUL  (dossier `FAC-DOS-B`)

**Protocole :**
1. Créer un dossier neuf. Noter réf + heure. **N'uploader AUCUN document.**
2. Envoyer la conversation, **un message à la fois** :
   1. `Bonjour, je veux préparer un dossier MDPH pour moi.`
   2. `Marie-Christine CECORA, femme, née le 19/01/1966.`
   3. `J'habite 159 Bd Henri Barnier, 13015 Marseille, département 13.`
   4. `Mon numéro de sécurité sociale : 2 66 01 13 055 042 12.`
   5. `Je suis à la CAF, allocataire n° 1234567.`
   6. `Je touche une pension d'invalidité catégorie 2.`
   7. `Toilette : autonome. Habillage : besoin d'aide.`
   8. `Repas : autonome. Déplacements extérieurs : besoin d'aide. Ménage : besoin d'aide.`
   9. `Je demande l'AAH, la PCH, la RQTH et la CMI mention invalidité.`
   10. `Mon projet : préserver ma santé puis retravailler dans les métiers du lien.`
3. Dashboard → complétude. Prévisualiser CERFA. Me signaler (réf + heure).

**Traces attendues :** `[TRACE_COLLECTE]` 1-MSG (×10) → 4-EXTRACT → 5-EXTRAIT → 6-REJETES → 7-SYNTHESE_APRES (completude croissante) → 9-SAVE ok. **Aucune** trace `[TRACE_SOURCE_SYNTHESE]`.

**Mesure (à remplir) :**
| Champ | Extrait `5-EXTRAIT` | Persisté `9-SAVE` | Dashboard | CERFA | Attendu (théorie code) |
|---|---|---|---|---|---|
| nom_prenom / date_naissance / adresse / num_secu | ☐ | ☐ | ☐ | ☐ | attendu PRÉSENT (requis + whitelist) |
| organisme_payeur / numero_allocataire | ☐ | ☐ | ☐ | ☐ | extractible (whitelist 1dccf6c) ; **CERFA : non mappé V2** |
| pension_invalidite / categorie_invalidite | ☐ | ☐ | ☐ | ☐ | extractible ; CERFA partiel/absent |
| avq_toilette/habillage/repas/déplacements/gestion | ☐ | ☐ | ☐ | ☐ | extractible **si** valeur = enum ; CERFA cases si avq_* |
| droits.aah/pch/rqth/cmi_invalidite | ☐ | ☐ | ☐ | ☐ | extractible (objet) ; CERFA P17 |
| projet_de_vie | ☐ | ☐ | ☐ | ☐ | via projet_orientation/texte_e |

**Objectif B :** prouver ce que WhatsApp apporte **seul** → confirmer/infirmer que l'extraction capte réellement identité + NIVEAU A, et où ça s'arrête (extraction vs persistance vs dashboard vs CERFA).

---

# TEST C — DOCUMENT + WHATSAPP  (deux dossiers, deux ordres)

**C1 = `FAC-DOS-C1` : conversation D'ABORD, puis document.**
1. Créer dossier. Faire la conversation (B, messages 1→10).
2. Puis uploader le bilan PCR. Dashboard + CERFA. Signaler.

**C2 = `FAC-DOS-C2` : document D'ABORD, puis conversation.**
1. Créer dossier. Uploader le bilan PCR.
2. Puis faire la conversation (B, messages 1→10). Dashboard + CERFA. Signaler.

**Mesure fusion (à remplir, par dossier) :** repérer dans les traces
- `10/11-DOC ajoutes / ignores_deja_presents` (chemin document),
- `5-EXTRAIT` vs `7-SYNTHESE_APRES` (chemin WhatsApp),
pour chaque champ **commun** (nom, date, adresse, impact, projet) et **disjoint** (organisme/allocataire/invalidité/avq = WA ; santé/limitations = doc).

| Champ commun | C1 (WA puis doc) : qui gagne ? | C2 (doc puis WA) : qui gagne ? | Attendu (théorie : 1er écrivain gagne, pas d'écrasement) |
|---|---|---|---|
| nom_prenom | ☐ | ☐ | C1→WA, C2→doc |
| date_naissance | ☐ | ☐ | C1→WA, C2→doc |
| adresse_complete | ☐ | ☐ | C1→WA, C2→doc |
| impact_quotidien | ☐ | ☐ | **C1→WA (doc ignoré) / C2→doc (WA ignoré)** ⚠️ conflit |
| projet_de_vie | ☐ | ☐ | usager prioritaire (WA) selon règle |

**Objectif C :** prouver si les deux sources **se complètent** (champs disjoints) ou **se neutralisent** (champs communs → 2ᵉ source ignorée car clé déjà présente, y compris si vide).

---

# LIVRABLE — MATRICES (à compléter avec les traces réelles)

## MATRICE SOURCE → SYNTHÈSE
| Champ | Origine WhatsApp (B) | Origine Document (A) | Extrait | Persisté | Visible dashboard | Visible CERFA |
|---|---|---|---|---|---|---|
| nom_prenom | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| date_naissance | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| adresse_complete | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| num_secu | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| organisme_payeur | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| numero_allocataire | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| pension_invalidite | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| categorie_invalidite | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| avq_toilette | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| avq_habillage | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| avq_repas | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| avq_deplacements | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| avq_gestion_quotidienne | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| droits.aah / pch / rqth / cmi_invalidite | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| projet_de_vie | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| limitations / santé (bilan) | — | ☐ | ☐ | ☐ | ☐ | ☐ |

## MATRICE DE FUSION
| Champ | WhatsApp (valeur ?) | Document (valeur ?) | Résultat final (synthese_json) | Mécanisme observé |
|---|---|---|---|---|
| nom_prenom | ☐ | ☐ | ☐ | (ajouté / ignoré / écrasé) |
| impact_quotidien | ☐ | ☐ | ☐ | ⚠️ conflit attendu |
| organisme_payeur | ☐ | ✗ | ☐ | (WA seul) |
| avq_* | ☐ | ✗ | ☐ | (WA seul) |
| limitations / santé | ✗ | ☐ | ☐ | (doc seul) |

## MATRICE DE PERTE
| Champ | Dernière étape où il EXISTE (déclaré / extrait / persisté / dashboard / CERFA) |
|---|---|
| (chaque champ) | ☐ → permet de pointer l'étape exacte de disparition |

---

# VERDICT (à rendre après les 3 tests)

Le principal goulot est : **un seul** parmi —
- extraction WhatsApp · extraction document · fusion · persistance · mapping dashboard · mapping CERFA.

**Règle de lecture croisée :**
- **A vide partout** mais **B plein** → goulot = **exploitation document** (extraction doc / structuration).
- **B vide** mais **A plein** → goulot = **extraction WhatsApp**.
- **A et B pleins séparément** mais **C perd des champs** → goulot = **fusion** (1er écrivain gagne / clé vide bloquante).
- **Tout présent en synthese_json** (A/B/C) mais **dashboard/CERFA vides** → goulot = **mapping aval**.
- **`5-*` pleins mais `9/13-SAVE` absents** → **persistance**.

> Le verdict sera **une seule cause**, démontrée par les lignes `[TRACE_COLLECTE]` / `[TRACE_SOURCE_SYNTHESE]` des 3 dossiers. Rien avant.

---

# PROTOCOLE D'EXÉCUTION (récapitulatif jour J)
1. **TEST A** (`FAC-DOS-A`) : doc seul → signaler réf+heure.
2. **TEST B** (`FAC-DOS-B`) : conversation seule → signaler réf+heure.
3. **TEST C1** (`FAC-DOS-C1`) : conversation puis doc → signaler.
4. **TEST C2** (`FAC-DOS-C2`) : doc puis conversation → signaler.
5. Pour chaque dossier : noter complétude dashboard + prévisualiser CERFA + cocher les tableaux.
6. Me transmettre les **4 références + heures** (groupées, ≤ 20 min après le dernier test).
7. Je lis **exclusivement** les traces, je remplis les 3 matrices, je rends **un verdict unique**.

---

*Protocole de preuve définitive uniquement. Aucun code modifié, aucun bug corrigé, aucun audit lancé. Données admin = fictives de test. Les colonnes « Attendu (théorie code) » servent de référence de comparaison, à confirmer/infirmer par les traces réelles.*
