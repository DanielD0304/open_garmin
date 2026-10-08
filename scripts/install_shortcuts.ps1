# Legt Verknuepfungen fuer "AI Coach" im Startmenue und auf dem Desktop an.
#
#   .\scripts\install_shortcuts.ps1        # Start ueber das signierte pythonw.exe (Standard)
#   .\scripts\install_shortcuts.ps1 -Exe   # Start ueber dist\AI Coach\AI Coach.exe
#
# Standard ist pythonw.exe: Windows "Intelligente App-Steuerung" (Smart App Control) blockiert
# selbst gebaute, unsignierte .exe-Dateien. pythonw.exe ist von der Python Software Foundation
# signiert und startet die App ohne Konsolenfenster.
param([switch]$Exe)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

if ($Exe) {
    $target = Join-Path $root 'dist\AI Coach\AI Coach.exe'
    $arguments = ''
    $workdir = Split-Path $target
    $icon = "$target,0"
    if (-not (Test-Path $target)) { throw "Nicht gefunden: $target - zuerst .\scripts\build_exe.ps1 ausfuehren." }
} else {
    $target = Join-Path $root 'venv\Scripts\pythonw.exe'
    $arguments = '"' + (Join-Path $root 'app.py') + '"'
    $workdir = $root
    $icon = (Join-Path $root 'packaging\ai_coach.ico') + ',0'
    if (-not (Test-Path $target)) { throw "venv fehlt: python -m venv venv; .\venv\Scripts\pip install -r requirements.txt" }
}

$shell = New-Object -ComObject WScript.Shell
$links = @(
    (Join-Path ([Environment]::GetFolderPath('Programs')) 'AI Coach.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'AI Coach.lnk')
)
foreach ($path in $links) {
    $link = $shell.CreateShortcut($path)
    $link.TargetPath = $target
    $link.Arguments = $arguments
    $link.WorkingDirectory = $workdir
    $link.IconLocation = $icon
    $link.Description = 'AI Coach - Training, Erholung und Ernaehrung'
    $link.Save()
    Write-Host "Verknuepfung: $path"
}
