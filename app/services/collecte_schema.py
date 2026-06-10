"""
app/services/collecte_schema.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FACILIM — Schéma de collecte UNIQUE (Vague 1, NIVEAU A)

Source de vérité unique de la collecte, alignée sur COLLECTE_CERFA_TARGET_SCHEMA.md.
Remplace la coexistence de checklists divergentes : les 3 agents
(`adult/child/protected`) construisent leur CHECKLIST via `checklist_for(profil)`.

Vague 1 — NIVEAU A ajouté (champs structurés) :
  - Identité fine : prenom, nom_naissance
  - Administratif : organisme_payeur (CAF/MSA/autre), numero_allocataire
  - Invalidité de base : pension_invalidite, categorie_invalidite, accident_travail,
                         maladie_professionnelle, taux_ipp
  - AVQ cœur : avq_toilette, avq_habillage, avq_repas, avq_deplacements,
               avq_gestion_quotidienne  (niveaux : AUTONOME/DIFFICULTE/AIDE_PARTIELLE/AIDE_TOTALE)
  - Droits explicites : objet `droits.*` (booléens) — voir DROITS_KEYS

RÈGLE DE COMPATIBILITÉ (transition) :
  - Les anciens champs restent LUS (`impact_quotidien`, `droits_demandes`).
  - `normaliser_collecte()` DÉRIVE les champs legacy depuis les champs structurés
    (droits.* → droits_demandes) pour que les moteurs / le CERFA V2 existants
    fonctionnent SANS modification. Les champs structurés deviennent prioritaires.
  - Les nouveaux champs NIVEAU A sont `requis=False` : `is_complete` est INCHANGÉ
    (aucune régression). Leur promotion en `requis=True` est un réglage ultérieur,
    à valider en collecte réelle.
"""

from __future__ import annotations

from typing import Any

# ── Énumérations / clés ───────────────────────────────────────────────────────
AVQ_NIVEAUX = ("AUTONOME", "DIFFICULTE", "AIDE_PARTIELLE", "AIDE_TOTALE")
AVQ_BESOIN_AIDE = ("DIFFICULTE", "AIDE_PARTIELLE", "AIDE_TOTALE")  # niveaux impliquant un besoin

AVQ_CHAMPS = [
    "avq_toilette", "avq_habillage", "avq_repas",
    "avq_deplacements", "avq_gestion_quotidienne",
]

DROITS_KEYS = [
    "aah", "pch", "rqth",
    "cmi_invalidite", "cmi_priorite", "cmi_stationnement",
]

# Mapping droit structuré → libellé texte (compat `droits_demandes` lu par les moteurs/CERFA)
_DROIT_LABEL = {
    "aah":              "AAH",
    "pch":              "PCH",
    "rqth":             "RQTH",
    "cmi_invalidite":   "CMI invalidité",
    "cmi_priorite":     "CMI priorité",
    "cmi_stationnement": "CMI stationnement",
    "aeeh":             "AEEH",
}

ORGANISME_PAYEUR_VALEURS = ("CAF", "MSA", "AUTRE")


# ── Criticité des champs (gestion des refus « champ non communiqué ») ─────────
# Le refus d'un champ BLOQUANT empêche la finalisation tant que le professionnel
# n'a pas tranché. Le refus d'un autre champ est seulement SIGNALÉ (alerte pro) et
# n'empêche pas de finaliser. Dans les deux cas : message bienveillant à la famille,
# alerte au professionnel, et AUCUNE valeur inventée.
CHAMPS_CRITIQUES_BLOQUANTS = {
    "nom_prenom",
    "date_naissance",
    "adresse_complete",
    "num_secu",
    "departement",
    # NB : `diagnostics` n'est PLUS bloquant. Le médical (diagnostic, traitements,
    # médecin) ne figure pas sur ce CERFA — il est sur le certificat médical 15695,
    # rempli par le médecin. On ne le demande pas, on ne le bloque pas. Cf. cartographie.
    "droits_demandes",          # type(s) de demande — sans quoi la MDPH ne peut instruire
    "representant_legal_nom",   # enfant / majeur protégé : représentant légal indispensable
}


def criticite_champ(field_id: str) -> str:
    """'bloquant' si le refus de ce champ empêche la finalisation, sinon 'signale'."""
    return "bloquant" if field_id in CHAMPS_CRITIQUES_BLOQUANTS else "signale"


