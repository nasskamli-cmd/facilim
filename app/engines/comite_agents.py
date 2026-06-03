"""
app/engines/comite_agents.py — Comité d'agents experts Facilim.

9 agents spécialisés analysent le dossier MDPH avant transmission.
Principes absolus :
  - Lecture seule : aucun agent ne modifie jamais synthese_json ni le CERFA.
  - Non décisionnaires : ils détectent, alertent, recommandent.
  - Jamais bloquants sur score seul.
  - Python pur : pas d'appel LLM (règles statiques, reproductibles, testables).
  - Extensibles : une couche IA optionnelle peut être ajoutée en wrapping futur.

Alertes bloquantes (3 uniquement) :
  B1 — consentement RGPD absent
  B2 — certificat médical absent
  B3 — justificatif identité absent

B4 (validation usager) et B5 (validation professionnel) sont vérifiés
uniquement à l'envoi du CERFA, pas dans le comité.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("facilim.comite_agents")


# ── Structures de données ─────────────────────────────────────────────────────

@dataclass
class AlerteAgent:
    agent:    str            # ex. "Agent 8 — Qualité MDPH"
    type:     str            # "bloquant" | "avertissement" | "info"
    champ:    str | None     # champ CERFA concerné si applicable
    message:  str            # message lisible par le professionnel
    source:   str            # "synthese_json" | "cerfa_validations" | "db" | "regle"


@dataclass
class RapportComite:
    score:               int = 100
    alertes_bloquantes:  list[AlerteAgent] = field(default_factory=list)
    alertes_mineures:    list[AlerteAgent] = field(default_factory=list)
    pieces_manquantes:   list[str]         = field(default_factory=list)
    droits_potentiels:   list[str]         = field(default_factory=list)  # jamais auto-ajoutés
    recommandations:     list[str]         = field(default_factory=list)
    agents_actives:      list[str]         = field(default_factory=list)
    bloquant:            bool              = False  # True si alerte bloquante explicite


# ── Constantes ────────────────────────────────────────────────────────────────

_PENALITE_BLOQUANT     = 30
_PENALITE_AVERTISSEMENT = 5
_PENALITE_PIECE        = 10


# ── Orchestration principale ──────────────────────────────────────────────────

def executer_comite_agents(
    donnees: dict[str, Any],
    profil: str,
    dossier_id: str,
    db: Any,
    mode: str = "pre_validation",   # "pre_validation" | "post_validation"
) -> RapportComite:
    """
    Exécute les agents activés selon le profil et le mode.
    Retourne un RapportComite complet.
    Ne modifie RIEN — lecture seule.

    Args:
        donnees    : synthese_json du dossier (copie — jamais modifiée)
        profil     : "enfant" | "mixte" | "adulte" | "protege" | "identification"
        dossier_id : UUID du dossier
        db         : connexion DB (lecture seule dans ce module)
        mode       : "pre_validation" (avant validation usager)
                     "post_validation" (au moment de l'envoi)
    """
    rapport = RapportComite()

    # Agents toujours exécutés
    _executer_agent(rapport, "Agent 8 — Qualité MDPH",
                    _agent_qualite_mdph, donnees, db, dossier_id)
    _executer_agent(rapport, "Agent 9 — Juridique/RGPD",
                    _agent_juridique_rgpd, donnees, db, dossier_id, mode=mode)

    # Agents conditionnels selon profil
    age = _extraire_age(donnees)

    if age is not None and age < 16:
        _executer_agent(rapport, "Agent 1 — Enfance",
                        _agent_enfance, donnees, db, dossier_id)

    if age is not None and 16 <= age <= 25:
        _executer_agent(rapport, "Agent 2 — Jeunes 16-25",
                        _agent_jeunes, donnees, db, dossier_id)

    if age is not None and age > 25:
        _executer_agent(rapport, "Agent 3 — Handicap adulte",
                        _agent_adulte, donnees, db, dossier_id)

    droits = (donnees.get("droits_demandes") or "").upper()
    statut = (donnees.get("statut_emploi") or "").lower()
    if any(t in droits for t in ("RQTH", "ESRP", "ESAT")) or \
       any(w in statut for w in ("emploi", "formation", "france travail")):
        _executer_agent(rapport, "Agent 4 — Emploi/insertion",
                        _agent_emploi, donnees, db, dossier_id)

    if "PCH" in droits:
        _executer_agent(rapport, "Agent 5 — PCH/compensation",
                        _agent_pch, donnees, db, dossier_id)

    protection = (donnees.get("protection_juridique") or "").lower()
    if any(t in protection for t in ("tutelle", "curatelle", "habilitation")):
        _executer_agent(rapport, "Agent 6 — Protection juridique",
                        _agent_protection_juridique, donnees, db, dossier_id)

    orientation = (donnees.get("souhait_orientation_usager") or "").upper()
    structures_esms = ("SAMSAH", "SAVS", "MAS", "FAM", "ESAT", "ESRP", "IME", "PCPE")
    if any(s in orientation or s in droits for s in structures_esms):
        _executer_agent(rapport, "Agent 7 — Médico-social",
                        _agent_medico_social, donnees, db, dossier_id)

    # Calcul du score final
    score = 100
    score -= len(rapport.alertes_bloquantes) * _PENALITE_BLOQUANT
    score -= len(rapport.alertes_mineures)   * _PENALITE_AVERTISSEMENT
    score -= len(rapport.pieces_manquantes)  * _PENALITE_PIECE
    rapport.score   = max(0, score)
    rapport.bloquant = len(rapport.alertes_bloquantes) > 0

    logger.info(
        "[COMITE] Dossier=%s | profil=%s | score=%d | bloquant=%s | agents=%s",
        dossier_id[:8], profil, rapport.score, rapport.bloquant,
        ", ".join(rapport.agents_actives),
    )
    return rapport


def _executer_agent(rapport: RapportComite, nom: str, fn, *args, **kwargs) -> None:
    """Exécute un agent, capture les exceptions, ajoute au rapport."""
    try:
        alertes = fn(*args, **kwargs)
        for a in alertes:
            if a.type == "bloquant":
                rapport.alertes_bloquantes.append(a)
            elif a.type == "avertissement":
                rapport.alertes_mineures.append(a)
        rapport.agents_actives.append(nom)
    except Exception as e:
        logger.warning("[COMITE] Agent %s échoué : %s", nom, e)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extraire_age(donnees: dict) -> int | None:
    """Extrait l'âge depuis date_naissance si disponible."""
    ddn = donnees.get("date_naissance")
    if not ddn:
        return None
    try:
        from app.engines.profile_engine import _parser_date_naissance
        from datetime import date
        d = _parser_date_naissance(str(ddn))
        if d:
            return (date.today() - d).days // 365
    except Exception:
        pass
    return None


def _alerte(agent, type_, champ, message, source="synthese_json") -> AlerteAgent:
    return AlerteAgent(agent=agent, type=type_, champ=champ, message=message, source=source)


# ── Agent 1 — Enfance ─────────────────────────────────────────────────────────

def _agent_enfance(donnees, db, dossier_id) -> list[AlerteAgent]:
    a = []
    nom = "Agent 1 — Enfance"
    if not (donnees.get("representant_legal_nom") or donnees.get("nom_parent")):
        a.append(_alerte(nom, "bloquant", "representant_legal",
                         "Représentant légal non identifié — obligatoire pour un dossier enfant"))
    if not donnees.get("situation_scolaire"):
        a.append(_alerte(nom, "avertissement", "situation_scolaire",
                         "Situation scolaire non renseignée"))
    droits = (donnees.get("droits_demandes") or "").upper()
    if "AEEH" in droits:
        age = _extraire_age(donnees)
        if age is not None and age > 20:
            a.append(_alerte(nom, "bloquant", "droits_demandes",
                             f"AEEH demandée pour une personne de {age} ans — incohérence (limite 20 ans)"))
    return a


# ── Agent 2 — Jeunes 16-25 ────────────────────────────────────────────────────

def _agent_jeunes(donnees, db, dossier_id) -> list[AlerteAgent]:
    a = []
    nom = "Agent 2 — Jeunes 16-25"
    if not donnees.get("situation_scolaire") and not donnees.get("statut_emploi"):
        a.append(_alerte(nom, "avertissement", "situation_scolaire",
                         "Ni situation scolaire ni situation professionnelle renseignée — profil mixte à préciser"))
    if not donnees.get("souhait_orientation_usager"):
        a.append(_alerte(nom, "avertissement", "projet_orientation",
                         "Projet d'orientation / de vie non renseigné — fortement recommandé pour profil 16-25"))
    return a


# ── Agent 3 — Handicap adulte ─────────────────────────────────────────────────

def _agent_adulte(donnees, db, dossier_id) -> list[AlerteAgent]:
    a = []
    nom = "Agent 3 — Handicap adulte"
    if not donnees.get("impact_quotidien"):
        a.append(_alerte(nom, "avertissement", "impact_quotidien",
                         "Impact du handicap sur la vie quotidienne non renseigné"))
    if not donnees.get("souhait_orientation_usager") and not donnees.get("projet_professionnel"):
        a.append(_alerte(nom, "avertissement", "projet_orientation",
                         "Projet de vie / professionnel non renseigné"))
    return a


# ── Agent 4 — Emploi / insertion ──────────────────────────────────────────────

def _agent_emploi(donnees, db, dossier_id) -> list[AlerteAgent]:
    a = []
    nom = "Agent 4 — Emploi/insertion"
    droits = (donnees.get("droits_demandes") or "").upper()
    if "RQTH" in droits and not donnees.get("statut_emploi"):
        a.append(_alerte(nom, "avertissement", "statut_emploi",
                         "RQTH demandée sans situation professionnelle renseignée"))
    if donnees.get("accident_travail") and not donnees.get("a_deja_travaille"):
        a.append(_alerte(nom, "avertissement", "a_deja_travaille",
                         "Accident du travail signalé mais 'a déjà travaillé' non confirmé"))
    # Droits potentiels — jamais auto-ajoutés, info uniquement
    if "RQTH" in droits and donnees.get("inscrit_pole_emploi"):
        a.append(_alerte(nom, "info", None,
                         "Droit potentiel : ORP (Orientation et Reclassement Professionnel) — à évaluer avec le bénéficiaire",
                         source="regle"))
    return a


# ── Agent 5 — PCH / compensation ─────────────────────────────────────────────

def _agent_pch(donnees, db, dossier_id) -> list[AlerteAgent]:
    a = []
    nom = "Agent 5 — PCH/compensation"
    if not donnees.get("impact_quotidien"):
        a.append(_alerte(nom, "avertissement", "impact_quotidien",
                         "PCH demandée mais impact quotidien non détaillé — pièces justificatives à vérifier"))
    if not (donnees.get("adresse_complete") or donnees.get("type_logement")):
        a.append(_alerte(nom, "avertissement", "logement",
                         "Situation de logement non renseignée — pertinente pour PCH aménagement"))
    return a


# ── Agent 6 — Protection juridique ───────────────────────────────────────────

def _agent_protection_juridique(donnees, db, dossier_id) -> list[AlerteAgent]:
    a = []
    nom = "Agent 6 — Protection juridique"
    if not donnees.get("representant_legal_nom") and not donnees.get("nom_parent"):
        a.append(_alerte(nom, "bloquant", "representant_legal",
                         "Mesure de protection détectée mais identité du représentant non renseignée"))
    return a


# ── Agent 7 — Médico-social ───────────────────────────────────────────────────

def _agent_medico_social(donnees, db, dossier_id) -> list[AlerteAgent]:
    a = []
    nom = "Agent 7 — Médico-social"
    if not donnees.get("souhait_orientation_usager"):
        a.append(_alerte(nom, "avertissement", "orientation",
                         "Orientation médico-sociale demandée mais souhait de la personne non renseigné"))
    return a


# ── Agent 8 — Qualité MDPH (toujours) ────────────────────────────────────────

def _agent_qualite_mdph(donnees, db, dossier_id) -> list[AlerteAgent]:
    a = []
    nom = "Agent 8 — Qualité MDPH"

    # B1 — Consentement (base de données)
    try:
        usager_row = db.execute(
            "SELECT usager_id FROM sessions_whatsapp WHERE dossier_id = ? LIMIT 1",
            (dossier_id,)
        ).fetchone()
        if usager_row:
            consent = db.execute(
                "SELECT id FROM consentements WHERE usager_id = ? AND retire_le IS NULL LIMIT 1",
                (usager_row["usager_id"],)
            ).fetchone()
            if not consent:
                a.append(_alerte(nom, "bloquant", "consentement",
                                 "Consentement RGPD non enregistré pour cet usager", source="db"))
    except Exception:
        a.append(_alerte(nom, "avertissement", "consentement",
                         "Impossible de vérifier le consentement RGPD", source="db"))

    # B2 — Certificat médical
    if not donnees.get("certificat_medical_recu"):
        a.append(_alerte(nom, "bloquant", "certificat_medical",
                         "Certificat médical (formulaire 13878 ou certificat médecin) non joint"))
        _piece_manquante = "Certificat médical obligatoire"
    else:
        _piece_manquante = None

    # B3 — Justificatif identité
    if not donnees.get("justificatif_identite"):
        a.append(_alerte(nom, "bloquant", "justificatif_identite",
                         "Justificatif d'identité non joint"))

    # Nom / prénom
    if not donnees.get("nom_prenom"):
        a.append(_alerte(nom, "bloquant", "nom_prenom",
                         "Nom et prénom non renseignés"))

    # Date de naissance
    if not donnees.get("date_naissance"):
        a.append(_alerte(nom, "bloquant", "date_naissance",
                         "Date de naissance non renseignée — indispensable pour calculer le profil"))

    # Droits demandés
    if not donnees.get("droits_demandes"):
        a.append(_alerte(nom, "bloquant", "droits_demandes",
                         "Aucun droit demandé dans le dossier"))

    # Projet de vie (avertissement)
    if not donnees.get("souhait_orientation_usager") and not donnees.get("projet_professionnel"):
        a.append(_alerte(nom, "avertissement", "projet_de_vie",
                         "Projet de vie non renseigné — fortement conseillé pour l'instruction MDPH"))

    # Contradiction aide humaine
    impact = (donnees.get("impact_quotidien") or "").lower()
    if any(w in impact for w in ["pas besoin", "pas d'aide", "sans aide", "autonome"]) \
       and donnees.get("besoins_aide_humaine"):
        a.append(_alerte(nom, "avertissement", "besoins_aide_humaine",
                         "Contradiction : la personne déclare ne pas avoir besoin d'aide humaine "
                         "mais la case 'aide humaine' est cochée — à vérifier"))

    return a


# ── Agent 9 — Juridique / RGPD (toujours, deux modes) ────────────────────────

def _agent_juridique_rgpd(donnees, db, dossier_id, mode="pre_validation") -> list[AlerteAgent]:
    """
    Mode "pre_validation" : vérifie consentement, audit, version, hash.
    Mode "post_validation" : vérifie en plus validation usager et cohérence version/hash.

    B4 (validation usager) et B5 (validation pro) ne sont PAS vérifiés ici.
    Ils sont contrôlés uniquement à l'envoi du CERFA dans envoyer_cerfa().
    """
    a = []
    nom = "Agent 9 — Juridique/RGPD"

    # Présence du journal d'audit pour ce dossier
    try:
        audit = db.execute(
            "SELECT id FROM cerfa_audit_log WHERE dossier_id = ? LIMIT 1", (dossier_id,)
        ).fetchone()
        if not audit:
            a.append(_alerte(nom, "avertissement", "audit_log",
                             "Aucune entrée dans le journal d'audit pour ce dossier", source="db"))
    except Exception:
        pass

    # Version présente
    try:
        dossier_row = db.execute(
            "SELECT version FROM dossiers WHERE id = ?", (dossier_id,)
        ).fetchone()
        if dossier_row and not dossier_row["version"]:
            a.append(_alerte(nom, "avertissement", "version",
                             "Numéro de version du dossier absent — versionning non initialisé", source="db"))
    except Exception:
        pass

    if mode == "post_validation":
        # Cohérence version entre dernière validation pro et version actuelle
        try:
            derniere_val = db.execute(
                """SELECT dossier_version FROM cerfa_validations
                   WHERE dossier_id = ? AND type_validation = 'professionnel'
                   AND reponse_usager = 'OUI'
                   ORDER BY validated_at DESC LIMIT 1""",
                (dossier_id,)
            ).fetchone()
            version_actuelle = db.execute(
                "SELECT version FROM dossiers WHERE id = ?", (dossier_id,)
            ).fetchone()
            if derniere_val and version_actuelle:
                if derniere_val["dossier_version"] != version_actuelle["version"]:
                    a.append(_alerte(nom, "avertissement", "version",
                                     "Le dossier a été modifié depuis la validation professionnelle — "
                                     "vérifier que les modifications sont mineures",
                                     source="db"))
        except Exception:
            pass

    return a
