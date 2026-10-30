# -*- coding: utf-8 -*-
"""Спецификация PyInstaller для сборки AI Dialysis Diary на PySide6 (~140 МБ).

Полноценный «красивый» интерфейс gui_qt.py. Использовать, если размер файла
не критичен. Для лёгкой сборки (~10 МБ, tkinter) — AIDialysisDiary.spec.

Сборка (на Windows, из корня проекта):
    pip install -r requirements_qt.txt
    pyinstaller AIDialysisDiary_Qt.spec --clean

Результат: dist/AIDialysisDiary_Qt/AIDialysisDiary_Qt.exe
"""

block_cipher = None

a = Analysis(
    ['gui_qt.py'],
    pathex=[],
    binaries=[],
    datas=[('examples', 'examples')],
    hiddenimports=['app', 'app.main_window', 'app.service', 'app.map_parser',
                   'app.template_parser', 'app.diary_builder', 'app.validator',
                   'app.medications', 'app.models', 'app.textio', 'app.theme'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'pandas', 'scipy', 'PIL'],
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
    name='AIDialysisDiary_Qt',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='AIDialysisDiary_Qt',
)
