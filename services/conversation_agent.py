"""
services/conversation_agent.py — Agent conversationnel WhatsApp Facilim.

Protocole CERFA 15692 : collecte strictement ordonnée, sans répétition.
Chaque message entrant tente d'extraire la valeur du champ en cours ;
le champ suivant est déterminé par CERFA_FIELD_ORDER.

Architecture documentaire MDPH :
  Le CERFA 15692 (dossier administratif) porte sur les RETENTISSEMENTS
  FONCTIONNELS du handicap dans la vie quotidienne : ce que la personne
  ne peut pas faire seule, ses difficultés concrètes, ses besoins de
  compensation. C'est ce que collecte le bot WhatsApp.

  Le certificat médical (rempli par le médecin) contient : diagnostics,
  traitements, examens, taux. Ces données ne transitent JAMAIS par WhatsApp
  (canal non chiffré hébergé par Meta, incompatible avec l'art. 9 RGPD).
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Champs strictement médicaux — jamais collectés via WhatsApp
# ATTENTION : "impact_quotidien" n'est PAS ici — les difficultés fonctionnelles
# sont le cœur du CERFA et peuvent être collectées via WhatsApp.
# ---------------------------------------------------------------------------
MEDICAL_FIELDS: frozenset[str] = frozenset({
    "numero_securite_sociale",   # NIR 15 chiffres — donnée sensible de 1er rang (art. 9 RGPD)
    "diagnostic_principal",      # donnée de santé stricto sensu (art. 9 RGPD)
    "medecin_traitant",          # information médicale identifiante
    "traitements_en_cours",      # médicaments et thérapies — secret médical
    "taux_incapacite",           # taux MDPH — donnée médicale certifiée
})

# Clé sentinel dans cerfa_reponses — indique que le message de redirection a été envoyé
_MEDICAL_REDIRECT_SENT_KEY = "__medical_redirect_sent__"
# Valeur sentinel pour indiquer "à fournir via canal sécurisé"
_MEDICAL_VIA_EMAIL = "__via_email__"

_MESSAGE_CANAL_SECURISE = (
    "🔒 Pour protéger vos données de santé, certaines informations médicales "
    "confidentielles ne peuvent pas être partagées par WhatsApp.\n\n"
    "Merci de transmettre les éléments suivants *par email* à votre accompagnateur "
    "ou *via la messagerie sécurisée* de votre structure :\n\n"
    "• Numéro de sécurité sociale (NIR)\n"
    "• Diagnostic médical précis et date d'apparition\n"
    "• Nom et coordonnées du médecin traitant\n"
    "• Traitements en cours (médicaments, thérapies)\n"
    "• Taux d'incapacité (si renouvellement)\n\n"
    "Votre accompagnateur intégrera ces éléments directement dans le dossier "
    "à partir des documents médicaux. Toutes les autres informations sont déjà collectées. "
    "Merci pour votre précieuse collaboration !"
)

# ---------------------------------------------------------------------------
# Ordre strict CERFA 15692 — immuable, jamais modifié par le LLM.
#
# ARCHITECTURE : Le CERFA principal porte sur le FONCTIONNEL (sections A-E).
# Les champs fonctionnels sont collectés via WhatsApp (sections marquées ✓).
# Les champs strictement médicaux (marqués [MED]) restent hors WhatsApp.
#
# Champs conditionnels (★) : skippés par get_next_cerfa_field si la condition
# n'est pas remplie (ex. urgence_droits uniquement pour les renouvellements).
# ---------------------------------------------------------------------------
CERFA_FIELD_ORDER: list[str] = [
    # Section A — Identité
    "type_demande",               # premiere demande ou renouvellement
    "urgence_droits",             # droits expirent dans <2 mois ? (conditionnel: renouvellement)
    "nom_prenom",                 # nom et prenom du beneficiaire
    "date_naissance",             # JJ/MM/AAAA
    "genre",                      # homme / femme
    "adresse_complete",           # numero, rue, CP, ville
    "situation_familiale",        # celibataire, marie, en couple...
    "enfants_a_charge",           # nombre (0 si aucun)
    "type_logement_statut",       # ★ P5 : type logement + statut occupation (maison/appart + proprio/locataire)
    "organisme_payeur",           # CAF ou MSA - systematique (expert Q2)
    "protection_juridique",       # tutelle / curatelle / aucune (expert Q8)
    # Section B — Vie quotidienne & retentissements fonctionnels
    "difficultes_quotidiennes",   # ce que la personne ne peut pas faire seule
    "besoins_aide",               # type d'aide humaine/technique necessaire
    "aidant_identite",            # (conditionnel: si aide humaine confirmee) nom, prenom, lien avec la personne
    "ressources_actuelles",       # allocations recues + frais handicap non rembourses
    # Section C/D — Parcours scolaire / professionnel
    "situation_pro_scolaire",     # emploi, scolarite, formation, recherche d'emploi, inactivite
    "scolarite_details",          # ★ P9-12 : type etablissement, classe, PPS/PAI/AESH (conditionnel: mineur)
    # Section E — Demandes
    "type_droits",                # AAH, RQTH, PCH, AEEH, CMI, orientation IME/ESAT/SESSAD
    "cmi_type",                   # priorite (station debout) ou stationnement (PMR/<200m) ou les deux
    "emploi_accompagne",          # emploi accompagne vs droit commun (conditionnel: si ORP demande)
    "qualification_parcours",     # ★ D1/D2 : niveau formation + dernier poste (conditionnel: adulte RQTH/ORP/AAH, apres type_droits)
    "historique_mdph",            # date derniere notification (conditionnel: si renouvellement)
    # Donnees medicales — collectees HORS WhatsApp par l'educateur [MED]
    "numero_securite_sociale",    # [MED] NIR
    "diagnostic_principal",       # [MED] pathologie certifiee
    "medecin_traitant",           # [MED] coordonnees medecin
    "traitements_en_cours",       # [MED] medicaments et therapies
    "taux_incapacite",            # [MED] taux MDPH si renouvellement
]

CERFA_FIELD_LABELS: dict[str, str] = {
    # Identité
    "type_demande":               "s'il s'agit d'une première demande MDPH ou d'un renouvellement",
    "urgence_droits":             "si les droits actuels arrivent à échéance dans moins de 2 mois (répondre oui ou non)",
    "nom_prenom":                 "le nom et prénom complet du bénéficiaire",
    "date_naissance":             "la date de naissance du bénéficiaire (format JJ/MM/AAAA)",
    "genre":                      "le genre du bénéficiaire (homme ou femme)",
    "adresse_complete":           "l'adresse complète (numéro, rue, code postal, ville)",
    "situation_familiale":        "la situation familiale (célibataire, marié·e, en couple, divorcé·e…)",
    "enfants_a_charge":           "le nombre d'enfants à charge (indiquez 0 si aucun)",
    "type_logement_statut":       "le type de logement (maison, appartement, foyer…) et le statut d'occupation (propriétaire, locataire, ou hébergé chez quelqu'un)",
    "organisme_payeur":           "l'organisme qui verse les allocations familiales : CAF ou MSA ?",
    "protection_juridique":       "si la personne est sous mesure de protection juridique (tutelle, curatelle, ou aucune)",
    # Fonctionnel — cœur du CERFA
    "difficultes_quotidiennes":   "les principales difficultés dans la vie de tous les jours (ce que la personne ne peut pas faire seule, ce qui lui est difficile ou épuisant)",
    "besoins_aide":               "les aides dont la personne a besoin (aide humaine, aide technique, aménagement du logement, accompagnement…)",
    "aidant_identite":            "le prénom, le nom et le lien avec la personne aidée (ex : Marie Dupont, épouse) — uniquement si quelqu'un aide la personne au quotidien",
    "ressources_actuelles":       "les ressources actuelles (ex : AAH, APL, pension d'invalidité, ARE, ASS, ou aucune) et les frais importants liés au handicap qui ne sont pas remboursés",
    # Parcours
    "situation_pro_scolaire":     "la situation professionnelle ou scolaire actuelle (emploi, scolarité, formation, recherche d'emploi, inactivité…)",
    "scolarite_details":          "le type d'établissement scolaire (classe ordinaire, ULIS, IME, SESSAD…), la classe actuelle, et si un PPS, PAI ou une AESH est en place",
    "qualification_parcours":     "le niveau de formation obtenu (CAP, BAC, BTS, licence…) et le dernier métier ou poste occupé avant l'arrêt ou le handicap",
    # Demandes
    "type_droits":                "le ou les types de droits demandés à la MDPH (AAH, RQTH, PCH, AEEH, CMI, orientation IME/ESAT/SESSAD…)",
    "cmi_type":                   "le type de CMI souhaité : priorité (difficultés à rester debout longtemps), stationnement (déplacements réduits ou périmètre de marche inférieur à 200 mètres), ou les deux",
    "emploi_accompagne":          "si la personne souhaite être accompagnée pour trouver un emploi ou une formation (dispositif emploi accompagné), ou si elle peut chercher seule (droit commun)",
    "historique_mdph":            "la date de la dernière notification MDPH et les droits déjà accordés (uniquement si renouvellement)",
    # Médical — hors WhatsApp
    "numero_securite_sociale":    "le numéro de sécurité sociale (15 chiffres)",
    "diagnostic_principal":       "le diagnostic médical précis (pathologie, depuis quand, confirmé par quel médecin)",
    "medecin_traitant":           "le nom et la ville du médecin traitant",
    "traitements_en_cours":       "les traitements médicaux en cours (médicaments, thérapies, fréquence)",
    "taux_incapacite":            "le taux d'incapacité reconnu par la MDPH (indiqué sur la dernière notification)",
}

_TAUX_FIELD        = "taux_incapacite"
_HISTORIQUE        = "historique_mdph"
_TYPE_DEMANDE      = "type_demande"
_DIFFICULTES       = "difficultes_quotidiennes"
_BESOINS           = "besoins_aide"
_URGENCE           = "urgence_droits"
_CMI_TYPE          = "cmi_type"
_EMPLOI_ACCOMPAGNE = "emploi_accompagne"
_AIDANT_IDENTITE   = "aidant_identite"
_SCOLARITE         = "scolarite_details"
_QUALIFICATION     = "qualification_parcours"


# ---------------------------------------------------------------------------
# Pré-remplissage : évite de reposer des questions déjà connues
# ---------------------------------------------------------------------------

def prepopuler_cerfa_depuis_dossier(cerfa_reponses: dict, dossier: dict) -> None:
    """
    Synchronise cerfa_reponses avec les données déjà connues du dossier
    (données saisies par l'éducateur + extraites automatiquement depuis le document).

    N'écrase jamais une réponse déjà saisie par l'usager.
    Appelé à chaque message WhatsApp entrant, avant get_next_cerfa_field.
    """
    analyse = dossier.get("analyse") or {}
    ds      = analyse.get("donnees_structurees") or {}

    def _set(field: str, value: str | None) -> None:
        """Ne remplace que si le champ est vide ET la valeur non-vide."""
        if not cerfa_reponses.get(field) and value and str(value).strip():
            cerfa_reponses[field] = str(value).strip()

    # Nom + prénom
    nom    = (dossier.get("nom_enfant") or "").strip()
    prenom = (dossier.get("prenom_enfant") or "").strip()
    if nom and prenom:
        _set("nom_prenom", f"{prenom} {nom}")
    elif nom:
        _set("nom_prenom", nom)

    # Date de naissance
    _set("date_naissance", dossier.get("ddn_enfant"))

    # Genre (depuis les données structurées de l'analyse IA)
    _set("genre", ds.get("genre"))

    # Adresse complète
    adresse  = (dossier.get("adresse_enfant") or "").strip()
    cp       = (dossier.get("cp_enfant") or "").strip()
    commune  = (dossier.get("commune_enfant") or "").strip()
    if adresse:
        parts = [p for p in [adresse, cp, commune] if p]
        _set("adresse_complete", ", ".join(parts))

    # Situation familiale
    _set("situation_familiale", ds.get("situation_familiale"))

    # Type de droits demandés
    droits = analyse.get("droits_identifies") or []
    if droits:
        _set("type_droits", ", ".join(droits))

    # Situation professionnelle / scolaire
    _set("situation_pro_scolaire", ds.get("situation_professionnelle"))

    # Type de demande (première / renouvellement)
    _set("type_demande", ds.get("type_demande"))

    # Historique MDPH
    _set("historique_mdph", ds.get("historique_mdph"))

    # Organisme payeur (CAF/MSA)
    _set("organisme_payeur", ds.get("organisme_payeur"))

    # Protection juridique
    _set("protection_juridique", ds.get("protection_juridique"))

    # CMI type (si déjà connu)
    cmi_p = ds.get("cmi_priorite", False)
    cmi_s = ds.get("cmi_stationnement", False)
    if cmi_p and cmi_s:
        _set("cmi_type", "les deux (priorité et stationnement)")
    elif cmi_p:
        _set("cmi_type", "priorité")
    elif cmi_s:
        _set("cmi_type", "stationnement")

    # Emploi accompagné
    if ds.get("emploi_accompagne"):
        _set("emploi_accompagne", "oui, emploi accompagné")

    # Aidant — pré-remplissage si déjà connu
    _nom_a   = (ds.get("nom_aidant") or "").strip()
    _prenom_a = (ds.get("prenom_aidant") or "").strip()
    _lien_a  = (ds.get("lien_aidant") or "").strip()
    if _prenom_a and _nom_a:
        _set("aidant_identite", f"{_prenom_a} {_nom_a}" + (f", {_lien_a}" if _lien_a else ""))
    elif _lien_a:
        _set("aidant_identite", _lien_a)

    # Date de naissance — dossier (formulaire éducateur) > ds (bilan)
    _set("date_naissance", dossier.get("ddn_enfant") or ds.get("date_naissance"))

    # Adresse complète — dossier > ds
    if not cerfa_reponses.get("adresse_complete"):
        _adr  = (dossier.get("adresse_enfant") or ds.get("adresse") or ds.get("adresse_beneficiaire") or "").strip()
        _cp   = (dossier.get("cp_enfant") or ds.get("code_postal") or "").strip()
        _comm = (dossier.get("commune_enfant") or ds.get("commune") or "").strip()
        _adresse_full = ", ".join(p for p in [_adr, _cp, _comm] if p)
        if _adresse_full:
            _set("adresse_complete", _adresse_full)

    # Nom / prénom — dossier > ds
    if not cerfa_reponses.get("nom_prenom"):
        _nom_d    = (dossier.get("nom_enfant") or ds.get("nom") or "").strip()
        _prenom_d = (dossier.get("prenom_enfant") or ds.get("prenom") or "").strip()
        if _nom_d or _prenom_d:
            _set("nom_prenom", f"{_prenom_d} {_nom_d}".strip())

    # Ressources actuelles — depuis ds
    _ressources_ds = ds.get("ressources_actuelles") or ""
    if not _ressources_ds:
        _aides_actuelles = ds.get("aides_actuelles") or []
        if isinstance(_aides_actuelles, list) and _aides_actuelles:
            _ressources_ds = " / ".join(str(a) for a in _aides_actuelles[:5])
    _set("ressources_actuelles", _ressources_ds)

    # Enfants à charge — depuis ds
    _enfants_ds = ds.get("enfants_a_charge")
    if _enfants_ds is not None:
        _set("enfants_a_charge", str(_enfants_ds))
    elif ds.get("a_enfants_charge") is False:
        _set("enfants_a_charge", "0")

    # Pré-remplissage fonctionnel — préférer expressions_libres (texte rédigé pour le CERFA)
    # à geva_pro (synthèse analytique contenant du jargon non adapté aux champs CERFA).
    syntheses          = analyse.get("synthese_agents") or {}
    geva_pro           = str(syntheses.get("geva_pro") or "").strip()
    expressions_libres = analyse.get("expressions_libres") or {}
    _vie_quotidienne   = str(expressions_libres.get("vie_quotidienne") or "").strip()
    _autonomie         = str(expressions_libres.get("autonomie") or "").strip()

    # difficultes_quotidiennes : vie_quotidienne CERFA-ready > geva_pro analytique
    if _vie_quotidienne and len(_vie_quotidienne) > 20:
        _set("difficultes_quotidiennes", _vie_quotidienne[:500])
    elif geva_pro and len(geva_pro) > 40:
        _set("difficultes_quotidiennes", geva_pro[:500])

    # Besoins d'aide — depuis les données structurées
    aides = ds.get("aides_actuelles") or []
    if isinstance(aides, list) and aides:
        _set("besoins_aide", " / ".join(str(a) for a in aides[:5]))
    elif ds.get("besoins_aide_humaine"):
        _set("besoins_aide", "Aide humaine nécessaire")

    # besoins_aide : autonomie CERFA-ready > geva_pro analytique
    if not cerfa_reponses.get("besoins_aide"):
        if _autonomie and len(_autonomie) > 20:
            _set("besoins_aide", _autonomie[:300])
        elif geva_pro and len(geva_pro) > 30:
            _set("besoins_aide", geva_pro[:300])

    # Situation professionnelle — enrichie depuis projet_professionnel si disponible
    projet_pro = (ds.get("projet_professionnel") or "").strip()
    nom_formation = (ds.get("nom_formation") or "").strip()
    organisme_formation = (ds.get("organisme_formation") or "").strip()
    sit_pro_actuelle = (ds.get("situation_professionnelle") or "").strip()

    if not cerfa_reponses.get("situation_pro_scolaire"):
        parts_sit = []
        if sit_pro_actuelle:
            parts_sit.append(sit_pro_actuelle)
        if nom_formation:
            parts_sit.append(f"Formation : {nom_formation}")
        if organisme_formation:
            parts_sit.append(f"Organisme : {organisme_formation}")
        if ds.get("inscrit_pole_emploi") or ds.get("en_recherche_emploi"):
            parts_sit.append("inscrit France Travail / en recherche d'emploi")
        if ds.get("accident_travail"):
            dat = ds.get("date_accident_travail", "")
            parts_sit.append(f"Accident du travail{' le ' + dat if dat else ''}")
        if parts_sit:
            _set("situation_pro_scolaire", " — ".join(parts_sit))

    # Historique MDPH — depuis les données structurées
    _set("historique_mdph", ds.get("numero_dossier_mdph") or ds.get("historique_mdph"))

    # Type de demande — première vs renouvellement
    if not cerfa_reponses.get("type_demande"):
        _type_dem = (ds.get("type_demande") or "").strip()
        if not _type_dem and ds.get("deja_connu_mdph"):
            _type_dem = "renouvellement"
        _set("type_demande", _type_dem)

    # ── Nouveaux champs (P5, P9-12, D1/D2) ──────────────────────────────────

    # type_logement_statut — P5 (logement + statut occupation)
    _tl = (ds.get("type_logement") or "").strip()
    _so = (ds.get("statut_occupation") or "").strip()
    if _tl or _so:
        _combined = " / ".join(p for p in [_tl, _so] if p)
        _set("type_logement_statut", _combined)

    # scolarite_details — P9-P12 (pour les mineurs)
    _scol_parts: list[str] = []
    if ds.get("type_etablissement_scolaire"):
        _scol_parts.append(str(ds["type_etablissement_scolaire"]))
    if ds.get("nom_ecole"):
        _scol_parts.append(str(ds["nom_ecole"]))
    if ds.get("classe_scolaire"):
        _scol_parts.append(f"classe {ds['classe_scolaire']}")
    if ds.get("a_pps"):
        _scol_parts.append("PPS")
    if ds.get("a_pai"):
        _scol_parts.append("PAI")
    if ds.get("a_ulis"):
        _scol_parts.append("ULIS")
    if _scol_parts:
        _set("scolarite_details", " | ".join(_scol_parts))

    # qualification_parcours — D1/D2 (adultes, parcours pro + niveau qualification)
    _qual  = (ds.get("niveau_qualification") or "").strip()
    _poste = (ds.get("poste_occupe") or "").strip()
    _emp   = (ds.get("nom_employeur") or "").strip()
    _qp_parts: list[str] = []
    if _qual:
        _qp_parts.append(_qual)
    if _poste:
        _qp_parts.append(f"poste : {_poste}")
    if _emp:
        _qp_parts.append(f"chez {_emp}")
    if _qp_parts:
        _set("qualification_parcours", " / ".join(_qp_parts))


# ---------------------------------------------------------------------------
# Extraction complète CERFA depuis le texte du bilan (appel LLM dédié)
# ---------------------------------------------------------------------------

def extraire_cerfa_depuis_bilan(texte_bilan: str, cerfa_reponses: dict) -> dict:
    """
    Lit le texte complet du bilan uploadé et extrait TOUS les champs CERFA
    directement. Beaucoup plus fiable que le mappage depuis donnees_structurees.

    Appelle le LLM avec un prompt ciblé CERFA — distinct de l'analyse CNSA.
    Ne remplace jamais un champ déjà renseigné dans cerfa_reponses.

    Retourne le dict cerfa_reponses mis à jour.
    """
    import importlib
    _llm = importlib.import_module("4_llm_client.openai_client")
    call_llm = _llm.call_llm

    # Tronquer le texte si nécessaire
    texte = texte_bilan[:8000] if len(texte_bilan) > 8000 else texte_bilan

    # Champs à extraire (hors médicaux et champs déjà renseignés)
    champs_cibles = {
        field: label
        for field, label in CERFA_FIELD_LABELS.items()
        if field not in MEDICAL_FIELDS and not cerfa_reponses.get(field)
    }

    if not champs_cibles:
        return cerfa_reponses  # Tout est déjà renseigné

    liste_champs = "\n".join(
        f'  "{k}": "{v}"'
        for k, v in champs_cibles.items()
    )

    system_prompt = """
Tu es un assistant spécialisé dans l'analyse de bilans sociaux et éducatifs pour des dossiers MDPH.
Ta tâche : extraire des informations précises depuis un document, pour pré-remplir un formulaire CERFA 15692.

RÈGLES ABSOLUES :
1. Tu extrais UNIQUEMENT ce qui est explicitement écrit dans le document.
2. Si une information n'est pas dans le document, mets null (pas de supposition).
3. Pour "situation_pro_scolaire" : indique EXACTEMENT ce que dit le document (ex: "inscrit France Travail depuis AT 2019", "formation visa pro à l'ESRP Richebois ciblée").
4. Pour "besoins_aide" : décris les aides concrètes mentionnées dans le document.
5. Pour "difficultes_quotidiennes" : reprends en substance les difficultés décrites (3-5 phrases max).
6. Pour "type_droits" : liste UNIQUEMENT les droits explicitement mentionnés ou clairement impliqués (RQTH, ORP, CRP, AAH, PCH, AEEH, CMI, ESAT, SAVS, SAMSAH...).
7. Tu réponds UNIQUEMENT en JSON valide — aucun texte autour.
"""

    user_prompt = (
        f"Voici les champs CERFA à extraire depuis ce document :\n{liste_champs}\n\n"
        f"DOCUMENT :\n---\n{texte}\n---\n\n"
        f"Réponds en JSON avec exactement ces clés. Valeur = texte extrait du document, ou null si absent.\n"
        f"Exemple de format attendu :\n"
        f'{{\n  "situation_pro_scolaire": "Inscrit à France Travail, AT en 2019...",\n  "besoins_aide": null\n}}'
    )

    import json
    try:
        raw = call_llm(
            system_prompt=system_prompt,
            user_message=user_prompt,
            temperature=0.0,
            max_tokens=1500,
        )
        # Nettoyer les blocs markdown éventuels
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()

        extracted = json.loads(cleaned)
        updated = 0
        for field, value in extracted.items():
            if value and str(value).strip() and str(value).strip().lower() not in ("null", "none", ""):
                if field in CERFA_FIELD_LABELS and field not in MEDICAL_FIELDS:
                    if not cerfa_reponses.get(field):
                        cerfa_reponses[field] = str(value).strip()
                        updated += 1
        logger.info(f"[CERFA-EXTRACTION] {updated} champs extraits du bilan via LLM")

    except Exception as e:
        logger.warning(f"[CERFA-EXTRACTION] Extraction LLM échouée : {e}")

    return cerfa_reponses


# ---------------------------------------------------------------------------
# Logique de progression CERFA
# ---------------------------------------------------------------------------

def get_next_cerfa_field(cerfa_reponses: dict[str, str]) -> str | None:
    """
    Retourne le prochain champ CERFA à collecter via WhatsApp.

    Règles de saut conditionnel :
    - Les champs médicaux (MEDICAL_FIELDS) sont toujours sautés.
    - urgence_droits : sauté si ce n'est pas un renouvellement.
    - cmi_type : sauté si "CMI" n'est pas dans type_droits.
    - emploi_accompagne : sauté si ORP n'est pas dans type_droits.
    - historique_mdph : sauté si c'est clairement une première demande.
    - taux_incapacite : sauté si première demande.
    - Si tous les champs non-médicaux sont renseignés mais des champs médicaux
      sont encore vides → retourne le sentinel _MEDICAL_REDIRECT_SENT_KEY.
    """
    medical_pending = False

    type_d   = cerfa_reponses.get(_TYPE_DEMANDE, "").lower()
    type_droits_val = cerfa_reponses.get("type_droits", "").lower()

    # Indicateurs contextuels
    is_renouvellement = any(
        w in type_d for w in ["renouvellement", "renouvel"]
    )
    is_first = any(
        w in type_d for w in ["premiere", "premier", "première", "jamais", "nouveau", "1ere", "1ère"]
    )
    has_cmi = any(w in type_droits_val for w in ["cmi", "carte mobilite", "carte invalidite"])
    has_orp = any(
        w in type_droits_val
        for w in ["orp", "orientation pro", "rqth", "emploi", "esat", "travail"]
    )

    for field in CERFA_FIELD_ORDER:
        # Champ déjà renseigné → suivant
        if field in cerfa_reponses and cerfa_reponses[field]:
            continue

        # Champ médical → jamais collecté via WhatsApp
        if field in MEDICAL_FIELDS:
            medical_pending = True
            continue

        # ── Champs conditionnels ─────────────────────────────────────────────

        # urgence_droits : uniquement si renouvellement
        if field == _URGENCE:
            if not is_renouvellement and not type_d:
                continue  # type_demande pas encore répondu → sauter pour l'instant
            if is_first or (type_d and not is_renouvellement):
                continue  # Pas un renouvellement → pas besoin de demander l'urgence

        # historique_mdph : inutile pour une première demande
        if field == _HISTORIQUE:
            if is_first:
                continue
            if type_d and not is_renouvellement:
                continue

        # cmi_type : uniquement si CMI dans les droits demandés
        if field == _CMI_TYPE:
            if not has_cmi:
                continue

        # emploi_accompagne : uniquement si orientation pro dans les droits
        if field == _EMPLOI_ACCOMPAGNE:
            if not has_orp:
                continue

        # aidant_identite : uniquement si aide humaine confirmée dans besoins_aide
        if field == _AIDANT_IDENTITE:
            besoins_txt = cerfa_reponses.get(_BESOINS, "").lower()
            _mots_aide = [
                "quelqu'un", "aide de", "aidé par", "ma femme", "mon mari",
                "ma mère", "mon père", "mes enfants", "ma fille", "mon fils",
                "mon conjoint", "aide humaine", "auxiliaire", "avs", "aide à domicile",
            ]
            if not any(w in besoins_txt for w in _mots_aide):
                continue  # Pas d'aide humaine confirmée → ne pas poser la question

        # scolarite_details : uniquement pour les mineurs (< 18 ans)
        if field == _SCOLARITE:
            _ddn = cerfa_reponses.get("date_naissance", "")
            _is_minor = None
            if _ddn and "/" in _ddn:
                try:
                    from datetime import date as _dt
                    _p = _ddn.split("/")
                    if len(_p) == 3:
                        _age = (_dt.today() - _dt(int(_p[2]), int(_p[1]), int(_p[0]))).days // 365
                        _is_minor = _age < 18
                except Exception:
                    pass
            if _is_minor is not True:
                continue  # adulte ou âge inconnu → sauter P9-P12

        # qualification_parcours : uniquement pour les adultes avec RQTH / ORP / AAH demandé.
        # Ce champ vient APRÈS type_droits dans l'ordre → on attend que type_droits soit renseigné.
        if field == _QUALIFICATION:
            _ddn = cerfa_reponses.get("date_naissance", "")
            _is_adult = True  # défaut : adulte (pas de mineur sans date connue)
            if _ddn and "/" in _ddn:
                try:
                    from datetime import date as _dt
                    _p = _ddn.split("/")
                    if len(_p) == 3:
                        _age = (_dt.today() - _dt(int(_p[2]), int(_p[1]), int(_p[0]))).days // 365
                        _is_adult = _age >= 18
                except Exception:
                    pass
            if not _is_adult:
                continue  # mineur → sauter D1/D2
            # Attendre que type_droits soit renseigné (qualification suit logiquement les droits)
            _td = cerfa_reponses.get("type_droits", "").lower()
            if not _td:
                continue  # type_droits pas encore renseigné → sauter pour l'instant
            # Poser uniquement si le contexte est professionnel (RQTH, ORP, AAH, emploi)
            _has_pro_droits = any(
                w in _td for w in ["rqth", "orp", "aah", "emploi", "cdi", "cdd", "formation"]
            )
            if not _has_pro_droits:
                continue  # Droits sans contexte professionnel → sauter

        # taux_incapacite : uniquement si renouvellement (redondant avec MEDICAL_FIELDS mais garde)
        if field == _TAUX_FIELD:
            hist     = cerfa_reponses.get(_HISTORIQUE, "").lower()
            combined = type_d + " " + hist
            is_renewal_ctx = any(
                w in combined
                for w in ["renouvellement", "renouvel", "taux reconnu", "notification", "deja accorde"]
            )
            if is_first and not is_renewal_ctx:
                continue

        return field  # prochain champ non-médical à collecter

    # Tous les champs non-médicaux sont renseignés.
    if medical_pending and not cerfa_reponses.get(_MEDICAL_REDIRECT_SENT_KEY):
        return _MEDICAL_REDIRECT_SENT_KEY

    return None


def extract_cerfa_field_from_reply(
    message: str,
    field: str,
    openai_client: Any,
) -> str | None:
    """
    Extrait la valeur d'un champ CERFA précis depuis le message de l'usager.
    Retourne None si l'information n'est pas présente ou est ambiguë.
    """
    label = CERFA_FIELD_LABELS.get(field, field)
    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"Tu dois extraire '{label}' depuis le message utilisateur.\n"
                        "Réponds UNIQUEMENT avec la valeur extraite, sans explication.\n"
                        "Si le message ne contient pas cette information, réponds exactement : NON_TROUVE\n"
                        "Si la valeur est ambiguë, réponds exactement : NON_TROUVE"
                    ),
                },
                {"role": "user", "content": message},
            ],
            max_tokens=80,
            temperature=0,
        )
        val = resp.choices[0].message.content.strip()
        return None if val.upper() == "NON_TROUVE" else val
    except Exception as e:
        logger.warning(f"[CONV_AGENT] Extraction champ '{field}' échouée : {e}")
        return None


# ---------------------------------------------------------------------------
# Génération de la réponse
# ---------------------------------------------------------------------------

def generer_reponse_agent(
    message_entrant: str,
    historique: list[dict],
    donnees_collectees: dict,
    elements_manquants: list[str],
    openai_client: Any,
    is_enfant: bool = True,
    cerfa_reponses: dict | None = None,
    force_medical_redirect: bool = False,
) -> str:
    """
    Génère la prochaine question selon l'ordre strict CERFA 15692.

    Args:
        cerfa_reponses         : mapping {field_name: valeur_fournie} — état persisté par l'appelant.
                                 L'appelant doit mettre à jour ce dict AVANT d'appeler cette fonction
                                 (via extract_cerfa_field_from_reply) puis le sauvegarder en base.
        force_medical_redirect : Si True, retourne le message de redirection canal sécurisé
                                 sans appel LLM. L'appelant a détecté que le prochain champ
                                 est un champ médical non collecté via WhatsApp.
    """
    cerfa_reponses = cerfa_reponses or {}

    # Redirection canal sécurisé (champs médicaux)
    if force_medical_redirect:
        logger.info("[CONV_AGENT] Message de redirection canal sécurisé envoyé.")
        return _MESSAGE_CANAL_SECURISE

    next_field = get_next_cerfa_field(cerfa_reponses)

    # Le sentinel indique que le message de redirection doit être envoyé
    if next_field == _MEDICAL_REDIRECT_SENT_KEY:
        logger.info("[CONV_AGENT] Sentinel médical détecté → redirection canal sécurisé.")
        return _MESSAGE_CANAL_SECURISE

    if next_field is None:
        return (
            "✅ Toutes les informations ont bien été collectées.\n\n"
            "Le dossier est en cours de finalisation. Vous recevrez le CERFA pré-rempli "
            "et le résumé du dossier par email sous peu.\n\n"
            "Votre accompagnateur complétera les éléments médicaux directement à partir "
            "des documents du médecin. Bien cordialement, l'équipe Facilim."
        )

    next_label = CERFA_FIELD_LABELS[next_field]

    # Contexte : champs déjà renseignés (uniquement les champs avec valeur)
    answered_lines = [
        f"  ✓ {CERFA_FIELD_LABELS.get(f, f)} : {v}"
        for f, v in cerfa_reponses.items()
        if v and not f.startswith("__")
    ]
    answered_ctx = (
        "\n".join(answered_lines)
        if answered_lines
        else "  (aucun champ encore renseigné)"
    )

    sujet = "de l'enfant" if is_enfant else "de la personne"

    # Instructions spécifiques par champ
    field_hints = {
        "urgence_droits": (
            "Explique brièvement pourquoi c'est important : si les droits expirent dans moins "
            "de 2 mois, on peut utiliser une procédure simplifiée pour éviter une interruption."
        ),
        "protection_juridique": (
            "Si la personne est sous tutelle ou curatelle, précise que le tuteur/curateur "
            "devra donner son accord par écrit ou par mail, ou être l'interlocuteur principal."
        ),
        "cmi_type": (
            "CMI priorité = difficultés à rester debout longtemps (file d'attente, supermarché). "
            "CMI stationnement = difficultés à se déplacer ou périmètre de marche limité à 200m."
        ),
        "emploi_accompagne": (
            "Droit commun = la personne peut chercher un emploi seule (service public de l'emploi). "
            "Emploi accompagné = la personne a un projet professionnel mais a besoin d'un soutien "
            "renforcé pour trouver et maintenir un emploi."
        ),
        "ressources_actuelles": (
            "Demande : allocations déjà reçues (AAH, APL, ARE, ASS, pension invalidité) "
            "ET frais importants liés au handicap non remboursés (transports, matériel, soins…)."
        ),
        "organisme_payeur": (
            "CAF = Caisse d'Allocations Familiales (la plupart des familles). "
            "MSA = Mutualité Sociale Agricole (agriculteurs et salariés agricoles)."
        ),
        "type_logement_statut": (
            "Exemple de réponses attendues : 'appartement locataire', 'maison propriétaire', "
            "'hébergé chez ses parents', 'foyer de vie'. "
            "Si la personne vit dans un établissement médico-social, le préciser."
        ),
        "scolarite_details": (
            "PPS = Projet Personnalisé de Scolarisation (accompagnement spécifique pour élève en situation de handicap). "
            "PAI = Projet d'Accueil Individualisé (aménagements pour maladie ou allergie). "
            "AESH = Accompagnant des Élèves en Situation de Handicap (aide humaine en classe). "
            "ULIS = dispositif spécialisé en classe ordinaire."
        ),
        "qualification_parcours": (
            "Cette information sert à remplir le parcours professionnel dans le dossier MDPH. "
            "Exemple : 'CAP menuisier, dernier emploi magasinier chez Leroy Merlin en 2019'. "
            "Ou : 'Bac pro comptabilité, en formation depuis 2022'. "
            "Ou : 'sans qualification, a toujours travaillé dans le bâtiment'. "
            "Si la personne n'a jamais travaillé, préciser simplement 'sans emploi depuis toujours'."
        ),
    }
    hint = field_hints.get(next_field, "")

    # Détecter si l'utilisateur signale que l'info est déjà dans le bilan / déjà répondu
    _msg_lower = message_entrant.lower()
    _deja_patterns = [
        "déjà répondu", "deja repondu", "j'ai déjà", "j'ai deja",
        "dans le bilan", "dans le dossier", "dans mon dossier",
        "c'est noté", "c'est inscrit", "c'est transmis", "c'est indiqué",
        "mon accompagnateur", "déjà transmis", "deja transmis",
        "déjà indiqué", "deja indique", "vous l'avez", "tu l'as",
    ]
    _urgence_patterns = ["en urgence", "urgent", "j'ai besoin", "rapidement", "vite"]
    _is_deja_bilan   = any(p in _msg_lower for p in _deja_patterns)
    _is_urgence      = any(p in _msg_lower for p in _urgence_patterns)

    # Note de contexte urgence
    urgence_note = (
        "\n⚠️  LA PERSONNE SIGNALE UNE URGENCE. Accuse réception de l'urgence en 1 phrase, "
        "rassure-la, et pose la question essentielle sans perdre de temps.\n"
        if _is_urgence else ""
    )

    # Note de contexte "déjà répondu / dans le bilan"
    deja_note = (
        "\n⚠️  LA PERSONNE DIT QUE L'INFORMATION EST DÉJÀ DANS LE BILAN OU QU'ELLE A DÉJÀ RÉPONDU. "
        "NE PAS reposer la question. Répondre : 'Bien reçu, j'ai cette information dans le dossier.' "
        "puis passer directement à la prochaine question non encore renseignée.\n"
        if _is_deja_bilan else ""
    )

    system = (
        f"Tu es l'Assistant Facilim, spécialisé dans la constitution de dossiers MDPH.\n"
        f"Tu discutes via WhatsApp pour constituer le dossier MDPH {sujet}.\n"
        f"Langue : français simple, bienveillant, FALC (phrases courtes, mots courants).\n"
        f"{urgence_note}{deja_note}\n"
        f"RÔLE DU CERFA : Le formulaire MDPH porte sur les conséquences concrètes du\n"
        f"handicap dans la vie quotidienne — pas sur les données médicales.\n"
        f"NE JAMAIS demander : diagnostic, médicaments, nom du médecin, taux d'incapacité,\n"
        f"numéro de sécurité sociale (ces infos sont collectées par le médecin/l'éducateur).\n\n"
        f"DONNÉES DÉJÀ COLLECTÉES (ne pas re-demander) :\n{answered_ctx}\n\n"
        f"PROCHAIN CHAMP À COLLECTER : {next_label}\n"
        f"{('CONSEIL POUR CE CHAMP : ' + hint) if hint else ''}\n\n"
        f"RÈGLES ABSOLUES :\n"
        f"- Accuse d'abord réception en 1 phrase courte et chaleureuse\n"
        f"- Si l'information est dans 'DONNÉES DÉJÀ COLLECTÉES' → ne la re-demande PAS\n"
        f"- Pose UNIQUEMENT la question sur : {next_label}\n"
        f"- Pour les champs fonctionnels (difficultés, besoins) : formule en termes\n"
        f"  de vie quotidienne, pas médicaux. Ex : 'Qu'est-ce qui est difficile au quotidien ?'\n"
        f"- Ne demande PAS d'autres informations dans ce message\n"
        f"- Ne répète jamais une question déjà posée et répondue\n"
        f"- N'invente jamais d'information\n"
        f"- Réponse max : 3 phrases + 1 question"
    )

    messages = [{"role": "system", "content": system}]
    for msg in historique[-8:]:
        role    = msg.get("role", "user")
        content = msg.get("content") or msg.get("reponse") or ""
        if content and role in ("user", "assistant"):
            messages.append({"role": role, "content": str(content)})
    messages.append({"role": "user", "content": message_entrant})

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=250,
            temperature=0.5,
        )
        reponse = response.choices[0].message.content.strip()
        logger.info(f"[CONV_AGENT] Champ={next_field} | {len(reponse)} chars")
        return reponse
    except Exception as e:
        logger.error(f"[CONV_AGENT] Erreur LLM : {e}")
        return f"Merci pour votre message. Pouvez-vous me préciser : {next_label} ?"


# ---------------------------------------------------------------------------
# Utilitaire historique
# ---------------------------------------------------------------------------

def construire_historique_conversation(reponses_json: list) -> list[dict]:
    """Convertit les réponses stockées en historique de conversation pour le LLM."""
    historique = []
    for rep in reponses_json or []:
        if isinstance(rep, dict):
            role    = rep.get("role", "user")
            content = rep.get("content") or rep.get("reponse") or ""
            if content:
                historique.append({"role": role, "content": str(content)})
        elif isinstance(rep, str) and rep.strip():
            historique.append({"role": "user", "content": rep})
    return historique
