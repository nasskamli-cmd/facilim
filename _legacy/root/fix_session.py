content = open("main.py", encoding="utf-8").read()

# L'endpoint fichier lit "_session" mais le cookie s'appelle "session_token"
# On cherche la fonction extract_text_from_file et on corrige
old = "_session: str | None = Cookie(default=None)"
new = "session_token: str | None = Cookie(default=None)"
if old in content:
    content = content.replace(old, new)
    # Corriger aussi les references internes a _session dans cette fonction
    # On cherche is_valid_session(_session) et on met session_token
    content = content.replace("is_valid_session(_session)", "is_valid_session(session_token)")
    open("main.py", "w", encoding="utf-8").write(content)
    import py_compile
    py_compile.compile("main.py", doraise=True)
    print("OK - session corrigee, syntaxe OK")
else:
    print("Parametre non trouve - cherche manuellement:")
    for i, l in enumerate(content.split("\n")):
        if "_session" in l and ("Cookie" in l or "is_valid" in l):
            print(f"  ligne {i}: {l}")
