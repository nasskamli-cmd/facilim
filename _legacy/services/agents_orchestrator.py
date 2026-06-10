"""
services/agents_orchestrator.py — Orchestrateur Multi-Agents CERFA Facilim.

Réseau de 4 agents (1 transversal + 3 métier) :
  Agent 0 — Traducteur (pré/post-filtre universel)
  Agent 1 — AiguileurEtatCivil          : Sections A & B
  Agent 2 — SpécialisteAutonomie        : Sections C & F
  Agent 3 — ConseillerOrientationEmploi : Sections D & E

Flux multilingue :
  message (toute langue) → Traducteur → message_fr → Agents 1/2/3
  reponse_fr → Traducteur → reponse (langue usager) → WhatsApp

L'orchestrateur :
  1. Détecte la langue + traduit le message entrant si nécessaire
  2. Sélectionne l'agent actif selon l'état du DossierCERFA
  3. Appelle le LLM avec le prompt spécialisé de l'agent
  4. Applique le protocole de validation des réponses négatives
  4. Met à jour le DossierCERFA avec les champs extraits
  5. Appelle le moteur de règles
  6. Retourne la réponse WhatsApp à envoyer

Règles réglementaires intégrées :
  - Profil "mixte" (16-25 ans) : Sections C ET D obligatoires
  - ESPO : "trouver ma voie" / projet non défini → orientation_espo = True
  - ESRP : "Richebois" / "Visa Pro" → orientation_esrp = True
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from app.database.schemas import (
    AidantFamilial,
    ConfigurationCanal,
    ConfigurationDossier,
    ConfigurationLangue,
    DossierCERFA,
    IdentitePersonne,
    ProfilMDPH,
    SectionA_Identite,
    SectionB_VieScolaire,
    SectionC_VieQuotidienne,
    SectionD_SituationPro,
    SectionE_ProjetPro,
    SectionF_VieAidant,
    Section_Urgence,
    SituationJuridique,
    iso_vers_langue,
    langue_vers_iso,
)
from app.engines.rules_engine import executer_regles_metier_mdph

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Dictionnaires de tokens — Règles 2 & 3
# ─────────────────────────────────────────────────────────────────────────────

# Règle 3 — ESRP (alias Richebois, Visa Pro, CRP…)
TOKENS_ESRP: frozenset[str] = frozenset({
    "CRP", "CPO", "UEROS", "ESRP", "VISA PRO", "VISAPRO",
    "RICHEBOIS", "CENTRE DE REEDUCATION", "CENTRE DE READAPTATION",
    "REEDUCATION PROFESSIONNELLE", "READAPTATION PROFESSIONNELLE",
    "CENTRE DE RÉÉDUCATION", "CENTRE DE RÉADAPTATION",
})

TOKENS_ESAT: frozenset[str] = frozenset({
    "ESAT", "MILIEU PROTEGE", "MILIEU PROTÉGÉ",
    "ÉTABLISSEMENT ET SERVICE D'AIDE PAR LE TRAVAIL",
})

TOKENS_RQTH: frozenset[str] = frozenset({
    "RQTH", "RECONNAISSANCE TRAVAILLEUR HANDICAPÉ",
    "RECONNAISSANCE QUALITÉ TRAVAILLEUR HANDICAPÉ",
})

TOKENS_EA: frozenset[str] = frozenset({
    "ENTREPRISE ADAPTÉE", "ENTREPRISE ADAPTEE", "EA ",
})

# Règle 2 — ESPO (projet non défini)
TOKENS_ESPO: frozenset[str] = frozenset({
    "PAS DE PROJET", "PROJET NON DÉFINI", "PROJET NON DEFINI",
    "TROUVER MA VOIE", "JE NE SAIS PAS", "PAS ENCORE DÉFINI",
    "PAS ENCORE DEFINI", "EN RÉFLEXION", "EN REFLEXION",
    "CHERCHE SA VOIE", "CHERCHER MA VOIE", "ORIENTATION À DÉFINIR",
    "ORIENTATION A DEFINIR", "SANS PROJET PRÉCIS", "SANS PROJET PRECIS",
})

# Négations → valeurs sentinelles (protocole réponses négatives)
_NEGATIONS_AIDANT: tuple[str, ...] = (
    "personne ne m'aide", "je me débrouille seul", "je me débrouille seule",
    "pas d'aidant", "aucun aidant", "personne ne m'accompagne",
    "pas d'aide", "seul", "seule", "autonome",
)
_NEGATIONS_PROTECTION: tuple[str, ...] = (
    "pas de tuteur", "je gère seul", "je gère seule", "aucune protection",
    "pas sous tutelle", "pas de protection", "gère moi-même", "capable seul",
)
_NEGATIONS_URGENCE: tuple[str, ...] = (
    "pas d'urgence", "pas urgent", "pas pressé", "pas pressée",
    "aucune urgence", "pas de délai", "renouvellement tranquille",
)
_NEGATIONS_CMI: tuple[str, ...] = (
    "pas besoin de cmi", "pas de carte", "pas de carte mobilité",
    "pas besoin de carte", "pas de stationnement", "pas de priorité",
)
_NEGATIONS_RQTH: tuple[str, ...] = (
    "pas besoin de rqth", "pas de reconnaissance", "refuse rqth",
)


# ─────────────────────────────────────────────────────────────────────────────
# Structures d'entrée / sortie
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class OrchestratorInput:
    message_whatsapp:  str
    cerfa_reponses:    dict
    historique:        list[dict]
    openai_client:     Any
    dossier_cerfa:     Optional[DossierCERFA] = None
    est_message_vocal: bool = False   # True si le message vient d'un vocal transcrit


@dataclass
class OrchestratorOutput:
    dossier_cerfa:            DossierCERFA
    reponse_whatsapp:         str          # dans la langue de l'usager
    agent_ayant_repondu:      str          # "traducteur"|"aiguilleur"|"autonomie"|"orientation"
    langue_detectee:          str          = "fr"
    message_traduit_fr:       str          = ""   # message en français soumis aux agents
    audio_bytes:              bytes | None = None  # audio TTS si canal_cible == "vocal"
    champs_negatifs_resolus:  list[str]    = field(default_factory=list)
    champs_extraits:          dict         = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Agent 0 — Traducteur universel (pré/post-filtre)
# ─────────────────────────────────────────────────────────────────────────────

_PROMPT_TRADUCTEUR = """
Tu es le module de détection linguistique de Facilim.
Ta tâche est double :
  1. Détecter la langue du message (code ISO 639-1 : "fr", "ar", "en", "es", "pt", "tr"…)
  2. Si la langue n'est PAS le français, traduire FIDÈLEMENT le message en français.
     La traduction doit préserver le sens exact sans reformuler ni ajouter d'informations.

