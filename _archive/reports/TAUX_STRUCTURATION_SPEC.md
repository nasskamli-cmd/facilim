# TAUX_STRUCTURATION_SPEC.md — Définition des taux

**Généré le :** 2026-06-08 · spécification de calcul (aucun code).

## Définitions
- **Fait observé** : fait présent dans une source (pièce/WhatsApp) du dossier (référentiel « or » du dossier).
- **Fait structuré** : fait présent comme **clé/valeur structurée** dans `synthese_json` (pas seulement dans du texte libre : impact_quotidien, _document_knowledge, narratifs).
- **Fait exploité** : fait lu par un moteur/cockpit ou écrit au CERFA.

## Taux
- **Taux de structuration (global)** = `faits_structurés / faits_observés`.
- **Taux de persistance** = `faits_persistés (synthese_json) / faits_structurés`.
- **Taux d'exploitation** = `faits_au_CERFA_ou_cockpit / faits_structurés`.
- **Taux de bout-en-bout** = `faits_au_CERFA / faits_observés` (le plus parlant).

## Par domaine
Calculer chaque taux **par domaine** (identité, santé, professionnels, AVQ, limitations, orientation, droits, projet, emploi, …) :
`taux_domaine = faits_structurés_domaine / faits_observés_domaine`.

## Tableau de restitution (à remplir par dossier)
| Domaine | Faits observés | Faits structurés | Taux struct. | Faits au CERFA | Taux bout-en-bout |
|---|---|---|---|---|---|
| Identité | | | | | |
| Santé | | | | | |
| Professionnels | | | | | |
| AVQ | | | | | |
| Limitations | | | | | |
| Orientation | | | | | |
| Droits | | | | | |
| Projet de vie | | | | | |
| **GLOBAL** | | | | | |

## Convention de comptage
- Un fait « en texte uniquement » (présent dans impact_quotidien / _document_knowledge / narratif mais sans clé structurée dédiée) compte comme **observé** mais **NON structuré**.
- Un fait dont la clé existe mais la valeur est vide compte comme **non structuré** (clé vide ≠ structuré).

## Attendu (hypothèse à confirmer par la mesure)
D'après les preuves déjà acquises (bilans riches → CERFA quasi vide), on s'attend à un **taux de structuration faible pour Santé/Professionnels/Limitations/AVQ/Orientation** et correct pour Identité de base (si peuplée). **À confirmer par l'export réel** — aucune valeur chiffrée n'est affirmée ici sans données.

---
*Spécification de calcul. Aucune valeur inventée ; à remplir avec les exports réels.*
