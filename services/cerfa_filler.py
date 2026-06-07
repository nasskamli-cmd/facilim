"""
cerfa_filler.py — Pré-remplissage automatique du CERFA 15692*01 (MDPH national).

Couvre l'intégralité des sections remplissables sans intervention médicale,
pour les dossiers enfants ET adultes :

  Page 1  : Département MDPH + type de demande + procédure simplifiée
  Page 2  : Identité complète (nom, prénom, DDN, NSS, genre, adresse, contact)
  Page 3  : Représentant légal / protection juridique + NSS parent
  Page 4  : Situation familiale (signature laissée VIDE — signée par l'éducateur)
  Page 5  : Lieu de vie / logement / mode de vie
  Page 6  : Aides humaines et soins
  Page 7  : Mobilité, transports, communication
  Page 8  : Description narrative (situation + retentissements + projets de vie)
  Pages 9-12 : Scolarité (enfants et jeunes majeurs)
  Pages 13-16 : Situation professionnelle (adultes et jeunes majeurs)
  Page 17 : Demandes allocations/droits (AAH, PCH, AEEH, CMI, ESMS)
  Page 18 : Orientations professionnelles (RQTH, ORP, emploi accompagné, ESAT)
  Page 20 : Aidant familial
  Bas de page : Nom / prénom répétés sur chaque page

Section médicale (page 5 médicale) : laissée vide — remplie par le médecin traitant.

Nuances expertes intégrées (v3 — 2025) :
  - Signature page 4 : TOUJOURS laissée vide (signée par l'éducateur à l'impression)
  - CMI priorité (station debout prolongée pénible) ≠ CMI stationnement (PMR/<200m)
  - Emploi accompagné (P18 6) distinct de droit commun (P18 5 sans EA)
  - Procédure simplifiée : UNIQUEMENT renouvellement sans réexamen + urgence droits
  - NSS page 3 : NSS du parent déclarant (enfants), pas uniquement du bénéficiaire
  - Ressources actuelles + frais liés au handicap : section B1
  - P8 : structure narrative « situation → retentissements → projets de vie »
  - Creton (P17 9) : jeune adulte >20 ans maintenu en établissement enfants
  - Consentement partage informations (page 4) mappé depuis ds.consentement_informations
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
    projet_professionnel: str = "",
    difficultes_quotidiennes: str = "",
    besoins_aide: str = "",
    prenom: str = "",
    nom: str = "",
) -> str:
    """
    Compose le texte narratif de la page 8 du CERFA 15692 :
    « Description de la situation et des difficultés »

    Structure : Situation actuelle → Retentissements fonctionnels → Projets de vie
    - Adulte : 1ère personne (« je ne peux pas… »)
    - Enfant  : 3ème personne (« il/elle ne peut pas… »)
    - Phrases courtes, sans jargon, fort impact
    - Référence implicite au cadre réglementaire GEVA
    - Sans mention de RSDAE, ESAT, PCH, AAH, score, algorithme
    """
    # ── Assemblage du contexte brut ───────────────────────────────────────────
    parties = []
    if difficultes_quotidiennes and difficultes_quotidiennes.strip():
        parties.append(difficultes_quotidiennes.strip())
    if besoins_aide and besoins_aide.strip():
        parties.append(besoins_aide.strip())
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

        # POINT 5 : utiliser le vrai prénom/nom pour personnaliser la narration
        _prenom_clean = prenom.strip() if prenom else ""
        _nom_clean    = nom.strip()    if nom    else ""
        _identite     = f"{_prenom_clean} {_nom_clean}".strip() or ("l'enfant" if is_enfant else "la personne")
        _civilite     = _identite  # ex. "Yasmine BENALI" ou "M. Dupont"

        sujet    = f"de {_identite}" if _identite not in ("l'enfant", "la personne") else ("de l'enfant" if is_enfant else "de la personne")
        personne = (
            f"{_civilite} (à la 3ème personne, ex : « {_civilite} ne peut pas… », « il/elle ne peut pas… »)"
            if is_enfant else
            f"{_civilite} elle-même (à la 1ère personne, ex : « je ne peux pas… »)"
        )
        projet_str = f"\nProjet de vie : {projet_professionnel}" if projet_professionnel else ""

        prompt = (
            f"Tu rédiges la section 'Description de la situation et des difficultés' "
            f"d'un formulaire MDPH pour {sujet}.\n"
            f"Rédige ce texte du point de vue de {personne}.\n\n"
            f"Structure OBLIGATOIRE en 4 parties (sans titres, texte continu) :\n"
            f"1. SITUATION ACTUELLE — qui est la personne, quel est son handicap/sa pathologie, "
            f"   dans quel contexte elle vit (2-3 phrases)\n"
            f"2. RETENTISSEMENTS FONCTIONNELS — ce qu'elle ne peut pas faire seule, "
            f"   ce qui est difficile ou épuisant (3-5 phrases courtes et concrètes, fort impact)\n"
            f"3. RETENTISSEMENTS DANS LA VIE QUOTIDIENNE HORS TRAVAIL — "
            f"   ce que le handicap change concrètement au quotidien EN DEHORS du travail : "
            f"   repas/alimentation, courses, déplacements, sorties en famille, loisirs, "
            f"   vie à domicile, relations sociales, gestion de la fatigue et/ou des douleurs "
            f"   (2-4 phrases concrètes, ne pas parler de travail dans cette partie)\n"
            f"4. PROJET DE VIE — ce que la personne souhaite accomplir : aspirations personnelles, "
            f"   autonomie souhaitée, projet professionnel ou de formation si pertinent "
            f"   (1-2 phrases){projet_str}\n\n"
            f"Règles strictes :\n"
            f"- Phrases simples, courtes, concrètes (pas de jargon médical ni administratif)\n"
            f"- Ne mentionne JAMAIS : RSDAE, PCH, AAH, MDPH, score, algorithme, GEVA\n"
            f"- Exemples de formulations : 'ne peut pas faire ses courses seul', "
            f"  'fatigue intense après 20 min de marche', 'a besoin d'aide pour préparer ses repas', "
            f"  'ne peut pas accompagner ses enfants en sortie scolaire'\n"
            f"- Maximum 500 mots, pas de titres, pas de listes à puces, texte continu\n\n"
            f"Informations disponibles :\n{contexte_brut}"
        )

        resp = _client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=700,
            temperature=0.3,
        )
        texte = resp.choices[0].message.content.strip()
        logger.info(f"[CERFA P8] Description générée par LLM ({len(texte)} chars)")
        return texte[:2000]

    except Exception as e:
        logger.warning(f"[CERFA P8] LLM indisponible, fallback texte brut : {e}")
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


def _decocher_case(writer: PdfWriter, field_name: str) -> bool:
    """
    Décoche explicitement une case à cocher (force /Off au niveau des octets PDF).
    Utilisé pour garantir que "première demande" est désactivée quand type=renouvellement.
    """
    for page in writer.pages:
        if "/Annots" not in page:
            continue
        for annot_ref in page["/Annots"]:
            try:
                annot = annot_ref.get_object()
                t_val = annot.get("/T")
                if t_val is not None and str(t_val) == field_name:
                    annot.update({
                        NameObject("/V"):  NameObject("/Off"),
                        NameObject("/AS"): NameObject("/Off"),
                    })
                    logger.debug(f"Case décochée : {field_name} → /Off")
                    return True
            except Exception:
                pass
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

    Implémentation : met à jour le widget (/AS) ET le nœud parent (/V) pour que
    get_fields() et les viewers PDF reflètent la bonne valeur.
    """
    candidates = []
    for page in writer.pages:
        if "/Annots" not in page:
            continue
        for annot_ref in page["/Annots"]:
            try:
                annot = annot_ref.get_object()
                t_val  = annot.get("/T")
                parent = None
                if t_val is None:
                    parent_ref = annot.get("/Parent")
                    if parent_ref:
                        parent = parent_ref.get_object()
                        t_val  = parent.get("/T")
                if t_val is not None and str(t_val) == field_name:
                    rect = annot.get("/Rect")
                    x    = float(rect[0]) if rect else 0
                    on_val = _get_on_value(annot)
                    candidates.append((x, annot, on_val, parent))
            except Exception as e:
                logger.debug(f"_cocher_option_nth scan err : {e!r}")

    if not candidates:
        logger.warning(f"Groupe radio non trouvé : {field_name}")
        return False

    candidates.sort(key=lambda c: c[0])   # tri par X croissant = ordre visuel gauche→droite

    if n >= len(candidates):
        logger.warning(f"Option {n} hors limites pour {field_name} ({len(candidates)} options)")
        return False

    x, annot, on_val, parent = candidates[n]
    # 1. Widget : mettre /AS pour l'affichage visuel
    annot.update({NameObject("/AS"): NameObject(on_val)})
    # 2. Remettre les autres widgets à /Off
    for i, (_, other_annot, _, _) in enumerate(candidates):
        if i != n:
            try:
                other_annot.update({NameObject("/AS"): NameObject("/Off")})
            except Exception:
                pass
    # 3. Nœud parent (field node) : mettre /V — c'est là que get_fields() lit la valeur
    try:
        if parent is not None:
            parent.update({NameObject("/V"): NameObject(on_val)})
        else:
            # T direct sur le widget (pas de parent) : /V sur le widget lui-même
            annot.update({NameObject("/V"): NameObject(on_val)})
    except Exception as e:
        logger.debug(f"_cocher_option_nth parent /V err : {e!r}")

    logger.debug(f"Option #{n} cochée : {field_name} → {on_val} (x={x:.0f})")
    return True


# ─────────────────────────────────────────────────────────────────────────────
#  Mapping droits → cases P17 / P18 / P19
# ─────────────────────────────────────────────────────────────────────────────

def _mapper_droits(
    droits: list,
    is_enfant: bool,
    besoins_aide_humaine: bool,
    cmi_priorite: bool = False,
    cmi_stationnement: bool = False,
    emploi_accompagne: bool = False,
    creton: bool = False,
) -> list[str]:
    """
    Traduit la liste de droits identifiés par l'IA en noms de cases CERFA.

    Mapping vérifié par inspection directe des positions Y/X dans le PDF 15692*01 :

    ── PAGE 17 (E1 — Allocations et droits vie quotidienne) ──
      P17 1  = AEEH                    (enfants < 20 ans)
      P17 2  = PCH                     (enfants < 20 ans)
      P17 3  = CMI invalidité/priorité (enfants < 20 ans) ← station debout pénible
      P17 4  = CMI stationnement       (enfants < 20 ans) ← PMR / périmètre <200m
      P17 5  = AVPF                    (enfants < 20 ans)
      P17 6  = AAH                     (adultes ≥ 20 ans)
      P17 7  = Complément de ressources
      P17 8  = Orientation ESMS adultes (case unique)
      P17 9  = Maintien Creton         (>20 ans, maintenu en structure enfants)
      P17 10 = ACTP
      P17 11 = ACFP
      P17 12 = PCH                     (adultes ≥ 20 ans)
      P17 13 = CMI invalidité/priorité (adultes ≥ 20 ans) ← station debout pénible
      P17 14 = CMI stationnement       (adultes ≥ 20 ans) ← PMR / périmètre <200m
      P17 15 = AVPF                    (adultes ≥ 20 ans)
      P17 16 = E2 scolarisation avec ESMS (enfants)

    ── PAGE 18 (E3 — Travail, emploi, formation professionnelle) ──
      P18 1  = RQTH
      P18 2  = Orientation professionnelle (ORP — case parente)
      P18 3  = └─ CRP / CPO / UEROS   (sous-type ORP)
      P18 4  = └─ ESAT                (sous-type ORP — milieu protégé)
      P18 5  = └─ Marché du travail   (sous-type ORP — milieu ordinaire)
      P18 6  = └──── Emploi accompagné (sous-option marché du travail)
                     ↑ Quand la personne a un projet mais du mal à trouver seule
                       → combine P18 5 + P18 6
                       Droit commun (sans EA) → P18 5 uniquement
    """
    cases: list[str] = []
    # Normalisation : tokens majuscules, tirets → espaces
    droits_str = " ".join(str(d).upper().replace("-", " ") for d in droits)

    # ── PAGE 17 — E1 Allocations ─────────────────────────────────────────────

    # AEEH : Allocation d'Éducation de l'Enfant Handicapé (enfants < 20 ans uniquement)
    if is_enfant and "AEEH" in droits_str:
        cases.append("Case à cocher P17 1")

    # PCH enfant (< 20 ans) — UNIQUEMENT si explicitement dans les droits identifiés
    # Ne jamais déduire automatiquement de besoins_aide_humaine : la personne doit valider
    if is_enfant and "PCH" in droits_str:
        cases.append("Case à cocher P17 2")

    # CMI priorité (invalidité) — station debout prolongée pénible
    # Distincte de CMI stationnement (PMR / périmètre de marche < 200 m)
    has_cmi_generic = any(t in droits_str for t in ("CMI", "CARTE MOBILITE", "CARTE INVALIDITE"))

    # CMI priorité : coché uniquement si explicitement déclaré.
    if cmi_priorite:
        cases.append("Case à cocher P17 3" if is_enfant else "Case à cocher P17 13")

    # CMI stationnement : coché uniquement si explicitement déclaré.
    # Suppression de la déduction par élimination (has_cmi_generic and not cmi_priorite).
    # "CMI" sans précision du type → aucune case cochée + signalement à l'éducateur.
    if cmi_stationnement:
        cases.append("Case à cocher P17 4" if is_enfant else "Case à cocher P17 14")

    # Si has_cmi_generic mais aucun type précisé → log pour relecture manuelle
    if has_cmi_generic and not cmi_priorite and not cmi_stationnement:
        logger.info(
            "[CERFA P17] CMI demandée sans précision du type (priorité/stationnement). "
            "Aucune case cochée — à qualifier par l'éducateur avant signature."
        )

    # AAH : Allocation aux Adultes Handicapés (≥ 20 ans)
    if "AAH" in droits_str:
        cases.append("Case à cocher P17 6")

    # PCH adulte (≥ 20 ans) — UNIQUEMENT si explicitement dans les droits identifiés
    if not is_enfant and "PCH" in droits_str:
        cases.append("Case à cocher P17 12")

    # Complément de ressources (toujours avec AAH si mentionné)
    if any(t in droits_str for t in ("COMPLEMENT DE RESSOURCES", "MAJORATION")):
        cases.append("Case à cocher P17 7")

    # AVPF : Allocation Vieillesse des Parents au Foyer (sur demande explicite uniquement)
    if "AVPF" in droits_str:
        cases.append("Case à cocher P17 5" if is_enfant else "Case à cocher P17 15")

    # Orientation ESMS adultes (case P17 8) — UNIQUEMENT structures adultes
    # IME/SESSAD/ITEP/ULIS sont des structures enfants → ne jamais déclencher P17 8
    _esms_adulte_tokens = ("ESAT", "SAVS", "SAMSAH", "FAM", "MAS",
                           "FOYER D HEBERGEMENT", "FOYER D'HEBERGEMENT")
    _esms_enfant_tokens = ("IME", "SESSAD", "ITEP", "ULIS")
    if not is_enfant and any(t in droits_str for t in _esms_adulte_tokens):
        cases.append("Case à cocher P17 8")   # Orientation ESMS adultes
    if is_enfant and any(t in droits_str for t in (_esms_adulte_tokens + _esms_enfant_tokens)):
        cases.append("Case à cocher P17 16")  # Scolarisation avec ESMS (enfants)

    # Maintien Creton (P17 9) : jeune adulte >20 ans maintenu en structure pour enfants
    # en attente d'une place dans une structure adultes adaptée
    if creton or "CRETON" in droits_str:
        cases.append("Case à cocher P17 9")

    # ── PAGE 18 — E3 Travail, emploi, formation professionnelle ─────────────

    # RQTH (case P18 1)
    if "RQTH" in droits_str:
        cases.append("Case à cocher P18 1")

    # ORP : Orientation Professionnelle
    # CORRECTION 5 — Cohérence C/D : ESAT et formation/CRP sont MUTUELLEMENT EXCLUSIFS.
    # Si ESAT est dans les droits → P18 4 uniquement (milieu protégé), jamais P18 3 (CRP).
    # Si CRP/formation → P18 3 uniquement, jamais P18 4.
    # Ne jamais cocher les deux pour un même objectif.
    _orp_tokens = ("ORP", "ORIENTATION PROFESSIONNELLE", "ORIENTATION PRO",
                   "RECLASSEMENT PROFESSIONNEL", "INSERTION PROFESSIONNELLE")
    _is_esat_projet = "ESAT" in droits_str and not is_enfant
    _is_crp_projet  = any(t in droits_str for t in (
        "CRP", "CPO", "UEROS", "ESRP", "VISA PRO",
        "REEDUCATION PROFESSIONNELLE", "READAPTATION PROFESSIONNELLE",
        "CENTRE DE REEDUCATION", "CENTRE DE READAPTATION",
    ))
    if any(t in droits_str for t in _orp_tokens):
        cases.append("Case à cocher P18 2")  # Case parente ORP
        if _is_esat_projet and not _is_crp_projet:
            # Projet ESAT uniquement → milieu protégé
            cases.append("Case à cocher P18 4")
        elif _is_crp_projet and not _is_esat_projet:
            # Projet formation/CRP uniquement → réadaptation professionnelle
            cases.append("Case à cocher P18 3")
        elif _is_esat_projet and _is_crp_projet:
            # Les deux mentionnés → privilégier ESAT (plus structurant pour profil MIXTE)
            cases.append("Case à cocher P18 4")
            logger.warning("[CERFA C5] ESAT + CRP tous deux présents — P18 4 (ESAT) retenu, P18 3 ignoré.")
        else:
            # Marché du travail (milieu ordinaire)
            cases.append("Case à cocher P18 5")
            if emploi_accompagne or "EMPLOI ACCOMPAGNE" in droits_str:
                cases.append("Case à cocher P18 6")

    logger.debug(
        f"_mapper_droits | droits={droits} | cmi_p={cmi_priorite} cmi_s={cmi_stationnement} "
        f"ea={emploi_accompagne} creton={creton} | cases={cases}"
    )
    return cases


