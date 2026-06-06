"""
app/tests/qa/pdf_massive_audit_runner.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-6 — Audit massif des PDF CERFA réels générés par Facilim

Mesure à grande échelle :
  - couverture réelle des 612 champs AcroForm CERFA 15692*01
  - couverture critique N1 (champs décisionnels)
  - champs fantômes (field_mapper → clé inexistante dans le PDF)
  - droits détectés mais non cochés dans le PDF
  - droits cochés mais non justifiés
  - couverture par section métier

Ne modifie aucun moteur. Audit pur en lecture.

Usage :
  python -m app.tests.qa.pdf_massive_audit_runner --n 100 --seed 42 --save
  python -m app.tests.qa.pdf_massive_audit_runner --n 500 --seed 42 --save
  python -m app.tests.qa.pdf_massive_audit_runner --n 1000 --seed 42 --save
"""

from __future__ import annotations

import sys

# Force l'affichage UTF-8 sur la console (évite les crashs Windows cp1252 sur ≥, ✅, …)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, ".")
os.environ.setdefault("DATABASE_URL", "sqlite:///./mdph_dossiers.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-key-32-chars-minimum-length!")
os.environ.setdefault("WHATSAPP_API_TOKEN", "test")
os.environ.setdefault("WHATSAPP_PHONE_NUMBER_ID", "test")

PDF_CERFA = Path("storage/templates/cerfa_15692_01.pdf")

# ─────────────────────────────────────────────────────────────────────────────
# INVENTAIRE PDF — chargé une seule fois au démarrage
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ChampPDFInfo:
    nom:        str
    page:       int
    type_raw:   str    # "/Tx" | "/Btn" | "/Sig"
    section:    str
    criticite:  int    # 1=critique 2=important 3=secondaire


def _detecter_section(nom: str, page: int) -> str:
    if page == 1:               return "garde"
    if page == 2:               return "identite"
    if page == 3:               return "urgence_protection"
    if page == 4:               return "consentement"
    if page == 5:               return "vie_quotidienne"
    if page in (6, 7):          return "avq_besoins"
    if page == 8:               return "texte_b"
    if page in (9, 10, 11, 12): return "scolarite"
    if page in (13, 14):        return "emploi"
    if page == 15:              return "parcours_pro"
    if page == 16:              return "projet_vie"
    if page == 17:              return "droits_e1_e2"
    if page == 18:              return "droits_e3"
    if page in (19, 20):        return "aidant"
    return "autre"


def _criticite_rapide(nom: str, page: int) -> int:
    n = nom.lower()
    # Critique (1)
    if any(p in n for p in ["p17", "p18"]):         return 1
    if any(p in n for p in ["p2 1", "p2 2", "p2 3", "date a", "p1 1", "p1 2", "p1 3", "p1 a"]):
        return 1
    if "numero ss" in n or "ss enfant" in n:         return 1
    if "representant legal" in n:                    return 1
    if "champ de texte p8 1" in n:                   return 1
    if "champ de texte p16 1" in n:                  return 1
    if page in (9, 10) and "/Btn" in nom:            return 2
    # Important (2)
    if page in (13, 14):                             return 2
    if "autorite parent" in n:                       return 2
    # Secondaire
    return 3


_PDF_INVENTORY: dict[str, ChampPDFInfo] = {}   # {nom: ChampPDFInfo}
_PDF_NOMS: set[str] = set()


def _charger_inventaire_pdf() -> None:
    """Charge l'inventaire PDF une seule fois au démarrage."""
    global _PDF_INVENTORY, _PDF_NOMS
    if _PDF_INVENTORY:
        return  # Déjà chargé

    import pypdf
    reader = pypdf.PdfReader(str(PDF_CERFA))
    pdf_fields = reader.get_fields() or {}

    page_map: dict[str, int] = {}
    for page_num, page in enumerate(reader.pages, 1):
        annots = page.get("/Annots")
        if not annots:
            continue
        for annot in annots:
            try:
                obj = annot.get_object() if hasattr(annot, "get_object") else annot
                t = obj.get("/T")
                if t:
                    page_map[str(t)] = page_num
            except Exception:
                pass

    for nom, f in pdf_fields.items():
        type_raw = str(f.get("/FT", "/Tx"))
        page = page_map.get(nom, 0)
        _PDF_INVENTORY[nom] = ChampPDFInfo(
            nom=nom,
            page=page,
            type_raw=type_raw,
            section=_detecter_section(nom, page),
            criticite=_criticite_rapide(nom, page),
        )
    _PDF_NOMS = set(_PDF_INVENTORY.keys())


# ─────────────────────────────────────────────────────────────────────────────
# MAPPING DROIT → CASE CERFA
# ─────────────────────────────────────────────────────────────────────────────

