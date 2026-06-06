"""
app/engines/human_validation_engine.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FACILIM 85 — Couche de validation humaine obligatoire

Classifie chaque élément détecté par Facilim en deux catégories :
  AUTOMATIQUE   : informations factuelles sans impact CDAPH
  À_VALIDER     : toute proposition ayant un impact sur la décision MDPH

RÈGLE ABSOLUE :
  Aucun droit stratégique ne peut être marqué validé = True
  sans action explicite du professionnel.
  La valeur par défaut est toujours validation_professionnelle = False.

Usage :
  from app.engines.human_validation_engine import creer_tableau_validation
  tableau = creer_tableau_validation(donnees, profil_mdph="adulte")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger("facilim.engines.human_validation")


# ─────────────────────────────────────────────────────────────────────────────
# CLASSIFICATION DES ÉLÉMENTS
# ─────────────────────────────────────────────────────────────────────────────

# Éléments factuels — validation non requise
_ELEMENTS_AUTOMATIQUES: set[str] = {
    "nom", "prenom", "nom_usage", "adresse", "telephone", "telephone_fixe",
    "email", "date_naissance", "num_secu", "genre", "nationalite",
    "departement", "code_postal", "commune", "pays_naissance",
    "commune_naissance", "numero_allocataire", "organisme_payeur",
    "type_dossier", "numero_dossier_mdph", "representant_legal_nom",
    "representant_legal_lien", "representant_legal_naissance",
    "aidant_nom", "aidant_lien", "mode_vie", "type_logement",
    "nom_employeur", "type_protection",
}

# Droits et orientations ayant un impact CDAPH — validation obligatoire
_DROITS_STRATEGIQUES: dict[str, str] = {
    "AAH":               "Allocation aux Adultes Handicapés",
    "PCH":               "Prestation de Compensation du Handicap",
    "RQTH":              "Reconnaissance Qualité Travailleur Handicapé",
    "CMI":               "Carte Mobilité Inclusion (tout type)",
    "CMI_STATIONNEMENT": "CMI — Mention Stationnement",
    "CMI_PRIORITE":      "CMI — Mention Priorité",
    "CMI_INVALIDITE":    "CMI — Mention Invalidité",
    "AEEH":              "Allocation d'Éducation de l'Enfant Handicapé",
    "AVPF":              "Affiliation Vieillesse Parent au Foyer",
    "SAVS":              "Service d'Accompagnement à la Vie Sociale",
    "SAMSAH":            "Service d'Accompagnement Médico-Social Adultes",
    "ESAT":              "Établissement et Service d'Aide par le Travail",
    "ESPO":              "Évaluation et Soutien à l'Orientation Pro.",
    "ESRP":              "Établissement Rééducation Professionnelle",
    "UEROS":             "Unité d'Évaluation Rééducation Orientation Sociale",
    "EMPLOI_ACCOMPAGNE": "Emploi Accompagné",
    "SESSAD":            "Service Éducation Spéciale et Soins à Domicile",
    "IME":               "Institut Médico-Éducatif",
    "ITEP":              "Institut Thérapeutique Éducatif et Pédagogique",
    "ULIS":              "Unité Localisée pour l'Inclusion Scolaire",
    "EEAP":              "Établissement pour Enfants Polyhandicapés",
    "MAS":               "Maison d'Accueil Spécialisée",
    "FAM":               "Foyer d'Accueil Médicalisé",
    "FOYER_VIE":         "Foyer de Vie",
    "FOYER_HEBERGEMENT": "Foyer d'Hébergement (ESAT)",
    "ACTP":              "Allocation Compensatrice Tierce Personne",
}


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ElementAutomatique:
    """Élément factuel — validation non requise."""
    champ:          str     # nom du champ dans donnees
    valeur:         str     # valeur présente
    label:          str     # description lisible
    present:        bool    # est-ce que la donnée est renseignée ?


@dataclass
class ElementAValider:
    """Proposition stratégique — validation humaine obligatoire."""
    element:                    str         # identifiant (ex: "PCH")
    label:                      str         # libellé complet
    confiance:                  int         # 0-100
    statut:                     str         # "a_valider" | "valide" | "refuse" | "modifie"
    preuves:                    list[str]   # preuves depuis evidence engine
    sources:                    list[str]   # types de sources
    citations:                  list[str]   # extraits textuels
    decision_previsible:        str         # "favorable" | "incertain" | "défavorable"
    raisonnement:               str
    pieces_manquantes:          list[str]

    # Validation humaine — JAMAIS pré-remplie à True
    validation_professionnelle: bool   = False
    commentaire_professionnel:  str    = ""
    date_validation:            str    = ""
    modifie_par:                str    = ""

    def valider(self, commentaire: str = "", auteur: str = "") -> None:
        """Valide l'élément. Appel humain obligatoire."""
        self.validation_professionnelle = True
        self.statut = "valide"
        self.commentaire_professionnel = commentaire
        self.date_validation = datetime.now().isoformat()
        self.modifie_par = auteur

    def refuser(self, raison: str = "", auteur: str = "") -> None:
        """Refuse l'élément."""
        self.validation_professionnelle = False
        self.statut = "refuse"
        self.commentaire_professionnel = raison
        self.date_validation = datetime.now().isoformat()
        self.modifie_par = auteur

    def modifier(self, nouveau_commentaire: str, auteur: str = "") -> None:
        """Modifie avec commentaire — nécessite quand même validation explicite."""
        self.commentaire_professionnel = nouveau_commentaire
        self.statut = "modifie"
        self.modifie_par = auteur

    @property
    def est_valide(self) -> bool:
        return self.statut == "valide" and self.validation_professionnelle

    def to_dict(self) -> dict:
        return {
            "element":                   self.element,
            "label":                     self.label,
            "confiance":                 self.confiance,
            "statut":                    self.statut,
            "preuves":                   self.preuves,
            "sources":                   self.sources,
            "citations":                 self.citations[:2],
            "decision_previsible":       self.decision_previsible,
            "raisonnement":              self.raisonnement,
            "pieces_manquantes":         self.pieces_manquantes[:2],
            "validation_professionnelle":self.validation_professionnelle,
            "commentaire":               self.commentaire_professionnel,
            "date_validation":           self.date_validation,
        }


