# ARCHITECTURE_STRUCTURATION_CIBLE.md

**Généré le :** 2026-06-07 · conception de référence. Aucun code, aucun moteur, aucun patch.
(Complète `ARCHITECTURE_CIBLE_STRUCTURATION_FACILIM.md` ; se concentre sur le modèle FAIT + cycle de vie + impact + simplifications.)

## MODÈLE UNIQUE — FAIT FACILIM
```json
{
  "id": "uuid",
  "domaine": "Professionnels",
  "champ": "intervenant.psychiatre",
  "valeur": "Dr COLLOMBARD",
  "source": "bilan BFP AIT ABBAS",
  "citation": "accompagnement par Mme COLLOMBARD la psychiatre",
  "confiance": "forte",
  "validation_professionnel": false,
  "validation_personne": false,
  "historique": [ {"valeur":"…","source":"…","date":"…","statut":"…"} ]
}
```
- **Hôte** : `synthese_json.faits[]` (additif, non-cassant — réutilise l'existant).
- **Référentiel domaines/champs** : `collecte_schema` (réutilisé).
- **source/citation** : réutilise `EvidenceItem.origine` + `_document_knowledge.extrait_source` + `pieces_justificatives`.

## STRUCTURE
- Un fait = une (domaine, champ) + valeur + provenance + confiance + 2 validations + historique.
- Le **texte libre** (bilan, narratif) reste comme **preuve attachée** (citation), jamais comme donnée.

## CYCLE DE VIE
`extrait` → `proposé` → `validé_professionnel` → `validé_personne` → (`rejeté`).
- Extraction (WA/doc) produit des faits `extrait`/`proposé`.
- Le professionnel valide/corrige (réutilise `human_validation`/`gate`).
- Le CERFA ne consomme que `validé_*`.

## FUSION (sans écrasement)
- **Enrichissement** : ajout d'un fait absent.
- **Correction** : nouvelle valeur **proposée** → ancienne en `historique` (jamais supprimée).
- **Conflit** : valeurs divergentes → coexistence + signalement validation.
- Priorité = **suggestion** (doc/pro > déclaratif vague ; usager prioritaire pour projet), jamais un écrasement silencieux.

## TRAÇABILITÉ
```
SOURCE(citation) → FAIT{source,citation,confiance,statut}
 → SYNTHÈSE (faits validés agrégés)
 → COCKPIT (faits + statut + origine)
 → MOTEURS (décident sur faits validés, pas sur texte)
 → CERFA (chaque champ/case = un fait validé tracé)
 → AUDIT (audit_events : qui/quand/quelle source — réutilisé)
```

## IMPACT (SOURCE → … → AUDIT) + simplifications possibles
| Étage | Aujourd'hui | Cible (faits) | Simplification |
|---|---|---|---|
| Source | texte → _document_knowledge/impact | faits {source,citation} | un seul format d'entrée |
| Synthèse | champs legacy + texte | `faits[]` (legacy dérivé) | fin des silos texte parallèles |
| Cockpit | score CDAPH + texte | faits + statut | complétude = couverture domaines |
| Moteurs | lisent texte+structuré mêlés | lisent **faits validés** | **supprime l'ambiguïté texte/preuve** (renforce anti-contamination) |
| CERFA | mapping depuis legacy | mapping depuis faits validés | un mapping unique (réduit le besoin du fallback divergent) |
| Audit | partiel | source/citation par fait | traçabilité native |

→ **Simplifiable à terme** : silos `_document_knowledge` bruts, double philosophie narrative, dépendance du CERFA au narratif.

## CRITÈRE DE RÉUSSITE
Les 5 faits exemples (COLLOMBARD, fatigabilité, ESAT, ménage, absences) deviennent des faits sourcés, validables, alimentant cockpit + CERFA, **sans narratif libre**, répondant à : d'où / qui / quel document / validé / où utilisé.

---
*Conception de référence. Aucun code, aucun moteur, aucune modification produit.*
