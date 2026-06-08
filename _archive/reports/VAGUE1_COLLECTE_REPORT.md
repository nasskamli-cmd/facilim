# VAGUE1_COLLECTE_REPORT.md — Collecte NIVEAU A (checklist unique + champs structurés)

**Généré le :** 2026-06-07
**Périmètre :** Vague 1 (NIVEAU A) uniquement. Pas de Vague 2/3. Pas de réécriture. **Pas de déploiement.**
**Statut :** ✅ QA-SCHEMA-1→5 PASS (5/5) · non-régression 14/14 PASS.

---

## 0. Résultat

| Élément | Statut |
|---|---|
| Checklist unique | ✅ (3 agents → `checklist_for`) |
| Identité fine structurée | ✅ (`prenom`, `nom_naissance`) |
| AVQ cœur structurées | ✅ (5 champs `avq_level`) |
| Droits explicites structurés | ✅ (objet `droits.*`) |
| Invalidité de base structurée | ✅ (`pension_invalidite`, `categorie_invalidite`, `at`, `mp`, `taux_ipp`) |
| Synthèse enrichie | ✅ (normalisation structuré ↔ legacy) |
| Cockpit enrichi | ✅ (consomme le dossier structuré) |
| CERFA alimenté | ✅ (`avq_*`→P6/P7, `droits.*`→P17, identité→P2) |
| QA vertes | ✅ (QA-SCHEMA 5/5 + non-rég 14/14) |

---

## 1. DIAGNOSTIC AVANT CODAGE

### CE QUI EXISTE DÉJÀ
3 CHECKLISTs d'agents (adulte/enfant/protégé) + une checklist parallèle inutilisée (`conversation_engine.CHECKLIST_MDPH`) ; `field_mapper`/`cerfa_filler` consommant `impact_quotidien` (mots-clés) et `droits_demandes` (texte) ; `_calculer_completude_live`.

### CE QUI EST RÉUTILISÉ
Le mécanisme CHECKLIST des agents ; le mapping CERFA existant (P6/P7 mots-clés, P17 parsing droits) ; le filet `_COLONNES_PHASE3` ; l'aval (CERFA/cockpit) **inchangé** grâce à la normalisation.

### CE QUI EST AJOUTÉ
`app/services/collecte_schema.py` (source unique) : `checklist_for(profil)`, `AVQ_*`, `DROITS_KEYS`, `normaliser_collecte()` ; les champs NIVEAU A (identité fine, organisme/allocataire, invalidité base, AVQ cœur) ; lecture `avq_*`/`prenom`/`nom_naissance` dans `field_mapper` et `v2_bridge`.