_DROIT_TO_CERFA: dict[str, str | None] = {
    "AEEH":              "Case à cocher P17 1",
    "PCH":               "Case à cocher P17 2",  # enfant
    "CMI_INVALIDITE":    "Case à cocher P17 3",
    "AVPF":              "Case à cocher P17 4",
    "AAH":               "Case à cocher P17 5",
    "RQTH":              "Case à cocher P17 6",
    "PCH_ADULTE":        "Case à cocher P17 7",
    "MAS":               "Case à cocher P17 8",
    "FOYER_VIE":         "Case à cocher P17 9",
    "FOYER_HEBERGEMENT": "Case à cocher P17 10",
    "ESAT":              "Case à cocher P17 11",
    "CMI_STATIONNEMENT": "Case à cocher P17 13",
    "CMI_PRIORITE":      "Case à cocher P17 14",
    "RQTH_emploi":       "Case à cocher P18 1",
    "ESPO":              "Case à cocher P18 3",
    "ESAT_emploi":       "Case à cocher P18 4",
    "EMPLOI_ACCOMPAGNE": "Case à cocher P18 6",
    "SESSAD":            "Case à cocher P10 5",
    "IME":               "Case à cocher P10 6",
    "EEAP":              "Case à cocher P10 10",
    # Droits sans case CERFA directe
    "SAVS":              None,
    "SAMSAH":            None,
    "UEROS":             None,
    "ESRP":              "Case à cocher P18 5",
}

# Champs connus comme CRITIQUES (si fantômes → alerte rouge)
_CHAMPS_CRITIQUES_CONNUS = {
    "Case à cocher P17 1", "Case à cocher P17 2", "Case à cocher P17 3",
    "Case à cocher P17 4", "Case à cocher P17 5", "Case à cocher P17 6",
    "Case à cocher P17 7", "Case à cocher P17 8", "Case à cocher P17 9",
    "Case à cocher P17 10", "Case à cocher P17 11", "Case à cocher P17 12",
    "Case à cocher P17 13", "Case à cocher P17 14",
    "Case à cocher P18 1", "Case à cocher P18 2", "Case à cocher P18 3",
    "Case à cocher P18 4", "Case à cocher P18 5", "Case à cocher P18 6",
    "Champ de texte P8 1", "Champ de texte P16 1",
    "Case à cocher P10 1", "Case à cocher P10 2",
    "Case à cocher P10 3", "Case à cocher P10 4",
    "Case à cocher P10 5", "Case à cocher P10 6", "Case à cocher P10 10",
}


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURES DE RÉSULTATS PAR DOSSIER
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CerfaAuditResult:
    profil_id:          str
    famille:            str
    profil_mdph:        str
    niveau_doc:         str

    # Couverture brute
    champs_produits:        int     # combien de champs field_mapper a produit
    champs_valides:         int     # combien sont dans le PDF réel
    champs_fantomes:        list[str]  # produits mais inexistants dans PDF
    champs_fantomes_critiques: list[str]  # fantômes ET critiques

    # Couverture PDF
    total_pdf:              int     # 612
    total_applicables:      int     # champs applicables selon profil
    couverts:               int     # champs réellement produits (non /Off)
    taux_global:            float
    taux_applicable:        float

    # Par section
    couverture_sections:    dict[str, float]  # {section: taux}

    # Couverture N1
    n1_applicables:         int
    n1_couverts:            int
    taux_n1:                float

    # Droits
    droits_attendus:        list[str]
    droits_coches_cerfa:    list[str]  # cases /Yes dans field_map
    droits_detectes_non_coches: list[str]  # détectés par moteur mais pas cochés
    droits_incompatibles_coches: list[str]  # cas incompatibles cochés

    # Contrôle global
    has_ghost_critique:     bool
    has_droit_incompatible: bool
    taux_droits_p17p18:     float

    statut:                 str     # "PASS" | "WARN" | "FAIL"
    erreur:                 str     = ""


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE PAR DOSSIER
# ─────────────────────────────────────────────────────────────────────────────

