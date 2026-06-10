# PLAN_MESURE_STRUCTURATION.md — Plan de mesure (Phase 1)

**Généré le :** 2026-06-08 · plan de mesure (aucun code, aucune modif produit).

## MISSION 5 — Audit composants (existe / utilisé / visible / persistant / exploité / non utilisé / redondant)
| Composant | Existe | Utilisé | Visible | Persistant | Exploité (aval) | Non utilisé | Redondant |
|---|---|---|---|---|---|---|---|
| synthese_json | ✅ | ✅ | dashboard | ✅ (BDD) | ✅ (tout l'aval) | — | non |
| evidence_engine (origine taguée) | ✅ | ✅ | cockpit | ✅ (recalculé) | ✅ (graphe preuves) | — | non — **réutilisable** (origine=base du champ `source`) |
| _document_knowledge | ✅ | ✅ (texte) | 🟡 | ✅ (dans synthese) | 🟡 (texte moteurs/P8) | — | non — **réutilisable** (proto-fait {valeur,extrait}) |
| collecte_schema | ✅ | ✅ | — | n/a | ✅ (checklist/AVQ/DROITS) | — | vs `CHECKLIST_MDPH` (déprécié) = **redondant** |
| human_validation / gate | ✅ | ✅ | gate | ✅ | ✅ (export) | — | non — **réutilisable** (états de validation) |
| cockpit | ✅ | ✅ | ✅ | cockpit_pro_json | ✅ | — | non |
| CERFA (v2_bridge+cerfa_filler) | ✅ | ✅ | PDF | cerfa_chemin (non relu pour servir) | ✅ | — | **field_mapper V3 = redondant** (2 mappers) |
| moteurs 60→100 | ✅ | ✅ | partiel | analyse_situation_json | ✅ | `rules_engine` = ❓ orphelin | 2 moteurs narratifs (anti-invention vs _composer_description_p8) = **redondant** |

## Données nécessaires à la mesure
1. **Pièces sources** du dossier (bilan, conversation) → déjà disponibles pour AIT ABBAS, CECORA.
2. **`synthese_json` réel** du dossier → **manquant** ; accessible via endpoint **existant** `GET /api/v1/dashboard/dossiers` (renvoie `SELECT *` incl. `synthese_json`, `id`, `updated_at`, `cerfa_genere_le`, `score_completude`).
3. **CERFA généré** → disponible (CF TEST 5/6), idéalement régénéré au moment de la mesure.
4. *(optionnel)* logs `[TRACE_COLLECTE]`/`[TRACE_SOURCE_SYNTHESE]` d'un rejeu instrumenté.

## Données déjà accessibles vs exports nécessaires
| Donnée | Accessible ? |
|---|---|
| Pièces sources (bilan/WA) | ✅ (fournies) |
| CERFA PDF | ✅ (fourni) |
| `synthese_json` réel | ❌ → **export via endpoint** (1 appel, lecture seule) |
| `updated_at` / `cerfa_genere_le` | ❌ → mêmes export |
| Référentiel de faits « or » | ✅ (REFERENTIEL_FAITS_MDPH.md) |

## Procédure de mesure (hors-produit, observation seule)
1. Construire le **référentiel « or »** du dossier depuis ses pièces (faits + citations).
2. **Exporter `synthese_json`** (+ id, updated_at, cerfa_genere_le, score_completude) via l'endpoint.
3. Lire le **CERFA** (champs texte + cases si rendu).
4. Remplir **MATRICE_TRACEABILITE_FAITS** (étape de disparition par fait).
5. Classer chaque fait **A-F** (CLASSIFICATION_PERTES_A_F).
6. Calculer **les taux** (TAUX_STRUCTURATION_SPEC), global + par domaine.

## Preuves qui valident / invalident l'hypothèse « le problème = structuration »
- **Valide** si : faits riches (santé/professionnels/limitations) majoritairement classés **C** (extrait mais non structuré) → taux de structuration faible sur ces domaines.
- **Invalide** si : faits présents en **clés structurées** dans `synthese_json` mais absents du CERFA → la perte serait **F (mapping)** ou **D (persistance)**, pas la structuration.

## CRITÈRE DE RÉUSSITE DE LA MESURE
Pour chaque dossier réel (CECORA, AIT ABBAS, +1) : une matrice fait-par-fait **mesurée**, un taux de structuration global + par domaine, et une catégorie A-F par fait — **toutes adossées au `synthese_json` réel**, zéro estimation.

---
*Plan de mesure. Aucune modification produit. Le seul export requis = `synthese_json` réel (endpoint existant).*
