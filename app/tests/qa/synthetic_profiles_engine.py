"""
app/tests/qa/synthetic_profiles_engine.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA-5 — Générateur de profils synthétiques réalistes

Génère des centaines de situations MDPH réalistes pour tests massifs.
Aucun appel LLM — rapide, reproductible, déterministe (seed).

30+ types de profils × variations automatiques sur 12 dimensions :
  âge · sexe · situation familiale · situation scolaire
  situation professionnelle · documents présents/absents
  droits demandés/oubliés · niveau retentissement
  aidant · projet professionnel · type demande · niveau documentation

Usage :
  from app.tests.qa.synthetic_profiles_engine import generer_profils
  profils = generer_profils(n=100, seed=42)
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURE
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SyntheticProfile:
    id:                     str
    famille:                str     # "enfant_tsa" | "adulte_moteur" | etc.
    profil_mdph:            str     # "adulte" | "enfant" | "protege" | "mixte"
    profil_handicap:        str
    donnees:                dict    # synthese_json compatible
    niveau_documentation:   str     # "pauvre" | "moyen" | "riche"
    type_demande:           str     # "premiere" | "renouvellement" | "reevaluation"

    # Ground truth pour validation
    droits_attendus:        list[str]   # Droits que le dossier doit explicitement demander
    droits_non_attendus:    list[str]   # Droits incompatibles avec ce profil
    droits_oublies:         list[str]   # Droits que le moteur DOIT détecter comme oubliés
    cases_cerfa_attendues:  dict[str, str]  # champs CERFA qui doivent être remplis


# ─────────────────────────────────────────────────────────────────────────────
# DONNÉES DE VARIATION
# ─────────────────────────────────────────────────────────────────────────────

_PRENOMS_H = ["Lucas", "Noah", "Tom", "Louis", "Hugo", "Théo", "Maxime", "Jules", "Karim", "Mohamed", "Antoine", "Pierre"]
_PRENOMS_F = ["Emma", "Léa", "Marie", "Sophie", "Isabelle", "Claire", "Fatima", "Camille", "Julie", "Nathalie", "Céline"]
_NOMS = ["MARTIN", "DUPONT", "BERNARD", "THOMAS", "PETIT", "DURAND", "LEROY", "MOREAU", "SIMON", "MICHEL",
          "GARCIA", "DAVID", "MARTINEZ", "ROBERT", "RICHARD", "NAIT ALI", "BENALI", "ROUSSEAU", "LAMBERT"]

_DEPARTEMENTS = ["13", "75", "69", "31", "44", "67", "06", "33", "59", "34"]

_MODES_VIE = {
    "seul":    "seul(e)",
    "couple":  "en couple",
    "famille": "avec famille",
    "parents": "chez les parents",
}

_TYPES_LOGEMENT = {
    "locataire":    "locataire appartement",
    "proprietaire": "propriétaire maison",
    "parents":      "domicile parental",
    "etablissement":"établissement spécialisé",
}


def _nom_prenom(rng: random.Random, genre: str = "h") -> tuple[str, str]:
    prenom = rng.choice(_PRENOMS_H if genre == "h" else _PRENOMS_F)
    nom = rng.choice(_NOMS)
    return nom, prenom


def _date_naissance(rng: random.Random, age: int) -> str:
    annee = 2026 - age
    mois = rng.randint(1, 12)
    jour = rng.randint(1, 28)
    return f"{jour:02d}/{mois:02d}/{annee}"


def _niveau_documentation(rng: random.Random) -> str:
    return rng.choice(["pauvre", "pauvre", "moyen", "moyen", "moyen", "riche"])


def _type_demande(rng: random.Random) -> str:
    return rng.choice(["INITIAL", "INITIAL", "INITIAL", "RENOUVELLEMENT", "REEVALUATION"])


def _impact_pauvre(base: str) -> str:
    """Version courte et vague de l'impact."""
    return base.split(",")[0] if "," in base else base[:60]


def _impact_riche(base: str, extras: list[str]) -> str:
    """Version longue et détaillée."""
    return base + ", " + ", ".join(extras)


def _num_secu_adulte(rng: random.Random, genre: str = "h", annee_naissance: int = 1975) -> str:
    """Génère un NSS synthétique réaliste (non valide, usage test uniquement)."""
    sexe = "1" if genre == "h" else "2"
    aa = str(annee_naissance % 100).zfill(2)
    mois = str(rng.randint(1, 12)).zfill(2)
    dept = str(rng.randint(1, 95)).zfill(2)
    commune = str(rng.randint(1, 999)).zfill(3)
    ordre = str(rng.randint(1, 999)).zfill(3)
    cle = str(rng.randint(1, 97)).zfill(2)
    return f"{sexe}{aa}{mois}{dept}{commune}{ordre}{cle}"


def _adresse_adulte(rng: random.Random) -> str:
    """Génère une adresse synthétique."""
    num = rng.randint(1, 150)
    rues = ["rue de la Paix", "avenue de la République", "boulevard Gambetta",
            "rue Victor Hugo", "impasse des Lilas", "chemin des Roses"]
    villes = ["Marseille", "Lyon", "Paris", "Bordeaux", "Nantes", "Strasbourg",
              "Toulouse", "Lille", "Nice", "Rennes"]
    codes = ["13001", "69001", "75001", "33000", "44000", "67000",
             "31000", "59000", "06000", "35000"]
    i = rng.randint(0, len(villes)-1)
    return f"{num} {rng.choice(rues)} {codes[i]} {villes[i]}"


# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATES PAR FAMILLE
# Chaque template définit la base du profil et les ground truth
# ─────────────────────────────────────────────────────────────────────────────

class _Template:
    """Template de profil. Rempli par le générateur."""
    def generer(self, rng: random.Random, doc_level: str, type_demande: str,
                id_: str) -> SyntheticProfile:
        raise NotImplementedError


# ── ENFANTS ──────────────────────────────────────────────────────────────────

