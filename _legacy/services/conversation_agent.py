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

from app.engines.rules_engine import executer_regles_metier_mdph
from app.database.schemas import (
    DossierCERFA,
    SectionA_Identite,
    SectionC_VieQuotidienne,
    SectionD_SituationPro,
    SectionE_ProjetPro,
    SectionF_VieAidant,
    AidantFamilial,
    SituationJuridique,
    IdentitePersonne,
    Section_Urgence,
)

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
    "🔒 Pour protéger vos données de santé, certaines informations ne peuvent "
    "pas être partagées par WhatsApp.\n\n"
    "Merci de nous envoyer les éléments suivants *par email* à :\n"
    "📧 *contactfacilim@gmail.com*\n\n"
    "• Votre numéro de sécurité sociale\n"
    "• Votre diagnostic médical et sa date\n"
    "• Le nom et la ville de votre médecin traitant\n"
    "• Vos traitements en cours\n"
    "• Votre taux d'incapacité si vous avez déjà un dossier MDPH\n\n"
    "Indiquez simplement votre nom en objet de l'email.\n"
    "Nous intégrerons ces informations directement dans votre dossier. "
    "Merci pour votre aide !"
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
    # Scolarité enfant — collectés via WhatsApp (C8/C9 Sarah)
    "nom_ecole":               "le nom exact de l'établissement scolaire (ex : École élémentaire Jean Jaurès, IME Les Pins…)",
    "gevasco_disponible":      "si un document GEVASCO récent est disponible (oui / non) — ce document décrit les besoins de l'enfant à l'école",
    # Médical — hors WhatsApp
    "numero_securite_sociale":    "le numéro de sécurité sociale (15 chiffres)",
    "diagnostic_principal":       "le diagnostic médical précis (pathologie, depuis quand, confirmé par quel médecin)",
    "medecin_traitant":           "le nom et la ville du médecin traitant",
    "traitements_en_cours":       "les traitements médicaux en cours (médicaments, thérapies, fréquence)",
    "taux_incapacite":            "le taux d'incapacité reconnu par la MDPH (indiqué sur la dernière notification)",
}

# ---------------------------------------------------------------------------
# Champs non applicables au profil ENFANT (< 16 ans)
# Ces champs ne doivent jamais être demandés à un parent pour son enfant.
# Ils sont pré-remplis automatiquement ou ignorés. (C1 / C2 Sarah)
# ---------------------------------------------------------------------------
_CHAMPS_NON_ENFANT: frozenset[str] = frozenset({
    "situation_familiale",    # un enfant n'est pas célibataire/marié
    "enfants_a_charge",       # un enfant n'a pas d'enfants à charge
    "emploi_accompagne",      # pas de projet professionnel pour un jeune enfant
    "type_logement_statut",   # un enfant vit chez ses parents
    "qualification_parcours", # pas de parcours pro pour un enfant
    "situation_pro_scolaire", # remplacé par scolarite_details pour les enfants
})

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
# PROMPT MAÎTRE — Intelligence métier MDPH (adapté dialogue WhatsApp)
#
# Ce bloc est injecté dans TOUS les appels LLM de generer_reponse_agent.
# Il ne remplace pas la structure des 5 groupes : il pilote le RAISONNEMENT
# à l'intérieur de chaque groupe (priorisation, transformation, qualité).
# ---------------------------------------------------------------------------

_PROMPT_MAITRE_WHATSAPP = """
Tu es Mathilde, une assistante gentille qui aide à remplir un dossier MDPH sur WhatsApp. Ton seul but est de poser des questions simples à l'utilisateur, une par une, pour découvrir s'il utilise un fauteuil roulant, s'il a du mal à marcher ou s'il a besoin d'aide pour la toilette. Ne cherche pas à deviner les cases du formulaire CERFA, collecte juste les réponses de l'utilisateur.

━━━ RÈGLE AIDANT (NON NÉGOCIABLE) ━━━
Si l'usager mentionne qu'un proche l'aide (mari, femme, enfant, voisin…),
cette information va EXCLUSIVEMENT dans le champ "aidant_identite".
Elle ne doit JAMAIS apparaître dans "ressources_actuelles" ni dans les "frais".
Les frais sont uniquement des sommes d'argent payées (matériel, soins privés).

━━━ RÈGLE URGENCE (NON NÉGOCIABLE) ━━━
Si l'usager dit "c'est un renouvellement, pas d'urgence", "pas urgent", "aucune urgence"
ou toute formulation négative sur l'urgence → urgence_droits = False de manière absolue.
Ne jamais supposer l'urgence par défaut. En cas de doute → False.
"""


def _detecter_profil(cerfa_reponses: dict) -> str:
    """
    Détecte automatiquement le profil MDPH selon la date de naissance.
    Retourne : 'enfant' (0-15 ans) | 'jeune' (16-25 ans) | 'adulte' (26+ ans) | 'inconnu'
    """
    ddn = cerfa_reponses.get("date_naissance", "")
    if not ddn or "/" not in ddn:
        return "inconnu"
    try:
        from datetime import date as _dt
        p = ddn.split("/")
        if len(p) == 3:
            age = (_dt.today() - _dt(int(p[2]), int(p[1]), int(p[0]))).days // 365
            if age <= 15:
                return "enfant"
            if age <= 25:
                return "jeune"
            return "adulte"
    except Exception:
        pass
    return "inconnu"


