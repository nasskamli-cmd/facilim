"""
agents/camille_agent.py — Camille (Niveau 1 : Instruction & normalisation)

Responsabilités :
  - Extraction OCR du texte brut depuis fichiers uploadés (PDF, images)
  - Normalisation en JSON structuré via GPT-4o-mini
  - Validation cohérence DDN vs type de dossier
  - Délègue à Lucas si le document est illisible

S'intègre dans la pipeline existante : remplace / complète file_extractor.py
"""
import json
import importlib
from typing import Any

from agents.base_agent import BaseAgent

_llm = importlib.import_module("4_llm_client.openai_client")
call_llm = _llm.call_llm

# Schéma cible des données structurées CERFA 15692
_SCHEMA_CIBLE = {
    "nom": None, "prenom": None, "date_naissance": None,
    "genre": None, "adresse": None, "code_postal": None, "commune": None,
    "nss": None, "telephone": None, "email": None,
    "situation_familiale": None, "nb_enfants_charge": None,
    "diagnostics": [], "traitements": [], "medecin_traitant": None,
    "impact_vie_quotidienne": None, "situation_scolaire_pro": None,
    "historique_mdph": None, "droits_demandes": [],
}


class CamilleAgent(BaseAgent):
    NOM    = "Camille"
    NIVEAU = "N1"
    ROLE   = "Instruction, OCR & normalisation JSON"

    def run(self, dossier: dict[str, Any], **kwargs) -> dict[str, Any]:
        dossier_id = dossier.get("dossier_id", "—")
        texte_brut = (
            dossier.get("texte_brut")
            or dossier.get("analyse", {}).get("_texte_anon")
            or ""
        )

        if not texte_brut.strip():
            self.log_warning("Aucun texte disponible pour l'instruction.", dossier_id=dossier_id)
            dossier["camille_resultat"] = "texte_vide"
            return dossier

        # ── Normalisation LLM → JSON structuré ────────────────────────────────
        prompt = f"""
Tu es Camille, spécialiste en instruction de dossiers MDPH.
Extrais TOUTES les informations présentes dans ce texte et structure-les en JSON selon ce schéma :
{json.dumps(_SCHEMA_CIBLE, ensure_ascii=False, indent=2)}

Règles :
- Si une information est absente, met null (pas de chaîne vide).
- Pour droits_demandes, liste tous les droits mentionnés (AAH, PCH, RQTH, AEEH, CMI, IME, ESAT, SESSAD, SAVS, etc.)
- Pour diagnostics, liste tous les diagnostics avec leur ancienneté si connue.
- date_naissance : format JJ/MM/AAAA si possible.
- Réponds UNIQUEMENT avec le JSON, sans texte avant ou après.

=== TEXTE À ANALYSER ===
{texte_brut[:3000]}
"""
        try:
            reponse = call_llm(
                system_prompt="Tu es Camille, agent d'instruction MDPH. Tu réponds UNIQUEMENT en JSON valide.",
                user_message=prompt,
                model="gpt-4o-mini",
                max_tokens=1000,
                temperature=0.0,
            )
            reponse = reponse.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            donnees = json.loads(reponse)

            # Fusion avec les données déjà présentes dans le dossier
            for champ, valeur in donnees.items():
                if valeur is not None and valeur != [] and not dossier.get(champ):
                    dossier[champ] = valeur

            # Synchronisation des champs clés CERFA
            for k, v_dos in [
                ("nom_enfant", donnees.get("nom")),
                ("prenom_enfant", donnees.get("prenom")),
                ("ddn_enfant", donnees.get("date_naissance")),
                ("adresse_enfant", donnees.get("adresse")),
                ("cp_enfant", donnees.get("code_postal")),
                ("commune_enfant", donnees.get("commune")),
                ("email_famille", donnees.get("email")),
            ]:
                if v_dos and not dossier.get(k):
                    dossier[k] = v_dos

            dossier["donnees_normalisees"] = donnees
            dossier["camille_resultat"]    = "ok"
            dossier["agent_actuel"]        = "Camille"

            self.log_info(
                f"Normalisation OK | {sum(1 for v in donnees.values() if v)} champs extraits",
                dossier_id=dossier_id,
            )

        except (json.JSONDecodeError, Exception) as e:
            self.log_error(f"Normalisation LLM échouée : {e}", dossier_id=dossier_id)
            dossier["camille_resultat"] = "erreur_llm"

        # ── Validation cohérence DDN / type dossier ────────────────────────────
        self._valider_coherence(dossier, dossier_id)
        return dossier

    def _valider_coherence(self, dossier: dict, dossier_id: str):
        type_dos = dossier.get("type_dossier", "")
        donnees  = dossier.get("donnees_normalisees", {})
        droits   = donnees.get("droits_demandes", [])

        # Vérification AEEH réservé aux enfants
        if "AEEH" in str(droits) and type_dos not in ("enfant", "jeune_16_25"):
            self.log_warning(
                "Incohérence : AEEH demandé pour un adulte (âge ≥ 26 ans).",
                dossier_id=dossier_id,
            )
            dossier["alerte_coherence"] = "AEEH demandé mais bénéficiaire adulte (> 20 ans)."

        # ESAT/SAVS normalement adultes
        if "IME" in str(droits) and type_dos == "adulte":
            self.log_warning(
                "Incohérence : IME demandé pour un adulte.",
                dossier_id=dossier_id,
            )
