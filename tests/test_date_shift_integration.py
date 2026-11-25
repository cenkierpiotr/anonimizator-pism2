import random

import pytest

from app.config import AppConfig
from app.pipeline import ner
from app.pipeline.detect_all import anonymize_text


@pytest.fixture(scope="module")
def nlp():
    return ner.load_nlp()


def test_date_left_untouched_by_default(nlp):
    text = "Termin rozprawy wyznaczono na 14.05.2026."
    result, _ = anonymize_text(text, nlp=nlp)
    assert "14.05.2026" in result


def test_date_shifted_when_enabled_and_offset_consistent_within_document(nlp):
    # Losowy offset (patrz IdentityRegistry, zakres +/-365 dni) jest z natury
    # niedeterministyczny - bez ustalonego seeda ten test bywa flaky, bo
    # niektore konkretne wylosowane wartosci (np. -14, dokladnie odstep miedzy
    # dwiema datami w tekscie ponizej) powoduja, ze przesunieta druga data
    # wizualnie pokrywa sie z oryginalna pierwsza data - test wtedy falszywie
    # wykrywa "wyciek" (zaobserwowane w CI 03.08.2026). Seed dobrany tak, by
    # dawac wartosc offsetu bezpieczna dla assercji ponizej.
    random.seed(1)
    config = AppConfig(date_shifting_enabled=True)
    text = (
        "Umowę zawarto w dniu 14.05.2026. Termin płatności upływa 28.05.2026 "
        "- dokładnie 14 dni po zawarciu umowy."
    )
    result, registry = anonymize_text(text, config=config, nlp=nlp)

    assert "14.05.2026" not in result
    assert "28.05.2026" not in result
    assert registry.date_shift_offset_days != 0

    # odstęp między datami (14 dni) musi zostać zachowany mimo przesunięcia
    import re

    from app.pipeline.date_shift import parse_date

    found = re.findall(r"\d{2}\.\d{2}\.\d{4}", result)
    assert len(found) == 2
    shifted_first, shifted_second = (parse_date(d) for d in found)
    assert (shifted_second - shifted_first).days == 14
