# -*- mode: python ; coding: utf-8 -*-

import datetime
import os


# Bypass qtpy when building
os.environ["QT_API"] = "pyside6"


# Write _buildconstants.py
buildDate = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
with open('gitfourchette/_buildconstants.py', 'wt') as f:
	f.write(f"buildDate = \"{buildDate}\"\n")


block_cipher = None


a = Analysis(
    ['../gitfourchette/__main__.py'],
    pathex=[],
    binaries=[('../gitfourchette/assets', 'assets')],
    datas=[],
    hiddenimports=['_cffi_backend'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
    	'PySide6.QtNetwork',
    	'PySide6.QtOpenGL',
    	'PySide6.QtQml',
    	'PySide6.QtQuick',
    	'PySide6.QtQuick3D',
    	'PySide6.QtQuickControls2',
    	'PySide6.QtQuickWidgets',
    	'psutil'],
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
    name='GitFourchette',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch='arm64', #'universal2',
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='GitFourchette',
)
app = BUNDLE(
    coll,
    name='GitFourchette.app',
    icon='gitfourchette.icns',
    bundle_identifier='io.jor.gitfourchette',
)
