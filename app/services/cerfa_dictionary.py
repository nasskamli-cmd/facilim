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


# ── PARTIE B — Vie quotidienne : actes essentiels, aides, frais ───────────────
# Les actes (toilette, habillage, repas, déplacements, gestion) ne sont PAS posés
# un par un : l'assistant questionne OUVERTEMENT et ne cible un acte que si la
# personne en parle d'elle-même (règle dans _shared.py). Ici on rend « à demander »
# ce qui ne l'était jamais : aides humaines, aides techniques, frais restant à charge.
SECTION_B: list[dict[str, Any]] = [
    {
        "id": "aides_en_place",
        "section": "B",
        "profils": ("tous",),
        "requis": True,
        "extractible": True,
        "label": "Aide humaine au quotidien (qui et pour quoi)",
        "question": "Au quotidien, une personne vous aide-t-elle pour certains gestes ? Si oui, qui vous aide, et pour quoi ?",
        "cible_cerfa": "Aide humaine en place (narratif B / P6)",
    },
    {
        "id": "aides_techniques",
        "section": "B",
        "profils": ("tous",),
        "requis": True,
        "extractible": True,
        "label": "Aides techniques ou aménagements utilisés",
        "question": "Utilisez-vous du matériel ou des aménagements au quotidien (fauteuil, canne, aide auditive, adaptation du logement...) ?",
        "cible_cerfa": "Aides techniques (P6)",
    },
    {
        "id": "frais_handicap",
        "section": "B",
        "profils": ("tous",),
        "requis": True,
        "extractible": True,
        "label": "Frais liés au handicap restant à charge (non remboursés)",
        "question": "Avez-vous des dépenses liées à votre handicap qui restent à votre charge et qui ne sont pas remboursées ?",
        "cible_cerfa": "Frais liés au handicap (B1)",
    },
]


# ── PARTIE C — Scolarité (enfants et jeunes 16-25 ans UNIQUEMENT) ──────────────
# Conditionnel : un adulte n'est PAS concerné par la scolarité (profils restreints).
SECTION_C: list[dict[str, Any]] = [
    {
        "id": "type_etablissement_scolaire",
        "section": "C",
        "profils": ("enfant", "mixte"),
        "requis": True,
        "extractible": True,
        "label": "Type de scolarisation",
        "question": "Quel est le type de scolarisation actuel : école ordinaire, ULIS, IME, SESSAD, ITEP, ou autre ?",
        "valeurs": "ordinaire | ULIS | IME | SESSAD | ITEP | autre",
        "cible_cerfa": "C1 — type d'établissement (P9 / classe_ordinaire)",
    },
    {
        "id": "classe_scolaire",
        "section": "C",
        "profils": ("enfant", "mixte"),
        "requis": True,
        "extractible": True,
        "label": "Classe ou niveau scolaire actuel",
        "question": "En quelle classe ou à quel niveau scolaire en êtes-vous actuellement ?",
        "cible_cerfa": "Champ texte P9 2 (classe)",
    },
    {
        "id": "accompagnement_scolaire",
        "section": "C",
        "profils": ("enfant", "mixte"),
        "requis": True,
        "extractible": True,
        "label": "Accompagnement humain à l'école (AESH / AVS)",
        "question": "Y a-t-il un accompagnement à l'école (AESH ou AVS) ? Si oui, combien d'heures par semaine ?",
        "cible_cerfa": "C2 — AESH (P10 2)",
    },
    {
        "id": "amenagements_scolaires",
        "section": "C",
        "profils": ("enfant", "mixte"),
        "requis": True,
        "extractible": True,
        "label": "Aménagements scolaires en place",
        "question": "Y a-t-il des aménagements scolaires en place (tiers-temps, matériel adapté, projet PPS, GEVASCO) ?",
        "cible_cerfa": "C2 — aménagements (P10 1)",
    },
]


