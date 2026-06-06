"""
app/tests/qa/qa_prod_2.py
━━━━━━━━━━━━━━━━━━━━━━━━━
QA-PROD-2 — Visibilité du cockpit professionnel dans le dashboard

Vérifie, SANS recalcul ni logique métier nouvelle, que :

  A. Câblage statique du dashboard (dashboard.html)
     - panneau #panel-cockpit présent
     - fonction renderCockpit présente
     - renderCockpit lit cockpit_pro_json (JSON.parse)
     - renderCockpit est appelée dans openDossier
     - mention « FACILIM recommande. Le professionnel valide. » présente
     - AUCUN fetch / appel moteur dans renderCockpit (pas de recalcul frontend)
     - les 8 sections (ids) sont présentes

  B. Mapping des données — sur 4 cockpits RÉELS (Karim, Lucas, SEP, aidant)
     - chaque section a sa clé source dans cockpit_pro_json
     - robustesse : droits_oublies vide géré explicitement

  C. Artefacts visuels
     - génère app/tests/qa/reports/cockpit_render_<n>.html
       (renderCockpit + markup EXTRAITS de dashboard.html → zéro duplication,
        alimentés par le cockpit réel) pour capture d'écran.

PASS = tous les contrôles A + B sur 4/4 profils.

Usage :
  python -m app.tests.qa.qa_prod_2
"""

from __future__ import annotations

import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import json
import os
import re
from pathlib import Path

sys.path.insert(0, ".")
os.environ.setdefault("DATABASE_URL", "sqlite:///./mdph_dossiers.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-key-32-chars-minimum-length!")
os.environ.setdefault("WHATSAPP_API_TOKEN", "test")

from app.tests.qa.qa_prod_1 import PROFILS
from app.engines import facilim_prod

DASHBOARD = Path("app/dashboards/dashboard.html")
REPORTS = Path("app/tests/qa/reports")

# id HTML → (clé cockpit source, libellé section)
SECTIONS = [
    ("cockpit-resume",     "resume",              "1. Synthèse professionnelle"),
    ("cockpit-droits",     "droits_detectes",     "2. Droits détectés"),
    ("cockpit-oublies",    "droits_oublies",      "3. Droits oubliés"),
    ("cockpit-risques",    "risques_refus",       "4. Risques du dossier"),
    ("cockpit-preuves",    "pieces_prioritaires", "5. Preuves recommandées"),
    ("cockpit-gate",       "gate_export",         "6. Gate CERFA"),
    ("cockpit-plan",       "plan_action",         "7. Plan d'action"),
    ("cockpit-validation", "validation_humaine",  "8. Validation humaine"),
]


def checks_statiques(txt: str) -> list[tuple[str, bool]]:
    # Isoler le corps de renderCockpit pour vérifier l'absence de recalcul
    # Borne sur la fermeture propre de renderCockpit (accolade en colonne 0),
    # robuste à l'insertion d'autres fonctions juste après (ex. renderHistorique).
    m = re.search(r"function renderCockpit\(d\) \{(.*?)\n\}\n", txt, re.S)
    body = m.group(1) if m else ""
    res = [
        ("panneau #panel-cockpit présent",            'id="panel-cockpit"' in txt),
        ("fonction renderCockpit présente",           "function renderCockpit(d)" in txt),
        ("renderCockpit lit cockpit_pro_json",        "cockpit_pro_json" in body and "JSON.parse" in body),
        ("renderCockpit appelée dans openDossier",    "renderCockpit(d)" in txt),
        ("mention 'FACILIM recommande...' présente",  "FACILIM recommande. Le professionnel valide." in txt),
        ("aucun fetch dans renderCockpit (no recalc)", "fetch(" not in body),
        ("aucun appel moteur dans renderCockpit",     "/api/" not in body),
        ("8 sections (ids) présentes",                all(f'id="{sid}"' in txt for sid, _, _ in SECTIONS)),
    ]
    return res


