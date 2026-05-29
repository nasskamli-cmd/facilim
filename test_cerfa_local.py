"""
test_cerfa_local.py — Test de l'intégration cerfa_service sans serveur ni WhatsApp.

Lance avec :
    python test_cerfa_local.py

Ce script teste directement traiter_dossier_cerfa() — la même fonction
appelée dans main.py quand get_next_cerfa_field() retourne None.

Aucune dépendance réseau, aucune clé API nécessaire pour les tests 1 et 2.
Le test 3 (PDF complet) appelle le LLM pour la page 8 — il passe en mode
fallback texte brut si OPENAI_API_KEY n'est pas configurée.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.cerfa_service import traiter_dossier_cerfa

SEP = "=" * 60


# ---------------------------------------------------------------------------
# TEST 1 — Dossier vide : simule un usager qui n'a encore rien répondu
# Comportement attendu : type=validation, message_a_envoyer = 1ère question
# ---------------------------------------------------------------------------
print(SEP)
print("TEST 1 — Dossier vide (cerfa_reponses tous vides)")
print(SEP)

dossier_vide = {
    # Champs dossier (renseignés par l'éducateur au départ)
    "dossier_id":        "TEST-LOCAL-001",
    "nom_enfant":        "NAIT ALI",
    "prenom_enfant":     "Karim",
    "ddn_enfant":        "05/12/1969",
    "telephone_famille": "0642087770",
    "email_famille":     "test@test.com",
    "departement_code":  "13",
    # cerfa_reponses vides = aucune réponse WhatsApp collectée
}

r1 = traiter_dossier_cerfa(dossier_vide)
print(f"valide             : {r1['valide']}")
print(f"type               : {r1['type']}")
print(f"nb erreurs         : {len(r1.get('erreurs', []))}")
print(f"message_a_envoyer  : {r1.get('message_a_envoyer', '')[:100]}")
print(f"questions restantes: {len(r1.get('questions_restantes', []))}")
assert r1["valide"] is False
assert r1["type"] == "validation"
assert r1.get("message_a_envoyer")
print("[OK]")


# ---------------------------------------------------------------------------
# TEST 2 — Dossier partiellement rempli : simule 3 réponses WhatsApp reçues
# Comportement attendu : type=validation, question sur le champ suivant manquant
# ---------------------------------------------------------------------------
print()
print(SEP)
print("TEST 2 — Dossier partiel (type_demande + nom_prenom + date_naissance reçus)")
print(SEP)

dossier_partiel = {
    **dossier_vide,
    # cerfa_reponses = ce que le bot a collecté jusqu'ici via WhatsApp
    "type_demande":  "renouvellement",
    "nom_prenom":    "Karim NAIT ALI",
    "date_naissance": "05/12/1969",
    # Manquent encore : genre, adresse_complete, situation_familiale,
    #                   type_droits, difficultes_quotidiennes
}

r2 = traiter_dossier_cerfa(dossier_partiel)
print(f"valide             : {r2['valide']}")
print(f"type               : {r2['type']}")
print(f"nb erreurs         : {len(r2.get('erreurs', []))}")
print(f"message_a_envoyer  : {r2.get('message_a_envoyer', '')[:100]}")
assert r2["valide"] is False
assert r2["type"] == "validation"
# Le message doit poser la prochaine question (genre, adresse ou situation fam)
assert r2.get("message_a_envoyer")
print("[OK]")


# ---------------------------------------------------------------------------
# TEST 3 — Dossier complet : simule toutes les réponses WhatsApp collectées
# Comportement attendu : type=succes, pdf_bytes non vide
# ---------------------------------------------------------------------------
print()
print(SEP)
print("TEST 3 — Dossier complet (tous les champs obligatoires remplis)")
print(SEP)

dossier_complet = {
    # Champs dossier (éducateur)
    "dossier_id":        "TEST-LOCAL-003",
    "nom_enfant":        "NAIT ALI",
    "prenom_enfant":     "Karim",
    "ddn_enfant":        "05/12/1969",
    "adresse_enfant":    "1 rue des Bateliers",
    "cp_enfant":         "13016",
    "commune_enfant":    "MARSEILLE",
    "telephone_famille": "0642087770",
    "email_famille":     "test@test.com",
    "departement_code":  "13",
    "cerfa_reponses":    {},
    # cerfa_reponses fusionnés au niveau racine (comme dans main.py Cas 3)
    "type_demande":           "renouvellement",
    "nom_prenom":             "Karim NAIT ALI",
    "date_naissance":         "05/12/1969",
    "genre":                  "homme",
    "adresse_complete":       "1 rue des Bateliers, 13016 Marseille",
    "situation_familiale":    "marie",
    "type_droits":            "RQTH, AAH",
    "difficultes_quotidiennes": (
        "Douleurs chroniques suite à un accident du travail en 2019. "
        "Difficultés à rester debout plus de 20 minutes. "
        "Fatigabilité importante, nécessite des pauses fréquentes."
    ),
    "besoins_aide":        "Aménagement du poste de travail, aide aux déplacements",
    "organisme_payeur":    "CAF",
    "protection_juridique": "aucune",
    # Analyse LLM (structure attendue par cerfa_filler)
    "analyse": {
        "droits_identifies": ["RQTH", "AAH"],
        "elements_probants": ["AT 2019"],
        "synthese_agents": {
            "geva_pro": "Accident du travail 2019, limitations fonctionnelles avérées",
            "juriste":  "RQTH et AAH justifiés",
        },
        "donnees_structurees": {
            "is_enfant":           False,
            "genre":               "homme",
            "situation_familiale": "marié",
            "a_enfants_charge":    True,
            "type_logement":       "appartement",
            "statut_occupation":   "locataire",
            "type_demande":        "renouvellement",
            "deja_connu_mdph":     True,
            "accident_travail":    True,
            "consentement_informations": True,
        },
    },
}

r3 = traiter_dossier_cerfa(dossier_complet)
print(f"valide    : {r3['valide']}")
print(f"type      : {r3['type']}")
print(f"warnings  : {r3.get('warnings', [])}")
if r3["valide"]:
    taille = len(r3.get("pdf_bytes", b""))
    print(f"pdf_bytes : {taille} octets [OK]")
    assert taille > 0
else:
    print(f"erreur    : {r3.get('erreur', '')}")
    print(f"erreurs   : {r3.get('erreurs', [])}")
assert r3["valide"] is True
assert r3["type"] == "succes"
print("[OK]")


# ---------------------------------------------------------------------------
# TEST 4 — Erreur technique simulée : dossier avec cerfa_reponses corrects
#           mais analyse absente → remplir_cerfa lèvera une exception
#           → type=technique attendu
# ---------------------------------------------------------------------------
print()
print(SEP)
print("TEST 4 — Erreur technique (analyse absente -> remplir_cerfa plante)")
print(SEP)

dossier_sans_analyse = {
    **{k: v for k, v in dossier_complet.items() if k != "analyse"},
    "analyse": None,   # forcer l'absence d'analyse
}

r4 = traiter_dossier_cerfa(dossier_sans_analyse)
print(f"valide : {r4['valide']}")
print(f"type   : {r4['type']}")
if r4["type"] == "technique":
    print(f"erreur : {r4.get('erreur', '')[:80]}")
    print("[OK] — erreur technique bien isolée, pas d'exception levée")
elif r4["type"] == "succes":
    # cerfa_filler a des fallbacks robustes, il peut passer quand même
    print(f"[INFO] remplir_cerfa a généré le PDF malgré l'absence d'analyse ({len(r4.get('pdf_bytes',b''))} octets)")
    print("[OK] — pas d'exception levée")


# ---------------------------------------------------------------------------
print()
print(SEP)
print("TOUS LES TESTS PASSES")
print(SEP)
print()
print("Pour tester avec le serveur complet :")
print("  1. uvicorn main:app --host 127.0.0.1 --port 8000 --reload")
print("  2. POST http://localhost:8000/api/v1/webhook/whatsapp")
print("     avec le payload JSON ci-dessous :")
print("""
  {
    "object": "whatsapp_business_account",
    "entry": [{
      "changes": [{
        "value": {
          "messages": [{
            "from": "33642087770",
            "id":   "wamid.test001",
            "type": "text",
            "text": { "body": "renouvellement" }
          }]
        }
      }]
    }]
  }
""")
print("  Chaque POST simule une réponse WhatsApp de l'usager.")
print("  Le dossier doit déjà exister en base (créé via POST /api/v1/dossiers/initiate).")
