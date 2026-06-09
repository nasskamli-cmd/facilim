"""
app/engines/verbatim_engine.py — Collecte et filtrage des verbatim significatifs.

Responsabilités :
  1. Déterminer si un message usager est "significatif" (mérite d'être conservé)
  2. Attribuer un message à une section CERFA (B/C/D/E)
  3. Extraire les repères chronologiques (standards et libres)
  4. Accumuler les verbatim dans synthese_json sans jamais écraser

RÈGLE ABSOLUE : aucun appel LLM dans ce module.
Tout est déterministe — regex + heuristiques simples.
"""

from __future__ import annotations

import re
from typing import Any

# ── Plafond par section ───────────────────────────────────────────────────────
MAX_VERBATIM_PAR_SECTION  = 20
LONGUEUR_MIN_VERBATIM     = 8    # mots minimum pour être candidat (WhatsApp = messages courts)
LONGUEUR_MIN_RICHE        = 10   # mots minimum pour évaluation richesse (relance)

# ── Patterns de signification ─────────────────────────────────────────────────
# Un message est significatif s'il contient au moins un signal dans l'une des 5 catégories.

_PATTERNS_LIMITATION = [
    r"ne (peux|peut|pouvons|pouvez|peuvent) (pas|plus)",
    r"ne (parviens|parvient|parvenons|parvenez|parviennent) (pas|plus)",
    r"diffi(cile|cilement|cultés?)",
    r"impossibl[e]",
    r"incapabl[e]",
    r"avec (de l.)?aide",
    r"limité(e)?",
    r"restreint(e)?",
    r"ne fait? plus",
    r"ne marche? plus",
    r"n.?arrive? (pas|plus)",
    r"n.?y arrive? (pas|plus)",
    r"j.?ai (du|de la) mal",
    r"galère",
    r"peine à",
    r"(douleurs?|mal)\s+(dans|au|à)",   # "douleurs dans les jambes"
]

_PATTERNS_CONSEQUENCE = [
    r"(ce qui|ça|cela) (m.empêche|empêche|me|nous)",
    r"du coup",
    r"alors",
    r"donc",
    r"par conséquent",
    r"en conséquence",
    r"résultat",
    r"du coup je",
    r"(c.est pourquoi|c.est pour ça)",
    r"à cause de (ça|cela|ça|mon|ma|mes|son|sa|ses)",
    r"(ça|cela) m.a (obligé|forcé|poussé)",
    r"j.ai (dû|été obligé)",
    r"mon (mari|femme|fils|fille|mère|père|aidant) (doit|fait|prend)",
]

_PATTERNS_BESOIN = [
    r"j.?ai besoin",
    r"(il|elle) (lui|me) faut",
    r"j.?aurais besoin",
    r"(il|elle) aurait besoin",
    r"(j.ai|on a) besoin",
    r"nécessaire",
    r"indispensable",
    r"sans (aide|accompagnement|soutien)",
    r"on (m.aide|l.aide|nous aide)",
    r"quelqu.un (m.aide|l.aide|doit aider)",
    r"aide (humaine|technique|financière)",
]

_PATTERNS_EMOTION = [
    r"je (me sens|ressens|vis)",
    r"c.?est (difficile|dur|épuisant|lourd|pesant|terrible|horrible|compliqué)",
    r"(c est|c'est) (difficile|dur|epuisant|lourd|pesant|terrible|horrible|complique)",
    r"(j.ai|il a|elle a) (honte|peur|mal|du mal)",
    r"(j.en peux|j.en pouvais) plus",
    r"(ça|cela) (m.affecte|m.impacte|me touche|m.atteint|me pèse)",
    r"(je souffre|il souffre|elle souffre)",
    r"(épuisé|épuisée|dépassé|dépassée|perdu|perdue)",
    r"(seul|seule) (dans|face à)",
    r"(c.est|c.était) (compliqué|dur|difficile) (pour|de)",
    r"(ma|notre) (vie|famille|relation|quotidien) (a changé|est difficile|n.est plus)",
    r"je (n.ose|n.osais) plus",
    r"(ça me|ça nous) (pèse|déprime|angoisse|stresse)",
]

