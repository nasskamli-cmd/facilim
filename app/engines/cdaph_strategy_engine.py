"""
app/engines/cdaph_strategy_engine.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FACILIM 70 — Moteur de Stratégie CDAPH

Raisonne comme une équipe d'évaluation MDPH/CDAPH :
  - Analyse les forces et faiblesses du dossier
  - Évalue la solidité de chaque droit demandé
  - Identifie les risques de refus
  - Produit les 5 questions à fort levier
  - Calcule un score de solidité global

RÈGLE ABSOLUE :
  Ce moteur n'est jamais décisionnaire.
  Il analyse. Il signale. Il conseille.
  Toute formulation utilise : "semble", "paraît", "éléments compatibles avec".

Usage :
  from app.engines.cdaph_strategy_engine import analyser_strategie_cdaph
  rapport = analyser_strategie_cdaph(donnees, profil_mdph="adulte")
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("facilim.engines.cdaph_strategy")


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURES DE DONNÉES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AnalyseDroit:
    """Analyse stratégique d'un droit pour la CDAPH."""
    droit:                  str
    label:                  str
    robustesse_pct:         int     # 0-100 — solidité du dossier pour ce droit
    risque_refus:           str     # "faible" | "moyen" | "élevé"
    forces:                 list[str]
    faiblesses:             list[str]
    pieces_attendues:       list[str]   # ce que la CDAPH s'attend à trouver
    pieces_presentes:       list[str]   # ce qui est effectivement présent
    pieces_manquantes:      list[str]   # écart = pièces manquantes
    decision_previsible:    str     # "favorable" | "incertain" | "défavorable"
    raisonnement_cdaph:     str     # une phrase expliquant le raisonnement


@dataclass
class RapportCDAPH:
    """Rapport stratégique complet pour un dossier."""

    # Synthèse
    score_solidite:         int         # 0-100
    resume_executif:        str

    # Analyse par droit
    droits_solides:         list[AnalyseDroit]   # robustesse ≥ 70
    droits_fragiles:        list[AnalyseDroit]   # robustesse < 70
    droits_sans_analyse:    list[str]

    # Forces et faiblesses globales
    forces_globales:        list[str]
    faiblesses_globales:    list[str]

    # Action
    questions_levier:       list[str]   # max 5, ordre de priorité
    actions_recommandees:   list[str]   # ordre de priorité

    # Détail scores
    score_preuves:          int         # /100
    score_coherence:        int         # /100
    score_retentissement:   int         # /100
    score_projet:           int         # /100
    score_justificatifs:    int         # /100


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _texte_complet(donnees: dict) -> str:
    """Construit un texte d'analyse depuis toutes les sources."""
    champs = [
        "diagnostics", "traitements", "impact_quotidien", "restrictions_emploi",
        "statut_emploi", "notes_pro", "texte_b_vie_quotidienne", "texte_c_scolarite",
        "texte_d_situation_pro", "texte_e_projet_vie", "situation_scolaire",
        "expression_directe", "droits_demandes", "historique_mdph",
        "projet_orientation", "mode_vie", "type_protection",
    ]
    parties = [str(donnees.get(c, "") or "") for c in champs]

    # Verbatims
    for c in ["_verbatim_b", "_verbatim_c", "_verbatim_d", "_verbatim_e"]:
        lst = donnees.get(c) or []
        if isinstance(lst, list):
            parties.extend(str(x) for x in lst)

    # Document knowledge
    dk = donnees.get("_document_knowledge") or {}
    for categorie in dk.values():
        if isinstance(categorie, list):
            for item in categorie:
                if isinstance(item, dict) and item.get("valeur"):
                    parties.append(str(item["valeur"]))

    return " ".join(parties).lower()


def _signal(texte: str, patterns: list[str]) -> tuple[bool, str]:
    """Retourne (trouvé, fragment contextualisé)."""
    for p in patterns:
        m = re.search(p, texte, re.IGNORECASE)
        if m:
            start = max(0, m.start() - 30)
            end = min(len(texte), m.end() + 50)
            return True, texte[start:end].strip()
    return False, ""


def _score_to_risque(robustesse: int) -> str:
    if robustesse >= 70: return "faible"
    if robustesse >= 40: return "moyen"
    return "élevé"


def _score_to_decision(robustesse: int, risque: str) -> str:
    if robustesse >= 70 and risque == "faible": return "favorable"
    if robustesse >= 40: return "incertain"
    return "défavorable"


# ─────────────────────────────────────────────────────────────────────────────
# CRITÈRES GLOBAUX DE SOLIDITÉ
# Pondération : Preuves 35% · Cohérence 25% · Retentissement 20% · Projet 15% · Justificatifs 5%
# ─────────────────────────────────────────────────────────────────────────────

