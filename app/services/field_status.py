"""
app/services/field_status.py — Statut d'acquisition par champ.

Gère la fonctionnalité « champ non communiqué » : quand la famille refuse de
répondre à un champ, on ne l'invente JAMAIS. On enregistre son statut, on
prévient la famille avec bienveillance, et on alerte le professionnel.

Tout vit dans synthese_json["_champs_metadata"], déjà persisté avec le dossier.
Aucune table à créer.

États possibles d'un champ :
  - "fourni"      : la famille a répondu (valeur présente dans les données)
  - "refuse"      : la famille a refusé / préféré ne pas répondre
  - "en_attente"  : ni renseigné ni refusé (collecte à poursuivre)
"""

from __future__ import annotations

from typing import Any

META_KEY = "_champs_metadata"

FOURNI = "fourni"
REFUSE = "refuse"
EN_ATTENTE = "en_attente"

_VIDES = (None, "", 0, [])


def _meta(donnees: dict[str, Any]) -> dict[str, Any]:
    """Retourne (en le créant si besoin) le dict de métadonnées par champ."""
    m = donnees.get(META_KEY)
    if not isinstance(m, dict):
        m = {}
        donnees[META_KEY] = m
    return m


def statut_champ(donnees: dict[str, Any], field_id: str) -> str:
    """Statut courant d'un champ : refuse > fourni > en_attente."""
    meta = donnees.get(META_KEY) or {}
    entry = meta.get(field_id)
    if isinstance(entry, dict) and entry.get("statut") == REFUSE:
        return REFUSE
    if donnees.get(field_id) not in _VIDES:
        return FOURNI
    return EN_ATTENTE


def est_refuse(donnees: dict[str, Any], field_id: str) -> bool:
    return statut_champ(donnees, field_id) == REFUSE


def marquer_refus(donnees: dict[str, Any], field_id: str, message_personne: str = "") -> None:
    """
    Marque un champ comme refusé par la famille. N'écrit AUCUNE valeur dans le
    champ lui-même : le champ reste vide, seul son statut est enregistré.
    """
    meta = _meta(donnees)
    meta[field_id] = {
        "statut": REFUSE,
        "message_personne": (message_personne or "").strip()[:300],
    }


def champs_refuses(donnees: dict[str, Any]) -> list[str]:
    """Liste des ids de champs refusés par la famille."""
    meta = donnees.get(META_KEY) or {}
    return [fid for fid, e in meta.items()
            if isinstance(e, dict) and e.get("statut") == REFUSE]


def champs_bloquants_refuses(donnees: dict[str, Any]) -> list[str]:
    """Champs CRITIQUES refusés — ceux qui bloquent la finalisation."""
    from app.services.collecte_schema import criticite_champ
    return [fid for fid in champs_refuses(donnees)
            if criticite_champ(fid) == "bloquant"]


def finalisation_bloquee(donnees: dict[str, Any]) -> bool:
    """True si au moins un champ critique a été refusé (gate de finalisation pro)."""
    return len(champs_bloquants_refuses(donnees)) > 0


# ── Détection d'un refus exprimé par la famille ───────────────────────────────
import unicodedata

_REFUS_PATTERNS = (
    "je ne veux pas", "veux pas repondre", "veux pas le dire", "veux pas donner",
    "je prefere ne pas", "je prefere pas", "prefere ne rien dire",
    "je prefere garder", "je ne souhaite pas", "souhaite pas repondre",
    "souhaite pas le dire", "pas envie de repondre", "je refuse",
    "ca ne vous regarde pas", "ca vous regarde pas", "ca te regarde pas",
    "je ne donnerai pas", "je donne pas", "sans repondre",
    "je ne reponds pas", "je reponds pas", "je ne dirai pas",
)


# Locutions qui CONTIENNENT un fragment de refus sans en être un (idiomes courants).
# Leur présence neutralise la détection : sans ce garde-fou, des phrases comme
# « je donne pas mal de détails… » ou « je ne réponds pas toujours vite mais voici
# mon adresse… » étaient prises pour un refus et marquaient DÉFINITIVEMENT le champ
# requis comme refusé (donc plus jamais reposé). Faux positif = donnée perdue.
_REFUS_ANTI_PATTERNS = (
    "pas mal",        # « pas mal de détails »
    "pas toujours",   # « je ne réponds pas toujours vite »
    "pas encore",
    "pas que",
    "pas seulement",
)


def _sans_accents(text: str) -> str:
    t = (text or "").lower()
    t = unicodedata.normalize("NFD", t)
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def phrase_de_refus(text: str) -> bool:
    """
    True si le message exprime explicitement un refus de répondre.
    Volontairement conservateur (ne capte pas « je ne sais pas », qui n'est pas
    un refus) afin d'éviter les faux positifs.
    """
    t = _sans_accents(text)
    if any(a in t for a in _REFUS_ANTI_PATTERNS):
        return False  # idiome contenant « pas » : ce n'est pas un refus
    return any(p in t for p in _REFUS_PATTERNS)
