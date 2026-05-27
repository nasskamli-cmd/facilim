"""
cerfa_filler.py — Pré-remplissage automatique du CERFA 15692*01 (MDPH national).

Couvre l'intégralité des sections remplissables sans intervention médicale,
pour les dossiers enfants ET adultes :

  Page 1  : Département MDPH + type de demande (1ère demande)
  Page 2  : Identité complète (nom, prénom, DDN, NSS, genre, adresse, contact)
  Page 3  : Représentant légal (uniquement si enfant ou adulte sous tutelle)
  Page 4  : Situation familiale
  Page 7  : Vie professionnelle (situation actuelle + projet professionnel)
  Page 8  : Description narrative des difficultés (1ère pers. adulte / 3ème pers. enfant)
  Page 9  : Aides et accompagnements déjà en place
  Page 10 : Besoins en aide humaine
  Page 11 : Besoins en aides techniques / aménagement logement
  Page 13 : Logement (adresse + type + statut)
  Page 17 : Demandes d'allocations (AEEH, PCH, AAH)
  Page 18 : Orientations (IME, SESSAD, ITEP, ESAT, SAVS, SAMSAH, MAS, FAM)
  Page 19 : Cartes et RQTH
  Bas de page : Nom / prénom répétés sur chaque page

Section médicale (page 5) : laissée vide — remplie par le médecin.

Corrections apportées (v2) :
  - Genre : cases OPTION P2 1 (Homme) / OPTION P2 2 (Femme) cochées depuis ds.genre
  - NSS adulte : Numero SS 3 → Numero SS 17 (au lieu de N° SS Enfant X)
  - Date B supprimée : ces champs remplissaient "date d'arrivée en France" par erreur
  - P8 : texte narratif à la 1ère personne pour les adultes, 3ème pour les enfants
           sans mention de RSDAE, ESAT, titres de section — humanisé via LLM dédié
  - P17/P18/P19 : cochage via annotation directe (plus fiable que update_page_form_field_values)
  - _mapper_droits : détection robuste par tokens, fallback besoins_aide_humaine
"""

import io
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Description narrative Page 8 du CERFA
# ─────────────────────────────────────────────────────────────────────────────

def _composer_description_p8(
    geva_pro: str,
    juriste: str,
    elements_probants: list,
    is_enfant: bool,
) -> str:
    """
    Compose le texte narratif de la page 8 du CERFA 15692 :
    « Description de la situation et des difficultés ».

    - Adulte : 1ère personne (« je ne peux pas… »)
    - Enfant  : 3ème personne (« il/elle ne peut pas… »)
    - Sans mention de RSDAE, ESAT, titres de section, ni jargon administratif.
    - Tente d'utiliser le LLM (gpt-4o-mini) pour humaniser le texte ;
      en cas d'échec, assemble les données brutes disponibles.
    """
    # ── Assemblage du contexte brut ───────────────────────────────────────────
    parties = []
    if geva_pro and geva_pro.strip():
        parties.append(geva_pro.strip())
    if juriste and juriste.strip():
        parties.append(juriste.strip())
    if elements_probants:
        probants_str = " | ".join(str(e) for e in elements_probants if e)
        if probants_str.strip():
            parties.append(probants_str.strip())

    contexte_brut = "\n\n".join(parties).strip()

    if not contexte_brut:
        return ""

    # ── Tentative LLM ─────────────────────────────────────────────────────────
    try:
        from config import get_settings as _get_settings
        import openai as _openai

        _settings = _get_settings()
        _client   = _openai.OpenAI(api_key=_settings.openai_api_key)

        sujet     = "de l'enfant" if is_enfant else "de la personne"
        personne  = "l'enfant (à la 3ème personne, ex : « il/elle ne peut pas… »)" \
                    if is_enfant else \
                    "la personne elle-même (à la 1ère personne, ex : « je ne peux pas… »)"

        prompt = (
            f"Tu rédiges la section 'Description de la situation et des difficultés' "
            f"d'un formulaire MDPH pour {sujet}.\n"
            f"Rédige ce texte du point de vue de {personne}.\n"
            f"Règles :\n"
            f"- Phrases simples, courtes, concrètes (pas de jargon médical)\n"
            f"- Ne mentionne jamais : RSDAE, ESAT, PCH, AAH, MDPH, score, algorithme\n"
            f"- Décris les difficultés quotidiennes réelles (ce que la personne ne peut pas faire seule)\n"
            f"- Maximum 400 mots\n"
            f"- Pas de titres, pas de listes à puces\n\n"
            f"Informations disponibles :\n{contexte_brut}"
        )

        resp = _client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.3,
        )
        texte = resp.choices[0].message.content.strip()
        logger.info(f"[CERFA P8] Description générée par LLM ({len(texte)} chars)")
        return texte[:2000]

    except Exception as e:
        logger.warning(f"[CERFA P8] LLM indisponible, fallback texte brut : {e}")
        # Fallback : retourner le contexte brut nettoyé (max 2000 chars)
        return contexte_brut[:2000]

_CERFA_PATH = Path(__file__).parent.parent / "static" / "forms" / "cerfa_15692.pdf"


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers — cochage de cases via annotation directe
# ─────────────────────────────────────────────────────────────────────────────

def _get_on_value(annot) -> str:
    """
    Lit la vraie valeur 'cochée' depuis le dictionnaire AP/N de l'annotation.
    Dans le CERFA 15692, les cases normales utilisent /Oui (pas /Yes).
    Les cases radio utilisent des valeurs custom : /Homme, /Femme, etc.
    Retourne /Yes en fallback si AP est absent.
    """
    try:
        ap = annot.get("/AP")
        if ap:
            ap_obj = ap.get_object()
            n = ap_obj.get("/N")
            if n:
                n_obj = n.get_object()
                for key in n_obj.keys():
                    if str(key) != "/Off":
                        return str(key)
    except Exception:
        pass
    return "/Yes"