class _TplEnfantTSALeger(_Template):
    famille = "enfant_tsa_leger"
    profil_mdph = "enfant"
    profil_handicap = "tsa"

    def generer(self, rng, doc, td, id_):
        genre = rng.choice(["h", "h", "h", "f"])  # TSA plus freq garçons
        nom, prenom = _nom_prenom(rng, genre)
        age = rng.randint(5, 16)
        aesh_h = rng.choice([8, 12, 15, 20])
        amen = rng.choice(["tiers-temps accordé", "tiers-temps + AESH", "AESH seule"])
        niveau = rng.choice(["CP", "CE1", "CE2", "CM1", "CM2", "6ème", "5ème", "4ème", "lycée"])
        has_sessad = rng.random() < 0.4
        parent_reduit = rng.random() < 0.5
        droits = ["AEEH"]
        if has_sessad: droits.append("SESSAD")

        impact_base = f"crises 2-3x/semaine lors changements de routine, hypersensibilité sensorielle au bruit"
        impact_extras = ["s'isole en récréation", "difficultés socialisation", f"AESH {aesh_h}h/semaine indispensable"]

        if doc == "pauvre":
            impact = _impact_pauvre(impact_base)
            notes = ""
        elif doc == "moyen":
            impact = impact_base
            notes = f"TSA niveau 1. AESH {aesh_h}h. {amen}."
        else:
            impact = _impact_riche(impact_base, impact_extras)
            notes = f"Bilan TSA : niveau 1. AESH individuelle {aesh_h}h/semaine. {amen}. Crises hebdomadaires documentées."

        donnees = {
            "nom_prenom": f"{nom} {prenom}",
            "date_naissance": _date_naissance(rng, age),
            "genre": "garçon" if genre == "h" else "fille",
            "diagnostics": f"TSA niveau 1{'+ dyspraxie' if rng.random() < 0.3 else ''}",
            "traitements": "suivi psychomoteur hebdomadaire" if doc != "pauvre" else "",
            "impact_quotidien": impact,
            "situation_scolaire": f"{niveau} avec AESH {aesh_h}h/semaine, {amen}",
            "droits_demandes": " ".join(droits),
            "type_dossier": td,
            "representant_legal_nom": f"{rng.choice(_NOMS)} {rng.choice(_PRENOMS_F)}",
            "representant_legal_lien": rng.choice(["mère", "père"]),
            "notes_pro": notes,
            "departement": rng.choice(_DEPARTEMENTS),
            "num_secu": _num_secu_adulte(rng, "h", 2026 - age),
            "adresse_complete": _adresse_adulte(rng),
        }
        if parent_reduit:
            donnees["aidant_besoins"] = "réduction activité professionnelle mi-temps pour accompagnement"

        droits_oublies = ["AVPF"] if parent_reduit and "AVPF" not in droits else []
        if not has_sessad: droits_oublies.append("SESSAD")

        cases = {"Case à cocher P17 1": "/Yes"}  # AEEH
        if has_sessad: cases["Case à cocher P10 5"] = "/Yes"

        return SyntheticProfile(
            id=id_, famille=self.famille, profil_mdph=self.profil_mdph,
            profil_handicap=self.profil_handicap, donnees=donnees,
            niveau_documentation=doc, type_demande=td,
            droits_attendus=droits, droits_non_attendus=["AAH", "RQTH", "ESAT", "MAS"],
            droits_oublies=droits_oublies, cases_cerfa_attendues=cases,
        )


class _TplEnfantTSASevere(_Template):
    famille = "enfant_tsa_severe"
    profil_mdph = "enfant"
    profil_handicap = "tsa"

    def generer(self, rng, doc, td, id_):
        genre = rng.choice(["h", "h", "h", "f"])
        nom, prenom = _nom_prenom(rng, genre)
        age = rng.randint(4, 18)
        droits = ["AEEH", "SESSAD"]
        if rng.random() < 0.4: droits.append("PCH")
        parent_reduit = rng.random() < 0.7

        impact_base = "pas de langage verbal, crises d'agitation quotidiennes, dépendance totale pour soins"
        notes = "TSA niveau 3. Communication pictogrammes. Accompagnement AESH individuel 24h/24 en école spécialisée." if doc == "riche" else ""

        donnees = {
            "nom_prenom": f"{nom} {prenom}",
            "date_naissance": _date_naissance(rng, age),
            "genre": "garçon" if genre == "h" else "fille",
            "diagnostics": "TSA niveau 2-3, déficience intellectuelle associée",
            "impact_quotidien": impact_base if doc != "pauvre" else "autisme sévère",
            "situation_scolaire": "IME ou ULIS spécialisée TSA" if rng.random() < 0.5 else "SESSAD + école ordinaire",
            "droits_demandes": " ".join(droits),
            "type_dossier": td,
            "representant_legal_nom": f"{rng.choice(_NOMS)} {rng.choice(_PRENOMS_F)}",
            "representant_legal_lien": "mère",
            "notes_pro": notes,
            "departement": rng.choice(_DEPARTEMENTS),
            "num_secu": _num_secu_adulte(rng, "h", 2026 - age),
            "adresse_complete": _adresse_adulte(rng),
        }
        if parent_reduit:
            donnees["aidant_besoins"] = "cessation activité professionnelle, épuisement total"

        droits_oublies = []
        if "PCH" not in droits: droits_oublies.append("PCH")
        if parent_reduit: droits_oublies.append("AVPF")

        cases = {"Case à cocher P17 1": "/Yes"}
        return SyntheticProfile(
            id=id_, famille=self.famille, profil_mdph=self.profil_mdph,
            profil_handicap=self.profil_handicap, donnees=donnees,
            niveau_documentation=doc, type_demande=td,
            droits_attendus=droits, droits_non_attendus=["AAH", "RQTH"],
            droits_oublies=droits_oublies, cases_cerfa_attendues=cases,
        )


