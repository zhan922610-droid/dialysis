# -*- coding: utf-8 -*-
"""Цвета статусов и тёмная тема интерфейса (без Qt-зависимостей)."""

STATUS_COLORS = {
    "Готов": "#4caf7d",
    "Требует проверки": "#e0a53c",
    "Ошибка": "#e05c5c",
}

DARK_STYLE = """
QWidget { background: #1e2126; color: #e8eaed; font-family: 'Segoe UI', sans-serif; font-size: 14px; }
QLabel#subtitle { color: #9aa0a6; }
QPushButton {
  background: #2d3238; color: #e8eaed; border: 1px solid #3c424a;
  border-radius: 8px; padding: 10px 16px; font-size: 14px;
}
QPushButton:hover { background: #363c44; }
QPushButton:disabled { color: #6b7280; background: #262a30; }
QPushButton#primary { background: #2f6fed; border: none; font-weight: 600; padding: 12px 18px; }
QPushButton#primary:hover { background: #3f7ef7; }
QListWidget { background: #24272c; border: 1px solid #3c424a; border-radius: 8px; padding: 4px; }
QListWidget::item { padding: 10px 8px; border-radius: 6px; }
QListWidget::item:selected { background: #2f6fed; color: white; }
QTextEdit { background: #24272c; border: 1px solid #3c424a; border-radius: 8px; padding: 8px;
            font-family: 'Consolas','Segoe UI',monospace; }
QFrame#card { background: #24272c; border: 1px solid #3c424a; border-radius: 10px; }
QScrollBar:vertical { background: #24272c; width: 10px; }
QScrollBar::handle:vertical { background: #3c424a; border-radius: 5px; min-height: 24px; }
"""
