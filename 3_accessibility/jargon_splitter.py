"""
jargon_splitter.py — Traducteur FALC (Facile À Lire et à Comprendre).
Transforme les questions expertes générées par les agents CNSA
en questions simples, bienveillantes et compréhensibles pour les usagers et leurs familles.

Le format FALC est un standard européen (EN 301 549) visant à rendre
l'information accessible aux personnes ayant des difficultés cognitives,
des troubles DYS, un faible niveau de littératie, ou des difficultés linguistiques.

Principes FALC appliqués :
  - Phrases courtes (< 15 mots)
  - Un seul concept par phrase
  - Vocabulaire courant et positif
  - Absence de jargon administratif ou médical
  - Ton chaleureux et rassurant
"""

import logging
import importlib

logger = logging.getLogger(__name__)

# Import dynamique depuis le paquet numéroté 4_llm_client
_llm = importlib.import_module("4_llm_client.openai_client")
call_llm = _llm.call_llm

# --------------------------------------------------------------------------- #
#  Prompt système — agent de traduction FALC                                  #
# --------------------------------------------------------------------------- #
_FALC_SYSTEM_PROMPT_ENFANT = """
Tu es un spécialiste de la communication inclusive et du format FALC (Facile À Lire et à Comprendre).
Tu travailles pour une plateforme d'aide aux familles qui constituent des dossiers MDPH pour un ENFANT.

Ton rôle est de transformer des questions administratives complexes en questions simples,
claires et bienveillantes pour les familles.

RÈGLES FALC STRICTES :
1. Phrases très courtes (maximum 12-15 mots par phrase).
2. Un seul concept ou une seule question par item.
3. Utilise des mots du quotidien. Jamais de jargon médical ou administratif.
4. Commence toujours par un mot positif et rassurant si possible.
5. Pose la question de façon directe et bienveillante.
6. Si une question complexe contient plusieurs sous-questions, sépare-les en items distincts.
7. Évite les négations doubles, le subjonctif complexe, les phrases passives.
8. Parle de "votre enfant", "il" ou "elle" selon le contexte.

EXEMPLES DE TRANSFORMATION (enfant) :
❌ "Quelles limitations fonctionnelles affectent les capacités d'autonomie dans les actes essentiels de la vie quotidienne ?"
✅ "Pour faire sa toilette, votre enfant a-t-il besoin d'aide ?"

❌ "Existe-t-il des troubles de la déglutition nécessitant une adaptation texturale des aliments ?"
✅ "A-t-il du mal à avaler les aliments ?"

❌ "Les transferts lit/fauteuil nécessitent-ils une assistance humaine ?"
✅ "Pour se lever ou s'asseoir, a-t-il besoin que quelqu'un l'aide ?"

FORMAT DE RÉPONSE :
Retourne UNIQUEMENT une liste JSON de questions FALC, sans aucun autre texte.
Exemple : ["Question simple 1 ?", "Question simple 2 ?", "Question simple 3 ?"]
"""

_FALC_SYSTEM_PROMPT_ADULTE = """
Tu es un spécialiste de la communication inclusive et du format FALC (Facile À Lire et à Comprendre).
Tu travailles pour une plateforme d'aide aux personnes adultes en situation de handicap qui constituent leur dossier MDPH.

Ton rôle est de transformer des questions administratives complexes en questions simples,
claires et bienveillantes, directement adressées à la personne concernée.

RÈGLES FALC STRICTES :
1. Phrases très courtes (maximum 12-15 mots par phrase).
2. Un seul concept ou une seule question par item.
3. Utilise des mots du quotidien. Jamais de jargon médical ou administratif.
4. Commence toujours par un mot positif et rassurant si possible.
5. Pose la question de façon directe et bienveillante en utilisant "vous".
6. Si une question complexe contient plusieurs sous-questions, sépare-les en items distincts.
7. Évite les négations doubles, le subjonctif complexe, les phrases passives.
8. JAMAIS "votre enfant" — parle directement à la personne avec "vous", "votre".

EXEMPLES DE TRANSFORMATION (adulte) :
❌ "Quelles limitations fonctionnelles affectent les capacités d'autonomie dans les actes essentiels de la vie quotidienne ?"
✅ "Pour faire votre toilette, avez-vous besoin d'aide ?"

❌ "Existe-t-il des troubles de la déglutition nécessitant une adaptation texturale des aliments ?"
✅ "Avez-vous du mal à avaler les aliments ?"

❌ "Les transferts lit/fauteuil nécessitent-ils une assistance humaine ?"
✅ "Pour vous lever ou vous asseoir, avez-vous besoin d'aide ?"

FORMAT DE RÉPONSE :
Retourne UNIQUEMENT une liste JSON de questions FALC, sans aucun autre texte.
Exemple : ["Question simple 1 ?", "Question simple 2 ?", "Question simple 3 ?"]
"""


