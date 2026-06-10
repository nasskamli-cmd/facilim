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

from app.services.field_status import (
    est_a_completer_pro,
    est_refuse,
    finalisation_bloquee,
    statut_champ,
)

# Cœur substantiel d'un dossier MDPH « solide » : ces champs ne peuvent PAS être
# tous délégués/refusés sans vider le dossier de son sens. Un dossier n'est
# « prêt à transmettre » que s'ils sont réellement FOURNIS (cf. dossier_solide).
CHAMPS_COEUR_SOLIDITE = (
    "impact_quotidien",     # retentissement (B) — ce que la MDPH évalue
    "aides_en_place",       # besoins de compensation (B2)
    "attentes_usager",      # attentes (E) — autodétermination
    "projet_de_vie",        # projet de vie (E)
)

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
                max_tokens=400,
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

    def _applicable(self, item: dict, donnees: dict[str, Any]) -> bool:
        """True si un champ requis est applicable ici (condition remplie)."""
        if not item.get("requis", True):
            return False
        from app.services.collecte_schema import condition_remplie
        return condition_remplie(donnees, item.get("condition"))

    def missing_fields(self, donnees: dict[str, Any]) -> list[str]:
        """
        Libellés des champs obligatoires encore À POSER À L'USAGER. Exclut les
        champs refusés ET ceux délégués au professionnel (« à compléter par pro ») :
        on ne les repose pas à l'usager — mais ils restent comptés et VISIBLES
        ailleurs (synthese_completude / points_d_attention), jamais effacés.
        """
        return [it["label"] for it in self.CHECKLIST
                if self._applicable(it, donnees)
                and statut_champ(donnees, it["id"]) == "en_attente"]

    def missing_field_ids(self, donnees: dict[str, Any]) -> list[str]:
        """Comme missing_fields() mais retourne les IDS (détection refus / relance)."""
        return [it["id"] for it in self.CHECKLIST
                if self._applicable(it, donnees)
                and statut_champ(donnees, it["id"]) == "en_attente"]

    def etat_par_champ(self, donnees: dict[str, Any]) -> list[dict[str, str]]:
        """
        État de CHAQUE champ requis applicable : 'fourni' | 'refuse' |
        'a_completer_pro' | 'en_attente'. Aucun champ exigé n'est masqué.
        """
        out: list[dict[str, str]] = []
        for it in self.CHECKLIST:
            if not self._applicable(it, donnees):
                continue
            out.append({
                "id": it["id"],
                "label": it.get("label", it["id"]),
                "etat": statut_champ(donnees, it["id"]),
            })
        return out

    def synthese_completude(self, donnees: dict[str, Any]) -> dict[str, Any]:
        """
        Synthèse de complétude différenciée d'un dossier. Distingue clairement
        complet / en_attente / à compléter par pro / refusé, sans rien masquer.
        """
        etats = self.etat_par_champ(donnees)
        par = {e["etat"]: [] for e in etats}
        for e in etats:
            par.setdefault(e["etat"], []).append(e)
        requis = len(etats)
        fournis = len(par.get("fourni", []))
        return {
            "requis_total": requis,
            "fournis": fournis,
            "en_attente": [e["label"] for e in par.get("en_attente", [])],
            "a_completer_pro": [e["label"] for e in par.get("a_completer_pro", [])],
            "refuses": [e["label"] for e in par.get("refuse", [])],
            "taux_completude": round(fournis / requis, 2) if requis else 1.0,
        }

    def dossier_solide(self, donnees: dict[str, Any]) -> bool:
        """
        True si le CŒUR substantiel du dossier est réellement FOURNI (pas vide, pas
        refusé, pas seulement délégué). Empêche qu'un dossier creux passe « prêt ».
        """
        return all(statut_champ(donnees, cid) == "fourni" for cid in CHAMPS_COEUR_SOLIDITE)

    def is_complete(self, donnees: dict[str, Any]) -> bool:
        """
        COLLECTE RÉSOLUE côté usager : plus aucun champ requis « en_attente » (tout
        est fourni, refusé ou délégué au pro) ET aucun champ bloquant refusé. C'est
        le signal de fin de collecte (stoppe les relances), PAS le feu vert de
        transmission : un dossier « prêt à transmettre » exige en plus dossier_solide
        (cf. revue_instructeur.validite_dossier) — un dossier creux ne passe jamais.
        """
        if self.missing_fields(donnees):
            return False
        return not finalisation_bloquee(donnees)

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

        # Signal profil handicap — adapte le nombre de questions par message
        _profil_principal  = donnees.get("profil_principal", "")
        _profil_secondaire = donnees.get("profil_secondaire", "")
        _sous_profil       = donnees.get("sous_profil", "")
        _tags              = donnees.get("tags_detectes", [])
        _PROFILS_COGNITIFS = {"tsa", "di", "cognitif"}
        _PROFILS_FRAGILES  = {"psychique", "psychique_humeur", "psychique_psychotique",
                               "maladie_chronique", "parcours_esms"}
        if _profil_principal in _PROFILS_COGNITIFS or _profil_secondaire in _PROFILS_COGNITIFS:
            ctx += "\n⚠️ PROFIL COGNITIF détecté (TSA/DI/cognitif) → MAXIMUM 1 question par message. Formulation très concrète."
        elif _profil_principal in _PROFILS_FRAGILES or _profil_secondaire in _PROFILS_FRAGILES:
            ctx += "\n⚠️ PROFIL FRAGILE détecté → maximum 2 questions par message. Ton particulièrement doux et patient."
        elif _profil_principal:
            ctx += f"\n📋 Profil handicap : {_profil_principal}" + (f" + {_profil_secondaire}" if _profil_secondaire else "") + " → 2 à 3 questions par message autorisées si thème cohérent."
        if _tags:
            ctx += f"\n🏷️ Tags : {', '.join(_tags)}"

        # Questions spécifiques au profil — injectées selon l'onglet courant
        if _profil_principal:
            try:
                from app.engines.profil_specifique_engine import (
                    formater_questions_specifiques_pour_contexte,
                )
                from app.engines.verbatim_engine import section_depuis_onglet as _sdo
                _section_courante = _sdo(onglet_courant)
                if _section_courante:
                    _qs = formater_questions_specifiques_pour_contexte(
                        _profil_principal, _sous_profil or _profil_principal, _section_courante
                    )
                    if _qs:
                        ctx += _qs
            except Exception:
                pass
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

        # ── Instruction de relance (Sprint 2) ────────────────────────────────
        # Injectée par l'orchestrateur quand la réponse précédente était pauvre.
        # Elle prend la priorité absolue sur les questions normales.
        _instruction_relance = donnees.get("_instruction_relance_active", "")
        if _instruction_relance:
            ctx += _instruction_relance
            return ctx   # Retour immédiat — la relance est la seule instruction

        manquants_ids = [
            item["id"] for item in self.CHECKLIST
            if item.get("requis", True)
            and not donnees.get(item["id"])
            and not est_refuse(donnees, item["id"])
        ]
        # Filtrer les champs déjà couverts par l'extraction documentaire
        _knowledge = donnees.get("_document_knowledge") or {}
        if _knowledge:
            try:
                from app.engines.document_functional_extractor import filtrer_couverts_par_document
                manquants_ids = filtrer_couverts_par_document(manquants_ids, _knowledge)
            except Exception:
                pass

        # ── Groupement par nature de question ─────────────────────────────────
        # Questions OUVERTES (réflexives) : posées UNE par une, pour laisser la
        # personne s'exprimer. Questions FACTUELLES courtes (identité, administratif,
        # dates, choix) : regroupées en un seul message pour réduire les allers-retours
        # et éviter les redondances.
        _CHAMPS_OUVERTS = {
            "impact_quotidien", "aides_en_place", "aides_techniques", "frais_handicap",
            "consequences_professionnelles", "projet_professionnel", "attentes_usager",
            "projet_de_vie", "aidant_identite", "accompagnement_scolaire",
            "amenagements_scolaires", "expression_directe", "situation_professionnelle",
        }

        # Reconvertir en labels pour l'affichage
        _id_to_label = {item["id"]: item["label"] for item in self.CHECKLIST}
        manquants = [_id_to_label[mid] for mid in manquants_ids if mid in _id_to_label]

        if manquants_ids:
            _premier = manquants_ids[0]
            if _premier in _CHAMPS_OUVERTS:
                # Question ouverte → seule, pour ne pas brider l'expression.
                prochains_ids = [_premier]
            else:
                # Grouper les questions factuelles courtes consécutives (jusqu'à 4).
                prochains_ids = []
                for mid in manquants_ids:
                    if mid in _CHAMPS_OUVERTS:
                        break
                    prochains_ids.append(mid)
                    if len(prochains_ids) >= 4:
                        break
            prochains = [_id_to_label[mid] for mid in prochains_ids if mid in _id_to_label]
            _groupe = len(prochains) > 1
            # Relance douce : une de ces questions avait déjà été posée et est restée
            # sans réponse (oubli, pas refus) → on la redemande avec délicatesse.
            _oublies_ids = set(donnees.get("_champs_oublies") or [])
            _relance_douce = any(mid in _oublies_ids for mid in prochains_ids)

            ctx += f"\nInformations à collecter MAINTENANT ({len(prochains)}/{len(manquants)} restantes) :\n"
            for m in prochains:
                ctx += f"  → {m}\n"
            if _groupe:
                ctx += (
                    "\nRègle absolue :\n"
                    "• Pose ces questions courtes ENSEMBLE, en UN SEUL message fluide et naturel "
                    "(pas une par une) — par exemple en une phrase qui les enchaîne.\n"
                    "• JAMAIS de liste numérotée (1. 2. 3.)\n"
                    "• ATTENDS la réponse, puis ne redemande QUE ce qui manque encore\n"
                    "• Ton : chaleureux, simple, FALC (facile à lire et à comprendre)"
                )
            else:
                ctx += (
                    "\nRègle absolue :\n"
                    "• Pose CETTE seule question, ouverte, et laisse la personne s'exprimer librement\n"
                    "• JAMAIS de liste numérotée\n"
                    "• ATTENDS la réponse avant toute autre question\n"
                    "• Ton : chaleureux, simple, FALC (facile à lire et à comprendre)"
                )
            if _relance_douce:
                ctx += (
                    "\n• RELANCE DOUCE : une de ces informations avait déjà été demandée et "
                    "n'a pas encore été reçue. Redemande-la avec délicatesse, sans reproche, "
                    "en commençant par « Sauf erreur de ma part, je n'ai pas encore noté… »."
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
            ctx += (
                "Ces informations sont déjà connues : ne les redemande pas, passe aux éléments manquants. "
                "MAIS si l'usager demande à les voir, les vérifier ou les confirmer "
                "(par ex. « montre-moi », « récapitule », « qu'as-tu noté »), présente-lui un "
                "récapitulatif clair et lisible de ces informations. Ne refuse JAMAIS de les montrer."
            )

        return ctx
