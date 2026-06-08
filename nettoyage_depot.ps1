# nettoyage_depot.ps1 — Assainissement du depot Facilim
# Genere par Claude le 8 juin 2026.
# REVERSIBLE : aucun fichier n'est supprime. Tout est DEPLACE dans _legacy\ ou _archive\.
# A lancer depuis la racine du depot : C:\Users\Nassim KAMLI\mdph-backbone

$ErrorActionPreference = "Stop"

# 0. Securite : verifier qu'on est bien a la racine du depot
if (-not (Test-Path ".\app\main.py")) {
    Write-Host "ERREUR : lance ce script depuis la racine du depot (la ou se trouve le dossier 'app')." -ForegroundColor Red
    exit 1
}

# 1. Lever un eventuel verrou git fige (vu le 8 juin)
if (Test-Path ".\.git\index.lock") {
    Remove-Item ".\.git\index.lock" -Force
    Write-Host "Verrou git fige supprime (.git\index.lock)."
}

# 2. Creer les dossiers de rangement
foreach ($d in @("_legacy\root", "_legacy\services", "_archive\reports", "_archive\divers")) {
    New-Item -ItemType Directory -Force -Path $d | Out-Null
}

# 3. Fichiers VIVANTS — a NE JAMAIS deplacer (verifies un par un)
$keepRootPy     = @("config.py")
$keepServicesPy = @("__init__.py", "cerfa_expert.py", "cerfa_filler.py", "ocr_image.py")

$moved = 0

# 4. Code mort de la racine : tous les .py sauf les vivants
Get-ChildItem -File -Path . -Filter *.py | Where-Object { $keepRootPy -notcontains $_.Name } | ForEach-Object {
    Move-Item -LiteralPath $_.FullName -Destination "_legacy\root\" -Force
    Write-Host "  _legacy\root      <- $($_.Name)"
    $moved++
}

# 5. Services morts : tous les .py de services\ sauf les vivants
Get-ChildItem -File -Path .\services -Filter *.py | Where-Object { $keepServicesPy -notcontains $_.Name } | ForEach-Object {
    Move-Item -LiteralPath $_.FullName -Destination "_legacy\services\" -Force
    Write-Host "  _legacy\services  <- $($_.Name)"
    $moved++
}

# 6. Rapports .md : tous sauf README.md
Get-ChildItem -File -Path . -Filter *.md | Where-Object { $_.Name -ne "README.md" } | ForEach-Object {
    Move-Item -LiteralPath $_.FullName -Destination "_archive\reports\" -Force
    Write-Host "  _archive\reports  <- $($_.Name)"
    $moved++
}

# 7. Gros fichiers de travail encombrants
foreach ($f in @("facilim.log", "test_nait_ali.pdf")) {
    if (Test-Path ".\$f") {
        Move-Item -LiteralPath ".\$f" -Destination "_archive\divers\" -Force
        Write-Host "  _archive\divers   <- $f"
        $moved++
    }
}

# 8. Exclure _legacy et _archive du DEPLOIEMENT (ils restent dans git, mais ne partent pas en prod)
foreach ($ign in @(".railwayignore", ".dockerignore")) {
    if (Test-Path ".\$ign") {
        $content = Get-Content ".\$ign" -Raw
        if ($content -notmatch "_legacy") {
            Add-Content ".\$ign" "`n# Code mort et archives - non deployes`n_legacy/`n_archive/"
            Write-Host "  Mis a jour        :  $ign"
        }
    }
}

Write-Host ""
Write-Host "Termine. $moved fichiers ranges. Rien n'a ete supprime." -ForegroundColor Green
Write-Host ""
Write-Host "Etape suivante, verifie puis valide :" -ForegroundColor Cyan
Write-Host "    git status"
Write-Host '    git add -A'
Write-Host '    git commit -m "chore: depot assaini - code mort dans _legacy, rapports dans _archive, README source de verite"'
