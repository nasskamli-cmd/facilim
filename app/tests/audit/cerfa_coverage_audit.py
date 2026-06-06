"""
app/tests/audit/cerfa_coverage_audit.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FACILIM QA-2 — Audit terrain CERFA réel

Mesure la couverture RÉELLE du CERFA 15692*01 par Facilim.
Pas de théorie. Pas d'estimation. Vérité terrain.

Méthode :
  1. Lire les 612 champs AcroForm réels depuis le PDF officiel
  2. Pour chaque profil QA, appeler build_field_map() exactement comme en production
  3. Comparer champ par champ ce que Facilim produit vs ce que le PDF attend
  4. Classifier chaque champ (couvert / non couvert / non applicable)
  5. Calculer les taux réels par section, profil, type

Sorties :
  - couverture_reelle.csv         : inventaire complet 612 lignes
  - qa_vs_reality.md              : comparaison QA théorique vs CERFA réel
  - top_100_champs_critiques.md   : champs critiques manquants
  - rapport_audit_cerfa.txt       : rapport global

Usage :
  python -m app.tests.audit.cerfa_coverage_audit
  python -m app.tests.audit.cerfa_coverage_audit --profil ADULTE_ACCIDENT_TRAVAIL
  python -m app.tests.audit.cerfa_coverage_audit --all --save
"""

from __future__ import annotations

import csv
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ─── Configuration ────────────────────────────────────────────────────────────

PDF_CERFA = Path("storage/templates/cerfa_15692_01.pdf")
OUTPUT_DIR = Path("app/tests/audit/reports")

# ─────────────────────────────────────────────────────────────────────────────
# ÉTAPE 1 — INVENTAIRE PDF COMPLET
# Lecture des 612 champs AcroForm réels
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ChampPDF:
    """Un champ AcroForm du CERFA 15692*01."""
    nom:         str
    page:        int
    type_champ:  str          # "texte" | "case" | "signature"
    type_raw:    str          # "/Tx" | "/Btn" | "/Sig"
    section:     str          # identite | scolaire | emploi | droits | aidant | ...
    criticite:   int          # 1=critique 2=important 3=secondaire
    label_metier: str         # description humaine
    applicable_adulte:  bool
    applicable_enfant:  bool
    applicable_protege: bool


def _detecter_section(nom: str, page: int) -> str:
    """Déduit la section métier depuis le nom du champ et la page."""
    n = nom.lower()
    if page in (1,):             return "garde"
    if page == 2 and any(k in n for k in ["nss","ss enfant","numero ss","autorite","date a","date b","p2"]): return "identite"
    if page == 3:                return "protection_juridique"
    if page == 4:                return "aides_humaines"
    if page == 5:                return "vie_quotidienne_b1"
    if page in (6, 7):           return "besoins_avq"
    if page == 8:                return "texte_libre_b"
    if page in (9, 10, 11, 12): return "scolarite"
    if page == 13:               return "emploi_d1"
    if page == 14:               return "emploi_d2"
    if page == 15:               return "parcours_pro"
    if page == 16:               return "projet_vie"
    if page == 17:               return "droits_e1_e2"
    if page == 18:               return "droits_e3"
    if page == 19:               return "aidant_f"
    if page == 20:               return "aidant_f2"
    return "autre"


def _criticite(nom: str, page: int, type_raw: str) -> int:
    """
    Niveau de criticité métier :
    1 = Critique  — absence peut compromettre recevabilité ou attribution droit
    2 = Important — absence réduit les chances d'obtenir le droit
    3 = Secondaire — information utile mais non bloquante
    """
    n = nom.lower()
    # Champs N°1 critiques : identité, droits demandés, type de dossier
    critique_patterns = [
        "p2 1", "p2 2", "p2 3",          # nom, nom usage, prénom
        "date a",                          # date de naissance
        "p1 1", "p1 2", "p1 3", "p1 a",  # type de dossier
        "p17", "p18",                      # droits demandés
        "numero ss", "ss enfant",          # NIR
        "champ de texte p8 1",            # texte B libre
        "champ de texte p16 1",           # texte E projet de vie
        "representant legal",
        "autorite parent 1  a",
        "autorite parent 1  b",
        "champ de texte p1 1",            # département
        "champ de texte p 1 2",           # N° dossier
    ]
    important_patterns = [
        "p13", "p14",                      # situation emploi
        "p 9", "p 10",                     # scolarité / aménagements
        "p5",                              # mode de vie / ressources
        "p6", "p7",                        # besoins AVQ
        "champ de texte p14 1",           # texte D emploi
        "champ de texte p13",
        "p15",                             # parcours pro
        "p16",                             # projet vie
        "date b",                          # date du représentant
        "autorite parent",
    ]
    for p in critique_patterns:
        if p in n: return 1
    for p in important_patterns:
        if p in n: return 2
    # Signatures → secondaire
    if type_raw == "/Sig": return 3
    # NSS chiffres individuels → critique en bloc mais secondaires unitairement
    if "numero ss" in n or "ss enfant" in n: return 1
    return 3


