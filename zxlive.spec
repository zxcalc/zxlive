# -*- mode: python ; coding: utf-8 -*-

# To create executable, run:
#     pyinstaller zxlive.spec
# This will create a directory called "dist" containing the executable for the host OS.


a = Analysis(
    ['zxlive.py'],
    pathex=[],
    binaries=[],
    datas=[('zxlive/icons/magic-wand.svg', 'zxlive/icons'),
           ('zxlive/icons/tikzit-tool-edge.svg', 'zxlive/icons'),
           ('zxlive/icons/tikzit-tool-node.svg', 'zxlive/icons'),
           ('zxlive/icons/tikzit-tool-select.svg', 'zxlive/icons'),
           ('zxlive/icons/undo.svg', 'zxlive/icons'),
           ('zxlive/icons/redo.svg', 'zxlive/icons')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='zxlive',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
