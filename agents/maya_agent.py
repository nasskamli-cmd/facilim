"""
agents/maya_agent.py — Maya (Niveau 2 : Scoring prédictif RAG)

Responsabilités :
  - Calcule un score de dossier (0-100) basé sur la base légale MDPH
  - Identifie le score potentiel si la famille ajoute des demandes manquantes
  - Produit une justification réglementaire citant CASF, CSS, Code du travail
  - Utilise une base de connaissances vectorielle locale (JSON) ou Pinecone/Qdrant

La base de connaissances est chargée depuis agents/knowledge_base.json.
En production, remplacer _retriever par un vrai client Pinecone ou Qdrant.
"""
import json
import os
import importlib
from pathlib import Path
from typing import Any

from agents.base_agent import BaseAgent

_BASE_DIR = Path(__file__).parent


# ── Base de connaissances MDPH ────────────────────────────────────────────────

def _charger_base_connaissances() -> list[dict]:
    """Charge la base légale depuis le JSON local."""
    kb_path = _BASE_DIR / "knowledge_base.json"
    if kb_path.exists():
        with open(kb_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return _BASE_LEGALE_DEFAUT


def _retriever_local(query_tags: list[str], kb: list[dict], top_k: int = 5) -> list[dict]:
    """
    Retriever simple par intersection de tags.
    Remplacer par un appel Pinecone/Qdrant en production.
    """
    scores = []
    for chunk in kb:
        tags = set(chunk.get("tags", []))
        intersection = len(tags & set(query_tags))
        if intersection > 0:
            scores.append((intersection, chunk))
    scores.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scores[:top_k]]


# Fallback si knowledge_base.json absent
_BASE_LEGALE_DEFAUT = [
    {
        "id": "aah_taux_80",
        "tags": ["AAH", "taux_incapacite", "80pct", "ressources"],
        "texte": "Art. L821-1 CSS : L'AAH est accordée aux personnes dont le taux d'incapacité est ≥ 80%, sous condition de ressources (plafond ~12 000€/an pour une personne seule).",
        "source": "CSS L821-1",
    },
    {
        "id": "aah_rsdae",
        "tags": ["AAH", "RSDAE", "emploi", "50pct"],
        "texte": "Art. L821-2 CSS : L'AAH peut être accordée pour un taux entre 50% et 79% si la personne présente une RSDAE (restriction substantielle et durable d'accès à l'emploi).",
        "source": "CSS L821-2",
    },
    {
        "id": "pch_criteres",
        "tags": ["PCH", "aide_humaine", "aide_technique", "taux_incapacite"],
        "texte": "Art. L245-1 CASF : La PCH est ouverte aux personnes présentant une difficulté absolue pour au moins 1 activité ou grave pour au moins 2 activités des domaines du GEVA. Le taux d'incapacité doit être ≥ 80%.",
        "source": "CASF L245-1",
    },
    {
        "id": "aeeh_criteres",
        "tags": ["AEEH", "enfant", "taux_incapacite", "scolarité"],
        "texte": "Art. L541-1 CSS : L'AEEH est versée pour les enfants < 20 ans présentant un taux d'incapacité ≥ 80%, ou entre 50% et 79% si l'enfant fréquente un établissement d'éducation spéciale ou reçoit des soins continus.",
        "source": "CSS L541-1",
    },
    {
        "id": "rqth_criteres",
        "tags": ["RQTH", "emploi", "travailleur_handicape"],
        "texte": "Art. L5213-1 Code du travail : La RQTH est reconnue à tout travailleur dont les possibilités d'obtenir ou de conserver un emploi sont effectivement réduites par suite d'une altération d'une ou plusieurs fonctions physique, sensorielle, mentale ou psychique.",
        "source": "Code du travail L5213-1",
    },
    {
        "id": "cmi_criteres",
        "tags": ["CMI", "taux_incapacite", "mobilite"],
        "texte": "Art. L241-3 CASF : La CMI-invalidité est délivrée aux personnes présentant un taux d'incapacité ≥ 80%. La CMI-priorité nécessite une réduction importante et durable des capacités et de l'autonomie. La CMI-stationnement requiert une impossibilité ou une grande difficulté de marche.",
        "source": "CASF L241-3",
    },
    {
        "id": "taux_incapacite_bareme",
        "tags": ["taux_incapacite", "barème", "cotation"],
        "texte": "Guide-barème MDPH : Le taux d'incapacité est coté de 0 à 4 dans chaque domaine (0 = aucune gêne, 4 = gêne totale). Le taux global résulte de l'évaluation pluridisciplinaire. Un taux ≥ 50% est le seuil minimal pour la plupart des droits.",
        "source": "Guide-barème CASF annexe 2-4",
    },
]

_llm = importlib.import_module("4_llm_client.openai_client")
call_llm = _llm.call_llm


