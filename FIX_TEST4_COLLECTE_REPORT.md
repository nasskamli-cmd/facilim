# FIX_TEST4_COLLECTE_REPORT.md — Fin de collecte gatée (un bilan pré-rempli ne termine plus la collecte)

**Généré le :** 2026-06-07
**Principe :** *Un dossier enrichi uniquement par du contenu pré-collecte (bilan uploadé, notes de création) ne doit pas terminer la collecte.* La collecte doit progresser réellement avant de pouvoir se clôturer.
**Statut :** ✅ QA-FIX-TEST4-COLLECTE 6/6 PASS · non-régression 13/13 PASS.

---

## 0. Résultat

| Élément | Avant | Après |
|---|---|---|
| Collecte continue après « oui » | ❌ (validation au tour 1) | ✅ |
| Validation non déclenchée au tour 1 | ❌ | ✅ |
| Section E atteignable | ❌ (court-circuitée) | ✅ (collecte non close) |
| `droits_demandes` collectable | ❌ jamais atteint | ✅ (champ Section E, collecte ouverte) |
| TEST4 rejouable correctement | ❌ | ✅ (décision = pas de validation) |

---

## 1. DIAGNOSTIC

### État actuel (condition AVANT)
`app/engines/orchestration_engine.py`, `traiter_message_async` :
```python
_declencher_narratif = (
    (agent.is_complete(donnees) or _dossier_narratif_exploitable(donnees))
    and service_type != "validation_en_attente"
)
```
`_dossier_narratif_exploitable` est vrai dès qu'un contenu fonctionnel (`diagnostics`, `documents_texte`, …) + une identité sont présents — ce que **l'upload du bilan suffit à fournir avant toute collecte**. ⇒ au 1ᵉʳ « oui », `_declencher_narratif=True` → `_demander_validation_usager` → fin.

### État corrigé (condition APRÈS)
```python
_declencher_narratif = (
    (
        agent.is_complete(donnees)
        or (_dossier_narratif_exploitable(donnees) and _collecte_presque_complete(agent, donnees))
    )
    and service_type != "validation_en_attente"
)
```
avec le helper :
```python
def _collecte_presque_complete(agent, donnees, seuil_manquants: int = 3) -> bool:
    # True si ≤ 3 champs REQUIS de la checklist restent à collecter.
    return len(agent.missing_fields(donnees)) <= seuil_manquants
```

### Pourquoi ce correctif élimine « oui → fin » sans casser « collecte complète → narratif → validation »
- Le raccourci `_dossier_narratif_exploitable` (P0.2-H3) retrouve **son intention d'origine** : « quelques champs administratifs secondaires manquent encore » — il n'autorise la fin que si la collecte est **presque complète** (≤ 3 requis manquants).
- Un dossier pré-rempli par un bilan a **beaucoup** de champs requis manquants (genre, num_secu, situation familiale, traitements, médecin traitant, qualif. C/D…) → `presque_complete=False` → le raccourci ne s'applique pas → **la collecte continue** (la question calculée est envoyée).
- **`is_complete` reste inchangé** comme déclencheur de fin : quand la collecte est réellement terminée (0 requis manquant), la validation/narratif se déclenche normalement.
- ⇒ « oui → fin » disparaît ; « collecte complète → fin » est préservé.

---

## 2. Fichiers modifiés
| Fichier | Modification | Hors moteurs/CERFA ? |
|---|---|---|
| `app/engines/orchestration_engine.py` | (1) nouveau helper `_collecte_presque_complete(agent, donnees)` ; (2) condition `_declencher_narratif` gate le raccourci `exploitable` par ce helper. **Uniquement la condition de clôture de collecte.** | ✅ aucun moteur 60→100, CERFA, field_mapper, cockpit, gate, audit, droits, scoring touché |
| `app/tests/qa/qa_fix_test4_collecte.py` | **Nouveau** — QA-FIX-TEST4-COLLECTE (6 cas) | Test |

---

## 3. Diff avant / après de la condition
```diff
- _declencher_narratif = (
-     (agent.is_complete(donnees) or _dossier_narratif_exploitable(donnees))
-     and service_type != "validation_en_attente"
- )
+ _declencher_narratif = (
+     (
+         agent.is_complete(donnees)
+         or (_dossier_narratif_exploitable(donnees) and _collecte_presque_complete(agent, donnees))
+     )
+     and service_type != "validation_en_attente"
+ )
```
\+ ajout du helper `_collecte_presque_complete` (≤ 3 champs requis manquants).

---