class _TplEnfantTDAH(_Template):
    famille = "enfant_tdah"
    profil_mdph = "enfant"
    profil_handicap = "di"  # TND classé DI en attendant TDAH specifique

    def generer(self, rng, doc, td, id_):
        nom, prenom = _nom_prenom(rng, rng.choice(["h", "h", "f"]))
        age = rng.randint(6, 17)
        niveau = rng.choice(["CM1", "CM2", "6ème", "5ème", "4ème"])
        has_ritaline = rng.random() < 0.6
        droits = ["AEEH"] if rng.random() < 0.7 else []

        donnees = {
            "nom_prenom": f"{nom} {prenom}",
            "date_naissance": _date_naissance(rng, age),
            "genre": "garçon",
            "diagnostics": f"TDAH combiné sévère{', dyslexie' if rng.random() < 0.5 else ''}",
            "traitements": "Ritaline, orthophonie" if has_ritaline else "orthophonie",
            "impact_quotidien": "difficultés importantes en classe, devoirs problématiques, tiers-temps accordé",
            "situation_scolaire": f"{niveau}, tiers-temps accordé{', AESH' if rng.random() < 0.5 else ''}",
            "droits_demandes": " ".join(droits) if droits else "aménagements",
            "type_dossier": td,
            "notes_pro": f"TDAH diagnostiqué. Tiers-temps confirmé. {'Tablette recommandée.' if doc == 'riche' else ''}",
        }

        droits_oublies = ["AEEH"] if not droits else []
        cases = {}
        if droits: cases["Case à cocher P17 1"] = "/Yes"

        return SyntheticProfile(
            id=id_, famille=self.famille, profil_mdph=self.profil_mdph,
            profil_handicap=self.profil_handicap, donnees=donnees,
            niveau_documentation=doc, type_demande=td,
            droits_attendus=droits or ["AEEH"], droits_non_attendus=["AAH", "ESAT"],
            droits_oublies=droits_oublies, cases_cerfa_attendues=cases,
        )


class _TplEnfantDI(_Template):
    famille = "enfant_di"
    profil_mdph = "enfant"
    profil_handicap = "di"

    def generer(self, rng, doc, td, id_):
        nom, prenom = _nom_prenom(rng)
        age = rng.randint(5, 18)
        severite = rng.choice(["légère", "modérée"])
        droits = ["AEEH", "IME" if severite == "modérée" else "SESSAD"]

        donnees = {
            "nom_prenom": f"{nom} {prenom}",
            "date_naissance": _date_naissance(rng, age),
            "genre": rng.choice(["garçon", "fille"]),
            "diagnostics": f"déficience intellectuelle {severite}",
            "impact_quotidien": "difficultés apprentissages, besoin encadrement permanent, communication simple",
            "situation_scolaire": "ULIS" if severite == "légère" else "IME ou classe spécialisée",
            "droits_demandes": " ".join(droits),
            "type_dossier": td,
        }
        return SyntheticProfile(
            id=id_, famille=self.famille, profil_mdph=self.profil_mdph,
            profil_handicap=self.profil_handicap, donnees=donnees,
            niveau_documentation=doc, type_demande=td,
            droits_attendus=droits, droits_non_attendus=["AAH", "RQTH"],
            droits_oublies=[], cases_cerfa_attendues={"Case à cocher P17 1": "/Yes"},
        )


class _TplEnfantPolyhandicap(_Template):
    famille = "enfant_polyhandicap"
    profil_mdph = "enfant"
    profil_handicap = "moteur"

    def generer(self, rng, doc, td, id_):
        nom, prenom = _nom_prenom(rng)
        age = rng.randint(3, 20)
        droits = ["AEEH", "EEAP", "PCH"]
        parent_arrete = rng.random() < 0.8

        donnees = {
            "nom_prenom": f"{nom} {prenom}",
            "date_naissance": _date_naissance(rng, age),
            "genre": rng.choice(["garçon", "fille"]),
            "diagnostics": "polyhandicap sévère, paralysie cérébrale, épilepsie réfractaire",
            "impact_quotidien": "dépendance totale pour tous les actes de la vie, fauteuil roulant, gastrostomie",
            "situation_scolaire": "EEAP ou école à domicile",
            "droits_demandes": " ".join(droits),
            "type_dossier": td,
            "notes_pro": "Polyhandicap sévère. PCH accordée. EEAP." if doc == "riche" else "",
        }
        if parent_arrete:
            donnees["aidant_besoins"] = "cessation complète activité professionnelle"

        droits_oublies = ["AVPF"] if parent_arrete else []
        return SyntheticProfile(
            id=id_, famille=self.famille, profil_mdph=self.profil_mdph,
            profil_handicap=self.profil_handicap, donnees=donnees,
            niveau_documentation=doc, type_demande=td,
            droits_attendus=droits, droits_non_attendus=["AAH", "RQTH", "ESAT"],
            droits_oublies=droits_oublies,
            cases_cerfa_attendues={"Case à cocher P17 1": "/Yes", "Case à cocher P17 2": "/Yes"},
        )


# ── ADULTES MOTEUR ────────────────────────────────────────────────────────────

class _TplAdulteAT(_Template):
    famille = "adulte_at"
    profil_mdph = "adulte"
    profil_handicap = "moteur"

    def generer(self, rng, doc, td, id_):
        genre = rng.choice(["h", "h", "f"])
        nom, prenom = _nom_prenom(rng, genre)
        age = rng.randint(30, 58)
        annee_at = 2026 - rng.randint(1, 7)
        droits = ["RQTH", "AAH"]
        if rng.random() < 0.6: droits.append("ESPO")
        ask_pch = rng.random() < 0.3
        if ask_pch: droits.append("PCH")

        impact_base = f"accident du travail {annee_at}, marche limitée, douleurs chroniques dorsales"
        impact_extras = ["ne peut plus rester debout plus de 10 minutes", "aide pour toilette certains matins", "insomnies"]

        donnees = {
            "nom_prenom": f"{nom} {prenom}",
            "date_naissance": _date_naissance(rng, age),
            "genre": "homme" if genre == "h" else "femme",
            "diagnostics": "douleurs chroniques dorsales, séquelles AT, anxiété",
            "traitements": "antalgiques, kinésithérapie, suivi psychologique",
            "impact_quotidien": _impact_riche(impact_base, impact_extras) if doc == "riche" else impact_base,
            "statut_emploi": f"sans emploi depuis {annee_at}, arrêt longue durée, ancien poste industrie",
            "droits_demandes": " ".join(droits),
            "type_dossier": td,
            "restrictions_emploi": "pas port charges, pas station debout prolongée, pas milieu bruyant" if doc != "pauvre" else "",
            "notes_pro": f"AT {annee_at}. Rente AT en cours. ESPO recommandé." if doc == "riche" else "",
            "departement": rng.choice(_DEPARTEMENTS),
            "num_secu": _num_secu_adulte(rng, "h", 2026 - age),
            "adresse_complete": _adresse_adulte(rng),
        }

        droits_oublies = []
        if not ask_pch: droits_oublies.append("PCH")
        droits_oublies.append("CMI_STATIONNEMENT")  # presque toujours oublié

        cases = {
            "Case à cocher P17 6": "/Yes",  # RQTH
            "Case à cocher P17 5": "/Yes",  # AAH
        }
        return SyntheticProfile(
            id=id_, famille=self.famille, profil_mdph=self.profil_mdph,
            profil_handicap=self.profil_handicap, donnees=donnees,
            niveau_documentation=doc, type_demande=td,
            droits_attendus=droits, droits_non_attendus=["AEEH", "IME", "MAS"],
            droits_oublies=droits_oublies, cases_cerfa_attendues=cases,
        )


