lines = open("main.py", encoding="utf-8").readlines()
# Ligne 319 et contexte
print("=== APPEL ligne 319 ===")
for i, l in enumerate(lines[314:330], start=314):
    print(i, l.rstrip())

# Definition de extract_text
print("\n=== DEFINITION extract_text ===")
for i, l in enumerate(lines):
    if "def extract_text" in l:
        print(i, l.rstrip())
        for j, ll in enumerate(lines[i+1:i+5], start=i+1):
            print(j, ll.rstrip())
        break
