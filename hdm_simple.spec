# -*- mode: python ; coding: utf-8 -*-
# FALLBACK spec — no icon, no version resource.
# Use only if hdm.spec fails:  pyinstaller hdm_simple.spec --noconfirm --clean
# Result: dist\HDM-2.1.2\HDM-2.1.2.exe   (then run build_installer.bat)

block_cipher = None

a = Analysis(
    ["hdm_gui.py"],
    pathex=["."],
    binaries=[],
    datas=[("web/index.html", "web"), ("web/logo.png", "web"), ("hdm.ico", "."), ("endpoints.json", ".")],
    hiddenimports=["hdm_engine", "hdm_license", "hdm_server", "webbrowser"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "PySide6", "numpy", "pandas"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HDM-2.1.2",
    debug=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="HDM-2.1.2",
)