class _TplAdulteSEP(_Template):
    famille = "adulte_sep"
    profil_mdph = "adulte"
    profil_handicap = "moteur"

    def generer(self, rng, doc, td, id_):
        genre = rng.choice(["f", "f", "h"])
        nom, prenom = _nom_prenom(rng, genre)
        age = rng.randint(28, 55)
        droits = ["RQTH", "AAH"]
        ask_pch = rng.random() < 0.4
        if ask_pch: droits.append("PCH")

        donnees = {
            "nom_prenom": f"{nom} {prenom}",
            "date_naissance": _date_naissance(rng, age),
            "genre": "femme" if genre == "f" else "homme",
            "diagnostics": "sclérose en plaques secondaire progressive, fatigue chronique neurologique",
            "traitements": "Ocrevus, kinésithérapie 2x/semaine",
            "impact_quotidien": "marche limitée à 100 mètres avec canne, fauteuil extérieur, aide douche",
            "statut_emploi": "arrêt longue durée depuis 3 ans, ancienne infirmière",
            "droits_demandes": " ".join(droits),
            "type_dossier": td,
            "notes_pro": "SEP progressive. Marche 100m. Fauteuil. Aide douche obligatoire." if doc == "riche" else "",
            "departement": rng.choice(_DEPARTEMENTS),
            "num_secu": _num_secu_adulte(rng, "h", 2026 - age),
            "adresse_complete": _adresse_adulte(rng),
        }

        droits_oublies = []
        if not ask_pch: droits_oublies.append("PCH")
        droits_oublies.append("CMI_STATIONNEMENT")

        return SyntheticProfile(
            id=id_, famille=self.famille, profil_mdph=self.profil_mdph,
            profil_handicap=self.profil_handicap, donnees=donnees,
            niveau_documentation=doc, type_demande=td,
            droits_attendus=droits, droits_non_attendus=["AEEH", "IME", "ESAT"],
            droits_oublies=droits_oublies,
            cases_cerfa_attendues={"Case à cocher P17 6": "/Yes", "Case à cocher P17 5": "/Yes"},
        )


class _TplAdulteAVC(_Template):
    famille = "adulte_avc"
    profil_mdph = "adulte"
    profil_handicap = "moteur"

    def generer(self, rng, doc, td, id_):
        nom, prenom = _nom_prenom(rng, rng.choice(["h", "h", "f"]))
        age = rng.randint(40, 65)
        annee_avc = 2026 - rng.randint(1, 5)
        droits = ["RQTH", "AAH", "UEROS"] if rng.random() < 0.4 else ["RQTH", "AAH"]

        donnees = {
            "nom_prenom": f"{nom} {prenom}",
            "date_naissance": _date_naissance(rng, age),
            "genre": rng.choice(["homme", "femme"]),
            "diagnostics": f"AVC ischémique {annee_avc}, séquelles hémiplégie droite, aphasie partielle",
            "impact_quotidien": "hémiparésie droite, difficultés d'élocution, fatigue cognitive importante, aide pour certains actes",
            "statut_emploi": f"sans emploi depuis {annee_avc}, arrêt longue durée, séquelles AVC",
            "droits_demandes": " ".join(droits),
            "type_dossier": td,
        }
        return SyntheticProfile(
            id=id_, famille=self.famille, profil_mdph=self.profil_mdph,
            profil_handicap=self.profil_handicap, donnees=donnees,
            niveau_documentation=doc, type_demande=td,
            droits_attendus=droits, droits_non_attendus=["AEEH", "IME"],
            droits_oublies=["PCH", "UEROS"] if "UEROS" not in droits else ["PCH"],
            cases_cerfa_attendues={"Case à cocher P17 5": "/Yes"},
        )


class _TplAdulteParkinson(_Template):
    famille = "adulte_parkinson"
    profil_mdph = "adulte"
    profil_handicap = "moteur"

    def generer(self, rng, doc, td, id_):
        nom, prenom = _nom_prenom(rng)
        age = rng.randint(55, 72)
        droits = ["AAH", "PCH"] if rng.random() < 0.5 else ["AAH"]

        donnees = {
            "nom_prenom": f"{nom} {prenom}",
            "date_naissance": _date_naissance(rng, age),
            "genre": rng.choice(["homme", "femme"]),
            "diagnostics": "maladie de Parkinson, tremblements, rigidité, troubles posturaux",
            "impact_quotidien": "tremblements limitant les gestes fins, chutes fréquentes, aide pour habillage et repas",
            "statut_emploi": "retraite anticipée, arrêt travail pour maladie",
            "droits_demandes": " ".join(droits),
            "type_dossier": td,
        }
        return SyntheticProfile(
            id=id_, famille=self.famille, profil_mdph=self.profil_mdph,
            profil_handicap=self.profil_handicap, donnees=donnees,
            niveau_documentation=doc, type_demande=td,
            droits_attendus=droits,
            droits_non_attendus=["AEEH", "RQTH", "ESAT"],
            droits_oublies=["PCH"] if "PCH" not in droits else [],
            cases_cerfa_attendues={"Case à cocher P17 5": "/Yes"},
        )


# ── ADULTES MALADIE CHRONIQUE ──────────────────────────────────────────────

