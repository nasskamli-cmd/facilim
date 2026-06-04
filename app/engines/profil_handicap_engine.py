"""
app/engines/profil_handicap_engine.py — Profilage métier multi-handicap.

Niveau 2 de profilage (complémentaire au profil_mdph basé sur l'âge).
Calcule : profil_principal, profil_secondaire, tags_detectes.

Principe :
- Détection UNIQUEMENT sur ce qui est déclaré (diagnostics, traitements)
- Aucune inférence, aucune supposition
- Recalculé à chaque mise à jour du champ diagnostics
- Persisté en base : profil_principal, profil_secondaire, tags_detectes (JSON)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("facilim.engines.profil_handicap")

# ── Mots-clés par catégorie de handicap ──────────────────────────────────────
# Clé = identifiant catégorie, valeur = liste de patterns (insensible à la casse)

_MOTS_CLES: dict[str, list[str]] = {
    "tsa": [
        r"autis", r"\btsa\b", r"asperger", r"trouble.{0,10}spectre",
        r"\bted\b", r"trouble.{0,15}envahissant", r"\bhfa\b",
        r"trouble.{0,10}communication", r"trouble.{0,10}interaction",
    ],
    "di": [
        r"déficience intellectuelle", r"retard mental", r"trisomie",
        r"syndrome de down", r"\bx fragile\b", r"syndrome de williams",
        r"syndrome d.angelman", r"prader.willi",
        r"\bdi légère\b", r"\bdi modérée\b", r"\bdi sévère\b",
        r"trouble.{0,10}apprentissage.{0,10}sévère",
    ],
    "psychique": [
        r"schizophréni", r"bipolarité", r"trouble bipolaire", r"psychose",
        r"schizo.affectif", r"schizoaffectif",
        r"dépression.{0,10}sévère", r"dépression.{0,10}chronique",
        r"trouble borderline", r"trouble.{0,10}personnalité",
        r"anxiété.{0,10}généralisée", r"\btoc\b", r"trouble obsessionnel",
        r"\bptsd\b", r"stress post.traumatique", r"état de stress",
        r"trouble.{0,10}psychiatrique", r"trouble.{0,10}mental",
    ],
    "moteur": [
        r"paralys", r"hémiplég", r"paraplég", r"tétraplég",
        r"infirmité motrice", r"\bimc\b", r"sclérose en plaques", r"\bsep\b",
        r"myopathie", r"dystrophie musculaire", r"accident vasculaire",
        r"\bavc\b", r"traumatisme crânien", r"\btc\b",
        r"ataxie", r"spasticité", r"amputation",
    ],
    "cognitif": [
        r"alzheimer", r"démence", r"trouble neurocognitif",
        r"aphasie", r"troubles mnésiques", r"troubles.{0,10}exécutifs",
        r"lésion cérébrale", r"traumatisme crânien", r"séquelles.{0,10}cérébral",
        r"troubles.{0,10}neuropsychologiques",
    ],
    "maladie_chronique": [
        r"cancer", r"insuffisance.{0,15}(rénale|cardiaque|respiratoire|hépatique)",
        r"diabète.{0,10}(type|insulino)", r"épilepsie", r"\blupus\b",
        r"maladie de crohn", r"rectocolite", r"polyarthrite",
        r"fibromyalgie", r"fatigue chronique", r"\bsfc\b", r"\bsed\b",
        r"syndrome d.ehlers", r"maladie rare",
    ],
    "sensoriel": [
        r"surdité", r"cécité", r"malvoyance", r"malentendant",
        r"déficience visuelle", r"déficience auditive",
        r"implant cochléaire", r"basse vision", r"amblyopie",
    ],
    "parcours_esms": [
        r"\bime\b", r"\beast\b", r"\bsessad\b", r"\bsavs\b", r"\bsamsah\b",
        r"\bulis\b", r"inclusion scolaire spécialisée",
        r"\bmas\b", r"\bfam\b", r"maison d.accueil",
        r"foyer de vie", r"établissement spécialisé",
    ],
}

# ── Priorité de sélection du profil principal ─────────────────────────────────
# Plus le rang est bas, plus la catégorie est prioritaire
_PRIORITE: dict[str, int] = {
    "tsa":              1,
    "di":               2,
    "cognitif":         3,
    "psychique":        4,
    "moteur":           5,
    "sensoriel":        6,
    "maladie_chronique": 7,
    "parcours_esms":    8,  # toujours tag additionnel — rarement principal
}

# ── Adaptation du questionnement ──────────────────────────────────────────────
PROFILS_COGNITIFS  = frozenset({"tsa", "di", "cognitif"})
PROFILS_FRAGILES   = frozenset({"psychique", "maladie_chronique", "parcours_esms"})
PROFILS_AUTONOMES  = frozenset({"moteur", "sensoriel"})


# ── Mots-clés pour sous-profilage psychique ──────────────────────────────────
# ── Mots-clés pour sous-profilage sensoriel ──────────────────────────────────
_MOTS_CLES_SENSORIEL_AUDITIF = [
    r"surdité", r"malentendant", r"déficience auditive",
    r"implant cochléaire", r"appareillage auditif",
    r"langue des signes", r"\blsf\b", r"\blpc\b",
    r"surd[io]", r"hypoacousie",
]
_MOTS_CLES_SENSORIEL_VISUEL = [
    r"cécité", r"malvoyance", r"déficience visuelle",
    r"basse vision", r"amblyopie",
    r"lecteur d.écran", r"braille", r"chien guide",
    r"non-voyant", r"aveugle",
]


def detecter_sous_profil_sensoriel(texte: str) -> str:
    """
    Détermine le sous-profil sensoriel depuis le texte des diagnostics.
    Retourne 'sensoriel_auditif' | 'sensoriel_visuel' | 'sensoriel'.
    """
    t = texte.lower()
    score_auditif = sum(1 for p in _MOTS_CLES_SENSORIEL_AUDITIF if re.search(p, t, re.IGNORECASE))
    score_visuel  = sum(1 for p in _MOTS_CLES_SENSORIEL_VISUEL  if re.search(p, t, re.IGNORECASE))

    if score_auditif >= score_visuel and score_auditif > 0:
        return "sensoriel_auditif"
    if score_visuel > 0:
        return "sensoriel_visuel"
    return "sensoriel"   # indéterminé → fallback


_MOTS_CLES_PSYCHIQUE_HUMEUR = [
    r"dépression", r"trouble bipolaire", r"bipolarité",
    r"trouble de l.humeur", r"dysthymie", r"burnout sévère",
    r"épisode dépressif", r"épisode maniaque",
]
_MOTS_CLES_PSYCHIQUE_PSYCHOTIQUE = [
    r"schizophréni", r"psychose", r"trouble schizo",
    r"schizo.affectif", r"schizoaffectif",
    r"hallucination", r"délire", r"paranoïa",
    r"trouble psychotique",
]


def detecter_sous_profil_psychique(texte: str) -> str:
    """
    Détermine le sous-profil psychique depuis le texte des diagnostics.
    Retourne 'psychique_humeur' | 'psychique_psychotique' | 'psychique'.
    """
    t = texte.lower()
    score_psychotique = sum(1 for p in _MOTS_CLES_PSYCHIQUE_PSYCHOTIQUE if re.search(p, t, re.IGNORECASE))
    score_humeur      = sum(1 for p in _MOTS_CLES_PSYCHIQUE_HUMEUR if re.search(p, t, re.IGNORECASE))

    if score_psychotique > 0:
        return "psychique_psychotique"
    if score_humeur > 0:
        return "psychique_humeur"
    return "psychique"   # sous-profil indéterminé → fallback


@dataclass
class ProfilHandicap:
    profil_principal:  str        = ""    # catégorie dominante déclarée
    profil_secondaire: str        = ""    # deuxième catégorie si présente
    sous_profil:       str        = ""    # sous-profil affiné (ex: psychique_humeur)
    tags_detectes:     list[str]  = field(default_factory=list)  # toutes catégories trouvées
    nb_questions_max:  int        = 3     # adapté selon profil cognitif
    source:            str        = ""    # champ source utilisé pour la détection

    @property
    def est_cognitif(self) -> bool:
        return self.profil_principal in PROFILS_COGNITIFS or self.profil_secondaire in PROFILS_COGNITIFS

    @property
    def est_fragile(self) -> bool:
        return self.profil_principal in PROFILS_FRAGILES or self.profil_secondaire in PROFILS_FRAGILES

    def to_dict(self) -> dict[str, Any]:
        return {
            "profil_principal":  self.profil_principal,
            "profil_secondaire": self.profil_secondaire,
            "sous_profil":       self.sous_profil,
            "tags_detectes":     self.tags_detectes,
        }


def detecter_profil_handicap(donnees: dict[str, Any]) -> ProfilHandicap:
    """
    Calcule le profil handicap depuis les données déclarées.

    Sources consultées (dans l'ordre de priorité) :
      1. diagnostics
      2. traitements (signal secondaire)
      3. situation_scolaire / statut_emploi (contexte)

    RÈGLE ABSOLUE : n'utilise QUE ce qui est explicitement déclaré.
    Aucune inférence, aucune extrapolation.
    """
    texte_source = " ".join(filter(None, [
        str(donnees.get("diagnostics", "") or ""),
        str(donnees.get("traitements", "") or ""),
        str(donnees.get("situation_scolaire", "") or ""),
        str(donnees.get("statut_emploi", "") or ""),
        str(donnees.get("impact_quotidien", "") or ""),
    ])).lower()

    if not texte_source.strip():
        return ProfilHandicap(source="aucune_donnee")

    # Détecter toutes les catégories présentes
    categories_trouvees: dict[str, int] = {}  # catégorie → score (nb matches)
    for categorie, patterns in _MOTS_CLES.items():
        score = sum(1 for p in patterns if re.search(p, texte_source, re.IGNORECASE))
        if score > 0:
            categories_trouvees[categorie] = score

    if not categories_trouvees:
        return ProfilHandicap(source="non_identifie")

    # Trier par priorité (rang le plus bas = plus prioritaire)
    # En cas d'égalité de rang, préférer le score le plus élevé
    rang_score = lambda cat: (_PRIORITE.get(cat, 99), -categories_trouvees[cat])
    triees = sorted(categories_trouvees.keys(), key=rang_score)

    profil_principal  = triees[0]
    profil_secondaire = triees[1] if len(triees) > 1 else ""
    tags_detectes     = triees  # toutes les catégories, triées par priorité

    # Calcul nb_questions_max
    if profil_principal in PROFILS_COGNITIFS or profil_secondaire in PROFILS_COGNITIFS:
        nb_questions_max = 1
    elif profil_principal in PROFILS_FRAGILES or profil_secondaire in PROFILS_FRAGILES:
        nb_questions_max = 2
    else:
        nb_questions_max = 3

    logger.info(
        "[PROFIL_HANDICAP] principal=%s secondaire=%s tags=%s nb_q_max=%d",
        profil_principal, profil_secondaire, tags_detectes, nb_questions_max,
    )

    # Sous-profil affiné — psychique et sensoriel
    sous_profil = ""
    if profil_principal == "psychique":
        sous_profil = detecter_sous_profil_psychique(texte_source)
    elif profil_principal == "sensoriel":
        sous_profil = detecter_sous_profil_sensoriel(texte_source)

    logger.info(
        "[PROFIL_HANDICAP] principal=%s sous_profil=%s secondaire=%s tags=%s nb_q_max=%d",
        profil_principal, sous_profil, profil_secondaire, tags_detectes, nb_questions_max,
    )

    return ProfilHandicap(
        profil_principal=profil_principal,
        profil_secondaire=profil_secondaire,
        sous_profil=sous_profil,
        tags_detectes=tags_detectes,
        nb_questions_max=nb_questions_max,
        source="diagnostics+traitements",
    )


def persister_profil_handicap(db: Any, dossier_id: str, profil: ProfilHandicap) -> None:
    """Met à jour les colonnes profil_principal / profil_secondaire / tags_detectes en base."""
    try:
        db.execute(
            """
            UPDATE dossiers SET
                profil_principal  = ?,
                profil_secondaire = ?,
                tags_detectes     = ?
            WHERE id = ?
            """,
            (
                profil.sous_profil or profil.profil_principal,  # sous-profil affiné si disponible
                profil.profil_secondaire,
                json.dumps(profil.tags_detectes, ensure_ascii=False),
                dossier_id,
            ),
        )
        db.commit()
    except Exception as e:
        logger.warning("[PROFIL_HANDICAP] Persistance échouée : %s", e)
