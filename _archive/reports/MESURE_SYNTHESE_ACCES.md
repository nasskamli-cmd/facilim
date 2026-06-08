# MESURE_SYNTHESE_ACCES.md — Obtenir `synthese_json` réel (preuve mesurée)

**Généré le :** 2026-06-07
**Mode :** lecture seule. Aucun moteur/prompt/CERFA/dashboard/règle métier modifié.
**Découverte clé :** `synthese_json` est **déjà observable** via un endpoint **existant**, **sans aucun changement produit**.

---

## CE QUI EST PROUVÉ
- **Endpoint existant** : `GET /api/v1/dashboard/dossiers/{dossier_id}` (main.py L651-668) — authentifié (`_get_current_user`), permission `DOSSIER_READ`, **lecture seule**.
- Il renvoie (preuve, lignes citées) :
  - `d["synthese"] = json.loads(synthese_json)` (**L666**) → **le `synthese_json` complet**,
  - `d["conversation"]` (L668), `d["droits_identifies"]` (L665), `d["questions"]` (L667),
  - via `SELECT *` (L658) : `score_completude`, `cockpit_pro_json`, `analyse_situation_json`, `texte_b/c/d/e_*`, etc.
- **Endpoints complémentaires existants** : `GET …/{id}/appui-evaluation` (analyse_situation_json, L901), `GET …/{id}/historique` (L1270), `GET /api/v1/rgpd/export/{usager_id}` (export complet, L1210).

