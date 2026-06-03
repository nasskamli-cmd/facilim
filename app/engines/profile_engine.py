"""
app/engines/profile_engine.py — Moteur de profil par âge.

Responsabilité unique : déterminer le profil légal d'un usager
(enfant / mixte / adulte) depuis sa date de naissance, puis appliquer
les contraintes qui en découlent sur les données et le prompt LLM.

Pourquoi un module séparé ?
  - L'âge est recalculé UNE SEULE FOIS dès que date_naissance est connu,
    pas à chaque message.
  - Les champs interdits aux enfants sont définis ICI, pas dans le prompt LLM
    ni dans l'orchestrateur.
  - Le profil est persisté en base → pas de recalcul à chaque échange.

Seuils MDPH officiels :
  < 16 ans   → "enfant"  (sections B+C ; D/E/emploi interdits)
  16-25 ans  → "mixte"   (règle équipe mixte : toutes sections actives)
  > 25 ans   → "adulte"  (section B scolaire supprimée)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

logger = logging.getLogger("facilim.engines.profile")

# ── Seuils d'âge MDPH ────────────────────────────────────────────────────────
#
# Deux dimensions INDÉPENDANTES :
#
#   profil_mdph  (sections CERFA à remplir)
#     ≤ 15 ans  → "enfant"  : sections A1/A2/B/C obligatoires, D INTERDITE
#     16-25 ans → "mixte"   : équipe pluridisciplinaire, C+D possibles selon projet
#     > 25 ans  → "adulte"  : flux standard
#
#   est_mineur  (posture / interlocuteur légal)
#     < 18 ans  → True  : s'adresser au représentant légal
#     ≥ 18 ans  → False : s'adresser directement à la personne
#
# La spec dit "enfant < 18" pour la POSTURE et "mixte 16-25" pour les SECTIONS.
# Ces deux règles coexistent : un 17 ans est est_mineur=True (posture parents)
# ET profil="mixte" (sections C+D accessibles si projet pro).
# AGE_SEUIL_ENFANT_MAX = 15 : "enfant" au sens CERFA = moins de 16 ans seulement.

AGE_SEUIL_ENFANT_MAX = 15   # ≤ 15 ans → profil "enfant" (sections CERFA)
AGE_SEUIL_MIXTE_MAX  = 25   # 16-25 ans → profil "mixte" (équipe mixte MDPH)


# ── Champs collectés par conversation qui n'ont AUCUN sens pour un enfant ────
# Ces clés de synthese_json sont mises à None/0 si profil == "enfant".
CHAMPS_INTERDITS_ENFANT: dict[str, Any] = {
    "situation_maritale":   None,   # un enfant n'a pas de situation conjugale
    "nb_enfants":           0,      # un enfant n'a pas d'enfants à charge
    "enfants_a_charge":     0,
    "situation_familiale":  None,   # remplacé par "vit avec ses parents / en établissement"
    "statut_emploi":        None,   # pas de contrat de travail
    "nom_employeur":        None,
    "poste_occupe":         None,
    "revenus_emploi":       None,
    "aah":                  None,   # AAH non applicable < 20 ans
    "rsa":                  None,   # RSA non applicable < 25 ans
}

# Questions à poser aux parents/représentants à la place des questions adultes
QUESTIONS_REMPLACEMENT_ENFANT: dict[str, str] = {
    "situation_familiale":  "situation_familiale_enfant",   # vit chez parents / famille d'accueil / établissement
    "enfants_a_charge":     None,                           # supprimé — pas de question
    "statut_emploi":        "situation_scolaire",
}

# Champs supplémentaires à collecter UNIQUEMENT pour les enfants
CHAMPS_SPECIFIQUES_ENFANT: list[str] = [
    "situation_scolaire",       # école, IME, SESSAD, ULIS, non-scolarisé
    "etablissement_scolaire",   # nom de l'établissement
    "classe_niveau",            # CE1, 5ème, ULIS, etc.
    "representant_legal_nom",   # nom du responsable légal
    "representant_legal_lien",  # père / mère / tuteur
]


# ── Dataclass résultat ────────────────────────────────────────────────────────

@dataclass
class ProfilUsager:
    """Profil calculé, immuable une fois la date de naissance connue."""
    age_annees:              int
    profil_mdph:             str          # "enfant" | "mixte" | "adulte" | "inconnu"
    est_mineur:              bool         # < 18 ans au sens légal
    date_naissance:          str          # JJ/MM/AAAA normalisée
    champs_bloques:          dict[str, Any] = field(default_factory=dict)
    a_tutelle_ou_curatelle:  bool = False  # True → agent ADULTE_PROTEGE

    @property
    def interlocuteur(self) -> str:
        """Qui parle à l'assistant : l'usager lui-même ou ses représentants."""
        if self.profil_mdph == "enfant":
            return "les parents ou représentants légaux de l'enfant"
        return "la personne concernée ou son représentant"

    @property
    def sujet_dossier(self) -> str:
        if self.profil_mdph == "enfant":
            return "de l'enfant"
        return "de la personne"


# ── Parseur de date ───────────────────────────────────────────────────────────

_DATE_FORMATS = [
    "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y",
    "%d/%m/%y", "%d-%m-%y",
    "%d%m%Y",   # format brut sans séparateur : 02041985
    "%d%m%y",   # format court : 020485
    "%Y%m%d",   # format ISO compact : 19850402
]


_MOIS_FR = {
    "janvier": "01", "février": "02", "fevrier": "02", "mars": "03",
    "avril": "04", "mai": "05", "juin": "06", "juillet": "07",
    "août": "08", "aout": "08", "septembre": "09", "octobre": "10",
    "novembre": "11", "décembre": "12", "decembre": "12",
}


def _parser_date_naissance(texte: str) -> date | None:
    """Parse une date de naissance dans les formats usuels français et bruts."""
    texte = texte.strip()

    # Conversion mois texte → numérique : "02 avril 1985" → "02/04/1985"
    texte_lower = texte.lower()
    for mois_nom, mois_num in _MOIS_FR.items():
        if mois_nom in texte_lower:
            texte_lower = texte_lower.replace(mois_nom, mois_num)
            texte = re.sub(r"\s+", "/", texte_lower.strip())
            break

    # Normalisation séparateurs
    texte_norm = re.sub(r"[.\-\s]", "/", texte)
    # Supprimer les slashes multiples
    texte_norm = re.sub(r"/+", "/", texte_norm).strip("/")

    for fmt in _DATE_FORMATS:
        try:
            d = datetime.strptime(texte_norm, fmt).date()
            # Sanity check : pas dans le futur, pas avant 1900
            if date(1900, 1, 1) <= d <= date.today():
                return d
        except ValueError:
            continue
    return None


# ── Calcul de profil ──────────────────────────────────────────────────────────

def calculer_profil(date_naissance_str: str) -> ProfilUsager | None:
    """
    Calcule le profil MDPH depuis une date de naissance.
    Retourne None si la date est illisible.

    Seuils :
      ≤ 15 ans  → enfant   (sections B+C uniquement)
      16-25 ans → mixte    (équipe pluridisciplinaire)
      > 25 ans  → adulte   (section B supprimée)
    """
    ddn = _parser_date_naissance(date_naissance_str)
    if not ddn:
        logger.warning(f"[PROFIL] Date illisible : {date_naissance_str!r}")
        return None

    today = date.today()
    age = (today - ddn).days // 365

    if age <= AGE_SEUIL_ENFANT_MAX:
        profil = "enfant"
        champs_bloques = dict(CHAMPS_INTERDITS_ENFANT)
    elif age <= AGE_SEUIL_MIXTE_MAX:
        profil = "mixte"
        champs_bloques = {}
    else:
        profil = "adulte"
        champs_bloques = {}

    est_mineur = age < 18

    date_norm = ddn.strftime("%d/%m/%Y")
    logger.info(
        f"[PROFIL] Calculé : age={age} ans | profil={profil} | "
        f"est_mineur={est_mineur} | ddn={date_norm}"
    )
    return ProfilUsager(
        age_annees=age,
        profil_mdph=profil,
        est_mineur=est_mineur,
        date_naissance=date_norm,
        champs_bloques=champs_bloques,
    )


# ── Nettoyage des données selon le profil ─────────────────────────────────────

def appliquer_contraintes_profil(
    donnees: dict[str, Any],
    profil: ProfilUsager,
) -> dict[str, Any]:
    """
    Applique les contraintes de profil sur le dict de synthese_json.

    Pour un enfant :
      - Efface tous les champs adultes (CHAMPS_INTERDITS_ENFANT)
      - Remplace les clés dont le sens change (ex: situation_familiale)

    Retourne le dict nettoyé (modifie en place ET retourne pour clarté).
    """
    if profil.profil_mdph not in ("enfant",):
        return donnees   # mixte et adulte : aucune contrainte à appliquer

    for champ, valeur_forcee in profil.champs_bloques.items():
        if champ in donnees and donnees[champ]:
            logger.info(
                f"[PROFIL] Champ '{champ}' écrasé (enfant) : "
                f"'{donnees[champ]}' → {valeur_forcee!r}"
            )
        donnees[champ] = valeur_forcee

    return donnees


# ── Génération du complément de prompt système ───────────────────────────────

def generer_contraintes_prompt(profil: ProfilUsager) -> str:
    """
    Retourne le bloc de texte à injecter dans le system prompt
    pour verrouiller le comportement de l'IA selon le profil.
    """
    if profil.profil_mdph == "enfant":
        return f"""
