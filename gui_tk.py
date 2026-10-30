# -*- coding: utf-8 -*-
"""Главное окно AI Dialysis Diary (tkinter, тёмная тема) — вариант «лёгкий».

Интерфейс и логика полностью совпадают с версией на PySide6 (gui_qt.py):
Блок 1 — загрузка файлов; Блок 2 — формирование; Блок 3 — список дневников
слева и предпросмотр справа. Никаких сетевых запросов: всё локально.

tkinter входит в состав Python на Windows, поэтому EXE на этой основе весит
~8-12 МБ вместо ~140 МБ (Qt). Рекомендуемый вариант для передачи врачу.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext
from typing import List, Optional

from app.models import STATUS_ERROR, STATUS_NEEDS_CHECK, STATUS_READY, Diary
from app.service import (
    ServiceError,
    copy_all_text,
    generate_diaries,
    save_all_diaries,
    save_diary_txt,
)

# Цвета взяты из app/theme.py; у «требует проверки» чуть осветлённый фон текста.
BG = "#1e2126"
CARD = "#24272c"
BORDER = "#3c424a"
FG = "#e8eaed"
MUTED = "#9aa0a6"
ACCENT = "#2f6fed"
AMBER_TEXT = "#f0c060"

_STATUS_TEXT = {
    STATUS_READY: "#4caf7d",
    STATUS_NEEDS_CHECK: AMBER_TEXT,
    STATUS_ERROR: "#e05c5c",
}


class WarningWindow(tk.Toplevel):
    """Окно «Показать предупреждения» с рекомендациями."""

    def __init__(self, parent, diary: Diary):
        super().__init__(parent)
        self.title(f"Предупреждения — дневник №{diary.number}")
        self.configure(bg=BG)
        self.geometry("640x420")
        self.transient(parent)
        head = tk.Label(self, text=f"Статус: {diary.status}", bg=BG,
                        fg=_STATUS_TEXT.get(diary.status, FG),
                        font=("Segoe UI", 11, "bold"))
        head.pack(anchor="w", padx=12, pady=(12, 4))
        txt = scrolledtext.ScrolledText(self, bg=CARD, fg=FG, insertbackground=FG,
                                        relief="flat", wrap="word", height=15,
                                        font=("Consolas", 11))
        txt.pack(fill="both", expand=True, padx=12)
        txt.insert("1.0", diary.warnings_text())
        txt.configure(state="disabled")
        btn = tk.Button(self, text="Закрыть", command=self.destroy,
                        bg="#2d3238", fg=FG, activebackground="#363c44",
                        relief="flat", padx=14, pady=6, cursor="hand2")
        btn.pack(pady=10)


class MainWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.map_path: Optional[Path] = None
        self.template_path: Optional[Path] = None
        self.diaries: List[Diary] = []

        root.title("AI Dialysis Diary")
        root.geometry("1180x760")
        root.configure(bg=BG, padx=16, pady=16)
        ttk_style()
        root.option_add("*TCombobox*Listbox.background", CARD)

        # ---------------- Шапка ----------------
        tk.Label(root, text="AI Dialysis Diary — дневники гемодиализа",
                 bg=BG, fg=FG, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        tk.Label(root,
                 text="Шаблон неизменяем. Данные берутся только из карты. Каждый дневник проходит проверку.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 10))

        # ---------------- Блок 1. Загрузка файлов ----------------
        card = tk.Frame(root, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="x", pady=(0, 10))
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="x", padx=14, pady=12)
        inner.columnconfigure(0, weight=1)
        inner.columnconfigure(1, weight=1)

        self.btn_map = make_button(inner, "Загрузить карту диализных процедур", self._choose_map)
        self.btn_map.grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=4)
        self.btn_template = make_button(inner, "Загрузить шаблон дневника", self._choose_template)
        self.btn_template.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=4)

        self.lbl_map = tk.Label(inner, text="Карта: не загружена", bg=CARD, fg=MUTED,
                                anchor="w", font=("Segoe UI", 10))
        self.lbl_map.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        self.lbl_template = tk.Label(inner, text="Шаблон: не загружен", bg=CARD, fg=MUTED,
                                     anchor="w", font=("Segoe UI", 10))
        self.lbl_template.grid(row=1, column=1, sticky="ew", padx=(8, 0))

        # ---------------- Блок 2. Формирование ----------------
        gen_row = tk.Frame(root, bg=BG)
        gen_row.pack(fill="x", pady=(0, 10))
        gen_row.columnconfigure(0, weight=2)
        gen_row.columnconfigure(1, weight=1)
        gen_row.columnconfigure(2, weight=1)

        self.btn_generate = make_button(gen_row, "Сформировать дневники", self._generate, primary=True)
        self.btn_generate.grid(row=0, column=0, sticky="ew", padx=(0, 8), ipady=8)
        self.btn_generate.state(["disabled"])
        self.btn_copy_all = make_button(gen_row, "Копировать все дневники", self._copy_all)
        self.btn_copy_all.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        self.btn_copy_all.state(["disabled"])
        self.btn_save_all = make_button(gen_row, "Сохранить все в TXT", self._save_all)
        self.btn_save_all.grid(row=0, column=2, sticky="ew", padx=(8, 0))
        self.btn_save_all.state(["disabled"])

        # ---------------- Блок 3. Список + предпросмотр ----------------
        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=0, minsize=340)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        self.list_widget = tk.Listbox(
            body, bg=CARD, fg=FG, selectbackground=ACCENT, selectforeground="white",
            highlightbackground=BORDER, activestyle="none", relief="flat",
            font=("Segoe UI", 11), exportselection=False)
        self.list_widget.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.list_widget.bind("<<ListboxSelect>>", self._show_selected)

        preview_wrap = tk.Frame(body, bg=BG)
        preview_wrap.grid(row=0, column=1, sticky="nsew")
        preview_wrap.rowconfigure(1, weight=1)
        preview_wrap.columnconfigure(0, weight=1)

        self.lbl_status = tk.Label(preview_wrap, text="", bg=BG, fg=FG,
                                   anchor="w", font=("Segoe UI", 11, "bold"))
        self.lbl_status.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        self.preview = scrolledtext.ScrolledText(
            preview_wrap, bg=CARD, fg=FG, insertbackground=FG, relief="flat",
            wrap="word", state="disabled", font=("Consolas", 11))
        self.preview.grid(row=1, column=0, sticky="nsew")

        btn_row = tk.Frame(preview_wrap, bg=BG)
        btn_row.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.btn_copy = make_button(btn_row, "Копировать дневник", self._copy_current)
        self.btn_copy.pack(side="left", padx=(0, 8))
        self.btn_copy.state(["disabled"])
        self.btn_save = make_button(btn_row, "Сохранить в TXT", self._save_current)
        self.btn_save.pack(side="left", padx=(0, 8))
        self.btn_save.state(["disabled"])
        self.btn_warnings = make_button(btn_row, "Показать предупреждения", self._show_warnings)
        self.btn_warnings.pack(side="left")
        self.btn_warnings.state(["disabled"])

        # ---------------- Строчка состояния ----------------
        self.statusbar = tk.Label(root, text="", bg=BG, fg=MUTED, anchor="w",
                                  font=("Segoe UI", 10))
        self.statusbar.pack(fill="x", pady=(8, 0))

    # ------------------------------------------------------------------

    def _choose_map(self) -> None:
        filename = filedialog.askopenfilename(
            title="Выберите карту диализных процедур",
            filetypes=[("Текстовые файлы", "*.txt"), ("Все файлы", "*.*")])
        if filename:
            self.map_path = Path(filename)
            self.lbl_map.configure(text=f"Карта: {self.map_path.name}")
            self._update_generate_enabled()

    def _choose_template(self) -> None:
        filename = filedialog.askopenfilename(
            title="Выберите шаблон дневника",
            filetypes=[("Текстовые файлы", "*.txt"), ("Все файлы", "*.*")])
        if filename:
            self.template_path = Path(filename)
            self.lbl_template.configure(text=f"Шаблон: {self.template_path.name}")
            self._update_generate_enabled()

    def _update_generate_enabled(self) -> None:
        if self.map_path and self.template_path:
            self.btn_generate.state(["!disabled"])
        else:
            self.btn_generate.state(["disabled"])

    # ------------------------------------------------------------------
    def _generate(self) -> None:
        try:
            self.diaries = generate_diaries(self.map_path, self.template_path)
        except ServiceError as exc:
            messagebox.showerror("Ошибка формирования", str(exc))
            return
        self.list_widget.delete(0, "end")
        for d in self.diaries:
            date = d.session.date if d.session and d.session.date else "Без даты"
            self.list_widget.insert("end", f"{date} — Сеанс №{d.number}  [{d.status}]")
        counts = ", ".join(
            f"{s}: {sum(1 for x in self.diaries if x.status == s)}"
            for s in (STATUS_READY, STATUS_NEEDS_CHECK, STATUS_ERROR)
        )
        self.statusbar.configure(
            text=f"Сформировано дневников: {len(self.diaries)} ({counts})")
        self._recolor_list()
        for b in (self.btn_copy_all, self.btn_save_all):
            b.state(["!disabled"] if self.diaries else ["disabled"])
        if self.diaries:
            self.list_widget.selection_set(0)
            self._show_selected()

    def _recolor_list(self) -> None:
        """Цветовая маркировка статусов в списке (у selected-строк Qt-стиль перекрывает цвет)."""
        for i, d in enumerate(self.diaries):
            self.list_widget.itemconfig(i, foreground=_STATUS_TEXT.get(d.status, FG))

    # ------------------------------------------------------------------
    def _current_diary(self) -> Optional[Diary]:
        sel = self.list_widget.curselection()
        if sel and 0 <= sel[0] < len(self.diaries):
            return self.diaries[sel[0]]
        return None

    def _show_selected(self, event=None) -> None:
        d = self._current_diary()
        if not d:
            return
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", d.full_text)
        self.preview.configure(state="disabled")
        color = _STATUS_TEXT.get(d.status, FG)
        extra = f" • предупреждений: {len(d.warnings)}" if d.warnings else ""
        self.lbl_status.configure(text=f"Статус: {d.status}{extra}", fg=color)
        for b in (self.btn_copy, self.btn_save, self.btn_warnings):
            b.state(["!disabled"])

    # ------------------------------------------------------------------
    def _copy_to_clipboard(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()  # буфер закрепляется в буфере обмена Windows

    def _copy_current(self) -> None:
        d = self._current_diary()
        if not d:
            return
        if d.status == STATUS_ERROR:
            messagebox.showwarning(
                "Дневник со статусом «Ошибка»",
                "Этот дневник нельзя копировать без исправления данных.\n\n"
                "Откройте «Показать предупреждения», устраните проблемы и повторите формирование.")
            return
        if d.status == STATUS_NEEDS_CHECK:
            if not messagebox.askyesno(
                    "Требует проверки",
                    "У дневника есть предупреждения. Скопировать текст в буфер обмена?\n"
                    "Проверьте его перед вставкой в МИС."):
                return
        self._copy_to_clipboard(d.full_text)
        self.statusbar.configure(text=f"Дневник №{d.number} скопирован в буфер обмена.")

    def _copy_all(self) -> None:
        if not self.diaries:
            return
        error_count = sum(1 for d in self.diaries if d.status == STATUS_ERROR)
        if error_count:
            if not messagebox.askyesno(
                    "Есть дневники со статусом «Ошибка»",
                    f"В списке {error_count} дневник(ов) со статусом «Ошибка». "
                    "Они будут помечены в тексте. Копировать всё?"):
                return
        self._copy_to_clipboard(copy_all_text(self.diaries))
        self.statusbar.configure(text="Все дневники скопированы в буфер обмена.")

    def _save_current(self) -> None:
        d = self._current_diary()
        if not d:
            return
        folder = filedialog.askdirectory(title="Папка для сохранения дневника")
        if not folder:
            return
        target = save_diary_txt(d, folder)
        self.statusbar.configure(text=f"Сохранено: {target}")

    def _save_all(self) -> None:
        if not self.diaries:
            return
        folder = filedialog.askdirectory(title="Папка для сохранения всех дневников")
        if not folder:
            return
        paths = save_all_diaries(self.diaries, folder)
        self.statusbar.configure(text=f"Сохранено файлов: {len(paths)} в {folder}")

    def _show_warnings(self) -> None:
        d = self._current_diary()
        if not d:
            return
        WarningWindow(self.root, d)


def make_button(parent, text, command, primary: bool = False):
    """Крупная плоская кнопка в тёмной теме."""
    from tkinter import ttk
    style_name = "Primary.TButton" if primary else "Dark.TButton"
    btn = ttk.Button(parent, text=text, command=command, style=style_name)
    return btn


def ttk_style():
    from tkinter import ttk
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("Dark.TButton", background="#2d3238", foreground=FG,
                    bordercolor=BORDER, lightcolor="#2d3238", darkcolor="#2d3238",
                    padding=(14, 9), font=("Segoe UI", 11), relief="flat")
    style.map("Dark.TButton",
              background=[("active", "#363c44"), ("disabled", "#262a30")],
              foreground=[("disabled", "#6b7280")])
    style.configure("Primary.TButton", background=ACCENT, foreground="white",
                    bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT,
                    padding=(14, 12), font=("Segoe UI", 11, "bold"), relief="flat")
    style.map("Primary.TButton",
              background=[("active", "#3f7ef7"), ("disabled", "#262a30")],
              foreground=[("disabled", "#6b7280")])
    return style


def main() -> int:
    root = tk.Tk()
    try:
        root.icondefault()
    except Exception:
        pass
    MainWindow(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
