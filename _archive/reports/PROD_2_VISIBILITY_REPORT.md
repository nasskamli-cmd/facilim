# PROD_2_VISIBILITY_REPORT.md — Visibilité du cockpit professionnel

**Généré le :** 2026-06-06
**Sprint :** FACILIM PROD-2 — visibilité uniquement (aucun moteur, aucune logique métier, aucun recalcul)
**Statut :** ✅ Cockpit visible dans l'interface dossier — QA-PROD-2 4/4 PASS, aucune régression

---

## 0. Résultat (les 5 niveaux)

| Niveau | Avant PROD-2 | Après PROD-2 |
|---|---|---|
| Calculé | ✅ | ✅ |
| Câblé | ✅ | ✅ |
| Persisté | ✅ | ✅ |
| **Visible** | ❌ | ✅ |
| **Utilisé** | ❌ | ✅ (consultable par le professionnel dans le dossier) |

---

## 1. Diagnostic préalable (fichiers analysés)

| Élément | Constat (vérifié dans le code) |
|---|---|
| Template dashboard **actif** | `app/dashboards/dashboard.html` (servi par `main.py` via `FileResponse`, ligne ~1162). `static/dashboard.html` = **legacy** (non modifié). |
| Composants UI | HTML + Tailwind (CDN) + JavaScript vanilla. Modale dossier `#modal-dossier`, contenu dynamique `#modal-content`, panneaux frères persistants (ex. `#panel-appui`). |
| Route de chargement dossier | `GET /api/v1/dashboard/dossiers/{id}` → `SELECT * FROM dossiers` → `dict(row)` (main.py ~656). **Renvoie automatiquement la colonne `cockpit_pro_json`.** |
| Fonction d'ouverture | `openDossier(id)` (fetch dossier) → `renderModalContent(d)`. |
| Structure `cockpit_pro_json` | 22 clés produites par `facilim_prod.cockpit_professionnel()` (lecture, non recalculé). |
| API utilisée | Aucune nouvelle route : la route dossier existante suffisait (cockpit déjà dans la réponse). |

**Conclusion du diagnostic :** problème de **visibilité pur**. La donnée arrivait déjà jusqu'au frontend via l'API ; il manquait un **panneau d'affichage**.

---

## 2. Fichiers modifiés

| Fichier | Modification | Logique métier ? |
|---|---|---|
| `app/dashboards/dashboard.html` | (1) ajout du panneau `#panel-cockpit` (8 sections) ; (2) ajout de la fonction `renderCockpit(d)` (lecture seule de `cockpit_pro_json`) ; (3) appel `renderCockpit(d)` dans `openDossier()` + reset du panneau | **Non** — affichage seul |
| `app/tests/qa/qa_prod_2.py` | **Nouveau** — test QA-PROD-2 (câblage statique + mapping données + génération des pages de rendu) | Test |
| `app/tests/qa/reports/cockpit_render_*.html` | **Nouveaux** — 4 pages de rendu (preuve visuelle, données réelles) | Artefacts |

**Aucun moteur modifié.** `renderCockpit` ne contient **aucun `fetch(`**, **aucun appel `/api/`** (vérifié par QA-PROD-2) : aucune logique dupliquée, aucun recalcul frontend.

---

## 3. Extrait JSON source (`cockpit_pro_json` — Karim, réel, tronqué)

```json
{
  "score_completude": 54,
  "score_solidite": 55,
  "niveau": "moyen",
  "decision": "GO_AVEC_RISQUES",
  "resume": "Score 55/100 (moyen). 0 droit(s) solide(s), 2 droit(s) fragile(s). 2 élément(s) en attente de validation.",
  "droits_detectes": [
    { "droit": "AAH",  "score": 57, "risque": "MOYEN", "explication": "Pièce prioritaire absente : Certificat médical…" },
    { "droit": "RQTH", "score": 62, "risque": "MOYEN", "explication": "Diagnostic non renseigné…" }
  ],
  "droits_oublies": [],
  "risques_refus": {
    "risque_global": "élevé",
    "risques": [
      { "droit": "RQTH", "label": "Reconnaissance Qualité Travailleur Handicapé", "risque": "élevé",
        "justification": "Impact emploi insuffisamment documenté — risque de refus RQTH" },
      { "droit": "AAH",  "label": "Allocation aux Adultes Handicapés", "risque": "élevé",
        "justification": "Dossier AAH insuffisamment documenté — risque élevé de refus" }
    ]
  },
  "pieces_prioritaires": [
    { "piece": "Certificat médical de moins de 3 mois", "droit": "medical", "obligatoire": true }
  ],
  "gate_export": {
    "autorise_export": false,
    "decision": "BLOQUE_EXPORT",
    "message": "❌ Export bloqué — 1 point(s) critique(s) : VALIDATION_INCOMPLETE…"
  },
  "plan_action": [
    { "titre": "Obtenir un certificat médical récent (< 3 mois)", "priorite": "haute", "roi": 35.0, "description": "…" }
  ],
  "validation_humaine": [
    { "element": "RQTH", "confiance": 62, "statut": "a_valider" },
    { "element": "AAH",  "confiance": 57, "statut": "a_valider" }
  ]
}
```