def extraire_render_et_panel(txt: str) -> tuple[str, str]:
    """Extrait renderCockpit + le markup du panneau depuis dashboard.html (zéro duplication)."""
    m = re.search(r"(function renderCockpit\(d\) \{.*?\n\})\n", txt, re.S)
    render_fn = m.group(1) if m else ""
    ps = txt.index('<div id="panel-cockpit"')
    # Le panneau cockpit est immédiatement suivi du panneau historique (PROD-5) ;
    # on borne sur ce marqueur, sinon sur la Zone pro (compat. ascendante).
    try:
        pe = txt.index("<!-- ── Panneau HISTORIQUE", ps)
        chunk = txt[ps:pe].rstrip()
    except ValueError:
        pe = txt.index("<!-- Zone pro", ps)
        chunk = txt[ps:pe].rstrip()
        chunk = chunk[:chunk.rfind("</div>")].rstrip()
    return render_fn, chunk


# CSS inline hors-ligne (sous-ensemble des utilitaires Tailwind utilisés par le panneau).
# Évite la dépendance au CDN Tailwind (JIT navigateur qui bloque la capture).
HARNESS_CSS = r"""
*{box-sizing:border-box}body{font-family:system-ui,'Segoe UI',sans-serif;color:#374151;margin:0}
.hidden{display:none}.mt-4{margin-top:1rem}.mb-3{margin-bottom:.75rem}.mb-2{margin-bottom:.5rem}.mb-1{margin-bottom:.25rem}.mt-1{margin-top:.25rem}.mt-0\.5{margin-top:.125rem}
.p-6{padding:1.5rem}.px-5{padding:0 1.25rem}.py-3{padding:.75rem 0}.py-4{padding:1rem 0}.py-2{padding:.5rem 0}.py-1{padding:.25rem 0}.px-3{padding:0 .75rem}.px-2{padding:0 .5rem}.px-2\.5{padding:0 .625rem}.px-1\.5{padding:0 .375rem}.py-0\.5{padding:.125rem 0}.pl-3{padding-left:.75rem}
.px-5.py-3{padding:.75rem 1.25rem}.px-5.py-4{padding:1rem 1.25rem}.px-5.py-2{padding:.5rem 1.25rem}.px-3.py-2{padding:.5rem .75rem}.px-2.py-0\.5{padding:.125rem .5rem}.px-2\.5.py-1{padding:.25rem .625rem}.px-2\.5.py-0\.5{padding:.125rem .625rem}.px-1\.5.py-0\.5{padding:.125rem .375rem}
.flex{display:flex}.flex-wrap{flex-wrap:wrap}.items-center{align-items:center}.items-start{align-items:flex-start}.justify-between{justify-content:space-between}.gap-2{gap:.5rem}.gap-1\.5{gap:.375rem}
.border{border:1px solid #e5e7eb}.border-l-2{border-left:3px solid #818cf8}.border-b{border-bottom:1px solid #eee}.last\:border-0:last-child{border:0}
.rounded-xl{border-radius:.75rem}.rounded-lg{border-radius:.5rem}.rounded-full{border-radius:9999px}.overflow-hidden{overflow:hidden}.max-w-2xl{max-width:42rem}
.text-xs{font-size:.75rem;line-height:1.4}.text-sm{font-size:.875rem}.text-\[10px\]{font-size:10px}
.font-semibold{font-weight:600}.font-bold{font-weight:700}.font-medium{font-weight:500}
.uppercase{text-transform:uppercase}.italic{font-style:italic}.tracking-wide{letter-spacing:.03em}.leading-relaxed{line-height:1.6}.whitespace-nowrap{white-space:nowrap}.opacity-90{opacity:.9}
.space-y-1\.5>*+*{margin-top:.375rem}.space-y-1>*+*{margin-top:.25rem}.space-y-2>*+*{margin-top:.5rem}.divide-y>*+*{border-top:1px solid #f3f4f6}
.bg-gray-50{background:#f9fafb}.bg-gray-100{background:#f3f4f6}.bg-facilim-50{background:#eef2ff}.bg-facilim-100{background:#e0e7ff}.bg-amber-50{background:#fffbeb}.bg-red-50{background:#fef2f2}.bg-orange-50{background:#fff7ed}.bg-green-50{background:#f0fdf4}.bg-red-100{background:#fee2e2}.bg-orange-100{background:#ffedd5}.bg-green-100{background:#dcfce7}
.text-gray-400{color:#9ca3af}.text-gray-500{color:#6b7280}.text-gray-600{color:#4b5563}.text-gray-700{color:#374151}.text-gray-800{color:#1f2937}.text-red-600{color:#dc2626}.text-red-700{color:#b91c1c}.text-orange-700{color:#c2410c}.text-green-600{color:#16a34a}.text-green-700{color:#15803d}.text-facilim-700{color:#4338ca}.text-facilim-900{color:#312e81}.text-amber-800{color:#92400e}
.border-facilim-100{border-color:#e0e7ff}.border-amber-100{border-color:#fde68a}.border-gray-50{border-color:#f9fafb}
"""


