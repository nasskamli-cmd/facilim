lines = open("main.py", encoding="utf-8").readlines()
for i, l in enumerate(lines[340:365], start=340):
    print(i, l.rstrip())
