# -*- coding: utf-8 -*-
"""Сервисный слой: загрузка файлов, формирование и экспорт дневников.

GUI (app/main_window.py) и тесты вызывают только эти функции —
вся бизнес-логика отделена от интерфейса.
Данные обрабатываются ИСКЛЮЧИТЕЛЬНО локально, без сетевых запросов.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from app.diary_builder import build_diary
from app.map_parser import MapParseError, parse_dialysis_map
from app.models import Diary
from app.template_parser import parse_template
from app.textio import read_text_file
from app.validator import validate_diary


class ServiceError(Exception):
    """Понятная пользователю ошибка с указанием проблемного поля/файла."""


def load_map(path: str | Path) -> Tuple[Optional[dict], list]:
    try:
        text = read_text_file(path)
    except FileNotFoundError:
        raise ServiceError(f"Файл карты не найден: {path}")
    except UnicodeDecodeError as exc:
        raise ServiceError(f"Не удалось прочитать файл карты ({exc.reason}). "
                           "Сохраните файл в UTF-8 или Windows-1251.")
    try:
        return parse_dialysis_map(text)
    except MapParseError as exc:
        raise ServiceError(str(exc))


def load_template(path: str | Path):
    try:
        text = read_text_file(path)
    except FileNotFoundError:
        raise ServiceError(f"Файл шаблона не найден: {path}")
    except UnicodeDecodeError as exc:
        raise ServiceError(f"Не удалось прочитать файл шаблона ({exc.reason}). "
                           "Сохраните файл в UTF-8 или Windows-1251.")
    return parse_template(text)


def generate_diaries(map_path: str | Path, template_path: str | Path) -> List[Diary]:
    """Полный цикл: прочитать карту и шаблон, собрать и проверить дневники."""
    _header, sessions = load_map(map_path)
    template = load_template(template_path)
    diaries: List[Diary] = []
    for i, session in enumerate(sessions, start=1):
        diary = build_diary(i, session, template)
        diary = validate_diary(diary, template.sections)
        diaries.append(diary)
    return diaries


ALL_SEPARATOR = "\n\n========================================\n\n"


def copy_all_text(diaries: List[Diary]) -> str:
    """Текст всех дневников с разделителями для кнопки «Копировать все дневники»."""
    chunks = []
    for d in diaries:
        status_note = ""
        if d.status != "Готов":
            status_note = f"\n[Статус: {d.status}]"
        chunks.append(d.full_text + status_note)
    return ALL_SEPARATOR.join(chunks)


def save_diary_txt(diary: Diary, folder: str | Path, filename: Optional[str] = None) -> Path:
    """Сохранить один дневник в TXT (UTF-8). Исходные файлы не изменяются."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (filename or diary.suggested_filename)
    target.write_text(diary.full_text + "\n", encoding="utf-8")
    return target


def save_all_diaries(diaries: List[Diary], folder: str | Path) -> List[Path]:
    """Сохранить все дневники в отдельные TXT-файлы."""
    return [save_diary_txt(d, folder) for d in diaries]
