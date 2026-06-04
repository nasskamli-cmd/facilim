"""
app/engines/profil_specifique_engine.py — Questions, relances et axes spécifiques par profil.

Quatre profils couverts en V1 : tsa · psychique_humeur · psychique_psychotique · moteur · di

Architecture en deux niveaux :
  - profil_principal  : tsa | psychique | moteur | di | ...
  - sous_profil       : psychique_humeur | psychique_psychotique (pour le profil psychique)

Les contrôles qualité évaluent des THÈMES (concepts) et non des mots-clés.
L'évaluation thématique est déléguée à GPT-4o-mini pour éviter les faux négatifs lexicaux.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("facilim.engines.profil_specifique")


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURE DE DONNÉES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ProfilSpecifique:
    """Contenu métier d'un profil handicap pour enrichir la collecte et la narration."""

    profil:              str
    sous_profil:         str   = ""

    # Questions additionnelles injectées dans le contexte de l'agent
    questions_b:         list[str] = field(default_factory=list)  # vie quotidienne
    questions_d:         list[str] = field(default_factory=list)  # emploi
    questions_e:         list[str] = field(default_factory=list)  # projet de vie

    # Relances spécifiques (remplacent la relance générique si profil détecté)
    relances_b:          list[str] = field(default_factory=list)
    relances_d:          list[str] = field(default_factory=list)
    relances_e:          list[str] = field(default_factory=list)

    # Axes de retentissement obligatoires pour le moteur narratif
    axes_retentissement_b: list[str] = field(default_factory=list)
    axes_retentissement_d: list[str] = field(default_factory=list)
    axes_retentissement_e: list[str] = field(default_factory=list)

    # Thèmes obligatoires pour le contrôle qualité (évaluation thématique, pas lexicale)
    themes_qualite_b:    list[str] = field(default_factory=list)
    themes_qualite_e:    list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# PROFIL TSA
# ─────────────────────────────────────────────────────────────────────────────

TSA = ProfilSpecifique(
    profil="tsa",

    questions_b=[
        "Y a-t-il des environnements ou des situations qui provoquent une grande fatigue "
        "ou un sentiment d'être dépassé(e) ? (bruit, lumière, foule, changements imprévus)",

        "Comment votre enfant / vous réagissez quand quelque chose change de façon imprévue "
        "dans la routine habituelle ?",

        "Comment se passe la communication au quotidien ? "
        "(langage oral, écrit, pictogrammes, autre moyen ?)",

        "Y a-t-il des moments dans la journée qui sont particulièrement difficiles ? "
        "Est-ce que des crises ou des effondrements surviennent, et à quelle fréquence ?",
    ],

    questions_e=[
        "Quel type d'environnement ou d'accompagnement permettrait de mieux "
        "fonctionner au quotidien ?",

        "Y a-t-il un projet professionnel ou d'activité ? "
        "Un accompagnement spécialisé serait-il utile pour le mettre en place ?",
    ],

    relances_b=[
        "Pouvez-vous décrire une situation concrète récente où il y a eu une surcharge "
        "ou une crise ? Comment ça s'est passé, et combien de temps ça a duré ?",

        "Quand la routine change, qu'est-ce qui se passe concrètement ? "
        "Ça dure combien de temps avant que la situation se stabilise ?",
    ],

    relances_e=[
        "Dans l'idéal, quel type d'accompagnement ou de structure permettrait "
        "à votre enfant / à vous de mieux vivre au quotidien ?",
    ],

    axes_retentissement_b=[
        "Hypersensibilité ou hyposensibilité sensorielle (sons, lumières, textures, foules) "
        "— déclencheurs et conséquences sur le fonctionnement quotidien",
        "Rigidité et attachement aux routines — conséquences des changements imprévus",
        "Communication sociale — ce que la personne ne peut pas faire en interaction",
        "Régulation émotionnelle — fréquence, durée et conséquences des crises ou effondrements",
        "Fonctions exécutives — planification, initiation de tâches, gestion administrative",
    ],

    axes_retentissement_e=[
        "Besoin d'un environnement structuré et prévisible",
        "Type d'accompagnement souhaité : SAVS/SAMSAH spécialisé TSA, job coaching",
        "Orientation : EA, ESAT, milieu ordinaire avec soutien, autre",
        "Attentes concrètes vis-à-vis de la MDPH",
    ],

    # Thèmes évalués par GPT — concepts, pas mots-clés
    themes_qualite_b=[
        "gestion des imprévus et de la rigidité aux routines",
        "environnement sensoriel et surcharges",
        "difficultés de communication et d'interaction sociale",
        "régulation émotionnelle et épisodes de crise ou d'effondrement",
    ],

    themes_qualite_e=[
        "besoin d'un environnement structuré et adapté",
        "projet d'orientation ou d'accompagnement spécialisé",
    ],
)


