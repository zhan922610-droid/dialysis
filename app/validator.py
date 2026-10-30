# -*- coding: utf-8 -*-
"""Механизм проверки достоверности дневников (регламент п. 6).

Проверяются: наличие обязательных данных, сохранение текста шаблона,
отсутствие запрещённых формулировок («введён», «введено», «дан» вместо
«назначен»), отсутствие пустых строк между разделами, расхождение веса
и объёма ультрафильтрации. Программа ничего не исправляет — только
предупреждает.
"""
from __future__ import annotations

import re
from typing import List

from app.diary_builder import EMPTY_THERAPY_PHRASE, NO_COMPLICATIONS_PHRASE
from app.models import STATUS_ERROR, STATUS_NEEDS_CHECK, Diary, Warning

FORBIDDEN_PHRASES = ("введён", "введена", "введено", "был дан", "была дана", "было дано")

REQUIRED_TEMPLATE_MARKERS = {
    "complaints": "Жалобы",
    "objective": "Объективно",
    "connection": "Способ подключения",
    "dialysis_course": "Течение диализа",
    "replacement_therapy": "Заместительная терапия",
    "weights": "Веса",
}


def validate_diary(diary: Diary, template_sections: dict) -> Diary:
    """Дополнить дневник результатами финальной проверки и скорректировать статус."""
    warnings: List[Warning] = []
    date = diary.session.date if diary.session else None
    text = diary.full_text
    body_text = "\n".join(diary.body_lines)

    # 1. Обязательные данные сеанса
    s = diary.session
    if s is not None:
        checks = [
            ("Дата процедуры", s.date, "дата"),
            ("Время начала", s.start_time, "время начала"),
            ("АД перед ГД", s.blood_pressure_before, "АД перед началом гемодиализа"),
            ("Все три веса", None, None),
        ]
        for name, value, msg in checks:
            if value is None and msg:
                if not any(w.field_name == name for w in diary.warnings):
                    warnings.append(Warning(name, f"В дневнике нет данных: {msg}.", date))
        if len(s.blood_pressure_mid) < 3:
            if not any("промежуточн" in w.message.lower() for w in diary.warnings):
                warnings.append(Warning("АД в динамике",
                                        "Промежуточные измерения АД неполные.", date))
        if s.heart_rate is None and re.search(r"(?i)(чсс|пульс)", body_text):
            if not any(w.field_name == "ЧСС" for w in diary.warnings):
                warnings.append(Warning("ЧСС",
                                        "ЧСС требуется для объективного статуса, но измеренное значение отсутствует.",
                                        date))
        if s.connection_method is None:
            pass  # способ подключения берётся из шаблона — это допустимо
        if not s.constant_medications:
            # явная проверка: если поле пустое, используется установленная формулировка
            if EMPTY_THERAPY_PHRASE not in body_text:
                warnings.append(Warning("Заместительная терапия",
                                        "Поле постоянных препаратов пустое, но установленная формулировка "
                                        "не использована — проверьте шаблон.", date))

    # 2. Запрещённые формулировки
    low = text.lower()
    found_forbidden = [p for p in FORBIDDEN_PHRASES if p in low]
    if found_forbidden:
        warnings.append(Warning("Формулировки",
                                "Обнаружены запрещённые формулировки: " + ", ".join(found_forbidden) +
                                ". По регламенту используется слово «назначен».", date))

    # 3. Сохранение неизменяемого текста шаблона
    for key, marker in REQUIRED_TEMPLATE_MARKERS.items():
        if key in template_sections:
            if marker.lower() not in low:
                warnings.append(Warning("Шаблон",
                                        f"В дневнике отсутствует раздел «{marker}» из шаблона.", date))
    complaints_tpl = template_sections.get("complaints", "")
    if complaints_tpl:
        first_line = complaints_tpl.split("\n")[0].strip()
        if first_line and first_line not in text:
            warnings.append(Warning("Шаблон",
                                    "Текст жалоб отличается от шаблона — дословность нарушена.", date))

    # 4. Пустые строки между разделами
    if "\n\n" in text:
        warnings.append(Warning("Формат", "Между абзацами есть пустые строки (нарушение формата).", date))

    # 5. Дата/время перед текстом
    if not diary.header_line or diary.header_line == "Дата не указана":
        warnings.append(Warning("Дата", "Перед дневником отсутствует дата начала процедуры.", date))

    # 6. УФО vs изменение веса
    if s and s.weight_before is not None and s.weight_after is not None and s.ultrafiltration_volume is not None:
        delta = round(s.weight_before - s.weight_after, 2)
        if abs(delta - s.ultrafiltration_volume) > 0.5:
            if not any("Ультрафильтрация" == w.field_name for w in diary.warnings):
                warnings.append(Warning("Ультрафильтрация",
                                        f"Изменение веса ({delta} кг) не совпадает с указанным объёмом УФО "
                                        f"({s.ultrafiltration_volume} л). Исправление не выполняется.", date))

    if warnings:
        diary.warnings.extend(warnings)
    if diary.warnings:
        if diary.status == STATUS_ERROR:
            pass
        else:
            diary.status = STATUS_NEEDS_CHECK
    return diary
