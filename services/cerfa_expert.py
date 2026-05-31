"""
services/cerfa_expert.py — Agent expert CERFA MDPH.

S'intercale AVANT cerfa_filler. Détermine le profil MDPH, vérifie les
cohérences, enrichit les données structurées, génère la narration P8.

Pipeline :
  dossier brut
    → analyser_profil_mdph()   → profil + alertes + cohérence
    → enrichir_donnees_cerfa() → ds enrichi + narration_p8
    → remplir_cerfa()          → PDF

Retour de analyser_profil_mdph() :
    {
        "profil":         "ENFANT" | "MIXTE" | "ADULTE",
        "coherence":      { urgence, logement_critique, aidant, protection_juridique },
        "cerfa":          dict enrichi prêt pour remplir_cerfa,
        "alertes":        list[str],
        "justifications": list[str],
        "narration_p8":   str,
    }
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes métier
# ---------------------------------------------------------------------------

_NIVEAUX_PRIMAIRES = {"cp", "ce1", "ce2", "cm1", "cm2", "maternelle",
                      "ps", "ms", "gs", "tps"}
_NIVEAUX_COLLEGE   = {"6ème", "5ème", "4ème", "3ème", "6e", "5e", "4e", "3e"}
_NIVEAUX_LYCEE     = {"2nde", "seconde", "1ère", "première", "terminale"}
_ETABLISSEMENTS_SPECIALISES = {"ime", "itep", "sessad", "ulis", "esat", "camsp",
                                "mas", "fam", "savs", "samsah", "uema"}

_MOTS_URGENCE_LOGEMENT = {
    "sans domicile", "sans abri", "sdf", "expulsé", "expulsion",
    "ne peut plus vivre", "hébergement d'urgence", "rupture", "mise en danger",
    "sécurité en danger", "hospitalisation", "foyer urgence",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _age_depuis_ddn(ddn: str) -> int | None:
    """Calcule l'âge à partir d'une date JJ/MM/AAAA. Retourne None si invalide."""
    if not ddn or "/" not in ddn:
        return None
    try:
        parts = ddn.split("/")
        if len(parts) == 3:
            j, m, a = int(parts[0]), int(parts[1]), int(parts[2])
            return (date.today() - date(a, m, j)).days // 365
    except Exception:
        pass
    return None


def _texte_contient(texte: str, mots: set) -> bool:
    t = texte.lower()
    return any(m in t for m in mots)


def _profil_depuis_age(age: int | None) -> str:
    if age is None:
        return "ADULTE"
    if age < 16:
        return "ENFANT"
    if age <= 25:
        return "MIXTE"
    return "ADULTE"


def _coherence_niveau_scolaire(classe: str, type_etab: str, age: int | None) -> bool:
    """
    Retourne True si le niveau scolaire est cohérent avec l'âge.
    Ex : CE2 à 21 ans → False.
    """
    if age is None:
        return True
    c = (classe or "").lower()
    e = (type_etab or "").lower()
    # Établissements spécialisés : toujours cohérents (pas de classe standard)
    if any(s in e for s in _ETABLISSEMENTS_SPECIALISES):
        return True
    if age >= 18 and any(n in c or n in e for n in _NIVEAUX_PRIMAIRES):
        return False
    if age >= 22 and any(n in c or n in e for n in _NIVEAUX_COLLEGE):
        return False
    return True


# ---------------------------------------------------------------------------
# Narration P8 — fallback sans LLM
# ---------------------------------------------------------------------------

def _construire_narration_fallback(
    prenom: str,
    nom: str,
    profil: str,
    difficultes: str,
    besoins_aide: str,
    is_enfant: bool,
) -> str:
    """
    Construit une narration P8 humaine sans LLM.
    Utilisée quand le LLM est indisponible.
    """
    identite = f"{prenom} {nom}".strip() or ("votre enfant" if is_enfant else "la personne")
    sujet    = identite

    # Détecter la voix depuis les données
    if is_enfant:
        # Parent qui écrit pour l'enfant
        possessif = f"mon fils {prenom}" if "homme" in (profil or "").lower() else f"ma fille {prenom}"
        # Fallback si genre inconnu
        possessif = possessif if prenom else f"{sujet}"
    else:
        possessif = "je"

    parties = []

    # --- Situation actuelle ---
    if difficultes and difficultes.strip():
        if is_enfant:
            parties.append(
                f"Au quotidien, {sujet} fait face à des difficultés importantes "
                f"qui nécessitent un accompagnement constant. {difficultes.strip()}"
            )
        else:
            parties.append(
                f"Au quotidien, je fais face à des difficultés importantes "
                f"qui limitent mon autonomie. {difficultes.strip()}"
            )

    # --- Retentissements ---
    if besoins_aide and besoins_aide.strip():
        if is_enfant:
            parties.append(
                f"Pour les actes essentiels de la vie — repas, habillage, hygiène, "
                f"déplacements — {sujet} a besoin d'aide. {besoins_aide.strip()}"
            )
        else:
            parties.append(
                f"Pour les actes essentiels de la vie — repas, habillage, hygiène, "
                f"déplacements — j'ai besoin d'aide. {besoins_aide.strip()}"
            )

    # --- Impact sur la vie familiale ---
    if is_enfant:
        parties.append(
            f"Cette situation a un impact direct sur notre vie de famille. "
            f"Un des parents a dû adapter son activité professionnelle pour assurer "
            f"l'accompagnement quotidien de {sujet}."
        )

    return "\n\n".join(parties)[:2000] if parties else ""


# ---------------------------------------------------------------------------
# Construire la narration P8 via LLM (avec fallback)
# ---------------------------------------------------------------------------

def _generer_narration_p8(
    prenom: str,
    nom: str,
    profil: str,
    is_enfant: bool,
    difficultes: str,
    besoins_aide: str,
    geva_pro: str,
    elements_probants: list,
) -> str:
    """
    Génère la narration P8 via LLM (gpt-4o-mini) ou fallback texte.
    """
    identite = f"{prenom} {nom}".strip() or ("l'enfant" if is_enfant else "la personne")

    contexte = "\n".join(filter(None, [
        difficultes,
        besoins_aide,
        geva_pro,
        " | ".join(str(e) for e in (elements_probants or []) if e),
    ]))
    if not contexte.strip():
        return ""

    try:
        from config import get_settings as _gs
        import openai as _openai

        _client = _openai.OpenAI(api_key=_gs().openai_api_key)

        if is_enfant:
            voix = (
                f"un parent qui parle de son enfant {identite} "
                f"(utiliser 'mon fils'/'ma fille'/{identite}, jamais 'je' pour l'enfant)"
            )
        else:
            voix = f"la personne elle-même ({identite}) à la 1ère personne (je, me, mon...)"

        prompt = f"""Tu rédiges la section 'Description de la situation et des difficultés' du formulaire MDPH pour {identite}.