# ─────────────────────────────────────────────────────────────────────────────
# PROFIL PSYCHIQUE — architecture à deux sous-profils
# ─────────────────────────────────────────────────────────────────────────────

def _questions_psychique_communes() -> list[str]:
    return [
        "Comment se passent les jours difficiles concrètement ? "
        "Qu'est-ce que vous ne pouvez plus faire ces jours-là ?",

        "À quelle fréquence les périodes difficiles arrivent-elles ? "
        "(tous les jours, par semaines, par épisodes de plusieurs semaines ?)",

        "Est-ce que le traitement a des effets secondaires qui gênent "
        "dans la vie de tous les jours ?",
    ]


def _axes_b_psychique_communes() -> list[str]:
    return [
        "Variabilité des symptômes — distinction jours stables / jours difficiles / crises",
        "Rythme et sommeil — hypersomnie, insomnie, inversion nuit/jour",
        "Isolement social — rupture des liens, retrait, peur du regard des autres",
        "Gestion administrative — incapacité à ouvrir le courrier, gérer les démarches",
        "Effets du traitement sur le fonctionnement quotidien",
    ]


def _themes_qualite_b_psychique() -> list[str]:
    return [
        "variabilité des symptômes entre les bonnes et mauvaises périodes",
        "impact sur le rythme de vie, le sommeil et l'organisation quotidienne",
        "isolement social ou rupture des liens",
        "effets du traitement ou difficultés liées à la maladie sur le quotidien",
    ]


PSYCHIQUE_HUMEUR = ProfilSpecifique(
    profil="psychique",
    sous_profil="psychique_humeur",  # dépression sévère, bipolarité, dysthymie

    questions_b=_questions_psychique_communes() + [
        "Y a-t-il des périodes où vous ne pouvez plus quitter le domicile ou le lit ? "
        "Combien de temps ça dure en général ?",
    ],

    questions_d=[
        "Avez-vous déjà dû vous absenter du travail à cause de votre état de santé ? "
        "Pour combien de temps, et combien de fois ces dernières années ?",
    ],

    questions_e=[
        "Qu'est-ce qui vous aiderait le plus à aller mieux ou à maintenir une stabilité ? "
        "(accompagnement, logement, activité, lien social...)",
    ],

    relances_b=[
        "Sur une journée difficile, à quoi ressemble votre matinée ? "
        "Qu'est-ce qui est impossible à faire ?",

        "Pendant les épisodes difficiles, est-ce que quelqu'un vous aide ? "
        "Qui, et pour quoi faire concrètement ?",
    ],

    relances_d=[
        "Pendant les périodes difficiles, comment ça se passe au travail ? "
        "Est-ce que vos collègues ou votre employeur sont au courant ?",
    ],

    axes_retentissement_b=_axes_b_psychique_communes() + [
        "Épisodes dépressifs ou maniaques — durée, fréquence, conséquences sur l'autonomie",
    ],

    axes_retentissement_d=[
        "Absentéisme lié aux épisodes — historique, durée des arrêts",
        "Impact des symptômes sur la concentration et la productivité au travail",
        "Relations professionnelles pendant les épisodes difficiles",
    ],

    axes_retentissement_e=[
        "Besoin de stabilité résidentielle et d'accompagnement thérapeutique pérenne",
        "Souhait de maintenir ou retrouver une activité adaptée",
        "Plan de crise : que faire lors d'une décompensation ?",
    ],

    themes_qualite_b=_themes_qualite_b_psychique() + [
        "épisodes dépressifs ou maniaques et leurs conséquences fonctionnelles",
    ],

    themes_qualite_e=[
        "projet de vie tenant compte de la variabilité des symptômes",
        "besoins de soutien thérapeutique et social",
    ],
)


