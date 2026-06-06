"""
app/engines/action_plan_engine.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FACILIM 100 — Moteur de plan d'action

Transforme les constats (completeness + refusal_risk + cdaph_strategy)
en actions concrètes, priorisées et expliquées.

Trois versions de chaque action :
  - Professionnel : description technique
  - Usager (FALC) : langage simple, phrases courtes, 1ère personne
  - ESSMS : instruction pour la structure

Usage :
  from app.engines.action_plan_engine import generer_plan_action
  plan = generer_plan_action(donnees, profil_mdph="adulte")
"""

from __future__ import annotations

import re
import logging
from typing import Any

from app.engines.priorisation_engine import Action, prioriser_actions, TableauPriorisation

logger = logging.getLogger("facilim.engines.action_plan")


# ─────────────────────────────────────────────────────────────────────────────
# BIBLIOTHÈQUE D'ACTIONS
# Pour chaque situation, une action prédéfinie avec 3 versions de langage
# ─────────────────────────────────────────────────────────────────────────────

def _action(id_: str, titre: str, pro: str, usager: str, essms: str,
             droit: str, dim: str, impact: int, effort: int, delai: int,
             categorie: str, justif: str) -> Action:
    """Constructeur d'action avec ROI non encore calculé."""
    return Action(
        id=id_, titre=titre,
        description=pro,
        description_usager=usager,
        description_essms=essms,
        droit_concerne=droit,
        dimension_cerfa=dim,
        impact=impact, effort=effort, roi=0.0,
        delai_jours=delai,
        priorite="haute",  # recalculé par prioriser_actions
        categorie=categorie,
        deja_realisee=False,
        source_constat="action_plan_engine",
        justification=justif,
    )


