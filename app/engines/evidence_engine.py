"""
app/engines/evidence_engine.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FACILIM 80 — Moteur de preuves (Evidence Engine)

Construit un graphe de preuves traçables depuis toutes les sources.
Chaque information est taggée avec : source, confiance, citation exacte.

RÈGLE ABSOLUE :
  Aucune preuve inventée.
  Chaque citation doit être un extrait réel d'un champ de donnees.
  Chaque source doit correspondre à un champ réellement présent.

Usage :
  from app.engines.evidence_engine import construire_graphe_preuves
  graphe = construire_graphe_preuves(donnees, profil_mdph="adulte")
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("facilim.engines.evidence")

# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EvidenceItem:
    """Une preuve traçable."""
    information:        str     # Description lisible ("besoin aide toilette")
    source_type:        str     # "WhatsApp" | "Document" | "Narratif" | "Déclaration" | "Inférence"
    source_champ:       str     # Champ exact dans donnees (ex: "_verbatim_b")
    confiance:          float   # 0.0 à 1.0
    citation:           str     # Extrait textuel exact (jamais inventé)
    droits_concernes:   list[str]   # Droits soutenus par cette preuve
    section_cerfa:      str         # Section CERFA concernée ("B" | "C" | "D" | "E" | "identite")

    def to_dict(self) -> dict:
        return {
            "information":      self.information,
            "source_type":      self.source_type,
            "source_champ":     self.source_champ,
            "confiance":        round(self.confiance, 2),
            "citation":         self.citation[:150],
            "droits_concernes": self.droits_concernes,
            "section_cerfa":    self.section_cerfa,
        }


@dataclass
class EvidenceGraph:
    """Graphe complet des preuves pour un dossier."""
    items:                  list[EvidenceItem]
    sources_presentes:      list[str]   # Types de sources avec contenu
    sources_absentes:       list[str]   # Types de sources vides ou absentes
    nb_preuves_total:       int
    nb_preuves_par_droit:   dict[str, int]
    resume_preuves:         str

    def preuves_pour_droit(self, droit: str) -> list[EvidenceItem]:
        return [item for item in self.items if droit in item.droits_concernes]

    def preuves_par_source(self, source_type: str) -> list[EvidenceItem]:
        return [item for item in self.items if item.source_type == source_type]

    def to_dict(self) -> dict:
        return {
            "items":                [i.to_dict() for i in self.items],
            "sources_presentes":    self.sources_presentes,
            "sources_absentes":     self.sources_absentes,
            "nb_preuves":           self.nb_preuves_total,
            "nb_par_droit":         self.nb_preuves_par_droit,
            "resume":               self.resume_preuves,
        }


# ─────────────────────────────────────────────────────────────────────────────
# CONFIDENCES PAR SOURCE
# ─────────────────────────────────────────────────────────────────────────────

_CONFIANCE_SOURCE = {
    "WhatsApp":     0.90,   # Verbatim direct de la personne — très fort
    "Document":     0.88,   # Document professionnel (PCR, bilan, attestation)
    "Narratif":     0.78,   # Texte généré par Facilim (LLM) — bon mais non verbatim
    "Déclaration":  0.72,   # Déclaration saisie par le professionnel
    "Inférence":    0.62,   # Inférence calculée par le moteur
}

# ─────────────────────────────────────────────────────────────────────────────
# MAPPINGS INFORMATION → DROITS
# ─────────────────────────────────────────────────────────────────────────────

_PATTERNS_DROITS: list[tuple[str, list[str], list[str], str]] = [
    # (pattern, droits_concernes, informations_label, section_cerfa)

    # Aide humaine / AVQ
    (r"aide.{0,20}(toilette|douche|lavage|corps|hygi[eè]ne|lever)",
     ["PCH", "AAH"], "Besoin d'aide pour les soins corporels", "B"),
    (r"aide.{0,20}(habillage|s'habiller|v[eê]tements?)",
     ["PCH"], "Besoin d'aide pour l'habillage", "B"),
    (r"aide.{0,20}(repas|manger|cuisiner|alimentation)",
     ["PCH"], "Besoin d'aide pour l'alimentation", "B"),
    (r"tierce personne|aide humaine quotidienne",
     ["PCH", "AAH"], "Besoin de tierce personne documenté", "B"),

    # Mobilité
    (r"fauteuil roulant|en fauteuil",
     ["PCH", "CMI_STATIONNEMENT"], "Utilisation d'un fauteuil roulant", "B"),
    (r"canne|b[eé]quille|d[eé]ambulateur",
     ["PCH", "CMI_STATIONNEMENT"], "Aide à la mobilité (canne/béquilles)", "B"),
    (r"marche.{0,20}(limit[eé]e?|difficile|p[eé]nible|\d+.{0,5}m[eè]tres?)",
     ["CMI_STATIONNEMENT", "PCH"], "Limitation de la marche documentée", "B"),
    (r"p[eé]rim[eè]tre.{0,15}march|\d+.{0,5}m[eè]tres?",
     ["CMI_STATIONNEMENT"], "Distance de marche précisée", "B"),
    (r"ne peut (pas|plus).{0,20}(marcher|se d[eé]placer|sortir seul)",
     ["PCH", "CMI_STATIONNEMENT"], "Impossibilité de déplacement autonome", "B"),

    # Impact professionnel
    (r"arr[eê]t.{0,20}(longue dur[eé]e|travail|\d+.{0,5}(ans?|mois))",
     ["AAH", "RQTH"], "Arrêt de travail prolongé", "D"),
    (r"invalidit[eé]|pension d.invalidit[eé]|\d[eè]me.{0,10}cat[eé]gorie",
     ["AAH"], "Invalidité documentée", "D"),
    (r"inapte|inaptitude.{0,15}(poste|travail|emploi)",
     ["RQTH", "AAH"], "Inaptitude au travail déclarée", "D"),
    (r"sans emploi.{0,20}(depuis|\d+.{0,5}(ans?|mois))",
     ["AAH", "RQTH"], "Inactivité professionnelle prolongée", "D"),
    (r"ne peut (pas|plus).{0,20}(travailler|reprendre|exercer)",
     ["AAH", "RQTH"], "Impossibilité de retour à l'emploi", "D"),
    (r"accident.{0,15}travail|\bAT\b.{0,5}(2[0-9]{3}|s[eé]quelles?)",
     ["RQTH", "AAH"], "Accident du travail documenté", "D"),
    (r"restriction.{0,15}(emploi|travail|poste)",
     ["RQTH"], "Restrictions médicales au travail", "D"),
    (r"m[eé]decin.{0,10}travail|am[eé]nagement.{0,15}poste",
     ["RQTH"], "Suivi médecin du travail / aménagement poste", "D"),

    # Taux / incapacité
    (r"taux.{0,10}(80|90|100)\s*%|incapacit[eé].{0,15}(80|90|100)",
     ["AAH", "CMI_STATIONNEMENT"], "Taux d'incapacité ≥ 80% documenté", "B"),

    # AEEH / enfant
    (r"AESH|AVS.{0,15}(individuelle?|mutualis[eé]e?|\d+.{0,5}h)",
     ["AEEH", "SESSAD"], "AESH/AVS présente et documentée", "C"),
    (r"tiers.?temps.{0,20}(accord|confirm|attribu)",
     ["AEEH"], "Tiers-temps accordé documenté", "C"),
    (r"SESSAD|service.{0,15}(éducation|soin).{0,15}sp[eé]cialis[eé]",
     ["AEEH", "SESSAD"], "SESSAD identifié ou en place", "C"),
    (r"GEVASCO|évaluation.{0,15}scolaire.{0,15}sp[eé]cialis[eé]",
     ["AEEH"], "GEVASCO présent", "C"),
    (r"IME|institut.{0,20}m[eé]dico.{0,5}[eé]ducatif",
     ["AEEH", "IME"], "IME identifié", "C"),

    # Psychique / SAVS
    (r"bipolaire|trouble.{0,10}bipolaire",
     ["AAH", "SAVS"], "Trouble bipolaire documenté", "B"),
    (r"schizophr[eé]nie|psychose",
     ["AAH", "SAVS", "ESAT"], "Schizophrénie/psychose documentée", "B"),
    (r"(bons?|mauvais?).{0,10}jours?|épisodes?.{0,15}(dépressif|maniaque|difficile)",
     ["AAH", "SAVS"], "Variabilité des capacités documentée", "B"),
    (r"hospitalis.{0,10}(psychiatr|\d+.{0,10}fois)",
     ["AAH"], "Hospitalisations psychiatriques", "B"),

    # ESAT / DI
    (r"\bESAT\b|milieu prot[eé]g[eé]|travail.{0,10}adapt[eé]",
     ["ESAT"], "ESAT / milieu protégé identifié", "D"),
    (r"d[eé]ficience.{0,15}intellectuelle|trisomie|\bDI\b.{0,5}(l[eé]g[eè]re|mod[eé]r[eé]e)",
     ["ESAT", "AAH", "SESSAD"], "Déficience intellectuelle documentée", "B"),

    # Urgence
    (r"renouvellement.{0,20}(urgent|[eé]ch[eé]ance|dans.{0,10}mois)",
     ["RQTH", "AAH", "AEEH"], "Urgence renouvellement identifiée", "B"),

    # Projets / ESPO
    (r"pas de projet|sans orientation|bilan.{0,10}capacit[eé]s?",
     ["ESPO"], "Absence de projet professionnel → ESPO pertinent", "E"),
    (r"\bESPO\b|orientation.{0,15}professionnelle.{0,15}recommand",
     ["ESPO"], "ESPO recommandé ou identifié", "E"),

    # AVPF
    (r"r[eé]duction.{0,15}activit[eé]|mi-temps.{0,10}(aidant|parent)",
     ["AVPF"], "Réduction d'activité parentale documentée", "B"),

    # PCH complémentaires
    (r"gastrostomie|sonde|trachéotomie",
     ["PCH"], "Soins médicaux complexes (gastrostomie/sonde)", "B"),
    (r"risque.{0,15}(chute|fugue|mise en danger)",
     ["PCH"], "Risque de sécurité documenté", "B"),
    (r"dépendance.{0,15}(totale|compl[eè]te)|grabataire",
     ["PCH", "MAS"], "Dépendance totale documentée", "B"),
]


# ─────────────────────────────────────────────────────────────────────────────
# EXTRACTION DES PREUVES PAR SOURCE
# ─────────────────────────────────────────────────────────────────────────────

def _extraire_citation(texte: str, pattern: str, max_chars: int = 120) -> str:
    """Extrait un fragment contextuel autour d'un match. Jamais inventé."""
    m = re.search(pattern, texte, re.IGNORECASE)
    if not m:
        return texte[:max_chars].strip()
    start = max(0, m.start() - 40)
    end   = min(len(texte), m.end() + 60)
    fragment = texte[start:end].strip()
    return fragment[:max_chars]


