"""
app/engines/cerfa_narrative_engine.py — Moteur de rédaction narrative CERFA.

Transforme les données brutes collectées en textes rédigés exploitables par
l'équipe pluridisciplinaire MDPH.

RÈGLE ABSOLUE : préremplir ce qui est déclaré, jamais inventer ce qui est supposé.
Si une information est absente → la signaler avec [INFO MANQUANTE : nom_champ].
Aucune inférence, aucune extrapolation à partir de suppositions.

Chaque texte répond aux 6 questions obligatoires :
  1. Quelles sont les difficultés ?
  2. Depuis quand ?
  3. Quelles conséquences concrètes ?
  4. Quelles limitations fonctionnelles ?
  5. Quels besoins de compensation ?
  6. Quelles attentes vis-à-vis de la MDPH ?
"""

from __future__ import annotations

import logging
from typing import Any

from app.engines.verbatim_engine import (
    formater_verbatim_pour_prompt,
    formater_chronologie_pour_prompt,
)
from app.engines.profil_specifique_engine import formater_axes_retentissement


def _formater_document_knowledge(donnees: dict, champs: list[str]) -> str:
    """
    Sprint P0.2 — H2.
    Formate les informations extraites des documents pour injection dans les prompts.
    Aucune inférence — uniquement les données réellement extraites.
    Chaque item conserve sa valeur telle qu'extraite.
    """
    dk = donnees.get("_document_knowledge") or {}
    if not dk:
        return ""

    _LABELS = {
        "limitations_fonctionnelles": "LIMITATIONS FONCTIONNELLES",
        "restrictions_medicales":     "RESTRICTIONS MÉDICALES",
        "freins":                     "FREINS IDENTIFIÉS",
        "projets":                    "PROJETS ET ORIENTATIONS",
        "verbatim":                   "PAROLES DE LA PERSONNE",
        "chronologie":                "CHRONOLOGIE",
        "besoins":                    "BESOINS IDENTIFIÉS",
        "ressources":                 "RESSOURCES ET CAPACITÉS",
    }

    lignes: list[str] = []
    for champ in champs:
        items = dk.get(champ, [])
        if not items:
            continue
        lignes.append(f"\n{_LABELS.get(champ, champ.upper())} (depuis le bilan transmis) :")
        for item in items[:10]:
            valeur = item.get("valeur", "") if isinstance(item, dict) else str(item)
            if valeur:
                lignes.append(f"  - {valeur}")

    if not lignes:
        return ""

    return (
        "\n\nINFORMATIONS DOCUMENTAIRES"
        " (extraites du bilan professionnel transmis — à utiliser prioritairement) :"
        + "".join(lignes)
        + "\n"
    )

logger = logging.getLogger("facilim.engines.cerfa_narrative")

# ── Pronoms par profil ────────────────────────────────────────────────────────

_PRONOMS = {
    "adulte": {
        "sujet":   "je",
        "possessif": "mon/ma/mes",
        "reflexif": "me",
        "exemple_diff": "Je rencontre des difficultés pour",
        "exemple_aide": "J'ai besoin d'aide pour",
        "exemple_attente": "J'attends de la MDPH",
    },
    "mixte": {
        "sujet":   "je",
        "possessif": "mon/ma/mes",
        "reflexif": "me",
        "exemple_diff": "Je rencontre des difficultés pour",
        "exemple_aide": "J'ai besoin d'aide pour",
        "exemple_attente": "J'attends de la MDPH",
    },
    "enfant": {
        "sujet":   "il/elle",
        "possessif": "son/sa/ses",
        "reflexif": "se",
        "exemple_diff": "[PRÉNOM] rencontre des difficultés pour",
        "exemple_aide": "[PRÉNOM] a besoin d'aide pour",
        "exemple_attente": "Ses parents attendent de la MDPH",
    },
    "protege": {
        "sujet":   "M./Mme [NOM]",
        "possessif": "son/sa/ses",
        "reflexif": "se",
        "exemple_diff": "M./Mme [NOM] rencontre des difficultés pour",
        "exemple_aide": "M./Mme [NOM] a besoin d'aide pour",
        "exemple_attente": "Le représentant légal attend de la MDPH",
    },
}

# ── Domaines à explorer par section ──────────────────────────────────────────

_DOMAINES_B = [
    "déplacements et mobilité",
    "autonomie dans les actes essentiels (se lever, se laver, s'habiller)",
    "sommeil et repos",
    "hygiène corporelle",
    "alimentation et repas",
    "tâches ménagères et entretien du domicile",
    "gestion administrative et financière",
    "vie sociale et relations",
    "communication et expression",
]

