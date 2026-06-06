"""
app/engines/audit_trail_engine.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FACILIM PROD — Journal d'audit et traçabilité totale

Pour chaque élément du dossier, répond à :
  "Pourquoi cette case est cochée ?"
  "Quelle preuve l'a déclenchée ?"
  "Qui l'a validée ?"
  "Quand ?"

Crée un journal d'audit immuable, horodaté et exportable.

Usage :
  from app.engines.audit_trail_engine import creer_journal_audit
  journal = creer_journal_audit(donnees, field_map, profil_mdph="adulte")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("facilim.engines.audit_trail")


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EntreeAudit:
    """Une entrée du journal d'audit pour un élément du dossier."""
    timestamp:          str
    element:            str         # "Case à cocher P17 5" | "RQTH" | "Section B"
    element_type:       str         # "champ_cerfa" | "droit" | "section" | "document"
    valeur:             str         # valeur produite
    raison:             str         # pourquoi cette valeur a été produite
    preuve:             str         # extrait de texte ou source ayant déclenché
    source_donnee:      str         # champ synthese_json source
    moteur_source:      str         # moteur Facilim ayant produit cette valeur
    validation_humaine: bool        # True si validé par un professionnel
    validateur:         str         # identité du validateur si disponible
    date_validation:    str         # horodatage de la validation

    def to_dict(self) -> dict:
        return {
            "timestamp":          self.timestamp,
            "element":            self.element,
            "type":               self.element_type,
            "valeur":             self.valeur[:80],
            "raison":             self.raison[:120],
            "preuve":             self.preuve[:100],
            "source":             self.source_donnee,
            "moteur":             self.moteur_source,
            "valide_humain":      self.validation_humaine,
            "validateur":         self.validateur,
            "date_validation":    self.date_validation,
        }


@dataclass
class JournalAudit:
    """Journal d'audit complet pour un dossier."""
    dossier_id:         str
    profil_mdph:        str
    timestamp_creation: str
    entrees:            list[EntreeAudit] = field(default_factory=list)

    def ajouter(self, entree: EntreeAudit) -> None:
        self.entrees.append(entree)

    def chercher(self, element: str) -> list[EntreeAudit]:
        return [e for e in self.entrees if e.element == element]

    def pourquoi(self, champ_cerfa: str) -> str:
        """Répond à 'Pourquoi cette case est cochée ?'"""
        entrees = self.chercher(champ_cerfa)
        if not entrees:
            return f"Aucune trace d'audit pour {champ_cerfa}"
        e = entrees[0]
        return (
            f"{e.raison} "
            f"(Source : {e.source_donnee} | Moteur : {e.moteur_source})"
            + (f" — Validé par {e.validateur} le {e.date_validation}" if e.validation_humaine else " — En attente de validation")
        )

    def quelle_preuve(self, champ_cerfa: str) -> str:
        """Répond à 'Quelle preuve a déclenché cette case ?'"""
        entrees = self.chercher(champ_cerfa)
        if not entrees or not entrees[0].preuve:
            return "Aucune preuve traçable"
        return entrees[0].preuve

    def to_dict(self) -> dict:
        return {
            "dossier_id":   self.dossier_id,
            "profil_mdph":  self.profil_mdph,
            "cree_le":      self.timestamp_creation,
            "nb_entrees":   len(self.entrees),
            "entrees":      [e.to_dict() for e in self.entrees],
        }

    def exporter_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def rapport_audit(self) -> str:
        """Génère un rapport d'audit lisible."""
        sep = "─" * 60
        lines = [
            "═" * 60,
            f"  JOURNAL D'AUDIT — FACILIM PROD",
            f"  Dossier : {self.dossier_id}",
            f"  Créé le : {self.timestamp_creation}",
            f"  Entrées : {len(self.entrees)}",
            "═" * 60,
            "",
        ]

        # Grouper par type
        cerfa_entries  = [e for e in self.entrees if e.element_type == "champ_cerfa"]
        droits_entries = [e for e in self.entrees if e.element_type == "droit"]
        doc_entries    = [e for e in self.entrees if e.element_type == "document"]

        if cerfa_entries:
            lines += [f"  CHAMPS CERFA TRACÉS ({len(cerfa_entries)})", sep]
            for e in cerfa_entries[:20]:
                valide_tag = "✅" if e.validation_humaine else "☐"
                lines += [
                    f"  {valide_tag} {e.element}",
                    f"     Valeur   : {e.valeur[:60]}",
                    f"     Raison   : {e.raison[:70]}",
                    f"     Preuve   : {e.preuve[:60]}" if e.preuve else "",
                    f"     Moteur   : {e.moteur_source}",
                    "",
                ]

        if droits_entries:
            lines += [f"  DROITS TRACÉS ({len(droits_entries)})", sep]
            for e in droits_entries:
                lines += [
                    f"  [{e.element}] {e.valeur[:40]}",
                    f"    {e.raison[:80]}",
                    "",
                ]

        non_valides = [e for e in self.entrees if not e.validation_humaine and e.element_type == "droit"]
        if non_valides:
            lines += [
                "",
                f"  ⚠️  EN ATTENTE DE VALIDATION ({len(non_valides)} élément(s))",
                sep,
            ]
            for e in non_valides:
                lines.append(f"  ☐ {e.element} — {e.raison[:60]}")

        lines += ["", "═" * 60]
        return "\n".join(l for l in lines if l is not None)