def _evaluer_preuves(donnees: dict, texte: str) -> tuple[int, list[str], list[str]]:
    """35% — Documents, bilans, preuves objectives."""
    score = 0
    forces, faiblesses = [], []

    # Texte B présent et substantiel
    texte_b = str(donnees.get("texte_b_vie_quotidienne", "") or "")
    if len(texte_b) > 800:
        score += 30
        forces.append("Description de la vie quotidienne détaillée et documentée")
    elif len(texte_b) > 300:
        score += 20
        forces.append("Description de la vie quotidienne présente et substantielle")
    elif len(texte_b) > 100:
        score += 10
        forces.append("Description de la vie quotidienne présente (à enrichir)")
    else:
        faiblesses.append("Section B (vie quotidienne) absente ou trop vague — axe prioritaire")

    # Documents externes
    notes = str(donnees.get("notes_pro", "") or "")
    dk = donnees.get("_document_knowledge") or {}
    if notes and len(notes) > 200:
        score += 20
        forces.append("Documents professionnels ou bilans injectés dans le dossier")
    elif isinstance(dk, dict) and any(dk.values()):
        score += 15
        forces.append("Informations documentaires extraites disponibles")
    else:
        faiblesses.append("Absence de documents externes (bilans, comptes-rendus) — dossier repose sur déclarations")

    # Certificat médical / diagnostics précis
    if re.search(r"diagnos|bilan|certificat|compte.?rendu|rapport", texte):
        score += 20
        forces.append("Données médicales ou paramédicales référencées")
    else:
        faiblesses.append("Absence de référence à un certificat médical ou bilan dans les données")

    # Expression directe / verbatim
    expr = str(donnees.get("expression_directe", "") or "")
    verbatim = any(donnees.get(c) for c in ["_verbatim_b", "_verbatim_c", "_verbatim_d", "_verbatim_e"])
    if expr or verbatim:
        score += 15
        forces.append("Expressions directes de la personne présentes — renforce la crédibilité")

    # Dates précises (temporalité objectivée)
    if re.search(r"\b(20[0-9]{2}|depuis\s+\d|il\s+y\s+a\s+\d)", texte):
        score += 15
        forces.append("Temporalité documentée (dates, durées) — apporte objectivité")

    return min(100, score), forces, faiblesses


def _evaluer_coherence(donnees: dict, texte: str) -> tuple[int, list[str], list[str]]:
    """25% — Cohérence interne : diagnostics ↔ limitations ↔ droits."""
    score = 50  # baseline
    forces, faiblesses = [], []

    diagnostics = str(donnees.get("diagnostics", "") or "").lower()
    impact      = str(donnees.get("impact_quotidien", "") or "").lower()
    droits      = str(donnees.get("droits_demandes", "") or "").upper()
    statut      = str(donnees.get("statut_emploi", "") or "").lower()

    # Triangle diagnostics → limitations → droits
    if diagnostics and impact:
        score += 15
        forces.append("Cohérence diagnostics → impact fonctionnel documentée")
    elif diagnostics and not impact:
        score -= 15
        faiblesses.append("Diagnostics présents mais impact fonctionnel non décrit — chaîne causale incomplète")

    # Cohérence droits / profil
    profil_mdph = donnees.get("_profil_mdph", "adulte")
    if profil_mdph == "enfant" and "AEEH" not in droits and droits:
        score -= 15
        faiblesses.append("Dossier enfant sans AEEH — vérifier si oubli")
    if profil_mdph == "adulte" and "AEEH" in droits:
        score -= 25
        faiblesses.append("AEEH demandée pour un profil adulte — incohérence forte")

    # Cohérence PCH / aide documentée
    if "PCH" in droits:
        aide_ok, _ = _signal(texte, [r"aide.{0,20}(toilette|matin|soins|domicile)", r"tierce personne"])
        if aide_ok:
            score += 15
            forces.append("PCH demandée et besoin d'aide humaine documenté — cohérence forte")
        else:
            score -= 10
            faiblesses.append("PCH demandée mais aucune mention d'aide humaine dans le dossier")

    # Cohérence emploi / RQTH ou AAH
    if "sans emploi" in statut and ("RQTH" in droits or "AAH" in droits):
        score += 10
        forces.append("Situation d'inactivité professionnelle cohérente avec droits emploi/vie quotidienne")

    # Pas de contradiction temporelle évidente
    if re.search(r"travaille.{0,20}(actuellement|temps plein)", texte) and "AAH" in droits:
        score -= 10
        faiblesses.append("Activité professionnelle mentionnée avec demande AAH — vérifier compatibilité ressources")

    return max(0, min(100, score)), forces, faiblesses