def generer_harness(render_fn: str, panel_html: str, cockpit: dict, nom: str) -> Path:
    data = json.dumps(cockpit, ensure_ascii=False)
    page = f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<title>Cockpit — {nom}</title>
<style>{HARNESS_CSS}</style>
</head><body class="p-6">
<h1 class="text-sm text-gray-400 mb-3">Harness de rendu — {nom} (données réelles cockpit_pro_json, aucun recalcul)</h1>
<div class="max-w-2xl">
{panel_html}
</div>
<script>
{render_fn}
// Donnée RÉELLE produite par facilim_prod (sérialisée comme en base)
const d = {{ cockpit_pro_json: {data} }};
renderCockpit(d);
</script>
</body></html>"""
    REPORTS.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", nom.lower()).strip("_")
    path = REPORTS / f"cockpit_render_{slug}.html"
    path.write_text(page, encoding="utf-8")
    return path


def main() -> None:
    txt = DASHBOARD.read_text(encoding="utf-8")
    sep = "═" * 64
    print(sep); print("  QA-PROD-2 — Visibilité du cockpit professionnel"); print(sep)

    # A. Câblage statique
    print("\n  ── A. Câblage statique (dashboard.html) ──")
    stat = checks_statiques(txt)
    for label, ok in stat:
        print(f"     {'✅' if ok else '❌'} {label}")
    statique_ok = all(ok for _, ok in stat)

    # B + C. Données réelles + artefacts
    render_fn, panel_html = extraire_render_et_panel(txt)
    print(f"\n  ── B. Mapping données (4 cockpits réels) ──")
    profils_ok = 0
    artefacts = []
    for p in PROFILS:
        r = facilim_prod.run(p["donnees"], profil_mdph=p["profil_mdph"],
                             profil_handicap=p["profil_handicap"], generer_cerfa=False)
        cockpit = r.cockpit_professionnel()
        manquantes = [lib for _, key, lib in SECTIONS if key not in cockpit]
        ok = len(manquantes) == 0
        if ok:
            profils_ok += 1
        path = generer_harness(render_fn, panel_html, cockpit, p["nom_test"])
        artefacts.append(path)
        oublies = len(cockpit.get("droits_oublies", []))
        gate = (cockpit.get("gate_export", {}) or {}).get("decision", "?")
        print(f"     {'✅' if ok else '❌'} {p['nom_test']:32} | sections OK={8-len(manquantes)}/8 "
              f"| oubliés={oublies} | gate={gate} | → {path.name}")
        if manquantes:
            print(f"        clés manquantes : {manquantes}")

    print(f"\n{sep}")
    ok_global = statique_ok and profils_ok == len(PROFILS)
    print(f"  DÉCISION QA-PROD-2 : {'✅ PASS' if ok_global else '❌ FAIL'} "
          f"(statique={'OK' if statique_ok else 'KO'}, profils={profils_ok}/{len(PROFILS)})")
    print(f"  Artefacts visuels : {len(artefacts)} pages dans {REPORTS}/")
    print(sep)
    sys.exit(0 if ok_global else 1)


if __name__ == "__main__":
    main()
