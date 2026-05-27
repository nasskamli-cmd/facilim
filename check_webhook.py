lines = open("main.py", encoding="utf-8").readlines()
for i, l in enumerate(lines):
    if "webhook" in l.lower() and ("def " in l or "app." in l):
        print(i, l.rstrip())