Réponds en JSON :
{
  "langue": "<code ISO 639-1>",
  "est_francais": true ou false,
  "traduction_fr": "<traduction fidèle en français, ou null si déjà en français>"
}

Exemples :
  Message : "أنا أستخدم كرسي متحرك"
  → {"langue": "ar", "est_francais": false, "traduction_fr": "J'utilise un fauteuil roulant"}

  Message : "Je ne peux pas marcher plus de 100 mètres"
  → {"langue": "fr", "est_francais": true, "traduction_fr": null}
"""

_PROMPT_TRADUCTEUR_RETOUR = """
Tu es le module de traduction de Facilim.
Traduis le message suivant du français vers la langue indiquée.
La traduction doit être naturelle, bienveillante et conserver le ton d'une assistante sociale.
Ne modifie pas les emojis ni les éléments de mise en forme (sauts de ligne, puces).

Réponds UNIQUEMENT avec la traduction — aucun texte supplémentaire.
"""

# Langues pour lesquelles on ne tente pas la traduction (évite les faux positifs)
_LANGUES_SANS_TRADUCTION: frozenset[str] = frozenset({"fr", "unknown", ""})


def agent0_detecter_langue(
    message: str,
    openai_client: Any,
) -> tuple[str, str]:
    """
    Détecte la langue du message et retourne sa traduction en français.

    Retourne :
      (langue_iso, message_en_francais)
      Si déjà en français → message_en_francais == message original
    """
    if not message or not message.strip():
        return "fr", message

    result = _appeler_llm_json(
        openai_client,
        _PROMPT_TRADUCTEUR,
        message,
        max_tokens=600,
    )

    langue          = (result.get("langue") or "fr").lower().strip()[:5]
    est_francais    = result.get("est_francais", True)
    traduction_fr   = result.get("traduction_fr")

    if est_francais or not traduction_fr:
        return langue, message

    logger.info(f"[TRADUCTEUR] Langue détectée : {langue} → traduction FR appliquée")
    return langue, traduction_fr


def agent0_traduire_reponse(
    reponse_fr: str,
    langue_cible: str,
    openai_client: Any,
) -> str:
    """
    Traduit la réponse de Mathilde du français vers la langue de l'usager.
    Retourne la réponse originale si langue_cible == "fr" ou inconnue.
    """
    if langue_cible in _LANGUES_SANS_TRADUCTION:
        return reponse_fr

    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"{_PROMPT_TRADUCTEUR_RETOUR}\n"
                        f"Langue cible : {langue_cible}"
                    ),
                },
                {"role": "user", "content": reponse_fr},
            ],
            max_tokens=800,
            temperature=0.2,
        )
        traduit = resp.choices[0].message.content.strip()
        logger.info(f"[TRADUCTEUR] Réponse traduite vers '{langue_cible}'")
        return traduit
    except Exception as e:
        logger.warning(f"[TRADUCTEUR] Traduction retour échouée ({langue_cible}) : {e}")
        return reponse_fr   # fallback : réponse française


# ─────────────────────────────────────────────────────────────────────────────
# Utilitaires
# ─────────────────────────────────────────────────────────────────────────────

def _calculer_profil(date_naissance: str | None,
                     situation_pro: str | None = None) -> ProfilMDPH:
    """Calcule le profil légal depuis la date de naissance."""
    if not date_naissance or "/" not in date_naissance:
        return "inconnu"
    try:
        p = date_naissance.split("/")
        if len(p) != 3:
            return "inconnu"
        age = (date.today() - date(int(p[2]), int(p[1]), int(p[0]))).days // 365
        if age <= 15:
            return "enfant"
        if age <= 25:
            return "mixte"   # Règle équipe mixte
        return "adulte"      # > 25 ans — statut actif/inactif porté par SectionD.statut
    except Exception:
        return "inconnu"


def _texte_upper(cerfa: dict, *cles: str) -> str:
    """Concatène plusieurs champs cerfa en majuscules pour la détection de tokens."""
    return " ".join((cerfa.get(c) or "") for c in cles).upper()


def _appeler_llm_json(
    openai_client: Any,
    system_prompt: str,
    user_message: str,
    max_tokens: int = 500,
) -> dict:
    """Appelle le LLM et retourne le JSON parsé. Retourne {} en cas d'erreur."""
    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
            max_tokens=max_tokens,
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content.strip())
    except Exception as e:
        logger.warning(f"[ORCHESTRATEUR] Erreur LLM : {e}")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Protocole de validation des réponses négatives
