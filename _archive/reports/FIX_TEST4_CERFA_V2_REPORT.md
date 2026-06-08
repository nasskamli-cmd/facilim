# FIX_TEST4_CERFA_V2_REPORT.md — Rétablissement du moteur CERFA V2

**Généré le :** 2026-06-06
**Principe appliqué :** *une erreur d'audit ne doit jamais détruire un PDF V2 déjà généré.*
**Statut :** ✅ V2 rétabli — QA-FIX-TEST4-CERFA-V2 4/4 PASS, aucune régression (12/12).

---

## 0. Résultat

| Élément | Avant | Après |
|---|---|---|
| Génération V2 | tentée puis jetée | ✅ utilisée |
| Audit indépendant | dans le try V2 (bloquant) | ✅ non bloquant |
| PDF V2 conservé | ❌ abandonné sur erreur audit | ✅ conservé |
| Fallback V3 | déclenché par erreur d'audit | ✅ uniquement si la génération V2 échoue |
| TEST4 rejouable | ❌ V3 dégradé | ✅ V2 |

---

## 1. Cause corrigée (rappel)
`_generer_cerfa_pdf` exécutait `SELECT version FROM dossiers` (audit) **dans le `try` de génération V2**. La colonne `version` étant absente (ALTER de la migration 008 avalé par le découpeur), l'exception `no such column: version` était capturée par l'`except` de génération → le PDF V2 déjà produit était jeté → fallback V3 dégradé. **Deux causes** : migration manquante + mauvais périmètre try/except.

---

## 2. Liste exacte des fichiers modifiés
| Fichier | Modification |
|---|---|
| `app/main.py` `_generer_cerfa_pdf()` | **Correction 1** — restructuration du périmètre `try/except` : seule la **génération V2** déclenche le fallback ; hashes, page de couverture, **SELECT version** et journalisation d'audit deviennent **non bloquants** ; persistance hors du try-de-fallback. |
| `app/main.py` `_COLONNES_PHASE3` | **Correction 2 (Option B)** — ajout de `("version", "INTEGER DEFAULT 1")` au filet de démarrage qui garantit les colonnes (la plus petite correction, sans réécrire le moteur de migration). |
| `app/tests/qa/qa_fix_test4_cerfa_v2.py` | **Nouveau** — test QA-FIX-TEST4-CERFA-V2 (4 cas). |

**Aucun moteur métier, aucune règle MDPH, aucun narratif, aucun mapping CERFA, aucun fallback V3 modifié.**

---

## 3. Diff avant / après du périmètre try/except

**AVANT** (génération + audit + persistance dans le même `try` → l'audit fait échouer V2) :
```python
try:
    pdf_bytes = generer_cerfa_depuis_synthese(...)      # génération V2
    _synthese_hash = ...; _cerfa_pdf_hash = sha256(pdf_bytes)   # audit
    pdf_bytes = _ajouter_page_couverture(pdf_bytes, ...)        # mise en forme
    _dossier_version = db.execute("SELECT version FROM dossiers WHERE id=?")  # ← AUDIT : lève "no such column: version"
    _log_cerfa_audit(... version=_version_val ...)             # audit
    with open(output_path,"wb") as f: f.write(pdf_bytes)       # persistance
    return output_path, pdf_bytes
except Exception as e_v2:
    logger.warning("[CERFA V2] Moteur V2 indisponible (%s) — fallback V3", e_v2)   # ← l'erreur d'AUDIT tombe ici
# fallback V3 (dump dégradé)
```

**APRÈS** (seule la génération peut déclencher le fallback ; audit non bloquant) :
```python
pdf_bytes = None
try:
    pdf_bytes = generer_cerfa_depuis_synthese(...)      # SEULE la génération V2 → fallback
except Exception as e_v2:
    logger.warning("[CERFA V2] Génération V2 échouée (%s) — fallback V3", e_v2)
    pdf_bytes = None

if pdf_bytes is not None:
    try:    # hashes/pagination — non bloquant
        _synthese_hash = ...; _cerfa_pdf_hash = sha256(pdf_bytes); _nb_pages = ...
    except Exception as e_hash:
        logger.debug(...)
    try:    # page de couverture — non bloquant
        pdf_bytes = _ajouter_page_couverture(pdf_bytes, ...)
    except Exception as e_cov:
        logger.warning(...)
    try:    # AUDIT (SELECT version + journalisation) — NON BLOQUANT
        _dossier_version = db.execute("SELECT version FROM dossiers WHERE id=?")
        _version_val = ...
        _log_cerfa_audit(...)
    except Exception as e_audit:
        logger.warning("[CERFA V2] Audit non bloquant ignoré (%s) — PDF V2 conservé", e_audit)
    with open(output_path,"wb") as f: f.write(pdf_bytes)       # persistance
    logger.info("[CERFA V2] PDF généré via moteur V2 | ...")
    return output_path, pdf_bytes

# fallback V3 — UNIQUEMENT si la génération V2 a réellement échoué
logger.warning("[CERFA V2] Fallback V3 activé pour dossier=%s (génération V2 indisponible)", ...)
...
```

---

## 4. Preuve que le PDF V2 survit à une erreur d'audit
Exécution réelle de `_generer_cerfa_pdf` (logs `facilim.app` capturés) :
```
Cas 1 (version absente — SELECT version forcé à lever) : v2=True  fallback=False  pdf=979 703 o
Cas 2 (audit forcé à lever — _log_cerfa_audit)         : v2=True  fallback=False  pdf=979 703 o
Cas 3 (vraie erreur de génération V2)                  : v2=False fallback=True   pdf=1 076 495 o
Cas 4 (TEST4 rejoué, sans injection)                   : v2=True  fallback=False  pdf=979 703 o
```
→ **Cas 1 & 2** : une erreur d'audit (dont l'exacte `no such column: version`) **n'entraîne plus** de fallback ; le PDF V2 (979 703 o, avec couverture) est conservé et journalisé `[CERFA V2] PDF généré via moteur V2`.
→ **Cas 3** : une **vraie** panne de génération V2 déclenche toujours le fallback V3 (1 076 495 o) — comportement de sécurité préservé.
→ **Cas 4** : le scénario TEST4 produit désormais un **PDF V2**, plus le V3 dégradé.

