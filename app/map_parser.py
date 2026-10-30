# -*- coding: utf-8 -*-
"""Парсер карты диализных процедур.

Формат карты (пример — examples/Карта_диализа.txt):

    Пациент: Иванов Иван Иванович, 1955
    Диагноз: ХБП 5 ст., на программном гемодиализе с 2024 г.

    --- Сеанс 1 ---
    Дата: 01.10.2026
    Время начала: 08:00
    Время окончания: 12:00
    Длительность: 4 ч
    АД перед ГД: 140/85 мм рт.ст.
    ЧСС: 78 уд/мин
    АД в динамике: 135/80, 128/75, 120/70
    АД после ГД: 118/70
    Сухой вес: 80 кг
    Вес до ГД: 82,4 кг
    Вес после ГД: 79,8 кг
    Объём УФО: 2,6 л
    Осложнения: нет
    Назначения интрадиализно: нет
    Постоянная терапия: Эпрекс 4000 МЕ п/к в/в в конце сеанса

Парсер устойчив к небольшим изменениям расположения строк: поля собираются
по ключевым словам внутри блока сеанса. Значения, которые нельзя однозначно
отнести к сеансу или полю, НЕ переносятся наугад — вместо этого формируются
предупреждения (см. app.validator).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from app.models import SessionData, parse_blood_pressure, parse_weight_kg

# Заголовок сеанса: «--- Сеанс 1 ---», «Сеанс 1», «[Сеанс №1]» и т.п.
_SESSION_HEADER_RE = re.compile(
    r"^\s*[-=*#\[\]]*\s*сеанс\s*(?:№|no\.?)?\s*(\d{1,2})\b",
    re.IGNORECASE,
)

_DATE_RE = re.compile(r"(\d{1,2}\.\d{1,2}\.\d{2,4})")
_TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")

# Ключевые слова полей. Первое совпадение в строке решает принадлежность значения.
_FIELD_PATTERNS: List[Tuple[str, str]] = [
    ("date", r"^\s*дата\b"),
    ("start_time", r"время\s+начал"),
    ("end_time", r"время\s+оконч"),
    ("duration", r"длительност"),
    ("bp_before", r"ад\s+перед\s+гд|^ад\s*до\s*гд"),
    ("heart_rate", r"^чсс|пульс"),
    ("bp_mid", r"ад\s+(в\s+)?(динамике|интрадиализно)|промежуточн"),
    ("bp_after", r"ад\s+после\s+гд|ад\s+по\s+окончании"),
    ("dry_weight", r"сухой\s+вес"),
    ("weight_before", r"вес\s+до\s+гд"),
    ("weight_after", r"вес\s+после\s+гд"),
    ("uf_volume", r"объ[её]м\s*(увф|уф|ультрафильтрации)|^увф|ультрафильтрац"),
    ("connection", r"способ\s+подключен|подключен|авф|катетер"),
    ("complications", r"осложнен|нежелательн|во\s+время\s+гд|в\s+ходе\s+гд"),
    ("intradialytic_meds", r"назначени\w*\s+интрадиализно|интрадиализн\w*\s+назначен|препараты\s+в\s+ходе"),
    ("constant_meds", r"постоянн\w+\s+терап|постоянн\w+\s+медикамент|заместительн\w+\s+терап"),
    ("notes", r"^примечан|^заметк|^коммент"),
]

_SPLIT_VALUES_RE = re.compile(r"[;,]|\n")


def _strip_field_name(line: str) -> str:
    """Убрать имя поля до первого двоеточия («АД перед ГД: 140/85» -> «140/85»)."""
    if ":" in line:
        return line.split(":", 1)[1].strip()
    return line.strip()


def _detect_field(line: str) -> Optional[str]:
    for name, pattern in _FIELD_PATTERNS:
        if re.search(pattern, line, re.IGNORECASE):
            return name
    return None


def _parse_duration(text: str) -> Optional[float]:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:ч|час|h)", text, re.IGNORECASE)
    if m:
        return float(m.group(1).replace(",", "."))
    return None


def _split_medication_list(text: str) -> List[str]:
    """Разбить перечень препаратов на элементы («нет» -> пустой список)."""
    cleaned = text.strip().rstrip(".")
    if not cleaned or cleaned.lower() in {"нет", "не было", "нет.", "—", "-", "-"}:
        return []
    parts = [p.strip(" .;") for p in _SPLIT_VALUES_RE.split(cleaned)]
    return [p for p in parts if p and p.lower() != "нет"]


class MapParseError(Exception):
    """Критическая ошибка разбора карты: сеансы не найдены."""


def parse_dialysis_map(text: str) -> Tuple[Optional[Dict[str, str]], List[SessionData]]:
    """Разобрать карту процедур.

    Возвращает (шапка карты с данными пациента, список сеансов).
    Блоки сеансов разделяются заголовками вида «--- Сеанс N ---».
    Если заголовков нет, но есть даты — блоки разделяются по строкам «Дата: ...».
    """
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]

    # Разбиваем на блоки -----------------------------------------------------
    blocks: List[List[str]] = []
    current: List[str] = []
    header_info: Dict[str, str] = {}
    seen_session = False
    pending_date_block = False

    def _flush() -> None:
        nonlocal current
        if any(ln.strip() for ln in current):
            blocks.append(current)
        current = []

    for ln in lines:
        m = _SESSION_HEADER_RE.match(ln)
        is_date_start = bool(re.match(r"^\s*дата\b", ln, re.IGNORECASE)) and bool(_DATE_RE.search(ln))
        if m:
            if seen_session or pending_date_block:
                _flush()
            elif current:
                # всё, что до первого сеанса, — шапка карты
                for h in current:
                    if ":" in h:
                        k, v = h.split(":", 1)
                        header_info[k.strip().lower()] = v.strip()
                current = []
            seen_session = True
            continue
        if not seen_session and is_date_start and (pending_date_block or any(current)):
            # Формат без заголовков сеансов: новый блок начинается со строки «Дата:»
            if pending_date_block:
                _flush()
            pending_date_block = True
        current.append(ln)
    _flush()

    if not blocks:
        raise MapParseError("В карте не найдено ни одного сеанса гемодиализа.")

    sessions: List[SessionData] = []
    for block in blocks:
        session = _parse_block(block)
        if session.date or session.start_time or session.blood_pressure_before:
            sessions.append(session)

    if not sessions:
        raise MapParseError("Не удалось извлечь данные сеансов из карты.")

    sessions.sort(key=lambda s: _sort_key(s.date))
    return header_info, sessions


def _sort_key(date: Optional[str]) -> Tuple[int, int, int]:
    if not date:
        return (9999, 12, 31)
    m = _DATE_RE.match(date) or _DATE_RE.search(date)
    if not m:
        return (9999, 12, 31)
    d, mo, y = m.group(1).split(".")
    y = int(y)
    if y < 100:
        y += 2000
    return (y, int(mo), int(d))


def _parse_block(block: List[str]) -> SessionData:
    s = SessionData()
    raw_bp_mid_parts: List[str] = []
    for ln in block:
        if not ln.strip():
            continue
        field = _detect_field(ln)
        value = _strip_field_name(ln)
        if field == "date":
            m = _DATE_RE.search(value)
            if m:
                s.date = m.group(1)
            else:
                tm = _TIME_RE.search(value)
                s.date = value if value else None
                if tm and not s.start_time:
                    s.start_time = f"{int(tm.group(1)):02d}:{tm.group(2)}"
        elif field == "start_time":
            tm = _TIME_RE.search(value)
            if tm:
                s.start_time = f"{int(tm.group(1)):02d}:{tm.group(2)}"
        elif field == "end_time":
            tm = _TIME_RE.search(value)
            if tm:
                s.end_time = f"{int(tm.group(1)):02d}:{tm.group(2)}"
        elif field == "duration":
            s.duration_hours = _parse_duration(value)
        elif field == "bp_before":
            s.blood_pressure_before = parse_blood_pressure(value)
        elif field == "heart_rate":
            m = re.search(r"\b(\d{2,3})\b", value)
            if m:
                s.heart_rate = int(m.group(1))
        elif field == "bp_mid":
            raw_bp_mid_parts.append(value)
        elif field == "bp_after":
            s.blood_pressure_after = parse_blood_pressure(value)
        elif field == "dry_weight":
            s.dry_weight = parse_weight_kg(value)
        elif field == "weight_before":
            s.weight_before = parse_weight_kg(value)
        elif field == "weight_after":
            s.weight_after = parse_weight_kg(value)
        elif field == "uf_volume":
            v = parse_weight_kg(value)  # тот же разбор числа с запятой
            s.ultrafiltration_volume = v
        elif field == "connection":
            s.connection_method = value or None
        elif field == "complications":
            s.complications = _split_medication_list(value)
        elif field == "intradialytic_meds":
            s.intradialytic_medications = _split_medication_list(value)
        elif field == "constant_meds":
            s.constant_medications = _split_medication_list(value)
        elif field == "notes":
            s.notes = (s.notes + " " + value).strip()
        else:
            s.notes = (s.notes + " " + ln.strip()).strip()

    # Промежуточные АД: собираем все пары «число/число» из соответствующих строк.
    for part in raw_bp_mid_parts:
        for bp in re.findall(r"\d{2,3}\s*[–\-/]\s*\d{2,3}", part):
            norm = parse_blood_pressure(bp)
            if norm:
                s.blood_pressure_mid.append(norm)
    return s
