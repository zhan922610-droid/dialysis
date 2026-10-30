# -*- coding: utf-8 -*-
"""Чтение текстовых файлов с автоматическим определением кодировки.

Поддерживаются UTF-8 (в т.ч. с BOM) и Windows-1251.
Исходные файлы никогда не изменяются программой.
"""
from __future__ import annotations

from pathlib import Path

_ENCODINGS = ("utf-8-sig", "utf-8", "cp1251")


def read_text_file(path: str | Path) -> str:
    """Прочитать текстовый файл, вернув его содержимое как str.

    Порядок попыток: UTF-8 c BOM -> UTF-8 -> Windows-1251.
    """
    raw = Path(path).read_bytes()
    last_err: Exception | None = None
    for enc in _ENCODINGS:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError as exc:  # pragma: no cover - зависит от файла
            last_err = exc
    raise UnicodeDecodeError(
        getattr(last_err, "encoding", "unknown"),
        getattr(last_err, "object", raw),
        getattr(last_err, "start", 0),
        getattr(last_err, "end", len(raw)),
        "Не удалось определить кодировку файла (UTF-8 / UTF-8 BOM / Windows-1251)",
    )
