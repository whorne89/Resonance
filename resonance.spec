# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Resonance — portable onedir build.

Build:
    uv pip install pyinstaller && uv pip install -e . && pyinstaller resonance.spec

Output:
    dist/Resonance/Resonance.exe
"""

from PyInstaller.utils.hooks import collect_all, copy_metadata

# Collect native DLLs and data for faster-whisper / CTranslate2
fw_datas, fw_binaries, fw_hiddenimports = collect_all('faster_whisper')
ct_datas, ct_binaries, ct_hiddenimports = collect_all('ctranslate2')

# Copy package metadata so importlib.metadata.version('resonance') works
meta_datas = copy_metadata('resonance')

a = Analysis(
    ['src/main.py'],
    pathex=['src'],
    binaries=fw_binaries + ct_binaries,
    datas=[
        ('src/resources/icons/', 'resources/icons/'),
    ] + fw_datas + ct_datas + meta_datas,
    hiddenimports=[
        'sounddevice',
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
        '_sounddevice_data',
    ] + fw_hiddenimports + ct_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'test'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Resonance',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='src/resources/icons/tray_idle.png',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Resonance',
)
