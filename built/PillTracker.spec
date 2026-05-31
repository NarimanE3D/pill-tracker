# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

project_root = Path.cwd()
app_name = "PillTracker"
main_script = str(project_root / "PillTracker.py")
assets_dir = project_root / "assets"

hiddenimports = collect_submodules("qtpy")

datas = [
    (str(assets_dir / "icon.ico"), "assets"),
    (str(assets_dir / "icon.png"), "assets"),
]

a = Analysis(
    [main_script],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(assets_dir / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=app_name,
)