_DOMAINES_C = [
    "difficultés d'apprentissage et de mémorisation",
    "attention et concentration",
    "comportement et régulation émotionnelle",
    "fatigue et endurance scolaire",
    "accompagnements en place (AESH, PPS, GEVASCO)",
    "besoins d'aménagements pédagogiques",
]

_DOMAINES_D = [
    "maintien dans l'emploi actuel",
    "restrictions médicales ou fonctionnelles au travail",
    "fatigabilité professionnelle",
    "besoins d'aménagement du poste",
    "projet de reconversion ou de formation",
    "besoin d'accompagnement ESRP ou emploi accompagné",
]

_DOMAINES_E = [
    "besoins de compensation exprimés",
    "attentes concrètes vis-à-vis de la MDPH",
    "objectifs de vie à court et moyen terme",
    "souhaits en matière d'orientation et d'accompagnement",
    "projet de vie global (logement, activité, lien social)",
]

# ── Marqueurs de supposition interdits ───────────────────────────────────────

_MARQUEURS_SUPPOSITION = [
    "probablement", "sans doute", "il est possible que", "on peut penser que",
    "il est probable", "vraisemblablement", "il semblerait", "peut-être que",
    "il est vraisemblable", "on suppose", "il est supposé",
]


def _detecter_supposition(texte: str) -> list[str]:
    """Retourne les marqueurs de supposition trouvés dans le texte généré."""
    return [m for m in _MARQUEURS_SUPPOSITION if m.lower() in texte.lower()]


def _resoudre_pronoms(profil_mdph: str, donnees: dict[str, Any]) -> dict[str, str]:
    """Résout les pronoms + remplace [PRÉNOM] et [NOM] par les valeurs réelles."""
    base = _PRONOMS.get(profil_mdph, _PRONOMS["adulte"]).copy()
    nom_complet = str(donnees.get("nom_prenom", "") or "")
    if nom_complet:
        parties = nom_complet.strip().split()
        prenom = parties[0] if parties else "la personne"
        nom    = parties[-1] if len(parties) > 1 else ""
        civilite = "M." if str(donnees.get("genre", "")).lower() in ("homme", "m", "masculin") else "Mme"
        for cle in base:
            base[cle] = (
                base[cle]
                .replace("[PRÉNOM]", prenom)
                .replace("[NOM]", nom)
                .replace("M./Mme", civilite)
            )
    return base


# ── Prompts de génération par section ────────────────────────────────────────

def _prompt_section_b(donnees: dict, pronoms: dict, profil_handicap: str) -> str:
    impact = donnees.get("impact_quotidien", "") or ""
    aides  = donnees.get("aides_en_place", "") or donnees.get("detail_aide_humaine", "") or ""
    diags  = donnees.get("diagnostics", "") or ""
    frais  = donnees.get("frais_restant_charge", "") or ""

    verbatim_b    = formater_verbatim_pour_prompt(donnees, "b")
    chronologie   = formater_chronologie_pour_prompt(donnees)
    axes_specifiques_b = formater_axes_retentissement(donnees, "b")
    # Sprint P0.2 — H2 : données documentaires (limitations, restrictions, freins)
    doc_knowledge_b = _formater_document_knowledge(donnees, [
        "limitations_fonctionnelles", "restrictions_medicales",
        "freins", "chronologie", "verbatim",
    ])
    domaines_str  = "\n".join(f"  - {d}" for d in _DOMAINES_B)
    sujet    = pronoms["sujet"]
    ex_diff  = pronoms["exemple_diff"]
    ex_aide  = pronoms["exemple_aide"]

    return f"""Tu es un rédacteur expert en dossiers MDPH. Tu dois rédiger la PARTIE B — Vie quotidienne.

RÈGLE ABSOLUE : utilise UNIQUEMENT les informations ci-dessous.
Si une information est absente, écris exactement : [INFO MANQUANTE : nom_du_domaine]
N'invente rien. N'infère rien. Ne suppose rien.
{doc_knowledge_b}{verbatim_b}{chronologie}
INFORMATIONS STRUCTURÉES DÉCLARÉES :
- Diagnostic(s) : {diags or "[INFO MANQUANTE : diagnostics]"}
- Impact quotidien déclaré : {impact or "[INFO MANQUANTE : impact_quotidien]"}
- Aides en place : {aides or "[INFO MANQUANTE : aides_en_place]"}
- Frais restant à charge : {frais or "non renseigné"}
- Profil handicap détecté : {profil_handicap or "non identifié"}

PRONOMS À UTILISER : {sujet} (ex : "{ex_diff}...", "{ex_aide}...")

RÈGLE VERBATIM : si un verbatim décrit une situation concrète, intègre-le dans le texte.
Tu peux le reformuler ou le citer entre guillemets : «comme elle l'exprime elle-même : "..."»
La parole directe de la personne prime sur la reformulation clinique.

{axes_specifiques_b}CONSIGNE DE RÉDACTION — STRICTE (anti-invention) :
Décris UNIQUEMENT les difficultés et limitations EXPLICITEMENT présentes dans les informations ci-dessus, en t'appuyant d'abord sur les mots de la personne (verbatim).
- N'introduis JAMAIS un acte ni une aide (toilette, habillage, repas, douche, déplacements, fauteuil roulant, aidant, aménagement du logement, etc.) s'il n'est pas écrit explicitement dans les informations.
- Ne déduis AUCUNE dépendance à partir d'un diagnostic, d'une douleur ou d'une fatigue. Une fatigue déclarée ne signifie pas un besoin d'aide pour se laver.
- Si une dimension n'est pas renseignée, NE L'ÉVOQUE PAS. Tu n'es PAS obligé de couvrir tous les domaines.
- AUCUNE longueur imposée : sois aussi bref que le permettent les informations réelles. Trois phrases vraies valent mieux qu'un paragraphe inventé.

FORMAT : paragraphes continus, sans liste à puces.
"""


