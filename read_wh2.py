lines = open("main.py", encoding="utf-8").readlines()
print("=== DEBUT WEBHOOK ligne 567 ===")
for i, l in enumerate(lines[566:614], start=566):
    print(i, l.rstrip())