_PATTERNS_OBJECTIF = [
    r"(je|il|elle) (voudrai|voudrais|voudrait|aimerais|aimerait|souhaite|souhaites?)",
    r"(mon|notre|son) (objectif|projet|but|souhait|rêve|ambition)",
    r"(j.espère|il espère|elle espère)",
    r"(pour pouvoir|pour être capable|pour arriver à)",
    r"(j.aimerais?|il aimerait|elle aimerait)",
    r"dans l.idéal",
    r"(à terme|à l.avenir|plus tard)",
    r"(continuer|reprendre|retrouver|maintenir)",
]

_CATEGORIES: dict[str, list[str]] = {
    "limitation":  _PATTERNS_LIMITATION,
    "consequence": _PATTERNS_CONSEQUENCE,
    "besoin":      _PATTERNS_BESOIN,
    "emotion":     _PATTERNS_EMOTION,
    "objectif":    _PATTERNS_OBJECTIF,
}

# ── Attribution onglet → section ─────────────────────────────────────────────
_SECTION_PAR_ONGLET: dict[int, str | None] = {
    1: None, 2: None, 3: None,   # accueil/identité — pas de verbatim
    4: "b",  5: "b",  6: "b",   # vie quotidienne
    7: "c",                       # scolarité
    8: "d",                       # emploi
    9: "e",  10: "e",            # projet de vie + aidant
}

# ── Chronologie standard ──────────────────────────────────────────────────────
_PATTERNS_CHRONO_STANDARD: dict[str, list[str]] = {
    "debut_limitations": [
        r"depuis\s+(\d{1,2}\s+(?:an|mois|semaine)s?(?:\s+et\s+demi)?)",
        r"depuis\s+(20\d{2}|19\d{2})",
        r"il y a\s+(\d{1,2}\s+(?:an|mois)s?)",
        r"depuis\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+\d{4}",
        r"depuis\s+(mon|ma|mes|son|sa|ses|l[ae])\s+\w+",
    ],
    "debut_situation_pro": [
        r"en arrêt\s+(?:de travail\s+)?depuis\s+(\d+\s+(?:an|mois)s?)",
        r"plus au travail depuis\s+(\d+\s+(?:an|mois)s?)",
        r"licencié\w*\s+(?:en|il y a)\s+(\d{4}|\d+\s+(?:an|mois)s?)",
        r"(?:en chômage|sans emploi)\s+depuis\s+(\d+\s+(?:an|mois)s?)",
    ],
    "debut_situation_scolaire": [
        r"(?:en|depuis)\s+(?:la\s+)?(?:CP|CE1|CE2|CM1|CM2|6ème|5ème|4ème|3ème|seconde|première|terminale)",
        r"depuis\s+(?:l.entrée|son entrée)\s+en\s+\w+",
        r"dès\s+(?:la\s+)?(?:maternelle|primaire|le CP|l.école)",
    ],
    "debut_accompagnement": [
        r"suivi\w*\s+depuis\s+(\d+\s+(?:an|mois)s?)",
        r"(?:en\s+)?thérapie\s+depuis\s+(\d+\s+(?:an|mois)s?)",
        r"traitement\s+depuis\s+(\d{4}|\d+\s+(?:an|mois)s?)",
        r"hospitalisé\w*\s+(?:en|il y a)\s+(\d{4}|\d+\s+(?:an|mois)s?)",
    ],
    "evenement_declencheur": [
        r"après\s+(?:mon|ma|mes|son|sa|l[ae]|un[e]?\s+)\w+(?:\s+\w+)?",
        r"suite à\s+\w+(?:\s+\w+)?",
        r"depuis\s+(?:le\s+)?(?:diagnostic|accident|opération|chute|AVC|infarctus|burnout)",
        r"quand\s+(?:j.ai|on\s+a|il\s+a|elle\s+a)\s+(?:appris|découvert|su|reçu\s+le\s+diagnostic)",
    ],
}