def _tagger_preuves(texte: str, source_type: str, source_champ: str) -> list[EvidenceItem]:
    """Extrait toutes les preuves d'un texte donné selon les patterns."""
    if not texte or not texte.strip():
        return []

    texte_l = texte.lower()
    confiance = _CONFIANCE_SOURCE.get(source_type, 0.70)
    items: list[EvidenceItem] = []
    seen_patterns: set[str] = set()  # évite les doublons

    for pattern, droits, label, section in _PATTERNS_DROITS:
        if pattern in seen_patterns:
            continue
        if re.search(pattern, texte_l, re.IGNORECASE):
            citation = _extraire_citation(texte, pattern)
            # Vérification anti-invention : la citation doit être dans le texte original
            if citation.lower() in texte_l or any(w in texte_l for w in citation.lower().split()[:3]):
                items.append(EvidenceItem(
                    information=label,
                    source_type=source_type,
                    source_champ=source_champ,
                    confiance=confiance,
                    citation=citation,
                    droits_concernes=droits,
                    section_cerfa=section,
                ))
                seen_patterns.add(pattern)

    return items


def _extraire_whatsapp(donnees: dict) -> list[EvidenceItem]:
    """Extrait les preuves des verbatims WhatsApp."""
    items: list[EvidenceItem] = []

    # Verbatims par section
    for champ, section in [
        ("_verbatim_b", "B"), ("_verbatim_c", "C"),
        ("_verbatim_d", "D"), ("_verbatim_e", "E"),
    ]:
        lst = donnees.get(champ) or []
        if isinstance(lst, list):
            for verbatim in lst:
                if isinstance(verbatim, str) and verbatim.strip():
                    preuves = _tagger_preuves(verbatim, "WhatsApp", champ)
                    items.extend(preuves)

    # Expression directe
    expr = str(donnees.get("expression_directe", "") or "")
    if expr.strip():
        items.extend(_tagger_preuves(expr, "WhatsApp", "expression_directe"))

    return items


