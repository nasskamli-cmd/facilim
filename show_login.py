lines = open("main.py", encoding="utf-8").readlines()
for i, l in enumerate(lines[174:200], start=174):
    print(i, l.rstrip())
