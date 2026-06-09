"""
app/engines/correction_loop.py — Boucle de correction de l'instructeur.

Ferme la boucle : l'instructeur signale des points → l'agent tente de corriger
À PARTIR DES DONNÉES RÉELLES déjà présentes (jamais d'invention), puis relance la
personne ou le professionnel pour ce qui manque encore.

GARDE-FOUS (non négociables) :
  - Limite de tours : au plus MAX_TOURS relances, pour ne jamais tourner en rond.
  - Correction uniquement à partir d'informations DÉJÀ déclarées ou présentes dans
    les documents — aucune donnée n'est fabriquée.
  - Validation humaine TOUJOURS requise avant finalisation (gérée par
    cerfa_gate_engine) : la boucle ne finalise rien.
  - Aucune soumission automatique à la MDPH : la boucle n'a aucun chemin d'envoi.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("facilim.engines.correction_loop")

MAX_TOURS = 2


def corriger_depuis_donnees_reelles(donnees: dict[str, Any]) -> list[dict[str, str]]:
    """
    Corrige des champs manquants UNIQUEMENT à partir d'informations déjà présentes
    ailleurs dans le dossier. Propager une donnée existante n'est pas l'inventer.
    Retourne la liste des corrections appliquées (champ, valeur, source).
    """
    corrections: list[dict[str, str]] = []

    # 1. Département déduit du code postal de l'adresse déjà déclarée.
    if not donnees.get("departement"):
        m = re.search(r"\b(\d{5})\b", str(donnees.get("adresse_complete", "") or ""))
        if m:
            # Helper partagé : gère les DOM (97400 → 974, et non « 97 »).
            from app.services.collecte_schema import code_postal_vers_departement
            dep = code_postal_vers_departement(m.group(1))
            if dep:
                donnees["departement"] = dep
                corrections.append({"champ": "departement", "valeur": dep,
                                    "source": "code postal de l'adresse déclarée"})

    # 2. Genre déduit d'une civilité déjà présente (nom, civilité, document, notes).
    if not donnees.get("genre"):
        blob = " ".join(
            str(donnees.get(k, "") or "")
            for k in ("nom_prenom", "civilite", "documents_texte", "notes_pro")
        ).lower()
        if re.search(r"\b(mr|m\.|monsieur)\b", blob):
            donnees["genre"] = "homme"
            corrections.append({"champ": "genre", "valeur": "homme",
                                "source": "civilité déjà présente dans le dossier"})
        elif re.search(r"\b(mme|madame|mlle|mademoiselle)\b", blob):
            donnees["genre"] = "femme"
            corrections.append({"champ": "genre", "valeur": "femme",
                                "source": "civilité déjà présente dans le dossier"})

    # 3. Miroir NIR : aligner les alias du numéro de sécurité sociale s'il existe.
    from app.services.collecte_schema import synchroniser_nir
    synchroniser_nir(donnees)

    if corrections:
        logger.info("[BOUCLE] %d correction(s) depuis données réelles : %s",
                    len(corrections), [c["champ"] for c in corrections])
    return corrections


def boucle_correction(
    donnees: dict[str, Any],
    profil: str,
    dossier_id: str,
    db: Any | None = None,
    wa: Any | None = None,
    phone: str | None = None,
    notifier_famille: bool = False,
) -> dict[str, Any]:
    """
    Un tour de boucle de correction, borné et sans effet irréversible.
    Corrige ce qui peut l'être depuis le réel, lance la revue de l'instructeur, et
    n'autorise une relance de la personne que tant que la limite de tours n'est pas
    atteinte. Ne finalise jamais, n'envoie jamais à la MDPH.
    """
    from app.engines.revue_instructeur import revue_dossier

    tours = int(donnees.get("_corrections_tours") or 0)

    # 1. Correction à partir des données réelles déjà connues.
    corrections = corriger_depuis_donnees_reelles(donnees)

    # 2. Revue de l'instructeur. La relance famille n'est tentée que sous la limite.
    relancer = tours < MAX_TOURS
    rev = revue_dossier(
        donnees, profil, dossier_id,
        db=db, wa=wa, phone=phone,
        notifier_famille=(notifier_famille and relancer),
    )

    # 3. Incrémenter le compteur si des points subsistent et qu'on a relancé.
    reste_des_points = bool(rev.get("points") or rev.get("coherence"))
    if relancer and reste_des_points:
        donnees["_corrections_tours"] = tours + 1

    if not relancer and reste_des_points:
        logger.info("[BOUCLE] dossier=%s : limite de %d tours atteinte — "
                    "on s'arrête, la main revient à l'humain.", dossier_id, MAX_TOURS)

    return {
        "tours": donnees.get("_corrections_tours", tours),
        "max_tours": MAX_TOURS,
        "limite_atteinte": not relancer and reste_des_points,
        "corrections_auto": corrections,
        "revue": rev,
        # Garde-fous explicites, lus par les couches supérieures.
        "validation_humaine_requise": True,
        "soumission_mdph_auto": False,
    }
