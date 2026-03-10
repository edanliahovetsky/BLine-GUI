# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for BLine macOS .app bundle

from pathlib import Path

project_dir = Path(SPECPATH).parent
assets_dir = project_dir / 'assets'
build_dir = Path(SPECPATH) / 'build'
icns_path = build_dir / 'BLine.icns'

a = Analysis(
    [str(project_dir / 'main.py')],
    pathex=[str(project_dir)],
    binaries=[],
    datas=[(str(assets_dir), 'assets')],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'imageio',
        'pyshortcuts',
        'assets_rc',
    ],
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
    [],
    exclude_binaries=True,
    name='BLine',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icns_path) if icns_path.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BLine',
)

app = BUNDLE(
    coll,
    name='BLine.app',
    icon=str(icns_path) if icns_path.exists() else None,
    bundle_identifier=None,
)
