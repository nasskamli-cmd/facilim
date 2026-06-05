"""
app/engines/pdf/field_mapper.py

Mapping complet données (synthese_json) → champs PDF CERFA 15692*01.
580 champs sur 20 pages. Chaque section est documentée.

Règle : toute donnée présente dans synthese_json DOIT être reportée dans le PDF.
"""

from __future__ import annotations
import re
from typing import Any


# ── Helpers ──────────────────────────────────────────────────────────────────

def _nir_to_fields(nir: str, prefix: str) -> dict[str, str]:
    cleaned = "".join(c for c in (nir or "") if c.isdigit())[:15].ljust(15)
    return {f"{prefix} {i+1}": cleaned[i] for i in range(15)}


def _date_to_fields(date_str: str, prefix: str) -> dict[str, str]:
    parts = (date_str or "").replace("-", "/").split("/")
    j, m, a = ("", "", "")
    if len(parts) == 3:
        j, m, a = parts[0].zfill(2), parts[1].zfill(2), parts[2].zfill(4)
    return {f"{prefix} 1": j, f"{prefix} 2": m, f"{prefix} 3": a}


def _check(value: bool) -> str:
    return "/Yes" if value else "/Off"


def _trunc(s: str, n: int = 250) -> str:
    return str(s or "")[:n]


def _nom(full: str) -> str:
    parts = (full or "").strip().split()
    # Heuristique : le nom de famille est en MAJUSCULES ou le dernier mot
    for p in parts:
        if p.isupper() and len(p) > 1:
            return p
    return parts[-1].upper() if len(parts) > 1 else (parts[0].upper() if parts else "")


def _prenom(full: str) -> str:
    parts = (full or "").strip().split()
    # Le prénom est le premier mot qui n'est pas en MAJUSCULES
    for p in parts:
        if not p.isupper():
            return p
    return parts[0] if parts else ""


def _contains_any(text: str, keywords: list[str]) -> bool:
    t = text.lower()
    return any(k in t for k in keywords)


# ── Mapping principal ─────────────────────────────────────────────────────────

