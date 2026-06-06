# PROD_3_GATE_REPORT.md — Application réelle du gate CERFA

**Généré le :** 2026-06-06
**Sprint :** FACILIM PROD-3 — verrou d'export (application uniquement, aucun recalcul, aucun moteur modifié)
**Statut :** ✅ Gate appliqué — QA-PROD-3 PASS, aucune régression. Un export BLOCK est désormais réellement refusé (403).

---

## 0. Résultat

| Élément | Avant PROD-3 | Après PROD-3 |
|---|---|---|
| Gate calculé | ✅ | ✅ |
| Gate persisté | ✅ | ✅ |
| Gate visible | ✅ | ✅ |
| **Gate appliqué** | ❌ | ✅ |
| **Export sécurisé** | ❌ | ✅ |

---

## 1. Diagnostic — flux d'export actuel (vérifié dans le code)

```
Utilisateur (dashboard)
  ├─ bouton « Prévisualiser »  → previsualiserCerfa()  → window.open(GET /cerfa.pdf)
  │                                                       → telecharger_cerfa() → _generer_cerfa_pdf()  [CONSULTATION]
  └─ bouton « Envoyer »        → envoyerCerfa()        → POST /envoyer-cerfa
                                                          → envoyer_cerfa() → _generer_cerfa_pdf() → email Brevo  [EXPORT RÉEL]
```

| Élément | Fichier / fonction | Rôle |
|---|---|---|
| Bouton export | `dashboard.html` → `envoyerCerfa()` (L1120) | Transmission email = export réel |
| Bouton prévisualisation | `dashboard.html` → `previsualiserCerfa()` (L1114) | Consultation — doit rester libre |
| Route transmission | `main.py` `@POST /api/v1/dossiers/{id}/envoyer-cerfa` (`envoyer_cerfa`) | Génère + envoie |
| Route PDF | `main.py` `@GET /api/v1/dossiers/{id}/cerfa.pdf` (`telecharger_cerfa`) | Sert le PDF (prévisualisation inline) |
| Génération PDF | `main.py` `_generer_cerfa_pdf()` (centrale, appelée par les deux) | Produit le PDF |
| Audit existant | `main.py` `_log_cerfa_audit()` → table `cerfa_audit_log` | Journalisation |

**Constat :** la génération est centralisée (`_generer_cerfa_pdf`) mais elle sert **à la fois** la prévisualisation (qui doit rester libre) et la transmission. Le verrou ne doit donc PAS être posé sur `_generer_cerfa_pdf` (sinon il bloque la prévisualisation), mais au **point d'export réel**.

---

## 2. Cartographie : export actuel → export sécurisé

```
AVANT                                   APRÈS (PROD-3)
─────                                   ──────────────
POST /envoyer-cerfa                     POST /envoyer-cerfa
  → génère PDF                            → _verrou_export_cerfa(...)   ← lit cockpit_pro_json (gate déjà calculé)
  → envoie email                            ├─ BLOCK   → 403, AUCUN PDF, AUCUN email
                                            ├─ WARNING → autorisé + avertissement renvoyé
                                            └─ PASS    → autorisé
                                          → (si autorisé) génère PDF → email

GET /cerfa.pdf                          GET /cerfa.pdf            → prévisualisation : INCHANGÉE, jamais bloquée
                                        GET /cerfa.pdf?export=true → export définitif : _verrou_export_cerfa(...) → 403 si BLOCK
```

Le verrou est **centralisé** dans une seule fonction `_verrou_export_cerfa()` (aucune duplication), appelée aux deux points d'export.

---

## 3. Liste exacte des fichiers modifiés / créés

| Fichier | Modification | Moteur / logique métier ? |
|---|---|---|
| `app/services/export_gate.py` | **Nouveau** — `lire_gate_export()` : lit `gate_export.decision` depuis `cockpit_pro_json` et le mappe en PASS/WARNING/BLOCK. **Fonction pure, aucun recalcul.** | Non — lecteur, pas un moteur |
| `app/main.py` | (1) `_verrou_export_cerfa()` (verrou centralisé : lit le gate persisté, journalise, lève 403 si BLOCK) ; (2) appel dans `envoyer_cerfa` ; (3) param `export` + appel conditionnel dans `telecharger_cerfa` ; (4) statut gate ajouté à la réponse d'envoi | Non — couche export uniquement |
| `app/dashboards/dashboard.html` | `envoyerCerfa()` : affiche l'avertissement WARNING au succès (le refus 403 BLOCK était déjà géré par la branche `data.detail`) | Non — affichage |
| `app/tests/qa/qa_prod_3.py` | **Nouveau** — test QA-PROD-3 | Test |