def _contexte_profil(profil: str) -> str:
    """Retourne la note de profil à insérer dans les system prompts."""
    if profil == "enfant":
        return (
            "PROFIL DÉTECTÉ : ENFANT (0-15 ans)\n"
            "━━━ RÈGLES ABSOLUES PROFIL ENFANT ━━━\n"
            "→ Tu t'adresses AU PARENT, jamais à l'enfant.\n"
            "→ Toujours formuler : 'Votre enfant…', 'Votre fils/fille…', 'Il/elle…'\n"
            "→ JAMAIS de 'je' ou 'vous' pour l'enfant. JAMAIS de 'Êtes-vous célibataire ?'\n"
            "→ JAMAIS demander : situation familiale, enfants à charge, logement propre,\n"
            "   emploi, niveau de formation, emploi accompagné.\n"
            "→ Ces champs sont déjà pré-remplis 'non concerné (enfant)'.\n"
            "→ Priorité absolue : scolarité (nom école, classe, AESH, PPS/PAI), AEEH,\n"
            "   difficultés quotidiennes, aidant familial (nom/prénom du parent).\n"
            "→ Demander le GEVASCO si scolarisé.\n"
        )
    if profil == "jeune":
        return (
            "PROFIL DÉTECTÉ : JEUNE / TRANSITION (16-25 ans)\n"
            "→ Vérifier : études, IME, CFA, insertion, logement\n"
            "→ Si IME : 'parcours scolaire adapté' (jamais 'classe ordinaire fictive')\n"
            "→ Droits : AAH, RQTH, ESAT, formation, logement accompagné\n"
            "→ Adapter le tutoiement selon le répondant (jeune ou parent)\n"
        )
    if profil == "adulte":
        return (
            "PROFIL DÉTECTÉ : ADULTE (26+ ans)\n"
            "→ Ne pas poser de questions scolaires\n"
            "→ Priorité : emploi, ESAT, inactivité, logement\n"
        )
    return "PROFIL : non encore déterminé (date de naissance manquante)\n"


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

    # Type de droits demandés (seul champ métier pré-rempli — vient de l'analyse IA, pas du bilan)
    droits = analyse.get("droits_identifies") or []
    if droits:
        _set("type_droits", ", ".join(droits))

    # Situation professionnelle / scolaire
    _set("situation_pro_scolaire", ds.get("situation_professionnelle"))

    # ── Champs JAMAIS pré-remplis — toujours demander à la famille via WhatsApp ──
    # Ces informations peuvent avoir changé depuis le document, ou n'y figurent pas :
    #   - situation_familiale  : peut avoir évolué (mariage, veuvage, séparation…)
    #   - type_demande         : première demande ou renouvellement → à confirmer
    #   - organisme_payeur     : CAF / MSA / autre → ne pas supposer
    #   - protection_juridique : tutelle / curatelle → ne pas supposer "aucune"
    #   - historique_mdph      : numéro de dossier existant → jamais dans un bilan
    #   - numero_secu          : jamais dans un bilan professionnel
    # Ces champs restent VIDES ici et seront collectés par le dialogue WhatsApp.

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

    # Lieu de naissance (page 2) — depuis les données structurées de l'analyse IA
    # Ces champs ne sont jamais demandés via WhatsApp (trop intrusifs) :
    # ils viennent du bilan ou de la saisie éducateur uniquement.
    _set("commune_naissance",     ds.get("commune_naissance"))
    _set("departement_naissance", ds.get("departement_naissance"))
    _set("pays_naissance",        ds.get("pays_naissance"))

    # NSS — pré-rempli si déjà connu via canal sécurisé (email médical)
    # Pour un enfant, c'est le NIR du parent déclarant (pas celui de l'enfant).
    _set("numero_securite_sociale", ds.get("nss") or ds.get("numero_securite_sociale"))

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

    # Historique MDPH — interface éducateur (priorité absolue) > ds > bilan
    # CORRECTION 1 : Le numéro MDPH peut être saisi directement dans l'interface
    # (champs dossier.numero_mdph / dossier.historique_mdph / dossier.numero_dossier_mdph).
    # C'est la source la plus fiable — ne jamais la redemander via WhatsApp.
    _num_mdph_interface = (
        dossier.get("numero_mdph")
        or dossier.get("historique_mdph")
        or dossier.get("numero_dossier_mdph")
        or ""
    ).strip()
    _num_mdph_ds = (ds.get("numero_dossier_mdph") or ds.get("historique_mdph") or "").strip()
    _num_mdph_final = _num_mdph_interface or _num_mdph_ds
    _set("historique_mdph", _num_mdph_final)

    # Type de demande — première vs renouvellement
    # CORRECTION 1 : Si un numéro de dossier est présent (interface ou ds),
    # la demande est OBLIGATOIREMENT un renouvellement. Ne pas redemander.
    if not cerfa_reponses.get("type_demande"):
        _type_dem = (ds.get("type_demande") or "").strip()
        if not _type_dem and ds.get("deja_connu_mdph"):
            _type_dem = "renouvellement"
        _set("type_demande", _type_dem)
    # Forcer renouvellement si numéro présent, quelle que soit la valeur actuelle de type_demande
    if _num_mdph_final and any(c.isdigit() for c in _num_mdph_final):
        _mots_premiere = ["premiere", "première", "1ere", "jamais", "nouveau"]
        _td_actuel = cerfa_reponses.get("type_demande", "").lower()
        if not _td_actuel or any(w in _td_actuel for w in _mots_premiere):
            cerfa_reponses["type_demande"] = "renouvellement"
            logger.info(
                f"[PREPOPULER C1] Numéro MDPH détecté ({_num_mdph_final!r}) "
                "→ type_demande forcé à 'renouvellement'."
            )

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

    # ── CORRECTION 2 (Sarah) — Pré-remplissage automatique profil ENFANT ──────
    # Pour un enfant (< 16 ans), les champs non applicables sont pré-remplis
    # avec des valeurs sentinelles "non concerné (enfant)" afin qu'ils n'apparaissent
    # jamais comme "manquants" dans l'interface et ne soient pas demandés via WhatsApp.
    _ddn_enfant = (dossier.get("ddn_enfant") or cerfa_reponses.get("date_naissance") or "").strip()
    _est_enfant_prepop = False
    if _ddn_enfant and "/" in _ddn_enfant:
        try:
            from datetime import date as _dte
            _dp = _ddn_enfant.split("/")
            if len(_dp) == 3:
                _age_prepop = (_dte.today() - _dte(int(_dp[2]), int(_dp[1]), int(_dp[0]))).days // 365
                _est_enfant_prepop = _age_prepop < 16
        except Exception:
            pass

    if _est_enfant_prepop:
        # Champs non applicables → sentinelle "non concerné (enfant)"
        # N'écrasent jamais une valeur déjà saisie par la famille
        _set("situation_familiale",    "non concerné (enfant)")
        _set("enfants_a_charge",       "0")
        _set("situation_pro_scolaire", "non concerné (enfant)")
        _set("emploi_accompagne",      "non concerné (enfant)")
        _set("type_logement_statut",   "vit chez ses parents")
        _set("qualification_parcours", "non concerné (enfant)")
        logger.info(
            f"[PREPOPULER C2] Profil ENFANT détecté (âge={_age_prepop} ans) "
            "→ champs non applicables pré-remplis automatiquement."
        )

    # CORRECTION 3 (Sarah) — NIR depuis l'interface éducateur au moment du pré-remplissage
    # La correction précédente C2 le fait dans cerfa_filler ; on le fait aussi ici
    # pour que le bot WhatsApp ne redemande pas le NIR si déjà dans l'interface.
    _nir_interface = (
        dossier.get("numero_securite_sociale")
        or dossier.get("nss")
        or ""
    ).replace(" ", "").replace(".", "").replace("-", "")
    if _nir_interface and _nir_interface.isdigit():
        _set("numero_securite_sociale", _nir_interface)


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
# Règles de nettoyage automatique — cohérence interface graphique
# ---------------------------------------------------------------------------