# ── Chronologie libre (repères non standards) ─────────────────────────────────
_PATTERNS_CHRONO_LIBRE: list[str] = [
    r"quand\s+j.?(?:étais|etais|avais|travaillais|habitais|vivais)\s+\w+(?:\s+\w+){0,3}",
    r"quand\s+(?:il|elle)\s+(?:était|etait|avait|allait)\s+\w+(?:\s+\w+){0,3}",
    r"après\s+(?:mon|ma|mes|son|sa|le|la)\s+licenciement\w*",
    r"après\s+(?:ma|la|sa)\s+(?:naissance|grossesse)",
    r"après\s+(?:la\s+naissance\s+de|l.arrivée\s+de)\s+\w+",
    r"avant\s+(?:le\s+)?(?:covid|confinement|covid-19)",
    r"pendant\s+(?:le\s+)?(?:covid|confinement)",
    r"depuis\s+(?:le\s+)?(?:covid|confinement)",
    r"quand\s+j.(?:ai|avais)\s+commencé\w*\s+(?:mon|le|la|les|ce|cette)\s+\w+",
    r"quand\s+(?:j.étais|il était|elle était)\s+au\s+(?:collège|lycée|primaire|CP|CM|CE)",
    r"à\s+l.époque\s+(?:où|de|du|de la)\s+\w+(?:\s+\w+){0,2}",
    r"quand\s+(?:j.habitais|on habitait|il habitait|elle habitait)\s+\w+",
    r"(?:avant|après)\s+(?:mon|ma|notre)\s+(?:divorce|séparation|rupture|mariage)",
    r"depuis\s+(?:que|qu.)\s+(?:je|il|elle|on|nous)\s+(?:suis|est|sommes|avons?|ai)\s+\w+",
    r"à\s+l.âge\s+de\s+\d+\s+ans",
    r"(?:en|pendant)\s+ma\s+(?:jeunesse|enfance|adolescence)",
    r"(?:en|à partir de|courant|dès)\s+(?:19|20)\d{2}",       # « en 2025 », « dès 2018 »
    r"plusieurs\s+(?:ans|années|mois|semaines)",              # « plusieurs années »
    r"quelques\s+(?:ans|années|mois|semaines|jours)",
    r"il y a\s+\d+\s+(?:ans?|mois|semaines?)",
]


# ── Réponse à une question temporelle (« depuis quand ? ») ────────────────────
# Une réponse qui donne une date, une année ou une durée RÉPOND à « depuis quand ».
# Elle ne doit donc jamais être jugée « pauvre » ni relancée en boucle, même courte
# (« en 2025 », « depuis plusieurs années »). C'est la cause de la boucle du test 11.
_PATTERNS_REPONSE_TEMPORELLE: list[str] = [
    r"\b(?:19|20)\d{2}\b",                                    # une année : 2025, 1998
    r"\bdepuis\b",
    r"\bil y a\s+\d+",
    r"\b\d+\s*(?:an|ans|mois|semaines?|années?)\b",
    r"\bplusieurs\s+(?:ans|années|mois|semaines)\b",
    r"\bquelques\s+(?:ans|années|mois|semaines|jours)\b",
    r"\b(?:toujours|de naissance|à la naissance|enfance|toute ma vie|longtemps|récemment)\b",
    r"\b(?:janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|"
    r"septembre|octobre|novembre|décembre|decembre)\b",
]


def repond_a_question_temporelle(texte: str) -> bool:
    """True si le message donne une date, une année ou une durée (répond à « depuis quand »)."""
    t = (texte or "").lower()
    return any(re.search(p, t) for p in _PATTERNS_REPONSE_TEMPORELLE)


def est_verbatim_significatif(texte: str) -> tuple[bool, list[str]]:
    """
    Évalue si un message usager mérite d'être conservé comme verbatim.

    Retourne (significatif: bool, categories: list[str]).
    Un message est significatif s'il :
    - contient au moins LONGUEUR_MIN_VERBATIM mots
    - ET déclenche au moins un pattern dans l'une des 5 catégories
    """
    mots = texte.strip().split()
    if len(mots) < LONGUEUR_MIN_VERBATIM:
        return False, []

    t = texte.lower()
    categories_trouvees: list[str] = []
    for nom_cat, patterns in _CATEGORIES.items():
        if any(re.search(p, t) for p in patterns):
            categories_trouvees.append(nom_cat)

    return len(categories_trouvees) > 0, categories_trouvees


