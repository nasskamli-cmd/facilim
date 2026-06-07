"""
app/engines/facilim_prod.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━
FACILIM PROD — Orchestrateur unique

Point d'entrée unique qui orchestre TOUS les moteurs Facilim
dans l'ordre optimal et produit le cockpit professionnel complet.

Pipeline :
  synthese_json
    → evidence_engine         (preuves traçables)
    → completeness_engine     (score complétude)
    → refusal_risk_engine     (risques de refus)
    → cdaph_strategy_engine   (stratégie CDAPH)
    → eligibilite_droits      (compatibilité 22 droits)
    → strategie_dossier       (droits oubliés, urgences)
    → human_validation        (tableau validation)
    → pre_submission          (GO/GO_RISQUES/NO_GO)
    → action_plan             (plan d'action priorisé)
    → parcours                (feuille de route)
    → cerfa_gate              (verrou sécurité)
    → field_mapper            (CERFA fields)
    → audit_trail             (journal audit)
    → cockpit professionnel   (écran unique)
    → rapports (4 formats)

Usage :
  from app.engines.facilim_prod import analyser_dossier_complet
  resultat = analyser_dossier_complet(donnees, profil_mdph="adulte")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("facilim.prod")


# ─────────────────────────────────────────────────────────────────────────────
# RÉSULTAT COMPLET
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ResultatFacilimProd:
    """Résultat complet de l'analyse Facilim PROD."""

    # Métadonnées
    dossier_id:             str
    profil_mdph:            str
    duree_ms:               int
    timestamp:              str

    # Moteurs de fond
    graphe_preuves:         Any     # EvidenceGraph
    completude:             Any     # RapportCompletude
    risques:                Any     # RapportRisques
    rapport_cdaph:          Any     # RapportCDAPH
    eligibilite:            Any     # ResultatEligibiliteComplete
    strategie:              Any     # StrategieDossier
    tableau_validation:     Any     # TableauValidation
    decision_presoumission: Any     # DecisionPreSoumission

    # Plan d'action et parcours
    plan_action:            Any     # TableauPriorisation
    parcours:               Any     # PlanParcours

    # Production CERFA
    gate_cerfa:             Any     # ResultatGate
    field_map:              dict    # sortie field_mapper
    journal_audit:          Any     # JournalAudit

    # Interface professionnelle
    cockpit:                Any     # CockpitProfessionnel
    rapports:               Any     # SuiteRapports

    # Scores synthèse
    score_completude:       int
    score_solidite:         int
    decision_depot:         str     # GO | GO_AVEC_RISQUES | NO_GO
    pret_cerfa:             bool

    def cockpit_text(self) -> str:
        return self.cockpit.dashboard_text() if self.cockpit else "(cockpit non disponible)"

    def to_summary(self) -> dict:
        return {
            "dossier_id":       self.dossier_id,
            "profil_mdph":      self.profil_mdph,
            "duree_ms":         self.duree_ms,
            "score_completude": self.score_completude,
            "score_solidite":   self.score_solidite,
            "decision_depot":   self.decision_depot,
            "pret_cerfa":       self.pret_cerfa,
            "nb_preuves":       self.graphe_preuves.nb_preuves_total if self.graphe_preuves else 0,
            "nb_actions":       len(self.plan_action.actions_triees) if self.plan_action else 0,
            "gate_autorise":    self.gate_cerfa.autorisation if self.gate_cerfa else False,
            "nb_droits_omis":   len(self.strategie.droits_omis) if self.strategie else 0,
        }

    def cockpit_professionnel(self) -> dict:
        """
        FACILIM PROD-1 — Objet COCKPIT unique consolidé pour le professionnel.

        Rassemble en une seule structure, sans duplication ni nouvelle logique :
          complétude · solidité · risques de refus · droits détectés ·
          droits oubliés · questions ROI · pièces prioritaires · plan d'action ·
          validation humaine · décision GO / GO_AVEC_RISQUES / NO_GO.

        Sérialisation entièrement défensive : ne lève jamais d'exception
        (chaque sous-bloc retombe sur une valeur vide en cas d'erreur).
        """
        def _safe(fn, default):
            try:
                return fn()
            except Exception:
                return default

        blocs = _safe(lambda: self.cockpit.to_dict(), {})

        return {
            "dossier_id":          self.dossier_id,
            "profil_mdph":         self.profil_mdph,
            "genere_le":           self.timestamp,
            "duree_ms":            self.duree_ms,

            # Scores
            "score_completude":    self.score_completude,
            "score_solidite":      self.score_solidite,
            "niveau":              blocs.get("niveau", ""),

            # Décision
            "decision":            self.decision_depot,   # GO | GO_AVEC_RISQUES | NO_GO
            "pret_cerfa":          self.pret_cerfa,

            # Forces / faiblesses
            "forces":              blocs.get("forces", []),
            "faiblesses":          blocs.get("faiblesses", []),

            # Risques de refus
            "risques_refus":       _safe(lambda: self.risques.to_dict(), {}),

            # Droits détectés (solides + fragiles) et droits oubliés
            "droits_detectes":     (blocs.get("droits_solides", []) + blocs.get("droits_fragiles", [])),
            "droits_oublies":      _safe(lambda: self.strategie.to_dict().get("droits_omis", []), []),

            # Questions à fort levier (ROI)
            "questions_roi":       blocs.get("questions", []),

            # Pièces prioritaires
            "pieces_prioritaires": blocs.get("pieces", []),

            # Plan d'action priorisé (10 premières actions, triées par ROI)
            "plan_action":         _safe(lambda: [a.to_dict() for a in self.plan_action.actions_triees[:10]], []),

            # Validation humaine
            "validation_humaine":  blocs.get("validation", []),
            "nb_en_attente":       blocs.get("nb_attente", 0),

            # Verrou d'export
            "gate_export":         _safe(lambda: self.gate_cerfa.to_dict(), {}),

            # Résumé + rendu texte (pour affichage direct)
            "resume":              blocs.get("resume", ""),
            "cockpit_texte":       _safe(lambda: self.cockpit.dashboard_text(), ""),
        }


# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATEUR
# ─────────────────────────────────────────────────────────────────────────────

def analyser_dossier_complet(
    donnees: dict[str, Any],
    profil_mdph: str = "adulte",
    profil_handicap: str = "",
    dossier_id: str = "",
    generer_cerfa: bool = True,
) -> ResultatFacilimProd:
    """
    Orchestrateur FACILIM PROD — analyse complète d'un dossier.

    Exécute tous les moteurs dans l'ordre optimal.
    Retourne un résultat unique avec toutes les analyses.

    Args:
        donnees:        synthese_json du dossier
        profil_mdph:    "adulte" | "enfant" | "protege" | "mixte"
        profil_handicap: optionnel — "tsa" | "psychique" | etc.
        dossier_id:     identifiant unique (généré si absent)
        generer_cerfa:  True → inclure field_mapper + audit

    Returns:
        ResultatFacilimProd — résultat complet
    """
    t0 = time.time()
    now = datetime.now(timezone.utc).isoformat()

    if not dossier_id:
        nom = str(donnees.get("nom_prenom", "inconnu")).replace(" ", "_")[:15]
        dossier_id = f"{nom}_{datetime.now().strftime('%H%M%S')}"

    logger.info(f"FACILIM PROD — Dossier {dossier_id} | Profil {profil_mdph}")

    # Résultats partiels (None si moteur échoue)
    graphe_preuves = completude = risques = None
    rapport_cdaph = eligibilite = strategie = None
    tableau_validation = decision_presoumission = None
    plan_action = parcours_r = None
    gate_cerfa = None
    field_map: dict = {}
    journal_audit = None
    cockpit = None
    rapports = None

    # ── 1. Evidence Engine ──────────────────────────────────────────────────
    try:
        from app.engines.evidence_engine import construire_graphe_preuves
        graphe_preuves = construire_graphe_preuves(donnees, profil_mdph)
    except Exception as e:
        logger.warning(f"evidence_engine: {e}")

    # ── 2. Complétude ───────────────────────────────────────────────────────
    try:
        from app.engines.completeness_engine import evaluer_completude
        completude = evaluer_completude(donnees, profil_mdph)
    except Exception as e:
        logger.warning(f"completeness_engine: {e}")

    # ── 3. Risques de refus ─────────────────────────────────────────────────
    try:
        from app.engines.refusal_risk_engine import evaluer_risques_refus
        risques = evaluer_risques_refus(donnees, profil_mdph)
    except Exception as e:
        logger.warning(f"refusal_risk_engine: {e}")

    # ── 4. Stratégie CDAPH ──────────────────────────────────────────────────
    try:
        from app.engines.cdaph_strategy_engine import analyser_strategie_cdaph
        rapport_cdaph = analyser_strategie_cdaph(donnees, profil_mdph, profil_handicap)
    except Exception as e:
        logger.warning(f"cdaph_strategy_engine: {e}")

    # ── 5. Éligibilité 22 droits ────────────────────────────────────────────
    try:
        from app.engines.eligibilite_droits_engine import analyser_eligibilite
        eligibilite = analyser_eligibilite(donnees, profil_mdph, profil_handicap)
    except Exception as e:
        logger.warning(f"eligibilite_droits_engine: {e}")

    # ── 6. Stratégie dossier ────────────────────────────────────────────────
    try:
        from app.engines.strategie_dossier_engine import analyser_strategie
        strategie = analyser_strategie(donnees, profil_mdph, profil_handicap)
    except Exception as e:
        logger.warning(f"strategie_dossier_engine: {e}")

    # ── 7. Validation humaine ───────────────────────────────────────────────
    try:
        from app.engines.human_validation_engine import creer_tableau_validation
        tableau_validation = creer_tableau_validation(donnees, profil_mdph, profil_handicap)
    except Exception as e:
        logger.warning(f"human_validation_engine: {e}")

    # ── 8. Pré-soumission ───────────────────────────────────────────────────
    try:
        from app.engines.pre_submission_engine import pre_valider_dossier
        decision_presoumission = pre_valider_dossier(donnees, profil_mdph, profil_handicap)
    except Exception as e:
        logger.warning(f"pre_submission_engine: {e}")

    # ── 9. Plan d'action ────────────────────────────────────────────────────
    try:
        from app.engines.action_plan_engine import generer_plan_action
        plan_action = generer_plan_action(donnees, profil_mdph, profil_handicap)
    except Exception as e:
        logger.warning(f"action_plan_engine: {e}")

    # ── 10. Parcours ─────────────────────────────────────────────────────────
    try:
        if plan_action:
            from app.engines.parcours_engine import construire_parcours
            parcours_r = construire_parcours(plan_action)
    except Exception as e:
        logger.warning(f"parcours_engine: {e}")

    # ── 11. Gate CERFA ───────────────────────────────────────────────────────
    try:
        from app.engines.cerfa_gate_engine import verifier_gate_cerfa
        gate_cerfa = verifier_gate_cerfa(
            donnees, tableau_validation, decision_presoumission, profil_mdph
        )
    except Exception as e:
        logger.warning(f"cerfa_gate_engine: {e}")

    # ── 12. Field Mapper (CERFA) ─────────────────────────────────────────────
    if generer_cerfa:
        try:
            from app.engines.pdf.field_mapper import build_field_map
            field_map = build_field_map(donnees, profil_mdph)
        except Exception as e:
            logger.warning(f"field_mapper: {e}")

    # ── 13. Journal d'audit ──────────────────────────────────────────────────
    if generer_cerfa:
        try:
            from app.engines.audit_trail_engine import creer_journal_audit
            journal_audit = creer_journal_audit(
                donnees, field_map, profil_mdph,
                tableau_validation, graphe_preuves, dossier_id,
            )
        except Exception as e:
            logger.warning(f"audit_trail_engine: {e}")

    # ── 14. Cockpit professionnel ────────────────────────────────────────────
    try:
        from app.engines.professional_cockpit_engine import generer_cockpit
        cockpit = generer_cockpit(donnees, profil_mdph, profil_handicap)
    except Exception as e:
        logger.warning(f"professional_cockpit_engine: {e}")

    # ── 15. Rapports (4 formats) ─────────────────────────────────────────────
    try:
        if cockpit:
            from app.engines.pro_report_engine import generer_rapports
            rapports = generer_rapports(cockpit, donnees)
    except Exception as e:
        logger.warning(f"pro_report_engine: {e}")

    # ── Synthèse ─────────────────────────────────────────────────────────────
    score_completude = completude.score_global if completude else 0
    score_solidite   = rapport_cdaph.score_solidite if rapport_cdaph else 0
    decision_depot   = decision_presoumission.decision if decision_presoumission else "INCONNU"
    pret_cerfa       = gate_cerfa.autorisation if gate_cerfa else False

    duree_ms = round((time.time() - t0) * 1000)
    logger.info(
        f"FACILIM PROD terminé — {dossier_id} | "
        f"complétude={score_completude}% | solidité={score_solidite} | "
        f"décision={decision_depot} | cerfa={'OK' if pret_cerfa else 'BLOQUÉ'} | "
        f"{duree_ms}ms"
    )

    return ResultatFacilimProd(
        dossier_id=dossier_id,
        profil_mdph=profil_mdph,
        duree_ms=duree_ms,
        timestamp=now,
        graphe_preuves=graphe_preuves,
        completude=completude,
        risques=risques,
        rapport_cdaph=rapport_cdaph,
        eligibilite=eligibilite,
        strategie=strategie,
        tableau_validation=tableau_validation,
        decision_presoumission=decision_presoumission,
        plan_action=plan_action,
        parcours=parcours_r,
        gate_cerfa=gate_cerfa,
        field_map=field_map,
        journal_audit=journal_audit,
        cockpit=cockpit,
        rapports=rapports,
        score_completude=score_completude,
        score_solidite=score_solidite,
        decision_depot=decision_depot,
        pret_cerfa=pret_cerfa,
    )


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE DE CÂBLAGE (FACILIM PROD-1)
# ─────────────────────────────────────────────────────────────────────────────

def run(
    donnees: dict[str, Any],
    profil_mdph: str = "adulte",
    profil_handicap: str = "",
    dossier_id: str = "",
    generer_cerfa: bool = False,
) -> ResultatFacilimProd:
    """
    Point d'entrée unique demandé par le workflow : ``facilim_prod.run(donnees)``.

    Alias direct de :func:`analyser_dossier_complet`. Aucune logique ajoutée —
    sert uniquement à câbler la chaîne FACILIM 60→100 dans le parcours réel.

    Note : ``generer_cerfa`` vaut False par défaut ici car le CERFA est déjà
    produit par le pipeline existant ; le verrou (gate) et le cockpit sont
    calculés dans tous les cas.
    """
    # FIX VAGUE 1 : normalise les champs structurés (droits.* → droits_demandes)
    # pour que cockpit / moteurs (qui lisent droits_demandes) en bénéficient.
    try:
        from app.services.collecte_schema import normaliser_collecte
        donnees = normaliser_collecte(donnees)
    except Exception:
        pass
    return analyser_dossier_complet(
        donnees,
        profil_mdph=profil_mdph,
        profil_handicap=profil_handicap,
        dossier_id=dossier_id,
        generer_cerfa=generer_cerfa,
    )
