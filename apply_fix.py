content = open("services/conversation_agent.py", encoding="utf-8").read()

old = "Ton r\u00f4le : collecter de mani\u00e8re conversationnelle et bienveillante toutes les informations n\u00e9cessaires au dossier MDPH {sujet_dossier}."

new = "Ton r\u00f4le : collecter de mani\u00e8re conversationnelle et bienveillante toutes les informations n\u00e9cessaires au dossier MDPH {sujet_dossier}. Une fois toutes les informations collect\u00e9es, Facilim g\u00e9n\u00e8re automatiquement le CERFA MDPH et l envoie par email \u00e0 la famille. Si la personne demande l envoi du dossier, explique-lui que Facilim s en occupe automatiquement d\u00e8s que le dossier est complet."

if old in content:
    content = content.replace(old, new)
    open("services/conversation_agent.py", "w", encoding="utf-8").write(content)
    print("OK - prompt corrige")
else:
    print("TEXTE NON TROUVE - affiche ligne 23:")
    lines = content.split("\n")
    print(repr(lines[23]))