def section_depuis_onglet(onglet: int) -> str | None:
    """Retourne la section CERFA ('b'|'c'|'d'|'e') correspondant à l'onglet courant."""
    return _SECTION_PAR_ONGLET.get(onglet)


def accumuler_verbatim(
    donnees: dict[str, Any],
    message_usager: str,
    onglet_courant: int,
) -> dict[str, Any]:
    """
    Ajoute le message à la liste verbatim de sa section si significatif.
    Retourne les donnees mises à jour (modifiées en place).

    Règles :
    - Attribution par onglet → section
    - Filtrage par signification (5 catégories)
    - Plafond MAX_VERBATIM_PAR_SECTION = 20 (les 20 plus récents significatifs)
    - Aucun doublon exact
    """
    section = section_depuis_onglet(onglet_courant)
    if not section:
        return donnees

    cle = f"_verbatim_{section}"
    significatif, _ = est_verbatim_significatif(message_usager)
    if not significatif:
        return donnees

    liste_actuelle: list[str] = donnees.get(cle) or []

    # Éviter les doublons exacts
    texte_norm = message_usager.strip()
    if texte_norm in liste_actuelle:
        return donnees

    liste_actuelle.append(texte_norm)

    # Plafond : conserver les 20 plus récents
    if len(liste_actuelle) > MAX_VERBATIM_PAR_SECTION:
        liste_actuelle = liste_actuelle[-MAX_VERBATIM_PAR_SECTION:]

    donnees[cle] = liste_actuelle
    return donnees


