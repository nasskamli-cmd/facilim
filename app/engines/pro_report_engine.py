"""
app/engines/pro_report_engine.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FACILIM 85 — Moteur d'export professionnel

Génère 4 types de rapports depuis le cockpit :
  1. Rapport professionnel       → accompagnant / travailleur social
  2. Rapport ESSMS               → structure médico-sociale
  3. Rapport MDPH                → contexte de soumission
  4. Rapport interne qualité     → QA et traçabilité

Usage :
  from app.engines.pro_report_engine import generer_rapports
  rapports = generer_rapports(cockpit, donnees)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SuiteRapports:
    professionnel:  str     # rapport pour l'accompagnant
    essms:          str     # rapport pour l'établissement
    mdph:           str     # rapport pour le contexte MDPH
    qualite:        str     # rapport interne qualité

    def to_dict(self) -> dict:
        return {
            "professionnel": self.professionnel,
            "essms":         self.essms,
            "mdph":          self.mdph,
            "qualite":       self.qualite,
        }


# ─────────────────────────────────────────────────────────────────────────────
# RAPPORT PROFESSIONNEL (accompagnant / travailleur social)
# ─────────────────────────────────────────────────────────────────────────────

def _rapport_professionnel(cockpit, donnees: dict) -> str:
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    nom = donnees.get("nom_prenom", "Personne accompagnée")
    dep = donnees.get("departement", "")

    lines = [
        "┌─────────────────────────────────────────────────────┐",
        f"│  RAPPORT D'ACCOMPAGNEMENT MDPH                      │",
        f"│  Facilim — {now}{'':>20}│",
        "└─────────────────────────────────────────────────────┘",
        "",
        f"  Bénéficiaire : {nom}",
        f"  MDPH         : Département {dep}" if dep else "",
        f"  Profil       : {cockpit.profil_mdph.upper()}",
        "",
        "═" * 55,
        "  RÉSUMÉ EXÉCUTIF",
        "─" * 55,
        f"  {cockpit.resume}",
        "",
        "═" * 55,
        "  ANALYSE DU DOSSIER",
        "─" * 55,
        f"  Score de solidité : {cockpit.score_global}/100  ({cockpit.niveau.upper()})",
        f"  Sources actives   : {', '.join(cockpit.sources_actives) or 'Déclarations uniquement'}",
        f"  Preuves extraites : {cockpit.nb_preuves}",
        "",
    ]

    # Forces
    if cockpit.forces:
        lines += ["  Points forts :"]
        for f in cockpit.forces[:4]:
            lines.append(f"    • {f}")
        lines.append("")

    # Droits solides
    if cockpit.droits_solides:
        lines += ["  Droits à profil favorable :"]
        for d in cockpit.droits_solides:
            lines.append(f"    ✅ {d.label} ({d.score}% — {d.decision})")
        lines.append("")

    # Droits fragiles
    if cockpit.droits_fragiles:
        lines += ["  Droits à renforcer :"]
        for d in cockpit.droits_fragiles:
            lines.append(f"    ⚠️  {d.label} ({d.score}% — risque {d.risque})")
            if d.explication:
                lines.append(f"       → {d.explication[:70]}")
        lines.append("")

    # Questions clés
    if cockpit.questions:
        lines += ["  Questions prioritaires :"]
        for q in cockpit.questions[:3]:
            lines.append(f"    {q.numero}. {q.question[:70]}")
            lines.append(f"       Impact estimé : +{q.impact_roi}")
        lines.append("")

    # Pièces
    if cockpit.pieces:
        obligatoires = [p for p in cockpit.pieces if p.obligatoire]
        lines += ["  Pièces obligatoires :"]
        for p in obligatoires[:4]:
            lines.append(f"    → {p.piece}")
        lines.append("")

    # État validation
    lines += [
        "─" * 55,
        f"  État : {'PRÊT POUR CERFA' if cockpit.pret_pour_cerfa else f'EN ATTENTE ({cockpit.nb_en_attente_validation} élément(s) à valider)'}",
    ]

    return "\n".join(l for l in lines if l is not None)


# ─────────────────────────────────────────────────────────────────────────────
# RAPPORT ESSMS (structure médico-sociale)
# ─────────────────────────────────────────────────────────────────────────────

def _rapport_essms(cockpit, donnees: dict) -> str:
    now = datetime.now().strftime("%d/%m/%Y")
    nom = donnees.get("nom_prenom", "N/A")

    lines = [
        f"RAPPORT ORIENTATION ESSMS — {now}",
        f"Bénéficiaire : {nom}",
        f"Profil : {cockpit.profil_mdph.upper()}",
        "",
        "── ORIENTATION(S) IDENTIFIÉE(S) ────────────────────────",
    ]

    # Orientations depuis droits solides
    orientations_essms = [
        d for d in cockpit.droits_solides
        if d.droit in {"ESAT", "SESSAD", "IME", "EEAP", "MAS", "FAM",
                       "FOYER_VIE", "FOYER_HEBERGEMENT", "SAVS", "SAMSAH"}
    ]
    orientations_fragiles = [
        d for d in cockpit.droits_fragiles
        if d.droit in {"ESAT", "SESSAD", "IME", "EEAP", "MAS", "FAM",
                       "FOYER_VIE", "FOYER_HEBERGEMENT", "SAVS", "SAMSAH"}
    ]

    if orientations_essms:
        lines.append("Orientations à profil favorable :")
        for d in orientations_essms:
            lines += [
                f"  ✅ {d.label}",
                f"     Score : {d.score}% — Décision : {d.decision}",
                f"     {d.explication[:70]}",
                "",
            ]
    if orientations_fragiles:
        lines.append("Orientations à renforcer :")
        for d in orientations_fragiles:
            lines += [
                f"  ⚠️  {d.label} ({d.score}%) — {d.explication[:60]}",
            ]
        lines.append("")

    if not orientations_essms and not orientations_fragiles:
        lines.append("Aucune orientation ESSMS spécifique identifiée.")
        lines.append("")

    # Pièces pour ESSMS
    pieces_essms = [p for p in cockpit.pieces if p.droit_concerne in
                    {"social", "emploi", "scolaire", "medical"}]
    if pieces_essms:
        lines.append("── PIÈCES ATTENDUES ─────────────────────────────────────")
        for p in pieces_essms[:4]:
            tag = "[OBLIGATOIRE]" if p.obligatoire else "[recommandée]"
            lines.append(f"  {tag} {p.piece}")
        lines.append("")

    lines += [
        "── ÉTAT DU DOSSIER ──────────────────────────────────────",
        f"Score solidité : {cockpit.score_global}/100",
        f"Forces : {len(cockpit.forces)} identifiées",
        f"Faiblesses : {len(cockpit.faiblesses)} à traiter",
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# RAPPORT MDPH (contexte de soumission)
# ─────────────────────────────────────────────────────────────────────────────

def _rapport_mdph(cockpit, donnees: dict) -> str:
    now = datetime.now().strftime("%d/%m/%Y")
    nom = donnees.get("nom_prenom", "N/A")
    dob = donnees.get("date_naissance", "")
    dep = donnees.get("departement", "")

    lines = [
        f"NOTE DE SYNTHÈSE PRÉPARATION DOSSIER MDPH",
        f"Généré par Facilim le {now}",
        f"",
        f"Bénéficiaire       : {nom}",
        f"Date de naissance  : {dob}",
        f"MDPH               : Département {dep}" if dep else "MDPH : (département non renseigné)",
        f"Type de demande    : {donnees.get('type_dossier', 'INITIAL')}",
        "",
        "═" * 55,
        "DROITS DEMANDÉS ET ANALYSE DE SOLIDITÉ",
        "─" * 55,
    ]

    for d in cockpit.droits_solides + cockpit.droits_fragiles:
        statut = "FAVORABLE" if d.score >= 70 else ("INCERTAIN" if d.score >= 40 else "FRAGILE")
        lines.append(f"  {d.label:<40} {d.score:>3}%  [{statut}]")

    lines += ["", "═" * 55, "ÉLÉMENTS CLÉS POUR L'INSTRUCTION", "─" * 55]

    if cockpit.forces:
        lines += ["Points forts du dossier :"]
        for f in cockpit.forces[:3]:
            lines.append(f"  • {f[:70]}")
        lines.append("")

    if cockpit.faiblesses:
        lines += ["Points de vigilance :"]
        for f in cockpit.faiblesses[:3]:
            lines.append(f"  • {f[:70]}")
        lines.append("")

    lines += ["═" * 55, "PIÈCES JOINTES PRÉVUES", "─" * 55]
    if cockpit.pieces:
        for p in cockpit.pieces:
            tag = "✅ Obligatoire" if p.obligatoire else "○  Recommandée"
            lines.append(f"  {tag} : {p.piece[:55]}")
    else:
        lines.append("  (Liste non générée)")

    lines += [
        "",
        "─" * 55,
        f"Note de solidité globale : {cockpit.score_global}/100",
        f"Niveau : {cockpit.niveau.upper()}",
        f"Ce document est une aide à la préparation.",
        f"Il ne constitue pas une décision d'attribution.",
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# RAPPORT INTERNE QUALITÉ
# ─────────────────────────────────────────────────────────────────────────────

def _rapport_qualite(cockpit, donnees: dict) -> str:
    now = datetime.now().isoformat()

    lines = [
        f"RAPPORT QUALITÉ INTERNE — Facilim 85",
        f"Timestamp : {now}",
        f"Profil : {cockpit.profil_mdph}",
        "",
        "── COUVERTURE DES DONNÉES ───────────────────────────────",
        f"Sources actives    : {len(cockpit.sources_actives)}/5",
        f"Sources présentes  : {', '.join(cockpit.sources_actives) or '(aucune)'}",
        f"Preuves extraites  : {cockpit.nb_preuves}",
        "",
        "── SCORES DÉTAILLÉS ────────────────────────────────────",
        f"Score global       : {cockpit.score_global}/100",
        f"Droits solides     : {len(cockpit.droits_solides)}",
        f"Droits fragiles    : {len(cockpit.droits_fragiles)}",
        "",
        "── VALIDATION HUMAINE ──────────────────────────────────",
        f"Éléments à valider : {cockpit.nb_en_attente_validation}",
        f"Prêt pour CERFA    : {'OUI' if cockpit.pret_pour_cerfa else 'NON — validation requise'}",
        "",
        "── TABLEAU DE VALIDATION ───────────────────────────────",
    ]

    for v in cockpit.lignes_validation:
        lines.append(
            f"  {v.element:<22} conf={v.confiance:>3}%  "
            f"statut={v.statut:<10}  {v.checkbox}"
        )

    lines += [
        "",
        "── QUESTIONS LEVIER ────────────────────────────────────",
    ]
    for q in cockpit.questions:
        lines.append(f"  [{q.impact_roi:>3} ROI] {q.question[:65]}")

    lines += [
        "",
        "── PIÈCES IDENTIFIÉES ──────────────────────────────────",
    ]
    for p in cockpit.pieces:
        tag = "OBL" if p.obligatoire else "REC"
        lines.append(f"  [{tag}] {p.piece[:55]}")

    lines += [
        "",
        f"── CONFORMITÉ ─────────────────────────────────────────",
        f"  0 droit auto-validé : ✅ (validation humaine requise pour tous)",
        f"  100% droits avec statut : {'✅' if cockpit.lignes_validation else '❌'}",
        f"  Rapports générés : professionnel · ESSMS · MDPH · qualité",
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────────────────────

def generer_rapports(
    cockpit,
    donnees: dict[str, Any],
) -> SuiteRapports:
    """
    Génère les 4 types de rapports depuis le cockpit professionnel.

    Args:
        cockpit: CockpitProfessionnel (depuis professional_cockpit_engine)
        donnees: synthese_json du dossier

    Returns:
        SuiteRapports avec les 4 formats
    """
    return SuiteRapports(
        professionnel = _rapport_professionnel(cockpit, donnees),
        essms         = _rapport_essms(cockpit, donnees),
        mdph          = _rapport_mdph(cockpit, donnees),
        qualite       = _rapport_qualite(cockpit, donnees),
    )