def appliquer_regles_nettoyage(cerfa_reponses: dict) -> None:
    """
    Marque automatiquement les champs non-applicables avec une valeur sentinelle
    pour qu'ils n'apparaissent plus en rouge dans l'interface comme 'manquants'.

    Règle 1 : Adulte (≥ 18 ans) → scolarite_details, nom_ecole, gevasco non applicables.
    Règle 2 : historique_mdph contient un chiffre → forcer type_demande = 'renouvellement'.
    Règle 4 : type_demande = 'premiere' → urgence_droits non applicable.

    À appeler juste après prepopuler_cerfa_depuis_dossier à chaque message entrant.
    Ne remplace jamais une valeur déjà saisie par l'usager.
    """
    from datetime import date as _dt

    # ── Règle 1 : Adulte → champs scolarité non applicables ──────────────────
    _ddn = cerfa_reponses.get("date_naissance", "")
    if _ddn and "/" in _ddn:
        try:
            _p = _ddn.split("/")
            if len(_p) == 3:
                _age = (_dt.today() - _dt(int(_p[2]), int(_p[1]), int(_p[0]))).days // 365
                if _age >= 18:
                    cerfa_reponses.setdefault("scolarite_details", "N/A (adulte)")
                    cerfa_reponses.setdefault("nom_ecole",          "N/A (adulte)")
                    cerfa_reponses.setdefault("gevasco_disponible", "N/A (adulte)")
                    logger.debug(f"[NETTOYAGE R1] Adulte ({_age} ans) → scolarité marquée N/A")
        except Exception:
            pass

    # ── Règle 2 : historique_mdph renseigné → forcer renouvellement ──────────
    _hist = cerfa_reponses.get("historique_mdph", "")
    if _hist and any(c.isdigit() for c in _hist):
        _td_actuel = cerfa_reponses.get("type_demande", "").lower()
        _mots_premiere = ["premiere", "première", "nouveau", "jamais", "1ere"]
        if not _td_actuel or any(w in _td_actuel for w in _mots_premiere):
            cerfa_reponses["type_demande"] = "renouvellement"
            logger.info(
                f"[NETTOYAGE R2] historique_mdph={_hist!r} → type_demande forcé 'renouvellement'"
            )

    # ── Règle 4 : première demande → urgence_droits non applicable ────────────
    _td = cerfa_reponses.get("type_demande", "").lower()
    _mots_premiere = ["premiere", "première", "nouveau", "jamais", "1ere"]
    if any(w in _td for w in _mots_premiere):
        cerfa_reponses.setdefault("urgence_droits", "N/A (première demande)")
        logger.debug("[NETTOYAGE R4] Première demande → urgence_droits marqué N/A")


# ---------------------------------------------------------------------------
# Groupes de questions CERFA — max 5 messages au lieu de 22
# Chaque groupe est envoyé en un seul message WhatsApp.
# L'extraction multi-champs se fait sur chaque champ du groupe après réponse.
# ---------------------------------------------------------------------------

CERFA_GROUPES: list[dict] = [
    {
        # CORRECTION 4 : ajout de nom_prenom, date_naissance, genre, adresse_complete.
        # Ces champs étaient absents de tous les groupes → posés un par un en mode
        # résiduel APRÈS les 5 groupes, ce qui donnait l'impression que le nom/prénom
        # était demandé à la fin. prepopuler_cerfa_depuis_dossier les remplit
        # automatiquement si le dossier les contient — dans ce cas ils sont skippés
        # et la question de groupe ne les mentionne pas (get_next_groupe_cerfa filtre
        # les champs déjà remplis avant d'envoyer).
        "id": "type_demande",
        "champs": [
            "type_demande", "urgence_droits",
            "nom_prenom", "date_naissance", "genre", "adresse_complete",
        ],
        "question_falc": (
            "Bonjour 👋 Je suis Mathilde, de l'équipe Facilim. Je vous accompagne pour constituer votre dossier MDPH via WhatsApp. Pour commencer, j'ai quelques questions simples.\n\n"
            "1️⃣ S'agit-il d'une *première demande* à la MDPH, ou d'un *renouvellement* de droits existants ?\n"
            "2️⃣ Si c'est un renouvellement : vos droits actuels expirent-ils dans moins de 2 mois ?\n"
            "3️⃣ Quel est le *nom et prénom complet* de la personne concernée ?\n"
            "4️⃣ Quelle est sa *date de naissance* ? (format JJ/MM/AAAA)\n"
            "5️⃣ Est-ce un *homme* ou une *femme* ?\n"
            "6️⃣ Quelle est son *adresse complète* ? (numéro, rue, code postal, ville)"
        ),
    },
    {
        "id": "situation_vie",
        # C1 Sarah : les champs non_enfant (situation_familiale, enfants_a_charge,
        # type_logement_statut) sont filtrés par get_next_groupe_cerfa pour le profil ENFANT.
        # La question_falc adulte reste la référence ; le LLM reçoit les instructions de
        # profil dans system_groupe et adapte le texte au contexte parent/enfant.
        "champs": [
            "situation_familiale", "enfants_a_charge",
            "type_logement_statut", "organisme_payeur", "protection_juridique",
        ],
        "question_falc": (
            "Merci ! Quelques questions sur votre situation de vie :\n\n"
            "1️⃣ Êtes-vous *célibataire*, marié·e, en couple, divorcé·e ou veuf·ve ?\n"
            "2️⃣ Avez-vous des *enfants à charge* ? (oui/non, et combien)\n"
            "3️⃣ Quel est votre *type de logement* ? (appartement, maison…) et êtes-vous propriétaire ou locataire ?\n"
            "4️⃣ Votre organisme d'allocations : *CAF* ou *MSA* ?\n"
            "5️⃣ Êtes-vous sous *tutelle ou curatelle* ? (oui/non)\n\n"
            "[VERSION PARENT/ENFANT — utilisée par le LLM si profil ENFANT :\n"
            "1️⃣ Votre organisme d'allocations familiales : *CAF* ou *MSA* ?\n"
            "2️⃣ Votre enfant est-il sous mesure de *tutelle ou curatelle* ? (oui/non — dans la grande majorité des cas la réponse est non)]"
        ),
    },
    {
        "id": "difficultes",
        # CORRECTION 7 : aidant_identite ajouté à ce groupe — collecté systématiquement
        # quand une aide humaine est décrite (profil enfant/jeune ou aide quotidienne).
        # La question est posée de façon naturelle après besoins_aide.
        "champs": ["difficultes_quotidiennes", "besoins_aide", "aidant_identite", "ressources_actuelles"],
        "question_falc": (
            "Maintenant, parlez-moi de votre quotidien :\n\n"
            "1️⃣ Quelles sont vos *principales difficultés* dans la vie de tous les jours ?\n"
            "   (ce que vous ne pouvez pas faire seul·e, ce qui est épuisant ou douloureux)\n"
            "2️⃣ De quelles *aides* avez-vous besoin ?\n"
            "   (aide humaine, matériel, aménagements…)\n"
            "3️⃣ *Qui vous accompagne au quotidien ?*\n"
            "   Si quelqu'un vous aide régulièrement (parent, conjoint, proche), "
            "indiquez son prénom, nom et son lien avec vous.\n"
            "   (exemple : Marie Dupont, mère / Jean Martin, conjoint)\n"
            "   Si personne ne vous aide, répondez simplement 'personne'.\n"
            "4️⃣ Quelles sont vos *ressources actuelles* ?\n"
            "   (allocations comme AAH, APL, pension d'invalidité, ou aucune)"
        ),
    },
    {
        "id": "parcours",
        # C8 Sarah : nom_ecole ajouté — obligatoire profil ENFANT.
        # C9 Sarah : gevasco_disponible ajouté — GEVASCO demandé si scolarisé.
        # Pour un adulte, ces deux champs sont skippés par get_next_groupe_cerfa
        # (via la règle scolarite_details + profil).
        "champs": [
            "situation_pro_scolaire", "qualification_parcours", "scolarite_details",
            "nom_ecole", "gevasco_disponible",
        ],
        "question_falc": (
            "Quelques questions sur votre parcours :\n\n"
            "1️⃣ Quelle est votre *situation actuelle* ?\n"
            "   (en emploi, en recherche d'emploi, en formation, sans activité, scolarisé·e…)\n"
            "2️⃣ Quel est votre *niveau de formation* et votre dernier emploi ou métier ?\n"
            "   (exemple : CAP plombier, dernier emploi caissière en 2020)\n\n"
            "[VERSION PARENT/ENFANT — utilisée par le LLM si profil ENFANT :\n"
            "1️⃣ Dans quel établissement scolaire est scolarisé votre enfant ?\n"
            "   *Indiquez le nom exact* (ex : École élémentaire Jean Jaurès, IME Les Pins…)\n"
            "2️⃣ Quelle classe fréquente-t-il/elle ? (CP, CE1, CE2…)\n"
            "3️⃣ Des aménagements sont-ils en place à l'école ?\n"
            "   (AESH, tiers-temps, matériel adapté, ULIS, PPS, PAI…)\n"
            "4️⃣ Avez-vous un document *GEVASCO* récent ? (oui / non)\n"
            "   Si oui, vous pourrez nous l'envoyer par email à contactfacilim@gmail.com]"
        ),
    },
    {
        "id": "droits",
        "champs": ["type_droits", "cmi_type", "emploi_accompagne", "historique_mdph"],
        "question_falc": (
            "Dernière étape !\n\n"
            "1️⃣ Quels *droits souhaitez-vous demander* à la MDPH ?\n"
            "   (exemples : AAH, RQTH, PCH, CMI, orientation ESAT/IME…)\n"
            "2️⃣ Si vous demandez une *carte mobilité* (CMI) :\n"
            "   - Priorité (difficultés à rester debout longtemps) ?\n"
            "   - Stationnement (déplacements très limités) ?\n"
            "   - Ou les deux ?\n"
            "3️⃣ Si vous avez déjà un dossier MDPH : quel est votre *numéro de dossier* ?"
        ),
    },
]