PSYCHIQUE_PSYCHOTIQUE = ProfilSpecifique(
    profil="psychique",
    sous_profil="psychique_psychotique",  # schizophrénie, trouble schizo-affectif

    questions_b=_questions_psychique_communes() + [
        "Y a-t-il eu des hospitalisations en psychiatrie ces dernières années ? "
        "Combien, et pour combien de temps environ ?",

        "Est-ce que vous / la personne vit seul(e), en famille, en foyer, "
        "ou avec un soutien à domicile ?",
    ],

    questions_d=[
        "Quelle est la situation professionnelle ou d'activité actuelle ? "
        "(ESAT, domicile, établissement, sans activité...)",

        "Y a-t-il des projets d'orientation vers une structure adaptée ?",
    ],

    questions_e=[
        "Qu'est-ce qui permettrait d'améliorer la stabilité au quotidien ? "
        "(accompagnement, logement adapté, activité structurée...)",
    ],

    relances_b=[
        "Sur une mauvaise journée, qu'est-ce qui est impossible à faire ? "
        "Est-ce que quelqu'un intervient pour aider à ce moment-là ?",

        "Comment se passe la gestion du quotidien : les courses, le ménage, "
        "les rendez-vous médicaux — qui s'en occupe ?",
    ],

    relances_d=[
        "Au travail ou en activité, comment se passent les relations avec les autres ? "
        "Y a-t-il eu des difficultés liées à la maladie ?",
    ],

    axes_retentissement_b=_axes_b_psychique_communes() + [
        "Hospitalisations — fréquence, durée, impact sur la continuité de vie",
        "Autonomie dans les actes essentiels — ce qui nécessite une supervision",
    ],

    axes_retentissement_d=[
        "Activité actuelle (ESAT, domicile, établissement) et son adéquation",
        "Capacité à maintenir une activité structurée dans la durée",
        "Projet d'orientation ou de réorientation",
    ],

    axes_retentissement_e=[
        "Besoin d'un accompagnement structuré et continu (SAVS, SAMSAH)",
        "Stabilité du logement comme condition de la stabilité psychiatrique",
        "Souhait d'orientation : ESAT, foyer de vie, MAS/FAM selon le niveau d'autonomie",
        "Plan de crise et contacts en cas de décompensation",
    ],

    themes_qualite_b=_themes_qualite_b_psychique() + [
        "hospitalisations et leur impact sur la continuité de vie",
        "niveau d'autonomie réel dans les actes essentiels",
    ],

    themes_qualite_e=[
        "projet d'orientation en structure adaptée",
        "besoins d'accompagnement structuré pour la stabilité",
        "plan de crise ou dispositif de soutien en cas de décompensation",
    ],
)


# ─────────────────────────────────────────────────────────────────────────────
# PROFIL MOTEUR
# ─────────────────────────────────────────────────────────────────────────────