VOIX : {voix}

STRUCTURE OBLIGATOIRE (texte continu, sans titres ni puces) :
1. LE MATIN — réveil, toilette, habillage, petit-déjeuner : ce qui se passe, ce qui est difficile
2. LA JOURNÉE — déplacements, communication, apprentissages, relations sociales, gestion des tâches
3. LE SOIR — repas, toilette, coucher, fatigue accumulée
4. IMPACT SUR L'ENTOURAGE — famille, aidants, aménagements nécessaires

RÈGLES STRICTES :
- Phrases courtes et concrètes, jamais de jargon médical
- Décrire les limitations fonctionnelles, pas les diagnostics
- Minimum 800 caractères, maximum 2000
- Pas de listes à puces, pas de tirets, texte continu
- Ne jamais mentionner : RSDAE, PCH, AAH, MDPH, score, algorithme, GEVA
- Utiliser des formulations fortes : "ne peut pas", "doit être aidé pour", "est incapable seul de"

Informations disponibles :
{contexte}"""

        resp = _client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.4,
        )
        texte = resp.choices[0].message.content.strip()
        logger.info(f"[EXPERT-P8] Narration LLM générée ({len(texte)} chars)")
        return texte[:2000]

    except Exception as e:
        logger.warning(f"[EXPERT-P8] LLM indisponible, fallback : {e}")
        return _construire_narration_fallback(
            prenom, nom, profil, difficultes, besoins_aide, is_enfant
        )


# ---------------------------------------------------------------------------
# Point d'entrée principal
# ---------------------------------------------------------------------------

def analyser_profil_mdph(dossier: dict[str, Any]) -> dict[str, Any]:
    """
    Analyse le profil MDPH du dossier, vérifie les cohérences et enrichit
    les données structurées pour le remplissage du CERFA.

    Args:
        dossier: dossier brut (même structure que pour remplir_cerfa)

    Returns:
        {
            "profil":         str,
            "coherence":      dict,
            "cerfa":          dict,   ← dossier enrichi à passer à remplir_cerfa
            "alertes":        list[str],
            "justifications": list[str],
            "narration_p8":   str,
        }
    """
    alertes:        list[str] = []
    justifications: list[str] = []
    coherence:      dict      = {}

    analyse  = dossier.get("analyse") or {}
    ds       = dict(analyse.get("donnees_structurees") or {})  # copie pour enrichissement
    cerfa_rep = dossier.get("cerfa_reponses") or {}

    # ── Identité de base ─────────────────────────────────────────────────────
    nom    = (dossier.get("nom_enfant") or ds.get("nom") or "").strip().upper()
    prenom = (dossier.get("prenom_enfant") or ds.get("prenom") or "").strip()
    ddn    = (dossier.get("ddn_enfant") or cerfa_rep.get("date_naissance")
              or dossier.get("date_naissance") or "").strip()

    age = _age_depuis_ddn(ddn)

    # ─────────────────────────────────────────────────────────────────────────
    # ÉTAPE 0 — Déterminer le profil
    # ─────────────────────────────────────────────────────────────────────────
    _is_enfant_ds = ds.get("is_enfant")
    if _is_enfant_ds is not None:
        is_enfant = bool(_is_enfant_ds)
    elif age is not None:
        is_enfant = age < 18
    else:
        is_enfant = True  # défaut conservateur

    profil = _profil_depuis_age(age)

    # Forcer ENFANT si is_enfant explicitement True dans ds
    if _is_enfant_ds is True and profil != "ENFANT":
        profil = "ENFANT"
        is_enfant = True

    justifications.append(
        f"Profil {profil} retenu — âge {'inconnu' if age is None else f'{age} ans'}"
        f"{', is_enfant forcé depuis analyse IA' if _is_enfant_ds is not None else ''}"
    )

    # ─────────────────────────────────────────────────────────────────────────
    # ÉTAPE 1 — Contrôle de cohérence
    # ─────────────────────────────────────────────────────────────────────────

    # --- Logement ---
    type_logement_detail = (
        ds.get("type_logement") or cerfa_rep.get("type_logement_statut") or ""
    ).lower()
    difficultes_txt = (
        ds.get("difficultes_quotidiennes")
        or cerfa_rep.get("difficultes_quotidiennes")
        or dossier.get("difficultes_quotidiennes") or ""
    ).lower()

    logement_critique = _texte_contient(type_logement_detail, _MOTS_URGENCE_LOGEMENT)
    if not logement_critique:
        # Chercher aussi dans les difficultés
        logement_critique = _texte_contient(difficultes_txt, _MOTS_URGENCE_LOGEMENT)

    urgence_droits_raw = (cerfa_rep.get("urgence_droits") or dossier.get("urgence_droits") or "").lower()
    urgence_droits = any(w in urgence_droits_raw for w in ["oui", "yes", "1", "vrai"])

    urgence_finale = urgence_droits or logement_critique
    if urgence_finale:
        raison_urgence = []
        if urgence_droits:
            raison_urgence.append("droits expirant dans moins de 2 mois")
        if logement_critique:
            raison_urgence.append("situation de logement critique")
        coherence["urgence"] = "oui — " + " et ".join(raison_urgence)
        justifications.append(f"Urgence activée : {' + '.join(raison_urgence)}")
        ds["urgence_droits"] = True
    else:
        coherence["urgence"] = "non"

    coherence["logement_critique"] = "oui" if logement_critique else "non"

    # --- Protection juridique ---
    protection = (
        ds.get("protection_juridique")
        or cerfa_rep.get("protection_juridique")
        or dossier.get("protection_juridique") or "aucune"
    ).lower()

    if any(p in protection for p in ["tutelle", "curatelle", "sauvegarde", "habilitation"]):
        coherence["protection_juridique"] = f"mesure détectée : {protection}"
        justifications.append(f"Protection juridique : {protection} — pages 2-3 à renseigner")
        if not ds.get("protection_juridique"):
            ds["protection_juridique"] = protection
        if not ds.get("nom_tuteur") and not ds.get("nom_representant"):
            alertes.append(
                f"Mesure de protection '{protection}' détectée — "
                "nom du représentant légal manquant (à compléter par l'éducateur)"
            )
    else:
        coherence["protection_juridique"] = "aucune mesure"
        ds["protection_juridique"] = "aucune"

    # --- Aidant ---
    nom_aidant    = (ds.get("nom_aidant") or cerfa_rep.get("nom_aidant") or "").strip()
    prenom_aidant = (ds.get("prenom_aidant") or cerfa_rep.get("prenom_aidant") or "").strip()
    lien_aidant   = (ds.get("lien_aidant") or cerfa_rep.get("lien_aidant") or "").strip()
    aidant_reduction = ds.get("aidant_reduction_travail", False)

    if profil == "ENFANT":
        # Parent = aidant automatique pour enfant
        if not nom_aidant:
            nom_aidant    = nom       # nom de famille (même que l'enfant)
            prenom_aidant = prenom_aidant or ""
            lien_aidant   = lien_aidant or "Père / Mère (représentant légal)"
            ds["nom_aidant"]    = nom_aidant
            ds["prenom_aidant"] = prenom_aidant
            ds["lien_aidant"]   = lien_aidant
        coherence["aidant"] = f"parent aidant automatique (profil ENFANT) — {lien_aidant}"
        justifications.append("Aidant familial = parent, car profil ENFANT")
    elif nom_aidant or aidant_reduction:
        coherence["aidant"] = f"aidant identifié : {prenom_aidant} {nom_aidant} ({lien_aidant})"
        justifications.append(
            f"Aidant renseigné : {prenom_aidant} {nom_aidant}"
            + (" — réduction de travail confirmée" if aidant_reduction else "")
        )
    else:
        coherence["aidant"] = "non renseigné"
        if ds.get("besoins_aide_humaine"):
            alertes.append(
                "Aide humaine détectée mais aidant non identifié — "
                "demander 'aidant_identite' via WhatsApp"
            )

    # --- Cohérence scolarité ---
    classe_scolaire   = ds.get("classe_scolaire") or cerfa_rep.get("classe_scolaire") or ""
    type_etablissement = (ds.get("type_etablissement_scolaire") or "").lower()

    if not _coherence_niveau_scolaire(classe_scolaire, type_etablissement, age):
        alertes.append(
            f"Incohérence scolarité : niveau '{classe_scolaire}' "
            f"incompatible avec l'âge ({age} ans) — section P9-12 désactivée"
        )
        ds["scolarise"] = False
        classe_scolaire = ""
        justifications.append(
            f"Scolarité ignorée : niveau primaire détecté pour un adulte de {age} ans"
        )
    elif profil == "MIXTE" and type_etablissement in _ETABLISSEMENTS_SPECIALISES:
        justifications.append(
            f"Scolarité en établissement spécialisé ({type_etablissement}) — "
            "aucune classe ordinaire générée"
        )
        # Ne pas inventer de classe scolaire pour un établissement spécialisé
        if classe_scolaire and any(n in classe_scolaire.lower() for n in _NIVEAUX_PRIMAIRES):
            alertes.append(
                f"Classe '{classe_scolaire}' incohérente avec établissement "
                f"spécialisé '{type_etablissement}' — classe effacée"
            )
            ds["classe_scolaire"] = ""

    # --- NIR ---
    nss = (ds.get("nss") or ds.get("numero_securite_sociale")
           or cerfa_rep.get("numero_securite_sociale") or "").strip()
    if not nss:
        alertes.append(
            "NIR (numéro de sécurité sociale) manquant — à transmettre par email sécurisé. "
            + ("Pour un enfant : indiquer le NIR du parent déclarant." if is_enfant else "")
        )

    # --- Mode de contact ---
    pref_contact = (ds.get("preference_contact") or cerfa_rep.get("preference_contact") or "").lower()
    if not pref_contact:
        # Si dossier initié via WhatsApp → téléphone par défaut
        if dossier.get("telephone_famille"):
            ds["preference_contact"] = "telephone"
            justifications.append("Mode de contact = téléphone (dossier initié via WhatsApp)")
        else:
            alertes.append("Mode de contact non renseigné")

    # ─────────────────────────────────────────────────────────────────────────
    # ÉTAPE 2 — Narration P8
    # ─────────────────────────────────────────────────────────────────────────
    difficultes_brut = (
        dossier.get("difficultes_quotidiennes")
        or cerfa_rep.get("difficultes_quotidiennes")
        or ds.get("difficultes_quotidiennes") or ""
    )
    besoins_aide_brut = (
        dossier.get("besoins_aide")
        or cerfa_rep.get("besoins_aide")
        or ds.get("besoins_aide_narrative") or ""
    )
    syntheses  = analyse.get("synthese_agents") or {}
    geva_pro   = syntheses.get("geva_pro") or ""
    elements_p = analyse.get("elements_probants") or []

    narration_p8 = _generer_narration_p8(
        prenom=prenom,
        nom=nom,
        profil=profil,
        is_enfant=is_enfant,
        difficultes=difficultes_brut,
        besoins_aide=besoins_aide_brut,
        geva_pro=geva_pro,
        elements_probants=elements_p,
    )

    if len(narration_p8) < 800:
        alertes.append(
            f"Narration P8 trop courte ({len(narration_p8)} caractères) — "
            "enrichir les données de difficultés pour améliorer la qualité"
        )
    else:
        justifications.append(f"Narration P8 générée ({len(narration_p8)} caractères)")

    # ─────────────────────────────────────────────────────────────────────────
    # ÉTAPE 3 — Construire le dossier enrichi pour remplir_cerfa
    # ─────────────────────────────────────────────────────────────────────────
    dossier_enrichi = dict(dossier)
    # Injecter les données structurées enrichies
    if "analyse" not in dossier_enrichi:
        dossier_enrichi["analyse"] = {}
    dossier_enrichi["analyse"] = dict(dossier_enrichi["analyse"])
    dossier_enrichi["analyse"]["donnees_structurees"] = ds

    # Injecter la narration directement dans ds pour que _composer_description_p8
    # la reçoive via difficultes_quotidiennes si le LLM est indisponible
    if narration_p8 and not ds.get("difficultes_quotidiennes"):
        ds["difficultes_quotidiennes"] = narration_p8

    # Injecter aidant dans cerfa_reponses si détecté ici
    cerfa_rep_enrichi = dict(cerfa_rep)
    if nom_aidant and not cerfa_rep_enrichi.get("aidant_identite"):
        _aidant_str = f"{prenom_aidant} {nom_aidant}".strip()
        if lien_aidant:
            _aidant_str += f", {lien_aidant}"
        cerfa_rep_enrichi["aidant_identite"] = _aidant_str
    dossier_enrichi["cerfa_reponses"] = cerfa_rep_enrichi

    # ── Vérification finale ──────────────────────────────────────────────────
    champs_obligatoires_manquants = []
    for champ, label in [
        ("nom_prenom",              "nom et prénom"),
        ("date_naissance",          "date de naissance"),
        ("genre",                   "genre"),
        ("adresse_complete",        "adresse complète"),
        ("situation_familiale",     "situation familiale"),
        ("type_droits",             "type de droits demandés"),
        ("difficultes_quotidiennes", "difficultés quotidiennes"),
    ]:
        val = (dossier_enrichi.get(champ) or cerfa_rep_enrichi.get(champ)
               or ds.get(champ) or "")
        if not str(val).strip():
            champs_obligatoires_manquants.append(label)

    if champs_obligatoires_manquants:
        alertes.append(
            "Champs obligatoires manquants : "
            + ", ".join(champs_obligatoires_manquants)
        )

    logger.info(
        f"[EXPERT-MDPH] Profil={profil} | âge={age} | urgence={urgence_finale} "
        f"| alertes={len(alertes)} | narration_p8={len(narration_p8)} chars"
    )

    return {
        "profil":         profil,
        "coherence":      coherence,
        "cerfa":          dossier_enrichi,
        "alertes":        alertes,
        "justifications": justifications,
        "narration_p8":   narration_p8,
    }
