# WORKFLOW_ACTUEL.md — Cartographie du parcours réel d'un dossier

**Généré le :** 2026-06-06
**Source :** lecture du code (`app/main.py`, `app/engines/orchestration_engine.py`)
**Statut :** après câblage FACILIM PROD-1

---

## 1. Chaîne d'exécution réelle

```
WhatsApp (message entrant)
   │  POST /webhook/whatsapp                              [main.py]
   ▼
main.py — webhook ASYNC : 200 OK immédiat → BackgroundTasks
   │
   ▼
OrchestrationService.traiter_message_async()             [orchestration_engine.py]
   │
   ├─ profile_engine          → ProfilUsager (âge, mineur, tutelle)
   ├─ conversation_engine     → routage agent + collecte structurée
   ├─ case_state_engine       → état d'avancement
   ├─ verbatim_engine         → verbatim cumulatif + relance intelligente
   ├─ inferencer_mdph         → hypothèses droits (78 règles)
   ├─ profil_handicap_engine  → profil_principal / secondaire
   ├─ document_functional_extractor → extraction documents (si pièce jointe)
   │
   ▼  (déclenché quand la collecte est COMPLÈTE)
_generer_narratif_et_qualite()                           [orchestration_engine.py ≈ l.874]
   │
   ├─ cerfa_narrative_engine  → texte_b/c/d/e (LLM, gpt-4o)
   ├─ cerfa_quality_agent     → score maturité + alertes
   ├─ analyse_situation_engine→ analyse 10 clés
   │
   ▼  ★ POINT D'INJECTION FACILIM PROD-1 ★
   facilim_prod.run(donnees)                             [NOUVEAU CÂBLAGE]
   │   → chaîne analytique FACILIM 60→100 (11 moteurs critiques)
   │   → cockpit_professionnel() (objet consolidé)
   │   → persistance dans dossiers.cockpit_pro_json
   │
   ▼
CERFA — pdf/cerfa_filler (remplissage AcroForm)          [pipeline existant]
   │
   ▼
Restitution : dashboard + API
   GET /api/v1/dashboard/dossiers/{id}  → SELECT * → dict(row)
       (renvoie automatiquement cockpit_pro_json)
```

---

## 2. Points d'entrée

| Point d'entrée | Fichier | Rôle |
|---|---|---|
| `POST /webhook/whatsapp` | main.py | Canal principal — réception messages usager (async) |
| `POST /api/v1/dossiers/{id}/lancer-conversation` | main.py | Démarrage conversation par le pro |
| `POST /api/v1/dossiers/{id}/upload-document` | main.py | Ajout d'une pièce |
| `GET /api/v1/dashboard/dossiers/{id}` | main.py | Lecture dossier (renvoie toutes les colonnes) |

## 3. Points de sortie

| Point de sortie | Fichier | Contenu |
|---|---|---|
| Message WhatsApp | whatsapp_service | Réponse à l'usager |
| `dossiers.cockpit_pro_json` | DB | **NOUVEAU** — cockpit consolidé persisté |
| `dossiers.texte_b/c/d/e` | DB | Narratifs CERFA |
| `dossiers.analyse_situation_json` | DB | Analyse de situation |
| CERFA rempli | pdf/cerfa_filler | PDF AcroForm |
| `GET .../dossiers/{id}` (API) | main.py | JSON dossier complet (cockpit inclus) |

---

## 4. Modules APPELÉS dans le parcours réel

**Collecte / conversation :** profile_engine · conversation_engine · case_state_engine · verbatim_engine · inferencer_mdph · profil_handicap_engine · document_functional_extractor · document_engine · scoring_engine · comite_agents
**Narratifs / qualité :** cerfa_narrative_engine · cerfa_quality_agent · analyse_situation_engine
**FACILIM 60→100 (depuis le câblage PROD-1) :** facilim_prod → evidence_engine · completeness_engine · refusal_risk_engine · cdaph_strategy_engine · eligibilite_droits_engine · strategie_dossier_engine · human_validation_engine · pre_submission_engine · action_plan_engine · parcours_engine · priorisation_engine · cerfa_gate_engine · professional_cockpit_engine · pro_report_engine · justificatifs_engine · questions_levier_engine · dossier_strength_engine
**CERFA :** pdf/cerfa_filler · pdf/field_mapper

## 5. Modules encore IGNORÉS dans le parcours réel

| Module | Statut | Raison |
|---|---|---|
| `audit_trail_engine` | Non appelé | Exécuté seulement si `generer_cerfa=True` ; le câblage PROD-1 l'appelle avec `False` |
| `pdf/field_mapper` **via facilim_prod** | Non appelé par PROD-1 | Le CERFA reste produit par le pipeline `cerfa_filler` existant |
| `explainability_engine` | Orphelin | `expliquer_dossier` importé uniquement par QA-8 ; le cockpit utilise `questions_levier_engine` directement |

## 6. Avant / Après (synthèse)

- **Avant PROD-1 :** la chaîne s'arrêtait à narratifs + analyse de situation. Les moteurs FACILIM 60→100 existaient mais n'étaient **jamais appelés** dans le parcours.
- **Après PROD-1 :** à la fin de la collecte, `facilim_prod.run()` exécute les 11 moteurs critiques, produit le cockpit consolidé et le **persiste**. Le cockpit est exposé automatiquement par l'API de lecture dossier.
