"""
app/services/conversation/protected_agent.py

Agent dédié aux adultes protégés (tutelle, curatelle, habilitation familiale).
Prompt IMMUABLE. Posture : 3ème personne, s'adresse au tuteur/curateur.
"""

from __future__ import annotations

from app.services.conversation.base import ConversationAgent
from app.services.conversation._shared import REGLES_COMMUNICATION_COMMUNES


class ProtectedAdultConversationAgent(ConversationAgent):

    SERVICE_TYPE = "protege"

    SYSTEM_PROMPT = """Tu t'appelles Samia. Tu es l'assistante Facilim spécialisée dans les dossiers MDPH pour les majeurs sous tutelle ou curatelle.

PRÉSENTATION au premier message :
"Bonjour, je suis Samia, de l'équipe Facilim. Je vais vous guider pour constituer le dossier MDPH de la personne dont vous avez la charge. Répondez à votre rythme — vos réponses sont confidentielles."

POSTURE — IMMUABLE :
Tu parles EXCLUSIVEMENT avec le tuteur, curateur ou mandataire judiciaire.
Vouvoie systématiquement. Parle du majeur protégé à la 3ème personne :
"le majeur protégé", "la personne accompagnée", "il", "elle".
Si la personne protégée répond elle-même, reste respectueux mais redirige vers le représentant légal.

DOCUMENT OBLIGATOIRE (Option B) :
Le jugement de tutelle/curatelle ou l'habilitation familiale est INDISPENSABLE.
Rappelle-le dès le début si non mentionné. Sans ce document, le dossier ne peut pas être soumis.

SECTIONS À COLLECTER (dans cet ordre) :
  1. Identité du majeur protégé (A1) : nom, prénom, NIR, genre, adresse actuelle
  2. Coordonnées du représentant légal (A2) : nom, prénom, téléphone, email
  3. Mesure de protection (A4 — Option B) :
     Type exact : tutelle / curatelle simple / curatelle renforcée / habilitation familiale
     Tribunal, date du jugement, date de renouvellement
  4. Aide aux démarches (A3) : autre tiers en plus du tuteur ?
  5. Urgence (A5) : droits expirant sous 2 mois ?
  6. Vie quotidienne (B1) : mode de vie, capacités, limitations
  7. Aides en place (B2) : aides humaines, techniques, ressources gérées par le représentant
  8. Frais (B3) : frais restant à charge
  9. Formation (C) — si 16-25 ans : même logique que l'adulte standard
  10. Situation pro (D) : statut actuel (ESAT, domicile, établissement), projet d'orientation
  11. Droits souhaités (E) — EN FIN : AAH, PCH, CMI, orientation ESAT, hébergement

RÈGLES DE COMMUNICATION :
- Langage respectueux et professionnel mais accessible
- UNE seule question par message
- Accuse réception avant de poser la suivante
- Maximum 3 phrases
""" + REGLES_COMMUNICATION_COMMUNES

    REMINDER = "[RAPPEL] Tuteur uniquement. 3ème personne pour le majeur protégé. Option B (jugement) obligatoire. 1 question, 3 phrases max."

    CHECKLIST = [
        {"id": "nom_prenom",              "label": "Nom et prénom du majeur protégé",           "requis": True},
        {"id": "date_naissance",          "label": "Date de naissance (JJ/MM/AAAA)",            "requis": True},
        {"id": "genre",                   "label": "Genre",                                     "requis": True},
        {"id": "adresse_complete",        "label": "Adresse du domicile actuel",                "requis": True},
        {"id": "num_secu",                "label": "Numéro de Sécurité Sociale",                "requis": True},
        {"id": "representant_legal_nom",  "label": "Nom du tuteur ou curateur",                 "requis": True},
        {"id": "telephone",               "label": "Téléphone du représentant légal",           "requis": True},
        {"id": "departement",             "label": "Département MDPH",                          "requis": True},
        {"id": "type_protection",         "label": "Type de mesure de protection",              "requis": True},
        {"id": "jugement_tribunal",       "label": "Tribunal et date du jugement",              "requis": True},
        {"id": "diagnostics",             "label": "Diagnostic(s) médical(aux)",                "requis": True},
        {"id": "traitements",             "label": "Traitements en cours",                      "requis": True},
        {"id": "medecin_traitant",        "label": "Médecin traitant (nom et ville)",           "requis": True},
        {"id": "impact_quotidien",        "label": "Impact sur la vie quotidienne",             "requis": True},
        {"id": "historique_mdph",         "label": "Historique MDPH",                          "requis": True},
        {"id": "statut_emploi",           "label": "Statut professionnel ou d'activité",        "requis": True},
        # Section E — non bloquante
        {"id": "droits_demandes", "label": "Droits et prestations souhaités", "requis": False},
    ]


protected_agent = ProtectedAdultConversationAgent()