@dataclass
class TableauValidation:
    """Tableau complet de validation humaine pour un dossier."""

    # Éléments factuels (automatiques)
    elements_automatiques:      list[ElementAutomatique]
    nb_automatiques_presents:   int
    nb_automatiques_manquants:  int

    # Éléments à valider
    elements_a_valider:         list[ElementAValider]

    # Statistiques de validation
    @property
    def nb_a_valider(self) -> int:
        return len(self.elements_a_valider)

    @property
    def nb_valides(self) -> int:
        return sum(1 for e in self.elements_a_valider if e.est_valide)

    @property
    def nb_refuses(self) -> int:
        return sum(1 for e in self.elements_a_valider if e.statut == "refuse")

    @property
    def nb_en_attente(self) -> int:
        return sum(1 for e in self.elements_a_valider if e.statut == "a_valider")

    @property
    def pret_pour_cerfa(self) -> bool:
        """Vrai seulement si TOUS les éléments à fort impact ont été validés ou refusés."""
        hautes_confidences = [e for e in self.elements_a_valider if e.confiance >= 60]
        return all(e.statut in ("valide", "refuse") for e in hautes_confidences)

    def get_valides(self) -> list[str]:
        """Retourne les identifiants des éléments validés."""
        return [e.element for e in self.elements_a_valider if e.est_valide]

    def get_a_valider(self) -> list[ElementAValider]:
        """Retourne les éléments en attente de validation."""
        return [e for e in self.elements_a_valider if e.statut == "a_valider"]

    def to_dict(self) -> dict:
        return {
            "elements_automatiques": {
                "presents": self.nb_automatiques_presents,
                "manquants": self.nb_automatiques_manquants,
                "liste": [{"champ": e.champ, "valeur": e.valeur[:40] if e.valeur else ""}
                          for e in self.elements_automatiques if e.present],
            },
            "elements_a_valider": [e.to_dict() for e in self.elements_a_valider],
            "statistiques": {
                "total_a_valider": self.nb_a_valider,
                "valides":         self.nb_valides,
                "refuses":         self.nb_refuses,
                "en_attente":      self.nb_en_attente,
                "pret_pour_cerfa": self.pret_pour_cerfa,
            },
        }


