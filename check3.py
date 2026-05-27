import re
content = open("main.py", encoding="utf-8").read()
imports = re.findall(r"^(?:import|from)\s+(\w+)", content, re.MULTILINE)
stdlib = {"os","sys","re","json","datetime","typing","uuid","logging","time","pathlib","io","traceback","asyncio","functools","collections","itertools","hashlib","hmac","base64","urllib","http","email","copy","math","random","string","struct","socket","threading","subprocess","tempfile","shutil","glob","pickle","csv","html","xml","sqlite3","zipfile","gzip","zlib","abc","contextlib","dataclasses","enum","warnings","inspect","secrets","calendar"}
third_party = sorted(set(imp for imp in imports if imp not in stdlib and not imp.startswith("_")))
reqs = open("requirements.txt").read()
print("=== MANQUANTS dans requirements.txt ===")
for imp in third_party:
    pkg = imp.replace("_","-")
    if imp not in reqs and pkg not in reqs:
        print("ABSENT:", imp)
print("=== TOUS les imports tiers ===")
for imp in third_party:
    print(" -", imp)
