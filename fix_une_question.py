content = open("main.py", encoding="utf-8").read()
old = "questions_falc = simplify_questions(questions_expertes[:4], is_enfant=_is_enfant_intro)"
new = "questions_falc = simplify_questions(questions_expertes[:1], is_enfant=_is_enfant_intro)"
if old in content:
    content = content.replace(old, new, 1)
    open("main.py", "w", encoding="utf-8").write(content)
    import py_compile
    py_compile.compile("main.py", doraise=True)
    print("OK - 1 seule question au demarrage, syntaxe OK")
else:
    print("TEXTE NON TROUVE")