# ── PARTIE D — Situation professionnelle & projet (adultes, 16-25, protégés) ───
# Conditionnel : un enfant n'a PAS de situation professionnelle (profils restreints).
SECTION_D: list[dict[str, Any]] = [
    {
        "id": "situation_professionnelle",
        "section": "D",
        "profils": ("adulte", "mixte", "protege"),
        "requis": True,
        "extractible": True,
        "label": "Situation professionnelle actuelle",
        "question": "Quelle est votre situation professionnelle actuelle : en emploi, au chômage, en arrêt maladie, en invalidité, ou sans activité ?",
        "valeurs": "emploi | chomage | arret_maladie | invalidite | sans_activite",
        "cible_cerfa": "D1/D2 — situation pro (P13...)",
    },
    {
        "id": "consequences_professionnelles",
        "section": "D",
        "profils": ("adulte", "mixte", "protege"),
        "requis": True,
        "extractible": True,
        "label": "Conséquences de la santé sur le travail",
        "question": "Votre santé a-t-elle des conséquences sur votre travail : fatigabilité, restrictions, inaptitude, besoin d'aménagement du poste ?",
        "cible_cerfa": "D2 — retentissements professionnels",
    },
    {
        "id": "projet_professionnel",
        "section": "D",
        "profils": ("adulte", "mixte", "protege"),
        "requis": True,
        "extractible": True,
        "label": "Projet professionnel ou de reconversion",
        "question": "Avez-vous un projet professionnel, un souhait de reconversion ou de formation ?",
        "cible_cerfa": "D3 — projet professionnel (P16)",
    },
    {
        "id": "emploi_accompagne",
        "section": "D",
        "profils": ("adulte", "mixte", "protege"),
        "requis": True,
        "extractible": True,
        "label": "Besoin d'accompagnement vers ou dans l'emploi",
        "question": "Avez-vous besoin d'un accompagnement pour trouver ou garder un emploi (emploi accompagné, ESRP, ou milieu protégé type ESAT) ?",
        "valeurs": "oui | non",
        "cible_cerfa": "Orientation pro (P18 — ORP / ESAT / emploi accompagné)",
    },
]


# ── PARTIE E — Projet de vie et attentes (tous profils) ───────────────────────
SECTION_E: list[dict[str, Any]] = [
    {
        "id": "attentes_usager",
        "section": "E",
        "profils": ("tous",),
        "requis": True,
        "extractible": True,
        "label": "Attentes vis-à-vis de la MDPH",
        "question": "Qu'attendez-vous de la MDPH ? Quels sont vos besoins et vos demandes ?",
        "cible_cerfa": "E — attentes / projet de vie",
    },
    {
        "id": "projet_de_vie",
        "section": "E",
        "profils": ("tous",),
        "requis": True,
        "extractible": True,
        "label": "Objectifs et souhaits de vie",
        "question": "Quels sont vos objectifs, vos souhaits, vos projets de vie pour l'avenir ?",
        "cible_cerfa": "E — projet de vie",
    },
]


# ── PARTIE F — Aidant familial (recueilli quand une aide existe ; jamais inventé) ─
# Volontairement requis=False : ces champs ne sont pas posés mécaniquement. Une règle
# de conversation (dans _shared.py) demande l'aidant DÈS qu'une aide est évoquée, et
# pour un enfant le parent qui remplit EST l'aidant. Si la personne est seule, rien.
SECTION_F: list[dict[str, Any]] = [
    {
        "id": "aidant_identite",
        "section": "F",
        "profils": ("tous",),
        "requis": False,
        "extractible": True,
        "label": "Identité de l'aidant (nom et lien avec la personne)",
        "question": "Si une personne vous aide régulièrement au quotidien, qui est-elle (son nom et son lien avec vous) ?",
        "cible_cerfa": "E1/E2 — aidant familial (P19-P20)",
    },
    {
        "id": "aidant_reduction_travail",
        "section": "F",
        "profils": ("tous",),
        "requis": False,
        "extractible": True,
        "label": "Impact de l'aide sur l'activité professionnelle de l'aidant",
        "question": "Cette personne a-t-elle dû réduire ou aménager son travail pour vous aider ?",
        "valeurs": "oui | non",
        "cible_cerfa": "E2 — réduction d'activité de l'aidant",
    },
]


