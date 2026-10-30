# -*- coding: utf-8 -*-
"""Тесты корректности формирования дневников (регламент ТЗ п. 5, 6, 11).

Запуск:  python -m pytest tests -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.diary_builder import build_diary  # noqa: E402
from app.map_parser import parse_dialysis_map  # noqa: E402
from app.models import STATUS_ERROR, STATUS_NEEDS_CHECK, STATUS_READY, SessionData  # noqa: E402
from app.service import copy_all_text, generate_diaries, save_all_diaries  # noqa: E402
from app.template_parser import parse_template  # noqa: E402
from app.validator import validate_diary  # noqa: E402

EXAMPLE_MAP = ROOT / "examples" / "Карта_диализа.txt"
EXAMPLE_TEMPLATE = ROOT / "examples" / "Шаблон_дневника.txt"

TEMPLATE_TEXT = """Жалобы: на слабость во время сеансов гемодиализа, периодические судороги в икроножных мышцах, головные боли напряжения.
Объективно: Состояние удовлетворительное. Сознание ясное. Кожные покровы обычной окраски, влажные. Периферических отёков нет. Дыхание везикулярное, ЧДД 18 в мин. Тоны сердца ритмичные, АД 150/90 мм рт.ст., ЧСС 80 уд/мин. Живот мягкий, безболезненный. Печень и селезёнка не увеличены.
Способ подключения: АВФ левой верхней конечности (артериовенозная фистула по Банчевскому, операция 12.02.2024), пункция по методу «лески».
Течение диализа: {ТЕЧЕНИЕ_ДИАЛИЗА}
Заместительная терапия: {ЗАМЕСТИТЕЛЬНАЯ_ТЕРАПИЯ}
Веса:
Сухой вес: {СУХОЙ_ВЕС}.
Вес до ГД: {ВЕС_ДО_ГД}.
Вес после ГД: {ВЕС_ПОСЛЕ_ГД}.
"""


def make_session(**kw) -> SessionData:
    s = SessionData(
        date="03.10.2026", start_time="12:00", end_time="16:00", duration_hours=4.0,
        blood_pressure_before="140/85",
        blood_pressure_mid=["135/80", "128/75", "120/70"],
        blood_pressure_after="118/70", heart_rate=78,
        dry_weight=80.0, weight_before=82.4, weight_after=79.8,
        ultrafiltration_volume=2.6, constant_medications=["Эпрекс 4000 МЕ в/в"],
    )
    for k, v in kw.items():
        setattr(s, k, v)
    return s


@pytest.fixture()
def template():
    return parse_template(TEMPLATE_TEXT)


# ---------------------------------------------------------------------------
# Парсер карты
# ---------------------------------------------------------------------------

class TestMapParser:
    def test_splits_sessions_chronologically(self):
        _, sessions = parse_dialysis_map(EXAMPLE_MAP.read_text(encoding="utf-8"))
        assert [s.date for s in sessions] == ["01.10.2026", "03.10.2026", "06.10.2026",
                                              "08.10.2026", "10.10.2026"]

    def test_extracts_fields(self):
        _, sessions = parse_dialysis_map(EXAMPLE_MAP.read_text(encoding="utf-8"))
        s2 = sessions[1]
        assert s2.start_time == "12:00"
        assert s2.blood_pressure_before == "165/95"
        assert s2.blood_pressure_mid == ["160/90", "155/88", "150/85", "145/82"]
        assert s2.blood_pressure_after == "140/80"
        assert s2.heart_rate == 84
        assert s2.weight_before == 83.2 and s2.weight_after == 80.4
        assert s2.ultrafiltration_volume == 2.8
        assert s2.complications == ["артериальная гипертензия", "головная боль"]
        assert len(s2.intradialytic_medications) == 2
        assert len(s2.constant_medications) == 2

    def test_no_sessions_raises(self):
        from app.map_parser import MapParseError
        with pytest.raises(MapParseError):
            parse_dialysis_map("Пациент: кто-то\nПросто текст без сеансов")

    def test_windows1251_file(self, tmp_path):
        from app.textio import read_text_file
        p = tmp_path / "map.txt"
        text = EXAMPLE_MAP.read_text(encoding="utf-8")
        p.write_bytes(text.encode("cp1251"))
        parsed = read_text_file(p)
        assert "Иванов" in parsed
        _, sessions = parse_dialysis_map(parsed)
        assert len(sessions) == 5

    def test_utf8_bom(self, tmp_path):
        from app.textio import read_text_file
        p = tmp_path / "map.txt"
        p.write_bytes(b"\xef\xbb\xbf" + EXAMPLE_MAP.read_text(encoding="utf-8").encode("utf-8"))
        assert "Иванов" in read_text_file(p)


# ---------------------------------------------------------------------------
# Формирование: регламент п. 5
# ---------------------------------------------------------------------------

class TestDiaryRegulations:
    def test_section_order_and_header(self, template):
        d = build_diary(1, make_session(), template)
        lines = d.full_text.split("\n")
        assert lines[0] == "03.10.2026 12:00"  # дата + ВРЕМЯ НАЧАЛА, не окончания
        markers = ["Жалобы:", "Объективно:", "Способ подключения:", "Течение диализа:",
                   "Заместительная терапия", "Веса:"]
        positions = []
        for m in markers:
            idx = next(i for i, ln in enumerate(lines) if ln.startswith(m))
            positions.append(idx)
        assert positions == sorted(positions)

    def test_no_empty_lines_between_sections(self, template):
        d = build_diary(1, make_session(), template)
        assert "\n\n" not in d.full_text

    def test_complaints_verbatim(self, template):
        d = build_diary(1, make_session(), template)
        complaint_line = TEMPLATE_TEXT.splitlines()[0]
        assert complaint_line in d.full_text

    def test_objective_ad_replaced_with_pre_hd(self, template):
        d = build_diary(1, make_session(blood_pressure_before="158/92"), template)
        obj = next(ln for ln in d.full_text.split("\n") if ln.startswith("Объективно:"))
        assert "АД 158/92" in obj
        assert "150/90" not in obj  # шаблонное АД заменено

    def test_hr_only_from_map_never_invented(self, template):
        # ЧСС есть в карте — подставляется измеренное значение
        d = build_diary(1, make_session(heart_rate=91), template)
        obj = next(ln for ln in d.full_text.split("\n") if ln.startswith("Объективно:"))
        assert "ЧСС 91" in obj
        # ЧСС отсутствует — значение НЕ придумывается, предупреждение обязательно
        d2 = build_diary(1, make_session(heart_rate=None), template)
        obj2 = next(ln for ln in d2.full_text.split("\n") if ln.startswith("Объективно:"))
        assert "ЧСС 80" in obj2  # осталось шаблонное, не случайное
        assert any(w.field_name == "ЧСС" for w in d2.warnings)
        assert d2.status == STATUS_NEEDS_CHECK

    def test_bp_sequence_format_four_values(self, template):
        d = build_diary(1, make_session(), template)
        assert "АД 140/85 – 135/80 – 128/75 – 120/70 мм.рт.ст." in d.full_text

    def test_fourth_intermediate_excluded_from_sequence(self, template):
        s = make_session(blood_pressure_mid=["135/80", "128/75", "120/70", "115/68"])
        d = build_diary(1, s, template)
        course = d.full_text
        assert "АД 140/85 – 135/80 – 128/75 – 120/70 мм.рт.ст." in course
        assert "– 115/68" not in course  # 4-е не входит в последовательность
        assert "115/68" in course  # но задокументировано как дополнительное измерение

    def test_ad_after_not_in_sequence(self, template):
        d = build_diary(1, make_session(blood_pressure_after="118/70"), template)
        seq_line = next(ln for ln in d.full_text.split("\n") if ln.startswith("АД 140/85"))
        assert "118/70" not in seq_line.replace("Сеанс", "")

    def test_missing_mid_bp_warning_not_invention(self, template):
        d = build_diary(1, make_session(blood_pressure_mid=["135/80"]), template)
        assert d.status == STATUS_NEEDS_CHECK
        assert any("промежуточн" in w.message.lower() for w in d.warnings)

    def test_no_complications_standard_phrase(self, template):
        d = build_diary(1, make_session(), template)
        assert "Сеанс гемодиализа перенесён удовлетворительно, без дополнительных назначений." in d.full_text

    def test_intradialytic_word_naznachen_only(self, template):
        s = make_session(complications=["артериальная гипотензия, слабость"],
                         notes="в динамике АД повысилось до 105/65")
        s.intradialytic_medications = ["Кофеин бензоат-натрий 10% 2 мл в/в"]
        d = build_diary(1, s, template)
        assert "Назначен Кофеин" in d.full_text
        for forbidden in ("введён", "введено", "дан "):
            assert forbidden not in d.full_text.lower().replace("в/в", "")

    def test_caffeine_requires_documented_hypotension(self, template):
        # препарат есть, гипотензии в карте нет -> причина НЕ придумывается, ручная проверка
        s = make_session(complications=[], notes="")
        s.intradialytic_medications = ["Кофеин бензоат-натрий 10% 2 мл в/в"]
        d = build_diary(1, s, template)
        assert d.status == STATUS_NEEDS_CHECK
        assert any("причины" in w.message for w in d.warnings)

    def test_assignment_without_result_goes_to_manual_check(self, template):
        s = make_session(complications=["артериальная гипертензия"], notes="")
        s.intradialytic_medications = ["Каптоприл 25 мг сублингвально"]
        d = build_diary(1, s, template)
        assert d.status == STATUS_NEEDS_CHECK
        assert any("результата" in w.message for w in d.warnings)

    def test_calcium_only_with_cramps_documented(self, template):
        s = make_session(complications=["судороги в ногах"], notes="в динамике судороги купированы")
        s.intradialytic_medications = ["Кальция хлорид 10% 5 мл в/в"]
        d = build_diary(1, s, template)
        assert "Интрадиализно отмечена судороги в ногах. Назначен Кальция хлорид" in d.full_text

    def test_constant_vs_intradialytic_separated(self, template):
        s = make_session(complications=["артериальная гипертензия"],
                         notes="в динамике АД снизилось")
        s.intradialytic_medications = ["Каптоприл 25 мг"]
        s.constant_medications = ["Эпрекс 4000 МЕ в/в"]
        d = build_diary(1, s, template)
        therapy_line = next(ln for ln in d.full_text.split("\n") if ln.startswith("Заместительная терапия"))
        assert "Эпрекс" in therapy_line
        assert "Каптоприл" not in therapy_line  # интрадиализный — только в течении диализа
        course_idx = d.full_text.index("Течение диализа")
        therapy_idx = d.full_text.index("Заместительная терапия")
        assert course_idx < d.full_text.index("Каптоприл") < therapy_idx

    def test_empty_constant_therapy_exact_phrase(self, template):
        d = build_diary(1, make_session(constant_medications=[]), template)
        assert "Заместительная терапия: (нет дополнительных медикаментов)." in d.full_text

    def test_weights_block_format(self, template):
        d = build_diary(1, make_session(), template)
        assert "Сухой вес: 80,00 кг." in d.full_text
        assert "Вес до ГД: 82,40 кг." in d.full_text
        assert "Вес после ГД: 79,80 кг." in d.full_text

    def test_uf_mismatch_warned_not_fixed(self, template):
        s = make_session(weight_before=82.4, weight_after=79.8, ultrafiltration_volume=4.5)
        d = build_diary(1, s, template)
        validate_diary(d, template.sections)
        assert d.status == STATUS_NEEDS_CHECK
        assert any("Ультрафильтрац" in w.field_name or "УФО" in w.message for w in d.warnings)
        # веса перенесены без изменения
        assert "Вес до ГД: 82,40 кг." in d.full_text
        assert "Вес после ГД: 79,80 кг." in d.full_text

    def test_start_time_not_end_time(self, template):
        s = make_session(start_time="08:00", end_time="12:00")
        d = build_diary(1, s, template)
        assert d.header_line == "03.10.2026 08:00"

    def test_missing_date_is_error(self, template):
        d = build_diary(1, make_session(date=None), template)
        assert d.status == STATUS_ERROR

    def test_template_missing_section_is_error(self):
        bad_tpl = parse_template("Жалобы: только жалобы.\n")
        d = build_diary(1, make_session(), bad_tpl)
        assert d.status == STATUS_ERROR
        assert any("Шаблон" in w.field_name for w in d.warnings)


# ---------------------------------------------------------------------------
# Интеграция с примерами + экспорт
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def test_example_map_generates_five_diaries(self):
        ds = generate_diaries(EXAMPLE_MAP, EXAMPLE_TEMPLATE)
        assert len(ds) == 5
        assert ds[3].status == STATUS_NEEDS_CHECK  # сеанс 4: неполные АД, неподтверждённые назначения
        assert all(d.status != STATUS_ERROR for d in ds)

    def test_template_text_preserved_for_all(self):
        ds = generate_diaries(EXAMPLE_MAP, EXAMPLE_TEMPLATE)
        verbatim = "АВФ левой верхней конечности (артериовенозная фистула по Банчевскому, операция 12.02.2024)"
        for d in ds:
            assert verbatim in d.full_text

    def test_save_all_files_names(self, tmp_path):
        ds = generate_diaries(EXAMPLE_MAP, EXAMPLE_TEMPLATE)
        paths = save_all_diaries(ds, tmp_path)
        names = sorted(p.name for p in paths)
        assert "03.10.2026_Сеанс_2.txt" in names
        assert all(n.endswith(".txt") for n in names)
        content = (tmp_path / "03.10.2026_Сеанс_2.txt").read_text(encoding="utf-8")
        assert content.startswith("03.10.2026 12:00")

    def test_copy_all_has_separators(self):
        ds = generate_diaries(EXAMPLE_MAP, EXAMPLE_TEMPLATE)
        text = copy_all_text(ds)
        assert text.count("========================================") == len(ds) - 1

    def test_source_files_not_modified(self):
        before = EXAMPLE_MAP.read_bytes()
        generate_diaries(EXAMPLE_MAP, EXAMPLE_TEMPLATE)
        assert EXAMPLE_MAP.read_bytes() == before

    def test_no_random_numbers_heart_rate(self):
        # при отсутствии ЧСС в карте два прогона дают идентичный текст (нет генерации)
        s = make_session(heart_rate=None)
        tpl = parse_template(TEMPLATE_TEXT)
        t1 = build_diary(1, s, tpl).full_text
        t2 = build_diary(1, s, tpl).full_text
        assert t1 == t2