---

## 5. Résultat QA-FIX-TEST4-CERFA-V2
```
✅ Cas 1 — version absente → V2 conservé, pas de fallback
✅ Cas 2 — audit en erreur → V2 conservé, pas de fallback
✅ Cas 3 — vraie erreur V2 → fallback V3 autorisé
✅ Cas 4 — TEST4 rejoué → V2 utilisé, aucun fallback
DÉCISION : ✅ PASS (4/4)
```
Filet vérifié au démarrage : `[STARTUP] Colonnes Phase 3+ ajoutées : ['version']` → `SELECT version` ne lève plus.

---

## 6. Résultat non-régression
| Test | Résultat |
|---|---|
| QA-PROD-1 / 2 / 3 / 4 / 5 | ✅ PASS |
| QA-VALIDATION-1-TEST4 | ✅ PASS |
| QA-FIX-TEST4-CERFA-V2 | ✅ PASS |
| QA-5 / QA-7 / QA-9 / QA-10 / QA-11 (n=100) | ✅ PASS |

**12/12 PASS — aucune régression.**

---

## 7. Preuves — PROUVÉ / DÉCLARÉ / NON VÉRIFIÉ

### ✅ CE QUI EST PROUVÉ
- Une erreur d'audit (`no such column: version` ou exception de journalisation) **ne déclenche plus** le fallback (Cas 1 & 2).
- Le PDF V2 est **conservé** quand l'audit échoue (979 703 o produits + log `PDF généré via moteur V2`).
- Le fallback V3 reste **disponible** uniquement sur **vraie** panne de génération V2 (Cas 3).
- Le scénario **TEST4 rejoué** utilise désormais V2 (Cas 4).
- La colonne `version` est **garantie** par le filet de démarrage (`[STARTUP] … ['version']`).
- Aucune régression (12/12 QA).

### 🟦 CE QUI EST DÉCLARÉ
- Le filet `_COLONNES_PHASE3` s'exécute au démarrage de l'app sur Railway comme en local → la colonne `version` sera créée au prochain déploiement/redémarrage de prod (même mécanisme que `cockpit_pro_json`).
- Les Cas 1/2/3 utilisent une injection de faute ciblée (proxy DB / `mock.patch`) pour simuler les pannes — c'est du test, pas une donnée mockée en production.

### ⚠️ CE QUI EST NON VÉRIFIÉ
- **Exécution réelle sur Railway** : la confirmation que le prochain dossier en prod génère un V2 (et non V3) nécessite un redéploiement + un nouveau dossier réel → à observer dans les logs (`[CERFA V2] PDF généré via moteur V2`, absence de fallback).
- L'**option A** (corriger l'ALTER de la migration 008) n'a pas été appliquée — le filet (option B) suffit ; A reste recommandée pour les déploiements neufs.
- Le **moteur de migration** (découpeur qui avale les ALTER précédés de commentaires) n'est pas corrigé (hors périmètre minimal) — cause systémique récurrente à traiter séparément.

---

## 8. Critères de refus — contrôle
| Critère de refus | Présent ? |
|---|---|
| Une erreur d'audit déclenche encore le fallback | ❌ Non (Cas 1 & 2 : pas de fallback) |
| La colonne `version` reste absente sans filet | ❌ Non (ajoutée au filet `_COLONNES_PHASE3`) |
| Le PDF V2 peut encore être abandonné après génération | ❌ Non (conservé, Cas 1/2/4) |
| QA-FIX-TEST4-CERFA-V2 absent | ❌ Non (présent, PASS 4/4) |
| Absence de preuve d'exécution réelle | ❌ Non (exécution réelle + logs capturés) |

---

## Conclusion
Le moteur CERFA V2 est **rétabli** : l'audit (hash, `SELECT version`, journalisation) et la persistance sont désormais **non bloquants**, et le fallback V3 n'intervient **que** si la génération V2 échoue réellement. La colonne `version` est garantie par le filet de démarrage. Le système ne produit plus un CERFA V3 dégradé à cause d'une erreur d'audit. Reste à **confirmer en production** (redéploiement) que le prochain dossier réel génère bien un V2.

*Aucun moteur FACILIM, aucune règle MDPH, aucun narratif, aucun fallback V3 modifié. Correction limitée au périmètre try/except + filet de colonne.*
