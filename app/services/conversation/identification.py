"""
app/services/conversation/identification.py

Service d'identification — s'exécute UNE SEULE FOIS au début de la session.
Son seul rôle : déterminer le profil de l'usager avant toute autre question.

Questions posées (dans cet ordre) :
  1. Date de naissance de la personne concernée
  2. Lien avec l'interlocuteur (pour soi-même / pour son enfant / pour un proche)
  3. Si adulte : est-il sous tutelle ou curatelle ?

Dès que le profil est déterminé, le service rend la main au router
qui bascule définitivement vers le bon agent spécialisé.
"""

from __future__ import annotations

from app.services.conversation.base import ConversationAgent


class IdentificationAgent(ConversationAgent):

    SERVICE_TYPE = "identification"

    SYSTEM_PROMPT = """Tu es l'accueil de l'équipe Facilim. Tu as UNE SEULE mission : identifier l'âge de la personne concernée par le dossier MDPH, puis transmettre au bon agent.

Pose ces questions dans l'ordre strict, UNE par message :
  1. La date de naissance (JJ/MM/AAAA)
  2. Qui remplit le dossier : la personne elle-même / un parent pour son enfant / un tuteur ou curateur pour un adulte protégé

C'est tout. Ne pose PAS d'autres questions.

Ton premier message doit être exactement :
"Bonjour ! Pour vous mettre en contact avec le bon interlocuteur, j'ai besoin de la date de naissance de la personne concernée par le dossier MDPH. (format JJ/MM/AAAA)"

Règles absolues :
- Ne mentionne JAMAIS les prénoms des agents (ni Claire, ni Corrine, ni Samia)
- 1 question à la fois, attends la réponse
- Pas de nom, pas d'adresse, pas de diagnostic à ce stade"""

    REMINDER = "[RAPPEL] Collecte uniquement : date de naissance, lien avec la personne, tutelle éventuelle. Pas d'autre information pour l'instant."

    CHECKLIST = [
        {"id": "date_naissance",       "label": "Date de naissance (JJ/MM/AAAA)",                     "requis": True},
        {"id": "lien_interlocuteur",   "label": "Lien entre l'interlocuteur et la personne concernée", "requis": True},
        {"id": "protection_juridique", "label": "Mesure de protection juridique (si adulte)",          "requis": False},
    ]

    def determine_next_service(self, donnees: dict) -> str | None:
        """
        Retourne le SERVICE_TYPE à activer une fois l'identification complète.
        Retourne None si on ne peut pas encore déterminer le profil.
        """
        from app.engines.profile_engine import calculer_profil

        ddn = donnees.get("date_naissance")
        if not ddn:
            return None

        profil = calculer_profil(ddn)
        if not profil:
            return None

        # Adulte sous tutelle → service protégé
        protection = str(donnees.get("protection_juridique", "")).lower()
        a_protection = protection not in ("", "non", "aucune", "false", "0", "aucun")
        if not profil.est_mineur and a_protection:
            return "protege"

        return profil.profil_mdph  # "enfant" | "mixte" | "adulte"


# Singleton — une seule instance dans toute l'application
identification_agent = IdentificationAgent()