# Catalogue complet des actions disponibles
_CATALOGUE: dict[str, Action] = {

    # ── MÉDICALES ─────────────────────────────────────────────────────────────
    "cert_medical_recent": _action(
        id_="cert_medical_recent",
        titre="Obtenir un certificat médical récent (< 3 mois)",
        pro="Demander au médecin traitant un certificat médical daté de moins de 3 mois "
            "décrivant le diagnostic, les traitements et leurs effets. Idéalement avec "
            "mention du taux d'incapacité si estimable.",
        usager="Prenez rendez-vous avec votre médecin. "
               "Dites-lui que vous préparez un dossier MDPH. "
               "Demandez-lui un certificat médical récent.",
        essms="Contacter le médecin référent pour un certificat médical actualisé "
              "précisant le diagnostic, les traitements et leurs effets sur le quotidien.",
        droit="AAH", dim="Médical",
        impact=35, effort=1, delai=7,
        categorie="rendez-vous",
        justif="Le certificat médical est la pièce la plus consultée par la CDAPH. "
               "Un certificat récent augmente significativement la solidité du dossier.",
    ),

    "taux_incapacite": _action(
        id_="taux_incapacite",
        titre="Faire estimer le taux d'incapacité permanente",
        pro="Demander au médecin de mentionner ou d'estimer le taux d'incapacité "
            "permanente (IPP). Pour l'AAH : un taux ≥ 80% est déterminant pour l'AAH1.",
        usager="Demandez à votre médecin quel est votre taux d'invalidité. "
               "C'est important pour votre dossier.",
        essms="Obtenir une estimation médicale du taux d'incapacité (IPP) pour renforcer AAH.",
        droit="AAH", dim="Médical",
        impact=30, effort=2, delai=14,
        categorie="rendez-vous",
        justif="Le taux d'incapacité est le critère central de l'AAH1 (≥ 80%). "
               "Sans taux documenté, seule l'AAH2 est possible.",
    ),

    "bilan_specialise": _action(
        id_="bilan_specialise",
        titre="Joindre un bilan spécialisé récent",
        pro="Récupérer le bilan spécialisé le plus récent (neuropsychologique, ergothérapie, "
            "psychiatrique, kinésithérapie) pour étayer les limitations fonctionnelles.",
        usager="Demandez une copie de votre dernier bilan médical spécialisé "
               "(par exemple : bilan psychologique ou bilan de kiné).",
        essms="Récupérer bilans neuropsychologiques, ergothérapiques ou psychiatriques récents.",
        droit="PCH", dim="Médical",
        impact=20, effort=2, delai=14,
        categorie="document",
        justif="Les bilans spécialisés objectivent les limitations et renforcent PCH, AEEH, AAH.",
    ),

    "fiche_medecin_travail": _action(
        id_="fiche_medecin_travail",
        titre="Obtenir la fiche d'aptitude/inaptitude du médecin du travail",
        pro="Demander à l'employeur ou au médecin du travail la fiche d'aptitude "
            "ou d'inaptitude. Pièce déterminante pour RQTH et AAH.",
        usager="Si vous travaillez ou avez travaillé, demandez la lettre de votre médecin du travail. "
               "C'est la lettre qui dit ce que vous pouvez ou ne pouvez pas faire au travail.",
        essms="Obtenir du médecin du travail ou de l'employeur la fiche aptitude/inaptitude.",
        droit="RQTH", dim="D",
        impact=25, effort=1, delai=7,
        categorie="document",
        justif="La fiche médecin du travail est la preuve clé pour RQTH. "
               "Elle formalise les limitations professionnelles médicalement.",
    ),

    "attestation_arret": _action(
        id_="attestation_arret",
        titre="Joindre l'attestation d'arrêt de travail / CPAM",
        pro="Récupérer l'attestation CPAM de l'arrêt de travail en cours ou passé, "
            "ou la notification de pension d'invalidité.",
        usager="Demandez à la CPAM un document qui montre que vous êtes en arrêt de travail. "
               "Vous pouvez le télécharger sur ameli.fr.",
        essms="Demander attestation CPAM arrêt longue durée ou notification invalidité.",
        droit="AAH", dim="D",
        impact=20, effort=1, delai=3,
        categorie="document",
        justif="L'attestation CPAM prouve la durée de l'inactivité professionnelle, "
               "critère clé pour l'éligibilité AAH.",
    ),

    "avis_imposition": _action(
        id_="avis_imposition",
        titre="Joindre l'avis d'imposition ou de non-imposition",
        pro="Récupérer l'avis d'imposition N-1 pour justifier les ressources. "
            "Disponible sur impots.gouv.fr.",
        usager="Téléchargez votre avis d'impôts sur le site des impôts (impots.gouv.fr). "
               "Si vous ne payez pas d'impôts, téléchargez votre avis de non-imposition.",
        essms="Obtenir avis imposition N-1 pour calcul ressources AAH.",
        droit="AAH", dim="Administratif",
        impact=15, effort=1, delai=2,
        categorie="administratif",
        justif="Obligatoire pour le calcul de l'AAH différentielle.",
    ),

    # ── FONCTIONNELLES ────────────────────────────────────────────────────────

    "documenter_aide_humaine": _action(
        id_="documenter_aide_humaine",
        titre="Documenter les besoins d'aide humaine avec fréquences",
        pro="Décrire précisément les actes de la vie quotidienne nécessitant aide : "
            "liste des actes, fréquence hebdomadaire, durée, personne aidante. "
            "Section B du CERFA.",
        usager="Faites la liste des choses que vous ne pouvez pas faire seul(e). "
               "Par exemple : me laver, m'habiller, préparer un repas. "
               "Dites combien de fois par semaine vous avez besoin d'aide.",
        essms="Remplir grille AVQ : actes impossibles seul, fréquence/semaine, durée, aidant.",
        droit="PCH", dim="B",
        impact=30, effort=1, delai=2,
        categorie="narratif",
        justif="La fréquence et la nature des aides sont le critère central du barème PCH. "
               "Chaque acte documenté peut ouvrir droit à des heures supplémentaires.",
    ),

    "decrire_limitations_concretes": _action(
        id_="decrire_limitations_concretes",
        titre="Décrire les limitations fonctionnelles avec exemples concrets",
        pro="Enrichir la section B avec des exemples quotidiens concrets : "
            "distance de marche, durée de station debout, actes impossibles, "
            "comparaison avant/après le handicap.",
        usager="Décrivez une journée type. "
               "Qu'est-ce que vous ne pouvez plus faire ? "
               "Depuis quand ? Comment faisait-on avant ?",
        essms="Enrichir section B : exemples concrets, mesures, impossibilités quotidiennes.",
        droit="AAH", dim="B",
        impact=25, effort=1, delai=1,
        categorie="narratif",
        justif="Les exemples concrets permettent à la CDAPH d'objectiver le retentissement "
               "fonctionnel sans avoir besoin de rencontrer la personne.",
    ),

    "perimetre_marche": _action(
        id_="perimetre_marche",
        titre="Préciser la distance de marche maximale",
        pro="Documenter le périmètre de marche en mètres, les aides à la mobilité utilisées, "
            "et la douleur ou fatigue associée. Critère décisif pour CMI stationnement.",
        usager="Dites combien de mètres vous pouvez marcher sans vous arrêter. "
               "Utilisez-vous une canne ou un fauteuil ?",
        essms="Documenter : distance marche en m, aide mobilité, douleur ou fatigue associée.",
        droit="CMI_STATIONNEMENT", dim="B",
        impact=25, effort=1, delai=1,
        categorie="narratif",
        justif="Le périmètre de marche est le critère principal de la CMI stationnement.",
    ),

    "documenter_impact_professionnel": _action(
        id_="documenter_impact_professionnel",
        titre="Décrire l'impact du handicap sur l'emploi",
        pro="Section D : décrire les tâches professionnelles impossibles, les aménagements "
            "déjà demandés, la rupture de parcours emploi due au handicap.",
        usager="Décrivez ce que vous ne pouvez plus faire dans votre travail à cause de votre handicap. "
               "Depuis quand ? Qu'est-ce qui a changé ?",
        essms="Compléter section D : tâches impossibles, aménagements tentés, rupture parcours emploi.",
        droit="RQTH", dim="D",
        impact=20, effort=1, delai=1,
        categorie="narratif",
        justif="L'impact emploi objectivé renforce RQTH et la cohérence du dossier section D.",
    ),

    "completer_avq": _action(
        id_="completer_avq",
        titre="Compléter la grille des activités de la vie quotidienne (AVQ)",
        pro="Décrire les 10 activités AVQ du CERFA (hygiène, habillage, alimentation, "
            "déplacements, communication, sécurité, etc.) en précisant ce qui est "
            "impossible seul vs possible avec aide.",
        usager="Pour chaque activité de la vie quotidienne (se laver, s'habiller, manger...), "
               "dites si vous pouvez le faire seul(e) ou si vous avez besoin d'aide.",
        essms="Remplir grille AVQ pages 6-7 du CERFA : capacité/incapacité pour chaque domaine.",
        droit="PCH", dim="B",
        impact=20, effort=2, delai=3,
        categorie="narratif",
        justif="Les cases AVQ pages 6-7 sont les critères d'évaluation PCH. "
               "Chaque case cochée renforce la justification.",
    ),

    # ── PROJET DE VIE ─────────────────────────────────────────────────────────

    "rediger_projet_vie": _action(
        id_="rediger_projet_vie",
        titre="Rédiger ou compléter le projet de vie (section E)",
        pro="Rédiger la section E : attentes concrètes vis-à-vis de la MDPH, "
            "orientation souhaitée (ESAT, SESSAD, SAVS, emploi ordinaire), "
            "besoins de compensation identifiés.",
        usager="Décrivez ce que vous voulez pour votre avenir. "
               "Qu'est-ce qui vous aiderait le plus dans votre vie ? "
               "Qu'est-ce que vous souhaitez obtenir de la MDPH ?",
        essms="Co-rédiger la section E avec la personne : attentes, orientation, compensations.",
        droit="*", dim="E",
        impact=20, effort=2, delai=5,
        categorie="narratif",
        justif="La section E guide l'orientation décidée par la CDAPH. "
               "Son absence force la commission à deviner les besoins.",
    ),

    "preciser_orientation": _action(
        id_="preciser_orientation",
        titre="Préciser l'orientation professionnelle ou médico-sociale souhaitée",
        pro="Cocher et expliquer P16 : milieu ordinaire, ESAT, sans activité. "
            "Nommer si possible l'établissement souhaité (SESSAD, SAVS, IME...).",
        usager="Dites si vous voulez travailler dans une entreprise normale, "
               "dans un ESAT, ou si vous ne souhaitez pas travailler pour le moment.",
        essms="Préciser P16 : orientation et nom de l'établissement souhaité si identifié.",
        droit="ESPO", dim="E",
        impact=15, effort=1, delai=2,
        categorie="narratif",
        justif="L'orientation précisée guide la CDAPH vers la bonne décision d'attribution.",
    ),

    # ── SCOLAIRES ─────────────────────────────────────────────────────────────

    "obtenir_gevasco": _action(
        id_="obtenir_gevasco",
        titre="Obtenir le GEVASCO auprès de l'école (enfant)",
        pro="Contacter l'enseignant référent ou le directeur d'école pour obtenir "
            "le GEVASCO (Guide d'Évaluation des Volets Administratifs Scolaires et de Compensation).",
        usager="Demandez à l'école de votre enfant le document GEVASCO. "
               "C'est un document important que l'école doit faire pour la MDPH.",
        essms="Contacter l'établissement scolaire pour récupérer GEVASCO et ESS récents.",
        droit="AEEH", dim="C",
        impact=30, effort=1, delai=7,
        categorie="document",
        justif="Le GEVASCO est obligatoire pour les dossiers enfants. "
               "Son absence peut bloquer l'instruction AEEH.",
    ),

    "bulletins_scolaires": _action(
        id_="bulletins_scolaires",
        titre="Joindre les 2 derniers bulletins scolaires",
        pro="Récupérer les bulletins scolaires récents et le rapport de l'enseignant référent "
            "pour contextualiser les difficultés scolaires.",
        usager="Préparez les derniers bulletins scolaires de votre enfant. "
               "Ajoutez les commentaires de l'enseignant si possible.",
        essms="Récupérer bulletins scolaires N et N-1 + rapport enseignant référent.",
        droit="AEEH", dim="C",
        impact=15, effort=1, delai=3,
        categorie="document",
        justif="Les bulletins documentent les difficultés scolaires et renforcent AEEH.",
    ),

    "compte_rendu_ess": _action(
        id_="compte_rendu_ess",
        titre="Joindre le compte-rendu d'ESS (Équipe de Suivi de Scolarisation)",
        pro="Récupérer le compte-rendu de la dernière ESS auprès de l'enseignant référent. "
            "Si aucune ESS récente, en demander une urgente.",
        usager="Demandez à l'enseignant de votre enfant le compte-rendu de la dernière réunion "
               "sur la scolarité de votre enfant (on appelle ça une ESS).",
        essms="Récupérer CR ESS le plus récent ou planifier une ESS urgente.",
        droit="AEEH", dim="C",
        impact=20, effort=2, delai=14,
        categorie="document",
        justif="L'ESS documente les aménagements scolaires en place — renforcent AEEH.",
    ),

    # ── ADMINISTRATIVES ───────────────────────────────────────────────────────

    "completer_identite": _action(
        id_="completer_identite",
        titre="Compléter les données d'identité (NSS, adresse, téléphone)",
        pro="Compléter les champs administratifs manquants : NSS, adresse complète, "
            "téléphone, email. Critères de recevabilité administrative.",
        usager="Vérifiez que votre numéro de sécurité sociale, votre adresse "
               "et votre numéro de téléphone sont bien renseignés.",
        essms="Vérifier et compléter les informations administratives obligatoires.",
        droit="*", dim="Administratif",
        impact=15, effort=1, delai=1,
        categorie="administratif",
        justif="Les données administratives incomplètes peuvent entraîner "
               "un retour de dossier par le secrétariat MDPH.",
    ),

    "jugement_protection": _action(
        id_="jugement_protection",
        titre="Joindre le jugement de mesure de protection juridique",
        pro="Récupérer le jugement de tutelle, curatelle ou habilitation familiale en cours "
            "de validité auprès du représentant légal.",
        usager="Demandez à votre tuteur ou curateur la copie du jugement qui dit "
               "qu'il s'occupe de vos affaires. Ce document a une date de fin.",
        essms="Récupérer jugement tutelle/curatelle/habilitation en cours de validité.",
        droit="*", dim="Administratif",
        impact=20, effort=1, delai=3,
        categorie="document",
        justif="Obligatoire pour les dossiers de majeurs protégés. "
               "Sans jugement valide, le représentant légal n'est pas reconnu.",
    ),

    # ── RECUEIL INFORMATION ───────────────────────────────────────────────────

    "question_aide_toilette": _action(
        id_="question_aide_toilette",
        titre="Recueillir : fréquence des aides pour la toilette",
        pro="Demander : combien de fois par semaine la toilette nécessite-t-elle une aide ? "
            "Qui aide ? Durée de l'aide ? Type d'aide (physique, surveillance...)?",
        usager="Je dois vous poser une question : combien de fois par semaine "
               "avez-vous besoin d'aide pour vous laver ?",
        essms="Recueillir : fréquence aide toilette/semaine, qui aide, durée, type.",
        droit="PCH", dim="B",
        impact=30, effort=1, delai=1,
        categorie="narratif",
        justif="La fréquence d'aide hygiène est le 1er critère PCH catégorie 1.",
    ),

    "question_variabilite": _action(
        id_="question_variabilite",
        titre="Recueillir : description des bons/mauvais jours",
        pro="Pour les handicaps psychiques, TSA, SEP : demander la différence entre "
            "bons et mauvais jours. Fréquence des mauvaises périodes. Impact concret.",
        usager="Pouvez-vous me décrire un mauvais jour ? "
               "Qu'est-ce que vous ne pouvez pas faire ces jours-là ? "
               "Combien de jours difficiles par semaine ?",
        essms="Recueillir description détaillée bons/mauvais jours — fréquence et impact AVQ.",
        droit="AAH", dim="B",
        impact=20, effort=1, delai=1,
        categorie="narratif",
        justif="La variabilité des capacités est un critère AAH2 (RSDAE). "
               "Elle doit être documentée avec des exemples concrets.",
    ),

    "question_projet_professionnel": _action(
        id_="question_projet_professionnel",
        titre="Recueillir : orientation professionnelle souhaitée",
        pro="Demander si la personne souhaite : retourner en emploi ordinaire, "
            "orientation ESPO, milieu protégé ESAT, ou aucune activité.",
        usager="Que souhaitez-vous faire pour votre travail ? "
               "Voulez-vous travailler ? Dans quel type d'environnement ?",
        essms="Recueillir choix d'orientation professionnelle pour P16 du CERFA.",
        droit="RQTH", dim="E",
        impact=15, effort=1, delai=1,
        categorie="narratif",
        justif="L'orientation P16 guide la décision CDAPH. "
               "Elle doit refléter le souhait réel de la personne.",
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# GÉNÉRATEUR D'ACTIONS DEPUIS LES CONSTATS
# ─────────────────────────────────────────────────────────────────────────────

def _texte(donnees: dict) -> str:
    champs = ["diagnostics", "traitements", "impact_quotidien", "statut_emploi",
              "notes_pro", "texte_b_vie_quotidienne", "restrictions_emploi"]
    return " ".join(str(donnees.get(c, "") or "") for c in champs).lower()


def _action_deja_realisee(action_id: str, donnees: dict, texte: str) -> bool:
    """Vérifie si l'action est déjà réalisée (donnée présente)."""
    checks = {
        "cert_medical_recent":     lambda: bool(re.search(r"certificat|bilan.{0,10}recent", texte)),
        "taux_incapacite":         lambda: bool(re.search(r"taux.{0,10}(80|90|100)\s*%|taux d.incapacit[eé]", texte)),
        "bilan_specialise":        lambda: len(str(donnees.get("notes_pro", "") or "")) > 100,
        "fiche_medecin_travail":   lambda: bool(re.search(r"m[eé]decin.{0,10}travail|aptitude|inaptitude", texte)),
        "attestation_arret":       lambda: bool(re.search(r"arr[eê]t.{0,20}longue.{0,10}dur[eé]e|pension invalidit", texte)),
        "avis_imposition":         lambda: bool(re.search(r"avis.{0,15}(impos|non-impos)|impots.gouv", texte)),
        "documenter_aide_humaine": lambda: bool(re.search(r"aide.{0,20}(toilette|douche|hygi[eè]ne).{0,10}(\d+|quotidien|semaine)", texte)),
        "decrire_limitations_concretes": lambda: bool(re.search(r"ne (peut|peux) (pas|plus)\b.{0,30}(marcher|se lever|cuisiner)", texte)),
        "perimetre_marche":        lambda: bool(re.search(r"\d+.{0,5}m[eè]tres?|p[eé]rim[eè]tre.{0,10}march", texte)),
        "documenter_impact_professionnel": lambda: len(str(donnees.get("texte_d_situation_pro", "") or "")) > 100,
        "rediger_projet_vie":      lambda: len(str(donnees.get("texte_e_projet_vie", "") or "")) > 150,
        "obtenir_gevasco":         lambda: bool(re.search(r"gevasco|ess.{0,20}scolaire", texte)),
        "completer_identite":      lambda: bool(donnees.get("num_secu") and donnees.get("adresse_complete")),
        "question_aide_toilette":  lambda: bool(re.search(r"aide.{0,20}(toilette|douche).{0,30}(\d+.{0,5}fois|quotidien)", texte)),
        "question_variabilite":    lambda: bool(re.search(r"(bons?|mauvais?).{0,10}jours?", texte)),
    }
    check = checks.get(action_id)
    return check() if check else False


def _actions_depuis_completude(donnees: dict, completude, texte: str) -> list[str]:
    """Retourne les IDs d'actions suggérées par la complétude."""
    actions_ids = []
    dims = completude.dimensions

    # Médical
    if dims["medical"].score < 60:
        actions_ids.append("cert_medical_recent")
        if dims["medical"].score < 40:
            actions_ids.append("taux_incapacite")
            actions_ids.append("bilan_specialise")

    # Fonctionnel
    if dims["fonctionnel"].score < 60:
        actions_ids.append("decrire_limitations_concretes")
        actions_ids.append("question_variabilite")
        if dims["fonctionnel"].score < 40:
            actions_ids.append("completer_avq")

    # Projet de vie
    if dims["projet_vie"].score < 50:
        actions_ids.append("rediger_projet_vie")
        actions_ids.append("preciser_orientation")

    # Administratif
    if dims["administratif"].score < 70:
        actions_ids.append("completer_identite")

    # Justificatifs
    if dims["justificatifs"].score < 40:
        actions_ids.append("avis_imposition")

    return actions_ids


def _actions_depuis_risques(donnees: dict, risques, texte: str, profil_mdph: str) -> list[str]:
    """Retourne les IDs d'actions suggérées par les risques de refus."""
    actions_ids = []

    for r in risques.risques_par_droit:
        if r.niveau_risque == "élevé":
            if r.droit == "AAH":
                actions_ids.extend(["cert_medical_recent", "taux_incapacite", "attestation_arret"])
            elif r.droit == "PCH":
                actions_ids.extend(["documenter_aide_humaine", "question_aide_toilette", "completer_avq"])
            elif r.droit == "RQTH":
                actions_ids.extend(["fiche_medecin_travail", "documenter_impact_professionnel"])
            elif r.droit in ("AEEH", "SESSAD"):
                actions_ids.extend(["obtenir_gevasco", "bulletins_scolaires"])
            elif r.droit == "CMI_STATIONNEMENT":
                actions_ids.append("perimetre_marche")
        elif r.niveau_risque == "moyen":
            if r.droit == "AAH":
                actions_ids.append("decrire_limitations_concretes")
            elif r.droit == "PCH":
                actions_ids.append("question_aide_toilette")
            elif r.droit == "RQTH":
                actions_ids.append("question_projet_professionnel")

    # Protection juridique
    if donnees.get("type_protection") and not re.search(r"jugement|tribunal", texte):
        actions_ids.append("jugement_protection")

    # Profil enfant sans GEVASCO
    if profil_mdph in ("enfant", "mixte") and not re.search(r"gevasco", texte):
        if "obtenir_gevasco" not in actions_ids:
            actions_ids.append("obtenir_gevasco")

    return actions_ids


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────────────────────

def generer_plan_action(
    donnees: dict[str, Any],
    profil_mdph: str = "adulte",
    profil_handicap: str = "",
) -> TableauPriorisation:
    """
    Génère le plan d'action complet et priorisé depuis tous les moteurs FACILIM.

    Returns:
        TableauPriorisation — actions classées par ROI avec 3 versions de langage
    """
    texte = _texte(donnees)

    # Sources des constats
    actions_ids_brutes: set[str] = set()

    try:
        from app.engines.completeness_engine import evaluer_completude
        completude = evaluer_completude(donnees, profil_mdph)
        for id_ in _actions_depuis_completude(donnees, completude, texte):
            actions_ids_brutes.add(id_)
    except Exception:
        pass

    try:
        from app.engines.refusal_risk_engine import evaluer_risques_refus
        risques = evaluer_risques_refus(donnees, profil_mdph)
        for id_ in _actions_depuis_risques(donnees, risques, texte, profil_mdph):
            actions_ids_brutes.add(id_)
    except Exception:
        pass

    # Construire les objets Action
    actions: list[Action] = []
    for id_ in actions_ids_brutes:
        template = _CATALOGUE.get(id_)
        if not template:
            continue
        # Copier l'action du catalogue
        import copy
        action = copy.copy(template)
        action.deja_realisee = _action_deja_realisee(id_, donnees, texte)
        actions.append(action)

    # Toujours inclure quelques actions de base si le plan est vide
    if not actions:
        for fallback_id in ["cert_medical_recent", "decrire_limitations_concretes", "rediger_projet_vie"]:
            template = _CATALOGUE.get(fallback_id)
            if template:
                import copy
                action = copy.copy(template)
                action.deja_realisee = _action_deja_realisee(fallback_id, donnees, texte)
                actions.append(action)

    return prioriser_actions(actions)