def _prompt_section_c(donnees: dict, pronoms: dict) -> str:
    scol   = donnees.get("situation_scolaire", "") or ""
    etab   = donnees.get("etablissement_scolaire", "") or ""
    impact = donnees.get("impact_quotidien", "") or ""
    diags  = donnees.get("diagnostics", "") or ""

    verbatim_c  = formater_verbatim_pour_prompt(donnees, "c")
    chronologie = formater_chronologie_pour_prompt(donnees)
    domaines_str = "\n".join(f"  - {d}" for d in _DOMAINES_C)
    sujet   = pronoms["sujet"]
    ex_diff = pronoms["exemple_diff"]

    return f"""Tu es un rédacteur expert en dossiers MDPH. Tu dois rédiger la PARTIE C — Scolarité et formation.

RÈGLE ABSOLUE : utilise UNIQUEMENT les informations ci-dessous.
Si une information est absente → [INFO MANQUANTE : nom_du_domaine]
N'invente rien. N'infère rien.
{verbatim_c}{chronologie}
INFORMATIONS STRUCTURÉES DÉCLARÉES :
- Situation scolaire : {scol or "[INFO MANQUANTE : situation_scolaire]"}
- Établissement : {etab or "[INFO MANQUANTE : etablissement_scolaire]"}
- Diagnostic(s) : {diags or "[INFO MANQUANTE : diagnostics]"}
- Impact général déclaré : {impact or "[INFO MANQUANTE : impact_quotidien]"}

PRONOMS : {sujet} (ex : "{ex_diff}...")

RÈGLE VERBATIM : si un verbatim décrit une situation scolaire concrète, intègre-le.
La parole du représentant légal sur la réalité scolaire de l'enfant prime sur la description clinique.

STRUCTURE OBLIGATOIRE :
1. Situation scolaire actuelle et son évolution dans le temps (utiliser la chronologie)
2. Conséquences du handicap sur la scolarité dans les domaines suivants (si déclarés) :
{domaines_str}
3. Accompagnements en place et leur efficacité
4. Besoins d'aménagements complémentaires

FORMAT : paragraphes continus.
LONGUEUR CIBLE : 250 à 400 mots si les informations le permettent.
"""


