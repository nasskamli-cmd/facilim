import sys
sys.path.insert(0, ".")
try:
    import main
    print("Import OK")
except Exception as e:
    print("ERREUR IMPORT:", type(e).__name__, str(e))