MOTEUR = ProfilSpecifique(
    profil="moteur",

    questions_b=[
        "Y a-t-il des différences entre une bonne journée et une mauvaise journée "
        "sur vos capacités physiques ? À quelle heure de la journée êtes-vous "
        "au maximum ? Au minimum ?",

        "Utilisez-vous des aides techniques (fauteuil, déambulateur, orthèses, "
        "voiture adaptée...) ? Y en a-t-il dont vous auriez besoin et que vous "
        "n'avez pas encore ?",

        "Votre logement est-il accessible et adapté ? "
        "Pouvez-vous sortir seul(e) de votre domicile ?",
    ],

    questions_d=[
        "Au travail, y a-t-il des tâches que vous ne pouvez plus effectuer "
        "à cause de vos limitations physiques ?",

        "Des aménagements de poste ont-ils été mis en place ou demandés ?",
    ],

    relances_b=[
        "Le matin et le soir, est-ce pareil pour vous ? "
        "Y a-t-il des moments où c'est plus difficile ou plus facile ?",

        "Pour les soins du matin — se lever, toilette, s'habiller — "
        "combien de temps ça prend et avez-vous besoin d'aide pour certains gestes ?",
    ],

    relances_d=[
        "Est-ce que la fatigue physique affecte votre capacité à travailler "
        "sur la durée de la journée ou de la semaine ?",
    ],

    axes_retentissement_b=[
        "Endurance physique et variabilité dans la journée (matin/soir, bonnes/mauvaises journées)",
        "Mobilité fine et déplacements — intérieur, extérieur, conduite — ce qui est impossible",
        "Aides techniques en place — équipements utilisés, efficacité, lacunes",
        "Charge sur l'aidant familial — ce que le conjoint ou la famille assume",
        "Accessibilité du domicile — barrières architecturales restantes",
    ],

    axes_retentissement_d=[
        "Tâches professionnelles incompatibles avec les limitations physiques",
        "Aménagements de poste réalisés ou nécessaires",
        "Fatigabilité professionnelle sur la journée et la semaine",
    ],

    axes_retentissement_e=[
        "PCH aide humaine — actes nécessitant une aide, nombre d'heures estimé",
        "PCH aide technique — équipement prioritaire manquant",
        "CMI priorité ou stationnement — justification concrète par les limitations",
        "Maintien à domicile versus orientation en établissement",
    ],

    themes_qualite_b=[
        "variabilité des capacités physiques selon les moments de la journée",
        "aides techniques utilisées ou manquantes",
        "impact sur la mobilité et les déplacements",
        "charge sur l'entourage et les aidants",
    ],

    themes_qualite_e=[
        "besoins de compensation technique ou humaine argumentés",
        "projet de maintien à domicile ou d'orientation",
    ],
)


# ─────────────────────────────────────────────────────────────────────────────
# PROFIL DÉFICIENCE INTELLECTUELLE
# ─────────────────────────────────────────────────────────────────────────────

