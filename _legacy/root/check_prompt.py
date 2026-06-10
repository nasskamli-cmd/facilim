import os
for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in ["__pycache__",".git","venv"]]
    for f in files:
        if f.endswith(".py"):
            path = os.path.join(root, f)
            c = open(path, encoding="utf-8", errors="ignore").read()
            if "envoyer" in c.lower() and ("prompt" in c.lower() or "system" in c.lower()):
                print("FICHIER:", path)
