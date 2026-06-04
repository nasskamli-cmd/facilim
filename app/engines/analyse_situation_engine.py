"""
app/engines/analyse_situation_engine.py — Moteur d'analyse de situation universelle.

Facilim n'oriente pas. Facilim éclaire la décision.
Facilim n'attribue pas un droit. Facilim identifie des besoins.
Facilim ne remplace pas le professionnel. Facilim augmente sa capacité d'analyse.

Ce moteur est utilisable par n'importe quel acteur du champ du handicap,
de l'insertion, du médico-social, du social, de la formation et de l'emploi :
ESSMS, ESRP, ESPO, SAVS, SAMSAH, IME, SESSAD, MAS, FAM, CHRS,
France Travail, Cap Emploi, Missions Locales, MDPH, CCAS,
assistantes sociales, CIP, référents parcours, organismes de formation,
entreprises adaptées, médecine du travail, services handicap d'entreprises,
cabinets maintien dans l'emploi, associations d'accompagnement.

Pipeline :
  COUCHE 1 — Analyse déterministe (sans LLM) :
    Lit les données, textes narratifs et rapport qualité.
    Produit une représentation structurée des besoins, signaux et acteurs.
    Rapide, fiable, reproductible.

  COUCHE 2 — Synthèse narrative (GPT-4o, UN SEUL appel) :
    Reçoit la représentation structurée.
    Rédige la synthèse de situation et les préconisations en langage professionnel.
    Non bloquant si l'API échoue — retourne les données structurées seules.

Format de sortie :
{
  "synthese_situation":   str,    # paragraphe de lecture professionnelle
  "facteurs_risque":      list,   # signaux fragilisant la situation ou le dossier
  "facteurs_protection":  list,   # appuis, ressources, points positifs identifiés
  "besoins_compensation": list,   # besoins de compensation technique/humaine/financière
  "besoins_accompagnement": list, # besoins d'accompagnement identifiés
  "points_vigilance":     list,   # points nécessitant une attention particulière
  "preconisations":       list,   # pistes d'action avec justification
  "acteurs_mobilisables": list,   # acteurs pertinents avec leur rôle possible
  "niveau_confiance":     str,    # FORT | MOYEN | FAIBLE
  "points_a_completer":   list,   # informations manquantes pour consolider l'analyse
}
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("facilim.engines.analyse_situation")


# ─────────────────────────────────────────────────────────────────────────────
# CATALOGUE DES ACTEURS PAR TYPE DE BESOIN
# Chaque acteur est associé à un ou plusieurs types de besoins.
# La sélection se fait par pertinence, pas par profil.
# ─────────────────────────────────────────────────────────────────────────────

_ACTEURS_PAR_BESOIN: dict[str, list[dict]] = {

    "compensation_financiere": [
        {"acteur": "MDPH", "role": "attribution des droits financiers (AAH, PCH, AEEH)"},
        {"acteur": "CAF ou MSA", "role": "versement des prestations et orientation vers les aides"},
        {"acteur": "service social", "role": "accompagnement dans les démarches de droit commun"},
    ],

    "compensation_technique": [
        {"acteur": "ergothérapeute", "role": "évaluation et prescription des aides techniques adaptées"},
        {"acteur": "MDPH", "role": "financement PCH aide technique"},
        {"acteur": "service handicap d'entreprise", "role": "adaptation du poste de travail"},
        {"acteur": "médecine du travail", "role": "prescription des aménagements techniques au travail"},
    ],

    "compensation_humaine": [
        {"acteur": "MDPH", "role": "évaluation et attribution PCH aide humaine"},
        {"acteur": "SAVS", "role": "accompagnement à domicile et dans les actes de la vie sociale"},
        {"acteur": "SAMSAH", "role": "accompagnement médico-social pour les situations complexes"},
        {"acteur": "service social", "role": "coordination des aides humaines à domicile"},
        {"acteur": "CCAS", "role": "aide à domicile et accompagnement social de proximité"},
    ],

    "accompagnement_pro_maintien": [
        {"acteur": "médecine du travail", "role": "évaluation des aptitudes et prescription d'aménagements"},
        {"acteur": "service handicap d'entreprise", "role": "mise en œuvre des aménagements et maintien"},
        {"acteur": "Cap Emploi", "role": "appui au maintien dans l'emploi et RQTH"},
        {"acteur": "emploi accompagné", "role": "suivi renforcé en milieu ordinaire si besoin"},
        {"acteur": "cabinet spécialisé maintien dans l'emploi", "role": "expertise technique sur les situations complexes"},
        {"acteur": "SAMETH / Agefiph", "role": "financement des aménagements et des prestations de maintien"},
    ],

    "accompagnement_pro_insertion": [
        {"acteur": "France Travail", "role": "accompagnement vers l'emploi et accès aux formations"},
        {"acteur": "Cap Emploi", "role": "accompagnement spécialisé handicap vers l'emploi"},
        {"acteur": "Mission Locale", "role": "accompagnement global des jeunes de 16 à 25 ans"},
        {"acteur": "ESRP", "role": "rééducation et réorientation professionnelle spécialisée"},
        {"acteur": "ESPO", "role": "pré-orientation professionnelle pour évaluer les capacités"},
        {"acteur": "emploi accompagné", "role": "insertion et suivi en milieu ordinaire avec soutien durable"},
        {"acteur": "entreprise adaptée", "role": "emploi en milieu protégé avec accompagnement"},
        {"acteur": "conseiller en insertion professionnelle", "role": "accompagnement individualisé vers l'emploi"},
    ],

    "accompagnement_pro_formation": [
        {"acteur": "ESRP", "role": "formation professionnelle adaptée avec plateau technique spécialisé"},
        {"acteur": "organisme de formation", "role": "formation avec aménagements pédagogiques"},
        {"acteur": "France Travail", "role": "financement et accès aux formations certifiantes"},
        {"acteur": "référent parcours", "role": "coordination du parcours de formation"},
    ],

    "accompagnement_vie_sociale": [
        {"acteur": "SAVS", "role": "accompagnement dans la vie sociale et les démarches administratives"},
        {"acteur": "SAMSAH", "role": "accompagnement médico-social global"},
        {"acteur": "association d'accompagnement", "role": "soutien social et lien avec les ressources locales"},
        {"acteur": "coordinateur de parcours", "role": "articulation des différents intervenants"},
        {"acteur": "psychologue", "role": "soutien psychologique et accompagnement thérapeutique"},
    ],

    "accompagnement_scolaire": [
        {"acteur": "MDPH", "role": "notification AESH, PPS, orientation scolaire spécialisée"},
        {"acteur": "SESSAD", "role": "accompagnement en milieu scolaire ordinaire"},
        {"acteur": "IME", "role": "accueil et scolarisation en établissement spécialisé"},
        {"acteur": "enseignant référent", "role": "coordination du PPS et lien avec l'équipe éducative"},
        {"acteur": "psychologue scolaire", "role": "évaluation et soutien des apprentissages"},
    ],

    "protection_juridique": [
        {"acteur": "MDPH", "role": "évaluation du besoin de protection et orientation vers le tribunal"},
        {"acteur": "service social", "role": "accompagnement dans la demande de mesure de protection"},
        {"acteur": "mandataire judiciaire", "role": "exercice de la mesure de protection"},
        {"acteur": "assistant social", "role": "information sur les mesures disponibles (tutelle, curatelle, sauvegarde)"},
    ],

    "evaluation_situation": [
        {"acteur": "MDPH", "role": "évaluation globale des besoins et des droits"},
        {"acteur": "équipe pluridisciplinaire MDPH", "role": "évaluation médico-sociale et préconisations"},
        {"acteur": "référent de parcours", "role": "coordination et suivi du parcours"},
        {"acteur": "assistant social", "role": "évaluation sociale et orientation vers les ressources adaptées"},
    ],

    "orientation_medico_sociale": [
        {"acteur": "MDPH", "role": "notification d'orientation en établissement ou service"},
        {"acteur": "SAVS", "role": "accompagnement en milieu ordinaire"},
        {"acteur": "SAMSAH", "role": "accompagnement médico-social renforcé"},
        {"acteur": "MAS ou FAM", "role": "accueil en établissement pour les situations de grande dépendance"},
        {"acteur": "foyer de vie", "role": "hébergement et accompagnement pour les situations sans activité professionnelle"},
        {"acteur": "plateforme de répit", "role": "soutien aux aidants et répit temporaire"},
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# PATTERNS DE DÉTECTION — signaux dans les données et textes
# ─────────────────────────────────────────────────────────────────────────────

_SIGNAUX_RISQUE = [
    (r"ne peut (pas|plus)", "limitation fonctionnelle significative"),
    (r"incapacité|inaptitude",              "incapacité ou inaptitude déclarée"),
    (r"isolement|seul(e)? sans soutien",    "risque d'isolement social"),
    (r"hospitalisé|hospitalisation",        "antécédents d'hospitalisation"),
    (r"dette|surendettement|expulsion",     "vulnérabilité financière ou résidentielle"),
    (r"(sans emploi|chômage).{0,20}(ans|mois)", "chômage de longue durée"),
    (r"arrêt.{0,15}(longue durée|depuis)",  "arrêt de travail prolongé"),
    (r"rupture.{0,15}(contrat|emploi)",     "rupture de parcours professionnel"),
    (r"abandonn|décroché|quitté l.école",   "décrochage scolaire ou formation"),
    (r"tutelle|curatelle",                  "mesure de protection en place"),
    (r"\[INFO MANQUANTE",                   "informations importantes non renseignées"),
]

_SIGNAUX_PROTECTION = [
    (r"soutien.{0,20}(famille|proche|conjoint|aidant)", "soutien de l'entourage présent"),
    (r"suivi.{0,20}(médical|psychologique|thérapeutique)", "suivi thérapeutique en place"),
    (r"(déjà|actuellement).{0,20}(accompagn|suivi|encadré)", "accompagnement existant"),
    (r"(motivé|motivée|souhaite|projet|objectif)",  "motivation et projet exprimés"),
    (r"(logement|domicile).{0,20}(stable|adapté|accessible)", "situation résidentielle stable"),
    (r"(travail|emploi|activité).{0,20}(en cours|maintenu|conservé)", "activité professionnelle maintenue"),
    (r"aides?.{0,15}(technique|humaine|financière).{0,15}(en place|déjà)", "aides déjà en place"),
]

_SIGNAUX_BESOIN_COMPENSATION_TECHNIQUE = [
    r"fauteuil|déambulateur|orthèse|prothèse",
    r"aide.{0,15}technique|équipement.{0,15}adapté",
    r"lecteur d.écran|braille|synthèse vocale",
    r"implant|appareillage|boucle magnétique",
    r"véhicule adapté|scooter.{0,10}pmr|rampe",
    r"aménagement.{0,15}logement|adaptation.{0,15}domicile",
]

_SIGNAUX_BESOIN_COMPENSATION_HUMAINE = [
    r"aide.{0,15}(humaine|quotidienne|ménagère)",
    r"(mari|femme|famille|aidant).{0,20}(aide|s.occupe|doit)",
    r"ne peut pas.{0,30}seul",
    r"accompagnement.{0,15}(quotidien|daily|permanents?)",
    r"soins.{0,15}(infirmier|nursing|aide-soignant)",
]

_SIGNAUX_ACCOMPAGNEMENT_PRO = [
    r"(maintien|maintenir).{0,20}emploi",
    r"rqth|reconnaissance.{0,20}handicap",
    r"reconversion|réorientation|bilan.{0,20}compétences",
    r"inaptitude|restrictions.{0,20}médicales",
    r"(reprendre|retour).{0,20}travail",
    r"(formation|apprentissage).{0,15}(professionnelle|qualifiante)",
    r"projet.{0,15}(professionnel|emploi)",
]

_SIGNAUX_ACCOMPAGNEMENT_VIE = [
    r"(gestion|gérer).{0,20}(administrative|courrier|budget|argent)",
    r"(vie|lien).{0,20}social",
    r"autonomie.{0,20}(vie|logement|quotidien)",
    r"(coordination|articulation).{0,20}(soins|intervenants)",
]

_SIGNAUX_PROTECTION_JURIDIQUE = [
    r"vulnérabilité|vulnérable",
    r"(gestion|comprendre?).{0,20}argent",
    r"exploitat|influenc",
    r"(après nous|après.{0,10}parent|avenir)",
    r"tutelle|curatelle|habilitation familiale|sauvegarde",
]


def _detecter_signaux(texte: str, patterns: list) -> list[str]:
    """Retourne les signaux détectés dans le texte."""
    t = texte.lower()
    signaux = []
    for item in patterns:
        if isinstance(item, tuple):
            pattern, label = item
            if re.search(pattern, t, re.IGNORECASE):
                signaux.append(label)
        else:
            if re.search(item, t, re.IGNORECASE):
                signaux.append(item)
    return list(dict.fromkeys(signaux))   # dédupliqué, ordre conservé


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURE DE SORTIE
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AnalyseSituation:
    synthese_situation:     str       = ""
    facteurs_risque:        list[str] = field(default_factory=list)
    facteurs_protection:    list[str] = field(default_factory=list)
    besoins_compensation:   list[dict] = field(default_factory=list)
    besoins_accompagnement: list[dict] = field(default_factory=list)
    points_vigilance:       list[str] = field(default_factory=list)
    preconisations:         list[dict] = field(default_factory=list)
    acteurs_mobilisables:   list[dict] = field(default_factory=list)
    niveau_confiance:       str       = "FAIBLE"
    points_a_completer:     list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# COUCHE 1 — ANALYSE DÉTERMINISTE
# ─────────────────────────────────────────────────────────────────────────────

def _analyser_deterministique(
    donnees: dict[str, Any],
    textes_narratifs: dict[str, str],
    rapport_qualite: dict[str, Any],
    profil_mdph: str,
) -> AnalyseSituation:
    """
    Couche 1 — sans LLM.
    Analyse les signaux dans les données et produit la représentation structurée.
    """
    analyse = AnalyseSituation()

    # Texte consolidé pour la détection de signaux
    texte_global = " ".join(filter(None, [
        str(donnees.get("diagnostics", "") or ""),
        str(donnees.get("impact_quotidien", "") or ""),
        str(donnees.get("statut_emploi", "") or ""),
        str(donnees.get("expression_directe", "") or ""),
        textes_narratifs.get("texte_b_vie_quotidienne", ""),
        textes_narratifs.get("texte_d_situation_pro", ""),
        textes_narratifs.get("texte_e_projet_vie", ""),
        " ".join(donnees.get("_verbatim_b") or []),
        " ".join(donnees.get("_verbatim_d") or []),
        " ".join(donnees.get("_verbatim_e") or []),
    ]))

    # ── Facteurs de risque ────────────────────────────────────────────────────
    analyse.facteurs_risque = _detecter_signaux(texte_global, _SIGNAUX_RISQUE)

    # Facteurs de risque issus du rapport qualité
    alertes = rapport_qualite.get("alertes_rouges") or []
    for alerte in alertes:
        if alerte and alerte not in analyse.facteurs_risque:
            analyse.facteurs_risque.append(f"Qualité dossier — {alerte}")

    # ── Facteurs de protection ────────────────────────────────────────────────
    analyse.facteurs_protection = _detecter_signaux(texte_global, _SIGNAUX_PROTECTION)

    # ── Besoins de compensation ───────────────────────────────────────────────
    besoins_types: list[str] = []

    if any(re.search(p, texte_global, re.IGNORECASE) for p in _SIGNAUX_BESOIN_COMPENSATION_TECHNIQUE):
        besoins_types.append("compensation_technique")
        analyse.besoins_compensation.append({
            "type": "Compensation technique",
            "description": "Des aides techniques semblent nécessaires au regard des limitations identifiées.",
            "a_preciser": "Nature exacte des équipements, financement actuel ou manquant.",
        })

    if any(re.search(p, texte_global, re.IGNORECASE) for p in _SIGNAUX_BESOIN_COMPENSATION_HUMAINE):
        besoins_types.append("compensation_humaine")
        analyse.besoins_compensation.append({
            "type": "Compensation humaine",
            "description": "Des besoins d'aide humaine pour les actes essentiels ou la vie quotidienne sont présents.",
            "a_preciser": "Volume horaire, nature des actes, financement en place ou à demander.",
        })

    # Compensation financière — si arrêt de travail ou emploi compromis
    if re.search(r"arrêt.{0,15}(longue durée|depuis)|sans emploi|inactif", texte_global, re.IGNORECASE):
        besoins_types.append("compensation_financiere")
        analyse.besoins_compensation.append({
            "type": "Compensation financière",
            "description": "La situation professionnelle compromise peut générer un besoin de soutien financier.",
            "a_preciser": "Droits en cours, niveau de ressources, prestations non demandées.",
        })

    # ── Besoins d'accompagnement ──────────────────────────────────────────────
    types_accompagnement: list[str] = []

    if any(re.search(p, texte_global, re.IGNORECASE) for p in _SIGNAUX_ACCOMPAGNEMENT_PRO):
        # Distinguer maintien vs insertion
        if re.search(r"(maintien|maintenir).{0,20}emploi|en poste|actuellement.{0,10}emploi", texte_global, re.IGNORECASE):
            types_accompagnement.append("accompagnement_pro_maintien")
            analyse.besoins_accompagnement.append({
                "type": "Accompagnement au maintien dans l'emploi",
                "description": "Des signaux indiquent un risque sur la continuité de l'emploi actuel.",
                "a_preciser": "Évaluation de l'aptitude, aménagements possibles, temporalité d'intervention.",
            })
        if re.search(r"reconversion|réorientation|reprendre|retour|insertion|projet.{0,15}pro", texte_global, re.IGNORECASE):
            types_accompagnement.append("accompagnement_pro_insertion")
            analyse.besoins_accompagnement.append({
                "type": "Accompagnement vers l'emploi ou la formation",
                "description": "Un projet professionnel ou de réorientation est identifié ou nécessaire.",
                "a_preciser": "Niveau de motivation, capacités résiduelles, formations accessibles.",
            })

    if any(re.search(p, texte_global, re.IGNORECASE) for p in _SIGNAUX_ACCOMPAGNEMENT_VIE):
        types_accompagnement.append("accompagnement_vie_sociale")
        analyse.besoins_accompagnement.append({
            "type": "Accompagnement dans la vie sociale et administrative",
            "description": "Des difficultés dans la gestion du quotidien, des démarches ou du lien social sont identifiées.",
            "a_preciser": "Intensité du besoin, ressources familiales disponibles, services existants.",
        })

    if profil_mdph == "enfant" or str(donnees.get("situation_scolaire", "")).strip():
        types_accompagnement.append("accompagnement_scolaire")
        analyse.besoins_accompagnement.append({
            "type": "Accompagnement scolaire et éducatif",
            "description": "La situation scolaire nécessite une analyse des besoins éducatifs particuliers.",
            "a_preciser": "PPS en place, AESH, GEVASCO, aménagements pédagogiques.",
        })

    if any(re.search(p, texte_global, re.IGNORECASE) for p in _SIGNAUX_PROTECTION_JURIDIQUE):
        types_accompagnement.append("protection_juridique")
        analyse.besoins_accompagnement.append({
            "type": "Protection juridique et sécurisation",
            "description": "Des signaux de vulnérabilité ou un besoin de protection sont présents.",
            "a_preciser": "Capacité de discernement, mesure en place ou à demander, risques identifiés.",
        })

    # ── Acteurs mobilisables ──────────────────────────────────────────────────
    tous_types = besoins_types + types_accompagnement
    # Ajouter évaluation_situation si dossier incomplet
    score = rapport_qualite.get("score_maturite") or 0
    if score < 50:
        tous_types.append("evaluation_situation")

    # Construire la liste d'acteurs sans doublons
    acteurs_vus: set[str] = set()
    for type_besoin in tous_types:
        for acteur_info in _ACTEURS_PAR_BESOIN.get(type_besoin, []):
            if acteur_info["acteur"] not in acteurs_vus:
                acteurs_vus.add(acteur_info["acteur"])
                analyse.acteurs_mobilisables.append({
                    "acteur":       acteur_info["acteur"],
                    "role_possible": acteur_info["role"],
                    "type_besoin":  type_besoin,
                })

    # ── Points de vigilance ───────────────────────────────────────────────────
    if rapport_qualite.get("retentissement_absent"):
        analyse.points_vigilance.append(
            "Le retentissement fonctionnel n'est pas encore suffisamment documenté "
            "— le dossier risque d'être sous-évalué."
        )
    if rapport_qualite.get("projet_vie_incomplet"):
        analyse.points_vigilance.append(
            "Le projet de vie et les attentes de la personne ne sont pas clairement exprimés "
            "— dimension essentielle pour l'évaluation des besoins."
        )
    zones = rapport_qualite.get("zones_pauvres") or []
    for zone in zones[:3]:   # limiter à 3 pour la lisibilité
        analyse.points_vigilance.append(f"Terme sans description des conséquences : {zone}")

    contradictions = rapport_qualite.get("contradictions") or []
    for c in contradictions:
        analyse.points_vigilance.append(c)

    # ── Préconisations ────────────────────────────────────────────────────────
    # Construites depuis les besoins détectés — sans prescrire de structure
    if "accompagnement_pro_maintien" in types_accompagnement:
        analyse.preconisations.append({
            "piste": "Intervention rapide sur le maintien dans l'emploi",
            "justification": "Les signaux indiquent un risque de rupture professionnelle à court terme.",
            "prochaine_etape": "Prendre contact avec la médecine du travail et évaluer les aménagements possibles.",
        })
    if "accompagnement_pro_insertion" in types_accompagnement:
        analyse.preconisations.append({
            "piste": "Accompagnement vers un projet professionnel adapté",
            "justification": "Un projet ou une reprise d'activité est identifié mais nécessite un appui spécialisé.",
            "prochaine_etape": "Évaluer les capacités résiduelles et les pistes de formation ou d'emploi adapté.",
        })
    if "compensation_humaine" in besoins_types or "compensation_technique" in besoins_types:
        analyse.preconisations.append({
            "piste": "Évaluation et demande de compensation",
            "justification": "Des besoins de compensation technique ou humaine sont identifiés et non couverts.",
            "prochaine_etape": "Compléter le dossier MDPH pour les sections B et E, puis soumettre la demande.",
        })
    if "protection_juridique" in types_accompagnement:
        analyse.preconisations.append({
            "piste": "Examen de la nécessité d'une mesure de protection",
            "justification": "Des signaux de vulnérabilité sont présents dans le dossier.",
            "prochaine_etape": "Évaluation par un professionnel habilité avant toute démarche judiciaire.",
        })
    if score < 40:
        analyse.preconisations.append({
            "piste": "Compléter le recueil d'informations avant toute décision",
            "justification": "Le dossier est insuffisamment alimenté pour produire une analyse fiable.",
            "prochaine_etape": "Reprendre la collecte sur les parties B (vie quotidienne) et E (projet de vie).",
        })

    # ── Points à compléter ────────────────────────────────────────────────────
    manquants = rapport_qualite.get("points_a_completer") or []
    analyse.points_a_completer = list(manquants)

    # Ajouter les [INFO MANQUANTE] repérées dans les textes
    for texte in textes_narratifs.values():
        for m in re.findall(r"\[INFO MANQUANTE\s*:\s*([^\]]+)\]", texte):
            label = m.strip()
            if label not in analyse.points_a_completer:
                analyse.points_a_completer.append(label)

    # ── Niveau de confiance ───────────────────────────────────────────────────
    nb_manquants = len(analyse.points_a_completer)
    if score >= 70 and nb_manquants <= 2:
        analyse.niveau_confiance = "FORT"
    elif score >= 45 and nb_manquants <= 6:
        analyse.niveau_confiance = "MOYEN"
    else:
        analyse.niveau_confiance = "FAIBLE"

    return analyse


# ─────────────────────────────────────────────────────────────────────────────
# COUCHE 2 — SYNTHÈSE NARRATIVE (GPT-4o)
# ─────────────────────────────────────────────────────────────────────────────

def _generer_synthese_narrative(
    analyse: AnalyseSituation,
    donnees: dict[str, Any],
    textes_narratifs: dict[str, str],
    openai_client: Any,
    profil_mdph: str,
) -> str:
    """
    Couche 2 — appel LLM unique.
    Rédige la synthèse de situation en langage professionnel pluridisciplinaire.
    Retourne une chaîne vide si l'appel échoue (non bloquant).
    """
    diags     = donnees.get("diagnostics", "non renseigné")
    impact    = donnees.get("impact_quotidien", "non renseigné")
    expr_dir  = donnees.get("expression_directe", "")
    statut    = donnees.get("statut_emploi", "")
    texte_b   = textes_narratifs.get("texte_b_vie_quotidienne", "")[:800]
    texte_e   = textes_narratifs.get("texte_e_projet_vie", "")[:600]

    risques_str     = "\n".join(f"- {r}" for r in analyse.facteurs_risque[:5])
    protections_str = "\n".join(f"- {p}" for p in analyse.facteurs_protection[:5])
    besoins_str     = "\n".join(
        f"- {b['type']} : {b['description']}" for b in analyse.besoins_compensation + analyse.besoins_accompagnement
    )

    prompt = f"""Tu es un expert en évaluation médico-sociale et en accompagnement du handicap.