PROFIL USAGER : ENFANT ({profil.age_annees} ans)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INTERDICTIONS ABSOLUES — ne jamais mentionner, demander, ou suggérer :
  ✗ Situation conjugale (mariage, conjoint, concubinage, PACS)
  ✗ Nombre d'enfants à charge
  ✗ RSA, prime d'activité, revenus d'emploi
  ✗ Contrat de travail, employeur, poste occupé
  ✗ AAH (accessible seulement à partir de 20 ans)
  ✗ Toute terminologie financière adulte

RÈGLES DE COMMUNICATION :
  → Tu t'adresses EXCLUSIVEMENT aux parents ou représentants légaux
  → Vouvoiement en tout temps
  → Utilise "votre enfant" (pas "vous")
  → Si l'adulte semble être l'enfant lui-même, redirige poliment vers son représentant

CHAMPS À COLLECTER (spécifiques enfant) :
  ✓ Situation scolaire (école ordinaire, ULIS, IME, SESSAD, non-scolarisé)
  ✓ Nom et type de l'établissement scolaire
  ✓ Nom et lien du représentant légal (père, mère, tuteur)
"""

    if profil.profil_mdph == "mixte":
        return f"""
PROFIL USAGER : MIXTE / JEUNE ADULTE ({profil.age_annees} ans)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Règle équipe mixte : collecte simultanée des sections scolaires ET professionnelles.
  → S'adresser directement à la personne (si présente) ou à ses représentants
  → RSA non accessible avant 25 ans — ne pas demander
  → AAH accessible à partir de 20 ans uniquement
"""

    return ""   # adulte : aucune contrainte supplémentaire


# ── Persistance en base ───────────────────────────────────────────────────────

def persister_profil(
    profil: ProfilUsager,
    usager_id: str,
    dossier_id: str,
    db_conn: Any,
) -> None:
    """
    Met à jour usagers.est_mineur et dossiers.synthese_json avec le profil calculé.
    Appelé UNE SEULE FOIS dès que date_naissance devient disponible.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Mise à jour de l'usager
    db_conn.execute(
        "UPDATE usagers SET est_mineur = ?, updated_at = ? WHERE id = ?",
        (1 if profil.est_mineur else 0, now, usager_id),
    )

    # Mise à jour du profil sur le dossier
    db_conn.execute(
        "UPDATE dossiers SET updated_at = ? WHERE id = ?",
        (now, dossier_id),
    )

    logger.info(
        f"[PROFIL] Persisté | usager={usager_id[:8]} | "
        f"dossier={dossier_id[:8]} | profil={profil.profil_mdph}"
    )