def get_next_groupe_cerfa(cerfa_reponses: dict) -> dict | None:
    """
    Retourne le prochain groupe de questions à envoyer sur WhatsApp.
    Un groupe est "à envoyer" si AU MOINS UN champ non-médical est encore vide
    ET que le sentinel '__groupe_<id>__' n'est pas encore 'sent'.
    Retourne None quand tous les groupes sont couverts.
    """
    type_d          = cerfa_reponses.get("type_demande", "").lower()
    is_first        = any(w in type_d for w in ["premiere", "première", "jamais", "nouveau"])
    is_renouvellement = "renouvellement" in type_d
    # CORRECTION 1 — Un numéro de dossier présent dans historique_mdph
    # signifie que la personne est déjà connue de la MDPH → pas une première demande.
    _historique_val = cerfa_reponses.get("historique_mdph", "")
    if _historique_val and any(c.isdigit() for c in _historique_val):
        is_first          = False
        is_renouvellement = True
    type_droits_val = cerfa_reponses.get("type_droits", "").lower()
    has_cmi = any(w in type_droits_val for w in ["cmi", "carte mobilite", "carte invalidite"])
    has_orp = any(w in type_droits_val for w in ["orp", "rqth", "emploi", "esat"])

    # C1 Sarah : détection du profil pour filtrer les champs inadaptés
    _profil_groupe   = _detecter_profil(cerfa_reponses)
    _est_enfant_grp  = _profil_groupe == "enfant"

    for groupe in CERFA_GROUPES:
        gid = f"__groupe_{groupe['id']}__"

        # Groupe déjà envoyé → suivant
        if cerfa_reponses.get(gid) == "sent":
            continue

        # Construire la liste des champs vraiment utiles (non médicaux, non déjà remplis)
        champs_utiles = []
        for c in groupe["champs"]:
            if c in MEDICAL_FIELDS:
                continue
            if cerfa_reponses.get(c) and str(cerfa_reponses[c]) not in ("__via_email__", "sent", ""):
                continue  # déjà rempli

            # C1 Sarah : champs inadaptés au profil ENFANT → skip silencieux
            if _est_enfant_grp and c in _CHAMPS_NON_ENFANT:
                continue

            # Règles conditionnelles identiques à get_next_cerfa_field
            if c == "urgence_droits":
                if is_first or (type_d and not is_renouvellement):
                    continue
            if c == "historique_mdph" and is_first:
                continue
            if c == "historique_mdph" and cerfa_reponses.get("historique_mdph"):
                continue
            if c == "cmi_type" and not has_cmi:
                continue
            if c == "emploi_accompagne" and not has_orp:
                continue
            if c in ("scolarite_details", "nom_ecole", "gevasco_disponible"):
                ddn = cerfa_reponses.get("date_naissance", "")
                if ddn:
                    try:
                        from datetime import date as _dt
                        p = ddn.split("/")
                        if len(p) == 3:
                            age = (_dt.today() - _dt(int(p[2]), int(p[1]), int(p[0]))).days // 365
                            if age >= 18:
                                continue  # adulte → pas de scolarité
                    except Exception:
                        pass
                else:
                    if c in ("nom_ecole", "gevasco_disponible"):
                        continue  # âge inconnu → ne pas poser les questions scolarité
                    else:
                        continue  # scolarite_details : âge inconnu → reporter
            if c == "qualification_parcours":
                if not any(w in type_droits_val for w in ["rqth", "orp", "aah", "emploi"]):
                    continue

            champs_utiles.append(c)

        if champs_utiles:
            return groupe

    return None  # tous les groupes sont couverts


