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
    "diagnostics",
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
    {"id": "diagnostics",    "label": "Diagnostic(s) médical(aux)",     "requis": True},
    {"id": "traitements",    "label": "Traitements en cours",          "requis": True},
    {"id": "medecin_traitant", "label": "Médecin traitant (nom et ville)", "requis": True},
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
    return list(base) + list(NIVEAU_A_COMMUN) + list(_CHRONO_EXPR) + list(_DROITS_TEXTE)


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