def _cocher_case(writer: PdfWriter, field_name: str) -> bool:
    """
    Coche une case à cocher simple (un seul widget par nom de champ).
    Utilise la vraie valeur ON lue depuis AP/N — corrige le bug /Yes vs /Oui.
    Retourne True si le champ a été trouvé et coché.
    """
    for page in writer.pages:
        if "/Annots" not in page:
            continue
        for annot_ref in page["/Annots"]:
            try:
                annot = annot_ref.get_object()
                t_val = annot.get("/T")
                if t_val is not None and str(t_val) == field_name:
                    on_val = _get_on_value(annot)
                    annot.update({
                        NameObject("/V"):  NameObject(on_val),
                        NameObject("/AS"): NameObject(on_val),
                    })
                    logger.debug(f"Case cochée : {field_name} → {on_val}")
                    return True
            except Exception:
                pass
    logger.warning(f"Champ case à cocher non trouvé dans le PDF : {field_name}")
    return False


def _cocher_option(writer: PdfWriter, field_name: str, option_value: str) -> bool:
    """
    Sélectionne une option dans un groupe radio par valeur AP/N (ex. 'Homme', 'Femme').
    Gère /T direct ou via parent. Retourne True si trouvé et coché.
    """
    target = f"/{option_value}"
    for page in writer.pages:
        if "/Annots" not in page:
            continue
        for annot_ref in page["/Annots"]:
            try:
                annot = annot_ref.get_object()
                t_val = annot.get("/T")
                if t_val is None:
                    parent_ref = annot.get("/Parent")
                    if parent_ref:
                        t_val = parent_ref.get_object().get("/T")
                if t_val is not None and str(t_val) == field_name:
                    on_val = _get_on_value(annot)
                    if on_val == target:
                        annot.update({
                            NameObject("/V"):  NameObject(on_val),
                            NameObject("/AS"): NameObject(on_val),
                        })
                        logger.debug(f"Option cochée : {field_name} → {on_val}")
                        return True
            except Exception as e:
                logger.debug(f"_cocher_option exception : {field_name}/{option_value} → {e!r}")
    logger.warning(f"Option non trouvée : {field_name} / {option_value}")
    return False


def _cocher_option_nth(writer: PdfWriter, field_name: str, n: int) -> bool:
    """
    Sélectionne la Nième option (0-indexé, triée par position X croissante) d'un
    groupe radio. Plus robuste que _cocher_option pour les champs dont la valeur
    AP/N contient des caractères spéciaux ou mal encodés (ex. /Française).

    Exemple : _cocher_option_nth(writer, "Case à cocher OPTION P2 2", 0) → Française
              _cocher_option_nth(writer, "Case à cocher OPTION P2 4", 0) → CAF
    """
    candidates = []
    for page in writer.pages:
        if "/Annots" not in page:
            continue
        for annot_ref in page["/Annots"]:
            try:
                annot = annot_ref.get_object()
                t_val = annot.get("/T")
                if t_val is None:
                    parent_ref = annot.get("/Parent")
                    if parent_ref:
                        t_val = parent_ref.get_object().get("/T")
                if t_val is not None and str(t_val) == field_name:
                    rect = annot.get("/Rect")
                    x = float(rect[0]) if rect else 0
                    on_val = _get_on_value(annot)
                    candidates.append((x, annot, on_val))
            except Exception as e:
                logger.debug(f"_cocher_option_nth scan err : {e!r}")

    if not candidates:
        logger.warning(f"Groupe radio non trouvé : {field_name}")
        return False

    candidates.sort(key=lambda c: c[0])   # tri par X croissant = ordre visuel gauche→droite

    if n >= len(candidates):
        logger.warning(f"Option {n} hors limites pour {field_name} ({len(candidates)} options)")
        return False

    x, annot, on_val = candidates[n]
    annot.update({
        NameObject("/V"):  NameObject(on_val),
        NameObject("/AS"): NameObject(on_val),
    })
    logger.debug(f"Option #{n} cochée : {field_name} → {on_val} (x={x:.0f})")
    return True


# ─────────────────────────────────────────────────────────────────────────────
#  Point d'entrée public
# ─────────────────────────────────────────────────────────────────────────────