DI = ProfilSpecifique(
    profil="di",

    questions_b=[
        "Dans la vie de tous les jours, qu'est-ce que votre enfant / la personne "
        "peut faire seul(e) ? Qu'est-ce qu'il/elle ne peut pas faire sans aide "
        "ou sans supervision ?",

        "Comment se passe la communication : comprend-il/elle les consignes simples ? "
        "Les consignes complexes ? Peut-il/elle exprimer ses besoins et ses émotions ?",

        "Y a-t-il des comportements particuliers qui compliquent la vie quotidienne ? "
        "(agitation, automutilation, fugues, opposition...)",

        # Axe VULNÉRABILITÉ — obligatoire
        "Comment se passe la gestion de l'argent au quotidien ? "
        "Est-ce que la personne comprend la valeur des choses et les risques "
        "liés à l'argent ou aux inconnus ?",

        "Y a-t-il des situations où la personne pourrait être influencée "
        "ou exploitée par d'autres personnes ?",
    ],

    questions_d=[
        "Quelle est l'occupation actuelle ? "
        "(école, ESAT, centre de jour, domicile, autre...)",

        "Y a-t-il un projet d'orientation professionnelle ou d'activité ?",
    ],

    questions_e=[
        "Qu'est-ce qui est le plus important pour l'avenir de votre enfant "
        "/ de la personne ? Quelle vie souhaitez-vous pour lui/elle ?",

        "Qui s'occupera de la personne quand les parents ou les proches "
        "ne pourront plus le faire ? Un projet a-t-il été réfléchi ?",
    ],

    relances_b=[
        "Pouvez-vous me donner un exemple concret d'une tâche simple "
        "que votre enfant / la personne ne peut pas faire seul(e) ?",

        "Quand il/elle rencontre quelqu'un d'inconnu, comment ça se passe ? "
        "Est-ce qu'il/elle comprend ce qui est dangereux ou ce qu'il ne faut pas faire ?",
    ],

    relances_e=[
        "Dans 10 ou 20 ans, quand vous ne pourrez plus vous occuper "
        "de votre enfant / de la personne, qu'est-ce que vous souhaitez pour lui/elle ?",
    ],

    axes_retentissement_b=[
        "Niveau d'autonomie réel — actes possibles seul, avec guidage, impossibles",
        "Communication et compréhension — ce que la personne comprend et peut exprimer",
        "Comportements défis — fréquence, intensité, conséquences sur l'entourage",
        "Charge sur les aidants familiaux — épuisement, organisation, fratrie",
        # Axe VULNÉRABILITÉ
        "Vulnérabilité — gestion de l'argent, compréhension des risques, "
        "sécurité face aux inconnus, risque d'influence ou d'exploitation",
    ],

    axes_retentissement_d=[
        "Occupation actuelle et son adéquation avec les capacités réelles",
        "Capacité à suivre des consignes dans un environnement de travail",
        "Projet d'orientation : ESAT, EA, centre de jour, autre",
    ],

    axes_retentissement_e=[
        "Projet de vie à long terme — qui s'en occupera quand les parents ne pourront plus",
        "Orientation souhaitée : ESAT, MAS, FAM, SAVS, famille d'accueil",
        "Besoins d'accompagnement spécialisé : psychomotricité, orthophonie, éducateur",
        # Axe VULNÉRABILITÉ dans le projet de vie
        "Protection contre la vulnérabilité — mesure de protection juridique souhaitée, "
        "encadrement des actes de la vie civile",
        "Expression des souhaits de la personne elle-même si possible",
    ],

    themes_qualite_b=[
        "niveau d'autonomie réel dans les actes de la vie quotidienne",
        "capacités de communication et d'expression des besoins",
        "comportements défis et leur impact sur l'entourage",
        # Thème VULNÉRABILITÉ
        "vulnérabilité face aux risques, à l'argent et aux influences extérieures",
    ],

    themes_qualite_e=[
        "projet de vie à long terme et après la famille",
        "orientation en structure adaptée",
        "protection juridique ou mesure de sauvegarde si applicable",
    ],
)


# ─────────────────────────────────────────────────────────────────────────────
# PROFIL MALADIE CHRONIQUE
# ─────────────────────────────────────────────────────────────────────────────

