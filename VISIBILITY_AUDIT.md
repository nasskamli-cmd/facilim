# VISIBILITY_AUDIT.md — Audit de visibilité des moteurs

**Généré le :** 2026-06-06
**Question posée :** pour chaque moteur — `MOTEUR → résultat → visible par le professionnel ?`

## Définition des 3 niveaux

- **✅ Visible** — le résultat est exécuté, persisté **et rendu** dans une interface (dashboard ou message).
- **🟡 Partiellement visible** — le résultat est exécuté + persisté + **disponible via l'API** (`GET /api/v1/dashboard/dossiers/{id}` renvoie `cockpit_pro_json`), mais **pas encore rendu** par un panneau dédié du dashboard.
- **❌ Non visible** — le résultat n'atteint pas le professionnel (non exécuté, ou exécuté puis perdu).

> Fait technique : depuis le câblage PROD-1, tous les moteurs FACILIM 60→100 alimentent le champ unique `cockpit_pro_json`, exposé automatiquement par l'API (`SELECT * → dict(row)`). Ils passent donc de ❌ à 🟡. Le passage à ✅ nécessite **un panneau d'affichage dans `dashboard.html`** (non réalisé dans cette mission — câblage data uniquement).

---

## Moteurs de collecte / narratifs (déjà dans le parcours)

| Moteur | Résultat | Visible ? |
|---|---|---|
| profile_engine | ProfilUsager | ✅ Visible (routage, champs dashboard) |
| conversation_engine | Réponse agent | ✅ Visible (message WhatsApp) |
| cerfa_narrative_engine | texte_b/c/d/e | ✅ Visible (colonnes + CERFA) |
| cerfa_quality_agent | score maturité + alertes | ✅ Visible (notification + colonnes) |
| analyse_situation_engine | analyse 10 clés | ✅ Visible (panneau « Appui à l'évaluation » du dashboard) |

## Moteurs FACILIM 60→100 (câblés par PROD-1 → cockpit_pro_json)

| Moteur | Résultat (clé cockpit) | Visible ? |
|---|---|---|
| completeness_engine | `score_completude` | 🟡 Partiellement (API, pas de panneau) |
| cdaph_strategy_engine | `score_solidite`, `forces`, `faiblesses`, `droits_detectes` | 🟡 Partiellement |
| refusal_risk_engine | `risques_refus` | 🟡 Partiellement |
| evidence_engine | preuves (via cockpit) | 🟡 Partiellement |
| eligibilite_droits_engine | droits analysés | 🟡 Partiellement |
| strategie_dossier_engine | `droits_oublies` | 🟡 Partiellement |
| questions_levier_engine | `questions_roi` | 🟡 Partiellement |
| justificatifs_engine | `pieces_prioritaires` | 🟡 Partiellement |
| action_plan_engine / priorisation_engine | `plan_action` | 🟡 Partiellement |
| parcours_engine | feuille de route | 🟡 Partiellement |
| human_validation_engine | `validation_humaine`, `nb_en_attente` | 🟡 Partiellement |
| pre_submission_engine | `decision` (GO/RISQUES/NO_GO) | 🟡 Partiellement |
| professional_cockpit_engine | `cockpit_texte`, `resume` | 🟡 Partiellement |
| pro_report_engine | 4 rapports | 🟡 Partiellement (générés, non exposés par route dédiée) |
| cerfa_gate_engine | `gate_export` | 🟡 Calculé et exposé, mais **non appliqué** avant export |

## Moteurs non visibles

| Moteur | Résultat | Visible ? | Raison |
|---|---|---|---|
| audit_trail_engine | journal d'audit | ❌ Non visible | Non appelé par PROD-1 (`generer_cerfa=False`) |
| explainability_engine | explication dossier | ❌ Non visible | Orphelin — importé seulement par QA-8 |
| field_mapper (via facilim_prod) | field_map | ❌ Non visible | Le CERFA réel passe par `cerfa_filler` |

---

## Synthèse

| Niveau | Nb moteurs | Liste |
|---|---|---|
| ✅ Visible | 5 | profile, conversation, narrative, quality, analyse_situation |
| 🟡 Partiellement visible | 15 | toute la chaîne FACILIM 60→100 (via `cockpit_pro_json` + API) |
| ❌ Non visible | 3 | audit_trail, explainability, field_mapper(facilim_prod) |

**Conclusion :** le câblage PROD-1 a fait passer 15 moteurs de « non visible » à « partiellement visible » (données exécutées, persistées, exposées par l'API). **Le dernier pas vers ✅ est un travail d'interface** : ajouter un panneau « Cockpit FACILIM » dans `dashboard.html` qui lit `cockpit_pro_json`. Ce pas est volontairement hors périmètre de cette mission (câblage data uniquement, aucun moteur ni logique métier modifiés).
