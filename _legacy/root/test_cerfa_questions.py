"""
test_cerfa_questions.py — Diagnostique le démarrage automatique du dialogue CERFA.

Teste exactement ce que fait _demarrer_dialogue_cerfa() dans main.py :
  1. prepopuler_cerfa_depuis_dossier  — quels champs sont pré-remplis ?
  2. get_next_cerfa_field             — quel est le premier champ manquant ?
  3. traiter_dossier_cerfa            — quel message serait envoyé ?

Aucun envoi WhatsApp réel.

Lance avec :
    python test_cerfa_questions.py
"""

import sys, os, json, pprint
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.conversation_agent import (
    prepopuler_cerfa_depuis_dossier,
    get_next_cerfa_field,
)
from services.cerfa_service import traiter_dossier_cerfa

SEP  = "=" * 65
SEP2 = "-" * 65

# ── Dossier simulé ────────────────────────────────────────────────────────────
# Représente un dossier tel qu'il existe en base juste après DROITS_A_VALIDER :
# cerfa_reponses est vide, mais les champs du dossier sont renseignés.
dossier = {
    "dossier_id":           "TEST-QUESTIONS-001",
    "nom_enfant":           "DUPONT",
    "prenom_enfant":        "Marie",
    "ddn_enfant":           "15/03/1985",
    "adresse_enfant":       "12 rue des Lilas",
    "cp_enfant":            "69003",
    "commune_enfant":       "LYON",
    "telephone_famille":    "0601020304",
    "email_famille":        "marie.dupont@example.com",
    "departement_code":     "69",
    "cerfa_reponses":       {},          # vide — comme à la création
    "analyse": {
        "statut":            "COMPLET",
        "droits_identifies": ["AAH", "RQTH"],
        "score_global":      72,
        "donnees_structurees": {
            "is_enfant":           False,
            "genre":               "femme",
            "situation_familiale": "celibataire",
            "a_enfants_charge":    False,
            "type_logement":       "appartement",
            "statut_occupation":   "locataire",
            "type_demande":        "premiere_demande",
            "deja_connu_mdph":     False,
            "accident_travail":    False,
            "consentement_informations": True,
        },
        "elements_probants": ["TDA/H diagnostiqué 2022", "suivi psychiatrique"],
        "recommandation_finale": "Dossier AAH + RQTH recommandé.",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
print(SEP)
print("ÉTAPE 1 — État initial de cerfa_reponses (avant prepopuler)")
print(SEP)
cerfa_reponses = dossier.get("cerfa_reponses") or {}
print(f"Nb champs remplis : {len([v for v in cerfa_reponses.values() if v])}")
print(f"Clés présentes    : {list(cerfa_reponses.keys()) or '(aucune)'}")

# ─────────────────────────────────────────────────────────────────────────────
print()
print(SEP)
print("ÉTAPE 2 — Après prepopuler_cerfa_depuis_dossier")
print(SEP)
prepopuler_cerfa_depuis_dossier(cerfa_reponses, dossier)
dossier["cerfa_reponses"] = cerfa_reponses

remplis   = {k: v for k, v in cerfa_reponses.items() if v and str(v) not in ("__via_email__", "sent")}
vides     = {k: v for k, v in cerfa_reponses.items() if not v or str(v) in ("__via_email__", "sent")}

print(f"Nb champs REMPLIS après prepopuler : {len(remplis)}")
print("Champs remplis :")
for k, v in remplis.items():
    print(f"  {k:35s} = {str(v)[:60]}")

print(f"\nNb champs VIDES/SENTINEL après prepopuler : {len(vides)}")
print("Champs vides :")
for k, v in vides.items():
    print(f"  {k:35s} = {repr(v)}")

# ─────────────────────────────────────────────────────────────────────────────
print()
print(SEP)
print("ÉTAPE 3 — get_next_cerfa_field")
print(SEP)
first_field = get_next_cerfa_field(cerfa_reponses)
if first_field:
    print(f"✅ Premier champ manquant : {first_field!r}")
else:
    print("🟠 get_next_cerfa_field retourne None — tous les champs sont considérés remplis")
    print("   → _demarrer_dialogue_cerfa sortirait ici sans envoyer de message")

# ─────────────────────────────────────────────────────────────────────────────
print()
print(SEP)
print("ÉTAPE 4 — traiter_dossier_cerfa (sans WhatsApp réel)")
print(SEP)
_donnees = {**dossier, **cerfa_reponses}
resultat = traiter_dossier_cerfa(_donnees)

print(f"type             : {resultat.get('type')}")
print(f"valide           : {resultat.get('valide')}")
print(f"nb erreurs       : {len(resultat.get('erreurs', []))}")

if resultat.get("erreurs"):
    print("Erreurs :")
    for e in resultat["erreurs"]:
        print(f"  • {e}")

msg = resultat.get("message_a_envoyer", "")
if msg:
    print(f"\nmessage_a_envoyer ({len(msg)} chars) :")
    print(SEP2)
    print(msg)
    print(SEP2)
else:
    print("\n🟠 message_a_envoyer est VIDE")
    print("   → _demarrer_dialogue_cerfa sortirait ici sans envoyer de message")

if resultat.get("questions_restantes"):
    print(f"\nquestions_restantes ({len(resultat['questions_restantes'])}) :")
    for q in resultat["questions_restantes"]:
        print(f"  • {q}")

# ─────────────────────────────────────────────────────────────────────────────
print()
print(SEP)
print("RÉSUMÉ DIAGNOSTIC")
print(SEP)
if not first_field and not msg:
    print("❌ PROBLÈME : prepopuler remplit tout + get_next_cerfa_field = None")
    print("   Le dialogue CERFA ne peut pas démarrer car tous les champs sont")
    print("   considérés comme remplis dès la pré-population.")
    print("   → Vérifier la logique de prepopuler_cerfa_depuis_dossier")
elif not msg:
    print(f"❌ PROBLÈME : first_field={first_field!r} mais message_a_envoyer vide")
    print("   traiter_dossier_cerfa ne génère pas de message pour ce champ.")
else:
    print(f"✅ Le dialogue CERFA peut démarrer.")
    print(f"   Premier champ : {first_field!r}")
    print(f"   Message prêt  : {msg[:80]}…")
