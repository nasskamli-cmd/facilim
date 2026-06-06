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
    # QA-6 FIX — Le PDF CERFA 15692*01 numérote les cases NSS à partir de 3
    # (Numero SS 3 → Numero SS 17 pour adulte, N° SS Enfant 1 → 15 pour enfant)
    # Pour adulte (prefix "Numero SS") : décalage +3 pour coller aux vrais noms AcroForm
    # Pour enfant (prefix "N° SS Enfant") : pas de décalage (PDF commence bien à 1)
    if prefix == "Numero SS":
        return {f"{prefix} {i+3}": cleaned[i] for i in range(15)}
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
    # Sprint P0.6 — Normalisation case-insensitive + accents pour réévaluation
    _type_dos_norm = type_dos.lower().replace("é", "e").replace("è", "e")
    fields["Case à cocher P1 3"] = _check(
        type_dos in ("REEVALUATION", "REVISION", "RÉÉVALUATION", "RÉVISION")
        or _type_dos_norm in ("reevaluation", "revision")
        or any(k in hist for k in ("réévaluation", "reevaluation", "révision", "revision"))
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

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 3 — A3 Situations d'urgence — FACILIM 40 P0 LOT 1
    # ════════════════════════════════════════════════════════════════════════
    _urgence_src = " ".join(str(donnees.get(c, "") or "") for c in [
        "historique_mdph", "droits_demandes", "statut_emploi",
        "impact_quotidien", "notes_pro", "situation_scolaire",
    ]).lower()

    # P3 1 — Fin de droits imminente (< 2 mois)
    fields["Case à cocher P3 1"] = _check(_contains_any(_urgence_src, [
        "renouvellement", "échéance", "echeance", "expire", "fin de droits",
        "arrive à terme", "dans 2 mois",
    ]))

    # P3 2 — Risque de perte de logement / domicile
    fields["Case à cocher P3 2"] = _check(_contains_any(_urgence_src, [
        "ne peut plus vivre", "perte de logement", "expulsion",
        "quitter domicile", "sans hébergement",
    ]))

    # P3 3 — Scolarité en danger (NOM AVEC ESPACE dans le PDF officiel : P 3 3)
    fields["Case à cocher P 3 3"] = _check(
        service_type in ("enfant", "mixte") and
        _contains_any(_urgence_src, [
            "exclusion scolaire", "déscolarisé", "descolarise",
            "école ne peut plus", "risque déscolarisation",
        ])
    )

    # P3 4 — Sortie d'hospitalisation sans solution
    fields["Case à cocher P3 4"] = _check(_contains_any(_urgence_src, [
        "sortie hospitalisation", "sortie hôpital", "rééducation terminée",
        "retour difficile", "ne peut pas rentrer",
    ]))

    # P3 5 — Risque de perte d'emploi (urgence emploi)
    if donnees.get("urgence") or "urgent" in hist or "échéance" in hist:
        fields["Case à cocher P3 5"] = "/Yes"
    else:
        fields["Case à cocher P3 5"] = _check(_contains_any(_urgence_src, [
            "perd son emploi", "risque licenciement", "inaptitude imminente",
        ]))

    # P3 6 — Début d'emploi ou de formation imminent
    fields["Case à cocher P3 6"] = _check(_contains_any(_urgence_src, [
        "commence bientôt", "nouvel emploi", "nouveau poste", "début contrat",
        "embauche prochaine", "formation démarre", "prise de poste",
    ]))

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 4 — Consentements + Procédure simplifiée — FACILIM 40 P0 LOT 2
    # ════════════════════════════════════════════════════════════════════════
    # P4 4 — Consentement échanges professionnels
    # Facilim obtient le consentement via WhatsApp/interface → toujours /Yes
    fields["Case à cocher P4 4"] = "/Yes"
    fields["Case à cocher P4 5"] = "/Off"  # Refus → jamais

    # P4 0 — Procédure simplifiée renouvellement
    fields["Case à cocher P4 0"] = _check(
        type_dos in ("RENOUVELLEMENT",) or "renouvell" in hist
    )
    # P4 1 — Procédure simplifiée AVPF
    _droits_up_p4 = str(donnees.get("droits_demandes", "")).upper()
    fields["Case à cocher P4 1"] = _check("AVPF" in _droits_up_p4)

    # P4 2 — Procédure simplifiée RQTH
    fields["Case à cocher P4 2"] = _check(
        "RQTH" in _droits_up_p4 and
        (type_dos in ("RENOUVELLEMENT",) or "renouvell" in hist)
    )
    # P4 3 — Procédure simplifiée urgence
    fields["Case à cocher P4 3"] = _check(
        bool(donnees.get("urgence")) or
        _contains_any(_urgence_src, ["urgence", "urgent"])
    )

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

    # Sprint P0.6 — Correction mapping téléphone/commune
    # Preuve CERFA Nassim : Champ de texte 24 = téléphone, P 2 9 = commune
    fields["Champ de texte 24"]    = _trunc(donnees.get("telephone", ""), 20)
    # Champ de texte P 2 9 = commune (déjà renseigné par le parsing adresse → Champ de texte 18)
    # Assurer la cohérence en le renseignant aussi
    if cp_m:
        fields["Champ de texte P 2 9"] = adresse[cp_m.end():].strip().lstrip(",").strip()
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
    # Fix QA-1 : REPRESENTANT LEGAL mappé si service_type=protege OU si type_protection présent
    _type_prot = donnees.get("type_protection", "")
    if service_type == "protege" or _type_prot:
        fields["REPRESENTANT LEGAL 1"] = _trunc(_type_prot, 80)
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

        # Sprint QA-1 Fix 2 — Aménagements scolaires (P10) — TDAH, DYS, TSA
        # Sources : impact_quotidien · situation_scolaire · diagnostics · notes_pro
        _all_scol = " ".join(str(donnees.get(c, "") or "") for c in [
            "situation_scolaire", "impact_quotidien", "diagnostics",
            "notes_pro", "texte_c_scolarite",
        ]).lower()
        # AESH / AVS
        # QA-6 FIX — Correction nommage P10 : supprimer l'espace (P 10 → P10)
        # Le PDF CERFA 15692*01 utilise "Case à cocher P10 X" sans espace
        fields["Case à cocher P10 1"] = _check(
            _contains_any(_all_scol, ["aesh", "avs", "accompagnant", "auxiliaire"])
        )
        # Tiers-temps / temps aménagé / temps supplémentaire
        fields["Case à cocher P10 2"] = _check(
            _contains_any(_all_scol, ["tiers-temps", "tiers temps", "temps aménagé",
                                       "temps supplémentaire", "temps majoré", "1/3 temps"])
        )
        # Matériel adapté / ordinateur / tablette
        fields["Case à cocher P10 3"] = _check(
            _contains_any(_all_scol, ["matériel adapté", "ordinateur", "tablette",
                                       "logiciel", "dictée", "aide technique", "matériel"])
        )
        # Transport scolaire adapté
        fields["Case à cocher P10 4"] = _check(
            _contains_any(_all_scol, ["transport", "taxi", "véhicule scolaire"])
        )

        # ── FACILIM 40 P0 LOT 3 — Orientations médico-sociales P10 (5-12) ──
        _all_scol_orient = " ".join(str(donnees.get(c, "") or "") for c in [
            "situation_scolaire", "droits_demandes", "diagnostics",
            "notes_pro", "texte_c_scolarite", "texte_e_projet_vie", "impact_quotidien",
        ]).lower()

        # P10 5 — SESSAD
        fields["Case à cocher P10 5"] = _check(
            _contains_any(_all_scol_orient, ["sessad"])
        )
        # P10 6 — IME
        fields["Case à cocher P10 6"] = _check(
            _contains_any(_all_scol_orient, ["ime", "institut médico-éducatif",
                                               "medico-educatif", "médico-éducatif"])
        )
        # P10 7 — ITEP
        fields["Case à cocher P10 7"] = _check(
            _contains_any(_all_scol_orient, ["itep", "troubles comportement"])
        )
        # P10 9 — ULIS
        fields["Case à cocher P10 9"] = _check(
            _contains_any(_all_scol_orient, ["ulis"])
        )
        # P10 10 — EEAP (polyhandicap)
        fields["Case à cocher P10 10"] = _check(
            _contains_any(_all_scol_orient, ["eeap", "polyhandicap"])
        )
        # P10 11 — IEM (déficient visuel)
        fields["Case à cocher P10 11"] = _check(
            _contains_any(_all_scol_orient, ["iem", "déficient visuel", "deficient visuel",
                                               "malvoyant", "aveugle"])
        )
        # P10 12 — Institut déficient auditif / sourd
        fields["Case à cocher P10 12"] = _check(
            _contains_any(_all_scol_orient, ["sourd", "malentendant", "déficient auditif",
                                               "surdité"])
        )

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

        # ── FACILIM 40 P0 LOT 4 — Situations d'inactivité P14 ──────────────
        _statut_p14 = str(donnees.get("statut_emploi", "") or "").lower()
        _diag_p14   = str(donnees.get("diagnostics", "") or "").lower()
        _impact_p14 = str(donnees.get("impact_quotidien", "") or "").lower()
        _p14_all    = f"{_statut_p14} {_diag_p14} {_impact_p14}"

        # P14 2 — Arrêt maladie longue durée
        fields["Case à cocher P14 2"] = _check(_contains_any(_p14_all, [
            "arrêt longue durée", "arrêt de longue", "arret longue duree",
            "arrêt maladie", "longue maladie",
        ]))

        # P14 3 — Invalidité (pension)
        fields["Case à cocher P14 3"] = _check(_contains_any(_p14_all, [
            "invalidité", "invalide", "pension invalidité", "pension d'invalidité",
            "2ème catégorie", "3ème catégorie",
        ]))

        # P14 5 — Congé parental / disponibilité parent
        fields["Case à cocher P14 5"] = _check(_contains_any(_p14_all, [
            "congé parental", "conge parental", "disponibilité", "arrêt aidant",
        ]))

        # P14 6 — Inaptitude / licenciement pour inaptitude
        fields["Case à cocher P14 6"] = _check(_contains_any(_p14_all, [
            "inaptitude", "inapte", "licencié pour inaptitude", "licencié pour inapte",
            "licenciement pour inaptitude",
        ]))

        # P14 7 — Bénévolat / activité non rémunérée
        fields["Case à cocher P14 7"] = _check(_contains_any(_p14_all, [
            "bénévole", "benevolat", "bénévolat", "activité bénévole",
        ]))

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

    # Fix QA-1 : P16 5 — Bilan de compétences / bilan capacités (ESPO)
    _bilan_cap_signal = _contains_any(" ".join(str(donnees.get(c,"") or "") for c in [
        "droits_demandes","projet_orientation","texte_d_situation_pro","texte_e_projet_vie","notes_pro",
    ]).lower(), [
        "bilan de compétences", "bilan capacités", "bilan capacites",
        "bilan de compétence", "espo", "bilan compétences",
    ])
    if _bilan_cap_signal:
        fields["Case à cocher P16 5"] = "/Yes"

    # ── FACILIM 40 P0 LOT 5 — Orientations P16 ─────────────────────────────
    if service_type in ("adulte", "protege", "mixte"):
        _proj_p16 = " ".join(str(donnees.get(c, "") or "") for c in [
            "droits_demandes", "projet_orientation", "texte_e_projet_vie",
            "statut_emploi", "notes_pro",
        ]).lower()
        _droits_p16 = str(donnees.get("droits_demandes", "")).upper()

        # P16 1 — Souhait emploi milieu ordinaire (avec adaptations)
        fields["Case à cocher P16 1"] = _check(
            _contains_any(_proj_p16, ["milieu ordinaire", "emploi ordinaire",
                                       "retour emploi", "emploi classique"]) or
            ("RQTH" in _droits_p16 and "ESAT" not in _droits_p16)
        )

        # P16 2 — Souhait ESAT / milieu protégé
        fields["Case à cocher P16 2"] = _check(
            _contains_any(_proj_p16, ["esat", "milieu protégé", "milieu protege",
                                       "travail protégé"])
        )

        # P16 3 — Sans activité professionnelle souhaitée
        fields["Case à cocher P16 3"] = _check(
            _contains_any(_proj_p16, ["sans activité", "aucune activité professionnelle",
                                       "ne souhaite pas travailler", "pas de projet professionnel"])
        )

        # Champ P16 2 — Nom de la structure souhaitée (NOTE : P 16 2 avec espace)
        _structure_souhaitee = donnees.get("projet_orientation", "") or donnees.get("etablissement_souhaite", "")
        if _structure_souhaitee:
            fields["Champ de texte P 16 2"] = _trunc(str(_structure_souhaitee), 100)

        # Champ P16 3 — Informations complémentaires orientation
        if texte_narratif_e.strip():
            fields["Champ de texte P16 3"] = _trunc(texte_narratif_e[:300], 300)

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 17 — E1/E2/E3 Droits et prestations demandés
    # ════════════════════════════════════════════════════════════════════════
    droits = str(donnees.get("droits_demandes", "")).upper()
    droits_low = droits.lower()

    # Sprint QA-1 — Sources enrichies pour la détection des droits
    # statut_emploi, diagnostics, impact_quotidien, notes_pro, document_knowledge
    _dk_projets = " ".join(
        i.get("valeur","") for i in
        (donnees.get("_document_knowledge") or {}).get("projets", [])
        if isinstance(i, dict)
    ).lower()
    _dk_freins = " ".join(
        i.get("valeur","") for i in
        (donnees.get("_document_knowledge") or {}).get("freins", [])
        if isinstance(i, dict)
    ).lower()
    _all_sources = " ".join(str(donnees.get(c,"") or "") for c in [
        "droits_demandes","statut_emploi","diagnostics","impact_quotidien",
        "notes_pro","projet_orientation","texte_d_situation_pro","texte_e_projet_vie",
        "aidant_besoins","aidant_nom",
    ]).lower() + " " + _dk_projets + " " + _dk_freins

    # E1 — vie quotidienne (<20 ans)
    fields["Case à cocher P17 1"]  = _check("AEEH" in droits)
    fields["Case à cocher P17 2"]  = _check("PCH" in droits)
    fields["Case à cocher P17 3"]  = _check("CMI" in droits)
    # Fix QA-1 : AVPF détectée depuis droits OU signaux aidant (réduction activité pro pour enfant handicapé)
    _avpf_signal = "AVPF" in droits or _contains_any(_all_sources, [
        "avpf", "réduction activité", "reduction activite", "congé parental", "conge parental",
        "cessation activité", "cessation activite", "mi-temps aidant", "arrêt aidant",
    ])
    fields["Case à cocher P17 4"]  = _check(_avpf_signal)

    # E1 — vie quotidienne (>20 ans)
    # Fix QA-1-4 : AAH détectée depuis droits ET signaux indirects (maladie chronique + sans emploi)
    _arret_long = _contains_any(_all_sources, [
        "arrêt longue durée", "arrêt de longue", "arret longue duree",
        "sans emploi", "sans activité", "inapte", "invalidité", "allocation invalidité",
    ])
    _maladie_chron = _contains_any(_all_sources, [
        "fibromyalgie", "sclérose en plaques", "sep", "lupus", "cancer",
        "insuffisance", "maladie chronique", "fatigue chronique", "sfc",
        "parkinson", "épilepsie", "diabète", "insuffisance rénale", "vih",
        "sida", "polyarthrite", "crohn", "spondylarthrite",
    ])
    _aah_signal = "AAH" in droits or \
                  _contains_any(_all_sources, ["aah", "allocation adulte", "allocation aux adultes"]) or \
                  (_arret_long and _maladie_chron)
    fields["Case à cocher P17 5"]  = _check(_aah_signal)
    fields["Case à cocher P17 6"]  = _check("RQTH" in droits)
    fields["Case à cocher P17 7"]  = _check("PCH" in droits)

    # Fix QA-1-3 : ESAT/ESMS détectés depuis droits ET signaux ESAT dans données
    _esat_signal = _contains_any(droits_low, ["esat", "orientation médico", "orientation medico"]) or \
                   _contains_any(_all_sources, ["esat", "milieu protégé", "milieu protege"])
    fields["Case à cocher P17 11"] = _check(_esat_signal)

    # Fix QA-1-5 : CMI stationnement — signaux marche difficile (SEP, moteur, fatigue neuro)
    _cmi_station_signal = _contains_any(droits_low, ["cmi stationnement", "stationnement"]) or \
                          _contains_any(_all_sources, [
                              "marche difficile", "ne peut pas marcher", "marcher longtemps",
                              "fauteuil", "déambulateur", "canne", "béquille",
                              "périmètre marche", "distance marche",
                              "fatigue neurologique", "sclérose en plaques", "sep ",
                              "ne peut plus marcher", "marche limitée",
                          ])
    fields["Case à cocher P17 13"] = _check(_cmi_station_signal)

    # ── FACILIM 40 P0 LOT 6 — Droits P17 manquants ─────────────────────────
    # P17 8 — Orientation ESMS (MAS/FAM/établissement médico-social lourd)
    fields["Case à cocher P17 8"] = _check(
        _contains_any(droits_low, ["mas", "fam", "esms", "maison d'accueil"]) or
        _contains_any(_all_sources, [
            "maison d'accueil spécialisée", "foyer d'accueil médicalisé",
            "polyhandicap.{0,15}adulte", "grabataire",
        ])
    )
    # P17 9 — Foyer de vie
    fields["Case à cocher P17 9"] = _check(
        _contains_any(droits_low, ["foyer de vie", "foyer vie"]) or
        _contains_any(_all_sources, ["foyer de vie"])
    )
    # P17 10 — Foyer d'hébergement (travailleurs ESAT)
    fields["Case à cocher P17 10"] = _check(
        _contains_any(droits_low, ["foyer d'hébergement", "foyer hebergement"]) or
        (_esat_signal and _contains_any(_all_sources, [
            "hébergement", "logement accompagné", "foyer hébergement",
        ]))
    )
    # P17 12 — Accueil de jour
    fields["Case à cocher P17 12"] = _check(
        _contains_any(droits_low, ["accueil de jour", "accueil jour"]) or
        _contains_any(_all_sources, ["accueil de jour"])
    )
    # P17 14 — CMI priorité (file d'attente, transport)
    fields["Case à cocher P17 14"] = _check(
        _contains_any(droits_low, ["cmi priorité", "cmi priorite", "carte priorité"]) or
        _contains_any(_all_sources, [
            "ne peut pas rester debout", "douleur debout",
            "file d'attente difficile", "difficile rester debout",
        ])
    )
    # P17 15 — ACTP (droit historique, renouvellements antérieurs)
    fields["Case à cocher P17 15"] = _check(
        _contains_any(droits_low, ["actp", "allocation compensatrice"])
    )
    # P17 16 — Autre prestation vie quotidienne
    fields["Case à cocher P17 16"] = _check(
        _contains_any(droits_low, ["autre prestation"])
    )

    # E3 — travail / emploi / formation
    fields["Case à cocher P18 1"]  = _check("RQTH" in droits)
    fields["Case à cocher P18 2"]  = _check(
        _contains_any(droits_low, ["orientation professionnelle", "orientation prof"]) or
        ("RQTH" in droits and service_type in ("adulte", "mixte", "protege"))
    )
    fields["Case à cocher P18 3"]  = _check(
        _contains_any(droits_low, ["crp", "cpo", "ueros", "espo"]) or
        _contains_any(_all_sources, ["espo", "bilan capacités", "bilan capacites", "crp ", "cpo ", "ueros"])
    )

    # Fix QA-1-3 : ESAT dans E3 (P18 4) depuis droits ET signaux
    fields["Case à cocher P18 4"]  = _check("ESAT" in droits or _esat_signal)

    # FACILIM 40 P0 LOT 7 — P18 5 ESRP
    fields["Case à cocher P18 5"]  = _check(
        _contains_any(droits_low, ["esrp"]) or
        _contains_any(_all_sources, [
            "esrp", "rééducation professionnelle", "reeducation professionnelle",
            "reconversion obligatoire", "inapte.{0,20}reconversion",
        ])
    )
    fields["Case à cocher P18 6"]  = _check(
        _contains_any(droits_low, ["emploi accompagné", "emploi accompagne"]) or
        _contains_any(_all_sources, ["emploi accompagné", "job coaching"])
    )

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 19 — F Aidant familial
    # ════════════════════════════════════════════════════════════════════════
    aidant = donnees.get("aidant_nom", "")
    if aidant:
        fields["Champ de texte P19 1"] = _nom(aidant)
        fields["Champ de texte P19 2"] = _prenom(aidant)
        if donnees.get("aidant_besoins"):
            fields["Champ de texte P20 1"] = _trunc(donnees["aidant_besoins"], 200)

    # FACILIM 40 P0 — Filtre final
    # Les cases à cocher des pages décisionnelles (P3/P4/P16/P17/P18) conservent
    # leur valeur /Off (case explicitement non cochée = PDF valide + N1 couvert)
    # Les champs texte vides et les autres cases restent filtrés
    _KEEP_OFF_PAGES = re.compile(
        r"^Case\s+à\s+cocher\s+(P3\s|P\s*3\s|P4\s|P16\s|P17\s|P18\s)"
    )
    return {
        k: v for k, v in fields.items()
        if v not in ("", None)
        and not (v == "/Off" and not _KEEP_OFF_PAGES.match(k))
    }
