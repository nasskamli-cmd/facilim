content = open("main.py", encoding="utf-8").read()

# Remplace tous les TemplateResponse par FileResponse
content = content.replace(
    'templates.TemplateResponse("login.html", {"request": request})',
    'FileResponse("static/login.html")'
)
content = content.replace(
    'templates.TemplateResponse("verify.html", {"request": request})',
    'FileResponse("static/verify.html")'
)
content = content.replace(
    'templates.TemplateResponse("dashboard.html", {"request": request})',
    'FileResponse("static/dashboard.html")'
)

# Verifie que FileResponse est bien importe
if "FileResponse" not in content.split("from fastapi")[0] + content.split("from fastapi")[1].split("\n")[0]:
    content = content.replace(
        "from fastapi.responses import",
        "from fastapi.responses import FileResponse,"
    )

open("main.py", "w", encoding="utf-8").write(content)
print("OK - routes corrigees")

# Verification
import py_compile
py_compile.compile("main.py", doraise=True)
print("Syntaxe OK")
