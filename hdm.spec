# -*- mode: python ; coding: utf-8 -*-
# HDM 1.0.1 — Windows build
#   python -m pip install --upgrade pyinstaller pillow PyQt6
#   pyinstaller hdm.spec --noconfirm --clean
# Result: dist\HDM-1.0.1\HDM-1.0.1.exe   (desktop window)
# Then: build_installer.bat  ->  installer\HDM-1.0.1-Setup.exe

block_cipher = None

datas = [
    ("web/index.html", "web"),
    ("web/logo.png", "web"),
    ("hdm.ico", "."),
    ("hdm-bmp.ico", "."),
    ("endpoints.json", "."),
]

a = Analysis(
    ["hdm_gui.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=["hdm_engine", "hdm_license", "hdm_server", "webbrowser"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "PySide6", "numpy", "pandas", "matplotlib"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HDM-1.0.1",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,                 # windowed: no black console
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="hdm.ico",                # taskbar / explorer icon
    version="version_info.txt",    # company + product name in Windows
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="HDM-1.0.1",
)
