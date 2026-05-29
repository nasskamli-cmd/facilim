"""
cnsa_validator.py — Armée d'agents CNSA : audit, scoring et détection d'incomplétude.

Orchestration :
  1. Construction du prompt contextualisé (via prompt_builder)
  2. Appel LLM multi-agent (Expert CNSA, Juriste, Coordinateur local)
  3. Parsing de la réponse JSON
  4. Décision : COMPLET → pipeline continue | INCOMPLET → questions ciblées générées

Les "actes essentiels" (AVQ) constituent le seuil bloquant :
si le dossier ne documente pas au minimum 2 actes essentiels impactés,
le statut passe à INCOMPLET et le workflow WhatsApp est déclenché.
"""

import json
import logging
import importlib
from typing import Any

logger = logging.getLogger(__name__)

# Imports dynamiques pour contourner les noms de dossiers numérotés
_llm = importlib.import_module("4_llm_client.openai_client")
_pb  = importlib.import_module("2_intelligence.prompt_builder")

call_llm            = _llm.call_llm
build_analysis_prompt = _pb.build_analysis_prompt

# Indicateurs fonctionnels couvrant ADL classiques ET bilans adultes ESSMS.
# Élargi pour les cas accident du travail, handicap psychique, pathologies chroniques.
ACTES_ESSENTIELS_REQUIS = [
    # AVQ classiques
    "hygiène", "toilette", "repas", "alimentation", "habillage",
    "déplacement", "mobilité", "transfert", "continence", "communication", "sécurité",
    # Médicaments / traitements
    "médicament", "traitement", "ordonnance", "prescription",
    # Douleur et limitations physiques
    "douleur", "douloureux", "fatigabilité", "fatigue", "épuisement",
    "marche", "station debout", "debout", "déambulation",
    "port de charges", "effort physique", "limitation", "restriction",
    # Santé mentale
    "anxiété", "anxieux", "angoisse", "traumatisme", "traumatique",
    "dépression", "dépressif", "psychiatrique", "psychologique",
    "sommeil", "insomnie",
    # Accidents et parcours médical
    "accident", "hospitalisation", "rééducation", "kinésithérapie",
    # Autonomie
    "autonomie", "dépendance", "aide humaine", "aidant", "accompagnement",
    # Scolarité / insertion
    "scolarité", "scolaire", "apprentissage", "formation", "emploi",
]

# Seuil abaissé à 1 : avec la liste élargie, tous les vrais bilans ESSMS
# passent à l'analyse LLM complète plutôt que d'être bloqués par l'heuristique.
_SEUIL_ACTES_ESSENTIELS = 1


def _detect_actes_essentiels(text: str) -> list[str]:
    """
    Détection heuristique des actes essentiels présents dans le texte.
    Complétée ensuite par l'analyse LLM — cette passe rapide sert de garde-fou.
    """
    text_lower = text.lower()
    return [acte for acte in ACTES_ESSENTIELS_REQUIS if acte in text_lower]


def _parse_llm_json(raw_response: str) -> dict[str, Any]:
    """
    Extrait et parse le JSON retourné par le LLM.
    Gère trois cas de défense :
      1. Blocs markdown  (```json … ```)
      2. Préfixe textuel (le LLM ajoute une phrase avant le JSON)
      3. Troncature      (max_tokens atteint avant la fermeture du JSON)
    """
    cleaned = raw_response.strip()

    # Cas 1 : blocs markdown
    if "```" in cleaned:
        parts = cleaned.split("```")
        for part in parts:
            candidate = part.lstrip("json").strip()
            if candidate.startswith("{"):
                cleaned = candidate
                break

    # Cas 2 : préfixe textuel — extraire depuis le premier '{' jusqu'au dernier '}'
    start = cleaned.find("{")
    end   = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        # Log étendu pour diagnostiquer : début + fin de la réponse brute
        _preview_start = raw_response[:400]
        _preview_end   = raw_response[-200:] if len(raw_response) > 400 else ""
        logger.error(
            f"Échec du parsing JSON LLM : {e}\n"
            f"Longueur réponse : {len(raw_response)} chars\n"
            f"Début : {_preview_start!r}\n"
            f"Fin   : {_preview_end!r}"
        )
        # Réponse de secours : dossier marqué incomplet pour forcer une révision manuelle
        return {
            "statut": "INCOMPLET",
            "score_global": 0,
            "elements_probants": [],
            "elements_manquants": ["Impossible de parser la réponse du moteur d'analyse."],
            "droits_identifies": [],
            "questions_manquantes": [
                "Pouvez-vous fournir un résumé plus détaillé de la situation de la personne ?",
                "Quels sont les actes de la vie quotidienne qui posent le plus de difficultés ?",
            ],
            "synthese_agents": {
                "geva_pro": "Analyse impossible — format de réponse invalide.",
                "juriste": "Analyse impossible.",
                "coordinateur_local": "Analyse impossible.",
            },
            "recommandation_finale": "Révision manuelle du dossier requise avant toute soumission.",
        }


