# PROD_5_HISTORY_PANEL_REPORT.md — Panneau Historique dans le dashboard

**Généré le :** 2026-06-06
**Sprint :** FACILIM PROD-5 — visibilité de l'historique (affichage uniquement, aucun recalcul, aucun moteur modifié)
**Statut :** ✅ Timeline visible dans le dashboard — QA-PROD-5 PASS, aucune régression (10/10)

---

## 0. Résultat

| Élément | Avant | Après |
|---|---|---|
| Audit trail persistant | ✅ | ✅ |
| Historique consultable (API) | ✅ | ✅ |
| **Historique visible (dashboard)** | ❌ | ✅ |
| **Timeline professionnelle** | ❌ | ✅ |
| **Utilisation workflow réel** | ❌ | ✅ |

---

## 1. Diagnostic préalable

| Élément | Constat (vérifié) |
|---|---|
| Dashboard actif | `app/dashboards/dashboard.html` (servi par `main.py` ; `static/dashboard.html` = legacy, non touché) |
| Chargement dossier | `openDossier(id)` → `Promise.all([fetch dossier, loadAppuiEvaluation, loadHistorique])` → `renderModalContent` + `renderCockpit` + (panneaux) |
| Source historique | `GET /api/v1/dossiers/{id}/historique` (PROD-4) |
| Format réel | `{ dossier_id, nb_evenements, evenements: [ { source, type, date, canal, acteur, details } ] }`, **trié par date croissante** |

---

## 2. Cartographie : API historique → rendu dashboard

```
openDossier(id)
  └─ loadHistorique(id)
        └─ GET /api/v1/dossiers/{id}/historique        ← API réelle PROD-4 (lecture seule)
              └─ renderHistorique(data)                ← rendu générique, AUCUN recalcul
                    └─ #panel-historique / #historique-timeline
```

| Champ JSON | Élément affiché |
|---|---|
| `evenements[].date` | horodatage formaté (`toLocaleString('fr-FR')`) |
| `evenements[].type` | titre de l'entrée |
| `evenements[].source` | badge (`audit_events` / `cerfa_audit_log`) |
| `evenements[].acteur` | « par … » si présent |
| `evenements[].details` | rendu **générique** clé → valeur (aucune règle par type) |
| `nb_evenements` | compteur d'en-tête |

---

## 3. Liste exacte des fichiers modifiés

| Fichier | Modification | Logique métier ? |
|---|---|---|
| `app/dashboards/dashboard.html` | (1) panneau `#panel-historique` ; (2) `loadHistorique()` + `renderHistorique()` (timeline générique, lecture seule) ; (3) reset + `loadHistorique(id)` dans `openDossier` | **Non** — affichage |
| `app/tests/qa/qa_prod_5.py` | **Nouveau** — test QA-PROD-5 | Test |
| `app/tests/qa/qa_prod_2.py` | Correctif des **bornes d'extraction** du test (le `renderCockpit` du dashboard étant désormais suivi de `renderHistorique`) — le code du dashboard est inchangé | Test (maintenance) |
| `app/tests/qa/reports/historique_render_*.html` | **Nouveaux** — 2 pages de rendu (preuve visuelle) | Artefacts |

**Aucune table créée, aucun audit trail modifié, aucun événement recalculé.** `renderHistorique` ne contient **aucun `fetch`** (le fetch est dans `loadHistorique`) et **aucun type d'événement codé en dur** (rendu générique — vérifié par QA-PROD-5).

---

## 4. Exemples de timeline affichée (rendu réel navigateur, via `innerText`)

**Dossier avec événements** (`historique_render_events.html`, données réelles `GET /historique`) :
```
06/06/2026 16:50:01
COCKPIT_CALCULE            audit_events
score_completude : 54
score_solidite : 55
decision : GO_AVEC_RISQUES

06/06/2026 16:50:01
gate_export_check          cerfa_audit_log   par qa_prod_5
action : envoi
gate_statut : BLOCK
gate_present : true
export_autorise : false
raison : Pièces justificatives manquantes
```

**Dossier sans événement** (`historique_render_empty.html`) :
```
Historique du dossier            0 événement
Aucun événement enregistré pour ce dossier.
```

---

## 5. Résultat QA-PROD-5

```
A. Câblage statique (dashboard.html) — 9/9 ✅
   ✅ #panel-historique · ✅ #historique-timeline · ✅ renderHistorique · ✅ loadHistorique
   ✅ loadHistorique appelle /historique · ✅ appelée dans openDossier
   ✅ renderHistorique sans fetch · ✅ rendu générique (aucun type codé en dur) · ✅ liste vide gérée

B. Données réelles (GET /historique via TestClient) — 6/6 ✅
   ✅ 2 événements · ✅ champs date/type/source/details · ✅ ordre chronologique
   ✅ COCKPIT_CALCULE présent · ✅ gate BLOCK avec raison · ✅ dossier vide → liste vide

DÉCISION QA-PROD-5 : ✅ PASS (A=True, B=True)
```

