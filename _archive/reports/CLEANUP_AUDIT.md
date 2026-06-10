# CLEANUP_AUDIT.md — Audit de nettoyage FACILIM

**Généré le :** 2026-06-07
**Mode :** lecture seule + suppression d'artefacts temporaires **non suivis uniquement**. Aucun fichier source supprimé, aucun code métier touché, aucun commit, aucun déploiement.

---

## Actions réalisées (sûres, autorisées)
- 🗑️ **36 PDF non suivis** supprimés de `storage/cerfa/` (artefacts QA `cerfa_QAFIX_T4_*`, `cerfa_QAP3_BLO_*`, générés à chaque exécution de QA).
- 🛡️ **`.gitignore` complété** : `storage/cerfa/*.pdf` + `app/tests/qa/reports/*.html` (empêche la réapparition de ces artefacts en untracked).
- ✅ Garde-fou : la suppression a d'abord été **abandonnée** quand des fichiers suivis ont été détectés ; seuls les **non suivis** ont été retirés.

---

## Tableau d'audit

| Élément | Type | Utilisé ? | Risque si supprimé | Action recommandée | Statut |
|---|---|---|---|---|---|
| `storage/cerfa/*.pdf` (36 non suivis) | Artefact QA généré | Non (regénéré) | Aucun | **Supprimer** | ✅ **FAIT** |
| `storage/cerfa/*.pdf` (23 **suivis git**) | Artefact QA commité par erreur | Non | Aucun (mais dans l'historique git) | `git rm --cached` puis commit (besoin validation) | ⏸️ Recommandé |
| `app/tests/qa/reports/*.html` (5, modifiés) | Rendu QA regénéré, **suivi** | Non décisionnel | Faible | `git checkout --` pour revenir au commit, puis gitignore | ⏸️ Recommandé |
| `app/tests/qa/reports/*.md` (massive_qa/ghost_fields/pdf_audit/qa7…, ~80, suivis) | Rapports QA horodatés regénérés | Non | Faible | Archiver hors repo OU `git rm` (besoin validation) | ⏸️ Recommandé |
| `app/tests/audit/reports/*.md` | Rapports d'audit horodatés | Non | Faible | idem | ⏸️ Recommandé |
| Scripts temporaires `_*.py` | Temp | — | — | — | ✅ Aucun (déjà nettoyés) |
| `*.db` (`mdph_dossiers.db`, `facilim.db`, backup) | Base locale | Oui (tests locaux) | **Perte données locales** | **Ne pas toucher** (déjà gitignore `*.db`) | 🔒 Conserver |
| `.env` | Secrets | Oui | Critique | **Ne pas toucher** (gitignore) | 🔒 Conserver |
| `conversation_engine.CHECKLIST_MDPH` | Checklist **dépréciée** (Vague 1) | Non (commentée DÉPRÉCIÉ) | Faible mais code mort | Laisser (suppression = sprint dédié + QA) | ⏸️ Ne pas toucher |
| Rapports `.md` de session (AUDIT_*, FIX_*, PLAN_*, MDPH_*, DEPLOY_*, VAGUE1_*) | Livrables de traçabilité | Oui (mémoire projet) | Perte d'historique décisionnel | **Conserver** | 🔒 Conserver |
| `VAGUE1_PROD_VALIDATION_REPORT.md`, `DEPLOY_VALIDATION_PRE_MANUAL_REPORT.md` | Livrables (non commités) | Oui | — | Conserver (commit ultérieur au choix) | 🔒 Conserver |
| `DEPLOY_CHECKLIST.md`, `retours_terrain.md` | Docs projet | Oui | — | Conserver | 🔒 Conserver |
| `.venv/`, `node_modules/` | Dépendances | Oui (runtime/tests) | Réinstall nécessaire | Ne pas toucher (gitignore) | 🔒 Conserver |

---

## Recommandations (NON appliquées — nécessitent votre validation/commit)
1. **Désindexer les 23 PDF suivis** : `git rm --cached storage/cerfa/*.pdf` puis commit → allège le repo (le `.gitignore` les ignorera ensuite). *(nécessite un commit → non fait.)*
2. **Désindexer les rapports QA horodatés** (`app/tests/qa/reports/*.md`, `app/tests/audit/reports/*.md`) : ~80+ fichiers regénérés → `git rm --cached` + gitignore, ou archivage hors repo. *(non fait.)*
3. **Revenir au commit pour les 5 HTML modifiés** : `git checkout -- app/tests/qa/reports/*.html` (revert du bruit de rendu). *(non fait — modifie le working tree de fichiers suivis.)*
4. **Code mort** : `CHECKLIST_MDPH` (déprécié) → suppression à planifier dans un sprint dédié avec QA (pas en nettoyage à chaud).

---

## Ce qui N'A PAS été touché (par sécurité)
Aucun fichier **suivi git**, aucun **code métier**, aucun **moteur**, aucun **CERFA**, aucun **prompt**, aucune **base `.db`**, aucun **secret**. Aucun commit, aucun déploiement.

---

## Imports inutilisés / code mort
- **Non audité ligne à ligne** (hors périmètre sûr sans exécution d'outils d'analyse). Seul `CHECKLIST_MDPH` est identifié comme **déprécié explicite**. Toute suppression d'import/code = sprint dédié + QA (règle : ne pas supprimer de source sans preuve+validation).

---

*Nettoyage limité aux artefacts temporaires non suivis. Le reste est documenté pour décision ultérieure.*
