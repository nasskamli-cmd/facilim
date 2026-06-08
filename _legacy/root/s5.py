lines = open("main.py", encoding="utf-8").readlines()
for i, l in enumerate(lines[185:250], start=185):
    print(i, l.rstrip())