def remplir_cerfa(dossier: dict[str, Any]) -> bytes:
    """
    Pré-remplit le CERFA 15692*01 avec toutes les données disponibles du dossier.
    Compatible enfant ET adulte.
    """
    if not _CERFA_PATH.exists():
        raise FileNotFoundError(f"Formulaire CERFA introuvable : {_CERFA_PATH}")

    reader = PdfReader(str(_CERFA_PATH))
    writer = PdfWriter()
    writer.append(reader)

    champs: dict[str, str] = {}   # champs texte → update_page_form_field_values
    cases:  list[str]      = []   # cases à cocher → _cocher_case (annotation directe)

    # ── Données personnelles ─────────────────────────────────────────────────
    # Les colonnes DB utilisent "enfant" comme nom générique — valide pour adultes aussi
    nom       = (dossier.get("nom_enfant")     or "").upper()
    prenom    = dossier.get("prenom_enfant")   or ""
    ddn       = dossier.get("ddn_enfant")      or ""
    adresse   = dossier.get("adresse_enfant")  or ""
    cp        = dossier.get("cp_enfant")       or ""
    commune   = (dossier.get("commune_enfant") or "").upper()
    telephone = dossier.get("telephone_famille") or ""
    email     = dossier.get("email_famille")   or ""
    dept      = dossier.get("departement_code") or ""

    ddn_jour = ddn_mois = ddn_annee = ""
    if ddn and "/" in ddn:
        parts = ddn.split("/")
        if len(parts) == 3:
            ddn_jour, ddn_mois, ddn_annee = parts[0], parts[1], parts[2]

    # ── Données de l'analyse IA ──────────────────────────────────────────────
    analyse            = dossier.get("analyse") or {}
    syntheses          = analyse.get("synthese_agents") or {}
    geva_pro           = syntheses.get("geva_pro") or ""
    juriste            = syntheses.get("juriste") or ""
    droits             = analyse.get("droits_identifies") or []
    elements_probants  = analyse.get("elements_probants") or []

    # Données structurées extraites par l'IA
    ds = analyse.get("donnees_structurees") or {}
    is_enfant              = ds.get("is_enfant", True)
    genre                  = (ds.get("genre") or "").lower()
    situation_familiale    = (ds.get("situation_familiale") or "").lower()
    vie_seule              = ds.get("vie_seule", False)
    a_enfants_charge       = ds.get("a_enfants_charge", False)
    situation_pro          = (ds.get("situation_professionnelle") or "").lower()
    nom_employeur          = ds.get("nom_employeur") or ""
    poste_occupe           = ds.get("poste_occupe") or ""
    projet_professionnel   = ds.get("projet_professionnel") or ""
    aides_actuelles        = ds.get("aides_actuelles") or []
    besoins_aide_humaine   = ds.get("besoins_aide_humaine", False)
    besoins_aide_technique = ds.get("besoins_aide_technique", False)
    besoins_amenagement    = ds.get("besoins_amenagement_logement", False)
    type_logement          = (ds.get("type_logement") or "").lower()
    statut_logement        = (ds.get("statut_logement") or "").lower()
    nss                    = (ds.get("nss") or "").replace(" ", "").replace(".", "")
    # Nouveaux champs
    type_demande           = (ds.get("type_demande") or "premiere").lower()
    deja_connu_mdph        = ds.get("deja_connu_mdph", False)
    numero_dossier_mdph    = ds.get("numero_dossier_mdph") or ""
    nationalite            = (ds.get("nationalite") or "francaise").lower()
    commune_naissance      = ds.get("commune_naissance") or ""
    departement_naissance  = ds.get("departement_naissance") or ""
    pays_naissance         = (ds.get("pays_naissance") or "France").strip()
    nom_usage              = ds.get("nom_usage") or ""
    organisme_payeur       = (ds.get("organisme_payeur") or "").lower()
    numero_allocataire     = ds.get("numero_allocataire") or ""
    organisme_assurance    = (ds.get("organisme_assurance_maladie") or "cpam").lower()
    protection_juridique   = (ds.get("protection_juridique") or "aucune").lower()

    # ── Scolarité (P9-P12) ───────────────────────────────────────────────────
    scolarise              = ds.get("scolarise", is_enfant)
    nom_ecole              = ds.get("nom_ecole") or ""
    classe_scolaire        = ds.get("classe_scolaire") or ""
    type_etablissement     = (ds.get("type_etablissement_scolaire") or "").lower()
    a_pps                  = ds.get("a_pps", False)       # Plan Personnalisé de Scolarisation
    a_pai                  = ds.get("a_pai", False)       # Protocole d'Accueil Individualisé
    a_ulis                 = ds.get("a_ulis", False)      # Unité Locale Inclusion Scolaire
    classe_ordinaire       = ds.get("classe_ordinaire", True)

    # ── Situation professionnelle détaillée (P13-P16) ────────────────────────
    date_debut_emploi      = ds.get("date_debut_emploi") or ""
    type_contrat           = (ds.get("type_contrat") or "").lower()
    duree_hebdo            = ds.get("duree_hebdomadaire") or ""
    en_recherche_emploi    = ds.get("en_recherche_emploi", False)
    inscrit_pole_emploi    = ds.get("inscrit_pole_emploi", False)
    date_inscription_pe    = ds.get("date_inscription_pole_emploi") or ""
    en_formation           = ds.get("en_formation", False)
    nom_formation          = ds.get("nom_formation") or ""
    organisme_formation    = ds.get("organisme_formation") or ""

    # ── Logement / vie quotidienne (P5-P7) ───────────────────────────────────
    type_logement_detail   = (ds.get("type_logement") or "").lower()
    vie_en_couple          = ds.get("vie_en_couple", False)
    vie_en_famille         = ds.get("vie_en_famille", is_enfant)
    logement_adapte        = ds.get("logement_adapte")    # True / False / None
    statut_occupation      = (ds.get("statut_occupation") or "").lower()

    # ── Aides humaines (P6) ──────────────────────────────────────────────────
    a_aide_soignante       = ds.get("a_aide_soignante", False)
    a_auxiliaire_vie       = ds.get("a_auxiliaire_vie", False)
    a_aide_menagere        = ds.get("a_aide_menagere", False)

    # ── Aidant familial (P20) ────────────────────────────────────────────────
    nom_aidant             = ds.get("nom_aidant") or ""
    prenom_aidant          = ds.get("prenom_aidant") or ""
    lien_aidant            = ds.get("lien_aidant") or ""

    # Tranche d'âge — détermine les sections applicables du formulaire
    # Enfant (<18) : scolarité P9, pas de section pro
    # Jeune majeur (18-25) : section pro ET possibilité scolarité/formation
    # Adulte (>25) : section pro uniquement
    age_tranche = "enfant"
    if not is_enfant:
        age_tranche = "adulte"
        try:
            if ddn and "/" in ddn:
                j, m, a = ddn.split("/")
                naissance = date(int(a), int(m), int(j))
                age = (date.today() - naissance).days // 365
                age_tranche = "jeune_majeur" if 18 <= age <= 25 else "adulte"
        except Exception:
            pass

    # ── Description P8 (narrative humanisée) ────────────────────────────────
    description_situation = _composer_description_p8(
        geva_pro=geva_pro,
        juriste=juriste,
        elements_probants=elements_probants,
        is_enfant=is_enfant,
    )

    # ── Droits → liste de cases P17/P18/P19 ─────────────────────────────────
    cases_droits = _mapper_droits(
        droits,
        is_enfant=is_enfant,
        besoins_aide_humaine=besoins_aide_humaine,
    )

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 1 — Département et type de demande
    # ════════════════════════════════════════════════════════════════════════
    champs["Champ de texte P1 1"] = dept

    # Nature de la demande — mapping exact confirmé par inspection des positions Y :
    #   P1 A (y=557) = "C'est ma première demande à la MDPH"
    #   P1 B (y=582) = "Ma situation médicale/administrative/familiale a changé"
    #   P1 C (y=612) = "Je souhaite une réévaluation / révision de mes droits"
    #   P1 1 (y=663) = "Je souhaite le renouvellement de mes droits à l'identique"
    #   P1 2 (y=713) = "Votre aidant familial souhaite exprimer sa situation"
    #   P1 3 (y=798) = "Vous avez déjà un dossier à la MDPH ? OUI"
    if type_demande in ("premiere", "première", "1ere", "1ère"):
        cases.append("Case à cocher P1 A")
    elif type_demande in ("situation_changee", "situation_changée", "changement"):
        cases.append("Case à cocher P1 B")
    elif type_demande in ("reevaluation", "réévaluation", "revision", "révision"):
        cases.append("Case à cocher P1 C")
    elif type_demande == "renouvellement":
        cases.append("Case à cocher P1 1")
    else:
        cases.append("Case à cocher P1 A")   # défaut : première demande

    # Déjà connu de la MDPH (dossier existant)
    if deja_connu_mdph or type_demande in ("renouvellement", "reevaluation", "réévaluation",
                                            "revision", "révision", "situation_changee",
                                            "situation_changée", "changement"):
        cases.append("Case à cocher P1 3")
        if numero_dossier_mdph:
            champs["Champ de texte P 1 2"] = numero_dossier_mdph

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 2 — Identité complète de la personne
    # Mapping champs confirmé par inspection des positions X/Y du PDF :
    #   P2 1  = Nom de naissance
    #   P2 2  = Nom d'époux/se ou d'usage (vide si identique au nom de naissance)
    #   P2 3  = Prénoms (TOUS les prénoms)
    #   P2 4  = Commune de naissance
    #   P2 6  = Département de naissance
    #   P2 7  = Complément d'adresse (bâtiment, appartement…)
    #   P2 8  = Adresse principale (numéro et rue) ← corrigé (était P2 7)
    #   P 2 9 = Code postal
    #   P2 10 = Commune
    #   P2 11 = Pays
    #   P2 12 = Téléphone
    #   P2 13 = Email de contact
    #   P2 14 = N° d'allocataire (CAF / MSA)
    #   Champ de texte P2 Pays naisssance autre = Pays si ≠ France
    # ════════════════════════════════════════════════════════════════════════
    champs["Champ de texte P2 1"]  = nom          # Nom de naissance
    if nom_usage:
        champs["Champ de texte P2 2"] = nom_usage  # Nom d'usage uniquement si différent
    champs["Champ de texte P2 3"]  = prenom        # Prénoms ← corrigé (était P2 2)
    # Date de naissance
    champs["Date A 1"] = ddn_jour
    champs["Date A 2"] = ddn_mois
    champs["Date A 3"] = ddn_annee
    # Lieu de naissance
    if commune_naissance:
        champs["Champ de texte P2 4"] = commune_naissance
    if departement_naissance:
        champs["Champ de texte P2 6"] = departement_naissance
    if pays_naissance and pays_naissance.lower() != "france":
        champs["Champ de texte P2 Pays naisssance autre"] = pays_naissance
    # Adresse — P2 8 = numéro et rue, P2 7 = complément (bât., appt…)
    champs["Champ de texte P2 8"]  = adresse       # ← corrigé (était P2 7)
    champs["Champ de texte P 2 9"] = cp
    champs["Champ de texte P2 10"] = commune
    champs["Champ de texte P2 11"] = "France"
    champs["Champ de texte P2 12"] = telephone
    champs["Champ de texte P2 13"] = email         # Email contact famille/personne
    # Organisme payeur — N° d'allocataire
    if numero_allocataire:
        champs["Champ de texte P2 14"] = numero_allocataire

    # Numéro de sécurité sociale — 1 case par chiffre (15 chiffres)
    # Adulte : Numero SS 3 → Numero SS 17
    # Enfant : N° SS Enfant 1 → N° SS Enfant 15
    nss_clean = nss.replace(" ", "").replace(".", "").replace("-", "")
    if nss_clean and nss_clean.isdigit():
        if is_enfant:
            for i, digit in enumerate(nss_clean[:15], start=1):
                champs[f"N° SS Enfant {i}"] = digit
        else:
            for i, digit in enumerate(nss_clean[:15]):
                champs[f"Numero SS {i + 3}"] = digit

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 3 — Représentant légal / Protection juridique
    # ════════════════════════════════════════════════════════════════════════
    if is_enfant:
        # Représentant légal = parent (les données famille servent de représentant)
        champs["REPRESENTANT LEGAL 1"]  = nom
        champs["REPRESENTANT LEGAL 2"]  = prenom
        champs["REPRESENTANT LEGAL 3"]  = "Père / Mère"
        champs["REPRESENTANT LEGAL 6"]  = adresse
        champs["REPRESENTANT LEGAL 7"]  = cp
        champs["REPRESENTANT LEGAL 8"]  = commune
        champs["REPRESENTANT LEGAL 9"]  = telephone
        champs["REPRESENTANT LEGAL 10"] = email
        cases.append("Case à cocher P3 1")   # Titulaire autorité parentale
        # Cases P3 4-6 : mesure de protection
        if "tutelle" in protection_juridique:
            cases.append("Case à cocher P3 4")
        elif "curatelle" in protection_juridique:
            cases.append("Case à cocher P3 5")
        elif "sauvegarde" in protection_juridique:
            cases.append("Case à cocher P3 6")
    else:
        # Adulte : agit seul ou sous mesure de protection
        if protection_juridique in ("aucune", "", "none", "non"):
            cases.append("Case à cocher P3 2")    # Agit seul(e)
        else:
            cases.append("Case à cocher P 3 3")   # Représentant désigné
            if "tutelle" in protection_juridique:
                cases.append("Case à cocher P3 4")
            elif "curatelle" in protection_juridique:
                cases.append("Case à cocher P3 5")
            elif "sauvegarde" in protection_juridique:
                cases.append("Case à cocher P3 6")

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 4 — Situation personnelle, familiale et signature
    # ════════════════════════════════════════════════════════════════════════
    sit_fam_case = None
    sf = situation_familiale
    if "celibataire" in sf or "célibataire" in sf or (vie_seule and not sf):
        sit_fam_case = "Case à cocher P4 0"
    elif "marie" in sf or "marié" in sf:
        sit_fam_case = "Case à cocher P4 1"
    elif "pacse" in sf or "pacsé" in sf:
        sit_fam_case = "Case à cocher P4 2"
    elif "concubinage" in sf:
        sit_fam_case = "Case à cocher P4 3"
    elif "divorce" in sf or "séparé" in sf or "separe" in sf:
        sit_fam_case = "Case à cocher P4 4"
    elif "veuf" in sf or "veuve" in sf:
        sit_fam_case = "Case à cocher P4 5"
    if sit_fam_case:
        cases.append(sit_fam_case)
    if a_enfants_charge:
        cases.append("Case à cocher P4 1")    # Enfants à charge : case P4 1 (y=321)

    # Date de signature = aujourd'hui
    today = date.today()
    champs["Date P4 1 "] = f"{today.day:02d}"
    champs["Date P4 2"]  = f"{today.month:02d}"
    champs["Date P4 3"]  = str(today.year)

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 5 — Lieu de vie / Logement
    # ════════════════════════════════════════════════════════════════════════
    # Champ de texte P5 1 = intitulé lieu de vie (établissement ou adresse)
    champs["Champ de texte P5 1"] = adresse

    # Type de logement (P5 1-4 y=114) :
    #   x=128 = établissement médico-social
    #   x=203 = maison individuelle
    #   x=298 = appartement/collectif
    #   x=427 = foyer/résidence
    tl = type_logement_detail
    if any(x in tl for x in ["établissement", "institution", "medico", "ehpad", "esat", "foyer d'hébergement"]):
        cases.append("Case à cocher P5 1")
    elif any(x in tl for x in ["maison", "pavillon", "individuel"]):
        cases.append("Case à cocher P5 2")
    elif any(x in tl for x in ["appartement", "appart", "hlm", "immeuble"]):
        cases.append("Case à cocher P5 3")
    elif any(x in tl for x in ["foyer", "résidence", "residence"]):
        cases.append("Case à cocher P5 4")
    elif is_enfant:
        cases.append("Case à cocher P5 2")   # Défaut enfant : maison

    # Avec qui vivez-vous (P5 5-7 y=141-219 x=51) :
    #   P5 5 = seul(e) | P5 6 = famille/couple | P5 7 = colocation/autre
    if vie_seule:
        cases.append("Case à cocher P5 5")
    elif vie_en_couple or any(x in sf for x in ["marié", "marie", "pacsé", "pacse", "concubinage"]):
        cases.append("Case à cocher P5 6")
    elif vie_en_famille or is_enfant:
        cases.append("Case à cocher P5 6")
    else:
        cases.append("Case à cocher P5 7")   # Autre

    # Statut d'occupation (P5 8-10 y=191-219 x=298-429) :
    #   P5 8 = propriétaire | P5 9 = locataire | P5 10 = hébergé à titre gratuit
    so = statut_occupation
    if any(x in so for x in ["proprio", "propriétaire"]):
        cases.append("Case à cocher P5 8")
    elif any(x in so for x in ["locataire", "location"]):
        cases.append("Case à cocher P5 9")
    elif any(x in so for x in ["hébergé", "heberge", "gratuit"]):
        cases.append("Case à cocher P5 10")

    # Besoins d'aide technique (P5 22-26 y=499-542) — aides techniques identifiées
    if besoins_aide_technique:
        cases.append("Case à cocher P5 22")  # Aide technique nécessaire

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 6 — Aides humaines et soins
    # ════════════════════════════════════════════════════════════════════════
    aides_str = " ".join(aides_actuelles).lower() if aides_actuelles else ""

    # Soins médicaux en cours (P6 1 y=109)
    if aides_actuelles or a_aide_soignante:
        cases.append("Case à cocher P6 1")
        # Type de soins : libéral (P6 2), hospitalier (P6 3), autre (P6 4)
        has_lib  = any(x in aides_str for x in ["libéral", "liberal", "médecin", "infirmier lib", "kiné"])
        has_hosp = any(x in aides_str for x in ["hôpital", "hopital", "clinique", "hospitalier"])
        if has_lib:
            cases.append("Case à cocher P6 2")
        if has_hosp:
            cases.append("Case à cocher P6 3")
        if not has_lib and not has_hosp:
            cases.append("Case à cocher P6 4")

    # Aide humaine (P6 7 y=183)
    if besoins_aide_humaine or a_auxiliaire_vie or a_aide_menagere:
        cases.append("Case à cocher P6 7")
        if a_auxiliaire_vie or any(x in aides_str for x in ["auxiliaire", "avs", "aide humaine"]):
            cases.append("Case à cocher P6 9")   # Professionnel
        cases.append("Case à cocher P6 8")        # Famille/entourage (souvent les deux)

    # Tableau P6 — professionnels intervenants (5 colonnes × 3 lignes)
    if aides_actuelles:
        for i, aide in enumerate(aides_actuelles[:3], start=1):
            row_start = (i - 1) * 5 + 1
            champs[f"Tableau P6 {row_start}"] = aide[:25]

    # Besoins détaillés P6 B1-B10
    if besoins_aide_humaine or a_auxiliaire_vie:
        if any(x in aides_str for x in ["hygiène", "toilette", "bain", "douche", "lavage"]):
            cases.append("Case à cocher P6 B1")
        if any(x in aides_str for x in ["habillage", "vêtement", "vêtir", "s'habill"]):
            cases.append("Case à cocher P6 B2")
        if any(x in aides_str for x in ["repas", "alimentation", "manger", "nutrition", "préparer"]):
            cases.append("Case à cocher P6 B3")
        if any(x in aides_str for x in ["mobilité", "déplacement", "marche", "fauteuil", "déplacer"]):
            cases.append("Case à cocher P6 B4")
        if any(x in aides_str for x in ["extérieur", "sortie", "courses", "promenade"]):
            cases.append("Case à cocher P6 B5")
        if any(x in aides_str for x in ["communication", "langage", "parole", "comprendre"]):
            cases.append("Case à cocher P6 B6")

    # Champ libre P6 7 = précisions
    if besoins_aide_humaine and aides_actuelles:
        champs["Champ de texte P6 7"] = "; ".join(aides_actuelles)[:200]

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 7 — Vie quotidienne : mobilité, transports, communication
    # ════════════════════════════════════════════════════════════════════════
    # Mobilité dans le logement :
    #   356 (y=126 x=52) = se déplace seul
    #   P7 2 (y=146 x=52) = aide pour déplacement intérieur
    #   P7 3 (y=166 x=52) = ne se déplace pas
    if besoins_aide_humaine or any(x in aides_str for x in ["fauteuil roulant", "déambulateur", "canne"]):
        cases.append("Case à cocher P7 2")
    else:
        cases.append("Case à cocher 356")

    # Mobilité hors logement :
    #   P7 4 (y=126 x=316) = seul | P7 5 (y=146 x=316) = avec aide | P7 6 (y=166 x=316) = pas de sortie
    if any(x in aides_str for x in ["extérieur", "sortie", "handicap moteur", "fauteuil", "béquille", "aide pour sortir"]):
        cases.append("Case à cocher P7 5")
    else:
        cases.append("Case à cocher P7 4")

    # Transports :
    #   P7 8 (y=305 x=52) = transports commun | P7 9 (y=331) = voiture | P7 14 (y=384) = autre/VSL
    if any(x in aides_str for x in ["voiture personnelle", "véhicule adapté", "permis"]):
        cases.append("Case à cocher P7 9")
    elif any(x in aides_str for x in ["vsl", "ambulance", "taxi médical", "transport adapté"]):
        cases.append("Case à cocher P7 14")
    elif not besoins_aide_humaine:
        cases.append("Case à cocher P7 8")   # Transports en commun

    # Communication (P7 15-18 y=498-589) :
    #   P7 15 (y=498) = communique bien | P7 16 (y=524) = difficultés légères
    #   P7 17 (y=553) = nécessite aide | P7 18 (y=589) = communication très limitée
    if any(x in aides_str for x in ["autisme", "non verbal", "communication augmentative", "cécité", "surdité profonde"]):
        cases.append("Case à cocher P7 18")
    elif any(x in aides_str for x in ["communication", "langage", "parole", "expression"]):
        cases.append("Case à cocher P7 16")
    else:
        cases.append("Case à cocher P7 15")

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 8 — Description de la situation et des difficultés
    # ════════════════════════════════════════════════════════════════════════
    if description_situation:
        champs["Champ de texte P8 1"] = description_situation[:2000]

    # ════════════════════════════════════════════════════════════════════════
    # PAGES 9-12 — Scolarité (enfants < 18 et jeunes majeurs en formation initiale)
    # ════════════════════════════════════════════════════════════════════════
    if age_tranche in ("enfant", "jeune_majeur") and scolarise:
        # Type d'établissement (P 9 1-7 y=154-327 x=50) :
        #   1=petite enfance | 2=maternelle | 3=primaire | 4=collège
        #   5=lycée général | 6=lycée pro/CAP | 7=supérieur
        type_etab = type_etablissement
        if any(x in type_etab for x in ["crèche", "halte", "petite enfance"]):
            cases.append("Case à cocher P 9 1")
        elif any(x in type_etab for x in ["maternelle", "ps", "ms", "gs", "tps"]):
            cases.append("Case à cocher P 9 2")
        elif any(x in type_etab for x in ["primaire", "élémentaire", "cp", "ce1", "ce2", "cm1", "cm2"]):
            cases.append("Case à cocher P 9 3")
        elif any(x in type_etab for x in ["collège", "college", "6ème", "5ème", "4ème", "3ème"]):
            cases.append("Case à cocher P 9 4")
        elif any(x in type_etab for x in ["lycée professionnel", "lycee pro", "cap", "bep"]):
            cases.append("Case à cocher P 9 6")
        elif any(x in type_etab for x in ["lycée", "lycee", "seconde", "première", "terminale", "bac"]):
            cases.append("Case à cocher P 9 5")
        elif any(x in type_etab for x in ["université", "bts", "iut", "btsa", "cpge", "supérieur"]):
            cases.append("Case à cocher P 9 7")
        else:
            cases.append("Case à cocher P 9 3")   # Défaut enfant : primaire

        if nom_ecole:
            champs["Champ de texte P9 1"] = nom_ecole
        if classe_scolaire:
            champs["Champ de texte P9 2"] = classe_scolaire

        # PPS, ULIS, PAI
        if a_pps:
            cases.append("Case à cocher P 9 8")
        if a_ulis:
            cases.append("Case à cocher P 9 9")
        if a_pai:
            cases.append("Case à cocher P 9 10")

        # PAGE 10 (scolarité) — accompagnements scolaires
        if aides_actuelles:
            aides_texte = "\n".join(f"- {a}" for a in aides_actuelles)
            champs["Champ de texte P10 1"] = aides_texte[:500]
        if a_ulis or a_pps:
            cases.append("Case à cocher P10 2")   # Accompagnement humain (AESH)
        if any(x in aides_str for x in ["sessad", "camsp"]):
            cases.append("Case à cocher P10 3")

        # PAGE 12 — PAP / PPS existants
        if classe_scolaire:
            champs["Champ de texte P12 1"] = f"Classe : {classe_scolaire}"
        if a_pps:
            cases.append("Case à cocher P12 5")
        if a_pai:
            cases.append("Case à cocher P12 6")

    elif not is_enfant and aides_actuelles:
        # PAGE 10 adulte — accompagnements et soins actuels
        aides_texte = "\n".join(f"- {a}" for a in aides_actuelles)
        champs["Champ de texte P10 1"] = aides_texte[:500]
        # Cases P10 4-12 = types d'accompagnement
        if any(x in aides_str for x in ["infirmier", "soin infirmier"]):
            cases.append("Case à cocher P10 4")
        if any(x in aides_str for x in ["kiné", "kinésithérapie"]):
            cases.append("Case à cocher P10 5")
        if any(x in aides_str for x in ["psychologue", "psy", "psychiatre"]):
            cases.append("Case à cocher P10 6")
        if any(x in aides_str for x in ["orthophoniste", "orthophonie"]):
            cases.append("Case à cocher P10 7")
        if any(x in aides_str for x in ["ergothérapeute", "ergo"]):
            cases.append("Case à cocher P 10 8")
        if any(x in aides_str for x in ["auxiliaire de vie", "aide humaine", "avs"]):
            cases.append("Case à cocher P10 9")
        if any(x in aides_str for x in ["aide ménagère", "ménagère"]):
            cases.append("Case à cocher P10 10")
        if any(x in aides_str for x in ["sessad", "savs", "samsah", "camsp"]):
            cases.append("Case à cocher P10 11")
        if any(x in aides_str for x in ["hospitalisation", "hôpital", "clinique"]):
            cases.append("Case à cocher P10 12")

    # ════════════════════════════════════════════════════════════════════════
    # PAGES 13-16 — Situation professionnelle (adultes et jeunes majeurs)
    # ════════════════════════════════════════════════════════════════════════
    if age_tranche in ("adulte", "jeune_majeur"):
        sp = situation_pro
        has_emploi = any(x in sp for x in ["emploi", "travail", "esat", "ea", "cdd", "cdi", "temps"])

        # PAGE 13 — Situation actuelle
        if has_emploi:
            cases.append("Case à cocher P 13 1")    # A une activité professionnelle

        # Type d'emploi
        if "esat" in sp:
            cases.append("Case à cocher P 13 3")
        elif "entreprise adaptée" in sp or " ea " in sp or "ea " in sp:
            cases.append("Case à cocher P 13 4")
        elif any(x in sp for x in ["emploi ordinaire", "milieu ordinaire", "cdi", "cdd"]):
            cases.append("Case à cocher P 13 2")

        # Employeur / poste
        if nom_employeur:
            champs["Champ de texte P13 1"] = nom_employeur
        if poste_occupe:
            champs["Champ de texte P13 2"] = poste_occupe
        if type_contrat:
            champs["Champ de texte P13 3"] = type_contrat.upper()
        if duree_hebdo:
            champs["Champ de texte P13 7"] = duree_hebdo

        # Sans emploi / recherche
        if en_recherche_emploi or any(x in sp for x in ["sans emploi", "recherche", "chômage", "chomage"]):
            cases.append("Case à cocher P 13 9")
            if inscrit_pole_emploi:
                cases.append("Case à cocher P 13 7")
                if date_inscription_pe:
                    parts = date_inscription_pe.split("/")
                    if len(parts) == 3:
                        champs["DATE P13 1"] = parts[0]
                        champs["DATE P13 2"] = parts[1]
                        champs["DATE P13 3"] = parts[2]

        if any(x in sp for x in ["jamais travaillé", "jamais travaille"]):
            cases.append("Case à cocher P 13 11")
        if any(x in sp for x in ["arrêt", "arret maladie"]):
            cases.append("Case à cocher P 13 12")
        if any(x in sp for x in ["retraite", "retraité"]):
            cases.append("Case à cocher P 13 8")

        # Date début emploi
        if date_debut_emploi:
            parts = date_debut_emploi.split("/")
            if len(parts) == 3:
                champs["DATE P13 4"] = parts[0]
                champs["DATE P13 5"] = parts[1]
                champs["DATE P13 6"] = parts[2]

        # PAGE 14 — Formation professionnelle
        if en_formation or nom_formation:
            cases.append("Case \u00e0 cocher P14 1")
            if nom_formation:
                champs["Champ de texte P14 1"] = nom_formation
            if organisme_formation:
                champs["Champ de texte P14 2"] = organisme_formation

        # PAGE 16 — Projet(s) professionnel(s)
        if projet_professionnel:
            champs["Champ de texte P16 1"] = projet_professionnel[:500]
            cases.append("Case \u00e0 cocher P16 1")     # Oui, j'ai un projet
        else:
            cases.append("Case \u00e0 cocher P16 2")     # Non / en r\u00e9flexion

    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    # PAGE 20 \u2014 Aidant familial et orientations P18 suite
    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    if nom_aidant:
        champs["Champ de texte P20 1"] = nom_aidant
    if prenom_aidant:
        champs["Champ de texte P20 2"] = prenom_aidant
    if lien_aidant:
        champs["Champ de texte P20 3"] = lien_aidant

    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    # BAS DE PAGE \u2014 Nom / pr\u00e9nom r\u00e9p\u00e9t\u00e9s sur toutes les pages
    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    champs["NOM BAS DE PAGE"]    = nom
    champs["PRENOM BAS DE PAGE"] = prenom

    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    # PAGES 17 / 18 / 19 \u2014 Demandes (allocations, orientations, cartes)
    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    cases.extend(cases_droits)

    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    # RADIO BUTTONS \u2014 tous coch\u00e9s AVANT update_page_form_field_values
    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    # Genre (OPTION P2 1) \u2014 x=165 : Homme | x=252 : Femme
    genre_ok = False
    if genre in ("homme", "masculin", "m", "male"):
        genre_ok = _cocher_option_nth(writer, "Case \u00e0 cocher OPTION P2 1", 0)
    elif genre in ("femme", "f\u00e9minin", "f", "female"):
        genre_ok = _cocher_option_nth(writer, "Case \u00e0 cocher OPTION P2 1", 1)
    if not genre_ok and genre:
        logger.warning(f"Genre non coch\u00e9 : {genre!r}")

    # Nationalit\u00e9 (OPTION P2 2) \u2014 0:Fran\u00e7aise | 1:EEE Suisse | 2:Autre
    if "eee" in nationalite or "suisse" in nationalite or "europ\u00e9en" in nationalite:
        _cocher_option_nth(writer, "Case \u00e0 cocher OPTION P2 2", 1)
    elif "autre" in nationalite or (nationalite and "fran" not in nationalite):
        _cocher_option_nth(writer, "Case \u00e0 cocher OPTION P2 2", 2)
    else:
        _cocher_option_nth(writer, "Case \u00e0 cocher OPTION P2 2", 0)

    # Pays de naissance (OPTION P2 3) \u2014 0:France | 1:Autre
    if pays_naissance and pays_naissance.lower() != "france":
        _cocher_option_nth(writer, "Case \u00e0 cocher OPTION P2 3", 1)
    else:
        _cocher_option_nth(writer, "Case \u00e0 cocher OPTION P2 3", 0)

    # Organisme payeur (OPTION P2 4) \u2014 0:CAF | 1:MSA | 2:Autre
    if "msa" in organisme_payeur:
        _cocher_option_nth(writer, "Case \u00e0 cocher OPTION P2 4", 1)
    elif "caf" in organisme_payeur or not organisme_payeur:
        _cocher_option_nth(writer, "Case \u00e0 cocher OPTION P2 4", 0)
    else:
        _cocher_option_nth(writer, "Case \u00e0 cocher OPTION P2 4", 2)

    # Assurance maladie (OPTION P2 5) \u2014 0:CPAM | 1:MSA | 2:RSI | 3:Autre
    if "msa" in organisme_assurance:
        _cocher_option_nth(writer, "Case \u00e0 cocher OPTION P2 5", 1)
    elif "rsi" in organisme_assurance:
        _cocher_option_nth(writer, "Case \u00e0 cocher OPTION P2 5", 2)
    elif "autre" in organisme_assurance:
        _cocher_option_nth(writer, "Case \u00e0 cocher OPTION P2 5", 3)
    else:
        _cocher_option_nth(writer, "Case \u00e0 cocher OPTION P2 5", 0)

    # Classe ordinaire (OPTION P9 1) \u2014 0:Oui | 1:Non (si scolarit\u00e9 applicable)
    if age_tranche in ("enfant", "jeune_majeur") and scolarise:
        if classe_ordinaire:
            _cocher_option_nth(writer, "Case \u00e0 cocher OPTION P9 1", 0)
        else:
            _cocher_option_nth(writer, "Case \u00e0 cocher OPTION P9 1", 1)

    # Logement adapt\u00e9 (OPTION P5 1) \u2014 0:Non | 1:Oui (ordre x croissant)
    if logement_adapte is True:
        _cocher_option_nth(writer, "Case \u00e0 cocher OPTION P5 1", 1)
    elif logement_adapte is False:
        _cocher_option_nth(writer, "Case \u00e0 cocher OPTION P5 1", 0)

    # Emploi temps partiel (OPTION P13 6) \u2014 0:Temps plein | 1:Temps partiel
    if age_tranche in ("adulte", "jeune_majeur"):
        sp = situation_pro
        if "temps partiel" in sp or "mi-temps" in sp:
            _cocher_option_nth(writer, "Case \u00e0 cocher OPTION P13 6", 1)
        elif "temps plein" in sp or any(x in sp for x in ["emploi", "cdi", "cdd"]):
            _cocher_option_nth(writer, "Case \u00e0 cocher OPTION P13 6", 0)

        # Contrat en cours (OPTION P13 2) \u2014 0:Oui | 1:Non
        has_emploi_radio = any(x in sp for x in ["emploi", "travail", "esat", "cdi", "cdd"])
        _cocher_option_nth(writer, "Case \u00e0 cocher OPTION P13 2", 0 if has_emploi_radio else 1)

        # En arr\u00eat (OPTION P13 3) \u2014 0:Oui | 1:Non
        en_arret = any(x in sp for x in ["arr\u00eat", "arret"])
        _cocher_option_nth(writer, "Case \u00e0 cocher OPTION P13 3", 0 if en_arret else 1)

        # Formation en cours (OPTION P14 1) \u2014 0:Oui | 1:Non
        _cocher_option_nth(writer, "Case \u00e0 cocher OPTION P14 1", 0 if (en_formation or nom_formation) else 1)

        # Projet pro (OPTION P16 1) \u2014 0:Oui | 1:Non
        _cocher_option_nth(writer, "Case \u00e0 cocher OPTION P16 1", 0 if projet_professionnel else 1)

    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    # Remplissage des champs texte (toujours apr\u00e8s les radio buttons)
    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    # \u2500\u2500 Remplissage des champs texte \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    # Chaque page dans un try/except ind\u00e9pendant pour ne pas bloquer
    # si un champ n'existe pas dans cette version du formulaire.
    champs_remplis = 0
    champs_vides   = {k: v for k, v in champs.items() if v}  # ignore les valeurs vides
    for page_idx, page in enumerate(writer.pages):
        try:
            writer.update_page_form_field_values(page, champs_vides)
            champs_remplis += 1
        except Exception as e:
            logger.warning(f"[CERFA] update_page_form_field_values page {page_idx} : {e}")

    # \u2500\u2500 Cochage des cases simples via annotation directe \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    coches_ok = 0
    for field_name in cases:
        try:
            if _cocher_case(writer, field_name):
                coches_ok += 1
        except Exception as e:
            logger.debug(f"[CERFA] Cochage case '{field_name}' : {e}")

    # NeedAppearances \u2014 force les viewers \u00e0 recalculer l'aspect visuel
    try:
        acroform = writer._root_object["/AcroForm"].get_object()
        acroform.update({NameObject("/NeedAppearances"): BooleanObject(True)})
    except Exception as e:
        logger.debug(f"NeedAppearances non d\u00e9fini : {e}")

    logger.info(
        f"CERFA pr\u00e9-rempli | dossier={dossier.get('dossier_id', '?')} "
        f"| {nom} {prenom} | age_tranche={age_tranche} | genre={genre} "
        f"| pages={champs_remplis} | {coches_ok}/{len(cases)} cases coch\u00e9es "
        f"| genre_ok={genre_ok} | droits={droits}"
    )

    buffer = io.BytesIO()
    try:
        writer.write(buffer)
    except Exception as write_err:
        logger.error(f"[CERFA] \u00c9chec writer.write() : {write_err}", exc_info=True)
        raise  # Re-lever pour que l'appelant sache que le CERFA a \u00e9chou\u00e9

    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
