# -*- coding: utf-8 -*-
"""Парсер шаблона дневника.

Шаблон — главный источник НЕИЗМЕНЯЕМОГО медицинского текста.
Разделы распознаются по заголовкам вида «Жалобы:», «Объективно:» и т.д.
(заголовок может занимать отдельную строку или начинаться с неё).

Программа не переписывает, не сокращает и не улучшает текст разделов —
он переносится дословно (за исключением полей, прямо разрешённых регламентом).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

SECTION_ALIASES: Dict[str, List[str]] = {
    "complaints": ["жалобы"],
    "objective": ["объективно", "объективный статус", "status praesens objectivus"],
    "connection": ["способ подключения", "подключение"],
    "dialysis_course": ["течение диализа", "течение сеанса", "ход диализа"],
    "replacement_therapy": ["заместительная терапия", "постоянная терапия"],
    "weights": ["веса", "весовые значения", "вес пациента"],
    "dialysis_time": ["время диализа"],
}

_ORDER = ["complaints", "objective", "connection", "dialysis_course",
          "replacement_therapy", "weights"]


@dataclass
class Template:
    """Разобранный шаблон дневника."""

    sections: Dict[str, str] = field(default_factory=dict)  # ключ -> полный текст раздела
    raw_text: str = ""

    def get(self, key: str) -> Optional[str]:
        return self.sections.get(key)

    def missing_required(self) -> List[str]:
        return [k for k in _ORDER if k not in self.sections]


def _canonical_key(label: str) -> Optional[str]:
    low = label.lower().strip().rstrip(":").strip()
    for key, aliases in SECTION_ALIASES.items():
        for alias in aliases:
            if low.startswith(alias):
                return key
    return None


def parse_template(text: str) -> Template:
    """Разбить шаблон на разделы по заголовкам.

    Заголовок раздела — строка (или начало строки), совпадающая с известным
    алиасом и завершающаяся двоеточием либо стоящая отдельной строкой.
    Неизвестные заголовки сохраняются как отдельные «прочие» разделы и
    переносятся в дневник дословно (структура шаблона не ломается).
    """
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    sections: Dict[str, List[str]] = {}
    current_key: Optional[str] = None
    unknown_counter = 0

    header_re = re.compile(r"^\s*([А-Яа-яЁёA-Za-z][А-Яа-яЁёA-Za-z ()\-\.]{1,50}?)\s*:(.*)$")

    for ln in lines:
        stripped = ln.strip()
        key: Optional[str] = None
        remainder: Optional[str] = None

        m = header_re.match(ln)
        if m:
            cand = _canonical_key(m.group(1))
            if cand is not None:
                key, remainder = cand, m.group(2).strip()
            elif stripped.endswith(":") and _looks_like_heading(stripped[:-1]):
                # неизвестный, но похожий на заголовок раздел — сохраняем как есть
                unknown_counter += 1
                key, remainder = f"unknown_{unknown_counter}", ""
                sections.setdefault(key, []).append(stripped)
                current_key = key
                continue

        if key is None and stripped and _is_bare_heading(stripped):
            cand = _canonical_key(stripped)
            if cand is not None:
                key, remainder = cand, ""

        if key is not None:
            header_text = _find_header_text(stripped, key)
            sections.setdefault(key, [])
            if remainder:
                # заголовок и текст на одной строке — сохраняем строку дословно,
                # чтобы переносимый в дневник медицинский текст не изменялся
                sections[key].append(stripped)
            else:
                if header_text:
                    sections[key].append(header_text)
            current_key = key
        else:
            if current_key is None:
                # преамбула шаблона до первого раздела — игнорируется при сборке,
                # но сохраняется во raw_text
                continue
            sections[current_key].append(ln)

    result = Template(raw_text=text)
    for k, v in sections.items():
        # убираем пустые строки внутри раздела, сохраняем текст дословно
        cleaned: List[str] = []
        for line in v:
            if line.strip() == "" and (not cleaned or cleaned[-1].strip() == ""):
                continue
            cleaned.append(line.rstrip())
        while cleaned and cleaned[-1].strip() == "":
            cleaned.pop()
        result.sections[k] = "\n".join(cleaned)
    return result


_HEADING_WORDS = set()
for _aliases in SECTION_ALIASES.values():
    for _a in _aliases:
        _HEADING_WORDS.add(_a.split()[0].lower())


def _looks_like_heading(text: str) -> bool:
    low = text.lower().strip()
    return any(low.startswith(w) for w in _HEADING_WORDS)


def _is_bare_heading(stripped: str) -> bool:
    """Отдельная строка-заголовок без двоеточия («Объективно»)."""
    low = stripped.lower().rstrip(":").strip()
    if len(low) > 60:
        return False
    return _looks_like_heading(low)


def _find_header_text(stripped_line: str, key: str) -> str:
    """Восстановить текст заголовка раздела для дословного переноса."""
    aliases = SECTION_ALIASES.get(key, [])
    low = stripped_line.lower()
    for alias in aliases:
        idx = low.find(alias)
        if idx != -1:
            end = idx + len(alias)
            rest = stripped_line[end:]
            colon = rest.find(":")
            header_end = end + colon + 1 if colon != -1 else end
            return stripped_line[:header_end].rstrip()
    return stripped_line.split(":", 1)[0] + ":"
