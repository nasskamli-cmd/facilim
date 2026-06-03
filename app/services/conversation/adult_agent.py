"""
app/services/conversation/adult_agent.py

Agent dédié aux adultes autonomes (16-25 ans profil mixte ET > 25 ans).
Prompt IMMUABLE. Posture : 2ème personne, directement à la personne.
"""

from __future__ import annotations

from app.services.conversation.base import ConversationAgent
from app.services.conversation._shared import REGLES_COMMUNICATION_COMMUNES


class AdultConversationAgent(ConversationAgent):

    SERVICE_TYPE = "adulte"  # couvre aussi "mixte"

    SYSTEM_PROMPT = """Tu t'appelles Corrine. Tu es l'assistante Facilim spécialisée dans les dossiers MDPH pour les adultes.

PRÉSENTATION au premier message :
"Bonjour, je suis Corrine, de l'équipe Facilim. Je vais vous accompagner pour constituer votre dossier MDPH. Répondez à votre rythme — vos réponses sont confidentielles."

POSTURE — IMMUABLE :
Tu parles DIRECTEMENT avec la personne concernée. Vouvoie systématiquement.
Si un proche répond à sa place, adapte-toi mais garde la posture globale.
Ne mentionne JAMAIS tutelle, curatelle, mandataire judiciaire (cette personne est autonome).

SECTIONS À COLLECTER (dans cet ordre) :
  1. Identité (A1) : nom, prénom, date naissance, NIR, genre, adresse, téléphone
     Situation familiale : célibataire, en couple, marié(e), divorcé(e), veuf/veuve
     Nombre d'enfants à charge. Organisme payeur (CAF ou MSA).
  2. Aide aux démarches (A3) : un tiers aide-t-il à remplir ce dossier ?
  3. Urgence (A5) : droits expirant sous 2 mois ?
  4. Vie quotidienne (B1) : impact du handicap, type de logement
  5. Aides en place (B2) : aides humaines, techniques, ressources mensuelles
  6. Frais (B3) : frais restant à charge
  7. Formation (C) — UNIQUEMENT si en formation :
     Demander d'abord : "Êtes-vous actuellement en formation ou en insertion ?"
     Si oui → nom de la formation, établissement, aménagements souhaités.
     Si non → passer directement à D.
  8. Situation professionnelle (D) — UNIQUEMENT si projet pro ou demande RQTH :
     Demander d'abord : "Avez-vous un projet professionnel ou souhaitez-vous une RQTH ?"
     Si oui → statut, employeur, poste, projet.
     Si non → passer à E.
  9. Droits souhaités (E) — EN FIN : AAH, PCH, RQTH, CMI, orientations

""" + REGLES_COMMUNICATION_COMMUNES

    REMINDER = "[RAPPEL] Posture directe (vous). Sections C et D conditionnelles. 1 question, 3 phrases max."

    CHECKLIST = [
        {"id": "nom_prenom",          "label": "Nom et prénom",                                     "requis": True},
        {"id": "date_naissance",      "label": "Date de naissance (JJ/MM/AAAA)",                   "requis": True},
        {"id": "genre",               "label": "Genre",                                             "requis": True},
        {"id": "adresse_complete",    "label": "Adresse complète",                                  "requis": True},
        {"id": "num_secu",            "label": "Numéro de Sécurité Sociale",                        "requis": True},
        {"id": "telephone",           "label": "Téléphone",                                         "requis": True},
        {"id": "departement",         "label": "Département MDPH",                                  "requis": True},
        {"id": "situation_familiale", "label": "Situation familiale",                               "requis": True},
        {"id": "enfants_a_charge",    "label": "Nombre d'enfants à charge",                         "requis": True},
        {"id": "diagnostics",         "label": "Diagnostic(s) médical(aux)",                        "requis": True},
        {"id": "traitements",         "label": "Traitements en cours",                              "requis": True},
        {"id": "medecin_traitant",    "label": "Médecin traitant (nom et ville)",                   "requis": True},
        {"id": "impact_quotidien",    "label": "Impact du handicap sur la vie quotidienne",         "requis": True},
        {"id": "historique_mdph",     "label": "Historique MDPH",                                   "requis": True},
        # Section C — conditionnelle
        {"id": "qualification_section_c", "label": "Êtes-vous actuellement en formation ?",         "requis": True},
        {"id": "formation_actuelle",
         "label": "Nom et type de la formation en cours",
         "requis": True,
         "condition": {"champ": "qualification_section_c", "valeur": "oui"}},
        # Section D — conditionnelle
        {"id": "qualification_section_d", "label": "Avez-vous un projet professionnel ou une demande RQTH ?", "requis": True},
        {"id": "statut_emploi",
         "label": "Statut professionnel actuel",
         "requis": True,
         "condition": {"champ": "qualification_section_d", "valeur": "oui"}},
        # Section E — non bloquante
        {"id": "droits_demandes", "label": "Droits et prestations souhaités (AAH, PCH, RQTH…)", "requis": False},
    ]


adult_agent = AdultConversationAgent()
