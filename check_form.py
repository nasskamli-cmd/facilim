content = open("static/dashboard.html", encoding="utf-8").read()
import re
# Cherche tous les champs input/textarea du formulaire
inputs = re.findall(r'<input[^>]*>|<textarea[^>]*>', content)
for inp in inputs:
    print(inp[:150])
print("\n--- email dans le HTML ---")
if "email" in content.lower():
    lines = content.split("\n")
    for i, l in enumerate(lines):
        if "email" in l.lower():
            print(f"{i}: {l.strip()[:100]}")
else:
    print("AUCUN champ email trouve")
