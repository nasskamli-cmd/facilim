content = open("services/conversation_agent.py", encoding="utf-8").read()

# Trouve et affiche les lignes avec le mauvais comportement
print("=== LIGNES PROBLEMATIQUES ===")
for i, line in enumerate(content.split("\n")):
    if any(x in line.lower() for x in ["envoyer", "collecter", "role est", "constituer", "mon role"]):
        print(f"{i}: {line}")