class _TplAdulteMaladieChronique(_Template):
    famille = "adulte_maladie_chronique"
    profil_mdph = "adulte"
    profil_handicap = "maladie_chronique"

    def generer(self, rng, doc, td, id_):
        genre = rng.choice(["f", "f", "h"])
        nom, prenom = _nom_prenom(rng, genre)
        age = rng.randint(30, 58)
        maladie = rng.choice(["fibromyalgie sévère", "syndrome de fatigue chronique", "lupus", "maladie de Crohn", "polyarthrite rhumatoïde"])
        droits = ["RQTH"] if rng.random() < 0.6 else []
        if rng.random() < 0.4: droits.append("AAH")

        donnees = {
            "nom_prenom": f"{nom} {prenom}",
            "date_naissance": _date_naissance(rng, age),
            "genre": "femme" if genre == "f" else "homme",
            "diagnostics": maladie,
            "traitements": "antalgiques, suivi rhumatologue, kinésithérapie mensuelle",
            "impact_quotidien": "fatigue intense variable, mauvaises journées fréquentes, travail impossible",
            "statut_emploi": f"arrêt longue durée {rng.randint(1,4)} ans, {rng.choice(['assistante', 'employé', 'cadre', 'infirmière'])}",
            "droits_demandes": " ".join(droits) if droits else "RQTH",
            "type_dossier": td,
        }

        droits_oublies = ["AAH"] if "AAH" not in droits else []
        droits_oublies.append("CMI_PRIORITE")  # souvent oublié en maladie chronique
        return SyntheticProfile(
            id=id_, famille=self.famille, profil_mdph=self.profil_mdph,
            profil_handicap=self.profil_handicap, donnees=donnees,
            niveau_documentation=doc, type_demande=td,
            droits_attendus=droits or ["RQTH"],
            droits_non_attendus=["AEEH", "IME", "ESAT", "MAS"],
            droits_oublies=droits_oublies,
            cases_cerfa_attendues={"Case à cocher P17 6": "/Yes"},
        )


class _TplAdulteCancer(_Template):
    famille = "adulte_cancer"
    profil_mdph = "adulte"
    profil_handicap = "maladie_chronique"

    def generer(self, rng, doc, td, id_):
        nom, prenom = _nom_prenom(rng)
        age = rng.randint(35, 65)
        droits = ["RQTH", "AAH"] if rng.random() < 0.5 else ["RQTH"]

        donnees = {
            "nom_prenom": f"{nom} {prenom}",
            "date_naissance": _date_naissance(rng, age),
            "genre": rng.choice(["homme", "femme"]),
            "diagnostics": f"cancer {'sein' if rng.random() < 0.5 else 'poumon'} traité, séquelles chimiothérapie",
            "impact_quotidien": "fatigue chronique post-chimio, neuropathies périphériques, impossibilité travail temps plein",
            "statut_emploi": "arrêt maladie ALD, ancienne situation emploi",
            "droits_demandes": " ".join(droits),
            "type_dossier": td,
        }
        return SyntheticProfile(
            id=id_, famille=self.famille, profil_mdph=self.profil_mdph,
            profil_handicap=self.profil_handicap, donnees=donnees,
            niveau_documentation=doc, type_demande=td,
            droits_attendus=droits,
            droits_non_attendus=["AEEH", "IME", "ESAT"],
            droits_oublies=["AAH"] if "AAH" not in droits else [],
            cases_cerfa_attendues={"Case à cocher P17 6": "/Yes"},
        )


# ── ADULTES PSYCHIQUES ───────────────────────────────────────────────────────

class _TplAdulteBipolaire(_Template):
    famille = "adulte_bipolaire"
    profil_mdph = "adulte"
    profil_handicap = "psychique"

    def generer(self, rng, doc, td, id_):
        genre = rng.choice(["f", "h"])
        nom, prenom = _nom_prenom(rng, genre)
        age = rng.randint(25, 55)
        droits = ["RQTH", "AAH"]
        has_savs = rng.random() < 0.3
        if has_savs: droits.append("SAVS")

        donnees = {
            "nom_prenom": f"{nom} {prenom}",
            "date_naissance": _date_naissance(rng, age),
            "genre": "femme" if genre == "f" else "homme",
            "diagnostics": f"trouble bipolaire type {rng.choice(['1', '2'])}, épisodes maniaques et dépressifs",
            "traitements": "Lithium, antipsychotique, suivi psychiatrique mensuel",
            "impact_quotidien": "alternance jours stables et mauvaises périodes, emploi précaire, isolement",
            "statut_emploi": f"{'licencié pour inaptitude' if rng.random() < 0.5 else 'arrêt longue durée'}, CDD instables",
            "droits_demandes": " ".join(droits),
            "type_dossier": td,
            "notes_pro": f"Trouble bipolaire. {rng.randint(1,4)} hospitalisations. Arrêt longue durée." if doc == "riche" else "",
        }

        droits_oublies = ["SAVS"] if not has_savs else []
        return SyntheticProfile(
            id=id_, famille=self.famille, profil_mdph=self.profil_mdph,
            profil_handicap=self.profil_handicap, donnees=donnees,
            niveau_documentation=doc, type_demande=td,
            droits_attendus=droits,
            droits_non_attendus=["AEEH", "IME", "MAS", "ESAT"],
            droits_oublies=droits_oublies,
            cases_cerfa_attendues={"Case à cocher P17 5": "/Yes", "Case à cocher P17 6": "/Yes"},
        )


class _TplAdulteSchizophrenie(_Template):
    famille = "adulte_schizophrenie"
    profil_mdph = "adulte"
    profil_handicap = "psychique"

    def generer(self, rng, doc, td, id_):
        nom, prenom = _nom_prenom(rng, rng.choice(["h", "h", "f"]))
        age = rng.randint(22, 55)
        has_esat = rng.random() < 0.5
        droits = ["AAH"]
        if has_esat: droits.append("ESAT")

        donnees = {
            "nom_prenom": f"{nom} {prenom}",
            "date_naissance": _date_naissance(rng, age),
            "genre": rng.choice(["homme", "femme"]),
            "diagnostics": "schizophrénie paranoïde stabilisée, suivi ambulatoire",
            "traitements": "antipsychotiques dépôt, suivi CMP mensuel",
            "impact_quotidien": "activité ESAT depuis 3 ans, vie à domicile avec SAVS, maintien fragile",
            "statut_emploi": "ESAT" if has_esat else "sans activité, suivi CMP",
            "droits_demandes": " ".join(droits),
            "type_dossier": td,
        }

        droits_oublies = ["SAVS"] if rng.random() < 0.5 else []
        if has_esat: droits_oublies.append("FOYER_HEBERGEMENT")

        cases = {"Case à cocher P17 5": "/Yes"}
        if has_esat: cases["Case à cocher P17 11"] = "/Yes"

        return SyntheticProfile(
            id=id_, famille=self.famille, profil_mdph=self.profil_mdph,
            profil_handicap=self.profil_handicap, donnees=donnees,
            niveau_documentation=doc, type_demande=td,
            droits_attendus=droits,
            droits_non_attendus=["AEEH", "RQTH", "MAS"],
            droits_oublies=droits_oublies,
            cases_cerfa_attendues=cases,
        )


