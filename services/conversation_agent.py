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
# ---------------------------------------------------------------------------
CERFA_FIELD_ORDER: list[str] = [
    # ── Section A — Identité ────────────────────────────────────────────────
    "type_demande",               # ✓ première demande ou renouvellement
    "nom_prenom",                 # ✓ nom et prénom du bénéficiaire
    "date_naissance",             # ✓ JJ/MM/AAAA
    "genre",                      # ✓ homme / femme
    "adresse_complete",           # ✓ numéro, rue, CP, ville
    "situation_familiale",        # ✓ célibataire, marié·e, en couple…
    "enfants_a_charge",           # ✓ nombre (0 si aucun)
    # ── Section B — Vie quotidienne & retentissements fonctionnels ──────────
    "difficultes_quotidiennes",   # ✓ ce que la personne ne peut pas faire seule
    "besoins_aide",               # ✓ type d'aide humaine/technique nécessaire
    # ── Section C/D — Parcours scolaire / professionnel ────────────────────
    "situation_pro_scolaire",     # ✓ emploi, scolarité, sans activité…
    # ── Section E — Demandes ───────────────────────────────────────────────
    "type_droits",                # ✓ AAH, RQTH, PCH, AEEH, CMI, IME/ESAT…
    "historique_mdph",            # ✓ seulement si renouvellement
    # ── Données médicales — collectées HORS WhatsApp par l'éducateur [MED] ─
    "numero_securite_sociale",    # [MED] NIR
    "diagnostic_principal",       # [MED] pathologie certifiée
    "medecin_traitant",           # [MED] coordonnées médecin
    "traitements_en_cours",       # [MED] médicaments et thérapies
    "taux_incapacite",            # [MED] taux MDPH si renouvellement
]

CERFA_FIELD_LABELS: dict[str, str] = {
    # Identité
    "type_demande":               "s'il s'agit d'une première demande MDPH ou d'un renouvellement",
    "nom_prenom":                 "le nom et prénom complet du bénéficiaire",
    "date_naissance":             "la date de naissance du bénéficiaire (format JJ/MM/AAAA)",
    "genre":                      "le genre du bénéficiaire (homme ou femme)",
    "adresse_complete":           "l'adresse complète (numéro, rue, code postal, ville)",
    "situation_familiale":        "la situation familiale (célibataire, marié·e, en couple, divorcé·e…)",
    "enfants_a_charge":           "le nombre d'enfants à charge (indiquez 0 si aucun)",
    # Fonctionnel — cœur du CERFA
    "difficultes_quotidiennes":   "les principales difficultés dans la vie de tous les jours (ce que la personne ne peut pas faire seule, ce qui lui est difficile ou épuisant)",
    "besoins_aide":               "les aides dont la personne a besoin (aide humaine, aide technique, aménagement du logement, accompagnement…)",
    # Parcours
    "situation_pro_scolaire":     "la situation professionnelle ou scolaire actuelle (emploi, scolarité, formation, recherche d'emploi, inactivité…)",
    # Demandes
    "type_droits":                "le ou les types de droits demandés à la MDPH (AAH, RQTH, PCH, AEEH, CMI, orientation IME/ESAT/SESSAD…)",
    "historique_mdph":            "la date de la dernière notification MDPH (uniquement si renouvellement)",
    # Médical — hors WhatsApp
    "numero_securite_sociale":    "le numéro de sécurité sociale (15 chiffres)",
    "diagnostic_principal":       "le diagnostic médical précis (pathologie, depuis quand, confirmé par quel médecin)",
    "medecin_traitant":           "le nom et la ville du médecin traitant",
    "traitements_en_cours":       "les traitements médicaux en cours (médicaments, thérapies, fréquence)",
    "taux_incapacite":            "le taux d'incapacité reconnu par la MDPH (indiqué sur la dernière notification)",
}

_TAUX_FIELD    = "taux_incapacite"
_HISTORIQUE    = "historique_mdph"
_TYPE_DEMANDE  = "type_demande"
_DIFFICULTES   = "difficultes_quotidiennes"
_BESOINS       = "besoins_aide"


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

    # Pré-remplissage fonctionnel depuis la synthèse GEVA
    # Si l'analyse a produit une synthèse GEVA-Pro, on la réutilise
    # pour éviter de reposer la question sur les difficultés quotidiennes.
    syntheses = analyse.get("synthese_agents") or {}
    geva_pro  = str(syntheses.get("geva_pro") or "").strip()
    if geva_pro and len(geva_pro) > 40:
        _set("difficultes_quotidiennes", geva_pro[:500])

    # Besoins d'aide — depuis les données structurées
    aides = ds.get("aides_actuelles") or []
    if isinstance(aides, list) and aides:
        _set("besoins_aide", " / ".join(str(a) for a in aides[:5]))
    elif ds.get("besoins_aide_humaine"):
        _set("besoins_aide", "Aide humaine nécessaire")