# ── NIVEAU A — champs ajoutés (requis=False : is_complete inchangé) ───────────
_NIVEAU_A_IDENTITE = [
    {"id": "prenom",        "label": "Prénom(s)",                    "requis": False, "niveau": "A"},
    {"id": "nom_naissance", "label": "Nom de naissance",            "requis": False, "niveau": "A"},
]
_NIVEAU_A_ADMIN = [
    {"id": "organisme_payeur",   "label": "Organisme payeur (CAF / MSA / autre)",        "requis": False, "niveau": "A"},
    {"id": "numero_allocataire", "label": "Numéro d'allocataire CAF ou MSA",             "requis": False, "niveau": "A"},
]
_NIVEAU_A_INVALIDITE = [
    {"id": "pension_invalidite",     "label": "Bénéficiez-vous d'une pension d'invalidité ?", "requis": False, "niveau": "A"},
    {"id": "categorie_invalidite",   "label": "Catégorie d'invalidité (1, 2 ou 3)",           "requis": False, "niveau": "A"},
    {"id": "accident_travail",       "label": "Accident du travail (description)",            "requis": False, "niveau": "A"},
    {"id": "maladie_professionnelle", "label": "Maladie professionnelle (description)",       "requis": False, "niveau": "A"},
    {"id": "taux_ipp",               "label": "Taux d'incapacité permanente (IPP) %",         "requis": False, "niveau": "A"},
]
_NIVEAU_A_AVQ = [
    {"id": cid, "label": f"Autonomie — {cid.replace('avq_', '').replace('_', ' ')}",
     "requis": False, "niveau": "A", "type": "avq_level"}
    for cid in AVQ_CHAMPS
]

NIVEAU_A_COMMUN = (
    _NIVEAU_A_IDENTITE + _NIVEAU_A_ADMIN + _NIVEAU_A_INVALIDITE + _NIVEAU_A_AVQ
)


# ── Checklists existantes (reproduites fidèlement) + NIVEAU A ─────────────────
# (Les ids/requis/conditions des champs existants sont conservés à l'identique
#  pour ne PAS changer le comportement de collecte ni is_complete.)

_BASE_COMMUN = [
    {"id": "nom_prenom",     "label": "Nom et prénom",                  "requis": True},
    {"id": "date_naissance", "label": "Date de naissance (JJ/MM/AAAA)", "requis": True},
    {"id": "genre",          "label": "Genre",                          "requis": True},
    {"id": "adresse_complete", "label": "Adresse complète",             "requis": True},
    {"id": "num_secu",       "label": "Numéro de Sécurité Sociale",     "requis": True},
    {"id": "telephone",      "label": "Téléphone",                      "requis": True},
    {"id": "departement",    "label": "Département MDPH",                "requis": True},
    # Médical HORS CERFA (cf. cartographie) : diagnostic, traitements et médecin
    # traitant ne sont NI demandés NI inscrits sur ce formulaire — ils figurent sur
    # le certificat médical 15695 rempli par le médecin. Seuls comptent ici
    # l'existence du certificat et SA date (champ certificat_medical_date, dictionnaire),
    # avec alerte instructeur si absent ou de plus d'un an. On garde uniquement le
    # RETENTISSEMENT fonctionnel (impact_quotidien), qui, lui, est bien sur le CERFA.
    {"id": "impact_quotidien", "label": "Impact du handicap sur la vie quotidienne", "requis": True},
    {"id": "historique_mdph", "label": "Historique MDPH",               "requis": True},
]

_CHRONO_EXPR = [
    {"id": "date_debut_limitations", "label": "Depuis quand les limitations sont-elles présentes ?", "requis": False},
    {"id": "expression_directe",     "label": "Expression directe : ce que la personne vit au quotidien", "requis": False},
]
_DROITS_TEXTE = [
    {"id": "droits_demandes", "label": "Droits et prestations souhaités (AAH, PCH, RQTH, CMI, AEEH…)", "requis": False},
]

_ADULTE = _BASE_COMMUN + [
    {"id": "situation_familiale", "label": "Situation familiale (célibataire, en couple…)", "requis": True},
    {"id": "enfants_a_charge",    "label": "Nombre d'enfants à charge",                     "requis": True},
    {"id": "qualification_section_c", "label": "Êtes-vous actuellement en formation ?",      "requis": True},
    {"id": "formation_actuelle", "label": "Nom et type de la formation en cours", "requis": True,
     "condition": {"champ": "qualification_section_c", "valeur": "oui"}},
    {"id": "qualification_section_d", "label": "Avez-vous un projet professionnel ou une demande RQTH ?", "requis": True},
    {"id": "statut_emploi", "label": "Statut professionnel actuel", "requis": True,
     "condition": {"champ": "qualification_section_d", "valeur": "oui"}},
]

_ENFANT = _BASE_COMMUN + [
    {"id": "representant_legal_nom",  "label": "Nom du représentant légal", "requis": True},
    {"id": "representant_legal_lien", "label": "Lien avec l'enfant",        "requis": True},
    {"id": "situation_scolaire",      "label": "Situation scolaire de l'enfant", "requis": True},
    {"id": "etablissement_scolaire",  "label": "Nom de l'établissement scolaire", "requis": True},
]

_PROTEGE = _BASE_COMMUN + [
    {"id": "representant_legal_nom", "label": "Nom du tuteur ou curateur", "requis": True},
    {"id": "type_protection",       "label": "Type de mesure de protection", "requis": True},
    {"id": "jugement_tribunal",     "label": "Tribunal et date du jugement", "requis": True},
    {"id": "statut_emploi",         "label": "Statut professionnel ou d'activité", "requis": True},
]

_PROFILS = {
    "adulte":  _ADULTE,
    "mixte":   _ADULTE,
    "enfant":  _ENFANT,
    "protege": _PROTEGE,
}


