"""
app/services/conversation/child_agent.py

Agent dédié aux dossiers ENFANT (< 16 ans).
Prompt IMMUABLE. Aucune question adulte n'est possible structurellement.
"""

from __future__ import annotations

from app.services.conversation.base import ConversationAgent
from app.services.conversation._shared import REGLES_COMMUNICATION_COMMUNES


class ChildConversationAgent(ConversationAgent):

    SERVICE_TYPE = "enfant"

    SYSTEM_PROMPT = """Tu t'appelles Claire. Tu es l'assistante Facilim spécialisée dans les dossiers MDPH pour les enfants.

POSTURE — IMMUABLE :
Tu parles UNIQUEMENT avec le représentant légal (père, mère, tuteur judiciaire).
L'enfant n'est JAMAIS ton destinataire. Vouvoie systématiquement.
Parle de l'enfant à la 3ème personne : "votre enfant", "il", "elle", "votre fils", "votre fille".
Hypothèse par défaut : l'enfant vit chez ses parents (ne demande pas le logement sauf si établissement mentionné).

PRÉSENTATION au premier message :
"Bonjour, je suis Claire, de l'équipe Facilim. Je vais vous aider à constituer le dossier MDPH de votre enfant. Répondez à votre rythme — vos informations sont confidentielles et servent uniquement à cette demande."

MOTS BANNIS — NE JAMAIS PRONONCER NI SUGGÉRER :
  ✗ mariage, conjoint, concubinage, PACS
  ✗ emploi, contrat de travail, employeur, chômage
  ✗ RSA, prime d'activité, revenu professionnel, salaire
  ✗ AAH (non applicable avant 20 ans)
  ✗ vie active, insertion professionnelle, bilan de compétences, RQTH
  ✗ enfants à charge de l'usager
  ✗ situation maritale ou familiale de l'enfant

SECTIONS À COLLECTER (dans cet ordre) :
  1. Identité de l'enfant : prénom, nom, NIR, genre, adresse
  2. Représentant légal : nom, prénom, lien, téléphone, email
  3. Aide aux démarches (A3) : un tiers aide-t-il à remplir ce dossier ?
  4. Urgence (A5) : droits expirant sous 2 mois ?
  5. Vie quotidienne (B1) : difficultés habillage, repas, hygiène, déplacements
  6. Aides en place (B2) : aides humaines et techniques déjà utilisées
  7. Frais (B3) : matériel adapté, soins privés, transport spécialisé
  8. Scolarité (C) : établissement, type (ordinaire/ULIS/IME/SESSAD), PPS, AESH, GEVAsco
  9. Droits souhaités (E) — EN FIN : AEEH, PCH enfant, CMI, orientation

""" + REGLES_COMMUNICATION_COMMUNES

    REMINDER = "[RAPPEL ABSOLU] Représentant légal uniquement. 3ème personne pour l'enfant. INTERDITS : mariage, emploi, RSA, AAH. 1 question, 3 phrases max."

    CHECKLIST = [
        {"id": "nom_prenom",              "label": "Nom et prénom de l'enfant",             "requis": True},
        {"id": "date_naissance",          "label": "Date de naissance (JJ/MM/AAAA)",        "requis": True},
        {"id": "genre",                   "label": "Genre",                                 "requis": True},
        {"id": "adresse_complete",        "label": "Adresse du domicile familial",           "requis": True},
        {"id": "num_secu",                "label": "Numéro de Sécurité Sociale",             "requis": True},
        {"id": "telephone",               "label": "Téléphone du représentant légal",        "requis": True},
        {"id": "departement",             "label": "Département MDPH",                      "requis": True},
        {"id": "representant_legal_nom",  "label": "Nom du représentant légal",              "requis": True},
        {"id": "representant_legal_lien", "label": "Lien avec l'enfant",                    "requis": True},
        {"id": "diagnostics",             "label": "Diagnostic(s) médical(aux)",             "requis": True},
        {"id": "traitements",             "label": "Traitements en cours",                  "requis": True},
        {"id": "medecin_traitant",        "label": "Médecin traitant (nom et ville)",        "requis": True},
        {"id": "impact_quotidien",        "label": "Impact sur la vie quotidienne",          "requis": True},
        {"id": "historique_mdph",         "label": "Historique MDPH",                       "requis": True},
        {"id": "situation_scolaire",      "label": "Situation scolaire de l'enfant",         "requis": True},
        {"id": "etablissement_scolaire",  "label": "Nom de l'établissement scolaire",        "requis": True},
        # Section E — non bloquante, proposée en fin
        {"id": "droits_demandes",         "label": "Droits et prestations souhaités",        "requis": False},
    ]


child_agent = ChildConversationAgent()
