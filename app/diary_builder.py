# -*- coding: utf-8 -*-
"""Сборка дневника из шаблона и данных сеанса (регламент п. 5).

Порядок разделов: Жалобы, Объективно, Способ подключения, Течение диализа,
Заместительная терапия, Веса. Между абзацами нет пустых строк.
Дата и время начала диализа — перед текстом дневника.

Разрешённые изменения шаблона:
- АД в объективном статусе -> АД перед ГД из карты;
- ЧСС в объективном статусе -> только фактически измеренное значение;
- заполнение разделов «Течение диализа», «Заместительная терапия», «Веса»
  данными из карты без изменения постоянных формулировок.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from app.medications import analyze_assignment, format_assignment
from app.models import (
    STATUS_ERROR,
    STATUS_NEEDS_CHECK,
    STATUS_READY,
    Diary,
    SessionData,
    Warning,
    format_weight,
)
from app.template_parser import Template

NO_COMPLICATIONS_PHRASE = "Сеанс гемодиализа перенесён удовлетворительно, без дополнительных назначений."
EMPTY_THERAPY_PHRASE = "Заместительная терапия: (нет дополнительных медикаментов)"

# Плейсхолдеры вида {АД}, {ЧСС}, {АД_ТЕЧЕНИЕ}, {ТЕЧЕНИЕ_ДИАЛИЗА}, {САХАР}…
_PLACEHOLDER_RE = re.compile(r"\{([A-Za-zА-Яа-яЁё0-9_]+)\}")

# Известные (разрешённые регламентом) плейсхолдеры шаблона
KNOWN_PLACEHOLDERS = {
    "ТЕЧЕНИЕ_ДИАЛИЗА", "ЗАМЕСТИТЕЛЬНАЯ_ТЕРАПИЯ", "СУХОЙ_ВЕС", "ВЕС_ДО_ГД",
    "ВЕС_ПОСЛЕ_ГД", "СПОСОБ_ПОДКЛЮЧЕНИЯ", "ВРЕМЯ_ДИАЛИЗА", "ДЛИТЕЛЬНОСТЬ",
    "АД", "ЧСС",
}

_BLOOD_PRESSURE_RE = re.compile(r"(?<![\d/])(\d{2,3})\s*/\s*(\d{2,3})(?![\d/])")
_HEART_RATE_RE = re.compile(r"(?:чсс|пульс)[^\d\n]{0,25}?(\d{2,3})", re.IGNORECASE)


def _fill_placeholders(text: str, values: dict) -> Tuple[str, List[str]]:
    """Заменить {КЛЮЧ} на значения; вернуть текст и список неизвестных ключей."""
    unknown: List[str] = []

    def repl(m: re.Match) -> str:
        key = m.group(1)
        if key in values and values[key] is not None:
            return str(values[key])
        unknown.append(key)
        return m.group(0)

    return _PLACEHOLDER_RE.sub(repl, text), unknown


def _replace_ad_in_objective(text: str, bp_before: Optional[str]) -> Tuple[str, bool]:
    """Заменить первое АД объективного статуса на АД перед ГД из карты."""
    if not bp_before:
        return text, False
    new, n = _BLOOD_PRESSURE_RE.subn(bp_before, text, count=1)
    if n:
        return new, True
    # если явного «число/число» нет, пробуем плейсхолдер уже выполнен выше
    return text, False


def _replace_hr_in_objective(text: str, hr: Optional[int]) -> Tuple[str, bool, bool]:
    """Заменить ЧСС в тексте на измеренное значение.

    Возвращает (текст, заменено, требует_предупреждения).
    Если ЧСС в тексте есть, а измеренного значения нет — значение НЕ подставляется,
    остаётся шаблонное, выводится предупреждение (не придумываем!).
    """
    m = _HEART_RATE_RE.search(text)
    if not m:
        return text, False, False
    if hr is None:
        return text, False, True
    old = m.group(0)
    span = m.span(1)
    new = text[: span[0]] + str(hr) + text[span[1]:]
    changed = new != text
    return new, changed, False


def _course_line(template_section: Optional[str], session: SessionData,
                 warnings: List[Warning], date: Optional[str]) -> str:
    """Сформировать раздел «Течение диализа»."""
    parts: List[str] = []

    # --- последовательность АД: до ГД + ровно 3 промежуточных ---
    seq: List[str] = []
    if session.blood_pressure_before:
        seq.append(session.blood_pressure_before)
    else:
        warnings.append(Warning("АД перед ГД", "В карте отсутствует АД перед началом гемодиализа.", date))
    mid = list(session.blood_pressure_mid)
    # если промежуточных ровно 4 — четвёртое НЕ входит в последовательность (регламент п. 5.5),
    # но остаётся задокументированным дополнительным измерением
    extra_mid = mid[3:]
    mid = mid[:3]
    if len(mid) < 3:
        warnings.append(
            Warning("АД в динамике",
                    f"Задокументировано {len(mid)} промежуточных измерений АД вместо трёх. "
                    "Недостающие значения не подставляются.",
                    date))
    seq.extend(mid)
    ad_line = "АД " + " – ".join(seq) + " мм.рт.ст." if seq else ""

    # --- осложнения и события ---
    complications = [c.strip() for c in session.complications if c.strip()]
    assignments = []
    for drug in session.intradialytic_medications:
        a = analyze_assignment(drug, session.complications, session.notes, session.notes)
        assignments.append(a)
        if not a.documented:
            for p in a.problems:
                warnings.append(Warning("Интрадиализное назначение", p, date))

    events: List[str] = []
    if complications:
        events.append("Во время гемодиализа зафиксировано: " + "; ".join(complications) + ".")
    for a in assignments:
        events.append(format_assignment(a))
    if extra_mid:
        events.append(
            "Дополнительные измерения АД во время сеанса: " + ", ".join(extra_mid) + "."
        )
    if session.blood_pressure_after:
        events.append(f"АД после окончания диализа: {session.blood_pressure_after} мм.рт.ст.")

    no_events = not complications and not assignments and not extra_mid \
        and not session.notes  # АД после ГД не считается событием (в последовательность не входит)
    if no_events:
        # нет осложнений и назначений -> установленная формулировка один раз вместе с АД-строкой
        if ad_line:
            parts.append(ad_line + " " + NO_COMPLICATIONS_PHRASE)
        else:
            parts.append(NO_COMPLICATIONS_PHRASE)
    else:
        if ad_line:
            parts.append(ad_line)
        parts.extend(events)

    # дословный текст раздела из шаблона (постоянные формулировки), кроме плейсхолдеров
    if template_section:
        static, unknown = _fill_placeholders(template_section, {})
        for key in unknown:
            if key not in KNOWN_PLACEHOLDERS:
                warnings.append(Warning("Шаблон",
                                        f"В шаблоне есть неразрешённый плейсхолдер {{{key}}} — проверьте шаблон.",
                                        date))
        static = static.replace("{ТЕЧЕНИЕ_ДИАЛИЗА}", "").strip()
        # Если раздел шаблона содержит постоянные формулировки до маркера —
        # переносим их дословно перед сформированными строками.
        marker_idx = template_section.find("{ТЕЧЕНИЕ_ДИАЛИЗА}")
        if marker_idx != -1:
            prefix = template_section[:marker_idx].strip()
            if prefix:
                parts.insert(0, prefix)
        else:
            generated_prefixes = ("АД ", "Во время гемодиализа", "Интрадиализно",
                                  "Дополнительные измерения", "АД после")
            if static and not any(static.startswith(p) for p in generated_prefixes):
                parts.insert(0, static)
    return "\n".join(p for p in parts if p)


def _therapy_line(template_section: Optional[str], session: SessionData,
                  warnings: List[Warning], date: Optional[str]) -> str:
    meds = [m.strip() for m in session.constant_medications if m.strip()]
    # интрадиализные препараты сюда не попадают по регламенту
    if meds:
        line = "Заместительная терапия: " + "; ".join(meds) + "."
    else:
        line = EMPTY_THERAPY_PHRASE + "."
    if template_section:
        static, unknown = _fill_placeholders(template_section, {"ЗАМЕСТИТЕЛЬНАЯ_ТЕРАПИЯ": line})
        for key in unknown:
            if key not in KNOWN_PLACEHOLDERS:
                warnings.append(Warning("Шаблон",
                                        f"В шаблоне есть неразрешённый плейсхолдер {{{key}}} — проверьте шаблон.",
                                        date))
        if "{ЗАМЕСТИТЕЛЬНАЯ_ТЕРАПИЯ}" in template_section:
            # в шаблоне задан только маркер подстановки -> используем сформированную строку,
            # постоянные формулировки шаблона сохраняются дословно
            rest = static.replace("{ЗАМЕСТИТЕЛЬНАЯ_ТЕРАПИЯ}", "").strip().strip(":").strip()
            if rest and not rest.startswith("Заместительная терапия"):
                return (rest + "\n" + line).strip()
            return line
        if static.strip():
            return static.strip()
    return line


def _weights_lines(template_section: Optional[str], session: SessionData,
                   warnings: List[Warning], date: Optional[str]) -> str:
    missing = []
    if session.dry_weight is None:
        missing.append("сухой вес")
    if session.weight_before is None:
        missing.append("вес до ГД")
    if session.weight_after is None:
        missing.append("вес после ГД")
    if missing:
        warnings.append(Warning("Веса",
                                "В карте отсутствуют: " + ", ".join(missing) + ". Значения не подставляются.",
                                date))

    def w(v: Optional[float]) -> str:
        return format_weight(v) if v is not None else "— (нет в карте)"

    lines = [
        f"Сухой вес: {w(session.dry_weight)}.",
        f"Вес до ГД: {w(session.weight_before)}.",
        f"Вес после ГД: {w(session.weight_after)}.",
    ]
    # проверки расхождений
    if session.weight_before is not None and session.weight_after is not None:
        delta = round(session.weight_before - session.weight_after, 2)
        if session.ultrafiltration_volume is not None:
            if abs(delta - session.ultrafiltration_volume) > 0.5:
                warnings.append(Warning(
                    "Ультрафильтрация",
                    f"Расхождение: изменение веса {format_weight(delta)}, "
                    f"указанный объём УФО {format_weight(session.ultrafiltration_volume)}. "
                    "Автоматическое исправление не выполняется.",
                    date))
        if delta < 0:
            warnings.append(Warning("Веса",
                                    "Вес после ГД больше веса до ГД — проверьте данные карты.", date))
    if session.dry_weight is not None and session.weight_after is not None:
        if abs(session.weight_after - session.dry_weight) > 3:
            warnings.append(Warning(
                "Веса",
                f"Вес после ГД ({format_weight(session.weight_after)}) существенно отличается от сухого веса "
                f"({format_weight(session.dry_weight)}). Расхождения не исправляются автоматически.",
                date))
    if template_section:
        repl = {
            "СУХОЙ_ВЕС": w(session.dry_weight),
            "ВЕС_ДО_ГД": w(session.weight_before),
            "ВЕС_ПОСЛЕ_ГД": w(session.weight_after),
        }
        static, unknown = _fill_placeholders(template_section, repl)
        for key in unknown:
            if key not in KNOWN_PLACEHOLDERS:
                warnings.append(Warning("Шаблон",
                                        f"В шаблоне есть неразрешённый плейсхолдер {{{key}}} — проверьте шаблон.",
                                        date))
        # если в разделе остались неразрешённые маркеры из «Времени диализа» и т.п. —
        # не переносим их в дневник, а предупреждаем выше; пустые строки убираются
        cleaned_lines = [ln for ln in static.split("\n") if ln.strip() and "{" not in ln]
        if any(k in template_section for k in repl):
            return "\n".join(cleaned_lines).strip()
        if cleaned_lines and "Веса" in template_section:
            return "\n".join(cleaned_lines).strip()
    return "\n".join(lines)


def build_diary(number: int, session: SessionData, template: Template) -> Diary:
    """Сформировать один дневник по регламенту. Статусы: Готов / Требует проверки / Ошибка."""
    date = session.date
    warnings: List[Warning] = []

    # --- критические проблемы шаблона ---
    missing_sections = template.missing_required()
    if missing_sections:
        names = {"complaints": "Жалобы", "objective": "Объективно", "connection": "Способ подключения",
                 "dialysis_course": "Течение диализа", "replacement_therapy": "Заместительная терапия",
                 "weights": "Веса"}
        friendly = ", ".join(names.get(s, s) for s in missing_sections)
        warnings.append(Warning("Шаблон",
                                f"В шаблоне отсутствуют обязательные разделы: {friendly}. "
                                "Исправьте шаблон.", date))

    # --- дата и время ---
    header_line = ""
    if date and session.start_time:
        header_line = f"{date} {session.start_time}"
    elif date:
        header_line = date
        warnings.append(Warning("Время начала", "В карте нет времени начала процедуры. "
                               "Время окончания вместо начала не используется.", date))
    else:
        header_line = "Дата не указана"
        warnings.append(Warning("Дата", "В карте отсутствует дата процедуры.", date))

    body: List[str] = []

    # 1. Жалобы — дословно
    complaints = template.get("complaints")
    if complaints:
        body.append(complaints)

    # 2. Объективно — дословно, разрешено менять только АД и ЧСС
    objective = template.get("objective")
    if objective:
        obj, ad_changed = _replace_ad_in_objective(objective, session.blood_pressure_before)
        if not ad_changed:
            if not session.blood_pressure_before:
                warnings.append(Warning("АД перед ГД",
                                        "Нет АД перед началом ГД из карты — в объективном статусе оставлено "
                                        "значение шаблона (проверьте!).", date))
            else:
                warnings.append(Warning("АД",
                                        "В шаблоне не найдено поле АД для замены — проверьте структуру шаблона.",
                                        date))
        obj, hr_changed, hr_warn = _replace_hr_in_objective(obj, session.heart_rate)
        if hr_warn:
            warnings.append(Warning("ЧСС",
                                    "Фактически измеренная ЧСС в карте отсутствует. Значение не придумывается, "
                                    "в тексте осталось шаблонное число — проверьте и скорректируйте вручную.",
                                    date))
        body.append(obj)

    # 3. Способ подключения — полностью дословно
    connection = template.get("connection")
    if connection:
        conn_static, unknown = _fill_placeholders(connection, {"СПОСОБ_ПОДКЛЮЧЕНИЯ": session.connection_method})
        for key in unknown:
            warnings.append(Warning("Шаблон",
                                    f"В разделе «Способ подключения» есть неразрешённый плейсхолдер {{{key}}}.",
                                    date))
        body.append(conn_static)
    if session.connection_method and connection and \
            (session.connection_method.lower().split(",")[0].strip() not in connection.lower()):
        warnings.append(Warning("Способ подключения",
                                "Способ подключения в карте отличается от шаблона — проверьте, какой указать.",
                                date))

    # 4. Течение диализа
    course_tpl = template.get("dialysis_course")
    course = _course_line(course_tpl, session, warnings, date)
    if course:
        body.append(course)

    # 4b. Время диализа — отдельный раздел, если присутствует в шаблоне
    dialysis_time_tpl = template.get("dialysis_time")
    if dialysis_time_tpl:
        dur = session.duration_hours
        dt_values = {}
        if session.start_time and session.end_time:
            dt_values["{ВРЕМЯ_ДИАЛИЗА}"] = f"{session.start_time}–{session.end_time}"
        if dur is not None:
            dt_values["{ДЛИТЕЛЬНОСТЬ}"] = f"{dur:g} ч"
        dt_text, unknown = _fill_placeholders(dialysis_time_tpl, dt_values)
        for key in unknown:
            warnings.append(Warning("Шаблон",
                                    f"В разделе «Время диализа» нет данных для {{{key}}} — проверьте карту.",
                                    date))
        body.append(dt_text)

    # 5. Заместительная терапия
    therapy = _therapy_line(template.get("replacement_therapy"), session, warnings, date)
    if therapy:
        body.append(therapy)

    # 6. Веса
    weights = _weights_lines(template.get("weights"), session, warnings, date)
    if weights:
        body.append(weights)

    # прочие неизвестные разделы шаблона переносим дословно в исходном порядке
    for key in sorted(k for k in template.sections if k.startswith("unknown_")):
        body.append(template.sections[key])

    # --- статус ---
    has_error = bool(missing_sections) or not date
    has_check = bool(warnings)
    if has_error:
        status = STATUS_ERROR
    elif has_check:
        status = STATUS_NEEDS_CHECK
    else:
        status = STATUS_READY

    return Diary(number=number, header_line=header_line, body_lines=body,
                 status=status, warnings=warnings, session=session)
