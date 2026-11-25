from app.detectors.land_register import detector, is_valid_kw


def test_valid_kw():
    assert is_valid_kw("WA1M/00000001/8")


def test_invalid_kw_checksum():
    assert not is_valid_kw("WA1M/00000001/7")


def test_find_all_in_text():
    text = "Nieruchomość objęta księgą wieczystą WA1M/00000001/8 położona w..."
    matches = detector.find_all(text)
    assert len(matches) == 1
