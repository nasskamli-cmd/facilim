"""
validators/cerfa_validator.py — Validation des données collectées avant génération CERFA.

Rôle : vérifier que les données collectées (via WhatsApp ou saisie éducateur) sont
suffisamment complètes et cohérentes pour remplir le CERFA 15692.

Ce validateur NE valide PAS les données médicales (diagnostic, NIR, médecin, traitements).
Ces champs transitent par le canal sécurisé (email) et sont validés séparément.

Retour de valider() :
    {
        "valide":   bool,
        "erreurs":  list[str],   # messages d'erreur lisibles (compatibles relance_questions.py)
        "warnings": list[str],   # champs recommandés mais non bloquants
        "donnees":  dict,        # données d'entrée (inchangées)
    }
"""

from __future__ import annotations

import re
import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Valeurs autorisées — cohérentes avec conversation_agent.py et cerfa_filler.py
# ---------------------------------------------------------------------------

_TYPES_DEMANDE_VALIDES = frozenset({
    "premiere_demande", "première_demande", "premiere demande",
    "renouvellement", "reevaluation", "réévaluation",
    # Abréviations acceptées
    "premiere", "première", "renouveler", "renouveler les droits",
})

_GENRES_VALIDES = frozenset({
    "homme", "femme", "h", "f", "masculin", "féminin", "feminin",
    "male", "female", "m",
})

_SITUATIONS_FAMILIALES_VALIDES = frozenset({
    "célibataire", "celibataire",
    "marié", "mariée", "marie", "mariee",
    "en couple", "pacsé", "pacsée", "pacse", "pacsee",
    "divorcé", "divorcée", "divorce", "divorcee",
    "séparé", "séparée", "separe", "separee",
    "veuf", "veuve",
})

_DROITS_CONNUS = frozenset({
    "aah", "rqth", "pch", "aeeh", "cmi",
    "orp",
    "ime", "esat", "sessad", "savs", "samsah",
    "emploi accompagné", "emploi accompagne",
    "carte priorité", "carte priorite",
    "carte stationnement",
    "prestation compensation", "aide humaine",
    "formation",
})

# Champs obligatoires pour un dossier CERFA valide
# (hors champs médicaux et champs conditionnels)
_CHAMPS_OBLIGATOIRES: list[str] = [
    "type_demande",
    "nom_prenom",
    "date_naissance",
    "genre",
    "adresse_complete",
    "situation_familiale",
    "type_droits",
    "difficultes_quotidiennes",
]

# Champs recommandés (warning, non bloquants)
_CHAMPS_RECOMMANDES: list[str] = [
    "organisme_payeur",
    "protection_juridique",
    "besoins_aide",
    "ressources_actuelles",
    "situation_pro_scolaire",
]

# Regex NIR : 13 chiffres (ancien format) ou 15 chiffres (format actuel)
# Bug corrigé : les parenthèses groupent l'alternance entière.
# ❌ r'^\d{13}|\d{15}$'  → matche (^\d{13}) OU (\d{15}$) — faux positifs
# ✅ r'^(\d{13}|\d{15})$' → matche exactement 13 ou 15 chiffres en totalité
_NIR_RE = re.compile(r'^(\d{13}|\d{15})$')

# Regex date JJ/MM/AAAA
_DATE_RE = re.compile(r'^\d{2}/\d{2}/\d{4}$')


