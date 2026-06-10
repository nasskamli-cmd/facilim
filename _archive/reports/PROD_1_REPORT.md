# PROD_1_REPORT.md — Branchement réel du workflow FACILIM 60→100

**Généré le :** 2026-06-06
**Mission :** FACILIM PROD-1 — câblage uniquement (aucun nouveau moteur, aucune logique métier modifiée)
**Statut :** ✅ Câblage réalisé et vérifié — QA-PROD-1 4/4 PASS, aucune régression (7/7 QA)

---

## 1. Workflow réel — AVANT

```
WhatsApp → main.py → orchestration_engine
   → collecte (profile, conversation, inférences, profil handicap)
   → _generer_narratif_et_qualite()
        → narratifs B/C/D/E (LLM)
        → score qualité
        → analyse de situation
   → CERFA (cerfa_filler)
   → [FIN]
```

Les moteurs FACILIM 60→100 (éligibilité, CDAPH, risques, complétude, validation
humaine, plan d'action, gate, cockpit, rapports) **existaient et passaient les QA,
mais n'étaient appelés par aucun point du parcours** (vérifié : `facilim_prod`
n'était importé que par ses propres modules).

## 2. Workflow réel — APRÈS

```
WhatsApp → main.py → orchestration_engine
   → collecte …
   → _generer_narratif_et_qualite()
        → narratifs B/C/D/E (LLM)
        → score qualité
        → analyse de situation
        → ★ facilim_prod.run(donnees)               [NOUVEAU]
              → 11 moteurs critiques FACILIM 60→100
              → cockpit_professionnel() (22 clés)
              → persistance dossiers.cockpit_pro_json
   → CERFA (cerfa_filler)
   → API GET /dossiers/{id} renvoie cockpit_pro_json [exposé automatiquement]
```

**Modifications réalisées (intégration pure) :**
1. `app/engines/facilim_prod.py` — ajout du point d'entrée `run()` + méthode `cockpit_professionnel()` (consolidation, sérialisation défensive).
2. `app/engines/orchestration_engine.py` — injection d'un bloc **non bloquant** dans `_generer_narratif_et_qualite()` après l'analyse de situation.
3. `app/database/migrations/013_cockpit_prod_1.sql` — colonne `cockpit_pro_json`.
4. `app/main.py` — ajout de `cockpit_pro_json` au filet de sécurité `_COLONNES_PHASE3` (garantie de présence au démarrage).
5. `app/tests/qa/qa_prod_1.py` — QA-PROD-1.

**Bug d'intégration corrigé au passage :** le moteur de migrations ignore tout segment SQL commençant par `--`. Un `ALTER TABLE` précédé d'un bloc de commentaires était happé dans le même segment et **jamais exécuté** (alors que la migration était marquée « appliquée »). C'est le même incident que la note historique « colonne analyse_situation_json — migration partielle SQLite ». La migration 013 place donc l'`ALTER` en première position, et `main.py` garantit la colonne au démarrage.

## 3. Moteurs désormais CONNECTÉS au parcours

11 moteurs critiques exécutés à chaque dossier complété (vérifié 11/11 sur 4 profils) :

evidence_engine · completeness_engine · refusal_risk_engine · cdaph_strategy_engine ·
eligibilite_droits_engine · strategie_dossier_engine · human_validation_engine ·
pre_submission_engine · action_plan_engine · cerfa_gate_engine · professional_cockpit_engine

\+ moteurs support exécutés indirectement : parcours_engine · priorisation_engine ·
justificatifs_engine · questions_levier_engine · dossier_strength_engine · pro_report_engine.

## 4. Moteurs encore DÉBRANCHÉS

| Moteur | Pourquoi | Pour le brancher |
|---|---|---|
| `audit_trail_engine` | PROD-1 appelle `facilim_prod.run(generer_cerfa=False)` | Passer `generer_cerfa=True` + persister `journal_audit` |
| `cerfa_gate_engine` (application) | Le gate est **calculé** (visible dans le cockpit) mais **non appliqué** avant l'export CERFA | Appeler `verifier_gate_cerfa()` dans le chemin d'export PDF |
| `explainability_engine` | Orphelin (importé seulement par QA-8) | Le brancher dans le cockpit, ou le retirer |
| `field_mapper` via facilim_prod | Le CERFA réel passe par `cerfa_filler` | Aucune action — doublon volontairement évité |

## 5. Résultats désormais visibles pour le professionnel

**Mesure réelle — QA-PROD-1 (4 profils, sans LLM) :**

| Profil | Câblage | Temps | Décision | Complét. | Solidité | Droits détectés | Droits oubliés | Actions | Questions | Pièces | Gate export |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Karim — Accident travail | ✅ | 43 ms | GO_AVEC_RISQUES | 54 | 55 | 2 | 0 | 7 | 5 | 7 | bloqué (False) |
| Lucas — TSA enfant léger | ✅ | 6 ms | GO_AVEC_RISQUES | 40 | 27 | 2 | 0 | 9 | 2 | 5 | autorisé |
| SEP — Sclérose en plaques | ✅ | 6 ms | GO_AVEC_RISQUES | 44 | 34 | 3 | 0 | 10 | 5 | 5 | autorisé |
| Aidant familial | ✅ | 4 ms | GO_AVEC_RISQUES | 38 | 27 | 2 | 0 | 9 | 5 | 4 | autorisé |

**Le cockpit consolidé (`cockpit_pro_json`, 22 clés) contient :** score complétude · score
solidité · décision GO/RISQUES/NO_GO · risques de refus · droits détectés · droits oubliés ·
questions ROI · pièces prioritaires · plan d'action · validation humaine · verrou d'export ·
résumé + rendu texte.

**Canal de visibilité :** exposé automatiquement par `GET /api/v1/dashboard/dossiers/{id}`
(`SELECT * → dict(row)`). **Non encore rendu** par un panneau dédié du dashboard
(cf. VISIBILITY_AUDIT.md — niveau 🟡 partiellement visible).

## 6. Risques restants

1. **Affichage UI manquant.** Les données sont persistées et dans l'API, mais aucun panneau du dashboard ne rend le cockpit. → niveau 🟡, pas ✅.
2. **Gate non appliqué.** `cerfa_gate_engine` est calculé mais le chemin d'export CERFA ne l'invoque pas → un CERFA peut sortir sans contrôle.
3. **Journal d'audit débranché** (`generer_cerfa=False`) → pas de traçabilité persistée par dossier.
4. **Droits oubliés = 0** sur les 4 profils de test. À investiguer : la détection `droits_omis` ne s'active pas sur ces données ; à confronter au réel (la valeur métier « droits oubliés » est un argument clé de FACILIM).
5. **Scores bas sur données peu narratives** (solidité 27-55, complétude 38-54) — cohérent avec les QA synthétiques ; non représentatif d'un dossier réel enrichi par LLM.
6. **Coût d'exécution** : `facilim_prod.run()` ajoute 4-43 ms par dossier complété (négligeable, en BackgroundTask).
7. **Toujours zéro test sur dossier réel** et zéro validation par un professionnel MDPH.

## 7. Travail restant avant pilote ESSMS

| Action | Priorité | Effort estimé |
|---|---|---|
| Panneau « Cockpit FACILIM » dans `dashboard.html` (lit `cockpit_pro_json`) | P0 | ~1 j |
| Appliquer `verifier_gate_cerfa()` avant l'export CERFA | P0 | ~0.5 j |
| Brancher + persister le journal d'audit (`generer_cerfa=True`) | P1 | ~1 j |
| Investiguer la détection « droits oubliés » (0 sur les 4 profils) | P1 | ~0.5 j |
| Tester sur 5 dossiers MDPH réels (anonymisés) + clé OpenAI active | P0 | ~2 j |
| Validation de pertinence par un professionnel MDPH | P0 | ~1 j |

**Estimation : ≈ 5-6 jours** pour atteindre un pilote ESSMS exploitable (interface + gate + audit + test terrain).

---

## Conclusion

Le problème principal identifié par le READINESS_REPORT — *« les moteurs FACILIM 60→100
ne participent pas au parcours »* — **est résolu sur le plan du câblage** : à chaque dossier
complété, la chaîne s'exécute, produit un cockpit unique consolidé et le persiste, exposé par
l'API. Vérifié sur 4 profils (11/11 moteurs, 4/4 PASS) sans aucune régression (7/7 QA classiques).

**Il reste un pas, et un seul, pour que le professionnel le VOIE vraiment : l'affichage**
(un panneau dashboard) **et l'application du gate avant export.** C'est du travail d'interface
et de chemin d'export, pas de logique métier.

*Aucun nouveau moteur. Aucune logique d'éligibilité, CDAPH, droits ou CERFA modifiée.*
