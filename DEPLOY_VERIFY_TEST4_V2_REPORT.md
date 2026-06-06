# DEPLOY_VERIFY_TEST4_V2_REPORT.md — Vérification production du correctif CERFA V2

**Généré le :** 2026-06-06
**Environnement :** Railway · projet `facilim` · production · https://www.facilim.fr
**Correctif déployé :** FIX-TEST4-CERFA-V2 (commit `5887b96`)

---

## Résumé

| Étape | Statut |
|---|---|
| 1. Déploiement Railway | ✅ Réussi (déploiement `99a7013a`, Online) |
| 2. Colonne `version` au démarrage | ✅ Créée en prod (`[STARTUP] … ['version']`) |
| 3. Rejeu WhatsApp TEST4 | ⏳ **À faire par l'utilisateur** (non pilotable par l'agent) |
| 4. Génération CERFA observée | ⏳ **En attente** (aucune génération depuis le déploiement) |
| 5. PDF V2 confirmé en prod | ⏳ **En attente** |

---

## CE QUI EST PROUVÉ (observé en production)

### Déploiement (ÉTAPE 1)
`railway up` → build Docker → `railway status` :
```
status:        ● Online
deployment ID: 99a7013a-638b-419c-9270-b3ca5d5ec497
facilim: ● Online · https://www.facilim.fr · facilim-volume
```
Le déploiement est passé de `386dfd91` (ancien) à `99a7013a` (nouveau, contenant le correctif), **sans coupure** (l'ancienne version est restée Online pendant le build).

### Démarrage + colonne version (ÉTAPE 2) — logs verbatim
```
2026-06-06 21:33:55,312 | INFO     | facilim.app | [STARTUP] Colonnes Phase 3+ ajoutées : ['version']
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```
→ Le filet `_COLONNES_PHASE3` a **créé la colonne `version`** dans la base de production au démarrage.
→ **Aucune erreur SQL au démarrage**, application démarrée avec succès.
→ La requête `SELECT version FROM dossiers` (cause de l'exception TEST4) **ne peut plus lever** `no such column: version` en prod (colonne désormais présente).

### Validation locale rappelée
QA-FIX-TEST4-CERFA-V2 : 4/4 PASS (le PDF V2 survit à une erreur d'audit) + non-régression 12/12 — voir `FIX_TEST4_CERFA_V2_REPORT.md`.

---

## CE QUI EST DÉCLARÉ (hypothèses fortes, non encore observées en prod)

- Le correctif étant double — (a) colonne `version` désormais présente, (b) audit hors du `try` de génération — **la prochaine génération CERFA en production utilisera le moteur V2** et ne basculera plus en fallback V3.
- La preuve locale (QA-FIX 4/4) montre que même si une erreur d'audit survenait, le PDF V2 serait conservé.

---

## CE QUI EST NON VÉRIFIÉ (restant à confirmer en prod)

- **Aucune génération CERFA n'a eu lieu en production depuis le déploiement** (filtre logs `CERFA` après 21:33:55 → vide). Le log décisif `[CERFA V2] PDF généré via moteur V2` n'a donc pas encore pu être observé.
- Le **rejeu complet WhatsApp** de TEST4 (création + bilan + « oui ») n'a pas été exécuté.
- Raison : l'agent **ne peut pas** piloter WhatsApp, ni s'authentifier au dashboard, ni utiliser `railway ssh` (accès refusé par le garde-fou de sécurité prod — non autorisé). Le déclenchement doit venir de l'utilisateur.

---

## LOGS DE DÉMARRAGE (copie exacte)
```
2026-06-06 21:33:55,312 | INFO     | facilim.app | [STARTUP] Colonnes Phase 3+ ajoutées : ['version']
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

## LOGS CERFA (copie exacte)
```
(aucune ligne CERFA depuis le déploiement 21:33:55 — aucune génération déclenchée)
```

---

## COMPARAISON AVANT / APRÈS

| Élément | Avant correctif (prod) | Après déploiement (prod) |
|---|---|---|
| Colonne `version` | absente | ✅ **présente** (`[STARTUP] … ['version']`) |
| `no such column: version` au démarrage | — | ✅ aucune |
| `no such column: version` à la génération | ✅ observé (logs 06-05 / 06-06) | ⏳ ne peut plus se produire (colonne présente) — à confirmer sur génération réelle |
| V2 utilisé | ❌ (fallback) | ⏳ à confirmer sur génération réelle |
| Fallback V3 | ✅ observé | ⏳ à confirmer absent sur génération réelle |
| PDF généré | V3 (dump dégradé) | ⏳ V2 attendu — à confirmer |

---

## VERDICT (mis à jour le 2026-06-06 après prévisualisation prod)
```
TEST4 CERFA V2 — CLOS
```
**Preuve (logs prod verbatim, génération du 2026-06-06 21:44, dossier c8438033 = NAIT-ALI) :**
```
21:44:51 | services.cerfa_expert | [EXPERT-P8] Narration LLM générée (1670 chars)
21:44:58 | services.cerfa_filler | [CERFA P8] Description générée par LLM (2171 chars)
21:44:58 | services.cerfa_filler | CERFA pré-rempli | NAIT-ALI | pages=20 | 14/16 cases cochées | droits=[]
21:44:59 | facilim.app | [CERFA] Page de couverture ajoutée | dossier=c8438033
21:44:59 | facilim.app | [CERFA V2] PDF généré via moteur V2 | dossier=c8438033 | 984750 bytes | hash=330bf40a…
GET /api/v1/dossiers/c8438033-…/cerfa.pdf HTTP/1.1 200 OK
```
- ✅ Moteur **V2 utilisé** (chaîne expert + filler + narration LLM).
- ✅ **Aucun fallback V3**.
- ✅ **Aucun** `no such column: version`.
- ✅ PDF généré : **984 750 octets** (= fichier `CF TEST 4.2 FACILIM.pdf`).

> **Le sujet CERFA V2 (fallback dû à l'erreur d'audit) est clos.** Le CERFA reste perfectible mais pour une **cause distincte, déjà diagnostiquée** : collecte court-circuitée → `droits=[]`, NIR/genre absents. Voir `VALIDATION_1_TEST4_FAILURE_AUDIT.md` (rupture orchestration / `droits_demandes` jamais peuplé). Cette correction de collecte n'a PAS été appliquée et constitue un chantier séparé.

---

## ACTION REQUISE POUR CLÔTURER (1 étape utilisateur + vérification agent)

1. **Côté vous (≈ 30 s)** — sur https://www.facilim.fr/dashboard, ouvrir le dossier **FAC-DOS-VKSP2HXQ** et cliquer **« Prévisualiser le CERFA »** (cela appelle `GET /cerfa.pdf` → `_generer_cerfa_pdf` → moteur V2 sur le dossier réel — **même chemin de génération que TEST4**, sans avoir à rejouer WhatsApp).
   *Option complète : rejouer le scénario TEST4 entier (création Karim + bilan + « oui ») si vous voulez aussi valider la collecte.*
2. **Côté agent** — je lirai immédiatement les logs (`railway logs -d --filter "CERFA"`) et confirmerai :
   - présence de `[CERFA V2] PDF généré via moteur V2`,
   - absence de `fallback V3` / `Moteur V2 indisponible` / `no such column: version`,
   - PDF généré + taille.
   → Sur observation conforme : **VERDICT mis à jour en TEST4 CLOS**.

---

## État (résultat attendu)
| Élément | Statut |
|---|---|
| Correctif déployé | ✅ |
| Colonne version présente | ✅ |
| V2 actif en production | ⏳ à confirmer sur 1 génération |
| Fallback V3 supprimé | ⏳ à confirmer |
| TEST4 clôturé | ⏳ en attente de l'action ci-dessus |

*Aucune modification de code dans ce tour. Déploiement réalisé sur autorisation explicite (commit + railway up). Accès `railway ssh` aux secrets prod refusé par le garde-fou — non contourné.*