def _evaluer_retentissement(donnees: dict, texte: str) -> tuple[int, list[str], list[str]]:
    """20% — Retentissement fonctionnel concret et objectivé."""
    score = 0
    forces, faiblesses = [], []

    # Impossibilités concrètes nommées
    if re.search(r"ne\s+(peut|peux|peut\s+plus|peux\s+plus)\b", texte, re.I):
        score += 20
        forces.append("Limitations fonctionnelles exprimées par des impossibilités concrètes")

    # Mesures quantifiées (distances, fréquences, heures)
    if re.search(r"\d+\s*(m[eè]tres?|km|fois|heures?|minutes?|nuits?|fois\s+par)", texte):
        score += 20
        forces.append("Retentissement quantifié (mesures, fréquences) — très favorable pour la CDAPH")

    # Temporalité (avant / depuis)
    if re.search(r"(avant|depuis).{0,25}(accident|maladie|diagnostic|2[0-9]{3})", texte):
        score += 15
        forces.append("Rupture de trajectoire documentée (avant/depuis) — contextualise le handicap")

    # Variabilité (bons/mauvais jours)
    if re.search(r"(bons?|mauvais?).{0,10}jours?|épisodes?|variable|varie", texte):
        score += 10
        forces.append("Variabilité des capacités documentée — pertinent pour handicap psychique / SEP")

    # Aide actuelle documentée
    if re.search(r"(AESH|SAVS|SAMSAH|SESSAD|aidant|aide à domicile)", texte):
        score += 10
        forces.append("Accompagnement ou aide actuellement en place documenté")

    # Actes AVQ concrets
    if re.search(r"(toilette|habillage|alimentation|déplacement|communication|cuisine|courses)", texte):
        score += 10
        forces.append("Actes de la vie quotidienne (AVQ) cités — lecture directe par l'équipe MDPH")

    # Faiblesses
    if score < 30:
        faiblesses.append("Retentissement peu objectivé — la CDAPH ne peut pas quantifier les besoins")
    if not re.search(r"(quotidien|journée|semaine|matin|soir)", texte):
        faiblesses.append("Absence de temporalité quotidienne — difficile d'évaluer l'intensité des besoins")

    return min(100, score), forces, faiblesses


def _evaluer_projet(donnees: dict, texte: str) -> tuple[int, list[str], list[str]]:
    """15% — Cohérence et réalisme du projet de vie."""
    score = 30  # baseline
    forces, faiblesses = [], []

    texte_e = str(donnees.get("texte_e_projet_vie", "") or "")
    droits  = str(donnees.get("droits_demandes", "") or "").upper()

    if texte_e and len(texte_e) > 200:
        score += 30
        forces.append("Projet de vie documenté — section E présente et substantielle")
    elif texte_e:
        score += 10
    else:
        faiblesses.append("Section E (projet de vie) absente — la CDAPH ne connaît pas les attentes")

    # Cohérence projet / droits
    proj = str(donnees.get("projet_orientation", "") or "").lower()
    if "ESAT" in droits and re.search(r"esat|milieu prot", texte):
        score += 15
        forces.append("Orientation ESAT cohérente avec les droits demandés")
    if "RQTH" in droits and re.search(r"(emploi|travail|formation|retour)", texte):
        score += 15
        forces.append("Projet emploi/formation cohérent avec la demande RQTH")

    # Réalisme
    if re.search(r"(SESSAD|SAVS|SAMSAH|job coaching|emploi accompagné)", texte):
        score += 10
        forces.append("Structure d'accompagnement identifiée dans le projet — réalisme fort")

    return min(100, score), forces, faiblesses


def _evaluer_justificatifs(donnees: dict, profil_mdph: str) -> tuple[int, list[str], list[str]]:
    """5% — Pièces justificatives signalées ou attendues."""
    score = 0
    forces, faiblesses = [], []

    try:
        from app.engines.justificatifs_engine import justificatifs_requis
        justifs = justificatifs_requis(donnees, profil_mdph)
        obligatoires = [j for j in justifs if j.obligatoire]
        n_obligatoires = len(obligatoires)
        has_cert_medical = any("médical" in j.nom.lower() or "certificat" in j.nom.lower()
                               for j in obligatoires)
        if has_cert_medical:
            score += 50
            forces.append("Certificat médical obligatoire identifié dans la liste des pièces")
        else:
            faiblesses.append("Certificat médical non identifié — pièce indispensable")

        if n_obligatoires >= 2:
            score += 30
            forces.append(f"{n_obligatoires} pièces obligatoires identifiées")
        else:
            faiblesses.append("Pièces obligatoires manquantes pour un dossier complet")

        score += min(20, len(justifs) * 3)
    except Exception:
        faiblesses.append("Liste de justificatifs non générée")

    return min(100, score), forces, faiblesses


# ─────────────────────────────────────────────────────────────────────────────
# ANALYSE PAR DROIT
# ─────────────────────────────────────────────────────────────────────────────

