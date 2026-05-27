"""
agents/ibrahim_agent.py — Ibrahim (Niveau 0 : Traduction & multilinguisme)

Responsabilités :
  - Détecte la langue d'un message entrant (langdetect + fallback GPT)
  - Traduit les questions FALC dans la langue de la famille
  - Traduit les réponses famille vers le français pour traitement interne
  - Stocke la langue préférée dans le dossier

Langues supportées : fr, ar, tr, en, es, pt, ro, wo (wolof), ti (tigrigna)
"""
import importlib
from typing import Any

from agents.base_agent import BaseAgent

try:
    from langdetect import detect as langdetect_detect
    _HAS_LANGDETECT = True
except ImportError:
    _HAS_LANGDETECT = False

try:
    from deep_translator import GoogleTranslator
    _HAS_DEEP_TRANSLATOR = True
except ImportError:
    _HAS_DEEP_TRANSLATOR = False

_media = importlib.import_module("services.media_client")
_detect_lang_llm = _media.detect_language   # fallback GPT-4o-mini

# Langues pour lesquelles on a des confirmations de qualité
_LANGUES_SUPPORTEES = {"fr", "ar", "tr", "en", "es", "pt", "ro", "wo", "ti", "de", "nl"}

# Noms de langue lisibles (pour le dashboard)
_NOMS_LANGUES = {
    "fr": "Français", "ar": "Arabe", "tr": "Turc",
    "en": "Anglais", "es": "Espagnol", "pt": "Portugais",
    "ro": "Roumain", "wo": "Wolof", "ti": "Tigrigna",
    "de": "Allemand", "nl": "Néerlandais",
}


class IbrahimAgent(BaseAgent):
    NOM    = "Ibrahim"
    NIVEAU = "N0"
    ROLE   = "Traduction & détection de langue"

    def run(self, dossier: dict[str, Any], **kwargs) -> dict[str, Any]:
        """
        Détecte la langue et traduit si nécessaire.
        kwargs attendus :
          - texte (str) : texte à analyser / traduire
          - direction (str) : "detection" | "vers_fr" | "depuis_fr"
        """
        dossier_id = dossier.get("dossier_id", "—")
        texte      = kwargs.get("texte", "")
        direction  = kwargs.get("direction", "detection")

        if direction == "detection":
            langue = self.detecter_langue(texte, dossier_id)
            dossier["langue_detectee"] = langue
            if not dossier.get("langue_preferee"):
                dossier["langue_preferee"] = langue
            self.log_info(f"Langue détectée : {langue} ({_NOMS_LANGUES.get(langue, '?')})", dossier_id=dossier_id)

        elif direction == "vers_fr":
            langue_src = dossier.get("langue_preferee", "fr")
            if langue_src != "fr":
                traduit = self.traduire(texte, source=langue_src, cible="fr", dossier_id=dossier_id)
                dossier["texte_traduit_fr"] = traduit
            else:
                dossier["texte_traduit_fr"] = texte

        elif direction == "depuis_fr":
            langue_cible = dossier.get("langue_preferee", "fr")
            if langue_cible != "fr":
                traduit = self.traduire(texte, source="fr", cible=langue_cible, dossier_id=dossier_id)
                dossier["texte_traduit"] = traduit
            else:
                dossier["texte_traduit"] = texte

        dossier["agent_actuel"] = "Ibrahim"
        return dossier

    # ── Méthodes utilitaires ──────────────────────────────────────────────────

    def detecter_langue(self, texte: str, dossier_id: str = "—") -> str:
        """Détection en cascade : langdetect → GPT fallback."""
        if not texte or len(texte.strip()) < 5:
            return "fr"

        # 1. langdetect (rapide, offline)
        if _HAS_LANGDETECT:
            try:
                code = langdetect_detect(texte)
                if code in _LANGUES_SUPPORTEES:
                    return code
                # Pour les langues non listées, on laisse passer comme "fr" par défaut
                return code[:2] if len(code) >= 2 else "fr"
            except Exception:
                pass

        # 2. Fallback GPT-4o-mini
        try:
            return _detect_lang_llm(texte)
        except Exception as e:
            self.log_error(f"Détection langue échouée : {e}", dossier_id=dossier_id)
            return "fr"

    def traduire(self, texte: str, source: str, cible: str, dossier_id: str = "—") -> str:
        """
        Traduction deep_translator (GoogleTranslator) avec fallback GPT.
        """
        if not texte or source == cible:
            return texte

        # 1. deep_translator (Google Translate gratuit)
        if _HAS_DEEP_TRANSLATOR:
            try:
                traduit = GoogleTranslator(source=source, target=cible).translate(texte)
                if traduit:
                    self.log_info(f"Traduction {source}→{cible} OK ({len(traduit)} chars)", dossier_id=dossier_id)
                    return traduit
            except Exception as e:
                self.log_warning(f"deep_translator échoué ({e}), fallback GPT", dossier_id=dossier_id)

        # 2. Fallback GPT-4o-mini
        try:
            _llm = importlib.import_module("4_llm_client.openai_client")
            call_llm = _llm.call_llm
            result = call_llm(
                system_prompt=f"Traduis le texte suivant du {source} vers le {cible}. Réponds UNIQUEMENT avec la traduction, sans commentaire.",
                user_message=texte,
                model="gpt-4o-mini",
                max_tokens=500,
                temperature=0.1,
            )
            self.log_info(f"Traduction GPT {source}→{cible} OK", dossier_id=dossier_id)
            return result.strip()
        except Exception as e:
            self.log_error(f"Traduction GPT échouée : {e}", dossier_id=dossier_id)
            return texte  # fallback : texte original

    @staticmethod
    def nom_langue(code: str) -> str:
        return _NOMS_LANGUES.get(code, code)
