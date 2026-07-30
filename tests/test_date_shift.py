from datetime import date

from app.pipeline import date_shift


def test_parse_dotted_date():
    assert date_shift.parse_date("14.05.2026") == date(2026, 5, 14)


def test_parse_dashed_date():
    assert date_shift.parse_date("14-05-2026") == date(2026, 5, 14)


def test_parse_iso_date():
    assert date_shift.parse_date("2026-05-14") == date(2026, 5, 14)


def test_parse_textual_date():
    assert date_shift.parse_date("14 maja 2026 r.") == date(2026, 5, 14)


def test_parse_invalid_calendar_date_returns_none():
    assert date_shift.parse_date("31.02.2026") is None


def test_parse_unrecognized_format_returns_none():
    assert date_shift.parse_date("nie data") is None


def test_shift_date_string_preserves_dotted_style():
    assert date_shift.shift_date_string("14.05.2026", 1) == "15.05.2026"


def test_shift_date_string_preserves_dashed_separator():
    assert date_shift.shift_date_string("14-05-2026", 1) == "15-05-2026"


def test_shift_date_string_preserves_iso_style():
    assert date_shift.shift_date_string("2026-05-14", -1) == "2026-05-13"


def test_shift_date_string_preserves_textual_style_with_suffix():
    assert date_shift.shift_date_string("14 maja 2026 r.", 1) == "15 maja 2026 r."


def test_shift_date_string_crosses_month_boundary():
    assert date_shift.shift_date_string("31.05.2026", 1) == "01.06.2026"


def test_shift_date_string_unparseable_value_returned_unchanged():
    assert date_shift.shift_date_string("31.02.2026", 5) == "31.02.2026"
