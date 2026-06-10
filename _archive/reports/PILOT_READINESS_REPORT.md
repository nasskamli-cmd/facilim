# PILOT_READINESS_REPORT.md — Préparation pilote ESSMS

**Généré le :** 2026-06-07
**Mode :** lecture seule. Synthèse de l'état réel pour décision pilote.

---

## QUESTION CENTRALE
**« Quel est aujourd'hui le principal blocage empêchant un professionnel ESSMS de produire un dossier MDPH fiable de bout en bout à partir d'une collecte réelle ? »**

**Réponse (PROUVÉE sur le code) :** la **collecte conversationnelle des champs structurés NIVEAU A**. Ces champs sont `requis=False` ; le pilote de questions (`base.py` L193-196) et `missing_fields` (L90) **ne sollicitent que les `requis=True`**. Résultat : même si l'extraction (1dccf6c), la persistance et le mapping AVQ (7e04f89) sont réparés, **les questions ne sont pas posées → les données n'arrivent pas → le CERFA reste pauvre**. C'est le **goulot unique amont**.

Blocage secondaire prouvé : le **mapping CERFA** de `organisme_payeur`/`numero_allocataire`/invalidité (V2 ne les écrit pas).

---

### CE QUI EST PROUVÉ
- Déploiement stable (`d3587d13`, Online, HTTP 200, 0 erreur).
- CERFA V2, anti-contamination (V2), cockpit/gate/audit/historique opérationnels (QA-PROD/QA-ANTI/QA-SCHEMA/QA-V1-REAL PASS).
- Extraction/persistance NIVEAU A : plomberie fonctionnelle (QA-V1-REAL, LLM mocké).
- `droits`/`avq_*` → CERFA fonctionnent **si** les données sont présentes (injection directe prouvée).
- **Goulot collecte** : NIVEAU A `requis=False` non sollicité (code base.py).
- **Gap mapping** : `numero_allocataire` non écrit au CERFA (P2 13 vide, mesuré).

### CE QUI EST DÉCLARÉ
- Les `SYSTEM_PROMPT` des agents *pourraient* aborder AVQ/droits hors checklist déterministe (non relus exhaustivement).
- Les narratifs restent affichables/imprimables (règle de confiance).

### CE QUI EST NON VÉRIFIÉ
- **Qualité d'extraction du LLM réel** (langage naturel → niveaux AVQ / objet `droits`) — testé en mock uniquement.
- **L'agent pose-t-il réellement les questions NIVEAU A ?** (dépend du SYSTEM_PROMPT + requis=False).
- **Visibilité dashboard** des champs structurés.
- **Bout-en-bout en production réelle** (volume DB prod inaccessible ; `railway ssh` bloqué).
- **AVQ sur fallback V3** ; **fusion multi-tours `droits`** ; **enum AVQ** côté LLM réel.

### BLOQUANTS PILOTE
1. **Collecte NIVEAU A non sollicitée** (requis=False) → CERFA pauvre. **BLOQUANT #1.**
2. **Mapping CERFA admin/invalidité absent** (organisme/allocataire/pension/catégorie/taux). **BLOQUANT #2** (le dossier reste incomplet sur l'administratif).

### RISQUES PILOTE
- Enum AVQ non conforme → cases AVQ silencieusement vides.
- Fallback V3 → réapparition de détection AVQ par mots-clés (contamination résiduelle).
- Correction usager ignorée (règle « ne pas réécraser admin »).
- Dépendance forte à la fiabilité du LLM d'extraction.

### CE QUI NE DOIT PAS ÊTRE DÉVELOPPÉ (tant qu'un blocage de traçabilité existe)
- ❌ Aucun nouveau moteur. ❌ Vague 2. ❌ Refonte dossier_strength. ❌ Nouveau mapping spéculatif. ❌ Modif de prompt métier sans point de rupture prouvé. ❌ Toute fonctionnalité avant de lever le BLOQUANT #1 (collecte).

### PROCHAIN TEST TERRAIN
Un **dossier réel WhatsApp** (adulte de préférence), conversation complète déclarant : CAF + n° allocataire, invalidité catégorie 2, aide habillage/repas/déplacements, AAH+PCH+RQTH. Puis génération CERFA + capture dashboard.

### DONNÉES À OBSERVER
| Étape | À observer | Teste |
|---|---|---|
| **WhatsApp** | l'agent pose-t-il les questions AVQ/droits/organisme/catégorie ? | BLOQUANT #1 |
| **Extraction** | logs `[CONV]` : champs captés ? `Champs rejetés` ? `Extraction échouée` ? | LLM réel |
| **Synthèse** | `synthese_json` (via dashboard) contient `avq_*`/`droits`/`organisme_payeur`/`categorie_invalidite` ? valeurs AVQ = enum ? | extraction + enum |
| **Dashboard** | taux de remplissage ; champs structurés visibles ? | visibilité |
| **CERFA** | cases AVQ cochées (depuis avq_*) ? P2 organisme/allocataire ? cases invalidité ? droits P17 ? moteur V2 vs fallback V3 ? | mapping + anti-contamination |

### CRITÈRE GO PILOTE
- L'agent **pose** les questions NIVEAU A en conversation réelle (BLOQUANT #1 levé) ;
- `synthese_json` contient les `avq_*`/`droits`/admin déclarés, valeurs AVQ conformes à l'enum ;
- CERFA : cases AVQ + droits corrects, **0 limitation inventée** ;
- mapping admin/invalidité au CERFA traité (sprint MAPPING-NIVEAU-A-CERFA) ;
- ≥ 5 dossiers réels internes sans régression.

### CRITÈRE NO GO PILOTE
- L'agent ne sollicite pas le NIVEAU A → CERFA pauvre (BLOQUANT #1 non levé) ;
- valeurs AVQ non conformes → cases vides ;
- limitations inventées réapparaissent (fallback V3) ;
- admin/invalidité absents du CERFA et jugés indispensables par la MDPH ;
- toute régression sur les droits ou le CERFA V2.

---

## VERDICT PILOTE (état actuel)
**NON GO** en l'état — non par instabilité technique (le socle est stable et testé), mais parce que le **BLOQUANT #1 (collecte NIVEAU A non sollicitée)** n'est **pas levé** et **non vérifié en terrain**. Le dossier produit aujourd'hui à partir d'une collecte réelle serait au niveau **B (brouillon à compléter)**, pas **C/D (exploitable / prêt pilote)**, tant que les champs structurés ne sont pas réellement collectés et mappés.

➡️ **Action unique prioritaire : exécuter le test terrain** pour confirmer/infirmer le BLOQUANT #1, **puis** décider (promotion `requis` / ajustement SYSTEM_PROMPT, et sprint MAPPING-NIVEAU-A-CERFA). Aucune autre développement avant cela.

---

*Rapport de préparation pilote, lecture seule. Toute affirmation classée PROUVÉ/DÉCLARÉ/NON VÉRIFIÉ. Aucune correction, aucun déploiement.*