## 4. Résultat QA-FIX-TEST4-COLLECTE
```
missing_fields(bilan)   = 10  → presque_complete=False
missing_fields(partiel) = 6   → presque_complete=False
missing_fields(complet) = 0   → is_complete=True
exploitable(bilan)      = True
décision(bilan)=False  décision(partiel)=False  décision(complet)=True

✅ Cas 1 — bilan + 1ᵉʳ oui → PAS de validation
✅ Cas 2 — collecte partielle → PAS de validation (progression)
✅ Cas 3 — droits_demandes collectable + collecte ouverte
✅ Cas 4 — Section E renseignée → droits_demandes != []
✅ Cas 5 — collecte complète → validation (is_complete)
✅ Cas 6 — TEST4 rejoué → PAS de validation au tour 1
DÉCISION : ✅ PASS (6/6)
```

## 5. Preuve que « oui » n'entraîne plus « validation immédiate »
Le dossier TEST4 (bilan riche, réévaluation, 1ᵉʳ message « oui ») a **10 champs requis manquants** → `_collecte_presque_complete=False` → bien que `_dossier_narratif_exploitable=True`, **la décision de clôture est `False`** → la branche `_demander_validation_usager` (L842) n'est **pas** atteinte → la question de collecte (L864) est envoyée. **« oui » → question suivante, plus → validation.**

## 6. Non-régression
| Test | Résultat |
|---|---|
| QA-FIX-TEST4-COLLECTE | ✅ PASS |
| QA-FIX-TEST4-CERFA-V2 | ✅ PASS |
| QA-VALIDATION-1-TEST4 | ✅ PASS |
| QA-PROD-1 / 2 / 3 / 4 / 5 | ✅ PASS |
| QA-5 / 7 / 9 / 10 / 11 (n=100) | ✅ PASS |

**13/13 PASS — aucune régression.**

---

## 7. Preuves — PROUVÉ / DÉCLARÉ / NON VÉRIFIÉ

### ✅ CE QUI EST PROUVÉ (déterministe, niveau décision de clôture)
- Un dossier pré-rempli par un bilan (10 requis manquants) **ne déclenche plus** la fin de collecte (décision=False) — donc pas de validation au tour 1.
- Une collecte partielle (>3 requis manquants) **ne déclenche pas** la fin (progression préservée).
- Une collecte complète (0 requis manquant) **déclenche** la fin via `is_complete` (validation/narratif intacts).
- `droits_demandes` est un champ collectable (Section E) que la collecte, désormais non court-circuitée, peut atteindre.
- Aucun moteur métier modifié ; non-régression 13/13.

### 🟦 CE QUI EST DÉCLARÉ
- Seuil `≤ 3 champs requis manquants` = heuristique reflétant « quelques champs secondaires manquent » (ajustable). Choisi pour bloquer le cas pré-rempli (≥10 manquants) tout en autorisant une fin quasi-complète.
- La condition testée est la **réplique exacte** de la décision inline `_declencher_narratif` (mêmes helpers, même agent).

### ⚠️ CE QUI EST NON VÉRIFIÉ
- **Bout-en-bout WhatsApp réel** : que la collecte, en conversation live (LLM), parcoure effectivement les onglets jusqu'à la Section E et **pose la question des droits**, et que l'usager y réponde → `droits_demandes` rempli. Le présent test prouve la **condition de clôture** (la collecte n'est plus close au tour 1), pas le déroulé conversationnel complet.
- Comportement en **production** (nécessite redéploiement + un nouveau dossier réel pour observer la collecte se poursuivre au-delà du 1ᵉʳ « oui »).
- Le **500 `/appui-evaluation`** (`sqlite3.Row.get`) reste **non corrigé** (hors périmètre, indépendant).

---

## 8. Critères de refus — contrôle
| Critère de refus | Présent ? |
|---|---|
| Validation au 1ᵉʳ tour | ❌ Non (décision=False sur le bilan) |
| Section E toujours inatteignable | ❌ Non (collecte non close → atteignable) |
| `droits_demandes` reste vide | ❌ Non (collectable + collecte ouverte ; rempli si Section E renseignée) |
| Moteur métier modifié | ❌ Non (uniquement la condition de clôture) |
| Absence de QA-FIX-TEST4-COLLECTE | ❌ Non (présent, PASS 6/6) |

---

## Conclusion
FACILIM ne considère plus qu'un bilan pré-rempli suffit à terminer la collecte : le raccourci `exploitable` n'autorise la fin que si la collecte est presque complète (≤ 3 champs requis manquants), et `is_complete` reste le déclencheur de fin normal. La collecte se poursuit donc jusqu'à la Section E (droits). Validé en local (6/6 + 13/13). **À confirmer en production** par un rejeu réel (redéploiement requis).

*Correction limitée à la condition de clôture de collecte. Aucun moteur FACILIM, CERFA, droit, narratif, cockpit, gate ou audit modifié.*
