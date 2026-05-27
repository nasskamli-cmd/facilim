content = open("main.py", encoding="utf-8").read()

# Ajoute _is_enfant_intro = True juste avant "if dossier["statut"] == "INCOMPLET":"
# On cherche la ligne whatsapp_envoye = False qui est juste avant
old = "            whatsapp_envoye = False"
new = "            whatsapp_envoye = False\n            _is_enfant_intro = True  # valeur par defaut"

if old in content:
    content = content.replace(old, new, 1)
    open("main.py", "w", encoding="utf-8").write(content)
    import py_compile
    py_compile.compile("main.py", doraise=True)
    print("OK - fix applique, syntaxe OK")
else:
    print("Texte non trouve - cherche ligne 342:")
    lines = content.split("\n")
    print(repr(lines[341]))