# ─────────────────────────────────────────────────────────────────────────────
# CONSTRUCTION DU TABLEAU
# ─────────────────────────────────────────────────────────────────────────────

def _construire_automatiques(donnees: dict) -> list[ElementAutomatique]:
    """Construit la liste des éléments automatiques."""
    _LABELS = {
        "nom": "Nom de naissance",
        "prenom": "Prénom",
        "adresse": "Adresse complète",
        "telephone": "Téléphone",
        "email": "Email",
        "date_naissance": "Date de naissance",
        "num_secu": "Numéro de sécurité sociale",
        "genre": "Genre",
        "nationalite": "Nationalité",
        "departement": "Département MDPH",
        "representant_legal_nom": "Représentant légal",
        "aidant_nom": "Aidant familial",
        "mode_vie": "Mode de vie",
        "type_logement": "Type de logement",
        "nom_employeur": "Employeur",
        "type_dossier": "Type de demande",
        "type_protection": "Mesure de protection",
    }

    # Extraire nom/prénom depuis nom_prenom
    nom_complet = donnees.get("nom_prenom", "")

    champs_à_vérifier = {
        "nom":                      nom_complet.split()[0] if nom_complet else "",
        "prenom":                   nom_complet.split()[-1] if nom_complet else "",
        "adresse":                  donnees.get("adresse_complete", ""),
        "telephone":                donnees.get("telephone", ""),
        "email":                    donnees.get("email", ""),
        "date_naissance":           donnees.get("date_naissance", ""),
        "num_secu":                 donnees.get("num_secu", ""),
        "genre":                    donnees.get("genre", ""),
        "nationalite":              donnees.get("nationalite", ""),
        "departement":              donnees.get("departement", ""),
        "representant_legal_nom":   donnees.get("representant_legal_nom", ""),
        "aidant_nom":               donnees.get("aidant_nom", ""),
        "mode_vie":                 donnees.get("mode_vie", ""),
        "type_logement":            donnees.get("type_logement", ""),
        "nom_employeur":            donnees.get("nom_employeur", ""),
        "type_dossier":             donnees.get("type_dossier", ""),
        "type_protection":          donnees.get("type_protection", ""),
    }

    return [
        ElementAutomatique(
            champ=champ,
            valeur=str(valeur) if valeur else "",
            label=_LABELS.get(champ, champ),
            present=bool(valeur),
        )
        for champ, valeur in champs_à_vérifier.items()
    ]


