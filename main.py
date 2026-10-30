# -*- coding: utf-8 -*-
"""Точка входа AI Dialysis Diary.

Запуск для разработки:  python main.py
Сборка ЛЁГКОГО EXE (~10 МБ):  pyinstaller AIDialysisDiary.spec
Сборка EXE на PySide6 (~140 МБ): pyinstaller AIDialysisDiary_Qt.spec

При наличии установленного PySide6 запускается «красивый» интерфейс (gui_qt.py),
иначе — полностью аналогичный лёгкий интерфейс на tkinter (gui_tk.py).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    try:
        from gui_qt import main as qt_main
    except ImportError:
        from gui_tk import main as tk_main
        return tk_main()
    return qt_main()


if __name__ == "__main__":
    raise SystemExit(main())