def simplify_questions(expert_questions: list[str], is_enfant: bool = True) -> list[str]:
    """
    Transforme une liste de questions expertes en questions FALC.

    Args:
        expert_questions: Questions techniques générées par les agents CNSA.
        is_enfant: True si le dossier concerne un enfant, False pour un adulte.
                   Adapte le registre (vous/votre enfant) en conséquence.

    Returns:
        Liste de questions reformulées en langage simple et accessible.
        En cas d'erreur, retourne les questions originales (fallback gracieux).
    """
    if not expert_questions:
        logger.warning("jargon_splitter : aucune question reçue, rien à simplifier.")
        return []

    falc_prompt = _FALC_SYSTEM_PROMPT_ENFANT if is_enfant else _FALC_SYSTEM_PROMPT_ADULTE
    logger.info(f"Simplification FALC de {len(expert_questions)} question(s) | registre={'enfant' if is_enfant else 'adulte'}")

    # Formatage des questions pour le LLM
    questions_formatted = "\n".join(f"{i+1}. {q}" for i, q in enumerate(expert_questions))

    user_message = (
        "Transforme les questions expertes suivantes en questions FALC simples et bienveillantes.\n\n"
        f"QUESTIONS EXPERTES :\n{questions_formatted}\n\n"
        "QUESTIONS FALC (format JSON list) :"
    )

    try:
        raw_response = call_llm(
            system_prompt=falc_prompt,
            user_message=user_message,
            temperature=0.3,  # Légère créativité pour un ton naturel et chaleureux
            max_tokens=1024,
        )

        # Nettoyage des balises markdown éventuelles
        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            parts = cleaned.split("```")
            cleaned = parts[1] if len(parts) > 1 else cleaned
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()

        import json
        falc_questions = json.loads(cleaned)

        if not isinstance(falc_questions, list):
            raise ValueError("La réponse LLM n'est pas une liste JSON.")

        # Nettoyage final : suppression des éléments vides ou non-strings
        falc_questions = [str(q).strip() for q in falc_questions if q and str(q).strip()]

        logger.info(f"Simplification FALC terminée | {len(falc_questions)} question(s) produites")
        return falc_questions

    except Exception as e:
        # Fallback gracieux : on retourne les questions originales plutôt que de bloquer le workflow
        logger.error(f"Erreur lors de la simplification FALC : {e}. Retour aux questions originales.")
        return expert_questions


def translate_to_language(falc_questions: list[str], target_language: str) -> list[str]:
    """
    Traduit une liste de questions FALC vers la langue de la famille.
    Si la langue cible est le français, retourne les questions sans appel API.

    Args:
        falc_questions  : Questions déjà simplifiées en FALC (en français).
        target_language : Code ISO 639-1 de la langue cible (ex: "ar", "en", "tr").

    Returns:
        Liste de questions traduites dans la langue cible,
        en conservant le registre simple et bienveillant du FALC.
    """
    if not falc_questions:
        return []

    # Si la famille parle français, rien à traduire
    if target_language in ("fr", "french", None, ""):
        return falc_questions

    logger.info(f"Traduction FALC vers '{target_language}' | {len(falc_questions)} question(s)…")

    questions_formatted = "\n".join(f"{i+1}. {q}" for i, q in enumerate(falc_questions))

    system_prompt = (
        f"Tu es un traducteur spécialisé dans la communication simple et bienveillante. "
        f"Traduis les questions suivantes en '{target_language}'. "
        f"Ces questions sont destinées à des familles qui peuvent avoir un faible niveau de littératie. "
        f"Conserve impérativement : phrases courtes, vocabulaire simple, ton chaleureux. "
        f"Retourne UNIQUEMENT une liste JSON de questions traduites, sans aucun autre texte. "
        f"Exemple : [\"Question traduite 1 ?\", \"Question traduite 2 ?\"]"
    )

    user_message = (
        f"Traduis ces questions en '{target_language}' :\n\n"
        f"{questions_formatted}\n\n"
        f"Questions traduites (format JSON list) :"
    )

    try:
        raw_response = call_llm(
            system_prompt=system_prompt,
            user_message=user_message,
            temperature=0.2,
            max_tokens=1024,
        )

        # Nettoyage des balises markdown éventuelles
        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            parts = cleaned.split("```")
            cleaned = parts[1] if len(parts) > 1 else cleaned
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()

        import json
        translated = json.loads(cleaned)

        if not isinstance(translated, list):
            raise ValueError("La réponse LLM n'est pas une liste JSON.")

        translated = [str(q).strip() for q in translated if q and str(q).strip()]
        logger.info(f"Traduction terminée | {len(translated)} question(s) produites")
        return translated

    except Exception as e:
        # Fallback : on envoie les questions en français plutôt que de bloquer
        logger.error(f"Erreur traduction vers '{target_language}' : {e}. Retour au français.")
        return falc_questions


def format_for_whatsapp(falc_questions: list[str]) -> list[dict]:
    """
    Formate les questions FALC pour l'envoi WhatsApp.
    Détermine automatiquement si la question nécessite des boutons (oui/non)
    ou une réponse texte libre.

    Args:
        falc_questions: Liste de questions en format FALC.

    Returns:
        Liste de dicts avec les champs : "question", "type", "options".
        - type = "button" : question fermée (oui/non/parfois)
        - type = "text"   : question ouverte (réponse libre)
    """
    formatted = []

    # Mots-clés indiquant une question fermée (réponse oui/non)
    _oui_non_triggers = ["a-t-il", "a-t-elle", "peut-il", "peut-elle", "est-ce", "y a-t-il", "est-il", "est-elle"]

    for question in falc_questions:
        question_lower = question.lower()
        is_closed = any(trigger in question_lower for trigger in _oui_non_triggers)

        if is_closed:
            formatted.append({
                "question": question,
                "type": "button",
                "options": ["Oui", "Non", "Parfois"],
            })
        else:
            formatted.append({
                "question": question,
                "type": "text",
                "options": [],
            })

    return formatted
