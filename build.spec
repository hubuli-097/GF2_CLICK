# PyInstaller 打包配置
# 用法: pyinstaller build.spec
# 生成: dist/GF2_Click_Helper.exe
# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['gf2_gui.py'],
    pathex=[],
    datas=[
        ('calib', 'calib'),
        ('click_shots', 'click_shots'),
    ],
    hiddenimports=[],
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
    name='GF2_Click_Helper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
