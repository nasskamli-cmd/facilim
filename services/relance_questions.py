"""
services/relance_questions.py — Questions de relance WhatsApp pour champs CERFA manquants.

Architecture :
  - MAPPING_CHAMP_QUESTION : clé = NOM DE CHAMP CERFA (stable),
    PAS message d'erreur textuel (fragile, casse silencieusement à chaque modif du validateur).
  - obtenir_questions_depuis_champs(champs) → questions à partir de noms de champs directs.
  - obtenir_questions_depuis_erreurs(erreurs) → compat si le validateur retourne des strings.
    Extrait le nom de champ depuis le message d'erreur via regex + fallback substring.
  - formuler_message_whatsapp(champs) → UNE SEULE question (principe FALC : jamais de liste).
  - formuler_message_dashboard(champs) → résumé multi-lignes pour l'interface éducateur
    (ne PAS envoyer tel quel via WhatsApp).

Contrainte RGPD art. 9 :
  Les champs MEDICAL_FIELDS (diagnostic, NIR, médecin, traitements, taux) ne génèrent
  JAMAIS une question directe via WhatsApp. Ils déclenchent le message de redirection
  vers le canal sécurisé (email / messagerie chiffrée de la structure).
"""

from __future__ import annotations

import re
import logging
from typing import Sequence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes de champ — immuables, réutilisées dans les deux sens
# (import depuis conversation_agent si tu veux centraliser, mais
#  les dupliquer ici évite l'import circulaire)
# ---------------------------------------------------------------------------

# Champs médicaux : jamais via WhatsApp — redirection canal sécurisé
_MEDICAL_FIELDS: frozenset[str] = frozenset({
    "numero_securite_sociale",
    "diagnostic_principal",
    "medecin_traitant",
    "traitements_en_cours",
    "taux_incapacite",
})

# Message de redirection canal sécurisé (cohérent avec conversation_agent.py)
_MSG_CANAL_SECURISE = (
    "🔒 Pour les informations médicales (diagnostic, numéro de sécurité sociale, "
    "médecin traitant, traitements), merci de les transmettre *par email* à votre "
    "accompagnateur ou via la messagerie sécurisée de votre structure. "
    "Ces données ne peuvent pas être partagées par WhatsApp."
)

# ---------------------------------------------------------------------------
# Mapping principal : NOM DE CHAMP → question WhatsApp (FALC, 1 seule phrase)
# Phrases courtes, vocabulaire simple, sans jargon administratif.
# ---------------------------------------------------------------------------