def auditer_dossier_cerfa(profil) -> CerfaAuditResult:
    """Audit CERFA complet pour un profil synthétique."""
    try:
        from app.engines.pdf.field_mapper import build_field_map
        from app.engines.strategie_dossier_engine import analyser_strategie

        donnees = dict(profil.donnees)
        profil_mdph = profil.profil_mdph

        # 1. Générer le field_map (sans LLM)
        field_map = build_field_map(donnees, profil_mdph)

        # 2. Analyser la stratégie (pour droits détectés)
        strat = analyser_strategie(donnees, profil_mdph, profil.profil_handicap)

        # 3. Ghost fields : clés field_map inexistantes dans le PDF
        champs_fantomes = [k for k in field_map if k not in _PDF_NOMS]
        champs_fantomes_critiques = [k for k in champs_fantomes if k in _CHAMPS_CRITIQUES_CONNUS]

        # 4. Couverture — comparer field_map vs inventaire PDF
        #    On compte les champs valides (dans le PDF ET produits avec valeur non-/Off)
        champs_valides_produits = {k: v for k, v in field_map.items() if k in _PDF_NOMS}

        # 5. Applicabilité selon profil
        non_applicables: set[str] = set()
        # Pages scolarité + NSS enfant non applicables pour adulte
        if profil_mdph == "adulte":
            non_applicables.update(c.nom for c in _PDF_INVENTORY.values()
                                    if c.section == "scolarite")
            # NSS enfant (N° SS Enfant *) non applicable pour adulte
            non_applicables.update(c.nom for c in _PDF_INVENTORY.values()
                                    if c.nom.startswith("N° SS Enfant"))
        # Pages emploi non applicables pour enfant
        if profil_mdph == "enfant":
            non_applicables.update(c.nom for c in _PDF_INVENTORY.values()
                                    if c.section in ("emploi", "parcours_pro"))
            # NSS adulte (Numero SS *) non applicable pour enfant
            # L'enfant utilise "N° SS Enfant *" — les deux séries sont dans le PDF
            non_applicables.update(c.nom for c in _PDF_INVENTORY.values()
                                    if c.nom.startswith("Numero SS"))
        # Page protection non applicable si pas de type_protection
        if not donnees.get("type_protection") and profil_mdph != "protege":
            non_applicables.update(c.nom for c in _PDF_INVENTORY.values()
                                    if c.section == "urgence_protection" and "REPRESENTANT" in c.nom)
        # Aidant non applicable si pas d'aidant
        if not donnees.get("aidant_nom"):
            non_applicables.update(c.nom for c in _PDF_INVENTORY.values()
                                    if c.section == "aidant")

        # Signatures hors scope
        non_applicables.update(c.nom for c in _PDF_INVENTORY.values() if c.type_raw == "/Sig")

        applicables = _PDF_NOMS - non_applicables
        total_applicables = len(applicables)
        couverts = len({k for k in champs_valides_produits if k in applicables})
        total_pdf = len(_PDF_NOMS)

        taux_global = round(len(champs_valides_produits) / total_pdf * 100, 1) if total_pdf else 0
        taux_applicable = round(couverts / total_applicables * 100, 1) if total_applicables else 0

        # 6. Couverture N1
        n1_champs = {nom for nom, c in _PDF_INVENTORY.items() if c.criticite == 1}
        n1_applicables = len(n1_champs & applicables)
        n1_couverts = len({k for k in champs_valides_produits if k in n1_champs and k in applicables})
        taux_n1 = round(n1_couverts / n1_applicables * 100, 1) if n1_applicables else 0

        # 7. Couverture par section
        couverture_sections: dict[str, float] = {}
        sections_a_mesurer = ["garde", "identite", "droits_e1_e2", "droits_e3",
                               "texte_b", "scolarite", "emploi", "aidant", "consentement",
                               "vie_quotidienne", "avq_besoins", "projet_vie"]
        for section in sections_a_mesurer:
            champs_section = {nom for nom, c in _PDF_INVENTORY.items() if c.section == section}
            applicables_section = champs_section & applicables
            couverts_section = len({k for k in champs_valides_produits if k in applicables_section})
            if applicables_section:
                couverture_sections[section] = round(couverts_section / len(applicables_section) * 100, 1)

        # 8. Droits cochés dans le CERFA
        droits_coches: list[str] = []
        for droit, case in _DROIT_TO_CERFA.items():
            if case and field_map.get(case) == "/Yes":
                droits_coches.append(droit)

        # 9. Droits détectés par le moteur mais non cochés dans le CERFA
        droits_proposes = {d.droit for d in strat.droits_omis}
        droits_detectes_non_coches = []
        for droit in droits_proposes:
            case = _DROIT_TO_CERFA.get(droit)
            if case is not None and field_map.get(case) != "/Yes":
                droits_detectes_non_coches.append(droit)

        # 10. Droits incompatibles cochés (faux positifs dangereux)
        droits_incompatibles: list[str] = []
        for droit_incomp in profil.droits_non_attendus:
            case = _DROIT_TO_CERFA.get(droit_incomp)
            if case and field_map.get(case) == "/Yes":
                droits_incompatibles.append(droit_incomp)

        # 11. Couverture P17/P18
        p17p18_champs = {nom for nom in _PDF_NOMS if "P17" in nom or "P18" in nom}
        p17p18_produits = len({k for k in champs_valides_produits if k in p17p18_champs})
        taux_droits_p17p18 = round(p17p18_produits / len(p17p18_champs) * 100, 1) if p17p18_champs else 0

        # 12. Statut global
        if champs_fantomes_critiques or droits_incompatibles:
            statut = "FAIL"
        elif len(champs_fantomes) > 3 or taux_n1 < 15:
            statut = "WARN"
        else:
            statut = "PASS"

        return CerfaAuditResult(
            profil_id=profil.id,
            famille=profil.famille,
            profil_mdph=profil_mdph,
            niveau_doc=profil.niveau_documentation,
            champs_produits=len(field_map),
            champs_valides=len(champs_valides_produits),
            champs_fantomes=champs_fantomes,
            champs_fantomes_critiques=champs_fantomes_critiques,
            total_pdf=total_pdf,
            total_applicables=total_applicables,
            couverts=couverts,
            taux_global=taux_global,
            taux_applicable=taux_applicable,
            couverture_sections=couverture_sections,
            n1_applicables=n1_applicables,
            n1_couverts=n1_couverts,
            taux_n1=taux_n1,
            droits_attendus=profil.droits_attendus,
            droits_coches_cerfa=droits_coches,
            droits_detectes_non_coches=droits_detectes_non_coches,
            droits_incompatibles_coches=droits_incompatibles,
            has_ghost_critique=bool(champs_fantomes_critiques),
            has_droit_incompatible=bool(droits_incompatibles),
            taux_droits_p17p18=taux_droits_p17p18,
            statut=statut,
        )

    except Exception as e:
        import traceback
        return CerfaAuditResult(
            profil_id=profil.id,
            famille=profil.famille,
            profil_mdph=getattr(profil, "profil_mdph", "?"),
            niveau_doc=getattr(profil, "niveau_documentation", "?"),
            champs_produits=0, champs_valides=0,
            champs_fantomes=[], champs_fantomes_critiques=[],
            total_pdf=len(_PDF_NOMS), total_applicables=0, couverts=0,
            taux_global=0.0, taux_applicable=0.0,
            couverture_sections={}, n1_applicables=0, n1_couverts=0, taux_n1=0.0,
            droits_attendus=[], droits_coches_cerfa=[],
            droits_detectes_non_coches=[], droits_incompatibles_coches=[],
            has_ghost_critique=False, has_droit_incompatible=False,
            taux_droits_p17p18=0.0,
            statut="FAIL",
            erreur=f"{type(e).__name__}: {str(e)[:120]}",
        )


