content = open("main.py", encoding="utf-8").read()
content = content.replace(
    "texte_brut=request.texte_brut,",
    "raw_input=request.texte_brut,"
)
open("main.py", "w", encoding="utf-8").write(content)
import py_compile
py_compile.compile("main.py", doraise=True)
print("OK - syntaxe OK")
