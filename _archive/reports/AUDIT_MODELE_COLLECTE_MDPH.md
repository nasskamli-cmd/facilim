# AUDIT_MODELE_COLLECTE_MDPH.md — Le modèle de collecte couvre-t-il le CERFA 15692 ?

**Généré le :** 2026-06-07
**Nature :** Audit racine du modèle de collecte — **lecture seule, aucune correction, aucun code modifié**.
**Sources lues :** `app/services/conversation/{adult,child,protected}_agent.py` (CHECKLISTs actives), `base.py` (`is_complete`/`missing_fields`), `app/engines/conversation_engine.py` (`CHECKLIST_MDPH*`), `app/main.py` (`/initiate`, prompt d'extraction upload, `_calculer_completude_live`), `app/engines/pdf/field_mapper.py` + `services/cerfa_filler.py` (champs consommés), `app/database/schemas.py`.

> **Constat transverse majeur** : il existe **deux modèles de collecte divergents** :
> - `conversation_engine.CHECKLIST_MDPH` (riche : `numero_allocataire`, `projet_orientation`, `statut_occupation`, Section F aidant…) — **NON utilisé** par le flux réel ;
> - les **agents actifs** (`adult/child/protected_agent.CHECKLIST`) — **plus étroits**, ce sont eux qui pilotent réellement la collecte (`get_agent(service_type)`).
> Le flux réel utilise donc le modèle **le plus pauvre**.

---

## 1. CE QUI EXISTE (réellement collecté par les agents actifs)

**Tronc commun (adulte/enfant/protégé)** : `nom_prenom`, `date_naissance`, `genre`, `adresse_complete`, `num_secu`, `telephone`, `departement`, `diagnostics`, `traitements`, `medecin_traitant`, `impact_quotidien`, `historique_mdph`.
**Adulte** : + `situation_familiale`, `enfants_a_charge`, `qualification_section_c` (+`formation_actuelle` si oui), `qualification_section_d` (+`statut_emploi` si oui), `date_debut_limitations` (opt), `expression_directe` (opt), `droits_demandes` (opt).
**Enfant** : + `representant_legal_nom`/`representant_legal_lien`, `situation_scolaire`, `etablissement_scolaire`.
**Protégé** : + `type_protection`, `jugement_tribunal`, `representant_legal_nom`, `statut_emploi`.
**Création `/initiate`** : `email`, `type_dossier` (INITIAL/RENOUVELLEMENT/SITUATION_CHANGEE/REEVALUATION/AIDANT), `numero_dossier_mdph`, `aidant_familial` (booléen), `telephone`, `num_secu`(si saisi).
**Extraction bilan (upload, si document)** : `adresse_complete`, `num_secu`, `diagnostics`, `traitements`, `medecin_traitant`, `impact_quotidien`, `statut_emploi`, `historique_mdph`, `accident_travail`, `restrictions_emploi`, `representant_legal_*`.

---

## 2. CE QUI MANQUE (absent du modèle de collecte actif)

### Identité / administratif (Partie A)
❌ nom de naissance · ❌ commune/lieu de naissance · ❌ nationalité · ❌ mode de contact souhaité · ❌ organisme d'assurance maladie · ❌ CAF/MSA (`organisme_payeur`) · ❌ numéro allocataire *(opt dans conversation_engine, **absent** des agents actifs)* · ❌ personne à contacter.

### Protection juridique
⚠️ `type_protection` + `jugement_tribunal` (protégé) ; ❌ distinction curatelle simple/renforcée/habilitation familiale · ❌ coordonnées détaillées du représentant.

### Vie quotidienne (Partie B) — **gap massif**
❌ ressources / RSA / AAH perçue · ❌ pension d'invalidité + catégorie 1/2/3 · ❌ rente AT/MP · ❌ taux IPP · ❌ maladie professionnelle · ❌ **aides humaines structurées** (toilette, habillage, repas, ménage, courses, santé, budget, administratif) · ❌ déplacements domicile/extérieur · ❌ transport · ❌ sécurité · ❌ communication · ❌ relations sociales · ❌ loisirs · ❌ aide technique · ❌ aménagement logement/véhicule · ❌ frais liés au handicap · ❌ besoins PCH. *(Tout cela n'existe que noyé dans le texte libre `impact_quotidien`.)*

