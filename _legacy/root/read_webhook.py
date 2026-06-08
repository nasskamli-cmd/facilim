# Webhook WhatsApp - ce qui se passe quand une reponse arrive
lines = open("main.py", encoding="utf-8").readlines()
print("=== WEBHOOK ligne 567 ===")
for i, l in enumerate(lines[566:650], start=566):
    print(i, l.rstrip())