def validate_dossier(anonymized_text: str, departement_code: str) -> dict[str, Any]:
    """
    Orchestre l'analyse complète d'un dossier par l'armée d'agents.

    Étapes :
      1. Vérification heuristique rapide des actes essentiels (seuil bloquant)
      2. Appel LLM multi-agent pour l'audit complet
      3. Décision finale : COMPLET ou INCOMPLET

    Args:
        anonymized_text:   Texte anonymisé du dossier.
        departement_code:  Code du département MDPH cible.

    Returns:
        Dict d'analyse structuré contenant statut, score, droits, questions, synthèses.
        Champs garantis : statut, score_global, questions_manquantes, droits_identifies.
    """
    logger.info(f"Démarrage validation CNSA | département={departement_code}")

    # --- Garde-fou 1 : vérification heuristique des actes essentiels ---
    actes_detectes = _detect_actes_essentiels(anonymized_text)
    logger.info(f"Actes essentiels détectés (heuristique) : {actes_detectes}")

    if len(actes_detectes) < _SEUIL_ACTES_ESSENTIELS:
        # Blocage immédiat sans appel LLM : économie de tokens et réponse rapide
        logger.warning(
            f"Blocage heuristique : seulement {len(actes_detectes)} acte(s) essentiel(s) détecté(s) "
            f"(minimum requis : {_SEUIL_ACTES_ESSENTIELS})"
        )
        return {
            "statut": "INCOMPLET",
            "score_global": 10,
            "elements_probants": actes_detectes,
            "elements_manquants": [
                a for a in ACTES_ESSENTIELS_REQUIS if a not in actes_detectes
            ],
            "droits_identifies": [],
            "questions_manquantes": _generate_fallback_questions(actes_detectes),
            "synthese_agents": {
                "geva_pro": "Données insuffisantes pour évaluer les domaines GEVA.",
                "juriste": "Aucun droit identifiable sans description fonctionnelle minimale.",
                "coordinateur_local": "Le dossier ne satisfait pas les critères minimaux de complétude.",
            },
            "recommandation_finale": (
                "Contacter la famille via WhatsApp pour recueillir les informations manquantes "
                "sur les actes essentiels de la vie quotidienne."
            ),
            "_source": "heuristique",  # Méta-donnée interne pour le dashboard
        }

    # --- Troncature de sécurité : limite le texte à ~12 000 caractères --------
    # Un texte plus long dépasse les limites de contexte du modèle.
    # Les informations essentielles se trouvent généralement dans les premières pages.
    _LIMITE_CHARS = 12_000
    if len(anonymized_text) > _LIMITE_CHARS:
        logger.warning(
            f"Texte tronqué : {len(anonymized_text)} → {_LIMITE_CHARS} caractères "
            f"(document trop long pour une analyse complète en une passe)"
        )
        anonymized_text = anonymized_text[:_LIMITE_CHARS]

    # --- Appel LLM : analyse complète par les trois agents ---
    prompt_data = build_analysis_prompt(anonymized_text, departement_code)

    raw_response = call_llm(
        system_prompt=prompt_data["system_prompt"],
        user_message=prompt_data["user_prompt"],
        temperature=0.1,   # Légère créativité pour les recommandations, mais analyse rigoureuse
        max_tokens=6000,   # FACILIM_MDPH_ENGINE v2 génère ~3 500-5 000 tokens (donnees_structurees + scoring)
    )

    analysis = _parse_llm_json(raw_response)
    analysis["_source"] = "llm"
    analysis["_mdph_profile"] = prompt_data["mdph_profile"]["nom"]

    # --- Validation de cohérence post-LLM ---
    # Règle 1 : COMPLET exige un score ≥ 60/100
    _SCORE_MIN_COMPLET = 60
    if analysis.get("statut") == "COMPLET" and analysis.get("score_global", 0) < _SCORE_MIN_COMPLET:
        logger.warning(
            f"Score insuffisant ({analysis.get('score_global')}/100 < {_SCORE_MIN_COMPLET}) "
            f"→ correction COMPLET → INCOMPLET"
        )
        analysis["statut"] = "INCOMPLET"
        analysis["elements_manquants"] = analysis.get("elements_manquants", []) + [
            f"Dossier insuffisamment documenté (score {analysis.get('score_global')}/100). "
            "Des précisions supplémentaires sont nécessaires."
        ]

    # Règle 2 : COMPLET sans aucun droit identifié → force INCOMPLET
    if analysis.get("statut") == "COMPLET" and not analysis.get("droits_identifies"):
        logger.warning("Incohérence LLM : statut COMPLET mais aucun droit identifié → correction à INCOMPLET")
        analysis["statut"] = "INCOMPLET"
        analysis["elements_manquants"] = analysis.get("elements_manquants", []) + [
            "Aucun droit identifiable : le profil fonctionnel est trop peu détaillé."
        ]

    statut = analysis.get("statut", "INCOMPLET")
    score  = analysis.get("score_global", 0)
    logger.info(f"Validation terminée | statut={statut} | score={score}/100")

    return analysis


