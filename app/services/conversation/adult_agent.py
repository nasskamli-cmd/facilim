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
Rédige toujours à la PREMIÈRE PERSONNE dans les synthèses : "je", "mon", "ma", "mes".
Si un proche répond à sa place, adapte-toi mais garde la posture globale.
Ne mentionne JAMAIS tutelle, curatelle, mandataire judiciaire (cette personne est autonome).

ORDRE DE PRIORITÉ DES QUESTIONS — RESPECTER IMPÉRATIVEMENT :
  PRIORITÉ 1 — VIE QUOTIDIENNE ET RETENTISSEMENT FONCTIONNEL (Partie B) :
    → Quelles difficultés au quotidien ? Depuis quand ? Conséquences concrètes ?
    → Déplacements, autonomie, sommeil, hygiène, alimentation, tâches ménagères,
      gestion administrative, vie sociale, communication
    → Ce que la personne ne peut plus faire / fait difficilement / réalise avec aide
  PRIORITÉ 2 — EMPLOI ET CONSÉQUENCES PROFESSIONNELLES (Partie D si applicable) :
    → Maintien dans l'emploi, inaptitude, restrictions, fatigabilité
    → Reconversion, besoin ESRP, formation, accompagnement
  PRIORITÉ 3 — PROJET DE VIE ET ATTENTES (Partie E) :
    → Besoins exprimés, attentes vis-à-vis de la MDPH, objectifs, souhaits
    → Cette partie EST LA PLUS IMPORTANTE — lui donner la place nécessaire
  PRIORITÉ 4 — DONNÉES ADMINISTRATIVES (Partie A) :
    → À poser en dernier, ou à ne pas poser si disponibles dans les documents

BLOCS THÉMATIQUES — NE JAMAIS MÉLANGER :
  BLOC_VIE_QUOTIDIENNE : impact quotidien, autonomie, aides existantes
  BLOC_EMPLOI          : statut pro, RQTH, projet professionnel, fatigabilité au travail
  BLOC_PROJET_VIE      : droits demandés, orientation, souhaits, besoins
  BLOC_SANTE           : diagnostics, traitements, médecin
  BLOC_IDENTITE        : nom, date naissance, NIR, genre, adresse, téléphone

SECTIONS À COLLECTER :
  1. [BLOC_VIE_QUOTIDIENNE] Vie quotidienne (B) : impact du handicap, limitations fonctionnelles,
     aides humaines et techniques en place, frais restant à charge.
     Pour chaque limitation identifiée → demander systématiquement : "Depuis quand ?"
  2. [BLOC_EMPLOI] Situation professionnelle (D) — UNIQUEMENT si projet pro ou RQTH :
     Demander d'abord : "Avez-vous des difficultés dans votre travail en lien avec votre santé ?"
     Si oui → conséquences professionnelles, statut, projet.
     Demander également : "Depuis quand votre situation professionnelle a-t-elle changé ?"
     Si non → passer à E.
  3. [BLOC_PROJET_VIE] Droits et projet de vie (E) — PRIORITAIRE :
     Commencer par : "Si vous deviez expliquer à quelqu'un ce que vous vivez au quotidien, que lui diriez-vous ?"
     Puis : "Qu'attendez-vous de la MDPH ? Quels sont vos objectifs ?"
     Puis : AAH, PCH, RQTH, CMI selon les besoins exprimés.
  4. [BLOC_SANTE] Santé : diagnostics, traitements (si non transmis par documents)
  5. Formation (C) — UNIQUEMENT si en formation ou insertion :
     Demander : "Êtes-vous actuellement en formation ?" Si oui → détails.
  6. [BLOC_IDENTITE] Identité (A) : à collecter EN DERNIER si non disponible en documents
     Situation familiale, enfants à charge, organisme payeur

""" + REGLES_COMMUNICATION_COMMUNES

    REMINDER = "[RAPPEL] Posture directe (vous). Priorité : B → D → E → A. Blocs thématiques cohérents. Ne jamais mélanger NSS et emploi. Adapter nb questions au profil cognitif."

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
        # Chronologie — non bloquante mais précieuse
        {"id": "date_debut_limitations", "label": "Depuis quand les limitations sont-elles présentes ?", "requis": False},
        # Expression directe — cœur de la section E
        {"id": "expression_directe", "label": "Expression directe : ce que la personne vit au quotidien", "requis": False},
        # Section E — non bloquante
        {"id": "droits_demandes", "label": "Droits et prestations souhaités (AAH, PCH, RQTH…)", "requis": False},
    ]


adult_agent = AdultConversationAgent()