def extraire_chronologie(
    message_usager: str,
    chronologie_existante: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Extrait les repères temporels d'un message usager.
    Merge avec la chronologie existante (ne jamais écraser).

    Retourne le dict chronologie mis à jour.
    """
    chrono = dict(chronologie_existante or {})
    t = message_usager.lower()

    # Chronologie standard (champs typés)
    for champ, patterns in _PATTERNS_CHRONO_STANDARD.items():
        if champ in chrono:
            continue   # déjà renseigné — ne pas écraser
        for p in patterns:
            m = re.search(p, t, re.IGNORECASE)
            if m:
                # Capturer le groupe si défini, sinon tout le match
                valeur = m.group(1) if m.lastindex else m.group(0)
                chrono[champ] = valeur.strip()
                break

    # Chronologie libre (repères non standards — liste cumulée)
    evenements_libres: list[str] = list(chrono.get("chronologie_evenements_libres") or [])
    for p in _PATTERNS_CHRONO_LIBRE:
        m = re.search(p, t, re.IGNORECASE)
        if m:
            fragment = message_usager[m.start():m.end()].strip()
            if fragment and fragment.lower() not in [e.lower() for e in evenements_libres]:
                evenements_libres.append(fragment)

    if evenements_libres:
        chrono["chronologie_evenements_libres"] = evenements_libres

    return chrono


def enregistrer_enrichissement(
    donnees: dict[str, Any],
    section: str,
    texte_avant: str,
    texte_apres: str,
) -> dict[str, Any]:
    """
    Calcule et enregistre le taux d'enrichissement d'une relance.

    taux = nb_mots_après / nb_mots_avant
    Seuil d'efficacité : taux >= 2.0

    Stocké dans donnees["_enrichissement_relances"] (liste cumulée).
    Le taux moyen est accessible via donnees["_taux_enrichissement_moyen"].
    """
    mots_avant = len(texte_avant.strip().split()) or 1   # évite division par zéro
    mots_apres = len(texte_apres.strip().split())
    taux       = round(mots_apres / mots_avant, 2)
    enrichi    = taux >= 2.0

    evenement = {
        "section":    section,
        "mots_avant": mots_avant,
        "mots_apres": mots_apres,
        "taux":       taux,
        "enrichi":    enrichi,
    }

    historique: list[dict] = list(donnees.get("_enrichissement_relances") or [])
    historique.append(evenement)
    donnees["_enrichissement_relances"] = historique

    # Recalcul de la moyenne glissante
    taux_liste = [e["taux"] for e in historique]
    donnees["_taux_enrichissement_moyen"] = round(sum(taux_liste) / len(taux_liste), 2)

    return donnees


def evaluer_richesse_reponse(texte: str) -> tuple[bool, str]:
    """
    Évalue si la réponse d'un usager est suffisamment riche pour alimenter
    le CERFA sans relance.

    Retourne (est_pauvre: bool, raison: str).
    Une réponse est pauvre si :
      - elle contient moins de 10 mots, OU
      - elle ne déclenche aucune des 5 catégories de signification

    Utilisé par l'orchestrateur pour décider si une relance est nécessaire.
    """
    mots = texte.strip().split()
    # Une réponse qui situe dans le temps (« en 2025 », « depuis plusieurs années »)
    # répond pleinement à une question « depuis quand » : ne jamais la relancer,
    # même si elle est courte. Sans ce garde-fou, la relance « depuis quand »
    # tournait en boucle (test 11).
    if repond_a_question_temporelle(texte):
        return False, "réponse temporelle (date ou durée fournie)"
    if len(mots) < LONGUEUR_MIN_RICHE:
        return True, f"réponse trop courte ({len(mots)} mots)"

    _, categories = est_verbatim_significatif(texte)
    if not categories:
        return True, "aucune limitation, conséquence, besoin, émotion ou objectif détecté"

    return False, "réponse suffisante"


# ── Sections qui bénéficient d'une relance ───────────────────────────────────
SECTIONS_AVEC_RELANCE = frozenset({"b", "d", "e"})   # + "c" si enfant
SECTIONS_AVEC_RELANCE_ENFANT = frozenset({"b", "c", "e"})


def section_eligible_relance(section: str | None, profil_mdph: str = "adulte") -> bool:
    """Retourne True si la section justifie une relance en cas de réponse pauvre."""
    if not section:
        return False
    if profil_mdph == "enfant":
        return section in SECTIONS_AVEC_RELANCE_ENFANT
    return section in SECTIONS_AVEC_RELANCE


def formater_verbatim_pour_prompt(
    donnees: dict[str, Any],
    section: str,
    max_items: int = 10,
) -> str:
    """
    Formate les verbatim d'une section pour injection dans un prompt LLM.
    Retourne une chaîne vide si aucun verbatim disponible.
    """
    cle = f"_verbatim_{section}"
    liste: list[str] = donnees.get(cle) or []
    if not liste:
        return ""

    items = liste[-max_items:]  # les plus récents en priorité
    lignes = "\n".join(f'- "{v}"' for v in items)
    return (
        f"\nVERBATIM COLLECTÉS — paroles exactes de la personne "
        f"(utiliser prioritairement, reformuler ou citer entre guillemets) :\n"
        f"{lignes}\n"
    )


def formater_chronologie_pour_prompt(donnees: dict[str, Any]) -> str:
    """
    Formate la chronologie pour injection dans un prompt LLM.
    """
    chrono: dict = donnees.get("chronologie") or {}
    libres: list = chrono.get("chronologie_evenements_libres") or []

    if not chrono and not libres:
        return ""

    lignes: list[str] = []

    _LABELS = {
        "debut_limitations":       "Début des limitations",
        "debut_situation_pro":     "Changement professionnel",
        "debut_situation_scolaire": "Changement scolaire",
        "debut_accompagnement":    "Début de l'accompagnement",
        "evenement_declencheur":   "Événement déclencheur",
    }
    for champ, label in _LABELS.items():
        if champ in chrono and champ != "chronologie_evenements_libres":
            lignes.append(f"- {label} : {chrono[champ]}")

    if libres:
        lignes.append("- Repères de vie mentionnés : " + " · ".join(libres[:5]))

    if not lignes:
        return ""

    return "\nCHRONOLOGIE DÉCLARÉE (intégrer dans le texte pour situer dans le temps) :\n" + "\n".join(lignes) + "\n"
