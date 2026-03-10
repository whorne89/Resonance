# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Resonance — portable onedir build.

Build:
    uv pip install pyinstaller && uv pip install -e . && pyinstaller resonance.spec

Output:
    dist/Resonance/Resonance[.exe]
"""

import os
import sys
import sysconfig
from PyInstaller.utils.hooks import collect_all, copy_metadata

# Force-bundle the correct OpenSSL DLLs from Python's own directory (Windows only).
# Without this, PyInstaller may pick up mismatched versions from PySide6,
# causing "The specified procedure could not be found" on _ssl import.
ssl_binaries = []
if sys.platform == "win32":
    _python_dll_dir = os.path.join(os.path.dirname(sysconfig.get_path('stdlib')), 'DLLs')
    for _dll in ('libssl-3-x64.dll', 'libcrypto-3-x64.dll', '_ssl.pyd'):
        _path = os.path.join(_python_dll_dir, _dll)
        if os.path.isfile(_path):
            ssl_binaries.append((_path, '.'))

# Collect native DLLs and data for faster-whisper / CTranslate2
fw_datas, fw_binaries, fw_hiddenimports = collect_all('faster_whisper')
ct_datas, ct_binaries, ct_hiddenimports = collect_all('ctranslate2')

# Copy package metadata so importlib.metadata.version('resonance') works
meta_datas = copy_metadata('resonance')

# Platform-specific pynput hidden imports
if sys.platform == "win32":
    pynput_imports = ['pynput.keyboard._win32', 'pynput.mouse._win32']
elif sys.platform == "darwin":
    pynput_imports = ['pynput.keyboard._darwin', 'pynput.mouse._darwin']
else:
    pynput_imports = ['pynput.keyboard._xorg', 'pynput.mouse._xorg']

a = Analysis(
    ['src/main.py'],
    pathex=['src'],
    binaries=ssl_binaries + fw_binaries + ct_binaries,
    datas=[
        ('src/resources/icons/', 'resources/icons/'),
        ('src/resources/sounds/', 'resources/sounds/'),
    ] + fw_datas + ct_datas + meta_datas,
    hiddenimports=[
        'sounddevice',
        '_sounddevice_data',
    ] + pynput_imports + fw_hiddenimports + ct_hiddenimports,
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