def _label_metier(nom: str, page: int) -> str:
    """Génère un label lisible pour le rapport."""
    n = nom.lower()
    labels = {
        "champ de texte p2 1": "Nom de naissance",
        "champ de texte p2 2": "Nom d'usage",
        "champ de texte p2 3": "Prénom(s)",
        "champ de texte p2 8": "Adresse (voie)",
        "champ de texte 17":   "Code postal",
        "champ de texte 18":   "Commune",
        "champ de texte 24":   "Téléphone",
        "champ de texte 19":   "Pays",
        "champ de texte p 2 9":"Commune (bis)",
        "champ de texte p2 10":"N° allocataire",
        "champ de texte p1 1": "Département MDPH",
        "champ de texte p 1 2":"N° dossier existant",
        "case à cocher p1 1":  "Première demande",
        "case à cocher p1 2":  "Situation changée",
        "case à cocher p1 3":  "Réévaluation",
        "case à cocher p1 a":  "Renouvellement",
        "case à cocher p1 b":  "Aidant familial",
        "case à cocher 5":     "Genre masculin",
        "case à cocher 6":     "Genre féminin",
        "case à cocher 7":     "Nationalité française",
        "case à cocher 4":     "Organisme CAF",
        "champ de texte p8 1": "Texte libre B (vie quotidienne)",
        "champ de texte p14 1":"Texte libre D (emploi)",
        "champ de texte p16 1":"Texte libre E (projet de vie)",
        "case à cocher p17 1": "AEEH",
        "case à cocher p17 2": "PCH (enfant)",
        "case à cocher p17 3": "CMI invalidité",
        "case à cocher p17 4": "AVPF",
        "case à cocher p17 5": "AAH",
        "case à cocher p17 6": "RQTH",
        "case à cocher p17 7": "PCH (adulte)",
        "case à cocher p17 8": "Orientation ESMS (MAS/FAM)",
        "case à cocher p17 9": "Foyer de vie",
        "case à cocher p17 10":"Foyer d'hébergement",
        "case à cocher p17 11":"ESAT / orientation médico-sociale",
        "case à cocher p17 12":"Accueil de jour",
        "case à cocher p17 13":"CMI stationnement",
        "case à cocher p17 14":"CMI priorité",
        "case à cocher p17 15":"ACTP",
        "case à cocher p17 16":"Autre prestation vie quotidienne",
        "case à cocher p18 1": "RQTH (emploi)",
        "case à cocher p18 2": "Orientation professionnelle",
        "case à cocher p18 3": "ESPO/CRP/CPO/UEROS",
        "case à cocher p18 4": "ESAT (emploi)",
        "case à cocher p18 5": "ESRP",
        "case à cocher p18 6": "Emploi accompagné (EA)",
        "representant legal 1":"Type de protection juridique",
        "representant legal 3":"Nom tuteur/curateur",
        "representant legal 6":"Référence jugement",
        "case à cocher p 9 1": "Scolarité ordinaire",
        "case à cocher p 9 2": "Scolarité à domicile",
        "case à cocher p 9 3": "Établissement médico-social",
        "case à cocher p 9 4": "SESSAD",
        "case à cocher p 10 1":"Aménagement AESH/AVS",
        "case à cocher p 10 2":"Aménagement tiers-temps",
        "case à cocher p 10 3":"Aménagement matériel adapté",
        "case à cocher p 10 4":"Transport scolaire adapté",
        "case à cocher p5 1":  "Vie seul(e)",
        "case à cocher p5 2":  "Vie en couple",
        "case à cocher p5 3":  "Vie avec famille",
        "case à cocher p5 7":  "Propriétaire",
        "case à cocher p5 8":  "Locataire",
        "case à cocher p5 15": "Ressource AAH",
        "case à cocher p5 16": "Pension invalidité",
        "case à cocher p5 19": "Indemnités journalières",
        "case à cocher p 13 1":"En emploi",
        "case à cocher p 13 2":"Milieu ordinaire",
        "case à cocher p 13 9":"ESAT (emploi actuel)",
        "case à cocher p 13 15":"Retraite",
        "case à cocher p 13 16":"Sans emploi",
        "case à cocher p14 1": "Sans emploi (déclaré)",
        "case à cocher p14 4": "Inscrit Pôle Emploi/France Travail",
        "case à cocher p16 5": "Bilan capacités/ESPO",
        "champ de texte p19 1":"Nom aidant",
        "champ de texte p19 2":"Prénom aidant",
        "champ de texte p20 1":"Besoins aidant",
    }
    return labels.get(nom.lower(), nom)


