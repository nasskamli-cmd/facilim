"""
anonymizer.py — Anonymisation RGPD par LLM.
Remplace toutes les données à caractère personnel (DCP) par des tokens génériques
AVANT toute autre opération de traitement ou de stockage.

Données ciblées :
  - Noms et prénoms
  - Adresses postales complètes
  - Numéros de sécurité sociale (NIR)
  - Numéros de téléphone
  - Adresses e-mail
  - Dates de naissance précises

Le remplacement utilise des tokens séquentiels ([USAGER_A], [ADRESSE_1], etc.)
pour garantir la cohérence entre plusieurs occurrences d'un même élément.

NOTE : Les dossiers annotés avec des numéros (1_ingestion, 4_llm_client…) ne sont pas
des identifiants Python valides. On utilise importlib pour les traverser proprement.
"""

import logging
import re
import importlib

logger = logging.getLogger(__name__)

# Import dynamique depuis le paquet numéroté 4_llm_client
_llm = importlib.import_module("4_llm_client.openai_client")
call_llm = _llm.call_llm

from config import get_settings
settings = get_settings()

# --------------------------------------------------------------------------- #
#  Prompt système — agent d'anonymisation RGPD                                #
# --------------------------------------------------------------------------- #
_ANONYMIZER_SYSTEM_PROMPT = """
Tu es un expert en conformité RGPD spécialisé dans l'anonymisation de dossiers médico-sociaux français.

Ta mission UNIQUE est de remplacer toutes les données à caractère personnel (DCP) dans le texte fourni
par des tokens génériques, selon ces règles strictes :

RÈGLES DE REMPLACEMENT :
- Noms et prénoms                          → [USAGER_A], [USAGER_B], … (séquentiels si plusieurs personnes)
- Adresses complètes (rue, ville, CP)      → [ADRESSE_1], [ADRESSE_2], …
- Numéros de sécurité sociale (NIR)        → [NIR_1]
- Numéros de téléphone                     → [TEL_1], [TEL_2], …
- Adresses e-mail                          → [EMAIL_1]
- Dates de naissance précises              → [DATE_NAISSANCE_1] (garder l'âge ou l'année si pertinent médicalement)
- Noms de médecins / établissements        → [PROFESSIONNEL_1], [ETABLISSEMENT_1]

RÈGLES ABSOLUES :
1. Retourne UNIQUEMENT le texte anonymisé, sans aucun commentaire ni explication.
2. Conserve intégralement la structure, la ponctuation et le sens médical du texte.
3. Ne modifie PAS les informations médicales, diagnostics, codes CIM-10 ou descriptions fonctionnelles.
4. Si une même personne est mentionnée plusieurs fois, utilise TOUJOURS le même token.
5. Si aucune DCP n'est détectée, retourne le texte strictement tel quel.
"""


def anonymize(text: str) -> dict:
    """
    Anonymise un texte en remplaçant les DCP par des tokens RGPD.

    Args:
        text: Texte brut extrait du dossier (post-parsing).

    Returns:
        Dict contenant :
          - "anonymized_text"  : texte avec tokens de remplacement
          - "has_pii_detected" : booléen — DCP trouvées ou non
          - "token_count"      : nombre de tokens de remplacement insérés

    Raises:
        RuntimeError: Si l'appel LLM échoue.
    """
    logger.info("Lancement de l'anonymisation RGPD…")

    user_message = (
        "Anonymise le texte suivant en respectant strictement les règles données.\n\n"
        f"TEXTE À ANONYMISER :\n---\n{text}\n---\n\nTEXTE ANONYMISÉ :"
    )

    anonymized_text = call_llm(
        system_prompt=_ANONYMIZER_SYSTEM_PROMPT,
        user_message=user_message,
        model=settings.openai_anonymizer_model,
        temperature=0.0,          # Zéro créativité : tâche déterministe critique
        max_tokens=len(text) * 2, # Marge pour les tokens de remplacement plus longs
    )

    # Détection heuristique du nombre de tokens insérés (pour audit et reporting)
    _token_re = re.compile(
        r"\[(USAGER|ADRESSE|NIR|TEL|EMAIL|DATE_NAISSANCE|PROFESSIONNEL|ETABLISSEMENT)_\w+\]"
    )
    tokens_found = _token_re.findall(anonymized_text)
    has_pii = len(tokens_found) > 0

    if has_pii:
        logger.info(f"Anonymisation terminée | {len(tokens_found)} DCP remplacées")
    else:
        logger.info("Anonymisation terminée | Aucune DCP détectée dans ce texte")

    return {
        "anonymized_text": anonymized_text,
        "has_pii_detected": has_pii,
        "token_count": len(tokens_found),
    }