class _TplAdulteDepression(_Template):
    famille = "adulte_depression"
    profil_mdph = "adulte"
    profil_handicap = "psychique"

    def generer(self, rng, doc, td, id_):
        nom, prenom = _nom_prenom(rng)
        age = rng.randint(25, 58)
        droits = ["RQTH"] if rng.random() < 0.6 else ["RQTH", "AAH"]

        donnees = {
            "nom_prenom": f"{nom} {prenom}",
            "date_naissance": _date_naissance(rng, age),
            "genre": rng.choice(["homme", "femme"]),
            "diagnostics": "dépression sévère résistante, épisodes récurrents",
            "traitements": "antidépresseurs, psychothérapie hebdomadaire, suivi psychiatrique",
            "impact_quotidien": "impossibilité de travailler les jours difficiles, isolement, fatigue psychique",
            "statut_emploi": "arrêt longue durée, licencié pour inaptitude",
            "droits_demandes": " ".join(droits),
            "type_dossier": td,
        }
        return SyntheticProfile(
            id=id_, famille=self.famille, profil_mdph=self.profil_mdph,
            profil_handicap=self.profil_handicap, donnees=donnees,
            niveau_documentation=doc, type_demande=td,
            droits_attendus=droits,
            droits_non_attendus=["AEEH", "ESAT", "IME"],
            droits_oublies=["AAH"] if "AAH" not in droits else [],
            cases_cerfa_attendues={"Case à cocher P17 6": "/Yes"},
        )


# ── ADULTES TND ──────────────────────────────────────────────────────────────

class _TplAdulteTSA(_Template):
    famille = "adulte_tsa"
    profil_mdph = "adulte"
    profil_handicap = "tsa"

    def generer(self, rng, doc, td, id_):
        nom, prenom = _nom_prenom(rng, rng.choice(["h", "h", "f"]))
        age = rng.randint(18, 45)
        diagnostic_age = rng.randint(18, age) if rng.random() < 0.5 else rng.randint(5, 17)
        droits = ["RQTH"]
        if rng.random() < 0.3: droits.append("AAH")
        if rng.random() < 0.3: droits.append("ESPO")

        donnees = {
            "nom_prenom": f"{nom} {prenom}",
            "date_naissance": _date_naissance(rng, age),
            "genre": rng.choice(["homme", "femme"]),
            "diagnostics": f"TSA niveau 1, diagnostiqué à {diagnostic_age} ans",
            "impact_quotidien": "difficultés entretiens emploi, surcharge sensorielle open space, burn-out autistique",
            "statut_emploi": "sans emploi depuis 18 mois, difficultés répétées en emploi",
            "droits_demandes": " ".join(droits),
            "type_dossier": td,
        }
        return SyntheticProfile(
            id=id_, famille=self.famille, profil_mdph=self.profil_mdph,
            profil_handicap=self.profil_handicap, donnees=donnees,
            niveau_documentation=doc, type_demande=td,
            droits_attendus=droits,
            droits_non_attendus=["AEEH", "IME", "MAS"],
            droits_oublies=["EMPLOI_ACCOMPAGNE", "SAVS"] if len(droits) <= 1 else [],
            cases_cerfa_attendues={"Case à cocher P17 6": "/Yes"},
        )


class _TplAdulteTDAH(_Template):
    famille = "adulte_tdah"
    profil_mdph = "adulte"
    profil_handicap = "tsa"  # TND

    def generer(self, rng, doc, td, id_):
        nom, prenom = _nom_prenom(rng)
        age = rng.randint(18, 50)
        droits = ["RQTH"] if rng.random() < 0.7 else []

        donnees = {
            "nom_prenom": f"{nom} {prenom}",
            "date_naissance": _date_naissance(rng, age),
            "genre": rng.choice(["homme", "femme"]),
            "diagnostics": "TDAH adulte diagnostiqué tardivement, désorganisation sévère",
            "impact_quotidien": "impossible de tenir un poste standard, burn-out répété, difficultés organisation",
            "statut_emploi": "sans emploi, CDD multiples échoués",
            "droits_demandes": " ".join(droits) if droits else "RQTH",
            "type_dossier": td,
        }
        return SyntheticProfile(
            id=id_, famille=self.famille, profil_mdph=self.profil_mdph,
            profil_handicap=self.profil_handicap, donnees=donnees,
            niveau_documentation=doc, type_demande=td,
            droits_attendus=droits or ["RQTH"],
            droits_non_attendus=["AEEH", "MAS", "ESAT"],
            droits_oublies=["RQTH"] if not droits else ["ESPO"],
            cases_cerfa_attendues={"Case à cocher P17 6": "/Yes"},
        )


# ── ADULTES DI ───────────────────────────────────────────────────────────────

class _TplAdulteDI(_Template):
    famille = "adulte_di"
    profil_mdph = "adulte"
    profil_handicap = "di"

    def generer(self, rng, doc, td, id_):
        nom, prenom = _nom_prenom(rng)
        age = rng.randint(18, 55)
        severite = rng.choice(["légère", "modérée"])
        has_esat = rng.random() < 0.6
        droits = ["AAH"]
        if has_esat: droits.append("ESAT")

        donnees = {
            "nom_prenom": f"{nom} {prenom}",
            "date_naissance": _date_naissance(rng, age),
            "genre": rng.choice(["homme", "femme"]),
            "diagnostics": f"déficience intellectuelle {severite}",
            "impact_quotidien": "autonomie partielle, ESAT depuis 5 ans, tutelle" if has_esat else "vie à domicile avec aide",
            "statut_emploi": "ESAT" if has_esat else "sans activité",
            "droits_demandes": " ".join(droits),
            "type_dossier": td,
        }

        droits_oublies = ["FOYER_VIE"] if rng.random() < 0.6 else []
        cases = {"Case à cocher P17 5": "/Yes"}
        if has_esat: cases["Case à cocher P18 4"] = "/Yes"

        return SyntheticProfile(
            id=id_, famille=self.famille, profil_mdph=self.profil_mdph,
            profil_handicap=self.profil_handicap, donnees=donnees,
            niveau_documentation=doc, type_demande=td,
            droits_attendus=droits,
            droits_non_attendus=["AEEH", "RQTH"],
            droits_oublies=droits_oublies,
            cases_cerfa_attendues=cases,
        )