# ─────────────────────────────────────────────────────────────────────────────
#  Point d'entrée public
# ─────────────────────────────────────────────────────────────────────────────

def remplir_cerfa(dossier: dict[str, Any]) -> bytes:
    """
    Pré-remplit le CERFA 15692*01 avec toutes les données disponibles du dossier.
    Compatible enfant ET adulte.

    Si dossier contient la clé "_dossier_cerfa_v2" (DossierCERFA structuré),
    les sous-classes ProtectionJuridique et SectionAidant sont lues directement
    pour les sections A4 et P19-P20, sans parsing fragile de chaînes plates.
    """
    # Lecture du modèle structuré V2 si disponible
    _dv2 = dossier.get("_dossier_cerfa_v2")   # DossierCERFA | None

    if not _CERFA_PATH.exists():
        raise FileNotFoundError(f"Formulaire CERFA introuvable : {_CERFA_PATH}")

    reader = PdfReader(str(_CERFA_PATH))
    writer = PdfWriter()
    writer.append(reader)

    champs: dict[str, str] = {}   # champs texte → update_page_form_field_values
    cases:  list[str]      = []   # cases à cocher → _cocher_case (annotation directe)

    # ── Données personnelles ─────────────────────────────────────────────────
    nom       = (dossier.get("nom_enfant")     or "").upper()
    prenom    = dossier.get("prenom_enfant")   or ""
    ddn       = dossier.get("ddn_enfant")      or ""
    adresse   = dossier.get("adresse_enfant")  or ""
    cp        = dossier.get("cp_enfant")       or ""
    commune   = (dossier.get("commune_enfant") or "").upper()
    # Téléphone : reformater en format français local (0X XX XX XX XX)
    # Le numéro WhatsApp est stocké en format international (336XXXXXXXX → 06XXXXXXXX)
    _tel_raw  = (dossier.get("telephone_famille") or "").strip().replace(" ", "").replace("-", "")
    if _tel_raw.startswith("33") and len(_tel_raw) == 11:
        _tel_raw = "0" + _tel_raw[2:]   # 33642087770 → 0642087770
    elif _tel_raw.startswith("+33"):
        _tel_raw = "0" + _tel_raw[3:]
    telephone = _tel_raw
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
    droits_str         = " ".join(str(d).upper().replace("-", " ") for d in droits)
    elements_probants  = analyse.get("elements_probants") or []

    # Données structurées extraites par l'IA
    ds = analyse.get("donnees_structurees") or {}

    # ── Enrichissement depuis cerfa_reponses (WhatsApp) ──────────────────────
    # Les réponses collectées par le bot WhatsApp peuvent contenir des champs
    # qui ne sont pas encore dans ds (collecte en cours ou analyse antérieure).
    # On les injecte comme couche de substitution : cerfa_reponses ne remplace
    # jamais une valeur déjà présente dans ds, mais comble les trous.
    cerfa_rep = dossier.get("cerfa_reponses") or {}

    def _ds_or_cerfa(ds_key: str, cerfa_key: str, default=None):
        """Retourne ds[ds_key] si renseigné, sinon cerfa_reponses[cerfa_key]."""
        v = ds.get(ds_key)
        if v is not None and v != "" and v != [] and v is not False:
            return v
        return cerfa_rep.get(cerfa_key, default)

    # ── Fallback identité : ds > cerfa_rep comblent les champs dossier vides ───
    # Les champs dossier.* sont remplis par l'éducateur dans le formulaire.
    # Si certains sont vides (ex. adresse non saisie), on remonte vers l'IA
    # (ds = donnees_structurees) puis vers les réponses extraites (cerfa_rep).
    if not nom:
        _nom_fb = (ds.get("nom") or "").strip()
        nom = _nom_fb.upper() if _nom_fb else nom
    if not prenom:
        prenom = (ds.get("prenom") or "").strip() or prenom
    # BUG 5 CORRIGÉ : cerfa_rep ne contient jamais "nom_enfant" / "prenom_enfant"
    # (ces clés n'existent pas dans CERFA_FIELD_ORDER → jamais écrites par le bot WhatsApp).
    # Suppression du code mort. Le fallback unique est cerfa_rep["nom_prenom"] (champ réel).
    if not nom and not prenom:
        _np = (cerfa_rep.get("nom_prenom") or "").strip()
        if _np:
            # split(" ", 1) = prenom en premier, nom (composé possible) en second
            # Exemple : "Karim NAIT ALI" → prenom="Karim", nom="NAIT ALI" ✅
            # rsplit était incorrect : "Karim NAIT ALI" → prenom="Karim NAIT", nom="ALI" ❌
            _np_parts = _np.split(" ", 1)
            if len(_np_parts) == 2:
                prenom = _np_parts[0].strip()
                nom    = _np_parts[1].strip().upper()
            else:
                nom = _np.upper()
    if not ddn:
        ddn = (cerfa_rep.get("date_naissance") or ds.get("date_naissance") or "").strip()
        if ddn and "/" in ddn:
            _dp = ddn.split("/")
            if len(_dp) == 3:
                ddn_jour, ddn_mois, ddn_annee = _dp[0], _dp[1], _dp[2]
    if not adresse:
        adresse = (ds.get("adresse") or ds.get("adresse_beneficiaire") or "").strip()
    if not cp:
        cp = (ds.get("code_postal") or "").strip()
    if not commune:
        _comm_fb = (ds.get("commune") or "").strip()
        commune = _comm_fb.upper() if _comm_fb else commune
    # Fallback bloc adresse depuis cerfa_rep["adresse_complete"] si toujours vide
    if not adresse and not cp and not commune:
        _ac = (cerfa_rep.get("adresse_complete") or "").strip()
        if _ac:
            _ac_parts = [p.strip() for p in _ac.split(",")]
            if len(_ac_parts) >= 3:
                adresse = _ac_parts[0]
                cp      = re.sub(r'\D', '', _ac_parts[1])[:5]
                commune = _ac_parts[2].upper()
            elif len(_ac_parts) == 2:
                adresse = _ac_parts[0]
                commune = _ac_parts[1].upper()
            else:
                adresse = _ac

    # CMI : interpréter la réponse textuelle "priorité / stationnement / les deux"
    _cmi_rep = (cerfa_rep.get("cmi_type") or "").lower()
    _cmi_priorite_rep   = "priorité" in _cmi_rep or "priorite" in _cmi_rep or "les deux" in _cmi_rep
    _cmi_stationnement_rep = "stationnement" in _cmi_rep or "les deux" in _cmi_rep

    # Urgence droits : "oui" → True
    _urgence_rep = (cerfa_rep.get("urgence_droits") or "").lower()
    _urgence_bool = any(w in _urgence_rep for w in ["oui", "yes", "1", "vrai"])

    # Emploi accompagné : "oui" ou "emploi accompagné" → True
    _ea_rep = (cerfa_rep.get("emploi_accompagne") or "").lower()
    _ea_bool = any(w in _ea_rep for w in ["oui", "accompagné", "accompagne", "yes", "ea "])

    # Protection juridique depuis WhatsApp
    _prot_rep = (cerfa_rep.get("protection_juridique") or "").lower()

    # Détection is_enfant : ds > déduction depuis ddn > True (défaut conservateur)
    _is_enfant_ds = ds.get("is_enfant")
    if _is_enfant_ds is not None:
        is_enfant = bool(_is_enfant_ds)
    elif ddn and "/" in ddn:
        try:
            _ddn_parts = ddn.split("/")
            if len(_ddn_parts) == 3:
                _dj, _dm, _da = int(_ddn_parts[0]), int(_ddn_parts[1]), int(_ddn_parts[2])
                is_enfant = (date.today() - date(_da, _dm, _dj)).days // 365 < 18
            else:
                is_enfant = True
        except Exception:
            is_enfant = True
    else:
        is_enfant = True  # inconnu : défaut conservateur
    genre                  = (ds.get("genre") or cerfa_rep.get("genre") or "").lower()
    # CORRECTION 3 — La réponse WhatsApp de la famille prime sur l'analyse IA pour
    # situation_familiale. La famille connaît sa situation mieux que l'IA qui déduit
    # depuis un bilan souvent ancien. cerfa_rep > ds.
    situation_familiale    = (cerfa_rep.get("situation_familiale") or ds.get("situation_familiale") or "").lower()
    vie_seule              = ds.get("vie_seule", False)
    a_enfants_charge       = ds.get("a_enfants_charge", False)
    # La réponse WhatsApp de la famille PRIME sur l'analyse IA pour ce champ.
    # Si la famille a dit "0" ou "aucun", on écrase même si l'IA a dit True.
    _enfants_rep = (cerfa_rep.get("enfants_a_charge") or "").strip().lower()
    _nb_enfants_reel: int | None = None   # FIX 3b : nombre réel pour champ texte PDF
    if _enfants_rep:
        _pas_enfants = any(w in _enfants_rep for w in ["0", "aucun", "non", "pas d", "zéro", "zero", "personne"])
        if _pas_enfants:
            a_enfants_charge = False
            _nb_enfants_reel = 0
        else:
            a_enfants_charge = True
            # Extraire le nombre si l'usager l'a donné explicitement (ex: "4 enfants")
            import re as _re_enf
            _match_nb = _re_enf.search(r'\b(\d+)\b', _enfants_rep)
            if _match_nb:
                _nb_enfants_reel = int(_match_nb.group(1))
    situation_pro          = (ds.get("situation_professionnelle") or cerfa_rep.get("situation_pro_scolaire") or "").lower()
    nom_employeur          = ds.get("nom_employeur") or ""
    poste_occupe           = ds.get("poste_occupe") or ""
    projet_professionnel   = ds.get("projet_professionnel") or ""
    aides_actuelles        = ds.get("aides_actuelles") or []
    besoins_aide_humaine   = ds.get("besoins_aide_humaine", False)
    besoins_aide_technique = ds.get("besoins_aide_technique", False)
    besoins_amenagement    = ds.get("besoins_amenagement_logement", False)
    type_logement          = (ds.get("type_logement") or "").lower()
    statut_logement        = (ds.get("statut_logement") or "").lower()
    # CORRECTION 2 — NSS : chercher dans dossier (interface) > ds (IA) > cerfa_rep (WhatsApp)
    # L'interface permet à l'éducateur de saisir le NIR directement → source la plus fiable.
    # Niveau de confiance ÉLEVÉ si trouvé dans dossier ou ds → ne pas redemander.
    nss = (
        dossier.get("numero_securite_sociale")
        or dossier.get("nss")
        or ds.get("nss")
        or ds.get("numero_securite_sociale")
        or cerfa_rep.get("numero_securite_sociale")
        or ""
    ).replace(" ", "").replace(".", "").replace("-", "")
    nss_parent = (ds.get("nss_parent") or "").replace(" ", "").replace(".", "")

    # BUG 4 CORRIGÉ : la réponse WhatsApp de la famille prime sur l'analyse IA pour type_demande.
    # Avant : ds.type_demande écrasait cerfa_rep["type_demande"] → si l'IA avait analysé "première
    # demande" mais la famille dit "renouvellement" sur WhatsApp, c'était la version IA qui gagnait.
    # Après : cerfa_rep > ds. L'IA reste un fallback si la famille n'a pas répondu.
    _type_demande_rep    = (cerfa_rep.get("type_demande") or "").lower()
    # Normalisation accents pour la comparaison métier (ex : "clôturé" → "cloture")
    import unicodedata as _ud
    def _sans_accents(s: str) -> str:
        return "".join(c for c in _ud.normalize("NFD", s) if _ud.category(c) != "Mn")
    _historique_mdph_rep = _sans_accents((cerfa_rep.get("historique_mdph") or "").lower())
    type_demande         = (_type_demande_rep or ds.get("type_demande") or "").lower()
    deja_connu_mdph      = bool(ds.get("deja_connu_mdph", False))

    # ── Règle métier MDPH — Statut administratif "déjà connu MDPH" ──────────
    # Principe : ne pas déduire de la non-vacuité du champ.
    # Raisonner uniquement sur le statut administratif réel de la personne.
    #
    # OUI  → a déjà eu un dossier, une décision, un droit (même expiré/clôturé)
    # NON  → première demande explicite
    # Vide → ambigu ou non renseigné → ne rien cocher
    if not deja_connu_mdph and _historique_mdph_rep:
        _MOTS_CONNU_MDPH = {
            # Situations explicites de connaissance MDPH
            "déjà", "deja", "ancien", "ancienne", "antérieur", "anterieur",
            "précédent", "precedent", "renouvell", "révision", "revision",
            "réexamen", "reexamen", "recours", "dossier", "numéro", "numero",
            # Droits ou orientations passés
            "aah", "rqth", "aeeh", "pch", "cmpp", "esat", "ime", "sessad",
            "orientation", "notification", "décision", "decision", "accord",
            "attribué", "attribue", "obtenu", "accordé", "accorde",
            # Temporalité passée liée à la MDPH
            "clôturé", "cloture", "expiré", "expire", "périmé", "perime",
            "suivi", "suivie", "accompagné", "accompagnee",
            "oui",
        }
        _MOTS_PREMIERE_DEMANDE = {
            "première", "premiere", "1ère", "1ere", "1re",
            "premier", "jamais", "aucun", "aucune",
            "pas de dossier", "pas encore", "jamais eu",
            "jamais déposé", "jamais depose",
            "aucune demande", "aucun dossier",
            "jamais sollicité", "jamais sollicite",
            "non",
        }
        # Un numéro de dossier (5+ chiffres) = connue de la MDPH
        _has_numero = bool(re.search(r'\b\d{5,}\b', _historique_mdph_rep))
        _has_oui    = any(w in _historique_mdph_rep for w in _MOTS_CONNU_MDPH)
        _has_non    = any(w in _historique_mdph_rep for w in _MOTS_PREMIERE_DEMANDE)

        if _has_numero:
            deja_connu_mdph = True       # numéro de dossier = connue MDPH sans ambiguïté
        elif _has_oui and not _has_non:
            deja_connu_mdph = True       # signaux positifs sans signal négatif
        elif _has_non:
            deja_connu_mdph = False      # première demande explicite
        # else: ambigu ou non interprétable → ne pas cocher (deja_connu_mdph reste False)
    # Si le type de demande signifie renouvellement/réévaluation/changement → personne déjà connue.
    # BUG 3 (partiel) : on utilise une détection souple (sous-chaîne) au lieu d'un test d'égalité exacte,
    # cohérente avec la normalisation appliquée plus bas lors du cochage des cases P1.
    _td_connu_check = type_demande.replace("_", " ")
    if not deja_connu_mdph and any(w in _td_connu_check for w in (
        "renouvell", "rééval", "reeval", "revision", "révision",
        "changement", "situation chang",
    )):
        deja_connu_mdph = True
    # BUG 1 CORRIGÉ : le champ WhatsApp s'appelle "historique_mdph" (pas "numero_dossier_mdph").
    # On cherche d'abord dans ds, puis dans cerfa_rep["historique_mdph"] (valeur brute WhatsApp).
    numero_dossier_mdph = (ds.get("numero_dossier_mdph") or cerfa_rep.get("historique_mdph") or "")
    # Si la valeur brute contient du texte autour du numéro, extraire la séquence la plus longue.
    # On privilégie les suites >= 5 chiffres (vrais numéros de dossier) pour éviter de capturer une année.
    if numero_dossier_mdph:
        _candidats = re.findall(r'\b(\d{5,12})\b', numero_dossier_mdph)
        if _candidats:
            numero_dossier_mdph = max(_candidats, key=len)   # prend la suite la plus longue
        elif not re.search(r'\d', numero_dossier_mdph):
            numero_dossier_mdph = ""   # aucun chiffre → pas de numéro exploitable
    # CORRECTION 1 — Cohérence numéro de dossier / type de demande (renforcée)
    # Vérifier AUSSI les champs de l'interface éducateur (dossier.*), qui sont
    # la source la plus fiable et peuvent contenir le numéro MDPH avant tout dialogue.
    _num_mdph_interface_filler = (
        dossier.get("numero_mdph")
        or dossier.get("historique_mdph")
        or dossier.get("numero_dossier_mdph")
        or ""
    ).strip()
    if _num_mdph_interface_filler and not numero_dossier_mdph:
        # Extraire le numéro depuis le champ interface
        _candidats_if = re.findall(r'\b(\d{5,12})\b', _num_mdph_interface_filler)
        if _candidats_if:
            numero_dossier_mdph = max(_candidats_if, key=len)
            deja_connu_mdph = True
    _mots_premiere = ["premiere", "première", "1ere", "1ère", "1re", "premier", "jamais", "nouveau"]
    if numero_dossier_mdph:
        _est_marquee_premiere = any(w in type_demande for w in _mots_premiere)
        if _est_marquee_premiere:
            logger.warning(
                f"[CERFA C1] Incohérence détectée : numéro dossier présent ({numero_dossier_mdph!r}) "
                f"mais type_demande={type_demande!r}. Correction forcée → 'renouvellement'."
            )
            type_demande = "renouvellement"
        elif not type_demande:
            type_demande = "renouvellement"

    # urgence_droits et procedure_simplifiee : calculés après la lecture de cerfa_rep ci-dessous

    # Identité complémentaire
    # Règle 3 — pas de nationalité française par défaut sans source explicite
    nationalite            = (ds.get("nationalite") or cerfa_rep.get("nationalite") or dossier.get("nationalite") or "").lower()
    commune_naissance      = ds.get("commune_naissance") or ""
    departement_naissance  = ds.get("departement_naissance") or ""
    pays_naissance         = (ds.get("pays_naissance") or "").strip()  # pas de défaut "France"
    nom_usage              = ds.get("nom_usage") or ""
    organisme_payeur       = (ds.get("organisme_payeur") or cerfa_rep.get("organisme_payeur") or "").lower()
    numero_allocataire     = ds.get("numero_allocataire") or ""
    organisme_assurance    = (ds.get("organisme_assurance_maladie") or "cpam").lower()
    # Protection juridique — V3 : lecture depuis SituationJuridique.type_mesure
    if _dv2 and _dv2.section_a.situation_juridique.type_mesure != "aucune":
        _sj = _dv2.section_a.situation_juridique
        protection_juridique = _sj.type_mesure
        _rep = _sj.identite_representant
        if _rep:
            _nom_rep_v2    = _rep.nom or ""
            _prenom_rep_v2 = _rep.prenom or ""
            _qualite_v2    = _rep.qualite or ("Tuteur" if "tutelle" in _sj.type_mesure else "Curateur")
        else:
            _nom_rep_v2 = _prenom_rep_v2 = _qualite_v2 = ""
    else:
        protection_juridique = (ds.get("protection_juridique") or cerfa_rep.get("protection_juridique") or "aucune").lower()
        _nom_rep_v2 = _prenom_rep_v2 = _qualite_v2 = ""

    # CMI nuances (expert) — cases distinctes dans le CERFA
    # Priorité : ds > WhatsApp réponse textuelle cmi_type
    cmi_priorite      = ds.get("cmi_priorite") or _cmi_priorite_rep
    cmi_stationnement = ds.get("cmi_stationnement") or _cmi_stationnement_rep

    # Emploi accompagné (sous-option ORP marché du travail)
    emploi_accompagne = ds.get("emploi_accompagne") or _ea_bool

    # Creton (jeune adulte >20 maintenu en structure enfants)
    creton            = ds.get("creton", False)

    # Urgence droits — V3 : valeur dans Section_Urgence.est_urgent (False par défaut).
    if _dv2:
        urgence_droits = _dv2.section_urgence.est_urgent   # bool — False par défaut dans le modèle
    else:
        _urgence_rep_raw = (cerfa_rep.get("urgence_droits") or "").lower()
        _urgence_explicitement_non = any(
            w in _urgence_rep_raw
            for w in ["non", "no", "0", "faux", "false", "n/a", "pas d", "aucune", "première"]
        )
        if _urgence_explicitement_non:
            urgence_droits = False
        else:
            urgence_droits = ds.get("urgence_droits") or _urgence_bool
    procedure_simplifiee = ds.get("procedure_simplifiee", False)

    # Ressources et frais liés au handicap (section B1)
    ressources_actuelles = (
        ds.get("ressources_actuelles")
        or cerfa_rep.get("ressources_actuelles")
        or ""
    )
    frais_handicap = ds.get("frais_handicap") or ""

    # Consentement partage informations (page 4)
    consentement = ds.get("consentement_informations", True)

    # Données fonctionnelles (WhatsApp → ds ou réponse directe)
    difficultes_quotidiennes = (
        ds.get("difficultes_quotidiennes")
        or cerfa_rep.get("difficultes_quotidiennes")
        or ""
    )
    besoins_aide_str = (
        ds.get("besoins_aide_narrative")
        or ds.get("besoins_aide")
        or cerfa_rep.get("besoins_aide")
        or ""
    )

    # Protection juridique : ds > WhatsApp
    if not protection_juridique or protection_juridique == "aucune":
        if _prot_rep:
            if "tutelle" in _prot_rep:
                protection_juridique = "tutelle"
            elif "curatelle" in _prot_rep:
                protection_juridique = "curatelle"
            elif "sauvegarde" in _prot_rep:
                protection_juridique = "sauvegarde"

    # ── Données accident du travail / ESRP ──────────────────────────────────
    # Règle 7 : accident_travail depuis toutes les sources
    accident_travail    = bool(
        ds.get("accident_travail")
        or cerfa_rep.get("accident_travail")
        or dossier.get("accident_travail")
    )
    date_at             = ds.get("date_accident_travail") or ""
    narratif_at         = (
        ds.get("narratif_accident_travail")
        or ds.get("contexte_at")
        or (f"Accident de travail survenu en {date_at[:4]}." if date_at else "")
        or ""
    )
    a_cible_esrp        = ds.get("a_cible_esrp", False)
    nom_esrp            = ds.get("nom_esrp") or ""
    type_formation_pro  = ds.get("type_formation_pro") or ""
    narratif_rehab      = ds.get("narratif_rehabilitation") or ds.get("contexte_at") or ""
    a_cap_emploi        = (
        ds.get("a_cap_emploi", False)
        or any("cap emploi" in (a or "").lower() for a in (aides_actuelles or []))
    )

    # ── Scolarité (P9-P12) ───────────────────────────────────────────────────
    scolarise              = ds.get("scolarise", False)   # JAMAIS déduit de is_enfant — doit être confirmé explicitement
    nom_ecole              = ds.get("nom_ecole") or ""
    classe_scolaire        = ds.get("classe_scolaire") or ""
    type_etablissement     = (ds.get("type_etablissement_scolaire") or "").lower()
    a_pps                  = ds.get("a_pps", False)
    a_pai                  = ds.get("a_pai", False)
    a_ulis                 = ds.get("a_ulis", False)
    classe_ordinaire       = ds.get("classe_ordinaire", True)

    # Enrichissement depuis la réponse WhatsApp "scolarite_details" (pour les mineurs)
    _scol_rep = (cerfa_rep.get("scolarite_details") or "").lower()
    if _scol_rep and is_enfant:
        scolarise = True   # si on a des détails de scolarité, la personne est bien scolarisée
        if not type_etablissement:
            for _et in ["ime", "sessad", "itep", "ulis", "spécialisé", "specialise", "uema", "uem"]:
                if _et in _scol_rep:
                    type_etablissement = _et
                    classe_ordinaire   = _et == "ulis"
                    break
        if not a_pps and "pps" in _scol_rep:
            a_pps = True
        if not a_pai and "pai" in _scol_rep:
            a_pai = True
        if not a_ulis and "ulis" in _scol_rep:
            a_ulis = True
        if not classe_scolaire:
            import re as _re
            _cls_m = _re.search(
                r"\b(cp|ce1|ce2|cm1|cm2|6e|6ème|5e|5ème|4e|4ème|3e|3ème|"
                r"2nde|seconde|1ère|terminale|bac pro|bts)\b", _scol_rep
            )
            if _cls_m:
                classe_scolaire = _cls_m.group(1).upper()

    # ── Situation professionnelle détaillée (P13-P16) ────────────────────────
    date_debut_emploi      = ds.get("date_debut_emploi") or ""
    type_contrat           = (ds.get("type_contrat") or "").lower()
    duree_hebdo            = ds.get("duree_hebdomadaire") or ""
    en_recherche_emploi    = ds.get("en_recherche_emploi", False)

    # inscrit_pole_emploi / France Travail
    # Règle : uniquement depuis clés booléennes structurées.
    # Suppression de la concaténation multi-sources et des recherches de sous-chaînes
    # ("ft ", "oui", "true" dans chaîne assemblée → trop de faux positifs).
    inscrit_pole_emploi = bool(
        ds.get("inscrit_pole_emploi")
        or cerfa_rep.get("inscrit_pole_emploi")
        or dossier.get("inscrit_pole_emploi")
        or ds.get("france_travail")
        or cerfa_rep.get("france_travail")
    )

    date_inscription_pe    = ds.get("date_inscription_pole_emploi") or ""

    # en_formation : clé structurée ou réponse explicite "oui" à la question dédiée.
    # Suppression de "formation" in situation_pro — le mot seul ne suffit pas.
    en_formation           = bool(
        ds.get("en_formation") or cerfa_rep.get("en_formation")
        or dossier.get("en_formation")
        or ds.get("qualification_section_c") == "oui"
    )
    nom_formation          = (ds.get("nom_formation") or cerfa_rep.get("formation_actuelle")
                               or dossier.get("type_formation_pro") or "")
    organisme_formation    = (ds.get("organisme_formation") or cerfa_rep.get("etablissement_formation")
                               or ds.get("etablissement_formation") or "")

    # a_deja_travaille : clé structurée ou déduction métier forte (AT confirmé).
    # Suppression de la liste de sous-chaînes dans situation_pro.
    # Règle : "cdd" dans un texte ne prouve pas une expérience passée.
    _a_deja_travaille_raw = (
        ds.get("a_deja_travaille") or cerfa_rep.get("a_deja_travaille")
        or dossier.get("a_deja_travaille")
    )
    if _a_deja_travaille_raw is False:
        _a_deja_travaille = False   # déclaration explicite "jamais travaillé" → respecter
    elif _a_deja_travaille_raw:
        _a_deja_travaille = True    # déclaration explicite "a travaillé" → respecter
    elif accident_travail:
        _a_deja_travaille = True    # déduction métier forte : AT confirmé = a travaillé
    else:
        _a_deja_travaille = False   # inconnu → ne pas cocher

    # Enrichissement depuis la réponse WhatsApp "qualification_parcours" (D1/D2)
    _qual_rep = (cerfa_rep.get("qualification_parcours") or "").lower()
    if _qual_rep:
        if not poste_occupe:
            # Essayer d'extraire le poste depuis la réponse
            import re as _re
            _poste_m = _re.search(r"\b(poste\s*:?\s*|emploi\s*:?\s*|métier\s*:?\s*|dernier\s+emploi\s*:?\s*)([^,/\n]{3,40})", _qual_rep)
            if _poste_m:
                poste_occupe = _poste_m.group(2).strip()
        if not nom_employeur:
            _emp_m = _re.search(r"\b(chez\s+|employeur\s*:?\s*)([A-Za-zÀ-ÿ][^,/\n]{2,35})", _qual_rep)
            if _emp_m:
                nom_employeur = _emp_m.group(2).strip()
        # Stocker dans projet_professionnel si pas encore défini (contexte D2/D3)
        if not projet_professionnel:
            projet_professionnel = cerfa_rep.get("qualification_parcours", "")[:200]

    # ── Logement / vie quotidienne (P5-P7) ───────────────────────────────────
    type_logement_detail   = (ds.get("type_logement") or "").lower()
    vie_en_couple          = ds.get("vie_en_couple", False)
    vie_en_famille         = ds.get("vie_en_famille", False)   # pas de défaut is_enfant — doit être confirmé
    logement_adapte        = ds.get("logement_adapte")
    statut_occupation      = (ds.get("statut_occupation") or "").lower()

    # Enrichissement depuis la réponse WhatsApp "type_logement_statut"
    # FIX 3c : cerfa_rep PRIME TOUJOURS sur ds pour le statut d'occupation.
    # La famille sait si elle est propriétaire — l'IA peut se tromper.
    _logement_rep = (cerfa_rep.get("type_logement_statut") or "").lower()
    if _logement_rep:
        if not type_logement_detail:
            for _tl_kw in ["maison", "appartement", "studio", "foyer", "chambre", "hlm", "hlt"]:
                if _tl_kw in _logement_rep:
                    type_logement_detail = _tl_kw
                    break
        # Override inconditionnelle : cerfa_rep (WhatsApp) écrase ds (IA)
        if any(w in _logement_rep for w in ["propriétaire", "proprietaire"]):
            statut_occupation = "proprietaire"
        elif "locataire" in _logement_rep:
            statut_occupation = "locataire"
        elif any(w in _logement_rep for w in ["hébergé", "heberge", "hébergée"]):
            statut_occupation = "heberge"
    # V3 : lecture directe depuis section_c.statut_occupation si disponible
    if _dv2 and _dv2.section_c.statut_occupation:
        statut_occupation = _dv2.section_c.statut_occupation

    # ── Aides humaines (P6) ──────────────────────────────────────────────────
    a_aide_soignante       = ds.get("a_aide_soignante", False)
    a_auxiliaire_vie       = ds.get("a_auxiliaire_vie", False)
    a_aide_menagere        = ds.get("a_aide_menagere", False)

    # ── Aidant familial (P19-P20) ───────────────────────────────────────────
    nom_aidant             = ds.get("nom_aidant") or cerfa_rep.get("nom_aidant") or ""
    prenom_aidant          = ds.get("prenom_aidant") or cerfa_rep.get("prenom_aidant") or ""
    lien_aidant            = ds.get("lien_aidant") or cerfa_rep.get("lien_aidant") or ""

    # Aidant collecté via WhatsApp — FIX P19-P20 : parsing robuste de aidant_identite.
    # Formats acceptés : "Prénom NOM, lien" | "NOM Prénom, lien" | "lien seul" | "personne"
    _aidant_identite_rep = (cerfa_rep.get("aidant_identite") or "").strip()
    _mots_absence_aidant = ["personne", "aucun", "non", "pas d", "seul", "seule", "n/a"]
    if _aidant_identite_rep and not any(m in _aidant_identite_rep.lower() for m in _mots_absence_aidant):
        _parts = _aidant_identite_rep.split(",", 1)
        _identite_raw = _parts[0].strip()
        _lien_raw     = _parts[1].strip() if len(_parts) > 1 else ""

        # Détection du lien si absent de la partie après virgule mais dans identite
        _liens_connus = {
            "mari": "époux", "époux": "époux", "conjoint": "conjoint",
            "femme": "épouse", "épouse": "épouse", "compagne": "compagne",
            "mère": "mère", "mere": "mère", "père": "père", "pere": "père",
            "fils": "fils", "fille": "fille", "frère": "frère", "soeur": "sœur",
        }
        if not _lien_raw:
            for _mot_lien, _lien_norm in _liens_connus.items():
                if _mot_lien in _identite_raw.lower():
                    _lien_raw = _lien_norm
                    # Retirer le mot lien de l'identité
                    _identite_raw = re.sub(
                        rf'\b{_mot_lien}\b', '', _identite_raw, flags=re.IGNORECASE
                    ).strip(" ,")
                    break

        # Extraction prénom / nom depuis l'identité nettoyée
        _nom_parts = _identite_raw.split(" ", 1)
        if len(_nom_parts) >= 2:
            prenom_aidant = prenom_aidant or _nom_parts[0].strip()
            nom_aidant    = nom_aidant    or _nom_parts[1].strip()
        elif _nom_parts and _nom_parts[0]:
            nom_aidant = nom_aidant or _nom_parts[0].strip()

        lien_aidant = lien_aidant or _lien_raw

    # Détection aidant depuis la réponse WhatsApp "besoins_aide"
    _besoins_aide_rep_txt  = (cerfa_rep.get("besoins_aide") or "").lower()
    _a_aidant_confirme     = (
        bool(nom_aidant)
        or bool(_aidant_identite_rep)
        or ds.get("a_aidant_quotidien", False)
        or any(w in _besoins_aide_rep_txt for w in [
            "quelqu'un", "ma femme", "mon mari", "mon conjoint", "ma mère", "mon père",
            "mes enfants", "ma fille", "mon fils", "aidé par", "aide de", "avec l'aide",
        ])
    )

    # CORRECTION 6 — E1/E2 obligatoires quand aide humaine confirmée
    # Règle MDPH : un dossier sans E1/E2 remplis alors qu'une aide humaine est décrite
    # est systématiquement renvoyé. On force _a_aidant_confirme dans ces cas :
    #   - Profil enfant → parent = aidant par défaut (E1/E2 obligatoires)
    #   - Aide humaine décrite dans besoins ou narration P8 → E1 obligatoire
    #   - MIXTE (jeune vivant chez parents) avec aide → E1/E2 obligatoires
    _aide_humaine_decrite = (
        besoins_aide_humaine
        or a_auxiliaire_vie
        or bool(nom_aidant)
        or bool(_aidant_identite_rep)
        or any(w in _besoins_aide_rep_txt for w in [
            "quelqu'un", "ma femme", "mon mari", "mon conjoint", "ma mère", "mon père",
            "mes enfants", "ma fille", "mon fils", "aidé par", "aide de", "avec l'aide",
        ])
    )
    _aidant_temps_partiel = ds.get("aidant_reduction_travail", False)

    # Profil enfant : E1/E2 toujours nécessaires (parent = aidant naturel)
    if is_enfant and not _a_aidant_confirme:
        _a_aidant_confirme = True

    # Aide humaine décrite → E1 obligatoire
    if _aide_humaine_decrite and not _a_aidant_confirme:
        _a_aidant_confirme = True

    # Réduction de travail aidant confirmée
    if _aidant_temps_partiel and not nom_aidant:
        _a_aidant_confirme = True

    # Alerte si E1/E2 vides alors qu'une aide est décrite
    if _a_aidant_confirme and not nom_aidant:
        logger.warning(
            "[CERFA C6] Aide humaine confirmée mais identité aidant (E2) non collectée. "
            "Pages 19-20 partiellement vides — risque de renvoi MDPH. "
            "Vérifier que la question 'aidant_identite' a bien été posée via WhatsApp."
        )

    # Tranche d'âge — détermine les sections applicables du formulaire
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

    # ── Description P8 (narrative humanisée — structure : situation → retentissements) ──
    # Le projet professionnel est EXCLU de B8 — il figure UNIQUEMENT en D3 (page 16).
    # B8 = difficultés fonctionnelles et retentissements dans la vie quotidienne.
    description_situation = _composer_description_p8(
        geva_pro=geva_pro,
        juriste=juriste,
        elements_probants=elements_probants,
        is_enfant=is_enfant,
        projet_professionnel="",   # ← intentionnellement vide : projet pro = section D3
        difficultes_quotidiennes=difficultes_quotidiennes,
        besoins_aide=besoins_aide_str,
        prenom=prenom,
        nom=nom,
    )

    # ── Droits → liste de cases P17/P18 ─────────────────────────────────────
    cases_droits = _mapper_droits(
        droits,
        is_enfant=is_enfant,
        besoins_aide_humaine=besoins_aide_humaine,
        cmi_priorite=cmi_priorite,
        cmi_stationnement=cmi_stationnement,
        emploi_accompagne=emploi_accompagne,
        creton=creton,
    )

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 1 — Département et type de demande
    # ════════════════════════════════════════════════════════════════════════
    champs["Champ de texte P1 1"] = dept

    # Nature de la demande :
    #   P1 A = "C'est ma première demande à la MDPH"
    #   P1 B = "Ma situation a changé (médicale/administrative/familiale)"
    #   P1 C = "Je souhaite une réévaluation / révision de mes droits"
    #   P1 1 = "Je souhaite le renouvellement de mes droits à l'identique"
    #            ↑ Procédure simplifiée : UNIQUEMENT si renouvellement SANS réexamen
    #              et urgence droits (expire dans <2 mois)
    #   P1 2 = "Votre aidant familial souhaite exprimer sa situation"
    #   P1 3 = "Vous avez déjà un dossier à la MDPH ? OUI"
    # Inférence : si personne déjà connue de la MDPH mais type non précisé → réévaluation
    if not type_demande and deja_connu_mdph:
        type_demande = "reevaluation"

    # BUG 3 CORRIGÉ : normalisation de type_demande avant les tests.
    # Avant : seules les formes courtes ("premiere", "première") étaient reconnues.
    # Le LLM peut extraire "première demande", "premiere_demande", "renouveler les droits", etc.
    # → On normalise en remplaçant underscores et en testant la présence de mots-clés.
    _td_norm = type_demande.replace("_", " ").replace("-", " ")
    _is_premiere = any(w in _td_norm for w in [
        "première", "premiere", "1ere", "1ère", "1re", "premier", "jamais", "nouveau",
    ]) and not any(w in _td_norm for w in ["renouvell", "rééval", "reeval", "revision"])
    _is_renouvellement = any(w in _td_norm for w in ["renouvell", "renouveler"])
    _is_reevaluation   = any(w in _td_norm for w in ["rééval", "reeval", "révision", "revision"])
    _is_changement     = any(w in _td_norm for w in ["changement", "situation_changee", "situation changée", "situation changee"])

    if _is_premiere:
        cases.append("Case à cocher P1 A")
    elif _is_changement:
        cases.append("Case à cocher P1 B")
    elif _is_reevaluation:
        cases.append("Case à cocher P1 C")
    elif _is_renouvellement or type_demande == "renouvellement":
        # FIX 3d : décochage explicite de P1 A au niveau des octets PDF
        # (le template peut avoir P1 A coché par défaut → on force /Off)
        _decocher_case(writer, "Case à cocher P1 A")
        if procedure_simplifiee or urgence_droits:
            cases.append("Case à cocher P1 1")   # Renouvellement à l'identique (simplifié)
        else:
            cases.append("Case à cocher P1 C")   # Réévaluation (renouvellement avec révision)
    # Si type_demande inconnu → aucune case cochée (pas de défaut "première demande")

    # Déjà connu de la MDPH — utilise deja_connu_mdph (déjà normalisé ci-dessus)
    if deja_connu_mdph:
        cases.append("Case à cocher P1 3")
        if numero_dossier_mdph:
            champs["Champ de texte P 1 2"] = numero_dossier_mdph

    # Aidant familial (P1 2) — cocher UNIQUEMENT si l'aidant a un NOM ou des besoins documentés.
    # NE PAS cocher si seulement "aidant_demande=True" sans données — évite les faux positifs.
    if nom_aidant or (lien_aidant and (ds.get("aidant_besoins") or cerfa_rep.get("aidant_besoins"))):
        cases.append("Case à cocher P1 2")

    # POINT 4 — Traitement rapide (urgence)
    # Cocher si : urgence droits explicite OU situation de logement critique
    _logement_critique = any(x in (type_logement_detail or "").lower() for x in [
        "sans domicile", "sans abri", "sdf", "urgence", "expulsion", "ne peut plus vivre",
    ])
    if urgence_droits or _logement_critique:
        cases.append("Case à cocher P1 urgence")

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 2 — Identité complète de la personne
    # ════════════════════════════════════════════════════════════════════════
    champs["Champ de texte P2 1"]  = nom           # Nom de naissance
    # Nom d'usage : uniquement si différent du nom de naissance, non vide,
    # et sans placeholder d'anonymisation (ex. [USAGER_1]) ni égal au prénom
    _nom_usage_clean = (nom_usage or "").strip()
    if (
        _nom_usage_clean
        and not re.search(r'\[USAGER_\d+\]|\[USER_\d+\]|\[BENEFICIAIRE\]', _nom_usage_clean, re.I)
        and _nom_usage_clean.upper() != prenom.upper()
        and _nom_usage_clean.upper() != nom.upper()
    ):
        champs["Champ de texte P2 2"] = _nom_usage_clean
    champs["Champ de texte P2 3"]  = prenom        # Prénoms
    # Date de naissance
    champs["Date A 1"] = ddn_jour
    champs["Date A 2"] = ddn_mois
    champs["Date A 3"] = ddn_annee
    # Lieu de naissance — uniquement si renseigné
    if commune_naissance:
        champs["Champ de texte P2 4"] = commune_naissance
        champs["Champ de texte P2 5"] = commune_naissance   # doublon parfois présent dans le PDF
    if departement_naissance:
        champs["Champ de texte P2 6"] = departement_naissance
    if pays_naissance and pays_naissance.lower() not in ("france", ""):
        champs["Champ de texte P2 Pays naisssance autre"] = pays_naissance

    # Préférence de contact MDPH (comment souhaitez-vous être contacté ?)
    _pref_contact = (ds.get("preference_contact") or cerfa_rep.get("preference_contact") or "").lower()
    if "email" in _pref_contact or "mail" in _pref_contact or "courriel" in _pref_contact:
        try:
            cases.append("Case à cocher P2 contact email")
        except Exception:
            pass
    elif "telephone" in _pref_contact or "téléphone" in _pref_contact or "tel" in _pref_contact:
        try:
            cases.append("Case à cocher P2 contact tel")
        except Exception:
            pass
    elif "courrier" in _pref_contact or "postal" in _pref_contact or "lettre" in _pref_contact:
        try:
            cases.append("Case à cocher P2 contact courrier")
        except Exception:
            pass
    # Adresse — mappings confirmés par inspection PDF corrigé
    champs["Champ de texte P2 8"]  = adresse        # Numéro + voie
    champs["Champ de texte P 2 9"] = commune        # Commune de domicile  ← "P 2 9" avec espace
    # Code postal : 5 chiffres individuels dans Champ de texte 17-21
    if cp:
        _cp_clean = (cp or "").replace(" ", "").replace("-", "")[:5]
        for _ci, _digit in enumerate(_cp_clean, start=17):
            champs[f"Champ de texte {_ci}"] = _digit
    # Email et téléphone (noms de champs confirmés sur le PDF original)
    champs["Champ de texte P2 11"] = email          # Courriel (P2 11)
    champs["Champ de texte 24"]    = telephone      # Téléphone (champ 24)
    # Organisme payeur — N° d'allocataire (CAF ou MSA)
    # Champ confirmé par inspection PDF : P2 13 (pas P2 14)
    if numero_allocataire:
        champs["Champ de texte P2 13"] = numero_allocataire

    # CORRECTION 2 — NIR : injection dans le PDF + warning de traçabilité
    # On re-vérifie toutes les sources au moment du remplissage (pas seulement à la lecture).
    # Priorité : interface (dossier) > IA (ds) > WhatsApp (cerfa_rep).
    _nss_interface = (
        dossier.get("numero_securite_sociale")
        or dossier.get("nss")
        or ""
    ).replace(" ", "").replace(".", "").replace("-", "")
    nss_clean = (_nss_interface or nss).replace(" ", "").replace(".", "").replace("-", "")

    if _nss_interface and not nss:
        # NIR trouvé dans l'interface mais absent de ds/cerfa_rep → le noter
        logger.info(f"[CERFA C2] NIR récupéré depuis l'interface éducateur : {_nss_interface[:4]}***")
    elif not nss_clean:
        # NIR absent de toutes les sources → warning pour le professionnel
        logger.warning(
            "[CERFA C2] NIR absent de toutes les sources (interface, ds, WhatsApp). "
            "Les cases N° SS resteront vides. Vérifier la saisie dans l'interface."
        )

    if nss_clean and nss_clean.isdigit():
        if is_enfant:
            for i, digit in enumerate(nss_clean[:15], start=1):
                champs[f"N° SS Enfant {i}"] = digit
        else:
            for i, digit in enumerate(nss_clean[:15]):
                champs[f"Numero SS {i + 3}"] = digit
        logger.info(f"[CERFA C2] NIR injecté en page 2 ({len(nss_clean)} chiffres, is_enfant={is_enfant})")

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 3 — Représentant légal / Protection juridique
    # ════════════════════════════════════════════════════════════════════════
    if is_enfant:
        # CORRECTION 4 (Sarah) — A2 : représentants légaux obligatoires pour un ENFANT.
        # Les champs REPRESENTANT LEGAL doivent contenir les PARENTS (pas l'enfant).
        # On cherche les infos parent dans ds > cerfa_rep > dossier (contact famille).
        _nom_parent    = (ds.get("nom_parent") or ds.get("nom_aidant") or "").strip()
        _prenom_parent = (ds.get("prenom_parent") or ds.get("prenom_aidant") or "").strip()
        _lien_parent   = (ds.get("lien_aidant") or "Père / Mère").strip()

        # Fallback : cerfa_reponses["aidant_identite"] = "Marie Dupont, mère"
        _aidant_id_rep = (cerfa_rep.get("aidant_identite") or "").strip()
        if _aidant_id_rep and not _nom_parent:
            _parts_aid = _aidant_id_rep.split(",", 1)
            _np_aid = _parts_aid[0].strip().split(" ", 1)
            if len(_np_aid) == 2:
                _prenom_parent = _prenom_parent or _np_aid[0]
                _nom_parent    = _nom_parent or _np_aid[1]
            elif _np_aid:
                _nom_parent = _nom_parent or _np_aid[0]
            if len(_parts_aid) > 1:
                _lien_parent = _parts_aid[1].strip() or _lien_parent

        # Règle : si le représentant légal n'est pas identifié → laisser vide.
        # INTERDIT : utiliser le nom ou le prénom de l'enfant comme fallback.
        _nom_rep_final    = _nom_parent    or ""
        _prenom_rep_final = _prenom_parent or ""

        champs["REPRESENTANT LEGAL 1"]  = _nom_rep_final
        champs["REPRESENTANT LEGAL 2"]  = _prenom_rep_final
        champs["REPRESENTANT LEGAL 3"]  = _lien_parent
        champs["REPRESENTANT LEGAL 6"]  = adresse
        champs["REPRESENTANT LEGAL 7"]  = cp
        champs["REPRESENTANT LEGAL 8"]  = commune
        champs["REPRESENTANT LEGAL 9"]  = telephone
        champs["REPRESENTANT LEGAL 10"] = email
        cases.append("Case à cocher P3 1")   # Titulaire autorité parentale

        if not _nom_parent:
            logger.warning(
                "[CERFA C4] Profil ENFANT : identité parent/représentant légal (A2) non collectée. "
                "Page 3 remplie avec les coordonnées de contact famille. "
                "Vérifier que la question 'aidant_identite' a bien été posée."
            )

        # NSS du parent déclarant (si différent du NSS bénéficiaire)
        nss_parent_clean = nss_parent.replace("-", "")
        if nss_parent_clean and nss_parent_clean.isdigit():
            try:
                champs["Champ de texte P3 NSS Parent"] = nss_parent_clean[:15]
            except Exception:
                pass

        # CORRECTION 4 (Sarah) — A4 : NE PAS remplir tutelle/curatelle si protection = aucune.
        # Pour la grande majorité des enfants → autorité parentale ordinaire, A4 vide.
        _prot_enfant = protection_juridique.lower().strip()
        if _prot_enfant and _prot_enfant not in ("aucune", "", "none", "non", "non concerné", "non concerné (enfant)"):
            if "tutelle" in _prot_enfant:
                cases.append("Case à cocher P3 4")
            elif "curatelle" in _prot_enfant:
                cases.append("Case à cocher P3 5")
            elif "sauvegarde" in _prot_enfant:
                cases.append("Case à cocher P3 6")
        # Si aucune protection juridique → A4 reste vide (comportement correct)
    else:
        # Adulte : agit seul ou sous mesure de protection
        if protection_juridique in ("aucune", "", "none", "non"):
            # Pas de mesure → cocher "agit seul" (P3 2)
            cases.append("Case à cocher P3 2")
        else:
            cases.append("Case à cocher P 3 3")   # Représentant désigné
            if "tutelle" in protection_juridique:
                cases.append("Case à cocher P3 4")
            elif "curatelle" in protection_juridique:
                cases.append("Case à cocher P3 5")
            elif "sauvegarde" in protection_juridique:
                cases.append("Case à cocher P3 6")
            # Nom du représentant légal — V2 : lecture directe depuis ProtectionJuridique.
            # Fallback hiérarchique : V2 > ds > cerfa_rep > aidant_identite.
            _nom_tuteur    = _nom_rep_v2 or ds.get("nom_tuteur") or ds.get("nom_representant") or ""
            _prenom_tuteur = _prenom_rep_v2 or ds.get("prenom_tuteur") or ""
            _qualite_rep   = _qualite_v2 or ("Tuteur" if "tutelle" in protection_juridique else "Curateur")
            if not _nom_tuteur:
                _ai_rep = (cerfa_rep.get("aidant_identite") or "").strip()
                if _ai_rep:
                    _ai_p = _ai_rep.split(",", 1)
                    _ai_n = _ai_p[0].strip().split(" ", 1)
                    _nom_tuteur    = _ai_n[1].strip() if len(_ai_n) == 2 else _ai_n[0].strip()
                    _prenom_tuteur = _ai_n[0].strip() if len(_ai_n) == 2 else ""
            if _nom_tuteur:
                champs["REPRESENTANT LEGAL 1"] = _nom_tuteur
                if _prenom_tuteur:
                    champs["REPRESENTANT LEGAL 2"] = _prenom_tuteur
                champs["REPRESENTANT LEGAL 3"] = _qualite_rep

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 4 — Situation personnelle, familiale
    # IMPORTANT : Signature laissée VIDE — signée par l'éducateur à l'impression
    # ════════════════════════════════════════════════════════════════════════
    # CORRECTION 5 (Sarah) — Page 4 situation familiale : jamais cochée pour un enfant.
    # Un enfant de 6 ans ne peut pas être "célibataire", "marié" ou "en couple".
    sit_fam_case = None
    if is_enfant:
        # Aucune case P4 0-5 pour un enfant — la rubrique ne le concerne pas
        logger.debug("[CERFA C5] Profil ENFANT → cases P4 situation familiale ignorées.")
    else:
        sf = situation_familiale
        # FIX 3a : vie_seule (déduit par l'IA) ne doit pas écraser une réponse WhatsApp explicite.
        # Si la famille a déclaré "marié" via WhatsApp, cerfa_rep["situation_familiale"] est non vide.
        _sf_vient_de_whatsapp = bool(cerfa_rep.get("situation_familiale"))
        if "celibataire" in sf or "célibataire" in sf or (
            vie_seule and not sf and not _sf_vient_de_whatsapp
        ):
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
    # NOTE : "a_enfants_charge" ne mappe PAS à P4 1 (= marié).
    # FIX 3b : si le nombre réel d'enfants est connu, l'écrire dans le champ texte P4.
    if _nb_enfants_reel is not None and _nb_enfants_reel > 0:
        try:
            champs["Champ de texte P4 enfants"] = str(_nb_enfants_reel)
        except Exception:
            pass   # champ absent du template → ignorer silencieusement

    # Consentement partage informations — géré via le radio OPTION P4 1 dans la section radios
    # (valeur /J'accepte ou /Je n'accepte pas — cochée via _cocher_option_nth plus bas)

    # Case de certification sur l'honneur (page 4) — toujours cochée
    # "En cochant cette case, je certifie sur l'honneur l'exactitude des informations"
    try:
        cases.append("Case à cocher P4 certification")
    except Exception:
        pass

    # Difficultés remplissage dossier médical — UNIQUEMENT si question posée et réponse "oui"
    _difficultes_med_rep = (cerfa_rep.get("difficultes_dossier_medical") or "").lower()
    if any(w in _difficultes_med_rep for w in ["oui", "yes", "difficile", "aide", "aidé"]):
        try:
            cases.append("Case à cocher P4 difficultes_med")
        except Exception:
            pass

    # Date de rédaction du dossier médical — remplir si connue
    date_dossier_medical = (
        ds.get("date_dossier_medical")
        or cerfa_rep.get("date_dossier_medical")
        or ""
    )
    # Date de rédaction : explicite > aujourd'hui (noms confirmés par inspection PDF)
    _date_p4 = date_dossier_medical or date.today().strftime("%d/%m/%Y")
    if _date_p4 and "/" in _date_p4:
        _dmed_parts = _date_p4.split("/")
        if len(_dmed_parts) == 3:
            champs["Date P4 1 "] = _dmed_parts[0]   # "Date P4 1 " — espace final obligatoire
            champs["Date P4 2"]  = _dmed_parts[1]
            champs["Date P4 3"]  = _dmed_parts[2]

    # NB : La signature reste VIDE — signée par l'éducateur à l'impression (expert Q33)

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 5 — Lieu de vie / Logement
    # Structure réelle du CERFA 15692 (confirmée par inspection PDF + corrigé) :
    #
    #  "Vous vivez :" (avec qui ?)
    #     P5 1 = Seul(e)
    #     P5 2 = En couple
    #     P5 3 = Avec vos parents (ou l'un d'entre eux)
    #     P5 4 = Avec vos enfants (ou l'un d'entre eux)
    #     P5 5 = Autre situation
    #
    #  "Où vivez-vous ?" (type de lieu)
    #     P5 6 = Vous avez un logement indépendant (maison, appartement, foyer...)
    #     P5 7 = Dans un établissement médico-social ou de soin
    #     P5 8 = Hébergé au domicile de vos parents (ou l'un d'eux)
    #     P5 9 = Hébergé au domicile d'un(e) ami(e)
    #     P5 10 = Hébergé au domicile de vos enfants (ou l'un d'eux)
    #     P5 11 = Hébergé au domicile d'un autre membre de la famille
    #
    #  Statut d'occupation → radio OPTION P5 2 (/Propriétaire | /Locataire | /Hébergé)
    #  Logement adapté     → radio OPTION P5 1 (/Oui | /Non)
    # ════════════════════════════════════════════════════════════════════════

    # CORRECTION 5 (Sarah) — Gardes d'âge STRICTES page 5
    # Un enfant < 16 ans ne peut PAS vivre en couple, être propriétaire ou locataire.
    # Ces cases seraient une erreur factuelle détectée immédiatement par l'instructeur MDPH.
    _age_p5 = None
    if ddn and "/" in ddn:
        try:
            _dp5 = ddn.split("/")
            if len(_dp5) == 3:
                _age_p5 = (date.today() - date(int(_dp5[2]), int(_dp5[1]), int(_dp5[0]))).days // 365
        except Exception:
            pass
    _est_mineur_strict = (_age_p5 is not None and _age_p5 < 16) or is_enfant

    # "Avec qui vivez-vous ?" (P5 1-5)
    tl = type_logement_detail
    # _en_etablissement : uniquement formulations précises du lieu de résidence.
    # Suppression : "établissement", "medico", "institution", "esat" seuls (trop larges).
    import unicodedata as _ucd
    _tl_sa = "".join(
        c for c in _ucd.normalize("NFD", tl.lower())
        if _ucd.category(c) != "Mn"
    )  # version sans accents pour comparaison robuste
    _en_etablissement = any(x in _tl_sa for x in [
        "foyer d hebergement", "foyer hebergement",
        "ehpad", "mas ", "maison d accueil specialisee",
        "fam ", "foyer d accueil medicalise",
        "ime residentiel", "esms",
        "heberge en etablissement", "residence en etablissement",
        "vit en etablissement",
    ])

    # _heberge_parents : uniquement formulations précises du domicile parental.
    # Suppression : "parents", "mère", "père", "famille" seuls (trop larges — faux positifs).
    # Mineur < 16 → chez ses parents SAUF si hébergé en établissement (détecté ci-dessus).
    _heberge_parents = any(x in _tl_sa for x in [
        "chez ses parents", "chez parents",
        "domicile parental", "domicile de ses parents",
        "heberge par ses parents", "heberge par ses parents",
        "chez sa mere", "chez son pere",
    ]) or (_est_mineur_strict and not _en_etablissement)
    _heberge_enfants  = any(x in tl for x in ["chez enfants", "hébergé enfants"])
    _heberge_ami      = any(x in tl for x in ["chez ami", "hébergé ami"])
    _heberge_famille  = any(x in tl for x in ["chez famille", "hébergé famille"])
    _sans_domicile    = any(x in tl for x in [
        "sans domicile", "sans abri", "sdf", "hébergement d'urgence", "urgence",
        "ne peut plus vivre", "expulsion", "foyer urgence",
    ])

    # Avec qui — gardes strictes pour mineur
    if _est_mineur_strict:
        # Enfant < 16 : TOUJOURS P5 3 (chez ses parents) — aucune exception
        cases.append("Case à cocher P5 3")
        if vie_en_couple or any(x in (situation_familiale or "") for x in ["marié", "pacsé", "concubinage"]):
            logger.error(
                f"[CERFA C5] Incohérence bloquée : mineur ({_age_p5} ans) marqué 'vie en couple'. "
                "Case P5 2 non cochée — forcé sur P5 3 (chez ses parents)."
            )
    else:
        if vie_seule and not is_enfant:
            cases.append("Case à cocher P5 1")
        elif vie_en_couple or any(x in (situation_familiale or "") for x in ["marié", "marie", "pacsé", "pacse", "concubinage"]):
            cases.append("Case à cocher P5 2")
        elif _heberge_parents:
            cases.append("Case à cocher P5 3")
        elif a_enfants_charge or vie_en_famille:
            cases.append("Case à cocher P5 4")
    # Pas de défaut adulte inconnu

    # "Où vivez-vous ?" (P5 6-11)
    if _sans_domicile:
        # Pas de case dédiée "sans domicile" dans le CERFA — on laisse vide et on note P5 5 (autre)
        cases.append("Case à cocher P5 5")
    elif _en_etablissement:
        cases.append("Case à cocher P5 7")
    elif _heberge_parents and is_enfant:
        cases.append("Case à cocher P5 8")   # Hébergé au domicile des parents
    elif _heberge_parents and not is_enfant:
        cases.append("Case à cocher P5 8")
    elif _heberge_enfants:
        cases.append("Case à cocher P5 10")
    elif _heberge_ami:
        cases.append("Case à cocher P5 9")
    elif _heberge_famille:
        cases.append("Case à cocher P5 11")
    elif statut_occupation or (type_logement_detail and not is_enfant) or logement_adapte is not None:
        cases.append("Case à cocher P5 6")
    # Enfant sans info logement → P5 8 déjà cochée via _heberge_parents=True

    # Statut d'occupation → géré via OPTION P5 2 dans la section radios ci-dessous

    # Accident du travail / Maladie professionnelle (P5 15)
    if accident_travail:
        cases.append("Case à cocher P5 15")   # AT/MP reconnu
        cases.append("Case à cocher P5 20")   # Indemnisation en cours / rente

    # Ressources actuelles (B1) — AAH, chômage, ASS, pension invalidité, AEEH, PCH, etc.
    # (les prestations sont bien des ressources — elles vont dans le champ "ressources", pas "frais")
    if ressources_actuelles:
        try:
            champs["Champ de texte P5 ressources"] = ressources_actuelles[:300]
        except Exception:
            pass

    # CORRECTION 4/6 — Frais liés au handicap (B1) : JAMAIS de prestations ni de mentions d'aidant.
    # CORRECTION 6 (Sarah) : renforcement — extraire les frais réels si contenu mixte.
    # FIX FRAIS/AIDANT : si frais_handicap mentionne un proche (mari, conjoint, époux, enfant…),
    # ce soutien doit être dans la section Aidant Familial (P19-P20), PAS dans les frais.
    # → On détecte ces mentions et on les redirige vers aidant_identite si absent.
    _mentions_aidant_dans_frais = [
        "mari", "conjoint", "époux", "épouse", "femme", "compagnon", "compagne",
        "aide de mon", "aide de ma", "soutenu par", "soutenue par",
        "accompagné par", "accompagnée par", "aidé par", "aidée par",
    ]
    if frais_handicap:
        _frais_lower_aidant = frais_handicap.lower()
        _mention_aidant_trouvee = next(
            (m for m in _mentions_aidant_dans_frais if m in _frais_lower_aidant), None
        )
        if _mention_aidant_trouvee:
            # Rediriger vers aidant si non déjà renseigné
            if not nom_aidant and not lien_aidant:
                # Tenter d'extraire un lien depuis la mention détectée
                _lien_deduit = {
                    "mari": "époux", "conjoint": "conjoint", "époux": "époux",
                    "épouse": "épouse", "femme": "épouse", "compagnon": "compagnon",
                    "compagne": "compagne",
                }.get(_mention_aidant_trouvee, "proche aidant")
                lien_aidant = lien_aidant or _lien_deduit
                logger.info(
                    f"[CERFA FIX-FRAIS] Mention d'aidant détectée dans frais_handicap "
                    f"({_mention_aidant_trouvee!r}) → redirigé vers lien_aidant={_lien_deduit!r}. "
                    f"La mention sera supprimée des frais."
                )
            # Supprimer la phrase contenant la mention de la valeur frais
            import re as _re_aidant
            _phrases_frais = _re_aidant.split(r'[,;.\n]', frais_handicap)
            _phrases_sans_aidant = [
                p for p in _phrases_frais
                if not any(m in p.lower() for m in _mentions_aidant_dans_frais)
            ]
            frais_handicap = ", ".join(p.strip() for p in _phrases_sans_aidant if p.strip())

    _prestations_interdites = [
        "aeeh", "pch", "aah", "actp", "acfp", "avpf", "rsa", "rqth",
        "allocation", "prestation", "complément", "majoration",
        "versé par la caf", "versé par la msa", "droits ouverts",
    ]
    _frais_reels_mots = [
        "psychologue", "orthophoniste", "ostéopath", "ergothérap", "kinésithérap",
        "matériel", "fauteuil", "aide auditive", "appareillage", "aménagement",
        "transport", "garde", "accompagnement", "non remboursé", "reste à charge",
    ]
    if frais_handicap:
        _frais_lower = frais_handicap.lower()
        _contient_prestation = any(p in _frais_lower for p in _prestations_interdites)
        _contient_frais_reels = any(f in _frais_lower for f in _frais_reels_mots)

        if _contient_prestation and _contient_frais_reels:
            # Contenu mixte → extraire uniquement les phrases avec des frais réels
            import re as _re_frais
            _phrases = _re_frais.split(r'[,;.\n]', frais_handicap)
            _phrases_filtrees = [
                p.strip() for p in _phrases
                if any(f in p.lower() for f in _frais_reels_mots)
                and not any(pr in p.lower() for pr in _prestations_interdites)
            ]
            frais_handicap = ", ".join(_phrases_filtrees) if _phrases_filtrees else ""
            logger.warning(
                f"[CERFA C6] frais_handicap mixte → extraction des frais réels. "
                f"Résultat : {frais_handicap!r}"
            )
        elif _contient_prestation and not _contient_frais_reels:
            # Uniquement des prestations → vider
            logger.warning(
                f"[CERFA C6] frais_handicap ne contient que des prestations → champ vidé. "
                f"Valeur originale : {frais_handicap!r}"
            )
            frais_handicap = ""

        if frais_handicap:
            try:
                champs["Champ de texte P5 frais"] = frais_handicap[:300]
            except Exception:
                pass

    # Besoins d'aide technique
    if besoins_aide_technique:
        cases.append("Case à cocher P5 22")

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 6 — Aides humaines et soins
    # ════════════════════════════════════════════════════════════════════════
    # Sources pour la détection des cases P6 (aides humaines et soins) :
    #   ✓ aides_actuelles : liste structurée des aides (source IA fiable)
    #   ✓ besoins_aide_str : réponse WhatsApp "besoins_aide" (confirmée par la famille)
    #   ✗ difficultes_quotidiennes : description narrative libre — volontairement exclue
    #     pour éviter les faux positifs (ex : "besoin d'aide non documenté" dans geva_pro
    #     déclencherait P6 7 même si l'aide humaine n'est pas confirmée).
    aides_str = " ".join(aides_actuelles).lower() if aides_actuelles else ""
    if besoins_aide_str:
        aides_str = f"{aides_str} {besoins_aide_str.lower()}"

    # Soins médicaux en cours — uniquement si soins médicaux réels confirmés
    # (pas juste des aides humaines ou scolaires)
    _has_soins_med = a_aide_soignante or any(
        x in aides_str for x in [
            "infirmier", "soin infirmier", "médecin à domicile",
            "kinésithérapie", "kiné", "traitement médical",
            "hospitalisation", "clinique", "suivi médical", "soin à domicile",
        ]
    )
    if _has_soins_med:
        cases.append("Case à cocher P6 1")
        has_lib  = any(x in aides_str for x in ["libéral", "liberal", "médecin libéral", "infirmier lib", "kiné libéral"])
        has_hosp = any(x in aides_str for x in ["hôpital", "hopital", "clinique", "hospitalier"])
        if has_lib:
            cases.append("Case à cocher P6 2")
        if has_hosp:
            cases.append("Case à cocher P6 3")
        if not has_lib and not has_hosp:
            cases.append("Case à cocher P6 4")

    # CORRECTION 3 — Aide humaine P6 7 alignée sur la narration P8
    # Le booléen besoins_aide_humaine (source IA) peut être faux même quand la narration
    # décrit clairement une dépendance. On étend la détection à description_situation
    # et difficultes_quotidiennes pour garantir la cohérence B1 ↔ texte.
    # ANTI-CONTAMINATION : ni le narratif généré P8 (description_situation) ni
    # difficultes_quotidiennes (aliasé sur texte_b par v2_bridge L234) ne servent
    # à cocher une case CERFA. Détection sur aides DÉCLARÉES uniquement.
    _texte_aide_humaine = " ".join(filter(None, [
        aides_str,
        (besoins_aide_str or "").lower(),
    ]))
    _mots_aide_humaine = [
        "aide humaine", "aide pour", "aidé par", "accompagné par", "quelqu'un l'aide",
        "auxiliaire de vie", "avs", "aide à domicile", "aide-soignant",
        "avec l'aide de", "besoin d'aide", "dépend de", "ne peut pas seul",
        "ne peut pas seule", "aide quotidienne", "accompagnement quotidien",
        "mère l'aide", "père l'aide", "parents l'aident", "famille l'aide",
    ]
    _a_aide_humaine_detectee = (
        besoins_aide_humaine
        or a_auxiliaire_vie
        or a_aide_menagere
        or any(x in _texte_aide_humaine for x in _mots_aide_humaine)
    )
    if _a_aide_humaine_detectee:
        cases.append("Case à cocher P6 7")
        if a_auxiliaire_vie or any(x in _texte_aide_humaine for x in ["auxiliaire", "avs", "aide humaine"]):
            cases.append("Case à cocher P6 9")
        cases.append("Case à cocher P6 8")

    # Tableau professionnels intervenants
    if aides_actuelles:
        for i, aide in enumerate(aides_actuelles[:3], start=1):
            row_start = (i - 1) * 5 + 1
            champs[f"Tableau P6 {row_start}"] = aide[:25]

    # CORRECTION 7 (Sarah) — AESH / SESSAD : routage vers scolarité, jamais vers B2.
    # B2 (P6 B1-B6) = gestes de la vie quotidienne (toilette, repas, mobilité...).
    # AESH = accompagnement scolaire → rubrique C1/P9-12 uniquement.
    # SESSAD = suivi médico-éducatif → C1 + éventuellement P10 accompagnements.
    # Ces sigles ne doivent PAS déclencher les cases B2 (P6 B1-B6).
    # On les retire du texte de détection B2 avant analyse.
    # ANTI-CONTAMINATION : description_situation (narratif P8) ET difficultes_quotidiennes
    # (aliasé sur texte_b par v2_bridge L234) RETIRÉS de la détection AVQ.
    # Source officielle des cases = avq_* structurés (Vague 1) + aides DÉCLARÉES.
    _detection_b2b3_brut = " ".join(filter(None, [
        aides_str,
        (besoins_aide_str or "").lower(),
    ]))
    # Supprimer les mentions AESH/SESSAD du texte de détection B2
    _aesh_sessad_pattern = r'\b(aesh|sessad|accompagnement scolaire|suivi sessad|avs scolaire)\b'
    import re as _re_b2
    _detection_b2b3 = _re_b2.sub(_aesh_sessad_pattern, "", _detection_b2b3_brut, flags=_re_b2.IGNORECASE)

    # ── ANTI-CONTAMINATION : la source OFFICIELLE des cases AVQ est constituée des
    #    champs structurés avq_* (Vague 1). Le déclaré (difficultes/besoins) reste un
    #    complément ; le narratif généré (P8) n'intervient plus dans la détection.
    _AVQ_BESOIN_AIDE = ("DIFFICULTE", "AIDE_PARTIELLE", "AIDE_TOTALE")
    def _avq_besoin(_champ: str) -> bool:
        return str(ds.get(_champ, "") or "").strip().upper() in _AVQ_BESOIN_AIDE

    # Toilette / hygiène
    if _avq_besoin("avq_toilette") or any(x in _detection_b2b3 for x in ["hygiène", "toilette", "bain", "douche", "lavage", "se laver", "aide pour se laver"]):
        cases.append("Case à cocher P6 B1")
    # Habillage
    if _avq_besoin("avq_habillage") or any(x in _detection_b2b3 for x in ["habillage", "vêtement", "vêtir", "s'habill", "aide pour s'habill"]):
        cases.append("Case à cocher P6 B2")
    # Repas / manger
    if _avq_besoin("avq_repas") or any(x in _detection_b2b3 for x in ["repas", "alimentation", "manger", "nutrition", "préparer", "cuisine", "aide pour manger"]):
        cases.append("Case à cocher P6 B3")
    # Mobilité intérieure (B4)
    if _avq_besoin("avq_deplacements") or any(x in _detection_b2b3 for x in ["mobilité", "déplacement", "marche", "fauteuil", "déplacer", "se lever", "se déplace"]):
        cases.append("Case à cocher P6 B4")
    # Sorties / extérieur
    if any(x in _detection_b2b3 for x in ["extérieur", "sortie", "courses", "promenade", "accompagné", "ne sort pas seul"]):
        cases.append("Case à cocher P6 B5")
    # Communication
    if any(x in _detection_b2b3 for x in ["communication", "langage", "parole", "comprendre", "s'exprimer", "verbal"]):
        cases.append("Case à cocher P6 B6")

    if besoins_aide_humaine and aides_actuelles:
        champs["Champ de texte P6 7"] = "; ".join(aides_actuelles)[:200]

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 7 — Vie quotidienne : mobilité, transports, communication
    # ════════════════════════════════════════════════════════════════════════
    # Mobilité dans le logement — uniquement si information confirmée
    if besoins_aide_humaine or any(x in aides_str for x in ["fauteuil roulant", "déambulateur", "canne", "aide à la mobilité"]):
        cases.append("Case à cocher P7 2")
    elif any(x in aides_str for x in ["se déplace seul dans", "autonome dans le logement", "marche normalement"]):
        cases.append("Case à cocher 356")
    # Pas de défaut

    # Mobilité hors logement — uniquement si information confirmée
    if any(x in aides_str for x in ["fauteuil roulant", "béquille", "aide pour sortir", "ne sort pas seul", "accompagné dehors"]):
        cases.append("Case à cocher P7 5")
    elif any(x in aides_str for x in ["sort seul", "autonome extérieur", "se déplace sans aide hors"]):
        cases.append("Case à cocher P7 4")
    # Pas de défaut

    # Transports — uniquement si information confirmée
    if any(x in aides_str for x in ["voiture personnelle", "véhicule adapté", "conduit lui-même"]):
        cases.append("Case à cocher P7 9")
    elif any(x in aides_str for x in ["vsl", "ambulance", "taxi médical", "transport adapté", "transport médical"]):
        cases.append("Case à cocher P7 14")
    elif any(x in aides_str for x in ["transports en commun", "bus", "métro", "train seul", "utilise les transports"]):
        cases.append("Case à cocher P7 8")
    # Pas de défaut

    # Communication — uniquement si information confirmée
    if any(x in aides_str for x in ["autisme", "non verbal", "communication augmentative", "cécité", "surdité profonde"]):
        cases.append("Case à cocher P7 18")
    elif any(x in aides_str for x in ["difficultés de communication", "trouble du langage", "dysphasie", "aphasie", "mutisme"]):
        cases.append("Case à cocher P7 16")
    elif any(x in aides_str for x in ["communique normalement", "pas de trouble communication", "expression orale normale"]):
        cases.append("Case à cocher P7 15")
    # Pas de défaut

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 8 — Description de la situation et des difficultés
    # Structure : situation actuelle → retentissements fonctionnels → projets de vie
    # ════════════════════════════════════════════════════════════════════════
    if description_situation:
        champs["Champ de texte P8 1"] = description_situation[:2000]

    # ════════════════════════════════════════════════════════════════════════
    # PAGES 9-12 — Scolarité (enfants et jeunes majeurs en formation initiale)
    # Expert Q18 : REMPLISSAGE AUTOMATIQUE pour les checkboxes C2
    # ════════════════════════════════════════════════════════════════════════
    # POINT 6 — Cohérence âge / niveau scolaire
    _age_reel = None
    if ddn and "/" in ddn:
        try:
            _dp = ddn.split("/")
            if len(_dp) == 3:
                _age_reel = (date.today() - date(int(_dp[2]), int(_dp[1]), int(_dp[0]))).days // 365
        except Exception:
            pass
    _niveaux_primaires = ["cp", "ce1", "ce2", "cm1", "cm2", "maternelle", "ps", "ms", "gs"]
    _scol_incoherent = (
        _age_reel is not None and _age_reel >= 18
        and any(n in (classe_scolaire or "").lower() or n in (type_etablissement or "").lower()
                for n in _niveaux_primaires)
    )
    if _scol_incoherent:
        logger.warning(
            f"[CERFA P9] Incohérence âge/scolarité ignorée | âge={_age_reel} ans "
            f"| classe={classe_scolaire!r} | établissement={type_etablissement!r}"
        )
    if age_tranche in ("enfant", "jeune_majeur") and scolarise and not _scol_incoherent:
        # Type d'établissement scolaire (C1)
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
            cases.append("Case à cocher P 9 3")   # Défaut : primaire

        # CORRECTION 8 (Sarah) — Nom de l'établissement : utiliser le nom EXACT.
        # Ne jamais écrire "établissement" de manière générique.
        # Sources : cerfa_rep["nom_ecole"] (WhatsApp) > ds > scolarite_details (parsing).
        _nom_ecole_rep = (cerfa_rep.get("nom_ecole") or "").strip()
        _nom_ecole_ds  = (ds.get("nom_ecole") or "").strip()
        # Essayer d'extraire un nom depuis scolarite_details si nom_ecole vide
        _nom_ecole_final = _nom_ecole_rep or _nom_ecole_ds or nom_ecole or ""
        if not _nom_ecole_final:
            import re as _re_ecole
            _scol_rep_c8 = (cerfa_rep.get("scolarite_details") or "").strip()
            _ecole_match = _re_ecole.search(
                r'(?:école|ecole|établissement|IME|SESSAD|ULIS|collège|lycée)\s+([A-ZÀ-ÿa-z][^,\n]{3,60})',
                _scol_rep_c8, _re_ecole.IGNORECASE
            )
            if _ecole_match:
                _nom_ecole_final = _ecole_match.group(0).strip()

        if _nom_ecole_final and _nom_ecole_final.lower() not in ("établissement", "etablissement", "école", "ecole"):
            champs["Champ de texte P9 1"] = _nom_ecole_final[:100]
        elif is_enfant:
            logger.warning(
                "[CERFA C8] Profil ENFANT scolarisé : nom de l'établissement scolaire absent. "
                "La question 'nom_ecole' doit être posée via WhatsApp."
            )
        if classe_scolaire:
            champs["Champ de texte P9 2"] = classe_scolaire

        # CORRECTION 9 (Sarah) — C2/C3 : aménagements scolaires complets + GEVASCO
        # Pour un enfant scolarisé, C2 et C3 sont OBLIGATOIRES si des aménagements existent.
        # AESH doit apparaître dans C1 (scolarité), pas dans B2 (vie quotidienne).

        # Détection AESH depuis toutes les sources (C7 : déjà épuré du texte B2)
        _a_aesh = (
            a_pps or a_ulis
            or any(x in aides_str for x in ["aesh", "avs", "accompagnement scolaire humain"])
            or any(x in (cerfa_rep.get("scolarite_details") or "").lower() for x in ["aesh", "avs"])
        )
        _a_tiers_temps = any(x in aides_str or x in (cerfa_rep.get("scolarite_details") or "").lower()
                             for x in ["tiers temps", "tiers-temps", "1/3 temps"])
        _a_mat_adapte  = any(x in aides_str or x in (cerfa_rep.get("scolarite_details") or "").lower()
                             for x in ["matériel adapté", "ordinateur", "clavier adapté"])

        # C2 — Aménagements scolaires
        if a_pps:
            cases.append("Case à cocher P 9 8")
        if a_ulis:
            cases.append("Case à cocher P 9 9")
        if a_pai:
            cases.append("Case à cocher P 9 10")

        # AESH → P10 2 (accompagnement humain scolaire)
        if _a_aesh:
            cases.append("Case à cocher P10 2")

        # Construire le texte C2 (aménagements) pour P10 1
        _amenagements_c2 = []
        if _a_aesh:
            _amenagements_c2.append("AESH (Accompagnant des Élèves en Situation de Handicap)")
        if _a_tiers_temps:
            _amenagements_c2.append("Tiers-temps aux évaluations")
        if _a_mat_adapte:
            _amenagements_c2.append("Matériel adapté")
        if aides_actuelles:
            _amenagements_c2 += [a for a in aides_actuelles if a.lower() not in ("aesh", "avs")]
        if _amenagements_c2:
            champs["Champ de texte P10 1"] = "\n".join(f"- {a}" for a in _amenagements_c2)[:500]

        # SESSAD / CAMSP → P10 3 (suivi médico-éducatif)
        if any(x in aides_str for x in ["sessad", "camsp"]):
            cases.append("Case à cocher P10 3")

        # GEVASCO — signalement si non disponible pour un enfant scolarisé
        _gevasco_rep = (cerfa_rep.get("gevasco_disponible") or "").lower()
        if "oui" in _gevasco_rep:
            logger.info("[CERFA C9] GEVASCO disponible — demander l'envoi par email.")
            # On peut noter dans P12 qu'un GEVASCO est joint
            champs["Champ de texte P12 1"] = (
                f"Classe : {classe_scolaire} — GEVASCO joint au dossier" if classe_scolaire
                else "GEVASCO joint au dossier"
            )
        elif is_enfant and not _gevasco_rep:
            logger.warning(
                "[CERFA C9] Enfant scolarisé : GEVASCO non renseigné. "
                "La question gevasco_disponible doit être posée via WhatsApp."
            )
            if classe_scolaire:
                champs["Champ de texte P12 1"] = f"Classe : {classe_scolaire}"
        else:
            if classe_scolaire:
                champs["Champ de texte P12 1"] = f"Classe : {classe_scolaire}"

        # PAGE 12 — PPS / PAI existants (C3)
        if a_pps:
            cases.append("Case à cocher P12 5")
        if a_pai:
            cases.append("Case à cocher P12 6")

    elif not is_enfant and aides_actuelles:
        # PAGE 10 adulte — accompagnements actuels
        aides_texte = "\n".join(f"- {a}" for a in aides_actuelles)
        champs["Champ de texte P10 1"] = aides_texte[:500]
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
    # Expert Q19/22 : emploi, recherche, ORP, projet pro
    # ════════════════════════════════════════════════════════════════════════
    if age_tranche in ("adulte", "jeune_majeur"):
        sp = situation_pro
        # has_emploi : VRAI uniquement si vraiment en emploi actif
        # Exclure les signaux négatifs : inscrit France Travail, sans emploi, AT, chômage
        _sp_norm = sp.lower()
        _sig_pos = any(x in _sp_norm for x in ["en emploi", "esat", "cdd", "cdi", "entreprise adaptée", "contrat"])
        _sig_neg = any(x in _sp_norm for x in [
            "sans emploi", "france travail", "pôle emploi", "pole emploi",
            "inscrit à", "recherche d'emploi", "chômage", "chomage",
            "arrêt maladie", "arret maladie", "accident du travail", " at ",
            "inaptitude", "inapte",
        ])
        has_emploi = _sig_pos and not _sig_neg and not en_recherche_emploi and not inscrit_pole_emploi

        # PAGE 13 — Situation actuelle
        if has_emploi:
            cases.append("Case à cocher P 13 1")

        if "esat" in sp:
            cases.append("Case à cocher P 13 3")
        elif "entreprise adaptée" in sp or " ea " in sp or "ea " in sp:
            cases.append("Case à cocher P 13 4")
        elif any(x in sp for x in ["emploi ordinaire", "milieu ordinaire", "cdi", "cdd"]):
            cases.append("Case à cocher P 13 2")

        if nom_employeur:
            champs["Champ de texte P13 1"] = nom_employeur
        if poste_occupe:
            champs["Champ de texte P13 2"] = poste_occupe
        if type_contrat:
            champs["Champ de texte P13 3"] = type_contrat.upper()
        if duree_hebdo:
            champs["Champ de texte P13 7"] = duree_hebdo

        # P 13 9 = sans emploi / recherche d'emploi
        # NE PAS cocher si arrêt AT/MP — la case arrêt maladie (P 13 12) est plus appropriée
        _en_arret_at = accident_travail or any(x in sp for x in ["accident de travail", "arret at", "arrêt at"])
        if (en_recherche_emploi or any(x in sp for x in ["sans emploi", "recherche", "chômage", "chomage"])) and not _en_arret_at:
            cases.append("Case à cocher P 13 9")
            if inscrit_pole_emploi:
                cases.append("Case à cocher P 13 7")
                if date_inscription_pe:
                    parts = date_inscription_pe.split("/")
                    if len(parts) == 3:
                        champs["DATE P13 1"] = parts[0]
                        champs["DATE P13 2"] = parts[1]
                        champs["DATE P13 3"] = parts[2]

        # Règle 7 : "jamais travaillé" UNIQUEMENT si _a_deja_travaille est explicitement False
        # et qu'aucune source n'indique le contraire (AT, ancienne expérience)
        _jamais_travaille_texte = any(x in sp for x in ["jamais travaillé", "jamais travaille"])
        if _jamais_travaille_texte and not _a_deja_travaille:
            cases.append("Case à cocher P 13 11")
        if any(x in sp for x in ["arrêt", "arret maladie"]):
            cases.append("Case à cocher P 13 12")
        if any(x in sp for x in ["retraite", "retraité"]):
            cases.append("Case à cocher P 13 8")

        if date_debut_emploi:
            parts = date_debut_emploi.split("/")
            if len(parts) == 3:
                champs["DATE P13 4"] = parts[0]
                champs["DATE P13 5"] = parts[1]
                champs["DATE P13 6"] = parts[2]

        # PAGE 14 — Accident du travail / Maladie professionnelle + parcours emploi
        # Champ de texte P14 1 = description narrative AT (PAS le nom de la formation)
        if accident_travail:
            cases.append("Case à cocher P14 1")   # Oui, j'ai eu un AT/MP
            if narratif_at:
                champs["Champ de texte P14 1"] = narratif_at[:500]
            # Date de l'accident : "Date p14 1/2/3" (nom de champ avec p minuscule)
            if date_at and "/" in date_at:
                _at_parts = date_at.split("/")
                if len(_at_parts) >= 2:
                    champs["Date p14 1"] = _at_parts[0]   # jour
                    champs["Date p14 2"] = _at_parts[1]   # mois
                if len(_at_parts) == 3:
                    champs["Date p14 3"] = _at_parts[2]   # année

        # France Travail (P14 2)
        if inscrit_pole_emploi:
            cases.append("Case à cocher P14 2")

        # Cap Emploi (P14 7) — structure spécialisée insertion TH
        if a_cap_emploi:
            cases.append("Case à cocher P14 7")

        # CV (P15 5) — mentionner si dossier contient un CV ou si projet pro
        _cv_text = ds.get("cv_text") or cerfa_rep.get("cv_text") or ""
        if _cv_text:
            champs["Champ de texte P15 5"] = _cv_text[:300]
        elif projet_professionnel or a_cible_esrp:
            champs["Champ de texte P15 5"] = "CV joint au dossier"

        # PAGE 16 — Projet professionnel / Orientation CRP-ESRP
        # CORRECTION 5 — Rubrique D / D3 : projet de vie avec NOM d'établissement
        # On ne jamais écrire "établissement" de manière générique.
        # On cherche le nom réel dans toutes les sources disponibles.

        # ── Recherche du nom d'établissement dans toutes les sources ──────────
        _nom_etab_cible = ""

        # Source 1 : champs dédiés dans ds
        _nom_etab_cible = (
            ds.get("nom_etablissement_cible")
            or ds.get("nom_etablissement")
            or ds.get("nom_ime")
            or ds.get("nom_esat")
            or ds.get("nom_foyer")
            or ds.get("nom_esrp")
            or nom_esrp
            or organisme_formation
            or ""
        ).strip()

        # Source 2 : scolarite_details (WhatsApp) → peut contenir "IME Les Pins"
        if not _nom_etab_cible:
            _scol_rep_d5 = (cerfa_rep.get("scolarite_details") or "").strip()
            # Extraire le nom propre s'il suit "IME", "ESAT", "SESSAD", "foyer", "SAMSAH"
            import re as _re
            _etab_match = _re.search(
                r'\b(IME|ESAT|SESSAD|ITEP|SAVS|SAMSAH|foyer|MAS|FAM|IMPro|IMPRO|CRP|ESRP)\s+([A-ZÀ-ÿa-z][^,\n]{2,50})',
                _scol_rep_d5, _re.IGNORECASE
            )
            if _etab_match:
                _nom_etab_cible = f"{_etab_match.group(1)} {_etab_match.group(2)}".strip()

        # Source 3 : situation_pro_scolaire → peut contenir "ESAT Les Chênes"
        if not _nom_etab_cible:
            _sit_rep_d5 = (cerfa_rep.get("situation_pro_scolaire") or "").strip()
            _etab_match2 = _re.search(
                r'\b(IME|ESAT|SESSAD|ITEP|SAVS|SAMSAH|foyer|MAS|FAM|IMPro|IMPRO|CRP|ESRP)\s+([A-ZÀ-ÿa-z][^,\n]{2,50})',
                _sit_rep_d5, _re.IGNORECASE
            )
            if _etab_match2:
                _nom_etab_cible = f"{_etab_match2.group(1)} {_etab_match2.group(2)}".strip()

        # Source 4 : nom_formation (si contient un type d'établissement)
        if not _nom_etab_cible and nom_formation:
            _nf_lower = nom_formation.lower()
            if any(t in _nf_lower for t in ["ime", "esat", "sessad", "foyer", "crp", "esrp", "savs", "samsah"]):
                _nom_etab_cible = nom_formation.strip()

        # ── Construction du texte D3 ──────────────────────────────────────────
        # D3 = "Orientation vers [NOM] pour [RAISON]"
        # ou projet libre si pas d'établissement identifié

        _raison_d3 = ""
        # Raison depuis besoins_aide ou difficultes_quotidiennes
        _besoins_court = (cerfa_rep.get("besoins_aide") or besoins_aide_str or "").strip()
        if _besoins_court and len(_besoins_court) > 10:
            _raison_d3 = _besoins_court[:200]
        elif difficultes_quotidiennes and len(difficultes_quotidiennes) > 10:
            _raison_d3 = difficultes_quotidiennes[:200]

        if _nom_etab_cible:
            # Cas 1 : nom d'établissement identifié → formulation précise
            _d3_text = f"Orientation vers {_nom_etab_cible}"
            if _raison_d3:
                _d3_text += f" afin de bénéficier d'un accompagnement adapté aux besoins suivants : {_raison_d3}"
            _d3_text = _d3_text[:500]
            champs["Champ de texte P16 1"] = _d3_text
            logger.info(f"[CERFA D3] Établissement identifié : {_nom_etab_cible!r}")
        elif projet_professionnel:
            # Cas 2 : projet pro libre (sans établissement nommé)
            champs["Champ de texte P16 1"] = projet_professionnel[:500]
        elif _raison_d3:
            # Cas 3 : aucun établissement, aucun projet explicite → résumé des besoins
            champs["Champ de texte P16 1"] = (
                f"Accompagnement et orientation adaptés aux besoins identifiés : {_raison_d3}"
            )[:500]

        # Case à cocher P16 2 = Orientation vers CRP/ESRP
        _cible_crp = a_cible_esrp or any(t in droits_str for t in ("CRP", "ESRP", "CPO", "UEROS"))
        if _cible_crp:
            cases.append("Case à cocher P16 2")
            _esrp_label = nom_esrp or organisme_formation or ""
            if not _esrp_label and nom_formation and any(t in nom_formation.lower() for t in ["esrp", "crp"]):
                _esrp_label = nom_formation
            if _esrp_label:
                champs["Champ de texte P 16 2"] = _esrp_label[:200]

        # Case à cocher P16 5 = Formation professionnelle en cours ou envisagée
        _projet_esat_seul = "esat" in droits_str.lower() and not _cible_crp
        if (en_formation or _cible_crp) and not _projet_esat_seul:
            cases.append("Case à cocher P16 5")
            _form_label = type_formation_pro or nom_formation or ""
            if not _form_label and _cible_crp:
                _esrp_name = nom_esrp or organisme_formation or ""
                if _esrp_name:
                    _form_label = f"CRP / ESRP : {_esrp_name}"
                else:
                    _form_label = "Centre de Rééducation Professionnelle (CRP / ESRP)"
            if _form_label:
                champs["Champ de texte P 17 1"] = _form_label[:300]

        # Champ de texte P16 3 = narratif + mention établissement ciblé (démarche active)
        # Enrichissement V3 : si un établissement nommé est présent dans cerfa_reponses
        # ou dans projet_professionnel, on l'injecte explicitement pour l'instructeur MDPH.
        _narratif_p16_3 = narratif_rehab or ""
        _projet_pro_v3  = ""
        if _dv2 and _dv2.section_e and _dv2.section_e.projet_professionnel:
            _projet_pro_v3 = _dv2.section_e.projet_professionnel
        elif cerfa_rep.get("qualification_parcours"):
            _projet_pro_v3 = cerfa_rep["qualification_parcours"]

        # Mention "Démarche active" si établissement identifié (Richebois, Visa Pro…)
        from app.engines.rules_engine import _extraire_nom_etablissement
        _etab_mentionne = _extraire_nom_etablissement(
            droits_str + " " + _projet_pro_v3 + " " + (nom_esrp or "")
        )
        if _etab_mentionne:
            _mention_demarche = (
                f"Démarche active initiée auprès de l'établissement : {_etab_mentionne}"
            )
            if _mention_demarche not in _narratif_p16_3:
                _narratif_p16_3 = (
                    f"{_narratif_p16_3} — {_mention_demarche}".strip(" —")
                )

        # Mention autodétermination si présente dans projet_professionnel
        if _projet_pro_v3 and "autodétermination" in _projet_pro_v3.lower():
            if _projet_pro_v3 not in _narratif_p16_3:
                _narratif_p16_3 = (
                    f"{_narratif_p16_3} — {_projet_pro_v3}".strip(" —")
                )

        if _narratif_p16_3:
            champs["Champ de texte P16 3"] = _narratif_p16_3[:500]

    # ════════════════════════════════════════════════════════════════════════
    # PAGES 19-20 — Aidant familial
    # Expert Q29/30 : déclenché si aidant confirmé (réponse WhatsApp ou ds)
    # Question posée : « Est-ce que quelqu'un vous aide au quotidien ? »
    # Si oui → remplir intégralement pages 19 et 20
    # ════════════════════════════════════════════════════════════════════════
    # Pages 19-20 — V2 : lecture directe depuis SectionAidant si disponible.
    # SectionAidant.est_present = False → pages entièrement vides, sans ambiguïté.
    if _dv2 and _dv2.aidant.est_present:
        _av2 = _dv2.aidant
        if _av2.nom:
            nom_aidant    = _av2.nom
            champs["Champ de texte P20 1"] = _av2.nom
        if _av2.prenom:
            prenom_aidant = _av2.prenom
            champs["Champ de texte P20 2"] = _av2.prenom
        if _av2.lien_parente:
            lien_aidant = _av2.lien_parente
            champs["Champ de texte P20 3"] = _av2.lien_parente
        logger.info(
            f"[CERFA V2] Aidant P19-P20 depuis SectionAidant : "
            f"{_av2.prenom} {_av2.nom} ({_av2.lien_parente})"
        )

    if _a_aidant_confirme or nom_aidant:
        if nom_aidant:
            champs["Champ de texte P20 1"] = nom_aidant
        if prenom_aidant:
            champs["Champ de texte P20 2"] = prenom_aidant
        if lien_aidant:
            champs["Champ de texte P20 3"] = lien_aidant

        # CORRECTION 10 (Sarah) — Pages 19-20 : aidant familial avec NOM et PRÉNOM.
        # Pour un profil ENFANT, le parent est l'aidant familial — c'est OBLIGATOIRE.
        # Ne jamais écrire "mère" ou "père" sans nom et prénom.

        # Résolution du nom aidant depuis toutes les sources
        _nom_aidant_p20    = nom_aidant
        _prenom_aidant_p20 = prenom_aidant
        _lien_aidant_p20   = lien_aidant

        # Si identité incomplète → chercher dans les champs parent de cerfa_filler
        if is_enfant and not _nom_aidant_p20:
            # Utiliser les variables parent déjà résolues en page 3 (C4)
            _nom_aidant_p20    = _nom_parent    if "_nom_parent" in dir() else ""
            _prenom_aidant_p20 = _prenom_parent if "_prenom_parent" in dir() else ""
            _lien_aidant_p20   = _lien_parent   if "_lien_parent" in dir() else "Père / Mère"

        # Remplissage P20 — toujours avec nom + prénom
        if _nom_aidant_p20:
            champs["Champ de texte P20 1"] = _nom_aidant_p20
        if _prenom_aidant_p20:
            champs["Champ de texte P20 2"] = _prenom_aidant_p20
        if _lien_aidant_p20:
            champs["Champ de texte P20 3"] = _lien_aidant_p20

        if is_enfant and not _nom_aidant_p20:
            logger.warning(
                "[CERFA C10] Profil ENFANT : identité de l'aidant familial (P19-P20) non renseignée. "
                "Pages 19-20 partielles — risque de renvoi MDPH. "
                "Vérifier la question 'aidant_identite' posée via WhatsApp."
            )

        # PAGE 19 — Situation de l'aidant
        if _lien_aidant_p20:
            try:
                champs["Champ de texte P19 1"] = _lien_aidant_p20
            except Exception:
                pass

        # Description des aides pour le profil ENFANT (C3 — nature de l'aide)
        _nature_aide_enfant = ""
        if is_enfant:
            _nat_parties = []
            if any(x in _detection_b2b3 for x in ["toilette", "hygiène", "se laver"]):
                _nat_parties.append("aide pour la toilette")
            if any(x in _detection_b2b3 for x in ["habillage", "s'habill"]):
                _nat_parties.append("aide pour l'habillage")
            if any(x in _detection_b2b3 for x in ["repas", "manger"]):
                _nat_parties.append("aide pour les repas")
            if any(x in _detection_b2b3 for x in ["déplacement", "mobilité"]):
                _nat_parties.append("aide aux déplacements")
            if any(x in _detection_b2b3 for x in ["communication", "langage"]):
                _nat_parties.append("aide à la communication")
            if _nat_parties:
                _nature_aide_enfant = ", ".join(_nat_parties)
        _freq_aide = ds.get("frequence_aide") or cerfa_rep.get("frequence_aide") or (
            "Aide quotidienne" if is_enfant else ""
        )
        if _freq_aide:
            try:
                champs["Champ de texte P19 3"] = (
                    f"{_freq_aide} — {_nature_aide_enfant}" if _nature_aide_enfant else _freq_aide
                )
            except Exception:
                pass

        _activite_aidant = ds.get("activite_aidant") or cerfa_rep.get("activite_aidant") or ""
        if _activite_aidant:
            try:
                champs["Champ de texte P19 2"] = _activite_aidant
            except Exception:
                pass

        if _besoins_aide_rep_txt and not _nom_aidant_p20:
            logger.info(
                "[CERFA C10] Aidant détecté via besoins_aide mais identité non collectée. "
                "La question 'aidant_identite' doit être posée via WhatsApp."
            )

    # ════════════════════════════════════════════════════════════════════════
    # BAS DE PAGE — Nom / prénom répétés sur toutes les pages
    # ════════════════════════════════════════════════════════════════════════
    champs["NOM BAS DE PAGE"]    = nom
    champs["PRENOM BAS DE PAGE"] = prenom

    # ════════════════════════════════════════════════════════════════════════
    # PAGES 17 / 18 — Demandes (allocations, orientations professionnelles)
    # ════════════════════════════════════════════════════════════════════════
    cases.extend(cases_droits)

    # ════════════════════════════════════════════════════════════════════════
    # RADIO BUTTONS — cochés AVANT update_page_form_field_values
    # ════════════════════════════════════════════════════════════════════════

    # Genre (OPTION P2 1) — x=165 : Homme | x=252 : Femme
    genre_ok = False
    if genre in ("homme", "masculin", "m", "male"):
        genre_ok = _cocher_option_nth(writer, "Case à cocher OPTION P2 1", 0)
    elif genre in ("femme", "féminin", "f", "female"):
        genre_ok = _cocher_option_nth(writer, "Case à cocher OPTION P2 1", 1)
    if not genre_ok and genre:
        logger.warning(f"Genre non coché : {genre!r}")

    # Nationalité (OPTION P2 2) — 0:Française | 1:EEE/Suisse | 2:Autre
    # Règle : ne cocher que si la nationalité est EXPLICITEMENT renseignée.
    # Nationalité absente ou inconnue → aucune case cochée.
    if not nationalite:
        pass  # nationalité inconnue → radio laissé vide, pas de case par défaut
    elif "eee" in nationalite or "suisse" in nationalite or "européen" in nationalite:
        _cocher_option_nth(writer, "Case à cocher OPTION P2 2", 1)
    elif "fran" in nationalite:
        _cocher_option_nth(writer, "Case à cocher OPTION P2 2", 0)  # Française explicite
    else:
        _cocher_option_nth(writer, "Case à cocher OPTION P2 2", 2)  # Autre nationalité

    # Pays de naissance (OPTION P2 3) — 0:France | 1:Autre
    # Ne cocher que si le pays de naissance est effectivement renseigné
    if pays_naissance:
        if pays_naissance.lower() != "france":
            _cocher_option_nth(writer, "Case à cocher OPTION P2 3", 1)
        else:
            _cocher_option_nth(writer, "Case à cocher OPTION P2 3", 0)
    # Si inconnu : radio laissé vide

    # Organisme payeur (OPTION P2 4) — 0:CAF | 1:MSA | 2:Autre
    # Expert Q2 : "poser systématiquement la question CAF ou MSA"
    if "msa" in organisme_payeur:
        _cocher_option_nth(writer, "Case à cocher OPTION P2 4", 1)
    elif "caf" in organisme_payeur or not organisme_payeur:
        _cocher_option_nth(writer, "Case à cocher OPTION P2 4", 0)
    else:
        _cocher_option_nth(writer, "Case à cocher OPTION P2 4", 2)

    # Assurance maladie (OPTION P2 5) — 0:CPAM | 1:MSA | 2:RSI | 3:Autre
    if "msa" in organisme_assurance:
        _cocher_option_nth(writer, "Case à cocher OPTION P2 5", 1)
    elif "rsi" in organisme_assurance:
        _cocher_option_nth(writer, "Case à cocher OPTION P2 5", 2)
    elif "autre" in organisme_assurance:
        _cocher_option_nth(writer, "Case à cocher OPTION P2 5", 3)
    else:
        _cocher_option_nth(writer, "Case à cocher OPTION P2 5", 0)

    # Classe ordinaire (OPTION P9 1) — 0:Oui | 1:Non
    if age_tranche in ("enfant", "jeune_majeur") and scolarise:
        _cocher_option_nth(writer, "Case à cocher OPTION P9 1", 0 if classe_ordinaire else 1)

    # Consentement partage informations (OPTION P4 1) — 0:J'accepte | 1:Je n'accepte pas
    # Nom du champ confirmé par inspection PDF : "Case à cocher OPTION P4 1"
    _cocher_option_nth(writer, "Case à cocher OPTION P4 1", 0 if consentement else 1)

    # Logement adapté (OPTION P5 1) — 0:Oui | 1:Non (confirmé par test : index 0 = /Oui)
    if logement_adapte is True:
        _cocher_option_nth(writer, "Case à cocher OPTION P5 1", 0)
    elif logement_adapte is False:
        _cocher_option_nth(writer, "Case à cocher OPTION P5 1", 1)

    # Statut d'occupation (OPTION P5 2) — FIX LOGEMENT : indices corrigés après vérification PDF.
    # Ordre réel des boutons radio dans cerfa_15692.pdf (confirmé par inspection) :
    #   index 0 → Locataire  |  index 1 → Propriétaire  |  index 2 → Hébergé
    # ATTENTION : l'ordre affiché dans le PDF est inversé par rapport à l'ordre logique.
    # CORRECTION 5 (Sarah) : un mineur < 16 ans est TOUJOURS hébergé (index 2).
    _so = statut_occupation
    if _est_mineur_strict:
        if any(x in _so for x in ["proprio", "propriétaire", "proprietaire", "locataire", "location"]):
            logger.error(
                f"[CERFA C5] Incohérence bloquée : mineur ({_age_p5} ans) marqué "
                f"statut='{_so}'. Forcé sur 'Hébergé'."
            )
        _cocher_option_nth(writer, "Case à cocher OPTION P5 2", 2)  # Hébergé — toujours
    else:
        if any(x in _so for x in ["proprio", "propriétaire", "proprietaire"]):
            _cocher_option_nth(writer, "Case à cocher OPTION P5 2", 1)   # Propriétaire = index 1
        elif any(x in _so for x in ["locataire", "location"]):
            _cocher_option_nth(writer, "Case à cocher OPTION P5 2", 0)   # Locataire = index 0
        elif any(x in _so for x in ["hébergé", "heberge", "gratuit", "à titre gratuit"]):
            _cocher_option_nth(writer, "Case à cocher OPTION P5 2", 2)   # Hébergé = index 2

    # Emploi / formation radios (adultes et jeunes majeurs)
    if age_tranche in ("adulte", "jeune_majeur"):
        sp = situation_pro
        # Type de contrat (OPTION P13 6) — index 0:/CDI | index 1:/CDD
        # Confirmé par le corrigé expert : /CDI pour le dernier contrat
        _tc = type_contrat.lower()
        if "cdi" in _tc or (has_emploi and "cdi" in sp):
            _cocher_option_nth(writer, "Case à cocher OPTION P13 6", 0)
        elif "cdd" in _tc or (has_emploi and "cdd" in sp):
            _cocher_option_nth(writer, "Case à cocher OPTION P13 6", 1)

        # Contrat en cours (OPTION P13 2)
        # Attention : "emploi" est sous-chaîne de "sans_emploi" → exclure explicitement
        has_emploi_radio = (
            "sans_emploi" not in sp
            and any(x in sp for x in ["en emploi", "esat", "cdi", "cdd", "contrat"])
        ) or has_emploi
        _cocher_option_nth(writer, "Case à cocher OPTION P13 2", 0 if has_emploi_radio else 1)

        # En arrêt (OPTION P13 3)
        en_arret = any(x in sp for x in ["arrêt", "arret"])
        _cocher_option_nth(writer, "Case à cocher OPTION P13 3", 0 if en_arret else 1)

        # Formation en cours (OPTION P14 1)
        _cocher_option_nth(writer, "Case à cocher OPTION P14 1", 0 if (en_formation or nom_formation) else 1)

        # Projet pro (OPTION P16 1) — 0:Oui j'ai un projet | 1:Non/en réflexion
        _a_projet_pro = bool(projet_professionnel) or a_cible_esrp
        _cocher_option_nth(writer, "Case à cocher OPTION P16 1", 0 if _a_projet_pro else 1)

    # ── Remplissage des champs texte ──────────────────────────────────────────
    champs_vides   = {k: v for k, v in champs.items() if v}
    champs_remplis = 0
    for page_idx, page in enumerate(writer.pages):
        try:
            writer.update_page_form_field_values(page, champs_vides)
            champs_remplis += 1
        except Exception as e:
            logger.warning(f"[CERFA] update_page_form_field_values page {page_idx} : {e}")

    # ── Cochage des cases simples via annotation directe ──────────────────────
    coches_ok = 0
    for field_name in cases:
        try:
            if _cocher_case(writer, field_name):
                coches_ok += 1
        except Exception as e:
            logger.debug(f"[CERFA] Cochage case '{field_name}' : {e}")

    # NeedAppearances — force les viewers à recalculer l'aspect visuel
    try:
        acroform = writer._root_object["/AcroForm"].get_object()
        acroform.update({NameObject("/NeedAppearances"): BooleanObject(True)})
    except Exception as e:
        logger.debug(f"NeedAppearances non défini : {e}")

    logger.info(
        f"CERFA pré-rempli | dossier={dossier.get('dossier_id', '?')} "
        f"| {nom} {prenom} | age_tranche={age_tranche} | genre={genre} "
        f"| pages={champs_remplis} | {coches_ok}/{len(cases)} cases cochées "
        f"| genre_ok={genre_ok} | droits={droits} "
        f"| cmi_p={cmi_priorite} cmi_s={cmi_stationnement} ea={emploi_accompagne}"
    )

    buffer = io.BytesIO()
    try:
        writer.write(buffer)
    except Exception as write_err:
        logger.error(f"[CERFA] Échec writer.write() : {write_err}", exc_info=True)
        raise

    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
