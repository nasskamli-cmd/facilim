"""
app/services/cerfa_dictionary.py — DICTIONNAIRE UNIQUE DU CERFA MDPH 15692*01.

SOURCE DE VÉRITÉ. Chaque case / champ remplissable du formulaire est décrit ICI,
une seule fois. Les trois couches du système en sont DÉRIVÉES, pour qu'elles ne
puissent plus diverger :

  1. Collecte    : quelles questions l'assistant pose      → champs_checklist(profil)
  2. Extraction  : quels champs le LLM peut capter          → ids_extractibles()
  3. Remplissage : le générateur lit déjà ces id            → (cible documentée ici)

Avant ce dictionnaire, ces trois listes étaient écrites séparément et divergeaient :
une case pouvait exister côté CERFA sans jamais être demandée ni captée (ex.
preference_contact). Désormais, tout champ remplissable EST demandé et EST capté.

Règle de profil : "tous" = applicable à tous les profils. Sinon, restreindre via
"profils" : ("adulte",), ("enfant",), ("mixte",), ("protege",).
Un enfant n'a pas de section D (projet pro) ; un adulte pas de section C
(scolarité) ; le mixte 16-25 ans a les deux. Ces conditions vivent sur chaque
champ, section par section.

Cadre : FACILIM propose et structure, l'humain valide, FACILIM ne décide jamais
des droits.
"""

from __future__ import annotations

from typing import Any

# ── PARTIE A — Identité, contact, rattachements administratifs ────────────────
# (Première section construite. B, C, D, E, F suivront sur le même modèle.)
SECTION_A: list[dict[str, Any]] = [
    {
        "id": "preference_contact",
        "section": "A",
        "profils": ("tous",),
        "requis": True,
        "extractible": True,
        "label": "Mode de contact souhaité avec la MDPH",
        "question": "Comment préférez-vous que la MDPH vous contacte : par e-mail, par téléphone, ou par courrier ?",
        "valeurs": "email | telephone | courrier",
        "cible_cerfa": "OPTION/Case à cocher P2 contact (email/tel/courrier)",
    },
    {
        "id": "organisme_payeur",
        "section": "A",
        "profils": ("tous",),
        "requis": True,
        "extractible": True,
        "label": "Organisme payeur des allocations",
        "question": "Êtes-vous allocataire de la CAF, de la MSA, ou d'aucune des deux ?",
        "valeurs": "CAF | MSA | AUTRE",
        "cible_cerfa": "OPTION P2 4 (CAF/MSA/Autre)",
    },
    {
        "id": "numero_allocataire",
        "section": "A",
        "profils": ("tous",),
        "requis": True,
        "extractible": True,
        "label": "Numéro d'allocataire CAF ou MSA",
        "question": "Si vous êtes allocataire CAF ou MSA, quel est votre numéro d'allocataire ?",
        "cible_cerfa": "Champ texte n° allocataire",
    },
    {
        "id": "organisme_assurance_maladie",
        "section": "A",
        "profils": ("tous",),
        "requis": True,
        "extractible": True,
        "label": "Caisse d'assurance maladie",
        "question": "Quelle est votre caisse d'assurance maladie : CPAM, MSA, ou autre ?",
        "valeurs": "CPAM | MSA | RSI | AUTRE",
        "cible_cerfa": "OPTION P2 5 (CPAM/MSA/RSI/Autre)",
    },
    {
        "id": "nationalite",
        "section": "A",
        "profils": ("tous",),
        "requis": True,
        "extractible": True,
        "label": "Nationalité",
        "question": "Quelle est votre nationalité ?",
        "valeurs": "française | EEE | autre",
        "cible_cerfa": "OPTION nationalité",
    },
    {
        "id": "nom_naissance",
        "section": "A",
        "profils": ("tous",),
        "requis": False,  # demandé seulement si différent du nom d'usage
        "extractible": True,
        "label": "Nom de naissance (s'il diffère du nom actuel)",
        "question": "Votre nom de naissance est-il différent de votre nom actuel ? Si oui, lequel ?",
        "cible_cerfa": "Champ texte nom de naissance",
    },
    {
        "id": "commune_naissance",
        "section": "A",
        "profils": ("tous",),
        "requis": True,
        "extractible": True,
        "label": "Commune de naissance",
        "question": "Dans quelle commune êtes-vous né(e) ?",
        "cible_cerfa": "Champ texte commune de naissance",
    },
    {
        "id": "pays_naissance",
        "section": "A",
        "profils": ("tous",),
        "requis": True,
        "extractible": True,
        "label": "Pays de naissance",
        "question": "Dans quel pays êtes-vous né(e) ?",
        "cible_cerfa": "Champ texte pays de naissance",
    },
]

# Dictionnaire complet (s'étendra : SECTION_A + SECTION_B + ... + SECTION_F)
_DICTIONNAIRE: list[dict[str, Any]] = list(SECTION_A)


def _applicable(champ: dict, profil: str) -> bool:
    profils = champ.get("profils", ("tous",))
    return "tous" in profils or (profil or "adulte").lower() in profils


def champs_checklist(profil: str) -> list[dict]:
    """
    Champs du dictionnaire applicables au profil, au FORMAT checklist attendu par
    les agents (id, label, requis, condition optionnelle).
    Le 'label' porte la question naturelle pour que l'assistant la pose clairement.
    """
    out: list[dict] = []
    for c in _DICTIONNAIRE:
        if not _applicable(c, profil):
            continue
        item: dict[str, Any] = {
            "id": c["id"],
            "label": c.get("question") or c["label"],
            "requis": bool(c.get("requis", True)),
        }
        if c.get("condition"):
            item["condition"] = c["condition"]
        out.append(item)
    return out


def ids_extractibles() -> list[str]:
    """Identifiants que l'extraction doit pouvoir capter (whitelist dérivée)."""
    return [c["id"] for c in _DICTIONNAIRE if c.get("extractible")]


def hints_extraction() -> str:
    """Indices de valeurs pour le prompt d'extraction (formats attendus)."""
    lignes = []
    for c in _DICTIONNAIRE:
        if c.get("extractible") and c.get("valeurs"):
            lignes.append(f"- {c['id']} : valeur attendue parmi {c['valeurs']}")
    return "\n".join(lignes)
