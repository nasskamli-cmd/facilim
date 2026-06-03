"""
app/services/conversation/base.py

Contrat abstrait d'un agent de conversation MDPH.

Chaque agent est UN OBJET SINGLETON avec :
  - SYSTEM_PROMPT  : prompt système IMMUABLE (jamais assemblé dynamiquement)
  - REMINDER       : rappel court ré-injecté juste avant chaque message user
  - CHECKLIST      : liste des champs à collecter (filtrée par profil)
  - SERVICE_TYPE   : identifiant stocké dans sessions_whatsapp.persona_actif

La méthode respond() est la seule interface publique.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger("facilim.conversation")


class ConversationAgent(ABC):
    """Agent de conversation MDPH — une instance par profil, jamais recréée."""

    SERVICE_TYPE:  str        # "enfant" | "mixte" | "adulte" | "protege" | "identification"
    SYSTEM_PROMPT: str        # prompt système complet, figé à la définition de la classe
    REMINDER:      str        # rappel court, injecté après l'historique

    # Champs obligatoires à collecter (id, label, requis, condition optionnelle)
    CHECKLIST: list[dict]

    # ── Interface publique ────────────────────────────────────────────────────

    def respond(
        self,
        message: str,
        history: list[dict],
        donnees: dict[str, Any],
        openai_client: Any,
        model: str = "gpt-4o-mini",
        onglet_courant: int = 2,
        validation_en_attente: bool = False,
        history_window: int = 10,
    ) -> str:
        """
        Génère la réponse de l'agent au message entrant.
        Le prompt système est celui de la classe — jamais modifié.
        """
        try:
            context = self._build_context(donnees, onglet_courant, validation_en_attente)
            system_full = self.SYSTEM_PROMPT + context

            messages: list[dict] = [{"role": "system", "content": system_full}]

            # Historique : fenêtre configurable (défaut 10, paramétrable depuis settings)
            for m in history[-history_window:]:
                role    = m.get("role", "user")
                content = m.get("content") or m.get("reponse") or ""
                if content and role in ("user", "assistant"):
                    messages.append({"role": role, "content": str(content)[:500]})

            # Rappel sandwich — injecté APRÈS l'historique, AVANT le message
            messages.append({"role": "system", "content": self.REMINDER})
            messages.append({"role": "user",   "content": message})

            response = openai_client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=250,
                temperature=0.4,
            )
            reponse = response.choices[0].message.content.strip()
            logger.info("[%s] Réponse générée (%d chars)", self.SERVICE_TYPE, len(reponse))
            return reponse

        except Exception as e:
            logger.error("[%s] Erreur LLM : %s", self.SERVICE_TYPE, e)
            manquants = self.missing_fields(donnees)
            if manquants:
                return f"Merci. Pourriez-vous me préciser : {manquants[0]} ?"
            return "Merci pour vos informations. — L'équipe Facilim"

    def missing_fields(self, donnees: dict[str, Any]) -> list[str]:
        """Retourne les libellés des champs obligatoires non encore renseignés."""
        missing = []
        for item in self.CHECKLIST:
            if not item.get("requis", True):
                continue
            cond = item.get("condition")
            if cond:
                val = str(donnees.get(cond["champ"], "")).lower()
                if not val.startswith(cond["valeur"].lower()):
                    continue
            if not donnees.get(item["id"]):
                missing.append(item["label"])
        return missing

    def is_complete(self, donnees: dict[str, Any]) -> bool:
        return len(self.missing_fields(donnees)) == 0

    # ── Contexte dynamique (onglet + données) ────────────────────────────────

    def _build_context(
        self,
        donnees: dict[str, Any],
        onglet_courant: int,
        validation_en_attente: bool,
    ) -> str:
        """
        Construit le contexte dynamique injecté APRÈS le prompt statique.
        Ne touche jamais au SYSTEM_PROMPT.
        """
        from app.engines.conversation_engine import ONGLETS_MDPH
        onglet = next((o for o in ONGLETS_MDPH if o["num"] == onglet_courant), None)
        titre  = onglet["titre"] if onglet else f"Section {onglet_courant}"

        # Détection de langue du dernier message
        langue_detectee = "français"
        try:
            from langdetect import detect as _detect_lang
            code = _detect_lang(list(donnees.get("_derniere_langue_detectee", ["fr"]))[-1]
                                 if isinstance(donnees.get("_derniere_langue_detectee"), list)
                                 else donnees.get("_derniere_langue_detectee", "fr"))
            _LANGUES = {"ar": "arabe", "es": "espagnol", "en": "anglais",
                        "pt": "portugais", "tr": "turc", "it": "italien", "de": "allemand"}
            langue_detectee = _LANGUES.get(code, "français")
        except Exception:
            pass

        ctx = f"\n\n--- CONTEXTE SESSION ---\nOnglet en cours : {onglet_courant} — {titre}"
        # Langue choisie explicitement prioritaire sur détection automatique
        _langue_choisie_code = donnees.get("_langue_choisie", "")
        _CODES = {"fr": "français", "en": "anglais", "es": "espagnol",
                  "ar": "arabe", "pt": "portugais", "tr": "turc",
                  "ro": "roumain", "de": "allemand", "it": "italien"}
        if _langue_choisie_code and _langue_choisie_code != "fr":
            _lng_nom = _CODES.get(_langue_choisie_code, _langue_choisie_code)
            ctx += f"\n🌍 LANGUE : réponds UNIQUEMENT en {_lng_nom}. Toutes les questions en {_lng_nom}."
        elif langue_detectee != "français":
            ctx += f"\n⚠️ L'usager s'exprime en {langue_detectee}. Réponds DANS SA LANGUE."

        if validation_en_attente:
            ctx += (
                f"\n⚠️  Validation en attente sur l'onglet {onglet_courant}."
                " Rappelle poliment de répondre OUI ou de corriger."
            )

        manquants = self.missing_fields(donnees)
        if manquants:
            # Maximum 2 questions par message pour ne pas surcharger.
            # Le LLM les formule de façon naturelle et conversationnelle.
            prochains = manquants[:2]
            ctx += f"\nInformations à collecter MAINTENANT ({len(prochains)}/{len(manquants)} restantes) :\n"
            for m in prochains:
                ctx += f"  → {m}\n"
            ctx += (
                "\nRègle absolue :\n"
                "• Pose ces 1 ou 2 questions EN UN SEUL message, formulé naturellement\n"
                "• JAMAIS de liste numérotée (1. 2. 3.)\n"
                "• ATTENDS la réponse avant d'envoyer un autre message\n"
                "• Si la réponse est partielle, ne redemande QUE ce qui manque\n"
                "• Ton : chaleureux, simple, professionnel"
            )
        else:
            ctx += "\nToutes les informations sont collectées. Félicite chaleureusement et annonce la suite."

        # Résumé de ce qui est DÉJÀ CONNU — NE PAS REDEMANDER CES INFORMATIONS
        _champs_a_afficher = [
            (k, v) for k, v in donnees.items()
            if v not in (None, "", 0, [])
            and not k.startswith("_")
            and k not in ("notes_pro", "email", "documents_texte", "urgence",
                          "aidant_demande", "lien_interlocuteur")
        ]
        if _champs_a_afficher:
            ctx += f"\n\n⛔ INFORMATIONS DÉJÀ CONNUES — NE PAS REDEMANDER ({len(_champs_a_afficher)} champs) :\n"
            for k, v in _champs_a_afficher[:8]:
                ctx += f"  ✓ {k}: {str(v)[:80]}\n"
            ctx += "Ces informations ont été transmises par le professionnel. Passer directement aux éléments manquants."

        return ctx