# Conditions CDAPH pour chaque droit (ce qui doit être objectivé)
_EXIGENCES_CDAPH: dict[str, dict] = {
    "RQTH": {
        "label":     "Reconnaissance de la Qualité de Travailleur Handicapé",
        "preuves_attendues": [
            "Certificat médical décrivant les limitations au travail",
            "Avis du médecin du travail (si en poste)",
            "CV ou historique professionnel",
        ],
        "signaux_force": [
            r"impact.{0,20}(travail|emploi|poste|professionnel)",
            r"am[eé]nagement.{0,15}(poste|travail|horaire)",
            r"m[eé]decin.{0,10}travail",
            r"restriction.{0,15}(emploi|travail)",
            # Signaux AT et inactivité professionnelle
            r"accident.{0,15}travail|\bAT\b.{0,10}(2[0-9]{3}|s[eé]quelles?)",
            r"sans emploi.{0,20}(depuis|2[0-9]{3})",
            r"inapte|inaptitude.{0,15}(travail|poste)",
            r"ancien.{0,15}(CDI|CDD|poste|employ[eé])",
            r"ne peut (pas|plus).{0,20}(travailler|reprendre)",
        ],
        "signaux_faiblesse": [
            r"retraite|plus de 62 ans",
        ],
        "raisonnement": "La CDAPH valide RQTH si les limitations au travail sont objectivées par un médecin",
    },
    "AAH": {
        "label":     "Allocation aux Adultes Handicapés",
        "preuves_attendues": [
            "Certificat médical avec taux d'incapacité",
            "Avis d'imposition ou de non-imposition",
            "Attestation d'arrêt de travail / invalidité",
        ],
        "signaux_force": [
            r"arr[eê]t.{0,20}(longue dur[eé]e|\d+.{0,5}ans?)",
            r"invalidit[eé]|pension d.invalidit[eé]",
            r"taux.{0,10}(80|90|100)\s*%",
            r"inapte|inaptitude",
            r"sans emploi.{0,20}(depuis|3 ans|4 ans|5 ans)",
            r"licenci[eé].{0,20}inaptitude",
            r"(maladie.{0,20}chron|fibromyal|SLA|scl[eé]rose|parkinson).{0,30}(travail|emploi)",
        ],
        "signaux_faiblesse": [
            r"travaille.{0,20}(actuellement|temps plein)",
        ],
        "raisonnement": "La CDAPH valide AAH si l'incapacité est prouvée ET les ressources sous plafond",
    },
    "PCH": {
        "label":     "Prestation de Compensation du Handicap",
        "preuves_attendues": [
            "Grille des besoins d'aide humaine (actes + fréquence)",
            "Devis de prestataire ou attestation d'aide actuelle",
            "Certificat médical avec description des actes impossibles",
        ],
        "signaux_force": [
            r"aide.{0,20}(toilette|douche|habillage|repas|d[eé]placement)",
            r"tierce personne|aide humaine quotidienne",
            r"fauteuil roulant|grabataire",
            r"aide.{0,15}matin|aide.{0,15}quotidienne",
        ],
        "signaux_faiblesse": [
            r"vit seul.{0,20}(sans aide|aucune aide)",
        ],
        "raisonnement": "La CDAPH valide PCH si au moins 1 acte AVQ impossible seul est objectivé",
    },
    "AEEH": {
        "label":     "Allocation d'Éducation de l'Enfant Handicapé",
        "preuves_attendues": [
            "GEVASCO (Guide d'Évaluation des besoins scolaires)",
            "Compte-rendu ESS récent",
            "Bulletins scolaires avec rapport de l'enseignant",
            "Certificat médical pédiatrique",
        ],
        "signaux_force": [
            r"GEVASCO|évaluation scolaire",
            r"AESH|AVS|tiers.?temps",
            r"SESSAD|suivi sp[eé]cialis[eé]",
        ],
        "signaux_faiblesse": [
            r"non scolarisé.{0,10}(depuis longtemps|ne va plus)",
        ],
        "raisonnement": "La CDAPH valide AEEH si le diagnostic est documenté et les aménagements actuels justifiés",
    },
    "CMI_STATIONNEMENT": {
        "label":     "CMI — Mention Stationnement",
        "preuves_attendues": [
            "Certificat médical précisant la distance de marche",
            "Attestation aide à la mobilité si applicable",
        ],
        "signaux_force": [
            r"march.{0,20}(limit[eé]e?|difficile|impossible|\d+.{0,5}m[eè]tres?)",
            r"fauteuil roulant|canne|d[eé]ambulateur|b[eé]quille",
            r"p[eé]rim[eè]tre.{0,15}march",
        ],
        "signaux_faiblesse": [],
        "raisonnement": "La CDAPH valide CMI stationnement si la limitation de marche est médicalement objectivée",
    },
    "SAVS": {
        "label":     "Service d'Accompagnement à la Vie Sociale",
        "preuves_attendues": [
            "Compte-rendu psychiatrique ou psychologique récent",
            "Bilan d'autonomie",
        ],
        "signaux_force": [
            r"(psychique|TSA|DI).{0,20}(adulte|domicile)",
            r"accompagnement.{0,20}(vie sociale|quotidien|d[eé]marches)",
            r"autonomie.{0,15}partielle",
        ],
        "signaux_faiblesse": [],
        "raisonnement": "La CDAPH oriente vers SAVS si le profil psychique/TSA/DI adulte est documenté et la vie à domicile confirmée",
    },
    "ESAT": {
        "label":     "Établissement et Service d'Aide par le Travail",
        "preuves_attendues": [
            "Bilan d'orientation professionnel",
            "Attestation capacités de travail partielles",
        ],
        "signaux_force": [
            r"(DI|d[eé]ficience|trisomie|psychique).{0,20}(capacit[eé]s?.{0,10}travail|peut travailler)",
            r"milieu prot[eé]g[eé]|ESAT",
        ],
        "signaux_faiblesse": [
            r"grabataire|d[eé]pendance totale",
        ],
        "raisonnement": "La CDAPH oriente vers ESAT si des capacités de travail partielles sont confirmées",
    },
    "SESSAD": {
        "label":     "Service d'Éducation Spéciale et de Soins à Domicile",
        "preuves_attendues": [
            "GEVASCO",
            "Bilan neuropsychologique ou orthophonique",
            "Rapport scolaire",
        ],
        "signaux_force": [
            r"(TSA|TDAH|DYS|TND).{0,20}(enfant|scolaire)",
            r"milieu ordinaire.{0,20}(avec|soutien|SESSAD)",
            r"AESH|tiers.?temps",
        ],
        "signaux_faiblesse": [],
        "raisonnement": "La CDAPH oriente vers SESSAD pour les enfants TND maintenus en milieu scolaire ordinaire avec soutien",
    },
    "ESPO": {
        "label":     "Évaluation et Soutien à l'Orientation Professionnelle",
        "preuves_attendues": [
            "CV ou historique professionnel",
            "Bilan de compétences si disponible",
        ],
        "signaux_force": [
            r"pas de projet|sans orientation|bilan capacit[eé]s?",
            r"(AT|accident du travail|handicap acquis).{0,20}(sans projet|inapte)",
        ],
        "signaux_faiblesse": [],
        "raisonnement": "La CDAPH oriente vers ESPO si la personne est sans projet professionnel défini après rupture",
    },
}