### Enfant / scolarité (Partie C)
⚠️ `situation_scolaire`, `etablissement_scolaire` ; ❌ AESH · ❌ PPS · ❌ matériel adapté · ❌ transport scolaire · ❌ GEVASCO · ❌ orientation scolaire · ❌ ESMS enfant · ❌ AEEH/complément · ❌ PCH enfant.

### Emploi / orientation (Partie D)
⚠️ `statut_emploi`, `qualification_section_d` ; ❌ employeur · ❌ type contrat · ❌ temps plein/partiel · ❌ médecin du travail · ❌ Cap emploi/France Travail/mission locale · ❌ ESAT/CRP/CPO/UEROS structurés · ❌ formation/reconversion structurées · ❌ niveau scolaire/diplômes · ❌ limitations professionnelles · ❌ besoin d'aménagement · ❌ maintien dans l'emploi.

### Droits (Partie E)
⚠️ **un seul champ texte `droits_demandes`** (liste libre), parsé par mots-clés dans le mapper. ❌ pas de collecte **explicite par droit** (AAH, complément, PCH, CMI invalidité/priorité/stationnement, RQTH, orientation pro, ESAT, CRP/CPO/UEROS, ESMS adulte, AEEH/complément, AVPF, ACTP/ACFP).

### Aidant (Partie F) — **quasi absent**
❌ Section F absente des **agents actifs** (présente seulement dans `conversation_engine` inutilisé). Seul `aidant_familial` (booléen) est posé à la création. ❌ lien, cohabitation, emploi aidant, réduction activité, nature de l'aide, surveillance, aides (hygiène/repas/déplacements/administrative/financière), coordination, épuisement, besoin de répit, soutien psychologique, AVPF aidant.

---

## 3. COLLECTÉ MAIS NON STRUCTURÉ
- **`impact_quotidien`** : texte libre contenant TOUTES les limitations AVQ → jamais éclaté en champs PCH exploitables.
- **Projet de vie / professionnel** : `expression_directe`, `projet_professionnel`, `projet_orientation` → texte libre, non transformés en champs/cases.
- **`droits_demandes`** : un seul champ texte (liste) → parsé par mots-clés au mapping, pas une collecte structurée par droit.
- **`notes_pro`** / bilan collé : texte libre (le bilan PCR de 29 000 car. y atterrit, tronqué).
- **`diagnostics`** : liste textuelle (semi-structurée).

---

## 4. STRUCTURÉ MAIS NON UTILISÉ (défini mais jamais alimenté / consommé)
- `numero_allocataire`, `organisme_payeur` : présents dans `schemas.py` + `conversation_engine` + **lus** par `field_mapper` (P2 10 / Case 4) — mais **jamais collectés** par les agents actifs → champs structurés morts.
- `projet_orientation`, `statut_occupation`, `inscrit_pole_emploi` : définis dans `conversation_engine.CHECKLIST_MDPH` mais **absents des agents actifs** → jamais demandés.
- **`CHECKLIST_MDPH` (conversation_engine) entier** : modèle riche **non utilisé** par le flux (les agents ont leur propre checklist plus étroite).

---

## 5. UTILISÉ PAR LE CERFA MAIS PAS COLLECTÉ
`services/cerfa_filler.py` (V2, actif en prod) **consomme** des champs jamais collectés :
- `nationalite` (L809), `commune_naissance` (L810), `organisme_payeur` (L814), `organisme_assurance_maladie` (L816), `ressources_actuelles` (L860), `organisme_formation` (L979).
- + (par le mapping cases) pension d'invalidité, catégorie, rente AT/MP, taux IPP, aides AVQ (P6/P7), aménagements — tous attendus côté CERFA, **aucun champ de collecte** ne les alimente.
→ Ces champs restent vides dans le CERFA car **rien ne les remplit**.

---

## 6. MATRICE CERFA → FACILIM (par section ; champs représentatifs)

