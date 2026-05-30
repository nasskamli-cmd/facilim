import sqlite3

conn = sqlite3.connect("mdph_dossiers.db")
rows = conn.execute("SELECT dossier_id, nom_enfant, prenom_enfant, statut FROM dossiers WHERE deleted_at IS NULL").fetchall()
for r in rows:
    print(r)
conn.close()
