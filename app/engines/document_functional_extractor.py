"""
app/engines/document_functional_extractor.py — Extracteur fonctionnel de bilans.

Sprint P0.1 — MVP extraction métier des bilans transmis.

Sources reconnues : PCR · ESRP · ESPO · UEROS · Bilans médico-sociaux
                    Bilans psychologiques · Neuropsychologiques · Synthèses

Philosophie :
  - Extraction fidèle uniquement — aucune inférence, aucune déduction
  - Chaque item conserve son extrait source exact (auditabilité)
  - Le moteur narratif n'est PAS modifié dans ce sprint
  - La valeur est mesurée par la réduction des questions WhatsApp

8 champs à fort impact CERFA :
  limitations_fonctionnelles · restrictions_medicales · besoins · freins
  ressources · projets · verbatim · chronologie

Stockage : donnees["_document_knowledge"] dans synthese_json existant.
Aucune migration SQL nécessaire dans ce sprint.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("facilim.engines.document_extractor")


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURES DE DONNÉES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ExtractedItem:
    """Unité atomique d'information extraite d'un document."""
    valeur:         str    # "station debout prolongée difficile"
    source:         str    # "Bilan PCR NAIT ALI.docx"
    extrait_source: str    # Fragment exact du document ayant produit cet item


@dataclass
class DocumentKnowledge:
    """Base de connaissances extraite d'un document professionnel."""

    # Les 8 champs à fort impact CERFA
    limitations_fonctionnelles: list[ExtractedItem] = field(default_factory=list)
    restrictions_medicales:     list[ExtractedItem] = field(default_factory=list)
    besoins:                    list[ExtractedItem] = field(default_factory=list)
    freins:                     list[ExtractedItem] = field(default_factory=list)
    ressources:                 list[ExtractedItem] = field(default_factory=list)
    projets:                    list[ExtractedItem] = field(default_factory=list)
    verbatim:                   list[ExtractedItem] = field(default_factory=list)
    chronologie:                list[ExtractedItem] = field(default_factory=list)

    # Métadonnées
    source_document: str = ""
    type_document:   str = ""   # "PCR" | "ESRP" | "ESPO" | "UEROS" | "bilan" | "autre"
    date_document:   str = ""
    nb_items_total:  int = 0

    def to_dict(self) -> dict:
        """Sérialisation JSON pour stockage dans synthese_json."""
        champs = [
            "limitations_fonctionnelles", "restrictions_medicales", "besoins",
            "freins", "ressources", "projets", "verbatim", "chronologie",
        ]
        return {
            **{c: [{"valeur": i.valeur, "source": i.source, "extrait_source": i.extrait_source}
                   for i in getattr(self, c)]
               for c in champs},
            "_meta": {
                "source_document": self.source_document,
                "type_document":   self.type_document,
                "date_document":   self.date_document,
                "nb_items_total":  self.nb_items_total,
            },
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DocumentKnowledge":
        """Désérialisation depuis synthese_json."""
        champs = [
            "limitations_fonctionnelles", "restrictions_medicales", "besoins",
            "freins", "ressources", "projets", "verbatim", "chronologie",
        ]
        meta = d.get("_meta", {})
        obj = cls(
            source_document=meta.get("source_document", ""),
            type_document=meta.get("type_document", ""),
            date_document=meta.get("date_document", ""),
            nb_items_total=meta.get("nb_items_total", 0),
        )
        for c in champs:
            setattr(obj, c, [
                ExtractedItem(
                    valeur=i.get("valeur", ""),
                    source=i.get("source", ""),
                    extrait_source=i.get("extrait_source", ""),
                )
                for i in d.get(c, []) if i.get("valeur")
            ])
        return obj


@dataclass
class QuestionSupprimee:
    """Question WhatsApp supprimée grâce à l'extraction documentaire."""
    question_label:    str    # "Impact du handicap sur la vie quotidienne"
    champ_checklist:   str    # "impact_quotidien"
    source_knowledge:  str    # "limitations_fonctionnelles"
    nb_items_source:   int    # nombre d'items ayant justifié la suppression


@dataclass
class ExtractionAudit:
    """Audit de l'extraction + mesure du ROI en questions évitées."""

    # Comptage par champ
    limitations_fonctionnelles: int = 0
    restrictions_medicales:     int = 0
    besoins:                    int = 0
    freins:                     int = 0
    ressources:                 int = 0
    projets:                    int = 0
    verbatim:                   int = 0
    chronologie:                int = 0

    # Totaux
    total_items:     int = 0
    champs_alimentes: int = 0    # nb champs avec ≥ 1 item

    # ROI — questions supprimées enrichies
    questions_supprimees: list[QuestionSupprimee] = field(default_factory=list)
    nb_questions_avant:   int = 0
    nb_questions_apres:   int = 0
    gain_questions:       int = 0

    # Méta
    type_document:   str = ""
    source_document: str = ""
    date_extraction: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# DÉTECTION DU TYPE DE DOCUMENT
# ─────────────────────────────────────────────────────────────────────────────

_PATTERNS_TYPE: dict[str, list[str]] = {
    "PCR":   [r"prestation conseil", r"prestation.{0,5}repérage", r"\bpcr\b", r"bilan pcr"],
    "ESRP":  [r"\besrp\b", r"établissement.{0,20}réadaptation professionnelle",
              r"centre.{0,20}réadaptation professionnelle"],
    "ESPO":  [r"\bespo\b", r"établissement.{0,20}pré.?orientation",
              r"centre.{0,20}pré.?orientation"],
    "UEROS": [r"\bueros\b", r"cérébro.?lésé", r"réentraînement.{0,20}orientation"],
    "bilan": [r"bilan.{0,20}(psychologique|neuropsychologique|médico.?social|ergothérap|compétences)",
              r"synthèse.{0,20}(accompagnement|parcours|bilan)",
              r"compte.?rendu.{0,20}(médical|hospitalier|psychiatrique)",
              r"rapport.{0,20}(infirmier|assistante sociale|médecin du travail)",
              r"évaluation.{0,20}(pluridisciplinaire|fonctionnelle|cognitive)"],
}


def detecter_type_document(texte: str) -> str:
    """Identifie le type de document professionnel."""
    t = texte.lower()
    for type_doc, patterns in _PATTERNS_TYPE.items():
        if any(re.search(p, t, re.IGNORECASE) for p in patterns):
            return type_doc
    return "autre"


# ─────────────────────────────────────────────────────────────────────────────
# CLOISONNEMENT DU PRESCRIPTEUR (RGPD)
# ─────────────────────────────────────────────────────────────────────────────
# Un bilan (PCR/ESRP/France Travail…) contient une section prescripteur :
# conseiller référent, son nom, son email, sa structure. Ces données ne sont
# JAMAIS celles de l'usager et ne doivent entrer NI dans son identité, NI dans
# un récit, NI sur le CERFA. Deux défenses complémentaires :
#   1. le prompt d'extraction l'interdit explicitement (voir _PROMPT_EXTRACTION) ;
#   2. ce garde-fou déterministe écarte tout item dont la VALEUR est une
#      coordonnée de tiers, et nettoie emails/téléphones des extraits d'audit.

_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+", re.IGNORECASE)
# Téléphone FR : 0X ou +33X suivi de 4 paires de chiffres (séparateurs tolérés).
_RE_TEL = re.compile(r"(?:\+33|0)\s?[1-9](?:[\s.\-]?\d{2}){4}")

# Étiquettes de rôle du rédacteur/prescripteur. Recherchées EN DÉBUT de valeur
# (« Conseillère : S. Martin », « Référent : … ») pour viser l'identité du
# professionnel, sans écarter une mention légitime (« besoin d'un conseiller »).
_MARQUEURS_PRESCRIPTEUR_DEBUT = (
    "prescripteur", "conseiller", "conseillere", "referent", "referente",
    "redige par", "redigee par", "redacteur", "redactrice", "signataire",
)


def _sans_accents_min(texte: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFD", (texte or "").lower().strip())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _scrub_pii(texte: str) -> str:
    """Retire emails et numéros de téléphone d'un texte (coordonnées de tiers)."""
    t = _RE_EMAIL.sub("", texte)
    t = _RE_TEL.sub("", t)
    return re.sub(r"\s{2,}", " ", t).strip(" ;,-—\t")


def cloisonner_prescripteur_item(valeur: str, extrait: str) -> tuple[str, str] | None:
    """
    Garde-fou RGPD déterministe sur un item extrait.

    Écarte l'item (retourne None) si la VALEUR est :
      - une coordonnée de tiers (email / téléphone), ou
      - une identité de rédacteur/prescripteur (commence par « Conseiller : »,
        « Référent : », « Rédigé par … », etc.).
    Sinon conserve l'item en nettoyant une éventuelle coordonnée résiduelle dans
    l'extrait source (audit).
    """
    if _RE_EMAIL.search(valeur) or _RE_TEL.search(valeur):
        return None
    _v = _sans_accents_min(valeur)
    if any(_v.startswith(m) for m in _MARQUEURS_PRESCRIPTEUR_DEBUT):
        return None
    return valeur, _scrub_pii(extrait)


# ─────────────────────────────────────────────────────────────────────────────
# MAPPING VERS LA CHECKLIST AGENT
# ─────────────────────────────────────────────────────────────────────────────

# champ_knowledge → liste de champs checklist couverts
_MAPPING_COVERAGE: dict[str, list[str]] = {
    "limitations_fonctionnelles": ["impact_quotidien"],
    "restrictions_medicales":     ["impact_quotidien"],
    "freins":                     ["qualification_section_d", "historique_mdph"],
    "projets":                    ["qualification_section_d", "projet_orientation", "droits_demandes"],
    "verbatim":                   ["expression_directe"],
    "chronologie":                ["date_debut_limitations"],
    "besoins":                    ["droits_demandes"],
    "ressources":                 [],   # enrichissement section E — ne couvre aucun champ obligatoire
}


def questions_supprimees(
    knowledge: dict[str, Any],
    checklist_agent: list[dict],
) -> list[QuestionSupprimee]:
    """
    Calcule les questions WhatsApp rendues inutiles par l'extraction documentaire.
    Retourne la liste enrichie avec source_knowledge.
    """
    # Construire le reverse mapping : champ_checklist → champ_knowledge responsable
    reverse: dict[str, str] = {}
    for champ_k, champs_c in _MAPPING_COVERAGE.items():
        for c in champs_c:
            if c not in reverse:
                reverse[c] = champ_k

    supprimees: list[QuestionSupprimee] = []
    for item in checklist_agent:
        champ_id = item.get("id", "")
        if champ_id in reverse:
            champ_k = reverse[champ_id]
            items_k  = knowledge.get(champ_k, [])
            if items_k:   # le champ documentaire est renseigné
                supprimees.append(QuestionSupprimee(
                    question_label=item.get("label", champ_id),
                    champ_checklist=champ_id,
                    source_knowledge=champ_k,
                    nb_items_source=len(items_k),
                ))
    return supprimees


def filtrer_couverts_par_document(
    ids_manquants: list[str],
    knowledge: dict[str, Any],
) -> list[str]:
    """
    Retourne la liste des IDs de champs encore manquants après couverture documentaire.
    Un champ est couvert si le champ DocumentKnowledge correspondant contient ≥ 1 item.
    """
    champs_couverts: set[str] = set()
    for champ_k, champs_c in _MAPPING_COVERAGE.items():
        if knowledge.get(champ_k):
            champs_couverts.update(champs_c)
    return [mid for mid in ids_manquants if mid not in champs_couverts]


# ─────────────────────────────────────────────────────────────────────────────
# EXTRACTION LLM
# ─────────────────────────────────────────────────────────────────────────────

_PROMPT_EXTRACTION = """Tu es un expert en dossiers MDPH et bilans médico-sociaux.

MISSION : Extraire les informations utiles de ce document professionnel et les classer.

RÈGLE ABSOLUE : extraire UNIQUEMENT ce qui est explicitement écrit.
Aucune inférence. Aucune déduction. Aucune interprétation clinique.
Si une information est absente → ne pas créer d'item.

RÈGLE DE CLOISONNEMENT (RGPD) — IMPÉRATIVE :
Le document peut contenir une section « prescripteur / rédacteur » : conseiller
référent, France Travail / Pôle emploi / Cap emploi / mission locale, médecin ou
psychologue rédacteur, avec leur NOM, EMAIL, TÉLÉPHONE, structure et signature.
Ces personnes ne sont PAS l'usager. N'extrais JAMAIS leur identité ni leurs
coordonnées. N'inclus AUCUN email ni numéro de téléphone dans tes items. Tu
extrais seulement ce qui décrit la situation de l'USAGER (la personne concernée
par le dossier MDPH), jamais le professionnel qui a rédigé le bilan.

Pour chaque information extraite, fournir OBLIGATOIREMENT :
- "valeur" : reformulation courte et précise (max 15 mots)
- "extrait_source" : fragment exact copié du document (max 100 caractères)

CHAMPS À REMPLIR (uniquement les 8 suivants) :

1. limitations_fonctionnelles
   Ce que la personne ne peut pas faire ou fait difficilement.
   Exemples : "station debout prolongée difficile", "marche limitée"

2. restrictions_medicales
   Contre-indications formelles médicales ou professionnelles.
   Exemples : "port de charges contre-indiqué", "pas de travail en hauteur"

3. besoins
   Ce dont la personne a besoin (accompagnement, aide, suivi).
   Exemples : "suivi médico-psychologique", "aide à la définition d'un projet"

4. freins
   Obstacles identifiés au retour à l'emploi ou à l'autonomie.
   Exemples : "blocage psychologique", "faible niveau de français écrit"

5. ressources
   Capacités, qualités, appuis positifs observés.
   Exemples : "travail en équipe", "motivation", "ponctualité"

6. projets
   Projets envisagés ou recommandés.
   Exemples : "projet à définir", "orientation vers ESPO recommandée"

7. verbatim
   Paroles directes de la personne (entre guillemets dans le document).
   Exemples : "J'ai peur de retourner travailler"

8. chronologie
   Événements datés ou séquencés importants.
   Exemples : "CDI en 2018 avant l'accident", "accident du travail en 2019"

RETOURNER UNIQUEMENT ce JSON :
{
  "date_document": "JJ/MM/AAAA si trouvée, sinon vide",
  "limitations_fonctionnelles": [{"valeur": "...", "extrait_source": "..."}],
  "restrictions_medicales":     [{"valeur": "...", "extrait_source": "..."}],
  "besoins":                    [{"valeur": "...", "extrait_source": "..."}],
  "freins":                     [{"valeur": "...", "extrait_source": "..."}],
  "ressources":                 [{"valeur": "...", "extrait_source": "..."}],
  "projets":                    [{"valeur": "...", "extrait_source": "..."}],
  "verbatim":                   [{"valeur": "...", "extrait_source": "..."}],
  "chronologie":                [{"valeur": "...", "extrait_source": "..."}]
}

DOCUMENT :
{texte}
"""

_LONGUEUR_MAX_DOCUMENT = 5000   # chars — les bilans PCR/ESRP dépassent rarement 4 pages utiles


def extraire_connaissance_document(
    texte: str,
    nom_fichier: str,
    openai_client: Any,
    model: str = "gpt-4o",
) -> DocumentKnowledge:
    """
    Extrait les connaissances fonctionnelles d'un document professionnel.

    Règle : extraction fidèle uniquement.
    Chaque item est rejeté si extrait_source est vide.
    """
    if not texte.strip():
        return DocumentKnowledge(source_document=nom_fichier, type_document="vide")

    type_doc = detecter_type_document(texte)

    # Troncature si document trop long (priorité au début qui contient généralement l'essentiel)
    texte_tronque = texte[:_LONGUEUR_MAX_DOCUMENT]
    if len(texte) > _LONGUEUR_MAX_DOCUMENT:
        logger.info("[EXTRACTOR] Document tronqué : %d → %d chars", len(texte), _LONGUEUR_MAX_DOCUMENT)

    prompt = _PROMPT_EXTRACTION.replace("{texte}", texte_tronque)

    try:
        response = openai_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Tu extrais fidèlement des informations de documents professionnels MDPH. "
                        "Tu ne déduis rien. Tu ne complètes rien. "
                        "Chaque item doit avoir un extrait_source non vide."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=1500,
            temperature=0.0,
            response_format={"type": "json_object"},
        )

        raw = json.loads(response.choices[0].message.content.strip())
        return _construire_knowledge(raw, nom_fichier, type_doc)

    except Exception as e:
        logger.error("[EXTRACTOR] Extraction échouée pour %s : %s", nom_fichier, e)
        return DocumentKnowledge(source_document=nom_fichier, type_document=type_doc)


def _construire_knowledge(
    raw: dict,
    nom_fichier: str,
    type_doc: str,
) -> DocumentKnowledge:
    """Construit le DocumentKnowledge depuis la réponse LLM, en rejetant les items sans extrait."""
    champs = [
        "limitations_fonctionnelles", "restrictions_medicales", "besoins",
        "freins", "ressources", "projets", "verbatim", "chronologie",
    ]
    knowledge = DocumentKnowledge(
        source_document=nom_fichier,
        type_document=type_doc,
        date_document=raw.get("date_document", ""),
    )
    total = 0
    for c in champs:
        items_valides = []
        for item in raw.get(c, []):
            valeur  = str(item.get("valeur", "")).strip()
            extrait = str(item.get("extrait_source", "")).strip()
            if valeur and extrait:   # REJET si extrait vide — règle absolue
                # Cloisonnement prescripteur (RGPD) : écarter tout contact tiers,
                # nettoyer les coordonnées résiduelles des extraits d'audit.
                cloisonne = cloisonner_prescripteur_item(valeur, extrait)
                if cloisonne is None:
                    logger.info(
                        "[EXTRACTOR] Item écarté (donnée prescripteur/contact tiers) : %s",
                        valeur[:60],
                    )
                    continue
                valeur, extrait = cloisonne
                items_valides.append(ExtractedItem(
                    valeur=valeur,
                    source=nom_fichier,
                    extrait_source=extrait[:150],
                ))
            elif valeur:
                logger.warning("[EXTRACTOR] Item rejeté (extrait_source vide) : %s", valeur[:60])
        setattr(knowledge, c, items_valides)
        total += len(items_valides)

    knowledge.nb_items_total = total
    logger.info(
        "[EXTRACTOR] %s (type=%s) → %d items extraits",
        nom_fichier, type_doc, total,
    )
    return knowledge


# ─────────────────────────────────────────────────────────────────────────────
# AUDIT ET ROI
# ─────────────────────────────────────────────────────────────────────────────

def calculer_audit(
    knowledge: DocumentKnowledge | dict,
    checklist_agent: list[dict] | None = None,
) -> ExtractionAudit:
    """
    Calcule l'audit d'extraction et le ROI en questions évitées.

    checklist_agent : liste des champs requis de l'agent concerné.
    Si fournie, calcule nb_questions_avant/apres et questions_supprimees enrichies.
    """
    from datetime import datetime, timezone

    # Accepter dict ou DocumentKnowledge
    if isinstance(knowledge, dict):
        k = DocumentKnowledge.from_dict(knowledge)
    else:
        k = knowledge

    champs = [
        "limitations_fonctionnelles", "restrictions_medicales", "besoins",
        "freins", "ressources", "projets", "verbatim", "chronologie",
    ]

    audit = ExtractionAudit(
        type_document=k.type_document,
        source_document=k.source_document,
        date_extraction=datetime.now(timezone.utc).isoformat(),
    )
    total = 0
    nb_alimentes = 0
    for c in champs:
        items = getattr(k, c, [])
        nb = len(items)
        setattr(audit, c, nb)
        total += nb
        if nb > 0:
            nb_alimentes += 1

    audit.total_items     = total
    audit.champs_alimentes = nb_alimentes

    # ROI questions
    if checklist_agent:
        k_dict = k.to_dict()
        supprimees = questions_supprimees(k_dict, checklist_agent)
        avant      = sum(1 for i in checklist_agent if i.get("requis", True))
        apres      = avant - len(supprimees)

        audit.questions_supprimees = supprimees
        audit.nb_questions_avant   = avant
        audit.nb_questions_apres   = apres
        audit.gain_questions       = len(supprimees)

    return audit


def log_audit(audit: ExtractionAudit) -> None:
    """Log lisible de l'audit d'extraction."""
    logger.info("[EXTRACTION_AUDIT] %s (type=%s)", audit.source_document, audit.type_document)
    logger.info(
        "[EXTRACTION_AUDIT]  limitations=%d | restrictions=%d | besoins=%d | freins=%d",
        audit.limitations_fonctionnelles, audit.restrictions_medicales,
        audit.besoins, audit.freins,
    )
    logger.info(
        "[EXTRACTION_AUDIT]  ressources=%d | projets=%d | verbatim=%d | chronologie=%d",
        audit.ressources, audit.projets, audit.verbatim, audit.chronologie,
    )
    logger.info(
        "[EXTRACTION_AUDIT]  total=%d items | champs=%d/8 alimentés",
        audit.total_items, audit.champs_alimentes,
    )
    if audit.gain_questions:
        logger.info(
            "[EXTRACTION_AUDIT]  ROI : %d questions évitées (%d→%d)",
            audit.gain_questions, audit.nb_questions_avant, audit.nb_questions_apres,
        )
        for qs in audit.questions_supprimees:
            logger.info(
                "[EXTRACTION_AUDIT]    ✓ %s ← %s (%d items)",
                qs.champ_checklist, qs.source_knowledge, qs.nb_items_source,
            )


# ─────────────────────────────────────────────────────────────────────────────
# FUSION MULTI-DOCUMENTS (accumulation simple pour le MVP)
# ─────────────────────────────────────────────────────────────────────────────

def fusionner_dans_donnees(
    donnees: dict[str, Any],
    knowledge: DocumentKnowledge,
) -> dict[str, Any]:
    """
    Merge les items du nouveau document dans donnees["_document_knowledge"].
    Règle MVP : accumulation — les items existants ne sont jamais écrasés.
    """
    existing = donnees.get("_document_knowledge") or {}
    k_dict   = knowledge.to_dict()

    champs = [
        "limitations_fonctionnelles", "restrictions_medicales", "besoins",
        "freins", "ressources", "projets", "verbatim", "chronologie",
    ]
    merged: dict[str, Any] = {}
    for c in champs:
        merged[c] = existing.get(c, []) + k_dict.get(c, [])

    # Mettre à jour les méta avec le document le plus récent
    merged["_meta"] = k_dict.get("_meta", {})
    # Conserver la liste des sources traitées
    sources = existing.get("_sources_traitees", [])
    if knowledge.source_document not in sources:
        sources.append(knowledge.source_document)
    merged["_sources_traitees"] = sources

    donnees["_document_knowledge"] = merged
    return donnees