MAPPING_CHAMP_QUESTION: dict[str, str] = {
    # Section A — Identité
    "type_demande": (
        "Est-ce une *première demande* à la MDPH, ou un *renouvellement* de droits déjà accordés ?"
    ),
    "urgence_droits": (
        "Vos droits actuels arrivent-ils à échéance dans *moins de 2 mois* ? (répondez oui ou non)"
    ),
    "nom_prenom": (
        "Quel est le *nom et prénom complet* de la personne concernée par la demande MDPH ?"
    ),
    "date_naissance": (
        "Quelle est la *date de naissance* de la personne ? (format JJ/MM/AAAA)"
    ),
    "genre": (
        "La personne est-elle un *homme* ou une *femme* ?"
    ),
    "adresse_complete": (
        "Quelle est l'*adresse complète* de la personne ? (numéro, rue, code postal, ville)"
    ),
    "situation_familiale": (
        "Quelle est la *situation familiale* de la personne ? "
        "(célibataire, marié·e, en couple, divorcé·e, veuf·ve…)"
    ),
    "enfants_a_charge": (
        "Combien d'*enfants à charge* la personne a-t-elle ? (indiquez 0 si aucun)"
    ),
    "type_logement_statut": (
        "Dans quel type de *logement* vit la personne ? (maison, appartement, foyer, chambre chez un proche…) "
        "Et est-elle *propriétaire*, *locataire*, ou *hébergée* chez quelqu'un ?"
    ),
    "organisme_payeur": (
        "Les allocations familiales sont-elles versées par la *CAF* ou la *MSA* ?"
    ),
    "protection_juridique": (
        "La personne est-elle sous *mesure de protection juridique* ? "
        "(tutelle, curatelle, sauvegarde de justice, ou aucune)"
    ),

    # Section B — Fonctionnel (cœur du dossier)
    "difficultes_quotidiennes": (
        "Quelles sont les *principales difficultés* de la personne dans sa vie de tous les jours ? "
        "(ce qu'elle ne peut pas faire seule, ce qui lui est difficile ou épuisant)"
    ),
    "besoins_aide": (
        "De quelles *aides* la personne a-t-elle besoin au quotidien ? "
        "(aide humaine, aide technique, aménagement du logement, accompagnement…)"
    ),
    "aidant_identite": (
        "Qui aide la personne au quotidien ? Merci d'indiquer le *prénom, le nom et le lien* "
        "avec la personne aidée (ex : Marie Dupont, épouse)."
    ),
    "ressources_actuelles": (
        "Quelles sont les *ressources actuelles* de la personne ? "
        "(AAH, APL, pension d'invalidité, ARE, ou aucune) "
        "Y a-t-il des frais importants liés au handicap non remboursés ?"
    ),

    # Section C/D — Parcours
    "situation_pro_scolaire": (
        "Quelle est la *situation actuelle* de la personne ? "
        "(en emploi, en scolarité, en formation, en recherche d'emploi, sans activité…)"
    ),
    "scolarite_details": (
        "Dans quel *type d'établissement* est scolarisé·e l'enfant ? "
        "(classe ordinaire, ULIS, IME, SESSAD…) "
        "Quelle est sa *classe actuelle* ? Y a-t-il un PPS, un PAI ou une AESH en place ?"
    ),
    "qualification_parcours": (
        "Quel est le *niveau de formation* obtenu par la personne ? (CAP, BAC, BTS, licence…) "
        "Et quel était son *dernier métier ou poste* avant l'arrêt ou le handicap ?"
    ),

    # Section E — Demandes
    "type_droits": (
        "Quel(s) *type(s) de droits ou d'orientations* souhaitez-vous demander à la MDPH ? "
        "(AAH, RQTH, PCH, AEEH, CMI, orientation IME / ESAT / SESSAD…)"
    ),
    "cmi_type": (
        "Quel type de *Carte Mobilité Inclusion* est nécessaire ? "
        "— *Priorité* (difficultés à rester debout longtemps), "
        "*Stationnement* (déplacements très réduits ou périmètre de marche < 200 m), "
        "ou *les deux* ?"
    ),
    "emploi_accompagne": (
        "La personne souhaite-t-elle bénéficier d'un *accompagnement pour trouver un emploi* "
        "(dispositif emploi accompagné), ou chercher par le droit commun ?"
    ),
    "historique_mdph": (
        "Quelle est la *date de la dernière notification MDPH* et quels droits ont été accordés ?"
    ),

    # Champs médicaux → redirection (RGPD art. 9, jamais via WhatsApp)
    "numero_securite_sociale":  _MSG_CANAL_SECURISE,
    "diagnostic_principal":     _MSG_CANAL_SECURISE,
    "medecin_traitant":         _MSG_CANAL_SECURISE,
    "traitements_en_cours":     _MSG_CANAL_SECURISE,
    "taux_incapacite":          _MSG_CANAL_SECURISE,
}

# ---------------------------------------------------------------------------
# Patterns pour extraire un nom de champ depuis un message d'erreur textuel.
# Permet de rester compatible avec un validateur qui retourne des strings.
# Ordre : du plus spécifique au plus générique.
# ---------------------------------------------------------------------------