def _extraire_documents(donnees: dict) -> list[EvidenceItem]:
    """Extrait les preuves des documents professionnels."""
    items: list[EvidenceItem] = []

    # Notes pro (PCR, bilans, comptes-rendus)
    notes = str(donnees.get("notes_pro", "") or "")
    if notes.strip():
        items.extend(_tagger_preuves(notes, "Document", "notes_pro"))

    # Document knowledge (extraction structurée)
    dk = donnees.get("_document_knowledge") or {}
    if isinstance(dk, dict):
        for categorie, liste in dk.items():
            if not isinstance(liste, list):
                continue
            for item in liste:
                if isinstance(item, dict):
                    valeur = str(item.get("valeur", "") or "")
                    if valeur.strip():
                        champ = f"_document_knowledge.{categorie}"
                        items.extend(_tagger_preuves(valeur, "Document", champ))

    return items


def _extraire_narratifs(donnees: dict) -> list[EvidenceItem]:
    """Extrait les preuves des narratifs générés (B/C/D/E)."""
    items: list[EvidenceItem] = []

    champs_sections = [
        ("texte_b_vie_quotidienne", "B"),
        ("texte_c_scolarite", "C"),
        ("texte_d_situation_pro", "D"),
        ("texte_e_projet_vie", "E"),
    ]
    for champ, section in champs_sections:
        texte = str(donnees.get(champ, "") or "")
        if texte.strip():
            preuves = _tagger_preuves(texte, "Narratif", champ)
            # Filtrer au bon section CERFA
            for p in preuves:
                p.section_cerfa = section
            items.extend(preuves)

    return items