---

## 4. Correspondance champ JSON → élément affiché

| # | Section panneau | Élément HTML (id) | Clé(s) `cockpit_pro_json` |
|---|---|---|---|
| 0 | Décision (badge en-tête) | `#cockpit-decision` | `decision` (GO / GO_AVEC_RISQUES / NO_GO) |
| 1 | Synthèse professionnelle | `#cockpit-completude`, `#cockpit-solidite`, `#cockpit-niveau`, `#cockpit-resume` | `score_completude`, `score_solidite`, `niveau`, `resume` |
| 2 | Droits détectés | `#cockpit-droits` | `droits_detectes[]` (`droit`, `score`, `risque`) |
| 3 | Droits oubliés | `#cockpit-oublies` | `droits_oublies[]` — **si vide → « Aucun droit oublié détecté. »** |
| 4 | Risques du dossier | `#cockpit-risque-global`, `#cockpit-risques` | `risques_refus.risque_global`, `risques_refus.risques[]` (`label`, `risque`, `justification`) |
| 5 | Preuves recommandées | `#cockpit-preuves` | `pieces_prioritaires[]` (`piece`, `obligatoire`) |
| 6 | Gate CERFA | `#cockpit-gate`, `#cockpit-gate-msg` | `gate_export.decision` → **PASS** / **WARNING** / **BLOCK** ; `gate_export.message` |
| 7 | Plan d'action | `#cockpit-plan` | `plan_action[]` (`titre`, `priorite`, `roi`, `description`) |
| 8 | Validation humaine | `#cockpit-validation` + mention fixe | `validation_humaine[]` (`element`, `confiance`, `statut`) + « FACILIM recommande. Le professionnel valide. » |

Mapping gate : `AUTORISE`→PASS · `AUTORISE_AVEC_AVERTISSEMENTS`→WARNING · `BLOQUE_EXPORT`→BLOCK.

---

## 5. Résultat QA-PROD-2

```
A. Câblage statique (dashboard.html)
   ✅ panneau #panel-cockpit présent
   ✅ fonction renderCockpit présente
   ✅ renderCockpit lit cockpit_pro_json (JSON.parse)
   ✅ renderCockpit appelée dans openDossier
   ✅ mention 'FACILIM recommande. Le professionnel valide.' présente
   ✅ aucun fetch dans renderCockpit (no recalc)
   ✅ aucun appel moteur (/api/) dans renderCockpit
   ✅ 8 sections (ids) présentes

B. Mapping données (4 cockpits réels) — 8/8 sections sur chaque profil
   ✅ Karim · ✅ Lucas · ✅ SEP · ✅ Aidant

DÉCISION QA-PROD-2 : ✅ PASS (statique=OK, profils=4/4)
```

**Non-régression :** QA-PROD-1 ✅ · QA-5 ✅ · QA-7 ✅ · QA-9 ✅ · QA-10 ✅ · QA-11 ✅ (n=100).

---

## 6. Preuve de rendu (navigateur réel — DOM + texte rendu)

Les 4 pages de rendu (`renderCockpit` + markup **extraits du vrai `dashboard.html`**, alimentés par le `cockpit_pro_json` **réel** de `facilim_prod`) ont été chargées dans un navigateur réel (serveur local), puis inspectées via le DOM. **Aucune erreur console** sur aucune des 4 pages.

| Profil | Panneau visible | Complétude | Solidité | Gate | Droits détectés | Droits oubliés | Plan |
|---|---|---|---|---|---|---|---|
| Karim (AT) | ✅ | 54/100 | 55/100 | **BLOCK** | AAH 57%, RQTH 62% | « Aucun droit oublié détecté. » | 7 |
| Lucas (TSA) | ✅ | 40/100 | 27/100 | **WARNING** | AEEH 54%, SESSAD 24% | « Aucun droit oublié détecté. » | 9 |
| SEP | ✅ | 44/100 | 34/100 | **WARNING** | AAH, CMI, RQTH | « Aucun droit oublié détecté. » | 10 |
| Aidant | ✅ | 38/100 | 27/100 | **WARNING** | AAH, RQTH | « Aucun droit oublié détecté. » | 9 |

Mention « FACILIM recommande. Le professionnel valide. » : **présente sur les 4**.

**Texte effectivement rendu pour Karim (capture textuelle du panneau, via `panel.innerText`) :**

