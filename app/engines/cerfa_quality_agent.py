"""
app/engines/cerfa_quality_agent.py — Agent qualité CERFA.

Contient trois sous-agents :
  1. Agent Retentissement Fonctionnel — diagnostic sans conséquences = ALERTE ROUGE
  2. Agent Projet de Vie — section E sans les 4 dimensions = ALERTE ROUGE
  3. Agent Cohérence CERFA — contradictions entre sections = ALERTE ORANGE

Plus le Score de Maturité CERFA (0-100) — indicateur de pilotage, jamais bloquant.

Évaluation basée PRINCIPALEMENT sur les dimensions de contenu, pas sur la longueur.
La longueur est un signal secondaire d'alerte uniquement.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("facilim.engines.cerfa_quality")


# ── Seuils de longueur minimale (signal d'alerte secondaire uniquement) ───────

SEUILS_LONGUEUR = {
    "texte_b_vie_quotidienne": 500,
    "texte_c_scolarite":       300,
    "texte_d_situation_pro":   400,
    "texte_e_projet_vie":      500,
}

# ── Dimensions de qualité — évaluation principale ────────────────────────────

_PATTERNS_LIMITATIONS = [
    r"ne peut (pas|plus)", r"ne parvient (pas|plus)", r"difficilement",
    r"avec aide", r"avec (l.aide|l'assistance)", r"impossible",
    r"limité(e)?", r"restreint(e)?", r"incapable", r"ne fait plus",
    r"nécessite (une aide|un accompagnement|une assistance)",
]

_PATTERNS_CONSEQUENCES = [
    r"ce qui (entraîne|provoque|implique|engendre)",
    r"ainsi", r"par conséquent", r"en conséquence",
    r"cela (impacte|affecte|perturbe|entraîne)",
    r"il en résulte", r"cela se traduit",
    r"les conséquences", r"l.impact (est|se manifeste)",
]

_PATTERNS_BESOINS = [
    r"besoin (de|d.une|d.un)", r"nécessite (un|une|des)",
    r"a besoin", r"requiert", r"indispensable",
    r"aide (humaine|technique)", r"accompagnement",
    r"compensation", r"aménagement",
]

_PATTERNS_ATTENTES = [
    r"attend(s)? (de la MDPH|que la MDPH)", r"souhaite (que|obtenir|bénéficier)",
    r"espère", r"demande (à la MDPH|que la MDPH|l.attribution)",
    r"attente(s)?", r"demande (de|d.une|d.un)",
    r"j.attend", r"nous attendons",
]

_PATTERNS_OBJECTIFS = [
    r"objectif", r"projet (de|d.)", r"vise (à|l.)", r"souhaite",
    r"ambitionne", r"aspire", r"dans l.objectif", r"pour permettre",
    r"afin de", r"dans le but",
]

# ── Termes pauvres (diagnostic sans conséquences) ────────────────────────────

_TERMES_PAUVRES = [
    "anxiété", "douleurs", "fatigue", "stress", "difficultés",
    "problèmes", "trouble", "souffrance", "gêne", "malaise",
]

# ── Contradictions à détecter (Agent Cohérence) ──────────────────────────────

_CONTRADICTIONS = [
    {
        "id": "autonomie_aide_humaine",
        "signal_a": [r"autonome pour", r"totalement autonome", r"vit seul(e)? et autonome"],
        "signal_b": [r"aide humaine.{0,20}(heures|h/semaine)", r"pch.{0,20}aide humaine"],
        "message": "La personne est décrite comme autonome mais une aide humaine importante est demandée — justification nécessaire.",
    },
    {
        "id": "emploi_inaptitude",
        "signal_a": [r"en emploi.{0,20}temps plein", r"travaille.{0,20}temps plein"],
        "signal_b": [r"incapacité totale", r"inapte total", r"ne peut pas travailler"],
        "message": "Emploi à temps plein ET incapacité totale de travailler sont contradictoires.",
    },
    {
        "id": "scolarite_ulis",
        "signal_a": [r"scolarisé(e)? normalement", r"classe ordinaire sans aménagement"],
        "signal_b": [r"\bulis\b", r"classe spécialisée", r"ime"],
        "message": "Scolarisation ordinaire sans aménagement et demande ULIS/IME — préciser la situation réelle.",
    },
    {
        "id": "logement_pch",
        "signal_a": [r"vit seul(e)? de manière autonome", r"gère seul(e)? son domicile"],
        "signal_b": [r"pch.{0,30}aide humaine.{0,20}(15|20|25|30|40)\s*h"],
        "message": "Vie autonome au domicile et PCH aide humaine > 15h/semaine — cohérence à vérifier.",
    },
]


@dataclass
class QualiteSection:
    section:              str
    limitations_ok:       bool = False
    consequences_ok:      bool = False
    besoins_ok:           bool = False
    attentes_ok:          bool = False   # section E uniquement
    objectifs_ok:         bool = False   # section E uniquement
    longueur:             int  = 0
    longueur_suffisante:  bool = False
    zones_pauvres:        list[str] = field(default_factory=list)
    marqueurs_supposition: list[str] = field(default_factory=list)
    infos_manquantes:     list[str] = field(default_factory=list)

    @property
    def score_dimensions(self) -> float:
        """Score basé sur les dimensions de contenu (0.0 à 1.0)."""
        if self.section == "E":
            dims = [self.limitations_ok, self.besoins_ok, self.attentes_ok, self.objectifs_ok]
        else:
            dims = [self.limitations_ok, self.consequences_ok, self.besoins_ok]
        present = sum(1 for d in dims if d)
        return present / len(dims)

    @property
    def est_suffisante(self) -> bool:
        """Une section est suffisante si au moins 2/3 dimensions sont présentes."""
        return self.score_dimensions >= 0.66


@dataclass
class QualiteRapport:
    alertes_rouges:           list[str] = field(default_factory=list)
    alertes_oranges:          list[str] = field(default_factory=list)
    zones_pauvres:            list[str] = field(default_factory=list)
    contradictions:           list[str] = field(default_factory=list)
    retentissement_absent:    bool      = False
    projet_vie_incomplet:     bool      = False
    dimensions_manquantes_E:  list[str] = field(default_factory=list)
    infos_manquantes:         list[str] = field(default_factory=list)
    marqueurs_supposition:    list[str] = field(default_factory=list)
    sections:                 dict[str, QualiteSection] = field(default_factory=dict)
    score_maturite:           int       = 0
    niveau_maturite:          str       = ""

    @property
    def validation_bloquee(self) -> bool:
        return len(self.alertes_rouges) > 0


# ── Sous-agent 1 — Retentissement Fonctionnel ─────────────────────────────────

def _analyser_retentissement(
    texte_b: str,
    donnees: dict[str, Any],
) -> tuple[bool, list[str]]:
    """
    Détecte si des diagnostics sont présents sans description de leurs conséquences.
    Retourne (retentissement_présent, zones_pauvres).
    """
    zones_pauvres: list[str] = []
    texte_analyse = (texte_b + " " + str(donnees.get("impact_quotidien", ""))).lower()

    # Vérifier si au moins un marqueur de limitation est présent
    limitations_trouvees = any(
        re.search(p, texte_analyse) for p in _PATTERNS_LIMITATIONS
    )

    # Détecter les termes pauvres (diagnostic sans conséquence dans les 150 chars suivants)
    for terme in _TERMES_PAUVRES:
        match = re.search(re.escape(terme), texte_analyse, re.IGNORECASE)
        if match:
            # Regarder les 150 caractères suivants pour trouver une conséquence
            fenetre = texte_analyse[match.end():match.end() + 150]
            a_consequence = any(re.search(p, fenetre) for p in _PATTERNS_CONSEQUENCES + _PATTERNS_LIMITATIONS)
            if not a_consequence:
                zones_pauvres.append(f"'{terme}' mentionné sans description de ses conséquences concrètes")

    return limitations_trouvees, zones_pauvres


# ── Sous-agent 2 — Projet de Vie ──────────────────────────────────────────────

def _analyser_projet_vie(texte_e: str) -> tuple[bool, list[str]]:
    """
    Vérifie que la section E contient les 4 dimensions obligatoires.
    Retourne (complet, dimensions_manquantes).
    """
    texte = texte_e.lower()
    manquantes: list[str] = []

    dimensions = {
        "besoins":   _PATTERNS_BESOINS,
        "attentes":  _PATTERNS_ATTENTES,
        "objectifs": _PATTERNS_OBJECTIFS,
        "souhaits":  [r"souhai", r"désir", r"aspir", r"envie de"],
    }
    for nom_dim, patterns in dimensions.items():
        if not any(re.search(p, texte) for p in patterns):
            manquantes.append(nom_dim)

    return len(manquantes) == 0, manquantes


# ── Sous-agent 3 — Cohérence CERFA ───────────────────────────────────────────

def _analyser_coherence(donnees: dict[str, Any], textes: dict[str, str]) -> list[str]:
    """
    Détecte les contradictions entre sections.
    Retourne la liste des messages d'alerte ORANGE.
    """
    texte_global = " ".join([
        str(v).lower() for v in {**donnees, **textes}.values()
        if isinstance(v, str)
    ])
    alertes: list[str] = []

    for contradiction in _CONTRADICTIONS:
        a_trouve = any(re.search(p, texte_global) for p in contradiction["signal_a"])
        b_trouve = any(re.search(p, texte_global) for p in contradiction["signal_b"])
        if a_trouve and b_trouve:
            alertes.append(f"[COHÉRENCE] {contradiction['message']}")

    return alertes


# ── Analyse d'une section ─────────────────────────────────────────────────────

def _analyser_section(nom: str, texte: str, seuil_longueur: int) -> QualiteSection:
    """Évalue une section sur les dimensions de contenu + longueur."""
    t = texte.lower()
    sec = QualiteSection(section=nom, longueur=len(texte))
    sec.longueur_suffisante = len(texte) >= seuil_longueur

    sec.limitations_ok  = any(re.search(p, t) for p in _PATTERNS_LIMITATIONS)
    sec.consequences_ok = any(re.search(p, t) for p in _PATTERNS_CONSEQUENCES)
    sec.besoins_ok      = any(re.search(p, t) for p in _PATTERNS_BESOINS)

    if nom == "E":
        sec.attentes_ok  = any(re.search(p, t) for p in _PATTERNS_ATTENTES)
        sec.objectifs_ok = any(re.search(p, t) for p in _PATTERNS_OBJECTIFS)

    # Infos manquantes déclarées par le moteur narratif
    sec.infos_manquantes = re.findall(r"\[INFO MANQUANTE\s*:\s*([^\]]+)\]", texte)

    # Marqueurs de supposition
    _SUPP = ["probablement", "sans doute", "il est possible que", "vraisemblablement",
             "il semblerait", "peut-être que", "on suppose"]
    sec.marqueurs_supposition = [m for m in _SUPP if m in t]

    return sec


# ── Score de maturité CERFA ───────────────────────────────────────────────────

def _calculer_score_maturite(
    sections: dict[str, QualiteSection],
    donnees: dict[str, Any],
    profil_mdph: str,
) -> int:
    """
    Calcule le score de maturité CERFA (0-100).

    Poids :
      E (projet de vie)      : 30 pts  ← le plus important
      B (vie quotidienne)    : 25 pts
      Retentissement présent : 20 pts
      C (scolarité)          : 10 pts  (si active, sinon score plein)
      D (situation pro)      : 10 pts  (si active, sinon score plein)
      Pièces présentes       :  5 pts
    """
    score = 0

    # ── Section E (30 pts) ────────────────────────────────────────────────────
    if "E" in sections:
        sec_e = sections["E"]
        score += int(30 * sec_e.score_dimensions)
    else:
        score += 15  # données insuffisantes → score partiel

    # ── Section B (25 pts) ────────────────────────────────────────────────────
    if "B" in sections:
        sec_b = sections["B"]
        score += int(25 * sec_b.score_dimensions)
    else:
        # Fallback sur les données brutes si texte narratif absent
        if donnees.get("impact_quotidien"):
            score += 10
        if donnees.get("diagnostics"):
            score += 5

    # ── Retentissement fonctionnel (20 pts) ────────────────────────────────────
    texte_b_brut = sections.get("B", QualiteSection(section="B")).longueur
    impact_raw   = str(donnees.get("impact_quotidien", "")).lower()
    a_retent = (
        ("B" in sections and sections["B"].limitations_ok)
        or any(re.search(p, impact_raw) for p in _PATTERNS_LIMITATIONS)
    )
    score += 20 if a_retent else 0

    # ── Section C (10 pts) ────────────────────────────────────────────────────
    section_c_active = (
        profil_mdph == "enfant"
        or str(donnees.get("qualification_section_c", "")).lower().startswith("oui")
    )
    if section_c_active:
        score += int(10 * sections["C"].score_dimensions) if "C" in sections else 0
    else:
        score += 10  # non applicable → score plein

    # ── Section D (10 pts) ────────────────────────────────────────────────────
    section_d_active = (
        profil_mdph != "enfant"
        and str(donnees.get("qualification_section_d", "")).lower().startswith("oui")
    ) or bool(donnees.get("statut_emploi"))
    if section_d_active:
        score += int(10 * sections["D"].score_dimensions) if "D" in sections else 0
    else:
        score += 10  # non applicable → score plein

    # ── Pièces justificatives (5 pts) ─────────────────────────────────────────
    if donnees.get("documents_texte") or donnees.get("certificat_medical"):
        score += 5

    return min(score, 100)


def _niveau_maturite(score: int) -> str:
    if score <= 30:  return "FAIBLE"
    if score <= 60:  return "MOYEN"
    if score <= 85:  return "SOLIDE"
    return "EXCELLENT"


# ── Fonction principale ────────────────────────────────────────────────────────

def _verifier_themes_profil(
    profil_principal: str,
    sous_profil: str,
    texte_b: str,
    texte_e: str,
) -> list[str]:
    """
    Vérifie que les thèmes obligatoires du profil sont bien présents dans les textes.

    Évaluation THÉMATIQUE (concepts) — pas de recherche de mots-clés exacts.
    Utilise GPT-4o-mini avec une question binaire par thème.

    Retourne une liste d'alertes ROUGE pour les thèmes absents.
    Non bloquant si l'appel LLM échoue.
    """
    try:
        from app.engines.profil_specifique_engine import get_profil_specifique
        import os
        from openai import OpenAI

        ps = get_profil_specifique(profil_principal, sous_profil)
        if not ps:
            return []

        alertes: list[str] = []
        client  = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

        def _theme_present(texte: str, theme: str) -> bool:
            """Demande à GPT-4o-mini si le thème est abordé dans le texte."""
            if not texte.strip() or not theme.strip():
                return False
            try:
                rep = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{
                        "role": "user",
                        "content": (
                            f"Le texte suivant aborde-t-il le thème : «{theme}» ?\n"
                            f"Réponds uniquement OUI ou NON.\n\n"
                            f"Texte :\n{texte[:1500]}"
                        ),
                    }],
                    max_tokens=5,
                    temperature=0.0,
                )
                return "OUI" in rep.choices[0].message.content.upper()
            except Exception:
                return True   # En cas d'erreur → ne pas bloquer

        # Vérification section B
        for theme in ps.themes_qualite_b:
            if not _theme_present(texte_b, theme):
                alertes.append(
                    f"[PROFIL {profil_principal.upper()}] Partie B — "
                    f"thème absent : «{theme}»"
                )

        # Vérification section E
        for theme in ps.themes_qualite_e:
            if not _theme_present(texte_e, theme):
                alertes.append(
                    f"[PROFIL {profil_principal.upper()}] Partie E — "
                    f"thème absent : «{theme}»"
                )

        return alertes

    except Exception as e:
        logger.warning("[QUALITE_PROFIL] Vérification thématique non bloquante : %s", e)
        return []


def verifier_qualite_cerfa(
    donnees: dict[str, Any],
    textes_narratifs: dict[str, str],
    profil_mdph: str = "adulte",
    sections_actives: set[str] | None = None,
) -> QualiteRapport:
    """
    Contrôle qualité complet avant validation finale.

    textes_narratifs : dict produit par cerfa_narrative_engine.generer_textes_narratifs()
    Retourne un QualiteRapport avec alertes rouges/oranges et score de maturité.
    """
    rapport = QualiteRapport()

    if sections_actives is None:
        sections_actives = {"B", "E"}
        if profil_mdph == "enfant" or str(donnees.get("qualification_section_c", "")).lower().startswith("oui"):
            sections_actives.add("C")
        if profil_mdph != "enfant" and (
            str(donnees.get("qualification_section_d", "")).lower().startswith("oui")
            or donnees.get("statut_emploi")
        ):
            sections_actives.add("D")

    # ── Analyse de chaque section ─────────────────────────────────────────────
    _map_champs = {
        "B": "texte_b_vie_quotidienne",
        "C": "texte_c_scolarite",
        "D": "texte_d_situation_pro",
        "E": "texte_e_projet_vie",
    }
    for section, champ in _map_champs.items():
        if section not in sections_actives:
            continue
        texte  = textes_narratifs.get(champ, "")
        seuil  = SEUILS_LONGUEUR.get(champ, 300)
        sec    = _analyser_section(section, texte, seuil)
        rapport.sections[section] = sec

        rapport.infos_manquantes.extend(sec.infos_manquantes)
        rapport.marqueurs_supposition.extend(sec.marqueurs_supposition)

        # Alerte longueur insuffisante (signal secondaire — orange, pas rouge)
        if texte and not sec.longueur_suffisante:
            rapport.alertes_oranges.append(
                f"Section {section} : texte court ({sec.longueur} chars < {seuil} attendus) "
                f"— vérifier si les informations collectées sont suffisantes."
            )

        # Section active vide → ROUGE
        if not texte.strip():
            rapport.alertes_rouges.append(
                f"Section {section} active mais texte vide — collecte insuffisante."
            )

    # ── Sous-agent 1 : Retentissement Fonctionnel ─────────────────────────────
    texte_b = textes_narratifs.get("texte_b_vie_quotidienne", "")
    retent_present, zones_pauvres = _analyser_retentissement(texte_b, donnees)
    rapport.retentissement_absent = not retent_present
    rapport.zones_pauvres = zones_pauvres

    if rapport.retentissement_absent and donnees.get("diagnostics"):
        rapport.alertes_rouges.append(
            "Diagnostic(s) présent(s) mais aucune conséquence fonctionnelle décrite "
            "— la partie B doit décrire ce que la personne ne peut plus faire."
        )
    for zone in zones_pauvres:
        rapport.alertes_oranges.append(f"[ZONE PAUVRE] {zone}")

    # ── Sous-agent 2 : Projet de Vie ──────────────────────────────────────────
    texte_e = textes_narratifs.get("texte_e_projet_vie", "")
    if texte_e.strip():
        projet_complet, dims_manquantes = _analyser_projet_vie(texte_e)
        rapport.projet_vie_incomplet = not projet_complet
        rapport.dimensions_manquantes_E = dims_manquantes
        if not projet_complet:
            rapport.alertes_rouges.append(
                f"Partie E — Projet de vie incomplet. Dimensions manquantes : {', '.join(dims_manquantes)}."
            )
    elif "E" in sections_actives:
        rapport.projet_vie_incomplet = True
        rapport.alertes_rouges.append("Partie E — Projet de vie absente.")

    # ── Sous-agent 3 : Cohérence CERFA ────────────────────────────────────────
    contradictions = _analyser_coherence(donnees, textes_narratifs)
    rapport.contradictions = contradictions
    rapport.alertes_oranges.extend(contradictions)

    # ── Sous-agent 4 : Contrôles thématiques par profil ───────────────────────
    _profil_h  = donnees.get("profil_principal", "")
    _sous_prof = donnees.get("sous_profil", "")
    if _profil_h:
        alertes_profil = _verifier_themes_profil(
            profil_principal=_profil_h,
            sous_profil=_sous_prof,
            texte_b=textes_narratifs.get("texte_b_vie_quotidienne", ""),
            texte_e=textes_narratifs.get("texte_e_projet_vie", ""),
        )
        rapport.alertes_rouges.extend(alertes_profil)

    # ── Score de maturité ─────────────────────────────────────────────────────
    rapport.score_maturite  = _calculer_score_maturite(rapport.sections, donnees, profil_mdph)
    rapport.niveau_maturite = _niveau_maturite(rapport.score_maturite)

    logger.info(
        "[QUALITE_CERFA] score_maturite=%d (%s) alertes_rouges=%d alertes_oranges=%d",
        rapport.score_maturite, rapport.niveau_maturite,
        len(rapport.alertes_rouges), len(rapport.alertes_oranges),
    )

    return rapport