| Section CERFA | Champ CERFA | Collecté | Structuré | Utilisé cockpit | Utilisé CERFA | Statut |
|---|---|---|---|---|---|---|
| A2 Identité | nom | ✅ | ✅ | ✅ | ✅ | OK |
| A2 Identité | prénom | ⚠️ | ⚠️ | ❌ | ⚠️ | Perdu (cf. audit Karim) |
| A2 Identité | sexe/genre | ⚠️ (requis, pas de saisie création) | ✅ | ❌ | ✅ | Souvent vide |
| A2 Identité | nom de naissance | ❌ | ❌ | ❌ | ✅ attend | **Manquant** |
| A2 Identité | commune/nationalité | ❌ | ❌ | ❌ | ✅ attend | **Manquant** |
| A2 Contact | mode de contact souhaité | ❌ | ❌ | ❌ | ✅ attend | **Manquant** |
| A Admin | NIR | ⚠️ (requis, souvent non fourni) | ✅ | ❌ | ✅ | Souvent vide |
| A Admin | organisme assurance maladie | ❌ | ❌ | ❌ | ✅ attend | **Manquant** |
| A Admin | CAF/MSA + n° allocataire | ❌ | ✅ (schéma) | ❌ | ✅ lit | **Non collecté** |
| A1 Type demande | 1ʳᵉ/réévaluation/renouvellement | ✅ (`type_dossier`) | ✅ | — | ✅ (P1) | OK |
| A4 Protection | tutelle/curatelle | ⚠️ (`type_protection` générique) | ⚠️ | — | ⚠️ | Partiel (pas de distinction fine) |
| B Vie quotidienne | difficultés (texte) | ✅ `impact_quotidien` | ❌ (libre) | ✅ | ✅ (narratif P8) | Non structuré |
| B Ressources | RSA/AAH/pension/cat. invalidité | ❌ | ❌ | ❌ | ✅ attend | **Manquant** |
| B AT/MP | rente / taux IPP | ⚠️ `accident_travail` (texte) | ❌ | ❌ | ✅ attend | **Non structuré** |
| B AVQ/PCH | toilette/habillage/repas/déplacements… | ❌ (dans impact libre) | ❌ | ⚠️ | ❌ cases P6/P7 ~0,8 % | **Non structuré** |
| C Scolarité | AESH/PPS/GEVASCO/AEEH | ❌ | ❌ | ❌ | ✅ attend | **Manquant** |
| D Emploi | médecin travail / employeur / limitations pro | ❌ | ❌ | ⚠️ | ✅ attend | **Manquant** |
| E Droits | AAH/PCH/CMI/RQTH/ESAT… | ⚠️ (`droits_demandes` texte unique) | ⚠️ (parsé mot-clé) | ✅ | ✅ (P17/P18) | Semi-structuré, fragile |
| E Projet de vie | projet/orientation | ⚠️ (texte libre) | ❌ | ⚠️ | ⚠️ (P16) | Non structuré |
| F Aidant | besoins aidant | ❌ (agents actifs) | ❌ | ❌ | ⚠️ (P19-20) | **Quasi absent** |

---

## 7. MATRICE PROFILS

| Profil | Couvert actuellement | Gaps critiques |
|---|---|---|
| Adulte réévaluation | ⚠️ Partiel | AVQ/PCH non structurés, ressources/invalidité absentes, CAF/MSA/allocataire, projet libre |
| Première demande adulte | ⚠️ Partiel | idem + identité incomplète (nom naissance, nationalité, mode contact) |
| Enfant scolarisé | ⚠️ Partiel | AESH, PPS, GEVASCO, AEEH/complément, PCH enfant non structurés |
| Aidant familial | ❌ **Très faible** | Section F absente des agents actifs (seul booléen création) |
| Curatelle / tutelle | ⚠️ Partiel | distinction curatelle simple/renforcée/habilitation, coordonnées représentant |
| Invalidité catégorie 2 | ❌ **Non couvert** | aucun champ pension/catégorie 1-2-3 |
| Accident du travail | ⚠️ Partiel | `accident_travail` en texte ; rente AT/MP, taux IPP, maladie pro non structurés |
| Demande PCH | ❌ **Critique** | limitations AVQ non structurées → PCH non objectivable |
| Demande RQTH | ⚠️ Partiel | limitations professionnelles, médecin du travail, maintien emploi non structurés |
| Orientation ESMS | ❌ **Non couvert** | pas de champ d'orientation ESMS structuré |

---