MALADIE_CHRONIQUE = ProfilSpecifique(
    profil="maladie_chronique",

    questions_b=[
        "Y a-t-il une différence entre une bonne journée et une mauvaise journée ? "
        "Sur une mauvaise journée, qu'est-ce que vous ne pouvez plus faire du tout ?",

        "La maladie évolue-t-elle de façon stable, ou y a-t-il des périodes "
        "où elle s'aggrave ? Depuis combien de temps la situation est-elle comme ça ?",

        "La fatigue est-elle présente ? À quelle fréquence et à quelle intensité ? "
        "Est-ce qu'elle s'améliore avec le repos, ou pas ?",

        "Est-ce que les traitements ont des effets secondaires qui gênent "
        "dans la vie de tous les jours ? Lesquels concrètement ?",
    ],

    questions_d=[
        "Est-ce que la maladie affecte votre capacité à travailler "
        "de façon régulière ? Y a-t-il des jours où vous ne pouvez pas travailler ?",

        "Des aménagements ont-ils été demandés ou mis en place au travail "
        "(horaires, poste, télétravail...) ?",
    ],

    questions_e=[
        "Qu'est-ce qui changerait le plus votre quotidien si vous aviez "
        "les aides nécessaires ?",
    ],

    relances_b=[
        "Sur une mauvaise journée typique, pouvez-vous me décrire votre matinée "
        "de façon concrète — ce que vous pouvez faire et ce qui est impossible ?",

        "La fatigue dont vous parlez, est-ce qu'elle arrive à certains moments "
        "prévisibles de la journée ou de la semaine, ou de façon imprévisible ?",
    ],

    relances_d=[
        "Depuis le début de la maladie, comment votre situation professionnelle "
        "a-t-elle changé ? Des arrêts de travail, des changements de poste ?",
    ],

    axes_retentissement_b=[
        "Variabilité des symptômes — distinction jours stables / mauvais jours / "
        "périodes de crise ou d'aggravation",
        "Fatigue — nature (physique, cognitive, post-effort), intensité, "
        "imprévisibilité, non-récupération par le repos",
        "Imprévisibilité — impossibilité de planifier, annulations fréquentes, "
        "impact sur la vie sociale et familiale",
        "Effets secondaires des traitements sur le fonctionnement quotidien",
        "Handicap invisible — décalage entre apparence et limitations réelles",
    ],

    axes_retentissement_d=[
        "Absentéisme lié aux poussées ou mauvaises journées — fréquence, durée",
        "Incapacité à tenir des horaires fixes ou à planifier des engagements",
        "Aménagements de poste réalisés ou nécessaires",
        "Impact de la fatigue sur la concentration et les performances au travail",
    ],

    axes_retentissement_e=[
        "Maintien d'une activité adaptée à la variabilité des symptômes",
        "Aides de compensation permettant de vivre malgré l'imprévisibilité",
        "Reconnaissance du handicap invisible et ses enjeux administratifs et sociaux",
        "Projet de vie tenant compte des contraintes médicales à long terme",
    ],

    themes_qualite_b=[
        "variabilité entre bonne et mauvaise journée",
        "fatigue et ses caractéristiques spécifiques (non récupération, imprévisibilité)",
        "impact de l'imprévisibilité sur la vie quotidienne et sociale",
        "effets du traitement sur le fonctionnement",
    ],

    themes_qualite_e=[
        "projet de vie compatible avec la variabilité de la maladie",
        "besoins de compensation pour les jours difficiles",
    ],
)


# ─────────────────────────────────────────────────────────────────────────────
# PROFIL SENSORIEL — deux sous-profils : auditif / visuel
# ─────────────────────────────────────────────────────────────────────────────

def _questions_sensoriel_communes() -> list[str]:
    return [
        "Depuis quand ce trouble est-il présent, et a-t-il évolué au fil du temps ?",
        "Des aides techniques sont-elles utilisées actuellement ? "
        "Y en a-t-il dont vous auriez besoin et que vous n'avez pas encore ?",
    ]


