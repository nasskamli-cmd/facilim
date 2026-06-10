# MATRICE_EXISTE_UTILISE_VISIBLE.md

**Généré le :** 2026-06-07 · conception/lecture seule. Basé sur le code vérifié cette session.
Légende : ✅ oui · 🟡 partiel/conditionnel · ❌ non · ❓ NON VÉRIFIÉ.

## Champs / données

| Élément | Existe | Câblé | Visible (dashboard/CERFA) | Utilisé (moteurs) | Nature |
|---|---|---|---|---|---|
| nom_prenom | ✅ | ✅ | ✅ (P2, dashboard 15pts) | non | structuré |
| date_naissance | ✅ | ✅ | ✅ (Date A, 15pts) | ✅ (âge) | structuré |
| adresse_complete | ✅ | ✅ | ✅ (P2, 8pts) | non | structuré |
| num_secu | ✅ | ✅ | ✅ (NSS, 10pts) | non | structuré |
| telephone / email | ✅ | ✅ | ✅ (P2) | non | structuré |
| departement | ✅ | ✅ | ✅ (5pts) | ✅ | structuré |
| numero_dossier_mdph | ✅ | ✅ | ✅ (P1) | non | structuré |
| statut_emploi | ✅ | ✅ | ✅ (P13) | ✅ | structuré (texte) |
| diagnostics | ✅ | ✅ | ✅ (P8) | ✅ | texte |
| impact_quotidien | ✅ | ✅ | ✅ (P8, 10pts) | ✅ | **texte libre** |
| droits_demandes | ✅ | ✅ | ✅ (P17, 10pts) | ✅ | texte (tokens) |
| droits.* (objet) | ✅ défini | 🟡 | 🟡 | ❌ (lisent le texte) | structuré (peu persisté) |
| avq_* (×5) | ✅ défini | 🟡 (V2 post-fix) | 🟡 | 🟡 | structuré (peu persisté) |
| organisme_payeur / numero_allocataire | ✅ défini | 🟡 | ❌ (non mappé V2) | ❌ | structuré (peu persisté) |
| pension/categorie/taux invalidité | ✅ défini | 🟡 | ❌ | 🟡 (texte) | structuré (peu persisté) |
| situation_scolaire / etablissement | ✅ | ✅ | ✅ (P9) | ✅ | structuré (texte) |
| representant_legal / type_protection | ✅ | ✅ | ✅ (P3) | 🟡 | structuré |
| projet_orientation / projet_professionnel | ✅ | ✅ | ✅ (P16) | ✅ | texte |
| texte_b/c/d/e (narratifs) | ✅ | ✅ | ✅ (P8/P16) | ❌ (retiré 7e04f89) | **généré** |
| description_situation (P8) | ✅ | ✅ | ✅ (P8) | ❌ (retiré) | **généré** |
| _document_knowledge | ✅ | ✅ | 🟡 | ✅ (texte) | **texte structuré-léger** |
| notes_pro / documents_texte / expression_directe / _verbatim_* | ✅ | ✅ | 🟡 | ✅ | texte |

## Composants

| Composant | Existe | Câblé | Utilisé prod | Visible |
|---|---|---|---|---|
| synthese_json (source de vérité) | ✅ | ✅ | ✅ | — |
| extraction conversation (whitelist) | ✅ | ✅ | ✅ | — |
| extraction document + _document_knowledge | ✅ | ✅ | ✅ (si upload) | — |
| eligibility / cdaph / evidence / strength / completeness / refusal_risk / strategie / pre_submission / action_plan / questions_levier / justificatifs / inferencer / profil_handicap / profil_specifique | ✅ | ✅ (via facilim_prod) | ✅ | partiel |
| cerfa_filler V2 + v2_bridge | ✅ | ✅ | ✅ | CERFA |
| field_mapper V3 | ✅ | 🟡 fallback | 🟡 | CERFA(fallback) |
| professional_cockpit | ✅ | ✅ | ✅ | dashboard |
| cerfa_gate (validation humaine) | ✅ | ✅ | ✅ | gate |
| audit_trail / historique | ✅ | ✅ | ✅ | historique |
| cerfa_narrative_engine (anti-invention) | ✅ | ✅ | ✅ | texte_b/c/d/e |
| _composer_description_p8 (amplificateur) | ✅ | ✅ | ✅ (impression seule) | P8 |
| rules_engine | ✅ | ❓ aucun consommateur trouvé | ❓ | — |
| conversation_engine.CHECKLIST_MDPH | ✅ | refs internes | ❌ (déprécié) | — |
| instrumentation [TRACE_*] | ✅ | ✅ | ✅ | logs |

---
*Lecture seule. Statuts 🟡/❓ explicités. Aucune modification.*
