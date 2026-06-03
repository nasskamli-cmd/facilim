"""
app/services/conversation/router.py

Routeur de services de conversation MDPH.

Principe :
  - Le service_type est lu depuis sessions_whatsapp.persona_actif
  - Une fois défini, il ne change JAMAIS (stocké en DB, lu à chaque message)
  - get_agent(service_type) retourne toujours le même singleton

Services disponibles :
  "identification" → IdentificationAgent  (étape initiale, toujours)
  "enfant"         → ChildConversationAgent
  "mixte"          → AdultConversationAgent  (même agent, profil mixte 16-25 ans)
  "adulte"         → AdultConversationAgent
  "protege"        → ProtectedAdultConversationAgent
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.services.conversation.identification import identification_agent
from app.services.conversation.child_agent    import child_agent
from app.services.conversation.adult_agent    import adult_agent
from app.services.conversation.protected_agent import protected_agent

if TYPE_CHECKING:
    from app.services.conversation.base import ConversationAgent

logger = logging.getLogger("facilim.conversation.router")

# Registre immuable — singleton par service
_REGISTRY: dict[str, "ConversationAgent"] = {
    "identification": identification_agent,
    "enfant":         child_agent,
    "mixte":          adult_agent,    # 16-25 ans : même agent que adulte standard
    "adulte":         adult_agent,
    "protege":        protected_agent,
    # Alias legacy
    "intake":         identification_agent,
    "collecte":       identification_agent,
    # Point 2 — état de validation finale en attente de réponse usager
    # L'agent identification sert de fallback neutre : il ne pose pas de question
    # de dossier, il attend uniquement OUI/NON (géré dans orchestration_engine.py).
    "validation_en_attente": identification_agent,
}


def get_agent(service_type: str) -> "ConversationAgent":
    """
    Retourne le singleton de l'agent correspondant au service_type.
    Si service_type inconnu, retourne l'agent d'identification par sécurité.
    """
    agent = _REGISTRY.get(service_type)
    if agent is None:
        logger.warning("[ROUTER] service_type inconnu : %r → identification", service_type)
        return identification_agent
    return agent


def service_type_from_persona(persona_actif: str) -> str:
    """
    Convertit la valeur de sessions_whatsapp.persona_actif en service_type normalisé.
    Les valeurs legacy ("intake", "collecte", "") sont toutes mappées sur "identification".
    """
    if persona_actif in _REGISTRY:
        agent = _REGISTRY[persona_actif]
        return agent.SERVICE_TYPE   # retourne le SERVICE_TYPE canonique
    return "identification"