SENSORIEL_AUDITIF = ProfilSpecifique(
    profil="sensoriel",
    sous_profil="sensoriel_auditif",

    questions_b=_questions_sensoriel_communes() + [
        "Comment se passe la communication au quotidien ? "
        "(langue des signes, LPC, lecture labiale, écrit, implant, appareils...)",

        "Y a-t-il des situations de la vie courante qui deviennent très difficiles "
        "à cause de la surdité ? (téléphone, alarmes, conversations de groupe...)",
    ],

    questions_d=[
        "Au travail, la surdité crée-t-elle des difficultés particulières ? "
        "(réunions, appels téléphoniques, communication avec les collègues...)",

        "Des aménagements ont-ils été mis en place ou demandés ? "
        "(boucle magnétique, sous-titrage, interprète LSF...)",
    ],

    questions_e=[
        "Quels aménagements ou accompagnements permettraient d'améliorer "
        "votre participation à la vie sociale et professionnelle ?",
    ],

    relances_b=[
        "Dans une situation de groupe ou dans un lieu bruyant, "
        "comment ça se passe concrètement pour vous ? "
        "Qu'est-ce que vous ne pouvez pas faire que les autres font facilement ?",
    ],

    relances_d=[
        "Est-ce que les collègues ou l'employeur sont au courant de votre surdité ? "
        "Comment ça se passe au quotidien dans les échanges professionnels ?",
    ],

    axes_retentissement_b=[
        "Mode de communication utilisé et ses limitations au quotidien "
        "(téléphone impossible, conversations de groupe difficiles, alarmes non entendues)",
        "Isolement social lié à la surdité — situations évitées, fatigue de la vigilance",
        "Aides auditives en place — efficacité, situations où elles ne suffisent pas",
        "Sécurité au domicile — alertes sonores, sonnette, alarmes",
    ],

    axes_retentissement_d=[
        "Difficultés de communication professionnelle (téléphone, réunions, formations)",
        "Aménagements professionnels en place ou nécessaires",
        "Impact de la fatigue de décodage sur les performances",
    ],

    axes_retentissement_e=[
        "Accès aux services et aux droits — interprète LSF, sous-titrage",
        "Projet d'intégration professionnelle avec aménagements adaptés",
        "Vie sociale et culturelle en lien avec la communauté sourde si applicable",
    ],

    themes_qualite_b=[
        "mode de communication et ses limitations dans la vie quotidienne",
        "situations rendues impossibles ou très difficiles par la surdité",
        "impact sur les relations sociales et l'isolement",
    ],

    themes_qualite_e=[
        "aménagements nécessaires pour la vie sociale et professionnelle",
        "accès aux droits et aux services adaptés",
    ],
)


SENSORIEL_VISUEL = ProfilSpecifique(
    profil="sensoriel",
    sous_profil="sensoriel_visuel",

    questions_b=_questions_sensoriel_communes() + [
        "Quel est le niveau de vision résiduelle ? "
        "Y a-t-il encore une vision partielle, ou la vision est-elle totalement absente ?",

        "Comment se passent les déplacements — à l'intérieur du domicile, "
        "à l'extérieur, dans les transports ?",

        "Comment se passe la lecture, l'écriture, l'utilisation d'un téléphone "
        "ou d'un ordinateur ?",
    ],

    questions_d=[
        "Au travail, comment les tâches sont-elles réalisées ? "
        "Des aides techniques ou des aménagements sont-ils utilisés ?",
    ],

    questions_e=[
        "Quels accompagnements ou équipements permettraient de maintenir "
        "ou d'améliorer l'autonomie au quotidien ?",
    ],

    relances_b=[
        "Pour vous déplacer seul(e) à l'extérieur — faire des courses, "
        "aller à un rendez-vous médical — comment ça se passe concrètement ? "
        "Avez-vous besoin d'aide ou d'accompagnement ?",

        "Pour les tâches du quotidien comme cuisiner, s'habiller ou gérer "
        "le courrier, quelles difficultés rencontrez-vous ?",
    ],

    relances_d=[
        "Est-ce que des aides techniques numériques sont utilisées au travail "
        "(lecteur d'écran, grossissement, synthèse vocale...) ? "
        "Sont-elles suffisantes ?",
    ],

    axes_retentissement_b=[
        "Vision résiduelle et ses fluctuations — ce qui est possible et ce qui ne l'est plus",
        "Mobilité et orientation — déplacements intérieur, extérieur, transports",
        "Accès à l'information écrite — lecture, courrier, numérique, téléphone",
        "Aides techniques utilisées (canne, chien guide, loupe, lecteur d'écran) "
        "et leurs limites",
        "Sécurité au domicile — risques liés à la déficience visuelle",
    ],

    axes_retentissement_d=[
        "Compatibilité du poste de travail avec la déficience visuelle",
        "Aides numériques et aménagements professionnels en place ou nécessaires",
        "Tâches professionnelles impossibles ou très difficiles",
    ],

    axes_retentissement_e=[
        "Autonomie de déplacement — besoin d'accompagnement humain ou technique",
        "Accès à la culture, aux loisirs, à la vie sociale",
        "Projet professionnel compatible avec la déficience visuelle",
    ],

    themes_qualite_b=[
        "niveau de vision résiduelle et ses conséquences concrètes",
        "limitations de déplacement et d'orientation",
        "accès à l'information écrite et au numérique",
        "aides techniques utilisées et leurs insuffisances",
    ],

    themes_qualite_e=[
        "besoins d'accompagnement à la mobilité et à l'autonomie",
        "projet de vie tenant compte de la déficience visuelle",
    ],
)


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRE — accès par profil + sous-profil
# ─────────────────────────────────────────────────────────────────────────────

