import py_compile, sys
try:
    py_compile.compile("main.py", doraise=True)
    print("Syntaxe OK")
except py_compile.PyCompileError as e:
    print("ERREUR SYNTAXE:", e)