## 8. RISQUE PILOTE
**Le modèle de collecte actuel ne couvre PAS suffisamment le CERFA 15692 pour un pilote ESSMS visant des dossiers complets.** Il produit un socle **identité + médical + narratif** correct, mais les sections **décisionnelles** (PCH/AVQ, ressources & invalidité, droits explicites, aidant, orientation pro/ESMS, scolarité fine) sont **non structurées ou absentes**.
- **Pilote possible** en mode « **assistance / brouillon à compléter manuellement** » par le professionnel (FACILIM pré-remplit identité + narratif + droits détectés au mot-clé).
- **Pilote NON recommandé** en mode « dossier MDPH complet et auto-suffisant » : les profils PCH, invalidité, ESMS, aidant et la page E resteront lacunaires.

---

## 9. PROCHAIN SPRINT RECOMMANDÉ (racine, unique)
> **Sprint « Schéma de collecte aligné CERFA 15692 » : une checklist unique, structurée par sections CERFA, source de vérité partagée.**

Principe (description, **non codé**) :
1. **Unifier** les deux modèles divergents en **une seule checklist** pilotant les agents (supprimer la divergence `conversation_engine` vs agents).
2. **Structurer les champs aujourd'hui en texte libre** : éclater `impact_quotidien` en items **AVQ/PCH** (toilette, habillage, repas, déplacements, ménage, courses, communication…), et `droits_demandes` en **droits explicites** (cases par droit), + ressources/invalidité/AT-MP, + Section F aidant, + identité complète (nom naissance, nationalité, mode contact, organisme, CAF/MSA).
3. **Brancher cette checklist de bout en bout** : collecte → `synthese_json` → cockpit → CERFA (un champ collecté = un champ exploitable), pour ne plus avoir de « collecté non structuré » ni « attendu CERFA non collecté ».

C'est **un seul chantier structurant** (le schéma de données de collecte), pas une série de correctifs champ par champ — il supprime la racine commune à tous les gaps observés.

---

## CE QUI EST PROUVÉ
- Les CHECKLISTs actives (agents) sont plus étroites que `conversation_engine.CHECKLIST_MDPH` ; le flux utilise les agents.
- `numero_allocataire`/`organisme_payeur` lus par le mapper mais absents des agents → jamais collectés.
- `cerfa_filler` consomme `nationalite`/`commune_naissance`/`organisme_payeur`/`organisme_assurance_maladie`/`ressources_actuelles`/`organisme_formation` → jamais collectés.
- AVQ/PCH, ressources/invalidité, Section F aidant : aucun champ structuré dans les agents actifs.
- `droits_demandes`/projet : champ texte unique (semi/non structuré).

## CE QUI EST DÉCLARÉ
- L'ampleur exacte des champs CERFA non remplis par profil (la matrice §6/§7 couvre les sections et champs représentatifs, pas les 612 champs un par un).
- Le mode « brouillon assisté » comme cadre de pilote réaliste.

## CE QUI EST NON VÉRIFIÉ
- Exhaustivité des 612 champs AcroForm (audit par section, pas champ-par-champ).
- Comportement réel de collecte après le fix collecte (rejeu non encore réalisé) — certains « non collectés » peuvent être dus au court-circuit récemment corrigé, à re-mesurer.
- Contenu réel `synthese_json`/`cockpit_pro_json` prod (base inaccessible).

---

## Réponse au critère de réussite
1. **Couvre-t-il le CERFA 15692 ?** Non — couverture partielle (socle identité+médical+narratif ; sections décisionnelles sous-structurées).
2. **Champs manquants** : §2 (identité complète, ressources/invalidité, AVQ/PCH, scolarité fine, emploi détaillé, droits explicites, aidant).
3. **Profils sous-couverts** : aidant, invalidité cat. 2, PCH, orientation ESMS (❌) ; les autres ⚠️ partiels (§7).
4. **Données à structurer** : AVQ/PCH, droits par droit, ressources/invalidité/AT-MP, projet de vie, identité complète, Section F.
5. **Sprint unique racine** : §9 — un schéma de collecte unifié aligné CERFA, branché bout-en-bout.

*Audit uniquement. Aucun fichier de code modifié, aucun moteur créé, aucun prompt/CERFA touché, aucun déploiement.*