def build_field_map(donnees: dict[str, Any], service_type: str = "adulte") -> dict[str, str]:
    """
    Construit le dict complet {nom_champ_pdf: valeur} depuis synthese_json.
    Couvre les 20 pages du CERFA 15692*01.
    """
    fields: dict[str, str] = {}

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 1 — Page de garde : type de demande + dossier existant
    # ════════════════════════════════════════════════════════════════════════
    type_dos  = str(donnees.get("type_dossier", "INITIAL")).upper()
    hist      = str(donnees.get("historique_mdph", "")).lower()
    num_dos   = str(donnees.get("numero_dossier_mdph", "")).strip()

    # Cases type de demande
    fields["Case à cocher P1 1"] = _check(
        type_dos in ("INITIAL", "PREMIERE") or
        ("première" in hist or "premier" in hist or "1ère" in hist) and "renouvell" not in hist
    )
    fields["Case à cocher P1 2"] = _check(
        type_dos in ("SITUATION_CHANGEE", "CHANGEMENT") or "changé" in hist or "change" in hist
    )
    fields["Case à cocher P1 3"] = _check(
        type_dos in ("REEVALUATION", "REVISION") or
        "réévaluation" in hist or "reevaluation" in hist or "révision" in hist
    )
    fields["Case à cocher P1 A"] = _check(
        type_dos in ("RENOUVELLEMENT",) or "renouvell" in hist
    )
    fields["Case à cocher P1 B"] = _check(
        type_dos == "AIDANT" or donnees.get("aidant_demande")
    )

    # Département MDPH
    fields["Champ de texte P1 1"] = str(donnees.get("departement", ""))

    # Dossier existant
    if num_dos:
        fields["Champ de texte P 1 2"] = num_dos   # N° de dossier existant

    # Urgence
    if donnees.get("urgence") or "urgent" in hist or "échéance" in hist:
        fields["Case à cocher P3 5"] = "/Yes"

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 2 — A1 Identité
    # ════════════════════════════════════════════════════════════════════════
    nom_complet = donnees.get("nom_prenom", "")
    fields["Champ de texte P2 1"] = _nom(nom_complet)    # Nom de naissance
    fields["Champ de texte P2 3"] = _prenom(nom_complet) # Prénom(s)

    # Genre
    genre = str(donnees.get("genre", "")).lower()
    fields["Case à cocher 5"] = _check(_contains_any(genre, ["homme", " m ", "masculin"]))
    fields["Case à cocher 6"] = _check(_contains_any(genre, ["femme", " f ", "féminin", "feminin"]))

    # Date de naissance
    fields.update(_date_to_fields(donnees.get("date_naissance", ""), "Date A"))

    # Nationalité
    nat = str(donnees.get("nationalite", "française")).lower()
    fields["Case à cocher 7"] = _check("franc" in nat)
    fields["Case à cocher 8"] = _check(any(k in nat for k in ("euro", "eee", "suisse")))
    fields["Case à cocher 9"] = _check("franc" not in nat and not any(k in nat for k in ("euro", "eee", "suisse")))

    # Adresse
    adresse = str(donnees.get("adresse_complete", ""))
    cp_m = re.search(r"\b(\d{5})\b", adresse)
    if cp_m:
        fields["Champ de texte P2 8"] = adresse[:cp_m.start()].strip()
        fields["Champ de texte 17"]   = cp_m.group(1)
        fields["Champ de texte 18"]   = adresse[cp_m.end():].strip()
    elif adresse:
        fields["Champ de texte P2 8"] = adresse

    fields["Champ de texte P 2 9"] = _trunc(donnees.get("telephone", ""), 20)
    fields["Champ de texte 19"]    = "France"

    # NIR
    nir = str(donnees.get("num_secu", ""))
    if service_type == "enfant":
        fields.update(_nir_to_fields(nir, "N° SS Enfant"))
    elif nir:
        fields.update(_nir_to_fields(nir, "Numero SS"))

    # N° allocataire
    fields["Champ de texte P2 10"] = _trunc(donnees.get("numero_allocataire", ""), 20)

    # Organisme payeur
    org = str(donnees.get("organisme_payeur", "")).upper()
    if "CAF" in org:
        fields["Case à cocher 4"] = "/Yes"  # CAF

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 2 — A2 Représentant légal (enfant / protégé)
    # ════════════════════════════════════════════════════════════════════════
    rep = donnees.get("representant_legal_nom", "")
    if rep:
        fields["Autorite Parent 1  A"] = _nom(rep)
        fields["Autorite Parent 1  B"] = _prenom(rep)
        fields["Autorite Parent 1  G"] = str(donnees.get("representant_legal_lien", ""))
        fields["Autorite Parent 1  I"] = _trunc(donnees.get("telephone", ""), 20)

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 3 — A4 Mesure de protection (adulte protégé)
    # ════════════════════════════════════════════════════════════════════════
    if service_type == "protege":
        fields["REPRESENTANT LEGAL 1"] = _trunc(donnees.get("type_protection", ""), 80)
        fields["REPRESENTANT LEGAL 3"] = _nom(rep)
        fields["REPRESENTANT LEGAL 6"] = _trunc(donnees.get("jugement_tribunal", ""), 100)

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 5 — B1 Vie quotidienne : mode de vie + ressources + accidents
    # ════════════════════════════════════════════════════════════════════════
    mode     = str(donnees.get("mode_vie", "")).lower()
    logement = str(donnees.get("type_logement", "")).lower()
    ressources = str(donnees.get("traitements", "") or donnees.get("ressources", "")).lower()

    # Mode de vie
    fields["Case à cocher P5 1"]  = _check(_contains_any(mode, ["seul", "seule"]))
    fields["Case à cocher P5 2"]  = _check(_contains_any(mode, ["couple", "conjoint"]))
    fields["Case à cocher P5 3"]  = _check(_contains_any(mode, ["parent", "famille"]))

    # Logement
    fields["Case à cocher P5 7"]  = _check(_contains_any(logement, ["propriétaire", "proprietaire"]))
    fields["Case à cocher P5 8"]  = _check("locataire" in logement)
    fields["Case à cocher P5 4"]  = _check(_contains_any(logement, ["établissement", "structure", "ehpad", "esat"]))

    # Accident de travail (champs B1 page 5)
    acc = str(donnees.get("accident_travail", "")).lower()
    if acc or "accident du travail" in str(donnees.get("statut_emploi", "")).lower():
        fields["Case à cocher P5 4"] = "/Yes"  # accident du travail
        # Extraire l'année de l'accident si présente
        acc_year = re.search(r"\b(20\d{2}|19\d{2})\b", acc)
        if acc_year:
            fields["Champ de texte P5 7"] = acc_year.group(1)

    # Ressources (page 5 — aide financière)
    # Pension d'invalidité / AAH / RSA selon statut
    statut_all = str(donnees.get("statut_emploi", "") or "").lower()
    if "invalidité" in statut_all or "invalide" in statut_all:
        fields["Case à cocher P5 16"] = "/Yes"  # pension d'invalidité
    if "aah" in statut_all.upper() or "aah" in str(donnees.get("droits_demandes", "")).upper():
        fields["Case à cocher P5 15"] = "/Yes"  # AAH

    # Indemnités journalières
    if "indemnité" in statut_all or "arrêt" in statut_all:
        fields["Case à cocher P5 19"] = "/Yes"

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 6 — B2 Besoins dans la vie quotidienne
    # ════════════════════════════════════════════════════════════════════════
    impact = str(donnees.get("impact_quotidien", "")).lower()
    rest   = str(donnees.get("restrictions_emploi", "")).lower()
    all_impact = impact + " " + rest

    fields["Case à cocher P6 B1"]  = _check(_contains_any(all_impact, ["dépense", "budget", "financ"]))
    fields["Case à cocher P6 B2"]  = _check(_contains_any(all_impact, ["hygiène", "toilette", "lavage"]))
    fields["Case à cocher P6 B3"]  = _check(_contains_any(all_impact, ["habill", "vêtement"]))
    fields["Case à cocher P6 B4"]  = _check(_contains_any(all_impact, ["repas", "manger", "cuisine", "préparer"]))
    fields["Case à cocher P6 B10"] = _check(_contains_any(all_impact, ["santé", "traitement", "médic", "soin"]))

    # Déplacements (page 7)
    fields["Case à cocher P7 2"]   = _check(_contains_any(all_impact, ["déplacer", "déplacement", "marcher", "domicile"]))
    fields["Case à cocher P7 3"]   = _check(_contains_any(all_impact, ["sortir", "extérieur"]))
    fields["Case à cocher P7 4"]   = _check(_contains_any(all_impact, ["transport", "commun"]))
    fields["Case à cocher P7 9"]   = _check(_contains_any(all_impact, ["fatigue", "fatigab"]))
    fields["Case à cocher P7 10"]  = _check(_contains_any(all_impact, ["douleur"]))
    fields["Case à cocher P7 11"]  = _check(_contains_any(all_impact, ["dormir", "sommeil"]))
    fields["Case à cocher P7 12"]  = _check(_contains_any(all_impact, ["stress", "anxiété", "anxiete", "psycho", "trauma"]))

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 7 — B3 Attentes : établissement identifié
    # ════════════════════════════════════════════════════════════════════════
    proj = str(donnees.get("projet_professionnel", "")).lower()
    if _contains_any(proj, ["esat", "milieu protégé", "iae"]):
        fields["Case à cocher P7 15"] = "/Yes"  # vivre en établissement
    elif proj:
        fields["Case à cocher P7 14"] = "/Yes"  # vivre à domicile

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 8 — B texte libre : informations importantes vie quotidienne
    # Sprint P0.2-H1 : priorité au texte narratif Phase 3
    # ════════════════════════════════════════════════════════════════════════
    texte_narratif_b = donnees.get("texte_b_vie_quotidienne", "") or ""
    notes_pro        = donnees.get("notes_pro", "") or ""
    if texte_narratif_b.strip():
        # Priorité 1 : texte narratif Phase 3
        fields["Champ de texte P8 1"] = _trunc(texte_narratif_b, 2000)
    elif notes_pro.strip():
        # Priorité 2 — Sprint P0.5-C : texte collé par le professionnel (notes_pro)
        # Le professionnel a saisi une description complète → l'utiliser directement
        fields["Champ de texte P8 1"] = _trunc(notes_pro, 2000)
    else:
        # Fallback : dump médical brut (comportement antérieur)
        texte_p8_parts = []
        if donnees.get("diagnostics"):
            texte_p8_parts.append(f"Diagnostics : {donnees['diagnostics']}")
        if donnees.get("traitements"):
            texte_p8_parts.append(f"Traitements : {donnees['traitements']}")
        if donnees.get("restrictions_emploi"):
            texte_p8_parts.append(f"Restrictions : {donnees['restrictions_emploi']}")
        if donnees.get("accident_travail"):
            texte_p8_parts.append(f"Accident de travail : {donnees['accident_travail']}")
        if texte_p8_parts:
            fields["Champ de texte P8 1"] = _trunc(" | ".join(texte_p8_parts), 500)

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 9 — C Scolarité (enfant / mixte)
    # ════════════════════════════════════════════════════════════════════════
    if service_type in ("enfant", "mixte"):
        scol = str(donnees.get("situation_scolaire", "")).lower()
        fields["Case à cocher P 9 1"]  = _check(_contains_any(scol, ["ordinaire", "classique"]))
        fields["Case à cocher P 9 2"]  = _check("domicile" in scol)
        fields["Case à cocher P 9 3"]  = _check(_contains_any(scol, ["ime", "médico", "medico"]))
        fields["Case à cocher P 9 4"]  = _check("sessad" in scol)
        fields["Case à cocher P 9 5"]  = _check("partagé" in scol or "partage" in scol)
        fields["Case à cocher P 9 9"]  = _check(_contains_any(scol, ["non scolarisé", "non-scolar", "déscolarisé"]))
        etab = donnees.get("etablissement_scolaire", "")
        if etab:
            fields["Champ de texte P9 1"] = _trunc(etab, 100)
        formation = donnees.get("formation_actuelle", "")
        if formation:
            fields["Champ de texte P9 4"] = _trunc(formation, 100)

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 13 — D1 Situation professionnelle
    # ════════════════════════════════════════════════════════════════════════
    if service_type in ("adulte", "mixte", "protege"):
        statut_e = str(donnees.get("statut_emploi", "")).lower()

        fields["Case à cocher P 13 1"]  = _check(_contains_any(statut_e, ["emploi"]) and "sans" not in statut_e)
        fields["Case à cocher P 13 2"]  = _check(_contains_any(statut_e, ["milieu ordinaire", "entreprise"]) and "sans" not in statut_e)
        fields["Case à cocher P 13 9"]  = _check("esat" in statut_e)
        fields["Case à cocher P 13 15"] = _check("retraite" in statut_e)
        fields["Case à cocher P 13 16"] = _check(_contains_any(statut_e, ["sans emploi", "chômage", "chomage", "inactif"]))

        # Employeur
        if donnees.get("nom_employeur"):
            fields["Champ de texte P13 3"] = _trunc(donnees["nom_employeur"], 60)

        # Difficultés liées au handicap (champ P13 7 et P13 8)
        diff_parts = []
        if donnees.get("restrictions_emploi"):
            diff_parts.append(donnees["restrictions_emploi"])
        if donnees.get("impact_quotidien"):
            diff_parts.append(donnees["impact_quotidien"])
        if diff_parts:
            fields["Champ de texte P13 7"] = _trunc(" | ".join(diff_parts), 300)
            fields["Champ de texte P13 8"] = _trunc(diff_parts[0], 200)

        # Date accident travail
        if donnees.get("accident_travail"):
            acc_text = str(donnees["accident_travail"])
            acc_yr = re.search(r"\b(20\d{2}|19\d{2})\b", acc_text)
            if acc_yr:
                fields["DATE P13 7"] = acc_yr.group(1)
            fields["Case à cocher P 13 10"] = "/Yes"  # arrêt de travail

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 14 — D situation sans emploi / recherche
    # Sprint P0.2-H1 : priorité au texte narratif Phase 3 pour les difficultés pro
    # ════════════════════════════════════════════════════════════════════════
    if service_type in ("adulte", "mixte", "protege"):
        statut_e = str(donnees.get("statut_emploi", "")).lower()
        if _contains_any(statut_e, ["sans emploi", "chômage", "chomage"]):
            fields["Case à cocher P14 1"] = "/Yes"  # sans emploi
            if "pôle emploi" in statut_e or "france travail" in statut_e:
                fields["Case à cocher P14 4"] = "/Yes"

        # Texte narratif Section D (difficultés professionnelles)
        texte_narratif_d = donnees.get("texte_d_situation_pro", "") or ""
        if texte_narratif_d.strip():
            fields["Champ de texte P14 1"] = _trunc(texte_narratif_d, 2000)

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 15 — D2 Parcours professionnel
    # ════════════════════════════════════════════════════════════════════════
    if service_type in ("adulte", "mixte", "protege") and donnees.get("nom_employeur"):
        fields["P15 Tableau A 1 "] = _trunc(donnees.get("nom_employeur", ""), 50)

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 16 — D3 / C3 Projet professionnel / Projet de vie
    # Sprint P0.2-H1 : texte narratif projet de vie (section E)
    # Sprint P0.4 : étendu au profil enfant (P16 1 = attentes scolaires/vie)
    # ════════════════════════════════════════════════════════════════════════
    texte_narratif_e = donnees.get("texte_e_projet_vie", "") or ""
    if texte_narratif_e.strip():
        fields["Champ de texte P16 1"] = _trunc(texte_narratif_e, 2000)

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 17 — E1/E2/E3 Droits et prestations demandés
    # ════════════════════════════════════════════════════════════════════════
    droits = str(donnees.get("droits_demandes", "")).upper()
    droits_low = droits.lower()

    # E1 — vie quotidienne (<20 ans)
    fields["Case à cocher P17 1"]  = _check("AEEH" in droits)
    fields["Case à cocher P17 2"]  = _check("PCH" in droits)
    fields["Case à cocher P17 3"]  = _check("CMI" in droits)
    fields["Case à cocher P17 4"]  = _check("AVPF" in droits)

    # E1 — vie quotidienne (>20 ans)
    fields["Case à cocher P17 5"]  = _check("AAH" in droits)
    fields["Case à cocher P17 6"]  = _check("RQTH" in droits)
    fields["Case à cocher P17 7"]  = _check("PCH" in droits)
    fields["Case à cocher P17 11"] = _check(_contains_any(droits_low, ["esat", "orientation médico", "orientation medico"]))

    # E3 — travail / emploi / formation
    fields["Case à cocher P18 1"]  = _check("RQTH" in droits)
    fields["Case à cocher P18 2"]  = _check(_contains_any(droits_low, ["orientation professionnelle", "orientation prof"]))
    fields["Case à cocher P18 3"]  = _check(_contains_any(droits, ["CRP", "CPO", "UEROS"]))
    fields["Case à cocher P18 4"]  = _check("ESAT" in droits)
    fields["Case à cocher P18 6"]  = _check("emploi accompagné" in droits_low)

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 19 — F Aidant familial
    # ════════════════════════════════════════════════════════════════════════
    aidant = donnees.get("aidant_nom", "")
    if aidant:
        fields["Champ de texte P19 1"] = _nom(aidant)
        fields["Champ de texte P19 2"] = _prenom(aidant)
        if donnees.get("aidant_besoins"):
            fields["Champ de texte P20 1"] = _trunc(donnees["aidant_besoins"], 200)

    # Supprime les valeurs vides
    return {k: v for k, v in fields.items() if v not in ("", None, "/Off")}
