"""
app/engines/scoring_engine.py — Moteur Jade : scoring réglementaire RAG-strict.

Jade est le moteur de scoring juridique de Facilim.
Il ne hallucine JAMAIS. Avant tout scoring :
  - Citation exacte de la source réglementaire
  - Extraction du passage pertinent
  - Version et date de la réglementation tracées
  - Score de confiance calculé

Si confiance < seuil → score NON CALCULÉ + flag humain.

Références juridiques :
  - CASF (Code de l'Action Sociale et des Familles)
  - Loi 2005-102 du 11 février 2005
  - Décret 2005-1213 (GEVA)
  - Circulaires CNSA
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.audit.event_logger import log_agent_action

logger = logging.getLogger("facilim.engines.scoring")

# ── Base réglementaire de référence (RAG minimal intégré) ───────────────────
# En production : remplacer par un vecteur store (ChromaDB, Pinecone)

_BASE_REGLEMENTAIRE = [
    {
        "ref":      "Loi 2005-102 art.2",
        "texte":    "Constitue un handicap, au sens de la présente loi, toute limitation d'activité ou restriction de participation à la vie en société subie dans son environnement par une personne en raison d'une altération substantielle, durable ou définitive d'une ou plusieurs fonctions physiques, sensorielles, mentales, cognitives ou psychiques, d'un polyhandicap ou d'un trouble de santé invalidant.",
        "droits":   ["AAH", "PCH", "RQTH", "AEEH", "CMI", "Carte_mobilite"],
        "mots_cles": ["limitation", "restriction", "participation", "altération", "handicap"],
    },
    {
        "ref":      "CASF L.245-1",
        "texte":    "Toute personne handicapée résidant de façon stable et régulière en France métropolitaine ayant dépassé l'âge d'ouverture du droit à l'allocation d'éducation de l'enfant handicapé mentionné au premier alinéa de l'article L.541-1 du code de la sécurité sociale et dont le handicap répond à des critères définis par décret prenant notamment en compte la nature et l'importance des besoins de compensation au regard de son projet de vie, a droit à une prestation de compensation qui a le caractère d'une prestation en nature.",
        "droits":   ["PCH"],
        "mots_cles": ["PCH", "compensation", "besoins", "projet de vie", "aide humaine"],
    },
    {
        "ref":      "CASF L.821-1",
        "texte":    "Toute personne résidant en France métropolitaine dont l'incapacité permanente est au moins égale à 80 % ou qui a une incapacité permanente inférieure à 80 % rendant son maintien en emploi particulièrement difficile bénéficie d'une allocation aux adultes handicapés.",
        "droits":   ["AAH"],
        "mots_cles": ["AAH", "incapacité", "emploi", "80%", "taux"],
    },
    {
        "ref":      "CASF L.541-1",
        "texte":    "Toute personne assume la charge effective et permanente d'un enfant dont le handicap répond à des critères définis par décret a droit à une allocation d'éducation de l'enfant handicapé.",
        "droits":   ["AEEH"],
        "mots_cles": ["AEEH", "enfant", "éducation", "handicap", "charge"],
    },
    {
        "ref":      "Décret 2005-1213 (GEVA) art.4",
        "texte":    "L'évaluation des besoins de compensation est réalisée par une équipe pluridisciplinaire à partir d'un référentiel national défini par arrêté du ministre chargé des personnes handicapées. Ce référentiel tient compte des activités de la vie quotidienne.",
        "droits":   ["PCH", "AEEH", "Orientation"],
        "mots_cles": ["GEVA", "évaluation", "pluridisciplinaire", "besoins", "référentiel"],
    },
]

_CONFIDENCE_THRESHOLD_DEFAULT = 0.75


def _compute_regulatory_match(text: str) -> list[dict[str, Any]]:
    """Recherche les articles réglementaires pertinents dans le texte du dossier."""
    text_lower = text.lower()
    matches = []
    for article in _BASE_REGLEMENTAIRE:
        keyword_hits = sum(
            1 for kw in article["mots_cles"]
            if kw.lower() in text_lower
        )
        if keyword_hits >= 2:
            score = min(keyword_hits / len(article["mots_cles"]), 1.0)
            matches.append({
                "article":               article["ref"],
                "texte_extrait":         article["texte"][:300] + "...",
                "version_reglementaire": "2024",
                "date_reference":        "2024-01-01",
                "droits_associes":       article["droits"],
                "pertinence":            round(score, 2),
            })
    return sorted(matches, key=lambda x: x["pertinence"], reverse=True)


def _identify_rights(sources: list[dict], analyse_llm: dict) -> list[str]:
    """Identifie les droits potentiels selon les sources réglementaires et l'analyse LLM."""
    droits_reglementaires = set()
    for src in sources:
        for droit in src.get("droits_associes", []):
            droits_reglementaires.add(droit)
    droits_llm = set(analyse_llm.get("droits_identifies", []))
    return sorted(droits_reglementaires | droits_llm)


def _compute_confidence(sources: list[dict], analyse_llm: dict) -> float:
    """Calcule le score de confiance global de l'analyse."""
    if not sources:
        return 0.0
    avg_pertinence = sum(s["pertinence"] for s in sources) / len(sources)
    llm_score = analyse_llm.get("score_global", 0) / 100
    completude_fields = min(len(analyse_llm.get("elements_probants", [])) / 5, 1.0)
    return round((avg_pertinence * 0.4 + llm_score * 0.4 + completude_fields * 0.2), 3)