class MayaAgent(BaseAgent):
    NOM    = "Maya"
    NIVEAU = "N2"
    ROLE   = "Scoring prédictif RAG"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._kb = _charger_base_connaissances()

    def run(self, dossier: dict[str, Any], **kwargs) -> dict[str, Any]:
        dossier_id  = dossier.get("dossier_id", "—")
        analyse     = dossier.get("analyse", {})
        droits      = analyse.get("droits_identifies", [])
        score_llm   = analyse.get("score_global", 0)

        # ── Récupération des chunks légaux pertinents ────────────────────────
        tags_query = self._extraire_tags(dossier, analyse)
        chunks     = _retriever_local(tags_query, self._kb, top_k=4)
        contexte_rag = "\n\n".join(
            f"[Source: {c['source']}]\n{c['texte']}" for c in chunks
        )

        # ── Prompt de scoring enrichi ─────────────────────────────────────────
        texte_anon  = (
            dossier.get("_texte_anon")
            or analyse.get("_texte_anon")
            or dossier.get("texte_brut", "")
        )
        type_dos    = dossier.get("type_dossier", "adulte")
        droits_str  = ", ".join(droits) if droits else "aucun identifié"

        prompt_user = f"""
Dossier MDPH — type : {type_dos}
Droits identifiés jusqu'ici : {droits_str}
Score LLM initial : {score_llm}/100

=== ÉLÉMENTS DU DOSSIER ===
{texte_anon[:2000] if texte_anon else "(dossier incomplet)"}

=== BASE LÉGALE PERTINENTE (RAG) ===
{contexte_rag}

=== MISSION ===
1. Confirme ou corrige le score actuel (0-100) en te basant UNIQUEMENT sur les textes ci-dessus.
2. Calcule un score potentiel si la famille ajoute une demande AAH, PCH ou AEEH (selon le cas).
3. Donne UNE suggestion concrète et sa justification légale exacte (article + alinéa).
4. Calcule le taux d'incapacité estimé selon le guide-barème (cotation 0-4 par domaine).

Réponds en JSON strict :
{{
  "score_actuel": <int 0-100>,
  "score_potentiel": <int 0-100>,
  "suggestion": "<texte clair pour l'éducateur>",
  "justification": "<base légale exacte>",
  "taux_incapacite_estime": "<ex: 50-79%>",
  "taux_justification": "<domaines impactés et cotation>",
  "sources_utilisees": ["<source1>", ...]
}}
"""

        try:
            reponse_json = call_llm(
                system_prompt=(
                    "Tu es Maya, expert MDPH en scoring prédictif. "
                    "Tu réponds UNIQUEMENT en JSON valide, sans texte autour."
                ),
                user_message=prompt_user,
                model="gpt-4o-mini",
                max_tokens=600,
                temperature=0.1,
            )
            # Nettoyage si le LLM ajoute des backticks
            reponse_json = reponse_json.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            data = json.loads(reponse_json)

            dossier["score_actuel"]        = data.get("score_actuel", score_llm)
            dossier["score_potentiel"]      = data.get("score_potentiel", score_llm)
            dossier["score_suggestion"]     = data.get("suggestion", "")
            dossier["score_justification"]  = data.get("justification", "")
            dossier["taux_incapacite"]      = data.get("taux_incapacite_estime", "")
            dossier["taux_justification"]   = data.get("taux_justification", "")
            dossier["rag_sources"]          = data.get("sources_utilisees", [c["source"] for c in chunks])

            # Injecter dans l'analyse pour compatibilité avec le reste du code
            if "analyse" not in dossier:
                dossier["analyse"] = {}
            dossier["analyse"]["score_global"]    = dossier["score_actuel"]
            dossier["analyse"]["score_potentiel"] = dossier["score_potentiel"]

            self.log_info(
                f"Score: {dossier['score_actuel']}/100 → potentiel {dossier['score_potentiel']}/100 | "
                f"taux={dossier['taux_incapacite']}",
                dossier_id=dossier_id,
            )

        except (json.JSONDecodeError, Exception) as e:
            self.log_error(f"Erreur scoring RAG : {e}", dossier_id=dossier_id)
            dossier["score_actuel"]   = score_llm
            dossier["score_potentiel"] = score_llm
            dossier["rag_sources"]    = []

        dossier["maya_traite"]  = True
        dossier["agent_actuel"] = "Maya"
        return dossier

    def _extraire_tags(self, dossier: dict, analyse: dict) -> list[str]:
        tags = []
        type_dos = dossier.get("type_dossier", "adulte")
        if type_dos == "enfant":
            tags.extend(["enfant", "AEEH", "scolarité"])
        elif type_dos == "jeune_16_25":
            tags.extend(["RQTH", "emploi", "AAH"])
        else:
            tags.extend(["AAH", "PCH", "RQTH", "CMI", "adulte"])

        droits = analyse.get("droits_identifies", [])
        for d in droits:
            d_upper = d.upper()
            for tag in ["AAH", "PCH", "AEEH", "RQTH", "CMI", "ESAT", "IME", "SESSAD", "SAVS"]:
                if tag in d_upper:
                    tags.append(tag)

        age = dossier.get("age_beneficiaire", 30)
        if age < 20:
            tags.append("taux_incapacite")
        if analyse.get("score_global", 0) >= 50:
            tags.append("50pct")
        if analyse.get("score_global", 0) >= 80:
            tags.append("80pct")

        return list(set(tags))