def inventorier_pdf(pdf_path: Path) -> list[ChampPDF]:
    """Lit les 612 champs AcroForm du CERFA et les retourne avec métadonnées."""
    import pypdf

    reader = pypdf.PdfReader(str(pdf_path))
    pdf_fields = reader.get_fields() or {}

    # Construire la map page → liste de noms de champs
    page_map: dict[str, int] = {}
    for page_num, page in enumerate(reader.pages, 1):
        annots = page.get("/Annots")
        if not annots:
            continue
        for annot in annots:
            try:
                obj = annot.get_object() if hasattr(annot, "get_object") else annot
                t = obj.get("/T")
                if t:
                    page_map[str(t)] = page_num
            except Exception:
                pass

    champs = []
    for nom, f in pdf_fields.items():
        type_raw = str(f.get("/FT", "/Tx"))
        page = page_map.get(nom, 0)
        section = _detecter_section(nom, page)
        criticite = _criticite(nom, page, type_raw)
        label = _label_metier(nom, page)

        if type_raw == "/Tx":
            type_champ = "texte"
        elif type_raw == "/Btn":
            type_champ = "case"
        elif type_raw == "/Sig":
            type_champ = "signature"
        else:
            type_champ = "autre"

        # Applicabilité par profil
        applicable_enfant  = page not in (13, 14, 15) or section in ("identite", "droits_e1_e2", "droits_e3")
        applicable_adulte  = page not in (9, 10, 11, 12) or section in ("identite", "droits_e1_e2", "droits_e3")
        applicable_protege = True  # inclut tout + page 3

        champs.append(ChampPDF(
            nom=nom,
            page=page,
            type_champ=type_champ,
            type_raw=type_raw,
            section=section,
            criticite=criticite,
            label_metier=label,
            applicable_adulte=applicable_adulte,
            applicable_enfant=applicable_enfant,
            applicable_protege=applicable_protege,
        ))

    return sorted(champs, key=lambda c: (c.page, c.nom))


# ─────────────────────────────────────────────────────────────────────────────
# ÉTAPE 2 — COUVERTURE PAR PROFIL
# Comparer build_field_map() vs inventaire PDF
# ─────────────────────────────────────────────────────────────────────────────

# Codes de statut couverture
COUVERT           = "COUVERT"          # Facilim produit ce champ avec une valeur
PARTIELLEMENT     = "PARTIEL"          # Champ produit mais valeur tronquée / dégradée
JAMAIS            = "JAMAIS"           # Champ jamais produit par Facilim (aucun mapping)
NON_APPLICABLE    = "N/A"              # Non applicable pour ce type de profil
MAL_POSITIONNE    = "MAL_POS"         # Valeur dans un champ mais pas le bon
SIGNATURE         = "SIGNATURE"        # Champ de signature — hors scope automatisation


@dataclass
class ResultatChamp:
    champ:          ChampPDF
    statut:         str
    valeur_produite: str
    source_mapping:  str   # "build_field_map" | "v2_bridge" | "jamais_atteint"
    observation:    str


@dataclass
class CoverageReport:
    profil_id:     str
    profil_mdph:   str
    timestamp:     str
    resultats:     list[ResultatChamp]

    @property
    def total(self) -> int:
        return len(self.resultats)

    @property
    def couverts(self) -> int:
        return sum(1 for r in self.resultats if r.statut in (COUVERT, PARTIELLEMENT))

    @property
    def jamais(self) -> int:
        return sum(1 for r in self.resultats if r.statut == JAMAIS)

    @property
    def non_applicables(self) -> int:
        return sum(1 for r in self.resultats if r.statut in (NON_APPLICABLE, SIGNATURE))

    @property
    def applicables(self) -> int:
        return self.total - self.non_applicables

    @property
    def taux_couverture_global(self) -> float:
        if not self.total:
            return 0.0
        return round(self.couverts / self.total * 100, 1)

    @property
    def taux_couverture_applicable(self) -> float:
        if not self.applicables:
            return 0.0
        return round(self.couverts / self.applicables * 100, 1)

    def taux_par_criticite(self, niveau: int) -> float:
        applicables = [r for r in self.resultats
                       if r.champ.criticite == niveau and r.statut != NON_APPLICABLE and r.statut != SIGNATURE]
        couverts = [r for r in applicables if r.statut in (COUVERT, PARTIELLEMENT)]
        if not applicables:
            return 0.0
        return round(len(couverts) / len(applicables) * 100, 1)

    def taux_par_section(self, section: str) -> float:
        applicables = [r for r in self.resultats
                       if r.champ.section == section and r.statut not in (NON_APPLICABLE, SIGNATURE)]
        couverts = [r for r in applicables if r.statut in (COUVERT, PARTIELLEMENT)]
        if not applicables:
            return 0.0
        return round(len(couverts) / len(applicables) * 100, 1)