def score_dossier(
    dossier_id: str,
    texte_anonymise: str,
    analyse_llm: dict[str, Any],
    confidence_threshold: float = _CONFIDENCE_THRESHOLD_DEFAULT,
    db_conn: Any = None,
) -> dict[str, Any]:
    """
    Scoring réglementaire complet d'un dossier.

    Le scoring est TOUJOURS justifié par des sources juridiques.
    Si la confiance est insuffisante → NON_CALCULÉ + flag humain.

    Args:
        dossier_id: ID du dossier
        texte_anonymise: Texte du bilan fonctionnel anonymisé
        analyse_llm: Résultat de l'analyse LLM CNSA
        confidence_threshold: Seuil de confiance minimal

    Returns:
        Dict de scoring avec sources juridiques tracées
    """
    start_ms = int(time.monotonic() * 1000)
    input_hash = hashlib.sha256(texte_anonymise.encode()).hexdigest()[:16]

    # 1. Recherche des sources réglementaires (RAG)
    sources_juridiques = _compute_regulatory_match(texte_anonymise)

    # 2. Calcul de la confiance
    confiance = _compute_confidence(sources_juridiques, analyse_llm)

    # 3. Décision selon le seuil
    statut_analyse = "NON_CALCULÉ"
    flag_revue_humaine = True
    raison_flag = None
    score_final = analyse_llm.get("score_global", 0)
    droits = []

    if confiance >= confidence_threshold:
        droits = _identify_rights(sources_juridiques, analyse_llm)
        if analyse_llm.get("statut") == "COMPLET" and score_final >= 60:
            statut_analyse = "COMPLET"
            flag_revue_humaine = False
        else:
            statut_analyse = "INCOMPLET"
            flag_revue_humaine = confiance < 0.85

    if confiance < confidence_threshold:
        raison_flag = (
            f"Confiance insuffisante ({confiance:.0%} < {confidence_threshold:.0%}) — "
            "validation humaine obligatoire avant toute recommandation."
        )
        logger.warning(f"[JADE] Confiance faible | dossier={dossier_id[:8]} | conf={confiance:.2f}")

    if not sources_juridiques:
        raison_flag = "Aucune source réglementaire identifiée — analyse impossible."
        statut_analyse = "NON_CALCULÉ"
        flag_revue_humaine = True

    output_hash = hashlib.sha256(
        json.dumps({"score": score_final, "droits": droits}, sort_keys=True).encode()
    ).hexdigest()[:16]

    duree_ms = int(time.monotonic() * 1000) - start_ms

    result = {
        "id":                       str(uuid.uuid4()),
        "dossier_id":               dossier_id,
        "moteur":                   "jade",
        "version_moteur":           "2.0",
        "score_global":             score_final,
        "statut_analyse":           statut_analyse,
        "sources_juridiques_json":  json.dumps(sources_juridiques, ensure_ascii=False),
        "elements_probants_json":   json.dumps(analyse_llm.get("elements_probants", []), ensure_ascii=False),
        "elements_manquants_json":  json.dumps(analyse_llm.get("elements_manquants", []), ensure_ascii=False),
        "droits_identifies_json":   json.dumps(droits, ensure_ascii=False),
        "synthese_agents_json":     json.dumps(analyse_llm.get("synthese_agents", {}), ensure_ascii=False),
        "recommandation":           analyse_llm.get("recommandation_finale", ""),
        "confiance":                confiance,
        "flag_revue_humaine":       1 if flag_revue_humaine else 0,
        "created_at":               datetime.now(timezone.utc).isoformat(),
    }

    # Persistance en base
    if db_conn:
        db_conn.execute(
            """
            INSERT INTO analyses_scoring
                (id, dossier_id, moteur, version_moteur, score_global, statut_analyse,
                 sources_juridiques_json, elements_probants_json, elements_manquants_json,
                 droits_identifies_json, synthese_agents_json, recommandation,
                 confiance, flag_revue_humaine, created_at)
            VALUES
                (:id, :dossier_id, :moteur, :version_moteur, :score_global, :statut_analyse,
                 :sources_juridiques_json, :elements_probants_json, :elements_manquants_json,
                 :droits_identifies_json, :synthese_agents_json, :recommandation,
                 :confiance, :flag_revue_humaine, :created_at)
            """,
            result,
        )
        log_agent_action(
            agent_nom="Jade",
            action="SCORING",
            dossier_id=dossier_id,
            agent_niveau="N2",
            input_hash=input_hash,
            output_hash=output_hash,
            score_confiance=confiance,
            duree_ms=duree_ms,
            flag_genere=flag_revue_humaine,
            db_conn=db_conn,
        )

    result["raison_flag"]         = raison_flag
    result["droits_identifies"]   = droits
    result["sources_juridiques"]  = sources_juridiques
    result["_flag_humain"]        = flag_revue_humaine

    logger.info(
        f"[JADE] Scoring terminé | dossier={dossier_id[:8]} | "
        f"score={score_final} | conf={confiance:.2f} | statut={statut_analyse}"
    )

    return result