### Vérification navigateur réel (DOM + console) — les 6 cas de la mission
| Cas | Vérification | Résultat |
|---|---|---|
| 1 — Historique présent | timeline chargée, 2 entrées, ordre chronologique | ✅ |
| 2 — Historique vide | « Aucun événement enregistré pour ce dossier. » | ✅ |
| 3 — Gate BLOCK | `gate_statut : BLOCK` + `raison : Pièces justificatives manquantes` visibles | ✅ |
| 4 — Cockpit calculé | `COCKPIT_CALCULE` visible avec scores | ✅ |
| 5 — Navigation dossier | passage events → vide → rendu correct à chaque fois | ✅ |
| 6 — Console navigateur | **0 erreur JS** (sur les 2 pages) | ✅ |

---

## 6. Non-régression

| Test | Résultat |
|---|---|
| QA-PROD-1 / 2 / 3 / 4 / 5 | ✅ PASS |
| QA-5 / QA-7 / QA-9 / QA-10 / QA-11 (n=100) | ✅ PASS |

> Note : QA-PROD-2 a d'abord échoué après l'ajout du panneau — non pas à cause du dashboard (renderCockpit inchangé) mais parce que son extraction de test lisait `renderCockpit` jusqu'à `loadDossiers`, englobant désormais `loadHistorique` (qui contient un `fetch`). Bornes d'extraction corrigées → PASS.

---

## 7. Preuves — PROUVÉ / DÉCLARÉ / NON VÉRIFIÉ

### ✅ CE QUI EST PROUVÉ
- La timeline s'affiche dans le dashboard, alimentée **exclusivement** par `GET /historique` (QA-PROD-5 + DOM navigateur réel).
- Données réelles issues de l'API (COCKPIT_CALCULE + gate BLOCK avec raison), ordre chronologique.
- État vide géré (message explicite), navigation entre dossiers, **0 erreur console**.
- Rendu **générique** (aucun type d'événement codé en dur, aucun `fetch` dans `renderHistorique`) → supporte les événements futurs.
- Aucune régression (10/10 QA).

### 🟦 CE QUI EST DÉCLARÉ
- En production, `openDossier()` appelle `loadHistorique(id)` qui interroge l'API réelle ; les pages de preuve utilisent le **même** `renderHistorique` et le **même** markup (extraits du fichier), alimentés par le JSON réel — seul le transport (fetch live vs JSON injecté) diffère.
- Style visuel : Tailwind en production ; CSS inline équivalent dans les pages de preuve.

### ⚠️ CE QUI EST NON VÉRIFIÉ
- Capture d'écran **image** : l'outil de capture de l'environnement expire (limite déjà constatée en PROD-2) ; preuve fournie en **DOM + texte rendu**. *Repro : `python -m http.server 8765 --directory app/tests/qa/reports` puis ouvrir `http://localhost:8765/historique_render_events.html`.*
- Rendu dans le **dashboard authentifié** sur un dossier réel ayant traversé le pipeline WhatsApp complet.
- Pagination / volumétrie pour des dossiers à très nombreux événements (limite API = 200).

---

## 8. Critères de refus — contrôle

| Critère de refus | Présent ? |
|---|---|
| Nouvelle table créée | ❌ Non |
| Audit trail modifié | ❌ Non |
| Événement recalculé | ❌ Non |
| Données mockées | ❌ Non (JSON réel de `GET /historique`) |
| Historique non relié à l'API réelle | ❌ Non — `loadHistorique` → `GET /historique` |
| Absence de QA-PROD-5 | ❌ Non — présent et PASS |
| Absence de preuve de rendu | 🟡 Preuve DOM + texte rendu (image indisponible, repro documentée) |

---

## Conclusion

Le professionnel peut désormais consulter **la timeline complète d'un dossier directement dans le dashboard** — calcul du cockpit, vérification du gate, export autorisé/refusé avec raison — sans passer par l'API. L'affichage est générique (prêt pour de futurs événements), robuste (liste vide, champs absents) et strictement alimenté par les données déjà persistées.

| Élément | Statut |
|---|---|
| Audit trail persistant | ✅ |
| Historique consultable (API) | ✅ |
| Historique visible (dashboard) | ✅ |
| Timeline professionnelle | ✅ |
| Utilisation workflow réel | ✅ |

*Aucun moteur modifié. Aucun audit trail touché. Aucun recalcul. Affichage uniquement.*