# ─────────────────────────────────────────────────────────────────────────────

def resoudre_negations(message: str, dossier: DossierCERFA) -> list[str]:
    """
    Détecte les négations dans le message et applique les valeurs sentinelles.
    Interdit la valeur None pour les champs concernés — enregistre False/"Aucun".
    Retourne la liste des champs résolus.
    """
    msg = message.lower()
    resolus: list[str] = []

    # Aidant familial
    if any(p in msg for p in _NEGATIONS_AIDANT):
        if not dossier.section_f.aidant.a_un_aidant:
            dossier.section_f.aidant.a_un_aidant = False
            resolus.append("section_f.aidant.a_un_aidant → False")

    # Protection juridique
    if any(p in msg for p in _NEGATIONS_PROTECTION):
        dossier.section_a.situation_juridique.sous_protection = False
        dossier.section_a.situation_juridique.type_mesure     = "aucune"
        dossier.section_a.situation_juridique.identite_representant = None
        resolus.append("situation_juridique.sous_protection → False")

    # Urgence
    if any(p in msg for p in _NEGATIONS_URGENCE):
        dossier.section_urgence.est_urgent = False
        resolus.append("section_urgence.est_urgent → False")

    # CMI
    if any(p in msg for p in _NEGATIONS_CMI):
        if dossier.section_e:
            dossier.section_e.cmi_priorite     = False
            dossier.section_e.cmi_stationnement = False
            resolus.append("section_e.cmi_* → False")

    # RQTH
    if any(p in msg for p in _NEGATIONS_RQTH):
        if dossier.section_e:
            dossier.section_e.orientation_rqth = False
            resolus.append("section_e.orientation_rqth → False")

    if resolus:
        logger.info(f"[ORCHESTRATEUR] Négations résolues : {resolus}")
    return resolus


# ─────────────────────────────────────────────────────────────────────────────
# Agent 1 — Aiguilleur État-Civil (Sections A & B)
# ─────────────────────────────────────────────────────────────────────────────

_PROMPT_AGENT1 = """
Tu es l'Aiguilleur État-Civil de Facilim, spécialisé MDPH.
Tu collectes UNIQUEMENT les données d'identité et de statut légal.
Tu ne poses JAMAIS de questions sur les difficultés, les soins ou l'emploi.

━━━ RÈGLES ABSOLUES (non négociables) ━━━
1. Le NIR (numéro de sécurité sociale, 15 chiffres) est OBLIGATOIRE pour tout dossier MDPH.
   Ne jamais dire qu'il n'est pas nécessaire. S'il est absent, le demander explicitement.
2. Le numéro d'allocataire CAF ou MSA est OBLIGATOIRE. Le demander s'il est absent.
3. Le mode de contact préféré (email ou courrier) doit toujours être collecté.
4. Si l'usager est en recherche d'emploi, la date de début de sans-emploi est requise.

Extrais les informations suivantes depuis le message de l'usager.
Réponds en JSON avec exactement ces clés (null si absent) :
{
  "nom": null,
  "prenom": null,
  "date_naissance": null,
  "genre": null,
  "adresse_complete": null,
  "situation_familiale": null,
  "enfants_a_charge": null,
  "organisme_payeur": null,
  "numero_allocataire": null,
  "numero_securite_sociale": null,
  "mode_contact": null,
  "historique_mdph": null,
  "type_demande": null,
  "sous_protection_juridique": null,
  "type_mesure_protection": null,
  "nom_representant": null,
  "prenom_representant": null,
  "nom_etablissement_scolaire": null,
  "classe_scolaire": null,
  "a_aesh": null,
  "a_pps": null,
  "gevasco_disponible": null,
  "date_debut_sans_emploi": null
}

Règle de la protection juridique :
- "sous tutelle de mon mari Jean Dupont" → sous_protection_juridique=true,
  type_mesure_protection="tutelle", nom_representant="Dupont", prenom_representant="Jean"
- "je gère seul" | "pas de tuteur" → sous_protection_juridique=false, type_mesure_protection="aucune"
  JAMAIS null pour sous_protection_juridique si le sujet est abordé.

Règle du mode_contact : utilise uniquement "email" ou "courrier".
"""