**Aucun moteur FACILIM 60→100 modifié. Aucun recalcul du gate. Aucune nouvelle évaluation.**

---

## 4. Preuve de lecture du gate depuis la persistance

Le verrou lit **exclusivement** la colonne déjà persistée `dossiers.cockpit_pro_json` (clé `gate_export.decision`) — il n'appelle aucun moteur.

`app/services/export_gate.py` (cœur) :
```python
_DECISION_MAP = {"AUTORISE":"PASS", "AUTORISE_AVEC_AVERTISSEMENTS":"WARNING", "BLOQUE_EXPORT":"BLOCK"}

def lire_gate_export(cockpit_pro_json):
    cockpit  = json.loads(cockpit_pro_json) if isinstance(cockpit_pro_json, str) else (cockpit_pro_json or {})
    gate     = (cockpit or {}).get("gate_export") or {}
    decision = gate.get("decision")              # valeur DÉJÀ calculée par cerfa_gate_engine
    statut   = _DECISION_MAP.get(decision, "UNKNOWN")
    return {"statut": statut, "autorise_export": statut != "BLOCK", "present": decision is not None, ...}
```

`app/main.py` (`_verrou_export_cerfa`) :
```python
row = db.execute("SELECT cockpit_pro_json FROM dossiers WHERE id = ?", (dossier_id,)).fetchone()
g = lire_gate_export(row["cockpit_pro_json"] if row else None)   # lecture, pas de recalcul
_log_cerfa_audit(db, dossier_id, event_type="gate_export_check", ... details={"gate_statut": g["statut"], ...})
if not g["autorise_export"]:
    raise HTTPException(status_code=403, detail=g["message"] or "Export bloqué par FACILIM (gate BLOCK)…")
```

**Preuve QA (Partie A)** — la décision suit le gate persisté :
```
PASS    → statut=PASS    autorise_export=True
WARNING → statut=WARNING autorise_export=True
BLOCK   → statut=BLOCK   autorise_export=False
ABSENT  → statut=UNKNOWN autorise_export=True   (fail-open documenté, cf. §6)
```

---

## 5. Résultats QA-PROD-3 (exécution réelle via FastAPI TestClient)

```
A. Fonction pure lire_gate_export                          → 4/4 ✅
B. Exécution réelle de la route :
   ✅ PASS     POST /envoyer-cerfa            → non bloqué (400 — étape suivante : email manquant)
   ✅ WARNING  POST /envoyer-cerfa            → non bloqué (400)
   ✅ BLOCK    POST /envoyer-cerfa            → REFUSÉ (403) — aucun PDF, aucun email
   ✅ ABSENT   POST /envoyer-cerfa            → non bloqué (400) — fail-open documenté
   ✅ BLOCK    GET /cerfa.pdf?export=true     → REFUSÉ (403)
   ✅ BLOCK    GET /cerfa.pdf (prévisualisation) → NON bloquée (200)
C. Trace d'audit : 5 entrées 'gate_export_check' journalisées dans cerfa_audit_log

DÉCISION QA-PROD-3 : ✅ PASS (A=True, B=True, C=True)
```

> Lecture des codes : pour PASS/WARNING/ABSENT, la route renvoie **400** (« email manquant ») — ce qui prouve que le gate a **laissé passer** et que l'échec vient d'une étape ultérieure, pas du verrou. Pour BLOCK, la route renvoie **403** avant toute génération.

### Règle fonctionnelle appliquée
| Gate | Export | Comportement |
|---|---|---|
| PASS | ✅ autorisé | — |
| WARNING | ✅ autorisé | message renvoyé (`gate_avertissement`), affiché au pro ; tracé dans l'audit |
| BLOCK | ❌ refusé | 403, aucun CERFA généré, aucun email/téléchargement |