Tu rédiges une synthèse de situation pour un professionnel pluridisciplinaire (travailleur social,
équipe MDPH, ESRP, Cap Emploi, Mission Locale, service handicap, ou tout autre acteur du champ).

RÈGLE ABSOLUE : utilise UNIQUEMENT les informations ci-dessous.
N'invente rien. N'infère rien au-delà de ce qui est déclaré.
Si une information manque, indique-le clairement plutôt que de supposer.

DONNÉES DÉCLARÉES :
- Profil MDPH : {profil_mdph}
- Diagnostic(s) : {diags}
- Impact déclaré : {impact}
- Statut professionnel : {statut or "non renseigné"}
- Expression directe de la personne : {expr_dir or "non disponible"}

EXTRAIT VIE QUOTIDIENNE (section B) :
{texte_b or "[non renseigné]"}

EXTRAIT PROJET DE VIE (section E) :
{texte_e or "[non renseigné]"}

FACTEURS DE RISQUE IDENTIFIÉS :
{risques_str or "Aucun signal de risque identifié"}

FACTEURS DE PROTECTION IDENTIFIÉS :
{protections_str or "Aucun facteur de protection identifié"}

BESOINS IDENTIFIÉS :
{besoins_str or "Besoins non encore identifiés — dossier à compléter"}

