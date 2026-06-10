# MATRICE_TRACEABILITE_FAITS.md — Localiser l'étape de disparition

**Généré le :** 2026-06-08 · gabarit de mesure (à remplir avec les données réelles : pièces + `synthese_json` exporté + CERFA).
**5 étapes :** SOURCE → STRUCTURÉ (clé dans synthese_json) → SYNTHÈSE (valeur exploitable) → COCKPIT (affiché) → CERFA (écrit).
Valeurs : ✅ présent · ❌ absent · ❓ NON VÉRIFIÉ.

## Gabarit (une ligne par fait du référentiel)
| Fait (domaine.champ) | SOURCE (citation) | STRUCTURÉ (clé synthese_json) | SYNTHÈSE (valeur) | COCKPIT | CERFA | Dernière étape où il existe |
|---|---|---|---|---|---|---|
| Identité.nom_prenom | ✅/❌ | `nom_prenom` ✅/❌ | … | … | P2 | … |
| Administratif.organisme_payeur | … | `organisme_payeur` | … | … | P2 | … |
| Santé.suivi_psychiatre | … | (clé ?) | … | … | P8 | … |
| Limitations.fatigabilite | … | (clé ?) | … | … | P7 | … |
| AVQ.avq_gestion_quotidienne | … | `avq_gestion_quotidienne` | … | … | P6 | … |
| Orientation.type | … | (clé ?) | … | … | E3 | … |
| … (tous les faits du référentiel) | | | | | | |

## Pré-rempli avec les preuves DÉJÀ acquises (TEST6 / AIT ABBAS, CERFA = CF TEST 6)
| Fait | SOURCE | STRUCTURÉ | SYNTHÈSE | COCKPIT | CERFA | Dernière étape |
|---|---|---|---|---|---|---|
| Identité.nom_prenom | ✅ (« AIT ABBAS Abdelkarim ») | ❓ (à exporter) | ❓ | ❓ | ❌ (texte CERFA vide hors en-tête) | **SOURCE** (au moins jusqu'à CERFA : absent) |
| Santé.suivi_psychiatre | ✅ (« Mme COLLOMBARD ») | ❌ (pas de clé structurée — texte/_document_knowledge) | ❓ texte | ❓ | ❌ | **SOURCE→texte** |
| Limitations.fatigabilite | ✅ (« il fatigue vite ») | ❌ | ❓ texte | ❓ | ❌ | **SOURCE→texte** |
| Orientation.type (ESAT) | ✅ (WA) | ❓ (`projet_orientation` ?) | ❓ | ❓ | ❌/❓ case | **SOURCE** |
| Emploi.absences_sante | ✅ (« absent … raison médicale ») | ❌ | ❓ texte | ❓ | ❌ | **SOURCE→texte** |

> Les colonnes ❓ deviennent ✅/❌ **mesurées** dès l'export du `synthese_json` réel (endpoint existant). La règle : la **dernière colonne ✅** = dernière étape où le fait existe ; la **première colonne ❌ suivante** = étape de disparition.

---
*Gabarit de mesure. Aucune modification produit.*
