import os, re

# Cherche dans tous les fichiers .py du projet
for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in ["__pycache__", ".git", "venv"]]
    for f in files:
        if f.endswith(".py"):
            path = os.path.join(root, f)
            content = open(path, encoding="utf-8", errors="ignore").read()
            if "def extract_text" in content and "extract_text_from_file" not in content.split("def extract_text")[0].split("\n")[-1]:
                lines = content.split("\n")
                for i, l in enumerate(lines):
                    if "def extract_text" in l and "from_file" not in l:
                        print(f"\nFICHIER: {path}, ligne {i}")
                        for j, ll in enumerate(lines[i:i+8]):
                            print(f"  {i+j}: {ll}")