def agent1_extraire_et_repondre(
    inp: OrchestratorInput,
    dossier: DossierCERFA,
) -> tuple[dict, str]:
    """
    Agent 1 — extrait identité + profil légal, génère la question suivante.
    Retourne (champs_extraits, question_whatsapp).
    """
    extracted = _appeler_llm_json(
        inp.openai_client, _PROMPT_AGENT1, inp.message_whatsapp
    )

    # Mise à jour Section A
    a = dossier.section_a
    _set_if(a, "nom",               extracted.get("nom"))
    _set_if(a, "prenom",            extracted.get("prenom"))
    _set_if(a, "date_naissance",    extracted.get("date_naissance"))
    _set_if(a, "genre",             extracted.get("genre"))
    _set_if(a, "adresse_complete",  extracted.get("adresse_complete"))
    _set_if(a, "situation_familiale", extracted.get("situation_familiale"))
    _set_if(a, "organisme_payeur",  extracted.get("organisme_payeur"))
    _set_if(a, "historique_mdph",     extracted.get("historique_mdph"))
    _set_if(a, "type_demande",        extracted.get("type_demande"))
    _set_if(a, "numero_allocataire",  extracted.get("numero_allocataire"))
    _set_if(a, "mode_contact",        extracted.get("mode_contact"))
    # NIR — validation 15 chiffres avant persistance
    _nir_raw = (extracted.get("numero_securite_sociale") or "").replace(" ", "").replace("-", "")
    if re.fullmatch(r"\d{15}", _nir_raw):
        _set_if(a, "numero_securite_sociale", _nir_raw)

    if extracted.get("enfants_a_charge") is not None:
        try:
            a.enfants_a_charge = int(extracted["enfants_a_charge"])
        except (ValueError, TypeError):
            pass

    # Protection juridique
    _sp = extracted.get("sous_protection_juridique")
    if _sp is not None:
        a.situation_juridique.sous_protection = bool(_sp)
        _tm = extracted.get("type_mesure_protection")
        if _tm in ("tutelle", "curatelle", "sauvegarde"):
            a.situation_juridique.type_mesure = _tm
        elif _sp is False:
            a.situation_juridique.type_mesure = "aucune"
        _nr = extracted.get("nom_representant")
        _pr = extracted.get("prenom_representant")
        if _nr or _pr:
            a.situation_juridique.identite_representant = IdentitePersonne(
                nom    = _nr,
                prenom = _pr,
                qualite = "Tuteur" if a.situation_juridique.type_mesure == "tutelle" else "Curateur",
            )

    # Calcul du profil légal
    if dossier.profil == "inconnu" and a.date_naissance:
        nouveau_profil = _calculer_profil(
            a.date_naissance,
            inp.cerfa_reponses.get("situation_pro_scolaire"),
        )
        if nouveau_profil != "inconnu":
            dossier.profil = nouveau_profil
            dossier.router_profil()   # active/désactive les sections
            logger.info(f"[AGENT1] Profil calculé : {dossier.profil}")

    # date_debut_sans_emploi → section_d si présente
    _dds = extracted.get("date_debut_sans_emploi")
    if _dds and dossier.section_d:
        _set_if(dossier.section_d, "date_debut_sans_emploi", _dds)

    # Section B (enfant / mixte)
    if dossier.section_b:
        _set_if(dossier.section_b, "nom_etablissement", extracted.get("nom_etablissement_scolaire"))
        _set_if(dossier.section_b, "classe_actuelle",   extracted.get("classe_scolaire"))
        if extracted.get("a_aesh") is not None:
            dossier.section_b.a_aesh = bool(extracted["a_aesh"])
        if extracted.get("a_pps") is not None:
            dossier.section_b.a_pps = bool(extracted["a_pps"])
        if extracted.get("gevasco_disponible") is not None:
            dossier.section_b.gevasco_disponible = bool(extracted["gevasco_disponible"])

    # Génération de la prochaine question
    reponse = _generer_question_agent1(dossier, inp)
    return extracted, reponse


def _generer_question_agent1(dossier: DossierCERFA, inp: OrchestratorInput) -> str:
    """
    Génère la question État-Civil adaptée à l'état actuel du dossier.
    Pose les questions UNE PAR UNE dans l'ordre de priorité.
    Le NIR et le n° allocataire sont OBLIGATOIRES — jamais sautés.
    """
    a = dossier.section_a

    # ── Priorité 1 : identité de base ────────────────────────────────────────
    if not a.nom or not a.prenom:
        return (
            "Bonjour 👋 Je suis Mathilde, de l'équipe Facilim.\n"
            "Pour commencer votre dossier MDPH, pouvez-vous me donner "
            "le *nom et prénom complet* de la personne concernée ?"
        )
    if not a.date_naissance:
        return f"Merci {a.prenom}. Quelle est votre *date de naissance* ? (format JJ/MM/AAAA)"

    if not a.adresse_complete:
        return "Quelle est votre *adresse complète* ? (numéro, rue, code postal, ville)"

    if not a.type_demande:
        return (
            "S'agit-il d'une *première demande* à la MDPH, "
            "ou d'un *renouvellement* de droits existants ?"
        )

    if not a.organisme_payeur:
        return "Votre organisme d'allocations familiales : *CAF* ou *MSA* ?"

    # ── Priorité 2 : NIR (OBLIGATOIRE — jamais optionnel) ────────────────────
    if not a.numero_securite_sociale:
        return (
            "J'ai besoin de votre *numéro de sécurité sociale* (15 chiffres).\n"
            "Il est obligatoire pour tout dossier MDPH et figure sur votre carte Vitale."
        )

    # ── Priorité 3 : N° allocataire (OBLIGATOIRE) ────────────────────────────
    if not a.numero_allocataire:
        org = a.organisme_payeur.upper() if a.organisme_payeur else "CAF ou MSA"
        return (
            f"Quel est votre *numéro d'allocataire {org}* ?\n"
            "Il figure sur vos courriers ou votre espace en ligne."
        )

    # ── Priorité 4 : Mode de contact préféré ─────────────────────────────────
    if not a.mode_contact:
        return (
            "Préférez-vous être contacté·e par *email* ou par *courrier postal* "
            "pour les échanges avec la MDPH ?"
        )

    # ── Priorité 5 : Date début sans-emploi (si profil recherche) ────────────
    if dossier.section_d and dossier.section_d.statut == "recherche":
        if not dossier.section_d.date_debut_sans_emploi:
            return (
                "Depuis quelle date êtes-vous en recherche d'emploi ?\n"
                "(format JJ/MM/AAAA)"
            )

    # ── Priorité 6 : Scolarité (enfant / mixte) ──────────────────────────────
    if dossier.profil in ("enfant", "mixte") and dossier.section_b:
        b = dossier.section_b
        if not b.nom_etablissement:
            return (
                "📚 Dans quel établissement scolaire est scolarisé·e votre enfant ?\n"
                "(Indiquez le nom exact de l'école ou de l'établissement)"
            )
        if b.gevasco_disponible is None:
            return (
                "Avez-vous un document *GEVASCO* récent pour votre enfant ? (oui / non)\n"
                "Ce document décrit ses besoins à l'école."
            )

    return "✅ Les informations d'identité sont complètes. Passons à votre quotidien."