# ── PROTECTION JURIDIQUE ─────────────────────────────────────────────────────

class _TplTutelle(_Template):
    famille = "protection_tutelle"
    profil_mdph = "protege"
    profil_handicap = "di"

    def generer(self, rng, doc, td, id_):
        nom, prenom = _nom_prenom(rng)
        age = rng.randint(20, 60)
        droits = ["AAH"]
        if rng.random() < 0.5: droits.append("ESAT")

        donnees = {
            "nom_prenom": f"{nom} {prenom}",
            "date_naissance": _date_naissance(rng, age),
            "genre": rng.choice(["homme", "femme"]),
            "diagnostics": "déficience intellectuelle modérée",
            "impact_quotidien": "autonomie limitée, ESAT, gestion administrative impossible",
            "statut_emploi": "ESAT" if "ESAT" in droits else "domicile familial",
            "type_protection": "tutelle",
            "jugement_tribunal": f"Tribunal Judiciaire {rng.choice(['Lyon', 'Marseille', 'Paris', 'Bordeaux'])} 20{rng.randint(18,24)}",
            "representant_legal_nom": f"{rng.choice(_NOMS)} {rng.choice(_PRENOMS_F)}",
            "droits_demandes": " ".join(droits),
            "type_dossier": td,
        }
        return SyntheticProfile(
            id=id_, famille=self.famille, profil_mdph=self.profil_mdph,
            profil_handicap=self.profil_handicap, donnees=donnees,
            niveau_documentation=doc, type_demande=td,
            droits_attendus=droits,
            droits_non_attendus=["RQTH", "AEEH"],
            droits_oublies=["FOYER_VIE"] if "ESAT" not in droits else ["FOYER_HEBERGEMENT"],
            cases_cerfa_attendues={"Case à cocher P17 5": "/Yes", "REPRESENTANT LEGAL 1": "tutelle"},
        )


class _TplHabilitation(_Template):
    famille = "protection_habilitation"
    profil_mdph = "protege"
    profil_handicap = "di"

    def generer(self, rng, doc, td, id_):
        nom, prenom = _nom_prenom(rng)
        age = rng.randint(20, 50)
        donnees = {
            "nom_prenom": f"{nom} {prenom}",
            "date_naissance": _date_naissance(rng, age),
            "genre": rng.choice(["homme", "femme"]),
            "diagnostics": "déficience intellectuelle légère, trisomie 21",
            "impact_quotidien": "vie en logement accompagné, SAVS, activités ESAT",
            "statut_emploi": "ESAT",
            "type_protection": "habilitation familiale",
            "jugement_tribunal": f"TJ {rng.choice(['Paris', 'Lyon', 'Nantes'])} 202{rng.randint(0,5)}",
            "representant_legal_nom": f"{rng.choice(_NOMS)} {rng.choice(_PRENOMS_F)}",
            "droits_demandes": "AAH ESAT",
            "type_dossier": td,
        }
        return SyntheticProfile(
            id=id_, famille=self.famille, profil_mdph=self.profil_mdph,
            profil_handicap=self.profil_handicap, donnees=donnees,
            niveau_documentation=doc, type_demande=td,
            droits_attendus=["AAH", "ESAT"],
            droits_non_attendus=["RQTH", "AEEH"],
            droits_oublies=["SAVS"],
            cases_cerfa_attendues={"Case à cocher P17 5": "/Yes"},
        )


# ── AIDANTS ──────────────────────────────────────────────────────────────────

class _TplAidantParent(_Template):
    famille = "aidant_parent"
    profil_mdph = "enfant"
    profil_handicap = "tsa"

    def generer(self, rng, doc, td, id_):
        nom, prenom = _nom_prenom(rng)
        age_enfant = rng.randint(5, 15)
        has_reduction = rng.random() < 0.7
        droits = ["AEEH"]
        if rng.random() < 0.5: droits.append("SESSAD")

        donnees = {
            "nom_prenom": f"{nom} {prenom}",
            "date_naissance": _date_naissance(rng, age_enfant),
            "genre": rng.choice(["garçon", "fille"]),
            "diagnostics": rng.choice(["TSA niveau 1", "TDAH + DYS", "DI légère", "TSA niveau 2"]),
            "situation_scolaire": f"classe ordinaire, AESH {rng.choice([8,12,15])}h",
            "droits_demandes": " ".join(droits),
            "representant_legal_nom": f"{rng.choice(_NOMS)} {rng.choice(_PRENOMS_F)}",
            "representant_legal_lien": "mère",
            "type_dossier": td,
            "aidant_nom": f"{rng.choice(_NOMS)} {rng.choice(_PRENOMS_F)}",
            "aidant_besoins": "réduction activité professionnelle mi-temps, épuisement" if has_reduction else "accompagnement quotidien intense",
        }

        droits_oublies = ["AVPF"] if has_reduction else []
        return SyntheticProfile(
            id=id_, famille=self.famille, profil_mdph=self.profil_mdph,
            profil_handicap=self.profil_handicap, donnees=donnees,
            niveau_documentation=doc, type_demande=td,
            droits_attendus=droits,
            droits_non_attendus=["AAH", "RQTH", "ESAT"],
            droits_oublies=droits_oublies,
            cases_cerfa_attendues={"Case à cocher P17 1": "/Yes"},
        )


