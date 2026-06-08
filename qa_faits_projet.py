# -*- coding: utf-8 -*-
"""
QA RÉEL — FACILIM V2 couche de faits canoniques (domaine pilote projet_professionnel).
Exécute le VRAI code (faits.py + 3 consommateurs réels) sur le cas BIM Modeleur.
Aucune fonction mockée : seul l'INPUT (sortie d'extraction = clés plates) est fourni,
conformément au contrat documenté de l'extracteur existant.
"""
import sys

from app.services.faits import (
    upsert_fait, make_fait, derive_faits_projet_professionnel,
    get_faits, fait_id,
)
from app.engines.orchestration_engine import _calculer_completude_live
from app.engines.evidence_engine import construire_graphe_preuves
from app.engines.completeness_engine import _dim_projet_vie

MSG = "Je souhaite intégrer l'ESRP La Rouguière pour suivre une formation BIM Modeleur."

ok, ko = [], []
def check(cond, label):
    (ok if cond else ko).append(label)
    print(("[OK] " if cond else "[KO] ") + label)
def section(t):
    print("\n=== " + t + " ===")

# Sortie de l'extraction LLM EXISTANTE pour ce message (clés plates whitelist adulte)
extraction_flat = {
    "projet_professionnel":     "Devenir BIM Modeleur",
    "formation_actuelle":       "BIM Modeleur",
    "etablissement_formation":  "ESRP La Rouguière",
    "projet_orientation":       "Orientation professionnelle / formation adaptée",
}

# 1 — message reçu
section("1. Message reçu")
print("message:", MSG)
check(bool(MSG), "message présent en entrée")

# 2+3 — faits créés et persistés dans synthese['faits']
section("2+3. Faits créés et persistés dans synthese['faits']")
synthese = dict(extraction_flat)
derive_faits_projet_professionnel(
    synthese, source="whatsapp", extrait=MSG, now="2026-06-08T00:00:00+00:00"
)
faits = get_faits(synthese)
champs = {f["champ"]: f for f in faits}
for c in ("projet_professionnel", "formation_cible", "etablissement_cible", "orientation_souhaitee"):
    check(c in champs, f"fait '{c}' créé")
check(champs.get("etablissement_cible", {}).get("valeur") == "ESRP La Rouguière", "établissement cible = ESRP La Rouguière")
check(champs.get("formation_cible", {}).get("valeur") == "BIM Modeleur", "formation cible = BIM Modeleur")
check(all(f.get("source") == "whatsapp" for f in faits), "source conservée = whatsapp")
check(all(f.get("extrait") == MSG for f in faits), "extrait conservé")
check(all(f.get("statut") == "DECLARE" for f in faits), "statut = DECLARE")
check(all(f.get("id") == fait_id(f["domaine"], f["champ"]) for f in faits), "id stable = domaine.champ")
check(isinstance(synthese.get("faits"), list), "synthese['faits'] est une liste persistée")

# 4 — clés plates intactes
section("4. Back-compat : clés plates intactes")
for k, v in extraction_flat.items():
    check(synthese.get(k) == v, f"clé plate '{k}' intacte")

# Idempotence
section("Idempotence : re-projection sans doublon")
n_avant = len(get_faits(synthese))
derive_faits_projet_professionnel(synthese, source="whatsapp", extrait=MSG, now="2026-06-09T00:00:00+00:00")
n_apres = len(get_faits(synthese))
check(n_avant == n_apres == 4, f"toujours 4 faits (avant={n_avant} apres={n_apres})")
ep = [f for f in get_faits(synthese) if f["champ"] == "etablissement_cible"][0]
check(ep["created_at"] == "2026-06-08T00:00:00+00:00", "created_at conservé après update")
check(ep["updated_at"] == "2026-06-09T00:00:00+00:00", "updated_at mis à jour")

# upsert direct : mise à jour valeur, pas de doublon
section("upsert_fait : update d'un fait existant")
upsert_fait(synthese, make_fait("projet_professionnel", "formation_cible",
                                "BIM Modeleur niveau 2", "whatsapp", MSG, "DECLARE",
                                now="2026-06-10T00:00:00+00:00"))
fc = [f for f in get_faits(synthese) if f["champ"] == "formation_cible"]
check(len(fc) == 1, "pas de doublon après update")
check(fc[0]["valeur"] == "BIM Modeleur niveau 2", "valeur mise à jour")

# 5 — cockpit (projet) lit le fait
section("5. Cockpit (projet) lit le fait")
d_sans = {"texte_e_projet_vie": "", "droits_demandes": ""}
dim_sans = _dim_projet_vie(d_sans, "adulte")
# d_avec = sortie d'extraction (clés plates) → on dérive les faits…
d_avec = dict(extraction_flat)
d_avec.update({"texte_e_projet_vie": "", "droits_demandes": ""})
derive_faits_projet_professionnel(d_avec, source="whatsapp", extrait=MSG, now="2026-06-08T00:00:00+00:00")
# …puis on RETIRE la clé plate projet_orientation pour prouver que l'orientation
# est désormais détectée via le FAIT, pas via la clé plate.
d_avec.pop("projet_orientation", None)
dim_avec = _dim_projet_vie(d_avec, "adulte")
check(dim_avec.score > dim_sans.score, f"score cockpit projet augmente via fait ({dim_sans.score} -> {dim_avec.score})")
check(any("rientation" in e for e in dim_avec.elements_presents), "orientation détectée via fait")

# 6 — score complétude compte le projet
section("6. Score complétude prend en compte le projet")
base = {"nom_prenom": "RABINEAU Chloé", "telephone": "0600000000"}
s_base = _calculer_completude_live(dict(base))
plat = dict(base); plat.update(extraction_flat)
s_plat = _calculer_completude_live(plat)             # clés plates seules
s_faits_dict = dict(plat)
derive_faits_projet_professionnel(s_faits_dict, source="whatsapp", extrait=MSG)
s_faits = _calculer_completude_live(s_faits_dict)    # avec faits
print(f"score base={s_base} | +cles plates seules={s_plat} | +faits={s_faits}")
check(s_plat == s_base, "clés plates seules NE bougent PAS le score (bug V4 confirmé)")
check(s_faits > s_base, "le FAIT projet fait monter le score")

# 7 — non-régression dossier legacy (aucun 'faits')
section("7. Non-régression : dossier legacy sans 'faits'")
legacy = {"projet_orientation": "ESAT", "droits_demandes": "AAH",
          "texte_e_projet_vie": "x" * 250, "nom_prenom": "Ancien Dossier"}
try:
    dlg = _dim_projet_vie(legacy, "adulte")
    g = construire_graphe_preuves(legacy, "adulte")
    sc = _calculer_completude_live(legacy)
    check("faits" not in legacy, "aucune clé 'faits' injectée dans un dossier legacy")
    check(True, f"legacy fonctionne (cockpit={dlg.score}, preuves={g.nb_preuves_total}, score={sc})")
except Exception as e:
    check(False, f"legacy cassé: {e!r}")

# Evidence engine lit le fait
section("Evidence engine : le fait devient une preuve traçable")
g2 = construire_graphe_preuves(synthese, "adulte")
faits_preuves = [i for i in g2.items if str(i.source_champ).startswith("faits:")]
check(len(faits_preuves) >= 1, f"preuve(s) issue(s) des faits = {len(faits_preuves)}")
for i in faits_preuves:
    print("   preuve:", i.information, "|", i.source_type, "|", i.source_champ)

# BILAN
section("BILAN")
print(f"OK={len(ok)}  KO={len(ko)}")
sys.exit(1 if ko else 0)