# Dictionnaire complet : A + B + C + D + E + F (couverture du formulaire)
_DICTIONNAIRE: list[dict[str, Any]] = (
    list(SECTION_A) + list(SECTION_B) + list(SECTION_C)
    + list(SECTION_D) + list(SECTION_E) + list(SECTION_F)
)


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


# ── ROUTE DE REMPLISSAGE — la jonction dictionnaire → CERFA ───────────────────
# C'est le 3e pilier annoncé en tête de fichier : on rend EXPLICITE par quel
# chemin chaque champ collecté atteint réellement le formulaire.
#   "filler"   : écrit directement par services/cerfa_filler.py (champ texte / case)
#   "narratif" : injecté via le texte narratif de sa section (B/C/D/E)
# Tout champ collecté DOIT avoir une route. Un champ porteur d'une valeur mais
# sans route, ou dont le narratif de section n'a pas été produit, est une donnée
# à risque de perte : on la signale à l'instructeur, jamais en silence.
ROUTE_REMPLISSAGE: dict[str, str] = {
    "preference_contact":           "filler",
    "organisme_payeur":             "filler",
    "numero_allocataire":           "filler",
    "organisme_assurance_maladie":  "filler",
    "nationalite":                  "filler",
    "nom_naissance":                "filler",
    "commune_naissance":            "filler",
    "pays_naissance":               "filler",
    "aides_en_place":               "narratif",
    "aides_techniques":             "narratif",
    "frais_handicap":               "filler",
    "type_etablissement_scolaire":  "filler",
    "classe_scolaire":              "filler",
    "accompagnement_scolaire":      "narratif",
    "amenagements_scolaires":       "narratif",
    "situation_professionnelle":    "filler",
    "consequences_professionnelles":"narratif",
    "projet_professionnel":         "filler",
    "emploi_accompagne":            "filler",
    "attentes_usager":              "narratif",
    "projet_de_vie":                "narratif",
    "aidant_identite":              "filler",
    "aidant_reduction_travail":     "filler",
}

# Clé du texte narratif produit pour chaque section (lu ensuite par le pont V2).
_NARRATIF_PAR_SECTION: dict[str, str] = {
    "B": "texte_b_vie_quotidienne",
    "C": "texte_c_scolarite",
    "D": "texte_d_situation_pro",
    "E": "texte_e_projet_vie",
}


def champs_a_risque_de_perte(donnees: dict, profil: str) -> list[dict[str, str]]:
    """
    Champs applicables AU profil, PORTEURS d'une valeur collectée, mais dont la
    route vers le CERFA n'est pas garantie :
      - aucune route déclarée, ou
      - route narrative alors que le narratif de la section est absent.
    Liste normalement vide. Tout retour signale une donnée collectée qui pourrait
    ne pas figurer sur le formulaire — à vérifier par l'instructeur.
    """
    risques: list[dict[str, str]] = []
    for c in _DICTIONNAIRE:
        if not _applicable(c, profil):
            continue
        cid = c["id"]
        if not donnees.get(cid):
            continue
        route = ROUTE_REMPLISSAGE.get(cid)
        if route is None:
            risques.append({"id": cid, "raison": "aucune route de remplissage déclarée"})
        elif route == "narratif":
            cle = _NARRATIF_PAR_SECTION.get(c.get("section", ""))
            if cle and not donnees.get(cle):
                risques.append({
                    "id": cid,
                    "raison": f"narratif de la section {c.get('section')} non produit "
                              f"— contenu collecté possiblement non reporté",
                })
    return risques
