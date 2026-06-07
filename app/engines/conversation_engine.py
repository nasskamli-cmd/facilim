"""
app/engines/conversation_engine.py — Moteur conversationnel omnicanal.

Ce moteur orchestre la conversation entre l'usager et "l'Assistant Facilim".
L'usager voit toujours le même interlocuteur.
En interne, différents états logiques (personas) gèrent des phases distinctes :
  - intake      : accueil, consentement, identification
  - collecte    : collecte conversationnelle des informations
  - documents   : demande et réception des pièces justificatives
  - analyse     : attente de l'analyse (messages de statut)
  - validation  : questions de clarification post-analyse
  - cloture     : confirmation de complétude

Le moteur est EVENT-DRIVEN : chaque message entrant déclenche
immédiatement un traitement et une réponse.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("facilim.engines.conversation")

# ── Nom public (façade unique) ────────────────────────────────────────────────
PERSONA_PUBLIC_NOM = "l'Assistant Facilim"

# ── États internes (invisibles à l'usager) ────────────────────────────────────
class ConversationState:
    INTAKE     = "intake"
    CONSENT    = "consent"
    COLLECTE   = "collecte"
    DOCUMENTS  = "documents"
    ANALYSE    = "analyse"
    VALIDATION = "validation"
    CLOTURE    = "cloture"
    TERMINE    = "termine"


# ── Checklist MDPH — champs communs à tous les profils ───────────────────────
CHECKLIST_MDPH_BASE = [
    {"id": "nom_prenom",       "label": "Nom et prénom",                  "requis": True},
    {"id": "date_naissance",   "label": "Date de naissance (JJ/MM/AAAA)", "requis": True},
    {"id": "genre",            "label": "Genre (homme/femme)",             "requis": True},
    {"id": "adresse_complete", "label": "Adresse complète",                "requis": True},
    {"id": "num_secu",         "label": "Numéro de Sécurité Sociale",      "requis": True},
    {"id": "telephone",        "label": "Numéro de téléphone de contact",  "requis": True},
    {"id": "departement",      "label": "Département MDPH",                "requis": True},
    {"id": "diagnostics",         "label": "Diagnostic(s) précis",                                  "requis": True},
    {"id": "traitements",         "label": "Traitements médicaux en cours",                          "requis": True},
    {"id": "impact_quotidien",    "label": "Impact du handicap sur la vie quotidienne",              "requis": True},
    {"id": "historique_mdph",     "label": "Historique MDPH (première demande ou renouvellement)",  "requis": True},
    # Note : médecin traitant non requis par le CERFA MDPH — supprimé de la checklist obligatoire
    {"id": "statut_occupation",   "label": "Situation de logement (locataire, propriétaire, hébergé…)", "requis": True},
]

# ── Champs ADULTE (sections B et identité) ───────────────────────────────────
_CHAMPS_ADULTE = [
    {"id": "situation_familiale",   "label": "Situation familiale (célibataire, en couple…)", "requis": True},
    {"id": "enfants_a_charge",      "label": "Nombre d'enfants à charge",                     "requis": True},
    {"id": "inscrit_pole_emploi",   "label": "Êtes-vous inscrit(e) à France Travail (Pôle Emploi) ?", "requis": False},
    {"id": "numero_allocataire",    "label": "Numéro d'allocataire CAF ou MSA (si vous en avez un)", "requis": False},
]

# ── Champs ENFANT (section C scolaire + représentant légal) ──────────────────
_CHAMPS_ENFANT = [
    {"id": "situation_scolaire",      "label": "Situation scolaire de l'enfant",                   "requis": True},
    {"id": "etablissement_scolaire",  "label": "Nom de l'établissement scolaire",                   "requis": True},
    {"id": "representant_legal_nom",  "label": "Nom du représentant légal",                         "requis": True},
    {"id": "representant_legal_lien", "label": "Lien du représentant avec l'enfant",                "requis": True},
]

# ── Section C — Scolarité/formation (adulte/mixte) ────────────────────────────
# Question de qualification (toujours posée pour adulte/mixte).
# Les champs détaillés ne sont requis que si qualification == "oui".
_CHAMPS_SECTION_C_ADULTE = [
    {
        "id":     "qualification_section_c",
        "label":  "Êtes-vous actuellement en formation ou en insertion professionnelle ?",
        "requis": True,
    },
    {
        "id":        "formation_actuelle",
        "label":     "Nom et type de la formation en cours",
        "requis":    True,
        "condition": {"champ": "qualification_section_c", "valeur": "oui"},
    },
    {
        "id":        "etablissement_formation",
        "label":     "Nom de l'établissement de formation",
        "requis":    False,
        "condition": {"champ": "qualification_section_c", "valeur": "oui"},
    },
]

# ── Section D — Situation professionnelle ─────────────────────────────────────
# Question de qualification (toujours posée pour adulte/mixte).
# Les champs détaillés ne sont requis que si qualification == "oui".
_CHAMPS_SECTION_D = [
    {
        "id":     "qualification_section_d",
        "label":  "Avez-vous un projet professionnel ou souhaitez-vous demander une RQTH ?",
        "requis": True,
    },
    {
        "id":        "statut_emploi",
        "label":     "Statut professionnel actuel (emploi, chômage, inactif, ESAT…)",
        "requis":    True,
        "condition": {"champ": "qualification_section_d", "valeur": "oui"},
    },
    {
        "id":        "projet_professionnel",
        "label":     "Description du projet professionnel ou de la demande RQTH",
        "requis":    False,
        "condition": {"champ": "qualification_section_d", "valeur": "oui"},
    },
]

# ── Section E — Droits et prestations (tous profils, EN FIN de collecte) ──────
# requis=False : non bloquante — proposée quand les besoins sont clarifiés.
_CHAMPS_SECTION_E = [
    {
        "id":     "droits_demandes",
        "label":  "Droits et prestations souhaités (AAH, PCH, RQTH, CMI, AEEH…)",
        "requis": False,
    },
    {
        "id":     "projet_orientation",
        "label":  "Projet d'orientation ou projet de vie",
        "requis": False,
    },
]

# ── Section F — Aidant familial (conditionnel, sur demande de l'aidant) ───────
# La qualification elle-même est non-bloquante.
_CHAMPS_SECTION_F = [
    {
        "id":     "qualification_section_f",
        "label":  "Souhaitez-vous ajouter les besoins de l'aidant familial ?",
        "requis": False,
    },
    {
        "id":        "aidant_nom",
        "label":     "Nom et prénom de l'aidant familial",
        "requis":    False,
        "condition": {"champ": "qualification_section_f", "valeur": "oui"},
    },
    {
        "id":        "aidant_besoins",
        "label":     "Besoins et attentes de l'aidant familial",
        "requis":    False,
        "condition": {"champ": "qualification_section_f", "valeur": "oui"},
    },
]

# ── Checklists complètes par profil ───────────────────────────────────────────
# ⚠️ DÉPRÉCIÉ (Vague 1) — modèle parallèle NON utilisé par le flux réel.
# La source de vérité UNIQUE est désormais `app/services/collecte_schema.py`
# (`checklist_for(profil)`), utilisée par les agents actifs. Ne plus étendre ceci.
CHECKLIST_MDPH = (
    CHECKLIST_MDPH_BASE
    + _CHAMPS_ADULTE
    + _CHAMPS_SECTION_C_ADULTE
    + _CHAMPS_SECTION_D
    + _CHAMPS_SECTION_E
    + _CHAMPS_SECTION_F
)

CHECKLIST_MDPH_ENFANT = (
    CHECKLIST_MDPH_BASE
    + _CHAMPS_ENFANT
    + _CHAMPS_SECTION_E
    + _CHAMPS_SECTION_F
)

CHECKLIST_MDPH_MIXTE = (
    CHECKLIST_MDPH_BASE
    + _CHAMPS_ADULTE
    + _CHAMPS_ENFANT
    + _CHAMPS_SECTION_C_ADULTE
    + _CHAMPS_SECTION_D
    + _CHAMPS_SECTION_E
    + _CHAMPS_SECTION_F
)

CHECKLIST_IDS = {item["id"] for item in CHECKLIST_MDPH}


def get_checklist(profil_mdph: str) -> list[dict]:
    """
    Retourne la checklist adaptée au profil.
    Délègue aux agents singletons (source unique de vérité).
    Fallback sur CHECKLIST_MDPH (adulte) si le profil n'est pas reconnu.
    """
    try:
        from app.services.conversation.router import get_agent
        return get_agent(profil_mdph).CHECKLIST
    except Exception:
        return CHECKLIST_MDPH  # fallback conservateur


# ── Structure des onglets — navigation conversationnelle ──────────────────────
#
# "conditionnel": True  → l'onglet n'est activé que si la question de qualification
#                         (stockée dans donnees) reçoit une réponse positive.
# "condition"           → champ + valeur déclencheurs.
# "profils"             → liste des profils pour lesquels cet onglet est actif.
#                         Si absent, actif pour tous.

ONGLETS_MDPH: list[dict] = [
    {
        "num": 1,
        "titre": "Accueil & Identification",
        "champs": [],
    },
    {
        "num": 2,
        "titre": "Identité (Section A)",
        "champs": ["nom_prenom", "date_naissance", "genre", "num_secu",
                   "adresse_complete", "telephone", "departement"],
        "resume_validation": "L'identité et les coordonnées",
    },
    {
        "num": 3,
        "titre": "Représentation & Urgences (A2 / A3 / A4 / A5)",
        "champs": [],   # géré par l'agent selon le profil (représentant légal, urgence)
        "resume_validation": "La représentation légale et les situations d'urgence",
    },
    {
        "num": 4,
        "titre": "Vie quotidienne (Section B1)",
        "champs": ["impact_quotidien"],
        "resume_validation": "L'impact du handicap sur la vie quotidienne",
    },
    {
        "num": 5,
        "titre": "Aides & Compensations (Section B2)",
        "champs": [],   # renseigné par le professionnel via Dashboard
        "resume_validation": "Les aides déjà en place",
    },
    {
        "num": 6,
        "titre": "Frais à charge (Section B3)",
        "champs": [],   # collecté dans la conversation B2/B3
        "resume_validation": "Les frais restant à charge",
    },
    {
        "num": 7,
        "titre": "Scolarité & Formation (Section C)",
        # Enfant : toujours actif
        # Adulte/mixte : conditionnel sur qualification_section_c
        # Mécanisme unifié : "condition_par_profil" liste les profils qui nécessitent
        # une qualification avant d'ouvrir l'onglet.
        "champs": ["situation_scolaire", "etablissement_scolaire",
                   "qualification_section_c", "formation_actuelle"],
        "resume_validation": "La situation scolaire ou de formation",
        "condition_par_profil": {
            "adulte": {"champ": "qualification_section_c", "valeur": "oui"},
            "mixte":  {"champ": "qualification_section_c", "valeur": "oui"},
        },
    },
    {
        "num": 8,
        "titre": "Situation professionnelle (Section D)",
        # Conditionnel sur qualification_section_d
        "champs": ["qualification_section_d", "statut_emploi"],
        "resume_validation": "La situation professionnelle et le projet",
        "profils": ["adulte", "mixte"],
        "conditionnel": True,
        "condition": {"champ": "qualification_section_d", "valeur": "oui"},
    },
    {
        "num": 9,
        "titre": "Droits & Prestations demandés (Section E)",
        # Toujours en fin de parcours — non bloquant
        "champs": ["droits_demandes"],
        "resume_validation": "Les droits et prestations souhaités",
    },
    {
        "num": 10,
        "titre": "Aidant familial (Section F)",
        # Conditionnel sur qualification_section_f
        "champs": ["qualification_section_f", "aidant_nom", "aidant_besoins"],
        "resume_validation": "Les besoins de l'aidant familial",
        "conditionnel": True,
        "condition": {"champ": "qualification_section_f", "valeur": "oui"},
    },
]

# Index rapide : champ_id → numéro d'onglet
_CHAMP_VERS_ONGLET: dict[str, int] = {}
for _onglet in ONGLETS_MDPH:
    for _champ in _onglet["champs"]:
        _CHAMP_VERS_ONGLET[_champ] = _onglet["num"]


@dataclass
class TabNavigationState:
    """État de navigation par onglets pour une session conversationnelle."""
    onglet_courant:      int       = 2      # commence à l'onglet 2 (identité)
    validation_demandee: bool      = False
    onglets_valides:     list[int] = field(default_factory=list)
    # Verrou de profil : une fois déterminé, jamais recalculé.
    # Évite tout rebasculement entre agents en cours de session.
    profil_mdph_lock:    str       = ""     # "" = non encore verrouillé


def detecter_saut_onglet(
    donnees_actuelles: dict[str, Any],
    nouveau_champ: str,
    onglet_courant: int,
) -> bool:
    """
    Retourne True si le nouveau champ appartient à un onglet PLUS AVANCÉ
    que l'onglet courant (détection de saut de sujet).
    """
    onglet_cible = _CHAMP_VERS_ONGLET.get(nouveau_champ, onglet_courant)
    return onglet_cible > onglet_courant + 1


def _champs_onglet_pour_profil(onglet_champs: list[str], profil: str) -> list[str]:
    """
    Filtre la liste des champs d'un onglet pour ne garder que ceux
    qui figurent dans la checklist du profil courant.
    Évite d'exiger des champs adultes pour un enfant (et vice-versa).
    """
    checklist_ids = {item["id"] for item in get_checklist(profil)}
    return [c for c in onglet_champs if c in checklist_ids]


def onglet_courant_complet(
    donnees: dict[str, Any],
    onglet_num: int,
    profil: str = "adulte",
) -> bool:
    """
    Vérifie si tous les champs requis de l'onglet courant sont renseignés.

    Règles :
    - Onglet non applicable au profil → True (ignoré)
    - Onglet conditionnel dont la condition n'est pas remplie → True (ignoré)
    - Seuls les champs présents dans la checklist du profil sont exigés
      (empêche de bloquer sur des champs adultes pour un enfant)
    """
    onglet = next((o for o in ONGLETS_MDPH if o["num"] == onglet_num), None)
    if not onglet:
        return True

    # Profil non concerné par cet onglet
    profils_autorises = onglet.get("profils")
    if profils_autorises and profil not in profils_autorises:
        return True

    # ── Condition générale (onglets 8, 10) ───────────────────────────────────
    if onglet.get("conditionnel"):
        cond = onglet.get("condition", {})
        valeur_actuelle = str(donnees.get(cond.get("champ", ""), "")).lower()
        if not valeur_actuelle.startswith(cond.get("valeur", "oui").lower()):
            return True  # condition non remplie → onglet sauté

    # ── Condition par profil (onglet 7 — Section C) ───────────────────────
    # Mécanisme unifié : remplace l'ancien "conditionnel_adulte"
    conditions_profil = onglet.get("condition_par_profil", {})
    if profil in conditions_profil:
        cond = conditions_profil[profil]
        qual = str(donnees.get(cond["champ"], "")).lower()
        valeur_cible = cond["valeur"].lower()
        if qual.startswith("non"):
            return True          # explicitement non concerné → onglet ignoré
        if qual.startswith(valeur_cible):
            # Condition satisfaite → vérifier les champs spécifiques au profil
            champs_profil = _champs_onglet_pour_profil(onglet.get("champs", []), profil)
            return all(donnees.get(c) for c in champs_profil)
        return False             # qualification pas encore répondue

    # Cas général : filtrer les champs par profil AVANT de vérifier
    champs_du_profil = _champs_onglet_pour_profil(onglet.get("champs", []), profil)

    # Si aucun champ de l'onglet n'appartient au profil → onglet ignoré
    if not champs_du_profil and onglet.get("champs"):
        return True

    return all(donnees.get(c) for c in champs_du_profil)


def generer_message_validation_onglet(onglet_num: int) -> str:
    """
    Génère le message de demande de validation d'un onglet avant de passer au suivant.
    Formulé en FALC, chaleureux.
    """
    onglet = next((o for o in ONGLETS_MDPH if o["num"] == onglet_num), None)
    if not onglet:
        return ""
    resume = onglet.get("resume_validation", f"la section {onglet['titre']}")
    return (
        f"✅ Nous avons bien noté *{resume}*.\n\n"
        "Est-ce que ces informations sont correctes et complètes ?\n"
        "Répondez *OUI* pour confirmer, ou dites-moi ce qu'il faut corriger."
    )


def detect_missing_fields(donnees: dict[str, Any], profil_mdph: str = "inconnu") -> list[str]:
    """
    Retourne les libellés des champs manquants dans la checklist adaptée au profil.

    Le profil détermine quels champs sont obligatoires :
      - "enfant"  → checklist sans champs adultes (emploi, situation maritale…)
      - "mixte"   → checklist complète (scolaire + professionnel)
      - "adulte"  → checklist adulte standard
      - "inconnu" → checklist adulte par défaut (conservative)
    """
    checklist = get_checklist(profil_mdph)
    missing = []
    for item in checklist:
        # Champs non-requis (section E, F) ne bloquent pas la progression
        if not item.get("requis", True):
            continue
        # Champs conditionnels : évaluer la condition avant d'exiger le champ
        condition = item.get("condition")
        if condition:
            valeur_condition = str(donnees.get(condition["champ"], "")).lower()
            if not valeur_condition.startswith(condition["valeur"].lower()):
                continue  # condition non remplie → champ ignoré pour l'instant
        if not donnees.get(item["id"]):
            missing.append(item["label"])
    return missing


# ── Champs extractibles par profil ───────────────────────────────────────────
# Seuls ces champs peuvent être extraits pour chaque profil.
# Empêche la pollution de synthese_json avec des concepts inadaptés
# (ex : situation_familiale extraite d'un dossier enfant).

_CHAMPS_EXTRACTIBLES_ENFANT = [
    "nom_prenom", "date_naissance", "genre", "adresse_complete",
    "num_secu", "numero_securite_sociale", "telephone", "email", "departement",
    "diagnostics", "traitements", "medecin_traitant", "impact_quotidien",
    "historique_mdph", "numero_dossier_mdph",
    # Spécifique enfant
    "situation_scolaire", "etablissement_scolaire",
    "representant_legal_nom", "representant_legal_lien",
    # Section E
    "droits_demandes", "projet_orientation",
    # Section F
    "qualification_section_f", "aidant_nom", "aidant_besoins",
]

_CHAMPS_EXTRACTIBLES_ADULTE = [
    "nom_prenom", "date_naissance", "genre", "adresse_complete",
    "num_secu", "numero_securite_sociale", "telephone", "email", "departement",
    "situation_familiale", "enfants_a_charge",
    "diagnostics", "traitements", "medecin_traitant", "impact_quotidien",
    "historique_mdph", "numero_dossier_mdph",
    "protection_juridique", "sous_tutelle",
    # Section C (qualification + champs)
    "qualification_section_c", "formation_actuelle", "etablissement_formation",
    # Section D (qualification + champs)
    "qualification_section_d", "statut_emploi", "projet_professionnel",
    # Section E
    "droits_demandes", "projet_orientation",
    # Section F
    "qualification_section_f", "aidant_nom", "aidant_besoins",
]

_CHAMPS_EXTRACTIBLES_MIXTE = list(
    {*_CHAMPS_EXTRACTIBLES_ENFANT, *_CHAMPS_EXTRACTIBLES_ADULTE}
)


def _champs_extractibles(profil_mdph: str) -> list[str]:
    if profil_mdph == "enfant":
        return _CHAMPS_EXTRACTIBLES_ENFANT
    if profil_mdph == "mixte":
        return _CHAMPS_EXTRACTIBLES_MIXTE
    return _CHAMPS_EXTRACTIBLES_ADULTE


def extract_structured_data_from_history(
    historique: list[dict],
    openai_client: Any,
    model: str = "gpt-4o-mini",
    profil_mdph: str = "inconnu",
) -> dict[str, Any]:
    """
    Extrait les données structurées de l'historique conversationnel.

    Le paramètre profil_mdph filtre la liste des champs extractibles :
    - Un dossier enfant ne peut JAMAIS produire situation_familiale,
      enfants_a_charge, statut_emploi, etc.
    - Un dossier adulte ne produit pas situation_scolaire.

    Ce filtrage est la dernière ligne de défense avant la persistance.
    """
    if not historique:
        return {}

    champs = _champs_extractibles(profil_mdph)
    champs_str = ", ".join(champs)

    conversation_text = "\n".join(
        f"{'Usager' if m.get('role') == 'user' else 'Assistant'}: {m.get('content', '')}"
        for m in historique[-20:]
        if m.get("role") in ("user", "assistant")
    )

    prompt = f"""Analyse cette conversation et extrait les informations MDPH collectées.
Retourne UNIQUEMENT un JSON valide avec les champs trouvés PARMI CETTE LISTE STRICTE :
{champs_str}

RÈGLE ABSOLUE : n'inclus AUCUN champ hors de cette liste, même si tu le trouves dans la conversation.
Si un champ n'est pas trouvé, ne l'inclus pas.
Exemple : {{"nom_prenom": "Jean Dupont", "date_naissance": "15/03/1980"}}

Conversation :
{conversation_text}
"""
    try:
        response = openai_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content.strip()
        extracted = json.loads(raw)

        # Filtrage défensif : supprimer tout champ hors whitelist même si le LLM triche
        champs_autorises = set(champs)
        filtered = {k: v for k, v in extracted.items() if k in champs_autorises}
        if len(filtered) != len(extracted):
            rejetes = set(extracted) - champs_autorises
            logger.warning("[CONV] Champs rejetés (hors profil %s) : %s", profil_mdph, rejetes)

        return filtered

    except Exception as e:
        logger.warning(f"[CONV] Extraction données échouée : {e}")
        return {}
