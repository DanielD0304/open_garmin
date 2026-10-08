# Baut die Desktop-App: dist\AI Coach\AI Coach.exe
# Aufruf aus dem Projektordner:  .\scripts\build_exe.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path '.\venv\Scripts\python.exe')) {
    Write-Host 'Erstelle venv ...'
    python -m venv venv
}
& .\venv\Scripts\python -m pip install -q -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'pip install fehlgeschlagen' }

if (-not (Test-Path '.\packaging\ai_coach.ico')) {
    & .\venv\Scripts\python .\packaging\make_icon.py
}

& .\venv\Scripts\pyinstaller .\packaging\ai_coach.spec --noconfirm --clean --distpath .\dist --workpath .\build
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller fehlgeschlagen' }

Write-Host ''
Write-Host "Fertig: $root\dist\AI Coach\AI Coach.exe"
Write-Host 'Verknuepfungen anlegen: .\scripts\install_shortcuts.ps1'