MISSION :
Rédige une SYNTHÈSE DE SITUATION de 3 à 5 paragraphes, en langage professionnel clair :
1. Présenter la situation globale de la personne (qui est-elle, quelle est sa situation ?)
2. Décrire les limitations fonctionnelles et leur impact sur la vie quotidienne et professionnelle
3. Identifier les ressources et appuis présents
4. Formuler les enjeux principaux pour l'accompagnement et l'évaluation

Ton : professionnel, factuel, respectueux de la personne.
Éviter : les jugements de valeur, les diagnostics implicites, les formulations standardisées vides de sens.
"""
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Tu es un expert en évaluation médico-sociale. "
                        "Tu rédiges des synthèses exploitables par des professionnels pluridisciplinaires. "
                        "Tu respectes strictement la règle : aucune invention, aucune inférence au-delà du déclaré."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=700,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("[ANALYSE] Synthèse narrative non bloquante : %s", e)
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE PUBLIC
# ─────────────────────────────────────────────────────────────────────────────

def analyser_situation(
    donnees: dict[str, Any],
    textes_narratifs: dict[str, str],
    rapport_qualite: dict[str, Any],
    profil_mdph: str = "adulte",
    openai_client: Any = None,
    infos_manquantes_inferees: list | None = None,  # list[InformationManquante] — optionnel
) -> AnalyseSituation:
    """
    Produit l'analyse de situation complète.

    Si openai_client est fourni → synthèse narrative générée (couche 2).
    Sinon → couche 1 uniquement (structurée, sans texte narratif).
    """
    analyse = _analyser_deterministique(
        donnees=donnees,
        textes_narratifs=textes_narratifs,
        rapport_qualite=rapport_qualite,
        profil_mdph=profil_mdph,
    )

    # Enrichissement depuis l'inférenceur (informations manquantes ciblées)
    if infos_manquantes_inferees:
        for info in infos_manquantes_inferees:
            label = info.label if hasattr(info, "label") else str(info)
            if label and label not in analyse.points_a_completer:
                analyse.points_a_completer.append(label)

    if openai_client and not analyse.synthese_situation:
        analyse.synthese_situation = _generer_synthese_narrative(
            analyse=analyse,
            donnees=donnees,
            textes_narratifs=textes_narratifs,
            openai_client=openai_client,
            profil_mdph=profil_mdph,
        )

    logger.info(
        "[ANALYSE] confiance=%s risques=%d protections=%d besoins=%d acteurs=%d",
        analyse.niveau_confiance,
        len(analyse.facteurs_risque),
        len(analyse.facteurs_protection),
        len(analyse.besoins_compensation) + len(analyse.besoins_accompagnement),
        len(analyse.acteurs_mobilisables),
    )

    return analyse
