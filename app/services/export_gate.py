"""
app/services/export_gate.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━
FACILIM PROD-3 — Verrou d'export CERFA (lecture seule)

Ce module NE calcule RIEN. Il lit uniquement le statut du gate DÉJÀ calculé
par cerfa_gate_engine et persisté dans la colonne `dossiers.cockpit_pro_json`
(clé `gate_export.decision`), puis le traduit en PASS / WARNING / BLOCK.

  - Aucun recalcul du gate
  - Aucune nouvelle évaluation
  - Aucun moteur métier
  - Aucune duplication de la logique de décision

Fonction pure et testable : utilisée par main.py pour refuser un export réel
lorsque le gate est en BLOCK.
"""

from __future__ import annotations

import json
from typing import Any

# Décisions produites par cerfa_gate_engine (déjà calculées, déjà persistées).
_DECISION_MAP = {
    "AUTORISE":                     "PASS",
    "AUTORISE_AVEC_AVERTISSEMENTS": "WARNING",
    "BLOQUE_EXPORT":                "BLOCK",
}


def lire_gate_export(cockpit_pro_json: Any) -> dict:
    """
    Lit le statut du gate d'export depuis le cockpit déjà persisté.

    Args:
        cockpit_pro_json: contenu de la colonne `dossiers.cockpit_pro_json`
                          (str JSON, dict, ou None).

    Returns:
        {
          "statut":          "PASS" | "WARNING" | "BLOCK" | "UNKNOWN",
          "autorise_export": bool,    # False UNIQUEMENT si BLOCK
          "present":         bool,    # True si un gate a été trouvé
          "message":         str,     # message lisible déjà produit
          "decision_brute":  str|None # valeur d'origine
        }

    Règle :
      - BLOCK            → export refusé
      - PASS / WARNING   → export autorisé
      - UNKNOWN (absent) → export autorisé (fail-open documenté, voir PROD_3_GATE_REPORT)
    """
    try:
        cockpit = json.loads(cockpit_pro_json) if isinstance(cockpit_pro_json, str) else (cockpit_pro_json or {})
    except Exception:
        cockpit = {}

    gate = (cockpit or {}).get("gate_export") or {}
    decision = gate.get("decision")
    statut = _DECISION_MAP.get(decision, "UNKNOWN")

    return {
        "statut":          statut,
        "autorise_export": statut != "BLOCK",
        "present":         decision is not None,
        "message":         gate.get("message", "") or "",
        "decision_brute":  decision,
    }


def coeur_incomplet(synthese: dict, profil: str | None = None) -> tuple[bool, str]:
    """
    Anti-gate-obsolète : revérifie la SOLIDITÉ du cœur métier sur la synthèse
    FRAÎCHE, au moment de l'export. Le gate persisté (cockpit_pro_json) peut être
    périmé (ex. champ du cœur vidé via une édition dashboard, sans recalcul du
    gate). Ce contrôle est déterministe (aucun LLM), réutilise validite_dossier
    déjà développé, et ne touche à aucun moteur droits/éligibilité/CDAPH.

    Retourne (bloque: bool, raison: str). bloque=True ⇒ export à refuser.
    """
    try:
        from app.engines.revue_instructeur import validite_dossier
        prof = (profil or (synthese or {}).get("profil_mdph")
                or (synthese or {}).get("profil_principal") or "adulte")
        v = validite_dossier(synthese or {}, prof)
        if not v.get("criteres", {}).get("dossier_solide", True):
            raison = next((m for m in v.get("manquants", []) if m.startswith("cœur")),
                          "cœur du dossier incomplet (retentissement / attentes / projet de vie)")
            return True, raison
    except Exception:
        return False, ""   # dégradation gracieuse : ne jamais bloquer sur une erreur technique
    return False, ""
