content = open("services/conversation_agent.py", encoding="utf-8").read()

old = "Ton role : collecter de maniere conversationnelle et bienveillante toutes les informations necessaires au dossier MDPH {sujet_dossier}."

# Cherche la ligne exacte
lines = content.split("\n")
for i, l in enumerate(lines):
    if "Ton r" in l and "le :" in l and "collecter" in l:
        print(f"TROUVE ligne {i}: {repr(l)}")