def _extraire_declarations(donnees: dict) -> list[EvidenceItem]:
    """Extrait les preuves des déclarations saisies (diagnostics, impact, etc.)."""
    items: list[EvidenceItem] = []

    champs_declarations = [
        ("diagnostics", "B"),
        ("impact_quotidien", "B"),
        ("restrictions_emploi", "D"),
        ("statut_emploi", "D"),
        ("situation_scolaire", "C"),
        ("aidant_besoins", "B"),
    ]
    for champ, section in champs_declarations:
        texte = str(donnees.get(champ, "") or "")
        if texte.strip():
            preuves = _tagger_preuves(texte, "Déclaration", champ)
            for p in preuves:
                p.section_cerfa = section
            items.extend(preuves)

    return items


def _extraire_inferences(donnees: dict) -> list[EvidenceItem]:
    """Extrait les preuves des inférences calculées par le moteur."""
    items: list[EvidenceItem] = []
    try:
        from app.engines.inferencer_mdph import inferer_contexte_mdph
        ctx = inferer_contexte_mdph(donnees, donnees.get("profil_principal", ""), "adulte")
        for h in ctx.hypotheses:
            if h.fragment_confirmatif:
                # La description_complete est une inférence (jamais un verbatim)
                # Le fragment est extrait du texte réel → preuve traçable
                items.append(EvidenceItem(
                    information=h.inference[:80],
                    source_type="Inférence",
                    source_champ=h.signal_source or "inferencer_mdph",
                    confiance=_CONFIANCE_SOURCE["Inférence"],
                    citation=h.fragment_confirmatif[:120],
                    droits_concernes=[],  # les inférences s'appliquent à toutes les sections
                    section_cerfa="B",
                ))
    except Exception:
        pass  # Le moteur d'inférence est optionnel ici
    return items