def _construire_a_valider(
    donnees: dict,
    rapport_cdaph,
    graphe_preuves,
) -> list[ElementAValider]:
    """
    Construit la liste des éléments à validation humaine.

    Pour chaque droit détecté (solide ou fragile) :
    - confiance = robustesse_pct du rapport CDAPH
    - preuves = depuis le graphe de preuves
    - validation_professionnelle = False (jamais pré-validé)
    """
    elements: list[ElementAValider] = []
    seen: set[str] = set()

    def _ajouter(droit_analyse) -> None:
        if droit_analyse.droit in seen:
            return
        seen.add(droit_analyse.droit)

        label = _DROITS_STRATEGIQUES.get(
            droit_analyse.droit,
            droit_analyse.label,
        )

        # Preuves depuis le graphe
        preuves_droit = graphe_preuves.preuves_pour_droit(droit_analyse.droit)
        preuves_descriptions = [p.information for p in preuves_droit[:4]]
        sources = sorted(set(p.source_type for p in preuves_droit))
        citations = [p.citation[:100] for p in preuves_droit[:2]]

        elements.append(ElementAValider(
            element=droit_analyse.droit,
            label=label,
            confiance=droit_analyse.robustesse_pct,
            statut="a_valider",  # TOUJOURS en attente au départ
            preuves=preuves_descriptions or droit_analyse.forces[:3],
            sources=sources,
            citations=citations,
            decision_previsible=droit_analyse.decision_previsible,
            raisonnement=droit_analyse.raisonnement_cdaph,
            pieces_manquantes=droit_analyse.pieces_manquantes[:2],
            validation_professionnelle=False,  # JAMAIS pré-remplie
        ))

    # Droits solides ET fragiles — tous doivent être validés
    for d in rapport_cdaph.droits_solides:
        _ajouter(d)
    for d in rapport_cdaph.droits_fragiles:
        _ajouter(d)

    # Tri : les plus confiants en premier (le professionnel valide les plus solides d'abord)
    elements.sort(key=lambda e: -e.confiance)

    return elements


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────────────────────

def creer_tableau_validation(
    donnees: dict[str, Any],
    profil_mdph: str = "adulte",
    profil_handicap: str = "",
) -> TableauValidation:
    """
    Crée le tableau de validation humaine complet.

    GARANTIE :
    - Aucun élément stratégique n'est pré-validé (validation_professionnelle = False)
    - Le professionnel doit appeler .valider() ou .refuser() explicitement
    - pret_pour_cerfa = False tant que tous les éléments ≥ 60% ne sont pas traités

    Args:
        donnees:        synthese_json du dossier
        profil_mdph:    "adulte" | "enfant" | "protege" | "mixte"
        profil_handicap: optionnel

    Returns:
        TableauValidation avec éléments classifiés et en attente de validation
    """
    # Éléments automatiques (factuels)
    auto_elements = _construire_automatiques(donnees)
    nb_presents  = sum(1 for e in auto_elements if e.present)
    nb_manquants = sum(1 for e in auto_elements if not e.present)

    # Analyse CDAPH + preuves (depuis moteurs existants)
    try:
        from app.engines.cdaph_strategy_engine import analyser_strategie_cdaph
        from app.engines.evidence_engine import construire_graphe_preuves

        rapport_cdaph = analyser_strategie_cdaph(donnees, profil_mdph, profil_handicap)
        graphe = construire_graphe_preuves(donnees, profil_mdph)

        a_valider = _construire_a_valider(donnees, rapport_cdaph, graphe)

    except Exception as e:
        logger.warning(f"Moteurs indisponibles : {e}")
        # Mode dégradé : créer les éléments depuis droits_demandes uniquement
        droits_raw = str(donnees.get("droits_demandes", "") or "").upper()
        import re
        droits_tokens = re.findall(r"[A-Z][A-Z_]+", droits_raw)
        a_valider = [
            ElementAValider(
                element=d,
                label=_DROITS_STRATEGIQUES.get(d, d),
                confiance=50,
                statut="a_valider",
                preuves=[],
                sources=[],
                citations=[],
                decision_previsible="incertain",
                raisonnement="Analyse moteur indisponible — vérifier manuellement",
                pieces_manquantes=[],
                validation_professionnelle=False,
            )
            for d in droits_tokens
            if d in _DROITS_STRATEGIQUES
        ]

    return TableauValidation(
        elements_automatiques=auto_elements,
        nb_automatiques_presents=nb_presents,
        nb_automatiques_manquants=nb_manquants,
        elements_a_valider=a_valider,
    )
