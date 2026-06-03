"""
app/engines/pdf/ — Package de génération du CERFA 15692*01.

Architecture modulaire calquée sur les 10 onglets de l'interface Facilim :
  cerfa_filler.py  → orchestrateur de haut niveau (point d'entrée unique)
  accueil.py       → Onglet 1  (page de garde, type de demande)
  section_a.py     → Onglets 2-3 (identité, représentation)
  section_b.py     → Onglets 4-6 (quotidien, compensations, besoins)
  section_c.py     → Onglet 7   (scolarité)
  section_d.py     → Onglets 8-9 (situation et projet professionnel)
  section_f.py     → Onglet 10  (aidant familial)
"""

from app.engines.pdf.cerfa_filler import CerfaFiller, CerfaFillerResult

__all__ = ["CerfaFiller", "CerfaFillerResult"]
