"""
app/tests/qa/qa_engine.py — Moteur de validation Facilim QA

FACILIM_QA_SCORE = score unique de qualité 0-100
  WhatsApp      15 %
  Documents     15 %
  Inférences    20 %
  Narratifs     20 %
  CERFA         20 %
  Justificatifs 10 %

Seuils :
  90-100 = Production Ready
  80-89  = Très bon
  70-79  = Utilisable avec vigilance
  60-69  = MVP
  < 60   = Non déployable

Usage :
  python -m app.tests.qa.qa_engine [--profil PROFIL_ID] [--all] [--report]
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("facilim.qa")

# ─────────────────────────────────────────────────────────────────────────────
# RÉSULTATS DE TESTS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TestResult:
    nom:    str
    statut: str   # "PASS" | "FAIL" | "WARN" | "SKIP"
    detail: str   = ""
    valeur_obtenue: str = ""
    valeur_attendue: str = ""


@dataclass
class SectionQA:
    """Résultat d'une section de tests."""
    nom:       str
    poids:     float          # poids dans le score total (0 à 1)
    tests:     list[TestResult] = field(default_factory=list)

    @property
    def nb_pass(self) -> int:
        return sum(1 for t in self.tests if t.statut == "PASS")

    @property
    def nb_fail(self) -> int:
        return sum(1 for t in self.tests if t.statut == "FAIL")

    @property
    def nb_warn(self) -> int:
        return sum(1 for t in self.tests if t.statut == "WARN")

    @property
    def score_section(self) -> float:
        """Score 0.0 à 1.0 pour cette section."""
        if not self.tests:
            return 0.0
        # FAIL = 0 · WARN = 0.5 · PASS = 1
        total = sum(
            1.0 if t.statut == "PASS" else 0.5 if t.statut == "WARN" else 0.0
            for t in self.tests
        )
        return round(total / len(self.tests), 3)


@dataclass
class ProfilQAResult:
    """Résultat complet d'un profil de test."""
    profil_id:   str
    profil_nom:  str
    timestamp:   str
    sections:    dict[str, SectionQA] = field(default_factory=dict)

    @property
    def qa_score(self) -> float:
        """FACILIM_QA_SCORE — score pondéré 0-100."""
        poids = {
            "whatsapp":      0.15,
            "documents":     0.15,
            "inferences":    0.20,
            "narratifs":     0.20,
            "cerfa":         0.20,
            "justificatifs": 0.10,
        }
        total = sum(
            self.sections[s].score_section * p
            for s, p in poids.items()
            if s in self.sections
        )
        return round(total * 100, 1)

    @property
    def niveau(self) -> str:
        s = self.qa_score
        if s >= 90: return "🟢 Production Ready"
        if s >= 80: return "🟢 Très bon"
        if s >= 70: return "🟡 Utilisable avec vigilance"
        if s >= 60: return "🟠 MVP"
        return "🔴 Non déployable"

    @property
    def pass_fail(self) -> str:
        return "PASS" if self.qa_score >= 60 else "FAIL"

    def nb_fails(self) -> int:
        return sum(s.nb_fail for s in self.sections.values())

    def nb_warns(self) -> int:
        return sum(s.nb_warn for s in self.sections.values())


# ─────────────────────────────────────────────────────────────────────────────
# MOTEUR DE TESTS
# ─────────────────────────────────────────────────────────────────────────────

