# -*- coding: utf-8 -*-
"""Совместимость: интерфейс на PySide6 перенесён в gui_qt.py (лёгкая сборка)."""
from gui_qt import MainWindow, WarningDialog, main  # noqa: F401

__all__ = ["MainWindow", "WarningDialog", "main"]