# ─────────────────────────────────────────────────────────────────────────────
# Agent 2 — Spécialiste Autonomie & Aidants (Sections C & F)
# ─────────────────────────────────────────────────────────────────────────────

_PROMPT_AGENT2 = """
Tu es le Spécialiste Autonomie de Facilim, spécialisé MDPH.
Tu collectes les difficultés du quotidien et l'environnement d'aide de l'usager.

RÈGLE ABSOLUE AIDANT (inviolable) :
Si l'usager mentionne qu'un proche l'aide (mari, femme, enfant, parent, voisin…),
cette information va EXCLUSIVEMENT dans les champs "aidant_*".
Elle ne doit JAMAIS apparaître dans "frais_reels".

RÈGLE FRAIS (inviolable) :
"frais_reels" = uniquement des sommes d'argent payées (matériel, soins privés non remboursés).
INTERDIT : aide gratuite d'un proche, prestations CAF/MSA, allocations.

RÈGLE URGENCE :
Si l'usager dit "pas d'urgence" ou toute négation → urgence_droits = false.
Ne jamais supposer l'urgence par défaut.

Extrais en JSON (null si absent) :
{
  "difficultes_quotidiennes": null,
  "utilise_fauteuil_roulant": null,
  "difficulte_marcher": null,
  "besoin_aide_toilette": null,
  "besoins_aide_humaine": null,
  "besoins_aide_technique": null,
  "besoins_amenagement_logement": null,
  "type_logement": null,
  "statut_occupation": null,
  "ressources_actuelles": null,
  "frais_reels": null,
  "urgence_droits": null,
  "aidant_a_un_aidant": null,
  "aidant_nom": null,
  "aidant_prenom": null,
  "aidant_lien_parental": null,
  "aidant_nature_aide": null
}

Pour statut_occupation, utilise uniquement : "proprietaire", "locataire", "heberge".
"""


def agent2_extraire_et_repondre(
    inp: OrchestratorInput,
    dossier: DossierCERFA,
) -> tuple[dict, str]:
    """Agent 2 — extrait vie quotidienne + aidant, génère la question suivante."""
    extracted = _appeler_llm_json(
        inp.openai_client, _PROMPT_AGENT2, inp.message_whatsapp
    )

    # Mise à jour Section C
    c = dossier.section_c
    _set_if(c, "difficultes_quotidiennes", extracted.get("difficultes_quotidiennes"))
    _set_if(c, "type_logement",            extracted.get("type_logement"))
    _set_if(c, "ressources_actuelles",     extracted.get("ressources_actuelles"))
    _set_if(c, "frais_reels",              extracted.get("frais_reels"))

    if extracted.get("statut_occupation") in ("proprietaire", "locataire", "heberge"):
        c.statut_occupation = extracted["statut_occupation"]

    for bool_champ in (
        "utilise_fauteuil_roulant", "difficulte_marcher", "besoin_aide_toilette",
        "besoins_aide_humaine", "besoins_aide_technique", "besoins_amenagement_logement",
    ):
        val = extracted.get(bool_champ)
        if val is not None:
            setattr(c, bool_champ, bool(val))

    # Urgence — False si négation explicite dans le message
    _urg = extracted.get("urgence_droits")
    if _urg is not None:
        dossier.section_urgence.est_urgent = bool(_urg)
    else:
        _msg_low = inp.message_whatsapp.lower()
        if any(p in _msg_low for p in _NEGATIONS_URGENCE):
            dossier.section_urgence.est_urgent = False

    # Mise à jour Section F — Aidant familial
    f = dossier.section_f
    _a_un = extracted.get("aidant_a_un_aidant")
    if _a_un is not None:
        f.aidant.a_un_aidant = bool(_a_un)
        if bool(_a_un):
            _set_if(f.aidant, "nom",           extracted.get("aidant_nom"))
            _set_if(f.aidant, "prenom",        extracted.get("aidant_prenom"))
            _set_if(f.aidant, "lien_parental", extracted.get("aidant_lien_parental"))
            _set_if(f.aidant, "nature_aide",   extracted.get("aidant_nature_aide"))
    elif any(p in inp.message_whatsapp.lower() for p in _NEGATIONS_AIDANT):
        f.aidant.a_un_aidant = False

    reponse = _generer_question_agent2(dossier, inp)
    return extracted, reponse


