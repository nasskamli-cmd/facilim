# DEAD_CODE_AUDIT.md — Chasse au code mort (avec preuves)

**Généré le :** 2026-06-07
**Mode :** lecture seule. **Rien supprimé** (hors artefacts temporaires non suivis, traités dans CLEANUP_AUDIT.md). Classement : **PROUVÉ** (preuve d'absence de consommateur) · **POSSIBLE** (indices, non concluant) · **NON VÉRIFIÉ** (grep limité).

> ⚠️ Méthode : « jamais appelé » via recherche d'imports/références dans `app/`. Une absence de résultat n'est pas une preuve absolue (chargements dynamiques, routes, réflexion). D'où le classement prudent.

---

## Composants jamais appelés
| Élément | Indice | Classe |
|---|---|---|
| `app/engines/rules_engine.py` | aucun `import rules_engine` trouvé dans `app/` (seule sa propre définition) | **POSSIBLE** (orphelin probable — à confirmer par grep exhaustif incluant `services/` et chargements dynamiques) |
| `conversation_engine.CHECKLIST_MDPH` / `CHECKLIST_MDPH_BASE/ENFANT/MIXTE` / `CHECKLIST_IDS` | référencés **uniquement à l'intérieur** de conversation_engine ; la collecte active utilise `collecte_schema.checklist_for` | **POSSIBLE** (parallèle déprécié ; vérifier si `CHECKLIST_IDS` est consommé ailleurs) |

## Moteurs jamais utilisés
| Moteur | Réalité | Classe |
|---|---|---|
| (la plupart) | **câblés** via `facilim_prod` (chaîne 60→100) — voir ARCHITECTURE_REELLE | **PROUVÉ UTILISÉS** |
| `comite_agents` | importé/appelé dans `main.py` (L2026/2041) via une **route dédiée** ; usage dans le flux principal non tracé | **NON VÉRIFIÉ** (route possiblement non sollicitée par le parcours WhatsApp) |
| `parcours_engine`, `pro_report_engine` | appelés **conditionnellement** dans facilim_prod (L285/L328) | **POSSIBLE** rarement exécutés (selon branches) |

## Fonctions orphelines
| Fonction | Indice | Classe |
|---|---|---|
| fallback profil de `conversation_engine` (retourne `CHECKLIST_MDPH`) | lié au parallèle déprécié | **POSSIBLE** |
| `droits_objet_vers_liste` (collecte_schema) | helper d'affichage ; consommateur non confirmé | **NON VÉRIFIÉ** |
| **Non audité exhaustivement** | une chasse fonction-par-fonction exige un outil d'analyse statique (non exécuté) | **NON VÉRIFIÉ** |

## Prompts jamais exécutés
| Prompt | Réalité | Classe |
|---|---|---|
| `cerfa_narrative_engine._prompt_section_b/c/d/e` (anti-invention) | exécutés (génèrent texte_b/c/d/e via orch L923) | **PROUVÉ EXÉCUTÉS** |
| `cerfa_filler._composer_description_p8` (amplificateur) | exécuté (P8) mais **plus en source décisionnelle** (7e04f89) | **PROUVÉ EXÉCUTÉ** (impression seule) |
| ⚠️ **Doublon de philosophie** : deux prompts narratifs coexistent (anti-invention vs amplificateur) | les deux tournent | **DOUBLON CONFIRMÉ** (non mort, mais redondant/incohérent) |

## Checklists abandonnées
| Élément | Classe |
|---|---|
| `conversation_engine.CHECKLIST_MDPH*` (parallèle) vs `collecte_schema` (actif) | **POSSIBLE abandonnée** (déprécié explicite, refs internes) |

## Mappings obsolètes / divergents
| Élément | Réalité | Classe |
|---|---|---|
| **field_mapper (V3)** vs **cerfa_filler (V2)** | deux mappings CERFA ; V2 = prod, V3 = fallback. V3 **non assaini** (AVQ par mots-clés) | **DOUBLON CONFIRMÉ** (divergence de comportement = risque sur fallback) |
| `cerfa_reponses`/`donnees_structurees` (v2_bridge) | n'embarquent pas `organisme_payeur`/`numero_allocataire` | **GAP de mapping** (pas mort, incomplet) |

## Doublons
1. **Deux moteurs narratifs** (anti-invention `cerfa_narrative_engine` vs amplificateur `_composer_description_p8`). **CONFIRMÉ.**
2. **Deux mappers CERFA** (V2 cerfa_filler / V3 field_mapper). **CONFIRMÉ.**
3. **Deux checklists** (collecte_schema actif / CHECKLIST_MDPH déprécié). **POSSIBLE.**

---

## Synthèse
- **Aucun moteur de la chaîne 60→100 n'est mort** : tous câblés via facilim_prod (PROUVÉ).
- **Candidats au nettoyage (NON supprimés)** : `rules_engine` (POSSIBLE orphelin), `CHECKLIST_MDPH*` (déprécié), doublons narratif/mapper (à rationaliser plus tard, **après** tests terrain).
- **Toute suppression = sprint dédié + QA + preuve d'absence de consommateur** (règle : ne pas supprimer de source sans preuve). Rien n'est supprimé ici.

---

*Audit code mort en lecture seule. Classements prudents. Aucune suppression de source.*
