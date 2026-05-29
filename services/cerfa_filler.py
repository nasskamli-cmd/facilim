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

        sujet    = "de l'enfant" if is_enfant else "de la personne"
        personne = (
            "l'enfant (à la 3ème personne, ex : « il/elle ne peut pas… »)"
            if is_enfant else
            "la personne elle-même (à la 1ère personne, ex : « je ne peux pas… »)"
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

    if cmi_priorite or (has_cmi_generic and not cmi_stationnement):
        # CMI invalidité / priorité
        cases.append("Case à cocher P17 3" if is_enfant else "Case à cocher P17 13")

    if cmi_stationnement or (has_cmi_generic and not cmi_priorite):
        # CMI stationnement
        cases.append("Case à cocher P17 4" if is_enfant else "Case à cocher P17 14")

    # Si les deux flags sont True → on coche les deux cases (personne cumule les deux situations)
    if cmi_priorite and cmi_stationnement:
        # S'assurer que les deux sont cochées (les ajouts conditionnels ci-dessus les ont déjà ajoutées)
        pass

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
    _orp_tokens = ("ORP", "ORIENTATION PROFESSIONNELLE", "ORIENTATION PRO",
                   "RECLASSEMENT PROFESSIONNEL", "INSERTION PROFESSIONNELLE")
    if any(t in droits_str for t in _orp_tokens):
        cases.append("Case à cocher P18 2")  # Case parente ORP
        # Sous-type :
        if any(t in droits_str for t in (
            "CRP", "CPO", "UEROS",
            "REEDUCATION PROFESSIONNELLE", "READAPTATION PROFESSIONNELLE",
            "ESRP",            # Établissement de Réadaptation Professionnelle (ex-CRP)
            "VISA PRO",        # formation reconnue CRP
            "CENTRE DE REEDUCATION", "CENTRE DE READAPTATION",
        )):
            cases.append("Case à cocher P18 3")   # CRP / CPO / UEROS / ESRP
        elif "ESAT" in droits_str and not is_enfant:
            cases.append("Case à cocher P18 4")   # ESAT (milieu protégé)
        else:
            # Marché du travail (milieu ordinaire)
            cases.append("Case à cocher P18 5")
            # Emploi accompagné (sous-option marché du travail)
            # Quand la personne a un projet mais du mal à trouver seule
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
    """
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
    # Si nom ET prénom toujours vides → parser cerfa_rep["nom_prenom"]
    if not nom and not prenom:
        _np = (cerfa_rep.get("nom_prenom") or "").strip()
        if _np:
            _np_parts = _np.rsplit(" ", 1)
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
    situation_familiale    = (ds.get("situation_familiale") or cerfa_rep.get("situation_familiale") or "").lower()
    vie_seule              = ds.get("vie_seule", False)
    a_enfants_charge       = ds.get("a_enfants_charge", False)
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
    # NSS : ds > cerfa_reponses (champ WhatsApp numero_securite_sociale)
    nss        = (ds.get("nss") or cerfa_rep.get("numero_securite_sociale") or "").replace(" ", "").replace(".", "").replace("-", "")
    nss_parent = (ds.get("nss_parent") or "").replace(" ", "").replace(".", "")

    # Type de demande et situation MDPH — ds > cerfa_reponses > vide (pas de défaut "premiere")
    _type_demande_rep    = (cerfa_rep.get("type_demande") or "").lower()
    _historique_mdph_rep = (cerfa_rep.get("historique_mdph") or "").lower()
    type_demande         = (ds.get("type_demande") or _type_demande_rep).lower()
    deja_connu_mdph      = bool(ds.get("deja_connu_mdph", False))
    if not deja_connu_mdph and _historique_mdph_rep:
        deja_connu_mdph = any(w in _historique_mdph_rep for w in ["oui", "yes", "déjà", "deja"])
    # Si le type de demande est explicitement un renouvellement ou réévaluation, la personne est connue
    if not deja_connu_mdph and type_demande in (
        "renouvellement", "reevaluation", "réévaluation",
        "revision", "révision", "situation_changee", "situation_changée", "changement",
    ):
        deja_connu_mdph = True
    numero_dossier_mdph  = (ds.get("numero_dossier_mdph") or cerfa_rep.get("numero_dossier_mdph") or "")
    # Essayer d'extraire le numéro de dossier MDPH depuis la réponse WhatsApp historique_mdph
    # (ex. "Oui, renouvellement, numéro 2021-12345-13" ou "mon dossier 4567890")
    if not numero_dossier_mdph and _historique_mdph_rep:
        _num_mdph_m = re.search(r'\b(\d{4,12})\b', _historique_mdph_rep)
        if _num_mdph_m:
            numero_dossier_mdph = _num_mdph_m.group(1)
    # urgence_droits et procedure_simplifiee : calculés après la lecture de cerfa_rep ci-dessous

    # Identité complémentaire
    nationalite            = (ds.get("nationalite") or "francaise").lower()
    commune_naissance      = ds.get("commune_naissance") or ""
    departement_naissance  = ds.get("departement_naissance") or ""
    pays_naissance         = (ds.get("pays_naissance") or "").strip()  # pas de défaut "France"
    nom_usage              = ds.get("nom_usage") or ""
    organisme_payeur       = (ds.get("organisme_payeur") or cerfa_rep.get("organisme_payeur") or "").lower()
    numero_allocataire     = ds.get("numero_allocataire") or ""
    organisme_assurance    = (ds.get("organisme_assurance_maladie") or "cpam").lower()
    protection_juridique   = (ds.get("protection_juridique") or cerfa_rep.get("protection_juridique") or "aucune").lower()

    # CMI nuances (expert) — cases distinctes dans le CERFA
    # Priorité : ds > WhatsApp réponse textuelle cmi_type
    cmi_priorite      = ds.get("cmi_priorite") or _cmi_priorite_rep
    cmi_stationnement = ds.get("cmi_stationnement") or _cmi_stationnement_rep

    # Emploi accompagné (sous-option ORP marché du travail)
    emploi_accompagne = ds.get("emploi_accompagne") or _ea_bool

    # Creton (jeune adulte >20 maintenu en structure enfants)
    creton            = ds.get("creton", False)

    # Urgence droits
    urgence_droits    = ds.get("urgence_droits") or _urgence_bool
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
    accident_travail    = ds.get("accident_travail", False)
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
    inscrit_pole_emploi    = ds.get("inscrit_pole_emploi", False)
    date_inscription_pe    = ds.get("date_inscription_pole_emploi") or ""
    en_formation           = ds.get("en_formation", False)
    nom_formation          = ds.get("nom_formation") or ""
    organisme_formation    = ds.get("organisme_formation") or ""

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
    # (collectée par le bot quand ds ne fournit pas les infos logement)
    _logement_rep = (cerfa_rep.get("type_logement_statut") or "").lower()
    if _logement_rep:
        if not type_logement_detail:
            for _tl_kw in ["maison", "appartement", "studio", "foyer", "chambre", "hlm", "hlt"]:
                if _tl_kw in _logement_rep:
                    type_logement_detail = _tl_kw
                    break
        if not statut_occupation:
            if any(w in _logement_rep for w in ["propriétaire", "proprietaire"]):
                statut_occupation = "proprietaire"
            elif "locataire" in _logement_rep:
                statut_occupation = "locataire"
            elif any(w in _logement_rep for w in ["hébergé", "heberge", "hébergée"]):
                statut_occupation = "heberge"

    # ── Aides humaines (P6) ──────────────────────────────────────────────────
    a_aide_soignante       = ds.get("a_aide_soignante", False)
    a_auxiliaire_vie       = ds.get("a_auxiliaire_vie", False)
    a_aide_menagere        = ds.get("a_aide_menagere", False)

    # ── Aidant familial (P19-P20) ───────────────────────────────────────────
    nom_aidant             = ds.get("nom_aidant") or cerfa_rep.get("nom_aidant") or ""
    prenom_aidant          = ds.get("prenom_aidant") or cerfa_rep.get("prenom_aidant") or ""
    lien_aidant            = ds.get("lien_aidant") or cerfa_rep.get("lien_aidant") or ""

    # Aidant collecté via WhatsApp (champ aidant_identite : "Prénom Nom, lien")
    _aidant_identite_rep = (cerfa_rep.get("aidant_identite") or "").strip()
    if _aidant_identite_rep and not nom_aidant:
        _parts = _aidant_identite_rep.split(",", 1)
        _nom_parts = _parts[0].strip().split(" ", 1)
        if len(_nom_parts) >= 2:
            prenom_aidant = prenom_aidant or _nom_parts[0]
            nom_aidant    = nom_aidant or _nom_parts[1]
        elif _nom_parts:
            nom_aidant = nom_aidant or _nom_parts[0]
        if len(_parts) > 1:
            lien_aidant = lien_aidant or _parts[1].strip()

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

    # ── Description P8 (narrative humanisée — structure : situation → retentissements → projets) ──
    description_situation = _composer_description_p8(
        geva_pro=geva_pro,
        juriste=juriste,
        elements_probants=elements_probants,
        is_enfant=is_enfant,
        projet_professionnel=projet_professionnel,
        difficultes_quotidiennes=difficultes_quotidiennes,
        besoins_aide=besoins_aide_str,
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

    if type_demande in ("premiere", "première", "1ere", "1ère"):
        cases.append("Case à cocher P1 A")
    elif type_demande in ("situation_changee", "situation_changée", "changement"):
        cases.append("Case à cocher P1 B")
    elif type_demande in ("reevaluation", "réévaluation", "revision", "révision"):
        cases.append("Case à cocher P1 C")
    elif type_demande == "renouvellement":
        # Procédure simplifiée (P1 1 = renouvellement à l'identique) :
        # UNIQUEMENT si urgence droits (expire dans <2 mois) ET pas de nouveaux droits
        if procedure_simplifiee or urgence_droits:
            cases.append("Case à cocher P1 1")   # Renouvellement à l'identique (simplifié)
        else:
            cases.append("Case à cocher P1 C")   # Réévaluation (renouvellement avec révision)
    # Si type_demande inconnu → aucune case cochée (pas de défaut "première demande")

    # Déjà connu de la MDPH
    if deja_connu_mdph or type_demande in ("renouvellement", "reevaluation", "réévaluation",
                                            "revision", "révision", "situation_changee",
                                            "situation_changée", "changement"):
        cases.append("Case à cocher P1 3")
        if numero_dossier_mdph:
            champs["Champ de texte P 1 2"] = numero_dossier_mdph

    # Aidant familial (P1 2) — cocher si l'aidant souhaite exprimer sa situation
    if nom_aidant:
        cases.append("Case à cocher P1 2")

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

    # NSS bénéficiaire (1 case par chiffre, 15 chiffres)
    # Adulte : Numero SS 3 → Numero SS 17 | Enfant : N° SS Enfant 1 → N° SS Enfant 15
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
        # Représentant légal = parent(s) déclarant(s)
        champs["REPRESENTANT LEGAL 1"]  = nom
        champs["REPRESENTANT LEGAL 2"]  = prenom
        champs["REPRESENTANT LEGAL 3"]  = "Père / Mère"
        champs["REPRESENTANT LEGAL 6"]  = adresse
        champs["REPRESENTANT LEGAL 7"]  = cp
        champs["REPRESENTANT LEGAL 8"]  = commune
        champs["REPRESENTANT LEGAL 9"]  = telephone
        champs["REPRESENTANT LEGAL 10"] = email
        cases.append("Case à cocher P3 1")   # Titulaire autorité parentale

        # NSS du parent déclarant (si différent du NSS bénéficiaire)
        # Per expert Q4 : "mettre numéro de sécurité sociale du parent qui remplit le dossier"
        nss_parent_clean = nss_parent.replace("-", "")
        if nss_parent_clean and nss_parent_clean.isdigit():
            try:
                # Champ P3 NSS parent — les deux parents sauf jugement contraire
                champs["Champ de texte P3 NSS Parent"] = nss_parent_clean[:15]
            except Exception:
                pass

        # Protection juridique (tutelle/curatelle de l'enfant si applicable)
        if "tutelle" in protection_juridique:
            cases.append("Case à cocher P3 4")
        elif "curatelle" in protection_juridique:
            cases.append("Case à cocher P3 5")
        elif "sauvegarde" in protection_juridique:
            cases.append("Case à cocher P3 6")
    else:
        # Adulte : agit seul ou sous mesure de protection
        # NB : ne pas cocher P3 2 "agit seul" par défaut — laisser vide si pas de protection connue
        if protection_juridique not in ("aucune", "", "none", "non"):
            cases.append("Case à cocher P 3 3")   # Représentant désigné
            if "tutelle" in protection_juridique:
                cases.append("Case à cocher P3 4")
            elif "curatelle" in protection_juridique:
                cases.append("Case à cocher P3 5")
            elif "sauvegarde" in protection_juridique:
                cases.append("Case à cocher P3 6")

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 4 — Situation personnelle, familiale
    # IMPORTANT : Signature laissée VIDE — signée par l'éducateur à l'impression
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
    # NOTE : "a_enfants_charge" ne mappe PAS à P4 1 (= marié).
    # Les enfants à charge n'ont pas de case dédiée sur la page 4 du CERFA 15692.
    # La situation maritale est déjà gérée ci-dessus via sit_fam_case.

    # Consentement partage informations — géré via le radio OPTION P4 1 dans la section radios
    # (valeur /J'accepte ou /Je n'accepte pas — cochée via _cocher_option_nth plus bas)

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

    # "Avec qui vivez-vous ?" (P5 1-5)
    tl = type_logement_detail
    _en_etablissement = any(x in tl for x in [
        "établissement", "institution", "medico", "ehpad", "esat", "foyer d'hébergement",
    ])
    _heberge_parents  = any(x in tl for x in ["chez parents", "hébergé parents"])
    _heberge_enfants  = any(x in tl for x in ["chez enfants", "hébergé enfants"])
    _heberge_ami      = any(x in tl for x in ["chez ami", "hébergé ami"])
    _heberge_famille  = any(x in tl for x in ["chez famille", "hébergé famille"])

    # Avec qui
    if vie_seule:
        cases.append("Case à cocher P5 1")
    elif vie_en_couple or any(x in sf for x in ["marié", "marie", "pacsé", "pacse", "concubinage"]):
        cases.append("Case à cocher P5 2")
    elif _heberge_parents or any(x in tl for x in ["parents", "mère", "père"]):
        cases.append("Case à cocher P5 3")
    elif a_enfants_charge or vie_en_famille:
        # Vit avec ses enfants (cas : parent avec enfant à charge) → P5 4
        # Sauf si l'enfant, auquel cas c'est P5 3 (chez parents)
        if not is_enfant:
            cases.append("Case à cocher P5 4")
    # Pas de défaut : si inconnu → laisser vide

    # "Où vivez-vous ?" (P5 6-11)
    if _en_etablissement:
        cases.append("Case à cocher P5 7")
    elif _heberge_parents:
        cases.append("Case à cocher P5 8")
    elif _heberge_enfants:
        cases.append("Case à cocher P5 10")
    elif _heberge_ami:
        cases.append("Case à cocher P5 9")
    elif _heberge_famille:
        cases.append("Case à cocher P5 11")
    elif statut_occupation or type_logement_detail or logement_adapte is not None:
        # Logement indépendant (maison, appartement, etc.) — le cas le plus courant
        cases.append("Case à cocher P5 6")
    # Pas de défaut si aucune info sur le logement

    # Statut d'occupation → géré via OPTION P5 2 dans la section radios ci-dessous

    # Accident du travail / Maladie professionnelle (P5 15)
    if accident_travail:
        cases.append("Case à cocher P5 15")   # AT/MP reconnu
        cases.append("Case à cocher P5 20")   # Indemnisation en cours / rente

    # Ressources actuelles (B1) — AAH, chômage, ASS, pension invalidité, etc.
    if ressources_actuelles:
        try:
            champs["Champ de texte P5 ressources"] = ressources_actuelles[:300]
        except Exception:
            pass

    # Frais liés au handicap (B1)
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

    # Aide humaine
    if besoins_aide_humaine or a_auxiliaire_vie or a_aide_menagere:
        cases.append("Case à cocher P6 7")
        if a_auxiliaire_vie or any(x in aides_str for x in ["auxiliaire", "avs", "aide humaine"]):
            cases.append("Case à cocher P6 9")
        cases.append("Case à cocher P6 8")

    # Tableau professionnels intervenants
    if aides_actuelles:
        for i, aide in enumerate(aides_actuelles[:3], start=1):
            row_start = (i - 1) * 5 + 1
            champs[f"Tableau P6 {row_start}"] = aide[:25]

    # Besoins détaillés — gestes primaires (expert Q24 : manger, dormir, se laver)
    if besoins_aide_humaine or a_auxiliaire_vie:
        # Hygiène / se laver
        if any(x in aides_str for x in ["hygiène", "toilette", "bain", "douche", "lavage", "se laver"]):
            cases.append("Case à cocher P6 B1")
        # Habillage
        if any(x in aides_str for x in ["habillage", "vêtement", "vêtir", "s'habill"]):
            cases.append("Case à cocher P6 B2")
        # Repas / manger
        if any(x in aides_str for x in ["repas", "alimentation", "manger", "nutrition", "préparer", "cuisine"]):
            cases.append("Case à cocher P6 B3")
        # Mobilité intérieure
        if any(x in aides_str for x in ["mobilité", "déplacement", "marche", "fauteuil", "déplacer", "se lever"]):
            cases.append("Case à cocher P6 B4")
        # Sorties / extérieur
        if any(x in aides_str for x in ["extérieur", "sortie", "courses", "promenade"]):
            cases.append("Case à cocher P6 B5")
        # Communication
        if any(x in aides_str for x in ["communication", "langage", "parole", "comprendre"]):
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
    if age_tranche in ("enfant", "jeune_majeur") and scolarise:
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

        if nom_ecole:
            champs["Champ de texte P9 1"] = nom_ecole
        if classe_scolaire:
            champs["Champ de texte P9 2"] = classe_scolaire

        # C2 — Aménagements scolaires (REMPLISSAGE AUTOMATIQUE — expert Q18)
        if a_pps:
            cases.append("Case à cocher P 9 8")
        if a_ulis:
            cases.append("Case à cocher P 9 9")
        if a_pai:
            cases.append("Case à cocher P 9 10")
        # AESH (accompagnement humain) : automatique si PPS ou ULIS
        if a_pps or a_ulis:
            cases.append("Case à cocher P10 2")

        # PAGE 10 (scolarité) — accompagnements
        if aides_actuelles:
            aides_texte = "\n".join(f"- {a}" for a in aides_actuelles)
            champs["Champ de texte P10 1"] = aides_texte[:500]
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

        if any(x in sp for x in ["jamais travaillé", "jamais travaille"]):
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
        # OPTION P16 1 (radio Oui/Non) est géré dans la section radio ci-dessous
        # Champ de texte P16 1 = description du projet / orientation souhaitée
        if projet_professionnel:
            champs["Champ de texte P16 1"] = projet_professionnel[:500]

        # Case à cocher P16 2 = Orientation vers CRP/ESRP (PAS "non en réflexion")
        _cible_crp = a_cible_esrp or any(t in droits_str for t in ("CRP", "ESRP", "CPO", "UEROS"))
        if _cible_crp:
            cases.append("Case à cocher P16 2")   # Orientation spécialisée CRP/ESRP
            # Nom et adresse de l'ESRP visé → "Champ de texte P 16 2" (avec espace)
            _esrp_label = nom_esrp or organisme_formation or ""
            if not _esrp_label and nom_formation and any(t in nom_formation.lower() for t in ["esrp", "crp"]):
                _esrp_label = nom_formation
            if _esrp_label:
                champs["Champ de texte P 16 2"] = _esrp_label[:200]

        # Case à cocher P16 5 = Formation professionnelle en cours ou envisagée
        if en_formation or (_cible_crp and type_formation_pro):
            cases.append("Case à cocher P16 5")
            # Nom de la formation → "Champ de texte P 17 1" (avec espace)
            _form_label = type_formation_pro or nom_formation or ""
            if _form_label:
                champs["Champ de texte P 17 1"] = _form_label[:300]

        # Champ de texte P16 3 = narratif de la situation / pourquoi réadaptation
        if narratif_rehab:
            champs["Champ de texte P16 3"] = narratif_rehab[:500]

    # ════════════════════════════════════════════════════════════════════════
    # PAGES 19-20 — Aidant familial
    # Expert Q29/30 : déclenché si aidant confirmé (réponse WhatsApp ou ds)
    # Question posée : « Est-ce que quelqu'un vous aide au quotidien ? »
    # Si oui → remplir intégralement pages 19 et 20
    # ════════════════════════════════════════════════════════════════════════
    if _a_aidant_confirme or nom_aidant:
        if nom_aidant:
            champs["Champ de texte P20 1"] = nom_aidant
        if prenom_aidant:
            champs["Champ de texte P20 2"] = prenom_aidant
        if lien_aidant:
            champs["Champ de texte P20 3"] = lien_aidant

        # PAGE 19 — Situation de l'aidant
        # Lien de parenté / relation avec la personne aidée
        if lien_aidant:
            try:
                champs["Champ de texte P19 1"] = lien_aidant
            except Exception:
                pass
        # Activité professionnelle de l'aidant (si renseignée)
        _activite_aidant = ds.get("activite_aidant") or cerfa_rep.get("activite_aidant") or ""
        if _activite_aidant:
            try:
                champs["Champ de texte P19 2"] = _activite_aidant
            except Exception:
                pass
        # Fréquence de l'aide (description)
        _freq_aide = ds.get("frequence_aide") or cerfa_rep.get("frequence_aide") or ""
        if _freq_aide:
            try:
                champs["Champ de texte P19 3"] = _freq_aide
            except Exception:
                pass
        # Description des aides apportées (depuis cerfa_reponses)
        if _besoins_aide_rep_txt and not nom_aidant:
            # Si seule la description existe (pas encore d'identité) — log pour alerter
            logger.info(
                "[CERFA P19-P20] Aidant détecté via besoins_aide mais identité non collectée. "
                "Ajouter la question 'aidant_identite' dans le flux WhatsApp."
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
    if "eee" in nationalite or "suisse" in nationalite or "européen" in nationalite:
        _cocher_option_nth(writer, "Case à cocher OPTION P2 2", 1)
    elif "autre" in nationalite or (nationalite and "fran" not in nationalite):
        _cocher_option_nth(writer, "Case à cocher OPTION P2 2", 2)
    else:
        _cocher_option_nth(writer, "Case à cocher OPTION P2 2", 0)

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

    # Statut d'occupation (OPTION P5 2) — 0:Propriétaire | 1:Locataire | 2:Hébergé
    # Confirmé par inspection PDF : "Case à cocher OPTION P5 2" avec valeurs /Propriétaire, /Locataire...
    _so = statut_occupation
    if any(x in _so for x in ["proprio", "propriétaire", "proprietaire"]):
        _cocher_option_nth(writer, "Case à cocher OPTION P5 2", 0)
    elif any(x in _so for x in ["locataire", "location"]):
        _cocher_option_nth(writer, "Case à cocher OPTION P5 2", 1)
    elif any(x in _so for x in ["hébergé", "heberge", "gratuit", "à titre gratuit"]):
        _cocher_option_nth(writer, "Case à cocher OPTION P5 2", 2)

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
        has_emploi_radio = any(x in sp for x in ["emploi", "travail", "esat", "cdi", "cdd"])
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