_REGISTRE: dict[str, ProfilSpecifique] = {
    "tsa":                    TSA,
    "psychique_humeur":       PSYCHIQUE_HUMEUR,
    "psychique_psychotique":  PSYCHIQUE_PSYCHOTIQUE,
    "psychique":              PSYCHIQUE_HUMEUR,       # fallback si sous-profil non déterminé
    "moteur":                 MOTEUR,
    "di":                     DI,
    "maladie_chronique":      MALADIE_CHRONIQUE,
    "sensoriel_auditif":      SENSORIEL_AUDITIF,
    "sensoriel_visuel":       SENSORIEL_VISUEL,
    "sensoriel":              SENSORIEL_AUDITIF,      # fallback si sous-profil non déterminé
}


def get_profil_specifique(
    profil_principal: str,
    sous_profil: str = "",
) -> ProfilSpecifique | None:
    """
    Retourne le ProfilSpecifique correspondant.
    Priorité : sous_profil > profil_principal > None.
    """
    cle = sous_profil or profil_principal
    return _REGISTRE.get(cle)


def formater_questions_specifiques_pour_contexte(
    profil_principal: str,
    sous_profil: str = "",
    section: str = "b",
) -> str:
    """
    Retourne le bloc de questions spécifiques à injecter dans le contexte de l'agent.
    section : "b" | "d" | "e"
    Retourne une chaîne vide si profil non reconnu ou section sans questions.
    """
    ps = get_profil_specifique(profil_principal, sous_profil)
    if not ps:
        return ""

    questions = {
        "b": ps.questions_b,
        "d": ps.questions_d,
        "e": ps.questions_e,
    }.get(section, [])

    if not questions:
        return ""

    lignes = "\n".join(f"  → {q}" for q in questions)
    return (
        f"\n📋 QUESTIONS SPÉCIFIQUES PROFIL {profil_principal.upper()} "
        f"(poser si non encore renseigné) :\n{lignes}\n"
    )


def formater_relance_specifique(
    profil_principal: str,
    sous_profil: str = "",
    section: str = "b",
) -> str:
    """
    Retourne une relance spécifique au profil pour remplacer la relance générique.
    """
    ps = get_profil_specifique(profil_principal, sous_profil)
    if not ps:
        return ""

    relances = {
        "b": ps.relances_b,
        "d": ps.relances_d,
        "e": ps.relances_e,
    }.get(section, [])

    return relances[0] if relances else ""


def formater_axes_retentissement(
    donnees: dict[str, Any],
    section: str = "b",
) -> str:
    """
    Retourne le bloc d'axes de retentissement spécifiques à injecter
    dans le prompt du moteur narratif.
    """
    profil    = str(donnees.get("profil_principal", "") or "")
    sous_prof = str(donnees.get("sous_profil", "") or "")
    ps = get_profil_specifique(profil, sous_prof)
    if not ps:
        return ""

    axes = {
        "b": ps.axes_retentissement_b,
        "d": ps.axes_retentissement_d,
        "e": ps.axes_retentissement_e,
    }.get(section, [])

    if not axes:
        return ""

    lignes = "\n".join(f"  • {a}" for a in axes)
    return (
        f"\n🎯 AXES DE RETENTISSEMENT SPÉCIFIQUES "
        f"(profil {profil.upper()} — couvrir impérativement si données disponibles) :\n"
        f"{lignes}\n"
    )
