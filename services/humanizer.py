"""
humanizer.py — Post-traitement de la recommandation finale pour effacer
les marqueurs d'écriture IA et produire un texte professionnel naturel.

Appliqué sur la recommandation_finale avant génération du PDF dossier.
Fail silencieux : si l'API est indisponible, le texte original est conservé.
"""

import logging
from openai import OpenAI
from config import get_settings

logger   = logging.getLogger(__name__)
settings = get_settings()

_SYSTEM_PROMPT = """\
Tu es un expert en rédaction administrative française, spécialisé dans les dossiers MDPH.
Ta mission : réécrire le texte fourni pour qu'il sonne comme la plume d'un travailleur social
expérimenté — pas comme un rapport généré automatiquement.

Directives stylistiques :
- Supprime les connecteurs mécaniques : "De plus", "En outre", "Par ailleurs", "Il convient de noter", "À cet égard"
- Évite les structures en trois points systématiques
- Varie les longueurs de phrases : alterne phrases longues et phrases courtes, parfois nominales
- Remplace les termes creux ("important", "essentiel", "crucial", "significatif", "il est à noter") par des formulations concrètes
- Supprime les tirets em (—) excessifs ; préfère la virgule ou le point
- Évite le mot "notamment" utilisé en début de proposition
- Pas de formulation "il apparaît que" ou "force est de constater"
- Registre soutenu mais direct, adapté à un courrier administratif MDPH

Contraintes absolues :
- Préserve TOUS les faits, droits identifiés, montants, diagnostics et éléments concrets
- Ne supprime aucune information substantielle — reformule uniquement
- Longueur finale proche de l'original
- Réponds UNIQUEMENT avec le texte réécrit, sans introduction ni commentaire
"""


def humaniser_texte(texte: str) -> str:
    """
    Passe le texte par GPT-4o pour supprimer les patterns d'écriture IA.

    Args:
        texte : Texte brut généré par le moteur d'analyse CNSA.

    Returns:
        Texte humanisé, ou texte original en cas d'échec (fail silencieux).
    """
    if not texte or len(texte.strip()) < 20:
        return texte

    try:
        client = OpenAI(api_key=settings.openai_api_key)

        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": texte},
            ],
            temperature=0.65,
            max_tokens=1500,
        )

        result = response.choices[0].message.content.strip()
        logger.info(f"Humanisation OK | {len(texte)} → {len(result)} caractères")
        return result

    except Exception as exc:
        logger.warning(f"Humanisation échouée (texte original conservé) : {exc}")
        return texte
