# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['src\\main.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('src\\resources', 'resources'),
    ],
    hiddenimports=[
        'faster_whisper',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'sounddevice',
        'pynput',
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
        'pyperclip',
        'core.audio_recorder',
        'core.transcriber',
        'core.keyboard_typer',
        'core.hotkey_manager',
        'gui.system_tray',
        'gui.settings_dialog',
        'utils.config',
        'utils.logger',
        'utils.resource_path',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='Resonance',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='src\\resources\\icons\\app.ico',  # Application icon
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Resonance',
)