def auditer_profil(
    champs_pdf:   list[ChampPDF],
    donnees:      dict[str, Any],
    profil_mdph:  str,
    profil_id:    str,
) -> CoverageReport:
    """
    Compare ce que build_field_map() produit pour ce profil
    versus les 612 champs existants dans le PDF.
    """
    from app.engines.pdf.field_mapper import build_field_map

    # Ce que Facilim produirait réellement
    try:
        produit = build_field_map(donnees, profil_mdph)
    except Exception as e:
        produit = {}

    # Noms produits pour la recherche rapide
    noms_produits = set(produit.keys())

    resultats = []
    for champ in champs_pdf:
        # Signature → hors scope
        if champ.type_champ == "signature":
            resultats.append(ResultatChamp(
                champ=champ,
                statut=SIGNATURE,
                valeur_produite="",
                source_mapping="hors_scope",
                observation="Signature manuscrite — non automatisable",
            ))
            continue

        # Applicabilité selon profil
        if profil_mdph == "enfant" and not champ.applicable_enfant:
            resultats.append(ResultatChamp(
                champ=champ,
                statut=NON_APPLICABLE,
                valeur_produite="",
                source_mapping="",
                observation=f"Section {champ.section} non applicable au profil enfant",
            ))
            continue

        if profil_mdph == "adulte" and not champ.applicable_adulte:
            resultats.append(ResultatChamp(
                champ=champ,
                statut=NON_APPLICABLE,
                valeur_produite="",
                source_mapping="",
                observation=f"Section {champ.section} non applicable au profil adulte",
            ))
            continue

        # Page 3 (protection juridique) — applicable uniquement si type_protection présent
        if champ.page == 3 and not donnees.get("type_protection") and profil_mdph != "protege":
            resultats.append(ResultatChamp(
                champ=champ,
                statut=NON_APPLICABLE,
                valeur_produite="",
                source_mapping="",
                observation="Protection juridique non déclarée pour ce profil",
            ))
            continue

        # Page 19-20 (aidant) — applicable uniquement si aidant_nom présent
        if champ.page in (19, 20) and not donnees.get("aidant_nom"):
            resultats.append(ResultatChamp(
                champ=champ,
                statut=NON_APPLICABLE,
                valeur_produite="",
                source_mapping="",
                observation="Pas d'aidant déclaré pour ce profil",
            ))
            continue

        # Vérification de couverture
        if champ.nom in noms_produits:
            val = produit[champ.nom]
            # Partiel si valeur très courte (< 10 chars) pour un champ texte long
            if champ.type_champ == "texte" and len(val) < 10 and champ.criticite == 1:
                statut = PARTIELLEMENT
                obs = f"Valeur courte ({len(val)} chars) pour un champ critique"
            else:
                statut = COUVERT
                obs = f"Produit par build_field_map : {val[:60]!r}"
            resultats.append(ResultatChamp(
                champ=champ,
                statut=statut,
                valeur_produite=val[:120],
                source_mapping="build_field_map",
                observation=obs,
            ))
        else:
            # Champ absent de la production
            # Vérifier si c'est un champ NIR groupé (les digits individuels)
            is_nir_group = any(k in champ.nom for k in ["Numero SS", "N° SS Enfant"])
            if is_nir_group:
                # Vérifier si la série est dans produit
                base = champ.nom.rsplit(" ", 1)[0]
                any_produced = any(n.startswith(base) for n in noms_produits)
                if any_produced:
                    obs = "NIR produit (autre chiffre de la série)"
                    statut = COUVERT
                else:
                    obs = "NIR non produit — num_secu absent des données"
                    statut = JAMAIS
            else:
                obs = "Aucun mapping dans build_field_map pour ce champ"
                statut = JAMAIS

            resultats.append(ResultatChamp(
                champ=champ,
                statut=statut,
                valeur_produite="",
                source_mapping="jamais_atteint",
                observation=obs,
            ))

    return CoverageReport(
        profil_id=profil_id,
        profil_mdph=profil_mdph,
        timestamp=datetime.now(timezone.utc).isoformat(),
        resultats=resultats,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ÉTAPE 3 — CLASSIFICATION RÉGLEMENTAIRE COMPLÈTE
# ─────────────────────────────────────────────────────────────────────────────

# Champs jamais atteints par Facilim — classés par criticité
# Construit dynamiquement à partir des résultats d'audit

def champs_jamais_atteints_critiques(
    rapports: list[CoverageReport],
    champs_pdf: list[ChampPDF],
) -> list[dict]:
    """Retourne les champs jamais couverts par aucun profil, triés par criticité."""
    champ_by_nom = {c.nom: c for c in champs_pdf}
    # Compter les fois où chaque champ est JAMAIS ou COUVERT
    jamais_count: dict[str, int] = {}
    couvert_count: dict[str, int] = {}
    total_applicable: dict[str, int] = {}

    for rapport in rapports:
        for r in rapport.resultats:
            nom = r.champ.nom
            if r.statut == JAMAIS:
                jamais_count[nom] = jamais_count.get(nom, 0) + 1
                total_applicable[nom] = total_applicable.get(nom, 0) + 1
            elif r.statut in (COUVERT, PARTIELLEMENT):
                couvert_count[nom] = couvert_count.get(nom, 0) + 1
                total_applicable[nom] = total_applicable.get(nom, 0) + 1
            elif r.statut not in (NON_APPLICABLE, SIGNATURE):
                total_applicable[nom] = total_applicable.get(nom, 0) + 1

    result = []
    for nom, jamais in jamais_count.items():
        total = total_applicable.get(nom, 0)
        if total == 0:
            continue
        pct_jamais = round(jamais / total * 100, 0)
        champ = champ_by_nom.get(nom)
        if not champ:
            continue
        result.append({
            "nom":          nom,
            "label":        champ.label_metier,
            "page":         champ.page,
            "section":      champ.section,
            "criticite":    champ.criticite,
            "type":         champ.type_champ,
            "jamais_pct":   pct_jamais,
            "jamais_n":     jamais,
            "total_n":      total,
        })

    return sorted(result, key=lambda x: (x["criticite"], -x["jamais_pct"]))


# ─────────────────────────────────────────────────────────────────────────────
# ÉTAPE 4 — EXPORTS
# ─────────────────────────────────────────────────────────────────────────────

SECTIONS_LABELS = {
    "garde":               "Page de garde",
    "identite":            "Identité (A1/A2)",
    "protection_juridique":"Protection juridique (A4)",
    "aides_humaines":      "Aides humaines (A5)",
    "vie_quotidienne_b1":  "Vie quotidienne B1",
    "besoins_avq":         "Besoins AVQ (B2/B3)",
    "texte_libre_b":       "Texte libre B",
    "scolarite":           "Scolarité (C)",
    "emploi_d1":           "Emploi D1",
    "emploi_d2":           "Emploi D2",
    "parcours_pro":        "Parcours professionnel (D2)",
    "projet_vie":          "Projet de vie (E)",
    "droits_e1_e2":        "Droits E1/E2",
    "droits_e3":           "Droits E3",
    "aidant_f":            "Aidant F",
    "aidant_f2":           "Aidant F2",
    "autre":               "Autre",
}


def exporter_csv(
    champs_pdf: list[ChampPDF],
    rapports: list[CoverageReport],
    path: Path,
) -> None:
    """Exporte couverture_reelle.csv — une ligne par champ × profil."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Champ", "Label_Metier", "Page", "Section", "Type",
            "Criticite", "Profil", "Statut", "Valeur_Produite",
            "Source", "Observation",
        ])
        for rapport in rapports:
            for r in rapport.resultats:
                writer.writerow([
                    r.champ.nom,
                    r.champ.label_metier,
                    r.champ.page,
                    SECTIONS_LABELS.get(r.champ.section, r.champ.section),
                    r.champ.type_champ,
                    r.champ.criticite,
                    rapport.profil_id,
                    r.statut,
                    r.valeur_produite[:80] if r.valeur_produite else "",
                    r.source_mapping,
                    r.observation[:100] if r.observation else "",
                ])


def exporter_top_critiques(
    manquants: list[dict],
    path: Path,
    n: int = 100,
) -> None:
    """Exporte top_100_champs_critiques.md."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# TOP CHAMPS CRITIQUES MANQUANTS — CERFA 15692*01",
        "",
        "Champs jamais couverts par Facilim, classés par criticité puis taux d'absence.",
        "",
        f"_Généré le {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
    ]

    for niveau, titre in [(1, "NIVEAU 1 — CRITIQUE"), (2, "NIVEAU 2 — IMPORTANT"), (3, "NIVEAU 3 — SECONDAIRE")]:
        items = [m for m in manquants if m["criticite"] == niveau][:n]
        if not items:
            continue
        lines += [f"## {titre}", ""]
        lines += ["| # | Champ | Label | Page | Section | Absence |", "|---|-------|-------|------|---------|---------|"]
        for i, m in enumerate(items, 1):
            lines.append(
                f"| {i} | `{m['nom']}` | {m['label']} | P{m['page']} | "
                f"{SECTIONS_LABELS.get(m['section'], m['section'])} | {m['jamais_pct']:.0f}% |"
            )
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def generer_rapport_global(
    rapports: list[CoverageReport],
    champs_pdf: list[ChampPDF],
    manquants: list[dict],
    sprint: str = "",
) -> str:
    """Génère le rapport texte principal."""
    sep = "═" * 72
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Stats globales agrégées
    total_champs = len(champs_pdf)
    total_hors_sig = sum(1 for c in champs_pdf if c.type_champ != "signature")

    # Couverture globale moyenne
    scores_global  = [r.taux_couverture_global for r in rapports]
    scores_applic  = [r.taux_couverture_applicable for r in rapports]
    moy_global = round(sum(scores_global) / len(scores_global), 1) if scores_global else 0
    moy_applic = round(sum(scores_applic) / len(scores_applic), 1) if scores_applic else 0

    # Couverture par criticité (agrégé tous profils)
    all_resultats = [r for rapport in rapports for r in rapport.resultats]
    def taux_crit(niveau: int) -> float:
        app = [r for r in all_resultats if r.champ.criticite == niveau and r.statut not in (NON_APPLICABLE, SIGNATURE)]
        couv = [r for r in app if r.statut in (COUVERT, PARTIELLEMENT)]
        return round(len(couv) / len(app) * 100, 1) if app else 0

    # Couverture par section
    sections_rates: dict[str, float] = {}
    for section in SECTIONS_LABELS:
        app = [r for r in all_resultats if r.champ.section == section and r.statut not in (NON_APPLICABLE, SIGNATURE)]
        couv = [r for r in app if r.statut in (COUVERT, PARTIELLEMENT)]
        if app:
            sections_rates[section] = round(len(couv) / len(app) * 100, 1)

    lines = [
        sep,
        "  FACILIM QA-2 — AUDIT TERRAIN CERFA 15692*01",
        f"  Généré le : {now}",
        f"  Sprint : {sprint or 'QA-2'}",
        f"  Profils testés : {len(rapports)}",
        sep,
        "",
        "  INVENTAIRE CERFA",
        f"  Champs AcroForm totaux    : {total_champs}",
        f"  Champs texte (/Tx)        : {sum(1 for c in champs_pdf if c.type_raw == '/Tx')}",
        f"  Cases à cocher (/Btn)     : {sum(1 for c in champs_pdf if c.type_raw == '/Btn')}",
        f"  Signatures (/Sig)         : {sum(1 for c in champs_pdf if c.type_raw == '/Sig')}",
        f"  Champs hors signatures    : {total_hors_sig}",
        "",
        "  COUVERTURE RÉELLE (MOYENNE TOUS PROFILS)",
        f"  Taux global (/ 612)       : {moy_global}%",
        f"  Taux applicable           : {moy_applic}%",
        "",
        "  COUVERTURE PAR NIVEAU DE CRITICITÉ",
        f"  Niveau 1 — Critique       : {taux_crit(1)}%",
        f"  Niveau 2 — Important      : {taux_crit(2)}%",
        f"  Niveau 3 — Secondaire     : {taux_crit(3)}%",
        "",
        "  COUVERTURE PAR SECTION MÉTIER",
    ]

    for section, label in SECTIONS_LABELS.items():
        rate = sections_rates.get(section)
        if rate is None:
            continue
        bar = "█" * int(rate // 10) + "░" * (10 - int(rate // 10))
        lines.append(f"  {label:<30} : {bar} {rate:5.1f}%")

    lines += ["", "  DÉTAIL PAR PROFIL"]
    lines.append(f"  {'ID':<30} {'Global':>8} {'Applic':>8} {'Critiques':>10} {'JAMAIS':>7}")
    lines.append("  " + "─" * 70)

    for rapport in sorted(rapports, key=lambda r: -r.taux_couverture_applicable):
        jamais_n = rapport.jamais
        crit1 = rapport.taux_par_criticite(1)
        lines.append(
            f"  {rapport.profil_id:<30} {rapport.taux_couverture_global:>7.1f}% "
            f"{rapport.taux_couverture_applicable:>7.1f}% "
            f"{crit1:>9.1f}% "
            f"{jamais_n:>7}"
        )

    # Champs critiques jamais couverts — top 20
    top20 = [m for m in manquants if m["criticite"] == 1][:20]
    if top20:
        lines += [
            "", "  TOP 20 CHAMPS CRITIQUES JAMAIS COUVERTS",
            "  " + "─" * 70,
        ]
        for m in top20:
            lines.append(f"  P{m['page']:>2} | {m['nom']:<40} | {m['label'][:30]}")

    lines += ["", sep]
    return "\n".join(lines)


def generer_qa_vs_reality(
    rapports: list[CoverageReport],
    champs_pdf: list[ChampPDF],
    path: Path,
) -> None:
    """Génère qa_vs_reality.md — compare ce que le QA teste vs le CERFA réel."""
    # Champs testés par le QA engine (cases_cerfa_attendues des profils)
    from app.tests.qa.profiles import ALL_PROFILES
    champs_testes_qa: set[str] = set()
    for p in ALL_PROFILES:
        champs_testes_qa.update(p.cases_cerfa_attendues.keys())
        champs_testes_qa.update(p.cases_cerfa_absentes)

    # Champs produits par Facilim (au moins une fois sur tous les profils)
    noms_produits_ever: dict[str, int] = {}
    for rapport in rapports:
        for r in rapport.resultats:
            if r.statut in (COUVERT, PARTIELLEMENT):
                noms_produits_ever[r.champ.nom] = noms_produits_ever.get(r.champ.nom, 0) + 1

    # Champs dans le PDF mais jamais produits
    jamais_produits = set(c.nom for c in champs_pdf) - set(noms_produits_ever.keys())

    # Champs testés QA mais non dans le PDF (doublons / erreurs de nom)
    noms_pdf = set(c.nom for c in champs_pdf)
    testes_inexistants = champs_testes_qa - noms_pdf

    lines = [
        "# QA vs RÉALITÉ — Comparaison audit terrain CERFA",
        "",
        f"_Généré le {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
        "## Synthèse",
        "",
        f"- **Champs PDF réels** : {len(champs_pdf)}",
        f"- **Champs produits par Facilim** (au moins 1 profil) : {len(noms_produits_ever)}",
        f"- **Champs PDF jamais produits** : {len(jamais_produits)}",
        f"- **Champs testés par QA** : {len(champs_testes_qa)}",
        f"- **Champs testés QA inexistants dans le PDF** : {len(testes_inexistants)}",
        "",
    ]

    if testes_inexistants:
        lines += [
            "## ⚠️ Champs testés par le QA mais absents du PDF (faux positifs QA)",
            "",
            "_Ces champs sont validés par le QA mais n'existent pas dans le PDF officiel._",
            "",
        ]
        for n in sorted(testes_inexistants):
            lines.append(f"- `{n}`")
        lines.append("")

    lines += [
        "## Champs produits par Facilim (couverts)",
        "",
        f"_{len(noms_produits_ever)} champs sur {len(champs_pdf)} ({round(len(noms_produits_ever)/len(champs_pdf)*100,1)}%)_",
        "",
    ]
    for nom, count in sorted(noms_produits_ever.items(), key=lambda x: -x[1]):
        lines.append(f"- `{nom}` ({count}/{len(rapports)} profils)")

    lines += [
        "",
        "## Champs JAMAIS produits — classés par criticité",
        "",
    ]
    champ_by_nom = {c.nom: c for c in champs_pdf}
    by_crit: dict[int, list[str]] = {1: [], 2: [], 3: []}
    for nom in sorted(jamais_produits):
        c = champ_by_nom.get(nom)
        if c and c.type_champ != "signature":
            by_crit.setdefault(c.criticite, []).append(nom)

    for niveau, titre in [(1, "Critique"), (2, "Important"), (3, "Secondaire")]:
        if not by_crit.get(niveau):
            continue
        lines += [f"### Niveau {niveau} — {titre}", ""]
        for nom in by_crit[niveau]:
            c = champ_by_nom.get(nom)
            label = c.label_metier if c else ""
            page = c.page if c else "?"
            lines.append(f"- P{page} `{nom}` — {label}")
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="FACILIM QA-2 — Audit terrain CERFA")
    parser.add_argument("--profil", help="ID d'un profil spécifique")
    parser.add_argument("--all",    action="store_true", help="Tous les profils QA")
    parser.add_argument("--save",   action="store_true", help="Sauvegarder les rapports")
    parser.add_argument("--sprint", default="QA-2",      help="Nom du sprint")
    args = parser.parse_args()

    # Setup environnement
    sys.path.insert(0, ".")
    os.environ.setdefault("DATABASE_URL", "sqlite:///./mdph_dossiers.db")
    os.environ.setdefault("JWT_SECRET_KEY", "test-key-32-chars-minimum-length!")
    os.environ.setdefault("WHATSAPP_API_TOKEN", "test")
    os.environ.setdefault("WHATSAPP_PHONE_NUMBER_ID", "test")

    # 1. Inventaire PDF
    print(f"Lecture du CERFA : {PDF_CERFA}")
    champs_pdf = inventorier_pdf(PDF_CERFA)
    print(f"  {len(champs_pdf)} champs inventoriés")

    # 2. Profils à tester
    from app.tests.qa.profiles import ALL_PROFILES

    # Profils supplémentaires (vide, WA seul, docs seul)
    from app.tests.qa.profiles import ProfilQA

    PROFILS_SUPPLEMENTAIRES = [
        ProfilQA(
            id="DOSSIER_VIDE",
            nom="Dossier vide — zéro donnée",
            categorie="adulte", profil_mdph="adulte", profil_handicap="",
            frequence="rare", donnees_entree={}, document_texte="", document_type="",
            droits_attendus=[], droits_non_attendus=[], cases_cerfa_attendues={},
            sections_narratives={}, justificatifs_attendus=[],
            narratif_doit_declencher=False, boucle_interdite=True, score_maturite_min=0,
        ),
        ProfilQA(
            id="DOSSIER_WA_SEUL",
            nom="Dossier WhatsApp seul — données basiques",
            categorie="adulte", profil_mdph="adulte", profil_handicap="moteur",
            frequence="frequent",
            donnees_entree={
                "nom_prenom":      "MARTIN Pierre",
                "date_naissance":  "15/03/1970",
                "genre":           "homme",
                "diagnostics":     "douleurs chroniques dorsales",
                "impact_quotidien":"marche difficile, fatigue",
                "droits_demandes": "RQTH",
            },
            document_texte="", document_type="",
            droits_attendus=["RQTH"], droits_non_attendus=["AAH"],
            cases_cerfa_attendues={"Case à cocher P17 6": "/Yes"},
            sections_narratives={}, justificatifs_attendus=[],
            narratif_doit_declencher=True, boucle_interdite=True, score_maturite_min=40,
        ),
        ProfilQA(
            id="DOSSIER_COMPLET_ADULTE",
            nom="Dossier complet adulte — toutes données renseignées",
            categorie="adulte", profil_mdph="adulte", profil_handicap="moteur",
            frequence="frequent",
            donnees_entree={
                "nom_prenom":             "DUPONT Marie",
                "date_naissance":         "10/05/1975",
                "genre":                  "femme",
                "adresse_complete":       "12 rue de la Paix 75001 Paris",
                "telephone":              "0612345678",
                "departement":            "75",
                "num_secu":               "275057500100012",
                "diagnostics":            "sclérose en plaques progressive, fatigue chronique",
                "traitements":            "Ocrevus, kinésithérapie hebdomadaire",
                "impact_quotidien":       "marche limitée à 200m, fauteuil en dehors domicile",
                "statut_emploi":          "sans emploi depuis 2022, ancienne infirmière",
                "droits_demandes":        "RQTH AAH PCH CMI",
                "mode_vie":               "seule",
                "type_logement":          "locataire",
                "type_dossier":           "INITIAL",
                "texte_b_vie_quotidienne": "Marie souffre de sclérose en plaques progressive depuis 2018. La marche est limitée à 200 mètres. Elle utilise un fauteuil roulant pour les déplacements extérieurs.",
                "texte_d_situation_pro":  "Marie a dû cesser son activité d'infirmière en 2022 en raison de l'aggravation des symptômes. Elle est en arrêt longue durée depuis 3 ans.",
                "texte_e_projet_vie":     "Marie souhaite bénéficier d'une compensation de la PCH pour maintenir son autonomie à domicile. Elle envisage une reconversion via le RQTH.",
                "notes_pro":              "Dossier préparé avec Marie. Situation de handicap moteur évolutif.",
            },
            document_texte="", document_type="",
            droits_attendus=["RQTH","AAH","PCH","CMI"],
            droits_non_attendus=["AEEH","ESAT"],
            cases_cerfa_attendues={
                "Case à cocher P17 5": "/Yes",
                "Case à cocher P17 6": "/Yes",
                "Case à cocher P17 7": "/Yes",
                "Champ de texte P8 1": "sclérose",
            },
            sections_narratives={"B": "marche", "D": "infirmière", "E": "autonomie"},
            justificatifs_attendus=["Certificat médical", "Bilan kinésithérapie"],
            narratif_doit_declencher=True, boucle_interdite=True, score_maturite_min=60,
        ),
    ]

    if args.profil:
        profils = [p for p in ALL_PROFILES + PROFILS_SUPPLEMENTAIRES if p.id == args.profil]
        if not profils:
            print(f"Profil '{args.profil}' non trouvé.")
            sys.exit(1)
    elif args.all:
        profils = ALL_PROFILES + PROFILS_SUPPLEMENTAIRES
    else:
        profils = PROFILS_SUPPLEMENTAIRES[:2]

    # 3. Audit profil par profil
    print(f"\nAudit de {len(profils)} profil(s)...")
    rapports: list[CoverageReport] = []
    for profil in profils:
        donnees = dict(profil.donnees_entree)
        # Injecter document_texte comme notes_pro si présent
        if profil.document_texte and not donnees.get("notes_pro"):
            donnees["notes_pro"] = profil.document_texte[:800]
        rapport = auditer_profil(
            champs_pdf=champs_pdf,
            donnees=donnees,
            profil_mdph=profil.profil_mdph,
            profil_id=profil.id,
        )
        rapports.append(rapport)
        print(f"  {profil.id:<35} global={rapport.taux_couverture_global:5.1f}%  applicable={rapport.taux_couverture_applicable:5.1f}%  jamais={rapport.jamais}")

    # 4. Analyse globale
    manquants = champs_jamais_atteints_critiques(rapports, champs_pdf)

    # 5. Rapport global
    rapport_txt = generer_rapport_global(rapports, champs_pdf, manquants, args.sprint)
    print("\n" + rapport_txt)

    # 6. Sauvegarde
    if args.save:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        csv_path = OUTPUT_DIR / f"couverture_reelle_{ts}.csv"
        exporter_csv(champs_pdf, rapports, csv_path)
        print(f"\nCSV : {csv_path}")

        crit_path = OUTPUT_DIR / f"top_100_champs_critiques_{ts}.md"
        exporter_top_critiques(manquants, crit_path, n=100)
        print(f"Critiques : {crit_path}")

        qa_vs_path = OUTPUT_DIR / f"qa_vs_reality_{ts}.md"
        generer_qa_vs_reality(rapports, champs_pdf, qa_vs_path)
        print(f"QA vs réalité : {qa_vs_path}")

        rapport_path = OUTPUT_DIR / f"rapport_audit_cerfa_{ts}.txt"
        rapport_path.write_text(rapport_txt, encoding="utf-8")
        print(f"Rapport : {rapport_path}")


if __name__ == "__main__":
    main()
