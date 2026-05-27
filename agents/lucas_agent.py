"""
agents/lucas_agent.py — Lucas (Niveau 1 : Correction documents illisibles)

Responsabilités :
  - Tente une récupération OCR par vision (GPT-4o avec image_url)
  - Si la qualité est insuffisante, génère un message de demande de re-téléversement
  - Extrait les informations structurées même depuis des images de mauvaise qualité

Prérequis : les images doivent être encodées en base64 ou accessibles par URL.
"""
import base64
import importlib
import json
from pathlib import Path
from typing import Any

from agents.base_agent import BaseAgent

_openai = importlib.import_module("4_llm_client.openai_client")


class LucasAgent(BaseAgent):
    NOM    = "Lucas"
    NIVEAU = "N1"
    ROLE   = "Correction documents illisibles (vision)"

    # Score de confiance minimal pour accepter l'extraction
    _SEUIL_CONFIANCE = 0.6

    def run(self, dossier: dict[str, Any], **kwargs) -> dict[str, Any]:
        """
        Tente d'extraire du texte d'une image de mauvaise qualité.
        kwargs attendus :
          - image_path (str) : chemin local du fichier image
          - image_b64 (str)  : image encodée en base64 (prioritaire sur image_path)
          - settings         : objet Settings avec openai_api_key
        """
        dossier_id  = dossier.get("dossier_id", "—")
        image_b64   = kwargs.get("image_b64")
        image_path  = kwargs.get("image_path")
        settings    = kwargs.get("settings") or self.settings

        if not image_b64 and image_path:
            try:
                image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
            except Exception as e:
                self.log_error(f"Lecture image échouée : {e}", dossier_id=dossier_id)
                dossier["lucas_resultat"] = "erreur_lecture"
                dossier["lucas_message_famille"] = self._message_retelechargement()
                return dossier

        if not image_b64:
            self.log_warning("Aucune image fournie à Lucas.", dossier_id=dossier_id)
            return dossier

        # ── Appel GPT-4o vision ────────────────────────────────────────────────
        try:
            import openai
            client = openai.OpenAI(api_key=settings.openai_api_key if settings else None)

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Tu es Lucas, expert en extraction de documents médicaux et administratifs. "
                            "Extrais TOUTES les informations lisibles de ce document, même partiellement flou. "
                            "Évalue ta confiance (0.0 à 1.0). "
                            "Réponds en JSON : "
                            '{"texte_extrait": "...", "confiance": 0.0-1.0, "champs": {}, "document_type": "..."}'
                        ),
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_b64}",
                                    "detail": "high",
                                },
                            },
                            {
                                "type": "text",
                                "text": "Extrais toutes les informations de ce document médical ou administratif.",
                            },
                        ],
                    },
                ],
                max_tokens=800,
                temperature=0.1,
            )

            raw = response.choices[0].message.content.strip()
            raw = raw.lstrip("```json").lstrip("```").rstrip("```").strip()
            data = json.loads(raw)

            confiance = float(data.get("confiance", 0.0))
            texte     = data.get("texte_extrait", "")
            champs    = data.get("champs", {})
            doc_type  = data.get("document_type", "inconnu")

            self.log_info(
                f"Vision extraction | confiance={confiance:.2f} | doc_type={doc_type}",
                dossier_id=dossier_id,
            )

            if confiance >= self._SEUIL_CONFIANCE:
                # ── Extraction réussie ─────────────────────────────────────────
                dossier["lucas_resultat"]        = "extraction_ok"
                dossier["lucas_texte_extrait"]   = texte
                dossier["lucas_champs"]          = champs
                dossier["lucas_confiance"]       = confiance
                dossier["lucas_doc_type"]        = doc_type
                # Enrichir l'analyse principale
                if texte and not dossier.get("texte_brut"):
                    dossier["texte_brut"] = texte
            else:
                # ── Qualité insuffisante → demande re-téléversement ────────────
                self.log_warning(
                    f"Qualité insuffisante ({confiance:.2f} < {self._SEUIL_CONFIANCE}) → re-téléversement",
                    dossier_id=dossier_id,
                )
                dossier["lucas_resultat"]          = "qualite_insuffisante"
                dossier["lucas_confiance"]         = confiance
                dossier["lucas_message_famille"]   = self._message_retelechargement(doc_type)

        except (json.JSONDecodeError, Exception) as e:
            self.log_error(f"Erreur vision extraction : {e}", dossier_id=dossier_id)
            dossier["lucas_resultat"]          = "erreur_vision"
            dossier["lucas_message_famille"]   = self._message_retelechargement()

        dossier["agent_actuel"] = "Lucas"
        return dossier

    @staticmethod
    def _message_retelechargement(doc_type: str = "document") -> str:
        return (
            f"Bonjour, je suis Lucas de l'équipe Facilim.\n\n"
            f"Le {doc_type} que vous avez envoyé est difficile à lire. "
            "Pourriez-vous le retéléverser en prenant soin de :\n"
            "  • Bonne luminosité (pas de reflet ni d'ombre)\n"
            "  • Document bien à plat et entier dans le cadre\n"
            "  • Photo nette (sans flou de bougé)\n\n"
            "Merci de votre compréhension."
        )
