content = open("main.py", encoding="utf-8").read()
old = "        whatsapp_envoye = False"
new = "        whatsapp_envoye = False\n        _is_enfant_intro = True  # valeur par defaut"
if old in content:
    content = content.replace(old, new, 1)
    open("main.py", "w", encoding="utf-8").write(content)
    import py_compile
    py_compile.compile("main.py", doraise=True)
    print("OK - _is_enfant_intro defini, syntaxe OK")
else:
    print("TEXTE NON TROUVE")