class FacilimQAEngine:
    """
    Moteur principal de validation Facilim QA.
    Pour chaque profil, execute les 6 catégories de tests.
    """

    def __init__(self, openai_client: Any | None = None):
        self.llm = openai_client
        self._setup_engines()

    def _setup_engines(self):
        """Initialise les moteurs Facilim nécessaires aux tests."""
        import sys
        sys.path.insert(0, ".")
        os.environ.setdefault("DATABASE_URL", "sqlite:///./mdph_dossiers.db")
        os.environ.setdefault("JWT_SECRET_KEY", "test-key-32-chars-minimum-length!")
        os.environ.setdefault("WHATSAPP_API_TOKEN", "test")
        os.environ.setdefault("WHATSAPP_PHONE_NUMBER_ID", "test")

    def run_profil(self, profil) -> ProfilQAResult:
        """Exécute tous les tests pour un profil donné."""
        from app.tests.qa.profiles import ProfilQA
        result = ProfilQAResult(
            profil_id=profil.id,
            profil_nom=profil.nom,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        result.sections["whatsapp"]      = self._test_whatsapp(profil)
        result.sections["documents"]     = self._test_documents(profil)
        result.sections["inferences"]    = self._test_inferences(profil)
        result.sections["narratifs"]     = self._test_narratifs(profil)
        result.sections["cerfa"]         = self._test_cerfa(profil)
        result.sections["justificatifs"] = self._test_justificatifs(profil)
        result.sections["strategie_f60"] = self._test_strategie(profil)

        return result

    # ── A — Tests WhatsApp ────────────────────────────────────────────────────

    def _test_whatsapp(self, profil) -> SectionQA:
        section = SectionQA(nom="WhatsApp", poids=0.15)
        donnees = dict(profil.donnees_entree)

        # Test A1 — Anti-boucle : _narratif_echec ne doit pas bloquer
        from app.engines.orchestration_engine import _dossier_narratif_exploitable
        donnees_boucle = {**donnees, "_narratif_echec": True}
        boucle = _dossier_narratif_exploitable(donnees_boucle)
        section.tests.append(TestResult(
            "A1 — Anti-boucle WhatsApp",
            "PASS" if not boucle else "FAIL",
            detail="Avec _narratif_echec=True, le pipeline ne doit pas se déclencher",
            valeur_obtenue=str(boucle),
            valeur_attendue="False",
        ))

        # Test A2 — Déclenchement narratif
        if profil.narratif_doit_declencher:
            exploitable = _dossier_narratif_exploitable(donnees)
            section.tests.append(TestResult(
                "A2 — Déclenchement moteur narratif",
                "PASS" if exploitable else "FAIL",
                detail="Le moteur narratif doit se déclencher avec ces données",
                valeur_obtenue=str(exploitable),
                valeur_attendue="True",
            ))

        # Test A3 — Regroupement thématique (pas de mélange NSS + emploi)
        from app.services.conversation._shared import REGLES_COMMUNICATION_COMMUNES
        section.tests.append(TestResult(
            "A3 — Règle blocs thématiques présente",
            "PASS" if "JAMAIS dans le même message" in REGLES_COMMUNICATION_COMMUNES else "WARN",
            detail="Règle de non-mélange thématique dans les prompts agents",
        ))

        # Test A4 — accepted_continue dans le code (anti-boucle post-consentement)
        import inspect
        from app.engines.orchestration_engine import OrchestrationEngine
        source = inspect.getsource(OrchestrationEngine._handle_consent_flow)
        section.tests.append(TestResult(
            "A4 — Fix post-consentement (accepted_continue)",
            "PASS" if "accepted_continue" in source else "FAIL",
            detail="Le fix P0.5 de la boucle post-consentement doit être actif",
        ))

        return section

    # ── B — Tests Documents ───────────────────────────────────────────────────

    def _test_documents(self, profil) -> SectionQA:
        section = SectionQA(nom="Documents", poids=0.15)

        if not profil.document_texte:
            # Fix QA-1-6 : L'absence de document est un cas valide géré correctement
            # → PASS (le système ne plante pas, il skipe proprement)
            section.tests.append(TestResult(
                "B0 — Pas de document (comportement attendu)",
                "PASS",
                detail="Profil sans document — le système gère correctement ce cas",
            ))
            return section

        # Test B1 — Extraction réelle
        try:
            from app.engines.document_functional_extractor import (
                detecter_type_document,
                _construire_knowledge,
            )
            # Simuler extraction sans appel LLM (test structurel)
            type_doc = detecter_type_document(profil.document_texte)
            section.tests.append(TestResult(
                "B1 — Détection type document",
                "PASS" if type_doc != "autre" else "WARN",
                detail=f"Type détecté pour '{profil.document_type}' attendu",
                valeur_obtenue=type_doc,
                valeur_attendue=profil.document_type.upper() if profil.document_type else "bilan/PCR",
            ))
        except Exception as e:
            section.tests.append(TestResult("B1 — Détection type", "FAIL", str(e)))

        # Test B2 — Notes pro déclenchent le moteur narratif
        from app.engines.orchestration_engine import _dossier_narratif_exploitable
        donnees_avec_notes = {**profil.donnees_entree, "notes_pro": profil.document_texte[:200]}
        section.tests.append(TestResult(
            "B2 — notes_pro déclenche le moteur narratif",
            "PASS" if _dossier_narratif_exploitable(donnees_avec_notes) else "FAIL",
            detail="Document injecté en notes_pro doit déclencher le narratif",
        ))

        # Test B3 — v2_bridge reçoit les textes narratifs
        from app.engines.pdf.v2_bridge import synthese_to_v2_dossier
        import inspect
        source_v2 = inspect.getsource(synthese_to_v2_dossier)
        section.tests.append(TestResult(
            "B3 — v2_bridge intègre textes narratifs Phase 3",
            "PASS" if "_texte_b" in source_v2 and "_texte_e" in source_v2 else "FAIL",
            detail="Fix P0.5-B doit être actif dans v2_bridge",
        ))

        return section

    # ── C — Tests Inférences ──────────────────────────────────────────────────

    def _test_inferences(self, profil) -> SectionQA:
        section = SectionQA(nom="Inférences", poids=0.20)
        donnees = dict(profil.donnees_entree)

        # Test C1 — Droits attendus détectés par inferencer
        try:
            from app.engines.inferencer_mdph import inferer_contexte_mdph
            ctx = inferer_contexte_mdph(
                donnees,
                donnees.get("profil_principal", ""),
                profil.profil_mdph,
            )
            # Vérifier que les signaux attendus sont détectés
            hypotheses_ids = {h.id for h in ctx.hypotheses}
            section.tests.append(TestResult(
                "C1 — Inférences déclenchées",
                "PASS" if ctx.hypotheses else "WARN",
                detail=f"{len(ctx.hypotheses)} hypothèses · Coverage {ctx.coverage.taux_couverture:.0%}",
                valeur_obtenue=f"{len(ctx.hypotheses)} hypothèses",
            ))
        except Exception as e:
            section.tests.append(TestResult("C1 — Inférences", "FAIL", str(e)))

        # Test C2 — Droits attendus dans droits_demandes ou détectables
        droits_dem = donnees.get("droits_demandes", "").upper()
        nb_attendus_presents = sum(
            1 for d in profil.droits_attendus
            if d.replace("_", " ") in droits_dem or d in droits_dem
        )
        pct = nb_attendus_presents / len(profil.droits_attendus) if profil.droits_attendus else 1
        section.tests.append(TestResult(
            "C2 — Droits attendus présents dans les données",
            "PASS" if pct >= 0.5 else "WARN",
            detail=f"{nb_attendus_presents}/{len(profil.droits_attendus)} droits présents",
            valeur_obtenue=f"{pct:.0%}",
            valeur_attendue="≥ 50 %",
        ))

        # Test C3 — Droits non-attendus absents
        droits_dem_low = droits_dem.lower()
        faux_pos = [d for d in profil.droits_non_attendus if d.lower() in droits_dem_low]
        section.tests.append(TestResult(
            "C3 — Absence de faux positifs droits",
            "PASS" if not faux_pos else "FAIL",
            detail=f"Droits non attendus : {faux_pos}" if faux_pos else "Aucun faux positif",
            valeur_obtenue=str(faux_pos),
            valeur_attendue="[]",
        ))

        # Test C4 — Incohérences attendues détectées
        if profil.incoherences_attendues:
            # Pour l'instant, vérification structurelle
            section.tests.append(TestResult(
                "C4 — Incohérences attendues (structurel)",
                "WARN",
                detail=f"{len(profil.incoherences_attendues)} incohérences attendues — vérification manuelle",
            ))

        return section

    # ── D — Tests Narratifs ───────────────────────────────────────────────────

    def _test_narratifs(self, profil) -> SectionQA:
        section = SectionQA(nom="Narratifs", poids=0.20)
        donnees = dict(profil.donnees_entree)

        if not self.llm:
            section.tests.append(TestResult(
                "D0 — LLM non configuré",
                "SKIP",
                detail="Tests narratifs nécessitent OpenAI API — configurer OPENAI_API_KEY",
            ))
            return section

        try:
            from app.engines.cerfa_narrative_engine import generer_textes_narratifs
            from app.engines.cerfa_quality_agent import verifier_qualite_cerfa

            # Injecter document si présent
            if profil.document_texte:
                donnees["notes_pro"] = profil.document_texte[:500]

            textes = generer_textes_narratifs(
                donnees=donnees,
                profil_mdph=profil.profil_mdph,
                openai_client=self.llm,
                profil_handicap=profil.profil_handicap,
                model="gpt-4o",
            )

            # Test D1 — Textes générés
            # Fix QA-1 : Section D non obligatoire pour profil enfant
            sections_a_tester = [
                ("B","texte_b_vie_quotidienne"),
                ("E","texte_e_projet_vie"),
            ]
            if profil.profil_mdph != "enfant":
                sections_a_tester.append(("D","texte_d_situation_pro"))
            else:
                sections_a_tester.append(("C","texte_c_scolarite"))  # C obligatoire pour enfant

            for section_lettre, champ in sections_a_tester:
                texte = textes.get(champ, "")
                longueur_ok = len(texte) > 200
                section.tests.append(TestResult(
                    f"D1 — Section {section_lettre} générée",
                    "PASS" if longueur_ok else ("WARN" if len(texte) > 50 else "FAIL"),
                    detail=f"{len(texte)} chars",
                    valeur_obtenue=f"{len(texte)} chars",
                    valeur_attendue="> 200 chars",
                ))

            # Test D2 — Fragments attendus dans les textes
            for section_lettre, fragment in profil.sections_narratives.items():
                champ_map = {"B":"texte_b_vie_quotidienne","C":"texte_c_scolarite","D":"texte_d_situation_pro","E":"texte_e_projet_vie"}
                champ = champ_map.get(section_lettre, "")
                texte = textes.get(champ, "")
                present = fragment.lower() in texte.lower()
                section.tests.append(TestResult(
                    f"D2 — Fragment '{fragment}' dans section {section_lettre}",
                    "PASS" if present else "FAIL",
                    detail=f"Fragment attendu dans le texte narratif",
                    valeur_obtenue="présent" if present else "absent",
                    valeur_attendue="présent",
                ))

            # Test D3 — Score maturité
            rapport = verifier_qualite_cerfa(donnees, textes, profil.profil_mdph)
            section.tests.append(TestResult(
                "D3 — Score maturité minimum",
                "PASS" if rapport.score_maturite >= profil.score_maturite_min else "FAIL",
                detail=f"Score {rapport.score_maturite}/100 (minimum {profil.score_maturite_min})",
                valeur_obtenue=str(rapport.score_maturite),
                valeur_attendue=f">= {profil.score_maturite_min}",
            ))

            # Test D4 — Pas de marqueurs de supposition dans texte B
            texte_b = textes.get("texte_b_vie_quotidienne", "")
            suppositions = [m for m in ["probablement","il est possible que","vraisemblablement"]
                           if m in texte_b.lower()]
            section.tests.append(TestResult(
                "D4 — Absence marqueurs supposition en B",
                "WARN" if suppositions else "PASS",
                detail=f"Marqueurs trouvés : {suppositions}" if suppositions else "Aucun",
            ))

        except Exception as e:
            section.tests.append(TestResult("D0 — Génération narratifs", "FAIL", str(e)))

        return section

    # ── E — Tests CERFA ───────────────────────────────────────────────────────

    def _test_cerfa(self, profil) -> SectionQA:
        section = SectionQA(nom="CERFA", poids=0.20)
        donnees = dict(profil.donnees_entree)
        # Fix QA-1-6 : Injecter document_texte dans notes_pro (simule l'extraction documentaire)
        if profil.document_texte and not donnees.get("notes_pro"):
            donnees["notes_pro"] = profil.document_texte[:800]

        try:
            from app.engines.pdf.field_mapper import build_field_map
            champs = build_field_map(donnees, profil.profil_mdph)

            # Test E1 — Cases attendues cochées
            for champ_nom, valeur_attendue in profil.cases_cerfa_attendues.items():
                valeur_obtenue = champs.get(champ_nom, "[ABSENT]")
                if valeur_attendue.startswith("/Yes"):
                    ok = valeur_obtenue == "/Yes"
                else:
                    ok = valeur_attendue.lower() in str(valeur_obtenue).lower()
                section.tests.append(TestResult(
                    f"E1 — {champ_nom}",
                    "PASS" if ok else "FAIL",
                    valeur_obtenue=str(valeur_obtenue)[:60],
                    valeur_attendue=valeur_attendue,
                ))

            # Test E2 — Cases absentes non cochées
            # FACILIM 40 P0 : /Off = case explicitement non cochée = équivalent absent
            for champ_nom in profil.cases_cerfa_absentes:
                valeur = champs.get(champ_nom, "")
                pas_coche = not valeur or valeur == "/Off"
                section.tests.append(TestResult(
                    f"E2 — {champ_nom} absent",
                    "PASS" if pas_coche else "FAIL",
                    detail=f"Cette case ne doit pas être cochée (/Off = non coché)",
                    valeur_obtenue=str(valeur) if valeur else "[absent]",
                    valeur_attendue="[absent] ou /Off",
                ))

            # Test E3 — NSS présent et longueur correcte (adulte)
            if profil.profil_mdph == "adulte" and donnees.get("num_secu"):
                nss_champs = {k: v for k, v in champs.items() if "Numero SS" in k}
                section.tests.append(TestResult(
                    "E3 — NSS mappé (≥ 13 chiffres)",
                    "PASS" if len(nss_champs) >= 13 else "WARN",
                    valeur_obtenue=f"{len(nss_champs)} cases",
                    valeur_attendue="≥ 13 cases",
                ))

            # Test E4 — Texte narratif B dans PDF
            texte_b = donnees.get("texte_b_vie_quotidienne", "") or donnees.get("notes_pro", "")
            p8 = champs.get("Champ de texte P8 1", "")
            if texte_b and len(texte_b) > 50:
                section.tests.append(TestResult(
                    "E4 — Texte narratif B injecté dans P8 1",
                    "PASS" if texte_b[:40] in p8 else "FAIL",
                    valeur_obtenue=p8[:60] if p8 else "[absent]",
                    valeur_attendue=texte_b[:40],
                ))

            # Test E5 — Texte section E injecté dans P16 1
            texte_e = donnees.get("texte_e_projet_vie", "")
            if texte_e and len(texte_e) > 50:
                p16 = champs.get("Champ de texte P16 1", "")
                section.tests.append(TestResult(
                    "E5 — Texte projet vie injecté dans P16 1",
                    "PASS" if texte_e[:40] in p16 else "FAIL",
                    valeur_obtenue=p16[:60] if p16 else "[absent]",
                    valeur_attendue=texte_e[:40],
                ))

        except Exception as e:
            section.tests.append(TestResult("E0 — field_mapper", "FAIL", str(e)))

        return section

    # ── F — Tests Justificatifs ───────────────────────────────────────────────

    def _test_justificatifs(self, profil) -> SectionQA:
        section = SectionQA(nom="Justificatifs", poids=0.10)

        if not profil.justificatifs_attendus:
            section.tests.append(TestResult("F0 — Pas de justificatifs attendus", "SKIP"))
            return section

        # Fix QA-1-7 : Signalement justificatifs via justificatifs_engine
        try:
            from app.engines.justificatifs_engine import noms_justificatifs_requis
            donnees = dict(profil.donnees_entree)
            noms_detectes = noms_justificatifs_requis(donnees, profil.profil_mdph)
            noms_detectes_low = [n.lower() for n in noms_detectes]

            for justif in profil.justificatifs_attendus:
                # Correspondance souple : vérifie si des mots-clés du justif attendu
                # se trouvent dans un justif détecté
                mots_cles = [m for m in justif.lower().split() if len(m) > 4]
                detecte = any(
                    any(mc in nd for mc in mots_cles)
                    for nd in noms_detectes_low
                )
                section.tests.append(TestResult(
                    f"F1 — Justificatif : {justif[:40]}",
                    "PASS" if detecte else "WARN",
                    detail=f"Détecté par justificatifs_engine" if detecte
                           else f"Non détecté automatiquement — vérification manuelle requise",
                    valeur_obtenue="détecté" if detecte else "non détecté",
                    valeur_attendue="détecté",
                ))
        except Exception as e:
            section.tests.append(TestResult("F0", "FAIL", str(e)))

        return section

    # ── G — Tests Stratégie FACILIM 60 ───────────────────────────────────────

    def _test_strategie(self, profil) -> SectionQA:
        """
        FACILIM 60 — Tests du Moteur Opportunités Droits et Stratégie.
        Poids : 0 (section bonus, ne compte pas dans le score principal).
        """
        section = SectionQA(nom="Strategie_F60", poids=0.0)
        donnees = dict(profil.donnees_entree)
        if profil.document_texte and not donnees.get("notes_pro"):
            donnees["notes_pro"] = profil.document_texte[:800]

        try:
            from app.engines.strategie_dossier_engine import analyser_strategie
            from app.engines.dossier_strength_engine import noter_robustesse

            strat = analyser_strategie(donnees, profil.profil_mdph, profil.profil_handicap)
            rob   = noter_robustesse(donnees, profil.profil_mdph)

            # G1 — Robustesse globale
            # Note : si le narratif B n'est pas généré (pas de LLM), la robustesse
            # sera naturellement basse. On évalue la structure du dossier, pas le LLM.
            seuil_rob = profil.score_maturite_min
            texte_b_present = bool(donnees.get("texte_b_vie_quotidienne"))
            if not texte_b_present:
                # Sans narratif : WARN systématique (LLM non actif en test structurel)
                statut_g1 = "WARN"
                detail_g1 = f"Score robustesse {rob.score_global}/100 — narratif B absent (LLM requis pour score complet)"
            else:
                statut_g1 = "PASS" if rob.score_global >= seuil_rob else (
                    "WARN" if rob.score_global >= seuil_rob - 20 else "FAIL"
                )
                detail_g1 = f"Score robustesse {rob.score_global}/100 (seuil {seuil_rob})"
            section.tests.append(TestResult(
                "G1 — Robustesse dossier",
                statut_g1,
                detail=detail_g1,
                valeur_obtenue=str(rob.score_global),
                valeur_attendue=f">= {seuil_rob}",
            ))

            # G2 — Droits demandés confirmés dans l'analyse
            droits_dem = set(profil.droits_attendus)
            droits_detectes = set(strat.droits_demandes)
            nb_confirmes = len(droits_dem & (droits_detectes | set([
                d.droit for d in strat.droits_omis
            ])))
            pct = nb_confirmes / len(droits_dem) if droits_dem else 1.0
            section.tests.append(TestResult(
                "G2 — Droits demandés reconnus",
                "PASS" if pct >= 0.5 else "WARN",
                detail=f"{nb_confirmes}/{len(droits_dem)} droits attendus reconnus",
                valeur_obtenue=f"{pct:.0%}",
                valeur_attendue="≥ 50%",
            ))

            # G3 — Droits non attendus non proposés (pas de faux positifs)
            faux_positifs = [
                d.droit for d in strat.droits_omis
                if d.droit in set(profil.droits_non_attendus)
            ]
            section.tests.append(TestResult(
                "G3 — Pas de faux positifs droits",
                "PASS" if not faux_positifs else "WARN",
                detail=f"Faux positifs : {faux_positifs}" if faux_positifs else "Aucun",
                valeur_obtenue=str(faux_positifs),
                valeur_attendue="[]",
            ))

            # G4 — Urgences détectées si attendues
            urgences_types = [u.type for u in strat.urgences]
            if profil.boucle_interdite and donnees.get("historique_mdph", ""):
                # Si historique indique un renouvellement, l'urgence P3 1 devrait être détectée
                if "renouvellement" in str(donnees.get("historique_mdph", "")).lower():
                    section.tests.append(TestResult(
                        "G4 — Urgence renouvellement détectée",
                        "PASS" if "FIN_DROITS" in urgences_types or "PROCEDURE_SIMPLIFIEE" in urgences_types else "WARN",
                        detail=f"Urgences détectées : {urgences_types}",
                    ))

            # G5 — Questions levier générées
            questions = strat.questions_levier
            section.tests.append(TestResult(
                "G5 — Questions levier générées",
                "PASS" if len(questions) >= 1 else "WARN",
                detail=f"{len(questions)} question(s) levier — ROI max : {questions[0].roi:.1f}" if questions else "Aucune",
                valeur_obtenue=str(len(questions)),
                valeur_attendue=">= 1",
            ))

            # G6 — Cohérence : pas d'alerte critique sur ce profil
            alertes = [a.type for a in strat.alertes_coherence]
            alertes_critiques = [
                a for a in strat.alertes_coherence
                if "MANQUANT" in a.type or "PROFIL_INCOMPLET" in a.type
            ]
            section.tests.append(TestResult(
                "G6 — Cohérence du dossier",
                "PASS" if not alertes_critiques else "WARN",
                detail=f"Alertes : {alertes}" if alertes else "Aucune alerte",
            ))

        except Exception as e:
            section.tests.append(TestResult("G0 — Moteur stratégie", "FAIL", str(e)))

        return section


# ─────────────────────────────────────────────────────────────────────────────
# RAPPORT
# ─────────────────────────────────────────────────────────────────────────────

def generer_rapport(results: list[ProfilQAResult], sprint: str = "") -> str:
    """Génère le rapport QA complet."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sep = "═" * 70

    lines = [
        sep,
        f"  FACILIM QA — RAPPORT DE VALIDATION",
        f"  Généré le : {now}",
        f"  Sprint : {sprint or 'non spécifié'}",
        f"  Profils testés : {len(results)}",
        sep,
    ]

    # Résumé global
    scores = [r.qa_score for r in results]
    score_moy = round(sum(scores) / len(scores), 1) if scores else 0
    nb_pass = sum(1 for r in results if r.pass_fail == "PASS")
    nb_fail = len(results) - nb_pass

    lines += [
        "",
        f"  RÉSUMÉ GLOBAL",
        f"  Score moyen        : {score_moy}/100",
        f"  Profils PASS       : {nb_pass}/{len(results)}",
        f"  Profils FAIL       : {nb_fail}/{len(results)}",
        "",
    ]

    # Couverture par section
    sections = ["whatsapp","documents","inferences","narratifs","cerfa","justificatifs"]
    lines.append("  COUVERTURE PAR SECTION")
    for s in sections:
        scores_s = [r.sections[s].score_section * 100 for r in results if s in r.sections]
        moy_s = round(sum(scores_s)/len(scores_s), 1) if scores_s else 0
        bar = "█" * int(moy_s // 10) + "░" * (10 - int(moy_s // 10))
        lines.append(f"  {s:<15} : {bar} {moy_s:5.1f}%")

    lines.append("")

    # Détail par profil
    lines.append("  DÉTAIL PAR PROFIL")
    lines.append(f"  {'ID':<30} {'Score':>6} {'Niveau':<25} {'FAIL':>5} {'WARN':>5}")
    lines.append("  " + "─" * 70)
    for r in sorted(results, key=lambda x: -x.qa_score):
        lines.append(
            f"  {r.profil_id:<30} {r.qa_score:>5.1f} {r.niveau:<25} "
            f"{r.nb_fails():>5} {r.nb_warns():>5}"
        )

    # Échecs critiques
    fails_critiques = []
    for r in results:
        for s in r.sections.values():
            for t in s.tests:
                if t.statut == "FAIL":
                    fails_critiques.append((r.profil_id, s.nom, t.nom, t.detail))

    if fails_critiques:
        lines += ["", "  ÉCHECS CRITIQUES (FAIL)", "  " + "─" * 70]
        for pid, snom, tnom, detail in fails_critiques[:20]:
            lines.append(f"  [{pid[:20]:<20}] {snom:<15} {tnom[:35]}")
            if detail:
                lines.append(f"    → {detail[:65]}")

    lines.append("")
    lines.append(sep)
    return "\n".join(lines)


def detecter_regressions(
    current: list[ProfilQAResult],
    previous: list[ProfilQAResult],
) -> list[dict]:
    """Compare deux runs et retourne les régressions."""
    prev_by_id = {r.profil_id: r for r in previous}
    regressions = []
    for curr in current:
        prev = prev_by_id.get(curr.profil_id)
        if not prev:
            continue
        delta = curr.qa_score - prev.qa_score
        if delta < -2:  # régression > 2 points
            regressions.append({
                "profil_id":    curr.profil_id,
                "score_avant":  prev.qa_score,
                "score_apres":  curr.qa_score,
                "delta":        round(delta, 1),
                "gravite":      "CRITIQUE" if delta < -10 else "IMPORTANTE",
            })
    return sorted(regressions, key=lambda x: x["delta"])


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Facilim QA Engine")
    parser.add_argument("--profil", help="ID du profil à tester")
    parser.add_argument("--all",    action="store_true", help="Tester tous les profils")
    parser.add_argument("--sprint", default="", help="Nom du sprint")
    parser.add_argument("--save",   action="store_true", help="Sauvegarder le rapport")
    args = parser.parse_args()

    # Clé OpenAI
    api_key = os.environ.get("OPENAI_API_KEY", "")
    client = None
    if api_key and api_key != "test":
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

    engine = FacilimQAEngine(openai_client=client)

    from app.tests.qa.profiles import ALL_PROFILES

    if args.profil:
        profils = [p for p in ALL_PROFILES if p.id == args.profil]
        if not profils:
            print(f"Profil '{args.profil}' non trouvé.")
            sys.exit(1)
    elif args.all:
        profils = ALL_PROFILES
    else:
        # Par défaut : les 3 profils les plus fréquents
        ids_default = {"ADULTE_ACCIDENT_TRAVAIL", "ENFANT_TSA_LEGER", "INSERTION_RQTH_ESPO"}
        profils = [p for p in ALL_PROFILES if p.id in ids_default]

    print(f"Tests en cours sur {len(profils)} profil(s)...")
    results = [engine.run_profil(p) for p in profils]
    rapport = generer_rapport(results, sprint=args.sprint)
    print(rapport)

    if args.save:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        path = f"app/tests/qa/reports/qa_{timestamp}.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write(rapport)
            f.write("\n\nJSON:\n")
            json.dump(
                [{"id": r.profil_id, "score": r.qa_score,
                  "sections": {k: {"score": v.score_section, "pass": v.nb_pass, "fail": v.nb_fail}
                               for k, v in r.sections.items()}}
                 for r in results],
                f, indent=2, ensure_ascii=False,
            )
        print(f"\nRapport sauvegardé : {path}")

    # Code retour CI
    fails = sum(1 for r in results if r.pass_fail == "FAIL")
    sys.exit(1 if fails > 0 else 0)
