import sqlite3, json
conn = sqlite3.connect("facilim.db")
rows = conn.execute("SELECT dossier_id, email_famille, statut, score FROM dossiers ORDER BY created_at DESC LIMIT 3").fetchall()
for r in rows:
    print(f"ID: {r[0][:8]} | email: {repr(r[1])} | statut: {r[2]} | score: {r[3]}")
conn.close()
