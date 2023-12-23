# -*- mode: python ; coding: utf-8 -*-

from pkg.pyinstaller import spec_helper
from gitfourchette.appconsts import APP_VERSION

QT_API = "pyqt6"
spec_helper.writeBuildConstants(QT_API)

a = Analysis(
    [spec_helper.ROOT / 'gitfourchette/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[(spec_helper.ROOT / 'gitfourchette/assets', 'assets')],
    hiddenimports=['_cffi_backend'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=spec_helper.getExcludeList(QT_API),
    noarchive=False,  # True: keep pyc files
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='gitfourchette-bin',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='GitFourchette',
)
