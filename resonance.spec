# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Resonance — portable onedir build.

Build:
    uv pip install pyinstaller && uv pip install -e . && pyinstaller resonance.spec

Output:
    dist/Resonance/Resonance.exe
"""

import os
import sysconfig
from PyInstaller.utils.hooks import collect_all, copy_metadata

# Force-bundle the correct OpenSSL DLLs from Python's own directory.
# Without this, PyInstaller may pick up mismatched versions from PySide6,
# causing "The specified procedure could not be found" on _ssl import.
_python_dll_dir = os.path.join(os.path.dirname(sysconfig.get_path('stdlib')), 'DLLs')
ssl_binaries = []
for _dll in ('libssl-3-x64.dll', 'libcrypto-3-x64.dll', '_ssl.pyd'):
    _path = os.path.join(_python_dll_dir, _dll)
    if os.path.isfile(_path):
        ssl_binaries.append((_path, '.'))

# Collect native DLLs and data for faster-whisper / CTranslate2
fw_datas, fw_binaries, fw_hiddenimports = collect_all('faster_whisper')
ct_datas, ct_binaries, ct_hiddenimports = collect_all('ctranslate2')

# Copy package metadata so importlib.metadata.version('resonance') works
meta_datas = copy_metadata('resonance')

# Bundle Tesseract OCR for Windows EXE (if available in project root)
tesseract_datas = []
tesseract_binaries = []
if os.path.isdir('tesseract'):
    tesseract_exe = os.path.join('tesseract', 'tesseract.exe')
    if os.path.isfile(tesseract_exe):
        tesseract_binaries.append((tesseract_exe, 'tesseract'))

    tessdata_dir = os.path.join('tesseract', 'tessdata')
    if os.path.isdir(tessdata_dir):
        for file in os.listdir(tessdata_dir):
            file_path = os.path.join(tessdata_dir, file)
            if os.path.isfile(file_path):
                tesseract_datas.append((file_path, 'tesseract/tessdata'))

    print(f"Bundling Tesseract: {len(tesseract_binaries)} binaries, {len(tesseract_datas)} data files")
else:
    print("Note: 'tesseract/' directory not found — Windows uses native OCR (winocr), no bundling needed")

a = Analysis(
    ['src/main.py'],
    pathex=['src'],
    binaries=ssl_binaries + fw_binaries + ct_binaries + tesseract_binaries,
    datas=[
        ('src/resources/icons/', 'resources/icons/'),
        ('src/resources/sounds/', 'resources/sounds/'),
    ] + fw_datas + ct_datas + meta_datas + tesseract_datas,
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
