"""
app/engines/rules_engine.py — Moteur de règles métier MDPH.

Encode les règles réglementaires MDPH en logique déterministe.
Ces règles sont non-LLM : elles s'exécutent avant le scoring Jade
et servent de garde-fous contractuels.

Règles implémentées :
  - Certificat médical obligatoire (bloquant)
  - Age minimum/maximum selon le type de droit
  - Cohérence département/domicile
  - Délais de renouvellement (anticipation 6 mois)
  - Pièces justificatives obligatoires par type de demande
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("facilim.engines.rules")


@dataclass
class RuleViolation:
    code:        str
    message:     str
    bloquant:    bool = True
    droit_impact: str | None = None


@dataclass
class RulesResult:
    valid:          bool
    violations:     list[RuleViolation] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)

    def add_violation(self, code: str, message: str, bloquant: bool = True) -> None:
        self.violations.append(RuleViolation(code=code, message=message, bloquant=bloquant))
        if bloquant:
            self.valid = False

    def add_warning(self, message: str) -> None:
        self.avertissements.append(message)


# ── Règles par type de droit ─────────────────────────────────────────────────

_PIECES_PAR_DROIT: dict[str, list[str]] = {
    "AAH": [
        "Justificatif d'identité",
        "Certificat médical (CERFA 13878)",
        "Justificatif de domicile",
        "Avis d'imposition",
    ],
    "PCH": [
        "Justificatif d'identité",
        "Certificat médical (CERFA 13878)",
        "Justificatif de domicile",
        "Devis ou factures des aides humaines",
        "Plan d'aide si renouvellement",
    ],
    "RQTH": [
        "Justificatif d'identité",
        "Certificat médical",
        "Justificatif de domicile",
    ],
    "AEEH": [
        "Justificatif d'identité du responsable légal",
        "Certificat médical enfant (CERFA 13878)",
        "Justificatif de domicile",
        "Compte-rendu scolaire ou médical récent",
    ],
    "CMI": [
        "Justificatif d'identité",
        "Certificat médical",
        "Justificatif de domicile",
        "Photo d'identité",
    ],
}

_AGE_MINIMUM_AAH   = 20
_AGE_MAXIMUM_AEEH  = 20
_AGE_MINIMUM_PCH   = 0   # Possible dès la naissance (si handicap congénital)
_DELAI_RENOUVELLEMENT_ALERTE_JOURS = 180  # 6 mois avant expiration


def check_certificat_medical(dossier: dict[str, Any], pieces: list[dict]) -> RuleViolation | None:
    """Règle bloquante : le certificat médical est obligatoire."""
    has_cert = any(
        p.get("type_piece") in ("CERTIFICAT_MEDICAL", "BILAN_FONCTIONNEL")
        and p.get("validee_par") is not None
        for p in pieces
    )
    if not has_cert:
        return RuleViolation(
            code="CERT_MEDICAL_MANQUANT",
            message=(
                "Le certificat médical (CERFA 13878) est obligatoire pour toute demande MDPH. "
                "Sans ce document, aucune décision ne peut être prise."
            ),
            bloquant=True,
        )
    return None


def check_coherence_age(
    date_naissance: str | None,
    droits_demandes: list[str],
) -> list[RuleViolation]:
    """Vérifie la cohérence âge / type de droit."""
    violations = []
    if not date_naissance:
        return violations

    try:
        # Parsing souple (JJ/MM/AAAA ou AAAA-MM-JJ)
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                ddn = datetime.strptime(date_naissance.strip(), fmt)
                break
            except ValueError:
                continue
        else:
            return violations

        today = datetime.now(timezone.utc).replace(tzinfo=None)
        age_annees = (today - ddn).days // 365

        if "AAH" in droits_demandes and age_annees < _AGE_MINIMUM_AAH:
            violations.append(RuleViolation(
                code="AGE_INSUFFISANT_AAH",
                message=f"L'AAH est accessible à partir de {_AGE_MINIMUM_AAH} ans (âge actuel : {age_annees} ans).",
                bloquant=True,
                droit_impact="AAH",
            ))

        if "AEEH" in droits_demandes and age_annees >= _AGE_MAXIMUM_AEEH:
            violations.append(RuleViolation(
                code="AGE_EXCESSIF_AEEH",
                message=f"L'AEEH est réservée aux enfants de moins de {_AGE_MAXIMUM_AEEH} ans.",
                bloquant=True,
                droit_impact="AEEH",
            ))

    except Exception:
        pass

    return violations


def check_pieces_requises(
    droits_demandes: list[str],
    pieces_presentes: list[dict],
) -> list[str]:
    """Retourne la liste des pièces manquantes selon les droits demandés."""
    types_presents = {p.get("type_piece", "") for p in pieces_presentes}
    manquantes = []

    for droit in droits_demandes:
        pieces_requises = _PIECES_PAR_DROIT.get(droit, [])
        for piece in pieces_requises:
            # Matching par mots significatifs (évite les faux positifs du [:10])
            # On normalise et on cherche les mots > 4 chars de la pièce requise
            mots_cles = [m for m in piece.lower().split() if len(m) > 4]
            found = any(
                all(mot in t.lower() for mot in mots_cles)
                for t in types_presents
            ) if mots_cles else any(
                piece.lower() in t.lower() for t in types_presents
            )
            if not found and piece not in manquantes:
                manquantes.append(f"{piece} (requis pour {droit})")

    return manquantes


def check_coherence_departement(
    departement_code: str | None,
    adresse_usager: str | None,
) -> RuleViolation | None:
    """
    Alerte si le département du dossier ne correspond pas à l'adresse.
    Non-bloquant (l'usager peut avoir déménagé).
    """
    if not departement_code or not adresse_usager:
        return None
    # Extraction du code postal dans l'adresse
    import re
    cp_match = re.search(r"\b(\d{5})\b", adresse_usager)
    if not cp_match:
        return None
    cp = cp_match.group(1)
    # DOM-TOM : 971-976 (Guadeloupe, Martinique, Guyane, Réunion, Mayotte, Saint-Pierre)
    # et 98x (Collectivités) → utiliser les 3 premiers chiffres
    if cp[:2] in ("97", "98"):
        dept_from_cp = cp[:3]
    else:
        dept_from_cp = cp[:2]
    if dept_from_cp != departement_code:
        return RuleViolation(
            code="COHERENCE_DEPARTEMENT",
            message=(
                f"Le code postal de l'adresse ({cp}) semble appartenir "
                f"au département {dept_from_cp} mais le dossier est ouvert "
                f"en département {departement_code}. Vérification recommandée."
            ),
            bloquant=False,
        )
    return None


def apply_all_rules(
    dossier: dict[str, Any],
    donnees: dict[str, Any],
    pieces: list[dict],
) -> RulesResult:
    """
    Applique l'ensemble des règles métier sur un dossier.

    Args:
        dossier: Données du dossier (DB)
        donnees: Données collectées (synthese_json)
        pieces: Liste des pièces justificatives

    Returns:
        RulesResult avec violations et avertissements
    """
    result = RulesResult(valid=True)
    droits = donnees.get("types_demande", [])
    if isinstance(droits, str):
        droits = [d.strip() for d in droits.replace(",", " ").split() if d.strip()]

    # Règle 1 : Certificat médical (bloquant)
    violation = check_certificat_medical(dossier, pieces)
    if violation:
        result.add_violation(violation.code, violation.message, violation.bloquant)

    # Règle 2 : Cohérence âge / droits
    ddn = donnees.get("date_naissance")
    age_violations = check_coherence_age(ddn, droits)
    for v in age_violations:
        result.add_violation(v.code, v.message, v.bloquant)

    # Règle 3 : Pièces requises
    pieces_manquantes = check_pieces_requises(droits, pieces)
    for pm in pieces_manquantes:
        result.add_warning(f"Pièce potentiellement manquante : {pm}")

    # Règle 4 : Cohérence département/adresse (non-bloquant)
    dept_violation = check_coherence_departement(
        dossier.get("departement_code"),
        donnees.get("adresse_complete"),
    )
    if dept_violation:
        result.add_violation(dept_violation.code, dept_violation.message, dept_violation.bloquant)

    if result.violations:
        bloquants = [v for v in result.violations if v.bloquant]
        logger.warning(
            f"[RULES] {len(result.violations)} violation(s) | "
            f"{len(bloquants)} bloquante(s) | dossier={dossier.get('id','?')[:8]}"
        )
    else:
        logger.info(f"[RULES] Règles OK | dossier={dossier.get('id','?')[:8]}")

    return result


# ── Moteur de règles fonctionnelles (cases CERFA) ────────────────────────────

from app.database.schemas import DossierCERFA

# ── Dictionnaire des établissements connus — Règle "Établissement Ciblé" ─────
_ETABLISSEMENTS_CONNUS: dict[str, str] = {
    "RICHEBOIS":  "ESRP Richebois",
    "VISA PRO":   "ESRP Visa Pro",
    "VISAPRO":    "ESRP Visa Pro",
    "CRP":        "Centre de Rééducation Professionnelle (CRP)",
    "ESRP":       "Établissement de Réadaptation Professionnelle (ESRP)",
    "CPO":        "Centre de Pré-Orientation (CPO)",
    "UEROS":      "Unité d'Évaluation, de Réentraînement et d'Orientation Sociale (UEROS)",
    "ESAT":       "Établissement et Service d'Aide par le Travail (ESAT)",
}


def _extraire_nom_etablissement(texte: str) -> str | None:
    """
    Cherche dans le texte un nom d'établissement connu et retourne
    son libellé complet normalisé. Retourne None si aucun trouvé.
    """
    texte_upper = texte.upper()
    for token, libelle in _ETABLISSEMENTS_CONNUS.items():
        if token in texte_upper:
            return libelle
    return None


@dataclass
class ConflitAutodetermination:
    """Enregistrement d'un conflit entre le choix usager et l'orientation professionnelle."""
    timestamp:        str
    souhait_usager:   str
    orientation_pro:  str
    champ_modifie:    str = "section_e.projet_professionnel"


def _appliquer_autodetermination(
    dossier: DossierCERFA,
    cerfa_reponses: dict,
    donnees_pro: dict,
) -> ConflitAutodetermination | None:
    """
    Règle A — Autodétermination adulte/mixte (Section D/E).

    Si l'usager exprime un souhait d'orientation différent de celui configuré
    par le professionnel, le choix de l'usager est ABSOLUMENT PRIORITAIRE.
    Le texte du projet professionnel reçoit une mention automatique.

    Retourne un ConflitAutodetermination si un écrasement a eu lieu, None sinon.
    """
    if dossier.profil not in ("adulte", "mixte"):
        return None
    if not dossier.section_e:
        return None

    souhait_usager = (cerfa_reponses.get("souhait_orientation_usager") or "").strip()
    if not souhait_usager:
        return None

    orientation_pro = (
        donnees_pro.get("orientation_professionnelle")
        or donnees_pro.get("projet_professionnel")
        or ""
    ).strip()

    # Pas de conflit → rien à faire
    if not orientation_pro or souhait_usager.lower() == orientation_pro.lower():
        return None

    # Le choix de l'usager prime — mise à jour de section_e
    mention = (
        f"Projet exprimé directement par l'usager dans le cadre de son droit "
        f"à l'autodétermination : {souhait_usager}"
    )
    if not dossier.section_e.projet_professionnel:
        dossier.section_e.projet_professionnel = mention
    elif mention not in dossier.section_e.projet_professionnel:
        dossier.section_e.projet_professionnel = (
            f"{dossier.section_e.projet_professionnel} — {mention}"
        )

    # Réaligner les booléens d'orientation selon le souhait usager
    _souhait_up = souhait_usager.upper()
    if any(t in _souhait_up for t in ("ORDINAIRE", "DROIT COMMUN", "MILIEU ORDINAIRE")):
        dossier.section_e.orientation_esat  = False
        dossier.section_e.orientation_esrp  = False
        dossier.section_e.emploi_accompagne = False
    elif any(t in _souhait_up for t in ("ESAT", "MILIEU PROTEGE", "MILIEU PROTÉGÉ")):
        dossier.section_e.orientation_esat = True
    elif any(t in _souhait_up for t in ("ESRP", "CRP", "RICHEBOIS", "VISA PRO", "FORMATION")):
        dossier.section_e.orientation_esrp = True

    logger.info(
        f"[AUTODÉTERMINATION A] Choix usager ({souhait_usager!r}) "
        f"prioritaire sur orientation pro ({orientation_pro!r})"
    )

    return ConflitAutodetermination(
        timestamp=datetime.now(timezone.utc).isoformat(),
        souhait_usager=souhait_usager,
        orientation_pro=orientation_pro,
    )


def _appliquer_refus_ime(
    dossier: DossierCERFA,
    cerfa_reponses: dict,
) -> None:
    """
    Règle B — Refus IME par les représentants légaux (Section B/C).

    Si les parents/tuteurs expriment un refus d'orientation en IME et
    une préférence pour le milieu ordinaire, le système force les booléens
    correspondants et ajoute une mention dans le projet de vie (Section C).

    Déclencheur : mots-clés de refus IME dans le message WhatsApp collecté
    """
    if dossier.profil not in ("enfant", "mixte"):
        return

    # Texte source : difficultes_quotidiennes + besoins_aide collectés via WhatsApp
    _texte = " ".join([
        cerfa_reponses.get("difficultes_quotidiennes") or "",
        cerfa_reponses.get("besoins_aide") or "",
        cerfa_reponses.get("souhait_scolarisation") or "",
    ]).lower()

    _mots_refus_ime = [
        "pas d'ime", "pas ime", "refus ime", "refuse ime", "refuse l'ime",
        "école ordinaire", "ecole ordinaire", "classe ordinaire",
        "milieu ordinaire", "inclusion scolaire", "pas de structure spécialisée",
        "pas de structure specialisee", "maintien en classe", "pas d'établissement spécialisé",
        "pas d'etablissement specialise", "contre l'ime",
    ]

    if not any(m in _texte for m in _mots_refus_ime):
        return

    # Forcer les booléens dans section_b
    if dossier.section_b:
        dossier.section_b.opposition_ime          = True
        dossier.section_b.scolarisation_ordinaire = True

    # Mention obligatoire dans section_c (projet de vie)
    mention_ime = (
        "Projet d'inclusion scolaire défini par les représentants légaux : "
        "Priorité stricte au milieu ordinaire, refus d'une orientation en "
        "structure médico-sociale type IME."
    )
    if dossier.section_c:
        diff = dossier.section_c.difficultes_quotidiennes or ""
        if mention_ime not in diff:
            dossier.section_c.difficultes_quotidiennes = (
                f"{diff} — {mention_ime}".strip(" —")
            )

    logger.info("[AUTODÉTERMINATION B] Refus IME détecté → inclusion ordinaire forcée")


def executer_regles_metier_mdph(
    dossier: DossierCERFA,
    cerfa_reponses: dict | None = None,
    donnees_pro: dict | None = None,
) -> dict:
    """
    Applique les règles métier MDPH sur le DossierCERFA V3 et retourne
    le dictionnaire des cases à cocher (clés = identifiants CERFA PDF).

    Section C  → cases mobilité / autonomie (C1)
    Section E  → cases orientations professionnelles (P18)
                 Règle 2 — ESPO  : case P18 pré-orientation
                 Règle 3 — ESRP  : case P18 3 (Richebois, Visa Pro, CRP…)
    Section F  → aidant familial (P19-P20) via booléen a_un_aidant
    Urgence    → case P1 urgence
    Règle A    → Autodétermination adulte/mixte
    Règle B    → Refus IME par les représentants légaux
    """
    cerfa_reponses = cerfa_reponses or {}
    donnees_pro    = donnees_pro    or {}

    # ── Règles d'autodétermination (avant le calcul des cases) ───────────────
    conflit = _appliquer_autodetermination(dossier, cerfa_reponses, donnees_pro)
    _appliquer_refus_ime(dossier, cerfa_reponses)

    cases_cerfa: dict = {}
    c = dossier.section_c
    e = dossier.section_e

    # ── Section C — mobilité / autonomie ────────────────────────────────────
    if c.utilise_fauteuil_roulant:
        cases_cerfa["case_C1_difficulte_deplacement"]         = True
        cases_cerfa["case_C1_deplacement_interieur_autonome"] = False

    if c.difficulte_marcher:
        cases_cerfa["case_C1_difficulte_deplacement"] = True

    if c.besoin_aide_toilette:
        cases_cerfa["case_C1_besoin_aide_toilette"] = True

    # ── Logement — anti-inversion propriétaire/locataire ─────────────────────
    if c.statut_occupation == "proprietaire":
        cases_cerfa["OPTION_P5_2_proprietaire"] = True
        cases_cerfa["OPTION_P5_2_locataire"]    = False
    elif c.statut_occupation == "locataire":
        cases_cerfa["OPTION_P5_2_proprietaire"] = False
        cases_cerfa["OPTION_P5_2_locataire"]    = True
    elif c.statut_occupation == "heberge":
        cases_cerfa["OPTION_P5_2_heberge"] = True

    # ── Section A — type_demande ──────────────────────────────────────────────
    _td = (dossier.section_a.type_demande or "").lower()
    if "renouvellement" in _td:
        cases_cerfa["case_P1_renouvellement"]   = True
        cases_cerfa["case_P1_premiere_demande"] = False  # anti-inversion explicite
    elif "premiere" in _td or "première" in _td:
        cases_cerfa["case_P1_premiere_demande"] = True
        cases_cerfa["case_P1_renouvellement"]   = False

    # ── Urgence ───────────────────────────────────────────────────────────────
    if dossier.section_urgence.est_urgent:
        cases_cerfa["Case à cocher P1 urgence"] = True

    # ── Section E — orientations professionnelles ─────────────────────────────
    if e:
        # RQTH — Case P18 1
        if e.orientation_rqth or "RQTH" in " ".join(e.type_droits).upper():
            cases_cerfa["Case à cocher P18 1"] = True

        # Règle 3 — ESRP (Richebois, Visa Pro…) — Case P18 3
        if e.orientation_esrp:
            if not e.orientation_esat:   # ESAT prime sur ESRP
                cases_cerfa["Case à cocher P18 3"] = True
            else:
                logger.warning("[RULES] ESRP + ESAT → ESAT prime, P18 3 ignoré.")
            # Règle "Établissement Ciblé" : enrichir projet_professionnel avec le nom complet
            _texte_e_local = " ".join(e.type_droits) + " " + (e.projet_professionnel or "")
            _etab = _extraire_nom_etablissement(_texte_e_local)
            if _etab:
                _mention = f"Démarche active initiée auprès de l'établissement : {_etab}"
                if not e.projet_professionnel:
                    e.projet_professionnel = _mention
                elif _mention not in e.projet_professionnel:
                    e.projet_professionnel = f"{e.projet_professionnel} — {_mention}"
                logger.info(f"[RULES] Établissement ciblé ajouté : {_etab}")

        # ESAT — Case P18 4
        if e.orientation_esat:
            cases_cerfa["Case à cocher P18 4"] = True

        # Règle 2 — ESPO (pré-orientation, projet non défini) — Case P18 2
        if e.orientation_espo:
            cases_cerfa["Case à cocher P18 2"] = True

        # Entreprise adaptée — Case P18 EA
        if e.orientation_ea:
            cases_cerfa["Case à cocher P18 EA"] = True

        # Emploi accompagné — Case P18 6
        if e.emploi_accompagne:
            cases_cerfa["Case à cocher P18 6"] = True

        # CMI
        if e.cmi_priorite:
            cases_cerfa["Case à cocher CMI priorité"] = True
        if e.cmi_stationnement:
            cases_cerfa["Case à cocher CMI stationnement"] = True

    # ── Section F — Aidant familial (déclencheur P19-P20) ────────────────────
    if dossier.section_f.aidant.a_un_aidant:
        cases_cerfa["_aidant_present"] = True   # signal pour cerfa_filler
    else:
        cases_cerfa["_aidant_present"] = False  # pages 19-20 vides

    # ── Métadonnée conflit d'autodétermination (consommée par cerfa_filler) ──
    if conflit:
        import dataclasses
        cases_cerfa["_autodetermination_conflict"] = dataclasses.asdict(conflit)
    else:
        cases_cerfa["_autodetermination_conflict"] = None

    return cases_cerfa
