# -*- coding: utf-8 -*-
"""Спецификация PyInstaller для ЛЁГКОЙ сборки AI Dialysis Diary (~10 МБ).

Интерфейс на tkinter (входит в состав Python, Qt не упаковывается).
Это рекомендуемый вариант для передачи врачу и для загрузки/пересылки файла.

Сборка (на Windows, из корня проекта):
    pip install pyinstaller
    pyinstaller AIDialysisDiary.spec --clean

Результат: dist/AIDialysisDiary/AIDialysisDiary.exe (запускается без установленного Python).
Для «одного файла» вместо папки см. README (параметр --onefile или правка spec).
"""

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('examples', 'examples')],
    hiddenimports=['gui_tk', 'app', 'app.service', 'app.map_parser',
                   'app.template_parser', 'app.diary_builder', 'app.validator',
                   'app.medications', 'app.models', 'app.textio', 'app.theme'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6', 'PySide2', 'shiboken6',
              'matplotlib', 'numpy', 'pandas', 'scipy', 'PIL'],
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
    name='AIDialysisDiary',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # оконное приложение: консоль не показываем
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # при наличии файла app.ico заменить на icon='app.ico'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='AIDialysisDiary',
)