# ─────────────────────────────────────────────────────────────────────────────
# ANALYSE GLOBALE
# ─────────────────────────────────────────────────────────────────────────────

def analyser_resultats_cerfa(resultats: list[CerfaAuditResult]) -> dict:
    n = len(resultats)
    if not n:
        return {}

    nb_pass = sum(1 for r in resultats if r.statut == "PASS")
    nb_warn = sum(1 for r in resultats if r.statut == "WARN")
    nb_fail = sum(1 for r in resultats if r.statut == "FAIL")

    taux_global_moy  = round(sum(r.taux_global for r in resultats) / n, 1)
    taux_applic_moy  = round(sum(r.taux_applicable for r in resultats) / n, 1)
    taux_n1_moy      = round(sum(r.taux_n1 for r in resultats) / n, 1)
    taux_p17p18_moy  = round(sum(r.taux_droits_p17p18 for r in resultats) / n, 1)
    champs_produits_moy = round(sum(r.champs_produits for r in resultats) / n, 1)

    # Couverture par section (agrégée)
    section_totals: dict[str, list[float]] = defaultdict(list)
    for r in resultats:
        for section, taux in r.couverture_sections.items():
            section_totals[section].append(taux)

    couverture_sections_moy = {
        section: round(sum(vals) / len(vals), 1)
        for section, vals in section_totals.items()
        if vals
    }

    # Ghost fields — fréquence par nom
    ghost_freq: dict[str, int] = defaultdict(int)
    ghost_crit_freq: dict[str, int] = defaultdict(int)
    for r in resultats:
        for g in r.champs_fantomes:
            ghost_freq[g] += 1
        for g in r.champs_fantomes_critiques:
            ghost_crit_freq[g] += 1

    # Top champs manquants (dans PDF, applicables, jamais produits)
    manquants_freq: dict[str, int] = defaultdict(int)
    for r in resultats:
        if r.statut == "FAIL" or r.taux_n1 < 20:
            continue  # On cherche les manquants sur dossiers normaux
    # Compter pour tous les dossiers : champs PDF N1 absents du field_map
    # Approximation : on compte les cases droits P17/P18 jamais produites
    droits_manquants_freq: dict[str, int] = defaultdict(int)
    for r in resultats:
        coches_set = set(r.droits_coches_cerfa)
        for droit in r.droits_attendus:
            case = _DROIT_TO_CERFA.get(droit)
            if case and droit not in coches_set:
                droits_manquants_freq[droit] += 1

    # Droits détectés non cochés agrégés
    detectes_non_coches_freq: dict[str, int] = defaultdict(int)
    for r in resultats:
        for d in r.droits_detectes_non_coches:
            detectes_non_coches_freq[d] += 1

    # Droits incompatibles cochés agrégés
    incompatibles_freq: dict[str, int] = defaultdict(int)
    for r in resultats:
        for d in r.droits_incompatibles_coches:
            incompatibles_freq[d] += 1

    # Par famille
    par_famille: dict[str, dict] = defaultdict(lambda: {"pass": 0, "warn": 0, "fail": 0,
                                                          "taux_global": [], "taux_n1": []})
    for r in resultats:
        par_famille[r.famille][r.statut.lower()] += 1
        par_famille[r.famille]["taux_global"].append(r.taux_global)
        par_famille[r.famille]["taux_n1"].append(r.taux_n1)

    # Par profil_mdph
    par_mdph: dict[str, dict] = defaultdict(lambda: {"pass": 0, "warn": 0, "fail": 0,
                                                        "taux_n1": []})
    for r in resultats:
        par_mdph[r.profil_mdph][r.statut.lower()] += 1
        par_mdph[r.profil_mdph]["taux_n1"].append(r.taux_n1)

    # Top profils les moins couverts
    sorted_by_coverage = sorted(resultats, key=lambda r: r.taux_n1)[:20]

    return {
        "n": n,
        "nb_pass": nb_pass, "nb_warn": nb_warn, "nb_fail": nb_fail,
        "taux_pass": round(nb_pass / n * 100, 1),
        "taux_fail": round(nb_fail / n * 100, 1),
        "taux_global_moy":   taux_global_moy,
        "taux_applic_moy":   taux_applic_moy,
        "taux_n1_moy":       taux_n1_moy,
        "taux_p17p18_moy":   taux_p17p18_moy,
        "champs_produits_moy": champs_produits_moy,
        "couverture_sections_moy": couverture_sections_moy,
        "nb_ghost_critique": sum(1 for r in resultats if r.has_ghost_critique),
        "nb_droit_incompatible": sum(1 for r in resultats if r.has_droit_incompatible),
        "top_ghost_champs":  sorted(ghost_freq.items(), key=lambda x: -x[1])[:50],
        "top_ghost_critiques": sorted(ghost_crit_freq.items(), key=lambda x: -x[1])[:20],
        "top_droits_manquants": sorted(droits_manquants_freq.items(), key=lambda x: -x[1])[:50],
        "top_detectes_non_coches": sorted(detectes_non_coches_freq.items(), key=lambda x: -x[1])[:20],
        "top_incompatibles": sorted(incompatibles_freq.items(), key=lambda x: -x[1])[:10],
        "par_famille": dict(par_famille),
        "par_mdph": dict(par_mdph),
        "top_fragiles": sorted_by_coverage,
    }


