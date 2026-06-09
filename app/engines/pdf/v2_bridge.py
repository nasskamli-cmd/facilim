"""
app/engines/pdf/v2_bridge.py

Pont entre les données V3 (synthese_json) et le moteur de remplissage V2
(services/cerfa_filler.py — 2197 lignes, 20 pages, logique MDPH complète).

Principe :
  V3 collecte les données via WhatsApp/documents → synthese_json
  Ce module convertit synthese_json → format attendu par remplir_cerfa() V2
  V2 cerfa_filler génère le PDF officiel avec les vraies valeurs AP/N

Mapping clés V3 → clés V2 :
  nom_prenom        → nom_enfant / prenom_enfant (ou nom_adulte / prenom_adulte)
  date_naissance    → ddn_enfant / ddn_adulte
  adresse_complete  → adresse_enfant + cp_enfant + commune_enfant
  telephone         → telephone_famille
  email             → email_famille
  departement       → departement_code
  type_dossier      → type_demande
  droits_demandes   → analyse.droits_identifies
  diagnostics       → analyse.donnees_structurees.diagnostic_principal
  impact_quotidien  → cerfa_reponses.difficultes_quotidiennes
  restrictions_emploi → cerfa_reponses.restrictions_emploi
  accident_travail  → cerfa_reponses + analyse
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("facilim.pdf.v2_bridge")


def synthese_to_v2_dossier(
    synthese: dict[str, Any],
    service_type: str = "adulte",
    numero_dossier_mdph: str = "",
) -> dict[str, Any]:
    """
    Convertit le synthese_json V3 en dict compatible avec remplir_cerfa() V2.

    Args:
        synthese:             contenu de synthese_json (données collectées)
        service_type:         "enfant" | "adulte" | "mixte" | "protege"
        numero_dossier_mdph:  N° dossier existant si réévaluation/renouvellement

    Returns:
        Dict prêt à être passé à remplir_cerfa()
    """
    is_enfant = service_type == "enfant"
    dossier: dict[str, Any] = {}

    # ── Identité ────────────────────────────────────────────────────────────────
    # FIX VAGUE 1 : normalise les champs structurés (droits.* → droits_demandes)
    # pour que le moteur V2 (qui lit droits_demandes) en bénéficie sans modification.
    from app.services.collecte_schema import normaliser_collecte
    synthese = normaliser_collecte(synthese)

    nom_complet = str(synthese.get("nom_prenom", "")).strip()
    # Priorité aux champs structurés s'ils existent (sinon split heuristique)
    nom, prenom = _split_nom_prenom(nom_complet)
    nom = synthese.get("nom_naissance") or nom
    prenom = synthese.get("prenom") or prenom

    ddn = _normaliser_date(synthese.get("date_naissance", ""))
    if is_enfant:
        dossier["nom_enfant"]    = nom
        dossier["prenom_enfant"] = prenom
        dossier["ddn_enfant"]    = ddn
    else:
        dossier["nom_enfant"]    = nom       # V2 utilise ces clés même pour les adultes
        dossier["prenom_enfant"] = prenom
        dossier["ddn_enfant"]    = ddn

    # ── Adresse ──────────────────────────────────────────────────────────────────
    adresse_complete = str(synthese.get("adresse_complete", ""))
    adresse, cp, commune = _split_adresse(adresse_complete)
    dossier["adresse_enfant"]  = adresse
    dossier["cp_enfant"]       = cp
    dossier["commune_enfant"]  = commune.upper() if commune else ""

    # ── Contact ──────────────────────────────────────────────────────────────────
    dossier["telephone_famille"] = str(synthese.get("telephone", "") or synthese.get("telephone_whatsapp", ""))
    dossier["email_famille"]     = str(synthese.get("email", "") or synthese.get("email_usager", ""))
    dossier["departement_code"]  = str(synthese.get("departement", "") or synthese.get("departement_code", ""))

    # ── NIR ──────────────────────────────────────────────────────────────────────
    nir = str(synthese.get("num_secu", "")
              or synthese.get("numero_securite_sociale", "")
              or synthese.get("nir", ""))
    dossier["nss"]         = nir   # NSS de la personne concernée
    dossier["nss_parent1"] = nir   # Idem pour V2 qui utilise parfois cette clé

    # ── Type de demande ──────────────────────────────────────────────────────────
    type_dos = str(synthese.get("type_dossier", "INITIAL")).upper()
    num_dos  = numero_dossier_mdph or str(synthese.get("numero_dossier_mdph", ""))
    dossier["type_demande"]         = type_dos
    dossier["num_dossier_existant"] = num_dos
    # Alias nécessaires pour cerfa_filler V2 qui cherche dans plusieurs clés
    dossier["numero_dossier_mdph"]  = num_dos
    dossier["historique_mdph"]      = num_dos

    # ── Représentant légal ───────────────────────────────────────────────────────
    rep_nom = str(synthese.get("representant_legal_nom", ""))
    rep_lien = str(synthese.get("representant_legal_lien", ""))
    if rep_nom:
        rep_n, rep_p = _split_nom_prenom(rep_nom)
        dossier["nom_representant1"]    = rep_n
        dossier["prenom_representant1"] = rep_p
        dossier["lien_representant1"]   = rep_lien

    # ── Protection juridique ─────────────────────────────────────────────────────
    if service_type == "protege":
        dossier["protection_juridique"] = str(synthese.get("type_protection", ""))
        dossier["tribunal_protection"]  = str(synthese.get("jugement_tribunal", ""))

    # ── Genre (normalisation) ───────────────────────────────────────────────────
    # On accepte aussi la CIVILITÉ : à la question « votre genre ? », une personne
    # répond souvent « Mr », « Monsieur », « Mme »… La civilité est une déclaration
    # de genre explicite, donc on la mappe (ce n'est pas une invention).
    _genre_raw = str(synthese.get("genre", "") or synthese.get("sexe", "")).lower().strip()
    _genre_raw = _genre_raw.replace(".", " ").strip()  # "m." → "m"
    _genre_map = {
        "homme": "m", "masculin": "m", "male": "m", "m": "m", "h": "m",
        "mr": "m", "monsieur": "m", "mister": "m",
        "femme": "f", "féminin": "f", "feminin": "f", "female": "f", "f": "f",
        "mme": "f", "madame": "f", "mlle": "f", "mademoiselle": "f", "mrs": "f",
    }
    _g = _genre_map.get(_genre_raw)
    if _g is None:
        # Tolérance : civilité ou variante en tout début de chaîne.
        if _genre_raw.startswith(("mr", "monsieur", "homme", "mascul", "m ")):
            _g = "m"
        elif _genre_raw.startswith(("mme", "mlle", "madame", "mademoiselle", "femme", "fémin", "femin")):
            _g = "f"
        else:
            _g = _genre_raw
    dossier["genre"] = _g

    # ── Situation matrimoniale / familiale ──────────────────────────────────────
    _sit_mat = str(synthese.get("situation_familiale", "") or synthese.get("situation_matrimoniale", "")).lower()
    dossier["situation_familiale"] = _sit_mat

    # ── Situation professionnelle ────────────────────────────────────────────────
    # Règle : préremplir uniquement ce qui est EXPLICITEMENT déclaré.
    # Aucune déduction par sous-chaîne dans les champs texte libres.
    statut = str(synthese.get("statut_emploi", "")).lower()

    # accident_travail : uniquement si clé booléenne structurée présente
    _accident = bool(synthese.get("accident_travail"))

    # inscrit_pole_emploi : uniquement si clé booléenne structurée présente
    _inscrit_pe = bool(
        synthese.get("inscrit_pole_emploi")
        or synthese.get("france_travail")
    )

    # en_formation : clé structurée ou réponse explicite "oui" à la question dédiée
    # La présence du mot "formation" dans statut_emploi n'est PAS suffisante.
    _en_formation = bool(
        synthese.get("en_formation")
        or synthese.get("qualification_section_c") == "oui"
        or synthese.get("formation_actuelle")
    )

    # a_deja_travaille : uniquement si clé structurée ou AT confirmé par clé structurée.
    # Règle métier forte autorisée : AT confirmé → a forcément travaillé.
    # Déduction par sous-chaîne dans statut_emploi SUPPRIMÉE.
    _a_deja_travaille = bool(
        synthese.get("a_deja_travaille")
        or _accident  # déduction métier forte : AT confirmé = a travaillé
    )

    dossier["situation_emploi"]      = synthese.get("statut_emploi", "")
    dossier["employeur"]             = synthese.get("nom_employeur", "")
    dossier["en_formation"]          = _en_formation
    dossier["type_formation_pro"]    = synthese.get("formation_actuelle", "")
    dossier["accident_travail"]      = _accident
    dossier["inscrit_pole_emploi"]   = _inscrit_pe
    dossier["a_deja_travaille"]      = _a_deja_travaille

    # ── Mode de vie / logement ───────────────────────────────────────────────────
    _sit_log = str(synthese.get("type_logement", "") or synthese.get("statut_occupation", "")).lower()
    dossier["mode_vie"]            = synthese.get("mode_vie", "")
    dossier["type_logement"]       = _sit_log
    dossier["statut_occupation"]   = synthese.get("statut_occupation", "")

    # ── Scolarité (enfant / mixte) ───────────────────────────────────────────────
    if service_type in ("enfant", "mixte"):
        dossier["situation_scolaire"]     = synthese.get("situation_scolaire", "")
        dossier["etablissement_scolaire"] = synthese.get("etablissement_scolaire", "")
        dossier["type_etablissement"]     = synthese.get("situation_scolaire", "")

    # ── Aidant familial ──────────────────────────────────────────────────────────
    aidant_nom = str(synthese.get("aidant_nom", ""))
    if aidant_nom or synthese.get("aidant_demande"):
        an, ap = _split_nom_prenom(aidant_nom)
        dossier["nom_aidant"]    = an
        dossier["prenom_aidant"] = ap
        dossier["lien_aidant"]   = str(synthese.get("aidant_lien", ""))

    # ── Analyse IA (droits + données structurées) ────────────────────────────────
    droits_bruts = str(synthese.get("droits_demandes", ""))
    droits_liste = [d.strip() for d in re.split(r"[,\s]+", droits_bruts.upper()) if d.strip()]

    # Données structurées depuis les documents uploadés
    donnees_structurees = {
        "nom":                   nom,
        "prenom":                prenom,
        "date_naissance":        ddn,
        "adresse":               adresse_complete,
        "diagnostic_principal":  synthese.get("diagnostics", ""),
        "traitements":           synthese.get("traitements", ""),
        "medecin_traitant":      synthese.get("medecin_traitant", ""),
        "accident_travail":      synthese.get("accident_travail", ""),
        "restrictions":          synthese.get("restrictions_emploi", ""),
        "statut_emploi":         synthese.get("statut_emploi", ""),
        # Champs critiques pour le filler V2
        "type_demande":          type_dos.lower(),
        "numero_dossier_mdph":   num_dos,
        "nss":                   synthese.get("num_secu", "") or synthese.get("numero_securite_sociale", ""),
        "aidant_demande":        bool(synthese.get("aidant_demande") or synthese.get("aidant_familial")),
        # ANTI-CONTAMINATION : champs AVQ structurés (Vague 1) propagés vers le filler V2
        # afin que les cases P6 soient cochées sur PREUVE STRUCTURÉE (jamais sur narratif).
        "avq_toilette":            synthese.get("avq_toilette", ""),
        "avq_habillage":           synthese.get("avq_habillage", ""),
        "avq_repas":               synthese.get("avq_repas", ""),
        "avq_deplacements":        synthese.get("avq_deplacements", ""),
        "avq_gestion_quotidienne": synthese.get("avq_gestion_quotidienne", ""),
    }

    # Synthèses narratives pour la page 8
    syntheses_agents = {
        "geva_pro": _composer_geva_pro(synthese),
        "juriste":  "",  # rempli par le moteur de règles V2
    }

    dossier["analyse"] = {
        "droits_identifies":    droits_liste,
        "elements_probants":    _extraire_elements_probants(synthese),
        "donnees_structurees":  donnees_structurees,
        "synthese_agents":      syntheses_agents,
    }

    # ── cerfa_reponses (données WhatsApp + textes narratifs Phase 3) ────────────
    # Sprint P0.5-B : priorité aux textes narratifs si présents
    _texte_b = synthese.get("texte_b_vie_quotidienne", "") or ""
    _texte_c = synthese.get("texte_c_scolarite", "") or ""
    _texte_d = synthese.get("texte_d_situation_pro", "") or ""
    _texte_e = synthese.get("texte_e_projet_vie", "") or ""

    dossier["cerfa_reponses"] = {
        # Vie quotidienne : texte narratif B en priorité
        "difficultes_quotidiennes":   _texte_b[:2000] if _texte_b else synthese.get("impact_quotidien", ""),
        # Scolarité : texte narratif C
        "situation_scolaire_narrative": _texte_c[:1500] if _texte_c else synthese.get("situation_scolaire", ""),
        # Emploi : texte narratif D
        "projet_professionnel_narratif": _texte_d[:1500] if _texte_d else synthese.get("projet_professionnel", ""),
        # Projet de vie : texte narratif E
        "projet_de_vie":              _texte_e[:2000] if _texte_e else synthese.get("projet_professionnel", ""),
        "besoins_aide":               synthese.get("aides_humaines", ""),
        "souhait_orientation_usager": synthese.get("souhait_orientation_usager", ""),
        "restrictions_emploi":        synthese.get("restrictions_emploi", ""),
        "situation_scolaire":         synthese.get("situation_scolaire", ""),
        "souhait_scolarisation":      synthese.get("situation_scolaire", ""),
        "notes_pro":                  synthese.get("notes_pro", ""),
        "documents_texte":            synthese.get("documents_texte", ""),
        # Champs critiques lus par le filler V2
        "type_demande":               type_dos.lower(),
        "historique_mdph":            num_dos,
        "numero_dossier_mdph":        num_dos,
        "nss":                        nir,
        "numero_securite_sociale":    nir,
        # Champs manquants dans le bridge (Règles métier)
        "genre":                      dossier.get("genre", ""),
        "situation_familiale":        _sit_mat,
        "accident_travail":           _accident,
        "inscrit_pole_emploi":        _inscrit_pe,
        "a_deja_travaille":           _a_deja_travaille,
        "en_formation":               _en_formation,
        "formation_actuelle":         synthese.get("formation_actuelle", ""),
        "nationalite":                synthese.get("nationalite", ""),
        "statut_occupation":          synthese.get("statut_occupation", ""),
    }

    # ── Notes pro pour contexte narratif page 8 ──────────────────────────────────
    notes = str(synthese.get("notes_pro", ""))
    if notes:
        dossier["notes_educateur"] = notes

    logger.info(
        "[V2 BRIDGE] Dossier converti | nom=%s | droits=%s | service=%s",
        nom, droits_liste, service_type,
    )
    return dossier


# ── Helpers ───────────────────────────────────────────────────────────────────

def _split_nom_prenom(full: str) -> tuple[str, str]:
    """Sépare 'NAIT ALI Karim' → ('NAIT ALI', 'Karim') de façon robuste."""
    parts = full.strip().split()
    if not parts:
        return "", ""
    # Trouver où finit le NOM (majuscules) et où commence le prénom
    nom_parts, prenom_parts = [], []
    for p in parts:
        if p.isupper() and len(p) > 1:
            nom_parts.append(p)
        else:
            prenom_parts.append(p)
    if not nom_parts:
        # Dernier mot = nom, reste = prénom
        return parts[-1].upper(), " ".join(parts[:-1])
    return " ".join(nom_parts), " ".join(prenom_parts)


def _normaliser_date(date_str: str) -> str:
    """
    Normalise une date en JJ/MM/AAAA quelle que soit la saisie :
      02041985      → 02/04/1985
      02-04-1985    → 02/04/1985
      02.04.1985    → 02/04/1985
      02/04/1985    → 02/04/1985 (inchangé)
    """
    if not date_str:
        return date_str
    import re as _re
    # Supprimer séparateurs existants
    cleaned = _re.sub(r"[-./\s]", "", date_str.strip())
    # Format 8 chiffres JJMMAAAA
    if _re.fullmatch(r"\d{8}", cleaned):
        return f"{cleaned[:2]}/{cleaned[2:4]}/{cleaned[4:]}"
    # Déjà avec séparateur → remplacer par /
    m = _re.match(r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})", date_str.strip())
    if m:
        j, mo, a = m.group(1).zfill(2), m.group(2).zfill(2), m.group(3)
        if len(a) == 2:
            a = f"19{a}" if int(a) > 24 else f"20{a}"
        return f"{j}/{mo}/{a}"
    return date_str  # format non reconnu → retourner tel quel


def _split_adresse(adresse: str) -> tuple[str, str, str]:
    """'1 rue des Bateliers 13016 MARSEILLE' → ('1 rue des Bateliers', '13016', 'MARSEILLE')"""
    cp_m = re.search(r"\b(\d{5})\b", adresse)
    if cp_m:
        rue     = adresse[:cp_m.start()].strip().rstrip(",")
        cp      = cp_m.group(1)
        commune = adresse[cp_m.end():].strip().lstrip(",").strip()
        return rue, cp, commune
    return adresse, "", ""


def _composer_geva_pro(synthese: dict) -> str:
    """
    Compose le texte GEVA-Pro pour la page 8 depuis toutes les sources disponibles.
    Sprint P0.5-B : priorité aux textes narratifs Phase 3 (texte_b, texte_d, texte_e).
    """
    parts = []

    # Priorité 1 — texte narratif Section B (Phase 3)
    texte_b = synthese.get("texte_b_vie_quotidienne", "") or ""
    if texte_b.strip():
        parts.append(texte_b[:1500])
    elif synthese.get("impact_quotidien"):
        # Fallback sur données brutes si narratif absent
        parts.append(synthese["impact_quotidien"])

    # Texte narratif Section D (Phase 3)
    texte_d = synthese.get("texte_d_situation_pro", "") or ""
    if texte_d.strip():
        parts.append(texte_d[:800])
    elif synthese.get("restrictions_emploi"):
        parts.append(f"Restrictions professionnelles : {synthese['restrictions_emploi']}")

    # Autres sources
    if synthese.get("accident_travail"):
        parts.append(f"Antécédent : {synthese['accident_travail']}")
    if synthese.get("notes_pro"):
        parts.append(synthese["notes_pro"])
    if synthese.get("documents_texte") and not texte_b:
        parts.append(str(synthese["documents_texte"])[:1000])

    return "\n\n".join(p for p in parts if p)


def _extraire_elements_probants(synthese: dict) -> list[str]:
    """Extrait les éléments probants depuis les données disponibles."""
    elements = []
    if synthese.get("diagnostics"):
        elements.append(f"Diagnostic : {synthese['diagnostics']}")
    if synthese.get("traitements"):
        elements.append(f"Traitements : {synthese['traitements']}")
    if synthese.get("medecin_traitant"):
        elements.append(f"Médecin : {synthese['medecin_traitant']}")
    return elements


def generer_cerfa_depuis_synthese(
    synthese: dict[str, Any],
    service_type: str = "adulte",
    numero_dossier_mdph: str = "",
) -> bytes:
    """
    Fonction principale : synthese_json → PDF CERFA bytes.
    Utilise le moteur V2 (2197 lignes de logique MDPH).
    """
    from services.cerfa_filler import remplir_cerfa
    from services.cerfa_expert import analyser_profil_mdph

    dossier = synthese_to_v2_dossier(synthese, service_type, numero_dossier_mdph)

    # Enrichissement par l'expert MDPH V2
    try:
        expertise = analyser_profil_mdph(dossier)
        dossier = expertise.get("cerfa", dossier)
    except Exception as e:
        logger.warning("[V2 BRIDGE] Expert MDPH indisponible : %s", e)

    return remplir_cerfa(dossier)