def checklist_for(profil: str) -> list[dict]:
    """
    Retourne la checklist UNIQUE pour un profil (source de vérité).
    = champs existants (inchangés) + NIVEAU A (requis=False) + chrono/expression + droits texte.
    """
    base = _PROFILS.get((profil or "adulte").lower(), _ADULTE)
    items = list(base) + list(NIVEAU_A_COMMUN) + list(_CHRONO_EXPR) + list(_DROITS_TEXTE)
    # Fusion avec le DICTIONNAIRE CERFA (source de vérité unique) : il PRIME par id.
    # C'est ce qui rend enfin « demandés » des champs jamais posés jusqu'ici
    # (mode de contact MDPH, CAF / n° allocataire, caisse, etc.). Si le module
    # est absent, dégradation gracieuse : on garde la checklist historique.
    try:
        from app.services.cerfa_dictionary import champs_checklist
        par_id = {it["id"]: it for it in items}
        for d in champs_checklist((profil or "adulte").lower()):
            par_id[d["id"]] = d
        items = list(par_id.values())
    except Exception:
        pass
    return items


def condition_remplie(donnees: dict[str, Any], condition: dict | None) -> bool:
    """
    Évalue la condition d'applicabilité d'un champ (source unique, partagée par la
    collecte, la revue et l'extraction). Formes supportées :
      - {"champ": X, "valeur": "y"}      → la valeur de X commence par « y »
      - {"champ": X, "valeur_in": [...]} → la valeur de X commence par l'une d'elles
      - {"champ": X, "present": True}    → X est renseigné (non vide)
    Pas de condition → champ toujours applicable.
    """
    if not condition:
        return True
    brut = donnees.get(condition.get("champ"))
    if condition.get("present"):
        return brut not in (None, "", 0, [])
    val = str(brut or "").lower()
    if "valeur_in" in condition:
        return any(val.startswith(str(v).lower()) for v in condition["valeur_in"])
    return val.startswith(str(condition.get("valeur", "")).lower())


# ── Normalisation (compat structuré ↔ legacy) — fonction PURE ────────────────
def normaliser_collecte(donnees: dict[str, Any]) -> dict[str, Any]:
    """
    Rend les champs structurés Vague 1 exploitables par les consommateurs existants
    SANS les modifier :
      - `droits` (dict booléens) → `droits_demandes` (texte) si non déjà renseigné.
      - `prenom`/`nom_naissance` : laissés tels quels (lus en priorité par field_mapper).
    Fonction pure : retourne un nouveau dict (n'écrase pas l'objet d'origine).
    Idempotente.
    """
    d = dict(donnees or {})

    # Droits structurés → libellés texte (compat moteurs / CERFA qui lisent droits_demandes)
    droits = d.get("droits")
    if isinstance(droits, dict):
        labels = [_DROIT_LABEL.get(k, k.upper()) for k in DROITS_KEYS + ["aeeh"]
                  if droits.get(k) is True]
        if labels:
            existant = str(d.get("droits_demandes", "") or "").strip()
            # Le structuré fait autorité : fusionne sans doublonner
            fusion = existant
            for lab in labels:
                if lab.upper() not in fusion.upper():
                    fusion = (fusion + ", " + lab).strip(", ") if fusion else lab
            d["droits_demandes"] = fusion

    return d


def droits_objet_vers_liste(droits: Any) -> list[str]:
    """Helper d'affichage : objet droits.* → liste de libellés actifs."""
    if not isinstance(droits, dict):
        return []
    return [_DROIT_LABEL.get(k, k.upper()) for k in DROITS_KEYS + ["aeeh"] if droits.get(k) is True]


# Alias historiques du numéro de sécurité sociale (NIR). L'interface, l'extraction
# et la collecte WhatsApp utilisent des noms différents : on les garde tous alignés.
_NIR_ALIASES = ("num_secu", "numero_securite_sociale", "nss")


def synchroniser_nir(donnees: dict[str, Any]) -> None:
    """
    Aligne EN PLACE les alias du NIR dans `donnees`. Source = première valeur non
    vide parmi `_NIR_ALIASES` ; sa valeur (espaces retirés) est recopiée sur tous
    les alias. Idempotent. Centralise une logique jusqu'ici copiée-collée en
    4 endroits (et déjà divergente : un seul site gérait l'alias `nss`), évitant
    qu'un NIR saisi sur un canal soit redemandé sur un autre.
    """
    if not isinstance(donnees, dict):
        return
    nir = ""
    for a in _NIR_ALIASES:
        v = str(donnees.get(a) or "").strip()
        if v:
            nir = v.replace(" ", "")
            break
    if not nir:
        return
    for a in _NIR_ALIASES:
        donnees[a] = nir


def code_postal_vers_departement(cp: str | None) -> str:
    """
    Code postal → code département. Gère les DOM/COM : 971-976 et 98x utilisent
    les 3 premiers chiffres (974 = La Réunion), les autres les 2 premiers.
    Retourne "" si le code postal est inexploitable.
    """
    cp = str(cp or "").strip()
    if len(cp) < 2 or not cp[:2].isdigit():
        return ""
    return cp[:3] if cp[:2] in ("97", "98") else cp[:2]
