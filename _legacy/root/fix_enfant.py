lines = open("main.py", encoding="utf-8").readlines()
for i, l in enumerate(lines):
    if "_is_enfant_intro" in l:
        print(i, l.rstrip())
