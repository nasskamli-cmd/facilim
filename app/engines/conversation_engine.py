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


# ── Checklist MDPH obligatoire (16 champs) ────────────────────────────────────
CHECKLIST_MDPH = [
    {"id": "nom_prenom",        "label": "Nom et prénom",                    "requis": True},
    {"id": "date_naissance",    "label": "Date de naissance (JJ/MM/AAAA)",   "requis": True},
    {"id": "genre",             "label": "Genre (homme/femme)",               "requis": True},
    {"id": "adresse_complete",  "label": "Adresse complète",                  "requis": True},
    {"id": "num_secu",          "label": "Numéro de Sécurité Sociale",        "requis": True},
    {"id": "telephone",         "label": "Numéro de téléphone de contact",    "requis": True},
    {"id": "departement",       "label": "Département MDPH",                  "requis": True},
    {"id": "situation_familiale","label": "Situation familiale",               "requis": True},
    {"id": "enfants_a_charge",  "label": "Nombre d'enfants à charge",         "requis": True},
    {"id": "types_demande",     "label": "Types de demandes MDPH",            "requis": True},
    {"id": "diagnostics",       "label": "Diagnostic(s) précis",              "requis": True},
    {"id": "traitements",       "label": "Traitements médicaux en cours",     "requis": True},
    {"id": "medecin_traitant",  "label": "Médecin traitant (nom et ville)",   "requis": True},
    {"id": "impact_quotidien",  "label": "Impact sur la vie quotidienne",     "requis": True},
    {"id": "situation_scol_pro","label": "Situation scolaire ou professionnelle", "requis": True},
    {"id": "historique_mdph",   "label": "Historique MDPH",                   "requis": True},
]

CHECKLIST_IDS = {item["id"] for item in CHECKLIST_MDPH}


# ── Système de prompts ────────────────────────────────────────────────────────

def _build_system_prompt(
    etat: str,
    donnees_collectees: dict[str, Any],
    elements_manquants: list[str],
    is_mineur: bool = False,
) -> str:
    """Construit le prompt système adapté à l'état conversationnel."""
    sujet = "de l'enfant" if is_mineur else "de la personne"
    interlocuteur = "la famille" if is_mineur else "la personne ou son représentant"

    base = f"""Tu es l'Assistant Facilim, spécialisé dans la constitution de dossiers MDPH en France.
Tu discutes avec {interlocuteur} via WhatsApp.

RÈGLES ABSOLUES :
- Réponds toujours en français, de manière chaleureuse et simple (niveau FALC)
- Tu es UN SEUL interlocuteur : l'Assistant Facilim
- Pose UNE SEULE question à la fois
- Accuse réception avant de poser la prochaine question
- Si adulte : vouvoiement, parle de la personne elle-même, jamais "votre enfant"
- N'invente JAMAIS d'informations
- Tous les champs de la checklist sont OBLIGATOIRES sans exception
- Ne déclare jamais le dossier complet s'il manque un seul élément
- Maximum 3 phrases par message
- Signature optionnelle : "L'équipe Facilim"

CONTEXTE : Dossier MDPH {sujet}
"""

    if etat == ConversationState.CONSENT:
        base += "\nÉTAT : Tu attends la confirmation de consentement de l'usager (OUI/NON)."

    elif etat == ConversationState.COLLECTE:
        if donnees_collectees:
            collecte_str = "\n".join(f"  ✓ {k}: {v}" for k, v in donnees_collectees.items() if v)
            base += f"\nINFORMATIONS DÉJÀ COLLECTÉES :\n{collecte_str}\n"
        if elements_manquants:
            manquants_str = "\n".join(f"  ✗ {m}" for m in elements_manquants[:5])
            base += f"\nINFORMATIONS ENCORE MANQUANTES (priorité) :\n{manquants_str}\n"
        else:
            base += "\nTOUTES LES INFORMATIONS SONT COLLECTÉES. Confirme et annonce la suite.\n"

    elif etat == ConversationState.DOCUMENTS:
        base += "\nÉTAT : Tu attends les pièces justificatives (certificat médical, etc.). Demande-les poliment."

    elif etat == ConversationState.CLOTURE:
        base += "\nÉTAT : Le dossier est complet. Félicite l'usager et explique les prochaines étapes."

    return base


def generate_response(
    message_entrant: str,
    historique: list[dict],
    etat: str,
    donnees_collectees: dict[str, Any],
    elements_manquants: list[str],
    openai_client: Any,
    is_mineur: bool = False,
    model: str = "gpt-4o-mini",
) -> str:
    """
    Génère la réponse de l'assistant à un message entrant.

    Returns:
        str: Message à envoyer à l'usager
    """
    try:
        system_prompt = _build_system_prompt(
            etat, donnees_collectees, elements_manquants, is_mineur
        )

        messages = [{"role": "system", "content": system_prompt}]

        # Historique limité (évite dépassement de contexte)
        for msg in historique[-12:]:
            role    = msg.get("role", "user")
            content = msg.get("content") or msg.get("reponse") or ""
            if content and role in ("user", "assistant"):
                messages.append({"role": role, "content": str(content)[:500]})

        messages.append({"role": "user", "content": message_entrant})

        response = openai_client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=250,
            temperature=0.5,
        )

        reponse = response.choices[0].message.content.strip()
        logger.info(f"[CONV] Réponse générée | état={etat} | {len(reponse)} chars")
        return reponse

    except Exception as e:
        logger.error(f"[CONV] Erreur LLM : {e}")
        if elements_manquants:
            return (
                f"Merci pour votre réponse. "
                f"Pourriez-vous me préciser : {elements_manquants[0]} ?"
            )
        return (
            "Merci, nous avons bien noté vos informations. "
            "Votre dossier est en cours de traitement. — L'équipe Facilim"
        )


def detect_missing_fields(donnees: dict[str, Any]) -> list[str]:
    """Retourne les libellés des champs manquants dans la checklist."""
    missing = []
    for item in CHECKLIST_MDPH:
        if not donnees.get(item["id"]):
            missing.append(item["label"])
    return missing


def extract_structured_data_from_history(
    historique: list[dict],
    openai_client: Any,
    model: str = "gpt-4o-mini",
) -> dict[str, Any]:
    """
    Extrait les données structurées de l'historique conversationnel.
    Utilisé pour mettre à jour le dossier après chaque échange.
    """
    if not historique:
        return {}

    conversation_text = "\n".join(
        f"{'Usager' if m.get('role') == 'user' else 'Assistant'}: {m.get('content', '')}"
        for m in historique[-20:]
    )

    prompt = f"""Analyse cette conversation et extrait les informations MDPH collectées.
Retourne UNIQUEMENT un JSON valide avec les champs trouvés parmi :
nom_prenom, date_naissance, genre, adresse_complete, num_secu, telephone,
departement, situation_familiale, enfants_a_charge, types_demande,
diagnostics, traitements, medecin_traitant, impact_quotidien,
situation_scol_pro, historique_mdph

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
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"[CONV] Extraction données échouée : {e}")
        return {}
