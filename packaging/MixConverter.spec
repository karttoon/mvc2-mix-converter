# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the MvC2 Mix Converter GUI.

Build:  py -m PyInstaller packaging/MixConverter.spec --noconfirm
Output: dist/MixConverter.exe  (onefile, windowed)

ffmpeg is NOT bundled inside the exe — it ships beside it as tools/ffmpeg.exe in
the release ZIP, and config.FFMPEG resolves to that folder (dirname of the exe)
at runtime. Only the small read-only manifest is embedded (--add-data).
"""
import os

ROOT = os.path.dirname(os.path.abspath(SPECPATH))   # project root (parent of packaging/)
MIXCONV = os.path.join(ROOT, "mixconv")

# Flat local modules are imported via `sys.path.insert(0, HERE)` + bare `import x`,
# so declare them (and put mixconv/ on pathex) or analysis may miss some.
HIDDEN = ["config", "install", "convert", "disc", "afs", "manifest",
          "steam", "dc_oversize", "palette", "music"]

a = Analysis(
    [os.path.join(MIXCONV, "gui.py")],
    pathex=[MIXCONV],
    binaries=[],
    datas=[(os.path.join(ROOT, "data", "afs_manifest.json"), "data")],
    hiddenimports=HIDDEN,
    hookspath=[],
    runtime_hooks=[],
    excludes=["numpy", "PIL", "pytest", "setuptools"],   # keep the onefile lean
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MixConverter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,          # --windowed (no console popup)
    disable_windowed_traceback=False,
    icon=os.path.join(ROOT, "packaging", "app.ico")
        if os.path.exists(os.path.join(ROOT, "packaging", "app.ico")) else None,
)