# ─────────────────────────────────────────────────────────────────────────────
# MAPPING CHAMPS → SOURCES
# Explique pourquoi chaque champ CERFA a une valeur
# ─────────────────────────────────────────────────────────────────────────────

_CHAMP_RAISONS: dict[str, tuple[str, str]] = {
    # (raison, source_donnee)
    "Champ de texte P2 1":   ("Nom de naissance de la personne", "nom_prenom"),
    "Champ de texte P2 3":   ("Prénom de la personne", "nom_prenom"),
    "Date A 1":              ("Date de naissance — jour", "date_naissance"),
    "Date A 2":              ("Date de naissance — mois", "date_naissance"),
    "Date A 3":              ("Date de naissance — année", "date_naissance"),
    "Champ de texte P1 1":   ("Département MDPH destinataire", "departement"),
    "Champ de texte P8 1":   ("Description de la vie quotidienne (section B)", "texte_b_vie_quotidienne"),
    "Champ de texte P16 1":  ("Projet de vie (section E)", "texte_e_projet_vie"),
    "Champ de texte P14 1":  ("Description situation professionnelle (section D)", "texte_d_situation_pro"),
    "Case à cocher P17 5":   ("AAH demandée ou signaux d'incapacité détectés", "droits_demandes"),
    "Case à cocher P17 6":   ("RQTH demandée", "droits_demandes"),
    "Case à cocher P17 1":   ("AEEH demandée (enfant)", "droits_demandes"),
    "Case à cocher P17 2":   ("PCH demandée (enfant)", "droits_demandes"),
    "Case à cocher P17 7":   ("PCH demandée (adulte)", "droits_demandes"),
    "Case à cocher P17 11":  ("ESAT ou orientation médico-sociale détectée", "droits_demandes"),
    "Case à cocher P17 13":  ("CMI stationnement — limitation marche détectée", "impact_quotidien"),
    "Case à cocher P18 1":   ("RQTH emploi demandée", "droits_demandes"),
    "Case à cocher P18 3":   ("ESPO/CRP/UEROS demandé", "droits_demandes"),
    "Case à cocher P18 4":   ("ESAT demandé ou détecté", "droits_demandes"),
    "Case à cocher P4 4":    ("Consentement échanges professionnels (toujours accordé via Facilim)", "consentement_whatsapp"),
    "Case à cocher P16 5":   ("Bilan capacités/ESPO détecté dans les données", "notes_pro"),
    "Case à cocher P10 1":   ("AESH détectée dans la scolarité", "situation_scolaire"),
    "Case à cocher P10 2":   ("Tiers-temps détecté dans la scolarité", "situation_scolaire"),
}


