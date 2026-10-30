# -*- coding: utf-8 -*-
"""Модели данных AI Dialysis Diary.

Все структуры хранят только сведения, фактически присутствующие в карте
диализных процедур или шаблоне дневника. Программа ничего не придумывает.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

# ---------------------------------------------------------------------------
# Утилиты разбора значений
# ---------------------------------------------------------------------------

_BLOOD_PRESSURE_RE = re.compile(r"(\d{2,3})\s*[–\-/]\s*(\d{2,3})")


def parse_blood_pressure(text: Optional[str]) -> Optional[str]:
    """Извлечь артериальное давление вида «140/80» из произвольной строки.

    Возвращает нормализованную строку «140/80» либо None.
    """
    if not text:
        return None
    m = _BLOOD_PRESSURE_RE.search(text)
    if not m:
        return None
    return f"{m.group(1)}/{m.group(2)}"


_WEIGHT_KG_RE = re.compile(r"(\d{1,3}(?:[.,]\d{1,2})?)")


def parse_weight_kg(text: Optional[str]) -> Optional[float]:
    """Извлечь вес в кг из строки («82,40 кг» -> 82.4). Возвращает None, если числа нет."""
    if not text:
        return None
    m = _WEIGHT_KG_RE.search(text.replace("\u00a0", " "))
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:  # pragma: no cover
        return None


def format_weight(value: Optional[float]) -> str:
    """Формат веса: «80,00 кг». Пустая строка, если значения нет."""
    if value is None:
        return ""
    return f"{value:.2f}".replace(".", ",") + " кг"


# ---------------------------------------------------------------------------
# Модель сеанса гемодиализа (данные из карты)
# ---------------------------------------------------------------------------


@dataclass
class SessionData:
    """Один сеанс гемодиализа, извлечённый из карты диализных процедур."""

    date: Optional[str] = None          # «03.10.2026»
    start_time: Optional[str] = None    # «12:00»
    end_time: Optional[str] = None      # «16:00» — используется только для проверки объёма
    duration_hours: Optional[float] = None
    blood_pressure_before: Optional[str] = None   # АД перед ГД, «140/80»
    blood_pressure_mid: List[str] = field(default_factory=list)  # промежуточные измерения
    blood_pressure_after: Optional[str] = None    # АД после ГД (в последовательность НЕ входит)
    heart_rate: Optional[int] = None              # фактическая ЧСС; None — если не измерена
    dry_weight: Optional[float] = None            # сухой вес, кг
    weight_before: Optional[float] = None         # вес до ГД, кг
    weight_after: Optional[float] = None          # вес после ГД, кг
    ultrafiltration_volume: Optional[float] = None  # указанный объём ультрафильтрации, л
    connection_method: Optional[str] = None       # способ подключения (если задан в карте)
    complications: List[str] = field(default_factory=list)  # документированные осложнения
    intradialytic_medications: List[str] = field(default_factory=list)  # назначения во время ГД
    constant_medications: List[str] = field(default_factory=list)       # постоянная терапия
    notes: str = ""                               # прочие заметки по сеансу


# ---------------------------------------------------------------------------
# Статусы и предупреждения сформированного дневника
# ---------------------------------------------------------------------------

STATUS_READY = "Готов"
STATUS_NEEDS_CHECK = "Требует проверки"
STATUS_ERROR = "Ошибка"


@dataclass
class Warning:
    """Предупреждение регламента: поле, сообщение, дата процедуры."""

    field_name: str
    message: str
    session_date: Optional[str] = None

    def as_text(self) -> str:
        prefix = f"[{self.session_date}] " if self.session_date else ""
        return f"{prefix}{self.field_name}: {self.message}"


@dataclass
class Diary:
    """Сформированный дневник гемодиализа."""

    number: int                       # порядковый номер сеанса (1-based)
    header_line: str                  # «03.10.2026 12:00»
    body_lines: List[str]             # строки разделов без пустых строк
    status: str                       # STATUS_READY / STATUS_NEEDS_CHECK / STATUS_ERROR
    warnings: List[Warning] = field(default_factory=list)
    session: Optional[SessionData] = None

    @property
    def full_text(self) -> str:
        """Полный текст дневника: дата/время + разделы, без пустых строк."""
        return "\n".join([self.header_line] + self.body_lines)

    @property
    def suggestions(self) -> List[str]:
        """Подсказки для врача на основе предупреждений (без автоисправлений)."""
        result: List[str] = []
        for w in self.warnings:
            msg = w.message
            low = msg.lower()
            if "чсс" in low and ("отсутств" in low or "нет" in low):
                result.append("Проверить объективный статус: убрать ЧСС или указать документированное значение.")
            elif "ад" in low and ("промежуточн" in low or "отсутству" in low):
                result.append("Проверить раздел «Течение диализа»: уточнить недостающие измерения АД.")
            elif "интрадиализн" in low:
                result.append("Уточнить документированную причину назначения и результат лечения.")
            elif "ультрафильтрац" in low:
                result.append("Сверить объём ультрафильтрации с изменением веса.")
            elif "вес" in low:
                result.append("Сверить весовые значения с картой.")
            elif "шаблон" in low:
                result.append("Исправить шаблон дневника и повторить формирование.")
            else:
                result.append("Проверить данные вручную перед копированием в МИС.")
        return result

    def warnings_text(self) -> str:
        """Текст окна «Показать предупреждения»."""
        parts: List[str] = []
        if not self.warnings:
            parts.append("Предупреждений нет. Все обязательные данные присутствуют.")
        else:
            parts.append("Предупреждения:")
            parts.extend(f"— {w.as_text()}" for w in self.warnings)
            sug = self.suggestions
            if sug:
                parts.append("")
                parts.append("Рекомендации:")
                parts.extend(f"* {s}" for s in dict.fromkeys(sug))
        return "\n".join(parts)

    @property
    def suggested_filename(self) -> str:
        """Имя файла вида «03.10.2026_Сеанс_2.txt»."""
        date_part = (self.session.date if self.session and self.session.date else "")
        if not date_part:
            date_part = "Без_даты"
        safe = re.sub(r"[^\d.]", "_", date_part)
        return f"{safe}_Сеанс_{self.number}.txt"
