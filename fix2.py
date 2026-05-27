content = open("main.py", encoding="utf-8").read()
lines = content.split("\n")
for i, l in enumerate(lines):
    if "whatsapp_envoye = False" in l:
        print(f"ligne {i}: {repr(l)}")