_ERREUR_PATTERNS: list[tuple[re.Pattern, str]] = [
    # "champ requis manquant : nom_du_champ"
    (re.compile(r"champ requis manquant\s*[:\-]\s*(\w+)", re.I), "field_name"),
    # "champ manquant : nom_du_champ"
    (re.compile(r"champ manquant\s*[:\-]\s*(\w+)", re.I), "field_name"),
    # "field 'nom_du_champ' missing" (format anglais éventuel)
    (re.compile(r"field\s+['\"]?(\w+)['\"]?\s+(?:is\s+)?missing", re.I), "field_name"),
    # "valeur invalide pour nom_du_champ"
    (re.compile(r"valeur invalide pour\s+(\w+)", re.I), "field_name"),
    # Patterns sémantiques pour les erreurs sans nom de champ explicite
    (re.compile(r"prestation\s+inconnue|type\s+de\s+droit|droits?\s+demand", re.I), "type_droits"),
    (re.compile(r"situation\s+famil", re.I), "situation_familiale"),
    (re.compile(r"date\s+de\s+naissance|ddn", re.I), "date_naissance"),
    (re.compile(r"num[eé]ro\s+de\s+s[eé]curit[eé]|nir\b|num[eé]ro\s+ss", re.I), "numero_securite_sociale"),
    (re.compile(r"diagnostic|pathologie", re.I), "diagnostic_principal"),
    (re.compile(r"m[eé]decin\s+traitant", re.I), "medecin_traitant"),
    (re.compile(r"traitement|m[eé]dicament", re.I), "traitements_en_cours"),
    (re.compile(r"taux\s+d.incapacit[eé]|taux\s+mdph", re.I), "taux_incapacite"),
    (re.compile(r"adresse", re.I), "adresse_complete"),
    (re.compile(r"logement|statut\s+occupation|propri[eé]taire|locataire|h[eé]berg", re.I), "type_logement_statut"),
    (re.compile(r"caf|msa|organisme\s+payeur", re.I), "organisme_payeur"),
    (re.compile(r"tutelle|curatelle|protection\s+juridique", re.I), "protection_juridique"),
    (re.compile(r"difficult[eé]s?\s+quotidien|vie\s+quotidien|retentissement", re.I), "difficultes_quotidiennes"),
    (re.compile(r"besoin[s]?\s+d.aide|aide\s+(humaine|technique)", re.I), "besoins_aide"),
    (re.compile(r"aidant|proche\s+aidant", re.I), "aidant_identite"),
    (re.compile(r"ressource|allocation|revenu", re.I), "ressources_actuelles"),
    (re.compile(r"scolarit[eé]|[eé]tablissement\s+scolaire|pps|pai|aesh", re.I), "scolarite_details"),
    (re.compile(r"qualification|niveau\s+formation|poste\s+occup[eé]|derni[eè]re?\s+emploi", re.I), "qualification_parcours"),
    (re.compile(r"cmi\b|carte\s+mobilit[eé]", re.I), "cmi_type"),
    (re.compile(r"emploi\s+accompagn[eé]|orp\b", re.I), "emploi_accompagne"),
    (re.compile(r"historique|derni[eè]re\s+notification|renouvellement", re.I), "historique_mdph"),
    (re.compile(r"type\s+de\s+demande|premi[eè]re\s+demande", re.I), "type_demande"),
    (re.compile(r"urgence|[eé]ch[eé]ance", re.I), "urgence_droits"),
    (re.compile(r"genre|homme|femme|masculin|f[eé]minin", re.I), "genre"),
    (re.compile(r"situation\s+pro|emploi|scolarit[eé]|inactiv", re.I), "situation_pro_scolaire"),
]


def _champ_depuis_erreur(erreur: str) -> str | None:
    """
    Tente d'extraire le nom du champ CERFA depuis un message d'erreur textuel.
    Retourne le nom de champ si trouvé, None sinon.
    """
    for pattern, result in _ERREUR_PATTERNS:
        m = pattern.search(erreur)
        if m:
            # Si le pattern capture un groupe → c'est le nom de champ extrait dynamiquement
            if result == "field_name" and m.lastindex:
                return m.group(1).lower()
            # Sinon → résultat statique (champ sémantique)
            return result
    return None


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------