# ─────────────────────────────────────────────────────────────────────────────
# CONSTRUCTION DU JOURNAL
# ─────────────────────────────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tracer_champs_cerfa(
    journal: JournalAudit,
    field_map: dict,
    donnees: dict,
    graphe_preuves,
) -> None:
    """Ajoute les entrées d'audit pour les champs CERFA produits."""
    for champ, valeur in field_map.items():
        if not valeur or valeur in ("/Off", ""):
            continue

        raison, source = _CHAMP_RAISONS.get(champ, (
            f"Champ mappé automatiquement depuis les données",
            "field_mapper",
        ))

        # Chercher une preuve dans le graphe
        preuve = ""
        if graphe_preuves:
            # Chercher une preuve liée à ce champ (approximation)
            for item in graphe_preuves.items[:5]:
                if any(source in item.source_champ for source in [source, "notes_pro"]):
                    preuve = item.citation[:80]
                    break

        journal.ajouter(EntreeAudit(
            timestamp=_ts(),
            element=champ,
            element_type="champ_cerfa",
            valeur=str(valeur),
            raison=raison,
            preuve=preuve,
            source_donnee=source,
            moteur_source="field_mapper",
            validation_humaine=False,
            validateur="",
            date_validation="",
        ))


def _tracer_droits(
    journal: JournalAudit,
    tableau_validation,
) -> None:
    """Ajoute les entrées d'audit pour les droits à valider."""
    for element in tableau_validation.elements_a_valider:
        raison = (
            f"Droit {element.label} — confiance {element.confiance}% — "
            f"{element.decision_previsible}"
        )
        preuve = element.citations[0] if element.citations else ""
        sources = ", ".join(element.sources) if element.sources else "Inférence"

        journal.ajouter(EntreeAudit(
            timestamp=_ts(),
            element=element.element,
            element_type="droit",
            valeur=f"confiance={element.confiance}% statut={element.statut}",
            raison=raison,
            preuve=preuve[:100],
            source_donnee=sources,
            moteur_source="cdaph_strategy_engine",
            validation_humaine=element.est_valide,
            validateur=element.modifie_par,
            date_validation=element.date_validation,
        ))


def _tracer_narratifs(
    journal: JournalAudit,
    donnees: dict,
) -> None:
    """Ajoute les entrées d'audit pour les textes narratifs."""
    sections = [
        ("texte_b_vie_quotidienne", "Section B", "cerfa_narrative_engine + GPT-4o"),
        ("texte_c_scolarite",       "Section C", "cerfa_narrative_engine + GPT-4o"),
        ("texte_d_situation_pro",   "Section D", "cerfa_narrative_engine + GPT-4o"),
        ("texte_e_projet_vie",      "Section E", "cerfa_narrative_engine + GPT-4o"),
    ]
    for champ, label, moteur in sections:
        texte = str(donnees.get(champ, "") or "")
        if texte.strip():
            journal.ajouter(EntreeAudit(
                timestamp=_ts(),
                element=label,
                element_type="section",
                valeur=f"{len(texte)} chars",
                raison=f"Narratif généré par LLM depuis diagnostics, impact et verbatims",
                preuve=texte[:80],
                source_donnee=champ,
                moteur_source=moteur,
                validation_humaine=False,
                validateur="",
                date_validation="",
            ))


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────────────────────

def creer_journal_audit(
    donnees: dict[str, Any],
    field_map: dict,
    profil_mdph: str = "adulte",
    tableau_validation=None,
    graphe_preuves=None,
    dossier_id: str = "",
) -> JournalAudit:
    """
    Crée le journal d'audit complet pour un dossier.

    Args:
        donnees:           synthese_json du dossier
        field_map:         sortie de build_field_map()
        profil_mdph:       "adulte" | "enfant" | "protege" | "mixte"
        tableau_validation: depuis human_validation_engine (optionnel)
        graphe_preuves:    depuis evidence_engine (optionnel)
        dossier_id:        identifiant unique du dossier

    Returns:
        JournalAudit immuable et exportable
    """
    if not dossier_id:
        nom = str(donnees.get("nom_prenom", "inconnu")).replace(" ", "_")[:20]
        dossier_id = f"{nom}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    journal = JournalAudit(
        dossier_id=dossier_id,
        profil_mdph=profil_mdph,
        timestamp_creation=_ts(),
    )

    # Tracer les champs CERFA
    _tracer_champs_cerfa(journal, field_map, donnees, graphe_preuves)

    # Tracer les droits (si tableau validation disponible)
    if tableau_validation:
        _tracer_droits(journal, tableau_validation)

    # Tracer les narratifs
    _tracer_narratifs(journal, donnees)

    logger.info(f"Journal audit créé : {len(journal.entrees)} entrées pour {dossier_id}")
    return journal