# ─────────────────────────────────────────────────────────────────────────────
# DÉDUPLICATION ET ENRICHISSEMENT
# ─────────────────────────────────────────────────────────────────────────────

def _dedupliquer(items: list[EvidenceItem]) -> list[EvidenceItem]:
    """
    Supprime les doublons tout en conservant la preuve avec la meilleure confiance.
    Critère : même information + même droit → garder la plus haute confiance.
    """
    seen: dict[tuple[str, str], EvidenceItem] = {}
    for item in items:
        key = (item.information.lower()[:40], "|".join(sorted(item.droits_concernes)))
        existing = seen.get(key)
        if existing is None or item.confiance > existing.confiance:
            seen[key] = item
    return sorted(seen.values(), key=lambda x: -x.confiance)


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────────────────────

def construire_graphe_preuves(
    donnees: dict[str, Any],
    profil_mdph: str = "adulte",
) -> EvidenceGraph:
    """
    Construit le graphe de preuves complet pour un dossier.

    Agrège depuis : WhatsApp · Documents · Narratifs · Déclarations · Inférences

    ANTI-INVENTION : Aucune preuve ne peut être produite si sa source
    (le champ donnees correspondant) est vide ou absente.

    Args:
        donnees:     synthese_json du dossier
        profil_mdph: "adulte" | "enfant" | "protege" | "mixte"

    Returns:
        EvidenceGraph traçable et auditable
    """
    all_items: list[EvidenceItem] = []
    sources_presentes: list[str] = []
    sources_absentes:  list[str] = []

    # WhatsApp
    wa_items = _extraire_whatsapp(donnees)
    all_items.extend(wa_items)
    if wa_items:
        sources_presentes.append("WhatsApp")
    else:
        sources_absentes.append("WhatsApp (aucun verbatim collecté)")

    # Documents
    doc_items = _extraire_documents(donnees)
    all_items.extend(doc_items)
    if doc_items:
        sources_presentes.append("Document")
    else:
        sources_absentes.append("Document (aucun bilan ou PCR joint)")

    # Narratifs LLM
    narr_items = _extraire_narratifs(donnees)
    all_items.extend(narr_items)
    if narr_items:
        sources_presentes.append("Narratif")
    else:
        sources_absentes.append("Narratif (textes B/C/D/E non générés)")

    # Déclarations
    decl_items = _extraire_declarations(donnees)
    all_items.extend(decl_items)
    if decl_items:
        sources_presentes.append("Déclaration")
    else:
        sources_absentes.append("Déclaration (données saisies absentes)")

    # Inférences
    inf_items = _extraire_inferences(donnees)
    all_items.extend(inf_items)
    if inf_items:
        sources_presentes.append("Inférence")

    # Déduplication
    items_nets = _dedupliquer(all_items)

    # Comptage par droit
    nb_par_droit: dict[str, int] = {}
    for item in items_nets:
        for droit in item.droits_concernes:
            nb_par_droit[droit] = nb_par_droit.get(droit, 0) + 1

    # Résumé
    nb = len(items_nets)
    droits_couverts = len(nb_par_droit)
    resume = (
        f"{nb} preuve(s) extraite(s) depuis {len(sources_presentes)} source(s). "
        f"{droits_couverts} droit(s) soutenu(s) par au moins 1 preuve."
        + (f" Sources manquantes : {', '.join(sources_absentes[:2])}" if sources_absentes else "")
    )

    logger.debug(f"EvidenceGraph : {nb} preuves · {sources_presentes}")

    return EvidenceGraph(
        items=items_nets,
        sources_presentes=sources_presentes,
        sources_absentes=sources_absentes,
        nb_preuves_total=nb,
        nb_preuves_par_droit=nb_par_droit,
        resume_preuves=resume,
    )
