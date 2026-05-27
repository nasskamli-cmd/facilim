content = open("requirements.txt", encoding="utf-8").read()
if "aiofiles" not in content:
    content = content.rstrip() + "\naiofiles>=23.2.1\n"
    open("requirements.txt", "w", encoding="utf-8").write(content)
    print("OK - aiofiles ajoute")
else:
    print("deja present")
print(open("requirements.txt").read())