### CE QUI EST DÉPRÉCIÉ
`conversation_engine.CHECKLIST_MDPH` (commentaire de dépréciation ; n'était déjà pas utilisé par le flux). Aucune suppression brutale (compatibilité conservée).

---

## 2. Fichiers modifiés / créés
| Fichier | Modification |
|---|---|
| `app/services/collecte_schema.py` | **NOUVEAU** — source de vérité unique : `checklist_for`, `normaliser_collecte`, `AVQ_*`, `DROITS_KEYS` |
| `app/services/conversation/adult_agent.py` | `CHECKLIST = checklist_for("adulte")` (+ import) |
| `app/services/conversation/child_agent.py` | `CHECKLIST = checklist_for("enfant")` (+ import) |
| `app/services/conversation/protected_agent.py` | `CHECKLIST = checklist_for("protege")` (+ import) |
| `app/engines/conversation_engine.py` | commentaire de dépréciation sur `CHECKLIST_MDPH` |
| `app/engines/pdf/field_mapper.py` | `normaliser_collecte` en entrée + identité `prenom`/`nom_naissance` + AVQ `avq_*`→P6/P7 (adaptation de lecture) |
| `app/engines/pdf/v2_bridge.py` | `normaliser_collecte` + identité structurée (adaptation de lecture, V2) |
| `app/engines/facilim_prod.py` | `normaliser_collecte` en entrée de `run()` (cockpit/moteurs) |
| `app/tests/qa/qa_schema_vague1.py` | **NOUVEAU** — QA-SCHEMA-1→5 |

**Aucun moteur FACILIM 60→100 modifié ; aucune logique CERFA/gate/audit/historique/scoring touchée** (uniquement adaptation de lecture + source de collecte).

---

## 3. Diff avant / après (clés)

**Agents (×3)** :
```diff
- CHECKLIST = [ {…20+ champs en dur…} ]          # 3 listes divergentes
+ CHECKLIST = checklist_for("adulte"/"enfant"/"protege")   # source unique
```

**field_mapper — identité** :
```diff
- fields["Champ de texte P2 1"] = _nom(nom_complet)
- fields["Champ de texte P2 3"] = _prenom(nom_complet)
+ fields["Champ de texte P2 1"] = donnees.get("nom_naissance") or _nom(nom_complet)
+ fields["Champ de texte P2 3"] = donnees.get("prenom") or _prenom(nom_complet)
```

**field_mapper — AVQ (exemple)** :
```diff
- fields["Case à cocher P6 B2"] = _check(_contains_any(all_impact, ["hygiène","toilette","lavage"]))
+ fields["Case à cocher P6 B2"] = _check(_avq("avq_toilette") or _contains_any(all_impact, ["hygiène","toilette","lavage"]))
```

**Normalisation (compat)** :
```diff
+ # droits.* (booléens) → droits_demandes (texte) lu par moteurs/CERFA existants
+ donnees = normaliser_collecte(donnees)
```

---

## 4. Résultats QA-SCHEMA-1→5
```
✅ QA-SCHEMA-1 — checklist unique + NIVEAU A + parallèle déprécié
✅ QA-SCHEMA-2 — nouveaux champs présents + is_complete inchangé
✅ QA-SCHEMA-3 — droits.* → droits_demandes + structurés préservés (idempotent)
✅ QA-SCHEMA-4 — dossier structuré → cockpit généré
✅ QA-SCHEMA-5 — avq_*→P6/P7, droits.*→P17, prenom/nom→P2
DÉCISION : ✅ PASS (5/5)
```

## 5. Résultats non-régression (14/14 PASS)
`qa_schema_vague1` · `qa_fix_test4_collecte` · `qa_fix_test4_cerfa_v2` · `qa_validation_1_test4` · `qa_prod_1→5` · `qa5/7/9/10/11` → **tous PASS**.

---

## 6. Exemple réel — `synthese_json` enrichi (après normalisation)
```json
{
  "nom_naissance": "DURAND", "prenom": "Marie",
  "organisme_payeur": "CAF", "numero_allocataire": "1234567",
  "pension_invalidite": true, "categorie_invalidite": "2",
  "avq_toilette": "AIDE_PARTIELLE", "avq_deplacements": "AIDE_TOTALE",
  "droits": {"aah": true, "pch": true, "rqth": true, "cmi_invalidite": true,
             "cmi_priorite": false, "cmi_stationnement": true},
  "droits_demandes": "AAH, PCH, RQTH, CMI invalidité, CMI stationnement"
}
```

## 7. Exemple réel — CERFA régénéré (`build_field_map`) utilisant `avq_*` et `droits.*`
```
Champ de texte P2 1  = 'DURAND'        (nom_naissance)
Champ de texte P2 3  = 'Marie'         (prenom)
Champ de texte P2 10 = '1234567'       (numero_allocataire)
Case à cocher P6 B1  = /Yes            (avq_gestion_quotidienne=DIFFICULTE)
Case à cocher P6 B2  = /Yes            (avq_toilette=AIDE_PARTIELLE)
Case à cocher P6 B3  = /Yes            (avq_habillage=DIFFICULTE)
Case à cocher P6 B4  = (vide)          (avq_repas=AUTONOME → pas de besoin) ✓ logique de niveau
Case à cocher P7 2   = /Yes            (avq_deplacements=AIDE_TOTALE)
Case à cocher P17 2  = /Yes            (droits.pch)
Case à cocher P17 3  = /Yes            (droits.cmi_invalidite)
Case à cocher P17 5  = /Yes            (droits.aah)
Case à cocher P17 6  = /Yes            (droits.rqth)
```
> `avq_repas=AUTONOME` ne coche PAS la case (seuls DIFFICULTE/AIDE_PARTIELLE/AIDE_TOTALE déclenchent un besoin) — la logique de niveau fonctionne.

---

## 8. PREUVES — PROUVÉ / DÉCLARÉ / NON VÉRIFIÉ

### ✅ CE QUI EST PROUVÉ
- **Checklist unique** : les 3 agents = `checklist_for(profil)` (QA-SCHEMA-1) ; modèle parallèle déprécié.
- **Champs NIVEAU A structurés** présents dans la checklist ; `is_complete` **inchangé** (requis=False → zéro régression).
- **Normalisation** `droits.*`→`droits_demandes`, structurés préservés, idempotente (QA-SCHEMA-3).
- **Bout-en-bout** : un dossier structuré → cockpit généré (QA-SCHEMA-4) → CERFA rempli (`avq_*`→P6/P7, `droits.*`→P17, identité→P2 ; QA-SCHEMA-5 + exemple §7).
- **Aucune régression** (14/14).

### 🟦 CE QUI EST DÉCLARÉ
- Les champs NIVEAU A sont volontairement `requis=False` (sécurité : is_complete stable). Leur **promotion en requis** (pour forcer la collecte conversationnelle) est un réglage Vague 1.x à valider en réel.
- La compatibilité repose sur `normaliser_collecte` appelé aux 3 entrées (field_mapper, v2_bridge, facilim_prod) → l'aval existant reste inchangé.

### ⚠️ CE QUI EST NON VÉRIFIÉ
- **Collecte conversationnelle réelle** : que le LLM pose effectivement les nouvelles questions (AVQ/droits/invalidité) et les structure — non testable hors conversation live. Le présent travail prouve la **structure + le branchement + le mapping**, pas le déroulé LLM.
- **CERFA V2 (cerfa_filler) côté AVQ** : V2 bénéficie de `droits.*` (via `droits_demandes` normalisé) et de l'identité structurée ; le mapping **AVQ→P6/P7 direct** est prouvé sur le chemin **field_mapper (V3)** — côté V2 il dépend des règles internes (suivi Vague 1.x).
- **Production** : non déployé (la prod conserve l'ancien comportement jusqu'à `railway up`).

---

## 9. Critères de refus — contrôle
| Critère de refus | Présent ? |
|---|---|
| Plusieurs checklists actives subsistent | ❌ Non (source unique `checklist_for` ; parallèle déprécié) |
| Champs collectés mais non structurés | ❌ Non (`avq_*`/`droits.*` structurés) |
| Champs structurés mais invisibles | ❌ Non (CERFA P6/P7/P17/P2 alimentés — §7) |
| QA-SCHEMA échouent | ❌ Non (5/5 PASS) |
| Régression | ❌ Non (14/14 PASS) |

---

## Conclusion
La Vague 1 (NIVEAU A) est implémentée : **une seule checklist active** (source de vérité `collecte_schema`), champs **identité fine / AVQ cœur / droits explicites / invalidité de base** structurés, branchés bout-en-bout (collecte → synthèse → cockpit → CERFA) via une **normalisation de compatibilité** qui n'altère ni les moteurs ni la logique CERFA. Validé en local (QA-SCHEMA 5/5 + non-régression 14/14), **non déployé**.

Reste (hors périmètre de cette livraison) : valider en **collecte WhatsApp réelle** que les nouvelles questions sont posées (éventuellement promouvoir certains NIVEAU A en `requis`), et étendre le mapping AVQ→P6/P7 côté moteur V2. Ce sont des suites Vague 1.x / Vague 2.

*Vague 1 uniquement. Aucun moteur FACILIM 60→100, gate, audit, historique, scoring modifié. Aucun déploiement.*