# ---------------------------------------------------------------------------
# Logique de progression CERFA (champ par champ — utilisé en fallback)
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
    # CORRECTION 1 — Un numéro de dossier dans historique_mdph → pas une première demande
    _hist_val = cerfa_reponses.get("historique_mdph", "")
    if _hist_val and any(c.isdigit() for c in _hist_val):
        is_first          = False
        is_renouvellement = True
    has_cmi = any(w in type_droits_val for w in ["cmi", "carte mobilite", "carte invalidite"])
    has_orp = any(
        w in type_droits_val
        for w in ["orp", "orientation pro", "rqth", "emploi", "esat", "travail"]
    )

    # C1 Sarah : détection du profil pour filtrer les champs inadaptés
    _profil_field  = _detecter_profil(cerfa_reponses)
    _est_enfant_f  = _profil_field == "enfant"

    for field in CERFA_FIELD_ORDER:
        # Champ déjà renseigné → suivant
        if field in cerfa_reponses and cerfa_reponses[field]:
            continue

        # Champ médical → jamais collecté via WhatsApp
        if field in MEDICAL_FIELDS:
            medical_pending = True
            continue

        # C1 Sarah : champs inadaptés au profil ENFANT → toujours sautés
        if _est_enfant_f and field in _CHAMPS_NON_ENFANT:
            continue

        # ── Champs conditionnels ─────────────────────────────────────────────

        # urgence_droits : uniquement si renouvellement
        if field == _URGENCE:
            if not is_renouvellement and not type_d:
                continue  # type_demande pas encore répondu → sauter pour l'instant
            if is_first or (type_d and not is_renouvellement):
                continue  # Pas un renouvellement → pas besoin de demander l'urgence

        # historique_mdph : inutile pour une première demande
        # CORRECTION 1 : si déjà renseigné (interface ou ds) → ne pas redemander
        if field == _HISTORIQUE:
            if cerfa_reponses.get(_HISTORIQUE):
                continue   # déjà connu — ne pas poser la question
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


def extract_groupe_cerfa_from_reply(
    message: str,
    champs: list[str],
    openai_client: Any,
) -> dict[str, str]:
    """
    Extrait TOUS les champs d'un groupe CERFA en UN SEUL appel LLM (JSON).
    Bien plus fiable que N appels séparés : le modèle voit tous les champs
    en même temps et distribue correctement les informations.

    Retourne un dict {champ: valeur} — seuls les champs trouvés sont inclus.
    """
    import json as _json

    champs_labels = {c: CERFA_FIELD_LABELS.get(c, c) for c in champs}
    champs_json   = "\n".join(f'  "{c}": "{label}"' for c, label in champs_labels.items())

    system_prompt = (
        "Tu es un assistant qui extrait des informations depuis un message WhatsApp "
        "pour remplir un formulaire MDPH.\n\n"
        "CHAMPS À EXTRAIRE (clé JSON : description) :\n"
        "{\n" + champs_json + "\n}\n\n"
        "Réponds UNIQUEMENT en JSON valide avec les valeurs extraites.\n"
        "Si un champ n'est pas présent dans le message, mets null.\n"
        "Exemple : {\"situation_familiale\": \"célibataire\", \"enfants_a_charge\": \"0\", ...}"
    )

    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": message},
            ],
            max_tokens=300,
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content.strip()
        data = _json.loads(raw)
        # Garder uniquement les valeurs non-null et non-vides
        result = {
            k: str(v).strip()
            for k, v in data.items()
            if k in champs and v is not None and str(v).strip() not in ("", "null", "None")
        }
        logger.info(f"[CONV_AGENT] Extraction groupe ({len(champs)} champs) → {len(result)} extraits : {list(result.keys())}")
        return result
    except Exception as e:
        logger.warning(f"[CONV_AGENT] Extraction groupe échouée : {e}")
        # Fallback : extraction champ par champ
        result = {}
        for champ in champs:
            val = extract_cerfa_field_from_reply(message, champ, openai_client)
            if val:
                result[champ] = val
        return result


# ---------------------------------------------------------------------------
# Mapping dict plat → DossierCERFA structuré
# ---------------------------------------------------------------------------