def _prompt_section_d(donnees: dict, pronoms: dict) -> str:
    statut   = donnees.get("statut_emploi", "") or ""
    projet   = donnees.get("projet_professionnel", "") or ""
    impact   = donnees.get("impact_quotidien", "") or ""
    diags    = donnees.get("diagnostics", "") or ""
    cons_pro = donnees.get("consequences_professionnelles", "") or ""

    verbatim_d  = formater_verbatim_pour_prompt(donnees, "d")
    chronologie = formater_chronologie_pour_prompt(donnees)
    domaines_str = "\n".join(f"  - {d}" for d in _DOMAINES_D)
    sujet = pronoms["sujet"]
    # Sprint P0.2 — H2 : projets, orientations, restrictions pro depuis les documents
    doc_knowledge_d = _formater_document_knowledge(donnees, [
        "projets", "freins", "restrictions_medicales", "chronologie",
    ])

    return f"""Tu es un rédacteur expert en dossiers MDPH. Tu dois rédiger la PARTIE D — Situation professionnelle.

RÈGLE ABSOLUE : utilise UNIQUEMENT les informations ci-dessous.
Si une information est absente → [INFO MANQUANTE : nom_du_domaine]
N'invente rien. N'infère rien.
{doc_knowledge_d}{verbatim_d}{chronologie}
INFORMATIONS STRUCTURÉES DÉCLARÉES :
- Statut professionnel : {statut or "[INFO MANQUANTE : statut_emploi]"}
- Projet professionnel : {projet or "non renseigné"}
- Conséquences professionnelles déclarées : {cons_pro or "non renseigné"}
- Diagnostic(s) : {diags or "[INFO MANQUANTE : diagnostics]"}
- Impact général : {impact or "non renseigné"}

PRONOMS : {sujet}

RÈGLE VERBATIM : si un verbatim décrit des difficultés professionnelles concrètes, intègre-le.
La parole de la personne sur son vécu au travail prime sur la description clinique.

STRUCTURE OBLIGATOIRE :
1. Situation professionnelle actuelle et son évolution (utiliser la chronologie déclarée)
2. Conséquences du handicap sur l'activité professionnelle dans les domaines suivants :
{domaines_str}
3. Restrictions ou inaptitudes déclarées
4. Projet professionnel et besoins d'accompagnement

FORMAT : paragraphes continus.
LONGUEUR CIBLE : 300 à 500 mots si les informations le permettent.
"""


def _prompt_section_e(donnees: dict, pronoms: dict, profil_mdph: str) -> str:
    droits           = donnees.get("droits_demandes", "") or ""
    projet_vie       = donnees.get("projet_orientation", "") or donnees.get("projet_professionnel", "") or ""
    diags            = donnees.get("diagnostics", "") or ""
    impact           = donnees.get("impact_quotidien", "") or ""
    attentes         = donnees.get("attentes_mdph", "") or ""
    besoins          = donnees.get("besoins_compensation", "") or ""
    expression_dir   = donnees.get("expression_directe", "") or ""

    # PRIORITÉ 1 : expression directe
    # PRIORITÉ 2 : verbatim_e cumulatif
    # PRIORITÉ 3 : données structurées
    verbatim_e  = formater_verbatim_pour_prompt(donnees, "e")
    chronologie = formater_chronologie_pour_prompt(donnees)
    axes_specifiques_e = formater_axes_retentissement(donnees, "e")
    # Sprint P0.2 — H2 : besoins, projets, verbatim depuis les documents
    doc_knowledge_e = _formater_document_knowledge(donnees, [
        "besoins", "projets", "verbatim", "ressources",
    ])
    domaines_str = "\n".join(f"  - {d}" for d in _DOMAINES_E)
    sujet      = pronoms["sujet"]
    ex_attente = pronoms["exemple_attente"]

    # Bloc expression directe — affiché en premier si présent
    _bloc_expression = ""
    if expression_dir.strip():
        _bloc_expression = (
            f"\n⭐ EXPRESSION DIRECTE DE LA PERSONNE (priorité absolue — "
            f"c'est le cœur du projet de vie) :\n"
            f"« {expression_dir.strip()} »\n"
            f"→ Cette parole doit structurer et inspirer toute la rédaction de la partie E.\n"
        )

    return f"""Tu es un rédacteur expert en dossiers MDPH. Tu dois rédiger la PARTIE E — Projet de vie.

C'est la PARTIE LA PLUS IMPORTANTE du dossier.
Elle doit permettre à l'équipe pluridisciplinaire de comprendre qui est la personne,
ce qu'elle vit, ce qu'elle souhaite, et ce dont elle a besoin.
{_bloc_expression}{doc_knowledge_e}{verbatim_e}{chronologie}
RÈGLE ABSOLUE : utilise UNIQUEMENT les informations ci-dessous et ci-dessus.
Si une information est absente → [INFO MANQUANTE : nom_du_domaine]
N'invente rien. N'infère rien.

ORDRE DE PRIORITÉ DES SOURCES :
  1. L'expression directe de la personne (si présente ci-dessus) — CŒUR du texte
  2. Les verbatim collectés (paroles de la personne ou de son représentant)
  3. Les données structurées ci-dessous

INFORMATIONS STRUCTURÉES DÉCLARÉES :
- Droits souhaités : {droits or "[INFO MANQUANTE : droits_demandes]"}
- Projet de vie / orientation : {projet_vie or "[INFO MANQUANTE : projet_orientation]"}
- Attentes vis-à-vis de la MDPH : {attentes or "non renseigné"}
- Besoins de compensation : {besoins or "non renseigné"}
- Diagnostic(s) : {diags or "[INFO MANQUANTE : diagnostics]"}
- Impact général : {impact or "non renseigné"}

PRONOMS : {sujet} (ex : "{ex_attente}...")

{axes_specifiques_e}STRUCTURE OBLIGATOIRE (les 4 dimensions DOIVENT être présentes) :
1. BESOINS — Ce dont la personne a besoin pour améliorer sa situation
2. ATTENTES — Ce qu'elle attend concrètement de la MDPH ({ex_attente}...)
3. OBJECTIFS — Ses objectifs à court et moyen terme
4. SOUHAITS — Ses souhaits d'orientation, d'accompagnement, de vie quotidienne

Pour chaque dimension absente → [INFO MANQUANTE : dimension]

FORMAT : paragraphes rédigés, un par dimension. Ton humain, personnel, respectueux.
Si l'expression directe est présente, ouvrir ou conclure avec une citation entre guillemets.
LONGUEUR CIBLE : 400 à 600 mots. C'est la section la plus développée — lui donner l'espace nécessaire.
"""