# ---------------------------------------------------------------------------
# Logique de progression CERFA
# ---------------------------------------------------------------------------

def get_next_cerfa_field(cerfa_reponses: dict[str, str]) -> str | None:
    """
    Retourne le prochain champ CERFA à collecter via WhatsApp.

    - Les champs médicaux (MEDICAL_FIELDS) sont toujours sautés :
      ils doivent être transmis par canal sécurisé (email / messagerie éducateur).
    - Si des champs médicaux sont encore vides ET que le message de redirection
      n'a pas encore été envoyé, retourne le sentinel _MEDICAL_REDIRECT_SENT_KEY
      pour que l'appelant déclenche ce message unique.
    - taux_incapacite est également sauté si c'est clairement une première demande.
    - Retourne None si tous les champs non-médicaux sont renseignés.
    """
    medical_pending = False

    for field in CERFA_FIELD_ORDER:
        # Champ déjà renseigné → suivant
        if field in cerfa_reponses and cerfa_reponses[field]:
            continue

        # Champ médical → jamais collecté via WhatsApp
        if field in MEDICAL_FIELDS:
            medical_pending = True
            continue

        # Règle spéciale historique_mdph : inutile pour une première demande
        # (la date de la dernière notification n'existe pas encore)
        if field == _HISTORIQUE:
            type_d   = cerfa_reponses.get(_TYPE_DEMANDE, "").lower()
            is_first = any(
                w in type_d
                for w in ["première", "premier", "premiere", "jamais", "nouveau", "1ere", "1ère"]
            )
            if is_first:
                continue  # Ne pas demander l'historique MDPH pour une première demande

        # Règle spéciale taux_incapacite (en plus du filtre MEDICAL_FIELDS)
        if field == _TAUX_FIELD:
            type_d   = cerfa_reponses.get(_TYPE_DEMANDE, "").lower()
            hist     = cerfa_reponses.get(_HISTORIQUE, "").lower()
            combined = type_d + " " + hist
            is_renewal = any(
                w in combined
                for w in ["renouvellement", "renouvel", "taux reconnu", "notification", "déjà accordé"]
            )
            is_first = any(
                w in combined
                for w in ["première", "premier", "jamais", "première fois", "nouveau"]
            )
            if is_first and not is_renewal:
                continue

        return field  # prochain champ non-médical à collecter

    # Tous les champs non-médicaux sont renseignés.
    # Si des champs médicaux sont encore vides et que le message n'a pas été envoyé :
    if medical_pending and not cerfa_reponses.get(_MEDICAL_REDIRECT_SENT_KEY):
        return _MEDICAL_REDIRECT_SENT_KEY  # sentinel → déclenche le message de redirection

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

    # ── Redirection canal sécurisé (champs médicaux) ─────────────────────────
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

    # Contexte : champs déjà renseignés
    answered_lines = [
        f"  ✓ {CERFA_FIELD_LABELS.get(f, f)} : {v}"
        for f, v in cerfa_reponses.items()
        if v
    ]
    answered_ctx = (
        "\n".join(answered_lines)
        if answered_lines
        else "  (aucun champ encore renseigné)"
    )

    sujet = "de l'enfant" if is_enfant else "de la personne"

    system = (
        f"Tu es l'Assistant Facilim, spécialisé dans la constitution de dossiers MDPH.\n"
        f"Tu discutes via WhatsApp pour constituer le dossier MDPH {sujet}.\n"
        f"Langue : français simple, bienveillant, FALC (phrases courtes, mots courants).\n\n"
        f"RÔLE DU CERFA : Le formulaire MDPH porte sur les conséquences concrètes du\n"
        f"handicap dans la vie quotidienne — pas sur les données médicales.\n"
        f"NE JAMAIS demander : diagnostic, médicaments, nom du médecin, taux d'incapacité.\n\n"
        f"CHAMPS DÉJÀ COLLECTÉS :\n{answered_ctx}\n\n"
        f"PROCHAIN CHAMP À COLLECTER : {next_label}\n\n"
        f"RÈGLES ABSOLUES :\n"
        f"- Accuse d'abord réception en 1 phrase courte et chaleureuse\n"
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
