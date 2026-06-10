import re
content = open("static/login.html", encoding="utf-8").read()
matches = re.findall(r'\{\{.*?\}\}|\{%.*?%\}', content, re.DOTALL)
if matches:
    print("Expressions trouvees:")
    for m in matches[:20]:
        print(" ", repr(m))
else:
    print("Aucune expression Jinja2")
    print("Taille:", len(content))
