# -*- coding: utf-8 -*-
"""Классификация интрадиализных назначений (регламент п. 5.6).

Наличие препарата в карте САМО ПО СЕБЕ не доказывает наличие симптома.
Поэтому для каждого назначения проверяется документированная причина
(осложнение/симптом или цифры АД) и документированный результат («в динамике»).
Если чего-то из этого нет — дневник отправляется на ручную проверку,
программа НЕ придумывает ни причину, ни динамику.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

# ---------------------------------------------------------------------------
# Группы препаратов и признаки документированных показаний
# ---------------------------------------------------------------------------

CAFFEINE = ("кофеин", "кофеину бензоат-натрий", "бензоат-натрий", "cordiamine", "кордиамин")
PAINKILLERS = ("анальгин", "метамизол", "кетотоп", "кетопрофен", "кетонал", "феброфид",
               "флурбипрофен", "баралгин", "спазмалгон")
HYPERTENSION_DRUGS = ("каптоприл", "физиотенз", "клонидин", "коринфар", "нифедипин",
                      "эбрантил", "моксонидин", "сульфат магния", "магния сульфат")
CRAMPS_DRUG = ("кальция хлорид", "кальция глюконат", "хлористый кальций", "calcium")

REASON_GROUPS = {
    "hypotension": ("гипотенз", "снижен", "паден", "артериальная гипотензия"),
    "hypertension": ("гипертенз", "повышен", "артериальная гипертензия"),
    "headache": ("головн", "цефалг"),
    "pain": ("боль", "болевой"),
    "cramps": ("судорог",),
    "weakness_dizziness": ("слабость", "головокружен"),
}

RESULT_RE = re.compile(r"в\s+динамике[:\s]*(.+)", re.IGNORECASE | re.DOTALL)


@dataclass
class MedAssignment:
    """Интрадиализное назначение с проверкой документированности."""

    drug_text: str
    group: Optional[str] = None                 # caffeine/painkillers/hypertension/cramps/other
    reason: Optional[str] = None                # документированнная причина (из карты)
    result: Optional[str] = None                # документированный результат («в динамике …»)
    missing_reason: bool = False
    missing_result: bool = False
    unknown_drug: bool = False                  # препарат не относится к известным группам
    problems: List[str] = field(default_factory=list)

    @property
    def documented(self) -> bool:
        return not self.missing_reason and not self.missing_result and not self.unknown_drug


def classify_drug(drug_text: str) -> Optional[str]:
    low = drug_text.lower()
    if any(k in low for k in CAFFEINE):
        return "caffeine"
    if any(k in low for k in PAINKILLERS):
        return "painkillers"
    if any(k in low for k in HYPERTENSION_DRUGS):
        return "hypertension"
    if any(k in low for k in CRAMPS_DRUG):
        return "cramps"
    return None


def _expected_reason_key(group: Optional[str]) -> Optional[str]:
    return {
        "caffeine": "hypotension",
        "painkillers": "pain",
        "hypertension": "hypertension",
        "cramps": "cramps",
    }.get(group)


def find_documented_reason(group: Optional[str], complications: List[str],
                           notes: str = "") -> Optional[str]:
    """Найти в осложнениях/заметках ДОКУМЕНТИРОВАННУЮ причину для группы препаратов."""
    key = _expected_reason_key(group)
    pool = list(complications) + ([notes] if notes else [])
    if key is None:
        # неизвестная группа: любая документированная жалоба/осложнение подходит как «уточнить»
        for item in pool:
            if item.strip():
                return item.strip().rstrip(".")
        return None
    for item in pool:
        low = item.lower()
        if any(sign in low for sign in REASON_GROUPS[key]):
            return item.strip().rstrip(".")
    # боль допускает и «головную боль»
    if key == "pain":
        for item in pool:
            low = item.lower()
            if any(sign in low for sign in REASON_GROUPS["headache"]):
                return item.strip().rstrip(".")
    if key == "hypotension":
        for item in pool:
            low = item.lower()
            if any(sign in low for sign in REASON_GROUPS["weakness_dizziness"]):
                return item.strip().rstrip(".")
    return None


def extract_result(text: str) -> Optional[str]:
    m = RESULT_RE.search(text or "")
    if not m:
        return None
    res = m.group(1).strip().rstrip(".").split("\n")[0].strip()
    return res or None


def analyze_assignment(drug_text: str, complications: List[str], notes: str,
                       full_block: str = "") -> MedAssignment:
    """Проверить одно интрадиализное назначение по регламенту п. 5.6."""
    a = MedAssignment(drug_text=drug_text.strip())
    a.group = classify_drug(drug_text)
    if a.group is None:
        a.unknown_drug = True
        a.problems.append(
            f"Препарат «{drug_text}» не относится к известным группам — классифицировать однозначно нельзя."
        )
    a.reason = find_documented_reason(a.group, complications, notes)
    if a.reason is None and not a.unknown_drug:
        a.missing_reason = True
        a.problems.append(
            f"Для препарата «{drug_text}» в карте нет документированной причины назначения."
        )
    a.result = extract_result(full_block or notes)
    if a.result is None:
        a.missing_result = True
        a.problems.append(
            f"Для препарата «{drug_text}» нет документированного результата лечения («в динамике …»)."
        )
    return a


def format_assignment(a: MedAssignment) -> str:
    """Сформировать предложение по установленному формату (регламент п. 5.6).

    «Интрадиализно отмечена [причина]. Назначен [препарат]. В динамике [результат]».
    Используется только слово «назначен».
    """
    reason = (a.reason or "").strip()
    # согласование слова «отмечена/отмечено» без изменения смысла
    lead_word = "отмечена"
    low_reason = reason.lower()
    if low_reason.startswith(("снижение", "повышение", "нарушение", "похудение")):
        lead_word = "отмечено"
    parts: List[str] = []
    if reason:
        parts.append(f"Интрадиализно {lead_word} {reason.lower()}")
    else:
        parts.append("Интрадиализно отмечена документированная причина (требуется уточнение)")
    body = a.drug_text.rstrip(".")
    parts.append(f"Назначен {body}")
    if a.result:
        parts.append(f"В динамике {a.result}")
    else:
        parts.append("В динамике — требуется уточнение документированного результата")
    return ". ".join(parts) + "."