def _generer_question_agent2(dossier: DossierCERFA, inp: OrchestratorInput) -> str:
    c = dossier.section_c
    f = dossier.section_f

    if not c.difficultes_quotidiennes:
        _sujet = "votre enfant" if dossier.profil == "enfant" else "vous"
        return (
            f"Merci pour ces informations. Maintenant, parlez-moi du quotidien de {_sujet} :\n\n"
            "• Quelles sont les principales difficultés ? "
            "(ce qu'il/elle ne peut pas faire seul·e, ce qui est épuisant ou douloureux)\n"
            "• De quelle aide a-t-il/elle besoin ? (humaine, matériel, aménagement…)"
        )

    if f.aidant.a_un_aidant is False and not f.aidant.nom:
        # a_un_aidant pas encore résolu
        if not hasattr(f.aidant, "_question_posee"):
            return (
                "Est-ce que quelqu'un vous aide régulièrement au quotidien ?\n"
                "(un proche, un conjoint, un parent…)\n"
                "Si oui, indiquez son prénom, nom et son lien avec vous.\n"
                "Si non, répondez simplement 'personne'."
            )

    if c.statut_occupation is None and not dossier.profil == "enfant":
        return (
            "Concernant votre logement :\n"
            "• Êtes-vous propriétaire, locataire ou hébergé·e ?"
        )

    return "✅ Les informations sur votre quotidien sont complètes."


# ─────────────────────────────────────────────────────────────────────────────
# Agent 3 — Conseiller Orientation & Emploi (Sections D & E)
# ─────────────────────────────────────────────────────────────────────────────

_PROMPT_AGENT3 = f"""
Tu es le Conseiller Orientation & Emploi de Facilim, spécialisé MDPH.
Tu traites UNIQUEMENT le parcours professionnel et les orientations demandées.
Tu ne poses JAMAIS de questions sur les difficultés quotidiennes ou l'identité.

RÈGLE ESRP (alias obligatoires) :
Les mots suivants signifient tous ESRP → orientation_esrp = true :
{', '.join(sorted(TOKENS_ESRP))}

RÈGLE ESPO (projet non défini) :
Les expressions suivantes signifient que le projet est à construire → orientation_espo = true :
"je ne sais pas", "trouver ma voie", "pas encore défini", "en réflexion",
"orientation à définir", "sans projet précis", "cherche sa voie"

RÈGLE EXCLUSIVE :
Le projet professionnel (CRP, ESRP, formation) va dans "projet_professionnel".
Il ne doit JAMAIS polluer "difficultes_quotidiennes".

Extrais en JSON (null si absent) :
{{
  "statut_pro": null,
  "nom_employeur": null,
  "poste_occupe": null,
  "niveau_qualification": null,
  "accident_travail": null,
  "type_droits": null,
  "cmi_priorite": null,
  "cmi_stationnement": null,
  "emploi_accompagne": null,
  "projet_professionnel": null,
  "orientation_esrp": null,
  "orientation_espo": null,
  "orientation_esat": null,
  "orientation_rqth": null,
  "orientation_ea": null
}}

Pour "type_droits", retourne une liste de chaînes : ["RQTH", "AAH", "ORP"…]
Pour "statut_pro", utilise : "emploi", "recherche", "formation", "inactif", "retraite"
"""


def agent3_extraire_et_repondre(
    inp: OrchestratorInput,
    dossier: DossierCERFA,
) -> tuple[dict, str]:
    """
    Agent 3 — extrait parcours pro + orientations, génère la question suivante.
    S'active uniquement pour profil 'adulte' et 'mixte'.
    """
    if dossier.profil not in ("adulte", "mixte"):
        logger.warning(f"[AGENT3] Appelé pour profil {dossier.profil} — ignoré.")
        return {}, "✅ Section professionnelle non applicable à ce profil."

    extracted = _appeler_llm_json(
        inp.openai_client, _PROMPT_AGENT3, inp.message_whatsapp
    )

    # Mise à jour Section D
    if dossier.section_d:
        d = dossier.section_d
        if extracted.get("statut_pro") in (
            "emploi", "recherche", "formation", "inactif", "retraite"
        ):
            d.statut = extracted["statut_pro"]
        _set_if(d, "nom_employeur",        extracted.get("nom_employeur"))
        _set_if(d, "poste_occupe",         extracted.get("poste_occupe"))
        _set_if(d, "niveau_qualification", extracted.get("niveau_qualification"))
        if extracted.get("accident_travail") is not None:
            d.accident_travail = bool(extracted["accident_travail"])

    # Mise à jour Section E
    if dossier.section_e:
        e = dossier.section_e
        _droits = extracted.get("type_droits")
        if isinstance(_droits, list):
            e.type_droits = _droits
        elif isinstance(_droits, str) and _droits:
            e.type_droits = [d.strip() for d in _droits.split(",") if d.strip()]

        _set_if(e, "projet_professionnel", extracted.get("projet_professionnel"))

        for bool_champ in ("cmi_priorite", "cmi_stationnement", "emploi_accompagne"):
            val = extracted.get(bool_champ)
            if val is not None:
                setattr(e, bool_champ, bool(val))

        # ── Règles 2 & 3 : détection automatique des orientations ────────────
        _texte = (inp.message_whatsapp + " " + (extracted.get("projet_professionnel") or "")).upper()

        # Règle 3 — ESRP (Richebois, Visa Pro, CRP…)
        if extracted.get("orientation_esrp") or any(t in _texte for t in TOKENS_ESRP):
            e.orientation_esrp = True
            logger.info(f"[AGENT3] orientation_esrp = True (token ESRP détecté)")

        # Règle 2 — ESPO (projet non défini)
        if extracted.get("orientation_espo") or any(t in _texte for t in TOKENS_ESPO):
            e.orientation_espo = True
            logger.info(f"[AGENT3] orientation_espo = True (projet non défini)")

        # ESAT (mutuellement exclusif avec ESRP — ESAT prime)
        if extracted.get("orientation_esat") or any(t in _texte for t in TOKENS_ESAT):
            if e.orientation_esrp:
                logger.warning("[AGENT3] ESRP + ESAT tous deux détectés — ESAT prime.")
                e.orientation_esrp = False
            e.orientation_esat = True

        # RQTH
        if extracted.get("orientation_rqth") or any(t in _texte for t in TOKENS_RQTH):
            e.orientation_rqth = True

        # Entreprise adaptée
        if extracted.get("orientation_ea") or any(t in _texte for t in TOKENS_EA):
            e.orientation_ea = True

    reponse = _generer_question_agent3(dossier, inp)
    return extracted, reponse


