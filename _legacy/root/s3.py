lines = open("main.py", encoding="utf-8").readlines()
for i, l in enumerate(lines):
    if "/dashboard" in l:
        print(i, l.rstrip())