---

## 6. Scénario 4 — absence de gate (choix documenté)

**Choix : fail-open** — si `cockpit_pro_json` est absent ou ne contient pas de `gate_export` (gate `UNKNOWN`), l'export est **autorisé** et l'audit enregistre `gate_present=false`.

**Justification :**
- Le gate ne refuse que sur un signal **explicite** BLOCK (cohérent avec `cerfa_gate_engine`, qui ne bloque que sur des blocages critiques avérés).
- Des dossiers créés **avant** PROD-1 n'ont pas de `cockpit_pro_json` ; un fail-closed bloquerait tous ces exports → régression d'usage.
- Choix **testé** (scénario ABSENT → non bloqué).

---

## 7. Non-régression

| Test | Résultat |
|---|---|
| QA-PROD-1 | ✅ PASS |
| QA-PROD-2 | ✅ PASS |
| QA-PROD-3 | ✅ PASS |
| QA-5 / QA-7 / QA-9 / QA-10 / QA-11 (n=100) | ✅ PASS |

---

## 8. Preuves — PROUVÉ / DÉCLARÉ / NON VÉRIFIÉ

### ✅ CE QUI EST PROUVÉ (exécution réelle)
- Un export **BLOCK est refusé (403)** au niveau de la route, **avant** toute génération de PDF ou envoi d'email (QA-PROD-3, TestClient).
- L'export définitif via `GET /cerfa.pdf?export=true` est aussi refusé (403) sur BLOCK.
- La **prévisualisation reste disponible** sur un dossier BLOCK (200).
- PASS / WARNING / absent **ne sont pas bloqués** par le gate.
- Le statut provient **exclusivement** de `cockpit_pro_json` (aucun recalcul — vérifié par la fonction pure).
- **Audit** : 5 lignes `gate_export_check` écrites dans `cerfa_audit_log` (date, dossier, acteur, statut, export autorisé/refusé).
- Aucune régression (QA-PROD-1/2/3 + QA-5/7/9/10/11).

### 🟦 CE QUI EST DÉCLARÉ
- En production, `envoyerCerfa()` affiche déjà `data.detail` sur erreur → le motif du refus 403 (message du gate) sera présenté au professionnel sans modification supplémentaire.
- Le mécanisme d'audit réutilisé (`cerfa_audit_log`) est celui déjà existant — aucun nouveau système créé.

### ⚠️ CE QUI EST NON VÉRIFIÉ
- Test en environnement de production réel (Railway) avec base PostgreSQL (les tests utilisent SQLite).
- Rendu visuel de l'alerte de refus côté navigateur authentifié (vérifié seulement au niveau API).
- Comportement si plusieurs colonnes UNIQUE additionnelles existent en prod (les tests insèrent des dossiers minimaux).

---

## 9. Critères de refus — contrôle

| Critère de refus | Présent ? |
|---|---|
| Un nouveau moteur créé | ❌ Non (`export_gate.py` = lecteur, pas un moteur) |
| Le gate est recalculé | ❌ Non — lecture de `cockpit_pro_json` uniquement |
| Le verrou est seulement visuel | ❌ Non — refus 403 côté backend prouvé |
| L'export continue malgré BLOCK | ❌ Non — 403, aucun PDF/email |
| Absence de QA-PROD-3 | ❌ Non — présent et PASS |
| Absence de preuve d'exécution réelle | ❌ Non — TestClient : 403 sur BLOCK, 200 sur prévisualisation |

---

## Conclusion

FACILIM **empêche désormais réellement** la production/transmission d'un CERFA lorsque le dossier est en BLOCK : le verrou lit le gate déjà calculé (`cockpit_pro_json`), refuse l'export (403) sans rien régénérer, journalise la décision, **et laisse la prévisualisation toujours disponible**. Les 5 niveaux du gate (calculé · persisté · visible · **appliqué** · **export sécurisé**) sont validés.

*Aucun moteur FACILIM 60→100 modifié. Aucun recalcul. Aucune logique métier, narratif, inférence ou CERFA touchée.*