def obtenir_questions_depuis_champs(champs_manquants: Sequence[str]) -> list[str]:
    """
    Retourne les questions correspondant à une liste de noms de champs CERFA manquants.

    - Les champs médicaux retournent le message de redirection canal sécurisé (une seule fois).
    - Les champs inconnus sont ignorés avec un warning.
    - Pas de doublon : si plusieurs champs médicaux manquent, un seul message de redirection.

    Args:
        champs_manquants: liste de noms de champs (ex: ["situation_familiale", "type_droits"])

    Returns:
        Liste de questions/messages ordonnée, dédupliquée.
    """
    questions: list[str] = []
    vus: set[str] = set()
    medical_redirect_added = False

    for champ in champs_manquants:
        if champ in _MEDICAL_FIELDS:
            if not medical_redirect_added:
                questions.append(_MSG_CANAL_SECURISE)
                medical_redirect_added = True
            continue

        question = MAPPING_CHAMP_QUESTION.get(champ)
        if not question:
            logger.warning(f"[RELANCE] Champ CERFA inconnu dans le mapping : {champ!r}")
            continue

        if question not in vus:
            questions.append(question)
            vus.add(question)

    return questions


def obtenir_questions_depuis_erreurs(erreurs: Sequence[str]) -> list[str]:
    """
    Compat : convertit une liste de messages d'erreur textuels en questions WhatsApp.

    Extrait le nom du champ depuis chaque message d'erreur, puis délègue à
    obtenir_questions_depuis_champs. Les erreurs non reconnues sont loguées.

    Args:
        erreurs: liste de strings retournées par CERFAValidator (ex: validation["erreurs"])

    Returns:
        Liste de questions/messages, dédupliquée.
    """
    champs: list[str] = []
    for erreur in erreurs:
        champ = _champ_depuis_erreur(erreur)
        if champ:
            champs.append(champ)
        else:
            logger.warning(f"[RELANCE] Impossible d'extraire un champ depuis l'erreur : {erreur!r}")

    return obtenir_questions_depuis_champs(champs)


def formuler_message_whatsapp(champs_manquants: Sequence[str]) -> str:
    """
    Retourne UNE SEULE question WhatsApp pour le premier champ manquant.

    Principe FALC : une question à la fois. Ne jamais envoyer une liste numérotée
    à un usager — c'est paralysant pour les publics accompagnés.

    Pour enchaîner les questions, appeler cette fonction après chaque réponse
    reçue (avec la liste de champs encore manquants à jour).

    Args:
        champs_manquants: liste de noms de champs CERFA encore non renseignés.

    Returns:
        La première question non médicale, ou le message de redirection si le
        premier champ manquant est médical, ou chaîne vide si tout est renseigné.
    """
    questions = obtenir_questions_depuis_champs(champs_manquants)
    return questions[0] if questions else ""


def formuler_message_dashboard(champs_manquants: Sequence[str]) -> str:
    """
    Résumé multi-lignes des informations manquantes — RÉSERVÉ À L'INTERFACE ÉDUCATEUR.

    ⚠️  Ne PAS envoyer ce message tel quel via WhatsApp.
        Utiliser formuler_message_whatsapp() pour les envois WhatsApp.

    Args:
        champs_manquants: liste de noms de champs CERFA encore non renseignés.

    Returns:
        Texte formaté pour le dashboard (bullet points numérotés).
    """
    questions = obtenir_questions_depuis_champs(champs_manquants)
    if not questions:
        return "✅ Dossier complet — aucune information manquante."

    lignes = [f"{i + 1}. {q}" for i, q in enumerate(questions)]
    return (
        f"ℹ️  {len(questions)} information(s) manquante(s) :\n\n"
        + "\n".join(lignes)
    )