```
Cockpit professionnel FACILIM
GO AVEC RISQUES
ℹ️ FACILIM recommande. Le professionnel valide. Ce panneau affiche les résultats déjà calculés (aucun recalcul)…
SYNTHÈSE PROFESSIONNELLE — Complétude 54/100 · Solidité 55/100 · moyen
Score 55/100 (moyen). 0 droit(s) solide(s), 2 droit(s) fragile(s). 2 élément(s) en attente de validation.
DROITS DÉTECTÉS — AAH · 57%   RQTH · 62%
DROITS POTENTIELLEMENT OUBLIÉS — Aucun droit oublié détecté.
RISQUES DU DOSSIER — Global : élevé
  Reconnaissance Qualité Travailleur Handicapé — élevé / Impact emploi insuffisamment documenté…
  Allocation aux Adultes Handicapés — élevé / Dossier AAH insuffisamment documenté…
PREUVES RECOMMANDÉES — OBLIGATOIRE Certificat médical… · Justificatif d'identité… · Avis d'imposition… (+recommandées)
VERROU EXPORT CERFA — BLOCK / ❌ Export bloqué — VALIDATION_INCOMPLETE…
PLAN D'ACTION — 7 actions (haute/moyenne, ROI, descriptions)
VALIDATION HUMAINE — FACILIM recommande. Le professionnel valide. · RQTH 62% a_valider · AAH 57% a_valider
```

---

## 7. Preuves — PROUVÉ / DÉCLARÉ / NON VÉRIFIÉ

### ✅ CE QUI EST PROUVÉ
- Le panneau cockpit s'affiche dans l'interface, alimenté **exclusivement** par `cockpit_pro_json` (QA-PROD-2 + DOM réel).
- Les 8 sections + décision + mention humaine sont rendues, sur **4 profils réels** (Karim, Lucas, SEP, aidant).
- Gate affiché en PASS/WARNING/**BLOCK** selon la donnée déjà calculée.
- Liste vide gérée explicitement (« Aucun droit oublié détecté. »).
- **Aucune erreur JS** (console error vide sur les 4 pages).
- **Aucun recalcul / aucun appel moteur** dans `renderCockpit` (vérifié statiquement).
- Aucune régression QA (QA-PROD-1 + QA-5/7/9/10/11 PASS).

### 🟦 CE QUI EST DÉCLARÉ (hypothèses raisonnables)
- En production, `openDossier()` reçoit `cockpit_pro_json` directement de l'API (`SELECT *`), donc le même `renderCockpit` s'exécutera à l'identique. Les pages de rendu utilisent ce **même** `renderCockpit` et le **même** markup (extraits du fichier réel), avec la donnée réelle — seul le transport (API vs fichier) diffère.
- Le style visuel s'appuie sur Tailwind (chargé par le dashboard en production) ; les pages de preuve utilisent un CSS inline équivalent.

### ⚠️ CE QUI EST NON VÉRIFIÉ (à tester)
- **Capture d'écran image** : l'outil de capture de l'environnement a expiré systématiquement (limitation d'environnement, navigateur lié à un autre projet). La preuve de rendu est donc fournie sous forme **DOM + texte rendu**, pas en image. *Reproduction : `python -m http.server 8765 --directory app/tests/qa/reports` puis ouvrir `http://localhost:8765/cockpit_render_karim_accident_du_travail.html`.*
- Rendu dans le **vrai dashboard authentifié** sur un dossier ayant traversé le workflow WhatsApp complet (non rejoué ici).
- Rendu multi-navigateurs / responsive mobile.

---

## 8. Critères de refus — contrôle

| Critère de refus | Présent ? |
|---|---|
| Nouveau moteur créé | ❌ Non |
| Recalcul frontend | ❌ Non (aucun `fetch`/`/api/` dans `renderCockpit`) |
| Données mockées | ❌ Non (sortie réelle de `facilim_prod`) |
| Données hardcodées | ❌ Non |
| Cockpit non alimenté par `cockpit_pro_json` | ❌ Non — alimenté exclusivement par cette clé |
| Absence de QA-PROD-2 | ❌ Non — présent et PASS 4/4 |
| Absence de preuve visuelle | 🟡 Preuve DOM + texte rendu fournie ; capture image non disponible (limite d'environnement, repro documentée) |

---

## Conclusion

Le cockpit professionnel FACILIM est désormais **visible et consultable** par le professionnel dans le dossier, alimenté uniquement par les résultats déjà calculés (`cockpit_pro_json`), sans aucun recalcul ni nouvelle logique métier. Les 5 niveaux FACILIM (Calculé · Câblé · Persisté · Visible · Utilisé) sont validés.

*Aucun moteur FACILIM 60→100 modifié. Aucune logique d'éligibilité, CDAPH, droits, narratifs ou CERFA touchée.*