## CE QUI EST NON VÉRIFIÉ
- Le **contenu réel** de `synthese_json` des dossiers témoins (je ne peux pas m'authentifier en prod : pas de jeton, `railway ssh` bloqué). → il faut **récupérer le JSON via l'endpoint** (toi, connecté) ou me le fournir.

---

## ÉTAPE 1 — MÉTHODES POSSIBLES POUR OBTENIR `synthese_json`

| Méthode | Existe | Câblé | Visible | Utilisable | Risque |
|---|---|---|---|---|---|
| **`GET /api/v1/dashboard/dossiers/{id}`** → champ `synthese` | ✅ | ✅ | ✅ (renvoie le JSON) | ✅ **immédiat** | **très faible** (auth, lecture seule, aucun changement) |
| `GET …/{id}/appui-evaluation` (analyse_situation_json) | ✅ | ✅ | ✅ | ✅ (complément) | très faible |
| `GET …/{id}/historique` | ✅ | ✅ | ✅ | partiel (événements) | très faible |
| `GET /api/v1/rgpd/export/{usager_id}` | ✅ | ✅ | ✅ | ✅ (export complet) | faible (données complètes) |
| Lecture directe base prod | ✅ | — | — | ❌ (`railway ssh` bloqué) | n/a |
| Logs `[TRACE_*]` | ✅ | ✅ | — | partiel (champ-level, besoin rejeu) | faible |

## ÉTAPE 2 — MÉTHODE LA MOINS INVASIVE
**`GET /api/v1/dashboard/dossiers/{dossier_id}`** → champ **`synthese`**.
**Zéro modification produit** : le frontend appelle déjà cet endpoint à l'ouverture d'un dossier ; le JSON arrive déjà dans ton navigateur (connecté). On l'observe sans rien changer.

## ÉTAPE 3 — MATRICE DE MESURE FINALE (à remplir avec le JSON réel)
| Fait | Source (pièces) | Structuré (clé dans `synthese`) | Synthèse (valeur) | Dashboard (`score_completude`/visible) | CERFA |
|---|---|---|---|---|---|
| (chaque fait AIT ABBAS / CECORA / 3ᵉ) | ✅ connu | ✅/❌ selon présence clé | valeur ou ∅ | ✅/❌ | ✅/❌ |

> Une fois le `synthese` récupéré, chaque ligne devient **mesurée** (présence/absence de la clé), plus aucune estimation.

## ÉTAPE 4 — PLUS PETIT CHANGEMENT NÉCESSAIRE
**AUCUN.** L'endpoint existe, est câblé, renvoie le `synthese_json` complet. Rien à coder, rien à déployer.

## ÉTAPE 5 — PLAN D'EXÉCUTION

### ACTION 1 — Récupérer le `synthese` de chaque dossier
Connecté au dashboard, ouvrir dans le navigateur (ou via l'outil réseau) :
`https://www.facilim.fr/api/v1/dashboard/dossiers/FAC-DOS--SW-VJVD`
puis idem pour `FAC-DOS-M30DPYEX` et un 3ᵉ dossier réel. **Copier le JSON renvoyé** (champ `synthese`, `conversation`, `score_completude`, `cockpit_pro_json`, `analyse_situation_json`) et me le transmettre.
**PREUVE ATTENDUE :** le contenu réel de `synthese_json` (liste des clés + valeurs) pour 3 dossiers.

### ACTION 2 — Mesurer fait par fait (harnais de traçabilité, hors-produit)
Croiser **référentiel de faits (sources déjà lues)** ↔ **`synthese`** ↔ **CERFA** ↔ **complétude**.
**PREUVE ATTENDUE :** matrice de mesure complète + **étape exacte de disparition** par fait + **taux de structuration** (faits source → clés structurées).

### ACTION 3 — Conclure le sous-pas exact
Comparer : fait présent en `synthese` mais absent CERFA → **mapping** ; fait absent de `synthese` mais présent en `conversation`/`_document_knowledge` → **structuration** ; fait absent partout → **collecte**.
**PREUVE ATTENDUE :** catégorie unique (A/B/C/D/E) **démontrée par les valeurs JSON**, par dossier.

---

## LIVRABLE FINAL

### CE QUI EST PROUVÉ
`synthese_json` est récupérable **maintenant**, sans changement, via `GET /api/v1/dashboard/dossiers/{id}` (champ `synthese`, L666).

### CE QUI EST NON VÉRIFIÉ
Le contenu réel des dossiers témoins (je n'ai pas d'accès authentifié prod) → à fournir via l'endpoint.

### COMMENT OBTENIR `synthese_json`
Appeler l'endpoint existant (connecté) pour chaque dossier ; le champ `synthese` = le JSON complet.

### MÉTHODE RECOMMANDÉE
`GET /api/v1/dashboard/dossiers/{dossier_id}` → `synthese` (+ `conversation`, `score_completude`, `cockpit_pro_json`). **Aucun code.**

### RISQUE
**Très faible** : endpoint authentifié, lecture seule, déjà utilisé par le produit. Aucune modification de comportement.

### PREUVES ATTENDUES
3 JSON `synthese` réels (AIT ABBAS, CECORA, 3ᵉ) → matrice fait-par-fait mesurée → étape de disparition par fait.

### PROCHAIN SPRINT UNIQUE
**« MESURE FAIT-PAR-FAIT »** (hors-produit, observation seule) : à partir des 3 `synthese` récupérés via l'endpoint existant + des sources + CERFA, produire la matrice de perte **mesurée** et le taux de structuration. **Aucun moteur, aucun correctif.**

---

## CRITÈRE DE SUCCÈS — réponse
On prend AIT ABBAS, CECORA, un 3ᵉ dossier ; on récupère leur `synthese` via l'endpoint **existant** ; on montre **fait par fait** : présent en source ? présent en `synthese` (clé) ? visible dashboard ? présent CERFA ? → l'**étape de disparition** devient **mesurée, pas supposée**. Le seul geste requis = **fournir le JSON `synthese`** des 3 dossiers ; tout le reste est déjà en place.

---

*Lecture seule. Aucun changement produit nécessaire pour mesurer. Le seul élément manquant = le JSON `synthese` réel des dossiers, récupérable via l'endpoint existant `GET /api/v1/dashboard/dossiers/{id}`.*
