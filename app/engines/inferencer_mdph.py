"""
app/engines/inferencer_mdph.py — Moteur d'inférence métier MDPH.

Référentiel Nassim V1 — Logique de raisonnement N+2.

Principe fondamental :
  Un diagnostic est un point de départ, jamais une conclusion.
  Chaque signal détecté produit des hypothèses fonctionnelles
  qui doivent être CONFIRMÉES avant tout usage dans le CERFA.

Pipeline :
  Détecter → Confirmer → Questionner → Compléter → Rédiger

Trois états de confirmation :
  DIRECTE    — mot ou synonyme exact trouvé dans les déclarés
  INDIRECTE  — concept présent via paraphrase ou reformulation
  ABSENTE    — aucune trace dans les données collectées

Les hypothèses ABSENTES alimentent :
  - les relances ciblées (une seule CRITIQUE par tour)
  - les alertes qualité (cerfa_quality_agent)
  - les informations manquantes (analyse_situation_engine)

Les hypothèses confirmées (DIRECTE ou INDIRECTE) alimentent :
  - confirmed_hypotheses (référentiel statistique futur)

JAMAIS : injection directe d'hypothèses dans le texte CERFA.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("facilim.engines.inferencer")


# ─────────────────────────────────────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────────────────────────────────────

class EtatConfirmation(str, Enum):
    DIRECTE    = "directe"
    INDIRECTE  = "indirecte"
    ABSENTE    = "absente"


class PrioriteRelance(str, Enum):
    CRITIQUE    = "critique"
    IMPORTANTE  = "importante"
    OPTIONNELLE = "optionnelle"


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURES DE DONNÉES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Hypothese:
    id:                   str
    signal_source:        str
    categorie:            str
    inference:            str
    description_complete: str
    confidence:           str               # "forte" | "moyenne" | "faible"
    sections:             list[str]
    confirmation:         EtatConfirmation
    champs_confirmation:  list[str]
    fragment_confirmatif: str               # extrait ayant confirmé
    priorite:             PrioriteRelance
    question_relance:     str               # question à poser si ABSENTE


@dataclass
class InformationManquante:
    label:         str
    hypothese_id:  str
    section:       str
    priorite:      PrioriteRelance


@dataclass
class RelanceSuggeree:
    question:         str
    contexte_interne: str
    hypothese_id:     str
    section:          str
    priorite:         PrioriteRelance


@dataclass
class AlerteQualiteInferee:
    message:      str
    hypothese_id: str
    type_alerte:  str   # "zone_pauvre" | "information_manquante"
    section:      str
    niveau:       str   # "rouge" | "orange"


@dataclass
class InferenceCoverage:
    total_detectees:             int
    confirmees_directes:         int
    confirmees_indirectes:       int
    non_confirmees:              int
    taux_couverture:             float
    non_confirmees_critiques:    int
    non_confirmees_importantes:  int


@dataclass
class ConfirmedHypothesisRecord:
    hypothese_id:       str
    signal_source:      str
    inference:          str
    etat_confirmation:  str
    fragment:           str    # tronqué à 80 chars, anonymisé
    source_confirmation: str   # champ ayant fourni la confirmation
    profil_principal:   str
    profil_mdph:        str


@dataclass
class ContexteInfere:
    hypotheses:               list[Hypothese]
    confirmed_hypotheses:     list[ConfirmedHypothesisRecord]
    informations_manquantes:  list[InformationManquante]
    relances_suggerees:       list[RelanceSuggeree]
    alertes_qualite:          list[AlerteQualiteInferee]
    coverage:                 InferenceCoverage
    profil_source:            str


# ─────────────────────────────────────────────────────────────────────────────
# RÈGLES D'INFÉRENCE — structure interne
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _RegleBase:
    id:                    str
    signaux:               list[str]       # patterns détectés dans texte source
    inference:             str             # label court
    description_complete:  str             # phrase rédigée
    confidence:            str
    sections:              list[str]
    priorite:              PrioriteRelance
    champs_confirmation:   list[str]       # champs à vérifier pour confirmation
    concept_confirmation:  str             # clé vers _SYNONYMES
    question_relance:      str


# ─────────────────────────────────────────────────────────────────────────────
# SYNONYMES POUR CONFIRMATION INDIRECTE
# Clé = concept · Valeur = patterns qui confirment ce concept
# ─────────────────────────────────────────────────────────────────────────────

_SYNONYMES: dict[str, list[str]] = {
    "fatigabilite": [
        r"épuis", r"crev", r"fatigu", r"n.?en peux plus", r"sans énergie",
        r"à plat", r"exténu", r"plus la force", r"pas l.énergie",
        r"dors peu", r"nuits difficiles", r"réveil",
    ],
    "limitations_physiques": [
        r"ne (peux|peut) (pas|plus)", r"difficilement", r"impossible",
        r"limité", r"ne marche? plus", r"ne porte? pas", r"douleur.{0,20}(quand|si|pour)",
        r"mal à (marcher|rester|porter|bouger|me lever)",
        r"position.{0,15}(difficile|impossible|douloureux)",
    ],
    "difficultes_concentration": [
        r"mal (à|a) (se )?concentr", r"tête dans le brouillard",
        r"mémoire", r"oubli", r"distrait", r"perdu le fil",
        r"difficultés? de (mémoire|concentration|attention)",
        r"ralentiss", r"lent(eur)?", r"cerveau.{0,10}(lent|brouillard)",
    ],
    "perturbation_sommeil": [
        r"dort? mal", r"insomnies?", r"réveils? (la )?nuit",
        r"nuits? difficile", r"ne (dors?|dort?) pas", r"sommeil perturbé",
        r"fatigue.{0,20}matin", r"épuisé.{0,15}lever",
    ],
    "evitement_social": [
        r"plus sortr", r"évite", r"plus de contacts?",
        r"isolé", r"seul(e)?", r"plus envie (de voir|de sortir)",
        r"difficultés? relation", r"mal (à l.)?aise",
    ],
    "difficultes_projection": [
        r"(n.?arrive|ne peut) pas (se )?project",
        r"au jour le jour", r"pas d.?avenir", r"difficile (de|d.?)imaginer",
        r"incertain", r"peur de l.?avenir",
    ],
    "rupture_trajectoire": [
        r"avant (l.accident|la maladie|l.AVC|le diagnostic)",
        r"avant (j.étais|j.avais|je travaillais|j.étais actif)",
        r"plus la même (vie|personne)",
        r"depuis l.accident", r"depuis que (j.ai|il a|elle a)",
        r"ça a tout changé",
    ],
    "impact_professionnel": [
        r"ne (travaille|peut) plus",
        r"arrêt.{0,15}travail", r"licenci", r"inaptitude",
        r"ne (peut|peux) pas reprendre",
        r"perdu (mon|son) emploi", r"plus capable de travailler",
    ],
    "gestion_imprevus": [
        r"changement.{0,15}(difficile|impossible|angoiss)",
        r"routine.{0,15}important", r"imprévu.{0,15}(stresse|angoiss|perturb)",
        r"besoin.{0,15}repère", r"désorganis",
    ],
    "surcharge_sensorielle": [
        r"bruit.{0,15}(insupportable|difficile|trop)",
        r"lumière.{0,15}(difficile|trop forte|agress)",
        r"foule.{0,15}(difficile|impossible|angoiss)",
        r"surcharge", r"saturé.{0,15}(bruit|monde)",
    ],
    "variabilite_capacites": [
        r"(bon|mauvais).{0,10}jours?",
        r"(meilleur|moins bien).{0,10}(jour|période)",
        r"pas toujours pareil", r"ça varie",
        r"certains jours.{0,20}(peut|impossible)",
    ],
    "vulnerabilite": [
        r"(comprend|comprend).{0,20}(argent|prix|billet)",
        r"se faire (avoir|exploiter|manipuler)",
        r"ne comprend pas (les|le|la).{0,10}danger",
        r"besoin (d.être|d.un).{0,15}accompagn",
        r"(seul|seule).{0,10}(difficile|impossible|dangereux)",
    ],
    "besoin_accompagnement": [
        r"besoin.{0,20}(aide|accompagnement|soutien)",
        r"ne peut pas (faire|gérer).{0,15}seul",
        r"quelqu.un.{0,15}(aide|accompagne|supervise)",
        r"aidant.{0,20}(fait|s.occupe|gère)",
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# RÈGLES D'INFÉRENCE PAR CATÉGORIE
# ─────────────────────────────────────────────────────────────────────────────

_REGLES: dict[str, list[_RegleBase]] = {

    "sommeil": [
        _RegleBase(
            id="sommeil_001",
            signaux=[r"troubles? du sommeil", r"insomnies?", r"réveils? nocturne"],
            inference="fatigabilité",
            description_complete="Les troubles du sommeil entraînent une fatigabilité importante qui impacte l'énergie et les capacités quotidiennes.",
            confidence="forte",
            sections=["B", "D"],
            priorite=PrioriteRelance.CRITIQUE,
            champs_confirmation=["impact_quotidien", "_verbatim_b", "_verbatim_d", "expression_directe"],
            concept_confirmation="fatigabilite",
            question_relance="La fatigue est-elle présente quotidiennement ? À quels moments de la journée est-elle la plus forte ?",
        ),
        _RegleBase(
            id="sommeil_002",
            signaux=[r"troubles? du sommeil", r"insomnies?"],
            inference="difficultés de concentration",
            description_complete="Le manque de sommeil engendre des difficultés de concentration et un ralentissement cognitif qui affectent les activités quotidiennes et professionnelles.",
            confidence="forte",
            sections=["B", "D"],
            priorite=PrioriteRelance.IMPORTANTE,
            champs_confirmation=["impact_quotidien", "_verbatim_b", "_verbatim_d"],
            concept_confirmation="difficultes_concentration",
            question_relance="Les troubles du sommeil affectent-ils votre capacité à vous concentrer ou à mémoriser des informations pendant la journée ?",
        ),
        _RegleBase(
            id="sommeil_003",
            signaux=[r"troubles? du sommeil", r"insomnies?", r"réveils? nocturne"],
            inference="impact sur le moral",
            description_complete="Les nuits perturbées ont des conséquences sur le moral et la capacité à faire face aux difficultés quotidiennes.",
            confidence="moyenne",
            sections=["B", "E"],
            priorite=PrioriteRelance.OPTIONNELLE,
            champs_confirmation=["impact_quotidien", "_verbatim_e", "expression_directe"],
            concept_confirmation="fatigabilite",
            question_relance="Les troubles du sommeil ont-ils un effet sur votre moral ou votre énergie pour affronter le quotidien ?",
        ),
    ],

    "douleur": [
        _RegleBase(
            id="douleur_001",
            signaux=[r"douleurs?", r"douleurs? chroniques?", r"algies?", r"douloureux"],
            inference="limitations physiques fonctionnelles",
            description_complete="Les douleurs chroniques limitent les capacités physiques : déplacements, maintien de postures, port de charges.",
            confidence="forte",
            sections=["B", "D"],
            priorite=PrioriteRelance.CRITIQUE,
            champs_confirmation=["impact_quotidien", "_verbatim_b", "_verbatim_d", "expression_directe"],
            concept_confirmation="limitations_physiques",
            question_relance="Les douleurs limitent-elles vos capacités concrètement ? Quels gestes ou activités sont devenus impossibles ou très difficiles ?",
        ),
        _RegleBase(
            id="douleur_002",
            signaux=[r"douleurs?", r"algies?"],
            inference="fatigabilité physique",
            description_complete="La douleur chronique entraîne une fatigabilité physique qui réduit l'endurance et la capacité à maintenir des activités.",
            confidence="forte",
            sections=["B", "D"],
            priorite=PrioriteRelance.IMPORTANTE,
            champs_confirmation=["impact_quotidien", "_verbatim_b"],
            concept_confirmation="fatigabilite",
            question_relance="La douleur provoque-t-elle une fatigue importante qui s'accumule dans la journée ou la semaine ?",
        ),
        _RegleBase(
            id="douleur_003",
            signaux=[r"douleurs?", r"algies?"],
            inference="besoin d'adaptation des activités",
            description_complete="Les douleurs nécessitent une adaptation des activités quotidiennes et professionnelles.",
            confidence="forte",
            sections=["B", "D", "E"],
            priorite=PrioriteRelance.IMPORTANTE,
            champs_confirmation=["impact_quotidien", "_verbatim_d", "droits_demandes"],
            concept_confirmation="limitations_physiques",
            question_relance="Des adaptations ont-elles été mises en place pour tenir compte de vos douleurs (aménagements, pauses, évitement de certains gestes) ?",
        ),
    ],

    "anxiete": [
        _RegleBase(
            id="anxiete_001",
            signaux=[r"anxiété", r"angoisse", r"stress chronique", r"trouble anxieux"],
            inference="comportements d'évitement",
            description_complete="L'anxiété génère des comportements d'évitement qui restreignent les activités sociales et professionnelles.",
            confidence="forte",
            sections=["B", "D", "E"],
            priorite=PrioriteRelance.IMPORTANTE,
            champs_confirmation=["impact_quotidien", "_verbatim_b", "_verbatim_e", "expression_directe"],
            concept_confirmation="evitement_social",
            question_relance="Y a-t-il des situations que vous évitez à cause de l'anxiété ? Des activités ou des lieux que vous ne fréquentez plus ?",
        ),
        _RegleBase(
            id="anxiete_002",
            signaux=[r"anxiété", r"angoisse"],
            inference="difficultés de projection dans l'avenir",
            description_complete="L'anxiété chronique rend difficile la projection dans l'avenir et la construction d'un projet stable.",
            confidence="forte",
            sections=["E"],
            priorite=PrioriteRelance.IMPORTANTE,
            champs_confirmation=["_verbatim_e", "expression_directe", "projet_orientation"],
            concept_confirmation="difficultes_projection",
            question_relance="L'anxiété rend-elle difficile de vous projeter dans l'avenir ou de construire un projet professionnel ou de vie ?",
        ),
        _RegleBase(
            id="anxiete_003",
            signaux=[r"anxiété", r"angoisse", r"stress chronique"],
            inference="impact sur les relations sociales",
            description_complete="L'anxiété affecte les relations avec les autres et la vie sociale.",
            confidence="moyenne",
            sections=["B", "E"],
            priorite=PrioriteRelance.OPTIONNELLE,
            champs_confirmation=["impact_quotidien", "_verbatim_b", "expression_directe"],
            concept_confirmation="evitement_social",
            question_relance="L'anxiété a-t-elle un impact sur vos relations avec les autres ou sur votre vie sociale ?",
        ),
    ],

    "depression": [
        _RegleBase(
            id="depression_001",
            signaux=[r"dépression", r"syndrome dépressif", r"épisode dépressif", r"dépressif"],
            inference="ralentissement psychomoteur",
            description_complete="La dépression entraîne un ralentissement psychomoteur qui réduit la capacité à initier et maintenir des activités.",
            confidence="forte",
            sections=["B", "D"],
            priorite=PrioriteRelance.CRITIQUE,
            champs_confirmation=["impact_quotidien", "_verbatim_b", "_verbatim_d"],
            concept_confirmation="difficultes_concentration",
            question_relance="La dépression ralentit-elle vos gestes et votre capacité à commencer ou terminer des activités du quotidien ?",
        ),
        _RegleBase(
            id="depression_002",
            signaux=[r"dépression", r"syndrome dépressif"],
            inference="perte de motivation et d'initiative",
            description_complete="La dépression engendre une perte de motivation qui rend difficile l'initiation d'actions, y compris les démarches administratives.",
            confidence="forte",
            sections=["B", "D", "E"],
            priorite=PrioriteRelance.IMPORTANTE,
            champs_confirmation=["impact_quotidien", "_verbatim_b", "expression_directe"],
            concept_confirmation="difficultes_projection",
            question_relance="La perte de motivation affecte-t-elle votre capacité à entreprendre des démarches ou à maintenir des activités ?",
        ),
        _RegleBase(
            id="depression_003",
            signaux=[r"dépression", r"dépressif"],
            inference="isolement social",
            description_complete="La dépression conduit souvent à un retrait social qui aggrave les difficultés quotidiennes.",
            confidence="moyenne",
            sections=["B", "E"],
            priorite=PrioriteRelance.IMPORTANTE,
            champs_confirmation=["impact_quotidien", "_verbatim_b", "expression_directe"],
            concept_confirmation="evitement_social",
            question_relance="La dépression a-t-elle entraîné un retrait des activités sociales ou une prise de distance avec l'entourage ?",
        ),
    ],

    "accident_travail": [
        _RegleBase(
            id="at_001",
            signaux=[r"accident du travail", r"\bAT\b", r"accident professionnel", r"accident.{0,15}travail"],
            inference="rupture de trajectoire professionnelle",
            description_complete="L'accident du travail a constitué une rupture dans la trajectoire professionnelle, avec un avant et un après clairement identifiés.",
            confidence="forte",
            sections=["B", "D"],
            priorite=PrioriteRelance.CRITIQUE,
            champs_confirmation=["impact_quotidien", "_verbatim_b", "_verbatim_d", "expression_directe"],
            concept_confirmation="rupture_trajectoire",
            question_relance="Avant l'accident, quelle était votre situation professionnelle ? En quoi votre quotidien a-t-il changé depuis ?",
        ),
        _RegleBase(
            id="at_002",
            signaux=[r"accident du travail", r"\bAT\b", r"accident.{0,15}travail"],
            inference="impact professionnel durable",
            description_complete="Les séquelles de l'accident du travail compromettent le retour à l'emploi dans les mêmes conditions qu'avant.",
            confidence="forte",
            sections=["D"],
            priorite=PrioriteRelance.CRITIQUE,
            champs_confirmation=["statut_emploi", "_verbatim_d", "qualification_section_d"],
            concept_confirmation="impact_professionnel",
            question_relance="L'accident vous a-t-il empêché de reprendre votre métier ? Depuis combien de temps êtes-vous sans emploi ou en arrêt ?",
        ),
        _RegleBase(
            id="at_003",
            signaux=[r"accident du travail", r"accident professionnel"],
            inference="possible dimension psychotraumatique",
            description_complete="Un accident du travail peut entraîner des répercussions psychologiques durables au-delà des séquelles physiques.",
            confidence="moyenne",
            sections=["B", "E"],
            priorite=PrioriteRelance.IMPORTANTE,
            champs_confirmation=["impact_quotidien", "_verbatim_b", "expression_directe"],
            concept_confirmation="rupture_trajectoire",
            question_relance="L'accident a-t-il des répercussions psychologiques ? Certaines situations vous rappellent-elles cet événement ?",
        ),
    ],

    "tsa": [
        _RegleBase(
            id="tsa_001",
            signaux=[r"autis", r"\btsa\b", r"asperger", r"trouble.{0,10}spectre"],
            inference="difficultés de gestion des imprévus",
            description_complete="Le TSA engendre des difficultés importantes face aux changements imprévus dans la routine.",
            confidence="forte",
            sections=["B", "C", "D"],
            priorite=PrioriteRelance.CRITIQUE,
            champs_confirmation=["impact_quotidien", "_verbatim_b", "_verbatim_d"],
            concept_confirmation="gestion_imprevus",
            question_relance="Les changements imprévus dans la routine créent-ils des difficultés importantes ? Comment se manifestent-elles concrètement ?",
        ),
        _RegleBase(
            id="tsa_002",
            signaux=[r"autis", r"\btsa\b", r"asperger"],
            inference="surcharge sensorielle possible",
            description_complete="Le TSA peut entraîner une hypersensibilité sensorielle générant des surcharges dans certains environnements.",
            confidence="forte",
            sections=["B", "D"],
            priorite=PrioriteRelance.CRITIQUE,
            champs_confirmation=["impact_quotidien", "_verbatim_b"],
            concept_confirmation="surcharge_sensorielle",
            question_relance="Certains environnements (bruit, lumière, foule) provoquent-ils une grande fatigue ou une sensation d'être dépassé(e) ?",
        ),
        _RegleBase(
            id="tsa_003",
            signaux=[r"autis", r"\btsa\b"],
            inference="fatigue sociale",
            description_complete="Les interactions sociales représentent un effort cognitif important générant une fatigue spécifique.",
            confidence="forte",
            sections=["B", "D", "E"],
            priorite=PrioriteRelance.IMPORTANTE,
            champs_confirmation=["impact_quotidien", "_verbatim_b", "expression_directe"],
            concept_confirmation="evitement_social",
            question_relance="Les interactions sociales ou les réunions génèrent-elles une fatigue importante ? Combien de temps faut-il pour récupérer ?",
        ),
    ],

    "psychique": [
        _RegleBase(
            id="psychique_001",
            signaux=[r"schizophréni", r"bipolarité", r"trouble bipolaire", r"psychose",
                     r"trouble.{0,15}psychique", r"trouble.{0,15}psychiatrique"],
            inference="variabilité des capacités",
            description_complete="Le handicap psychique entraîne une variabilité importante des capacités selon les périodes, rendant la planification difficile.",
            confidence="forte",
            sections=["B", "D"],
            priorite=PrioriteRelance.CRITIQUE,
            champs_confirmation=["impact_quotidien", "_verbatim_b", "_verbatim_d"],
            concept_confirmation="variabilite_capacites",
            question_relance="Y a-t-il des différences importantes entre les bonnes et les mauvaises périodes ? Que pouvez-vous faire ou ne plus faire lors des mauvaises périodes ?",
        ),
        _RegleBase(
            id="psychique_002",
            signaux=[r"schizophréni", r"bipolarité", r"psychose", r"trouble.{0,15}psychique"],
            inference="difficultés de projection",
            description_complete="La variabilité des symptômes rend difficile la projection dans l'avenir et la construction d'un projet professionnel stable.",
            confidence="forte",
            sections=["D", "E"],
            priorite=PrioriteRelance.IMPORTANTE,
            champs_confirmation=["_verbatim_e", "projet_orientation", "expression_directe"],
            concept_confirmation="difficultes_projection",
            question_relance="La maladie rend-elle difficile d'envisager un projet professionnel ou de vie à moyen terme ?",
        ),
        _RegleBase(
            id="psychique_003",
            signaux=[r"schizophréni", r"bipolarité", r"trouble bipolaire", r"trouble.{0,15}psychique"],
            inference="fatigabilité psychique",
            description_complete="Le handicap psychique génère une fatigabilité spécifique qui affecte les capacités de maintien d'une activité.",
            confidence="forte",
            sections=["B", "D"],
            priorite=PrioriteRelance.IMPORTANTE,
            champs_confirmation=["impact_quotidien", "_verbatim_b"],
            concept_confirmation="fatigabilite",
            question_relance="La maladie engendre-t-elle une fatigue importante ? Cette fatigue varie-t-elle selon les périodes ?",
        ),
    ],

    "di": [
        _RegleBase(
            id="di_001",
            signaux=[r"déficience intellectuelle", r"retard mental", r"trisomie",
                     r"syndrome de down", r"\bdi\b.{0,5}(légère|modérée|sévère)"],
            inference="besoin d'accompagnement pour les actes de la vie",
            description_complete="La déficience intellectuelle nécessite un accompagnement pour les actes de la vie quotidienne et les décisions.",
            confidence="forte",
            sections=["B", "D", "E"],
            priorite=PrioriteRelance.CRITIQUE,
            champs_confirmation=["impact_quotidien", "_verbatim_b", "expression_directe"],
            concept_confirmation="besoin_accompagnement",
            question_relance="Quels actes de la vie quotidienne peuvent être réalisés seul(e) ? Pour lesquels une aide ou une supervision est-elle nécessaire ?",
        ),
        _RegleBase(
            id="di_002",
            signaux=[r"déficience intellectuelle", r"retard mental", r"trisomie"],
            inference="vulnérabilité face aux risques",
            description_complete="La déficience intellectuelle génère une vulnérabilité spécifique face à la gestion de l'argent, aux risques et aux influences extérieures.",
            confidence="forte",
            sections=["B", "E"],
            priorite=PrioriteRelance.CRITIQUE,
            champs_confirmation=["impact_quotidien", "_verbatim_b", "expression_directe"],
            concept_confirmation="vulnerabilite",
            question_relance="La gestion de l'argent et la compréhension des risques sont-elles possibles de façon autonome ? Y a-t-il des situations de vulnérabilité face aux autres ?",
        ),
        _RegleBase(
            id="di_003",
            signaux=[r"déficience intellectuelle", r"trisomie", r"retard mental"],
            inference="difficultés administratives",
            description_complete="La déficience intellectuelle rend très difficile la compréhension et la gestion des démarches administratives.",
            confidence="forte",
            sections=["B", "E"],
            priorite=PrioriteRelance.IMPORTANTE,
            champs_confirmation=["impact_quotidien", "_verbatim_b"],
            concept_confirmation="besoin_accompagnement",
            question_relance="La compréhension des démarches administratives et des documents officiels est-elle possible de façon autonome ?",
        ),
    ],

    "combinaisons": [
        _RegleBase(
            id="combi_001",
            signaux=[r"douleurs?", r"troubles? du sommeil"],  # les DEUX doivent être présents
            inference="fatigue à double source non récupérable",
            description_complete="La combinaison douleurs chroniques et troubles du sommeil produit une fatigue à double source qui ne récupère pas par le repos habituel.",
            confidence="forte",
            sections=["B", "D"],
            priorite=PrioriteRelance.CRITIQUE,
            champs_confirmation=["impact_quotidien", "_verbatim_b"],
            concept_confirmation="fatigabilite",
            question_relance="La fatigue est-elle présente même après une nuit de sommeil ? Est-elle liée à la fois aux douleurs et aux traitements ?",
        ),
        _RegleBase(
            id="combi_002",
            signaux=[r"anxiété|angoisse", r"accident du travail|accident professionnel"],
            inference="probable dimension psychotraumatique",
            description_complete="L'association anxiété + accident du travail suggère une possible dimension psychotraumatique durable à explorer.",
            confidence="forte",
            sections=["B", "E"],
            priorite=PrioriteRelance.IMPORTANTE,
            champs_confirmation=["impact_quotidien", "_verbatim_b", "expression_directe"],
            concept_confirmation="rupture_trajectoire",
            question_relance="Certaines situations rappellent-elles l'accident ? Avez-vous encore du mal à parler de cet événement ou à vous en souvenir sans souffrir ?",
        ),
        _RegleBase(
            id="combi_003",
            signaux=[r"médicament.{0,20}(anxiété|sommeil|douleur)", r"douleurs?|troubles? du sommeil|anxiété"],
            inference="effets secondaires cognitifs des traitements",
            description_complete="Les traitements psychotropes et antalgiques peuvent engendrer des effets cognitifs : ralentissement, concentration réduite, sédation.",
            confidence="forte",
            sections=["B", "D"],
            priorite=PrioriteRelance.IMPORTANTE,
            champs_confirmation=["impact_quotidien", "_verbatim_b", "_verbatim_d"],
            concept_confirmation="difficultes_concentration",
            question_relance="Les traitements ont-ils des effets secondaires sur votre fonctionnement quotidien (somnolence, ralentissement, difficultés à vous concentrer) ?",
        ),
        _RegleBase(
            id="combi_004",
            signaux=[r"accident du travail|accident professionnel", r"sans emploi|arrêt.{0,15}travail|ne travaille plus"],
            inference="besoin d'un bilan de capacités avant orientation professionnelle",
            description_complete="L'accident du travail + l'absence d'emploi durable suggèrent qu'un bilan de capacités est nécessaire avant toute orientation professionnelle.",
            confidence="forte",
            sections=["D", "E"],
            priorite=PrioriteRelance.CRITIQUE,
            champs_confirmation=["statut_emploi", "_verbatim_d", "qualification_section_d", "projet_orientation"],
            concept_confirmation="impact_professionnel",
            question_relance="Avez-vous un projet professionnel ou souhaitez-vous faire un bilan de vos capacités pour en construire un ? Un ESPO ou une évaluation UEROS a-t-il déjà été évoqué ?",
        ),
        _RegleBase(
            id="combi_005",
            signaux=[r"dépression|syndrome dépressif", r"anxiété|angoisse"],
            inference="double fragilité psychique — collecte adaptée nécessaire",
            description_complete="La combinaison dépression et anxiété nécessite une attention particulière dans la collecte et la formulation des questions.",
            confidence="forte",
            sections=["B", "D", "E"],
            priorite=PrioriteRelance.IMPORTANTE,
            champs_confirmation=["impact_quotidien", "_verbatim_b", "expression_directe"],
            concept_confirmation="difficultes_projection",
            question_relance="Comment se passent les journées difficiles ? Qu'est-ce qui est impossible à faire ces jours-là ?",
        ),
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# FONCTIONS INTERNES
# ─────────────────────────────────────────────────────────────────────────────

def _texte_source(donnees: dict[str, Any]) -> str:
    """Construit le texte source pour la détection de signaux."""
    champs = [
        "diagnostics", "traitements", "impact_quotidien",
        "statut_emploi", "historique_mdph",
    ]
    return " ".join(str(donnees.get(c, "") or "") for c in champs).lower()


def _texte_declarations(donnees: dict[str, Any]) -> str:
    """Construit le texte des données déclarées pour la confirmation."""
    champs_verbatim = ["_verbatim_b", "_verbatim_c", "_verbatim_d", "_verbatim_e"]
    champs_texte = [
        "impact_quotidien", "expression_directe", "statut_emploi",
        "projet_orientation", "droits_demandes",
    ]
    parties = []
    for c in champs_texte:
        v = donnees.get(c, "")
        if v:
            parties.append(str(v))
    for c in champs_verbatim:
        lst = donnees.get(c, []) or []
        parties.extend(lst)

    # Textes narratifs si générés
    for c in ["texte_b_vie_quotidienne", "texte_d_situation_pro", "texte_e_projet_vie"]:
        v = donnees.get(c, "")
        if v:
            parties.append(str(v)[:400])

    return " ".join(parties).lower()


def _signal_present(texte: str, signaux: list[str]) -> bool:
    """
    Vérifie si au moins un signal est présent dans le texte.
    Pour les règles de combinaison (combi_*), tous les signaux doivent être présents.
    """
    return any(re.search(p, texte, re.IGNORECASE) for p in signaux)


def _signal_present_tous(texte: str, signaux: list[str]) -> bool:
    """Vérifie que TOUS les signaux sont présents (règles de combinaison)."""
    return all(re.search(p, texte, re.IGNORECASE) for p in signaux)


def _confirmer(
    regle: _RegleBase,
    texte_declarations: str,
) -> tuple[EtatConfirmation, str, str]:
    """
    Cherche la confirmation dans les données déclarées.
    Retourne (état, fragment, source_champ).
    """
    synonymes = _SYNONYMES.get(regle.concept_confirmation, [])

    # Confirmation directe : inference mot ou synonyme exact dans les déclarés
    tous_patterns = [re.escape(regle.inference)] + synonymes
    for p in tous_patterns:
        m = re.search(p, texte_declarations, re.IGNORECASE)
        if m:
            start = max(0, m.start() - 30)
            end   = min(len(texte_declarations), m.end() + 50)
            fragment = texte_declarations[start:end].strip()
            etat = EtatConfirmation.DIRECTE if p == re.escape(regle.inference) else EtatConfirmation.INDIRECTE
            # Identifier le champ source
            source = _identifier_source(fragment, regle.champs_confirmation)
            return etat, fragment, source

    return EtatConfirmation.ABSENTE, "", ""


def _identifier_source(fragment: str, champs: list[str]) -> str:
    """Identifie quel champ a fourni le fragment confirmatif."""
    # Heuristique : retourne le premier champ probable
    for c in champs:
        if "verbatim" in c:
            return "verbatim"
        if c in ("impact_quotidien", "expression_directe"):
            return c
    return champs[0] if champs else "inconnu"


def _detecter_regles(donnees: dict[str, Any]) -> list[tuple[str, _RegleBase]]:
    """Retourne les règles dont les signaux sont présents, avec leur catégorie."""
    texte = _texte_source(donnees)
    applicables = []
    for categorie, regles in _REGLES.items():
        for regle in regles:
            if categorie == "combinaisons":
                if _signal_present_tous(texte, regle.signaux):
                    applicables.append((categorie, regle))
            else:
                if _signal_present(texte, regle.signaux):
                    applicables.append((categorie, regle))
    return applicables


def _filtrer_confidence(regles: list[_RegleBase], confidence_min: str = "moyenne") -> list[_RegleBase]:
    """Filtre par niveau de confiance minimum."""
    niveaux = {"forte": 2, "moyenne": 1, "faible": 0}
    seuil = niveaux.get(confidence_min, 1)
    return [r for r in regles if niveaux.get(r.confidence, 0) >= seuil]


def _calculer_coverage(hypotheses: list[Hypothese]) -> InferenceCoverage:
    total      = len(hypotheses)
    directes   = sum(1 for h in hypotheses if h.confirmation == EtatConfirmation.DIRECTE)
    indirectes = sum(1 for h in hypotheses if h.confirmation == EtatConfirmation.INDIRECTE)
    absentes   = sum(1 for h in hypotheses if h.confirmation == EtatConfirmation.ABSENTE)
    taux       = round((directes + indirectes) / total, 3) if total else 0.0

    nc_crit  = sum(1 for h in hypotheses if h.confirmation == EtatConfirmation.ABSENTE and h.priorite == PrioriteRelance.CRITIQUE)
    nc_imp   = sum(1 for h in hypotheses if h.confirmation == EtatConfirmation.ABSENTE and h.priorite == PrioriteRelance.IMPORTANTE)

    return InferenceCoverage(
        total_detectees=total,
        confirmees_directes=directes,
        confirmees_indirectes=indirectes,
        non_confirmees=absentes,
        taux_couverture=taux,
        non_confirmees_critiques=nc_crit,
        non_confirmees_importantes=nc_imp,
    )


def _extraire_confirmed_records(
    hypotheses: list[Hypothese],
    profil_principal: str,
    profil_mdph: str,
) -> list[ConfirmedHypothesisRecord]:
    """
    Extrait uniquement les hypothèses confirmées (DIRECTE ou INDIRECTE).
    Jamais ABSENTE. Fragment anonymisé (80 chars max, sans identifiants).
    """
    records = []
    for h in hypotheses:
        if h.confirmation == EtatConfirmation.ABSENTE:
            continue
        fragment = h.fragment_confirmatif[:80] if h.fragment_confirmatif else ""
        records.append(ConfirmedHypothesisRecord(
            hypothese_id=h.id,
            signal_source=h.signal_source,
            inference=h.inference,
            etat_confirmation=h.confirmation.value,
            fragment=fragment,
            source_confirmation=_identifier_source(fragment, h.champs_confirmation),
            profil_principal=profil_principal,
            profil_mdph=profil_mdph,
        ))
    return records


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE PUBLIC
# ─────────────────────────────────────────────────────────────────────────────

def inferer_contexte_mdph(
    donnees: dict[str, Any],
    profil_principal: str = "",
    profil_mdph: str = "adulte",
) -> ContexteInfere:
    """
    Produit le contexte inféré à partir des données collectées.

    Les hypothèses ABSENTES génèrent relances, alertes et informations manquantes.
    Les hypothèses confirmées alimentent le référentiel statistique.
    Aucune hypothèse n'est injectée dans le moteur narratif.
    """
    texte_declarations = _texte_declarations(donnees)

    # Détection des règles applicables (confidence >= moyenne)
    _toutes_regles = _detecter_regles(donnees)
    # Filtrage par confidence
    niveaux = {"forte": 2, "moyenne": 1, "faible": 0}
    regles_applicables = [(cat, r) for cat, r in _toutes_regles if niveaux.get(r.confidence, 0) >= 1]

    # Déduplication : ne garder qu'une règle par (signal, inference)
    concepts_vus: set[str] = set()
    regles_uniques: list[tuple[str, _RegleBase]] = []
    for cat, r in regles_applicables:
        cle = f"{r.signaux[0] if r.signaux else r.id}_{r.inference}"
        if cle not in concepts_vus:
            concepts_vus.add(cle)
            regles_uniques.append((cat, r))

    hypotheses:      list[Hypothese]           = []
    informations:    list[InformationManquante]  = []
    relances:        list[RelanceSuggeree]       = []
    alertes:         list[AlerteQualiteInferee]  = []

    for cat, regle in regles_uniques:
        etat, fragment, source = _confirmer(regle, texte_declarations)

        h = Hypothese(
            id=regle.id,
            signal_source=regle.signaux[0] if regle.signaux else "",
            categorie=cat,
            inference=regle.inference,
            description_complete=regle.description_complete,
            confidence=regle.confidence,
            sections=regle.sections,
            confirmation=etat,
            champs_confirmation=regle.champs_confirmation,
            fragment_confirmatif=fragment,
            priorite=regle.priorite,
            question_relance=regle.question_relance,
        )
        hypotheses.append(h)

        # Log d'auditabilité
        logger.info(
            "[INFERENCER] signal=%-35s | inference=%-40s | conf=%s | etat=%s",
            regle.signaux[0][:35] if regle.signaux else "",
            regle.inference[:40],
            regle.confidence,
            etat.value,
        )

        # Traitement des hypothèses ABSENTES uniquement
        if etat == EtatConfirmation.ABSENTE:
            informations.append(InformationManquante(
                label=f"{regle.inference} — non renseigné(e) alors que {regle.signaux[0]} déclaré",
                hypothese_id=regle.id,
                section=regle.sections[0] if regle.sections else "B",
                priorite=regle.priorite,
            ))

            relances.append(RelanceSuggeree(
                question=regle.question_relance,
                contexte_interne=f"Signal : {regle.signaux[0]} | Inférence : {regle.inference} | Non confirmé",
                hypothese_id=regle.id,
                section=regle.sections[0] if regle.sections else "B",
                priorite=regle.priorite,
            ))

            # Alertes qualité
            if regle.priorite == PrioriteRelance.CRITIQUE:
                alertes.append(AlerteQualiteInferee(
                    message=f"{regle.signaux[0].capitalize()} déclaré(e) mais {regle.inference} non documenté(e) en section {regle.sections[0]}",
                    hypothese_id=regle.id,
                    type_alerte="zone_pauvre",
                    section=regle.sections[0] if regle.sections else "B",
                    niveau="rouge",
                ))
            elif regle.priorite == PrioriteRelance.IMPORTANTE:
                alertes.append(AlerteQualiteInferee(
                    message=f"{regle.inference} probable mais non exploré(e)",
                    hypothese_id=regle.id,
                    type_alerte="information_manquante",
                    section=regle.sections[0] if regle.sections else "B",
                    niveau="orange",
                ))

    # Trier relances : critiques en premier, puis importantes, puis optionnelles
    _ordre = {PrioriteRelance.CRITIQUE: 0, PrioriteRelance.IMPORTANTE: 1, PrioriteRelance.OPTIONNELLE: 2}
    relances.sort(key=lambda r: _ordre.get(r.priorite, 99))

    # Coverage
    coverage = _calculer_coverage(hypotheses)

    # Confirmed records (DIRECTE + INDIRECTE uniquement)
    confirmed = _extraire_confirmed_records(hypotheses, profil_principal, profil_mdph)

    logger.info(
        "[INFERENCER] total=%d | directes=%d | indirectes=%d | absentes=%d | couverture=%.0f%% | nc_crit=%d",
        coverage.total_detectees,
        coverage.confirmees_directes,
        coverage.confirmees_indirectes,
        coverage.non_confirmees,
        coverage.taux_couverture * 100,
        coverage.non_confirmees_critiques,
    )

    return ContexteInfere(
        hypotheses=hypotheses,
        confirmed_hypotheses=confirmed,
        informations_manquantes=informations,
        relances_suggerees=relances,
        alertes_qualite=alertes,
        coverage=coverage,
        profil_source=profil_principal or profil_mdph,
    )


def relance_critique_active(contexte: ContexteInfere, sections_deja_posees: set[str] | None = None) -> RelanceSuggeree | None:
    """
    Retourne la première relance CRITIQUE non encore posée.
    Une seule relance critique maximum par tour.
    sections_deja_posees : set d'hypothese_id déjà traités.
    """
    deja_posees = sections_deja_posees or set()
    for r in contexte.relances_suggerees:
        if r.priorite == PrioriteRelance.CRITIQUE and r.hypothese_id not in deja_posees:
            return r
    return None