class _TplAidantConjoint(_Template):
    famille = "aidant_conjoint"
    profil_mdph = "adulte"
    profil_handicap = "moteur"

    def generer(self, rng, doc, td, id_):
        nom, prenom = _nom_prenom(rng)
        age = rng.randint(40, 70)
        donnees = {
            "nom_prenom": f"{nom} {prenom}",
            "date_naissance": _date_naissance(rng, age),
            "genre": rng.choice(["homme", "femme"]),
            "diagnostics": rng.choice(["SEP progressive", "maladie de Parkinson", "AVC séquelles", "myopathie"]),
            "impact_quotidien": "dépendance totale pour déplacements et soins, fauteuil roulant",
            "statut_emploi": "invalide, arrêt longue durée",
            "droits_demandes": "AAH PCH",
            "mode_vie": "en couple",
            "aidant_nom": f"{rng.choice(_NOMS)} {rng.choice(_PRENOMS_H + _PRENOMS_F)}",
            "aidant_besoins": "aidant principal à domicile, a réduit son activité professionnelle",
            "type_dossier": td,
        }
        return SyntheticProfile(
            id=id_, famille=self.famille, profil_mdph=self.profil_mdph,
            profil_handicap=self.profil_handicap, donnees=donnees,
            niveau_documentation=doc, type_demande=td,
            droits_attendus=["AAH", "PCH"],
            droits_non_attendus=["AEEH", "IME"],
            droits_oublies=["CMI_STATIONNEMENT"],
            cases_cerfa_attendues={"Case à cocher P17 5": "/Yes", "Case à cocher P17 7": "/Yes"},
        )


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRE DES TEMPLATES
# ─────────────────────────────────────────────────────────────────────────────

_ALL_TEMPLATES: list[_Template] = [
    _TplEnfantTSALeger(),
    _TplEnfantTSASevere(),
    _TplEnfantTDAH(),
    _TplEnfantDI(),
    _TplEnfantPolyhandicap(),
    _TplAdulteAT(),
    _TplAdulteSEP(),
    _TplAdulteAVC(),
    _TplAdulteParkinson(),
    _TplAdulteMaladieChronique(),
    _TplAdulteCancer(),
    _TplAdulteBipolaire(),
    _TplAdulteSchizophrenie(),
    _TplAdulteDepression(),
    _TplAdulteTSA(),
    _TplAdulteTDAH(),
    _TplAdulteDI(),
    _TplTutelle(),
    _TplHabilitation(),
    _TplAidantParent(),
    _TplAidantConjoint(),
]

# Poids de tirage (certains profils plus fréquents que d'autres)
_POIDS_TEMPLATES = [
    3,  # TSA léger enfant — très fréquent
    2,  # TSA sévère
    3,  # TDAH enfant
    2,  # DI enfant
    1,  # Polyhandicap enfant
    3,  # AT adulte — très fréquent
    2,  # SEP
    2,  # AVC
    1,  # Parkinson
    3,  # Maladie chronique — très fréquent
    2,  # Cancer
    3,  # Bipolaire — très fréquent
    2,  # Schizophrénie
    2,  # Dépression
    2,  # TSA adulte
    2,  # TDAH adulte
    2,  # DI adulte
    2,  # Tutelle
    1,  # Habilitation
    2,  # Parent aidant
    1,  # Conjoint aidant
]


# ─────────────────────────────────────────────────────────────────────────────
# GÉNÉRATEUR PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def generer_profils(n: int = 100, seed: int = 42) -> list[SyntheticProfile]:
    """
    Génère N profils synthétiques réalistes.

    Args:
        n:    Nombre de profils à générer
        seed: Graine aléatoire pour reproductibilité

    Returns:
        Liste de SyntheticProfile prêts pour les moteurs Facilim
    """
    rng = random.Random(seed)
    profils = []

    for i in range(n):
        # Choisir un template avec pondération
        tpl = rng.choices(_ALL_TEMPLATES, weights=_POIDS_TEMPLATES, k=1)[0]
        doc = _niveau_documentation(rng)
        td  = _type_demande(rng)
        id_ = f"SYN_{i:04d}_{tpl.famille.upper()[:12]}"

        try:
            p = tpl.generer(rng, doc, td, id_)

            # Injection d'un texte E minimal pour tous les profils
            # En production : généré par le LLM. En test QA-6 : placeholder minimal
            # nécessaire pour couvrir le champ N1 "Champ de texte P16 1"
            if not p.donnees.get("texte_e_projet_vie"):
                droits_str = p.donnees.get("droits_demandes", "") or ""
                p.donnees["texte_e_projet_vie"] = (
                    f"Objectif : obtenir les droits adaptés à la situation ({droits_str}). "
                    f"Maintenir la qualité de vie et l'autonomie selon les possibilités."
                )

            # Enrichissement NSS pour tous les profils (adulte et enfant)
            # En production : collecté via WhatsApp ou interface
            if not p.donnees.get("num_secu"):
                age_est = 40
                dob = p.donnees.get("date_naissance", "")
                if dob and len(dob) >= 8:
                    try:
                        annee = int(dob.split("/")[-1]) if "/" in dob else int(dob[-4:])
                        age_est = 2026 - annee
                    except Exception:
                        pass
                p.donnees["num_secu"] = _num_secu_adulte(rng, "h", age_est)
                p.donnees.setdefault("departement", rng.choice(_DEPARTEMENTS))

            # Enrichissement adresse pour adultes
            if p.profil_mdph in ("adulte", "protege") and not p.donnees.get("num_secu"):
                age_est = 40  # estimation
                dob = p.donnees.get("date_naissance", "")
                if dob and len(dob) >= 8:
                    try:
                        annee = int(dob.split("/")[-1]) if "/" in dob else int(dob[-4:])
                        age_est = 2026 - annee
                    except Exception:
                        pass
                p.donnees.setdefault("num_secu", _num_secu_adulte(rng, "h", age_est))
                p.donnees.setdefault("adresse_complete", _adresse_adulte(rng))
                p.donnees.setdefault("departement", rng.choice(_DEPARTEMENTS))

            profils.append(p)
        except Exception as e:
            # Profil de fallback si erreur
            profils.append(SyntheticProfile(
                id=id_, famille=tpl.famille, profil_mdph=tpl.profil_mdph,
                profil_handicap=tpl.profil_handicap,
                donnees={"diagnostics": "handicap non spécifié", "droits_demandes": "RQTH",
                          "type_dossier": td},
                niveau_documentation=doc, type_demande=td,
                droits_attendus=["RQTH"], droits_non_attendus=[],
                droits_oublies=[], cases_cerfa_attendues={},
            ))

    return profils


def distribution_familles(profils: list[SyntheticProfile]) -> dict[str, int]:
    """Retourne la distribution des familles dans un lot de profils."""
    dist: dict[str, int] = {}
    for p in profils:
        dist[p.famille] = dist.get(p.famille, 0) + 1
    return dict(sorted(dist.items(), key=lambda x: -x[1]))
