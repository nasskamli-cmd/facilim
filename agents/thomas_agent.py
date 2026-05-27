"""
agents/thomas_agent.py — Thomas (Niveau -1 : Dispatch)

Responsabilités :
  - Dispatche vers la cellule de collecte appropriée selon le type de dossier
  - Priorise les dossiers urgents (traitement en premier dans la file)
  - Assigne un manager local (Sarah, Karim, Aïcha) et un sous-agent

Règles de dispatch :
  enfant      → cellule Enfance (manager Sarah, agents Emma/Lucas)
  jeune_16_25 → cellule Jeunes (manager Karim, agents Chloé/Noah)
  adulte      → cellule Adultes (manager Aïcha, agents Paul/Sofia)
"""
from typing import Any
from agents.base_agent import BaseAgent

# ── Configuration des cellules ────────────────────────────────────────────────
CELLULES = {
    "enfant": {
        "manager":     "Sarah",
        "agents":      ["Emma", "Lucas"],
        "description": "Cellule Enfance (0-15 ans)",
        "queue":       "queue:enfant",
    },
    "jeune_16_25": {
        "manager":     "Karim",
        "agents":      ["Chloé", "Noah"],
        "description": "Cellule Jeunes (16-25 ans)",
        "queue":       "queue:jeune",
    },
    "adulte": {
        "manager":     "Aïcha",
        "agents":      ["Paul", "Sofia"],
        "description": "Cellule Adultes (26+ ans)",
        "queue":       "queue:adulte",
    },
}


class ThomasAgent(BaseAgent):
    NOM    = "Thomas"
    NIVEAU = "N-1"
    ROLE   = "Dispatch & priorisation"

    def run(self, dossier: dict[str, Any], **kwargs) -> dict[str, Any]:
        dossier_id  = dossier.get("dossier_id", "—")
        type_dos    = dossier.get("type_dossier", "adulte")
        urgence     = dossier.get("urgence", "normal")

        cellule = CELLULES.get(type_dos, CELLULES["adulte"])

        dossier["cellule_assignee"]  = cellule["description"]
        dossier["manager_local"]     = cellule["manager"]
        dossier["agent_collecte"]    = cellule["agents"][0]
        dossier["queue_cible"]       = cellule["queue"]
        dossier["priorite"]          = 10 if urgence in ("urgent", "critique") else 50
        dossier["agent_actuel"]      = "Thomas"

        self.log_info(
            f"Dispatch → {cellule['description']} | "
            f"manager={cellule['manager']} | urgence={urgence} | priorité={dossier['priorite']}",
            dossier_id=dossier_id,
        )

        # Si urgence critique, on le note pour que les directeurs soient alertés
        if urgence == "critique":
            self.log_warning(
                "Dossier CRITIQUE — escalade directeur déclenchée.",
                dossier_id=dossier_id,
            )
            dossier["escalade_directeur"] = True

        return dossier
