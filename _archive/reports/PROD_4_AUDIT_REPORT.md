# PROD_4_AUDIT_REPORT.md — Audit trail persistant & consultable

**Généré le :** 2026-06-06
**Sprint :** FACILIM PROD-4 — traçabilité uniquement (réutilisation de l'existant, aucun moteur, aucun recalcul)
**Statut :** ✅ Audit trail persistant et consultable — QA-PROD-4 PASS (7/7), aucune régression

---

## 0. Résultat

| Élément | Avant PROD-4 | Après PROD-4 |
|---|---|---|
| Cockpit professionnel | ✅ | ✅ |
| Gate CERFA | ✅ | ✅ |
| **Audit trail persistant** | partiel | ✅ |
| **Historique consultable** | ❌ (logs techniques) | ✅ (API par dossier) |
| **Traçabilité dossier** | ❌ | ✅ |

---

## 1. Diagnostic (vérifié dans le code)

### Mécanismes de journalisation DÉJÀ existants
| Mécanisme | Table | Écrit par | Statut |
|---|---|---|---|
| `event_logger.log_event()` | `audit_events` | main.py (accès dashboard, CERFA envoyé, droits validés, relances, conversation…) | ✅ persistant |
| `_log_cerfa_audit()` | `cerfa_audit_log` | main.py — **gate_export_check** (depuis PROD-3) | ✅ persistant |
| `cerfa_validations` | `cerfa_validations` | validation usager/pro | ✅ persistant |
| Route lecture | — | `GET /api/v1/audit/events` (admin, table `audit_events` seule) | ✅ existante |

### Événements DÉJÀ persistés
- Validation humaine → `DROITS_VALIDES` + table `cerfa_validations`
- Vérification gate (PASS/WARNING/BLOCK) → `gate_export_check` (cerfa_audit_log, PROD-3)
- Export CERFA autorisé → `CERFA_ENVOYE_USAGER` (audit_events) + `gate_export_check`
- Export CERFA refusé → `gate_export_check` (export_autorise=false)

### Événement NON persisté (la seule vraie lacune)
- **Calcul du cockpit** : PROD-1 ne faisait qu'un `logger.info` (log technique) → **non rejouable**.

### Lacune de consultation
- Pas d'endpoint reconstruisant l'historique **complet** d'un dossier (les deux journaux n'étaient pas fusionnés ; `/audit/events` ne lit que `audit_events` et est réservé admin).

**Point de vérité retenu :** les **deux tables existantes** (`audit_events` + `cerfa_audit_log`). Aucune nouvelle table — dette technique minimale.

---

## 2. Cartographie : événement → stockage → consultation

| Événement | Écrit par | Table de stockage | type/event_type | Consultation |
|---|---|---|---|---|
| 1. Calcul cockpit | `orchestration_engine` (PROD-4) → `event_logger.log_event` | `audit_events` | `COCKPIT_CALCULE` | `GET /dossiers/{id}/historique` |
| 2. Validation humaine | `main.py` → `event_logger` | `audit_events` (+ `cerfa_validations`) | `DROITS_VALIDES` | idem |
| 3. Vérification gate | `main.py _verrou_export_cerfa` → `_log_cerfa_audit` | `cerfa_audit_log` | `gate_export_check` (gate_statut=PASS/WARNING/BLOCK) | idem |
| 4. Export autorisé | `main.py` (verrou + envoi) | `cerfa_audit_log` / `audit_events` | `gate_export_check` (export_autorise=true) / `CERFA_ENVOYE_USAGER` | idem |
| 5. Export refusé | `main.py _verrou_export_cerfa` | `cerfa_audit_log` | `gate_export_check` (export_autorise=false, **raison**) | idem |

Consultation unifiée : `GET /api/v1/dossiers/{id}/historique` **fusionne** les deux tables, trie par date croissante, lecture seule.

---

## 3. Liste exacte des fichiers modifiés / créés

| Fichier | Modification | Justification | Moteur ? |
|---|---|---|---|
| `app/engines/orchestration_engine.py` | Après persistance du cockpit (bloc PROD-1), appel `event_logger.log_event("COCKPIT_CALCULE", …)` — bloc non bloquant | Persister le seul événement manquant (calcul cockpit) | Non — ligne de journalisation, aucune logique métier |
| `app/main.py` | (1) **Nouvel endpoint** `GET /api/v1/dossiers/{id}/historique` (fusion des 2 journaux, lecture seule) ; (2) ajout de `raison` au détail du verrou gate (export refusé) | Consultation de l'historique + raison du refus | Non — couche API/audit |
| `app/tests/qa/qa_prod_4.py` | **Nouveau** — test QA-PROD-4 | Test | Test |

**Aucune nouvelle table. Aucun nouveau moteur. Aucun recalcul.** Réutilisation intégrale de `audit_events`, `cerfa_audit_log` et `event_logger`.

---

## 4. Schéma de persistance (tables existantes réutilisées)

```sql
-- audit_events (migration 001) — journal général append-only
audit_events(
  id, dossier_id, usager_id, utilisateur_id, organisation_id,
  type_evenement, canal, sous_type, payload_json,
  ip_address, user_agent, session_id, idempotency_key, created_at
)
-- → reçoit COCKPIT_CALCULE, DROITS_VALIDES, CERFA_ENVOYE_USAGER…

-- cerfa_audit_log (migration 008) — journal CERFA append-only
cerfa_audit_log(
  id, dossier_id, event_type, event_at, canal,
  acteur_id, acteur_type, details_json, created_at
)
-- → reçoit gate_export_check (gate_statut, export_autorise, raison)

INDEX idx_cerfa_audit_dossier (dossier_id, event_at)
```

