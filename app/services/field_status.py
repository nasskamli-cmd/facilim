"""
app/services/field_status.py — Statut d'acquisition par champ.

Gère la fonctionnalité « champ non communiqué » : quand la famille refuse de
répondre à un champ, on ne l'invente JAMAIS. On enregistre son statut, on
prévient la famille avec bienveillance, et on alerte le professionnel.

Tout vit dans synthese_json["_champs_metadata"], déjà persisté avec le dossier.
Aucune table à créer.

États possibles d'un champ (modèle de complétude différenciée) :
  - "fourni"           : l'usager a répondu (valeur présente dans les données)
  - "refuse"           : l'usager a explicitement refusé de répondre
  - "a_completer_pro"  : l'usager ne sait pas / ne peut pas → délégué au pro
                         (la donnée reste EXIGÉE et VISIBLE, juste plus posée à l'usager)
  - "en_attente"       : ni renseigné, ni refusé, ni délégué (collecte à poursuivre)
  - "non_applicable"   : champ conditionnel dont la condition n'est pas remplie
                         (porté par la checklist, pas par les métadonnées)

Principe : on ne transforme JAMAIS un champ exigé en facultatif silencieux. Un champ
exigé non fourni reste compté comme manquant — soit à reposer à l'usager, soit à
compléter par le professionnel, soit refusé — mais jamais invisible.
"""

from __future__ import annotations

from typing import Any

META_KEY = "_champs_metadata"

FOURNI = "fourni"
REFUSE = "refuse"
A_COMPLETER_PRO = "a_completer_pro"
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
    """
    Statut courant d'un champ. Priorité : valeur présente → fourni ; sinon le
    statut explicite (refuse / a_completer_pro) ; sinon en_attente.
    Une valeur réellement fournie prime sur tout marquage antérieur.
    """
    if donnees.get(field_id) not in _VIDES:
        return FOURNI
    meta = donnees.get(META_KEY) or {}
    entry = meta.get(field_id)
    if isinstance(entry, dict):
        st = entry.get("statut")
        if st in (REFUSE, A_COMPLETER_PRO):
            return st
    return EN_ATTENTE


def est_refuse(donnees: dict[str, Any], field_id: str) -> bool:
    return statut_champ(donnees, field_id) == REFUSE


def est_a_completer_pro(donnees: dict[str, Any], field_id: str) -> bool:
    return statut_champ(donnees, field_id) == A_COMPLETER_PRO


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


# ── « À compléter par le professionnel » ─────────────────────────────────────
# Quand l'usager ne SAIT pas / ne PEUT pas répondre, on ne boucle pas et on
# n'invente pas : le champ EXIGÉ est délégué au professionnel. Il reste manquant
# et visible (liste dédiée), mais n'est plus reposé à l'usager.

def marquer_a_completer_pro(donnees: dict[str, Any], field_id: str, raison: str = "") -> None:
    """
    Marque un champ exigé comme « à compléter par le professionnel ». N'écrit
    aucune valeur : le champ reste vide, son statut est enregistré. Réversible
    (une valeur fournie ensuite reprend le dessus, cf. statut_champ).
    """
    meta = _meta(donnees)
    meta[field_id] = {
        "statut": A_COMPLETER_PRO,
        "raison": (raison or "").strip()[:300],
    }


def champs_a_completer_pro(donnees: dict[str, Any]) -> list[str]:
    """Liste des ids de champs délégués au professionnel (encore vides)."""
    meta = donnees.get(META_KEY) or {}
    return [fid for fid, e in meta.items()
            if isinstance(e, dict) and e.get("statut") == A_COMPLETER_PRO
            and donnees.get(fid) in _VIDES]


# Détection « je ne sais pas » (distincte d'un refus : l'usager n'oppose pas un
# refus, il n'a simplement pas l'information → délégation au pro, pas blocage).
import unicodedata as _ud

_NE_SAIT_PAS_PATTERNS = (
    "je ne sais pas", "je sais pas", "j en sais rien", "aucune idee",
    "je ne sais plus", "je sais plus", "je ne me souviens pas",
    "je ne me rappelle pas", "pas sur", "pas sure", "je l ignore", "aucune idée",
)


def phrase_ne_sait_pas(text: str) -> bool:
    """True si le message exprime une absence d'information (et non un refus)."""
    t = _ud.normalize("NFD", (text or "").lower())
    t = "".join(c for c in t if _ud.category(c) != "Mn")
    return any(p in t for p in _NE_SAIT_PAS_PATTERNS)


# ── Audit trail des transitions de statut ────────────────────────────────────
# Historise en_attente→fourni / →refuse / →a_completer_pro et a_completer_pro→fourni,
# dans donnees["_historique_statuts"] (persisté avec la synthèse). Auditabilité ESSMS.

HIST_KEY = "_historique_statuts"


def etats_snapshot(donnees: dict[str, Any], field_ids) -> dict[str, str]:
    """Photo des statuts courants d'une liste de champs (avant traitement d'un tour)."""
    return {fid: statut_champ(donnees, fid) for fid in field_ids}


def journaliser_transitions(
    donnees: dict[str, Any],
    avant: dict[str, str],
    field_ids,
    origine: str = "",
    horodatage: str | None = None,
) -> int:
    """
    Compare les statuts AVANT/APRÈS et historise chaque transition dans
    donnees[HIST_KEY]. Chaque événement : {champ, ancien, nouveau, horodatage,
    origine}. Retourne le nombre d'événements ajoutés. Idempotent sur l'état
    (ne journalise que les changements réels).
    """
    from datetime import datetime, timezone
    ts = horodatage or datetime.now(timezone.utc).isoformat()
    hist = donnees.get(HIST_KEY)
    if not isinstance(hist, list):
        hist = []
        donnees[HIST_KEY] = hist
    n = 0
    for fid in field_ids:
        ancien = avant.get(fid, EN_ATTENTE)
        nouveau = statut_champ(donnees, fid)
        if nouveau != ancien:
            hist.append({
                "champ": fid,
                "ancien": ancien,
                "nouveau": nouveau,
                "horodatage": ts,
                "origine": origine,
            })
            n += 1
    return n


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