# ─────────────────────────────────────────────────────────────────────────────
# RAPPORT GHOST FIELDS
# ─────────────────────────────────────────────────────────────────────────────

def generer_rapport_ghost_fields(metriques: dict, n: int) -> str:
    """Génère ghost_fields.md — analyse des champs fantômes."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# Ghost Fields — Champs fantômes détectés par field_mapper",
        "",
        f"_Généré le {now} — {n} dossiers analysés_",
        "",
        "## Définition",
        "",
        "Un **champ fantôme** est une clé produite par `build_field_map()` qui n'existe",
        "pas dans les 612 champs AcroForm du CERFA 15692*01 officiel.",
        "Ces champs sont écrits dans le dict mais n'ont aucun effet sur le PDF.",
        "",
    ]

    top_ghost = metriques["top_ghost_champs"]
    top_crit  = metriques["top_ghost_critiques"]

    if top_crit:
        lines += [
            "## ⚠️ Champs fantômes CRITIQUES (clés qui DEVRAIENT être dans le PDF)",
            "",
            "Ces clés ressemblent à des champs critiques mais ont une orthographe incorrecte.",
            "",
            "| Champ fantôme | Apparitions | Champ réel probable |",
            "|--------------|------------|---------------------|",
        ]
        for nom, count in top_crit:
            # Essayer de deviner le nom réel
            probable = nom
            if " P 10 " in nom:
                probable = nom.replace(" P 10 ", " P10 ")
            elif " P 9 " in nom.replace("P 9", "").replace("P9", ""):
                probable = "vérifier manuellement"
            lines.append(f"| `{nom}` | {count}/{n} | `{probable}` |")
        lines.append("")
    else:
        lines += [
            "## ✅ Aucun champ fantôme critique détecté",
            "",
            "Tous les champs produits par `field_mapper` pour les clés critiques",
            "correspondent aux vrais noms AcroForm du PDF.",
            "",
        ]

    if top_ghost:
        lines += [
            "## Tous les champs fantômes détectés",
            "",
            "| Champ fantôme | Apparitions (/{n}) | Type probable |",
            "|--------------|-------------------|---------------|",
        ]
        for nom, count in top_ghost[:50]:
            is_crit = "⚠️ CRITIQUE" if nom in _CHAMPS_CRITIQUES_CONNUS else ""
            lines.append(f"| `{nom}` | {count}/{n} ({round(count/n*100,1)}%) | {is_crit} |")
    else:
        lines += [
            "## ✅ Aucun champ fantôme détecté",
            "",
            "Le `field_mapper` produit uniquement des clés valides présentes dans le PDF.",
            "",
        ]

    # Recommandations
    lines += ["", "## Recommandations", ""]
    if top_crit:
        lines.append(f"- **{len(top_crit)} champ(s) fantôme(s) critique(s)** — corriger les noms dans `field_mapper.py`")
    if top_ghost and not top_crit:
        lines.append("- Champs fantômes non critiques détectés — impact nul sur le PDF mais nettoyage recommandé")
    if not top_ghost:
        lines.append("- Aucune correction nécessaire — mapping propre ✅")

    return "\n".join(lines).replace("{n}", str(n))


# ─────────────────────────────────────────────────────────────────────────────
# RAPPORT MARKDOWN PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

_SECTION_LABELS = {
    "garde":             "Page de garde",
    "identite":          "Identité (A1/A2)",
    "urgence_protection":"Urgences + Protection (A3/A4)",
    "consentement":      "Consentement (P4)",
    "vie_quotidienne":   "Vie quotidienne B1 (P5)",
    "avq_besoins":       "Besoins AVQ (P6/P7)",
    "texte_b":           "Texte libre B (P8)",
    "scolarite":         "Scolarité C (P9-12)",
    "emploi":            "Emploi D (P13-14)",
    "parcours_pro":      "Parcours pro (P15)",
    "projet_vie":        "Projet de vie E (P16)",
    "droits_e1_e2":      "Droits E1/E2 (P17)",
    "droits_e3":         "Droits E3 (P18)",
    "aidant":            "Aidant F (P19-20)",
    "autre":             "Autre",
}


def generer_rapport_md(metriques: dict, seed: int, n: int, duree_s: float) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    taux_n1 = metriques["taux_n1_moy"]
    nb_ghost_crit = metriques["nb_ghost_critique"]
    nb_incomp = metriques["nb_droit_incompatible"]

    # Validation seuils QA-6
    ok_ghost  = nb_ghost_crit == 0
    ok_incomp = nb_incomp == 0
    ok_n1     = taux_n1 >= 35
    decision  = "✅ PASS" if (ok_ghost and ok_incomp and ok_n1) else (
                "⚠️ WARN" if (ok_ghost and ok_incomp) else "❌ FAIL"
    )

    lines = [
        f"# QA-6 — Audit Massif PDF CERFA Réels",
        f"",
        f"**Généré le :** {now}  ",
        f"**Dossiers audités :** {n}  ",
        f"**Seed :** {seed}  ",
        f"**Durée :** {duree_s:.1f}s ({duree_s/n*1000:.0f}ms/dossier)  ",
        f"**Décision QA-6 :** {decision}",
        "",
        "---",
        "",
        "## 1. Synthèse exécutive",
        "",
        f"Sur **{n} dossiers CERFA** audités (sans LLM, pipeline Facilim complet) :",
        "",
        f"- **Couverture globale moyenne** (/ 612 champs) : {metriques['taux_global_moy']}%",
        f"- **Couverture applicable moyenne** : {metriques['taux_applic_moy']}%",
        f"- **Couverture critique N1 moyenne** : {taux_n1}%  ",
        f"  _(seuil QA-6 requis : ≥ 35%)_",
        f"- **Couverture droits P17/P18** : {metriques['taux_p17p18_moy']}%",
        f"- **Champs produits en moyenne** : {metriques['champs_produits_moy']}/612",
        f"- **Ghost fields critiques** : {nb_ghost_crit} _(requis : 0)_",
        f"- **Droits incompatibles cochés** : {nb_incomp} _(requis : 0)_",
        "",
        "---",
        "",
        "## 2. Validation des seuils QA-6",
        "",
        f"| Critère | Résultat | Seuil | Statut |",
        f"|---------|---------|-------|--------|",
        f"| Ghost fields critiques = 0 | {nb_ghost_crit} | 0 | {'✅' if ok_ghost else '❌'} |",
        f"| Droits incompatibles cochés = 0 | {nb_incomp} | 0 | {'✅' if ok_incomp else '❌'} |",
        f"| Couverture N1 ≥ 35% | {taux_n1}% | 35% | {'✅' if ok_n1 else '❌'} |",
        "",
        "---",
        "",
        "## 3. Couverture par section CERFA",
        "",
        "| Section | Couverture | Barre |",
        "|---------|-----------|-------|",
    ]

    for section, label in _SECTION_LABELS.items():
        taux = metriques["couverture_sections_moy"].get(section)
        if taux is None:
            continue
        barre = "█" * int(taux / 10) + "░" * (10 - int(taux / 10))
        lines.append(f"| {label} | {taux:.1f}% | `{barre}` |")

    lines += [
        "",
        "---",
        "",
        "## 4. Couverture par type de profil",
        "",
        "| Profil MDPH | N | PASS | WARN | FAIL | Cov N1 moy |",
        "|------------|---|------|------|------|-----------|",
    ]
    for mdph, stats in sorted(metriques["par_mdph"].items()):
        n_mdph = stats["pass"] + stats["warn"] + stats["fail"]
        n1_moy = round(sum(stats["taux_n1"]) / len(stats["taux_n1"]), 1) if stats["taux_n1"] else 0
        lines.append(f"| {mdph} | {n_mdph} | {stats['pass']} | {stats['warn']} | {stats['fail']} | {n1_moy}% |")

    lines += [
        "",
        "---",
        "",
        "## 5. Top droits attendus non cochés dans le CERFA",
        "",
        "_(Droits dans `droits_attendus` du profil mais case CERFA absente du field_map)_",
        "",
        "| # | Droit | Non coché N fois | Case CERFA |",
        "|---|-------|----------------|-----------|",
    ]
    for i, (droit, count) in enumerate(metriques["top_droits_manquants"][:20], 1):
        case = _DROIT_TO_CERFA.get(droit, "N/A")
        lines.append(f"| {i} | `{droit}` | {count}/{n} ({round(count/n*100,1)}%) | `{case}` |")

    lines += [
        "",
        "---",
        "",
        "## 6. Droits détectés par moteur mais non cochés dans le PDF",
        "",
        "_(Le moteur stratégie identifie le droit mais field_mapper ne coche pas la case)_",
        "",
        "| # | Droit | Occurrences |",
        "|---|-------|------------|",
    ]
    for i, (droit, count) in enumerate(metriques["top_detectes_non_coches"][:20], 1):
        lines.append(f"| {i} | `{droit}` | {count}/{n} ({round(count/n*100,1)}%) |")

    # Ghost fields
    top_ghost = metriques["top_ghost_champs"]
    lines += [
        "",
        "---",
        "",
        "## 7. Champs fantômes (field_mapper → clé inexistante dans PDF)",
        "",
    ]
    if not top_ghost:
        lines.append("✅ **Aucun champ fantôme détecté.** Le field_mapper produit uniquement des clés valides.")
    else:
        lines += [
            f"| # | Champ fantôme | Apparitions | Critique ? |",
            f"|---|--------------|------------|-----------|",
        ]
        for i, (nom, count) in enumerate(top_ghost[:20], 1):
            crit = "⚠️ OUI" if nom in _CHAMPS_CRITIQUES_CONNUS else "non"
            lines.append(f"| {i} | `{nom}` | {count}/{n} | {crit} |")

    lines += [
        "",
        "---",
        "",
        "## 8. Top 20 profils les moins couverts",
        "",
        "| ID | Famille | Niveau doc | Cov N1 | Global | Statut |",
        "|----|---------|-----------|--------|--------|--------|",
    ]
    for r in metriques["top_fragiles"][:20]:
        lines.append(f"| {r.profil_id} | {r.famille} | {r.niveau_doc} | {r.taux_n1:.1f}% | {r.taux_global:.1f}% | {r.statut} |")

    lines += [
        "",
        "---",
        "",
        "## 9. Couverture par famille de handicap",
        "",
        "| Famille | N | Cov N1 moy | Cov globale | PASS | FAIL |",
        "|---------|---|-----------|------------|------|------|",
    ]
    for famille, stats in sorted(metriques["par_famille"].items(), key=lambda x: -len(x[1]["taux_n1"])):
        n_f = len(stats["taux_n1"])
        n1_moy = round(sum(stats["taux_n1"]) / n_f, 1) if n_f else 0
        glob_moy = round(sum(stats["taux_global"]) / n_f, 1) if n_f else 0
        lines.append(f"| {famille} | {n_f} | {n1_moy}% | {glob_moy}% | {stats['pass']} | {stats['fail']} |")

    lines += [
        "",
        "---",
        "",
        "## 10. Décision finale",
        "",
        f"| Critère | Résultat | Seuil | OK |",
        f"|---------|---------|-------|-----|",
        f"| Ghost fields critiques = 0 | {nb_ghost_crit} | 0 | {'✅' if ok_ghost else '❌'} |",
        f"| Droits incompatibles = 0 | {nb_incomp} | 0 | {'✅' if ok_incomp else '❌'} |",
        f"| Couverture N1 ≥ 35% | {taux_n1}% | 35% | {'✅' if ok_n1 else '❌'} |",
        f"",
        f"**{decision}**",
        "",
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="QA-6 — Audit massif PDF CERFA")
    parser.add_argument("--n",    type=int, default=100, help="Nombre de dossiers")
    parser.add_argument("--seed", type=int, default=42,  help="Seed aléatoire")
    parser.add_argument("--save", action="store_true",   help="Sauvegarder les rapports")
    args = parser.parse_args()

    n, seed = args.n, args.seed

    print(f"QA-6 — Audit massif PDF CERFA : {n} dossiers (seed={seed})")
    print(f"Seuils : ghost critique = 0 · droit incompatible = 0 · N1 ≥ 35%")
    print()

    # Chargement inventaire PDF
    print("[1/4] Chargement inventaire PDF CERFA...")
    t0 = time.time()
    _charger_inventaire_pdf()
    print(f"  {len(_PDF_INVENTORY)} champs AcroForm chargés depuis {PDF_CERFA}")

    # Génération profils
    print(f"\n[2/4] Génération de {n} profils synthétiques...")
    from app.tests.qa.synthetic_profiles_engine import generer_profils
    profils = generer_profils(n=n, seed=seed)
    print(f"  {len(profils)} profils générés")

    # Pipeline audit CERFA
    print(f"\n[3/4] Audit CERFA ({n} dossiers)...")
    resultats: list[CerfaAuditResult] = []
    errors = 0
    for i, profil in enumerate(profils):
        r = auditer_dossier_cerfa(profil)
        resultats.append(r)
        if r.erreur:
            errors += 1
        if (i + 1) % max(1, n // 10) == 0:
            nb_p = sum(1 for x in resultats if x.statut == "PASS")
            nb_f = sum(1 for x in resultats if x.statut == "FAIL")
            n1_moy = round(sum(x.taux_n1 for x in resultats) / len(resultats), 1)
            print(f"  [{i+1:>4}/{n}] PASS:{nb_p} FAIL:{nb_f} N1:{n1_moy}% erreurs:{errors}")

    t1 = time.time()
    duree = round(t1 - t0, 1)
    print(f"\n  ✅ Audit terminé en {duree}s ({duree/n*1000:.0f}ms/dossier)")

    # Analyse
    print(f"\n[4/4] Analyse des métriques CERFA...")
    metriques = analyser_resultats_cerfa(resultats)

    # Affichage console
    sep = "─" * 65
    taux_n1 = metriques["taux_n1_moy"]
    nb_ghost = metriques["nb_ghost_critique"]
    nb_incomp = metriques["nb_droit_incompatible"]

    print(f"\n{sep}")
    print(f"  RÉSULTATS QA-6 — {n} dossiers CERFA (seed={seed})")
    print(sep)
    print(f"  Couverture globale moy    : {metriques['taux_global_moy']:5.1f}%")
    print(f"  Couverture applicable moy : {metriques['taux_applic_moy']:5.1f}%")
    print(f"  Couverture N1 critique    : {taux_n1:5.1f}%  {'✅' if taux_n1 >= 35 else '❌'} (seuil 35%)")
    print(f"  Couverture droits P17/P18 : {metriques['taux_p17p18_moy']:5.1f}%")
    print(f"  Champs produits moy       : {metriques['champs_produits_moy']:5.1f}/612")
    print(f"  Ghost fields critiques    : {nb_ghost:5}  {'✅' if nb_ghost == 0 else '❌'}")
    print(f"  Droits incompatibles      : {nb_incomp:5}  {'✅' if nb_incomp == 0 else '❌'}")
    print()
    print(f"  Couverture par section :")
    for section, taux in sorted(metriques["couverture_sections_moy"].items(),
                                  key=lambda x: -x[1])[:8]:
        barre = "█" * int(taux / 10) + "░" * (10 - int(taux / 10))
        label = _SECTION_LABELS.get(section, section)
        print(f"    {label:<35} {barre} {taux:5.1f}%")

    print()
    print(f"  Top 5 droits attendus non cochés :")
    for droit, count in metriques["top_droits_manquants"][:5]:
        print(f"    {count:>5}/{n}  {droit}")

    if metriques["top_ghost_champs"]:
        print()
        print(f"  Ghost fields détectés (top 5) :")
        for nom, count in metriques["top_ghost_champs"][:5]:
            crit = " ⚠️ CRITIQUE" if nom in _CHAMPS_CRITIQUES_CONNUS else ""
            print(f"    {count:>5}/{n}  {nom}{crit}")

    # Décision
    ok = (nb_ghost == 0 and nb_incomp == 0 and taux_n1 >= 35)
    decision = "✅ PASS" if ok else ("⚠️ WARN" if (nb_ghost == 0 and nb_incomp == 0) else "❌ FAIL")
    print(f"\n  Décision QA-6 ({n} dossiers) : {decision}")
    print(sep)

    # Sauvegarde
    if args.save:
        out_dir = Path("app/tests/qa/reports")
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M")

        rapport_md = generer_rapport_md(metriques, seed, n, duree)
        path_md = out_dir / f"pdf_audit_{n}_{ts}.md"
        path_md.write_text(rapport_md, encoding="utf-8")
        print(f"\n  Rapport : {path_md}")

        ghost_md = generer_rapport_ghost_fields(metriques, n)
        path_ghost = out_dir / f"ghost_fields_{n}_{ts}.md"
        path_ghost.write_text(ghost_md, encoding="utf-8")
        print(f"  Ghost fields : {path_ghost}")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