def _generate_fallback_questions(actes_detectes: list[str]) -> list[str]:
    """
    Génère une liste de questions expertes de secours quand l'heuristique bloque
    avant même l'appel LLM. Couvre les actes non détectés.
    """
    questions = []
    actes_manquants = [a for a in ACTES_ESSENTIELS_REQUIS if a not in actes_detectes]

    mapping = {
        "hygiène":       "Pouvez-vous décrire les difficultés rencontrées pour la toilette et l'hygiène personnelle ?",
        "toilette":      "La personne peut-elle effectuer sa toilette seule, partiellement ou nécessite-t-elle une aide totale ?",
        "repas":         "Quelles difficultés la personne rencontre-t-elle pour préparer ou prendre ses repas ?",
        "alimentation":  "Y a-t-il des troubles de la déglutition ou des besoins d'aide à l'alimentation ?",
        "habillage":     "La personne peut-elle s'habiller et se déshabiller de manière autonome ?",
        "déplacement":   "Quels sont les modes de déplacement utilisés (fauteuil, canne, aide humaine) ?",
        "mobilité":      "La personne peut-elle se lever, s'asseoir et se déplacer seule dans son logement ?",
        "transfert":     "Des aides techniques ou humaines sont-elles nécessaires pour les transferts (lit/fauteuil) ?",
        "continence":    "Y a-t-il des troubles de la continence urinaire ou fécale ?",
        "médicament":    "La personne peut-elle gérer la prise de ses médicaments de manière autonome ?",
        "communication": "La personne a-t-elle des difficultés à communiquer oralement ou à comprendre les consignes ?",
        "sécurité":      "Existe-t-il des risques pour la sécurité de la personne au domicile (chutes, fugues, oublis) ?",
    }

    for acte in actes_manquants[:5]:  # Limite à 5 questions pour ne pas surcharger l'usager
        if acte in mapping:
            questions.append(mapping[acte])

    return questions or [
        "Pouvez-vous décrire en détail les difficultés rencontrées au quotidien par la personne ?",
        "Quelles activités de la vie quotidienne nécessitent une aide extérieure ?",
    ]