def cerfa_reponses_vers_dossier_cerfa(cerfa_reponses: dict) -> DossierCERFA:
    """
    Construit un DossierCERFA structuré depuis le dictionnaire plat cerfa_reponses.

    Extraction chirurgicale :
    - ProtectionJuridique : parse "tutelle de mon mari Jean Dupont" → sous-classe dédiée
    - SectionAidant       : toute aide humaine d'un proche → pages 19-20, JAMAIS dans frais
    - FraisEngages        : uniquement frais financiers prouvés
    - urgence_droits      : False par défaut — True uniquement si confirmation explicite
    """
    from datetime import date as _dt
    import re as _re

    # ── Détection du profil depuis la date de naissance ──────────────────────
    _ddn_raw = (cerfa_reponses.get("date_naissance") or "").strip()
    profil = "inconnu"
    _age   = None
    if _ddn_raw and "/" in _ddn_raw:
        try:
            _p = _ddn_raw.split("/")
            if len(_p) == 3:
                _age = (_dt.today() - _dt(int(_p[2]), int(_p[1]), int(_p[0]))).days // 365
                if _age < 16:
                    profil = "enfant"
                else:
                    _sit = (cerfa_reponses.get("situation_pro_scolaire") or "").lower()
                    _mots_actif = ["emploi", "travail", "cdi", "cdd", "formation", "apprenti", "stage"]
                    profil = "adulte"
        except Exception:
            pass

    # ── Section A — Identité ─────────────────────────────────────────────────
    _np = (cerfa_reponses.get("nom_prenom") or "").strip()
    _nom, _prenom = "", ""
    if _np:
        _parts = _np.split(" ", 1)
        _prenom = _parts[0].strip()
        _nom    = _parts[1].strip() if len(_parts) == 2 else ""

    _nir_raw = (cerfa_reponses.get("numero_securite_sociale") or "").strip()
    _nir_valid = None
    if _nir_raw:
        _cleaned = _re.sub(r"[\s.\-]", "", _nir_raw)
        _nir_valid = _cleaned if _re.fullmatch(r"\d{15}", _cleaned) else None

    # ── Protection juridique — extraction chirurgicale ────────────────────────
    _prot_raw = (cerfa_reponses.get("protection_juridique") or "").lower()
    _prot_mesure: str = "aucune"
    _prot_nom:    str | None = None
    _prot_prenom: str | None = None
    _prot_qualite: str | None = None

    if "tutelle" in _prot_raw:
        _prot_mesure  = "tutelle"
        _prot_qualite = "Tuteur"
    elif "curatelle" in _prot_raw:
        _prot_mesure  = "curatelle"
        _prot_qualite = "Curateur"
    elif "sauvegarde" in _prot_raw:
        _prot_mesure  = "sauvegarde"
        _prot_qualite = "Sauvegarde de justice"

    # Tenter d'extraire le nom du représentant depuis la phrase brute
    # ex : "tutelle de mon mari Jean Dupont" → prenom=Jean, nom=Dupont
    if _prot_mesure != "aucune":
        # Chercher un pattern "de [préposition?] Prénom NOM" dans le texte brut
        _match_rep = _re.search(
            r'\b(?:de (?:mon |ma |mes )?(?:mari|femme|époux|épouse|fils|fille|mère|père|conjoint)?\s*)?'
            r'([A-ZÀÂÉÈÊÎÔÙÛÆŒ][a-zàâéèêîïôùûüæœ]+)\s+([A-ZÀÂÉÈÊÎÔÙÛÆŒ]{2,})',
            cerfa_reponses.get("protection_juridique") or "",
        )
        if _match_rep:
            _prot_prenom = _match_rep.group(1)
            _prot_nom    = _match_rep.group(2)
        else:
            # Fallback : chercher dans aidant_identite si tutelle détectée
            _ai_raw = (cerfa_reponses.get("aidant_identite") or "").strip()
            if _ai_raw:
                _ai_parts = _ai_raw.split(",", 1)
                _ai_name  = _ai_parts[0].strip().split(" ", 1)
                if len(_ai_name) == 2:
                    _prot_prenom = _ai_name[0]
                    _prot_nom    = _ai_name[1]
                elif _ai_name:
                    _prot_nom = _ai_name[0]

    # ── Protection juridique → SituationJuridique V3 ────────────────────────
    _rep_identite = None
    if _prot_nom or _prot_prenom:
        _rep_identite = IdentitePersonne(
            nom     = _prot_nom,
            prenom  = _prot_prenom,
            qualite = _prot_qualite,
        )
    situation_juridique = SituationJuridique(
        sous_protection       = (_prot_mesure != "aucune"),
        type_mesure           = _prot_mesure,
        identite_representant = _rep_identite,
    )

    section_a = SectionA_Identite(
        nom                     = _nom or None,
        prenom                  = _prenom or None,
        date_naissance          = _ddn_raw or None,
        genre                   = cerfa_reponses.get("genre"),
        adresse_complete        = cerfa_reponses.get("adresse_complete"),
        situation_familiale     = cerfa_reponses.get("situation_familiale"),
        enfants_a_charge        = int(cerfa_reponses["enfants_a_charge"])
                                  if str(cerfa_reponses.get("enfants_a_charge", "")).isdigit() else None,
        organisme_payeur        = cerfa_reponses.get("organisme_payeur"),
        situation_juridique     = situation_juridique,
        historique_mdph         = cerfa_reponses.get("historique_mdph"),
        type_demande            = cerfa_reponses.get("type_demande"),
        numero_securite_sociale = _nir_valid,
    )

    # ── Aidant familial → AidantFamilial dans SectionF_VieAidant V3 ─────────
    _aidant_raw = (cerfa_reponses.get("aidant_identite") or "").strip()
    _mots_absence = ["personne", "aucun", "non", "pas d", "seul", "seule", "n/a"]
    _aidant_absent = not _aidant_raw or any(m in _aidant_raw.lower() for m in _mots_absence)

    _aidant_obj = AidantFamilial(a_un_aidant=False)
    if not _aidant_absent:
        _ai_parts    = _aidant_raw.split(",", 1)
        _ai_identite = _ai_parts[0].strip()
        _ai_lien     = _ai_parts[1].strip() if len(_ai_parts) > 1 else ""

        _liens_map = {
            "mari": "époux", "époux": "époux", "conjoint": "conjoint",
            "femme": "épouse", "épouse": "épouse", "compagne": "compagne",
            "compagnon": "compagnon", "mère": "mère", "mere": "mère",
            "père": "père", "pere": "père", "fils": "fils", "fille": "fille",
            "frère": "frère", "soeur": "sœur", "sœur": "sœur",
        }
        if not _ai_lien:
            for _mot, _lien_norm in _liens_map.items():
                if _mot in _ai_identite.lower():
                    _ai_lien = _lien_norm
                    _ai_identite = _re.sub(
                        rf'\b{_mot}\b', '', _ai_identite, flags=_re.IGNORECASE
                    ).strip(" ,")
                    break

        _ai_nom_parts = _ai_identite.split(" ", 1)
        _ai_prenom = _ai_nom_parts[0].strip() if _ai_nom_parts else ""
        _ai_nom    = _ai_nom_parts[1].strip() if len(_ai_nom_parts) > 1 else ""

        _aidant_obj = AidantFamilial(
            a_un_aidant   = True,
            nom           = _ai_nom or None,
            prenom        = _ai_prenom or None,
            lien_parental = _ai_lien or None,
        )

    section_f = SectionF_VieAidant(aidant=_aidant_obj)

    # ── Section C — Vie quotidienne ──────────────────────────────────────────
    _texte_diff    = (cerfa_reponses.get("difficultes_quotidiennes") or "").lower()
    _texte_besoins = (cerfa_reponses.get("besoins_aide") or "").lower()
    _texte_c       = _texte_diff + " " + _texte_besoins

    _type_log, _stat_log = "", ""
    _tls = (cerfa_reponses.get("type_logement_statut") or "")
    if "/" in _tls:
        _tls_parts = _tls.split("/", 1)
        _type_log  = _tls_parts[0].strip()
        _stat_log  = _tls_parts[1].strip()
    else:
        _type_log = _tls.strip()

    # urgence_droits : False par défaut — True uniquement si OUI explicite
    _urgence_raw = (cerfa_reponses.get("urgence_droits") or "").lower()
    _urgence_bool: bool = False
    if any(w in _urgence_raw for w in ["oui", "yes", "1", "vrai", "true", "urgent"]):
        _urgence_bool = True

    # Frais réels — uniquement financiers (str simple, conforme V3 SectionC)
    _frais_str = None
    _ressources_raw = (cerfa_reponses.get("ressources_actuelles") or "").lower()
    _frais_mots = [
        "psychologue", "orthophoniste", "ostéopath", "ergothérap",
        "matériel", "fauteuil", "appareillage", "aménagement",
        "transport", "reste à charge", "non remboursé",
    ]
    if any(w in _ressources_raw for w in _frais_mots):
        _frais_str = cerfa_reponses.get("ressources_actuelles")

    # Statut d'occupation — V3 Literal strict
    _statut_occ_raw = _stat_log.lower() if _stat_log else ""
    _statut_occ = None
    if any(w in _statut_occ_raw for w in ["proprio", "propriétaire"]):
        _statut_occ = "proprietaire"
    elif "locataire" in _statut_occ_raw:
        _statut_occ = "locataire"
    elif any(w in _statut_occ_raw for w in ["hébergé", "heberge"]):
        _statut_occ = "heberge"

    section_c = SectionC_VieQuotidienne(
        difficultes_quotidiennes    = cerfa_reponses.get("difficultes_quotidiennes"),
        besoins_aide_humaine        = any(w in _texte_besoins for w in
                                          ["aide humaine", "auxiliaire", "avs", "aide à domicile"]),
        besoins_aide_technique      = any(w in _texte_besoins for w in
                                          ["fauteuil", "déambulateur", "prothèse", "orthèse", "matériel"]),
        besoins_amenagement_logement = any(w in _texte_besoins for w in
                                           ["aménagement", "logement adapté", "rampe", "monte-escalier"]),
        type_logement               = _type_log or None,
        statut_occupation           = _statut_occ,
        ressources_actuelles        = cerfa_reponses.get("ressources_actuelles"),
        frais_reels                 = _frais_str,
        utilise_fauteuil_roulant    = "fauteuil" in _texte_c,
        difficulte_marcher          = "march" in _texte_c or "déplac" in _texte_c,
        besoin_aide_toilette        = "toilette" in _texte_c or "douche" in _texte_c,
    )

    # Urgence → Section_Urgence V3 (plus dans section_c)
    section_urgence = Section_Urgence(est_urgent=_urgence_bool)

    # ── Sections D et E — adulte_actif et mixte ──────────────────────────────
    section_d: SectionD_SituationPro | None = None
    section_e: SectionE_ProjetPro    | None = None

    if profil in ("adulte", "mixte"):
        _qual_raw = cerfa_reponses.get("qualification_parcours") or ""
        _poste, _niveau = "", ""
        if " — " in _qual_raw or " / " in _qual_raw:
            _sep    = " — " if " — " in _qual_raw else " / "
            _qp     = _qual_raw.split(_sep, 1)
            _niveau = _qp[0].strip()
            _poste  = _qp[1].strip()
        else:
            _niveau = _qual_raw.strip()

        section_d = SectionD_SituationPro(
            poste_occupe         = _poste or None,
            niveau_qualification = _niveau or None,
        )

        _droits_raw   = (cerfa_reponses.get("type_droits") or "").upper()
        _projet_raw   = (cerfa_reponses.get("qualification_parcours") or "").upper()
        _texte_e      = _droits_raw + " " + _projet_raw
        _TOKENS_ESRP  = ("CRP", "CPO", "UEROS", "ESRP", "VISA PRO", "RICHEBOIS",
                         "REEDUCATION", "READAPTATION")
        _TOKENS_ESAT  = ("ESAT", "MILIEU PROTEGE", "MILIEU PROTÉGÉ")
        _ea_raw  = (cerfa_reponses.get("emploi_accompagne") or "").lower()
        _ea_bool = any(w in _ea_raw for w in ["oui", "accompagné", "accompagne", "yes"])

        _droits_list = []
        if cerfa_reponses.get("type_droits"):
            _droits_list = [d.strip() for d in cerfa_reponses["type_droits"].split(",") if d.strip()]

        section_e = SectionE_ProjetPro(
            type_droits          = _droits_list,
            emploi_accompagne    = _ea_bool,
            projet_professionnel = cerfa_reponses.get("qualification_parcours"),
            orientation_esrp     = any(t in _texte_e for t in _TOKENS_ESRP),
            orientation_esat     = any(t in _texte_e for t in _TOKENS_ESAT),
            orientation_rqth     = "RQTH" in _texte_e,
        )

    return DossierCERFA(
        profil          = profil,
        section_a       = section_a,
        section_c       = section_c,
        section_d       = section_d,
        section_e       = section_e,
        section_f       = section_f,
        section_urgence = section_urgence,
    )


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

    # Passage automatique par le moteur de règles à chaque mise à jour des données.
    # On construit un DossierCERFA structuré depuis le dict plat, puis le moteur
    # de règles calcule les cases CERFA et les réinjecte dans cerfa_reponses.
    _dossier_cerfa = cerfa_reponses_vers_dossier_cerfa(cerfa_reponses)
    cerfa_reponses["cases_cerfa"] = executer_regles_metier_mdph(_dossier_cerfa)

    # ── Cas 0 : Redirection canal sécurisé (champs médicaux) ─────────────────
    if force_medical_redirect:
        logger.info("[CONV_AGENT] Message de redirection canal sécurisé envoyé.")
        return _MESSAGE_CANAL_SECURISE

    # ── Cas 1 : Prochain GROUPE de questions disponible ───────────────────────
    # On envoie d'abord les groupes (max 5 messages) avant de tomber en mode
    # champ-par-champ pour les champs résiduels ou conditionnels isolés.
    prochain_groupe = get_next_groupe_cerfa(cerfa_reponses)
    if prochain_groupe:
        gid = f"__groupe_{prochain_groupe['id']}__"
        # Marquer le groupe comme envoyé pour éviter les doublons
        cerfa_reponses[gid] = "sent"
        # Tracker quel groupe est en attente de réponse (pour extraction ciblée)
        cerfa_reponses["__groupe_actif__"] = prochain_groupe["id"]
        logger.info(f"[CONV_AGENT] Groupe '{prochain_groupe['id']}' envoyé.")

        # Si c'est la première prise de contact (groupe type_demande) :
        # on envoie la question pré-rédigée directement, sans LLM.
        if prochain_groupe["id"] == "type_demande" and not any(
            v for k, v in cerfa_reponses.items() if not k.startswith("__")
        ):
            return prochain_groupe["question_falc"]

        # Pour les groupes suivants : l'IA accuse réception puis pose le groupe
        answered_lines = [
            f"  ✓ {CERFA_FIELD_LABELS.get(f, f)} : {v}"
            for f, v in cerfa_reponses.items()
            if v and not f.startswith("__") and str(v) not in ("__via_email__", "sent")
        ]
        answered_ctx = "\n".join(answered_lines) if answered_lines else "  (aucun champ encore renseigné)"
        sujet = "de l'enfant" if is_enfant else "de la personne"

        # Détection automatique du profil MDPH
        profil        = _detecter_profil(cerfa_reponses)
        profil_note   = _contexte_profil(profil)

        _msg_lower = message_entrant.lower()
        _is_urgence = any(p in _msg_lower for p in ["urgent", "en urgence", "rapidement", "vite"])
        urgence_note = (
            "\n⚠️ LA PERSONNE SIGNALE UNE URGENCE. Accuse réception en 1 phrase, rassure-la.\n"
            if _is_urgence else ""
        )

        system_groupe = (
            f"{_PROMPT_MAITRE_WHATSAPP}\n"
            f"====== CONTEXTE DE CET ÉCHANGE ======\n"
            f"Tu es Mathilde, assistante de l'équipe Facilim, spécialisée MDPH. "
            f"Tu discutes via WhatsApp {sujet}.\n"
            f"Commence TOUJOURS ton message par 'Merci pour vos réponses 😊' ou une formule similaire chaleureuse.\n"
            f"Rappelle brièvement qui tu es si c'est le premier échange.\n"
            f"{urgence_note}\n"
            f"{profil_note}\n"
            f"DONNÉES DÉJÀ COLLECTÉES (7 sources vérifiées — ne pas re-demander) :\n{answered_ctx}\n\n"
            f"GROUPE EN COURS : {prochain_groupe['id']}\n"
            f"RÈGLES D'EXÉCUTION :\n"
            f"- Applique la Règle 0 : vérifie les 7 sources avant chaque question\n"
            f"- Si une info du groupe est déjà connue, note-la ('J'ai noté que…') sans la re-demander\n"
            f"- Pour difficultes_quotidiennes et besoins_aide : cherche le niveau 4-5 de preuve (Règle 2)\n"
            f"- Applique la chaîne de transformation (Règle 1) pour chaque réponse reçue\n"
            f"- Accuse réception en 1 phrase courte et chaleureuse\n"
            f"- Puis pose les questions manquantes ci-dessous (uniquement celles non déjà connues)\n"
            f"- N'invente jamais d'information\n\n"
            f"QUESTIONS DU GROUPE (poser uniquement celles dont la réponse est absente) :\n"
            f"{prochain_groupe['question_falc']}"
        )

        messages = [{"role": "system", "content": system_groupe}]
        for msg in historique[-6:]:
            role    = msg.get("role", "user")
            content = msg.get("content") or msg.get("reponse") or ""
            if content and role in ("user", "assistant"):
                messages.append({"role": role, "content": str(content)})
        messages.append({"role": "user", "content": message_entrant})

        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=400,
                temperature=0.4,
            )
            reponse = response.choices[0].message.content.strip()
            logger.info(f"[CONV_AGENT] Groupe={prochain_groupe['id']} | {len(reponse)} chars")
            return reponse
        except Exception as e:
            logger.error(f"[CONV_AGENT] Erreur LLM groupe : {e}")
            return prochain_groupe["question_falc"]

    # ── Cas 2 : Plus de groupe → champ résiduel isolé (conditionnel tardif) ───
    next_field = get_next_cerfa_field(cerfa_reponses)

    if next_field == _MEDICAL_REDIRECT_SENT_KEY:
        logger.info("[CONV_AGENT] Sentinel médical → redirection canal sécurisé.")
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

    answered_lines = [
        f"  ✓ {CERFA_FIELD_LABELS.get(f, f)} : {v}"
        for f, v in cerfa_reponses.items()
        if v and not f.startswith("__") and str(v) not in ("__via_email__", "sent")
    ]
    answered_ctx = "\n".join(answered_lines) if answered_lines else "  (aucun champ encore renseigné)"
    sujet = "de l'enfant" if is_enfant else "de la personne"

    # Détection automatique du profil MDPH
    profil      = _detecter_profil(cerfa_reponses)
    profil_note = _contexte_profil(profil)

    _msg_lower = message_entrant.lower()
    _deja_patterns = [
        "déjà répondu", "deja repondu", "j'ai déjà", "j'ai deja",
        "dans le bilan", "dans le dossier", "c'est noté", "c'est transmis",
        "déjà transmis", "déjà indiqué", "vous l'avez",
    ]
    _is_deja_bilan = any(p in _msg_lower for p in _deja_patterns)
    _is_urgence    = any(p in _msg_lower for p in ["urgent", "en urgence", "rapidement", "vite"])

    urgence_note = (
        "\n⚠️ LA PERSONNE SIGNALE UNE URGENCE. Accuse réception en 1 phrase, rassure-la.\n"
        if _is_urgence else ""
    )
    deja_note = (
        "\n⚠️ LA PERSONNE DIT QUE L'INFO EST DÉJÀ DANS LE DOSSIER. "
        "NE PAS reposer la question. Répondre 'Bien reçu.' puis poser la suivante.\n"
        if _is_deja_bilan else ""
    )

    system = (
        f"{_PROMPT_MAITRE_WHATSAPP}\n"
        f"====== CONTEXTE DE CET ÉCHANGE ======\n"
        f"Tu es Mathilde, assistante de l'équipe Facilim, spécialisée MDPH. "
        f"Tu discutes via WhatsApp {sujet}.\n"
        f"Langue : français simple, bienveillant, FALC.\n"
        f"{urgence_note}{deja_note}\n"
        f"{profil_note}\n"
        f"DONNÉES DÉJÀ COLLECTÉES (7 sources vérifiées — ne pas re-demander) :\n{answered_ctx}\n\n"
        f"CHAMP À COLLECTER : {next_label}\n\n"
        f"RÈGLES D'EXÉCUTION :\n"
        f"- Applique la Règle 0 : vérifie si ce champ est déjà connu dans les données ci-dessus\n"
        f"- Si l'information existe : la signaler ('J'ai noté que…') sans reposer la question\n"
        f"- Pour difficultes_quotidiennes / besoins_aide : relancer si niveau ≤ 2 (Règle 2)\n"
        f"- Applique la chaîne de transformation (Règle 1) pour formuler la question avec pertinence\n"
        f"- Ne demande PAS d'autres informations que ce champ\n"
        f"- Ne répète jamais une question déjà répondue\n"
        f"- N'invente jamais d'information\n"
        f"- Réponse max : 2 phrases + 1 question"
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
        logger.info(f"[CONV_AGENT] Champ résiduel={next_field} | {len(reponse)} chars")
        return reponse
    except Exception as e:
        logger.error(f"[CONV_AGENT] Erreur LLM champ résiduel : {e}")
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