_TOUS_LES_DROITS = list(_EXIGENCES_CDAPH.keys())
_DROITS_SUPPLEMENTAIRES = ["AVPF", "RQTH_emploi", "FOYER_VIE", "MAS", "FAM", "IME", "EEAP"]


def _analyser_droit(
    droit: str,
    donnees: dict,
    texte: str,
    score_preuves: int,
    score_retentissement: int,
) -> AnalyseDroit | None:
    """Analyse stratégique d'un droit pour la CDAPH."""
    exigences = _EXIGENCES_CDAPH.get(droit)
    if not exigences:
        return None

    forces, faiblesses = [], []
    score = 0

    # Base : preuves et retentissement globaux (40% du score)
    score += round(score_preuves * 0.25)
    score += round(score_retentissement * 0.15)

    # Signaux spécifiques au droit (50%)
    n_signaux = 0
    for p in exigences["signaux_force"]:
        trouvé, fragment = _signal(texte, [p])
        if trouvé:
            n_signaux += 1
            forces.append(f"Signal détecté : {fragment[:70]!r}")

    signal_bonus = min(50, n_signaux * 15)
    score += signal_bonus

    # Signaux négatifs
    for p in exigences["signaux_faiblesse"]:
        trouvé, fragment = _signal(texte, [p])
        if trouvé:
            score -= 20
            faiblesses.append(f"Signal défavorable : {fragment[:60]!r}")

    # Évaluation pièces (10%)
    pieces_attendues = exigences["preuves_attendues"]
    pieces_presentes, pieces_manquantes = [], []

    notes = str(donnees.get("notes_pro", "") or "")
    diag  = str(donnees.get("diagnostics", "") or "")

    for piece in pieces_attendues:
        # Heuristique simple : vérifier si des mots-clés de la pièce sont dans le texte
        mots = [m.lower() for m in piece.split() if len(m) > 4]
        presente = any(m in texte for m in mots) or any(m in notes.lower() for m in mots)
        if presente:
            pieces_presentes.append(piece)
            score += 5
        else:
            pieces_manquantes.append(piece)
            if piece == pieces_attendues[0]:  # Première pièce = la plus critique
                faiblesses.append(f"Pièce prioritaire absente : {piece}")

    # Faiblesses structurelles
    if not forces:
        faiblesses.append(f"Aucun signal objectivant la demande de {exigences['label']}")
    if not diag:
        faiblesses.append("Diagnostic non renseigné — indispensable pour toute demande MDPH")

    score = max(0, min(100, score))

    # FACILIM 80 — Garantie : tout droit fragile a au moins 1 faiblesse expliquée
    if score < 70 and not faiblesses:
        faiblesses.append(
            f"Robustesse insuffisante ({score}/100) — "
            f"des preuves complémentaires renforceront la demande {exigences['label'][:40]}"
        )

    risque = _score_to_risque(score)
    decision = _score_to_decision(score, risque)

    return AnalyseDroit(
        droit=droit,
        label=exigences["label"],
        robustesse_pct=score,
        risque_refus=risque,
        forces=forces,
        faiblesses=faiblesses,
        pieces_attendues=pieces_attendues,
        pieces_presentes=pieces_presentes,
        pieces_manquantes=pieces_manquantes,
        decision_previsible=decision,
        raisonnement_cdaph=exigences["raisonnement"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# QUESTIONS À FORT LEVIER
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _QuestionLevier:
    question:       str
    droit:          str
    impact_estime:  int  # 0-100
    effort_usager:  int  # 1=très facile, 2=moyen, 3=difficile
    condition:      list[str]  # patterns d'ABSENCE qui déclenchent la question


_QUESTIONS_CDAPH: list[_QuestionLevier] = [
    _QuestionLevier(
        question="Avez-vous un certificat médical récent (< 3 mois) ? Votre médecin y a-t-il précisé le taux d'incapacité permanente ?",
        droit="AAH", impact_estime=40, effort_usager=2,
        condition=[r"certificat|taux.{0,10}incapacit"],
    ),
    _QuestionLevier(
        question="Combien de fois par semaine avez-vous besoin d'aide pour la toilette, le lever ou les soins personnels ? Par qui êtes-vous aidé(e) ?",
        droit="PCH", impact_estime=35, effort_usager=1,
        condition=[r"aide.{0,20}(toilette|lever|soins|douche)"],
    ),
    _QuestionLevier(
        question="Quelle est la distance maximale que vous pouvez parcourir sans aide ou sans vous arrêter ? Utilisez-vous une aide à la mobilité (canne, fauteuil...) ?",
        droit="CMI_STATIONNEMENT", impact_estime=30, effort_usager=1,
        condition=[r"p[eé]rim[eè]tre|distance.{0,10}march|\d+.{0,5}m[eè]tres?"],
    ),
    _QuestionLevier(
        question="Y a-t-il un document GEVASCO récent pour votre enfant ? L'enseignant référent ou le directeur d'école a-t-il rédigé un rapport ?",
        droit="AEEH", impact_estime=30, effort_usager=2,
        condition=[r"gevasco|enseignant.{0,15}r[eé]f[eé]rent"],
    ),
    _QuestionLevier(
        question="Depuis combien de temps exactement êtes-vous sans activité professionnelle ? Avez-vous une lettre de licenciement pour inaptitude ou une attestation d'arrêt longue durée ?",
        droit="AAH", impact_estime=28, effort_usager=1,
        condition=[r"arr[eê]t.{0,20}(depuis|\d+\s*(ans?|mois))"],
    ),
    _QuestionLevier(
        question="Un médecin du travail vous a-t-il déclaré inapte ? Avez-vous la fiche d'aptitude/inaptitude ?",
        droit="RQTH", impact_estime=25, effort_usager=1,
        condition=[r"inapte|inaptitude|m[eé]decin.{0,10}travail"],
    ),
    _QuestionLevier(
        question="Y a-t-il des hospitalisations psychiatriques ces dernières années ? Combien et pour quelle durée ?",
        droit="AAH", impact_estime=22, effort_usager=2,
        condition=[r"hospitalis.{0,15}psychiatr"],
    ),
    _QuestionLevier(
        question="Pour les démarches administratives (courrier, paiements, rendez-vous), avez-vous besoin d'aide ? Qui vous aide et pour quoi concrètement ?",
        droit="SAVS", impact_estime=20, effort_usager=1,
        condition=[r"d[eé]marche.{0,20}(aide|impossible|difficile|besoin)"],
    ),
    _QuestionLevier(
        question="Votre enfant bénéficie-t-il d'une AESH ? Individuelle ou mutualisée ? Combien d'heures par semaine ?",
        droit="AEEH", impact_estime=20, effort_usager=1,
        condition=[r"AESH.{0,20}(individuelle|\d+.{0,5}h)"],
    ),
    _QuestionLevier(
        question="Percevez-vous une pension d'invalidité ? De quelle catégorie (1ère, 2ème, 3ème) ?",
        droit="AAH", impact_estime=20, effort_usager=1,
        condition=[r"pension.{0,15}invalidit[eé]|\d[eè]me\s+cat[eé]gorie"],
    ),
]


def _identifier_questions_levier(texte: str, droits_fragiles: list[AnalyseDroit]) -> list[str]:
    """Retourne les 5 questions à fort levier pertinentes pour ce dossier."""
    candidates: list[tuple[float, str]] = []
    droits_fragiles_set = {d.droit for d in droits_fragiles}

    for q in _QUESTIONS_CDAPH:
        # Pertinent seulement si le droit est fragile ou demandé
        if droits_fragiles_set and q.droit not in droits_fragiles_set:
            continue

        # Pertinent si le signal est ABSENT (= la question est utile)
        signal_absent = not any(re.search(p, texte, re.I) for p in q.condition)
        if not signal_absent:
            continue  # Information déjà présente → question inutile

        roi = q.impact_estime / q.effort_usager
        candidates.append((roi, q.question))

    # Trier par ROI décroissant, dédupliquer, prendre les 5 premières
    candidates.sort(key=lambda x: -x[0])
    seen: set[str] = set()
    result: list[str] = []
    for _, question in candidates:
        if question not in seen:
            seen.add(question)
            result.append(question)
        if len(result) >= 5:
            break

    return result


# ─────────────────────────────────────────────────────────────────────────────
# ACTIONS RECOMMANDÉES
# ─────────────────────────────────────────────────────────────────────────────

def _identifier_actions(
    droits_fragiles: list[AnalyseDroit],
    forces_globales: list[str],
    faiblesses_globales: list[str],
    score_preuves: int,
) -> list[str]:
    """Produit les actions recommandées en ordre de priorité."""
    actions: list[str] = []

    if score_preuves < 50:
        actions.append(
            "PRIORITÉ 1 — Renforcer les preuves : joindre certificat médical récent, "
            "bilans spécialisés, et toute attestation objectivant les limitations"
        )

    for droit_analyse in droits_fragiles[:3]:
        if droit_analyse.pieces_manquantes:
            actions.append(
                f"Compléter dossier {droit_analyse.label} — pièce prioritaire manquante : "
                f"{droit_analyse.pieces_manquantes[0]}"
            )

    if any("vague" in f.lower() or "insuffisant" in f.lower() or "absente" in f.lower()
           for f in faiblesses_globales):
        actions.append(
            "Enrichir la section B (vie quotidienne) avec des exemples concrets : "
            "nommer les actes impossibles, les fréquences, les aides reçues"
        )

    if not actions:
        actions.append("Dossier globalement solide — vérifier la complétude des pièces jointes")

    return actions[:6]


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def analyser_strategie_cdaph(
    donnees: dict[str, Any],
    profil_mdph: str = "adulte",
    profil_handicap: str = "",
) -> RapportCDAPH:
    """
    Analyse stratégique complète d'un dossier MDPH selon la logique CDAPH.

    Ne décide jamais. Analyse et conseille.

    Args:
        donnees:        synthese_json du dossier
        profil_mdph:    "adulte" | "enfant" | "protege" | "mixte"
        profil_handicap: optionnel — "tsa" | "psychique" | etc.

    Returns:
        RapportCDAPH complet avec scores, forces, faiblesses, questions
    """
    # Injecter le profil_mdph pour les évaluateurs internes
    donnees_local = {**donnees, "_profil_mdph": profil_mdph}
    texte = _texte_complet(donnees_local)

    # ── 1. Évaluation des 5 critères globaux ─────────────────────────────────
    score_preuves,       forces_p, faib_p = _evaluer_preuves(donnees_local, texte)
    score_coherence,     forces_c, faib_c = _evaluer_coherence(donnees_local, texte)
    score_retentissement, forces_r, faib_r = _evaluer_retentissement(donnees_local, texte)
    score_projet,        forces_j, faib_j = _evaluer_projet(donnees_local, texte)
    score_justif,        forces_jj, faib_jj = _evaluer_justificatifs(donnees_local, profil_mdph)

    # Score global pondéré
    score_solidite = round(
        score_preuves        * 0.35
        + score_coherence    * 0.25
        + score_retentissement * 0.20
        + score_projet       * 0.15
        + score_justif       * 0.05
    )

    # ── 2. Agrégation forces/faiblesses globales ──────────────────────────────
    forces_globales   = forces_p + forces_r + forces_c + forces_j + forces_jj
    faiblesses_globales = faib_p + faib_r + faib_c + faib_j + faib_jj

    # ── 3. Analyse par droit ─────────────────────────────────────────────────
    droits_raw = str(donnees.get("droits_demandes", "") or "").upper()
    droits_tokens: set[str] = set(re.findall(r"[A-Z][A-Z_]+", droits_raw))

    # Correspondances doits → clés internes
    _MAP = {
        "AAH": "AAH", "PCH": "PCH", "RQTH": "RQTH", "AEEH": "AEEH",
        "CMI": "CMI_STATIONNEMENT", "SESSAD": "SESSAD",
        "ESAT": "ESAT", "ESPO": "ESPO", "SAVS": "SAVS",
        "SAMSAH": "SAVS",  # utilise même analyse que SAVS
    }

    droits_a_analyser: set[str] = set()
    for tok in droits_tokens:
        mapped = _MAP.get(tok)
        if mapped:
            droits_a_analyser.add(mapped)
        elif tok in _EXIGENCES_CDAPH:
            droits_a_analyser.add(tok)

    # Toujours analyser les droits les plus communs si profil le permet
    if profil_mdph in ("adulte", "protege", "mixte"):
        droits_a_analyser.update(["RQTH", "AAH"])
    if profil_mdph in ("enfant", "mixte"):
        droits_a_analyser.update(["AEEH", "SESSAD"])

    analyses_droits: list[AnalyseDroit] = []
    droits_sans_analyse: list[str] = []

    for droit in sorted(droits_a_analyser):
        analyse = _analyser_droit(droit, donnees_local, texte, score_preuves, score_retentissement)
        if analyse:
            analyses_droits.append(analyse)
        else:
            droits_sans_analyse.append(droit)

    droits_solides  = [a for a in analyses_droits if a.robustesse_pct >= 70]
    droits_fragiles = [a for a in analyses_droits if a.robustesse_pct < 70]
    droits_solides.sort(key=lambda x: -x.robustesse_pct)
    droits_fragiles.sort(key=lambda x: x.robustesse_pct)

    # ── 4. Questions levier ───────────────────────────────────────────────────
    questions = _identifier_questions_levier(texte, droits_fragiles or analyses_droits)

    # ── 5. Actions recommandées ───────────────────────────────────────────────
    actions = _identifier_actions(droits_fragiles, forces_globales, faiblesses_globales, score_preuves)

    # ── 6. Résumé exécutif ────────────────────────────────────────────────────
    nb_solides  = len(droits_solides)
    nb_fragiles = len(droits_fragiles)
    niveau = (
        "très solide" if score_solidite >= 80 else
        "solide"      if score_solidite >= 65 else
        "moyen"       if score_solidite >= 45 else
        "fragile"
    )

    resume = (
        f"Dossier {niveau} (score {score_solidite}/100). "
        f"{nb_solides} droit(s) à profil favorable"
        + (f", {nb_fragiles} droit(s) fragile(s)" if nb_fragiles else "")
        + ". "
        + (forces_globales[0] if forces_globales else "Documentation à compléter.")
    )
    if faiblesses_globales:
        resume += f" Point de vigilance : {faiblesses_globales[0]}"

    return RapportCDAPH(
        score_solidite=score_solidite,
        resume_executif=resume,
        droits_solides=droits_solides,
        droits_fragiles=droits_fragiles,
        droits_sans_analyse=droits_sans_analyse,
        forces_globales=forces_globales,
        faiblesses_globales=faiblesses_globales,
        questions_levier=questions,
        actions_recommandees=actions,
        score_preuves=score_preuves,
        score_coherence=score_coherence,
        score_retentissement=score_retentissement,
        score_projet=score_projet,
        score_justificatifs=score_justif,
    )


def rapport_to_dict(rapport: RapportCDAPH) -> dict:
    """Sérialise le rapport pour stockage dans analyse_situation_json."""
    return {
        "score_solidite":    rapport.score_solidite,
        "resume_executif":   rapport.resume_executif,
        "forces":            rapport.forces_globales,
        "faiblesses":        rapport.faiblesses_globales,
        "questions_levier":  rapport.questions_levier,
        "actions":           rapport.actions_recommandees,
        "droits_solides": [
            {
                "droit":             d.droit,
                "label":             d.label,
                "robustesse":        d.robustesse_pct,
                "risque_refus":      d.risque_refus,
                "decision":          d.decision_previsible,
                "raisonnement":      d.raisonnement_cdaph,
                "forces":            d.forces,
                "pieces_manquantes": d.pieces_manquantes,
            }
            for d in rapport.droits_solides
        ],
        "droits_fragiles": [
            {
                "droit":             d.droit,
                "label":             d.label,
                "robustesse":        d.robustesse_pct,
                "risque_refus":      d.risque_refus,
                "decision":          d.decision_previsible,
                "faiblesses":        d.faiblesses,
                "pieces_manquantes": d.pieces_manquantes,
                "raisonnement":      d.raisonnement_cdaph,
            }
            for d in rapport.droits_fragiles
        ],
        "scores_detail": {
            "preuves":         rapport.score_preuves,
            "coherence":       rapport.score_coherence,
            "retentissement":  rapport.score_retentissement,
            "projet":          rapport.score_projet,
            "justificatifs":   rapport.score_justificatifs,
        },
    }
