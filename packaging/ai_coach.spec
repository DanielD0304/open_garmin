# PyInstaller-Spezifikation fuer die AI-Coach-Desktop-App.
# Bauen: scripts/build_exe.ps1  (oder: pyinstaller packaging/ai_coach.spec --noconfirm)
# Ergebnis: dist/AI Coach/AI Coach.exe  (onedir: startet schneller als eine einzelne Datei)

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent  # noqa: F821 – von PyInstaller gesetzt

hiddenimports = (
    collect_submodules("uvicorn")
    + collect_submodules("garminconnect")
    + ["webview.platforms.edgechromium", "clr"]
)

a = Analysis(  # noqa: F821
    [str(ROOT / "app.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "frontend"), "frontend")],
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AI Coach",
    icon=str(ROOT / "packaging" / "ai_coach.ico"),
    console=False,
    upx=False,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="AI Coach",
)
