# CLASSIFICATION_PERTES_A_F.md — Nomenclature unique des pertes

**Généré le :** 2026-06-08 · nomenclature de mesure (aucun code).

## Catégories
| Code | Signification | Test de décision (preuve) |
|---|---|---|
| **A** | Absent de la source | le fait n'est dans aucune pièce/WA du dossier |
| **B** | Présent source mais **non extrait** | dans la source, mais absent de `synthese_json` ET de `_document_knowledge`/texte |
| **C** | **Extrait mais non structuré** | présent en **texte** (impact_quotidien / _document_knowledge / narratif) mais **pas** comme clé structurée dédiée |
| **D** | Structuré mais **non persisté** | clé attendue mais absente/vide dans `synthese_json` enregistré |
| **E** | Persisté mais **non utilisé** | clé présente dans `synthese_json` mais ni moteur ni cockpit ne la lit |
| **F** | Utilisé mais **absent du CERFA** | lu par un moteur/cockpit mais non écrit au CERFA (gap mapping) |

## Règle d'attribution (une seule catégorie par fait)
Parcourir SOURCE→STRUCTURÉ→SYNTHÈSE→COCKPIT/MOTEURS→CERFA ; la catégorie = **la première étape où le fait disparaît** :
- pas en source → A
- en source, pas extrait du tout → B
- extrait en texte seulement → **C**
- clé attendue mais vide/absente en synthese_json → D
- en synthese_json mais ignoré aval → E
- exploité mais pas au CERFA → F

## Pré-classement des preuves déjà acquises (à confirmer par export)
| Fait (TEST6) | Catégorie probable | Justification (preuve actuelle) |
|---|---|---|
| Santé.suivi_psychiatre (COLLOMBARD) | **C** | présent bilan → au mieux `_document_knowledge` texte, pas de clé structurée |
| Limitations.fatigabilite | **C** | « il fatigue vite » → texte, pas de champ structuré |
| Emploi.absences_sante | **C** | bilan → texte, pas de champ |
| Orientation.type (ESAT) | **C** (à confirmer) | WA → `projet_orientation` texte, pas d'orientation structurée |
| Identité.nom_prenom | **D ou F** (à confirmer) | présent source ; CERFA vide → soit non persisté au moment (D/timing), soit présent synthese mais PDF antérieur (F/timing) — **export requis** |
| organisme_payeur / allocataire / invalidité | **C/D** | définis NIVEAU A mais peu persistés ; non mappés CERFA |

> Catégorie **C (extrait mais non structuré)** = dominante attendue pour les domaines riches des bilans. À **confirmer fait par fait** avec le `synthese_json` réel.

---
*Nomenclature de mesure. Pré-classement marqué « probable / à confirmer » ; aucune conclusion définitive sans export.*