class CERFAValidator:
    """
    Valide les données collectées pour le CERFA 15692.

    Usage :
        validation = CERFAValidator(donnees_collectees).valider()
        if not validation["valide"]:
            print(validation["erreurs"])
    """

    def __init__(self, donnees: dict[str, Any]) -> None:
        self.donnees = donnees or {}
        self._erreurs:  list[str] = []
        self._warnings: list[str] = []

    # ------------------------------------------------------------------
    # Point d'entrée public
    # ------------------------------------------------------------------

    def valider(self) -> dict[str, Any]:
        """
        Lance toutes les validations et retourne le résultat structuré.

        Returns:
            {"valide": bool, "erreurs": list[str], "warnings": list[str], "donnees": dict}
        """
        self._erreurs  = []
        self._warnings = []

        self._valider_champs_obligatoires()
        self._valider_format_date()
        self._valider_genre()
        self._valider_situation_familiale()
        self._valider_type_demande()
        self._valider_type_droits()
        self._valider_nir()         # uniquement si fourni (non bloquant si absent)
        self._verifier_champs_recommandes()

        valide = len(self._erreurs) == 0
        if valide:
            logger.info("[VALIDATOR] Dossier valide.")
        else:
            logger.warning(f"[VALIDATOR] Dossier invalide : {len(self._erreurs)} erreur(s).")

        return {
            "valide":   valide,
            "erreurs":  list(self._erreurs),
            "warnings": list(self._warnings),
            "donnees":  self.donnees,
        }

    # ------------------------------------------------------------------
    # Validations individuelles (privées)
    # ------------------------------------------------------------------

    def _valider_champs_obligatoires(self) -> None:
        """Vérifie que tous les champs obligatoires sont présents et non vides."""
        for champ in _CHAMPS_OBLIGATOIRES:
            valeur = self.donnees.get(champ)
            if not valeur or not str(valeur).strip():
                self._erreurs.append(
                    f"champ requis manquant : {champ}"
                )

    def _valider_format_date(self) -> None:
        """Vérifie que date_naissance est au format JJ/MM/AAAA et représente une date réelle."""
        ddn = str(self.donnees.get("date_naissance", "")).strip()
        if not ddn:
            return  # Déjà géré par _valider_champs_obligatoires

        if not _DATE_RE.match(ddn):
            self._erreurs.append(
                "date_naissance : format invalide — attendu JJ/MM/AAAA "
                f"(reçu : {ddn!r})"
            )
            return

        try:
            jour, mois, annee = (int(p) for p in ddn.split("/"))
            date(annee, mois, jour)  # lève ValueError si date impossible
        except ValueError:
            self._erreurs.append(
                f"date_naissance : date impossible ({ddn!r})"
            )
            return

        # Vérification de cohérence : pas de date dans le futur
        naissance = date(annee, mois, jour)  # type: ignore[arg-type]
        if naissance > date.today():
            self._erreurs.append(
                f"date_naissance : date dans le futur ({ddn!r})"
            )

    def _valider_genre(self) -> None:
        """Vérifie que le genre est une valeur reconnue."""
        genre = str(self.donnees.get("genre", "")).strip().lower()
        if not genre:
            return  # Déjà géré par _valider_champs_obligatoires

        if genre not in _GENRES_VALIDES:
            self._erreurs.append(
                f"genre : valeur non reconnue ({genre!r}) — "
                "valeurs attendues : homme, femme"
            )

    def _valider_situation_familiale(self) -> None:
        """Vérifie que la situation familiale est une valeur reconnue."""
        sf = str(self.donnees.get("situation_familiale", "")).strip().lower()
        if not sf:
            return  # Déjà géré par _valider_champs_obligatoires

        if sf not in _SITUATIONS_FAMILIALES_VALIDES:
            self._warnings.append(
                f"situation_familiale : valeur non standard ({sf!r}) — "
                "valeurs habituelles : célibataire, marié·e, en couple, divorcé·e, veuf·ve"
            )

    def _valider_type_demande(self) -> None:
        """Vérifie que le type de demande est reconnu."""
        td = str(self.donnees.get("type_demande", "")).strip().lower()
        if not td:
            return  # Déjà géré par _valider_champs_obligatoires

        if td not in _TYPES_DEMANDE_VALIDES:
            self._erreurs.append(
                f"type_demande : valeur non reconnue ({td!r}) — "
                "valeurs attendues : premiere_demande, renouvellement"
            )

    def _valider_type_droits(self) -> None:
        """
        Vérifie que type_droits contient au moins un droit reconnu.
        Un dossier sans droit identifiable n'a aucune raison d'être soumis à la MDPH.
        """
        td = str(self.donnees.get("type_droits", "")).strip().lower()
        if not td:
            return  # Déjà géré par _valider_champs_obligatoires

        td_normalise = td.replace(",", " ").replace(";", " ").replace("/", " ")
        mots = set(td_normalise.split())

        # Vérifie qu'au moins un droit connu est mentionné
        droit_trouve = any(
            droit in td_normalise
            for droit in _DROITS_CONNUS
        )

        if not droit_trouve:
            self._erreurs.append(
                f"type_droits : prestation inconnue -> {td!r} — "
                "valeurs attendues : AAH, RQTH, PCH, AEEH, CMI, ORP, IME, ESAT, SESSAD…"
            )

    def _valider_nir(self) -> None:
        """
        Vérifie le format NIR si fourni.
        Non bloquant si absent (le NIR transite par le canal sécurisé).
        """
        nir = str(self.donnees.get("numero_securite_sociale", "")).strip()
        if not nir:
            return  # Absent = normal, géré par canal sécurisé

        nir_chiffres = re.sub(r'\s', '', nir)  # retire les espaces éventuels
        if not _NIR_RE.match(nir_chiffres):
            self._erreurs.append(
                f"numero_securite_sociale : format invalide — "
                "attendu 13 ou 15 chiffres sans espace "
                f"(reçu : {len(nir_chiffres)} caractère(s))"
            )

    def _verifier_champs_recommandes(self) -> None:
        """Génère des warnings pour les champs recommandés mais non bloquants."""
        for champ in _CHAMPS_RECOMMANDES:
            valeur = self.donnees.get(champ)
            if not valeur or not str(valeur).strip():
                self._warnings.append(
                    f"champ recommandé manquant : {champ} "
                    "(le dossier sera moins complet sans cette information)"
                )
