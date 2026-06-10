lines = open("main.py", encoding="utf-8").readlines()
for i, l in enumerate(lines):
    if "/login" in l and ("app.get" in l or "app.post" in l or "router" in l):
        print(i, l.rstrip())