---

## 5. Exemples d'événements enregistrés (relus réellement via l'API)

Historique réel d'un dossier (sortie QA-PROD-4, `GET /dossiers/{id}/historique`) :

```
[2026-06-06T14:42:49] COCKPIT_CALCULE     src=audit_events     details={"score_completude":54,"score_solidite":55,"decision":"GO_AVEC_RISQUES","gate":"AUTORISE"}
[2026-06-06T14:42:49] gate_export_check   src=cerfa_audit_log  details={"action":"envoi","gate_statut":"PASS","gate_present":true,"export_autorise":true,"raison":""}
```

Événement d'export refusé (dossier BLOCK) :
```
gate_export_check  details={"action":"envoi","gate_statut":"BLOCK","export_autorise":false,"raison":"[test] BLOQUE_EXPORT"}
```

Chaque ligne répond à : **qui** (`acteur`/`utilisateur_id`), **quoi** (`type`), **quand** (`date`), **sur quel dossier** (`dossier_id`), **avec quel résultat** (`details`).

---

## 6. Résultat QA-PROD-4 (écritures + lectures réelles, FastAPI TestClient)

```
POST PASS → 400 (gate franchi) | POST BLOCK → 403 (refusé)
Historique PASS : 2 événements | Historique BLOCK : 1 événement

✅ Cas 1 — Calcul cockpit (écrit + relu)
✅ Cas 2 — Gate PASS (événement écrit)
✅ Cas 3 — Gate BLOCK (écrit + raison enregistrée)
✅ Cas 4 — Export autorisé (événement écrit)
✅ Cas 5 — Export refusé (événement écrit)
✅ Cas 6 — Historique chronologique cohérent (dates triées croissantes)
✅ Vérif statique : orchestration_engine journalise COCKPIT_CALCULE

DÉCISION QA-PROD-4 : ✅ PASS (7/7)
```

---

## 7. Non-régression

| Test | Résultat |
|---|---|
| QA-PROD-1 / QA-PROD-2 / QA-PROD-3 / QA-PROD-4 | ✅ PASS |
| QA-5 / QA-7 / QA-9 / QA-10 / QA-11 (n=100) | ✅ PASS |

---

## 8. Preuves — PROUVÉ / DÉCLARÉ / NON VÉRIFIÉ

### ✅ CE QUI EST PROUVÉ (écritures + lectures réelles, reproductibles)
- L'événement **calcul cockpit** est désormais persisté (`COCKPIT_CALCULE` dans `audit_events`) et **relu** via l'API.
- Les événements **gate PASS / BLOCK** sont persistés (`gate_export_check`), avec **raison** pour le refus.
- **Export refusé** et **export autorisé** sont distinguables et relisibles.
- `GET /dossiers/{id}/historique` **fusionne** les deux journaux et renvoie un **ordre chronologique cohérent**.
- Reproductible : `python -m app.tests.qa.qa_prod_4` (TestClient, écritures et lectures réelles).
- Aucune régression (QA-PROD-1→4 + QA-5/7/9/10/11).

### 🟦 CE QUI EST DÉCLARÉ
- L'événement `COCKPIT_CALCULE` en production est écrit par `orchestration_engine` à la fin de la collecte ; QA-PROD-4 le prouve via le **même** appel `event_logger.log_event` + une vérification statique que l'orchestrateur contient bien cet appel (le déclenchement complet exige le pipeline WhatsApp).
- Réutilisation du journal existant : pas de migration de données ; les événements antérieurs restent dans leurs tables d'origine.

### ⚠️ CE QUI EST NON VÉRIFIÉ
- Historique d'un dossier ayant traversé le **pipeline WhatsApp complet** réel (testé via écritures simulées équivalentes, pas via une conversation de bout en bout).
- Rendu de l'historique dans un **panneau dashboard** (la consultation est fournie en API ; aucun panneau UI ajouté ce sprint).
- Comportement en **PostgreSQL prod** (tests en SQLite).
- Politique de **rétention / purge RGPD** des journaux (hors périmètre de ce sprint).

---

## 9. Critères de refus — contrôle

| Critère de refus | Présent ? |
|---|---|
| Les événements restent uniquement dans les logs | ❌ Non — persistés en base (`audit_events`, `cerfa_audit_log`) |
| Aucun stockage persistant | ❌ Non — tables existantes réutilisées |
| Aucun historique consultable | ❌ Non — `GET /dossiers/{id}/historique` |
| QA-PROD-4 absent | ❌ Non — présent et PASS 7/7 |
| Absence de preuve de lecture | ❌ Non — lectures réelles via l'API (exemples §5) |

---

## Conclusion

FACILIM peut désormais **reconstruire l'historique complet d'un dossier** — calcul du cockpit, vérification du gate, export autorisé ou refusé (avec raison) — à partir de journaux **persistés** et **consultables** via une API unique, sans aucun recalcul ni nouveau moteur. La traçabilité, dernier verrou identifié avant pilote ESSMS, est en place.

| Élément | Statut |
|---|---|
| Cockpit professionnel | ✅ |
| Gate CERFA | ✅ |
| Audit trail persistant | ✅ |
| Historique consultable | ✅ |
| Traçabilité dossier | ✅ |

*Aucun moteur FACILIM 60→100 modifié. Aucune logique d'éligibilité, CDAPH, narratif ou CERFA métier touchée. Réutilisation maximale de l'infrastructure existante.*