def _generer_question_agent3(dossier: DossierCERFA, inp: OrchestratorInput) -> str:
    d = dossier.section_d
    e = dossier.section_e

    if d and not d.statut:
        return (
            "Quelques questions sur votre parcours professionnel :\n\n"
            "• Quelle est votre situation actuelle ?\n"
            "  (en emploi, en recherche d'emploi, en formation, sans activité…)\n"
            "• Quel est votre niveau de formation et votre dernier métier ?"
        )

    if e and not e.type_droits:
        return (
            "Quels droits souhaitez-vous demander à la MDPH ?\n\n"
            "Exemples : RQTH, AAH, ORP (orientation professionnelle), "
            "CMI (carte mobilité), PCH, orientation ESAT/ESRP…\n\n"
            "Si vous n'êtes pas sûr·e, décrivez simplement votre projet "
            "ou vos besoins et je trouverai les droits correspondants."
        )

    return "✅ Les informations professionnelles sont complètes."


# ─────────────────────────────────────────────────────────────────────────────
# Utilitaire : mise à jour conditionnelle
# ─────────────────────────────────────────────────────────────────────────────

def _set_if(obj: Any, attr: str, value: Any) -> None:
    """Met à jour obj.attr uniquement si value est non-None et que le champ est vide."""
    if value is None:
        return
    current = getattr(obj, attr, None)
    if not current:
        setattr(obj, attr, value)


# ─────────────────────────────────────────────────────────────────────────────
# TTS — Synthèse vocale multilingue (OpenAI tts-1)
# ─────────────────────────────────────────────────────────────────────────────

# Mapping langue cible → voix OpenAI TTS
# Voix disponibles : alloy, echo, fable, onyx, nova, shimmer
# Choix guidé par la naturalité dans chaque langue (tests empiriques)
_LANGUE_VERS_VOIX: dict[str, str] = {
    "français":   "alloy",     # neutre, clair, bon accent français
    "anglais":    "onyx",      # voix grave et articulée
    "arabe":      "nova",      # claire et bien articulée
    "espagnol":   "shimmer",   # naturelle, bonne prosodie
    "portugais":  "echo",      # fluide
    "italien":    "alloy",
    "allemand":   "echo",
    "turc":       "nova",
    "roumain":    "alloy",
    "russe":      "echo",
    "mandarin":   "nova",      # bonne clarté tonale
    "autre":      "alloy",     # fallback neutre
}