# ── Génération des textes narratifs ──────────────────────────────────────────

def generer_textes_narratifs(
    donnees: dict[str, Any],
    profil_mdph: str,
    openai_client: Any,
    profil_handicap: str = "",
    sections_actives: set[str] | None = None,
    model: str = "gpt-4o",
) -> dict[str, str]:
    """
    Génère les textes narratifs pour les sections B, C, D, E.

    sections_actives : ensemble de lettres ("B", "C", "D", "E").
                       Si None → génère B et E, C et D selon disponibilité.

    Retourne un dict {clé_champ: texte_rédigé}.
    Les champs [INFO MANQUANTE : ...] indiquent les données absentes — jamais des inventions.
    """
    if sections_actives is None:
        sections_actives = _determiner_sections_actives(donnees, profil_mdph)

    pronoms   = _resoudre_pronoms(profil_mdph, donnees)
    resultats: dict[str, str] = {}

    _generation_map = {
        "B": ("texte_b_vie_quotidienne", _prompt_section_b(donnees, pronoms, profil_handicap)),
        "C": ("texte_c_scolarite",       _prompt_section_c(donnees, pronoms)),
        "D": ("texte_d_situation_pro",   _prompt_section_d(donnees, pronoms)),
        "E": ("texte_e_projet_vie",      _prompt_section_e(donnees, pronoms, profil_mdph)),
    }

    for section, (cle_champ, prompt) in _generation_map.items():
        if section not in sections_actives:
            logger.debug("[NARRATIVE] Section %s non active — ignorée", section)
            continue

        try:
            response = openai_client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Tu es un rédacteur expert en dossiers MDPH français. "
                            "Tu rédiges des textes exploitables par une équipe pluridisciplinaire. "
                            "Tu respectes STRICTEMENT la règle : aucune invention, aucune inférence. "
                            "Si une donnée manque, tu écris [INFO MANQUANTE : nom_champ]."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=900,
                temperature=0.3,
            )
            texte = response.choices[0].message.content.strip()

            # Vérification anti-supposition post-génération
            marqueurs = _detecter_supposition(texte)
            if marqueurs:
                logger.warning(
                    "[NARRATIVE] Section %s — marqueurs de supposition détectés : %s",
                    section, marqueurs,
                )
                # Pas de blocage — signalement au rapport qualité uniquement

            resultats[cle_champ] = texte
            logger.info("[NARRATIVE] Section %s générée (%d chars)", section, len(texte))

        except Exception as e:
            logger.error("[NARRATIVE] Échec section %s : %s", section, e)
            resultats[cle_champ] = f"[ERREUR GÉNÉRATION : {section} — {e}]"

    return resultats


def _determiner_sections_actives(donnees: dict[str, Any], profil_mdph: str) -> set[str]:
    """Détermine les sections à générer selon le profil et les données disponibles."""
    actives = {"B", "E"}  # toujours générées

    # Section C : si enfant OU si qualification section C = oui
    if profil_mdph == "enfant" or str(donnees.get("qualification_section_c", "")).lower().startswith("oui"):
        actives.add("C")

    # Section D : si adulte/mixte/protege ET qualification section D = oui
    if profil_mdph != "enfant" and str(donnees.get("qualification_section_d", "")).lower().startswith("oui"):
        actives.add("D")

    # Section D également si statut_emploi renseigné
    if donnees.get("statut_emploi"):
        actives.add("D")

    return actives
