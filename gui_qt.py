# -*- coding: utf-8 -*-
"""Главное окно AI Dialysis Diary (PySide6, тёмная тема).

Блок 1 — загрузка файлов; Блок 2 — формирование; Блок 3 — список дневников
слева и предпросмотр справа. Никаких сетевых запросов: всё локально.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.models import STATUS_ERROR, STATUS_NEEDS_CHECK, STATUS_READY, Diary
from app.service import ServiceError, copy_all_text, generate_diaries, save_all_diaries, save_diary_txt
from app.theme import DARK_STYLE, STATUS_COLORS


class WarningDialog(QDialog):
    """Окно «Показать предупреждения» с рекомендациями."""

    def __init__(self, diary: Diary, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Предупреждения — дневник №{diary.number}")
        self.resize(640, 420)
        layout = QVBoxLayout(self)
        title = QLabel(f"Статус: {diary.status}")
        title.setStyleSheet(f"color: {STATUS_COLORS.get(diary.status, '#e8eaed')}; font-weight: 600;")
        layout.addWidget(title)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(diary.warnings_text())
        layout.addWidget(text)
        btn = QPushButton("Закрыть")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AI Dialysis Diary")
        self.resize(1180, 760)
        self.map_path: Optional[Path] = None
        self.template_path: Optional[Path] = None
        self.diaries: List[Diary] = []

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QLabel("AI Dialysis Diary — дневники гемодиализа")
        header_font = QFont()
        header_font.setPointSize(16)
        header_font.setBold(True)
        header.setFont(header_font)
        root.addWidget(header)
        subtitle = QLabel("Шаблон неизменяем. Данные берутся только из карты. Каждый дневник проходит проверку.")
        subtitle.setObjectName("subtitle")
        root.addWidget(subtitle)

        # ---------------- Блок 1. Загрузка файлов ----------------
        card_files = QWidget()
        card_files.setObjectName("card")
        file_layout = QHBoxLayout(card_files)
        self.btn_map = QPushButton("Загрузить карту диализных процедур")
        self.btn_template = QPushButton("Загрузить шаблон дневника")
        self.lbl_map = QLabel("Карта: не загружена")
        self.lbl_template = QLabel("Шаблон: не загружен")
        for w in (self.lbl_map, self.lbl_template):
            w.setObjectName("subtitle")
        self.btn_map.clicked.connect(self._choose_map)
        self.btn_template.clicked.connect(self._choose_template)
        left_col = QVBoxLayout()
        left_col.addWidget(self.btn_map)
        left_col.addWidget(self.lbl_map)
        right_col = QVBoxLayout()
        right_col.addWidget(self.btn_template)
        right_col.addWidget(self.lbl_template)
        file_layout.addLayout(left_col)
        file_layout.addLayout(right_col)
        root.addWidget(card_files)

        # ---------------- Блок 2. Формирование ----------------
        gen_row = QHBoxLayout()
        self.btn_generate = QPushButton("Сформировать дневники")
        self.btn_generate.setObjectName("primary")
        self.btn_generate.setMinimumHeight(46)
        self.btn_generate.setEnabled(False)
        self.btn_generate.clicked.connect(self._generate)
        self.btn_copy_all = QPushButton("Копировать все дневники")
        self.btn_copy_all.setEnabled(False)
        self.btn_copy_all.clicked.connect(self._copy_all)
        self.btn_save_all = QPushButton("Сохранить все в TXT")
        self.btn_save_all.setEnabled(False)
        self.btn_save_all.clicked.connect(self._save_all)
        gen_row.addWidget(self.btn_generate, stretch=2)
        gen_row.addWidget(self.btn_copy_all, stretch=1)
        gen_row.addWidget(self.btn_save_all, stretch=1)
        root.addLayout(gen_row)

        # ---------------- Блок 3. Список + предпросмотр ----------------
        splitter = QSplitter(Qt.Horizontal)

        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._show_selected)
        splitter.addWidget(self.list_widget)

        preview_wrap = QWidget()
        pv = QVBoxLayout(preview_wrap)
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("font-weight: 600;")
        pv.addWidget(self.lbl_status)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        pv.addWidget(self.preview, stretch=1)

        btn_row = QHBoxLayout()
        self.btn_copy = QPushButton("Копировать дневник")
        self.btn_copy.clicked.connect(self._copy_current)
        self.btn_save = QPushButton("Сохранить в TXT")
        self.btn_save.clicked.connect(self._save_current)
        self.btn_warnings = QPushButton("Показать предупреждения")
        self.btn_warnings.clicked.connect(self._show_warnings)
        for b in (self.btn_copy, self.btn_save, self.btn_warnings):
            b.setEnabled(False)
            btn_row.addWidget(b)
        pv.addLayout(btn_row)
        splitter.addWidget(preview_wrap)
        splitter.setSizes([360, 780])
        root.addWidget(splitter, stretch=1)

    # ------------------------------------------------------------------
    def _choose_map(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Выберите карту диализных процедур", "",
                                              "Текстовые файлы (*.txt);;Все файлы (*)")
        if path:
            self.map_path = Path(path)
            self.lbl_map.setText(f"Карта: {self.map_path.name}")
            self._update_generate_enabled()

    def _choose_template(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Выберите шаблон дневника", "",
                                              "Текстовые файлы (*.txt);;Все файлы (*)")
        if path:
            self.template_path = Path(path)
            self.lbl_template.setText(f"Шаблон: {self.template_path.name}")
            self._update_generate_enabled()

    def _update_generate_enabled(self) -> None:
        self.btn_generate.setEnabled(bool(self.map_path and self.template_path))

    # ------------------------------------------------------------------
    def _generate(self) -> None:
        assert self.map_path and self.template_path
        try:
            self.diaries = generate_diaries(self.map_path, self.template_path)
        except ServiceError as exc:
            QMessageBox.critical(self, "Ошибка формирования", str(exc))
            return
        self.list_widget.clear()
        for d in self.diaries:
            date = d.session.date if d.session and d.session.date else "Без даты"
            item = QListWidgetItem(f"{date} — Сеанс №{d.number}  [{d.status}]")
            item.setForeground(QColor(STATUS_COLORS.get(d.status, "#e8eaed")))
            self.list_widget.addItem(item)
        counts = ", ".join(
            f"{s}: {sum(1 for x in self.diaries if x.status == s)}"
            for s in (STATUS_READY, STATUS_NEEDS_CHECK, STATUS_ERROR)
        )
        self.statusBar().showMessage(f"Сформировано дневников: {len(self.diaries)} ({counts})")
        self.btn_copy_all.setEnabled(bool(self.diaries))
        self.btn_save_all.setEnabled(bool(self.diaries))
        if self.diaries:
            self.list_widget.setCurrentRow(0)

    # ------------------------------------------------------------------
    def _current_diary(self) -> Optional[Diary]:
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.diaries):
            return self.diaries[row]
        return None

    def _show_selected(self, row: int) -> None:
        if not (0 <= row < len(self.diaries)):
            return
        d = self.diaries[row]
        self.preview.setPlainText(d.full_text)
        color = STATUS_COLORS.get(d.status, "#e8eaed")
        extra = f" • предупреждений: {len(d.warnings)}" if d.warnings else ""
        self.lbl_status.setText(f"Статус: {d.status}{extra}")
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: 600;")
        for b in (self.btn_copy, self.btn_save, self.btn_warnings):
            b.setEnabled(True)

    # ------------------------------------------------------------------
    def _copy_current(self) -> None:
        d = self._current_diary()
        if not d:
            return
        if d.status == STATUS_ERROR:
            QMessageBox.warning(
                self, "Дневник со статусом «Ошибка»",
                "Этот дневник нельзя копировать без исправления данных.\n\n"
                "Откройте «Показать предупреждения», устраните проблемы и повторите формирование.")
            return
        if d.status == STATUS_NEEDS_CHECK:
            answer = QMessageBox.question(
                self, "Требует проверки",
                "У дневника есть предупреждения. Скопировать текст в буфер обмена?\n"
                "Проверьте его перед вставкой в МИС.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        QGuiApplication.clipboard().setText(d.full_text)
        self.statusBar().showMessage(f"Дневник №{d.number} скопирован в буфер обмена.")

    def _copy_all(self) -> None:
        if not self.diaries:
            return
        error_count = sum(1 for d in self.diaries if d.status == STATUS_ERROR)
        if error_count:
            answer = QMessageBox.question(
                self, "Есть дневники со статусом «Ошибка»",
                f"В списке {error_count} дневник(ов) со статусом «Ошибка». "
                "Они будут помечены в тексте. Копировать всё?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        QGuiApplication.clipboard().setText(copy_all_text(self.diaries))
        self.statusBar().showMessage("Все дневники скопированы в буфер обмена.")

    def _save_current(self) -> None:
        d = self._current_diary()
        if not d:
            return
        folder = QFileDialog.getExistingDirectory(self, "Папка для сохранения дневника")
        if not folder:
            return
        target = save_diary_txt(d, folder)
        self.statusBar().showMessage(f"Сохранено: {target}")

    def _save_all(self) -> None:
        if not self.diaries:
            return
        folder = QFileDialog.getExistingDirectory(self, "Папка для сохранения всех дневников")
        if not folder:
            return
        paths = save_all_diaries(self.diaries, folder)
        self.statusBar().showMessage(f"Сохранено файлов: {len(paths)} в {folder}")

    def _show_warnings(self) -> None:
        d = self._current_diary()
        if not d:
            return
        dlg = WarningDialog(d, self)
        dlg.exec()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLE)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