def generer_tts(
    texte: str,
    langue_cible: str,
    openai_client: Any,
) -> bytes | None:
    """
    Génère un fichier audio MP3 depuis le texte via l'API OpenAI TTS (tts-1).
    Sélectionne automatiquement la voix la plus adaptée à la langue cible.

    Args:
        texte         : Texte à synthétiser (réponse de Mathilde déjà traduite).
        langue_cible  : ConfigurationLangue (ex: "arabe", "espagnol"…).
        openai_client : Instance openai.OpenAI.

    Returns:
        Contenu audio en bytes (MP3), ou None si la synthèse échoue.
    """
    if not texte or not texte.strip():
        return None

    voix = _LANGUE_VERS_VOIX.get(langue_cible, "alloy")
    # Tronquer à 4096 caractères — limite OpenAI TTS
    texte_tts = texte[:4096]

    try:
        response = openai_client.audio.speech.create(
            model  = "tts-1",
            voice  = voix,
            input  = texte_tts,
            response_format = "mp3",
        )
        audio_bytes = response.content
        logger.info(
            f"[TTS] Synthèse OK | langue={langue_cible} | voix={voix} "
            f"| {len(texte_tts)} chars → {len(audio_bytes)} octets"
        )
        return audio_bytes
    except Exception as e:
        logger.warning(f"[TTS] Synthèse échouée pour langue={langue_cible} : {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrateur principal
# ─────────────────────────────────────────────────────────────────────────────

def orchestrer(inp: OrchestratorInput) -> OrchestratorOutput:
    """
    Point d'entrée unique — distribue le message au bon agent et retourne
    la réponse WhatsApp dans la langue de l'usager + le DossierCERFA mis à jour.

    Flux multilingue :
      message (toute langue) → Agent 0 → message_fr → Agents 1/2/3
      reponse_fr → Agent 0 → reponse (langue usager) → WhatsApp

    Routage métier :
      Agent 1 → profil inconnu OU section_a incomplète
      Agent 2 → profil connu ET section_c incomplète
      Agent 3 → profil adulte/mixte ET sections D/E incomplètes
    """
    # Initialiser le dossier si absent
    dossier = inp.dossier_cerfa or DossierCERFA()

    # ── Étape 0 : Agent Traducteur — détection langue + traduction entrante ──
    langue_detectee, message_fr = agent0_detecter_langue(
        inp.message_whatsapp, inp.openai_client
    )
    # Mettre à jour ConfigurationDossier (source de vérité de la session)
    if langue_detectee and langue_detectee not in ("unknown", ""):
        _langue_nom = iso_vers_langue(langue_detectee)
        dossier.configuration.langue_cible = _langue_nom
        # Synchroniser aussi langue_usager (ISO) dans section_a pour compatibilité
        dossier.section_a.langue_usager = langue_detectee
    # Canal vocal → mise à jour du canal cible
    if inp.est_message_vocal:
        dossier.configuration.canal_cible = "vocal"
        dossier.section_a.canal_prefere_vocal = True
    # Remplacer le message par sa version française — transparent pour les agents
    inp.message_whatsapp = message_fr

    # ── Étape 1 : Protocole réponses négatives (sur le message FR) ───────────
    negatifs_resolus = resoudre_negations(message_fr, dossier)

    # ── Étape 2 : Sélection de l'agent actif ────────────────────────────────
    a = dossier.section_a
    _section_a_incomplete = not a.nom or not a.prenom or not a.date_naissance

    if dossier.profil == "inconnu" or _section_a_incomplete:
        agent_id = "aiguilleur"
        extracted, reponse = agent1_extraire_et_repondre(inp, dossier)

    elif not dossier.section_c.difficultes_quotidiennes or (
        dossier.section_f.aidant.a_un_aidant is False
        and not dossier.section_f.aidant.nom
        and not any(p in inp.message_whatsapp.lower() for p in _NEGATIONS_AIDANT)
    ):
        agent_id = "autonomie"
        extracted, reponse = agent2_extraire_et_repondre(inp, dossier)

    elif dossier.profil in ("adulte", "mixte") and (
        (dossier.section_d and not dossier.section_d.statut)
        or (dossier.section_e and not dossier.section_e.type_droits)
    ):
        agent_id = "orientation"
        extracted, reponse = agent3_extraire_et_repondre(inp, dossier)

    else:
        # Tous les agents sont satisfaits — vérifier les champs manquants résiduels
        agent_id = "aucun"
        manquants = dossier.champs_obligatoires_manquants()
        if manquants:
            reponse = (
                f"Il manque encore quelques informations :\n"
                + "\n".join(f"• {m}" for m in manquants)
            )
        else:
            reponse = (
                "✅ Toutes les informations ont bien été collectées.\n\n"
                "Le dossier est en cours de finalisation. Vous recevrez le CERFA pré-rempli "
                "par email sous peu.\n\nBien cordialement, l'équipe Facilim."
            )
        extracted = {}

    # ── Étape 3 : Moteur de règles ───────────────────────────────────────────
    dossier.cases_cerfa = executer_regles_metier_mdph(dossier)

    # ── Étape 4a : Traduction retour vers la langue de l'usager ─────────────
    _code_iso_retour = langue_vers_iso(dossier.configuration.langue_cible)
    reponse_finale = agent0_traduire_reponse(
        reponse_fr    = reponse,
        langue_cible  = _code_iso_retour,
        openai_client = inp.openai_client,
    )

    # ── Étape 4b : TTS si canal_cible == "vocal" ─────────────────────────────
    audio_bytes: bytes | None = None
    if dossier.configuration.canal_cible == "vocal":
        audio_bytes = generer_tts(
            texte         = reponse_finale,
            langue_cible  = dossier.configuration.langue_cible,
            openai_client = inp.openai_client,
        )

    logger.info(
        f"[ORCHESTRATEUR] agent={agent_id} | profil={dossier.profil} "
        f"| langue={dossier.configuration.langue_cible} ({_code_iso_retour}) "
        f"| canal={dossier.configuration.canal_cible} "
        f"| tts={'oui' if audio_bytes else 'non'} "
        f"| manquants={dossier.champs_obligatoires_manquants()}"
    )

    return OrchestratorOutput(
        dossier_cerfa           = dossier,
        reponse_whatsapp        = reponse_finale,
        agent_ayant_repondu     = agent_id,
        langue_detectee         = langue_detectee,
        message_traduit_fr      = message_fr,
        audio_bytes             = audio_bytes,
        champs_negatifs_resolus = negatifs_resolus,
        champs_extraits         = extracted,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Point d'entrée compatible avec l'interface existante de main.py
# ─────────────────────────────────────────────────────────────────────────────

def traiter_message_whatsapp(
    message_entrant: str,
    historique: list[dict],
    cerfa_reponses: dict,
    openai_client: Any,
    dossier_cerfa: Optional[DossierCERFA] = None,
) -> tuple[str, DossierCERFA]:
    """
    Interface publique appelée depuis main.py.
    Retourne (reponse_whatsapp, dossier_cerfa_mis_a_jour).
    """
    inp = OrchestratorInput(
        message_whatsapp = message_entrant,
        cerfa_reponses   = cerfa_reponses,
        historique       = historique,
        openai_client    = openai_client,
        dossier_cerfa    = dossier_cerfa,
    )
    out = orchestrer(inp)
    return out.reponse_whatsapp, out.dossier_cerfa
